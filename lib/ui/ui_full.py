# /// script
# requires-python = ">=3.10"
# dependencies = ["aiohttp>=3.9"]
# ///
import sys, asyncio, os, pty, subprocess as S, struct, fcntl, termios, json, time, sqlite3; from html import escape as E; from aiohttp import web

# terminal is the API: ALL logic routes through local terminal commands (the `a` binary)
# so AI agents and humans can debug in terminal and know logic works identically in UI.
# no business logic in UI — UI calls CLI commands, never reimplements them.
# to add UI features: first build+debug as terminal command, then add UI that calls it.
# terminal is handled through tmux as our session manager and I/O device.
# all terminal ops should be tmux sessions — inspectable via tmux capture-pane,
# controllable via tmux send-keys, debuggable by attaching: tmux attach -t <session>.
# single-page app: all views in one HTML, show/hide for instant switching
# <1ms view transitions are mandatory. all data is server-side prerendered into
# the HTML so view switching is a pure CSS display toggle — no fetch, no render.
# never add client-side data fetching to show(). if a view needs data, prerender it.
# bookmarkable flat paths via pushState: /term /note work on reload + cross-device
_D = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
_A, _G = f'{_D}/a', f'{_D}/adata/git'
def _kv(p):
    r = {}
    for l in open(p):
        if ':' in l: k, v = l.split(':', 1); r[k.strip()] = v.strip()
    return r
HTML = '''<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-webgl@0.16.0/lib/xterm-addon-webgl.min.js"></script>
<style>*{font-family:system-ui}[data-go]{touch-action:manipulation}.b{padding:16px 24px;font-size:24px;background:#1a1a2e;color:#4af;border:2px solid #4af;border-radius:8px;cursor:pointer}</style>
<body style="margin:0;height:100vh;background:#000;overflow:hidden">
<div id=v_index style="display:none;height:100vh;flex-direction:column;align-items:center;justify-content:center;gap:20px">
  <a data-go="/jobs" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">jobs</a>
  <a data-go="/term" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">terminal</a>
  <a data-go="/note" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">note</a>
  <a onclick="fetch('/restart')" style="font-size:16px;color:#666;cursor:pointer;padding:10px 20px">restart server</a>
</div>
<div id=v_term style="display:none;height:100vh">
  <div id=t style="height:calc(100vh - 140px)"></div>
  <div id=bar style="position:fixed;bottom:0;left:0;right:0;height:140px;padding:10px;box-sizing:border-box;background:#1a1a2e;border-top:2px solid #4a4a6a;display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px">
    <input id=i autofocus placeholder="command" style="width:100%;padding:18px;font-size:20px;background:#0d0d1a;color:#fff;border:2px solid #4a4a6a;border-radius:8px;outline:none;box-sizing:border-box">
    <button onclick="var v=i.value;i.value='';ws(v+'\\n');i.focus()" style="flex:1;padding:18px;font-size:22px;min-width:60px">&#9654;</button>
  </div>
</div>
<div id=v_jobs style="display:none;height:100vh;flex-direction:column;align-items:center;justify-content:center;gap:20px;color:#fff">
  <select id=jp style="width:95vw;font-size:20px;padding:12px;background:#111;color:#fff;border:1px solid #333;border-radius:8px">__PO__</select>
  <select id=jd style="width:95vw;font-size:20px;padding:12px;background:#111;color:#fff;border:1px solid #333;border-radius:8px">__DO__</select>
  <div style="display:flex;gap:10px;width:95vw;align-items:center">
    <input id=jc placeholder="prompt" onkeydown="if(event.key==='Enter')runjob()" style="flex:1;font-size:24px;padding:16px;background:#111;color:#fff;border:1px solid #333;border-radius:8px">
    <select id=jn style="font-size:20px;padding:12px;background:#111;color:#fff;border:1px solid #333;border-radius:8px"><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select>
    <label style="color:#4af;font-size:18px;display:flex;align-items:center;gap:4px"><input type=checkbox id=jpr>PR</label>
    <button class=b onclick="runjob()">run</button>
  </div>
  <div id=jl style="width:95vw;overflow-y:auto;flex:1;margin-top:10px;font-family:monospace;font-size:14px;white-space:pre;color:#aaa">__JO__</div>
</div>
<div id=v_note style="display:none;height:100vh;flex-direction:column;padding-top:20px;align-items:center">
  <form id=nf style="display:flex;gap:10px;width:95vw;align-items:center">
    <input id=nc autofocus placeholder="note" style="flex:1;font-size:24px;padding:16px;background:#111;color:#fff;border:1px solid #333;border-radius:8px">
    <button class=b type=submit>save</button>
    <button class=b type=button onclick="this.textContent='...';fetch('/api/sync').then(()=>location.reload())">sync</button>
    <button class=b type=button data-go="/term">term</button>
  </form>
  <div id=nl style="width:95vw;overflow-y:auto;flex:1;margin-top:10px">__NO__</div>
</div>
<div id=v_dc style="position:fixed;inset:0;background:#000;color:red;text-align:center;padding-top:45vh;display:none">not connected</div>
<script>
var views={'/':'v_index','/jobs':'v_jobs','/term':'v_term','/note':'v_note'}, T, F, W;
function go(p){history.pushState(null,'',p);show(p);}
function show(p){for(var k in views)document.getElementById(views[k]).style.display=k===p?(k==='/term'?'block':'flex'):'none';if(p==='/term'&&F)setTimeout(function(){F.fit();T.focus()},0);}
function arcn(f,el){fetch('/api/note/archive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({f:f})});el.parentElement.remove();}
function loadjobs(){Promise.all([fetch('/api/jobs').then(function(r){return r.text()}),fetch('/api/job-status').then(function(r){return r.json()})]).then(function(d){
  var h=d[0];if(d[1].length){h+='\\n\\n--- Job PRs ---\\n';d[1].forEach(function(j){
    h+=j.status+(j.step?' ['+j.step+']':'')+' '+j.name;
    if(j.session)h+=' ('+j.session+')';h+='\\n';});}
  jl.textContent=h;});}
function ws(d){if(W&&W.readyState===1)W.send(d);}
function runjob(){var v=jc.value.trim(),p=jp.value,n=parseInt(jn.value),d=jd.value,pr=jpr.checked;if(!v)return;fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:v,project:p,count:n,device:d,pr:pr})}).then(function(r){return r.json()}).then(function(r){jc.value='';jc.placeholder=r.command||r.error;loadjobs();});}
window.onpopstate=function(){show(location.pathname);};
try{
  T=new Terminal();F=new(FitAddon.FitAddon||FitAddon)();
  T.loadAddon(F);T.open(document.getElementById('t'));try{T.loadAddon(new WebglAddon.WebglAddon())}catch(e){}
  i.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();var v=i.value;i.value='';ws(v+'\\n');i.focus();}});
  function connect(){
    W=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
    W.onopen=function(){v_dc.style.display='none';F.fit();ws(JSON.stringify({cols:T.cols,rows:T.rows}));};
    W.onmessage=function(e){T.write(e.data);};
    W.onerror=W.onclose=function(){v_dc.style.display='';setTimeout(connect,1000);};
  }
  connect();
  T.onData(function(d){ws(d);});
  new ResizeObserver(function(){F.fit();ws(JSON.stringify({cols:T.cols,rows:T.rows}));}).observe(document.getElementById('t'));
}catch(e){document.body.innerHTML='<pre style="color:red;padding:20px">'+e+'</pre>';}
nf.onsubmit=function(e){e.preventDefault();var c=nc.value.trim();if(c){fetch('/note',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'c='+encodeURIComponent(c)});nl.insertAdjacentHTML('afterbegin','<div style="padding:6px 0;color:#aaa;border-bottom:1px solid #222">'+c+'</div>');nc.value='';nc.placeholder='saved!';}};
var _tg=0;document.addEventListener('touchstart',function(e){var g=e.target.closest('[data-go]');if(g){e.preventDefault();_tg=1;go(g.dataset.go);}},{passive:false});
document.addEventListener('click',function(e){if(_tg){_tg=0;return;}var g=e.target.closest('[data-go]');if(g)go(g.dataset.go);});
show(views[location.pathname]?location.pathname:'/');
</script>'''

async def spa(r):
    S.Popen(['git','-C',_G,'pull','-q','--rebase'],stdout=S.DEVNULL,stderr=S.DEVNULL)
    po='<option value="">~ (home)</option>';pd=f'{_G}/workspace/projects'
    if os.path.isdir(pd):
        for f in sorted(os.listdir(pd)):
            if f.endswith('.txt'):
                kv=_kv(f'{pd}/{f}');n=kv.get('Name')
                if n: p=(kv.get('Path','') or f'~/projects/{n}').replace('~',os.path.expanduser('~'));po+=f'<option value="{E(p)}">{E(n)}</option>'
    do='<option value="">local</option>';dd=f'{_G}/ssh'
    if os.path.isdir(dd):
        for f in sorted(os.listdir(dd)):
            n=f.endswith('.txt') and _kv(f'{dd}/{f}').get('Name')
            if n: do+=f'<option value="{n}">{n}</option>'
    no = ''
    nd = f'{_G}/notes'
    if os.path.isdir(nd):
        for f in sorted(os.listdir(nd), key=lambda x: x.rsplit('_',1)[-1] if '_' in x else '0', reverse=True):
            if not f.endswith('.txt') or f.startswith('.'): continue
            try:
                for l in open(f'{nd}/{f}'):
                    if l.startswith('Text: '): no += f'<div style="padding:6px 0;color:#aaa;border-bottom:1px solid #222;display:flex;align-items:center"><button onclick="arcn(\'{f}\',this)" style="background:none;border:1px solid #555;color:#888;padding:12px 20px;margin-right:10px;border-radius:4px;cursor:pointer;font-size:16px">x</button><span>{E(l[6:].strip())}</span></div>'; break
            except: pass
    try:
        jo = S.run([_A,'jobs'],capture_output=True,text=True,timeout=10).stdout or 'No jobs'
        dp = f'{_D}/adata/local/aio.db'
        if os.path.exists(dp):
            c = sqlite3.connect(dp); c.row_factory = sqlite3.Row
            rows = c.execute("SELECT name,step,status,session FROM jobs ORDER BY updated_at DESC LIMIT 20").fetchall(); c.close()
            if rows:
                jo += '\n\n--- Job PRs ---\n'
                for row in rows: jo += row['status']+(f' [{row["step"]}]' if row['step'] else '')+' '+row['name']+(f' ({row["session"]})' if row['session'] else '')+'\n'
    except: jo = 'No jobs'
    h = HTML.replace('__PO__',po).replace('__DO__',do).replace('__NO__',no).replace('__JO__',E(jo))
    return web.Response(text=h, content_type='text/html', headers={'Cache-Control':'no-store'})

async def restart(r): os.execv(sys.executable, [sys.executable] + sys.argv)
async def term(r):
    ws = web.WebSocketResponse(); await ws.prepare(r); m, s = pty.openpty()
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}; env['TERM'] = 'xterm-256color'
    S.Popen([os.environ.get('SHELL', '/bin/bash'), '-l'], preexec_fn=os.setsid, stdin=s, stdout=s, stderr=s, env=env); os.close(s)
    loop = asyncio.get_event_loop()
    def _rd():
        try: d=os.read(m,4096)
        except: loop.remove_reader(m);return
        d and asyncio.create_task(ws.send_str(d.decode(errors='ignore'))) or loop.remove_reader(m)
    loop.add_reader(m,_rd)
    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                d = json.loads(msg.data)
                if isinstance(d, dict) and 'cols' in d: fcntl.ioctl(m, termios.TIOCSWINSZ, struct.pack('HHHH', d['rows'], d['cols'], 0, 0)); continue
            except Exception: pass
            os.write(m, msg.data.encode())
        elif msg.type == web.WSMsgType.BINARY: os.write(m, msg.data)
    loop.remove_reader(m); os.close(m)
    return ws

async def jobs_api(r):
    if r.method == 'POST':
        d = await r.json()
        prompt, project, count, device, pr = d.get('prompt', '').strip(), d.get('project', ''), d.get('count', 1), d.get('device', ''), d.get('pr', False)
        if not prompt: return web.json_response({'error': 'no prompt'}, status=400)
        env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
        if pr:
            # Full job: worktree → agent → PR → email
            args = [_A, 'job', project or '.', prompt]
            if device: args += ['--device', device]
        else:
            args = [_A, 'all', f'l:{count}'] if count > 1 else [_A, 'c']
            if project: args.append(project)
            args.append(prompt)
            if device:
                q = prompt.replace("'", "'\\''")
                cd = f"cd ~/projects/{os.path.basename(project)} && " if project else ''
                inner = f"{cd}{_A} all l:{count} '{q}'" if count > 1 else f"{cd}{_A} c '{q}'"
                args = [_A, 'ssh', device, inner]
        S.Popen(args, env=env, start_new_session=True, stdout=S.DEVNULL, stderr=S.DEVNULL)
        return web.json_response({'command': ' '.join(args)})
    p = S.run([_A, 'jobs'], capture_output=True, text=True, timeout=10)
    return web.Response(text=p.stdout or 'No jobs')

async def job_status_api(r):
    dp = f'{_D}/adata/local/aio.db'
    if not os.path.exists(dp): return web.json_response([])
    c = sqlite3.connect(dp); c.row_factory = sqlite3.Row
    rows = c.execute("SELECT name,step,status,path,session,updated_at FROM jobs ORDER BY updated_at DESC LIMIT 20").fetchall()
    c.close()
    return web.json_response([dict(r) for r in rows])

async def term_capture(r):
    s = r.query.get('session', ''); n = int(r.query.get('lines', '500'))
    if not s: return web.Response(text='usage: ?session=name&lines=500')
    p = S.run(['tmux', 'capture-pane', '-t', s, '-p', '-S', str(-n)], capture_output=True, text=True)
    return web.Response(text=p.stdout if p.returncode == 0 else f'no session: {s}')

async def note_api(r):
    if r.method == 'POST': d = await r.post(); c = d.get('c', '').strip(); c and S.Popen([_A, 'note', c]); return web.Response(text='ok')
    return web.Response(text='')
async def note_archive(r): d=await r.json();f=os.path.basename(d.get('f',''));nd=f'{_G}/notes';ad=f'{nd}/.archive';os.makedirs(ad,exist_ok=True);p=f'{nd}/{f}';os.path.isfile(p) and os.rename(p,f'{ad}/{f}');return web.Response(text='ok')
async def sync_api(r): S.run(f'cd {_G}&&git pull -q --rebase&&git add -A&&git commit -qm sync;git push -q',shell=True,timeout=15,capture_output=True);return web.Response(text='ok')

app = web.Application(); app.add_routes([web.get('/', spa), web.get('/jobs', spa), web.get('/term', spa), web.get('/note', spa), web.get('/ws', term), web.get('/restart', restart), web.get('/api/jobs', jobs_api), web.post('/api/jobs', jobs_api), web.get('/api/job-status', job_status_api), web.get('/api/term', term_capture), web.post('/note', note_api), web.post('/api/note/archive', note_archive), web.get('/api/sync', sync_api)])

def run(port=1111): web.run_app(app, port=port, print=None)
if __name__ == '__main__': run(int(sys.argv[1]) if len(sys.argv) > 1 else 1111)
