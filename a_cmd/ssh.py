"""aio ssh - SSH management (RFC 5322 .txt storage)"""
import sys, os, subprocess as sp, re, shutil, base64
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor as TP
from . _common import _up, _die, DATA_DIR
from .sync import sync, SYNC_ROOT

SSH_DIR = SYNC_ROOT / 'ssh'
def _parse(f): return {k.strip(): v.strip() for line in f.read_text().splitlines() if ':' in line for k, v in [line.split(':', 1)]}
def _save(n, h, pw=None, **kw):
    SSH_DIR.mkdir(parents=True, exist_ok=True); d = _parse(SSH_DIR/f'{n}.txt') if (SSH_DIR/f'{n}.txt').exists() else {}
    d.update({'Name': n, 'Host': h}); pw and d.update({'Password': pw}); d.update({k: v for k, v in kw.items() if v})
    (SSH_DIR/f'{n}.txt').write_text('\n'.join(f"{k}: {v}" for k, v in d.items() if v) + '\n'); sync('ssh')
def _load():
    SSH_DIR.mkdir(parents=True, exist_ok=True); sync('ssh')
    return [d for f in sorted(SSH_DIR.glob('*.txt')) if (d := _parse(f)).get('Name')]
def _rm(n): (SSH_DIR/f'{n}.txt').unlink(missing_ok=True); sync('ssh')
def _os(): return sp.run('uname -sr 2>/dev/null || echo unknown', shell=True, capture_output=True, text=True).stdout.strip()

def run():
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    def _sshd_running(): return _up('localhost:8022') or _up('localhost:22')
    def _sshd_ip():
        try: import socket as S; s=S.socket(S.AF_INET,S.SOCK_DGRAM); s.connect(("8.8.8.8",80)); ip=s.getsockname()[0]; s.close(); return ip
        except: return '?'
    def _sshd_port(): return 8022 if os.environ.get('TERMUX_VERSION') else 22

    raw = _load(); hosts = [(d.get('Name','?'), d.get('Host')) for d in raw]; hmap = {d['Name']: d['Host'] for d in raw if d.get('Host')}; pwmap = {d['Name']: d.get('Password') for d in raw}; osmap = {d['Name']: d.get('OS') for d in raw}

    if wda == 'start': r = sp.run(['sshd'], capture_output=True, text=True) if os.environ.get('TERMUX_VERSION') else sp.run(['sudo', '/usr/sbin/sshd'], capture_output=True, text=True); print(f"✓ sshd started (port {_sshd_port()})") if r.returncode == 0 or _sshd_running() else print(f"x sshd failed: {r.stderr.strip() or 'install openssh-server'}"); return
    if wda == 'stop': sp.run(['pkill', '-x', 'sshd']) if os.environ.get('TERMUX_VERSION') else sp.run(['sudo', 'pkill', '-x', 'sshd']); print("✓ sshd stopped" if not _sshd_running() else "x failed"); return
    if wda in ('status', 's'): u, ip, p = os.environ.get('USER', 'u0_a'), _sshd_ip(), _sshd_port(); print(f"{'✓ RUNNING' if _sshd_running() else 'x STOPPED'}  ssh {u}@{ip} -p {p}"); return
    if not wda: u, ip, p = os.environ.get('USER', 'u0_a'), _sshd_ip(), _sshd_port(); me = next((n for n,h in hosts if ip in h), None); url = sp.run(['git','-C',str(SSH_DIR),'remote','get-url','origin'], capture_output=True, text=True).stdout.strip(); shutil.which('ssh') or print("! pkg install openssh"); print(f"SSH {'✓ ON' if _sshd_running() else 'x OFF'}  →  ssh {u}@{ip} -p {p}{' ('+me+')' if me else ' [not in list]'}\n  {SSH_DIR}\n  {url}\n  start/stop/status  server control\n  setup              install & configure\n  self [name]        add this device\n  add/rm/mv/pw <#>   manage hosts\n  all \"cmd\"          run cmd on all hosts\n  Termux: run 'passwd' to set password before 'a ssh self'\nHosts:"); up=list(TP(8).map(_up,[h or '' for _,h in hosts])); [print(f"  {i}. x {n}: missing Name:/Host:") if not h else print(f"  {i}. {'✓x'[not up[i]]} {n}: {h}{' [pw]' if pwmap.get(n) else ''}{' <- this' if n==me else ''}") for i,(n,h) in enumerate(hosts)] or print("  (none)"); (any(not x for x in up) and not sp.run("ping -c1 -W1 $(ip route|awk '/default/{print $3}')",shell=True,capture_output=True).returncode) and print("! Unreachable hosts - check AP isolation (wired↔wifi blocked)"); print(f"\nAI: a ssh <#|name> cmd"); return
    if wda == 'setup': ip = _sshd_ip(); u = os.environ.get('USER', 'user'); ok = _sshd_running(); cmd = 'pkg install -y openssh && sshd' if os.environ.get('TERMUX_VERSION') else 'sudo apt install -y openssh-server && sudo systemctl enable --now ssh'; (not ok and input("SSH not running. Install? (y/n): ").lower() in ['y', 'yes'] and sp.run(cmd, shell=True)); ok = ok or _sshd_running(); print(f"This: {os.environ.get('HOSTNAME', 'host')} ({u}@{ip}:{_sshd_port()})\nSSH: {'✓ running' if ok else 'x not running'}\n\nTo connect here from another device:\n  ssh {u}@{ip} -p {_sshd_port()}"); return
    if wda == 'key': kf = Path.home()/'.ssh/id_ed25519'; kf.exists() or sp.run(['ssh-keygen','-t','ed25519','-N','','-f',str(kf)]); print(f"Public key:\n{(kf.with_suffix('.pub')).read_text().strip()}"); return
    if wda == 'auth': d = Path.home()/'.ssh'; d.mkdir(exist_ok=True); af = d/'authorized_keys'; k = input("Paste public key: ").strip(); af.open('a').write(f"\n{k}\n"); af.chmod(0o600); print("✓ Added"); return
    if wda=='push-auth': t=sp.run(['gh','auth','token'],capture_output=True,text=True).stdout.strip(); [sp.run([sys.executable,__file__.replace('a_cmd/ssh.py','a.py'),'ssh',sys.argv[3],f"mkdir -p ~/.config/{d}&&echo {base64.b64encode((Path.home()/'.config'/d/f).read_bytes()).decode()}|base64 -d>~/.config/{d}/{f}"+";touch ~/.local/share/a/.auth_shared"*(d<'q')]) for d,f in[('rclone','rclone.conf'),('gh','hosts.yml')]]; t and sp.run([sys.executable,__file__.replace('a_cmd/ssh.py','a.py'),'ssh',sys.argv[3],f'echo "{t}"|gh auth login --with-token']); print("✓"); return
    if wda == 'self':
        wsl = os.path.exists('/proc/version') and 'microsoft' in open('/proc/version').read().lower()
        # === WSL: needs Windows port forward (2222->22) to be reachable from LAN ===
        if wsl:
            wsl_ip = sp.run("hostname -I", shell=True, capture_output=True, text=True).stdout.split()[0]
            win_ip = re.search(r'192\.168\.1\.\d+', sp.run(["powershell.exe","-c","ipconfig"],capture_output=True,text=True).stdout)
            if not win_ip: _die("x No Windows LAN IP (192.168.1.x) found")
            ip, p = win_ip.group(), 2222; print(f"WSL: {wsl_ip} → Windows: {ip}:{p}")
            sp.run("pgrep -x sshd >/dev/null || sudo service ssh start", shell=True)
            # Check/setup port forward
            pf = sp.run(["powershell.exe","-c","netsh interface portproxy show all"], capture_output=True, text=True).stdout
            if "2222" not in pf:
                print("Setting up Windows port forward (UAC prompt)...")
                ps1 = f'netsh interface portproxy delete v4tov4 listenport=2222 listenaddress=0.0.0.0 2>$null\nnetsh interface portproxy add v4tov4 listenport=2222 listenaddress=0.0.0.0 connectport=22 connectaddress={wsl_ip}\nnetsh advfirewall firewall delete rule name="WSL SSH" 2>$null\nnetsh advfirewall firewall add rule name="WSL SSH" dir=in action=allow protocol=tcp localport=2222\nWrite-Host "Done" -ForegroundColor Green; netsh interface portproxy show all; pause'
                open("/mnt/c/Windows/Temp/wsl_ssh.ps1","w").write(ps1)
                sp.run(["powershell.exe","-c","Start-Process powershell -Verb RunAs -ArgumentList '-ExecutionPolicy','Bypass','-File','C:\\Windows\\Temp\\wsl_ssh.ps1'"])
                input("Press Enter after Windows admin window shows 'Done'...")
                if "2222" not in sp.run(["powershell.exe","-c","netsh interface portproxy show all"], capture_output=True, text=True).stdout: _die("x Port forward failed")
            print("✓ Port forward OK")
        # === macOS: may need to enable Remote Login ===
        elif sys.platform=='darwin':
            sp.run(['nc','-z','localhost','22'],capture_output=True).returncode and (input("Remote Login off. Enable? (y/n): ").lower() in ['y','yes'] and sp.run(['sudo','systemsetup','-setremotelogin','on']) or _die("x enable Remote Login"))
            ip, p = sp.run("ipconfig getifaddr en0", shell=True, capture_output=True, text=True).stdout.strip() or _sshd_ip(), _sshd_port()
        # === Linux/Termux: use local IP ===
        else: ip, p = sp.run("hostname -I 2>/dev/null | awk '{print $1}'", shell=True, capture_output=True, text=True).stdout.strip() or _sshd_ip(), _sshd_port()
        # self [name] [pw]
        u=os.environ.get('USER') or sp.run('whoami',shell=True,capture_output=True,text=True).stdout.strip() or 'user'; h=f"{u}@{ip}"+(f":{p}"if p!=22 else""); a=sys.argv[3:]; n=a[0]if a else u; pw=a[1]if len(a)>1 else input("Pw:").strip()
        os.system(f'sshpass -p "{pw}" ssh -oStrictHostKeyChecking=no -p{p} localhost exit')or 0
        _save(n, h, pw, OS=_os()); print(f"✓ {n}={h} [{_os()}]"); return
    if wda in ('info','i'): [print(f"{n}: ssh {'-p '+hp[1]+' ' if len(hp:=h.rsplit(':',1))>1 else ''}{hp[0]}{' ('+osmap[n]+')' if osmap.get(n) else ''}") for n,h in hosts]; return
    if wda == 'os':
        cmd = 'uname -sr'; results = []
        def _get(d): n,h,pw = d.get('Name'), d.get('Host'), d.get('Password'); hp=h.rsplit(':',1) if h else ['','']; r=sp.run((['sshpass','-p',pw]if pw else[])+['ssh','-oConnectTimeout=5','-oStrictHostKeyChecking=no']+(['-p',hp[1]]if len(hp)>1 else[])+[hp[0],cmd],capture_output=1,text=1); return (n,h,pw,r.stdout.strip() if not r.returncode else None)
        for n,h,pw,os_info in TP(8).map(_get, raw):
            if os_info: _save(n, h, pw, OS=os_info); print(f"✓ {n}: {os_info}")
            else: print(f"x {n}: unreachable")
        return
    if wda in ('all','*') and len(sys.argv)>3:
        cmd='bash -ic '+repr(' '.join(sys.argv[3:])); ok_l, fail_l = [], []
        def _run(nh): n,h=nh; pw=pwmap.get(n); hp=h.rsplit(':',1); r=sp.run((['sshpass','-p',pw]if pw else[])+['ssh','-oConnectTimeout=5','-oStrictHostKeyChecking=no','-oIdentitiesOnly=yes']+(['-p',hp[1]]if len(hp)>1 else[])+[hp[0],cmd],capture_output=1,text=1); return(n,not r.returncode,(r.stdout or r.stderr).strip())
        for n,ok,out in TP(8).map(_run,hosts): (ok_l if ok else fail_l).append(n); print(f"\n{'✓' if ok else 'x'} {n}"); out and print('\n'.join('  '+l for l in out.split('\n')[:100]))
        print(f"\n✓ {len(ok_l)}" + (f"  x {len(fail_l)} ({','.join(fail_l)})" if fail_l else ""))
        return
    if wda == 'rm' and len(sys.argv) > 3: a=sys.argv[3]; n=hosts[int(a)][0] if a.isdigit() and int(a)<len(hosts) else a; _rm(n); print(f"✓ rm {n}"); return
    if wda == 'pw' and len(sys.argv) > 3: a=sys.argv[3]; n=hosts[int(a)][0] if a.isdigit() and int(a)<len(hosts) else a; pw=input(f"Pw for {n}: ").strip(); _save(n, hmap[n], pw); print(f"✓ {n}"); return
    if wda in ('mv','rename') and len(sys.argv) > 4: o,n=sys.argv[3:5]; _rm(o); _save(n, hmap.get(o,""), pwmap.get(o)); print(f"✓ {o} → {n}"); return
    if wda == 'add': h=re.sub(r'\s+-p\s*(\d+)',r':\1',input("Host (user@ip): ").strip()); n=input("Name: ").strip() or h.split('@')[-1].split(':')[0].split('.')[-1]; pw=input("Pw? ").strip() or None; hp=h.rsplit(':',1); 'ok' in sp.run((['sshpass','-p',pw] if pw else [])+['ssh','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=no']+(['-p',hp[1]] if len(hp)>1 else [])+[hp[0],'echo ok'],capture_output=True,text=True).stdout or _die("x auth failed"); _save(n, h, pw); print(f"✓ {n}={h}{' [pw]' if pw else ''}"); return
    nm = hosts[int(wda)][0] if wda.isdigit() and int(wda) < len(hosts) else (_die(f"x No host #{wda}. Run: a ssh") if wda.isdigit() else wda); shutil.which('ssh') or _die("x ssh not installed"); h=hmap.get(nm,nm); pw=pwmap.get(nm); hp=h.rsplit(':',1)
    if len(sys.argv)>3:
        tty = sys.stdout.isatty(); cmd = ['ssh'] + (['-tt'] if tty else ['-oConnectTimeout=10']) + ['-oStrictHostKeyChecking=no'] + (['-p',hp[1]] if len(hp)>1 else []) + [hp[0], 'bash -ic '+repr(' '.join(sys.argv[3:]))+' 2>&1']
        r = sp.run((['sshpass','-p',pw] if pw else [])+cmd, capture_output=not tty, text=True); tty or print('\n'.join(l for l in r.stdout.split('\n') if not l.startswith('bash:'))); return
    cmd=['ssh','-tt','-o','StrictHostKeyChecking=accept-new']+(['-p',hp[1]] if len(hp)>1 else [])+[hp[0]]
    if not pw and nm in hmap: pw=input("Password? ").strip(); pw and _save(nm, hmap[nm], pw)
    pw and not shutil.which('sshpass') and _die("x need sshpass"); print(f"Connecting to {nm}...", file=sys.stderr, flush=True); os.execvp('sshpass',['sshpass','-p',pw]+cmd) if pw else os.execvp('ssh',cmd)
