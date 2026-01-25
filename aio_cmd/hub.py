"""aio hub - Scheduled jobs"""
import sys, os, subprocess as sp, shutil, re
from pathlib import Path
from . _common import init_db, load_cfg, load_proj, load_apps, db, db_sync, DEVICE_ID, DATA_DIR

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    APPS = load_apps()
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    _tx = os.path.exists('/data/data/com.termux')
    LOG = f"{DATA_DIR}/hub.log"
    db_sync(pull=True)

    if _tx:
        c = db(); c.execute("UPDATE hub_jobs SET device=? WHERE device='localhost'", (DEVICE_ID,)); c.commit(); c.close()
        db_sync()

    _pt = lambda s: (lambda m: f"{int(m[1])+(12 if m[3]=='pm' and int(m[1])!=12 else (-int(m[1]) if m[3]=='am' and int(m[1])==12 else 0))}:{m[2]}" if m else s)(re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)?$', s.lower().strip()))

    def _install(nm, sched, cmd):
        if _tx:
            shutil.which('crontab') or sp.run(['pkg', 'install', '-y', 'cronie'], capture_output=True)
            sp.run(['pgrep', 'crond'], capture_output=True).returncode != 0 and sp.run(['crond'])
            h, m = sched.split(':')
            old = '\n'.join(l for l in (sp.run(['crontab', '-l'], capture_output=True, text=True).stdout or '').split('\n') if f'# aio:{nm}' not in l).strip()
            sp.run(['crontab', '-'], input=f"{old}\n{m} {h} * * * {cmd} >> {LOG} 2>&1 # aio:{nm}\n", text=True)
        else:
            sd = Path.home() / '.config/systemd/user'; sd.mkdir(parents=True, exist_ok=True)
            (sd / f'aio-{nm}.service').write_text(f"[Unit]\nDescription={nm}\n[Service]\nType=oneshot\nExecStart=/bin/bash -c '{cmd} >> {LOG} 2>&1'\n")
            (sd / f'aio-{nm}.timer').write_text(f"[Unit]\nDescription={nm}\n[Timer]\nOnCalendar={sched}\nPersistent=true\n[Install]\nWantedBy=timers.target\n")
            [sp.run(['systemctl', '--user'] + a, capture_output=True) for a in [['daemon-reload'], ['enable', '--now', f'aio-{nm}.timer']]]

    def _uninstall(nm):
        if _tx:
            sp.run(['crontab', '-'], input='\n'.join(l for l in (sp.run(['crontab', '-l'], capture_output=True, text=True).stdout or '').split('\n') if f'# aio:{nm}' not in l) + '\n', text=True)
        else:
            sd = Path.home() / '.config/systemd/user'
            sp.run(['systemctl', '--user', 'disable', '--now', f'aio-{nm}.timer'], capture_output=True)
            [(sd / f'aio-{nm}.{x}').unlink(missing_ok=True) for x in ['timer', 'service']]

    with db() as c:
        jobs = c.execute("SELECT id,name,schedule,prompt,device,enabled,last_run FROM hub_jobs ORDER BY device,name").fetchall()

    if not wda:
        from datetime import datetime as dt
        _lr = lambda t: dt.strptime(t, '%Y-%m-%d %H:%M').strftime('%m/%d %I:%M%p').lower() if t else '-'
        _pj = lambda jobs: [print(f"{i:<3}{j[1]:<12}{j[2]:<7}{_lr(j[6]):<14}{j[4]:<10}{'✓' if j[5] else 'x':<4}{(j[3] or '')}") for i, j in enumerate(jobs)] or print("  (none)")
        print(f"{'#':<3}{'Name':<12}{'Time':<7}{'Last Run':<14}{'Device':<10}{'On':<4}{'Command'}"); _pj(jobs)
        while (c := input("\n<#>|add|rm|ed <#>|sync|log|q\n> ").strip()) and c != 'q':
            args = ['run', c] if c.isdigit() else c.split()
            sp.run([sys.executable, __file__.replace('hub.py', '../aio.py'), 'hub'] + args)
            jobs = db().execute("SELECT id,name,schedule,prompt,device,enabled,last_run FROM hub_jobs ORDER BY device,name").fetchall()
            print(f"{'#':<3}{'Name':<12}{'Time':<7}{'Last Run':<14}{'Device':<10}{'On':<4}{'Command'}"); _pj(jobs)
        return

    if wda == 'add':
        # One-line: aio hub add <name> <sched> <cmd...>  e.g. aio hub add gdrive-sync '*:0/30' aio gdrive sync
        a, tty = sys.argv[3:], sys.stdin.isatty(); n, s, c = (a+[''])[0], (a+['',''])[1], ' '.join(a[2:])
        items = [(os.path.basename(p), f"aio {i}") for i, p in enumerate(PROJ)] + [(nm, cmd) for nm, cmd in APPS]
        c = (c or (tty and ([print(f"  {i}. {nm} -> {cmd}") for i, (nm, cmd) in enumerate(items)], input("# or cmd: "))[-1].strip() or '')); c = items[int(c)][1] if c.isdigit() and int(c) < len(items) else c
        n, s = n or (tty and input("Name: ").strip().replace(' ','-')), s if ':' in s else (tty and input("Time (9:00am, *:0/30): ").strip())
        if not all([n,s,c]): sys.exit("Usage: aio hub add <name> <sched> <cmd...>")
        s = _pt(s) if s[0].isdigit() else s
        with db() as cn: cn.execute("INSERT OR REPLACE INTO hub_jobs(name,schedule,prompt,device,enabled)VALUES(?,?,?,?,1)", (n, s, c, DEVICE_ID)); cn.commit()
        cmd = c.replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../aio.py")} ') if c.startswith('aio ') else c; _install(n, s, cmd); db_sync(); print(f"✓ {n} @ {s}")
    elif wda == 'sync':
        [_uninstall(j[1]) for j in jobs]; mine = [j for j in jobs if j[4] == DEVICE_ID and j[5]]
        for j in mine:
            cmd = j[3].replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../aio.py")} ') if j[3].startswith('aio ') else j[3]
            _install(j[1], j[2], cmd)
        print(f"✓ synced {len(mine)} jobs")
    elif wda == 'log':
        if not os.path.exists(LOG): print('No logs'); return
        runs = [(m.group(1), m.group(2)[:20]) for l in open(LOG) if (m := re.match(r'^\[(\d{4}-\d{2}-\d{2}[^\]]+)\] (.+)', l))][-20:][::-1]
        print(f"{'Time':<24}{'Job'}"); [print(f"{t:<24}{n}") for t, n in runs] or print('No runs'); input("\nq to exit> ")
    elif wda == 'ed':
        n = sys.argv[3] if len(sys.argv) > 3 else ''; j = jobs[int(n)] if n.isdigit() and int(n) < len(jobs) else None
        if not j or not (new := input(f"Name [{j[1]}]: ").strip()): return print(f"x {n}?") if not j else None
        _uninstall(j[1]); c = db(); c.execute("UPDATE hub_jobs SET name=? WHERE id=?", (new, j[0])); c.commit(); db_sync(); print(f"✓ {new} (run 'sync' to update timer)")
    elif wda in ('rm', 'run'):
        n = sys.argv[3] if len(sys.argv) > 3 else ''
        j = jobs[int(n)] if n.isdigit() and int(n) < len(jobs) else next((x for x in jobs if x[1] == n), None)
        if not j: print(f"x {n}?"); return
        if wda == 'rm':
            _uninstall(j[1]); c = db(); c.execute("DELETE FROM hub_jobs WHERE id=?", (j[0],)); c.commit(); c.close(); db_sync(); print(f"✓ rm {j[1]}")
        else:
            from datetime import datetime
            cmd = j[3].replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../aio.py")} ') if j[3].startswith('aio ') else j[3]
            print(f"Running {j[1]}...", flush=True); r = sp.run(cmd, shell=True, capture_output=True, text=True); out = r.stdout + r.stderr
            print(out) if out else None; open(LOG, 'a').write(f"\n[{datetime.now():%Y-%m-%d %I:%M:%S%p}] {j[1]}\n{out}")
            c = db(); c.execute("UPDATE hub_jobs SET last_run=? WHERE id=?", (datetime.now().strftime('%Y-%m-%d %H:%M'), j[0])); c.commit(); c.close(); db_sync(); print(f"✓")
