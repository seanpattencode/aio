import sqlite3, subprocess, json, time, sys, os
from pathlib import Path
from typing import Optional, Dict, Any

DB_PATH = Path.home() / ".job_orchestrator.db"
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
]

class JobOrchestrator:
    def __init__(self, db_path=DB_PATH):
        self.c = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        for pragma in PRAGMAS:
            self.c.execute(pragma)
        self.c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                cmd TEXT NOT NULL,
                args TEXT,
                env TEXT,
                cwd TEXT,
                schedule TEXT,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued',
                created_at INTEGER DEFAULT (strftime('%s','now')),
                started_at INTEGER,
                ended_at INTEGER,
                error_message TEXT,
                result TEXT,
                systemd_unit TEXT,
                systemd_properties TEXT,
                dependencies TEXT,
                retry_count INTEGER DEFAULT 0,
                retry_delay INTEGER DEFAULT 1000
            )
        """)

    def add_job(self, name, cmd, args=None, env=None, cwd=None, schedule=None,
                priority=0, dependencies=None, systemd_properties=None):
        args_json = json.dumps(args) if args else None
        env_json = json.dumps(env) if env else None
        dependencies_json = json.dumps(dependencies) if dependencies else None
        systemd_properties_json = json.dumps(systemd_properties) if systemd_properties else None
        cursor = self.c.execute("""
            INSERT INTO jobs (name, cmd, args, env, cwd, schedule, priority, dependencies, systemd_properties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, cmd, args_json, env_json, cwd, schedule, priority, dependencies_json, systemd_properties_json))
        return cursor.lastrowid

    def start_job(self, job_id):
        with self.c:
            job = self.c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                return False, "Job not found"
            if job['status'] != 'queued':
                return False, "Job is not queued"

            if job['dependencies']:
                deps = json.loads(job['dependencies'])
                for dep_id in deps:
                    dep_job = self.c.execute("SELECT status FROM jobs WHERE id = ?", (dep_id,)).fetchone()
                    if not dep_job or dep_job['status'] != 'completed':
                        return False, f"Dependency {dep_id} not satisfied"

            self.c.execute("UPDATE jobs SET status = 'starting' WHERE id = ?", (job_id,))

            unit_name = f"job-{job_id}.service"
            cmd = ['systemd-run', '--user', '--collect', '--quiet', '--unit', unit_name]

            if job['systemd_properties']:
                properties = json.loads(job['systemd_properties'])
                for key, value in properties.items():
                    cmd.extend(['--property', f"{key}={value}"])

            cmd.extend(['--', job['cmd']])
            if job['args']:
                args = json.loads(job['args'])
                cmd.extend(args)

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                retry_count = job['retry_count'] + 1
                if retry_count < 3:
                    retry_delay = job['retry_delay'] * 2
                    self.c.execute("""
                        UPDATE jobs SET status = 'queued', retry_count = ?, retry_delay = ?, error_message = ?
                        WHERE id = ?
                    """, (retry_count, retry_delay, result.stderr, job_id))
                    return False, f"Job failed, will retry. Attempt {retry_count}/3"
                else:
                    self.c.execute("""
                        UPDATE jobs SET status = 'failed', error_message = ?, ended_at = ?
                        WHERE id = ?
                    """, (result.stderr, int(time.time()), job_id))
                    return False, result.stderr

            self.c.execute("""
                UPDATE jobs SET status = 'running', systemd_unit = ?, started_at = ?, retry_count = 0
                WHERE id = ?
            """, (unit_name, int(time.time()), job_id))
            return True, unit_name

    def stop_job(self, job_id):
        with self.c:
            job = self.c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                return False, "Job not found"
            if job['status'] not in ('running', 'starting'):
                return False, "Job is not running"

            unit_name = job['systemd_unit']
            stop_cmd = ['systemctl', '--user', 'stop', unit_name]
            result = subprocess.run(stop_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return False, result.stderr

            self.c.execute("""
                UPDATE jobs SET status = 'stopped', ended_at = ?
                WHERE id = ?
            """, (int(time.time()), job_id))
            return True, "Job stopped"

    def reclaim_stalled_jobs(self, timeout=300):
        cutoff = int(time.time()) - timeout
        with self.c:
            stalled = self.c.execute("""
                SELECT id FROM jobs WHERE status = 'starting' AND started_at < ?
            """, (cutoff,)).fetchall()
            for job in stalled:
                self.c.execute("""
                    UPDATE jobs SET status = 'queued', started_at = NULL, retry_count = retry_count + 1
                    WHERE id = ?
                """, (job['id'],))
            return len(stalled)

    def cleanup(self, days=7):
        cutoff = int(time.time()) - (days * 24 * 60 * 60)
        with self.c:
            self.c.execute("""
                DELETE FROM jobs WHERE status IN ('completed', 'failed', 'stopped') AND ended_at < ?
            """, (cutoff,))
            return self.c.total_changes

    def reconcile(self):
        with self.c:
            jobs = self.c.execute("SELECT id, systemd_unit FROM jobs WHERE systemd_unit IS NOT NULL").fetchall()
            for job in jobs:
                unit_name = job['systemd_unit']
                check_cmd = ['systemctl', '--user', 'show', unit_name, '--property=ActiveState,Result']
                result = subprocess.run(check_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    info = {}
                    for line in result.stdout.splitlines():
                        if '=' in line:
                            key, value = line.split('=', 1)
                            info[key] = value
                    if info.get('ActiveState') == 'inactive':
                        new_status = 'completed' if info.get('Result') == 'success' else 'failed'
                        self.c.execute("""
                            UPDATE jobs SET status = ? WHERE id = ?
                        """, (new_status, job['id']))
            return len(jobs)

    def list_jobs(self, status_filter=None):
        query = "SELECT * FROM jobs ORDER BY priority DESC, created_at DESC"
        if status_filter:
            query = f"SELECT * FROM jobs WHERE status = ? ORDER BY priority DESC, created_at DESC"
            return self.c.execute(query, (status_filter,)).fetchall()
        return self.c.execute(query).fetchall()

    def get_job_status(self, job_id):
        with self.c:
            job = self.c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                return None
            return dict(job)

    def stats(self):
        with self.c:
            stats = {
                'total': self.c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                'by_status': dict(self.c.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()),
                'retry_counts': dict(self.c.execute("SELECT retry_count, COUNT(*) FROM jobs GROUP BY retry_count").fetchall())
            }
            return stats

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Job Orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Add a job")
    a.add_argument("name")
    a.add_argument("command")
    a.add_argument("args", nargs='*')
    a.add_argument("--env", action="append", default=[])
    a.add_argument("--cwd")
    a.add_argument("--schedule")
    a.add_argument("--priority", type=int, default=0)
    a.add_argument("--dependencies", nargs='*', type=int)
    a.add_argument("--systemd-properties", type=json.loads)

    s = sub.add_parser("start", help="Start a job")
    s.add_argument("job_id", type=int)

    t = sub.add_parser("stop", help="Stop a job")
    t.add_argument("job_id", type=int)

    l = sub.add_parser("list", help="List jobs")
    l.add_argument("--status", help="Filter by status")

    u = sub.add_parser("status", help="Get job status")
    u.add_argument("job_id", type=int)

    r = sub.add_parser("reclaim", help="Reclaim stalled jobs")
    r.add_argument("--timeout", type=int, default=300)

    c = sub.add_parser("cleanup", help="Clean up old jobs")
    c.add_argument("--days", type=int, default=7)

    sub.add_parser("reconcile", help="Reconcile job statuses with systemd")
    sub.add_parser("stats", help="Show job statistics")

    args = ap.parse_args()
    jo = JobOrchestrator()

    if args.cmd == "add":
        env = dict(e.split("=", 1) for e in args.env) if args.env else {}
        job_id = jo.add_job(
            name=args.name,
            cmd=args.command,
            args=args.args,
            env=env,
            cwd=args.cwd,
            schedule=args.schedule,
            priority=args.priority,
            dependencies=args.dependencies,
            systemd_properties=args.systemd_properties
        )
        print(f"Added job with ID: {job_id}")

    elif args.cmd == "start":
        success, msg = jo.start_job(args.job_id)
        if success:
            print(f"Started job: {msg}")
        else:
            print(f"Error: {msg}")

    elif args.cmd == "stop":
        success, msg = jo.stop_job(args.job_id)
        if success:
            print(f"Stopped job: {msg}")
        else:
            print(f"Error: {msg}")

    elif args.cmd == "list":
        jobs = jo.list_jobs(args.status)
        for job in jobs:
            print(f"{job['id']}: {job['name']} - {job['status']} (Priority: {job['priority']})")

    elif args.cmd == "status":
        status = jo.get_job_status(args.job_id)
        if status:
            print(json.dumps(status, indent=2))
        else:
            print("Job not found")

    elif args.cmd == "reclaim":
        count = jo.reclaim_stalled_jobs(args.timeout)
        print(f"Reclaimed {count} stalled jobs")

    elif args.cmd == "cleanup":
        count = jo.cleanup(args.days)
        print(f"Cleaned up {count} old jobs")

    elif args.cmd == "reconcile":
        count = jo.reconcile()
        print(f"Reconciled {count} jobs")

    elif args.cmd == "stats":
        stats = jo.stats()
        print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()
