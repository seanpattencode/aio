#!/usr/bin/env python3
"""
Integrated Job Orchestrator: Combines task queue with systemd process management
"""
import sqlite3, subprocess, json, time, sys, os, signal, threading, argparse
from pathlib import Path

PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=268435456",
    "PRAGMA busy_timeout=5000",
    "PRAGMA wal_autocheckpoint=1000",
]

SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"]

class JobManager:
    def __init__(self, db="jobs.db"):
        self.db = db
        self.lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        with self.lock, sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            for pragma in PRAGMAS:
                conn.execute(pragma)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY,
                    cmd TEXT NOT NULL,
                    args TEXT,
                    env TEXT,
                    cwd TEXT,
                    p INT DEFAULT 0,
                    s TEXT DEFAULT 'q',
                    at INT DEFAULT 0,
                    w TEXT,
                    r INT DEFAULT 0,
                    e TEXT,
                    res TEXT,
                    ct INT DEFAULT (strftime('%s','now')*1000),
                    st INT,
                    et INT,
                    dep TEXT,
                    schedule TEXT,
                    rtprio INTEGER,
                    nice INTEGER,
                    slice TEXT,
                    cpu_weight INTEGER,
                    mem_max_mb INTEGER,
                    unit TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS ix ON jobs(s,p DESC,at,id)
                WHERE s IN ('q','r')
            """)

    def add_job(self, cmd, args=None, env=None, cwd=None, priority=0, 
                scheduled_at=None, deps=None, schedule=None, rtprio=None,
                nice=None, slice=None, cpu_weight=None, mem_max_mb=None):
        now = int(time.time() * 1000)
        at = int(scheduled_at * 1000) if scheduled_at else now
        dep_json = json.dumps(deps) if deps else None
        
        with self.lock, sqlite3.connect(self.db) as conn:
            return conn.execute("""
                INSERT INTO jobs 
                (cmd, args, env, cwd, p, at, dep, schedule, rtprio, nice, slice, cpu_weight, mem_max_mb)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                cmd, 
                json.dumps(args) if args else None,
                json.dumps(env) if env else None,
                cwd,
                priority,
                at,
                dep_json,
                schedule,
                rtprio,
                nice,
                slice,
                cpu_weight,
                mem_max_mb
            )).lastrowid

    def get_ready_jobs(self):
        now = int(time.time() * 1000)
        with self.lock, sqlite3.connect(self.db) as conn:
            return [dict(row) for row in conn.execute("""
                SELECT * FROM jobs
                WHERE s='q' AND at <= ?
                AND (dep IS NULL OR NOT EXISTS (
                    SELECT 1 FROM json_each(dep) AS d
                    JOIN jobs AS j ON j.id = d.value
                    WHERE j.s != 'd'
                ))
                ORDER BY p DESC, at, id
            """, (now,))]

    def start_job(self, job_id):
        with self.lock, sqlite3.connect(self.db) as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job['s'] != 'q':
                return False
            
            unit = f"job-{job_id}.service"
            props = [
                "--property=StandardOutput=journal",
                "--property=StandardError=journal",
                "--property=KillMode=control-group"
            ]
            
            if job['rtprio']:
                props += [
                    "--property=CPUSchedulingPolicy=rr",
                    f"--property=CPUSchedulingPriority={job['rtprio']}"
                ]
            if job['nice'] is not None:
                props.append(f"--property=Nice={job['nice']}")
            if job['slice']:
                props.append(f"--slice={job['slice']}")
            if job['cpu_weight']:
                props.append(f"--property=CPUWeight={job['cpu_weight']}")
            if job['mem_max_mb']:
                props.append(f"--property=MemoryMax={job['mem_max_mb']}M")
            if job['cwd']:
                props.append(f"--property=WorkingDirectory={job['cwd']}")
            
            cmd = [*SYSDRUN, "--unit", unit, *props]
            
            if job['env']:
                for k, v in json.loads(job['env']).items():
                    cmd += ["--setenv", f"{k}={v}"]
            
            if job['schedule']:
                cmd += ["--on-calendar", job['schedule']]
            
            cmd += ["--", job['cmd']]
            if job['args']:
                cmd += json.loads(job['args'])
            
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                conn.execute("UPDATE jobs SET s='r', unit=?, w=? WHERE id=?", 
                           (unit, os.getpid(), job_id))
                return True
            return False

    def reconcile(self):
        with self.lock, sqlite3.connect(self.db) as conn:
            for job in conn.execute("SELECT id, unit FROM jobs WHERE s='r' AND unit IS NOT NULL"):
                cp = subprocess.run(
                    [*SYSTEMCTL, "show", job['unit'], 
                     "--property=ActiveState", "--property=Result", 
                     "--property=ExecMainExitCode"],
                    capture_output=True, text=True
                )
                if cp.returncode != 0:
                    continue
                
                props = dict(line.split('=', 1) for line in cp.stdout.splitlines() if '=' in line)
                active = props.get("ActiveState", "")
                result = props.get("Result", "")
                
                if active in ("inactive", "failed"):
                    if result == "success":
                        conn.execute("""
                            UPDATE jobs SET s='d', et=?, res=? 
                            WHERE id=?
                        """, (int(time.time()*1000), json.dumps({'exit': props.get('ExecMainExitCode')}), job['id']))
                    else:
                        conn.execute("""
                            UPDATE jobs SET s='f', e=?, et=? 
                            WHERE id=?
                        """, (f"Exit {props.get('ExecMainExitCode')}", 
                              int(time.time()*1000), job['id']))

class Worker:
    def __init__(self, jm):
        self.jm = jm
        self.running = True
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, 'running', False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, 'running', False))

    def run(self):
        while self.running:
            self.jm.reconcile()
            for job in self.jm.get_ready_jobs():
                if not self.running:
                    break
                if self.jm.start_job(job['id']):
                    print(f"Started job {job['id']}")
            time.sleep(0.1)

def main():
    parser = argparse.ArgumentParser(description="Integrated Job Orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    add = sub.add_parser("add", help="Add new job")
    add.add_argument("cmd", help="Command to execute")
    add.add_argument("--args", type=json.loads, default=[])
    add.add_argument("--env", type=json.loads, default={})
    add.add_argument("--cwd", help="Working directory")
    add.add_argument("--priority", type=int, default=0)
    add.add_argument("--schedule", help="Systemd calendar schedule")
    add.add_argument("--rtprio", type=int, help="Real-time priority")
    add.add_argument("--nice", type=int, help="Nice value")
    add.add_argument("--slice", help="Systemd slice")
    add.add_argument("--cpu-weight", type=int, help="CPU weight")
    add.add_argument("--mem-max-mb", type=int, help="Memory limit in MB")
    add.add_argument("--deps", type=json.loads, default=[], help="Dependency IDs")
    
    sub.add_parser("worker", help="Start worker process")
    
    args = parser.parse_args()
    
    jm = JobManager()
    
    if args.cmd == "add":
        job_id = jm.add_job(
            cmd=args.cmd,
            args=args.args,
            env=args.env,
            cwd=args.cwd,
            priority=args.priority,
            schedule=args.schedule,
            rtprio=args.rtprio,
            nice=args.nice,
            slice=args.slice,
            cpu_weight=args.cpu_weight,
            mem_max_mb=args.mem_max_mb,
            deps=args.deps
        )
        print(f"Added job {job_id}")
    
    elif args.cmd == "worker":
        Worker(jm).run()

if __name__ == "__main__":
    main()