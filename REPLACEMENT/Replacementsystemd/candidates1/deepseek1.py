#!/usr/bin/env python3
import os
import time
import signal
import subprocess
import sqlite3
from systemd import daemon
from systemd import journal
from datetime import datetime
import select
import ctypes
import ctypes.util

# Real-time priority setup
libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)

class sched_param(ctypes.Structure):
    _fields_ = [('sched_priority', ctypes.c_int)]

def set_realtime_priority(priority=80):
    param = sched_param()
    param.sched_priority = priority
    if libc.sched_setscheduler(0, 1, param) < 0:  # 1 = SCHED_FIFO
        errno = ctypes.get_errno()
        journal.send(f"Failed to set realtime priority: {os.strerror(errno)}")

class AIOSManager:
    def __init__(self, db_path='/etc/aios/aios.db'):
        self.db_path = db_path
        self.running = True
        self.watchdog_interval = 5
        self.processes = {}
        
        # Systemd integration
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)
        
    def handle_signal(self, signum, frame):
        journal.send("Shutdown signal received")
        self.running = False
        
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    schedule TEXT,
                    priority INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
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
            ''')
            
    def get_pending_workflows(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, name, command, priority FROM workflows 
                WHERE enabled = 1 AND schedule <= datetime('now')
            ''')
            return cursor.fetchall()
            
    def execute_workflow(self, workflow_id, command, priority):
        try:
            # Set real-time priority for child process
            env = os.environ.copy()
            env['AIOS_PRIORITY'] = str(priority)
            
            proc = subprocess.Popen(
                command,
                shell=True,
                start_new_session=True,  # Prevent zombie processes
                env=env,
                preexec_fn=lambda: set_realtime_priority(priority)
            )
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'INSERT INTO executions (workflow_id, pid, start_time) VALUES (?, ?, ?)',
                    (workflow_id, proc.pid, datetime.now())
                )
                
            self.processes[proc.pid] = workflow_id
            journal.send(f"Started workflow {workflow_id} with PID {proc.pid}")
            
        except Exception as e:
            journal.send(f"Error executing workflow {workflow_id}: {str(e)}", PRIORITY=journal.LOG_ERR)
            
    def monitor_processes(self):
        for pid, workflow_id in list(self.processes.items()):
            try:
                _, status = os.waitpid(pid, os.WNOHANG)
                if os.WIFEXITED(status):
                    exit_code = os.WEXITSTATUS(status)
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute(
                            'UPDATE executions SET end_time=?, exit_code=? WHERE pid=?',
                            (datetime.now(), exit_code, pid)
                        )
                    del self.processes[pid]
                    journal.send(f"Workflow {workflow_id} completed with exit code {exit_code}")
            except ChildProcessError:
                del self.processes[pid]
                
    def run(self):
        # Initialize systemd integration
        daemon.notify('READY=1')
        journal.send("AIOS Manager started successfully")
        
        set_realtime_priority(90)  # Higher priority for manager
        
        # Main loop
        while self.running:
            try:
                # Update watchdog
                daemon.notify('WATCHDOG=1')
                
                # Check for new workflows
                workflows = self.get_pending_workflows()
                for wf_id, name, cmd, priority in workflows:
                    self.execute_workflow(wf_id, cmd, priority)
                
                # Monitor running processes
                self.monitor_processes()
                
                # Sleep with watchdog timing
                time.sleep(self.watchdog_interval)
                
            except Exception as e:
                journal.send(f"Main loop error: {str(e)}", PRIORITY=journal.LOG_ERR)
                time.sleep(self.watchdog_interval)
                
        # Clean shutdown
        for pid in list(self.processes.keys()):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        daemon.notify('STOPPING=1')

if __name__ == '__main__':
    manager = AIOSManager()
    manager.init_db()
    manager.run()