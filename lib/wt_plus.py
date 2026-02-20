"""aio <key>++ - Create worktree and start session"""
import sys, os
from datetime import datetime
from _common import init_db, load_cfg, load_proj, load_sess, wt_create, create_sess, send_prefix, launch_win, tm, _env

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    sess = load_sess(cfg)
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/a/adata/worktrees"))
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    new_win = '--new-window' in sys.argv or '-w' in sys.argv
    wd = os.getcwd()

    key = arg[:-2]  # Remove ++
    if key not in sess:
        print(f"x Unknown session key: {key}")
        return

    proj = PROJ[int(wda)] if wda and wda.isdigit() and int(wda) < len(PROJ) else wd
    bn, cmd = sess[key]
    wp = wt_create(proj, f"{bn}-{datetime.now().strftime('%Y%m%d-%H%M%S')}", WT_DIR)
    if not wp:
        return

    sn = os.path.basename(wp)
    create_sess(sn, wp, cmd, cfg, env=_env())
    send_prefix(sn, bn, wp, cfg)

    if new_win:
        launch_win(sn)
    elif "TMUX" in os.environ:
        print(f"✓ Session: {sn}")
    else:
        os.execvp(tm.attach(sn)[0], tm.attach(sn))

run()
