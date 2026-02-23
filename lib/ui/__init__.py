import sys, os, subprocess as S, webbrowser as W, time, platform

def _vpy():
    lib = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    vp = os.path.join(os.path.dirname(lib), 'adata', 'venv', 'bin', 'python')
    return vp if os.access(vp, os.X_OK) else sys.executable

PORT = 1111
_LIB = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

def _url(p): return f'http://localhost:{p}'  # universal: same URL works mobile+desktop, bookmarkable

def _bg(m, p):
    S.Popen([_vpy(), '-c', f"from ui.{m} import run;run({p})"], start_new_session=True, stdout=S.DEVNULL, stderr=None, env={**os.environ, 'PYTHONPATH': _LIB})
    time.sleep(0.3); W.open(_url(p))

_TERMUX = os.path.isdir('/data/data/com.termux')
def _plist(): return os.path.expanduser('~/Library/LaunchAgents/com.a.ui.plist')
def _unit(): return os.path.expanduser('~/.config/systemd/user/a-ui.service')
def _svdir(): return os.path.join(os.environ.get('PREFIX', '/usr'), 'var/service/a-ui')

def _svc_off():
    if platform.system() == 'Darwin':
        p = _plist()
        if os.path.exists(p): S.run(['launchctl', 'unload', p], capture_output=True); os.remove(p)
    elif _TERMUX:
        sd = _svdir()
        if os.path.isdir(sd): S.run(['sv', 'down', 'a-ui'], capture_output=True); S.run(['rm', '-rf', sd])
    else:
        S.run(['systemctl', '--user', 'disable', '--now', 'a-ui'], capture_output=True)
        u = _unit()
        if os.path.exists(u): os.remove(u)

def _svc_on(m='ui_full', p=PORT):
    vpy, lib = _vpy(), _LIB
    if platform.system() == 'Darwin':
        pf = _plist(); _svc_off()
        os.makedirs(os.path.dirname(pf), exist_ok=True)
        with open(pf, 'w') as f:
            f.write(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.a.ui</string>
    <key>ProgramArguments</key><array>
        <string>{vpy}</string><string>-c</string>
        <string>from ui.{m} import run;run({p})</string>
    </array>
    <key>EnvironmentVariables</key><dict>
        <key>PYTHONPATH</key><string>{lib}</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardErrorPath</key><string>/tmp/a-ui.err</string>
</dict>
</plist>''')
        S.run(['launchctl', 'load', pf], capture_output=True); return True
    if _TERMUX:
        sd = _svdir(); _svc_off(); os.makedirs(sd, exist_ok=True); rs = os.path.join(sd, 'run')
        prefix = os.environ.get('PREFIX', '/data/data/com.termux/files/usr')
        with open(rs, 'w') as f: f.write(f'#!{prefix}/bin/sh\nexport PYTHONPATH={lib}\nexec {vpy} -c "from ui.{m} import run;run({p})"\n')
        os.chmod(rs, 0o755); S.run(['sv', 'up', 'a-ui'], capture_output=True); return True
    if S.run(['systemctl', '--user', '--version'], capture_output=True).returncode == 0:
        _svc_off(); ud = os.path.dirname(_unit()); os.makedirs(ud, exist_ok=True)
        with open(_unit(), 'w') as f:
            f.write(f'[Unit]\nDescription=a UI server\n[Service]\nExecStart={vpy} -c "from ui.{m} import run;run({p})"\nEnvironment=PYTHONPATH={lib}\nRestart=always\nRestartSec=2\n[Install]\nWantedBy=default.target\n')
        S.run(['systemctl', '--user', 'daemon-reload']); S.run(['systemctl', '--user', 'enable', '--now', 'a-ui']); return True
    return False

def run():
    a = sys.argv[2:]
    if a and a[0][0] == 'k':
        S.run(['pkill', '-9', '-f', 'ui.ui_']); print('Killed (service will restart)')
    elif a and a[0] == 'on':
        if _svc_on(): print(f'UI service on — {_url(PORT)}')
        else: print('No service manager (use a ui)'); sys.exit(1)
    elif a and a[0] == 'off':
        _svc_off(); S.run(['pkill', '-9', '-f', 'ui.ui_']); print('UI service off')
    else:
        p = int(a[0]) if a and a[0].isdigit() else PORT
        S.run(['pkill','-9','-f','ui.ui_'],capture_output=True)
        _bg('ui_full', p)
        print(f"{_url(p)}\n  on  auto-start service\n  off stop service\n  k   kill")

if __name__ == '__main__': run()
