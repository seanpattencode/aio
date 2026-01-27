"""aio ssh - SSH management"""
import sys, os, subprocess as sp, re, shutil
from pathlib import Path
from . _common import init_db, db, _up, _die, emit_event, db_sync

def run():
    init_db(); db_sync(pull=True)
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    try: import keyring as kr
    except: kr = None
    _pw = lambda n,v=None: (kr.set_password('aio-ssh',n,v),v)[1] if v and kr else kr.get_password('aio-ssh',n) if kr else None

    def _sshd_running(): return sp.run(['pgrep', '-x', 'sshd'], capture_output=True).returncode == 0
    def _sshd_ip(): r = sp.run("ifconfig 2>/dev/null | grep -A1 wlan0 | grep inet | awk '{print $2}'", shell=True, capture_output=True, text=True); return r.stdout.strip() or '?'
    def _sshd_port(): return 8022 if os.environ.get('TERMUX_VERSION') else 22

    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS ssh(name TEXT PRIMARY KEY, host TEXT, pw TEXT)"); hosts = list(c.execute("SELECT name,host FROM ssh")); hmap = {r[0]: r[1] for r in hosts}
        [(c.execute("UPDATE ssh SET pw=NULL WHERE name=?",(n,)), _pw(n,p)) for n,_,p in c.execute("SELECT * FROM ssh WHERE pw IS NOT NULL")]; c.commit()

    if wda == 'start': r = sp.run(['sshd'], capture_output=True, text=True) if os.environ.get('TERMUX_VERSION') else sp.run(['sudo', '/usr/sbin/sshd'], capture_output=True, text=True); print(f"✓ sshd started (port {_sshd_port()})") if r.returncode == 0 or _sshd_running() else print(f"x sshd failed: {r.stderr.strip() or 'install openssh-server'}"); return
    if wda == 'stop': sp.run(['pkill', '-x', 'sshd']) if os.environ.get('TERMUX_VERSION') else sp.run(['sudo', 'pkill', '-x', 'sshd']); print("✓ sshd stopped" if not _sshd_running() else "x failed"); return
    if wda in ('status', 's'): u, ip, p = os.environ.get('USER', 'u0_a'), _sshd_ip(), _sshd_port(); print(f"{'✓ RUNNING' if _sshd_running() else 'x STOPPED'}  ssh {u}@{ip} -p {p}"); return
    if not wda: u, ip, p = os.environ.get('USER', 'u0_a'), _sshd_ip(), _sshd_port(); shutil.which('ssh') or print("! pkg install openssh"); print(f"SSH {'✓ ON' if _sshd_running() else 'x OFF'}  →  ssh {u}@{ip} -p {p}\n  start/stop/status  server control\n  setup              install & configure\n  self [name]        add this device\n  add/rm/mv <name>   manage hosts\nHosts:"); [print(f"  {i}. {n}: {h}{' [pw]' if _pw(n) else ''}") for i,(n,h) in enumerate(hosts)] or print("  (none)"); print(f"\nAI: sshpass -p \"$(python3 -c \"import keyring; print(keyring.get_password('aio-ssh','NAME'))\")\" ssh -p PORT USER@HOST \"cmd\""); return
    if wda == 'setup': ip = _sshd_ip(); u = os.environ.get('USER', 'user'); ok = _sshd_running(); cmd = 'pkg install -y openssh && sshd' if os.environ.get('TERMUX_VERSION') else 'sudo apt install -y openssh-server && sudo systemctl enable --now ssh'; (not ok and input("SSH not running. Install? (y/n): ").lower() in ['y', 'yes'] and sp.run(cmd, shell=True)); ok = ok or _sshd_running(); print(f"This: {os.environ.get('HOSTNAME', 'host')} ({u}@{ip}:{_sshd_port()})\nSSH: {'✓ running' if ok else 'x not running'}\n\nTo connect here from another device:\n  ssh {u}@{ip} -p {_sshd_port()}"); return
    if wda == 'key': kf = Path.home()/'.ssh/id_ed25519'; kf.exists() or sp.run(['ssh-keygen','-t','ed25519','-N','','-f',str(kf)]); print(f"Public key:\n{(kf.with_suffix('.pub')).read_text().strip()}"); return
    if wda == 'auth': d = Path.home()/'.ssh'; d.mkdir(exist_ok=True); af = d/'authorized_keys'; k = input("Paste public key: ").strip(); af.open('a').write(f"\n{k}\n"); af.chmod(0o600); print("✓ Added"); return
    if wda == 'self': u,p = os.environ.get('USER','user'), _sshd_port(); ip = sp.run("hostname -I 2>/dev/null | awk '{print $1}'", shell=True, capture_output=True, text=True).stdout.strip() or _sshd_ip(); h = f"{u}@{ip}" + (f":{p}" if p != 22 else ""); n = (sys.argv[3:] or [u])[0]; pw=input("Pw: ").strip(); sp.run(['sshpass','-p',pw,'ssh','-o','StrictHostKeyChecking=no','localhost','exit'],capture_output=True).returncode and _die("x pw"); _pw(n,pw); (c:=db()).execute("INSERT OR REPLACE INTO ssh(name,host)VALUES(?,?)",(n,h)); c.commit(); emit_event("ssh","add",{"name":n,"host":h,"pw":pw}); db_sync(); print(f"✓ {n}={h}"); return
    if wda in ('info','i'): [print(f"{n}: ssh {'-p '+hp[1]+' ' if len(hp:=h.rsplit(':',1))>1 else ''}{hp[0]}") for n,h in hosts]; return
    if wda == 'rm' and len(sys.argv) > 3: a=sys.argv[3]; n=hosts[int(a)][0] if a.isdigit() and int(a)<len(hosts) else a; _pw(n) and kr and kr.delete_password('aio-ssh',n); (c:=db()).execute("DELETE FROM ssh WHERE name=?",(n,)); c.commit(); emit_event("ssh","archive",{"name":n}); db_sync(); print(f"✓ rm {n}"); return
    if wda in ('mv','rename') and len(sys.argv) > 4: o,n=sys.argv[3:5]; (p:=_pw(o)) and _pw(n,p); p and kr and kr.delete_password('aio-ssh',o); h=hmap.get(o,""); (c:=db()).execute("DELETE FROM ssh WHERE name=?",(o,)); c.execute("INSERT OR REPLACE INTO ssh(name,host)VALUES(?,?)",(n,h)); c.commit(); emit_event("ssh","rename",{"old":o,"new":n,"host":h}); db_sync(); print(f"✓ {o} → {n}"); return
    if wda == 'add': h=re.sub(r'\s+-p\s*(\d+)',r':\1',input("Host (user@ip): ").strip()); _up(h) or _die(f"x cannot connect to {h}"); n=input("Name: ").strip() or h.split('@')[-1].split(':')[0].split('.')[-1]; pw=input("Pw? ").strip() or None; pw and _pw(n,pw); (c:=db()).execute("INSERT OR REPLACE INTO ssh(name,host) VALUES(?,?)",(n,h)); c.commit(); emit_event("ssh","add",{"name":n,"host":h,"pw":pw}); db_sync(); print(f"✓ {n}={h}{' [pw]' if pw else ''}"); return
    nm = hosts[int(wda)][0] if wda.isdigit() and int(wda) < len(hosts) else (_die(f"x No host #{wda}. Run: aio ssh") if wda.isdigit() else wda); shutil.which('ssh') or _die("x ssh not installed"); h=hmap.get(nm,nm); pw=_pw(nm); hp=h.rsplit(':',1); cmd=['ssh','-tt','-o','StrictHostKeyChecking=accept-new']+(['-p',hp[1]] if len(hp)>1 else [])+[hp[0]]
    if 'cmd' in sys.argv or '--cmd' in sys.argv: print(' '.join(cmd)); return
    if not pw and nm in hmap: pw=input("Password? ").strip(); pw and _pw(nm,pw)
    pw and not shutil.which('sshpass') and _die("x need sshpass"); print(f"Connecting to {nm}...", file=sys.stderr, flush=True); os.execvp('sshpass',['sshpass','-p',pw]+cmd) if pw else os.execvp('ssh',cmd)
