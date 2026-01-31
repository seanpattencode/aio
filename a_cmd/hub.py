"""aio hub - Scheduled jobs (RFC 5322 .txt storage)"""
import sys, os, subprocess as sp, shutil, re
from pathlib import Path
from . _common import init_db, load_cfg, load_proj, load_apps, db, DEVICE_ID, DATA_DIR, SYNC_ROOT
from .sync import sync

HUB_DIR = SYNC_ROOT / 'hub'
def _save_job(name, schedule, prompt, device, enabled=True, last_run=None):
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    (HUB_DIR/f'{name}.txt').write_text(f"Name: {name}\nSchedule: {schedule}\nPrompt: {prompt}\nDevice: {device}\nEnabled: {enabled}\n"+(f"Last-Run: {last_run}\n" if last_run else ""))
    sync('hub')
def _load_jobs():
    HUB_DIR.mkdir(parents=True, exist_ok=True); (HUB_DIR/'.git').exists() or sync('hub'); jobs = []
    for f in HUB_DIR.glob('*.txt'):
        d = {k.strip(): v.strip() for line in f.read_text().splitlines() if ':' in line for k, v in [line.split(':', 1)]}
        if 'Name' in d and 'Schedule' in d: jobs.append((0, d['Name'], d['Schedule'], d.get('Prompt',''), d.get('Device',DEVICE_ID), d.get('Enabled','true').lower()=='true', d.get('Last-Run')))
    return jobs
def _rm_job(name): (HUB_DIR/f'{name}.txt').unlink(missing_ok=True); sync('hub')

def run():
    init_db()
    cfg = load_cfg()
    PROJ = load_proj()
    APPS = load_apps()
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    _tx = os.path.exists('/data/data/com.termux')
    LOG = f"{DATA_DIR}/hub.log"
    
    if _tx:
        c = db(); c.execute("UPDATE hub_jobs SET device=? WHERE device='localhost'", (DEVICE_ID,)); c.commit(); c.close()
        
    _pt = lambda s: (lambda m: f"{int(m[1])+(12 if m[3]=='pm' and int(m[1])!=12 else (-int(m[1]) if m[3]=='am' and int(m[1])==12 else 0))}:{m[2]}" if m else s)(re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)?$', s.lower().strip()))

    def _install(nm, sched, cmd):
        aio = f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../a.py")}'
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

    jobs = _load_jobs()

    if not wda:
        from datetime import datetime as dt; tw = shutil.get_terminal_size().columns; m = tw<60
        url = sp.run(['git','-C',str(HUB_DIR),'remote','get-url','origin'], capture_output=True, text=True).stdout.strip()
        print(f"Hub: {len(jobs)} jobs\n  {HUB_DIR}\n  {url}\n")
        _el = lambda s,w: s if len(s)<=w else s[:w//2-1]+'..'+s[-(w-w//2-1):]
        _lr = lambda t: (lambda h=int((dt.now()-dt.strptime(t,'%Y-%m-%d %H:%M')).total_seconds()//3600):f"{h//24}d{h%24}h"if m else dt.strptime(t,'%Y-%m-%d %H:%M').strftime('%m/%d %H:%M'))()if t else'-'
        cw=tw-32 if m else tw-48;print(f"# {'Name':<8} {'Last':<9}On Cmd"if m else f"# {'Name':<10} {'Sched':<6} {'Last':<12} {'Dev':<8} On Cmd")
        _pj=lambda J:[print(f"{i:<2}{j[1][:8]:<9}{_lr(j[6]):<10}{'✓'if j[5]else' ':<3}{_el(j[3]or'',cw)}"if m else f"{i:<2}{j[1][:10]:<11}{j[2][:6]:<7}{_lr(j[6]):<13}{j[4][:7]:<8}{'✓'if j[5]else' ':<3}{_el(j[3]or'',cw)}")for i,j in enumerate(J)]or print("  (none)")
        _pj(jobs)
        if not sys.stdin.isatty(): return
        while (c := input("\n<#> run | on/off <#> | add|rm|ed <#> | q\n> ").strip()) and c != 'q':
            args = ['run', c] if c.isdigit() else c.split()
            sp.run([sys.executable, __file__.replace('hub.py', '../a.py'), 'hub'] + args)
            jobs = _load_jobs(); _pj(jobs)
        return

    if wda == 'add':
        # aio hub add <name> <sched> <cmd...>  e.g. aio hub add gdrive-sync '*:0/30' aio gdrive sync
        a, tty = sys.argv[3:], sys.stdin.isatty(); n, s, c = (a+[''])[0], (a+['',''])[1], ' '.join(a[2:])
        items = [(os.path.basename(p[0]), f"aio {i}") for i, p in enumerate(PROJ)] + [(nm, cmd) for nm, cmd in APPS]
        c = (c or (tty and ([print(f"  {i}. {nm} -> {cmd}") for i, (nm, cmd) in enumerate(items)], input("# or cmd: "))[-1].strip() or '')); c = items[int(c)][1] if c.isdigit() and int(c) < len(items) else c
        n, s = n or (tty and input("Name: ").strip().replace(' ','-')), s if ':' in s else (tty and input("Time (9:00am=daily, *:0/30=every 30min): ").strip())
        (e := "Missing name" if not n else "Bad sched (need : e.g. 9:00, *:0/30)" if ':' not in (s or '') else "Missing cmd" if not c else "") and sys.exit(f"✗ {e}")
        s = _pt(s) if s[0].isdigit() else s
        _save_job(n, s, c, DEVICE_ID)
        cmd = c.replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../a.py")} ').replace('python ', f'{sys.executable} '); _install(n, s, cmd); print(f"✓ {n} @ {s}")
    elif wda == 'sync':
        [_uninstall(j[1]) for j in jobs]; mine = [j for j in jobs if j[4] == DEVICE_ID and j[5]]
        for j in mine:
            cmd = j[3].replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../a.py")} ').replace('python ', f'{sys.executable} ')
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
        _uninstall(j[1]); _rm_job(j[1]); _save_job(new, j[2], j[3], j[4], j[5], j[6])
        print(f"✓ {new} (run 'sync' to update timer)")
    elif wda in ('on', 'off', 'rm', 'run'):
        n = sys.argv[3] if len(sys.argv) > 3 else ''; j = jobs[int(n)] if n.isdigit() and int(n) < len(jobs) else next((x for x in jobs if x[1] == n), None)
        if not j: print(f"x {n}?"); return
        if wda in ('on', 'off'):
            if j[4].lower() != DEVICE_ID.lower():
                hosts = {r[0].lower(): r[0] for r in db().execute("SELECT name FROM ssh")}
                if j[4].lower() not in hosts: print(f"x {j[4]} not in ssh hosts"); return
                r = sp.run([sys.executable, __file__.replace('hub.py','../a.py'), 'ssh', hosts[j[4].lower()], 'aio', 'hub', wda, j[1]], capture_output=True, text=True)
                print(r.stdout.strip() or f"x {j[4]} failed"); return
            en = wda == 'on'; _save_job(j[1], j[2], j[3], j[4], en, j[6])
            _install(j[1], j[2], j[3]) if en else _uninstall(j[1]); print(f"✓ {j[1]} {wda}"); return
        if wda == 'rm':
            _uninstall(j[1]); _rm_job(j[1])
            print(f"✓ rm {j[1]}")
        else:
            from datetime import datetime
            cmd = j[3].replace('aio ', f'{sys.executable} {os.path.abspath(__file__).replace("hub.py", "../a.py")} ').replace('python ', f'{sys.executable} ')
            print(f"Running {j[1]}...", flush=True); r = sp.run(cmd, shell=True, capture_output=True, text=True); out = r.stdout + r.stderr
            print(out) if out else None; open(LOG, 'a').write(f"\n[{datetime.now():%Y-%m-%d %I:%M:%S%p}] {j[1]}\n{out}")
            _save_job(j[1], j[2], j[3], j[4], j[5], datetime.now().strftime('%Y-%m-%d %H:%M')); print(f"✓")
