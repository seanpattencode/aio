import sys, os, socket, subprocess as S, webbrowser as W, time

def _vpy():
    lib = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    vp = os.path.join(os.path.dirname(lib), 'adata', 'venv', 'bin', 'python')
    return vp if os.access(vp, os.X_OK) else sys.executable

def _try(p=8080):
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', p)) == 0: W.open(f'http://127.0.0.1:{p}'); return True

def _bg(m, p):
    S.Popen([_vpy(), '-c', f"from ui.{m} import run;run({p})"], start_new_session=True, stdout=S.DEVNULL, stderr=None, env={**os.environ, 'PYTHONPATH': os.path.dirname(os.path.dirname(os.path.realpath(__file__)))})
    time.sleep(0.3); W.open(f'http://127.0.0.1:{p}'); print(f'UI on 127.0.0.1:{p}')

def run():
    a, M = sys.argv[2:], {'1': 'ui_full', '2': 'ui_xterm'}
    if a and a[0][0] == 'k': S.run(['pkill', '-f', 'ui.ui_']); print('Killed')
    elif a and (m := M.get(a[0])): _try(p := int(a[1]) if len(a) > 1 and a[1].isdigit() else 8080) or _bg(m, p)
    else: print("a ui 1  full (cmd+term)\na ui 2  xterm only\na ui k  kill")

if __name__ == '__main__': run()
