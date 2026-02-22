"""a job — full lifecycle: worktree → agent → PR → email
Usage: a job <project|path> <prompt> [--device DEV] [--agent c|g|l]
Flow: create worktree branch, launch agent session with prompt, wait for completion,
      git add+commit, gh pr create, email PR URL. Works locally or via SSH."""
import sys, os, subprocess as S, time
sys.stdout.reconfigure(line_buffering=True)
from datetime import datetime
from _common import init_db, load_cfg, load_sess, load_proj, db, DEVICE_ID, SCRIPT_DIR, ADATA_ROOT, DATA_DIR

_A = os.path.join(SCRIPT_DIR, 'a')

def _db_job(name, step, status, path='', session=''):
    with db() as c: c.execute("INSERT OR REPLACE INTO jobs VALUES(?,?,?,?,?,?)", (name, step, status, path, session, int(time.time())))

def _ssh(dev, cmd, timeout=300):
    r = S.run([_A, 'ssh', dev, cmd], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def _ssh_wait_ready(dev, sn, timeout=60):
    """Poll remote tmux pane until claude is ready to accept input"""
    for _ in range(timeout // 3):
        rc, out, _ = _ssh(dev, f"tmux capture-pane -t '{sn}' -p 2>/dev/null | tail -10", timeout=10)
        if rc != 0: time.sleep(3); continue
        lo = out.lower()
        if 'type your message' in lo or 'claude' in lo or '>' in out: return True
        time.sleep(3)
    return False

def _ssh_wait_done(dev, sn, timeout=600):
    """Wait for remote agent — idle 30s = done"""
    import re
    last_change, prev, start = time.time(), '', time.time()
    while time.time() - start < timeout:
        rc, out, _ = _ssh(dev, f"tmux capture-pane -t '{sn}' -p 2>/dev/null | tail -10", timeout=10)
        if rc != 0: return False
        stable = re.sub(r'\d+[ms] \d+s|\d+s','',out)
        if stable != prev: prev = stable; last_change = time.time()
        elif time.time() - last_change > 30: return True
        time.sleep(5)
    return True

def _extract_pr_url(text):
    import re
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)  # strip ANSI
    for line in text.split('\n'):
        line = line.strip()
        if '/pull/' in line and 'github.com/' in line:
            u = line[line.index('https://'):] if 'https://' in line else ''
            if u: return u
    return ''

def _go_one(qdir,sel,files,_A):
    kv=dict(l.split(': ',1)for l in open(os.path.join(qdir,sel+'.txt')).read().strip().split('\n')if': 'in l)
    cmd=[_A,'job',kv['Project'],kv.get('Prompt','')]+(['--device',kv['Device']]if kv.get('Device')else[])+(['--timeout',kv['Timeout']]if kv.get('Timeout')else[])+(['--no-prefix']if kv.get('Prefix','on')=='off'else[])+(['--no-agents']if kv.get('Agents','on')=='off'else[])
    print(f">>> {sel}");S.call(cmd)

def run():
    init_db(); cfg = load_cfg(); PROJ = load_proj(); sess = load_sess(cfg)
    args = sys.argv[2:]
    qdir=os.path.join(str(ADATA_ROOT/'git'/'jobs'),'queue');os.makedirs(qdir,exist_ok=True)
    if not args or args[0]=='status':
        for n,step,st,p,sn,ts in db().execute("SELECT name,step,status,path,session,updated_at FROM jobs ORDER BY updated_at DESC LIMIT 10"):
            live=''
            if st=='running' and p and '/' not in p:
                try: live=' LIVE' if not _ssh(p,f"tmux has-session -t '{sn}'",5)[0] else ' DONE'
                except: live=''
            print(f"  {'+'if st=='done'else'x'if st=='failed'else'~'} {n:30s} {step:10s} {(int(time.time())-ts)//3600}h{live}")
        files=sorted(f for f in os.listdir(qdir) if f.endswith('.txt'))
        if files: print(f"\nQueue:")
        for i,f in enumerate(files): kv=dict(l.split(': ',1)for l in open(os.path.join(qdir,f)).read().split('\n')if': 'in l);print(f"  {i} {f[:-4]:20s} {kv.get('Device','local'):8s} {kv.get('Prompt','')[:50]}")
        print(f"\n  a job add <name>    stage a job\n  a job go <#>        launch\n  a job go all        launch all\n  e {qdir}/<name>.txt  edit")
        return
    if args[0]=='log':
        ldir=os.path.join(DATA_DIR,'job_logs');print(open(os.path.join(ldir,args[1]+'.log')).read() if len(args)>1 and os.path.exists(os.path.join(ldir,args[1]+'.log')) else '\n'.join(sorted(os.listdir(ldir))[-10:]) if os.path.isdir(ldir) else 'No logs');return
    if args[0] in ('-h', '--help', 'help'):
        print("a job <project> <prompt> [--device DEV] [--watch] [--timeout S]\n\n"
              "  a job add <name>                  stage job (opens editor)\n"
              "  a job go <name|#>                 launch staged job\n"
              "  a job go all [--interval 300]     launch all queued\n"
              "  a job a \"fix bug\" --device hsu    run directly\n"
              "  a job a @prompt --device hsu      saved prompt\n"
              "  a job status                      running + queue\n"
              "  a job log <name>                  view agent output")
        return
    if args[0]=='add':
        qf=os.path.join(qdir,(args[1]if len(args)>1 else'job')+'.txt');os.path.exists(qf)or open(qf,'w').write('Project: a\nDevice: hsu\nPrompt: \nTimeout: 600\nPrefix: on\nAgents: on\n');S.run(['e',qf]);return
    if args[0]=='go':
        sel=args[1]if len(args)>1 else'';files=sorted(f for f in os.listdir(qdir)if f.endswith('.txt'))
        iv=int(args[args.index('--interval')+1])if '--interval'in args else 0
        if sel=='all':
            for i,f in enumerate(files):
                if i and iv:print(f"  sleeping {iv}s...");time.sleep(iv)
                _go_one(qdir,f[:-4],files,_A)
            return
        if sel.isdigit()and int(sel)<len(files):sel=files[int(sel)][:-4]
        _go_one(qdir,sel,files,_A);return
    # Parse args
    dev, ak, proj, pp, watch, timeout, use_prefix, use_agents = '', 'l', '', [], False, 600, True, True
    i = 0
    while i < len(args):
        if args[i] == '--watch' or args[i] == '-w': watch = True; i += 1
        elif args[i] == '--no-prefix': use_prefix = False; i += 1
        elif args[i] == '--no-agents': use_agents = False; i += 1
        elif args[i] == '--timeout' and i+1 < len(args): timeout = int(args[i+1]); i += 2
        elif args[i] == '--device' and i+1 < len(args): dev = args[i+1]; i += 2
        elif args[i] == '--agent' and i+1 < len(args): ak = args[i+1]; i += 2
        elif not proj:
            if args[i].isdigit() and int(args[i]) < len(PROJ): proj = PROJ[int(args[i])][0]; i += 1
            elif os.path.isdir(os.path.expanduser(args[i])): proj = os.path.expanduser(args[i]); i += 1
            elif os.path.isdir(os.path.expanduser(f'~/projects/{args[i]}')): proj = os.path.expanduser(f'~/projects/{args[i]}'); i += 1
            else:
                u=next((r for p,r in PROJ if os.path.basename(p)==args[i] and r),'');d=os.path.expanduser(f'~/projects/{args[i]}');proj=d if u and not S.run(['git','clone',u,d],capture_output=True).returncode else sys.exit(print(f"x No local project: {args[i]}"))
                i+=1;continue
        else: pp.append(args[i]); i += 1
    prompt = ' '.join(pp)
    pdir=os.path.join(str(ADATA_ROOT/'git'/'jobs'));os.makedirs(pdir,exist_ok=True)
    if prompt.startswith('@'):
        pf=os.path.join(pdir,prompt[1:]+'.txt');os.path.exists(pf)or open(pf,'w').close();S.run(['e',pf]);prompt=open(pf).read().strip()
    elif not prompt:
        pf=os.path.join(pdir,'_draft.txt');open(pf,'w').close();S.run(['e',pf]);prompt=open(pf).read().strip()
    if not prompt: print("x No prompt"); sys.exit(1)
    if use_prefix or use_agents:
        from _common import get_prefix
        pfx=get_prefix('claude',cfg,proj) if use_prefix else '';af=os.path.join(proj,'AGENTS.md')
        agents=open(af).read().strip() if use_agents and os.path.exists(af) else ''
        prompt=(pfx+' ' if pfx else '')+prompt+('\n\n'+agents if agents else '')
    if not os.path.isdir(os.path.join(proj, '.git')):
        print(f"x Not a git repo: {proj}"); sys.exit(1)

    rn = os.path.basename(proj)
    now = datetime.now()
    ts = now.strftime('%b%d-%-I%M%p').lower()  # feb20-517am
    jn = f'{rn}-{ts}'
    wt = cfg.get('worktrees_dir', str(ADATA_ROOT / 'worktrees'))
    wp = os.path.join(wt, jn)
    if os.path.exists(wp): jn += '-2'; wp = os.path.join(wt, jn)
    br = f'job-{jn}'
    sn = f'job-{jn}'

    open(os.path.join(pdir,jn+'.txt'),'w').write(prompt)
    print(f"Job: {jn}\n  Repo: {rn}\n  Agent: {ak}\n  Device: {dev or 'local'}\n  Prompt: {prompt[:80]}")

    if dev: _run_remote(dev, ak, proj, rn, prompt, jn, br, ts, sn)
    else: _run_local(ak, proj, rn, prompt, jn, br, wp, wt, sn, watch, timeout)

def _run_local(ak, proj, rn, prompt, jn, br, wp, wt, sn, watch=False, timeout=600):
    _db_job(jn, 'worktree', 'running', wp, sn)
    os.makedirs(wt, exist_ok=True)
    r = S.run(['git', '-C', proj, 'worktree', 'add', '-b', br, wp, 'HEAD'], capture_output=True, text=True)
    if r.returncode: print(f"x Worktree: {r.stderr}"); return
    print(f"+ Worktree: {wp}")

    _db_job(jn, 'agent', 'running', wp, sn)
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    S.run(['tmux', 'new-session', '-d', '-s', sn, '-c', wp, 'claude --dangerously-skip-permissions'], env=env)
    for _ in range(60):
        time.sleep(1)
        r = S.run(['tmux', 'capture-pane', '-t', sn, '-p'], capture_output=True, text=True, env=env)
        if any(x in r.stdout.lower() for x in ['type your message', 'claude', 'context']): break
    full = f"{prompt}\n\nWhen done, run: a done \"<summary of what you changed>\""
    S.run(['tmux', 'send-keys', '-t', sn, '-l', full], env=env)
    time.sleep(0.5)
    S.run(['tmux', 'send-keys', '-t', sn, 'Enter'], env=env)
    print(f"+ Attach: a {sn}")

    _db_job(jn, 'waiting', 'running', wp, sn)
    done_file = os.path.join(DATA_DIR, '.done')
    if os.path.exists(done_file): os.unlink(done_file)
    timed_out = False
    if watch:
        print(f"Attaching to {sn}... (Ctrl-B d to detach)")
        S.run(['tmux', 'attach', '-t', sn], env=env)
    else:
        print("Waiting for agent...")
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(done_file): break
            r = S.run(['tmux', 'has-session', '-t', sn], capture_output=True)
            if r.returncode != 0: break
            time.sleep(3)
        else: timed_out = True
    summary = open(done_file).read().strip() if os.path.exists(done_file) else ''
    log = S.run(['tmux', 'capture-pane', '-t', sn, '-S', '-1000', '-p'], capture_output=True, text=True, env=env).stdout
    S.run(['tmux', 'kill-session', '-t', sn], capture_output=True, env=env)
    resume = f"cd {wp} && claude --continue"
    print(("+ Done" if not timed_out else "x Timeout — killed") + f"\n  Resume: {resume}")

    _db_job(jn, 'pr', 'running', wp, sn)
    pr = _make_pr(wp, br, rn, prompt)
    if pr:
        _db_job(jn, 'email', 'running', wp, sn)
        _email(jn, rn, prompt, pr, wp, resume, summary, log)
        _db_job(jn, 'done', 'done', wp, sn)
    else:
        _db_job(jn, 'no-changes', 'done', wp, sn)

def _run_remote(dev, ak, proj, rn, prompt, jn, br, ts, sn):
    _db_job(jn, 'ssh-setup', 'running', dev, sn)
    # Ensure repo on remote
    rc, _, _ = _ssh(dev, f'test -d ~/projects/{rn}/.git', timeout=10)
    if rc:
        r = S.run(['git', '-C', proj, 'remote', 'get-url', 'origin'], capture_output=True, text=True)
        url = r.stdout.strip()
        if not url: print("x No remote origin"); return
        print(f"  Cloning {rn} on {dev}...")
        rc, _, err = _ssh(dev, f'git clone {url} ~/projects/{rn}', timeout=60)
        if rc: print(f"x Clone: {err}"); return
    else:
        _ssh(dev, f'cd ~/projects/{rn} && git checkout main && git pull --ff-only', timeout=30)

    # Worktree
    wt = f'~/projects/a/adata/worktrees/{jn}'
    _db_job(jn, 'worktree', 'running', dev, sn)
    rc, _, err = _ssh(dev, f'mkdir -p ~/projects/a/adata/worktrees && git -C ~/projects/{rn} worktree add -b {br} {wt} HEAD', timeout=30)
    if rc: print(f"x Worktree: {err}"); return
    print(f"+ Worktree: {wt}")

    # Launch agent — detached tmux, wait for ready, send prompt
    _db_job(jn, 'agent', 'running', dev, sn)
    q = prompt.replace("'", "'\\''")
    rc, _, err = _ssh(dev, f"tmux new-session -d -s '{sn}' -c {wt} 'claude --dangerously-skip-permissions'", timeout=15)
    if rc: print(f"x Session: {err}"); return
    print(f"+ Attach: a ssh {dev} \"a {sn}\"")
    print("  Waiting for claude to start...")
    if not _ssh_wait_ready(dev, sn, timeout=120):
        print("x Claude didn't start"); return
    # Send prompt in chunks — SSH command buffer is 4K
    import base64 as b64
    full=f"{prompt}\n\nWhen done, run: a done \"<summary of what you changed>\""
    enc=b64.b64encode(full.encode()).decode();_ssh(dev,"rm -f /tmp/a_job_prompt.b64",5)
    for i in range(0,len(enc),3000): _ssh(dev,f"echo -n '{enc[i:i+3000]}' >> /tmp/a_job_prompt.b64",10)
    _ssh(dev,f"base64 -d /tmp/a_job_prompt.b64 > /tmp/a_job_prompt.txt && tmux load-buffer /tmp/a_job_prompt.txt && tmux paste-buffer -t '{sn}'",10)
    time.sleep(1)
    _ssh(dev, f"tmux send-keys -t '{sn}' Enter", timeout=10)
    print(f"+ Prompt sent")

    # Wait for completion
    _db_job(jn, 'waiting', 'running', dev, sn)
    print("Waiting for agent...")
    _ssh_wait_done(dev, sn, timeout=600)
    _,summary,_=_ssh(dev,"cat ~/projects/a/adata/local/.done 2>/dev/null",5)
    os.makedirs(ld:=os.path.join(DATA_DIR,'job_logs'),exist_ok=True);_,lg,_=_ssh(dev,f"tmux capture-pane -t '{sn}' -S -1000 -p",10);lg and open(os.path.join(ld,jn+'.log'),'w').write(lg)
    print("+ Agent finished")

    # PR on remote — write script to avoid shell quoting issues
    _db_job(jn, 'pr', 'running', dev, sn)
    import base64 as b64
    short = prompt[:50].replace('"', "'")
    script = f'''#!/bin/bash
cd {wt}
git add -A
git diff --cached --quiet || git commit -m "job: {short}"
git log --oneline origin/main..HEAD 2>/dev/null | grep -q . || {{ echo "NO_CHANGES"; exit 0; }}
git push -u origin {br}
gh pr create --title "job: {short}" --body "Prompt: {prompt[:200].replace('"', "'")}"
'''
    encoded = b64.b64encode(script.encode()).decode()
    rc, out, err = _ssh(dev, f"echo {encoded} | base64 -d > /tmp/a_job_pr.sh && bash /tmp/a_job_pr.sh", timeout=60)
    if 'NO_CHANGES' in out:
        print("+ Done (no changes)"); _db_job(jn, 'done', 'done', dev, sn); return
    pr = _extract_pr_url(out + '\n' + err)
    if pr:
        print(f"+ PR: {pr}")
        _db_job(jn, 'email', 'running', dev, sn)
        _email(jn, rn, prompt, pr, '', f'a ssh {dev} "cd {wt} && claude --continue"', summary, lg)
        _db_job(jn, 'done', 'done', dev, sn)
        print(f"+ Done: {pr}")
    else:
        print(f"x PR failed: {out}\n{err}")
        _db_job(jn, 'pr-failed', 'failed', dev, sn)

def _make_pr(wp, br, rn, prompt):
    dirty = S.run(['git', '-C', wp, 'status', '--porcelain'], capture_output=True, text=True).stdout.strip()
    ahead = S.run(['git', '-C', wp, 'log', 'HEAD', '--not', '--remotes', '--oneline'], capture_output=True, text=True).stdout.strip()
    if not dirty and not ahead: print("x No changes"); return None
    r = S.run([_A, 'pr', f'job: {prompt[:50]}'], capture_output=True, text=True, cwd=wp)
    url = _extract_pr_url(r.stdout + '\n' + r.stderr)
    if url: print(f"+ PR: {url}")
    else: print(f"x PR: {r.stdout} {r.stderr}")
    return url or None

def _email(jn, rn, prompt, pr_url, wp, resume='', summary='', log=''):
    sep='='*60+'\n'
    subj=f'[a job] {rn}: {summary[:60] if summary else prompt[:40]}'
    body=f'{sep}JOB: {jn} | REPO: {rn} | DEVICE: {DEVICE_ID}\n{sep}\n'
    if summary: body+=f'>>> SUMMARY\n{summary}\n\n'
    body+=f'>>> PR\n{pr_url}\n\n>>> PROMPT\n{prompt}\n\n'
    if resume: body+=f'>>> RESUME\n{resume}\n\n'
    if wp:
        r=S.run(['git','-C',wp,'diff','HEAD~1','--stat'],capture_output=True,text=True)
        if r.stdout.strip(): body+=f'>>> DIFF\n{r.stdout.strip()}\n\n'
    if log: body+=f'{sep}FULL LOG\n{sep}{log}\n'
    r=S.run([_A,'email',subj,body],capture_output=True,text=True,timeout=30)
    if r.returncode==0: print(f"+ Emailed")
    else: print(f"x Email: {r.stderr or r.stdout}")

run()
