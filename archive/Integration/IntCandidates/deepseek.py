#!/usr/bin/env python3
"""
Unified Job Orchestration System
Combines task queue management with systemd integration for production deployment
"""
import sqlite3, subprocess, json, time, sys, os, signal, threading, argparse
from typing import Optional, Dict, Any, List
from pathlib import Path

# Optimized database settings
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL", 
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA busy_timeout=5000",
]

class JobOrchestrator:
    """Unified job manager with systemd integration"""
    
    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        
        for pragma in PRAGMAS:
            self.conn.execute(pragma)
            
        self._init_schema()
    
    def _init_schema(self):
        """Initialize unified database schema"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                command TEXT NOT NULL,
                args TEXT DEFAULT '[]',
                env TEXT,
                working_dir TEXT,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued',  -- queued, running, completed, failed
                schedule TEXT,  -- systemd calendar format or NULL for immediate
                worker_id TEXT,
                retries INTEGER DEFAULT 0,
                error_msg TEXT,
                result TEXT,
                created_at INTEGER DEFAULT (strftime('%s','now')),
                started_at INTEGER,
                completed_at INTEGER,
                dependencies TEXT,  -- JSON array of job names
                systemd_props TEXT  -- JSON of systemd properties
            );
            
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority DESC, created_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_schedule ON jobs(schedule) WHERE schedule IS NOT NULL;
        """)
    
    def add_job(self, name: str, command: str, args: List[str] = None, 
                env: Dict[str, str] = None, working_dir: str = None,
                priority: int = 0, schedule: str = None, 
                dependencies: List[str] = None, **systemd_props) -> int:
        """Add a job with optional systemd properties"""
        with self.lock:
            return self.conn.execute(
                """INSERT INTO jobs (name, command, args, env, working_dir, 
                   priority, schedule, dependencies, systemd_props) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, command, json.dumps(args or []), json.dumps(env) if env else None,
                 working_dir, priority, schedule, json.dumps(dependencies) if dependencies else None,
                 json.dumps(systemd_props) if systemd_props else None)
            ).lastrowid
    
    def get_pending_jobs(self, worker_id: str, limit: int = 1) -> List[Dict[str, Any]]:
        """Get jobs ready for execution with dependency resolution"""
        with self.lock:
            now = int(time.time())
            jobs = self.conn.execute("""
                SELECT id, name, command, args, env, working_dir, systemd_props 
                FROM jobs 
                WHERE status = 'queued' AND (schedule IS NULL OR schedule <= ?)
                AND (dependencies IS NULL OR NOT EXISTS (
                    SELECT 1 FROM json_each(jobs.dependencies) AS dep
                    JOIN jobs AS dep_job ON dep_job.name = dep.value
                    WHERE dep_job.status != 'completed'
                ))
                ORDER BY priority DESC, created_at
                LIMIT ?
            """, (now, limit)).fetchall()
            
            # Atomically claim jobs
            job_ids = [job['id'] for job in jobs]
            if job_ids:
                self.conn.execute(
                    f"UPDATE jobs SET status='running', worker_id=?, started_at=? WHERE id IN ({','.join('?'*len(job_ids))})",
                    [worker_id, now] + job_ids
                )
            
            return [dict(job) for job in jobs]
    
    def complete_job(self, job_id: int, success: bool = True, 
                    result: Any = None, error: str = None):
        """Mark job as completed or failed with retry logic"""
        with self.lock:
            job = self.conn.execute(
                "SELECT retries FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            
            if not job:
                return
                
            now = int(time.time())
            if success:
                self.conn.execute(
                    "UPDATE jobs SET status='completed', completed_at=?, result=? WHERE id=?",
                    (now, json.dumps(result) if result else None, job_id)
                )
            else:
                if job['retries'] < 3:
                    # Exponential backoff
                    delay = 60 * (2 ** job['retries'])  # 1, 2, 4 minutes
                    self.conn.execute(
                        "UPDATE jobs SET status='queued', retries=retries+1, error_msg=? WHERE id=?",
                        (error, job_id)
                    )
                else:
                    self.conn.execute(
                        "UPDATE jobs SET status='failed', completed_at=?, error_msg=? WHERE id=?",
                        (now, error, job_id)
                    )
    
    def reconcile_systemd_jobs(self):
        """Update status of systemd-managed jobs"""
        with self.lock:
            running_jobs = self.conn.execute(
                "SELECT id, name FROM jobs WHERE status='running' AND schedule IS NOT NULL"
            ).fetchall()
            
            for job in running_jobs:
                # Check systemd unit status
                unit_status = self._get_systemd_status(job['name'])
                if unit_status and unit_status.get('ActiveState') == 'inactive':
                    result = 'success' if unit_status.get('Result') == 'success' else 'failed'
                    self.complete_job(job['id'], result == 'success')
    
    def _get_systemd_status(self, job_name: str) -> Optional[Dict[str, str]]:
        """Get systemd unit status"""
        try:
            result = subprocess.run([
                'systemctl', '--user', 'show', f"aios-{job_name}.service",
                '--property=ActiveState,Result,MainPID'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                return dict(line.split('=', 1) for line in result.stdout.strip().split('\n') if '=')
        except:
            pass
        return None
    
    def start_systemd_job(self, job: Dict[str, Any]) -> bool:
        """Start a job as a systemd transient unit"""
        try:
            cmd = [
                'systemd-run', '--user', '--collect', '--quiet',
                '--unit', f"aios-{job['name']}.service",
                '--property=StandardOutput=journal',
                '--property=StandardError=journal',
            ]
            
            # Add systemd properties
            props = json.loads(job.get('systemd_props', '{}'))
            if props.get('nice'):
                cmd.extend(['--nice', str(props['nice'])])
            if props.get('working_dir'):
                cmd.extend(['--working-directory', props['working_dir']])
            
            # Add environment variables
            env = json.loads(job.get('env', '{}'))
            for k, v in env.items():
                cmd.extend(['--setenv', f"{k}={v}"])
            
            # Add command and arguments
            cmd.append(job['command'])
            cmd.extend(json.loads(job.get('args', '[]')))
            
            result = subprocess.run(cmd, timeout=10)
            return result.returncode == 0
        except:
            return False
    
    def cleanup_old_jobs(self, days: int = 7):
        """Remove old completed jobs"""
        cutoff = int(time.time()) - (days * 86400)
        with self.lock:
            deleted = self.conn.execute(
                "DELETE FROM jobs WHERE status IN ('completed', 'failed') AND completed_at < ?",
                (cutoff,)
            ).rowcount
            
            # Vacuum if significantly fragmented
            if deleted > 100:
                self.conn.execute("VACUUM")
            
            return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        with self.lock:
            counts = dict(self.conn.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status"
            ).fetchall())
            
            performance = self.conn.execute("""
                SELECT AVG(completed_at - started_at) as avg_duration,
                       MAX(completed_at - started_at) as max_duration
                FROM jobs WHERE status = 'completed'
            """).fetchone()
            
            return {
                'job_counts': counts,
                'performance': dict(performance) if performance else {},
                'total_jobs': sum(counts.values())
            }

class Worker:
    """Unified job worker"""
    
    def __init__(self, orchestrator: JobOrchestrator, worker_id: str = None):
        self.orchestrator = orchestrator
        self.worker_id = worker_id or f"worker-{os.getpid()}-{int(time.time())}"
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, signum, frame):
        self.running = False
    
    def run(self, batch_size: int = 1):
        """Main worker loop"""
        print(f"Worker {self.worker_id} started (batch_size={batch_size})")
        
        while self.running:
            try:
                # Reconcile systemd jobs periodically
                self.orchestrator.reconcile_systemd_jobs()
                
                # Get pending jobs
                jobs = self.orchestrator.get_pending_jobs(self.worker_id, batch_size)
                
                if not jobs:
                    time.sleep(1)
                    continue
                
                for job in jobs:
                    if not self.running:
                        break
                    
                    success = self._execute_job(job)
                    self.orchestrator.complete_job(
                        job['id'], 
                        success, 
                        error=None if success else "Execution failed"
                    )
                    
            except Exception as e:
                print(f"Worker error: {e}")
                time.sleep(5)
    
    def _execute_job(self, job: Dict[str, Any]) -> bool:
        """Execute a single job"""
        if job.get('schedule'):
            # Systemd scheduled job
            return self.orchestrator.start_systemd_job(job)
        else:
            # Immediate execution
            try:
                args = json.loads(job.get('args', '[]'))
                env = os.environ.copy()
                env.update(json.loads(job.get('env', '{}')))
                
                result = subprocess.run(
                    [job['command']] + args,
                    env=env,
                    cwd=job.get('working_dir'),
                    timeout=300,
                    capture_output=True,
                    text=True
                )
                
                return result.returncode == 0
            except Exception as e:
                print(f"Job execution failed: {e}")
                return False

def main():
    parser = argparse.ArgumentParser(description="Unified Job Orchestrator")
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Add job command
    add_parser = subparsers.add_parser('add', help='Add a new job')
    add_parser.add_argument('name', help='Job name')
    add_parser.add_argument('command', help='Command to execute')
    add_parser.add_argument('args', nargs='*', help='Command arguments')
    add_parser.add_argument('--env', nargs='*', help='Environment variables (KEY=VALUE)')
    add_parser.add_argument('--working-dir', help='Working directory')
    add_parser.add_argument('--priority', type=int, default=0, help='Job priority')
    add_parser.add_argument('--schedule', help='Systemd calendar schedule')
    add_parser.add_argument('--dependencies', nargs='*', help='Job dependencies')
    add_parser.add_argument('--nice', type=int, help='Nice level')
    
    # Worker command
    worker_parser = subparsers.add_parser('worker', help='Start worker')
    worker_parser.add_argument('--batch-size', type=int, default=1, help='Batch size')
    worker_parser.add_argument('--worker-id', help='Worker identifier')
    
    # Management commands
    subparsers.add_parser('stats', help='Show statistics')
    subparsers.add_parser('reconcile', help='Reconcile systemd jobs')
    cleanup_parser = subparsers.add_parser('cleanup', help='Cleanup old jobs')
    cleanup_parser.add_argument('--days', type=int, default=7, help='Days to keep')
    
    args = parser.parse_args()
    orchestrator = JobOrchestrator()
    
    if args.command == 'add':
        env_dict = {}
        if args.env:
            for env_var in args.env:
                k, v = env_var.split('=', 1)
                env_dict[k] = v
        
        systemd_props = {}
        if args.nice:
            systemd_props['nice'] = args.nice
        if args.working_dir:
            systemd_props['working_dir'] = args.working_dir
            
        job_id = orchestrator.add_job(
            name=args.name,
            command=args.command,
            args=args.args,
            env=env_dict,
            working_dir=args.working_dir,
            priority=args.priority,
            schedule=args.schedule,
            dependencies=args.dependencies,
            **systemd_props
        )
        print(f"Added job {job_id}: {args.name}")
        
    elif args.command == 'worker':
        worker = Worker(orchestrator, args.worker_id)
        worker.run(args.batch_size)
        
    elif args.command == 'stats':
        stats = orchestrator.get_stats()
        print(json.dumps(stats, indent=2))
        
    elif args.command == 'reconcile':
        orchestrator.reconcile_systemd_jobs()
        print("Systemd jobs reconciled")
        
    elif args.command == 'cleanup':
        deleted = orchestrator.cleanup_old_jobs(args.days)
        print(f"Cleaned up {deleted} old jobs")

if __name__ == '__main__':
    main()