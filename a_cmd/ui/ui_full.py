import sys, asyncio, os, pty, subprocess, webbrowser, struct, fcntl, termios, json; from aiohttp import web

HTML = '''<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit/lib/xterm-addon-fit.min.js"></script>
<body style="margin:0;height:100vh;background:#000;overflow:hidden">
<div id=t style="height:calc(100vh - 140px)"></div>
<div style="position:fixed;bottom:0;left:0;right:0;height:140px;padding:10px;box-sizing:border-box;background:#1a1a2e;border-top:2px solid #4a4a6a;display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px">
  <input id=i autofocus placeholder="command" style="width:100%;padding:18px;font-size:20px;background:#0d0d1a;color:#fff;border:2px solid #4a4a6a;border-radius:8px;outline:none;box-sizing:border-box"
    onkeydown="if(event.key==='Enter'){ws.send(this.value+'\\n');this.value='';}">
  <button onclick="ws.send(i.value+'\\n');i.value='';i.focus()" style="flex:1;padding:18px;font-size:22px;min-width:60px">▶</button>
  <button onclick="ws.send('aio\\n')" style="flex:1;padding:18px;font-size:22px;min-width:60px">aio</button>
  <button onclick="ws.send('aio note '+i.value+'\\n');i.value='';i.focus()" style="flex:1;padding:18px;font-size:22px;min-width:60px">note</button>
  <button onclick="fetch('/restart');(c=()=>fetch('/').then(()=>location.reload()).catch(()=>setTimeout(c,50)))()" style="flex:1;padding:18px;font-size:22px;min-width:60px">↻</button>
</div>
<script>
  const term = new Terminal(), fit = new (FitAddon.FitAddon||FitAddon)(), ws = new WebSocket("ws://"+location.host+"/ws");
  term.loadAddon(fit); term.open(t);
  const sendSize = () => ws.readyState===1 && ws.send(JSON.stringify({cols:term.cols,rows:term.rows}));
  const doFit = () => { fit.fit(); sendSize(); };
  new ResizeObserver(doFit).observe(t);
  ws.onopen = doFit; term.onData(d => ws.send(d)); ws.onmessage = e => term.write(e.data);
</script>'''

async def page(r): return web.Response(text=HTML, content_type='text/html', headers={'Cache-Control':'no-store'})
async def exec_cmd(r): d=await r.json(); return web.json_response({'out': subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {d['cmd']}")})

async def restart(r): os.execv(sys.executable, [sys.executable] + sys.argv)
async def term(r):
    ws = web.WebSocketResponse(); await ws.prepare(r); m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 180, 0, 0))  # Large default size
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    env['TERM'] = 'xterm-256color'
    subprocess.Popen(['bash'], preexec_fn=os.setsid, stdin=s, stdout=s, stderr=s, env=env); os.close(s)
    asyncio.get_event_loop().add_reader(m, lambda: asyncio.create_task(ws.send_str(os.read(m, 4096).decode(errors='ignore'))))
    async for msg in ws:
        try:
            d = json.loads(msg.data)
            if 'cols' in d and 'rows' in d: fcntl.ioctl(m, termios.TIOCSWINSZ, struct.pack('HHHH', d['rows'], d['cols'], 0, 0)); continue
        except: pass
        os.write(m, msg.data.encode())
    return ws

N='<meta name=viewport content="width=device-width"><form method=post style="height:100vh;display:flex;align-items:center;justify-content:center;background:#000"><input name=c autofocus style="width:95vw;font-size:24px;padding:16px;background:#111;color:#fff;border:1px solid #333;border-radius:8px"></form>'
async def note(r):
    if r.method=='POST': c=(await r.post()).get('c','').strip(); c and subprocess.run(['python3',os.path.expanduser('~/.local/bin/aio'),'note',c]); raise web.HTTPFound('/n')
    return web.Response(text=N,content_type='text/html')
app = web.Application(); app.add_routes([web.get('/', page), web.post('/exec', exec_cmd), web.get('/ws', term), web.get('/restart', restart), web.route('*','/n',note)])

def run(port=8080):
    u=f'http://localhost:{port}';(subprocess.run(['termux-open-url',u])if os.environ.get('TERMUX_VERSION')else webbrowser.open(u));web.run_app(app,port=port)
