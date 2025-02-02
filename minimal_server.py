import asyncio
import json
from aiohttp import web
import websockets
import numpy as np
import random

# Constants
DEFAULT_PORT = 8080
WEBSOCKET_PORT = 8081
SAMPLING_RATE = 256  # Hz
DURATION = 2  # seconds

class EEGServer:
    def __init__(self, host='127.0.0.1', port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.connected_clients = set()
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        self.app.router.add_get('/', self.handle_index)

    async def handle_index(self, request):
        html = """
        <!DOCTYPE html>
        <html>
          <head>
            <title>EEG Dashboard</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation"></script>
            <style>
              body {
                font-family: Arial, sans-serif;
                text-align: center;
                background-color: #1a1a1a;
                color: #D3D3D3;
              }
              h1 {
                color: #D3D3D3;
                font-size: 28px;
              }
              canvas {
                margin-bottom: 15px;
              }
              .nixie-container {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 20px;
              }
              .nixie-label {
                font-size: 18px;
                margin-top: 5px;
              }
              .nixie-display {
                display: inline-block;
                font-family: "Courier New", Courier, monospace;
                font-size: 50px;
                background: radial-gradient(circle, #ff8c00, #ff4500);
                border-radius: 5px;
                padding: 10px;
                width: 100px;
                text-align: center;
                text-shadow: 0px 0px 10px rgba(255, 165, 0, 0.7);
                margin: 5px;
              }
            </style>
            <script>
              let ws = new WebSocket(ws://${window.location.hostname}:8081);
              let rawSignalChart, powerSpectrumChart;

              ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.event === "data") {
                  // Update truly raw signal
                  rawSignalChart.data.datasets[0].data = data.data.raw_signal;
                  rawSignalChart.update();

                  // Update power spectrum
                  powerSpectrumChart.data.labels = data.data.fft_freqs;
                  powerSpectrumChart.data.datasets[0].data = data.data.power_spectrum;
                  powerSpectrumChart.update();

                  // Update Nixie Tubes
                  document.getElementById("attentionNixie").innerText = data.data.attention;
                  document.getElementById("meditationNixie").innerText = data.data.meditation;
                  document.getElementById("signalStrengthNixie").innerText = data.data.signal_strength;
                }
              };

              window.onload = function () {
                // 🟢 RAW SIGNAL CHART
                const ctx1 = document.getElementById("rawSignalChart").getContext("2d");
                rawSignalChart = new Chart(ctx1, {
                  type: "line",
                  data: {
                    labels: Array.from({ length: 256 }, (_, i) => (i / 256).toFixed(2)), // Time axis
                    datasets: [
                      {
                        label: "Composite EEG Signal",
                        data: [],
                        borderColor: "#10bac0",
                        borderWidth: 4,
                        fill: false,
                        tension: 0.4, // Smooth curves
                      },
                    ],
                  },
                  options: {
                    responsive: true,
                    scales: {
                      x: {
                        title: { display: true, text: "Time (s)" },
                        ticks: { maxTicksLimit: 10 },
                        grid: { display: false },
                      },
                      y: { title: { display: true, text: "Amplitude" }, grid: { display: false } },
                    },
                  },
                });

                // 🔴 POWER SPECTRUM CHART
                const ctx2 = document.getElementById("powerSpectrumChart").getContext("2d");
                powerSpectrumChart = new Chart(ctx2, {
                  type: "line",
                  data: {
                    labels: [],
                    datasets: [
                      {
                        label: "Power Spectrum",
                        data: [],
                        borderColor: "#f52796",
                        borderWidth: 4,
                        fill: false,
                        tension: 0.4,
                      },
                    ],
                  },
                  options: {
                    responsive: true,
                    scales: {
                      x: {
                        title: { display: true, text: "Frequency (Hz)" },
                        type: "logarithmic",
                        ticks: { min: 0.5, max: 50, callback: (value) => value },
                        grid: { display: false },
                      },
                      y: { title: { display: true, text: "Power" }, grid: { display: false } },
                    },
                    plugins: {
                      annotation: {
                        annotations: {
                          delta: { type: "box", xMin: 0.5, xMax: 4, backgroundColor: "rgba(255, 165, 0, 0.2)" },
                          theta: { type: "box", xMin: 4, xMax: 8, backgroundColor: "rgba(255, 165, 0, 0.5)" },
                          alpha: { type: "box", xMin: 8, xMax: 12, backgroundColor: "rgba(255, 0, 0, 0.2)" },
                          beta: { type: "box", xMin: 12, xMax: 30, backgroundColor: "rgba(255, 0, 0, 0.5)" },
                          gamma: { type: "box", xMin: 30, xMax: 50, backgroundColor: "rgba(128, 0, 128, 0.5)" },
                        },
                      },
                    },
                  },
                });
              };
            </script>
          </head>
          <body>
            <h1>Enhanced EEG Dashboard</h1>

            <canvas id="rawSignalChart" width="600" height="300"></canvas>

            <!-- NIXIE TUBES -->
            <div class="nixie-container">
              <div>
                <div class="nixie-display" id="attentionNixie">00</div>
                <div class="nixie-label">Attention</div>
              </div>
              <div>
                <div class="nixie-display" id="meditationNixie">00</div>
                <div class="nixie-label">Meditation</div>
              </div>
              <div>
                <div class="nixie-display" id="signalStrengthNixie">00</div>
                <div class="nixie-label">Signal Strength</div>
              </div>
            </div>

            <canvas id="powerSpectrumChart" width="600" height="300"></canvas>
          </body>
        </html>

        """
        return web.Response(text=html, content_type="text/html")

    async def handle_websocket(self, websocket, path=None):
        self.connected_clients.add(websocket)
        try:
            while True:
                await asyncio.sleep(1)

                # Simulate Power Bands
                power_bands = {
                    "delta": random.uniform(0.5, 1.5),
                    "theta": random.uniform(0.5, 1.5),
                    "low_alpha": random.uniform(0.5, 1.5),
                    "high_alpha": random.uniform(0.5, 1.5),
                    "low_beta": random.uniform(0.5, 1.5),
                    "high_beta": random.uniform(0.5, 1.5),
                    "low_gamma": random.uniform(0.5, 1.5),
                    "high_gamma": random.uniform(0.5, 1.5),
                }

                # Frequency ranges for each band
                band_frequencies = {
                    "delta": (0.5, 4),
                    "theta": (4, 8),
                    "low_alpha": (8, 10),
                    "high_alpha": (10, 12),
                    "low_beta": (12, 18),
                    "high_beta": (18, 30),
                    "low_gamma": (30, 40),
                    "high_gamma": (40, 50),
                }

                # Reconstruct Raw Signal
                t = np.linspace(0, DURATION, int(SAMPLING_RATE * DURATION), endpoint=False)
                raw_signal = np.zeros_like(t)
                for band, power in power_bands.items():
                    freq_range = band_frequencies[band]
                    freq = np.random.uniform(freq_range[0], freq_range[1])
                    phase = np.random.uniform(0, 2 * np.pi)
                    amplitude = power
                    raw_signal += amplitude * np.sin(2 * np.pi * freq * t + phase)

                # Compute Power Spectrum
                fft_vals = np.fft.rfft(raw_signal)
                fft_freqs = np.fft.rfftfreq(len(raw_signal), 1 / SAMPLING_RATE)
                power_spectrum = np.abs(fft_vals) ** 2

                # Send Data
                data = {
                    "event": "data",
                    "data": {
                        "raw_signal": raw_signal.tolist(),
                        "fft_freqs": fft_freqs.tolist(),
                        "power_spectrum": power_spectrum.tolist(),
                        "attention": random.randint(0, 100),  # Simulated attention
                        "meditation": random.randint(0, 100),  # Simulated meditation
                        "signal_strength": random.randint(1, 5),  # Signal strength (1-5 scale)
                    }
                }
                await websocket.send(json.dumps(data))
        except websockets.exceptions.ConnectionClosed:
            print("WebSocket client disconnected.")
        finally:
            self.connected_clients.remove(websocket)

    async def start(self):
        print("Starting WebSocket server...")
        websocket_server = await websockets.serve(self.handle_websocket, self.host, WEBSOCKET_PORT)

        print("Starting HTTP server...")
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        print(f"Server running at http://{self.host}:{self.port}")
        print(f"WebSocket server at ws://{self.host}:{WEBSOCKET_PORT}")

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            print("Shutting down...")

if __name__ == "__main__":
    server = EEGServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("Server stopped.")