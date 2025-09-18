#!/usr/bin/env python3
"""
AIOS Orchestrator - Automated Intelligence Operating System

⚠️  IMPORTANT: This application MUST be run using Docker for proper isolation and dependency management.
⚠️  DO NOT run this directly with Python. Use the Docker instructions in the README.
⚠️  Running outside Docker may cause security issues, dependency conflicts, and unpredictable behavior.
"""

import datetime
import importlib.util
import json
import os
import random
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Docker environment check and warning
if not os.path.exists('/.dockerenv') and 'DOCKER_CONTAINER' not in os.environ:
    print("\n" + "="*80)
    print("⚠️  WARNING: AIOS Orchestrator should ONLY be run using Docker!")
    print("="*80)
    print("Running outside Docker is not supported and may cause:")
    print("  - Security vulnerabilities")
    print("  - Dependency conflicts")
    print("  - Data corruption")
    print("  - Unpredictable behavior")
    print("\nPlease use Docker to run this application:")
    print("  cd docker && docker-compose up -d")
    print("="*80 + "\n")
    if '--force' not in sys.argv:
        print("Add --force flag to bypass this warning (NOT RECOMMENDED)")
        sys.exit(1)

ROOT_DIR = Path(__file__).parent.resolve()
PROGRAMS_DIR = ROOT_DIR / "Programs"
STATE_DB = ROOT_DIR / "orchestrator.db"

DEVICE_ID = os.environ.get("DEVICE_ID", str(os.getpid()))
DEVICE_TAGS = {tag for tag in os.environ.get("DEVICE_TAGS", "").split(",") if tag}

PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS jobs (job_name TEXT PRIMARY KEY, status TEXT NOT NULL, device TEXT NOT NULL, last_update REAL NOT NULL);"
    "CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL, device TEXT NOT NULL);"
    "CREATE TABLE IF NOT EXISTS triggers (id INTEGER PRIMARY KEY AUTOINCREMENT, job_name TEXT NOT NULL, args TEXT NOT NULL, kwargs TEXT NOT NULL, created REAL NOT NULL, processed REAL);"
    "CREATE TABLE IF NOT EXISTS scheduled_jobs (name TEXT PRIMARY KEY, file TEXT NOT NULL, function TEXT NOT NULL, type TEXT NOT NULL, tags TEXT, retries INTEGER DEFAULT 3, time TEXT, after_time TEXT, before_time TEXT, interval_minutes INTEGER, priority INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1);"
    "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL NOT NULL);"
)

DEFAULT_JOBS = [
    dict(name="web_server_daemon", file="web_server.py", function="run_server", type="always", tags=["browser"], retries=999),
    dict(name="stock_monitor", file="stock_monitor.py", function="monitor_stocks", type="always", tags=["gpu"], retries=999),
    dict(name="morning_report", file="reports.py", function="generate_morning_report", type="daily", time="09:00"),
    dict(name="random_check", file="health_check.py", function="random_health_check", type="random_daily", after_time="14:00", before_time="18:00"),
    dict(name="google_drive_backup", file="google_drive_backup.py", function="backup_to_drive", type="interval", interval_minutes=120, tags=["storage"], retries=3),
    dict(name="llm_processor", file="llm_tasks.py", function="process_llm_queue", type="trigger", tags=["gpu"]),
    dict(name="idle_baseline", file="idle_task.py", function="run_idle", type="idle", priority=-1),
]

LOCK = threading.Lock()
CONN = sqlite3.connect(STATE_DB, check_same_thread=False)
CONN.row_factory = sqlite3.Row
EXECUTOR = ThreadPoolExecutor(max_workers=10)
STOP_EVENT = threading.Event()


def db_execute(sql, params=(), fetch=None):
    with LOCK:
        cursor = CONN.execute(sql, params)
        CONN.commit()
        if fetch == "one":
            return cursor.fetchone()
        if fetch == "all":
            return cursor.fetchall()
        return None


def log(level, message):
    timestamp = time.time()
    db_execute(
        "INSERT INTO logs (timestamp, level, message, device) VALUES (?, ?, ?, ?)",
        (timestamp, level, message, DEVICE_ID)
    )
    now = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    print(f"{now} [{level}] {message}")


def update_job(job_name, status):
    db_execute(
        (
            "INSERT INTO jobs (job_name, status, device, last_update) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(job_name) DO UPDATE SET status=excluded.status, device=excluded.device, last_update=excluded.last_update"
        ),
        (job_name, status, DEVICE_ID, time.time())
    )


def add_trigger(job_name, args=None, kwargs=None):
    db_execute(
        "INSERT INTO triggers (job_name, args, kwargs, created) VALUES (?, ?, ?, ?)",
        (job_name, json.dumps(args or []), json.dumps(kwargs or {}), time.time())
    )


def get_config(key):
    """Get a config value from the database"""
    result = db_execute("SELECT value FROM config WHERE key = ?", (key,), fetch="one")
    return result["value"] if result else None


def set_config(key, value):
    """Set a config value in the database"""
    db_execute(
        "INSERT OR REPLACE INTO config (key, value, updated) VALUES (?, ?, ?)",
        (key, value, time.time())
    )


def init_db():
    with CONN:
        CONN.executescript(SCHEMA)
    if db_execute("SELECT 1 FROM scheduled_jobs LIMIT 1", fetch="one"):
        return
    for job in DEFAULT_JOBS:
        db_execute(
            (
                "INSERT OR IGNORE INTO scheduled_jobs "
                "(name, file, function, type, tags, retries, time, after_time, before_time, interval_minutes, priority, enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)"
            ),
            (
                job["name"],
                job["file"],
                job["function"],
                job["type"],
                json.dumps(job.get("tags", [])),
                job.get("retries", 3),
                job.get("time"),
                job.get("after_time"),
                job.get("before_time"),
                job.get("interval_minutes"),
                job.get("priority", 0),
            )
        )
    log("INFO", "Populated default scheduled jobs")


def _minutes(value):
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def job_due(job, now_minutes, now_ts, today, non_idle_running):
    job_type = job["type"]
    if job_type == "trigger" or (job["tags"] and not job["tag_set"].issubset(DEVICE_TAGS)):
        return False
    status = job.get("status", "")
    if status == "running":
        return False
    if job_type == "always":
        return True
    if job_type == "idle":
        return not non_idle_running

    last_run = job.get("last_update")
    ran_today = bool(last_run) and datetime.datetime.fromtimestamp(last_run).date() == today
    if job_type == "daily":
        target = job.get("time")
        return bool(target) and now_minutes >= _minutes(target) and not ran_today
    if job_type == "random_daily":
        if ran_today:
            return False
        start = _minutes(job.get("after_time", "00:00"))
        end = _minutes(job.get("before_time", "23:59"))
        return start <= now_minutes <= end and random.random() < 0.01
    if job_type == "interval":
        interval = job.get("interval_minutes")
        return bool(interval) and (not last_run or (now_ts - last_run) / 60 >= interval)
    return False


def load_and_call_function(file_path, function_name, *args, **kwargs):
    script_path = PROGRAMS_DIR / file_path
    if not script_path.exists():
        script_path.write_text(
            f"\ndef {function_name}(*args, **kwargs):\n    print(\"{function_name} called\")\n    return \"{function_name} completed\"\n"
        )

    spec = importlib.util.spec_from_file_location("module", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    func = getattr(module, function_name, None)
    return func(*args, **kwargs) if func else None


def execute_job(job, args, kwargs):
    name = job["name"]
    retries = job.get("retries", 3)
    log("INFO", f"Starting job: {name}")
    for attempt in range(retries):
        update_job(name, "running")
        try:
            result = load_and_call_function(job["file"], job["function"], *args, **kwargs)
        except Exception as exc:
            log("ERROR", f"Job {name} failed: {exc}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
        else:
            log("INFO", f"Job {name} completed with result: {result}")
            update_job(name, "completed")
            return
    update_job(name, "failed")


def start_job(job, *args, **kwargs):
    update_job(job["name"], "running")
    EXECUTOR.submit(execute_job, job, args, kwargs)


def run():
    log("INFO", f"Orchestrator started on device {DEVICE_ID} with tags {sorted(DEVICE_TAGS)}")
    while not STOP_EVENT.is_set():
        try:
            rows = db_execute(
                "SELECT s.*, j.status, j.last_update FROM scheduled_jobs s "
                "LEFT JOIN jobs j ON s.name = j.job_name WHERE s.enabled = 1",
                fetch="all"
            ) or []
            jobs = [
                {
                    **dict(row),
                    "tags": tags,
                    "tag_set": set(tags),
                    "status": row["status"] or "",
                    "last_update": row["last_update"],
                }
                for row in rows
                for tags in [json.loads(row["tags"]) if row["tags"] else []]
            ]
            non_idle_running = any(
                job["status"] == "running" and job["type"] != "idle" for job in jobs
            )
            now = datetime.datetime.now()
            now_minutes = now.hour * 60 + now.minute
            today = now.date()
            now_ts = time.time()

            for job in jobs:
                if job_due(job, now_minutes, now_ts, today, non_idle_running):
                    start_job(job)

            jobs_by_name = {job["name"]: job for job in jobs}
            triggers = db_execute(
                "SELECT id, job_name, args, kwargs FROM triggers WHERE processed IS NULL",
                fetch="all"
            ) or []
            for trigger in triggers:
                job = jobs_by_name.get(trigger["job_name"])
                if not job or (job["tags"] and not job["tag_set"].issubset(DEVICE_TAGS)):
                    db_execute("UPDATE triggers SET processed = ? WHERE id = ?", (time.time(), trigger["id"]))
                    continue
                args = json.loads(trigger["args"])
                kwargs = json.loads(trigger["kwargs"])
                start_job(job, *args, **kwargs)
                db_execute("UPDATE triggers SET processed = ? WHERE id = ?", (time.time(), trigger["id"]))
        except Exception as exc:
            log("ERROR", f"Scheduler error: {exc}")
        time.sleep(1)


def stop():
    STOP_EVENT.set()
    EXECUTOR.shutdown(wait=True)


def main():
    try:
        run()
    except KeyboardInterrupt:
        log("INFO", "Shutting down orchestrator")
        stop()


init_db()

# Check Google Drive authentication at startup
# Disabled for now to prevent blocking
# try:
#     from Programs.google_drive_backup import init_check
#     init_check()
# except Exception as e:
#     print(f"Google Drive backup initialization skipped: {e}")

if __name__ == "__main__":
    main()
