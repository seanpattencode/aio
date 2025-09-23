#!/usr/bin/env python3
"""
Unified Job Orchestrator: SQLite + systemd integration (<500 lines)
Combines task queue scheduling with systemd unit management for robust process control.
"""
import argparse, json, os, shlex, sqlite3, subprocess, sys, time, signal, threading
from pathlib import Path
from typing import Optional, Dict, Any

# Configuration
DB_PATH = Path.home() / ".job_orchestrator.db"
UNIT_PREFIX = "joborch-"
SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"]

# Database setup with optimized pragmas
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA busy_timeout=5000",
]

class JobOrchestrator:
    """Unified job scheduler and systemd unit manager"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database with optimized schema"""
        with self._get_connection() as conn:
            for pragma in PRAGMAS:
                conn.execute(pragma)
            
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    cmd TEXT NOT NULL,
                    args TEXT,
                    env TEXT,
                    cwd TEXT,
                    schedule TEXT,
                    priority INTEGER DEFAULT 0,
                    rtprio INTEGER,
                    nice INTEGER,
                    slice TEXT,
                    cpu_weight INTEGER,
                    mem_max_mb INTEGER,
                    unit TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at INTEGER DEFAULT (strftime('%s','now')),
                    started_at INTEGER,
                    ended_at INTEGER,
                    retries INTEGER DEFAULT 0,
                    last_error TEXT,
                    result TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_status_priority 
                ON jobs(status, priority DESC, created_at) 
                WHERE status IN ('pending', 'running');
                
                CREATE TABLE IF NOT EXISTS metrics (
                    job_id INTEGER PRIMARY KEY,
                    queue_time REAL,
                    exec_time REAL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );
            """)
    
    def _get_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def add_job(self, name: str, cmd: str, **kwargs) -> int:
        """Add a new job to the queue"""
        with self.lock, self._get_connection() as conn:
            # Convert complex types to JSON
            if 'args' in kwargs and kwargs['args'] is not None:
                kwargs['args'] = json.dumps(kwargs['args'])
            if 'env' in kwargs and kwargs['env'] is not None:
                kwargs['env'] = json.dumps(kwargs['env'])
            
            # Insert or replace job
            cursor = conn.execute("""
                INSERT OR REPLACE INTO jobs 
                (name, cmd, args, env, cwd, schedule, priority, rtprio, nice, 
                 slice, cpu_weight, mem_max_mb, unit, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', strftime('%s','now'))
                """, (
                    name, cmd, 
                    kwargs.get('args'), 
                    kwargs.get('env'), 
                    kwargs.get('cwd'), 
                    kwargs.get('schedule'), 
                    kwargs.get('priority', 0),
                    kwargs.get('rtprio'), 
                    kwargs.get('nice'), 
                    kwargs.get('slice'), 
                    kwargs.get('cpu_weight'), 
                    kwargs.get('mem_max_mb'), 
                    None
                ))
            return cursor.lastrowid
    
    def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get the next eligible job to run"""
        with self.lock, self._get_connection() as conn:
            # Get next pending job (considering schedule if present)
            now = int(time.time())
            row = conn.execute("""
                SELECT * FROM jobs 
                WHERE status = 'pending' 
                AND (schedule IS NULL OR strftime('%s', 'now') >= strftime('%s', schedule))
                ORDER BY priority DESC, created_at
                LIMIT 1
            """).fetchone()
            
            if not row:
                return None
            
            # Mark as running
            conn.execute(
                "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
                (now, row['id'])
            )
            
            # Convert JSON strings back to objects
            job = dict(row)
            if job['args']:
                job['args'] = json.loads(job['args'])
            if job['env']:
                job['env'] = json.loads(job['env'])
            
            return job
    
    def start_job_as_systemd_unit(self, job: Dict[str, Any]) -> bool:
        """Start a job as a transient systemd unit"""
        try:
            unit_name = self._get_unit_name(job['name'])
            props = [
                "--property=StandardOutput=journal",
                "--property=StandardError=journal",
                "--property=KillMode=control-group",
            ]
            
            # Add resource and scheduling properties
            if job['rtprio']:
                props += ["--property=CPUSchedulingPolicy=rr",
                         f"--property=CPUSchedulingPriority={job['rtprio']}"]
            if job['nice'] is not None:
                props += [f"--property=Nice={int(job['nice'])}"]
            if job['slice']:
                props += [f"--slice={job['slice']}"]
            if job['cpu_weight']:
                props += [f"--property=CPUWeight={job['cpu_weight']}"]
            if job['mem_max_mb']:
                props += [f"--property=MemoryMax={int(job['mem_max_mb'])}M"]
            
            # Add environment variables
            env = []
            if job['env']:
                for k, v in job['env'].items():
                    env += ["--setenv", f"{k}={v}"]
            
            # Add working directory
            if job['cwd']:
                props += [f"--property=WorkingDirectory={job['cwd']}"]
            
            # Build command
            cmd_args = job['args'] if job['args'] else []
            full_cmd = [job['cmd']] + cmd_args
            
            # Execute systemd-run
            systemd_cmd = [*SYSDRUN, "--unit", unit_name, *props, *env, "--", *full_cmd]
            result = subprocess.run(systemd_cmd, capture_output=True, text=True)
            
            # Update job record
            with self._get_connection() as conn:
                if result.returncode == 0:
                    status = "running_systemd"
                    conn.execute(
                        "UPDATE jobs SET unit = ?, status = ? WHERE id = ?",
                        (unit_name, status, job['id'])
                    )
                    return True
                else:
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    conn.execute(
                        "UPDATE jobs SET status = 'failed', last_error = ? WHERE id = ?",
                        (error_msg, job['id'])
                    )
                    return False
                    
        except Exception as e:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE jobs SET status = 'failed', last_error = ? WHERE id = ?",
                    (str(e), job['id'])
                )
            return False
    
    def complete_job(self, job_id: int, success: bool = True, result: Any = None, error: str = None):
        """Mark a job as completed (success or failure)"""
        with self.lock, self._get_connection() as conn:
            now = int(time.time())
            
            if success:
                # Record success
                conn.execute("""
                    UPDATE jobs SET status = 'completed', ended_at = ?, result = ?
                    WHERE id = ?
                """, (now, json.dumps(result) if result else None, job_id))
                
                # Record metrics
                row = conn.execute(
                    "SELECT created_at, started_at FROM jobs WHERE id = ?", 
                    (job_id,)
                ).fetchone()
                
                if row and row['started_at']:
                    queue_time = row['started_at'] - row['created_at']
                    exec_time = now - row['started_at']
                    conn.execute(
                        "INSERT OR REPLACE INTO metrics(job_id, queue_time, exec_time) VALUES(?, ?, ?)",
                        (job_id, queue_time, exec_time)
                    )
            else:
                # Handle failure with retry logic
                row = conn.execute(
                    "SELECT retries FROM jobs WHERE id = ?", 
                    (job_id,)
                ).fetchone()
                
                if row and row['retries'] < 3:
                    # Exponential backoff retry
                    delay = 60 * (2 ** row['retries'])  # 1m, 2m, 4m
                    new_schedule = now + delay
                    conn.execute("""
                        UPDATE jobs SET status = 'pending', retries = retries + 1, 
                        last_error = ?, schedule = datetime(?, 'unixepoch')
                        WHERE id = ?
                    """, (error or "Unknown error", new_schedule, job_id))
                else:
                    # Final failure
                    conn.execute("""
                        UPDATE jobs SET status = 'failed', ended_at = ?, last_error = ?
                        WHERE id = ?
                    """, (now, error or "Exceeded retry limit", job_id))
    
    def stop_job(self, name: str):
        """Stop a running job"""
        unit_name = self._get_unit_name(name)
        
        # Stop the systemd unit if it exists
        subprocess.run(SYSTEMCTL + ["stop", unit_name], capture_output=True)
        subprocess.run(SYSTEMCTL + ["stop", unit_name.replace(".service", ".timer")], capture_output=True)
        
        # Update database
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'stopped', ended_at = ? WHERE name = ?",
                (int(time.time()), name)
            )
    
    def get_job_status(self, name: str) -> Dict[str, Any]:
        """Get the status of a job"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE name = ?", 
                (name,)
            ).fetchone()
            
            if not row:
                return {"error": "Job not found"}
            
            job = dict(row)
            
            # Get systemd unit status if applicable
            if job['unit']:
                unit_info = self._get_unit_info(job['unit'])
                job.update({
                    "unit_active_state": unit_info.get("ActiveState"),
                    "unit_result": unit_info.get("Result"),
                    "unit_pid": unit_info.get("MainPID")
                })
            
            return job
    
    def list_jobs(self, status: Optional[str] = None) -> list:
        """List all jobs, optionally filtered by status"""
        with self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC",
                    (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC"
                ).fetchall()
            
            jobs = []
            for row in rows:
                job = dict(row)
                # Convert JSON fields
                if job['args']:
                    job['args'] = json.loads(job['args'])
                if job['env']:
                    job['env'] = json.loads(job['env'])
                jobs.append(job)
            
            return jobs
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        with self._get_connection() as conn:
            # Job counts by status
            counts = {row['status']: row['count'] for row in conn.execute(
                "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
            )}
            
            # Performance metrics
            metrics = conn.execute("""
                SELECT 
                    AVG(queue_time) as avg_queue_time,
                    AVG(exec_time) as avg_exec_time,
                    MAX(queue_time) as max_queue_time,
                    MAX(exec_time) as max_exec_time
                FROM metrics
            """).fetchone()
            
            return {
                "job_counts": counts,
                "metrics": dict(metrics) if metrics else {}
            }
    
    def cleanup_old_jobs(self, days: int = 7):
        """Clean up completed/failed jobs older than specified days"""
        cutoff = int(time.time()) - (days * 86400)
        with self._get_connection() as conn:
            deleted = conn.execute(
                "DELETE FROM jobs WHERE status IN ('completed', 'failed') AND ended_at < ?",
                (cutoff,)
            ).rowcount
            return deleted
    
    def reconcile_systemd_units(self):
        """Reconcile job statuses with systemd unit states"""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, unit, status FROM jobs WHERE unit IS NOT NULL AND status IN ('running_systemd', 'running')"
            ).fetchall()
            
            for row in rows:
                unit_info = self._get_unit_info(row['unit'])
                if unit_info and unit_info.get("ActiveState") in ("inactive", "failed"):
                    new_status = "completed" if unit_info.get("Result") == "success" else "failed"
                    conn.execute(
                        "UPDATE jobs SET status = ?, ended_at = ? WHERE id = ?",
                        (new_status, int(time.time()), row['id'])
                    )
    
    def _get_unit_name(self, name: str) -> str:
        """Generate a safe systemd unit name"""
        safe = "".join(c if c.isalnum() or c in "._-:" else "_" for c in name)
        return f"{UNIT_PREFIX}{safe}.service"
    
    def _get_unit_info(self, unit: str) -> Dict[str, str]:
        """Get information about a systemd unit"""
        try:
            result = subprocess.run(
                SYSTEMCTL + ["show", unit, "--property=ActiveState,Result,MainPID"],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                return {}
            
            info = {}
            for line in result.stdout.strip().splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    info[key] = value
            return info
        except Exception:
            return {}


class Worker:
    """Background worker that processes jobs"""
    
    def __init__(self, orchestrator: JobOrchestrator):
        self.orchestrator = orchestrator
        self.running = True
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
    
    def _shutdown(self, signum, frame):
        """Handle shutdown signals"""
        print(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def run(self):
        """Main worker loop"""
        print("Job Orchestrator Worker started")
        counter = 0
        
        while self.running:
            counter += 1
            
            # Periodic maintenance
            if counter % 30 == 0:  # Every ~30 seconds
                self.orchestrator.reconcile_systemd_units()
                print("Performed systemd unit reconciliation")
            
            # Get and process next job
            job = self.orchestrator.get_next_job()
            if job:
                print(f"Starting job: {job['name']}")
                success = self.orchestrator.start_job_as_systemd_unit(job)
                if not success:
                    self.orchestrator.complete_job(
                        job['id'], False, 
                        error="Failed to start systemd unit"
                    )
            else:
                # Sleep briefly if no jobs available
                time.sleep(1)


def main():
    """Command line interface"""
    parser = argparse.ArgumentParser(description="Unified Job Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Add job command
    add_parser = subparsers.add_parser("add", help="Add a new job")
    add_parser.add_argument("name", help="Job name")
    add_parser.add_argument("command", help="Command to execute")
    add_parser.add_argument("args", nargs="*", help="Command arguments")
    add_parser.add_argument("--priority", type=int, default=0, help="Job priority")
    add_parser.add_argument("--env", action="append", help="Environment variables (KEY=VALUE)")
    add_parser.add_argument("--cwd", help="Working directory")
    add_parser.add_argument("--schedule", help="Schedule in systemd calendar format")
    add_parser.add_argument("--rtprio", type=int, help="Real-time priority")
    add_parser.add_argument("--nice", type=int, help="Nice value")
    add_parser.add_argument("--slice", help="Systemd slice")
    add_parser.add_argument("--cpu-weight", type=int, help="CPU weight")
    add_parser.add_argument("--mem-max-mb", type=int, help="Memory limit in MB")
    
    # List jobs command
    list_parser = subparsers.add_parser("list", help="List jobs")
    list_parser.add_argument("--status", help="Filter by status")
    
    # Start worker command
    subparsers.add_parser("worker", help="Start background worker")
    
    # Stop job command
    stop_parser = subparsers.add_parser("stop", help="Stop a job")
    stop_parser.add_argument("name", help="Job name")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Get job status")
    status_parser.add_argument("name", help="Job name")
    
    # Stats command
    subparsers.add_parser("stats", help="Show system statistics")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old jobs")
    cleanup_parser.add_argument("--days", type=int, default=7, help="Days to keep completed jobs")
    
    # Reconcile command
    subparsers.add_parser("reconcile", help="Reconcile job statuses with systemd")
    
    args = parser.parse_args()
    orchestrator = JobOrchestrator()
    
    if args.command == "add":
        env = {}
        if args.env:
            for e in args.env:
                if "=" in e:
                    key, value = e.split("=", 1)
                    env[key] = value
        
        job_id = orchestrator.add_job(
            name=args.name,
            cmd=args.command,
            args=args.args if args.args else [],
            env=env if env else None,
            cwd=args.cwd,
            schedule=args.schedule,
            priority=args.priority,
            rtprio=args.rtprio,
            nice=args.nice,
            slice=args.slice,
            cpu_weight=args.cpu_weight,
            mem_max_mb=args.mem_max_mb
        )
        print(f"Job added with ID: {job_id}")
    
    elif args.command == "list":
        jobs = orchestrator.list_jobs(status=args.status)
        for job in jobs:
            schedule = job['schedule'] if job['schedule'] else "-"
            print(f"{job['name']}: {job['status']} (priority: {job['priority']}, schedule: {schedule})")
    
    elif args.command == "worker":
        worker = Worker(orchestrator)
        worker.run()
    
    elif args.command == "stop":
        orchestrator.stop_job(args.name)
        print(f"Job '{args.name}' stopped")
    
    elif args.command == "status":
        status = orchestrator.get_job_status(args.name)
        print(json.dumps(status, indent=2))
    
    elif args.command == "stats":
        stats = orchestrator.get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.command == "cleanup":
        deleted = orchestrator.cleanup_old_jobs(args.days)
        print(f"Cleaned up {deleted} old jobs")
    
    elif args.command == "reconcile":
        orchestrator.reconcile_systemd_units()
        print("Reconciliation completed")


if __name__ == "__main__":
    main()