import sys,os,pty,subprocess,webbrowser,struct,fcntl,termios,json,asyncio;from aiohttp import web
H='''<!doctype html><meta name=viewport content="width=device-width,initial-scale=1,user-scalable=no">
<link rel=stylesheet href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>
<body style="margin:0;height:100vh;background:#000"><div id=t style="height:100vh"></div>
<script>try{var T=new Terminal(),F=new(FitAddon.FitAddon||FitAddon)(),W;
T.loadAddon(F);T.open(document.getElementById('t'));
function S(d){if(W&&W.readyState===1)W.send(d);}
function connect(){W=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
W.onopen=function(){F.fit();S(JSON.stringify({cols:T.cols,rows:T.rows}));};
W.onmessage=function(e){T.write(e.data);};W.onclose=function(){setTimeout(connect,1000);};W.onerror=function(){};}
connect();T.onData(function(d){S(d);});
new ResizeObserver(function(){F.fit();S(JSON.stringify({cols:T.cols,rows:T.rows}));}).observe(document.getElementById('t'));
}catch(e){document.body.innerHTML='<pre style="color:red">'+e+'</pre>';}</script>'''
async def ws(r):
    s=web.WebSocketResponse();await s.prepare(r);m,sl=pty.openpty();fcntl.ioctl(sl,termios.TIOCSWINSZ,struct.pack('HHHH',50,180,0,0))
    subprocess.Popen(['bash','-l'],preexec_fn=os.setsid,stdin=sl,stdout=sl,stderr=sl,env={**{k:v for k,v in os.environ.items()if k not in('TMUX','TMUX_PANE')},'TERM':'xterm-256color'});os.close(sl)
    loop=asyncio.get_event_loop();loop.add_reader(m,lambda:asyncio.create_task(s.send_str(os.read(m,4096).decode(errors='ignore'))))
    async for msg in s:
        if msg.type==web.WSMsgType.TEXT:
            try:
                d=json.loads(msg.data)
                if isinstance(d,dict)and'cols'in d:fcntl.ioctl(m,termios.TIOCSWINSZ,struct.pack('HHHH',d['rows'],d['cols'],0,0));continue
            except Exception:pass
            os.write(m,msg.data.encode())
        elif msg.type==web.WSMsgType.BINARY:os.write(m,msg.data)
    loop.remove_reader(m);os.close(m)
    return s
app=web.Application();app.add_routes([web.get('/',lambda r:web.Response(text=H,content_type='text/html')),web.get('/ws',ws)])
def run(port=8080):web.run_app(app,port=port,print=None)
