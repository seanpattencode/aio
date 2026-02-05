"""a <key> - Start session"""
import sys, os, subprocess as sp, shlex
from . _common import (init_db, load_cfg, load_proj, load_apps, load_sess, tm, _env,
                       get_dir_sess, create_sess, send_prefix, launch_win, _start_log,
                       _ghost_claim, _GM, SCRIPT_DIR)

def _add_prompt(cmd, prompt):
    if not prompt or not cmd: return cmd, False
    p = shlex.quote(prompt)
    if 'gemini' in cmd: return cmd + f' -i {p}', True
    if 'claude' in cmd or 'codex' in cmd: return cmd + f' {p}', True
    return cmd, False

def run():
    init_db(); cfg = load_cfg(); PROJ = load_proj(); APPS = load_apps(); sess = load_sess(cfg)
    arg, wda = (sys.argv[1] if len(sys.argv) > 1 else None), (sys.argv[2] if len(sys.argv) > 2 else None)
    new_win, with_term = '--new-window' in sys.argv or '-w' in sys.argv, '--with-terminal' in sys.argv or '-t' in sys.argv

    try: WORK_DIR = os.getcwd()
    except FileNotFoundError: WORK_DIR = os.path.expanduser("~"); os.chdir(WORK_DIR)

    is_wda_prompt, _cmd_kw = False, {'add', 'remove', 'rm', 'cmd', 'command', 'commands', 'app', 'apps', 'prompt', 'a', 'all', 'review', 'w'}
    if wda and wda.isdigit() and arg not in _cmd_kw and not ('TMUX' in os.environ and arg in sess and len(arg) == 1):
        idx = int(wda)
        if 0 <= idx < len(PROJ): wd = PROJ[idx]
        elif 0 <= idx - len(PROJ) < len(APPS):
            an, ac = APPS[idx - len(PROJ)]; print(f"> Running: {an}\n   Command: {ac}"); os.execvp(sh:=os.environ.get('SHELL','/bin/bash'), [sh, '-c', ac])
        else: wd = WORK_DIR
    elif wda and os.path.isdir(os.path.expanduser(wda)): wd = wda
    elif wda: is_wda_prompt = True; wd = WORK_DIR
    else: wd = WORK_DIR

    is_p = arg and arg.endswith('p') and not arg.endswith('pp') and len(arg) == 2 and arg in sess
    pp = [a for a in sys.argv[(2 if is_wda_prompt else (3 if wda else 2)):] if a not in ['-w', '--new-window', '--yes', '-y', '-t', '--with-terminal']]
    prompt = ' '.join(pp) if pp else None

    if 'TMUX' in os.environ and arg in sess and len(arg) == 1:
        an, cmd = sess[arg]
        if prompt: cmd, _ = _add_prompt(cmd, (cfg.get('default_prompt', '') + ' ' if cfg.get('default_prompt') else '') + prompt)
        n = int(wda) if wda and wda.isdigit() and int(wda) < 10 else 1
        pids = [sp.run(['tmux', 'split-window', '-hfP', '-F', '#{pane_id}', '-c', wd, cmd], capture_output=True, text=True).stdout.strip() for _ in range(n)]
        for pid in pids:
            pid and (sp.run(['tmux', 'split-window', '-v', '-t', pid, '-c', wd, 'sh -c "ls;exec $SHELL"']), sp.run(['tmux', 'select-pane', '-t', pid]))
            pid and (not prompt and send_prefix(pid, an, wd, cfg), _start_log(f"{an}-{os.path.basename(wd)}", pid))
        sys.exit(0)

    if arg in _GM and not wda and (g := _ghost_claim(arg, wd)):
        sn=f"{sess[arg][0] if arg in sess else arg}-{os.path.basename(wd)}"; i=0
        while tm.has(sn+f"-{i}"*(i>0)): i+=1
        sn+=f"-{i}"*(i>0); sp.run(['tmux','rename-session','-t',g,sn],capture_output=True); print(f"Ghost: {sn}"); os.execvp((a:=tm.attach(sn))[0],a)

    sn, env, created = get_dir_sess(arg, wd, sess), _env(), False
    if sn is None or not tm.has(sn):
        n, c = sess.get(arg, (arg, None)) if sn is None else (sn, sess[arg][1])
        cmd = c if sn is None else sess[arg][1]
        agent = n if sn is None else sess[arg][0]
        if prompt: dp = cfg.get('default_prompt', ''); cmd, ok = _add_prompt(cmd, (dp + ' ' if dp else '') + prompt); ok and print(f"Prompt: {prompt[:50]}...")
        create_sess(sn or n, wd, cmd, cfg, env=env, skip_prefix=bool(prompt))
        sn, created = sn or n, True
    else:
        _start_log(sn)
        if prompt: sp.Popen([sys.executable, os.path.join(SCRIPT_DIR, 'a.py'), 'send', sn, prompt] + (['--no-enter'] if is_p else []), stdout=sp.DEVNULL, stderr=sp.DEVNULL); print("Prompt queued (existing session)")

    if not prompt:
        if is_p and (pm := {'cp': cfg.get('codex_prompt', ''), 'lp': cfg.get('claude_prompt', ''), 'gp': cfg.get('gemini_prompt', '')}.get(arg)):
            sp.Popen([sys.executable, os.path.join(SCRIPT_DIR, 'a.py'), 'send', sn, pm, '--no-enter'], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        elif created and arg in sess: send_prefix(sn, sess[arg][0], wd, cfg)

    if new_win: launch_win(sn); with_term and __import__('a_cmd._common', fromlist=['launch_dir']).launch_dir(wd)
    elif not sys.stdout.isatty(): print(f"✓ Session: {sn}")
    else: tm.go(sn)
