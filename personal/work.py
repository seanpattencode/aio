#!/usr/bin/env python3
"""Daily work agent - processes task list via Claude tmux sessions"""
import sys, os, time, subprocess as sp, re, json
from pathlib import Path
from base import save, send, GOALS

P = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(P / 'lib'))
from a_cmd._common import (init_db, load_cfg, load_proj, tm,
    create_sess, alog, SYNC_ROOT, DEVICE_ID, DATA_DIR)

TASKS_DIR = SYNC_ROOT / 'tasks'
IDEAS_DIR = P / 'ideas'
NOTES_DIR = SYNC_ROOT / 'notes'
WORK_LOG = Path(DATA_DIR) / 'work_log.jsonl'
TIMEOUT = 600

def load_tasks(limit=5):
    if not TASKS_DIR.exists(): return []
    tasks = []
    for f in sorted(TASKS_DIR.iterdir()):
        nm = f.name
        if nm.startswith('.') or nm == 'README.md': continue
        hp = len(nm) > 5 and nm[5] == '-' and nm[:5].isdigit()
        pri = nm[:5] if hp else '50000'
        slug = nm[6:] if hp else nm
        slug = re.sub(r'_\d{8}T\d{6}.*$', '', slug).replace('.txt', '')
        slug = re.sub(r'_[0-9a-f]{8,}$', '', slug)  # strip device ID suffix
        body = ''
        if f.is_dir():
            # Root-level .txt files have the main description
            for tf in sorted(f.glob('*.txt')):
                txt = tf.read_text().strip()
                if not txt: continue
                for line in txt.splitlines():
                    if line.startswith('Text: '): body = body or line[6:]
                if not body: body = txt.split('\n')[0]
        elif f.is_file():
            body = f.read_text().strip()
            if body.startswith('Text: '): body = body[6:].split('\n')[0]
        tasks.append({'file': str(f), 'slug': slug, 'pri': pri, 'body': body or slug.replace('-', ' ')})
    return tasks[:limit]

def work_one(task, cfg):
    slug = re.sub(r'[^a-z0-9]', '-', task['slug'].lower())[:20]
    sn = f"work-{slug}-{int(time.time())}"
    proj = load_proj()
    proj_path = proj[0][0] if proj else str(P)
    wt_dir = cfg.get('worktrees_dir', os.path.expanduser('~/projects/a/adata/worktrees'))

    create_sess(sn, proj_path, 'claude --dangerously-skip-permissions', cfg)

    for _ in range(30):
        time.sleep(1)
        out = sp.run(['tmux', 'capture-pane', '-t', sn, '-p'], capture_output=True, text=True).stdout
        if any(x in out.lower() for x in ['type your message', 'claude', 'opus']): break

    prompt = f"""Ultrathink. You have ONE task. Complete in <10 minutes then run: a done

TASK: {task['body']}

READ CONTEXT FIRST:
- Goals: {GOALS}
- Ideas: {IDEAS_DIR}/
- Tasks: {TASKS_DIR}/
- Notes: {NOTES_DIR}/

RULES:
- If CODE: create worktree via `git worktree add {wt_dir}/{slug} -b wt-{slug} HEAD`, work there, commit, `gh pr create`
- If DOCUMENT: write to {SYNC_ROOT}/docs/, then `a sync`
- If EMAIL: `python3 -c "import sys;sys.path.insert(0,'{P}/agents');from base import send;send('subject','body')"`
- Keep changes SMALL. When done: a done"""

    tm.send(sn, prompt); time.sleep(0.3)
    sp.run(['tmux', 'send-keys', '-t', sn, 'Enter'])

    entry = {'session': sn, 'task': task['slug'], 'body': task['body'][:100],
             'start': time.time(), 'device': DEVICE_ID, 'status': 'running'}
    WORK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WORK_LOG, 'a') as f: f.write(json.dumps(entry) + '\n')
    alog(f"work:{sn} task:{task['slug']}")

    done_file = Path(DATA_DIR) / '.done'; done_file.unlink(missing_ok=True)
    start = time.time()
    while time.time() - start < TIMEOUT:
        if done_file.exists(): break
        if not tm.has(sn): break
        time.sleep(5)

    out = sp.run(['tmux', 'capture-pane', '-t', sn, '-p', '-S', '-200'],
                 capture_output=True, text=True).stdout

    entry['end'] = time.time()
    entry['status'] = 'done' if done_file.exists() else 'timeout'
    entry['output'] = out.strip()[-300:]
    with open(WORK_LOG, 'a') as f: f.write(json.dumps(entry) + '\n')

    sp.run(['tmux', 'kill-session', '-t', sn], capture_output=True)
    save('work', f"Task: {task['slug']}\nStatus: {entry['status']}\n\n{out[-500:]}")
    alog(f"work:{sn} -> {entry['status']}")
    print(f"  {entry['status']}: {task['slug']}")

def run():
    init_db(); cfg = load_cfg()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
    tasks = load_tasks(limit)
    if not tasks: print("No tasks"); return
    print(f"Processing {len(tasks)} tasks...")
    for i, t in enumerate(tasks):
        print(f"\n[{i+1}/{len(tasks)}] {t['slug']}")
        work_one(t, cfg)
    print("\n+ Work complete")

if __name__ == '__main__': run()
