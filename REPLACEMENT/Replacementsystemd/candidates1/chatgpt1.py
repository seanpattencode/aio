#!/usr/bin/env python3
# AIOS Systemd Orchestrator — single file, <200 lines
# Manages user units/timers, transient runs, RT scheduling, and logs to SQLite.
import os, sys, json, sqlite3, subprocess
from pathlib import Path

HOME = Path.home()
USER_DIR = HOME/".config/systemd/user"
DB = HOME/".aios_tasks.db"
UNIT_PREFIX = "aios-"

def sh(*args):
    return subprocess.run(list(args), text=True, capture_output=True)

class Orchestrator:
    def __init__(self):
        USER_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB)
        self.db.execute("""CREATE TABLE IF NOT EXISTS tasks(
            name TEXT PRIMARY KEY, cmd TEXT, kind TEXT, props TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        self.db.commit()

    # ---------- core ----------
    def daemon_reload(self):
        sh("systemctl","--user","daemon-reload")

    def enable_now(self, unit):
        self.daemon_reload()
        sh("systemctl","--user","enable","--now",unit)

    def disable_now(self, unit):
        sh("systemctl","--user","disable","--now",unit)

    def status(self, unit):
        return sh("systemctl","--user","status",unit).stdout

    # ---------- file-backed units ----------
    def write_service(self, name, cmd, workdir=None, env=None, restart="on-failure",
                      killmode="control-group", rt=None, extra=None):
        unit = f"{UNIT_PREFIX}{name}.service"
        p = USER_DIR/unit
        env_lines = ""
        if env:
            for k,v in env.items():
                env_lines += f"Environment={k}={v}\n"
        rt_lines = ""
        if rt:
            pol, prio = rt
            rt_lines = f"CPUSchedulingPolicy={pol}\nCPUSchedulingPriority={prio}\n"
        extra = extra or ""
        wd = f"WorkingDirectory={workdir}\n" if workdir else ""
        text = f"""[Unit]
Description=AIOS job {name}
After=network-online.target
[Service]
Type=exec
ExecStart={cmd}
{wd}{env_lines}Restart={restart}
KillMode={killmode}
{rt_lines}StandardOutput=journal
StandardError=journal
[Install]
WantedBy=default.target
"""
        if extra:
            text = text.replace("[Install]\nWantedBy=default.target\n", extra + "\n[Install]\nWantedBy=default.target\n")
        p.write_text(text)
        self.db.execute("INSERT OR REPLACE INTO tasks(name,cmd,kind,props) VALUES(?,?,?,?)",
                        (name, cmd, "service", json.dumps({"rt":rt,"restart":restart})))
        self.db.commit()
        self.enable_now(unit)
        return unit

    def write_timer(self, name, *, on_calendar=None, on_active=None, on_boot=None,
                    on_unit_active=None, persistent=False):
        timer = f"{UNIT_PREFIX}{name}.timer"
        svc = f"{UNIT_PREFIX}{name}.service"
        p = USER_DIR/timer
        tsec = []
        if on_calendar: tsec.append(f"OnCalendar={on_calendar}")
        if on_active: tsec.append(f"OnActiveSec={on_active}")
        if on_boot: tsec.append(f"OnBootSec={on_boot}")
        if on_unit_active: tsec.append(f"OnUnitActiveSec={on_unit_active}")
        if persistent: tsec.append("Persistent=true")
        tblock = "\n".join(tsec) or "OnActiveSec=60"
        text = f"""[Unit]
Description=AIOS timer {name}
[Timer]
{tblock}
Unit={svc}
[Install]
WantedBy=timers.target
"""
        p.write_text(text)
        self.db.execute("INSERT OR REPLACE INTO tasks(name,cmd,kind,props) VALUES(?,?,?,?)",
                        (name, svc, "timer", json.dumps({"timer":tsec})))
        self.db.commit()
        self.enable_now(timer)
        return timer

    # ---------- transient runs (no files) ----------
    def run_transient(self, name, cmd, *, on_calendar=None, on_active=None, rt=None, env=None):
        unit = f"{UNIT_PREFIX}{name}.service"
        props = []
        if rt: props += [f"--property=CPUSchedulingPolicy={rt[0]}", f"--property=CPUSchedulingPriority={rt[1]}"]
        if env:
            for k,v in env.items(): props += [f"--setenv={k}={v}"]
        when = []
        if on_calendar: when += [f"--on-calendar={on_calendar}"]
        if on_active: when += [f"--on-active={on_active}"]
        out = sh("systemd-run","--user","--unit",unit,*props,*when,cmd)
        self.db.execute("INSERT OR REPLACE INTO tasks(name,cmd,kind,props) VALUES(?,?,?,?)",
                        (name, cmd, "transient", json.dumps({"rt":rt,"when":when})))
        self.db.commit()
        return out.stdout + out.stderr

    # ---------- live property tweaks ----------
    def set_rt(self, name, policy="fifo", prio=20):
        unit = f"{UNIT_PREFIX}{name}.service"
        return sh("systemctl","--user","set-property",unit,
                  f"CPUSchedulingPolicy={policy}", f"CPUSchedulingPriority={prio}").stdout

    def stop(self, name):
        unit = f"{UNIT_PREFIX}{name}.service"
        timer = f"{UNIT_PREFIX}{name}.timer"
        self.disable_now(unit)
        if (USER_DIR/timer).exists():
            self.disable_now(timer)

if __name__ == "__main__":
    o = Orchestrator()
    # demo usage when run directly (safe no-ops if systemd --user unavailable)
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        o.write_service("hello", "/usr/bin/python3 -c 'print(\"hi\")'; /usr/bin/sleep 5",
                        rt=("fifo", 10))
        o.write_timer("hello", on_active="10s", on_unit_active="1h", persistent=True)
        print(o.status(f"{UNIT_PREFIX}hello.service"))
