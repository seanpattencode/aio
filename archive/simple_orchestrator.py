#!/usr/bin/env python3
"""
AIOS Simple Orchestrator - Clean process management in under 500 lines
Strict performance requirements: All operations must complete within 100ms
"""

import datetime
import importlib.util
import json
import os
import random
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

# Configuration
ROOT = Path(__file__).parent.resolve()
PROGRAMS = ROOT / "Programs"
DB_PATH = ROOT / "orchestrator.db"
DEVICE_ID = os.environ.get("DEVICE_ID", str(os.getpid()))
DEVICE_TAGS = {t for t in os.environ.get("DEVICE_TAGS", "").split(",") if t}
PERF_LIMIT = 0.1  # 100ms performance limit

# Ensure Programs directory exists
PROGRAMS.mkdir(exist_ok=True)

# Database schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    name TEXT PRIMARY KEY, status TEXT, device TEXT, updated REAL, pid INTEGER);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, level TEXT, message TEXT, device TEXT);
CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT, args TEXT, kwargs TEXT,
    created REAL, done REAL);
CREATE TABLE IF NOT EXISTS config (
    name TEXT PRIMARY KEY, file TEXT, func TEXT, type TEXT, tags TEXT,
    retries INTEGER DEFAULT 3, time TEXT, after TEXT, before TEXT,
    interval INTEGER, priority INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1);
"""

# Default jobs
DEFAULTS = [
    {"name": "web_server", "file": "web_server.py", "func": "run_server",
     "type": "always", "retries": 999},
    {"name": "stock_monitor", "file": "stock_monitor.py", "func": "monitor_stocks",
     "type": "always", "tags": ["gpu"], "retries": 999},
    {"name": "morning_report", "file": "reports.py", "func": "generate_morning_report",
     "type": "daily", "time": "09:00"},
    {"name": "random_check", "file": "health_check.py", "func": "random_health_check",
     "type": "random_daily", "after": "14:00", "before": "18:00"},
    {"name": "backup", "file": "google_drive_backup.py", "func": "backup_to_drive",
     "type": "interval", "interval": 30},
    {"name": "llm_processor", "file": "llm_tasks.py", "func": "process_llm_queue",
     "type": "trigger", "tags": ["gpu"]},
    {"name": "idle_task", "file": "idle_task.py", "func": "run_idle",
     "type": "idle", "priority": -1},
]


class ProcessManager:
    """Manages subprocesses with clean termination and restart."""

    def __init__(self):
        self.procs = {}  # name -> subprocess.Popen
        self.lock = threading.Lock()
        signal.signal(signal.SIGCHLD, self._reap)

    def _reap(self, signum, frame):
        """Reap zombie children immediately."""
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                with self.lock:
                    for name, proc in list(self.procs.items()):
                        if proc.pid == pid:
                            del self.procs[name]
                            break
            except ChildProcessError:
                break

    def start(self, name: str, cmd: str) -> Optional[int]:
        """Start a process in its own group."""
        # Don't use lock context manager here to avoid deadlock with stop()
        self.lock.acquire()
        try:
            # Check if already running
            if name in self.procs and self.procs[name].poll() is None:
                pid = self.procs[name].pid
                self.lock.release()
                return pid

            # Stop if process exists but is dead
            if name in self.procs:
                del self.procs[name]

            # Start new process
            try:
                if os.name != 'nt':
                    proc = subprocess.Popen(
                        cmd, shell=True, preexec_fn=os.setsid,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                else:
                    proc = subprocess.Popen(
                        cmd, shell=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                self.procs[name] = proc
                log("INFO", f"Started {name} (pid={proc.pid})")
                return proc.pid
            except Exception as e:
                log("ERROR", f"Failed to start {name}: {e}")
                return None
        finally:
            self.lock.release()

    def stop(self, name: str):
        """Kill process and all its children."""
        with self.lock:
            if name not in self.procs:
                return
            proc = self.procs[name]
            try:
                # Check if process is still alive before trying to kill it
                if proc.poll() is None:
                    if os.name != 'nt':
                        # Use SIGKILL immediately for fastest shutdown
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        proc.wait(timeout=0.01)  # 10ms max wait
                    else:
                        proc.kill()  # Use kill directly on Windows
                        proc.wait(timeout=0.01)
            except Exception as e:
                pass  # Process might have already exited
            finally:
                if name in self.procs:  # Check again before deleting
                    del self.procs[name]

    def stop_all(self):
        """Stop all processes with parallel termination for speed."""
        with self.lock:
            if not self.procs:
                return
            # Send SIGKILL immediately to all processes (parallel) for fastest shutdown
            for name, proc in self.procs.items():
                try:
                    if os.name != 'nt':
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    else:
                        proc.kill()
                except:
                    pass
            # Very brief wait to ensure processes are dead
            time.sleep(0.005)  # 5ms to allow OS to clean up
            self.procs.clear()

    def is_running(self, name: str) -> bool:
        """Check if process is running."""
        with self.lock:
            if name not in self.procs:
                return False
            return self.procs[name].poll() is None


PM = ProcessManager()


def db(query: str, params=(), fetch=None):
    """Execute database query."""
    conn = sqlite3.connect(DB_PATH, timeout=1.0)
    conn.row_factory = sqlite3.Row if fetch else None
    cursor = conn.execute(query, params)
    conn.commit()
    if fetch == "one":
        result = cursor.fetchone()
    elif fetch == "all":
        result = cursor.fetchall()
    else:
        result = None
    conn.close()
    return result


def log(level: str, msg: str):
    """Log to database and console."""
    t = time.time()
    try:
        db("INSERT INTO logs (timestamp, level, message, device) VALUES (?, ?, ?, ?)",
           (t, level, msg, DEVICE_ID))
    except:
        pass
    ts = datetime.datetime.fromtimestamp(t).strftime('%H:%M:%S')
    print(f"{ts} [{level}] {msg}", flush=True)


def update_job(name: str, status: str, pid: Optional[int] = None):
    """Update job status in database."""
    db("""INSERT INTO jobs (name, status, device, updated, pid) VALUES (?, ?, ?, ?, ?)
          ON CONFLICT(name) DO UPDATE SET
          status=excluded.status, device=excluded.device,
          updated=excluded.updated, pid=excluded.pid""",
       (name, status, DEVICE_ID, time.time(), pid))


def init_db():
    """Initialize database with schema and defaults."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    if conn.execute("SELECT 1 FROM config LIMIT 1").fetchone():
        conn.close()
        return
    for job in DEFAULTS:
        conn.execute("""
            INSERT OR IGNORE INTO config
            (name, file, func, type, tags, retries, time, after, before, interval, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job["name"], job["file"], job.get("func", "run"), job["type"],
             json.dumps(job.get("tags", [])), job.get("retries", 3),
             job.get("time"), job.get("after"), job.get("before"),
             job.get("interval"), job.get("priority", 0)))
    conn.commit()
    conn.close()
    log("INFO", "Database initialized")


def load_function(file: str, func: str):
    """Load a function from a Python file."""
    path = PROGRAMS / file
    if not path.exists():
        path.write_text(f"def {func}(*args, **kwargs):\n    print('{func} called')\n")
    spec = importlib.util.spec_from_file_location("module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, func, None)


def run_job(job: dict, *args, **kwargs):
    """Execute a job."""
    name = job["name"]
    if job["type"] == "always":
        path = PROGRAMS / job["file"]
        cmd = f"{sys.executable} -c \"import sys; sys.path.insert(0, '{PROGRAMS}'); "
        cmd += f"from {job['file'][:-3]} import {job['func']}; {job['func']}()\""
        retries = job.get("retries", 3)
        log("INFO", f"Starting {name} as always job with command: {cmd[:100]}...")
        for attempt in range(retries):
            pid = PM.start(name, cmd)
            if pid:
                update_job(name, "running", pid)
                return
            if attempt < retries - 1:
                log("WARNING", f"Failed to start {name}, attempt {attempt+1}/{retries}")
                time.sleep(min(2 ** attempt, 5))
        update_job(name, "failed")
        log("ERROR", f"Failed to start {name} after {retries} attempts")
    else:
        update_job(name, "running")
        try:
            func = load_function(job["file"], job["func"])
            if func:
                result = func(*args, **kwargs)
                log("INFO", f"{name} completed: {result}")
                update_job(name, "completed")
            else:
                raise Exception(f"Function {job['func']} not found")
        except Exception as e:
            log("ERROR", f"{name} failed: {e}")
            update_job(name, "failed")


def should_run(job: dict, now: datetime.datetime, non_idle: int) -> bool:
    """Check if job should run based on schedule."""
    tags = set(json.loads(job["tags"])) if job["tags"] else set()
    if tags and not tags.issubset(DEVICE_TAGS):
        return False
    status = db("SELECT status FROM jobs WHERE name = ?", (job["name"],), fetch="one")
    if status and status["status"] == "running":
        return False
    type_ = job["type"]
    if type_ == "always":
        return False  # Always jobs are handled separately in main_loop
    if type_ == "trigger":
        return False
    if type_ == "idle":
        return non_idle == 0
    last = db("SELECT updated FROM jobs WHERE name = ?", (job["name"],), fetch="one")
    last_time = last["updated"] if last else 0
    if type_ == "daily":
        if not job["time"]:
            return False
        target_h, target_m = map(int, job["time"].split(":"))
        if now.hour >= target_h and now.minute >= target_m:
            if last_time == 0:
                return True
            last_date = datetime.datetime.fromtimestamp(last_time).date()
            return last_date < now.date()
    if type_ == "interval":
        if not job["interval"]:
            return False
        if last_time == 0:
            return True
        return (time.time() - last_time) / 60 >= job["interval"]
    if type_ == "random_daily":
        if last_time > 0:
            last_date = datetime.datetime.fromtimestamp(last_time).date()
            if last_date >= now.date():
                return False
        after_h, after_m = map(int, (job["after"] or "00:00").split(":"))
        before_h, before_m = map(int, (job["before"] or "23:59").split(":"))
        now_mins = now.hour * 60 + now.minute
        after_mins = after_h * 60 + after_m
        before_mins = before_h * 60 + before_m
        if after_mins <= now_mins <= before_mins:
            return random.random() < 0.01
    return False


def process_triggers():
    """Process pending triggers with performance monitoring."""
    triggers = db("SELECT * FROM triggers WHERE done IS NULL", fetch="all") or []
    for trigger in triggers:
        job_name = trigger["job"]
        start_time = time.time()
        if job_name == "RESTART_ALL":
            PM.stop_all()
            db("UPDATE jobs SET status = 'stopped', pid = NULL")
            elapsed = time.time() - start_time
            if elapsed > PERF_LIMIT:
                log("ERROR", f"PERFORMANCE CRITICAL: Full restart took {elapsed*1000:.1f}ms (>100ms limit)")
                raise Exception(f"Restart performance violation: {elapsed*1000:.1f}ms > 100ms")
            log("INFO", f"All jobs restarted in {elapsed*1000:.1f}ms")
        elif job_name.startswith("RESTART_"):
            name = job_name[8:]
            PM.stop(name)
            update_job(name, "stopped")
            elapsed = time.time() - start_time
            if elapsed > PERF_LIMIT:
                log("ERROR", f"PERFORMANCE CRITICAL: Job restart took {elapsed*1000:.1f}ms (>100ms limit)")
                raise Exception(f"Restart performance violation: {elapsed*1000:.1f}ms > 100ms")
            log("INFO", f"Restarted {name} in {elapsed*1000:.1f}ms")
        else:
            job = db("SELECT * FROM config WHERE name = ?", (job_name,), fetch="one")
            if job:
                args = json.loads(trigger["args"])
                kwargs = json.loads(trigger["kwargs"])
                threading.Thread(target=run_job, args=(dict(job), *args),
                               kwargs=kwargs, daemon=True).start()
        db("UPDATE triggers SET done = ? WHERE id = ?", (time.time(), trigger["id"]))


RUNNING = True  # Global flag for clean shutdown

def main_loop():
    """Main scheduler loop with startup performance monitoring."""
    global RUNNING
    startup_time = time.time()
    db("UPDATE jobs SET pid = NULL WHERE status != 'running'")
    startup_elapsed = time.time() - startup_time
    if startup_elapsed > PERF_LIMIT:
        log("ERROR", f"PERFORMANCE CRITICAL: Startup took {startup_elapsed*1000:.1f}ms (>100ms limit)")
        print(f"\n*** PERFORMANCE VIOLATION: Startup took {startup_elapsed*1000:.1f}ms (must be <100ms) ***\n", file=sys.stderr, flush=True)
        sys.exit(1)
    log("INFO", f"Orchestrator started in {startup_elapsed*1000:.1f}ms (device={DEVICE_ID}, tags={sorted(DEVICE_TAGS)})")
    while RUNNING:
        try:
            now = datetime.datetime.now()
            jobs = db("SELECT * FROM config WHERE enabled = 1", fetch="all") or []
            running = db("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'running' "
                        "AND name NOT LIKE 'idle%'", fetch="one")
            non_idle = running["cnt"] if running else 0
            for job in jobs:
                job = dict(job)
                if job["type"] == "always":
                    # Check tags for always jobs
                    tags = set(json.loads(job["tags"])) if job["tags"] else set()
                    if tags and not tags.issubset(DEVICE_TAGS):
                        continue  # Skip if tags don't match
                    status = db("SELECT status FROM jobs WHERE name = ?",
                              (job["name"],), fetch="one")
                    if status and status["status"] == "running":
                        if not PM.is_running(job["name"]):
                            log("WARNING", f"{job['name']} died, restarting")
                            update_job(job["name"], "stopped")
                            threading.Thread(target=run_job, args=(job,), daemon=True).start()
                    elif not status or status["status"] != "running":
                        # Start "always" job if not already running
                        threading.Thread(target=run_job, args=(job,), daemon=True).start()
                elif should_run(job, now, non_idle):
                    threading.Thread(target=run_job, args=(job,), daemon=True).start()
            process_triggers()
        except Exception as e:
            log("ERROR", f"Scheduler error: {e}")

        # Use smaller sleep intervals for faster shutdown response
        for _ in range(10):
            if not RUNNING:
                break
            time.sleep(0.1)


def shutdown(signum=None, frame=None):
    """Clean shutdown with performance monitoring."""
    global RUNNING
    RUNNING = False  # Stop the main loop
    start_time = time.time()

    # Kill all processes immediately
    PM.stop_all()

    # Quick database update - don't wait
    try:
        db("UPDATE jobs SET status = 'stopped', pid = NULL")
    except:
        pass  # Don't block on DB errors

    elapsed = time.time() - start_time

    # Log after measuring time to get accurate measurement
    if elapsed <= PERF_LIMIT:
        print(f"Shutdown completed in {elapsed*1000:.1f}ms", flush=True)
    else:
        print(f"PERFORMANCE CRITICAL: Shutdown took {elapsed*1000:.1f}ms (>100ms limit)", flush=True)

    # Exit immediately
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("AIOS Simple Orchestrator - Performance-Critical Process Manager")
            print("Usage: python simple_orchestrator.py [--force]")
            print("\nPerformance Requirements:")
            print("  - All operations must complete within 100ms")
            print("  - Violations will trigger critical errors")
            sys.exit(0)
        elif sys.argv[1] == "--force":
            init_db()
            conn = sqlite3.connect(DB_PATH)
            try:
                conn.execute("DELETE FROM jobs")
                conn.execute("DELETE FROM triggers")
                conn.commit()
                print("Force restart - cleared job states")
            except:
                pass
            finally:
                conn.close()
    init_db()
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        main_loop()
    except KeyboardInterrupt:
        shutdown()