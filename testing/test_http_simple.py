#!/usr/bin/env python3
"""Simple HTTP server test"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
import time
import urllib.request

class TestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/test":
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body>TEST_OK</body></html>")
            return
        self.send_response(404)
        self.end_headers()
    def log_message(self, *args): pass

print("Starting HTTP server on port 7681...")
def run_server():
    httpd = HTTPServer(('localhost', 7681), TestHandler)
    print("Server started")
    httpd.serve_forever()

t = Thread(target=run_server, daemon=True)
t.start()
time.sleep(2)

print("Testing HTTP server...")
try:
    response = urllib.request.urlopen("http://localhost:7681/test")
    content = response.read().decode()
    if "TEST_OK" in content:
        print("✓ HTTP server working!")
    else:
        print("✗ Unexpected content:", content)
except Exception as e:
    print(f"✗ Failed: {e}")

time.sleep(1)
