#!/usr/bin/env python3
"""Essential Job Queue - Minimal but production-ready in ~350 lines"""
import argparse, json, os, shlex, sqlite3, subprocess, sys, time, threading, signal
from pathlib import Path
from typing import Optional, Dict, Any, List

DB_PATH = Path.home() / ".essential_aiose.db"
UNIT_PREFIX = "eaiose-"
SYSTEMCTL = ["systemctl", "--user"] if os.geteuid() != 0 else ["systemctl"]
SYSDRUN = ["systemd-run", "--user", "--collect", "--quiet"] if os.geteuid() != 0 else ["systemd-run", "--collect", "--quiet"]

class Store:
    """SQLite queue with dependencies, scheduling, and metrics"""
    def __init__(self):
        self.db = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        
        # Production SQLite settings
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA busy_timeout=5000;
        PRAGMA cache_size=-8000;
        
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            cmd TEXT NOT NULL,
            mode TEXT DEFAULT 'local',  -- local or systemd
            args TEXT,
            env TEXT,
            status TEXT DEFAULT 'q',    -- q=queued r=running d=done f=failed
            priority INT DEFAULT 0,
            at INT DEFAULT 0,            -- scheduled_at (ms epoch)
            retry INT DEFAULT 0,
            max_retry INT DEFAULT 3,
            timeout INT DEFAULT 300,
            deps TEXT,                   -- JSON array of task IDs
            worker TEXT,
            error TEXT,
            result TEXT,
            created INT DEFAULT (strftime('%s','now')*1000),
            started INT,
            ended INT,
            -- systemd fields
            unit TEXT,
            mem_max_mb INT,
            cpu_weight INT
        );
        CREATE INDEX IF NOT EXISTS idx_queue ON tasks(status, priority DESC, at, id) 
            WHERE status IN ('q', 'r');
        CREATE INDEX IF NOT EXISTS idx_deps ON tasks(status) WHERE status='d';
        """)

    def add(self, **kw) -> int:
        """Add task with validation"""
        with self.lock:
            # Set scheduled time if delayed
            if 'delay' in kw:
                kw['at'] = int(time.time() * 1000) + (kw.pop('delay') * 1000)
            
            # Serialize JSON fields
            for field in ['args', 'env', 'deps']:
                if field in kw and kw[field] is not None:
                    kw[field] = json.dumps(kw[field])
            
            cols = ','.join(kw.keys())
            placeholders = ','.join('?' * len(kw))
            return self.db.execute(
                f"INSERT INTO tasks({cols}) VALUES({placeholders})",
                tuple(kw.values())
            ).lastrowid

    def pop(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Atomically get next eligible task (with dependency checking)"""
        with self.lock:
            now = int(time.time() * 1000)
            
            # Find eligible task
            row = self.db.execute("""
                SELECT id, name, cmd, mode, args, env, timeout, mem_max_mb, cpu_weight
                FROM tasks t
                WHERE status='q' 
                  AND at <= ?
                  AND mode IN ('local', 'systemd')
                  AND (deps IS NULL OR NOT EXISTS (
                      SELECT 1 FROM json_each(t.deps) AS d
                      JOIN tasks dt ON dt.id = d.value
                      WHERE dt.status != 'd'
                  ))
                ORDER BY priority DESC, at, id
                LIMIT 1
            """, (now,)).fetchone()
            
            if not row:
                return None
            
            # Try atomic claim with RETURNING
            try:
                claimed = self.db.execute("""
                    UPDATE tasks SET status='r', worker=?, started=?
                    WHERE id=? AND status='q'
                    RETURNING id, name, cmd, mode, args, env, timeout, mem_max_mb, cpu_weight
                """, (worker_id, now, row['id'])).fetchone()
                
                if claimed:
                    task = dict(claimed)
                    # Parse JSON fields
                    for field in ['args', 'env']:
                        if task[field]:
                            task[field] = json.loads(task[field])
                    return task
                    
            except sqlite3.OperationalError:
                # Fallback for older SQLite
                n = self.db.execute(
                    "UPDATE tasks SET status='r', worker=?, started=? WHERE id=? AND status='q'",
                    (worker_id, now, row['id'])
                ).rowcount
                if n:
                    task = dict(row)
                    for field in ['args', 'env']:
                        if task[field]:
                            task[field] = json.loads(task[field])
                    return task
            
            return None

    def complete(self, task_id: int, success: bool, result: str = None, error: str = None):
        """Mark task complete or schedule retry"""
        with self.lock:
            now = int(time.time() * 1000)
            task = self.db.execute(
                "SELECT retry, max_retry FROM tasks WHERE id=?", 
                (task_id,)
            ).fetchone()
            
            if not task:
                return
            
            if success:
                self.db.execute(
                    "UPDATE tasks SET status='d', ended=?, result=?, worker=NULL WHERE id=?",
                    (now, result[:1000] if result else None, task_id)
                )
            elif task['retry'] < task['max_retry']:
                # Exponential backoff: 1s, 2s, 4s, 8s...
                delay = 1000 * (2 ** task['retry'])
                self.db.execute(
                    "UPDATE tasks SET status='q', at=?, retry=retry+1, error=?, worker=NULL WHERE id=?",
                    (now + delay, error[:500] if error else None, task_id)
                )
            else:
                self.db.execute(
                    "UPDATE tasks SET status='f', ended=?, error=?, worker=NULL WHERE id=?",
                    (now, error[:500] if error else None, task_id)
                )

    def reclaim_stalled(self, timeout_ms: int = 300000) -> int:
        """Reclaim tasks that have been running too long"""
        with self.lock:
            cutoff = int(time.time() * 1000) - timeout_ms
            return self.db.execute(
                "UPDATE tasks SET status='q', worker=NULL, retry=retry+1 WHERE status='r' AND started < ?",
                (cutoff,)
            ).rowcount

    def update_systemd_task(self, task_id: int, unit: str):
        """Update task with systemd unit name"""
        with self.lock:
            self.db.execute("UPDATE tasks SET unit=? WHERE id=?", (unit, task_id))

    def get_systemd_tasks(self) -> List[sqlite3.Row]:
        """Get all tasks tracked by systemd"""
        with self.lock:
            return self.db.execute(
                "SELECT id, unit FROM tasks WHERE status='r' AND unit IS NOT NULL"
            ).fetchall()

    def list_tasks(self, limit: int = 50) -> List[sqlite3.Row]:
        with self.lock:
            return self.db.execute(
                "SELECT id, name, cmd, mode, status, priority, retry, created FROM tasks "
                "ORDER BY created DESC LIMIT ?",
                (limit,)
            ).fetchall()

    def stats(self) -> Dict[str, Any]:
        with self.lock:
            counts = self.db.execute(
                "SELECT status, COUNT(*) c FROM tasks GROUP BY status"
            ).fetchall()
            
            timing = self.db.execute("""
                SELECT 
                    AVG(CASE WHEN started AND created THEN (started - created) / 1000.0 END) as avg_queue_time,
                    AVG(CASE WHEN ended AND started THEN (ended - started) / 1000.0 END) as avg_exec_time
                FROM tasks WHERE status='d'
            """).fetchone()
            
            return {
                'tasks': {r['status']: r['c'] for r in counts},
                'timing': dict(timing) if timing else {}
            }

    def cleanup(self, days: int = 7) -> int:
        """Remove old completed tasks"""
        cutoff = int(time.time() * 1000) - (days * 86400 * 1000)
        with self.lock:
            return self.db.execute(
                "DELETE FROM tasks WHERE status IN ('d', 'f') AND ended < ?",
                (cutoff,)
            ).rowcount


class Worker:
    """Worker with local and systemd execution modes"""
    def __init__(self, store: Store, batch_size: int = 1):
        self.store = store
        self.batch_size = batch_size
        self.worker_id = f"w{os.getpid()}"
        self.running = True
        
        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, 'running', False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, 'running', False))

    def execute_local(self, task: Dict[str, Any]) -> tuple[bool, str, str]:
        """Execute task as local subprocess"""
        try:
            # Build command
            if task['args']:
                cmd = [task['cmd']] + task['args']
            else:
                cmd = task['cmd']
            
            # Prepare environment
            env = os.environ.copy()
            if task['env']:
                env.update(task['env'])
            
            # Run with timeout
            proc = subprocess.run(
                cmd,
                shell=isinstance(cmd, str),
                capture_output=True,
                text=True,
                timeout=task.get('timeout', 300),
                env=env
            )
            
            result = json.dumps({
                'stdout': proc.stdout[:500],
                'stderr': proc.stderr[:500],
                'returncode': proc.returncode
            })
            
            return (proc.returncode == 0, result, proc.stderr if proc.returncode != 0 else None)
            
        except subprocess.TimeoutExpired:
            return (False, None, "Task timed out")
        except Exception as e:
            return (False, None, str(e))

    def execute_systemd(self, task: Dict[str, Any]) -> tuple[bool, str, str]:
        """Execute task via systemd-run"""
        try:
            unit_name = f"{UNIT_PREFIX}{task.get('name', task['id'])}.service"
            
            # Build systemd-run command
            cmd_parts = SYSDRUN + [
                "--unit", unit_name,
                "--property=KillMode=mixed",
                f"--property=TimeoutSec={task.get('timeout', 300)}"
            ]
            
            # Add resource limits if specified
            if task.get('mem_max_mb'):
                cmd_parts.append(f"--property=MemoryMax={task['mem_max_mb']}M")
            if task.get('cpu_weight'):
                cmd_parts.append(f"--property=CPUWeight={task['cpu_weight']}")
            
            # Add environment
            if task.get('env'):
                for k, v in task['env'].items():
                    cmd_parts.extend(["--setenv", f"{k}={v}"])
            
            # Add the actual command
            if task.get('args'):
                cmd_parts.extend(["--", task['cmd']] + task['args'])
            else:
                cmd_parts.extend(["--", "sh", "-c", task['cmd']])
            
            # Launch via systemd
            proc = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=10)
            
            if proc.returncode == 0:
                self.store.update_systemd_task(task['id'], unit_name)
                return (True, f"Started as {unit_name}", None)
            else:
                return (False, None, f"systemd-run failed: {proc.stderr}")
                
        except Exception as e:
            return (False, None, f"systemd execution error: {str(e)}")

    def reconcile_systemd(self):
        """Check systemd units and update task status"""
        tasks = self.store.get_systemd_tasks()
        if not tasks:
            return
        
        for task in tasks:
            try:
                # Check unit status
                result = subprocess.run(
                    SYSTEMCTL + ["show", task['unit'], "--property=ActiveState,Result"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    props = dict(line.split('=', 1) for line in result.stdout.strip().split('\n') if '=' in line)
                    
                    if props.get('ActiveState') == 'inactive':
                        success = props.get('Result') == 'success'
                        self.store.complete(
                            task['id'],
                            success,
                            f"systemd result: {props.get('Result')}",
                            None if success else f"Unit failed: {props.get('Result')}"
                        )
            except Exception as e:
                print(f"Reconciliation error for {task['unit']}: {e}")

    def run(self):
        """Main worker loop"""
        print(f"Worker {self.worker_id} started (batch={self.batch_size})")
        tick = 0
        
        while self.running:
            tick += 1
            
            # Periodic maintenance
            if tick % 100 == 0:
                reclaimed = self.store.reclaim_stalled()
                if reclaimed:
                    print(f"Reclaimed {reclaimed} stalled tasks")
                self.reconcile_systemd()
            
            # Process batch of tasks
            processed = 0
            for _ in range(self.batch_size):
                task = self.store.pop(self.worker_id)
                if not task:
                    break
                
                processed += 1
                task_id = task['id']
                name = task.get('name', f"task_{task_id}")
                
                print(f"Executing [{task_id}] {name} mode={task['mode']}")
                
                # Execute based on mode
                if task['mode'] == 'systemd':
                    success, result, error = self.execute_systemd(task)
                else:
                    success, result, error = self.execute_local(task)
                
                # Only mark complete for local tasks (systemd tasks complete via reconciliation)
                if task['mode'] == 'local':
                    self.store.complete(task_id, success, result, error)
                    print(f"Task [{task_id}] {'completed' if success else 'failed'}")
            
            # Sleep if no work
            if processed == 0:
                time.sleep(0.1)
        
        print(f"Worker {self.worker_id} stopped")


def main():
    parser = argparse.ArgumentParser(description="Essential Job Queue")
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    # Add command
    add_p = sub.add_parser("add", help="Add task")
    add_p.add_argument("command", help="Command to run")
    add_p.add_argument("args", nargs="*", help="Arguments")
    add_p.add_argument("-n", "--name", help="Unique name")
    add_p.add_argument("-m", "--mode", choices=["local", "systemd"], default="local")
    add_p.add_argument("-p", "--priority", type=int, default=0)
    add_p.add_argument("-d", "--delay", type=int, help="Delay in seconds")
    add_p.add_argument("--deps", help="Comma-separated dependency IDs")
    add_p.add_argument("-t", "--timeout", type=int, default=300)
    add_p.add_argument("-r", "--retries", type=int, default=3)
    add_p.add_argument("-e", "--env", action="append", help="KEY=VALUE")
    add_p.add_argument("--mem-max-mb", type=int, help="Memory limit (systemd)")
    add_p.add_argument("--cpu-weight", type=int, help="CPU weight (systemd)")
    
    # Worker
    work_p = sub.add_parser("worker", help="Run worker")
    work_p.add_argument("-b", "--batch", type=int, default=1, help="Batch size")
    
    # Management
    sub.add_parser("list", help="List tasks")
    sub.add_parser("stats", help="Show statistics")
    clean_p = sub.add_parser("cleanup", help="Clean old tasks")
    clean_p.add_argument("--days", type=int, default=7)
    
    args = parser.parse_args()
    store = Store()
    
    if args.cmd == "add":
        kw = {
            'cmd': args.command,
            'mode': args.mode,
            'priority': args.priority,
            'timeout': args.timeout,
            'max_retry': args.retries
        }
        
        if args.name:
            kw['name'] = args.name
        if args.args:
            kw['args'] = args.args
        if args.delay:
            kw['delay'] = args.delay
        if args.deps:
            kw['deps'] = [int(d.strip()) for d in args.deps.split(',')]
        if args.env:
            kw['env'] = dict(e.split('=', 1) for e in args.env)
        if args.mem_max_mb:
            kw['mem_max_mb'] = args.mem_max_mb
        if args.cpu_weight:
            kw['cpu_weight'] = args.cpu_weight
        
        task_id = store.add(**kw)
        print(f"Added task {task_id}")
    
    elif args.cmd == "worker":
        Worker(store, args.batch).run()
    
    elif args.cmd == "list":
        for task in store.list_tasks():
            deps = f" deps={task['deps']}" if task['deps'] else ""
            print(f"[{task['id']:3}] {task['name'] or 'unnamed':15} {task['cmd']:30} "
                  f"status={task['status']} mode={task['mode']} p={task['priority']}{deps}")
    
    elif args.cmd == "stats":
        print(json.dumps(store.stats(), indent=2))
    
    elif args.cmd == "cleanup":
        n = store.cleanup(args.days)
        print(f"Cleaned up {n} old tasks")

if __name__ == "__main__":
    main()