#!/usr/bin/env python3
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

class SmartTodo:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.aios_dir.mkdir(exist_ok=True)
        self.tasks_file = self.aios_dir / "tasks.txt"
        self.status_file = self.aios_dir / "status.json"
        self.events_db = self.aios_dir / "events.db"
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.events_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY,
                source TEXT, target TEXT, type TEXT, data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_by TEXT
            )
        """)
        conn.close()

    def emit_event(self, target, event_type, data):
        conn = sqlite3.connect(self.events_db)
        conn.execute(
            "INSERT INTO events(source, target, type, data) VALUES (?, ?, ?, ?)",
            ("smart_todo", target, event_type, json.dumps(data))
        )
        conn.commit()
        conn.close()

    def load_tasks(self):
        if not self.tasks_file.exists():
            return []
        with open(self.tasks_file) as f:
            return [line.strip() for line in f if line.strip()]

    def save_tasks(self, tasks):
        with open(self.tasks_file, 'w') as f:
            f.write('\n'.join(tasks))
        self.update_status(tasks)

    def update_status(self, tasks):
        total = len(tasks)
        completed = sum(1 for t in tasks if t.startswith('[x]'))
        status = {"tasks_total": total, "tasks_completed": completed,
                  "last_update": datetime.now().isoformat()}
        with open(self.status_file, 'w') as f:
            json.dump(status, f, indent=2)

    def list_tasks(self):
        tasks = self.load_tasks()
        for i, task in enumerate(tasks, 1):
            print(f"{i}. {task}")

    def add_task(self, desc, priority='med'):
        tasks = self.load_tasks()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        task = f"[ ] {timestamp} p:{priority} {desc}"
        tasks.append(task)
        self.save_tasks(tasks)
        print(f"Added: {task}")

    def mark_done(self, task_id):
        tasks = self.load_tasks()
        if 0 < task_id <= len(tasks):
            tasks[task_id-1] = tasks[task_id-1].replace('[ ]', '[x]', 1)
            self.save_tasks(tasks)
            print(f"Completed task {task_id}")

    def skip_task(self, task_id):
        tasks = self.load_tasks()
        if 0 < task_id <= len(tasks):
            task = tasks[task_id-1]
            if 'p:crit' in task or 'p:high' in task:
                self.emit_event('daily_planner', 'need_replan',
                               {'skipped_task': task, 'reason': 'critical_skipped'})
                print("Critical task skipped - requesting replan")
            tasks[task_id-1] = task.replace('[ ]', '[!]', 1)
            self.save_tasks(tasks)

def main():
    parser = argparse.ArgumentParser(description='Smart Todo Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    subparsers.add_parser('list', help='List all tasks')

    add_parser = subparsers.add_parser('add', help='Add a task')
    add_parser.add_argument('description', help='Task description')
    add_parser.add_argument('-p', '--priority', choices=['low', 'med', 'high', 'crit'],
                           default='med', help='Priority level')

    done_parser = subparsers.add_parser('done', help='Mark task complete')
    done_parser.add_argument('id', type=int, help='Task ID')

    skip_parser = subparsers.add_parser('skip', help='Skip task')
    skip_parser.add_argument('id', type=int, help='Task ID')

    args = parser.parse_args()
    todo = SmartTodo()

    if args.command == 'list':
        todo.list_tasks()
    elif args.command == 'add':
        todo.add_task(args.description, args.priority)
    elif args.command == 'done':
        todo.mark_done(args.id)
    elif args.command == 'skip':
        todo.skip_task(args.id)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()