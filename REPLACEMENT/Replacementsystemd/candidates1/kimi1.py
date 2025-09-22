#!/usr/bin/env python3
"""
aios_systemd.py – tiny launcher for AIOS workflows
- starts any executable as a *transient* systemd user unit
- guarantees auto-reap (no zombies)
- supports real-time policy / nice / cgroup slices
- <200 lines, single file, zero deps except systemd
"""
import argparse, subprocess, sys, shlex, time, re, json, sqlite3, os

DB = "aios.sqlite"          # same DB AIOS already uses
SYSTEMD_RUN = "/usr/bin/systemd-run"

def _quote(*a): return " ".join(shlex.quote(str(x)) for x in a)

def _unit_name(wid: str) -> str:
    return "aios-" + re.sub(r"[^a-zA-Z0-9_:.-]", "_", wid)

def _status(unit: str):
    out = subprocess.run(["systemctl", "--user", "show", unit],
                         capture_output=True, text=True)
    return dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)

def launch(workflow_id: str, cmdline: list, *,
           realtime=False, nice=0, slice_name="aios.slice"):
    unit = _unit_name(workflow_id)
    extra = []
    if realtime:
        extra += ["--property=CPUSchedulingPolicy=rr",
                  "--property=CPUSchedulingPriority=90"]
    if nice:
        extra += [f"--property=Nice={nice}"]
    extra += [f"--slice={slice_name}"]
    subprocess.run([SYSTEMD_RUN,
                    "--user", "--collect", "--quiet",
                    "--unit", unit,
                    *extra, "--", *cmdline], check=True)
    return unit

def reap_until_done(unit: str, poll=1):
    while True:
        st = _status(unit).get("ActiveState", "")
        if st in ("inactive", "failed"): break
        time.sleep(poll)
    return st != "failed"

def db_record(wid: str, unit: str, status: str):
    with sqlite3.connect(DB) as con:
        con.execute("INSERT OR REPLACE INTO jobs(id,unit,status) VALUES(?,?,?)",
                    (wid, unit, status))

# ---------------- CLI ----------------
def cli():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("launch", help="start workflow as systemd unit")
    a.add_argument("workflow_id")
    a.add_argument("command", nargs="+")
    a.add_argument("--realtime", action="store_true")
    a.add_argument("--nice", type=int, default=0)

    b = sub.add_parser("wait", help="block until workflow finishes")
    b.add_argument("workflow_id")

    c = sub.add_parser("cleanup", help="remove finished units from DB")

    args = p.parse_args()

    if args.cmd == "launch":
        unit = launch(args.workflow_id, args.command,
                      realtime=args.realtime, nice=args.nice)
        db_record(args.workflow_id, unit, "running")
        print(unit)

    elif args.cmd == "wait":
        unit = _unit_name(args.workflow_id)
        ok = reap_until_done(unit)
        db_record(args.workflow_id, unit, "done" if ok else "failed")
        sys.exit(0 if ok else 1)

    elif args.cmd == "cleanup":
        with sqlite3.connect(DB) as con:
            cur = con.execute("SELECT id,unit FROM jobs")
            for wid, unit in cur.fetchall():
                st = _status(unit).get("ActiveState", "")
                if st in ("inactive", "failed", None):
                    con.execute("DELETE FROM jobs WHERE id=?", (wid,))

if __name__ == "__main__":
    cli()