#!/usr/bin/env python3
import asyncio
import datetime
import json
import sys
import time

from aiohttp import web
import websockets
import serial


###############################################################################
# MindFlex connection class
###############################################################################
DEBUG = True
VERBOSE = True  # Verbose mode provides more raw EEG updates
DEFAULT_PORT = 'COM3'
BAUD_RATE = 9600

MAX_PACKET_LEN = 169
RESET_CODE = b'\x00\xF8\x00\x00\x00\xE0'

# Power band labels for the 8 EEG power values in MindFlex packets
BAND_LABELS = [
    "delta",      # ret['eeg'][0]
    "theta",      # ret['eeg'][1]
    "lowAlpha",   # ret['eeg'][2]
    "highAlpha",  # ret['eeg'][3]
    "lowBeta",    # ret['eeg'][4]
    "highBeta",   # ret['eeg'][5]
    "lowGamma",   # ret['eeg'][6]
    "midGamma"    # ret['eeg'][7]
]

def mf_parser(packet):
    """
    Parse a MindFlex packet according to the MindSet communications protocol.
    """
    ret = {}
    i = 1  # The first byte in the list was packet_len, so start at i = 1
    while (i < len(packet) - 1):
        code_level = packet[i] if isinstance(packet[i], int) else ord(packet[i])
        # signal quality
        if code_level == 0x02:
            ret['quality'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
            i += 2
        # attention
        elif code_level == 0x04:
            ret['attention'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
            i += 2
        # meditation
        elif code_level == 0x05:
            ret['meditation'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
            i += 2
        # EEG power (8 frequency bands)
        elif code_level == 0x83:
            raw_eeg = []
            for c in range(i + 1, i + 25, 3):
                v1 = packet[c] if isinstance(packet[c], int) else ord(packet[c])
                v2 = packet[c + 1] if isinstance(packet[c + 1], int) else ord(packet[c + 1])
                v3 = packet[c + 2] if isinstance(packet[c + 2], int) else ord(packet[c + 2])
                raw_eeg.append((v1 << 16) | (v2 << 8) | v3)
            i += 26
            # Convert the raw list of 8 power values into a dict
            eeg_dict = {}
            for idx, val in enumerate(raw_eeg):
                eeg_dict[BAND_LABELS[idx]] = val
            ret['eeg'] = eeg_dict
        # Raw Wave Value (less commonly used)
        elif code_level == 0x80:
            v1 = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
            v2 = packet[i + 2] if isinstance(packet[i + 2], int) else ord(packet[i + 2])
            ret['eeg_raw'] = (v1 << 8) | v2
            i += 4
        else:
            # If we encounter an unknown code, skip it (prevents infinite loop).
            i += 1
    return ret


class MindFlexConnection:
    """
    Manages the raw serial connection to the MindFlex device, reading
    EEG data in a loop and calling 'callback' with parsed results.
    """
    def __init__(self, port=DEFAULT_PORT, debug=DEBUG, verbose=VERBOSE):
        self.debug = debug
        self.verbose = verbose
        self.port = port

        # Attempt to open serial connection
        print(f"[DEBUG] Opening serial port {self.port} at {BAUD_RATE} baud...")
        self.ser = serial.Serial(port=self.port, baudrate=BAUD_RATE)
        if self.debug:
            print(f"[DEBUG] Serial connection open on {self.port}")

    def close(self):
        """Close the serial port if open."""
        if self.ser.isOpen():
            try:
                self.ser.close()
            except Exception:
                pass
            if self.debug:
                print('[DEBUG] Connection closed')

    def read(self, callback):
        """
        Continuously read from the MindFlex headset. For each valid packet,
        parse it and pass the result to 'callback'.
        """
        # Send RESET_CODE to switch to Mode 2
        print("[DEBUG] Sending RESET_CODE to switch MindFlex to Mode 2...")
        self.ser.write(RESET_CODE)
        time.sleep(0.001)  # Short pause after sending RESET_CODE

        prev_byte = b'c'
        in_packet = False
        mode_2_confirmed = False

        checksum_total = 0
        packet = []

        try:
            while True:
                if self.ser.in_waiting == 0:
                    # Sleep very briefly so we don't spin CPU at 100%
                    time.sleep(0.001)
                    continue
                if self.ser.in_waiting:
                  cur_byte = self.ser.read(1)
                  print(f"[DEBUG] Raw byte: {cur_byte}")

                cur_byte = self.ser.read(1)

                # Confirm Mode 2 activation
                if not mode_2_confirmed:
                    # The moment we see a byte that's not 0xE0, we declare "Mode 2 enabled"
                    if cur_byte != b'\xE0':
                        print('[DEBUG] Mode 2 enabled (first non-0xE0 byte seen)')
                        mode_2_confirmed = True
                    continue

                # Look for the start of the packet (AA AA)
                if not in_packet and prev_byte == b'\xAA' and cur_byte == b'\xAA':
                    in_packet = True
                    packet = []
                    checksum_total = 0
                elif in_packet:
                    if len(packet) == 0:
                        # The first byte after AA AA is the packet length
                        if cur_byte == b'\xAA':
                            # Another 0xAA byte? Keep waiting for length
                            pass
                        else:
                            packet_len = cur_byte[0]
                            packet = [packet_len]
                            checksum_total = 0
                            if packet_len >= MAX_PACKET_LEN:
                                if self.debug:
                                    print('[DEBUG] Packet too long:', packet_len)
                                in_packet = False
                    elif len(packet) - 1 == packet[0]:
                        # We are now at the checksum byte
                        packet_checksum = cur_byte[0]
                        in_packet = False
                        if (~(checksum_total & 0xFF) & 0xFF) == packet_checksum:
                            try:
                                # Parse the packet
                                ret = mf_parser(packet)
                                if self.debug:
                                    print(f"[DEBUG] Parsed: {ret}")
                                callback(ret)
                            except Exception as e:
                                print('[DEBUG] Could not parse because of', e)
                        else:
                            if self.debug:
                                print('[DEBUG] Warning: invalid checksum')
                        packet = []
                    else:
                        # Add byte to packet and update checksum
                        byte_value = cur_byte[0]
                        checksum_total += byte_value
                        packet.append(byte_value)

                # Keep track of the previous byte (for detecting AA AA)
                prev_byte = cur_byte

        except KeyboardInterrupt:
            self.close()
            if self.debug:
                print('[DEBUG] Exiting read loop')
            sys.exit(0)


###############################################################################
# Single-file Web server + WebSocket server
###############################################################################
class MindFlexServer:
    def __init__(self, host='0.0.0.0', port=8080, serial_port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.serial_port = serial_port

        # Keep track of WebSocket clients
        self.connected_clients = set()

        # Create the aiohttp application
        self.app = web.Application()
        self.setup_routes()

        # File to log raw data if you want (optional)
        self.output_file = open("mindflex_data.csv", "w")
        self.output_file.write("Timestamp,Data\n")  # CSV header

        # Initialize MindFlex
        print(f"[DEBUG] Creating MindFlexConnection on port {self.serial_port}...")
        self.mindflex_connection = MindFlexConnection(
            port=self.serial_port,
            debug=True,
            verbose=True
        )

    def setup_routes(self):
        """
        Setup HTTP routes. We serve the index page that has two flot charts:
        one for attention/meditation, another for the 8 EEG bands.
        """
        self.app.router.add_get('/', self.serve_index)

    ############################################################################
    # Embedded index.html
    ############################################################################
    index_html = r"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>MindFlex EEG</title>
    <!-- Pull jQuery from CDN -->
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <!-- Pull Flot from CDN -->
    <script src="https://cdn.jsdelivr.net/npm/flot@4.2.2/dist/es5/jquery.flot.js"></script>
    <style>
      .connection {
        padding: 1em;
      }
      .good {
        background: green;
        color: white;
      }
      .bad {
        background: red;
        color: white;
      }
      .content {
        width: 700px;
        margin: 3% auto;
      }
      #quality {
        margin-bottom: 1em;
      }
      .chart-container {
        margin: 2em 0;
      }
    </style>
    <script>
      $(function() {
        // Open WebSocket
        var ws = new WebSocket(`ws://${window.location.hostname}:8081`);

        // Our Flot graph for attention/meditation
        var attMedOptions = {
          series: { shadowSize: 0 },
          yaxis: { min: 0, max: 100 },
          xaxis: { show: false }
        };

        // Our Flot graph for the 8 EEG bands
        var bandOptions = {
          series: { shadowSize: 0 },
          yaxis: { min: 0 },
          xaxis: { ticks: [
            [0, "delta"], [1, "theta"], [2, "lowAlpha"], [3, "highAlpha"],
            [4, "lowBeta"], [5, "highBeta"], [6, "lowGamma"], [7, "midGamma"]
          ] }
        };

        // Rolling arrays for attention/meditation
        var attentionData = Array(300).fill(0);
        var meditationData = Array(300).fill(0);

        // For the 8 EEG bands, we just keep the most recent value
        var bandValues = [0,0,0,0,0,0,0,0];

        // Create the attention/meditation plot
        var attMedPlot = $.plot($('#attMedGraph'), [
          { data: enumerate(attentionData), label: 'Attention' },
          { data: enumerate(meditationData), label: 'Meditation' }
        ], attMedOptions);

        // Create the band plot (bar style).
        // We'll store data as [ [0,val0], [1,val1], ..., [7,val7] ].
        var bandPlotData = bandValues.map(function(val,i){ return [i, val]; });
        var bandPlot = $.plot('#bandGraph', [{ data: bandPlotData, bars: { show: true } }], bandOptions);

        function enumerate(array) {
          var res = [];
          for (var i = 0; i < array.length; ++i) {
            res.push([i, array[i]]);
          }
          return res;
        }

        // WebSocket event handlers
        ws.onopen = function() {
          console.log('[WS] connected!');
        };

        ws.onmessage = function(event) {
          var message = JSON.parse(event.data);

          // If the event is "connect", mark status as connected
          if (message.event === 'connect') {
            $('#quality')
              .attr('class', 'good connection')
              .html('Connected (no data yet)');
            return;
          }

          // If we got EEG data, update UI
          if (message.event === 'data') {
            var data = message.data;

            // If we see "quality" in data
            var quality = data.quality !== undefined ? data.quality : 200;
            var qualityPercent = (200 - quality) / 2;
            if (quality < 60) {
              $('#quality')
                .attr('class', 'good connection')
                .text('Connected (' + qualityPercent.toFixed(0) + '%)');
            } else {
              $('#quality')
                .attr('class', 'bad connection')
                .text('Poor signal (' + qualityPercent.toFixed(0) + '%)');
            }

            // Update attention/meditation
            if (data.attention !== undefined) {
              attentionData.shift();
              attentionData.push(data.attention);
            }
            if (data.meditation !== undefined) {
              meditationData.shift();
              meditationData.push(data.meditation);
            }
            attMedPlot.setData([
              { data: enumerate(attentionData), label: 'Attention' },
              { data: enumerate(meditationData), label: 'Meditation' }
            ]);
            attMedPlot.draw();

            // If we got EEG band data (eight bands)
            if (data.eeg) {
              var bands = data.eeg;
              // Order is: delta, theta, lowAlpha, highAlpha, lowBeta, highBeta, lowGamma, midGamma
              // Turn them into an array in that order
              bandValues = [
                bands.delta || 0,
                bands.theta || 0,
                bands.lowAlpha || 0,
                bands.highAlpha || 0,
                bands.lowBeta || 0,
                bands.highBeta || 0,
                bands.lowGamma || 0,
                bands.midGamma || 0
              ];
              // Convert to flot-friendly data
              bandPlotData = bandValues.map(function(val, i) { return [i, val]; });
              bandPlot.setData([{ data: bandPlotData, bars: { show: true } }]);
              bandPlot.setupGrid();
              bandPlot.draw();
            }
          }
        };

        ws.onerror = function(error) {
          console.log('[WS] error:', error);
          $('#quality')
            .attr('class', 'bad connection')
            .text('Connection error');
        };

        ws.onclose = function() {
          console.log('[WS] disconnected');
          $('#quality')
            .attr('class', 'bad connection')
            .text('Disconnected');
          // Auto-reload in 5s to attempt reconnect
          setTimeout(function() { location.reload(); }, 5000);
        };

        function updateLoop() {
          // We could do something periodically, if needed
          setTimeout(updateLoop, 1000);
        }
        updateLoop();
      });
    </script>
  </head>
  <body>
    <div class="content">
      <h1>MindFlex EEG Dashboard</h1>
      <div id="quality" class="bad connection">Disconnected</div>

      <div class="chart-container">
        <h2>Attention &amp; Meditation</h2>
        <div id="attMedGraph" style="width: 600px; height: 300px;"></div>
      </div>

      <div class="chart-container">
        <h2>8 EEG Frequency Bands (Bar Chart)</h2>
        <div id="bandGraph" style="width: 600px; height: 300px;"></div>
      </div>

    </div>
  </body>
</html>
"""

    async def serve_index(self, request):
        """
        Serve our embedded index.html as a simple web.Response.
        """
        return web.Response(text=self.index_html, content_type='text/html')

    async def broadcast(self, message):
        """
        Broadcast a JSON-serializable object to all connected clients.
        """
        if self.connected_clients:
            await asyncio.gather(
                *[client.send(json.dumps(message)) for client in self.connected_clients]
            )

    def log_data(self, packet):
        """
        Example: log raw packet data to a CSV. This is optional.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        packet_str = ','.join(str(byte) for byte in packet)
        output_line = f"{timestamp},{packet_str}\n"
        print(output_line, end='')  # Print to console
        self.output_file.write(output_line)
        self.output_file.flush()

    async def handle_mindflex_data(self):
        """
        Reads data from MindFlex in a background thread (via run_in_executor)
        and broadcasts EEG info to the WebSocket clients.
        """
        def callback(data):
            # This is called by the MindFlex read() thread each time a full packet is parsed
            # Print the data for debugging
            print(f"[DEBUG] Received MindFlex data callback: {data}")

            # Enqueue broadcast back on the asyncio loop
            asyncio.create_task(self.broadcast({'event': 'data', 'data': data}))

        try:
            loop = asyncio.get_running_loop()
            # Run the blocking read() in a thread pool executor
            print("[DEBUG] Starting MindFlex read in executor...")
            await loop.run_in_executor(None, lambda: self.mindflex_connection.read(callback))
        except Exception as e:
            print("[DEBUG] Error reading from MindFlex:", e)
            await asyncio.sleep(1)

    async def handle_websocket(self, websocket, path=None):
        """
        Handle a new WebSocket connection from the browser.
        """
        self.connected_clients.add(websocket)
        print('[DEBUG] Client connected over WebSocket')
        try:
            # Immediately let the client know they're connected
            await websocket.send(json.dumps({'event': 'connect', 'data': 'Connected'}))

            # If the client sends messages, you can handle them here
            async for _message in websocket:
                pass

        except websockets.exceptions.ConnectionClosed:
            print('[DEBUG] Client disconnected')
        finally:
            self.connected_clients.remove(websocket)

    async def cleanup(self):
        """
        Cleanup resources (close file, close serial).
        """
        print("[DEBUG] Cleaning up server...")
        self.output_file.close()
        self.mindflex_connection.close()

    async def start(self):
        """
        Start both the HTTP (aiohttp) server and the WebSocket server,
        plus the background MindFlex reading task.
        """
        # Start the WebSocket server (port= self.port + 1)
        ws_server = websockets.serve(self.handle_websocket, self.host, self.port + 1)

        # Start the HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)

        # Background task to read from MindFlex
        mindflex_task = asyncio.create_task(self.handle_mindflex_data())

        print(f"[DEBUG] HTTP server listening on http://{self.host}:{self.port}")
        print(f"[DEBUG] WebSocket server listening on ws://{self.host}:{self.port + 1}")

        # Run everything concurrently
        await asyncio.gather(ws_server, site.start(), mindflex_task)


###############################################################################
# Main entry point
###############################################################################
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='MindFlex WebSocket Server (All-in-one)')
    parser.add_argument('--serial-port', '-p', default=DEFAULT_PORT,
                        help="MindFlex serial port (e.g. COM3 or /dev/ttyUSB0)")
    parser.add_argument('--host', default='0.0.0.0', help="Host/IP for the server")
    parser.add_argument('--web-port', type=int, default=8080,
                        help="Port for the HTTP server (WebSocket uses web-port+1)")

    args = parser.parse_args()

    server = MindFlexServer(
        host=args.host,
        port=args.web_port,
        serial_port=args.serial_port
    )
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\nShutting down server...")
