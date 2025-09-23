

```python
#!/usr/bin/env python3
"""
Unified Job Orchestration System
Combines the best features from multiple implementations into a single, cohesive system
"""
import argparse, json, os, shlex, sqlite3, subprocess, sys, time, signal, threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

# Configuration
DB_PATH = Path.home() / ".orchestrator.db"
UNIT_PREFIX = "orch-"
SYSTEMCTL = ["systemctl", "--user"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"]

# Optimized SQLite pragmas
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=268435456",
    "PRAGMA busy_timeout=5000",
    "PRAGMA wal_autocheckpoint=1000",
]

class Orchestrator:
    """Unified job orchestration system with dual execution modes"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database with optimized schema"""
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.row_factory = sqlite3.Row
            
            # Apply performance pragmas
            for pragma in PRAGMAS:
                conn.execute(pragma)
            
            # Unified schema combining best features
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE,
                    cmd TEXT NOT NULL,
                    args TEXT,
                    env TEXT,
                    cwd TEXT,
                    mode TEXT DEFAULT 'local',  -- 'local' or 'systemd'
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'queued',  -- queued, running, completed, failed, stopped
                    created_at INTEGER DEFAULT (strftime('%s','now')*1000),
                    scheduled_at INTEGER DEFAULT (strftime('%s','now')*1000),
                    started_at INTEGER,
                    ended_at INTEGER,
                    worker_id TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    result TEXT,
                    dependencies TEXT,  -- JSON array of job IDs
                    schedule TEXT,  -- systemd calendar format
                    unit TEXT,  -- systemd unit name
                    -- Resource controls
                    nice INTEGER,
                    rtprio INTEGER,
                    slice TEXT,
                    cpu_weight INTEGER,
                    mem_max_mb INTEGER
                );
                
                CREATE INDEX IF NOT EXISTS idx_jobs_queue 
                ON jobs(status, priority DESC, scheduled_at, id) 
                WHERE status IN ('queued', 'running');
                
                CREATE TABLE IF NOT EXISTS metrics (
                    job_id INTEGER PRIMARY KEY,
                    queue_time REAL,
                    exec_time REAL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );
            """)
    
    def add_job(self, name: str, cmd: str, args: List[str] = None, 
                env: Dict[str, str] = None, cwd: str = None, 
                mode: str = 'local', priority: int = 0,
                scheduled_at: int = None, dependencies: List[int] = None,
                schedule: str = None, max_retries: int = 3,
                nice: int = None, rtprio: int = None, slice: str = None,
                cpu_weight: int = None, mem_max_mb: int = None) -> int:
        """Add a new job to the system"""
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            return conn.execute("""
                INSERT INTO jobs (
                    name, cmd, args, env, cwd, mode, priority, scheduled_at,
                    dependencies, schedule, max_retries, nice, rtprio, slice, 
                    cpu_weight, mem_max_mb
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, cmd, json.dumps(args or []), json.dumps(env or {}), 
                cwd, mode, priority, scheduled_at or int(time.time() * 1000),
                json.dumps(dependencies or []), schedule, max_retries,
                nice, rtprio, slice, cpu_weight, mem_max_mb
            )).lastrowid
    
    def get_job(self, job_id: int = None, name: str = None) -> Optional[Dict]:
        """Get job by ID or name"""
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.row_factory = sqlite3.Row
            
            if job_id:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            elif name:
                row = conn.execute("SELECT * FROM jobs WHERE name = ?", (name,)).fetchone()
            else:
                return None
                
            if row:
                job = dict(row)
                # Convert JSON fields
                if job['args']:
                    job['args'] = json.loads(job['args'])
                if job['env']:
                    job['env'] = json.loads(job['env'])
                if job['dependencies']:
                    job['dependencies'] = json.loads(job['dependencies'])
                return job
            return None
    
    def _check_dependencies(self, conn: sqlite3.Connection, job_id: int) -> bool:
        """Check if all dependencies are completed"""
        row = conn.execute(
            "SELECT dependencies FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        
        if not row or not row['dependencies']:
            return True
            
        deps = json.loads(row['dependencies'])
        incomplete = conn.execute("""
            SELECT COUNT(*) as c FROM jobs 
            WHERE id IN ({}) AND status != 'completed'
        """.format(','.join('?' * len(deps))), deps).fetchone()
        
        return incomplete['c'] == 0
    
    def pop_job(self, worker_id: str) -> Optional[Dict]:
        """Get next available job for worker execution"""
        now = int(time.time() * 1000)
        
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.row_factory = sqlite3.Row
            
            # Find next eligible job
            row = conn.execute("""
                SELECT id, cmd, args, env, cwd, mode FROM jobs
                WHERE status = 'queued' AND scheduled_at <= ? AND mode = 'local'
                ORDER BY priority DESC, scheduled_at, id
                LIMIT 1
            """, (now,)).fetchone()
            
            if not row:
                return None
            
            # Check dependencies
            if not self._check_dependencies(conn, row['id']):
                return None
            
            # Try to claim the job
            try:
                result = conn.execute("""
                    UPDATE jobs 
                    SET status = 'running', worker_id = ?, started_at = ?
                    WHERE id = ? AND status = 'queued'
                    RETURNING id, cmd, args, env, cwd, mode
                """, (worker_id, now, row['id'])).fetchone()
                
                if result:
                    job = dict(result)
                    # Convert JSON fields
                    if job['args']:
                        job['args'] = json.loads(job['args'])
                    if job['env']:
                        job['env'] = json.loads(job['env'])
                    return job
                return None
            except sqlite3.OperationalError:
                # Fallback for older SQLite
                conn.execute("BEGIN IMMEDIATE")
                updated = conn.execute(
                    "UPDATE jobs SET status = 'running', worker_id = ?, started_at = ? "
                    "WHERE id = ? AND status = 'queued'",
                    (worker_id, now, row['id'])
                ).rowcount
                conn.execute("COMMIT")
                
                if updated:
                    job = dict(row)
                    # Convert JSON fields
                    if job['args']:
                        job['args'] = json.loads(job['args'])
                    if job['env']:
                        job['env'] = json.loads(job['env'])
                    return job
                return None
    
    def start_job_systemd(self, job_id: int) -> bool:
        """Start a job using systemd"""
        job = self.get_job(job_id)
        if not job or job['mode'] != 'systemd':
            return False
        
        unit = f"{UNIT_PREFIX}{job['name'] or job['id']}.service"
        props = [
            "--property=StandardOutput=journal",
            "--property=StandardError=journal",
            "--property=KillMode=control-group",
        ]
        
        # Add resource control properties
        if job.get('rtprio'):
            props.extend([
                "--property=CPUSchedulingPolicy=rr",
                f"--property=CPUSchedulingPriority={job['rtprio']}"
            ])
        if job.get('nice') is not None:
            props.append(f"--property=Nice={job['nice']}")
        if job.get('slice'):
            props.append(f"--slice={job['slice']}")
        if job.get('cpu_weight'):
            props.append(f"--property=CPUWeight={job['cpu_weight']}")
        if job.get('mem_max_mb'):
            props.append(f"--property=MemoryMax={job['mem_max_mb']}M")
        
        # Add environment variables
        env = []
        if job.get('env'):
            for k, v in job['env'].items():
                env.extend(["--setenv", f"{k}={v}"])
        
        # Add schedule if provided
        schedule = []
        if job.get('schedule'):
            schedule.extend(["--on-calendar", job['schedule']])
        
        # Add working directory
        if job.get('cwd'):
            props.append(f"--property=WorkingDirectory={job['cwd']}")
        
        # Build command
        cmd = [
            *SYSDRUN, "--unit", unit, *props, *env, *schedule,
            "--", job['cmd'], *job.get('args', [])
        ]
        
        # Execute systemd-run
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # Update job status
                with sqlite3.connect(self.db_path, isolation_level=None) as conn:
                    conn.execute(
                        "UPDATE jobs SET unit=?, status=? WHERE id=?",
                        (unit, "running", job_id)
                    )
                return True
            return False
        except Exception:
            return False
    
    def complete_job(self, job_id: int, success: bool = True, 
                     result: Any = None, error: str = None) -> bool:
        """Mark a job as completed"""
        now = int(time.time() * 1000)
        
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            # Get job details
            job = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            
            if not job:
                return False
            
            if success:
                # Update job status
                conn.execute("""
                    UPDATE jobs 
                    SET status = 'completed', ended_at = ?, result = ?, worker_id = NULL
                    WHERE id = ?
                """, (now, json.dumps(result) if result else None, job_id))
                
                # Record metrics
                if job['started_at']:
                    queue_time = (job['started_at'] - job['created_at']) / 1000.0
                    exec_time = (now - job['started_at']) / 1000.0
                    conn.execute(
                        "INSERT OR REPLACE INTO metrics(job_id, queue_time, exec_time) VALUES (?, ?, ?)",
                        (job_id, queue_time, exec_time)
                    )
                return True
            else:
                # Handle failure with retry logic
                if job['retry_count'] < job['max_retries']:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = 1000 * (2 ** job['retry_count'])
                    conn.execute("""
                        UPDATE jobs 
                        SET status = 'queued', retry_count = retry_count + 1, 
                            error_message = ?, worker_id = NULL, scheduled_at = ?
                        WHERE id = ?
                    """, (error, now + delay, job_id))
                else:
                    # Final failure
                    conn.execute("""
                        UPDATE jobs 
                        SET status = 'failed', ended_at = ?, error_message = ?, worker_id = NULL
                        WHERE id = ?
                    """, (now, error, job_id))
                return True
    
    def stop_job(self, job_id: int = None, name: str = None) -> bool:
        """Stop a running job"""
        job = self.get_job(job_id, name)
        if not job:
            return False
        
        if job.get('unit'):
            # Stop systemd unit
            try:
                subprocess.run(
                    SYSTEMCTL + ["stop", job['unit']], 
                    capture_output=True, check=True
                )
                # Also stop timer if it exists
                subprocess.run(
                    SYSTEMCTL + ["stop", job['unit'].replace('.service', '.timer')], 
                    capture_output=True, check=False
                )
            except subprocess.CalledProcessError:
                pass
        
        # Update status
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.execute(
                "UPDATE jobs SET status = 'stopped' WHERE id = ?",
                (job['id'],)
            )
        return True
    
    def reconcile_systemd_jobs(self):
        """Update status of systemd-managed jobs"""
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            running_jobs = conn.execute(
                "SELECT id, name, unit FROM jobs WHERE status = 'running' AND mode = 'systemd' AND unit IS NOT NULL"
            ).fetchall()
            
            for job in running_jobs:
                # Check systemd unit status
                try:
                    result = subprocess.run([
                        'systemctl', '--user', 'show', job['unit'],
                        '--property=ActiveState,Result,MainPID'
                    ], capture_output=True, text=True, check=True)
                    
                    if result.returncode == 0:
                        props = dict(line.split('=', 1) for line in result.stdout.strip().split('\n') if '=' in line)
                        active = props.get('ActiveState')
                        
                        if active in ('inactive', 'failed'):
                            success = props.get('Result') == 'success'
                            self.complete_job(job['id'], success)
                except subprocess.CalledProcessError:
                    pass
    
    def list_jobs(self, status: str = None) -> List[Dict]:
        """List jobs, optionally filtered by status"""
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.row_factory = sqlite3.Row
            
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
                if job['dependencies']:
                    job['dependencies'] = json.loads(job['dependencies'])
                jobs.append(job)
            
            return jobs
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            # Job counts by status
            counts = {row['status']: row['count'] for row in conn.execute(
                "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
            )}
            
            # Performance metrics
            perf = conn.execute("""
                SELECT AVG(queue_time) as avg_queue_time, 
                       AVG(exec_time) as avg_exec_time,
                       MAX(queue_time) as max_queue_time,
                       MAX(exec_time) as max_exec_time
                FROM metrics
            """).fetchone()
            
            return {
                'job_counts': counts,
                'performance': dict(perf) if perf else {}
            }
    
    def cleanup(self, days: int = 7) -> int:
        """Clean up old completed/failed jobs"""
        cutoff = int(time.time() * 1000) - (days * 86400000)
        
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            deleted = conn.execute("""
                DELETE FROM jobs 
                WHERE status IN ('completed', 'failed') AND ended_at < ?
            """, (cutoff,)).rowcount
            
            # Vacuum if needed
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
            
            if freelist > page_count * 0.3:
                conn.execute("VACUUM")
            
            return deleted

class Worker:
    """Worker process for local job execution"""
    
    def __init__(self, orchestrator: Orchestrator, worker_id: str = None):
        self.orchestrator = orchestrator
        self.worker_id = worker_id or f"worker-{os.getpid()}"
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, *_):
        self.running = False
    
    def run(self, batch_size: int = 1):
        """Main worker loop"""
        print(f"Worker {self.worker_id} started (batch_size={batch_size})")
        
        while self.running:
            # Reconcile systemd jobs periodically
            if int(time.time()) % 10 == 0:
                self.orchestrator.reconcile_systemd_jobs()
            
            # Process batch of jobs
            jobs = []
            for _ in range(batch_size):
                job = self.orchestrator.pop_job(self.worker_id)
                if job:
                    jobs.append(job)
            
            if not jobs:
                time.sleep(0.05)
                continue
            
            for job in jobs:
                if not self.running:
                    break
                
                try:
                    # Execute command
                    env = os.environ.copy()
                    env.update(job.get('env', {}))
                    
                    result = subprocess.run(
                        [job['cmd']] + job.get('args', []),
                        env=env,
                        cwd=job.get('cwd'),
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    
                    self.orchestrator.complete_job(
                        job['id'],
                        result.returncode == 0,
                        {
                            'stdout': result.stdout[:1000],
                            'stderr': result.stderr[:1000],
                            'returncode': result.returncode
                        },
                        result.stderr if result.returncode != 0 else None
                    )
                except subprocess.TimeoutExpired:
                    self.orchestrator.complete_job(
                        job['id'], False, error="TIMEOUT"
                    )
                except Exception as e:
                    self.orchestrator.complete_job(
                        job['id'], False, error=str(e)
                    )

def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(description="Job Orchestration System")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new job")
    add_parser.add_argument("name", help="Job name")
    add_parser.add_argument("command", help="Command to execute")
    add_parser.add_argument("args", nargs="*", help="Command arguments")
    add_parser.add_argument("--env", action="append", help="Environment variables (KEY=VAL)")
    add_parser.add_argument("--cwd", help="Working directory")
    add_parser.add_argument("--mode", choices=["local", "systemd"], default="local", help="Execution mode")
    add_parser.add_argument("--priority", type=int, default=0, help="Job priority")
    add_parser.add_argument("--schedule", help="Systemd calendar schedule")
    add_parser.add_argument("--delay", type=int, default=0, help="Delay execution by N seconds")
    add_parser.add_argument("--dependencies", nargs="*", type=int, help="Dependency job IDs")
    add_parser.add_argument("--max-retries", type=int, default=3, help="Maximum retry attempts")
    add_parser.add_argument("--rtprio", type=int, help="Real-time priority")
    add_parser.add_argument("--nice", type=int, help="Nice value")
    add_parser.add_argument("--slice", help="Systemd slice")
    add_parser.add_argument("--cpu-weight", type=int, help="CPU weight")
    add_parser.add_argument("--mem-max-mb", type=int, help="Memory limit in MB")
    add_parser.add_argument("--start", action="store_true", help="Start job immediately")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List jobs")
    list_parser.add_argument("--status", help="Filter by status")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start a job")
    start_parser.add_argument("name", help="Job name")
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop a job")
    stop_parser.add_argument("name", help="Job name")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show job status")
    status_parser.add_argument("name", help="Job name")
    
    # Worker command
    worker_parser = subparsers.add_parser("worker", help="Run worker process")
    worker_parser.add_argument("--batch", type=int, default=1, help="Batch size")
    
    # Stats command
    subparsers.add_parser("stats", help="Show system statistics")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old jobs")
    cleanup_parser.add_argument("--days", type=int, default=7, help="Keep jobs newer than N days")
    
    # Reconcile command
    subparsers.add_parser("reconcile", help="Reconcile systemd job statuses")
    
    args = parser.parse_args()
    orchestrator = Orchestrator()
    
    if args.command == "add":
        env = {}
        if args.env:
            for e in args.env:
                if "=" in e:
                    k, v = e.split("=", 1)
                    env[k] = v
        
        scheduled_at = None
        if args.delay > 0:
            scheduled_at = int(time.time() * 1000) + (args.delay * 1000)
        
        job_id = orchestrator.add_job(
            name=args.name,
            cmd=args.command,
            args=args.args,
            env=env,
            cwd=args.cwd,
            mode=args.mode,
            priority=args.priority,
            scheduled_at=scheduled_at,
            dependencies=args.dependencies,
            schedule=args.schedule,
            max_retries=args.max_retries,
            rtprio=args.rtprio,
            nice=args.nice,
            slice=args.slice,
            cpu_weight=args.cpu_weight,
            mem_max_mb=args.mem_max_mb
        )
        
        print(f"Added job {job_id}")
        
        if args.start:
            if args.mode == "systemd":
                success = orchestrator.start_job_systemd(job_id)
                print(f"Started with systemd: {'Success' if success else 'Failed'}")
            else:
                # Job will be picked up by a worker
                print("Job queued for worker execution")
    
    elif args.command == "list":
        jobs = orchestrator.list_jobs(args.status)
        for job in jobs:
            print(f"{job['id']}: {job['name']} - {job['status']} ({job['mode']})")
    
    elif args.command == "start":
        job = orchestrator.get_job(name=args.name)
        if not job:
            print(f"Job '{args.name}' not found")
            return
        
        if job['mode'] == "systemd":
            success = orchestrator.start_job_systemd(job['id'])
            print(f"Started with systemd: {'Success' if success else 'Failed'}")
        else:
            # Reset status to queued so worker can pick it up
            with sqlite3.connect(orchestrator.db_path, isolation_level=None) as conn:
                conn.execute(
                    "UPDATE jobs SET status = 'queued' WHERE id = ?",
                    (job['id'],)
                )
            print("Job queued for worker execution")
    
    elif args.command == "stop":
        success = orchestrator.stop_job(name=args.name)
        print(f"Stopped: {'Success' if success else 'Failed'}")
    
    elif args.command == "status":
        job = orchestrator.get_job(name=args.name)
        if not job:
            print(f"Job '{args.name}' not found")
            return
        
        print(f"Status: {job['status']}")
        if job.get('unit'):
            try:
                result = subprocess.run(
                    SYSTEMCTL + ["show", job['unit'], "--property", "ActiveState"],
                    capture_output=True, text=True, check=True
                )
                print(f"Systemd: {result.stdout.strip()}")
            except subprocess.CalledProcessError:
                print("Systemd: Not found")
    
    elif args.command == "worker":
        worker = Worker(orchestrator)
        worker.run(args.batch)
    
    elif args.command == "stats":
        stats = orchestrator.get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.command == "cleanup":
        deleted = orchestrator.cleanup(args.days)
        print(f"Deleted {deleted} old jobs")
    
    elif args.command == "reconcile":
        orchestrator.reconcile_systemd_jobs()
        print("Reconciliation completed")

if __name__ == "__main__":
    main()
```