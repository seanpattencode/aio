import sys, asyncio, os, pty, subprocess as S, struct, fcntl, termios, json, socket, time; from aiohttp import web; from concurrent.futures import ThreadPoolExecutor

# terminal is the API: ALL logic routes through local terminal commands (the `a` binary)
# so AI agents and humans can debug in terminal and know logic works identically in UI.
# no business logic in UI — UI calls CLI commands, never reimplements them.
# to add UI features: first build+debug as terminal command, then add UI that calls it.
# terminal is handled through tmux as our session manager and I/O device.
# all terminal ops should be tmux sessions — inspectable via tmux capture-pane,
# controllable via tmux send-keys, debuggable by attaching: tmux attach -t <session>.
# single-page app: all views in one HTML, show/hide for instant switching
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
<style>*{font-family:system-ui}</style>
<body style="margin:0;height:100vh;background:#000;overflow:hidden">
<div id=v_index style="display:none;height:100vh;flex-direction:column;align-items:center;justify-content:center;gap:20px">
  <a onclick="go('/jobs')" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">jobs</a>
  <a onclick="go('/term')" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">terminal</a>
  <a onclick="go('/note')" style="font-size:28px;color:#4af;cursor:pointer;padding:20px 40px;border:2px solid #4af;border-radius:12px">note</a>
  <a onclick="fetch('/restart')" style="font-size:16px;color:#666;cursor:pointer;padding:10px 20px">restart server</a>
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
<div id=v_jobs style="display:none;height:100vh;flex-direction:column;align-items:center;justify-content:center;gap:20px;color:#fff">
  <select id=jp style="width:95vw;font-size:20px;padding:12px;background:#111;color:#fff;border:1px solid #333;border-radius:8px"><option value="">loading...</option></select>
  <select id=jd style="width:95vw;font-size:20px;padding:12px;background:#111;color:#fff;border:1px solid #333;border-radius:8px"><option value="">local</option></select>
  <div style="display:flex;gap:10px;width:95vw;align-items:center">
    <input id=jc placeholder="prompt" onkeydown="if(event.key==='Enter')runjob()" style="flex:1;font-size:24px;padding:16px;background:#111;color:#fff;border:1px solid #333;border-radius:8px">
    <select id=jn style="font-size:20px;padding:12px;background:#111;color:#fff;border:1px solid #333;border-radius:8px"><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select>
    <label style="color:#4af;font-size:18px;display:flex;align-items:center;gap:4px"><input type=checkbox id=jpr>PR</label>
    <button onclick="runjob()" style="padding:16px 24px;font-size:24px;background:#1a1a2e;color:#4af;border:2px solid #4af;border-radius:8px;cursor:pointer">run</button>
  </div>
  <div id=jl style="width:95vw;overflow-y:auto;flex:1;margin-top:10px;font-family:monospace;font-size:14px;white-space:pre;color:#aaa"></div>
</div>
<div id=v_note style="display:none;height:100vh;flex-direction:column;padding-top:20px;align-items:center">
  <form id=nf style="display:flex;gap:10px;width:95vw;align-items:center">
    <input id=nc autofocus placeholder="note" style="flex:1;font-size:24px;padding:16px;background:#111;color:#fff;border:1px solid #333;border-radius:8px">
    <button type=submit style="padding:16px 24px;font-size:24px;background:#1a1a2e;color:#4af;border:2px solid #4af;border-radius:8px;cursor:pointer">save</button>
    <button type=button onclick="go('/term')" style="padding:16px 24px;font-size:24px;background:#1a1a2e;color:#4af;border:2px solid #4af;border-radius:8px;cursor:pointer">term</button>
  </form>
  <div id=nl style="width:95vw;overflow-y:auto;flex:1;margin-top:10px"></div>
</div>
<script>
var views={'/':'v_index','/jobs':'v_jobs','/term':'v_term','/note':'v_note'}, T, F, W;
function go(p){history.pushState(null,'',p);show(p);}
function show(p){for(var k in views)document.getElementById(views[k]).style.display=k===p?(k==='/term'?'block':'flex'):'none';if(p==='/term'&&F)setTimeout(function(){F.fit()},0);if(p==='/note')loadn();if(p==='/jobs')loadjobs();}
function loadn(){fetch('/api/notes').then(function(r){return r.json()}).then(function(d){nl.innerHTML=d.map(function(t){return'<div style="padding:6px 0;color:#aaa;border-bottom:1px solid #222">'+t+'</div>'}).join('');});}
function loadjobs(){fetch('/api/jobs').then(function(r){return r.text()}).then(function(d){
  var h=d;fetch('/api/job-status').then(function(r){return r.json()}).then(function(js){
    if(js.length){h+='\\n\\n--- Job PRs ---\\n';js.forEach(function(j){
      h+=j.status+(j.step?' ['+j.step+']':'')+' '+j.name;
      if(j.session)h+=' ('+j.session+')';h+='\\n';});}
    jl.textContent=h;});});}
function ws(d){if(W&&W.readyState===1)W.send(d);}
function runjob(){var v=jc.value.trim(),p=jp.value,n=parseInt(jn.value),d=jd.value,pr=jpr.checked;if(!v)return;fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:v,project:p,count:n,device:d,pr:pr})}).then(function(r){return r.json()}).then(function(r){jc.value='';jc.placeholder=r.command||r.error;loadjobs();});}
fetch('/api/projects').then(function(r){return r.json()}).then(function(d){jp.innerHTML='<option value="">~ (home)</option>';d.forEach(function(p){jp.innerHTML+='<option value="'+p.path+'">'+p.name+'</option>';});});
fetch('/api/devices').then(function(r){return r.json()}).then(function(d){jd.innerHTML='<option value="">local</option>';d.forEach(function(h){jd.innerHTML+='<option value="'+h.name+'"'+(h.live?'':' style="color:#666"')+'>'+h.name+(h.live?' ✓':' ✗')+'</option>';});});
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
nf.onsubmit=function(e){e.preventDefault();var c=nc.value.trim();if(c){fetch('/note',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'c='+encodeURIComponent(c)});nl.insertAdjacentHTML('afterbegin','<div style="padding:6px 0;color:#aaa;border-bottom:1px solid #222">'+c+'</div>');nc.value='';nc.placeholder='saved!';}};
show(views[location.pathname]?location.pathname:'/');
</script>'''

async def spa(r): return web.Response(text=HTML, content_type='text/html', headers={'Cache-Control':'no-store'})

async def restart(r): os.execv(sys.executable, [sys.executable] + sys.argv)
# xterm view is a plain user shell (no tmux) — interactive terminal for manual use.
# tmux is used for background jobs only (POST /api/jobs), where sessions must be
# inspectable (tmux capture-pane -t <job>), controllable (tmux send-keys), and
# debuggable by both humans and AI agents (tmux attach -t <job>).
async def term(r):
    ws = web.WebSocketResponse(); await ws.prepare(r); m, s = pty.openpty()
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}; env['TERM'] = 'xterm-256color'
    S.Popen([os.environ.get('SHELL', '/bin/bash'), '-l'], preexec_fn=os.setsid, stdin=s, stdout=s, stderr=s, env=env); os.close(s)
    loop = asyncio.get_event_loop()
    loop.add_reader(m, lambda: asyncio.create_task(ws.send_str(os.read(m, 4096).decode(errors='ignore'))))
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

async def projects_api(r):
    d = f'{_G}/workspace/projects'; ps = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if not f.endswith('.txt'): continue
            kv = _kv(f'{d}/{f}')
            if 'Name' in kv:
                p = kv.get('Path', '') or f'~/projects/{kv["Name"]}'
                ps.append({'name': kv['Name'], 'path': p.replace('~', os.path.expanduser('~'))})
    ps.sort(key=lambda x: x['name'])
    return web.json_response(ps)

def _up(h):
    try: s = socket.socket(); s.settimeout(0.5); hp = h.rsplit(':', 1); s.connect((hp[0].split('@')[-1], int(hp[1]) if len(hp) > 1 else 22)); s.close(); return True
    except: return False

async def devices_api(r):
    d = f'{_G}/ssh'; hosts = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if not f.endswith('.txt'): continue
            kv = _kv(f'{d}/{f}')
            if 'Name' in kv and 'Host' in kv: hosts.append({'name': kv['Name'], 'host': kv['Host']})
    with ThreadPoolExecutor(8) as ex: live = list(ex.map(lambda h: _up(h['host']), hosts))
    for i, h in enumerate(hosts): h['live'] = live[i]
    hosts.sort(key=lambda x: (-x['live'], x['name']))
    return web.json_response(hosts)

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
    import sqlite3
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

async def notes_list(r):
    d = f'{_G}/notes'; ns = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d), key=lambda x: x.rsplit('_', 1)[-1] if '_' in x else '0', reverse=True):
            if not f.endswith('.txt') or f.startswith('.'): continue
            for line in open(f'{d}/{f}'):
                if line.startswith('Text: '): ns.append(line[6:].strip()); break
    return web.json_response(ns)

app = web.Application(); app.add_routes([web.get('/', spa), web.get('/jobs', spa), web.get('/term', spa), web.get('/note', spa), web.get('/ws', term), web.get('/restart', restart), web.get('/api/projects', projects_api), web.get('/api/devices', devices_api), web.get('/api/notes', notes_list), web.get('/api/jobs', jobs_api), web.post('/api/jobs', jobs_api), web.get('/api/job-status', job_status_api), web.get('/api/term', term_capture), web.post('/note', note_api)])

def run(port=1111): web.run_app(app, port=port, print=None)
