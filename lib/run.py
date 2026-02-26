"""aio run - Run task on remote"""
import sys, os, shlex
from _common import init_db, load_sess, db
# ssh module ported to C; _dec was already dead code

def run():
    init_db()
    sess = load_sess({})
    args = sys.argv[2:]; hosts = list(db().execute("SELECT name,host FROM ssh"))
    [print(f"  {i}. {n}") for i,(n,h) in enumerate(hosts)] if args and not args[0].isdigit() else None
    hi = int(args.pop(0)) if args and args[0].isdigit() else int(input("Host #: ").strip())
    agent = args.pop(0) if args and args[0] in 'clg' else 'l'
    with db() as c:
        n, h, epw = list(c.execute("SELECT name,host,pw FROM ssh"))[hi]
        hp = h.rsplit(':',1); pw = _dec(epw)
        task = ' '.join(args)
        proj = os.path.basename(os.getcwd())
    cmd = f'cd ~/projects/{proj} && aio {agent}++' + (f' && sleep 2 && tmux send-keys -t $(tmux ls -F "#{{{{session_name}}}}" | grep "^{proj}" | tail -1) {shlex.quote(task)} Enter' if task else '')
    print(f"→ {n}")
    os.execvp('sshpass', ['sshpass', '-p', pw, 'ssh', '-tt', '-p', hp[1] if len(hp) > 1 else '22', hp[0], cmd])
run()
