import sys, asyncio, os, pty, subprocess, webbrowser, struct, fcntl, termios, json; from aiohttp import web

HTML = '''<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>
<body style="margin:0;height:100vh;background:#000;overflow:hidden">
<div id=t style="height:calc(100vh - 140px)"></div>
<div id=bar style="position:fixed;bottom:0;left:0;right:0;height:140px;padding:10px;box-sizing:border-box;background:#1a1a2e;border-top:2px solid #4a4a6a;display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px">
  <input id=i autofocus placeholder="command" style="width:100%;padding:18px;font-size:20px;background:#0d0d1a;color:#fff;border:2px solid #4a4a6a;border-radius:8px;outline:none;box-sizing:border-box">
  <button id=b0 style="flex:1;padding:18px;font-size:22px;min-width:60px">&#9654;</button>
  <button id=b1 style="flex:1;padding:18px;font-size:22px;min-width:60px">aio</button>
  <button id=b2 style="flex:1;padding:18px;font-size:22px;min-width:60px">note</button>
  <button id=b3 style="flex:1;padding:18px;font-size:22px;min-width:60px">&#8635;</button>
</div>
<script>
try {
  var T = new Terminal(), F = new (FitAddon.FitAddon||FitAddon)(), W;
  T.loadAddon(F); T.open(document.getElementById('t'));
  function S(d){if(W&&W.readyState===1)W.send(d);}
  function go(){var v=i.value;i.value='';S(v+'\\n');i.focus();}
  i.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();go();}});
  b0.onclick=go; b1.onclick=function(){S('aio\\n');}; b2.onclick=function(){S('aio note '+i.value+'\\n');i.value='';i.focus();};
  b3.onclick=function(){fetch('/restart');(function c(){fetch('/').then(function(){location.reload();}).catch(function(){setTimeout(c,50);});})();};
  function connect(){
    W=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
    W.onopen=function(){bar.style.borderTopColor='#4a4a6a';F.fit();S(JSON.stringify({cols:T.cols,rows:T.rows}));};
    W.onmessage=function(e){T.write(e.data);};
    W.onerror=function(){bar.style.borderTopColor='#a00';};
    W.onclose=function(){bar.style.borderTopColor='#a00';setTimeout(connect,1000);};
  }
  connect();
  T.onData(function(d){S(d);});
  new ResizeObserver(function(){F.fit();S(JSON.stringify({cols:T.cols,rows:T.rows}));}).observe(document.getElementById('t'));
} catch(e){document.body.innerHTML='<pre style="color:red;padding:20px">'+e+'</pre>';}
</script>'''

async def page(r): return web.Response(text=HTML, content_type='text/html', headers={'Cache-Control':'no-store'})

async def restart(r): os.execv(sys.executable, [sys.executable] + sys.argv)
async def term(r):
    ws = web.WebSocketResponse(); await ws.prepare(r); m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 180, 0, 0))
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    env['TERM'] = 'xterm-256color'
    subprocess.Popen(['bash', '-l'], preexec_fn=os.setsid, stdin=s, stdout=s, stderr=s, env=env); os.close(s)
    loop = asyncio.get_event_loop()
    loop.add_reader(m, lambda: asyncio.create_task(ws.send_str(os.read(m, 4096).decode(errors='ignore'))))
    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                d = json.loads(msg.data)
                if isinstance(d, dict) and 'cols' in d: fcntl.ioctl(m, termios.TIOCSWINSZ, struct.pack('HHHH', d['rows'], d['cols'], 0, 0)); continue
            except Exception: pass
            os.write(m, msg.data.encode())
        elif msg.type == web.WSMsgType.BINARY:
            os.write(m, msg.data)
    loop.remove_reader(m); os.close(m)
    return ws

N='<meta name=viewport content="width=device-width"><form method=post style="height:100vh;display:flex;align-items:center;justify-content:center;background:#000"><input name=c autofocus style="width:95vw;font-size:24px;padding:16px;background:#111;color:#fff;border:1px solid #333;border-radius:8px"></form>'
async def note(r):
    if r.method=='POST': c=(await r.post()).get('c','').strip(); c and subprocess.run(['python3',os.path.expanduser('~/.local/bin/aio'),'note',c]); raise web.HTTPFound('/n')
    return web.Response(text=N,content_type='text/html')
app = web.Application(); app.add_routes([web.get('/', page), web.get('/ws', term), web.get('/restart', restart), web.route('*','/n',note)])

def run(port=1111): web.run_app(app, port=port, print=None)
