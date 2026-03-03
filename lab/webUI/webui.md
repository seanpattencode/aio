from aiohttp import web
import asyncio, subprocess, webbrowser

async def index(r): return web.Response(text=HTML, content_type='text/html')
async def ws(r):
    ws = web.WebSocketResponse(); await ws.prepare(r)
    async for msg in ws:
        t = asyncio.create_subprocess_shell(msg.data, stdout=subprocess.PIPE)
        proc = await t; out, _ = await proc.communicate()
        await ws.send_str(out.decode())
    return ws

app = web.Application(); app.add_routes([web.get('/', index), web.get('/ws', ws)])
webbrowser.open('http://localhost:8080'); web.run_app(app)


import sys, asyncio, os, pty, subprocess; from aiohttp import web
sys.path.extend(['/home/seanpatten/projects/AIOS', '/home/seanpatten/projects/AIOS/core'])

async def page(r): return web.FileResponse('templates/index.html') # Serve Main UI
async def run(r): d=await r.json(); return web.json_response({'out': subprocess.getoutput(d['cmd'])}) # Universal Command Runner

async def term(r):
    ws = web.WebSocketResponse(); await ws.prepare(r); m, s = pty.openpty()
    subprocess.Popen('bash', preexec_fn=os.setsid, stdin=s, stdout=s, stderr=s); os.close(s)
    asyncio.get_event_loop().add_reader(m, lambda: asyncio.create_task(ws.send_str(os.read(m, 1024).decode(errors='ignore'))))
    async for msg in ws: os.write(m, msg.data.encode()) # Two-way PTY Bridge
    return ws

app = web.Application(); app.add_routes([web.get('/', page), web.post('/exec', run), web.get('/ws', term)])
if __name__ == '__main__': web.run_app(app, port=int(sys.argv[2]) if len(sys.argv)>2 else 8080)


from aiohttp import web; import subprocess
# UI: Connects persistent socket on load. Button sends 'ls', measures round-trip time.
async def i(r): return web.Response(text="<script>w=new WebSocket('ws://'+location.host+'/w');w.onmessage=e=>document.body.innerText=e.data+' '+(performance.now()-t).toFixed(2)+'ms'</script><button onclick=\"t=performance.now();w.send('ls -la')\">Run WS</button>", content_type='text/html')

# Server: Reads from socket -> Executes -> Streams back (Persistent)
async def w(r):
    ws=web.WebSocketResponse(); await ws.prepare(r)
    async for m in ws: await ws.send_str(subprocess.getoutput(m.data))
    return ws

app=web.Application(); app.add_routes([web.get('/',i), web.get('/w',w)]); web.run_app(app)


import tornado.ioloop, tornado.web, tornado.websocket, os, pty
H="""<html><head><script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.js"></script><link href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css" rel="stylesheet"></head>
<body><button onclick="x.send('ls -la\\r')">LS</button> <button onclick="x.send('date\\r')">Time</button><div id="t"></div>
<script>t=new Terminal();t.open(document.getElementById('t'));x=new WebSocket('ws://'+location.host+'/s');
x.onmessage=e=>t.write(e.data);t.onData(d=>x.send(d))</script></body></html>"""
class S(tornado.websocket.WebSocketHandler):
    def open(s): p,f=pty.fork(); (os.execvp("bash",["bash"]) if p==0 else (setattr(s,'f',f), tornado.ioloop.IOLoop.current().add_handler(f,lambda f,e:s.write_message(os.read(f,900).decode(errors='ignore')),1)))
    def on_message(s,m): os.write(s.f,m.encode())
if __name__=="__main__": tornado.web.Application([(r"/",tornado.web.RequestHandler,{'get':lambda s:s.write(H)}),(r"/s",S)]).listen(8888); tornado.ioloop.IOLoop.current().start()


import os, pty, asyncio, aiohttp.web as w
async def i(r): return w.Response(text='<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.js"></script><link href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css" rel="stylesheet"><div id="t"></div><script>t=new Terminal();t.open(document.getElementById("t"));s=new WebSocket("ws://"+location.host+"/w");s.onmessage=e=>t.write(e.data);t.onData(d=>s.send(d))</script><button onclick="s.send(\'ls -la\\n\')">LS</button><button onclick="s.send(\'time\\n\')">Time</button>', content_type='text/html')
async def s(r):
    ws=w.WebSocketResponse(); await ws.prepare(r); m,sl=pty.openpty()
    asyncio.create_task(asyncio.create_subprocess_shell('bash', stdin=sl, stdout=sl, stderr=sl)); os.close(sl)
    asyncio.get_event_loop().add_reader(m, lambda: asyncio.create_task(ws.send_str(os.read(m,1024).decode(errors='ignore'))))
    async for msg in ws: os.write(m, msg.data.encode())
    return ws
w.run_app(w.Application().add_routes([w.get('/',i), w.get('/w',s)]))

from flask import Flask, Response; import subprocess, time
app = Flask(__name__)

@app.route('/')
def index():
    return f'''<form method="post"><button name="cmd" value="ls" formaction="/run">Run ls</button></form><pre>{result}</pre>'''

@app.route('/run', methods=['POST'])
def run_ls():
    global result; start = time.time()
    try: out = subprocess.check_output('ls -lart', shell=True).decode()
    except Exception as e: out = str(e)
    end = time.time(); result = f"Execution Time: {end-start:.4f}s\n\n{out}"
    return index()

result = "Click 'Run ls' to execute."
if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)


import streamlit as st, subprocess, time
cmd = st.text_input("Command", "ls")
if st.button("Run"):
    s = time.time(); out = subprocess.getoutput(cmd)
    st.code(out)
    st.write(f"Duration: {time.time()-s}s")


from fastapi import FastAPI; from fastapi.responses import HTMLResponse; import subprocess, time
app = FastAPI()
@app.get("/", response_class=HTMLResponse)
def ui():
    s = time.time(); out = subprocess.getoutput("ls")
    return f"Time: {time.time()-s}s<pre>{out}</pre><button onclick='location.reload()'>ls</button>"
if __name__ == "__main__": import uvicorn; uvicorn.run(app)

import gradio as gr, subprocess, time
def run(cmd):
    s = time.time(); out = subprocess.getoutput(cmd)
    return out, f"{time.time()-s}s"
gr.Interface(run, "text", ["text", "text"], examples=[["ls"]]).launch()

from fastapi import FastAPI; import subprocess, time; from fastapi.responses import HTMLResponse
app = FastAPI()
@app.get("/", response_class=HTMLResponse)
async def run(c: str = "ls"):
    t = time.perf_counter(); out = subprocess.getoutput(c)
    return f"<b>{time.perf_counter()-t:.4f}s</b><pre>{out}</pre><button onclick=\"location.href='/?c=ls'\">ls</button>"
if __name__ == "__main__": import uvicorn; uvicorn.run(app)

from http.server import HTTPServer, BaseHTTPRequestHandler; import subprocess, time
class UI(BaseHTTPRequestHandler):
    def do_GET(self):
        t = time.time(); out = subprocess.getoutput("ls")
        self.send_response(200); self.end_headers()
        self.wfile.write(f"Time: {time.time()-t:.4f}s<pre>{out}</pre><button onclick='location.reload()'>ls</button>".encode())
HTTPServer(('localhost', 8000), UI).serve_forever()



from flask import Flask, request
import subprocess, time
app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    out, t = '', 0
    if request.method == 'POST':
        s = time.time(); out = subprocess.run(request.form['cmd'], shell=True, capture_output=True, text=True).stdout; t = time.time() - s
    return f'<form method=post><input name=cmd value="ls"><button>Run</button></form><pre>{out}</pre><p>{t:.3f}s</p>'

app.run(debug=True)


from flask import Flask, request, render_template_string
import subprocess, time, os

app = Flask(__name__)
HTML = '''<form method="post"><input name="cmd" placeholder="Command"><button>Run</button></form>
<pre>{{output}}</pre><button onclick="location.href='/?cmd=ls'">LS</button>
<button onclick="location.href='/?cmd=date'">Time</button>'''

@app.route('/', methods=['GET', 'POST'])
def run():
    cmd = request.args.get('cmd') or (request.form.get('cmd') if request.method == 'POST' else None)
    output = ''
    if cmd:
        start = time.time()
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=os.getcwd())
        output = f'{result.stdout}\n{result.stderr}\nTime: {time.time()-start:.2f}s'
    return render_template_string(HTML, output=output)

if __name__ == '__main__':
    app.run(debug=True)



from http.server import BaseHTTPRequestHandler,HTTPServer;import urllib.parse,subprocess,datetime
H="<!doctype html><html><meta charset=utf-8><body><input id=c value=ls><button onclick=run(c.value)>run</button><button onclick=run('ls')>ls</button><button onclick=run('time')>time</button><pre id=o></pre><script>run=x=>fetch('/?c='+encodeURIComponent(x)).then(r=>r.text()).then(t=>o.textContent=t)</script></body></html>"
A={"ls":lambda:subprocess.check_output(["ls"],text=True),"time":lambda:datetime.datetime.now().isoformat()}
class S(BaseHTTPRequestHandler):
 def do_GET(s):c=urllib.parse.parse_qs(urllib.parse.urlsplit(s.path).query).get("c",[""])[0];out=H if not c else A.get(c,lambda:"(blocked)")();s.send_response(200);s.send_header("Content-Type","text/html; charset=utf-8" if not c else "text/plain; charset=utf-8");s.end_headers();s.wfile.write(out.encode())
HTTPServer(("127.0.0.1",8000),S).serve_forever()
