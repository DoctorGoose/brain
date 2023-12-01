import os
from mindflex import MindFlexConnection

from gevent import monkey; monkey.patch_all()
import gevent

from flask_socketio import SocketIO, emit
from flask import Flask, render_template, url_for, copy_current_request_context

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

def broadcast_msg(event, *args):
    socketio.emit(event, args, namespace='/mindflex')

def read_mindflex(connection):
    def broadcast_callback(data):
        print(data)
        broadcast_msg('data', data)
    try:
        connection.read(broadcast_callback)
    except Exception as e:
        print("Error reading from MindFlex:", e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/<path:path>')
def static_file(path):
    return app.send_static_file(path) or app.send_static_file('index.html')

@socketio.on('connect', namespace='/mindflex')
def test_connect():
    print('socketio ready')

@socketio.on('disconnect', namespace='/mindflex')
def test_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    print('Listening on port 8080')
    connection = MindFlexConnection()
    gevent.spawn(read_mindflex, connection)
    socketio.run(app, host='0.0.0.0', port=8080)
