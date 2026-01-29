import sys,os,pty,subprocess,webbrowser,struct,fcntl,termios,json,asyncio;from aiohttp import web
H='''<!doctype html><meta name=viewport content="width=device-width,initial-scale=1,user-scalable=no">
<link rel=stylesheet href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit/lib/xterm-addon-fit.min.js"></script>
<body style="margin:0;height:100vh;background:#000"><div id=t style="height:100vh"></div>
<script>const t=new Terminal(),f=new(FitAddon.FitAddon||FitAddon)(),w=new WebSocket("ws://"+location.host+"/ws");
t.loadAddon(f);t.open(document.getElementById('t'));new ResizeObserver(()=>{f.fit();w.readyState===1&&w.send(JSON.stringify({cols:t.cols,rows:t.rows}))}).observe(document.getElementById('t'));
w.onopen=()=>{f.fit();w.send(JSON.stringify({cols:t.cols,rows:t.rows}))};t.onData(d=>w.send(d));w.onmessage=e=>t.write(e.data)</script>'''
async def ws(r):
    s=web.WebSocketResponse();await s.prepare(r);m,sl=pty.openpty();fcntl.ioctl(sl,termios.TIOCSWINSZ,struct.pack('HHHH',50,180,0,0))
    subprocess.Popen(['bash'],preexec_fn=os.setsid,stdin=sl,stdout=sl,stderr=sl,env={**{k:v for k,v in os.environ.items()if k not in('TMUX','TMUX_PANE')},'TERM':'xterm-256color'});os.close(sl)
    asyncio.get_event_loop().add_reader(m,lambda:asyncio.create_task(s.send_str(os.read(m,4096).decode(errors='ignore'))))
    async for msg in s:
        try:d=json.loads(msg.data);'cols'in d and fcntl.ioctl(m,termios.TIOCSWINSZ,struct.pack('HHHH',d['rows'],d['cols'],0,0));continue
        except:pass
        os.write(m,msg.data.encode())
    return s
app=web.Application();app.add_routes([web.get('/',lambda r:web.Response(text=H,content_type='text/html')),web.get('/ws',ws)])
def run(port=8080):u=f'http://localhost:{port}';(subprocess.run(['termux-open-url',u])if os.environ.get('TERMUX_VERSION')else webbrowser.open(u));web.run_app(app,port=port)
