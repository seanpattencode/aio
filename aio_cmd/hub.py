"""aio hub - Scheduled jobs"""
import sys, os, subprocess as sp, shutil, re
from pathlib import Path
from . _common import init_db, load_cfg, load_proj, load_apps, db, db_sync, emit_event, DEVICE_ID, DATA_DIR

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
        aio = f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../aio.py")}'
        if _tx:
            shutil.which('crontab') or sp.run(['pkg', 'install', '-y', 'cronie'], capture_output=True)
            sp.run(['pgrep', 'crond'], capture_output=True).returncode != 0 and sp.run(['crond'])
            h, m = sched.split(':')
            old = '\n'.join(l for l in (sp.run(['crontab', '-l'], capture_output=True, text=True).stdout or '').split('\n') if f'# aio:{nm}' not in l).strip()
            sp.run(['crontab', '-'], input=f"{old}\n{m} {h} * * * {aio} hub run {nm} # aio:{nm}\n", text=True)
        else:
            sd = Path.home() / '.config/systemd/user'; sd.mkdir(parents=True, exist_ok=True); esc = lambda s: s.replace('%','%%')
            (sd / f'aio-{nm}.service').write_text(f"[Unit]\nDescription={nm}\n[Service]\nType=oneshot\nExecStart=/bin/bash -c '{aio} hub run {nm}'\n")
            (sd / f'aio-{nm}.timer').write_text(f"[Unit]\nDescription={nm}\n[Timer]\nOnCalendar={esc(sched)}\nPersistent=true\n[Install]\nWantedBy=timers.target\n")
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
        from datetime import datetime as dt; w = os.get_terminal_size().columns - 50 if sys.stdout.isatty() else 60
        _lr = lambda t: dt.strptime(t, '%Y-%m-%d %H:%M').strftime('%m/%d %I:%M%p').lower() if t else '-'
        _pj = lambda jobs: [print(f"{i:<3}{j[1][:11]:<12}{j[2][:6]:<7}{_lr(j[6]):<14}{j[4][:9]:<10}{'✓' if j[5] else ' '} {(s:=j[3]or'') if len(s:=j[3]or'')<=w else s[:w//2-1]+'...'+s[-(w//2-2):]}") for i, j in enumerate(jobs)] or print("  (none)")
        print(f"{'#':<3}{'Name':<12}{'Time':<7}{'Last Run':<14}{'Device':<10}On Command"); _pj(jobs)
        if not sys.stdin.isatty(): return
        while (c := input("\n<#> run | on/off <#> | add|rm|ed <#> | q\n> ").strip()) and c != 'q':
            args = ['run', c] if c.isdigit() else c.split()
            sp.run([sys.executable, __file__.replace('hub.py', '../aio.py'), 'hub'] + args)
            jobs = db().execute("SELECT id,name,schedule,prompt,device,enabled,last_run FROM hub_jobs ORDER BY device,name").fetchall()
            print(f"{'#':<3}{'Name':<12}{'Time':<7}{'Last Run':<14}{'Device':<10}On Command"); _pj(jobs)
        return

    if wda == 'add':
        # aio hub add <name> <sched> <cmd...>  e.g. aio hub add gdrive-sync '*:0/30' aio gdrive sync
        a, tty = sys.argv[3:], sys.stdin.isatty(); n, s, c = (a+[''])[0], (a+['',''])[1], ' '.join(a[2:])
        items = [(os.path.basename(p), f"aio {i}") for i, p in enumerate(PROJ)] + [(nm, cmd) for nm, cmd in APPS]
        c = (c or (tty and ([print(f"  {i}. {nm} -> {cmd}") for i, (nm, cmd) in enumerate(items)], input("# or cmd: "))[-1].strip() or '')); c = items[int(c)][1] if c.isdigit() and int(c) < len(items) else c
        n, s = n or (tty and input("Name: ").strip().replace(' ','-')), s if ':' in s else (tty and input("Time (9:00am, *:0/30): ").strip())
        (e := "Missing name" if not n else "Bad sched (need : e.g. 9:00, *:0/30)" if ':' not in (s or '') else "Missing cmd" if not c else "") and sys.exit(f"✗ {e}")
        s = _pt(s) if s[0].isdigit() else s
        with db() as cn: cn.execute("INSERT OR REPLACE INTO hub_jobs(name,schedule,prompt,device,enabled)VALUES(?,?,?,?,1)", (n, s, c, DEVICE_ID)); cn.commit()
        emit_event('hub', 'add', {'name': n, 'schedule': s, 'prompt': c, 'device': DEVICE_ID, 'enabled': 1})
        cmd = c.replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../aio.py")} ').replace('python ', f'{sys.executable} '); _install(n, s, cmd); db_sync(); print(f"✓ {n} @ {s}")
    elif wda == 'sync':
        [_uninstall(j[1]) for j in jobs]; mine = [j for j in jobs if j[4] == DEVICE_ID and j[5]]
        for j in mine:
            cmd = j[3].replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../aio.py")} ').replace('python ', f'{sys.executable} ')
            _install(j[1], j[2], cmd)
        print(f"✓ synced {len(mine)} jobs")
    elif wda == 'log':
        if not os.path.exists(LOG): print('No logs'); return
        runs = [(m.group(1), m.group(2)[:20]) for l in open(LOG) if (m := re.match(r'^\[(\d{4}-\d{2}-\d{2}[^\]]+)\] (.+)', l))][-20:][::-1]
        print(f"{'Time':<24}{'Job'}"); [print(f"{t:<24}{n}") for t, n in runs] or print('No runs'); sys.stdin.isatty() and input("\nq to exit> ")
    elif wda == 'ed':
        n = sys.argv[3] if len(sys.argv) > 3 else ''; j = jobs[int(n)] if n.isdigit() and int(n) < len(jobs) else None
        new = sys.argv[4] if len(sys.argv) > 4 else (sys.stdin.isatty() and input(f"Name [{j[1]}]: ").strip() if j else '')
        if not j or not new: return print(f"x {n}?") if not j else None
        _uninstall(j[1]); c = db(); c.execute("UPDATE hub_jobs SET name=? WHERE id=?", (new, j[0])); c.commit()
        emit_event('hub', 'rename', {'old': j[1], 'new': new}); db_sync(); print(f"✓ {new} (run 'sync' to update timer)")
    elif wda in ('on', 'off', 'rm', 'run'):
        n = sys.argv[3] if len(sys.argv) > 3 else ''; j = jobs[int(n)] if n.isdigit() and int(n) < len(jobs) else next((x for x in jobs if x[1] == n), None)
        if not j: print(f"x {n}?"); return
        if wda in ('on', 'off'):
            if j[4].lower() != DEVICE_ID.lower():
                hosts = {r[0].lower(): r[0] for r in db().execute("SELECT name FROM ssh")}
                if j[4].lower() not in hosts: print(f"x {j[4]} not in ssh hosts"); return
                r = sp.run([sys.executable, __file__.replace('hub.py','../aio.py'), 'ssh', hosts[j[4].lower()], 'aio', 'hub', wda, j[1]], capture_output=True, text=True)
                print(r.stdout.strip() or f"x {j[4]} failed"); return
            en = wda == 'on'; c = db(); c.execute("UPDATE hub_jobs SET enabled=? WHERE id=?", (en, j[0])); c.commit(); c.close()
            _install(j[1], j[2], j[3]) if en else _uninstall(j[1]); db_sync(); print(f"✓ {j[1]} {wda}"); return
        if wda == 'rm':
            _uninstall(j[1]); c = db(); c.execute("DELETE FROM hub_jobs WHERE id=?", (j[0],)); c.commit(); c.close()
            emit_event('hub', 'archive', {'name': j[1]}); db_sync(); print(f"✓ rm {j[1]}")
        else:
            from datetime import datetime
            cmd = j[3].replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../aio.py")} ').replace('python ', f'{sys.executable} ')
            print(f"Running {j[1]}...", flush=True); r = sp.run(cmd, shell=True, capture_output=True, text=True); out = r.stdout + r.stderr
            print(out) if out else None; open(LOG, 'a').write(f"\n[{datetime.now():%Y-%m-%d %I:%M:%S%p}] {j[1]}\n{out}")
            c = db(); c.execute("UPDATE hub_jobs SET last_run=? WHERE id=?", (datetime.now().strftime('%Y-%m-%d %H:%M'), j[0])); c.commit(); c.close(); db_sync(); print(f"✓")
