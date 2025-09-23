#!/usr/bin/env python3
"""
AIOS Ultimate - Synthesized from production patterns across 500M+ devices
Combines: Android zombie reaping, transient systemd units, WAL SQLite, journal logging
"""
import os
import sys
import sqlite3
import subprocess
import signal
import time
import json
from pathlib import Path
from typing import Dict, Optional, Any
from enum import Enum

# Optional systemd integration
try:
    from systemd import journal
    HAS_JOURNAL = True
except ImportError:
    HAS_JOURNAL = False

class TaskState(Enum):
    PENDING = "pending"
    APPROVED = "approved"  
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class AIOS:
    def __init__(self, db_path: str = "~/.aios/state.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.running = True
        self.children: Dict[int, str] = {}
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGCHLD, self._reap_children)
        
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite with production settings (WAL mode for concurrency)"""
        self.conn = sqlite3.connect(str(self.db_path), isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Production SQLite configuration (from Gemini patterns)
        self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA busy_timeout=5000;
            PRAGMA temp_store=MEMORY;
            
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                command TEXT NOT NULL,
                state TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 5,
                realtime BOOLEAN DEFAULT 0,
                memory_limit_mb INTEGER,
                cpu_weight INTEGER DEFAULT 100,
                restart_policy TEXT DEFAULT 'on-failure',
                unit_name TEXT,
                pid INTEGER,
                exit_code INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_state_priority 
            ON tasks(state, priority DESC, created_at);
        """)
        
    def _log(self, message: str, level: str = "INFO"):
        """Log to systemd journal if available, otherwise stderr"""
        if HAS_JOURNAL:
            journal.send(message, SYSLOG_IDENTIFIER="aios", PRIORITY=level)
        print(f"[{level}] {message}", file=sys.stderr)
        
    def _reap_children(self, signum=None, frame=None):
        """Android-style zombie reaping - always reap first"""
        try:
            while True:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                    
                # Update database for reaped process
                exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
                task_id = self.children.get(pid)
                
                if task_id:
                    state = TaskState.COMPLETED if exit_code == 0 else TaskState.FAILED
                    self.conn.execute(
                        """UPDATE tasks SET state=?, exit_code=?, pid=NULL, 
                           completed_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (state.value, exit_code, task_id)
                    )
                    del self.children[pid]
                    self._log(f"Task {task_id} (PID {pid}) completed with code {exit_code}")
                    
        except ChildProcessError:
            pass  # No more children to reap
            
    def submit_task(self, name: str, command: str, **kwargs) -> Optional[int]:
        """Submit a new task for review/execution"""
        try:
            cursor = self.conn.execute(
                """INSERT INTO tasks (name, command, priority, realtime, 
                   memory_limit_mb, cpu_weight, restart_policy, state)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, command, 
                 kwargs.get('priority', 5),
                 kwargs.get('realtime', False),
                 kwargs.get('memory_limit_mb'),
                 kwargs.get('cpu_weight', 100),
                 kwargs.get('restart_policy', 'on-failure'),
                 TaskState.APPROVED.value if kwargs.get('auto_approve') else TaskState.PENDING.value)
            )
            task_id = cursor.lastrowid
            self._log(f"Submitted task '{name}' (ID: {task_id})")
            return task_id
        except sqlite3.IntegrityError:
            self._log(f"Task '{name}' already exists", "ERROR")
            return None
            
    def approve_task(self, task_id: int) -> bool:
        """Approve a pending task for execution"""
        cursor = self.conn.execute(
            "UPDATE tasks SET state=? WHERE id=? AND state=?",
            (TaskState.APPROVED.value, task_id, TaskState.PENDING.value)
        )
        if cursor.rowcount > 0:
            self._log(f"Task {task_id} approved")
            return True
        return False
        
    def _execute_transient(self, task: sqlite3.Row) -> bool:
        """Execute task as transient systemd unit (best pattern from research)"""
        unit_name = f"aios-task-{task['id']}.service"
        
        # Build systemd-run command (from Kimi/ChatGPT patterns)
        cmd = ["systemd-run", "--user", "--collect", "--quiet",
               "--unit", unit_name,
               "--property=StandardOutput=journal",
               "--property=StandardError=journal",
               f"--property=MemoryMax={task['memory_limit_mb']}M" if task['memory_limit_mb'] else "",
               f"--property=CPUWeight={task['cpu_weight']}",
               f"--property=Restart={task['restart_policy']}"]
        
        # Add realtime scheduling if requested
        if task['realtime']:
            cmd.extend(["--property=CPUSchedulingPolicy=rr",
                       "--property=CPUSchedulingPriority=90"])
                       
        # Filter empty properties and add command
        cmd = [c for c in cmd if c]
        cmd.extend(["--", "/bin/sh", "-c", task['command']])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.conn.execute(
                    "UPDATE tasks SET state=?, unit_name=? WHERE id=?",
                    (TaskState.RUNNING.value, unit_name, task['id'])
                )
                self._log(f"Started task {task['id']} as {unit_name}")
                return True
        except Exception as e:
            self._log(f"Failed to start task {task['id']}: {e}", "ERROR")
            
        return False
        
    def _execute_direct(self, task: sqlite3.Row) -> bool:
        """Direct fork/exec execution (fallback when systemd unavailable)"""
        try:
            # Update state to running
            self.conn.execute(
                "UPDATE tasks SET state=? WHERE id=?",
                (TaskState.RUNNING.value, task['id'])
            )
            
            # Fork and exec (from Copilot/DeepSeek patterns)
            pid = os.fork()
            
            if pid == 0:  # Child process
                try:
                    # Set realtime priority if requested
                    if task['realtime']:
                        try:
                            os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(90))
                        except PermissionError:
                            pass
                            
                    # Execute command
                    os.execvp("/bin/sh", ["/bin/sh", "-c", task['command']])
                except Exception:
                    os._exit(1)
            else:  # Parent process
                self.children[pid] = task['id']
                self.conn.execute(
                    "UPDATE tasks SET pid=? WHERE id=?",
                    (pid, task['id'])
                )
                self._log(f"Started task {task['id']} with PID {pid}")
                return True
                
        except Exception as e:
            self._log(f"Failed to execute task {task['id']}: {e}", "ERROR")
            self.conn.execute(
                "UPDATE tasks SET state=? WHERE id=?",
                (TaskState.FAILED.value, task['id'])
            )
            return False
            
    def process_queue(self):
        """Process approved tasks using atomic queue operations"""
        # Atomic fetch and update (from GeminiWeb pattern)
        cursor = self.conn.execute("""
            UPDATE tasks SET state='running' WHERE id IN (
                SELECT id FROM tasks WHERE state='approved'
                ORDER BY priority DESC, created_at ASC LIMIT 1
            ) RETURNING *
        """)
        
        task = cursor.fetchone()
        if not task:
            return
            
        # Try transient systemd unit first, fallback to direct execution
        if not self._has_systemd() or not self._execute_transient(task):
            self._execute_direct(task)
            
    def monitor_systemd_tasks(self):
        """Monitor systemd-managed tasks"""
        cursor = self.conn.execute(
            "SELECT id, unit_name FROM tasks WHERE state='running' AND unit_name IS NOT NULL"
        )
        
        for row in cursor.fetchall():
            result = subprocess.run(
                ["systemctl", "--user", "show", row['unit_name'], "--property=ActiveState"],
                capture_output=True, text=True
            )
            
            if "inactive" in result.stdout or "failed" in result.stdout:
                state = TaskState.FAILED if "failed" in result.stdout else TaskState.COMPLETED
                self.conn.execute(
                    """UPDATE tasks SET state=?, completed_at=CURRENT_TIMESTAMP 
                       WHERE id=?""",
                    (state.value, row['id'])
                )
                self._log(f"Task {row['id']} {state.value}")
                
    def _has_systemd(self) -> bool:
        """Check if systemd --user is available"""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "status"],
                capture_output=True, timeout=1
            )
            return result.returncode != 127  # Command not found
        except:
            return False
            
    def get_status(self) -> Dict[str, Any]:
        """Get system status"""
        cursor = self.conn.execute(
            "SELECT state, COUNT(*) as count FROM tasks GROUP BY state"
        )
        
        status = {row['state']: row['count'] for row in cursor}
        status['children'] = len(self.children)
        status['systemd'] = self._has_systemd()
        return status
        
    def _shutdown(self, signum=None, frame=None):
        """Graceful shutdown"""
        self._log("Shutting down...")
        self.running = False
        
        # Stop all children
        for pid in list(self.children.keys()):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
                
        # Give them time to exit
        time.sleep(1)
        
        # Force kill remaining
        for pid in list(self.children.keys()):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
                
    def run(self):
        """Main event loop"""
        self._log("AIOS started")
        
        # Notify systemd if available
        if HAS_JOURNAL:
            try:
                subprocess.run(["systemd-notify", "--ready"], check=False)
            except:
                pass
                
        while self.running:
            # Always reap children first (Android pattern)
            self._reap_children()
            
            # Process task queue
            self.process_queue()
            
            # Monitor systemd tasks
            if self._has_systemd():
                self.monitor_systemd_tasks()
                
            # Brief sleep to prevent CPU spinning
            time.sleep(0.5)
            
        self._log("AIOS stopped")
        self.conn.close()

# CLI Interface
def main():
    if len(sys.argv) < 2:
        print("Usage: aios [run|submit|approve|status]")
        sys.exit(1)
        
    aios = AIOS()
    cmd = sys.argv[1]
    
    if cmd == "run":
        try:
            aios.run()
        except KeyboardInterrupt:
            pass
    elif cmd == "submit" and len(sys.argv) >= 4:
        task_id = aios.submit_task(sys.argv[2], sys.argv[3], auto_approve=True)
        print(f"Task ID: {task_id}")
    elif cmd == "approve" and len(sys.argv) >= 3:
        if aios.approve_task(int(sys.argv[2])):
            print("Task approved")
        else:
            print("Task not found or already processed")
    elif cmd == "status":
        print(json.dumps(aios.get_status(), indent=2))
    else:
        print("Invalid command")
        sys.exit(1)

if __name__ == "__main__":
    main()