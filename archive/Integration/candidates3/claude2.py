#!/usr/bin/env python3
"""
Pure Python Job Orchestrator - Zero subprocess calls
Combines the best patterns from all implementations with multiprocessing execution
"""
import sqlite3, json, time, sys, os, signal, threading, traceback, pickle
from multiprocessing import Process, Queue, Manager, cpu_count
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
import importlib.util

# Configuration
DB_PATH = Path.home() / ".pyorch.db"

# Optimized SQLite pragmas (best from all implementations)
PRAGMAS = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-8000;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=268435456;
PRAGMA busy_timeout=5000;
PRAGMA wal_autocheckpoint=1000;
"""

class JobRegistry:
    """Registry for Python callable jobs"""
    _jobs = {}
    
    @classmethod
    def register(cls, name: str, func: Callable, module: str = None):
        """Register a Python function as a job"""
        cls._jobs[name] = {'func': func, 'module': module}
    
    @classmethod
    def get(cls, name: str) -> Optional[Callable]:
        """Get a registered function"""
        job = cls._jobs.get(name)
        return job['func'] if job else None
    
    @classmethod
    def load_module(cls, path: str):
        """Load jobs from a Python module"""
        spec = importlib.util.spec_from_file_location("jobs", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and not name.startswith('_'):
                cls.register(name, obj, path)
        return list(cls._jobs.keys())

class Orchestrator:
    """High-performance job orchestrator with multiprocessing"""
    
    def __init__(self, db_path: Path = DB_PATH, max_workers: int = None):
        self.db_path = db_path
        self.max_workers = max_workers or cpu_count()
        self.processes = {}
        self.manager = Manager()
        self.result_queue = self.manager.Queue()
        self.lock = threading.RLock()
        self._init_db()
    
    def _init_db(self):
        """Initialize database with best schema patterns"""
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(PRAGMAS + """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE,
                    func TEXT NOT NULL,
                    args TEXT,
                    kwargs TEXT,
                    
                    -- Scheduling
                    priority INT DEFAULT 0,
                    scheduled_at INT DEFAULT 0,
                    schedule TEXT,  -- cron-like pattern
                    
                    -- State
                    status TEXT DEFAULT 'pending' CHECK(status IN 
                        ('pending','running','completed','failed','cancelled')),
                    pid INT,
                    worker TEXT,
                    
                    -- Execution
                    retry_count INT DEFAULT 0,
                    max_retries INT DEFAULT 3,
                    timeout_sec INT DEFAULT 300,
                    
                    -- Results
                    error TEXT,
                    result TEXT,
                    traceback TEXT,
                    
                    -- Dependencies
                    depends_on TEXT,  -- JSON array of job IDs
                    
                    -- Resource limits
                    nice INT,
                    cpu_affinity TEXT,  -- JSON array of CPU indices
                    memory_limit_mb INT,
                    
                    -- Timestamps
                    created_at INT DEFAULT (strftime('%s','now')*1000),
                    started_at INT,
                    completed_at INT
                );
                
                -- Optimized composite index
                CREATE INDEX IF NOT EXISTS idx_queue ON jobs(
                    status, priority DESC, scheduled_at, id
                ) WHERE status IN ('pending','running');
                
                CREATE INDEX IF NOT EXISTS idx_deps ON jobs(depends_on) 
                    WHERE depends_on IS NOT NULL;
                
                -- Metrics table
                CREATE TABLE IF NOT EXISTS metrics (
                    job_id INTEGER PRIMARY KEY,
                    queue_time REAL,
                    exec_time REAL,
                    cpu_time REAL,
                    memory_peak_mb REAL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );
                
                -- Artifacts table for job outputs
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER,
                    key TEXT,
                    value BLOB,
                    created_at INT DEFAULT (strftime('%s','now')*1000),
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );
            """)
    
    def add(self, name: str, func: str, args: tuple = None, kwargs: dict = None,
            priority: int = 0, scheduled_at: int = None, depends_on: List[int] = None,
            max_retries: int = 3, timeout_sec: int = 300, schedule: str = None,
            nice: int = None, cpu_affinity: List[int] = None, 
            memory_limit_mb: int = None) -> int:
        """Add a job with comprehensive options"""
        now = int(time.time() * 1000)
        scheduled_at = scheduled_at or now
        
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO jobs 
                (name, func, args, kwargs, priority, scheduled_at, schedule,
                 depends_on, max_retries, timeout_sec, nice, cpu_affinity, memory_limit_mb)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, func,
                json.dumps(args) if args else None,
                json.dumps(kwargs) if kwargs else None,
                priority, scheduled_at, schedule,
                json.dumps(depends_on) if depends_on else None,
                max_retries, timeout_sec, nice,
                json.dumps(cpu_affinity) if cpu_affinity else None,
                memory_limit_mb
            ))
            return cursor.lastrowid
    
    def get_next(self) -> Optional[Dict[str, Any]]:
        """Atomically get next eligible job with dependency checking"""
        now = int(time.time() * 1000)
        
        with self.lock:
            conn = sqlite3.connect(self.db_path, isolation_level=None)
            conn.row_factory = sqlite3.Row
            
            try:
                # Atomic claim with RETURNING (most efficient)
                result = conn.execute("""
                    UPDATE jobs SET status='running', started_at=?, pid=?
                    WHERE id = (
                        SELECT id FROM jobs
                        WHERE status='pending' AND scheduled_at <= ?
                        AND (depends_on IS NULL OR NOT EXISTS (
                            SELECT 1 FROM json_each(jobs.depends_on) AS d
                            JOIN jobs AS dj ON dj.id = d.value
                            WHERE dj.status != 'completed'
                        ))
                        ORDER BY priority DESC, scheduled_at, id
                        LIMIT 1
                    )
                    RETURNING *
                """, (now, os.getpid(), now)).fetchone()
                
                if result:
                    return dict(result)
                    
            except sqlite3.OperationalError:
                # Fallback for older SQLite
                row = conn.execute("""
                    SELECT id FROM jobs
                    WHERE status='pending' AND scheduled_at <= ?
                    AND (depends_on IS NULL OR NOT EXISTS (
                        SELECT 1 FROM json_each(jobs.depends_on) AS d
                        JOIN jobs AS dj ON dj.id = d.value
                        WHERE dj.status != 'completed'
                    ))
                    ORDER BY priority DESC, scheduled_at, id
                    LIMIT 1
                """, (now,)).fetchone()
                
                if row:
                    conn.execute(
                        "UPDATE jobs SET status='running', started_at=?, pid=? WHERE id=? AND status='pending'",
                        (now, os.getpid(), row['id'])
                    )
                    return dict(conn.execute("SELECT * FROM jobs WHERE id=?", (row['id'],)).fetchone())
            finally:
                conn.close()
        
        return None
    
    def execute(self, job: Dict) -> bool:
        """Execute job in separate process with resource limits"""
        job_id = job['id']
        
        # Parse job data
        args = json.loads(job['args']) if job['args'] else ()
        kwargs = json.loads(job['kwargs']) if job['kwargs'] else {}
        
        # Create worker process
        p = Process(
            target=self._worker_process,
            args=(job_id, job['func'], args, kwargs, 
                  self.result_queue, job.get('timeout_sec', 300),
                  job.get('nice'), job.get('cpu_affinity'))
        )
        
        # Start process
        p.start()
        self.processes[job_id] = p
        
        # Update job with process ID
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.execute("UPDATE jobs SET pid=? WHERE id=?", (p.pid, job_id))
        
        return True
    
    def _worker_process(self, job_id: int, func_name: str, args: tuple,
                       kwargs: dict, result_queue: Queue, timeout: int,
                       nice: Optional[int], cpu_affinity: Optional[str]):
        """Worker process that executes a job"""
        try:
            # Set process nice value
            if nice is not None:
                os.nice(nice)
            
            # Set CPU affinity if specified
            if cpu_affinity:
                try:
                    import psutil
                    p = psutil.Process()
                    p.cpu_affinity(json.loads(cpu_affinity))
                except ImportError:
                    pass  # psutil not available
            
            # Setup timeout
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Job exceeded {timeout}s timeout")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            # Get and execute function
            func = JobRegistry.get(func_name)
            if not func:
                # Try to import dynamically
                if '.' in func_name:
                    module_name, func_name = func_name.rsplit('.', 1)
                    module = importlib.import_module(module_name)
                    func = getattr(module, func_name)
                else:
                    raise ValueError(f"Function {func_name} not found")
            
            # Execute
            result = func(*args, **kwargs) if args or kwargs else func()
            
            signal.alarm(0)  # Cancel timeout
            result_queue.put((job_id, True, result, None))
            
        except Exception as e:
            signal.alarm(0)
            result_queue.put((job_id, False, None, {
                'error': str(e),
                'traceback': traceback.format_exc()
            }))
    
    def complete(self, job_id: int, success: bool, result: Any = None,
                error_info: Dict = None):
        """Complete job with retry logic and metrics"""
        now = int(time.time() * 1000)
        
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            if success:
                # Success - mark completed and record metrics
                conn.execute("""
                    UPDATE jobs 
                    SET status='completed', completed_at=?, result=?, pid=NULL
                    WHERE id=?
                """, (now, json.dumps(result) if result else None, job_id))
                
                # Calculate and store metrics
                job = conn.execute(
                    "SELECT created_at, started_at FROM jobs WHERE id=?", 
                    (job_id,)
                ).fetchone()
                
                if job and job['started_at']:
                    queue_time = (job['started_at'] - job['created_at']) / 1000.0
                    exec_time = (now - job['started_at']) / 1000.0
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO metrics 
                        (job_id, queue_time, exec_time)
                        VALUES (?, ?, ?)
                    """, (job_id, queue_time, exec_time))
            else:
                # Failure - check retry logic
                job = conn.execute(
                    "SELECT retry_count, max_retries FROM jobs WHERE id=?",
                    (job_id,)
                ).fetchone()
                
                if job and job['retry_count'] < job['max_retries']:
                    # Exponential backoff: 1s, 2s, 4s, 8s...
                    delay = 1000 * (2 ** job['retry_count'])
                    conn.execute("""
                        UPDATE jobs 
                        SET status='pending', scheduled_at=?, retry_count=retry_count+1,
                            error=?, traceback=?, pid=NULL
                        WHERE id=?
                    """, (now + delay, error_info.get('error'),
                         error_info.get('traceback'), job_id))
                else:
                    # Final failure
                    conn.execute("""
                        UPDATE jobs 
                        SET status='failed', completed_at=?, error=?, traceback=?, pid=NULL
                        WHERE id=?
                    """, (now, error_info.get('error'),
                         error_info.get('traceback'), job_id))
        
        # Clean up process reference
        if job_id in self.processes:
            del self.processes[job_id]
    
    def process_results(self):
        """Process completed job results from queue"""
        processed = 0
        while not self.result_queue.empty():
            try:
                job_id, success, result, error = self.result_queue.get_nowait()
                self.complete(job_id, success, result, error)
                processed += 1
            except:
                break
        return processed
    
    def reclaim_stalled(self, timeout_ms: int = 300000) -> int:
        """Reclaim stalled jobs and terminate stuck processes"""
        cutoff = int(time.time() * 1000) - timeout_ms
        
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
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
        
        return len(stalled)
    
    def stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Job counts by status
            counts = {row['status']: row['c'] for row in conn.execute(
                "SELECT status, COUNT(*) c FROM jobs GROUP BY status"
            )}
            
            # Performance metrics
            perf = conn.execute("""
                SELECT AVG(queue_time) avg_qt, AVG(exec_time) avg_et,
                       MAX(queue_time) max_qt, MAX(exec_time) max_et,
                       MIN(queue_time) min_qt, MIN(exec_time) min_et,
                       COUNT(*) total
                FROM metrics
            """).fetchone()
            
            # Recent failures
            failures = conn.execute("""
                SELECT name, error FROM jobs 
                WHERE status='failed' 
                ORDER BY completed_at DESC LIMIT 5
            """).fetchall()
            
            return {
                'jobs': counts,
                'performance': dict(perf) if perf else {},
                'active_processes': len(self.processes),
                'max_workers': self.max_workers,
                'recent_failures': [dict(f) for f in failures]
            }
    
    def save_artifact(self, job_id: int, key: str, value: Any):
        """Save job output artifact"""
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.execute(
                "INSERT INTO artifacts (job_id, key, value) VALUES (?, ?, ?)",
                (job_id, key, pickle.dumps(value))
            )
    
    def get_artifact(self, job_id: int, key: str) -> Any:
        """Retrieve job output artifact"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM artifacts WHERE job_id=? AND key=?",
                (job_id, key)
            ).fetchone()
            return pickle.loads(row['value']) if row else None
    
    def cleanup(self, days: int = 7) -> int:
        """Clean old completed jobs and vacuum database"""
        cutoff = int(time.time() * 1000) - (days * 86400000)
        
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            deleted = conn.execute("""
                DELETE FROM jobs 
                WHERE status IN ('completed', 'failed') AND completed_at < ?
            """, (cutoff,)).rowcount
            
            # Vacuum if significantly fragmented
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
            
            if freelist > page_count * 0.3:
                conn.execute("VACUUM")
        
        return deleted

class Scheduler:
    """Main scheduler with worker pool management"""
    
    def __init__(self, orchestrator: Orchestrator, batch_size: int = 1):
        self.orch = orchestrator
        self.batch_size = batch_size
        self.running = True
        
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
    
    def _shutdown(self, *_):
        self.running = False
        print("\nScheduler shutting down...")
        
        # Terminate all processes
        for p in self.orch.processes.values():
            p.terminate()
            p.join(timeout=1)
    
    def run(self):
        """Main scheduler loop with intelligent job management"""
        print(f"Scheduler started (workers={self.orch.max_workers}, batch={self.batch_size})")
        maintenance_counter = 0
        
        while self.running:
            maintenance_counter += 1
            
            # Process completed jobs
            processed = self.orch.process_results()
            if processed:
                print(f"Processed {processed} job results")
            
            # Periodic maintenance
            if maintenance_counter % 50 == 0:
                reclaimed = self.orch.reclaim_stalled()
                if reclaimed:
                    print(f"Reclaimed {reclaimed} stalled jobs")
            
            # Clean up finished processes
            for job_id, process in list(self.orch.processes.items()):
                if not process.is_alive():
                    process.join(timeout=0.1)
                    if job_id in self.orch.processes:
                        del self.orch.processes[job_id]
            
            # Start new jobs if capacity available
            while len(self.orch.processes) < self.orch.max_workers:
                job = self.orch.get_next()
                
                if not job:
                    break
                
                print(f"Starting job {job['id']}: {job['name']} ({job['func']})")
                self.orch.execute(job)
            
            time.sleep(0.1)
        
        print("Scheduler stopped")

# Built-in job functions
def example_add(x: int, y: int) -> int:
    """Example job that adds two numbers"""
    time.sleep(1)
    return x + y

def example_fail():
    """Example job that always fails"""
    raise ValueError("This job always fails")

def example_long(duration: int = 10) -> str:
    """Example long-running job"""
    time.sleep(duration)
    return f"Completed after {duration} seconds"

def example_data_processor(input_file: str, output_file: str) -> Dict:
    """Example data processing job"""
    # Simulate processing
    time.sleep(2)
    return {"processed": True, "records": 1000, "output": output_file}

# Register built-in jobs
JobRegistry.register("add", example_add)
JobRegistry.register("fail", example_fail)
JobRegistry.register("long", example_long)
JobRegistry.register("process", example_data_processor)

def main():
    """CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Pure Python Job Orchestrator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    # Add command
    add_p = sub.add_parser("add", help="Add a job")
    add_p.add_argument("name", help="Job name")
    add_p.add_argument("func", help="Function name")
    add_p.add_argument("--args", nargs="+", help="Arguments")
    add_p.add_argument("--kwargs", type=json.loads, help="Keyword arguments (JSON)")
    add_p.add_argument("--priority", type=int, default=0)
    add_p.add_argument("--depends", type=int, nargs="+", help="Dependency job IDs")
    add_p.add_argument("--retries", type=int, default=3, help="Max retries")
    add_p.add_argument("--timeout", type=int, default=300, help="Timeout seconds")
    add_p.add_argument("--nice", type=int, help="Process nice value")
    add_p.add_argument("--delay", type=int, default=0, help="Delay seconds")
    
    # Scheduler command
    sched_p = sub.add_parser("scheduler", help="Run scheduler")
    sched_p.add_argument("--workers", type=int, help="Max workers")
    sched_p.add_argument("--batch", type=int, default=1, help="Batch size")
    
    # List command
    list_p = sub.add_parser("list", help="List jobs")
    list_p.add_argument("--status", help="Filter by status")
    list_p.add_argument("--limit", type=int, default=50, help="Limit results")
    
    # Stats command
    sub.add_parser("stats", help="Show statistics")
    
    # Cleanup command
    cleanup_p = sub.add_parser("cleanup", help="Clean old jobs")
    cleanup_p.add_argument("--days", type=int, default=7)
    
    # Load module command
    load_p = sub.add_parser("load", help="Load job module")
    load_p.add_argument("module", help="Python module path")
    
    # Get artifact command
    art_p = sub.add_parser("artifact", help="Get job artifact")
    art_p.add_argument("job_id", type=int)
    art_p.add_argument("key")
    
    args = parser.parse_args()
    orch = Orchestrator()
    
    if args.cmd == 'add':
        # Parse arguments
        parsed_args = []
        if args.args:
            for arg in args.args:
                # Try to parse as number
                try:
                    parsed_args.append(int(arg))
                except ValueError:
                    try:
                        parsed_args.append(float(arg))
                    except ValueError:
                        parsed_args.append(arg)
        
        scheduled_at = None
        if args.delay:
            scheduled_at = int(time.time() * 1000) + (args.delay * 1000)
        
        job_id = orch.add(
            name=args.name,
            func=args.func,
            args=tuple(parsed_args) if parsed_args else None,
            kwargs=args.kwargs,
            priority=args.priority,
            depends_on=args.depends,
            max_retries=args.retries,
            timeout_sec=args.timeout,
            nice=args.nice,
            scheduled_at=scheduled_at
        )
        print(f"Added job {job_id}: {args.name}")
    
    elif args.cmd == 'scheduler':
        if args.workers:
            orch.max_workers = args.workers
        scheduler = Scheduler(orch, args.batch)
        scheduler.run()
    
    elif args.cmd == 'list':
        with sqlite3.connect(orch.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM jobs"
            params = []
            
            if args.status:
                query += " WHERE status=?"
                params.append(args.status)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(args.limit)
            
            jobs = conn.execute(query, params).fetchall()
            
            for job in jobs:
                created = time.strftime('%Y-%m-%d %H:%M:%S',
                                       time.localtime(job['created_at'] / 1000))
                print(f"[{job['id']}] {job['name']} ({job['func']}): "
                      f"{job['status']} (pri={job['priority']}, created={created})")
    
    elif args.cmd == 'stats':
        stats = orch.stats()
        print(json.dumps(stats, indent=2))
    
    elif args.cmd == 'cleanup':
        deleted = orch.cleanup(args.days)
        print(f"Deleted {deleted} old jobs")
    
    elif args.cmd == 'load':
        jobs = JobRegistry.load_module(args.module)
        print(f"Loaded module {args.module}")
        print(f"Available jobs: {jobs}")
    
    elif args.cmd == 'artifact':
        value = orch.get_artifact(args.job_id, args.key)
        if value:
            print(json.dumps(value) if not isinstance(value, bytes) else value)
        else:
            print(f"No artifact '{args.key}' for job {args.job_id}")

if __name__ == "__main__":
    main()