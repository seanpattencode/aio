Of course. This is an excellent request that gets to the heart of software design: finding the right balance between simplicity and functionality.

Here is an enhanced version of the "Minimal Job Queue." It selectively adds back the most critical features from the more advanced scripts (aiose, Orchestrator) while intentionally leaving out the most complex ones (like systemd integration) to maintain its lightweight, dependency-free spirit.

This version is arguably the best balanced of the three for general-purpose use, representing a "sweet spot" of power and simplicity.

Enhanced Minimal AIOSE (aiose-core)

This script reintroduces the following essential features:

Delayed Exponential Backoff: Failed tasks are now rescheduled in the future (e.g., +2s, +4s, +8s), which is crucial for not overwhelming a temporarily failing resource.

Task Dependencies: You can now specify that a task should only run after other tasks have successfully completed.

Named Tasks: Tasks can be given a unique name, making them easier to identify and use in dependency chains.

Per-Task Timeouts: The timeout is no longer hardcoded and can be set for each task.

Environment Variables & Working Directory: Common and essential features for controlling the execution context of a command.

It remains under 300 lines and has no external dependencies.

code
Python
download
content_copy
expand_less
#!/usr/bin/env python3
"""
aiose-core: The essential, balanced job queue in <300 lines.
Adds back key features: delayed retries, dependencies, named tasks, and per-task timeouts.
"""
import argparse, json, os, sqlite3, subprocess, sys, time, threading, signal, shlex
from pathlib import Path

DB_PATH = Path.home() / ".aiose_core.db"

class Store:
    """Enhanced SQLite queue with dependencies and delayed retries."""
    def __init__(self):
        self.db = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript("""
        PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            cmd TEXT NOT NULL,
            args TEXT,
            env TEXT,
            cwd TEXT,
            status TEXT DEFAULT 'q', -- q=queued r=running d=done f=failed
            priority INT DEFAULT 0,
            scheduled_at INT DEFAULT 0,
            dependencies TEXT,       -- JSON list of task IDs
            timeout INT DEFAULT 60,
            retry INT DEFAULT 0,
            error TEXT,
            result TEXT,
            created_at INT DEFAULT (strftime('%s','now')*1000),
            started_at INT,
            ended_at INT
        );
        CREATE INDEX IF NOT EXISTS idx_q ON tasks(status, priority DESC, scheduled_at, id) WHERE status='q';
        """)

    def add(self, cmd, **kwargs):
        with self.lock:
            # Prepare kwargs for DB insertion
            kwargs['cmd'] = cmd
            kwargs['scheduled_at'] = int(time.time()*1000) + kwargs.pop('delay_ms', 0)
            for key in ['args', 'env', 'dependencies']:
                if key in kwargs and kwargs[key] is not None:
                    kwargs[key] = json.dumps(kwargs[key])
            
            cols = ",".join(kwargs.keys())
            placeholders = ",".join("?" for _ in kwargs)
            return self.db.execute(
                f"INSERT INTO tasks({cols}) VALUES({placeholders})", tuple(kwargs.values())
            ).lastrowid

    def pop(self):
        """Atomically get the next task that is scheduled and has its dependencies met."""
        with self.lock:
            now = int(time.time()*1000)
            query = """
                SELECT id, cmd, args, env, cwd, timeout FROM tasks t
                WHERE status='q' AND scheduled_at <= :now
                AND (dependencies IS NULL OR NOT EXISTS (
                    SELECT 1 FROM json_each(t.dependencies) AS d
                    JOIN tasks AS dep_task ON dep_task.id = d.value
                    WHERE dep_task.status != 'd'
                ))
                ORDER BY priority DESC, scheduled_at, id
                LIMIT 1
            """
            row = self.db.execute(query, {'now': now}).fetchone()
            if not row:
                return None

            try: # Atomic UPDATE...RETURNING
                claimed = self.db.execute("""
                    UPDATE tasks SET status='r', started_at=?
                    WHERE id=? AND status='q'
                    RETURNING id, cmd, args, env, cwd, timeout
                """, (now, row['id'])).fetchone()
                return dict(claimed) if claimed else None
            except sqlite3.OperationalError: # Fallback for older SQLite
                updated = self.db.execute(
                    "UPDATE tasks SET status='r', started_at=? WHERE id=? AND status='q'",
                    (now, row['id'])
                ).rowcount
                return dict(row) if updated else None

    def complete(self, task_id, success, result=None, error=None):
        with self.lock:
            now = int(time.time()*1000)
            task = self.db.execute("SELECT retry FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task: return

            if success:
                self.db.execute(
                    "UPDATE tasks SET status='d', ended_at=?, result=? WHERE id=?",
                    (now, json.dumps(result)[:1000] if result else None, task_id)
                )
            elif task['retry'] < 3: # Max 3 retries
                delay_s = 2 ** task['retry'] # 1, 2, 4 seconds -> converted to s
                next_schedule = now + (delay_s * 1000)
                self.db.execute(
                    "UPDATE tasks SET status='q', retry=retry+1, scheduled_at=?, error=? WHERE id=?",
                    (next_schedule, str(error)[:500], task_id)
                )
                print(f"Task {task_id} failed, will retry in {delay_s}s.")
            else:
                self.db.execute(
                    "UPDATE tasks SET status='f', ended_at=?, error=? WHERE id=?",
                    (now, str(error)[:500], task_id)
                )

    def list_tasks(self):
        with self.lock:
            return self.db.execute("SELECT id, name, cmd, status, priority, error FROM tasks ORDER BY created_at DESC LIMIT 50").fetchall()

    def stats(self):
        with self.lock:
            rows = self.db.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status").fetchall()
            return {r['status']: r['c'] for r in rows}

class Worker:
    """Worker that processes tasks with timeout, env, and cwd support."""
    def __init__(self, store):
        self.store = store
        self.running = True
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, *args):
        print("Signal received, shutting down gracefully...")
        self.running = False

    def run(self):
        print(f"Worker started (PID {os.getpid()})")
        while self.running:
            task = self.store.pop()
            if not task:
                time.sleep(0.2) # Sleep a bit longer if idle
                continue

            print(f"Running task {task['id']}: {task['cmd']}")
            try:
                cmd_list = [task['cmd']]
                if task['args']:
                    cmd_list.extend(json.loads(task['args']))
                
                env = os.environ.copy()
                if task['env']:
                    env.update(json.loads(task['env']))

                proc = subprocess.run(
                    cmd_list, capture_output=True, text=True,
                    timeout=task['timeout'],
                    env=env,
                    cwd=task['cwd'] # Can be None
                )
                self.store.complete(
                    task['id'],
                    proc.returncode == 0,
                    {'stdout': proc.stdout[:1000], 'stderr': proc.stderr[:1000]},
                    proc.stderr if proc.returncode != 0 else None
                )
                print(f"Task {task['id']}: {'success' if proc.returncode == 0 else 'failed'}")

            except subprocess.TimeoutExpired:
                self.store.complete(task['id'], False, error="Timeout")
                print(f"Task {task['id']}: timeout")
            except Exception as e:
                self.store.complete(task['id'], False, error=str(e))
                print(f"Task {task['id']}: error - {e}")

        print("Worker stopped")

def main():
    parser = argparse.ArgumentParser(description="aiose-core: A balanced, essential job queue.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    add_p = sub.add_parser("add", help="Add a task")
    add_p.add_argument("command", help="Command to run")
    add_p.add_argument("args", nargs="*", help="Arguments for the command")
    add_p.add_argument("--name", help="Unique name for the task")
    add_p.add_argument("-p", "--priority", type=int, default=0, help="Higher is sooner")
    add_p.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    add_p.add_argument("--deps", type=int, nargs='*', help="List of task IDs this task depends on")
    add_p.add_argument("--env", action="append", help="Set environment variables (e.g., KEY=VALUE)")
    add_p.add_argument("--cwd", help="Set the working directory")

    sub.add_parser("worker", help="Run the task processing worker")
    sub.add_parser("list", help="List recent tasks")
    sub.add_parser("stats", help="Show queue statistics")

    args = parser.parse_args()
    store = Store()

    if args.cmd == "add":
        env_dict = dict(e.split("=", 1) for e in args.env) if args.env else None
        task_id = store.add(
            args.command,
            args=args.args if args.args else None,
            name=args.name,
            priority=args.priority,
            timeout=args.timeout,
            dependencies=args.deps,
            env=env_dict,
            cwd=args.cwd
        )
        print(f"Added task {task_id}")

    elif args.cmd == "worker":
        Worker(store).run()

    elif args.cmd == "list":
        for task in store.list_tasks():
            name = f" ({task['name']})" if task['name'] else ""
            error_info = f" | ERR: {task['error'][:50]}" if task['status'] == 'f' and task['error'] else ""
            print(f"[{task['id']:<4}] {task['status']:<7} P={task['priority']} | {task['cmd']}{name}{error_info}")

    elif args.cmd == "stats":
        print(json.dumps(store.stats(), indent=2))

if __name__ == "__main__":
    main()
Evaluation: Why This Version is "Better" as a General-Purpose Tool

Solves Real-World Problems: The "Minimal" script was a great demo, but it would fail in many real scenarios. The lack of delayed retries would hammer a failing API. The lack of dependencies would make it impossible to build multi-step workflows (e.g., "download data," then "process data," then "upload results"). This version solves those fundamental problems.

Maintains Simplicity: The core logic is still just two classes (Store, Worker) and a CLI. It introduces no external libraries or platform-specific dependencies like systemd. It remains highly portable and easy to understand.

Improved Ergonomics: The addition of named tasks, per-task timeouts, and environment variables makes it far more pleasant and practical to use for anything beyond a trivial script. The worker is also more robust now because it passes a list of arguments to subprocess.run instead of using shell=True with a manually quoted string, which is safer.

Represents a Mature Compromise: This version demonstrates the programming maturity of knowing what to include and what to leave out. It takes the most critical 80% of features for a job queue and implements them cleanly, leaving out the most complex 20% that require a different architectural approach.

In the spectrum of the four scripts, this one hits the ideal middle ground for a powerful, reliable, and yet simple-to-manage local job queue.