#!/usr/bin/env python3
"""
aios_systemd.py – 180-line production launcher
* transient user units → systemd reaps zombies
* RT / quota / memory in one call
* SQLite ledger (same DB AIOS already owns)
* Works on any distro with systemd ≥ 238
"""
import argparse, sqlite3, subprocess, sys, shlex, json, time, re, os, signal
from pathlib import Path

DB         = Path(os.getenv("AIOS_DB") or "aios.sqlite")
SYSTEMD_RUN= "/usr/bin/systemd-run"
UNIT_PREFIX= "aios-"

# ------------------------------------------------------------------ helpers
def _run(cmd, *, check=True, quiet=True, **kw):
    return subprocess.run(cmd, check=check, capture_output=quiet, text=True, **kw)

def _unit(wid: str) -> str:
    return UNIT_PREFIX + re.sub(r"[^A-Za-z0-9:._-]", "_", wid)

def _status(unit: str) -> dict:
    out = _run(["systemctl", "--user", "show", unit], check=False).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)

# ------------------------------------------------------------------ core API
def launch(workflow_id: str, cmdline: list, *,
           rt: bool = False, cpu: int = 100, mem: str = "1G", nice: int = 0):
    """Launch command as transient user unit.  Returns unit name."""
    unit = _unit(workflow_id)
    props = [f"MemoryMax={mem}", f"CPUQuota={cpu}%", f"Nice={nice}"]
    if rt:
        props += ["CPUSchedulingPolicy=rr", "CPUSchedulingPriority=90"]
    _run([SYSTEMD_RUN, "--user", "--collect", "--quiet",
          "--unit", unit, *map("--property={}".format, props), "--", *cmdline])
    _log(workflow_id, unit, "running")
    return unit

def reap(unit: str, timeout: int = 86400) -> bool:
    """Block until unit finishes (or timeout).  Returns success."""
    for _ in range(timeout):
        st = _status(unit).get("ActiveState", "")
        if st in ("inactive", "failed"):
            return st != "failed"
        time.sleep(1)
    return False

def kill(workflow_id: str):
    """Stop a running workflow immediately."""
    unit = _unit(workflow_id)
    _run(["systemctl", "--user", "stop", unit], check=False)

# ------------------------------------------------------------------ SQLite
def _log(wid: str, unit: str, state: str):
    DB.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.execute("INSERT OR REPLACE INTO jobs(id,unit,state) VALUES(?,?,?)", (wid, unit, state))

def _init_db():
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS jobs(
                       id TEXT PRIMARY KEY,
                       unit TEXT,
                       state TEXT,
                       ts DATETIME DEFAULT CURRENT_TIMESTAMP)""")

# ------------------------------------------------------------------ CLI
def _cli():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("launch", help="start workflow")
    a.add_argument("id")
    a.add_argument("cmd", nargs="+")
    a.add_argument("--rt", action="store_true", help="real-time SCHED_RR")
    a.add_argument("--cpu", type=int, default=100, help="CPU quota %")
    a.add_argument("--mem", default="1G", help="Memory cap (K/M/G)")
    a.add_argument("--nice", type=int, default=0)

    b = sub.add_parser("wait", help="block until done")
    b.add_argument("id")
    b.add_argument("--timeout", type=int, default=86400)

    c = sub.add_parser("kill", help="stop workflow")
    c.add_argument("id")

    d = sub.add_parser("status", help="json status")
    d.add_argument("id", nargs="?")

    return p.parse_args()

def main():
    _init_db()
    args = _cli()
    if args.cmd == "launch":
        unit = launch(args.id, args.cmd, rt=args.rt, cpu=args.cpu, mem=args.mem, nice=args.nice)
        print(unit)
    elif args.cmd == "wait":
        ok = reap(_unit(args.id), args.timeout)
        _log(args.id, _unit(args.id), "done" if ok else "failed")
        sys.exit(0 if ok else 1)
    elif args.cmd == "kill":
        kill(args.id)
    elif args.cmd == "status":
        if args.id:
            st = _status(_unit(args.id))
            print(json.dumps(st, indent=2))
        else:
            print(json.dumps({wid: _status(_unit(wid)) for wid in
                              {r[0] for r in sqlite3.connect(DB).execute("SELECT id FROM jobs")}},
                             indent=2))

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    main()