"""aio all - Multi-agent runs"""
import sys, os, json, subprocess as sp
from datetime import datetime
from _common import init_db, load_cfg, load_proj, load_sess, db, _env, parse_specs, ensure_tmux, send_prefix

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    sess = load_sess(cfg)
    WT_DIR = cfg.get('worktrees_dir', os.path.expanduser("~/projects/a/adata/worktrees"))
    wda = sys.argv[2] if len(sys.argv) > 2 else None

    if wda == 'set':
        ns = ' '.join(sys.argv[3:]) if len(sys.argv) > 3 else ''
        if not ns: print(f"Current: {cfg.get('multi_default', 'c:3')}"); sys.exit(0)
        if not parse_specs([''] + ns.split(), 1, cfg)[0]: print(f"Invalid: {ns}"); sys.exit(1)
        with db() as c: c.execute("INSERT OR REPLACE INTO config VALUES ('multi_default', ?)", (ns,)); c.commit(); print(f"✓ Default: {ns}"); sys.exit(0)

    pp, si = (PROJ[int(wda)][0], 3) if wda and wda.isdigit() and int(wda) < len(PROJ) else (os.getcwd(), 2)
    if sp.run(['git','-C',pp,'rev-parse'],capture_output=True).returncode: print(f"x Not a git repo: {pp}"); sys.exit(1)
    specs, prompt, is_default = parse_specs(sys.argv, si, cfg)
    prompt = None if is_default else prompt
    if not specs: ds = cfg.get('multi_default', 'l:3'); specs, _, _ = parse_specs([''] + ds.split(), 1, cfg); print(f"Using: {ds}")
    now = datetime.now(); total, rn = sum(c for _, c in specs), os.path.basename(pp)
    rid = now.strftime('%b%d-%-I%M%p').lower()
    wt = WT_DIR if os.path.exists(os.path.dirname(WT_DIR)) else os.path.expanduser("~/projects/a/adata/worktrees")
    sn, rd = f"{rn}-{rid}", os.path.join(wt, rn, rid); os.makedirs(rd, exist_ok=True)
    cd = os.path.join(rd, "candidates"); os.makedirs(cd, exist_ok=True)
    with open(os.path.join(rd, "run.json"), "w") as f: json.dump({"agents": [f"{k}:{c}" for k, c in specs], "created": rid, "repo": pp}, f)
    with db() as c: c.execute("INSERT OR REPLACE INTO multi_runs VALUES (?, ?, '', ?, 'running', CURRENT_TIMESTAMP, NULL)", (rid, pp, json.dumps([f"{k}:{c}" for k, c in specs]))); c.commit()
    print(f"{total} agents in {rn}/{rid}..."); env, launched, an = _env(), [], {}
    for ak, cnt in specs:
        bn, bc = sess.get(ak, (None, None))
        if not bn: continue
        for i in range(cnt):
            an[bn] = an.get(bn, 0) + 1; aid = f"{ak}{i}"; wt_path = os.path.join(cd, aid)
            sp.run(['git', '-C', pp, 'worktree', 'add', '-b', f'wt-{rn}-{rid}-{aid}', wt_path], capture_output=True, env=env)
            if os.path.exists(wt_path): launched.append((wt_path, bc)); print(f"✓ {bn}-{an[bn]}")
    if not launched: print("x No agents created"); sys.exit(1)
    sp.run(['tmux', 'new-session', '-d', '-s', sn, '-c', launched[0][0], launched[0][1]], env=env)
    for wt_path, bc in launched[1:]: sp.run(['tmux', 'split-window', '-h', '-t', sn, '-c', wt_path, bc], env=env)
    sp.run(['tmux', 'split-window', '-h', '-t', sn, '-c', cd], env=env); sp.run(['tmux', 'send-keys', '-t', sn, f'n={len(launched)}; while read -ep "> " c; do [ -n "$c" ] && for i in $(seq 0 $((n-1))); do tmux send-keys -l -t ":.$i" "$c"; tmux send-keys -t ":.$i" C-m; done; done', 'C-m'])
    sp.run(['tmux', 'select-layout', '-t', sn, 'even-horizontal'], env=env); ensure_tmux(cfg)
    # send prefix + prompt to each agent pane in background
    for idx, (wt_path, bc) in enumerate(launched):
        send_prefix(f"{sn}:.{idx}", 'claude', wt_path, cfg, prompt)
    print(f"\n+ '{sn}': {len(launched)}+broadcast"); print(f"   tmux switch-client -t {sn}") if "TMUX" in os.environ else os.execvp('tmux', ['tmux', 'attach', '-t', sn])

run()
