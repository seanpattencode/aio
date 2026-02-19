import sys, asyncio, os, pty, subprocess, webbrowser, struct, fcntl, termios, json; from aiohttp import web

# terminal is the API: all logic runs via terminal commands, UI only visualizes
# no business logic in UI — buttons send terminal strings, results render in xterm
# single-page app: all views in one HTML, show/hide for instant switching
# bookmarkable flat paths via pushState: /term /note work on reload + cross-device
HTML = '''<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-webgl@0.16.0/lib/xterm-addon-webgl.min.js"></script>
<body style="margin:0;height:100vh;background:#000;overflow:hidden">
<div id=v_index style="display:none;height:100vh;flex-direction:column;align-items:center;justify-content:center;gap:20px">
  <a onclick="go('/jobs')" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">jobs</a>
  <a onclick="go('/term')" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">terminal</a>
  <a onclick="go('/note')" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">note</a>
</div>
<div id=v_term style="display:none;height:100vh">
  <div id=t style="height:calc(100vh - 140px)"></div>
  <div id=bar style="position:fixed;bottom:0;left:0;right:0;height:140px;padding:10px;box-sizing:border-box;background:#1a1a2e;border-top:2px solid #4a4a6a;display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px">
    <input id=i autofocus placeholder="command" style="width:100%;padding:18px;font-size:20px;background:#0d0d1a;color:#fff;border:2px solid #4a4a6a;border-radius:8px;outline:none;box-sizing:border-box">
    <button onclick="var v=i.value;i.value='';ws(v+'\\n');i.focus()" style="flex:1;padding:18px;font-size:22px;min-width:60px">&#9654;</button>
    <button onclick="ws('aio\\n')" style="flex:1;padding:18px;font-size:22px;min-width:60px">aio</button>
    <button onclick="go('/note')" style="flex:1;padding:18px;font-size:22px;min-width:60px">note</button>
    <button onclick="go('/')" style="flex:1;padding:18px;font-size:22px;min-width:60px">&#8962;</button>
  </div>
</div>
<div id=v_jobs style="display:none;height:100vh;flex-direction:column;align-items:center;justify-content:center;gap:20px;color:#fff;font-family:system-ui">
  <div style="display:flex;gap:10px;width:95vw;align-items:center">
    <input id=jc placeholder="command" style="flex:1;font-size:24px;padding:16px;background:#111;color:#fff;border:1px solid #333;border-radius:8px">
    <button onclick="runjob()" style="padding:16px 24px;font-size:24px;background:#1a1a2e;color:#4af;border:2px solid #4af;border-radius:8px;cursor:pointer">run</button>
  </div>
</div>
<div id=v_note style="display:none;height:100vh;align-items:center;justify-content:center">
  <form id=nf style="display:flex;gap:10px;width:95vw;align-items:center">
    <input id=nc autofocus placeholder="note" style="flex:1;font-size:24px;padding:16px;background:#111;color:#fff;border:1px solid #333;border-radius:8px">
    <button type=submit style="padding:16px 24px;font-size:24px;background:#1a1a2e;color:#4af;border:2px solid #4af;border-radius:8px;cursor:pointer">save</button>
    <button type=button onclick="go('/term')" style="padding:16px 24px;font-size:24px;background:#1a1a2e;color:#4af;border:2px solid #4af;border-radius:8px;cursor:pointer">term</button>
  </form>
</div>
<script>
var views={'/':'v_index','/jobs':'v_jobs','/term':'v_term','/note':'v_note'}, T, F, W;
function go(p){history.pushState(null,'',p);show(p);}
function show(p){for(var k in views)document.getElementById(views[k]).style.display=k===p?(k==='/term'?'block':'flex'):'none';if(p==='/term'&&F)setTimeout(function(){F.fit()},0);}
function ws(d){if(W&&W.readyState===1)W.send(d);}
function runjob(){var v=jc.value.trim();if(v){ws('claude "'+v.replace(/"/g,'\\\\"')+'"\\n');go('/term');}}
window.onpopstate=function(){show(location.pathname);};
try{
  T=new Terminal();F=new(FitAddon.FitAddon||FitAddon)();
  T.loadAddon(F);T.open(document.getElementById('t'));try{T.loadAddon(new WebglAddon.WebglAddon())}catch(e){}
  i.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();var v=i.value;i.value='';ws(v+'\\n');i.focus();}});
  function connect(){
    W=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
    W.onopen=function(){bar.style.borderTopColor='#4a4a6a';F.fit();ws(JSON.stringify({cols:T.cols,rows:T.rows}));};
    W.onmessage=function(e){T.write(e.data);};
    W.onerror=function(){bar.style.borderTopColor='#a00';};
    W.onclose=function(){bar.style.borderTopColor='#a00';setTimeout(connect,1000);};
  }
  connect();
  T.onData(function(d){ws(d);});
  new ResizeObserver(function(){F.fit();ws(JSON.stringify({cols:T.cols,rows:T.rows}));}).observe(document.getElementById('t'));
}catch(e){document.body.innerHTML='<pre style="color:red;padding:20px">'+e+'</pre>';}
nf.onsubmit=function(e){e.preventDefault();var c=nc.value.trim();if(c){fetch('/note',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'c='+encodeURIComponent(c)});nc.value='';nc.placeholder='saved!';}};
show(views[location.pathname]?location.pathname:'/');
</script>'''

async def spa(r): return web.Response(text=HTML, content_type='text/html', headers={'Cache-Control':'no-store'})

async def restart(r): os.execv(sys.executable, [sys.executable] + sys.argv)
async def term(r):
    ws = web.WebSocketResponse(); await ws.prepare(r); m, s = pty.openpty()
    fcntl.ioctl(s, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 180, 0, 0))
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    env['TERM'] = 'xterm-256color'
    subprocess.Popen([os.environ.get('SHELL', '/bin/bash'), '-l'], preexec_fn=os.setsid, stdin=s, stdout=s, stderr=s, env=env); os.close(s)
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

async def note_api(r):
    if r.method=='POST': d=await r.post(); c=d.get('c','').strip(); c and subprocess.run(['python3',os.path.expanduser('~/.local/bin/aio'),'note',c]); return web.Response(text='ok')
    return web.Response(text='')

# serve same SPA for all bookmarkable paths — JS reads pathname to show correct view
app = web.Application(); app.add_routes([web.get('/', spa), web.get('/jobs', spa), web.get('/term', spa), web.get('/note', spa), web.get('/ws', term), web.get('/restart', restart), web.post('/note', note_api)])

def run(port=1111): web.run_app(app, port=port, print=None)
