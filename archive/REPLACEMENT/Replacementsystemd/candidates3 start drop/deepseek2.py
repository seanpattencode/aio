#!/usr/bin/env python3
"""
AIOS Systemd Manager - Synthesized Production Version
Combines best practices from Android, Kubernetes, and large-scale deployments
Manages AI workflows with systemd integration, real-time scheduling, and zombie prevention
"""

import os
import sys
import sqlite3
import subprocess
import signal
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Systemd integration
try:
    from systemd import daemon, journal
    logging.root.addHandler(journal.JournalHandler(SYSLOG_IDENTIFIER='aios'))
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIOSSystemdManager:
    def __init__(self, db_path: str = "/var/lib/aios/aios.db"):
        self.db_path = db_path
        self.running = True
        self.processes: Dict[int, int] = {}  # pid -> workflow_id
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGCHLD, self._reap_children)
        
        # Initialize database
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database with required tables"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    schedule TEXT,
                    priority INTEGER DEFAULT 0,
                    state TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY,
                    workflow_id INTEGER,
                    pid INTEGER,
                    start_time DATETIME,
                    end_time DATETIME,
                    exit_code INTEGER,
                    FOREIGN KEY (workflow_id) REFERENCES workflows (id)
                );
            """)
    
    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, initiating shutdown")
        self.running = False
        daemon.notify('STOPPING=1') if 'daemon' in globals() else None
    
    def _reap_children(self, signum, frame):
        """Reap completed child processes to prevent zombies (Android pattern)"""
        try:
            while True:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                if pid in self.processes:
                    workflow_id = self.processes[pid]
                    exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
                    self._update_execution(workflow_id, pid, exit_code)
                    del self.processes[pid]
                    logger.info(f"Workflow {workflow_id} completed with exit code {exit_code}")
        except ChildProcessError:
            pass
    
    def _update_execution(self, workflow_id: int, pid: int, exit_code: int):
        """Update execution record in database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE executions SET end_time=CURRENT_TIMESTAMP, exit_code=? WHERE pid=?",
                (exit_code, pid)
            )
            conn.execute(
                "UPDATE workflows SET state='completed' WHERE id=?",
                (workflow_id,)
            )
    
    def submit_workflow(self, name: str, command: str, schedule: Optional[str] = None, 
                       priority: int = 0) -> int:
        """Submit a new workflow for review"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO workflows (name, command, schedule, priority) VALUES (?, ?, ?, ?) RETURNING id",
                (name, command, schedule, priority)
            )
            workflow_id = cursor.fetchone()[0]
            logger.info(f"Submitted workflow {workflow_id}: {name}")
            return workflow_id
    
    def review_workflow(self, workflow_id: int, approve: bool):
        """Review and approve/reject a workflow"""
        state = "approved" if approve else "rejected"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE workflows SET state=? WHERE id=?",
                (state, workflow_id)
            )
        logger.info(f"Workflow {workflow_id} {state}")
    
    def _set_realtime_priority(self, pid: int, priority: int):
        """Set real-time scheduling priority for process (Android/Kubernetes pattern)"""
        try:
            subprocess.run([
                'systemctl', 'set-property', 
                f'{pid}', 
                f'CPUSchedulingPolicy=rr',
                f'CPUSchedulingPriority={priority}'
            ], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(f"Could not set real-time priority for PID {pid}")
    
    def execute_workflow(self, workflow_id: int):
        """Execute a workflow using systemd-run for proper supervision"""
        with sqlite3.connect(self.db_path) as conn:
            workflow = conn.execute(
                "SELECT name, command, priority FROM workflows WHERE id=?", 
                (workflow_id,)
            ).fetchone()
        
        if not workflow:
            logger.error(f"Workflow {workflow_id} not found")
            return
        
        name, command, priority = workflow
        
        try:
            # Use systemd-run for proper process supervision and resource control
            proc = subprocess.Popen([
                'systemd-run', '--user', '--scope', '--same-dir',
                '--property=CPUWeight=100',
                '--property=MemoryMax=500M',
                '/bin/sh', '-c', command
            ], start_new_session=True)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO executions (workflow_id, pid, start_time) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (workflow_id, proc.pid)
                )
                conn.execute(
                    "UPDATE workflows SET state='running' WHERE id=?",
                    (workflow_id,)
                )
            
            self.processes[proc.pid] = workflow_id
            
            # Set real-time priority if specified
            if priority > 0:
                self._set_realtime_priority(proc.pid, priority)
            
            logger.info(f"Started workflow {workflow_id} with PID {proc.pid}")
            
        except Exception as e:
            logger.error(f"Error executing workflow {workflow_id}: {str(e)}")
    
    def run_scheduler(self):
        """Main scheduler loop that processes approved workflows"""
        if 'daemon' in globals():
            daemon.notify('READY=1')
        
        logger.info("AIOS Systemd Manager started")
        
        while self.running:
            try:
                # Get approved workflows
                with sqlite3.connect(self.db_path) as conn:
                    workflows = conn.execute(
                        "SELECT id, schedule FROM workflows WHERE state='approved'"
                    ).fetchall()
                
                # Execute workflows based on schedule
                for workflow_id, schedule in workflows:
                    if self._should_execute(schedule):
                        self.execute_workflow(workflow_id)
                
                # Update systemd watchdog
                if 'daemon' in globals():
                    daemon.notify('WATCHDOG=1')
                
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Scheduler error: {str(e)}")
                time.sleep(30)
        
        # Clean shutdown
        for pid in list(self.processes.keys()):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        
        logger.info("AIOS Systemd Manager stopped")
    
    def _should_execute(self, schedule: Optional[str]) -> bool:
        """Determine if a workflow should execute based on its schedule"""
        if not schedule:
            return True  # Immediate execution
        
        # Implement simple scheduling logic
        # In production, this would parse systemd-style calendar events
        return True

def main():
    """Command-line interface for AIOS management"""
    manager = AIOSSystemdManager()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "submit" and len(sys.argv) >= 4:
            name = sys.argv[2]
            cmd = sys.argv[3]
            schedule = sys.argv[4] if len(sys.argv) > 4 else None
            priority = int(sys.argv[5]) if len(sys.argv) > 5 else 0
            manager.submit_workflow(name, cmd, schedule, priority)
        
        elif command == "review" and len(sys.argv) >= 4:
            workflow_id = int(sys.argv[2])
            action = sys.argv[3].lower()
            manager.review_workflow(workflow_id, action == "approve")
        
        elif command == "start":
            manager.run_scheduler()
        
        else:
            print("Usage: aios [submit|review|start]")
    else:
        manager.run_scheduler()

if __name__ == "__main__":
    main()