import sqlite3
import json
from pathlib import Path

class SQLiteTaskQueue:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.create_table()

    def create_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                command TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at REAL NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    def add_task(self, name, command):
        self.cursor.execute("INSERT INTO tasks (name, command) VALUES (?, ?)", (name, command))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_task(self, task_id):
        self.cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self.cursor.fetchone()

    def update_task_status(self, task_id, status):
        self.cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        self.conn.commit()

    def get_pending_tasks(self):
        self.cursor.execute("SELECT * FROM tasks WHERE status = 'pending'")
        return self.cursor.fetchall()

    def close(self):
        self.conn.close()

class AIOSOrchestrator(SystemdOrchestrator):
    def __init__(self, db_path):
        super().__init__()
        self.task_queue = SQLiteTaskQueue(db_path)

    def add_job(self, name, command):
        task_id = self.task_queue.add_task(name, command)
        super().add_job(name, command)
        return task_id

    def start_job(self, name):
        task = self.task_queue.get_task_by_name(name)
        if task:
            super().start_job(name)
            self.task_queue.update_task_status(task[0], 'running')

    def stop_job(self, name):
        task = self.task_queue.get_task_by_name(name)
        if task:
            super().stop_job(name)
            self.task_queue.update_task_status(task[0], 'stopped')

    def get_task_status(self, task_id):
        task = self.task_queue.get_task(task_id)
        if task:
            return task[3]
        return None

def main():
    db_path = "aios.db"
    orch = AIOSOrchestrator(db_path)

    # Add jobs if they don't exist
    if "heartbeat" not in orch.jobs:
        orch.add_job("heartbeat", "while true; do echo Heartbeat; sleep 5; done")
        orch.start_job("heartbeat")

    # Handle commands
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "start":
            for name in orch.jobs:
                ms = orch.start_job(name)
                print(f"Started {name} in {ms:.2f}ms")
        elif cmd == "stop":
            for name in orch.jobs:
                ms = orch.stop_job(name)
                print(f"Stopped {name} in {ms:.2f}ms")
        elif cmd == "status":
            print(json.dumps(orch.status(), indent=2))
        elif cmd == "task_status":
            task_id = int(sys.argv[2])
            status = orch.get_task_status(task_id)
            print(f"Task {task_id} status: {status}")
    else:
        # Just show status
        status = orch.status()
        print(f"=== Systemd Orchestrator ===")
        print(f"Jobs: {len(status)}")
        for name, info in status.items():
            print(f"  {name}: {info['state']} (PID: {info['pid']})")

if __name__ == "__main__":
    main()