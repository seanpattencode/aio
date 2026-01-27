"""aio ssh - SSH management"""
import sys, os, subprocess as sp, re, shutil, base64
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor as TP
from . _common import init_db, db, _up, _die, emit_event, db_sync, DATA_DIR

_kf = Path(DATA_DIR) / '.sshkey'
def _k(): return _kf.read_bytes() if _kf.exists() else (_kf.write_bytes(k := os.urandom(32)) or k)
def _enc(t): k = _k(); return base64.b64encode(bytes(a ^ k[i % 32] for i, a in enumerate(t.encode()))).decode() if t else None
def _dec(e):
    try: k = _k(); return bytes(a ^ k[i % 32] for i, a in enumerate(base64.b64decode(e))).decode() if e else None
    except: return None

def run():
    init_db(); db_sync(pull=True)
    wda = sys.argv[2] if len(sys.argv) > 2 else None

    def _sshd_running(): return sp.run(['pgrep', '-x', 'sshd'], capture_output=True).returncode == 0
    def _sshd_ip(): r = sp.run("ipconfig getifaddr en0 2>/dev/null || ifconfig 2>/dev/null | grep -A1 'wlan0\\|en0' | grep inet | awk '{print $2}'", shell=True, capture_output=True, text=True); return r.stdout.strip() or '?'
    def _sshd_port(): return 8022 if os.environ.get('TERMUX_VERSION') else 22

    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS ssh(name TEXT PRIMARY KEY, host TEXT, pw TEXT)"); hosts = list(c.execute("SELECT name,host FROM ssh")); hmap = {r[0]: r[1] for r in hosts}; pwmap = {r[0]: _dec(r[2]) if r[2] else None for r in c.execute("SELECT name,host,pw FROM ssh")}

    if wda == 'start': r = sp.run(['sshd'], capture_output=True, text=True) if os.environ.get('TERMUX_VERSION') else sp.run(['sudo', '/usr/sbin/sshd'], capture_output=True, text=True); print(f"✓ sshd started (port {_sshd_port()})") if r.returncode == 0 or _sshd_running() else print(f"x sshd failed: {r.stderr.strip() or 'install openssh-server'}"); return
    if wda == 'stop': sp.run(['pkill', '-x', 'sshd']) if os.environ.get('TERMUX_VERSION') else sp.run(['sudo', 'pkill', '-x', 'sshd']); print("✓ sshd stopped" if not _sshd_running() else "x failed"); return
    if wda in ('status', 's'): u, ip, p = os.environ.get('USER', 'u0_a'), _sshd_ip(), _sshd_port(); print(f"{'✓ RUNNING' if _sshd_running() else 'x STOPPED'}  ssh {u}@{ip} -p {p}"); return
    if not wda: u, ip, p = os.environ.get('USER', 'u0_a'), _sshd_ip(), _sshd_port(); shutil.which('ssh') or print("! pkg install openssh"); print(f"SSH {'✓ ON' if _sshd_running() else 'x OFF'}  →  ssh {u}@{ip} -p {p}\n  start/stop/status  server control\n  setup              install & configure\n  self [name]        add this device\n  add/rm/mv/pw <#>   manage hosts\n  all \"cmd\"          run cmd on all hosts\nHosts:"); up=list(TP(8).map(_up,[h for _,h in hosts])); [print(f"  {i}. {'✓x'[not up[i]]} {n}: {h}{' [pw]' if pwmap.get(n) else ''}") for i,(n,h) in enumerate(hosts)] or print("  (none)"); (any(not x for x in up) and not sp.run("ping -c1 -W1 $(ip route|awk '/default/{print $3}')",shell=True,capture_output=True).returncode) and print("! Unreachable hosts - check AP isolation (wired↔wifi blocked)"); print(f"\nAI: aio ssh <#|name> cmd"); return
    if wda == 'setup': ip = _sshd_ip(); u = os.environ.get('USER', 'user'); ok = _sshd_running(); cmd = 'pkg install -y openssh && sshd' if os.environ.get('TERMUX_VERSION') else 'sudo apt install -y openssh-server && sudo systemctl enable --now ssh'; (not ok and input("SSH not running. Install? (y/n): ").lower() in ['y', 'yes'] and sp.run(cmd, shell=True)); ok = ok or _sshd_running(); print(f"This: {os.environ.get('HOSTNAME', 'host')} ({u}@{ip}:{_sshd_port()})\nSSH: {'✓ running' if ok else 'x not running'}\n\nTo connect here from another device:\n  ssh {u}@{ip} -p {_sshd_port()}"); return
    if wda == 'key': kf = Path.home()/'.ssh/id_ed25519'; kf.exists() or sp.run(['ssh-keygen','-t','ed25519','-N','','-f',str(kf)]); print(f"Public key:\n{(kf.with_suffix('.pub')).read_text().strip()}"); return
    if wda == 'auth': d = Path.home()/'.ssh'; d.mkdir(exist_ok=True); af = d/'authorized_keys'; k = input("Paste public key: ").strip(); af.open('a').write(f"\n{k}\n"); af.chmod(0o600); print("✓ Added"); return
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
        # Register
        u = os.environ.get('USER','user'); h = f"{u}@{ip}" + (f":{p}" if p != 22 else ""); n = (sys.argv[3:] or [u])[0]; pw=input("Pw: ").strip()
        sp.run(['sshpass','-p',pw,'ssh','-o','StrictHostKeyChecking=no','localhost','exit'],capture_output=True).returncode and _die("x bad pw")
        (c:=db()).execute("INSERT OR REPLACE INTO ssh(name,host,pw)VALUES(?,?,?)",(n,h,_enc(pw))); c.commit(); emit_event("ssh","add",{"name":n,"host":h,"pw":_enc(pw)}); db_sync(); print(f"✓ {n}={h}"); return
    if wda in ('info','i'): [print(f"{n}: ssh {'-p '+hp[1]+' ' if len(hp:=h.rsplit(':',1))>1 else ''}{hp[0]}") for n,h in hosts]; return
    if wda in ('all','*') and len(sys.argv)>3:
        cmd='bash -ic '+repr(' '.join(sys.argv[3:]));
        def _run(nh): n,h=nh; pw=pwmap.get(n); hp=h.rsplit(':',1); r=sp.run((['sshpass','-p',pw] if pw else [])+['ssh','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=accept-new']+(['-p',hp[1]] if len(hp)>1 else [])+[hp[0],cmd],capture_output=True,text=True); return(n,r.returncode==0,(r.stdout or r.stderr).split('\n')[0][:50])
        [print(f"{'✓' if ok else 'x'} {n}" + (f": {out}" if out else "")) for n,ok,out in TP(8).map(_run,hosts)]; return
    if wda == 'rm' and len(sys.argv) > 3: a=sys.argv[3]; n=hosts[int(a)][0] if a.isdigit() and int(a)<len(hosts) else a; (c:=db()).execute("DELETE FROM ssh WHERE name=?",(n,)); c.commit(); emit_event("ssh","archive",{"name":n}); db_sync(); print(f"✓ rm {n}"); return
    if wda == 'pw' and len(sys.argv) > 3: a=sys.argv[3]; n=hosts[int(a)][0] if a.isdigit() and int(a)<len(hosts) else a; pw=input(f"Pw for {n}: ").strip(); (c:=db()).execute("UPDATE ssh SET pw=? WHERE name=?",(_enc(pw) if pw else None,n)); c.commit(); emit_event("ssh","update",{"name":n,"pw":_enc(pw) if pw else None}); db_sync(); print(f"✓ {n}"); return
    if wda in ('mv','rename') and len(sys.argv) > 4: o,n=sys.argv[3:5]; p=pwmap.get(o); h=hmap.get(o,""); (c:=db()).execute("DELETE FROM ssh WHERE name=?",(o,)); c.execute("INSERT OR REPLACE INTO ssh(name,host,pw)VALUES(?,?,?)",(n,h,_enc(p) if p else None)); c.commit(); emit_event("ssh","rename",{"old":o,"new":n,"host":h}); db_sync(); print(f"✓ {o} → {n}"); return
    if wda == 'add': h=re.sub(r'\s+-p\s*(\d+)',r':\1',input("Host (user@ip): ").strip()); _up(h) or _die(f"x cannot connect to {h}"); n=input("Name: ").strip() or h.split('@')[-1].split(':')[0].split('.')[-1]; pw=input("Pw? ").strip() or None; (c:=db()).execute("INSERT OR REPLACE INTO ssh(name,host,pw) VALUES(?,?,?)",(n,h,_enc(pw) if pw else None)); c.commit(); emit_event("ssh","add",{"name":n,"host":h,"pw":_enc(pw) if pw else None}); db_sync(); print(f"✓ {n}={h}{' [pw]' if pw else ''}"); return
    nm = hosts[int(wda)][0] if wda.isdigit() and int(wda) < len(hosts) else (_die(f"x No host #{wda}. Run: aio ssh") if wda.isdigit() else wda); shutil.which('ssh') or _die("x ssh not installed"); h=hmap.get(nm,nm); pw=pwmap.get(nm); hp=h.rsplit(':',1); cmd=['ssh','-tt','-o','StrictHostKeyChecking=accept-new']+(['-p',hp[1]] if len(hp)>1 else [])+[hp[0]]
    if '--cmd' in sys.argv or len(sys.argv)>3: '--cmd' in sys.argv and (print(' '.join(cmd)) or 1) or sp.run((['sshpass','-p',pw] if pw else [])+cmd+sys.argv[3:]); return
    if not pw and nm in hmap: pw=input("Password? ").strip(); pw and ((c:=db()).execute("UPDATE ssh SET pw=? WHERE name=?",(_enc(pw),nm)),c.commit())
    pw and not shutil.which('sshpass') and _die("x need sshpass"); print(f"Connecting to {nm}...", file=sys.stderr, flush=True); os.execvp('sshpass',['sshpass','-p',pw]+cmd) if pw else os.execvp('ssh',cmd)
