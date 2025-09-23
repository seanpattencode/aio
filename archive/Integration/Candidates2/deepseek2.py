#!/usr/bin/env python3
"""
Ultimate Job Orchestrator - Best-of-Breed Synthesis
Combines optimal performance, robustness, and simplicity in under 300 lines
"""
import sqlite3, subprocess, json, time, sys, os, signal, threading, argparse
from pathlib import Path
from typing import Optional, Dict, Any, List

# Global configuration
DB_PATH = Path.home() / ".ultimate_orchestrator.db"
UNIT_PREFIX = "ultorch-"
PRAGMAS = ["PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL", "PRAGMA busy_timeout=5000"]

class UltimateOrchestrator:
    """Unified orchestrator with hybrid execution modes"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """Minimal but complete schema"""
        for pragma in PRAGMAS:
            self.conn.execute(pragma)
            
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                command TEXT NOT NULL,
                mode TEXT DEFAULT 'auto',  -- auto, direct, systemd
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued', -- queued, running, completed, failed
                scheduled_at INTEGER DEFAULT (strftime('%s','now')),
                worker_id TEXT,
                retries INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                error_msg TEXT,
                result TEXT,
                created_at INTEGER DEFAULT (strftime('%s','now')),
                started_at INTEGER,
                completed_at INTEGER,
                dependencies TEXT,  -- JSON array
                resource_limits TEXT  -- JSON: {mem_mb, cpu_weight, nice, ...}
            );
            
            CREATE INDEX IF NOT EXISTS idx_ready ON jobs(status, priority DESC, scheduled_at) 
            WHERE status = 'queued';
        """)
    
    def add_job(self, name: str, command: str, mode: str = "auto", 
                priority: int = 0, delay: int = 0, dependencies: List[str] = None,
                max_retries: int = 3, **resource_limits) -> int:
        """Add job with smart defaults"""
        scheduled_at = int(time.time()) + delay
        deps_json = json.dumps(dependencies) if dependencies else None
        resources_json = json.dumps(resource_limits) if resource_limits else None
        
        with self.lock:
            cursor = self.conn.execute("""
                INSERT INTO jobs (name, command, mode, priority, scheduled_at, 
                                dependencies, max_retries, resource_limits)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, command, mode, priority, scheduled_at, deps_json, max_retries, resources_json))
            return cursor.lastrowid
    
    def _get_execution_mode(self, job: Dict) -> str:
        """Smart mode selection: systemd for long-running, direct for quick tasks"""
        if job['mode'] != 'auto':
            return job['mode']
        
        # Heuristic: commands with nohup, sleep, or server indicators use systemd
        systemd_indicators = ['nohup', 'server', 'service', 'daemon', 'sleep']
        if any(indicator in job['command'].lower() for indicator in systemd_indicators):
            return 'systemd'
        return 'direct'
    
    def _check_dependencies(self, job_id: int) -> bool:
        """Verify all dependencies are completed"""
        job = self.conn.execute("SELECT dependencies FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job or not job['dependencies']:
            return True
            
        deps = json.loads(job['dependencies'])
        placeholders = ','.join('?' * len(deps))
        result = self.conn.execute(f"""
            SELECT COUNT(*) as incomplete FROM jobs 
            WHERE name IN ({placeholders}) AND status != 'completed'
        """, deps).fetchone()
        
        return result['incomplete'] == 0
    
    def get_ready_jobs(self, worker_id: str, limit: int = 5) -> List[Dict]:
        """Get jobs ready for execution with dependency resolution"""
        with self.lock:
            now = int(time.time())
            ready = []
            
            # Find eligible jobs
            candidates = self.conn.execute("""
                SELECT * FROM jobs 
                WHERE status = 'queued' AND scheduled_at <= ?
                ORDER BY priority DESC, scheduled_at, id
                LIMIT ?
            """, (now, limit * 2)).fetchall()  # Get extra to account for dependencies
            
            for job in candidates:
                if len(ready) >= limit:
                    break
                    
                if self._check_dependencies(job['id']):
                    # Atomically claim the job
                    updated = self.conn.execute("""
                        UPDATE jobs SET status = 'running', worker_id = ?, started_at = ?
                        WHERE id = ? AND status = 'queued'
                    """, (worker_id, now, job['id'])).rowcount
                    
                    if updated:
                        ready.append(dict(job))
            
            return ready
    
    def _execute_direct(self, job: Dict) -> tuple[bool, str, Any]:
        """Execute job directly with resource limits"""
        try:
            # Basic resource limits using ulimit if available
            resources = json.loads(job.get('resource_limits', '{}'))
            cmd = job['command']
            
            if resources.get('mem_mb'):
                cmd = f"ulimit -v {resources['mem_mb'] * 1024}; {cmd}"
            
            result = subprocess.run(
                cmd, shell=True, timeout=300, capture_output=True, text=True
            )
            
            success = result.returncode == 0
            output = {
                'stdout': result.stdout[:1000],
                'stderr': result.stderr[:1000],
                'returncode': result.returncode
            }
            return success, result.stderr if not success else None, output
            
        except subprocess.TimeoutExpired:
            return False, "Timeout after 300 seconds", None
        except Exception as e:
            return False, str(e), None
    
    def _execute_systemd(self, job: Dict) -> tuple[bool, str]:
        """Execute job as systemd transient unit"""
        try:
            unit_name = f"{UNIT_PREFIX}{job['name']}.service"
            resources = json.loads(job.get('resource_limits', '{}'))
            
            cmd = [
                'systemd-run', '--user', '--collect', '--quiet',
                '--unit', unit_name,
                '--property=StandardOutput=journal',
                '--property=StandardError=journal',
            ]
            
            # Apply resource limits
            if resources.get('nice'):
                cmd.extend(['--nice', str(resources['nice'])])
            if resources.get('mem_mb'):
                cmd.extend([f'--property=MemoryMax={resources["mem_mb"]}M'])
            
            cmd.extend(['--', 'sh', '-c', job['command']])
            
            result = subprocess.run(cmd, timeout=10, capture_output=True, text=True)
            
            if result.returncode == 0:
                return True, unit_name
            return False, result.stderr
            
        except Exception as e:
            return False, str(e)
    
    def complete_job(self, job_id: int, success: bool, error: str = None, result: Any = None):
        """Mark job completion with retry logic"""
        with self.lock:
            job = self.conn.execute(
                "SELECT retries, max_retries FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            
            now = int(time.time())
            
            if success:
                self.conn.execute("""
                    UPDATE jobs SET status = 'completed', completed_at = ?, result = ?
                    WHERE id = ?
                """, (now, json.dumps(result) if result else None, job_id))
            else:
                if job and job['retries'] < job['max_retries']:
                    # Exponential backoff
                    delay = 60 * (2 ** job['retries'])
                    self.conn.execute("""
                        UPDATE jobs SET status = 'queued', retries = retries + 1,
                        scheduled_at = ?, error_msg = ?
                        WHERE id = ?
                    """, (now + delay, error, job_id))
                else:
                    self.conn.execute("""
                        UPDATE jobs SET status = 'failed', completed_at = ?, error_msg = ?
                        WHERE id = ?
                    """, (now, error, job_id))
    
    def reconcile_systemd_jobs(self):
        """Update status of systemd-managed jobs"""
        with self.lock:
            systemd_jobs = self.conn.execute("""
                SELECT id, name FROM jobs 
                WHERE status = 'running' AND mode IN ('systemd', 'auto')
            """).fetchall()
            
            for job in systemd_jobs:
                unit_name = f"{UNIT_PREFIX}{job['name']}.service"
                try:
                    result = subprocess.run([
                        'systemctl', '--user', 'show', unit_name,
                        '--property=ActiveState,Result'
                    ], capture_output=True, text=True, timeout=5)
                    
                    if result.returncode == 0:
                        info = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=')
                        if info.get('ActiveState') in ('inactive', 'failed'):
                            success = info.get('Result') == 'success'
                            self.complete_job(job['id'], success, 
                                            error=None if success else f"Systemd: {info.get('Result')}")
                except:
                    pass  # Unit might not exist yet
    
    def cleanup_old_jobs(self, days: int = 7) -> int:
        """Remove old completed jobs"""
        cutoff = int(time.time()) - (days * 86400)
        with self.lock:
            deleted = self.conn.execute("""
                DELETE FROM jobs 
                WHERE status IN ('completed', 'failed') AND completed_at < ?
            """, (cutoff,)).rowcount
            return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        with self.lock:
            counts = dict(self.conn.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status"
            ).fetchall())
            
            performance = self.conn.execute("""
                SELECT 
                    AVG(started_at - created_at) as avg_queue_time,
                    AVG(completed_at - started_at) as avg_exec_time,
                    COUNT(*) as total_completed
                FROM jobs WHERE status = 'completed'
            """).fetchone()
            
            return {
                'job_counts': counts,
                'performance': dict(performance) if performance else {},
                'total_jobs': sum(counts.values())
            }

class SmartWorker:
    """Adaptive worker that chooses optimal execution strategy"""
    
    def __init__(self, orchestrator: UltimateOrchestrator, worker_id: str = None):
        self.orch = orchestrator
        self.worker_id = worker_id or f"worker-{os.getpid()}-{int(time.time())}"
        self.running = True
        self._setup_signals()
    
    def _setup_signals(self):
        """Graceful shutdown handling"""
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, signum, frame):
        """Handle shutdown gracefully"""
        self.running = False
        print(f"\nWorker {self.worker_id} shutting down...")
    
    def run(self, batch_size: int = 3):
        """Main worker loop with adaptive execution"""
        print(f"SmartWorker {self.worker_id} started (batch_size={batch_size})")
        
        while self.running:
            try:
                # Periodic maintenance
                self.orch.reconcile_systemd_jobs()
                
                # Get batch of ready jobs
                jobs = self.orch.get_ready_jobs(self.worker_id, batch_size)
                
                if not jobs:
                    time.sleep(1)
                    continue
                
                for job in jobs:
                    if not self.running:
                        break
                    
                    execution_mode = self.orch._get_execution_mode(job)
                    
                    if execution_mode == 'direct':
                        success, error, result = self.orch._execute_direct(job)
                        self.orch.complete_job(job['id'], success, error, result)
                    else:  # systemd
                        success, unit_info = self.orch._execute_systemd(job)
                        if success:
                            print(f"Started systemd unit: {unit_info}")
                            # Job completion will be handled by reconcile
                        else:
                            self.orch.complete_job(job['id'], False, error=unit_info)
                            
            except Exception as e:
                print(f"Worker error: {e}")
                time.sleep(5)

def main():
    """Clean CLI interface"""
    parser = argparse.ArgumentParser(description="Ultimate Job Orchestrator")
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Add job command
    add_parser = subparsers.add_parser('add', help='Add a new job')
    add_parser.add_argument('name', help='Job name (unique)')
    add_parser.add_argument('command', help='Command to execute')
    add_parser.add_argument('--mode', choices=['auto', 'direct', 'systemd'], default='auto',
                          help='Execution mode (default: auto)')
    add_parser.add_argument('--priority', type=int, default=0, help='Job priority')
    add_parser.add_argument('--delay', type=int, default=0, help='Delay execution by N seconds')
    add_parser.add_argument('--max-retries', type=int, default=3, help='Maximum retry attempts')
    add_parser.add_argument('--depends-on', nargs='*', help='Job dependencies by name')
    add_parser.add_argument('--mem-mb', type=int, help='Memory limit in MB')
    add_parser.add_argument('--nice', type=int, help='Nice level (-20 to 19)')
    add_parser.add_argument('--cpu-weight', type=int, help='CPU weight (1-10000)')
    
    # Worker command
    worker_parser = subparsers.add_parser('worker', help='Start smart worker')
    worker_parser.add_argument('--batch-size', type=int, default=3, help='Jobs to process simultaneously')
    worker_parser.add_argument('--worker-id', help='Worker identifier')
    
    # Management commands
    subparsers.add_parser('stats', help='Show system statistics')
    subparsers.add_parser('reconcile', help='Reconcile systemd jobs')
    cleanup_parser = subparsers.add_parser('cleanup', help='Cleanup old jobs')
    cleanup_parser.add_argument('--days', type=int, default=7, help='Remove jobs older than N days')
    
    args = parser.parse_args()
    orch = UltimateOrchestrator()
    
    if args.command == 'add':
        resource_limits = {}
        if args.mem_mb: resource_limits['mem_mb'] = args.mem_mb
        if args.nice: resource_limits['nice'] = args.nice
        if args.cpu_weight: resource_limits['cpu_weight'] = args.cpu_weight
        
        job_id = orch.add_job(
            name=args.name,
            command=args.command,
            mode=args.mode,
            priority=args.priority,
            delay=args.delay,
            dependencies=args.depends_on,
            max_retries=args.max_retries,
            **resource_limits
        )
        print(f"Added job {job_id}: {args.name}")
        
    elif args.command == 'worker':
        worker = SmartWorker(orch, args.worker_id)
        worker.run(args.batch_size)
        
    elif args.command == 'stats':
        stats = orch.get_stats()
        print(json.dumps(stats, indent=2))
        
    elif args.command == 'reconcile':
        orch.reconcile_systemd_jobs()
        print("Systemd jobs reconciled")
        
    elif args.command == 'cleanup':
        deleted = orch.cleanup_old_jobs(args.days)
        print(f"Cleaned up {deleted} old jobs")

if __name__ == '__main__':
    main()