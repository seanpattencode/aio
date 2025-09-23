#!/usr/bin/env python3
# aios_systemd_orchestrator.py  — <200 lines
# - One SQLite DB
# - systemd user units (.service/.timer) + transient runs
# - RT scheduling, resource caps, env/WD, journald logging
# - Minimal CLI: svc|tmr|run|setrt|stop|status|list
import os, sys, json, sqlite3, subprocess, shlex, time
from pathlib import Path

HOME = Path.home()
USER_DIR = HOME/".config/systemd/user"
DB = HOME/".aios_tasks.db"
UNIT_PREFIX = "aios-"
SYSTEMD_RUN = "systemd-run"

def sh(*args):  # systemctl --user helper
    return subprocess.run(["systemctl","--user",*args], text=True, capture_output=True)

def props_kwargs(rt=None, nice=None, mem=None, cpuw=None, slice_name=None):
    p=[]
    if rt: p += [f"--property=CPUSchedulingPolicy={rt[0]}", f"--property=CPUSchedulingPriority={rt[1]}"]
    if nice is not None: p += [f"--property=Nice={nice}"]
    if mem: p += [f"--property=MemoryMax={mem}"]
    if cpuw: p += [f"--property=CPUWeight={cpuw}"]
    if slice_name: p += [f"--slice={slice_name}"]
    return p

class Aiosd:
    def __init__(self):
        USER_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB)
        self.db.execute("""CREATE TABLE IF NOT EXISTS tasks(
            name TEXT PRIMARY KEY,
            kind TEXT, cmd TEXT, props TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        self.db.commit()

    # -------- file-backed services/timers --------
    def write_service(self, name, cmd, *, wd=None, env=None, restart="on-failure",
                      rt=None, nice=None, mem=None, cpuw=None, slice_name="aios.slice"):
        unit = f"{UNIT_PREFIX}{name}.service"
        p = USER_DIR/unit
        env_lines = ""
        if env:
            for k,v in env.items(): env_lines += f"Environment={k}={v}\n"
        rt_lines = ""
        if rt:
            pol,prio=rt; rt_lines = f"CPUSchedulingPolicy={pol}\nCPUSchedulingPriority={prio}\n"
        if nice is not None: rt_lines += f"Nice={nice}\n"
        if mem: rt_lines += f"MemoryMax={mem}\n"
        if cpuw: rt_lines += f"CPUWeight={cpuw}\n"
        if slice_name: rt_lines += f"Slice={slice_name}\n"
        wd_line = f"WorkingDirectory={wd}\n" if wd else ""
        text = f"""[Unit]
Description=AIOS job {name}
After=network-online.target
[Service]
Type=simple
ExecStart=/bin/sh -lc {shlex.quote(cmd)}
{wd_line}{env_lines}{rt_lines}Restart={restart}
KillMode=control-group
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=default.target
"""
        p.write_text(text)
        self.db.execute("INSERT OR REPLACE INTO tasks(name,kind,cmd,props) VALUES(?,?,?,?)",
                        (name,"service",cmd,json.dumps(dict(rt=rt,nice=nice,mem=mem,cpuw=cpuw,slice=slice_name))))
        self.db.commit()
        sh("daemon-reload"); sh("enable","--now",unit)
        return unit

    def write_timer(self, name, *, on_calendar=None, on_active=None, on_unit_active=None, persistent=True):
        timer = f"{UNIT_PREFIX}{name}.timer"
        svc   = f"{UNIT_PREFIX}{name}.service"
        lines=[]
        if on_calendar: lines.append(f"OnCalendar={on_calendar}")
        if on_active: lines.append(f"OnActiveSec={on_active}")
        if on_unit_active: lines.append(f"OnUnitActiveSec={on_unit_active}")
        if persistent: lines.append("Persistent=true")
        t = f"""[Unit]
Description=AIOS timer {name}
[Timer]
{os.linesep.join(lines) if lines else 'OnActiveSec=60'}
Unit={svc}
[Install]
WantedBy=timers.target
"""
        (USER_DIR/timer).write_text(t)
        self.db.execute("INSERT OR REPLACE INTO tasks(name,kind,cmd,props) VALUES(?,?,?,?)",
                        (name,"timer",svc,json.dumps(dict(timer=lines))))
        self.db.commit()
        sh("daemon-reload"); sh("enable","--now",timer)
        return timer

    # -------- transient runs (no files; auto-reap via systemd) --------
    def run_transient(self, name, cmd, *, on_calendar=None, on_active=None, rt=None,
                      env=None, nice=None, mem=None, cpuw=None, slice_name="aios.slice", wd=None):
        unit = f"{UNIT_PREFIX}{name}.service"
        when=[]
        if on_calendar: when += [f"--on-calendar={on_calendar}"]
        if on_active:   when += [f"--on-active={on_active}"]
        envs=[]
        if env:
            for k,v in env.items(): envs += [f"--setenv={k}={v}"]
        wdir = [f"--working-directory={wd}"] if wd else []
        extra = props_kwargs(rt=rt,nice=nice,mem=mem,cpuw=cpuw,slice_name=slice_name)
        cmd_list = shlex.split(cmd) if isinstance(cmd,str) else list(cmd)
        # --collect ensures unit is garbage-collected after exit; journald captures output
        out = subprocess.run([SYSTEMD_RUN,"--user","--quiet","--collect","--unit",unit,
                              *extra,*envs,*wdir,*when,"--",*cmd_list],
                             text=True, capture_output=True)
        self.db.execute("INSERT OR REPLACE INTO tasks(name,kind,cmd,props) VALUES(?,?,?,?)",
                        (name,"transient"," ".join(cmd_list),
                         json.dumps(dict(rt=rt,when=when,nice=nice,mem=mem,cpuw=cpuw,slice=slice_name,wd=wd)))))
        self.db.commit()
        return (out.returncode, unit, out.stderr.strip())

    # -------- live tweaks / lifecycle / status --------
    def set_rt(self, name, policy="fifo", prio=20):
        unit = f"{UNIT_PREFIX}{name}.service"
        return sh("set-property",unit,f"CPUSchedulingPolicy={policy}",f"CPUSchedulingPriority={prio}").stdout

    def stop(self, name):
        unit=f"{UNIT_PREFIX}{name}.service"; timer=f"{UNIT_PREFIX}{name}.timer"
        sh("disable","--now",unit); sh("disable","--now",timer)
        (USER_DIR/unit).unlink(missing_ok=True); (USER_DIR/timer).unlink(missing_ok=True); sh("daemon-reload")

    def status(self, pattern=f"{UNIT_PREFIX}*.service"):
        return sh("list-units",pattern,"--no-legend","--plain").stdout

    def list_db(self):
        rows=self.db.execute("SELECT name,kind,cmd,props,created_at FROM tasks ORDER BY created_at DESC").fetchall()
        return "\n".join(f"{r[0]:<24} {r[1]:<9} {r[2]}  props={r[3]}" for r in rows)

# ---------------- CLI ----------------
def main():
    a = sys.argv[1:] or []
    if not a or a[0] in {"-h","--help"}:
        print(f"""Usage:
  svc  <name> <cmd> [--rt fifo:10] [--nice N] [--mem 1G] [--cpuw 512] [--wd DIR] [--env K=V,K2=V2]
  tmr  <name> [--cal "Mon..Fri 09:00"] [--active 10s] [--unitactive 1h] [--no-persist]
  run  <name> <cmd> [--cal ...|--active ...] [--rt fifo:50] [--nice N] [--mem 2G] [--cpuw 800] [--wd DIR] [--env ...]
  setrt <name> <policy> <prio>
  stop <name>
  status
  list
Note: user services require 'loginctl enable-linger $USER' to run without a login session."""); return
    o=Aiosd(); cmd=a[0]

    if cmd=="svc":
        name, cmdline = a[1], a[2]
        opts = dict(rt=None,nice=None,mem=None,cpuw=None,wd=None,env=None)
        for i,x in enumerate(a[3:],3):
            if x=="--wd": opts["wd"]=a[i+1]
            if x=="--nice": opts["nice"]=int(a[i+1])
            if x=="--mem": opts["mem"]=a[i+1]
            if x=="--cpuw": opts["cpuw"]=int(a[i+1])
            if x=="--env": opts["env"]={k:v for k,v in (p.split("=",1) for p in a[i+1].split(","))}
            if x=="--rt":
                pol,prio=a[i+1].split(":"); opts["rt"]=(pol,int(prio))
        print(o.write_service(name,cmdline,**opts))

    elif cmd=="tmr":
        name=a[1]; cal=None; active=None; ua=None; persist=True
        for i,x in enumerate(a[2:],2):
            if x=="--cal": cal=a[i+1]
            if x=="--active": active=a[i+1]
            if x=="--unitactive": ua=a[i+1]
            if x=="--no-persist": persist=False
        print(o.write_timer(name,on_calendar=cal,on_active=active,on_unit_active=ua,persistent=persist))

    elif cmd=="run":
        name, cmdline = a[1], a[2]
        opts=dict(on_calendar=None,on_active=None,rt=None,nice=None,mem=None,cpuw=None,env=None,wd=None)
        for i,x in enumerate(a[3:],3):
            if x=="--cal": opts["on_calendar"]=a[i+1]
            if x=="--active": opts["on_active"]=a[i+1]
            if x=="--nice": opts["nice"]=int(a[i+1])
            if x=="--mem": opts["mem"]=a[i+1]
            if x=="--cpuw": opts["cpuw"]=int(a[i+1])
            if x=="--wd": opts["wd"]=a[i+1]
            if x=="--env": opts["env"]={k:v for k,v in (p.split("=",1) for p in a[i+1].split(","))}
            if x=="--rt":
                pol,prio=a[i+1].split(":"); opts["rt"]=(pol,int(prio))
        rc,unit,err = o.run_transient(name,cmdline,**opts)
        print(unit if rc==0 else f"ERR {unit}: {err}")

    elif cmd=="setrt":
        print(o.set_rt(a[1],a[2],int(a[3])))

    elif cmd=="stop":
        o.stop(a[1]); print("stopped")

    elif cmd=="status":
        print(o.status())

    elif cmd=="list":
        print(o.list_db())

if __name__=="__main__": main()
