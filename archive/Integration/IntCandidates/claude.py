#!/usr/bin/env python3
"""
Pure Python Job Orchestrator - No subprocess calls
Uses multiprocessing for job execution with full orchestration features
"""
import sqlite3, json, time, sys, os, signal, threading, traceback
from multiprocessing import Process, Queue, Manager
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
import importlib.util
import pickle

# Database configuration
DB_PATH = Path.home() / ".pyorch.db"

# Optimized SQLite pragmas
PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL", 
    "PRAGMA cache_size=-8000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA busy_timeout=5000",
]

class JobRegistry:
    """Registry for Python callable jobs"""
    _jobs = {}
    
    @classmethod
    def register(cls, name: str, func: Callable):
        """Register a Python function as a job"""
        cls._jobs[name] = func
    
    @classmethod
    def get(cls, name: str) -> Optional[Callable]:
        return cls._jobs.get(name)
    
    @classmethod
    def load_module(cls, path: str):
        """Load jobs from a Python module"""
        spec = importlib.util.spec_from_file_location("jobs", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and not name.startswith('_'):
                cls.register(name, obj)

class Orchestrator:
    """Pure Python job orchestrator with no subprocess usage"""
    
    def __init__(self, db_path: Path = DB_PATH, max_workers: int = 4):
        self.db_path = db_path
        self.max_workers = max_workers
        self.processes = {}
        self.manager = Manager()
        self.result_queue = self.manager.Queue()
        self.lock = threading.RLock()
        self._init_db()
        
    def _init_db(self):
        """Initialize database"""
        conn = self._get_conn()
        
        for pragma in PRAGMAS:
            conn.execute(pragma)
            
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                func_name TEXT NOT NULL,
                args TEXT,
                kwargs TEXT,
                
                -- Scheduling
                priority INT DEFAULT 0,
                scheduled_at INT DEFAULT 0,
                schedule_pattern TEXT,
                
                -- State
                status TEXT DEFAULT 'pending' CHECK(status IN 
                    ('pending','running','completed','failed','cancelled')),
                pid INT,
                
                -- Execution
                retry_count INT DEFAULT 0,
                max_retries INT DEFAULT 3,
                timeout_sec INT DEFAULT 300,
                error TEXT,
                result TEXT,
                traceback TEXT,
                
                -- Dependencies
                depends_on TEXT,
                
                -- Resource limits
                memory_limit_mb INT,
                cpu_affinity TEXT,
                
                -- Timestamps
                created_at INT DEFAULT (strftime('%s','now')*1000),
                started_at INT,
                completed_at INT
            );
            
            CREATE INDEX IF NOT EXISTS idx_queue ON jobs(status, priority DESC, scheduled_at, id)
                WHERE status IN ('pending','running');
                
            CREATE INDEX IF NOT EXISTS idx_deps ON jobs(depends_on) 
                WHERE depends_on IS NOT NULL;
            
            -- Metrics
            CREATE TABLE IF NOT EXISTS metrics (
                job_id INTEGER PRIMARY KEY,
                queue_time REAL,
                exec_time REAL,
                memory_peak_mb REAL,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            
            -- Job outputs/artifacts
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY,
                job_id INTEGER,
                key TEXT,
                value BLOB,
                created_at INT DEFAULT (strftime('%s','now')*1000),
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
        """)
        conn.close()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get a new database connection"""
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn
    
    def add_job(self, name: str, func_name: str, args: tuple = None, 
                kwargs: dict = None, priority: int = 0, 
                depends_on: List[int] = None, scheduled_at: int = None,
                max_retries: int = 3, timeout_sec: int = 300,
                schedule_pattern: str = None) -> int:
        """Add a job to the queue"""
        conn = self._get_conn()
        scheduled_at = scheduled_at or int(time.time() * 1000)
        
        cursor = conn.execute("""
            INSERT INTO jobs (name, func_name, args, kwargs, priority, 
                depends_on, scheduled_at, max_retries, timeout_sec, schedule_pattern)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, func_name,
            json.dumps(args) if args else None,
            json.dumps(kwargs) if kwargs else None,
            priority,
            json.dumps(depends_on) if depends_on else None,
            scheduled_at, max_retries, timeout_sec, schedule_pattern
        ))
        
        job_id = cursor.lastrowid
        conn.close()
        return job_id
    
    def _check_dependencies(self, conn: sqlite3.Connection, job_id: int) -> bool:
        """Check if all dependencies are completed"""
        row = conn.execute(
            "SELECT depends_on FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        
        if not row or not row['depends_on']:
            return True
            
        deps = json.loads(row['depends_on'])
        incomplete = conn.execute("""
            SELECT COUNT(*) as c FROM jobs 
            WHERE id IN ({}) AND status != 'completed'
        """.format(','.join('?' * len(deps))), deps).fetchone()
        
        return incomplete['c'] == 0
    
    def _worker_process(self, job_id: int, func_name: str, args: tuple, 
                       kwargs: dict, result_queue: Queue, timeout: int):
        """Worker process that executes a job"""
        try:
            # Set up signal handling for timeout
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Job exceeded {timeout}s timeout")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            # Get the function
            func = JobRegistry.get(func_name)
            if not func:
                # Try to import it as module.function
                if '.' in func_name:
                    module_name, func_name = func_name.rsplit('.', 1)
                    module = importlib.import_module(module_name)
                    func = getattr(module, func_name)
                else:
                    raise ValueError(f"Function {func_name} not found in registry")
            
            # Execute the function
            result = func(*args, **kwargs) if args or kwargs else func()
            
            signal.alarm(0)  # Cancel timeout
            result_queue.put((job_id, True, result, None))
            
        except Exception as e:
            signal.alarm(0)
            result_queue.put((job_id, False, None, {
                'error': str(e),
                'traceback': traceback.format_exc()
            }))
    
    def execute_job(self, job: Dict) -> bool:
        """Execute a job in a separate process"""
        job_id = job['id']
        
        # Parse arguments
        args = json.loads(job['args']) if job['args'] else ()
        kwargs = json.loads(job['kwargs']) if job['kwargs'] else {}
        
        # Create process
        p = Process(
            target=self._worker_process,
            args=(job_id, job['func_name'], args, kwargs, 
                  self.result_queue, job.get('timeout_sec', 300))
        )
        
        # Start process
        p.start()
        self.processes[job_id] = p
        
        # Update job status
        conn = self._get_conn()
        conn.execute(
            "UPDATE jobs SET status='running', pid=?, started_at=? WHERE id=?",
            (p.pid, int(time.time() * 1000), job_id)
        )
        conn.close()
        
        return True
    
    def get_next_job(self) -> Optional[Dict]:
        """Get the next eligible job"""
        conn = self._get_conn()
        now = int(time.time() * 1000)
        
        with self.lock:
            eligible = conn.execute("""
                SELECT * FROM jobs 
                WHERE status='pending' AND scheduled_at <= ?
                ORDER BY priority DESC, scheduled_at, id
                LIMIT 10
            """, (now,)).fetchall()
            
            for job in eligible:
                if self._check_dependencies(conn, job['id']):
                    # Claim the job
                    conn.execute(
                        "UPDATE jobs SET status='running' WHERE id=? AND status='pending'",
                        (job['id'],)
                    )
                    conn.close()
                    return dict(job)
            
            conn.close()
            return None
    
    def complete_job(self, job_id: int, success: bool, result: Any = None, 
                    error_info: Dict = None):
        """Mark a job as completed"""
        conn = self._get_conn()
        now = int(time.time() * 1000)
        
        if success:
            conn.execute("""
                UPDATE jobs 
                SET status='completed', completed_at=?, result=?, pid=NULL
                WHERE id=?
            """, (now, json.dumps(result) if result else None, job_id))
            
            # Record metrics
            job = conn.execute(
                "SELECT created_at, started_at FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            
            if job and job['started_at']:
                queue_time = (job['started_at'] - job['created_at']) / 1000.0
                exec_time = (now - job['started_at']) / 1000.0
                
                conn.execute("""
                    INSERT OR REPLACE INTO metrics (job_id, queue_time, exec_time)
                    VALUES (?, ?, ?)
                """, (job_id, queue_time, exec_time))
        else:
            # Check retry logic
            job = conn.execute(
                "SELECT retry_count, max_retries FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            
            if job and job['retry_count'] < job['max_retries']:
                # Retry with exponential backoff
                delay = 1000 * (2 ** job['retry_count'])
                conn.execute("""
                    UPDATE jobs 
                    SET status='pending', scheduled_at=?, retry_count=retry_count+1,
                        error=?, traceback=?, pid=NULL
                    WHERE id=?
                """, (now + delay, error_info.get('error'), 
                     error_info.get('traceback'), job_id))
            else:
                conn.execute("""
                    UPDATE jobs 
                    SET status='failed', completed_at=?, error=?, traceback=?, pid=NULL
                    WHERE id=?
                """, (now, error_info.get('error'), 
                     error_info.get('traceback'), job_id))
        
        # Clean up process
        if job_id in self.processes:
            del self.processes[job_id]
        
        conn.close()
    
    def process_results(self):
        """Process results from the result queue"""
        while not self.result_queue.empty():
            try:
                job_id, success, result, error = self.result_queue.get_nowait()
                self.complete_job(job_id, success, result, error)
            except:
                break
    
    def reclaim_stalled(self, timeout_ms: int = 300000) -> int:
        """Reclaim jobs that have been running too long"""
        conn = self._get_conn()
        cutoff = int(time.time() * 1000) - timeout_ms
        
        stalled = conn.execute("""
            SELECT id, pid FROM jobs 
            WHERE status='running' AND started_at < ?
        """, (cutoff,)).fetchall()
        
        for job in stalled:
            # Terminate process if still running
            if job['id'] in self.processes:
                self.processes[job['id']].terminate()
                del self.processes[job['id']]
            
            # Reset job for retry
            conn.execute("""
                UPDATE jobs 
                SET status='pending', pid=NULL, retry_count=retry_count+1
                WHERE id=?
            """, (job['id'],))
        
        conn.close()
        return len(stalled)
    
    def schedule_recurring(self):
        """Handle recurring scheduled jobs"""
        conn = self._get_conn()
        
        # Find completed recurring jobs that need rescheduling
        recurring = conn.execute("""
            SELECT id, name, func_name, args, kwargs, priority, 
                   schedule_pattern, max_retries, timeout_sec
            FROM jobs 
            WHERE status='completed' AND schedule_pattern IS NOT NULL
        """).fetchall()
        
        for job in recurring:
            # Calculate next run time (simplified - would need cron parser)
            next_run = int(time.time() * 1000) + 86400000  # Next day
            
            # Create new instance
            self.add_job(
                f"{job['name']}_recurring",
                job['func_name'],
                json.loads(job['args']) if job['args'] else None,
                json.loads(job['kwargs']) if job['kwargs'] else None,
                job['priority'],
                scheduled_at=next_run,
                max_retries=job['max_retries'],
                timeout_sec=job['timeout_sec'],
                schedule_pattern=job['schedule_pattern']
            )
        
        conn.close()
    
    def stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics"""
        conn = self._get_conn()
        
        # Job counts
        counts = {row['status']: row['c'] for row in conn.execute(
            "SELECT status, COUNT(*) c FROM jobs GROUP BY status"
        )}
        
        # Performance metrics
        perf = conn.execute("""
            SELECT AVG(queue_time) avg_qt, AVG(exec_time) avg_et,
                   MAX(queue_time) max_qt, MAX(exec_time) max_et,
                   COUNT(*) total
            FROM metrics
        """).fetchone()
        
        conn.close()
        
        return {
            'jobs': counts,
            'performance': dict(perf) if perf else {},
            'active_processes': len(self.processes),
            'max_workers': self.max_workers
        }
    
    def cleanup(self, days: int = 7) -> int:
        """Remove old completed jobs"""
        conn = self._get_conn()
        cutoff = int(time.time() * 1000) - (days * 86400000)
        
        deleted = conn.execute("""
            DELETE FROM jobs 
            WHERE status IN ('completed', 'failed') AND completed_at < ?
        """, (cutoff,)).rowcount
        
        conn.execute("VACUUM")
        conn.close()
        
        return deleted
    
    def save_artifact(self, job_id: int, key: str, value: Any):
        """Save job output artifact"""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO artifacts (job_id, key, value) VALUES (?, ?, ?)",
            (job_id, key, pickle.dumps(value))
        )
        conn.close()
    
    def get_artifact(self, job_id: int, key: str) -> Any:
        """Retrieve job output artifact"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM artifacts WHERE job_id=? AND key=?",
            (job_id, key)
        ).fetchone()
        conn.close()
        
        return pickle.loads(row['value']) if row else None

class Scheduler:
    """Main scheduler that coordinates job execution"""
    
    def __init__(self, orchestrator: Orchestrator):
        self.orch = orchestrator
        self.running = True
        self.executor = ThreadPoolExecutor(max_workers=orchestrator.max_workers)
        
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
    
    def _shutdown(self, *_):
        self.running = False
        print("\nScheduler shutting down...")
        
        # Terminate all processes
        for p in self.orch.processes.values():
            p.terminate()
    
    def run(self):
        """Main scheduler loop"""
        print(f"Scheduler started (max_workers={self.orch.max_workers})")
        maintenance_counter = 0
        
        while self.running:
            maintenance_counter += 1
            
            # Process results
            self.orch.process_results()
            
            # Periodic maintenance
            if maintenance_counter % 50 == 0:
                reclaimed = self.orch.reclaim_stalled()
                if reclaimed:
                    print(f"Reclaimed {reclaimed} stalled jobs")
                
                self.orch.schedule_recurring()
            
            # Check worker capacity
            if len(self.orch.processes) < self.orch.max_workers:
                job = self.orch.get_next_job()
                
                if job:
                    print(f"Executing job {job['id']}: {job['name']}")
                    self.orch.execute_job(job)
            
            time.sleep(0.1)
        
        self.executor.shutdown(wait=True)

# Example job functions
def example_job(x: int, y: int) -> int:
    """Example job that adds two numbers"""
    time.sleep(1)  # Simulate work
    return x + y

def failing_job():
    """Example job that fails"""
    raise ValueError("This job always fails")

def long_job(duration: int = 10):
    """Example long-running job"""
    time.sleep(duration)
    return f"Slept for {duration} seconds"

# Register example jobs
JobRegistry.register("add", example_job)
JobRegistry.register("fail", failing_job)  
JobRegistry.register("sleep", long_job)

def main():
    """CLI interface"""
    if len(sys.argv) < 2:
        print("""Usage:
  add <name> <func> [--args ...] [--kwargs ...] [--priority N] [--depends ID,ID]
  scheduler [--workers N]
  list
  stats
  cleanup [--days N]
  load <module.py>  # Load job functions from module
        """)
        sys.exit(1)
    
    cmd = sys.argv[1]
    orch = Orchestrator()
    
    if cmd == 'add':
        if len(sys.argv) < 4:
            print("Usage: add <name> <func_name> [options]")
            sys.exit(1)
        
        name = sys.argv[2]
        func_name = sys.argv[3]
        
        # Parse arguments
        kwargs = {'name': name, 'func_name': func_name}
        i = 4
        
        while i < len(sys.argv):
            if sys.argv[i] == '--args':
                args = []
                i += 1
                while i < len(sys.argv) and not sys.argv[i].startswith('--'):
                    # Try to parse as number
                    try:
                        args.append(int(sys.argv[i]))
                    except:
                        args.append(sys.argv[i])
                    i += 1
                kwargs['args'] = tuple(args)
            elif sys.argv[i] == '--priority':
                kwargs['priority'] = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == '--depends':
                kwargs['depends_on'] = [int(x) for x in sys.argv[i + 1].split(',')]
                i += 2
            else:
                i += 1
        
        job_id = orch.add_job(**kwargs)
        print(f"Added job {job_id}")
    
    elif cmd == 'scheduler':
        workers = 4
        if len(sys.argv) > 2 and sys.argv[2] == '--workers':
            workers = int(sys.argv[3])
        
        orch.max_workers = workers
        scheduler = Scheduler(orch)
        scheduler.run()
    
    elif cmd == 'list':
        conn = orch._get_conn()
        jobs = conn.execute("""
            SELECT id, name, func_name, status, priority, created_at 
            FROM jobs ORDER BY created_at DESC LIMIT 50
        """).fetchall()
        
        for job in jobs:
            created = time.strftime('%Y-%m-%d %H:%M:%S', 
                                   time.localtime(job['created_at'] / 1000))
            print(f"[{job['id']}] {job['name']} ({job['func_name']}): "
                  f"{job['status']} (pri={job['priority']}, created={created})")
        
        conn.close()
    
    elif cmd == 'stats':
        stats = orch.stats()
        print(json.dumps(stats, indent=2))
    
    elif cmd == 'cleanup':
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        deleted = orch.cleanup(days)
        print(f"Deleted {deleted} old jobs")
    
    elif cmd == 'load':
        if len(sys.argv) < 3:
            print("Usage: load <module.py>")
            sys.exit(1)
        
        JobRegistry.load_module(sys.argv[2])
        print(f"Loaded jobs from {sys.argv[2]}")
        print(f"Available jobs: {list(JobRegistry._jobs.keys())}")
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()