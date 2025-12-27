import sys, asyncio, os, pty, subprocess, webbrowser; from aiohttp import web

HTML = '''<!doctype html>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit/lib/xterm-addon-fit.min.js"></script>
<body style="margin:0;height:100vh;background:#000;overflow:hidden">
<div style="position:fixed;bottom:5px;left:50%;transform:translateX(-50%);z-index:9"><button onclick="ws.send('aio\\n')" style="padding:15px 30px;font-size:24px">aio</button><button onclick="ws.send('aio note\\n')" style="padding:15px 30px;font-size:24px">aio note</button><button onclick="location.href='/?'+Date.now()" style="padding:15px 30px;font-size:24px">restart</button></div>
<script>
  const term = new Terminal(), fit = new (FitAddon.FitAddon||FitAddon)(), ws = new WebSocket("ws://"+location.host+"/ws");
  term.loadAddon(fit); term.open(document.body); fit.fit();
  term.onData(d => ws.send(d)); ws.onmessage = e => term.write(e.data); window.onresize = () => fit.fit();
</script>'''

async def page(r): return web.Response(text=HTML, content_type='text/html', headers={'Cache-Control':'no-store'})
async def run(r): d=await r.json(); return web.json_response({'out': subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {d['cmd']}")})

async def term(r):
    ws = web.WebSocketResponse(); await ws.prepare(r); m, s = pty.openpty()
    subprocess.Popen('bash', preexec_fn=os.setsid, stdin=s, stdout=s, stderr=s); os.close(s)
    asyncio.get_event_loop().add_reader(m, lambda: asyncio.create_task(ws.send_str(os.read(m, 1024).decode(errors='ignore'))))
    async for msg in ws: os.write(m, msg.data.encode())
    return ws

app = web.Application(); app.add_routes([web.get('/', page), web.post('/exec', run), web.get('/ws', term)])
if __name__ == '__main__': p=int(sys.argv[1]) if len(sys.argv)>1 else 8080; webbrowser.open(f'http://localhost:{p}'); web.run_app(app, port=p)
