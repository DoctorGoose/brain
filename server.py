#import os
import asyncio
import websockets
import json
from aiohttp import web
from mindflex import MindFlexConnection

class MindFlexServer:
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.connected_clients = set()
        self.mindflex_connection = MindFlexConnection()
        self.app = web.Application()
        self.setup_routes()

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

    async def handle_mindflex_data(self):
        """Handle incoming MindFlex data and broadcast to clients"""
        def callback(data):
            print(data)
            # Convert callback to coroutine and schedule it
            asyncio.create_task(self.broadcast({'event': 'data', 'data': data}))

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.mindflex_connection.read(callback)
            )
        except Exception as e:
            print("Error reading from MindFlex:", e)
            await asyncio.sleep(1)  # Prevent tight loop on error

    async def handle_websocket(self, websocket, path=None):
        """Handle WebSocket connections"""
        self.connected_clients.add(websocket)
        print('Client connected')
        
        try:
            await websocket.send(json.dumps({'event': 'connect', 'data': 'Connected'}))
            
            async for message in websocket:
                # Handle any incoming WebSocket messages here if needed
                pass
                
        except websockets.exceptions.ConnectionClosed:
            print('Client disconnected')
        finally:
            self.connected_clients.remove(websocket)

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

        # Start MindFlex data handling
        mindflex_task = asyncio.create_task(self.handle_mindflex_data())

        print(f'HTTP server listening on http://{self.host}:{self.port}')
        print(f'WebSocket server listening on ws://{self.host}:{self.port + 1}')

        # Run everything concurrently
        await asyncio.gather(
            websocket_server,
            site.start(),
            mindflex_task
        )

if __name__ == '__main__':
    server = MindFlexServer()
    asyncio.run(server.start())