#!/bin/bash
cd /home/seanpatten/projects/aio/feature_tests/webUI/candidates

echo "| Candidate | Cold Start (ms) | LS Time (ms) | Lines |"
echo "|-----------|-----------------|--------------|-------|"

benchmark() {
    local name=$1
    local port=$2
    local cmd=$3
    local ls_url=$4

    # Start server and time cold start
    start_time=$(date +%s%3N)
    eval "$cmd" &>/dev/null &
    pid=$!

    # Wait for server to respond (cold start)
    for i in {1..50}; do
        if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port" 2>/dev/null | grep -qE "200|302"; then
            break
        fi
        sleep 0.1
    done
    cold_time=$(($(date +%s%3N) - start_time))

    sleep 0.2

    # Time LS request
    ls_start=$(date +%s%3N)
    response=$(curl -s "$ls_url" 2>/dev/null)
    ls_time=$(($(date +%s%3N) - ls_start))

    # Count lines
    lines=$(echo "$response" | wc -l)

    echo "| $name | $cold_time | $ls_time | $lines |"

    kill $pid 2>/dev/null
    sleep 0.3
}

# Candidate 03 - aiohttp ws timing
benchmark "03 aiohttp-ws" 8003 "python -c \"
from aiohttp import web; import subprocess
async def i(r): return web.Response(text='<h1>CANDIDATE 03</h1>', content_type='text/html')
async def w(r):
    ws=web.WebSocketResponse(); await ws.prepare(r)
    async for m in ws: await ws.send_str(subprocess.getoutput(m.data))
    return ws
app=web.Application(); app.add_routes([web.get('/',i), web.get('/w',w)]); web.run_app(app, port=8003, print=lambda *a:None)
\"" "http://localhost:8003/"

# Candidate 04 - tornado
benchmark "04 tornado" 8004 "python -c \"
import tornado.ioloop, tornado.web
class M(tornado.web.RequestHandler):
    def get(self): self.write('<h1>CANDIDATE 04</h1>')
tornado.web.Application([(r'/',M)]).listen(8004); tornado.ioloop.IOLoop.current().start()
\"" "http://localhost:8004/"

# Candidate 06 - flask
benchmark "06 flask" 8006 "python -c \"
from flask import Flask; import subprocess, time, os
app = Flask(__name__)
import logging; log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
@app.route('/')
def index(): return '<h1>CANDIDATE 06</h1><pre>'+subprocess.getoutput('ls -la')+'</pre>'
app.run(host='0.0.0.0', port=8006)
\"" "http://localhost:8006/"

# Candidate 08 - fastapi
benchmark "08 fastapi" 8008 "python -c \"
from fastapi import FastAPI; from fastapi.responses import HTMLResponse; import subprocess, uvicorn, logging
logging.getLogger('uvicorn').setLevel(logging.ERROR)
app = FastAPI()
@app.get('/', response_class=HTMLResponse)
def ui(): return '<h1>CANDIDATE 08</h1><pre>'+subprocess.getoutput('ls -la')+'</pre>'
uvicorn.run(app, port=8008, log_level='error')
\"" "http://localhost:8008/"

# Candidate 09 - gradio
benchmark "09 gradio" 8009 "python -c \"
import gradio as gr, subprocess
def run(cmd): return subprocess.getoutput(cmd)
gr.Interface(run, 'text', 'text', title='CANDIDATE 09').launch(server_port=8009, quiet=True)
\"" "http://localhost:8009/"

# Candidate 10 - fastapi query
benchmark "10 fastapi-q" 8010 "python -c \"
from fastapi import FastAPI; from fastapi.responses import HTMLResponse; import subprocess, uvicorn, logging
logging.getLogger('uvicorn').setLevel(logging.ERROR)
app = FastAPI()
@app.get('/', response_class=HTMLResponse)
async def run(c: str = 'ls -la'): return '<h1>CANDIDATE 10</h1><pre>'+subprocess.getoutput(c)+'</pre>'
uvicorn.run(app, port=8010, log_level='error')
\"" "http://localhost:8010/?c=ls%20-la"

# Candidate 11 - http.server
benchmark "11 http.server" 8011 "python -c \"
from http.server import HTTPServer, BaseHTTPRequestHandler; import subprocess
class UI(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(('<h1>CANDIDATE 11</h1><pre>'+subprocess.getoutput('ls -la')+'</pre>').encode())
    def log_message(self, *a): pass
HTTPServer(('0.0.0.0', 8011), UI).serve_forever()
\"" "http://localhost:8011/"

# Candidate 12 - flask form
benchmark "12 flask-form" 8012 "python -c \"
from flask import Flask; import subprocess, logging
app = Flask(__name__)
log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
@app.route('/')
def index(): return '<h1>CANDIDATE 12</h1><pre>'+subprocess.getoutput('ls -la')+'</pre>'
app.run(host='0.0.0.0', port=8012)
\"" "http://localhost:8012/"

# Candidate 13 - flask template
benchmark "13 flask-tpl" 8013 "python -c \"
from flask import Flask; import subprocess, logging
app = Flask(__name__)
log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
@app.route('/')
def run(): return '<h1>CANDIDATE 13</h1><pre>'+subprocess.getoutput('ls -la')+'</pre>'
app.run(host='0.0.0.0', port=8013)
\"" "http://localhost:8013/"

# Candidate 14 - http.server buttons
benchmark "14 http-btn" 8014 "python -c \"
from http.server import BaseHTTPRequestHandler,HTTPServer; import subprocess
class S(BaseHTTPRequestHandler):
    def do_GET(s): s.send_response(200); s.end_headers(); s.wfile.write(('<h1>CANDIDATE 14</h1><pre>'+subprocess.getoutput('ls -la')+'</pre>').encode())
    def log_message(self, *a): pass
HTTPServer(('0.0.0.0',8014),S).serve_forever()
\"" "http://localhost:8014/"
