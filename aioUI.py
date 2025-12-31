import sys, asyncio, os, pty, subprocess, webbrowser, struct, fcntl, termios, json; from aiohttp import web

HTML = '''<!doctype html>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit/lib/xterm-addon-fit.min.js"></script>
<body style="margin:0;height:100vh;background:#000;overflow:hidden">
<div id=t style="height:calc(100vh - 100px)"></div>
<div style="position:fixed;bottom:0;left:0;right:0;height:100px;background:#1a1a2e;border-top:2px solid #4a4a6a;display:flex;align-items:center;justify-content:center;gap:20px"><input id=i autofocus placeholder="type command, press Enter" onkeydown="if(event.key==='Enter'){ws.send(this.value+'\\n');this.value='';}" style="flex:1;max-width:500px;padding:15px;font-size:18px;background:#0d0d1a;color:#fff;border:2px solid #4a4a6a;border-radius:8px;outline:none"><button onclick="ws.send(i.value+'\\n');i.value='';i.focus()" style="padding:15px 30px;font-size:24px">▶</button><button onclick="ws.send('aio\\n')" style="padding:15px 30px;font-size:24px">aio</button><button onclick="ws.send('aio note\\n')" style="padding:15px 30px;font-size:24px">note</button><button onclick="fetch('/restart');setTimeout(()=>location.reload(),1000)" style="padding:15px 30px;font-size:24px">↻</button></div>
<script>
  const term = new Terminal(), fit = new (FitAddon.FitAddon||FitAddon)(), ws = new WebSocket("ws://"+location.host+"/ws");
  term.loadAddon(fit); term.open(t);
  const sendSize = () => ws.readyState===1 && ws.send(JSON.stringify({cols:term.cols,rows:term.rows}));
  const doFit = () => { fit.fit(); sendSize(); };
  new ResizeObserver(doFit).observe(t);
  ws.onopen = doFit; term.onData(d => ws.send(d)); ws.onmessage = e => term.write(e.data);
</script>'''

async def page(r): return web.Response(text=HTML, content_type='text/html', headers={'Cache-Control':'no-store'})
async def run(r): d=await r.json(); return web.json_response({'out': subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {d['cmd']}")})

async def restart(r): asyncio.get_event_loop().call_later(0.1, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)); return web.Response(text='ok')
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

app = web.Application(); app.add_routes([web.get('/', page), web.post('/exec', run), web.get('/ws', term), web.get('/restart', restart)])
if '--install' in sys.argv: os.makedirs(os.path.expanduser('~/.config/autostart'), exist_ok=True); open(os.path.expanduser('~/.config/autostart/aioUI.desktop'),'w').write(f'[Desktop Entry]\nType=Application\nExec=python3 {os.path.abspath(__file__)}\nName=aioUI'); sys.exit()
if __name__ == '__main__': p=int(sys.argv[1]) if len(sys.argv)>1 else 8080; webbrowser.open(f'http://localhost:{p}'); web.run_app(app, port=p)
