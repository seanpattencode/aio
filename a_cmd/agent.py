"""aio agent - Spawn autonomous subagent"""
import sys, os, time, subprocess as sp
from pathlib import Path
from . _common import init_db, load_cfg, load_sess, tm, _start_log, _die, DATA_DIR

def run():
    init_db()
    cfg = load_cfg()
    sess = load_sess(cfg)
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    existing = [s.split(':')[0] for s in sp.run(['tmux', 'ls'], capture_output=True, text=True).stdout.split('\n') if s.startswith('agent-')]

    if wda and wda.startswith('agent-') and wda in existing:
        sn, task = wda, ' '.join(sys.argv[3:])
    elif wda and wda.isdigit() and int(wda) < len(existing):
        sn, task = existing[int(wda)], ' '.join(sys.argv[3:])
    else:
        agent = wda if wda in sess else 'g'; task = ' '.join(sys.argv[3:]) if wda in sess else ' '.join(sys.argv[2:])
        if not task:
            if existing: print("Active agents:"); [print(f"  {i}. {s}") for i,s in enumerate(existing)]
            _die("Usage: a agent [g|c|l|#|name] <task>")
        sn = f"agent-{agent}-{int(time.time())}"; _, cmd = sess[agent]
        parent = sp.run(['tmux', 'display-message', '-p', '#S'], capture_output=True, text=True).stdout.strip(); parent = parent if parent.startswith('agent-') else None
        print(f"Agent: {agent} | Task: {task[:50]}..."); tm.new(sn, os.getcwd(), cmd or '', None); _start_log(sn, parent)
        print("Waiting for agent to start..."); last_out, stable = '', 0
        for _ in range(60):
            time.sleep(1); out = sp.run(['tmux', 'capture-pane', '-t', sn, '-p'], capture_output=True, text=True).stdout
            if 'Type your message' in out:
                if out == last_out: stable += 1
                else: stable = 0
                if stable >= 2: break
            last_out = out

    timeout, done_file = 300, Path(f"{DATA_DIR}/.done"); done_file.unlink(missing_ok=True)
    prompt = f'{task}\n\nCommands: "a agent g <task>" spawns gemini subagent, "a agent l <task>" spawns claude subagent. Subagents auto-signal when done. When YOUR task is fully complete, run: a done'
    print(f"Sending to {sn}..."); tm.send(sn, prompt); time.sleep(0.3); sp.run(['tmux', 'send-keys', '-t', sn, 'Enter'])
    print("Waiting for completion..."); start = time.time()
    while not done_file.exists():
        if time.time() - start > timeout: print(f"x Timeout after {timeout}s"); break
        time.sleep(1)
    output = sp.run(['tmux', 'capture-pane', '-t', sn, '-p', '-S', '-100'], capture_output=True, text=True).stdout
    print(f"--- Output ---\n{output}\n--- End ---")
