#!/usr/bin/env python3
import sqlite3
import signal
import subprocess
import os
import time
import sys
import sdnotify

# --- Constants ---
DB_PATH = "aios.db"
SHUTDOWN_TIMEOUT = 10  # Seconds to wait for children to terminate

class AIOSManager:
    """
    Manages AI-generated workflows and programs as child processes,
    interfacing with systemd for robust service lifecycle management.
    """
    def __init__(self):
        self.running = True
        self.children =
        self.db_conn = None
        self.notifier = sdnotify.SystemdNotifier()

        # Set up graceful shutdown handlers
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)

    def _log(self, message):
        """Simple logger that prints to stderr for systemd journal capture."""
        print(f"AIOSManager: {message}", file=sys.stderr)

    def setup(self):
        """Initializes database and notifies systemd of progress."""
        self._log("Initializing...")
        self.notifier.notify("STATUS=Initializing database...")

        try:
            # Connect to SQLite DB. WAL mode is crucial for concurrency.
            self.db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            self.db_conn.execute("PRAGMA journal_mode=WAL;")
            self._create_schema()
            self._log("Database connection established.")
        except sqlite3.Error as e:
            self._log(f"Database initialization failed: {e}")
            self.notifier.notify(f"STATUS=DB Error: {e}")
            sys.exit(1)

    def _create_schema(self):
        """Ensures the necessary database tables exist."""
        cursor = self.db_conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                script_path TEXT NOT NULL,
                pid INTEGER,
                status TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        """)
        self.db_conn.commit()

    def run(self):
        """Main service loop."""
        self.setup()

        # Signal to systemd that we are fully initialized and ready.
        self._log("Startup complete. Notifying systemd.")
        self.notifier.notify("READY=1")

        # Example: Spawn a dummy workflow for demonstration
        self.spawn_workflow(1, "/usr/bin/sleep", ["3600"])

        while self.running:
            self.notifier.notify("STATUS=Monitoring workflows...")
            self._monitor_children()

            # In a real application, this loop would also check for new
            # projects to run from the database or an IPC queue.
            time.sleep(5)

        self._log("Main loop exited.")

    def spawn_workflow(self, workflow_id, command, args):
        """Launches and tracks a new workflow as a child process."""
        try:
            self._log(f"Spawning workflow {workflow_id}: {command} {' '.join(args)}")
            # Using Popen to run the child process non-blockingly
            process = subprocess.Popen([command] + args)
            self.children.append(process)

            # Update database with PID
            cursor = self.db_conn.cursor()
            cursor.execute(
                "UPDATE workflows SET pid =?, status = 'running' WHERE id =?",
                (process.pid, workflow_id)
            )
            self.db_conn.commit()
            self._log(f"Workflow {workflow_id} started with PID {process.pid}.")

        except (OSError, FileNotFoundError) as e:
            self._log(f"Failed to spawn workflow {workflow_id}: {e}")
            self.notifier.notify(f"STATUS=Spawn Error: {e}")

    def _monitor_children(self):
        """
        Checks for terminated child processes and reaps them.
        This prevents zombie processes at the application level.
        """
        reaped_pids =
        for i in reversed(range(len(self.children))):
            child = self.children[i]
            if child.poll() is not None:  # poll() returns exit code or None if running
                self._log(f"Child process {child.pid} terminated with code {child.returncode}.")
                reaped_pids.append(child.pid)
                del self.children[i]

        if reaped_pids:
            # Update database for reaped processes
            cursor = self.db_conn.cursor()
            placeholders = ','.join('?' for _ in reaped_pids)
            query = f"UPDATE workflows SET status = 'terminated' WHERE pid IN ({placeholders})"
            cursor.execute(query, reaped_pids)
            self.db_conn.commit()

    def shutdown_handler(self, signum, frame):
        """Handles SIGTERM/SIGINT for graceful shutdown."""
        self._log(f"Received signal {signum}. Initiating graceful shutdown.")
        self.notifier.notify("STOPPING=1\nSTATUS=Graceful shutdown initiated...")
        self.running = False

    def cleanup(self):
        """Performs final cleanup before exiting."""
        self._log("Terminating all child processes...")
        for child in self.children:
            if child.poll() is None:
                child.terminate() # Send SIGTERM

        # Wait for children to exit
        start_time = time.time()
        while any(child.poll() is None for child in self.children):
            if time.time() - start_time > SHUTDOWN_TIMEOUT:
                self._log("Timeout reached. Forcing termination of remaining children.")
                for child in self.children:
                    if child.poll() is None:
                        child.kill() # Send SIGKILL
                break
            time.sleep(0.1)

        self._log("All child processes terminated.")
        if self.db_conn:
            self.db_conn.close()
            self._log("Database connection closed.")
        self._log("Cleanup complete. Exiting.")

if __name__ == "__main__":
    manager = AIOSManager()
    try:
        manager.run()
    finally:
        manager.cleanup()