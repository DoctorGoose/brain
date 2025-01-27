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
            <title>Enhanced EEG Dashboard</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation"></script>
            <script>
              let ws = new WebSocket(`ws://${window.location.hostname}:8081`);
              let timeDomainChart, powerSpectrumChart, attentionBar, meditationBar, signalStrengthBar;

              ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.event === "data") {
                  // Update raw signal (time domain)
                  timeDomainChart.data.datasets[0].data = data.data.raw_signal;
                  timeDomainChart.update();

                  // Update power spectrum
                  powerSpectrumChart.data.labels = data.data.fft_freqs;
                  powerSpectrumChart.data.datasets[0].data = data.data.power_spectrum;
                  powerSpectrumChart.update();

                  // Update bars
                  attentionBar.data.datasets[0].data = [data.data.attention];
                  meditationBar.data.datasets[0].data = [data.data.meditation];
                  signalStrengthBar.data.datasets[0].data = [data.data.signal_strength];
                  attentionBar.update();
                  meditationBar.update();
                  signalStrengthBar.update();
                }
              };

              window.onload = function () {
                // Time-domain chart
                const ctx1 = document.getElementById("timeDomainChart").getContext("2d");
                timeDomainChart = new Chart(ctx1, {
                  type: "line",
                  data: {
                    labels: Array.from({ length: 512 }, (_, i) => i / 256), // Time labels
                    datasets: [
                      {
                        label: "Raw Signal",
                        data: [],
                        borderColor: "blue",
                        borderWidth: 2,
                        fill: false,
                      },
                    ],
                  },
                  options: {
                    responsive: true,
                    scales: {
                      x: { title: { display: true, text: "Time (s)" } },
                      y: { title: { display: true, text: "Amplitude" } },
                    },
                  },
                });

                // Power spectrum chart with vertical band lines
                const ctx2 = document.getElementById("powerSpectrumChart").getContext("2d");
                powerSpectrumChart = new Chart(ctx2, {
                  type: "line",
                  data: {
                    labels: [], // Frequencies
                    datasets: [
                      {
                        label: "Power Spectrum",
                        data: [],
                        borderColor: "red",
                        borderWidth: 2,
                        fill: false,
                      },
                    ],
                  },
                  options: {
                    responsive: true,
                    plugins: {
                      annotation: {
                        annotations: {
                          delta: {
                            type: "line",
                            xMin: 4,
                            xMax: 4,
                            borderColor: "black",
                            borderWidth: 1,
                            label: { content: "Delta", enabled: true, position: "end" },
                          },
                          theta: {
                            type: "line",
                            xMin: 8,
                            xMax: 8,
                            borderColor: "black",
                            borderWidth: 1,
                            label: { content: "Theta", enabled: true, position: "end" },
                          },
                          alpha: {
                            type: "line",
                            xMin: 12,
                            xMax: 12,
                            borderColor: "black",
                            borderWidth: 1,
                            label: { content: "Alpha", enabled: true, position: "end" },
                          },
                          beta: {
                            type: "line",
                            xMin: 30,
                            xMax: 30,
                            borderColor: "black",
                            borderWidth: 1,
                            label: { content: "Beta", enabled: true, position: "end" },
                          },
                          gamma: {
                            type: "line",
                            xMin: 50,
                            xMax: 50,
                            borderColor: "black",
                            borderWidth: 1,
                            label: { content: "Gamma", enabled: true, position: "end" },
                          },
                        },
                      },
                    },
                    scales: {
                      x: {
                        title: { display: true, text: "Frequency (Hz)" },
                      },
                      y: { title: { display: true, text: "Power" } },
                    },
                  },
                });

                // Attention bar
                const ctx3 = document.getElementById("attentionBar").getContext("2d");
                attentionBar = new Chart(ctx3, {
                  type: "bar",
                  data: {
                    labels: ["Attention"],
                    datasets: [
                      {
                        label: "Attention",
                        data: [0],
                        backgroundColor: "orange",
                      },
                    ],
                  },
                  options: {
                    responsive: true,
                    indexAxis: "y",
                    scales: { x: { max: 100 } },
                  },
                });

                // Meditation bar
                const ctx4 = document.getElementById("meditationBar").getContext("2d");
                meditationBar = new Chart(ctx4, {
                  type: "bar",
                  data: {
                    labels: ["Meditation"],
                    datasets: [
                      {
                        label: "Meditation",
                        data: [0],
                        backgroundColor: "green",
                      },
                    ],
                  },
                  options: {
                    responsive: true,
                    indexAxis: "y",
                    scales: { x: { max: 100 } },
                  },
                });

                // Signal strength bar
                const ctx5 = document.getElementById("signalStrengthBar").getContext("2d");
                signalStrengthBar = new Chart(ctx5, {
                  type: "bar",
                  data: {
                    labels: ["Signal Strength"],
                    datasets: [
                      {
                        label: "Signal Strength",
                        data: [0],
                        backgroundColor: "blue",
                      },
                    ],
                  },
                  options: {
                    responsive: true,
                    indexAxis: "y",
                    scales: { x: { max: 5 } },
                  },
                });
              };
            </script>
          </head>
          <body>
            <h1>Enhanced EEG Dashboard</h1>

            <canvas id="timeDomainChart" width="800" height="400"></canvas>
            <canvas id="powerSpectrumChart" width="800" height="400"></canvas>

            <h2>Metrics</h2>
            <canvas id="attentionBar" width="300" height="65"></canvas>
            <canvas id="meditationBar" width="300" height="65"></canvas>
            <canvas id="signalStrengthBar" width="300" height="65"></canvas>
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
