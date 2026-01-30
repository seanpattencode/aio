"""aio login - GitHub token sync across trusted devices
This creates a sync chain of trusted devices. The truth is if one device got compromised and
you had your gh token there, it could already be found and copied. So if you were gh logging
in on multiple devices anyways (which you are), there isn't actually any more risk than before
in copying them if it's in a trusted location. In the future a different location than github
can be selected, but remember that billion dollar corporate software is securely held in github already."""
import subprocess as sp
from .sync import sync, SYNC_ROOT

LOGIN_DIR = SYNC_ROOT / 'login'
TOKEN_FILE = LOGIN_DIR / 'gh_token.txt'

def _get_local_token():
    r = sp.run(['gh', 'auth', 'token'], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None

def _save_token(token):
    import socket, datetime
    LOGIN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(f"Token: {token}\nSource: {socket.gethostname()}\nCreated: {datetime.datetime.now().isoformat()}\n")
    sync('login')

def _load_token():
    if not TOKEN_FILE.exists(): return None
    for line in TOKEN_FILE.read_text().splitlines():
        if line.startswith('Token:'): return line.split(':', 1)[1].strip()
    return None

def _apply_token(token):
    sp.run(f'echo "{token}" | gh auth login --with-token', shell=True, capture_output=True)

def run():
    enabled = (LOGIN_DIR/'.git').exists()
    if not enabled:
        if input("Enable gh token sharing across devices? [y/n]: ").lower() not in ('y','yes'):
            print("login sharing disabled - run 'a login' again to enable"); return
        sync('login'); enabled = True
    url = sp.run(['git','-C',str(LOGIN_DIR),'remote','get-url','origin'], capture_output=True, text=True).stdout.strip()
    local = _get_local_token()
    if local:
        _save_token(local)
        print(f"saved gh token\n  Local: {TOKEN_FILE}\n  Remote: {url}")
    else:
        token = _load_token()
        if token:
            _apply_token(token)
            print(f"applied gh token\n  Local: {TOKEN_FILE}\n  Remote: {url}" if _get_local_token() else "x failed to apply token")
        else:
            print(f"x no token found\n  Local: {TOKEN_FILE}\n  Remote: {url}\n  Run 'gh auth login' on an authed device first, then 'a login'")
