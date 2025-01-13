import asyncio
import websockets
import json
import serial
#import sys
import datetime
from aiohttp import web
#import os

# Constants
DEFAULT_PORT = 'COM3'
BAUD_RATE = 57600
MAX_PACKET_LEN = 169
RESET_CODE = b'\x00\xF8\x00\x00\x00\xE0'

class MindFlexServer:
    def __init__(self, host='0.0.0.0', port=8080, serial_port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.serial_port = serial_port
        self.connected_clients = set()
        self.app = web.Application()
        self.setup_routes()
        
        # Initialize data logging
        self.output_file = open("mindflex_data.csv", "w")
        self.output_file.write("Timestamp,Data\n")  # CSV header

    def setup_routes(self):
        """Setup HTTP routes for serving static files"""
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/{path:.*}', self.handle_static)

    async def handle_index(self, request):
        """Serve index.html"""
        return web.FileResponse('templates/index.html')

    async def handle_static(self, request):
        """Serve static files"""
        path = request.match_info['path']
        try:
            return web.FileResponse(f'static/{path}')
        except:
            return web.FileResponse('static/index.html')

    async def broadcast(self, message):
        """Broadcast message to all connected clients"""
        if self.connected_clients:
            await asyncio.gather(
                *[client.send(json.dumps(message)) for client in self.connected_clients]
            )

    def log_data(self, packet):
        """Log data to CSV file"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        packet_str = ','.join([f"{byte}" for byte in packet])
        output_line = f"{timestamp},{packet_str}\n"
        print(output_line, end='')  # Print to console
        self.output_file.write(output_line)
        self.output_file.flush()  # Ensure data is written immediately

    def parse_packet(self, packet):
        """Parse MindFlex packet data"""
        try:
            ret = {}
            i = 1
            while i < len(packet) - 1:
                code_level = packet[i] if isinstance(packet[i], int) else ord(packet[i])
                if code_level == 0x02:
                    ret['quality'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
                    i += 2
                elif code_level == 0x04:
                    ret['attention'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
                    i += 2
                elif code_level == 0x05:
                    ret['meditation'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
                    i += 2
                elif code_level == 0x83:
                    ret['eeg'] = []
                    for c in range(i + 1, i + 25, 3):
                        v1 = packet[c] if isinstance(packet[c], int) else ord(packet[c])
                        v2 = packet[c + 1] if isinstance(packet[c + 1], int) else ord(packet[c + 1])
                        v3 = packet[c + 2] if isinstance(packet[c + 2], int) else ord(packet[c + 2])
                        ret['eeg'].append(v1 << 16 | v2 << 8 | v3)
                    i += 26
                elif code_level == 0x80:
                    v1 = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
                    v2 = packet[i + 2] if isinstance(packet[i + 2], int) else ord(packet[i + 2])
                    ret['eeg_raw'] = v1 << 8 | v2
                    i += 4
            return ret
        except Exception as e:
            print(f"Error parsing packet: {e}")
            return None

    async def handle_serial(self):
        """Handle serial port communication with MindFlex"""
        ser = serial.Serial(port=self.serial_port, baudrate=BAUD_RATE)
        print(f'Serial connection opened on {self.serial_port}')
        
        try:
            prev_byte = b'c'
            in_packet = False
            packet = []

            while True:
                if ser.in_waiting:
                    cur_byte = ser.read(1)
                    print(f'Received byte: {cur_byte}')  # Debug output

                    if cur_byte == b'\xAA' and prev_byte == b'\xAA':
                        print('Start of new packet detected')
                        in_packet = True
                        packet = [cur_byte]
                        continue
                    elif in_packet:
                        packet.append(cur_byte)
                        if len(packet) > MAX_PACKET_LEN:
                            print('Packet too long, resetting')
                            in_packet = False
                            packet = []
                        elif cur_byte == b'\xAA' and packet[-2] == b'\xAA':
                            print('End of packet detected')
                            # Log raw data
                            self.log_data(packet)
                            # Parse and broadcast to WebSocket clients
                            parsed_data = self.parse_packet(packet)
                            if parsed_data:
                                await self.broadcast({
                                    'event': 'data',
                                    'timestamp': datetime.datetime.now().isoformat(),
                                    'data': parsed_data
                                })
                            in_packet = False
                            packet = []
                    prev_byte = cur_byte
                else:
                    await asyncio.sleep(0.001)  # Prevent CPU spinning

        except Exception as e:
            print(f"Serial error: {e}")
        finally:
            ser.close()
            print('Serial connection closed')

    async def handle_websocket(self, websocket, path=None):
        """Handle WebSocket connections"""
        self.connected_clients.add(websocket)
        print('Client connected')
        
        try:
            await websocket.send(json.dumps({
                'event': 'connect',
                'data': 'Connected to MindFlex server'
            }))
            
            async for message in websocket:
                # Handle any incoming WebSocket messages if needed
                pass
                
        except websockets.exceptions.ConnectionClosed:
            print('Client disconnected')
        finally:
            self.connected_clients.remove(websocket)

    async def cleanup(self):
        """Cleanup resources"""
        self.output_file.close()

    async def start(self):
        """Start the WebSocket server and web application"""
        # Start WebSocket server
        websocket_server = websockets.serve(
            self.handle_websocket, 
            self.host, 
            self.port + 1  # WebSocket on port 8081
        )

        # Start web server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)  # HTTP on port 8080

        print(f'HTTP server listening on http://{self.host}:{self.port}')
        print(f'WebSocket server listening on ws://{self.host}:{self.port + 1}')

        try:
            # Run everything concurrently
            await asyncio.gather(
                websocket_server,
                site.start(),
                self.handle_serial()
            )
        finally:
            await self.cleanup()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='MindFlex WebSocket Server')
    parser.add_argument('--port', '-p', default=DEFAULT_PORT)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--web-port', type=int, default=8080)
    args = parser.parse_args()

    server = MindFlexServer(
        host=args.host,
        port=args.web_port,
        serial_port=args.port
    )
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\nShutting down server...")