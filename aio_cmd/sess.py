"""aio <key> - Start session (fallback handler)"""
import sys, os, subprocess as sp
from . _common import (init_db, load_cfg, load_proj, load_apps, load_sess, tm, _env,
                       get_dir_sess, create_sess, send_prefix, launch_win, _start_log,
                       _ghost_claim, _GM, SCRIPT_DIR, fmt_cmd)

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    APPS = load_apps()
    sess = load_sess(cfg)
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    new_win = '--new-window' in sys.argv or '-w' in sys.argv
    with_term = '--with-terminal' in sys.argv or '-t' in sys.argv

    # Parse working directory
    try: WORK_DIR = os.getcwd()
    except FileNotFoundError: WORK_DIR = os.path.expanduser("~"); os.chdir(WORK_DIR)

    # Determine working directory
    is_wda_prompt = False
    _cmd_kw = {'add', 'remove', 'rm', 'cmd', 'command', 'commands', 'app', 'apps', 'prompt', 'a', 'all', 'review', 'w'}
    if wda and wda.isdigit() and arg not in _cmd_kw:
        idx = int(wda)
        if 0 <= idx < len(PROJ): wd = PROJ[idx]
        elif 0 <= idx - len(PROJ) < len(APPS):
            an, ac = APPS[idx - len(PROJ)]
            print(f"> Running: {an}\n   Command: {ac}")
            os.execvp(os.environ.get('SHELL', '/bin/bash'), [os.environ.get('SHELL', '/bin/bash'), '-c', ac])
        else: wd = WORK_DIR
    elif wda and os.path.isdir(os.path.expanduser(wda)): wd = wda
    elif wda: is_wda_prompt = True; wd = WORK_DIR
    else: wd = WORK_DIR

    # Session handling
    if 'TMUX' in os.environ and arg in sess and len(arg) == 1:
        an, cmd = sess[arg]
        n = int(wda) if wda and wda.isdigit() and int(wda) < 10 else 1
        pids = [sp.run(['tmux', 'split-window', '-hfP', '-F', '#{pane_id}', '-c', wd, cmd], capture_output=True, text=True).stdout.strip() for _ in range(n)]
        sp.run(['tmux', 'select-layout', 'even-horizontal'])
        for pid in pids:
            pid and (sp.run(['tmux', 'split-window', '-v', '-t', pid, '-c', wd, 'sh -c "ls;exec $SHELL"']), sp.run(['tmux', 'select-pane', '-t', pid]))
            pid and send_prefix(pid, an, wd, cfg)
        sys.exit(0)

    if arg in _GM and not wda and (g := _ghost_claim(arg, wd)):
        sn = f"{sess[arg][0] if arg in sess else arg}-{os.path.basename(wd)}"
        sp.run(['tmux', 'rename-session', '-t', g, sn], capture_output=True)
        print(f"Ghost: {sn}")
        os.execvp('tmux', ['tmux', 'attach', '-t', sn])

    sn = get_dir_sess(arg, wd, sess); env = _env(); created = False
    if sn is None:
        n, c = sess.get(arg, (arg, None))
        create_sess(n, wd, c or arg, cfg, env=env)
        sn = n; created = True
    elif not tm.has(sn):
        create_sess(sn, wd, sess[arg][1], cfg, env=env)
        created = True
    else:
        _start_log(sn)

    is_p = arg.endswith('p') and not arg.endswith('pp') and len(arg) == 2 and arg in sess
    pp = [a for a in sys.argv[(2 if is_wda_prompt else (3 if wda else 2)):] if a not in ['-w', '--new-window', '--yes', '-y', '-t', '--with-terminal']]

    if pp:
        print("Prompt queued")
        sp.Popen([sys.executable, os.path.join(SCRIPT_DIR, 'aio_new.py'), 'send', sn, ' '.join(pp)] + (['--no-enter'] if is_p else []), stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif is_p and (pm := {'cp': cfg.get('codex_prompt', ''), 'lp': cfg.get('claude_prompt', ''), 'gp': cfg.get('gemini_prompt', '')}.get(arg)):
        sp.Popen([sys.executable, os.path.join(SCRIPT_DIR, 'aio_new.py'), 'send', sn, pm, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    elif created and arg in sess:
        send_prefix(sn, sess[arg][0], wd, cfg)

    if new_win:
        launch_win(sn)
        from . _common import launch_dir
        with_term and launch_dir(wd)
    elif "TMUX" in os.environ or not sys.stdout.isatty():
        print(f"✓ Session: {sn}")
    else:
        os.execvp(tm.attach(sn)[0], tm.attach(sn))
