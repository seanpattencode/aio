#!/usr/bin/env python3
"""
AIOS Job Management Utility
Comprehensive tool for managing, monitoring, and debugging the AIOS orchestrator.

This utility provides all management functionality for the AIOS system from the host,
while the orchestrator runs safely isolated in Docker.
"""
import sqlite3
import json
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "orchestrator.db"

def list_jobs():
    """List all scheduled jobs with their configuration"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM scheduled_jobs ORDER BY name")

    print("\nScheduled Jobs:")
    print("-" * 80)
    for row in cursor:
        tags = json.loads(row["tags"]) if row["tags"] else []
        print(f"Name: {row['name']}")
        print(f"  Type: {row['type']}")
        print(f"  File: {row['file']}")
        print(f"  Function: {row['function']}")
        print(f"  Enabled: {'Yes' if row['enabled'] else 'No'}")
        if tags:
            print(f"  Tags: {', '.join(tags)}")
        if row["time"]:
            print(f"  Time: {row['time']}")
        if row["interval_minutes"]:
            print(f"  Interval: {row['interval_minutes']} minutes")
        if row["retries"]:
            print(f"  Retries: {row['retries']}")
        print()
    conn.close()

def enable_job(job_name):
    """Enable a scheduled job"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE scheduled_jobs SET enabled = 1 WHERE name = ?", (job_name,))
    conn.commit()
    conn.close()
    print(f"Job '{job_name}' enabled")

def disable_job(job_name):
    """Disable a scheduled job"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE scheduled_jobs SET enabled = 0 WHERE name = ?", (job_name,))
    conn.commit()
    conn.close()
    print(f"Job '{job_name}' disabled")

def add_job(name, file, function, job_type, **kwargs):
    """Add a new scheduled job"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO scheduled_jobs
            (name, file, function, type, tags, retries, time, after_time, before_time, interval_minutes, priority, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            file,
            function,
            job_type,
            json.dumps(kwargs.get("tags", [])),
            kwargs.get("retries", 3),
            kwargs.get("time"),
            kwargs.get("after_time"),
            kwargs.get("before_time"),
            kwargs.get("interval_minutes"),
            kwargs.get("priority", 0),
            1
        ))
        conn.commit()
        print(f"Job '{name}' added successfully")
    except sqlite3.IntegrityError:
        print(f"Job '{name}' already exists")
    finally:
        conn.close()

def remove_job(job_name):
    """Remove a scheduled job"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM scheduled_jobs WHERE name = ?", (job_name,))
    conn.commit()
    conn.close()
    print(f"Job '{job_name}' removed")

def trigger_job(job_name, *args, **kwargs):
    """Trigger a job for execution"""
    conn = sqlite3.connect(DB_PATH)

    # Check if job exists
    cursor = conn.execute("SELECT type FROM scheduled_jobs WHERE name = ?", (job_name,))
    job = cursor.fetchone()
    if not job:
        print(f"Error: Job '{job_name}' not found")
        conn.close()
        return

    job_type = job[0]

    # Handle different job types
    if 'trigger' in job_type:
        # Insert trigger for trigger-type jobs
        conn.execute(
            "INSERT INTO triggers (job_name, args, kwargs, created) VALUES (?, ?, ?, ?)",
            (job_name, json.dumps(list(args)), json.dumps(kwargs), time.time())
        )
        conn.commit()
        print(f"Trigger added for job '{job_name}'")
    elif 'interval' in job_type or 'daily' in job_type:
        # For interval/daily jobs, reset their last run to force execution
        conn.execute("DELETE FROM jobs WHERE job_name = ?", (job_name,))
        conn.commit()
        print(f"Force-triggered {job_type} job '{job_name}' by resetting its last run time")
        print("Note: The job will run on the next scheduler check (usually within 60 seconds)")
    else:
        print(f"Warning: Job '{job_name}' is type '{job_type}' and may not support manual triggering")
        # Try trigger anyway
        conn.execute(
            "INSERT INTO triggers (job_name, args, kwargs, created) VALUES (?, ?, ?, ?)",
            (job_name, json.dumps(list(args)), json.dumps(kwargs), time.time())
        )
        conn.commit()
        print(f"Trigger added anyway - job may or may not execute")

    if args or kwargs:
        print(f"  Args: {args}")
        print(f"  Kwargs: {kwargs}")

    conn.close()

def status():
    """Show current system status and job execution state"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("\n" + "=" * 80)
    print("AIOS System Status")
    print("=" * 80)

    # Check Docker container status
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=aios-orchestrator", "--format", "table {{.Status}}"],
            capture_output=True, text=True
        )
        if "Up" in result.stdout:
            print("✅ Docker Container: Running")
        else:
            print("❌ Docker Container: Not running")
    except:
        print("⚠️  Docker Container: Unable to check (is Docker installed?)")

    # Count jobs by status
    cursor = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM scheduled_jobs WHERE enabled = 1) as enabled,
            (SELECT COUNT(*) FROM scheduled_jobs WHERE enabled = 0) as disabled,
            (SELECT COUNT(*) FROM jobs WHERE status = 'running') as running,
            (SELECT COUNT(*) FROM jobs WHERE status = 'failed') as failed,
            (SELECT COUNT(*) FROM triggers WHERE processed IS NULL) as pending_triggers
    """)
    stats = cursor.fetchone()

    print(f"\n📊 Job Statistics:")
    print(f"  Enabled Jobs: {stats['enabled']}")
    print(f"  Disabled Jobs: {stats['disabled']}")
    print(f"  Currently Running: {stats['running']}")
    print(f"  Failed Jobs: {stats['failed']}")
    print(f"  Pending Triggers: {stats['pending_triggers']}")

    # Show recent job executions
    print(f"\n📋 Recent Job Executions (last 5):")
    cursor = conn.execute("""
        SELECT job_name, status, last_update
        FROM jobs
        ORDER BY last_update DESC
        LIMIT 5
    """)
    for row in cursor:
        timestamp = datetime.fromtimestamp(row['last_update']).strftime('%Y-%m-%d %H:%M:%S')
        status_icon = "✅" if row['status'] == 'completed' else "❌" if row['status'] == 'failed' else "🔄"
        print(f"  {status_icon} {row['job_name']}: {row['status']} at {timestamp}")

    conn.close()

def logs(job_name=None, limit=20, level=None, follow=False):
    """View system and job logs"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = "SELECT * FROM logs"
    params = []
    conditions = []

    if job_name:
        conditions.append("message LIKE ?")
        params.append(f"%{job_name}%")

    if level:
        conditions.append("level = ?")
        params.append(level.upper())

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    if follow:
        print(f"Following logs (press Ctrl+C to stop)...")
        last_id = 0
        try:
            while True:
                cursor = conn.execute(
                    query.replace("ORDER BY timestamp DESC", f"WHERE id > {last_id} ORDER BY timestamp ASC"),
                    params[:-1]  # Remove limit for follow mode
                )
                for row in cursor:
                    timestamp = datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    level_color = {
                        'ERROR': '\033[91m',
                        'WARNING': '\033[93m',
                        'INFO': '\033[92m',
                    }.get(row['level'], '')
                    reset_color = '\033[0m' if level_color else ''
                    print(f"{timestamp} {level_color}[{row['level']}]{reset_color} {row['message']}")
                    last_id = max(last_id, row['id'])
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped following logs")
    else:
        cursor = conn.execute(query, params)
        logs_list = list(cursor)

        # Print in chronological order (reverse the list)
        for row in reversed(logs_list):
            timestamp = datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{timestamp} [{row['level']}] {row['message']}")

    conn.close()

def db_info():
    """Show database information and statistics"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("\n" + "=" * 80)
    print("Database Information")
    print("=" * 80)

    # Database file info
    db_stat = DB_PATH.stat()
    print(f"\n📁 Database File:")
    print(f"  Path: {DB_PATH}")
    print(f"  Size: {db_stat.st_size / 1024:.2f} KB")
    print(f"  Modified: {datetime.fromtimestamp(db_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")

    # Table information
    print(f"\n📊 Tables:")
    cursor = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    for row in cursor:
        # Count rows in each table
        count_cursor = conn.execute(f"SELECT COUNT(*) as count FROM {row['name']}")
        count = count_cursor.fetchone()['count']
        print(f"  {row['name']}: {count} rows")

    # Database integrity
    cursor = conn.execute("PRAGMA integrity_check")
    integrity = cursor.fetchone()[0]
    print(f"\n🔍 Integrity Check: {integrity}")

    conn.close()

def check_job(job_name):
    """Check detailed information about a specific job"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get job configuration
    cursor = conn.execute("SELECT * FROM scheduled_jobs WHERE name = ?", (job_name,))
    job = cursor.fetchone()

    if not job:
        print(f"Job '{job_name}' not found")
        conn.close()
        return

    print(f"\n" + "=" * 80)
    print(f"Job Details: {job_name}")
    print("=" * 80)

    # Configuration
    print(f"\n📋 Configuration:")
    for key in job.keys():
        value = job[key]
        if key == 'tags' and value:
            value = ', '.join(json.loads(value))
        print(f"  {key}: {value}")

    # Execution status
    cursor = conn.execute("SELECT * FROM jobs WHERE job_name = ?", (job_name,))
    status = cursor.fetchone()
    if status:
        print(f"\n📊 Current Status:")
        print(f"  Status: {status['status']}")
        print(f"  Last Update: {datetime.fromtimestamp(status['last_update']).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Device: {status['device']}")

    # Recent logs
    print(f"\n📜 Recent Logs (last 10):")
    cursor = conn.execute(
        "SELECT * FROM logs WHERE message LIKE ? ORDER BY timestamp DESC LIMIT 10",
        (f"%{job_name}%",)
    )
    for row in cursor:
        timestamp = datetime.fromtimestamp(row['timestamp']).strftime('%H:%M:%S')
        print(f"  {timestamp} [{row['level']}] {row['message']}")

    # Recent triggers
    cursor = conn.execute(
        "SELECT * FROM triggers WHERE job_name = ? ORDER BY created DESC LIMIT 5",
        (job_name,)
    )
    triggers = list(cursor)
    if triggers:
        print(f"\n🔔 Recent Triggers:")
        for trigger in triggers:
            created = datetime.fromtimestamp(trigger['created']).strftime('%Y-%m-%d %H:%M:%S')
            processed = datetime.fromtimestamp(trigger['processed']).strftime('%H:%M:%S') if trigger['processed'] else 'Pending'
            print(f"  Created: {created}, Processed: {processed}")

    conn.close()

def reset_job(job_name):
    """Reset a job's execution state"""
    conn = sqlite3.connect(DB_PATH)

    # Delete job execution record
    conn.execute("DELETE FROM jobs WHERE job_name = ?", (job_name,))

    # Clear any pending triggers
    conn.execute("DELETE FROM triggers WHERE job_name = ? AND processed IS NULL", (job_name,))

    conn.commit()
    conn.close()

    print(f"Job '{job_name}' has been reset")
    print("  - Execution state cleared")
    print("  - Pending triggers removed")

def docker_logs(tail=50):
    """Show Docker container logs"""
    try:
        # Try to find docker-compose.yml
        docker_dir = Path(__file__).parent / "docker"
        if docker_dir.exists():
            result = subprocess.run(
                ["docker-compose", "logs", f"--tail={tail}"],
                cwd=docker_dir,
                capture_output=True,
                text=True
            )
        else:
            # Fallback to docker logs
            result = subprocess.run(
                ["docker", "logs", "aios-orchestrator", f"--tail={tail}"],
                capture_output=True,
                text=True
            )

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

    except FileNotFoundError:
        print("Error: Docker or docker-compose not found")
    except Exception as e:
        print(f"Error getting Docker logs: {e}")

def backup_db(output_path=None):
    """Create a backup of the database"""
    if not output_path:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f"orchestrator_backup_{timestamp}.db"

    import shutil
    shutil.copy2(DB_PATH, output_path)
    print(f"Database backed up to: {output_path}")

    # Show backup size
    backup_stat = Path(output_path).stat()
    print(f"Backup size: {backup_stat.st_size / 1024:.2f} KB")

def clean_restart():
    """Clean restart of Docker container, ensuring all child processes are terminated"""
    print("Performing clean restart of AIOS orchestrator...")

    # Check if we're in docker directory
    docker_dir = Path(__file__).parent / "docker"
    if not docker_dir.exists():
        print("Error: docker directory not found")
        return

    try:
        # Reset all running jobs in the database first
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE jobs SET status = 'idle' WHERE status IN ('running', 'pending')")
        conn.commit()
        print("✓ Reset job statuses in database")
        conn.close()

        # First, try to kill all python processes inside the container
        print("Killing all processes inside container...")
        try:
            subprocess.run(
                ["docker", "exec", "aios-orchestrator", "sh", "-c", "kill -9 -1 2>/dev/null || true"],
                capture_output=True,
                text=True,
                timeout=5
            )
        except:
            pass  # Container might not be running

        # Stop container completely with short timeout to force kill
        print("Stopping Docker container...")
        result = subprocess.run(
            ["docker-compose", "stop", "-t", "1"],
            cwd=docker_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Warning: {result.stderr}")
        else:
            print("✓ Container stopped")

        # Remove the container to ensure clean state
        print("Removing container...")
        result = subprocess.run(
            ["docker-compose", "rm", "-f"],
            cwd=docker_dir,
            capture_output=True,
            text=True
        )
        print("✓ Container removed")

        # Start fresh container
        print("Starting fresh container...")
        result = subprocess.run(
            ["docker-compose", "up", "-d"],
            cwd=docker_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Error starting container: {result.stderr}")
            return
        print("✓ Container started")

        # Wait a bit for orchestrator to initialize
        print("Waiting for orchestrator to initialize...")
        time.sleep(5)

        # Show recent logs to confirm startup
        print("\nRecent logs:")
        subprocess.run(
            ["docker-compose", "logs", "--tail=10"],
            cwd=docker_dir
        )

        print("\n✅ Clean restart complete!")
        print("The orchestrator and all jobs have been cleanly restarted.")

    except Exception as e:
        print(f"Error during clean restart: {e}")

def main():
    """Main entry point with enhanced command-line interface"""
    if len(sys.argv) < 2:
        print("AIOS Job Management Utility")
        print("=" * 60)
        print("\nJob Management Commands:")
        print("  list                      - List all scheduled jobs")
        print("  enable <job_name>         - Enable a job")
        print("  disable <job_name>        - Disable a job")
        print("  remove <job_name>         - Remove a job")
        print("  add <name> <file> <function> <type> [options]")
        print("                           - Add a new job")
        print("  trigger <job_name> [key=value...]")
        print("                           - Trigger a job")
        print("  reset <job_name>         - Reset job state")
        print("\nMonitoring Commands:")
        print("  status                   - Show system status")
        print("  logs [options]           - View logs")
        print("    --job <name>          - Filter by job name")
        print("    --level <level>       - Filter by log level")
        print("    --limit <n>           - Number of logs (default: 20)")
        print("    --follow              - Follow logs in real-time")
        print("  check <job_name>        - Check specific job details")
        print("  docker-logs [n]         - Show Docker container logs")
        print("\nDatabase Commands:")
        print("  db-info                 - Show database information")
        print("  backup [path]           - Backup database")
        print("\nSystem Commands:")
        print("  clean-restart           - Clean restart (kills all processes)")
        print("\nExamples:")
        print("  python3 manage_jobs.py status")
        print("  python3 manage_jobs.py trigger google_drive_backup")
        print("  python3 manage_jobs.py logs --job backup --limit 50")
        print("  python3 manage_jobs.py check llm_processor")
        return

    command = sys.argv[1]

    # Job management commands
    if command == "list":
        list_jobs()
    elif command == "enable" and len(sys.argv) >= 3:
        enable_job(sys.argv[2])
    elif command == "disable" and len(sys.argv) >= 3:
        disable_job(sys.argv[2])
    elif command == "remove" and len(sys.argv) >= 3:
        remove_job(sys.argv[2])
    elif command == "trigger" and len(sys.argv) >= 3:
        job_name = sys.argv[2]
        # Parse key=value arguments
        kwargs = {}
        for arg in sys.argv[3:]:
            if '=' in arg:
                key, value = arg.split('=', 1)
                kwargs[key] = value
        trigger_job(job_name, **kwargs)
    elif command == "add" and len(sys.argv) >= 5:
        # Basic add functionality
        add_job(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif command == "reset" and len(sys.argv) >= 3:
        reset_job(sys.argv[2])

    # Monitoring commands
    elif command == "status":
        status()
    elif command == "logs":
        # Parse log options
        job_name = None
        limit = 20
        level = None
        follow = False

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--job" and i + 1 < len(sys.argv):
                job_name = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--level" and i + 1 < len(sys.argv):
                level = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--follow":
                follow = True
                i += 1
            else:
                i += 1

        logs(job_name, limit, level, follow)
    elif command == "check" and len(sys.argv) >= 3:
        check_job(sys.argv[2])
    elif command == "docker-logs":
        tail = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        docker_logs(tail)

    # Database commands
    elif command == "db-info":
        db_info()
    elif command == "backup":
        output_path = sys.argv[2] if len(sys.argv) > 2 else None
        backup_db(output_path)

    # System commands
    elif command == "clean-restart":
        clean_restart()

    else:
        print(f"Unknown command: {command}")
        print("Run without arguments to see usage")

if __name__ == "__main__":
    main()