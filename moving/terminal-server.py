#!/usr/bin/env python3
import asyncio, websockets, json, pty, os, struct, fcntl, termios
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread

class HTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.getcwd(), **kwargs)
    def log_message(self, *args): pass

async def client_handler(ws):
    master, slave = pty.openpty()
    winsize = struct.pack('HHHH', 24, 80, 0, 0)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
    proc = await asyncio.create_subprocess_exec('bash', stdin=slave, stdout=slave, stderr=slave, preexec_fn=os.setsid)
    os.close(slave)
    os.set_blocking(master, False)
    loop = asyncio.get_event_loop()
    def read_output():
        try:
            data = os.read(master, 65536)
            if data: asyncio.create_task(ws.send(data))
        except (OSError, BlockingIOError): pass
    loop.add_reader(master, read_output)
    try:
        async for msg in ws:
            if isinstance(msg, bytes):
                try:
                    data = json.loads(msg.decode('utf-8'))
                    if 'resize' in data:
                        size = data['resize']
                        winsize = struct.pack('HHHH', size['rows'], size['cols'], 0, 0)
                        fcntl.ioctl(master, termios.TIOCSWINSZ, winsize)
                        if 'term' in data: os.environ['TERM'] = data['term']
                except: os.write(master, msg)
    finally:
        loop.remove_reader(master)
        proc.terminate()
        await proc.wait()
        os.close(master)

async def main():
    Thread(target=lambda: HTTPServer(('', 8700), HTTPHandler).serve_forever(), daemon=True).start()
    print("Terminal Server\nHTTP: http://localhost:8700\nWebSocket: ws://localhost:8766")
    async with websockets.serve(client_handler, 'localhost', 8766):
        await asyncio.Future()

if __name__ == '__main__': asyncio.run(main())
