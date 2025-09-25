#!/usr/bin/env python3
import json
import sqlite3
import argparse
import os
from pathlib import Path
from datetime import datetime, timedelta

class DailyPlanner:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.aios_dir.mkdir(exist_ok=True)
        self.goals_file = self.aios_dir / "goals.txt"
        self.tasks_file = self.aios_dir / "tasks.txt"
        self.plan_file = self.aios_dir / "daily_plan.md"
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

    def read_events(self):
        conn = sqlite3.connect(self.events_db)
        events = conn.execute(
            "SELECT * FROM events WHERE target='daily_planner' AND processed_by IS NULL"
        ).fetchall()
        for event in events:
            conn.execute("UPDATE events SET processed_by='daily_planner' WHERE id=?", (event[0],))
        conn.commit()
        conn.close()
        return events

    def load_goals(self):
        if not self.goals_file.exists():
            return []
        with open(self.goals_file) as f:
            return [line.strip() for line in f if line.strip()]

    def load_tasks(self):
        if not self.tasks_file.exists():
            return []
        with open(self.tasks_file) as f:
            return [line.strip() for line in f if line.strip() and line.startswith('[ ]')]

    def generate_plan(self, energy_level='normal'):
        goals = self.load_goals()
        tasks = self.load_tasks()

        # Check for API key
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            print("❌ Error: OPENAI_API_KEY environment variable not set")
            print("Please set: export OPENAI_API_KEY='your-api-key'")
            raise ValueError("OpenAI API key required for AI planning")

        plan = f"# Daily Plan - {datetime.now().strftime('%Y-%m-%d')}\n\n"
        plan += f"Energy Level: {energy_level}\n\n"

        # Parse tasks by priority
        high_pri = [t for t in tasks if 'p:high' in t or 'p:crit' in t]
        med_pri = [t for t in tasks if 'p:med' in t]
        low_pri = [t for t in tasks if 'p:low' in t]

        plan += "## Morning (9:00-12:00)\n"
        if energy_level == 'high':
            for task in high_pri[:2]:
                plan += f"- {task}\n"
        else:
            for task in med_pri[:1]:
                plan += f"- {task}\n"

        plan += "\n## Afternoon (13:00-17:00)\n"
        remaining = high_pri[2:] + med_pri[1:] + low_pri
        for task in remaining[:3]:
            plan += f"- {task}\n"

        plan += "\n## Goals Alignment\n"
        for goal in goals[:3]:
            plan += f"- {goal}\n"

        with open(self.plan_file, 'w') as f:
            f.write(plan)

        print(f"Plan generated at {self.plan_file}")
        return plan

    def replan(self):
        events = self.read_events()
        skipped_tasks = []

        for event in events:
            if event[3] == 'need_replan':  # type column
                data = json.loads(event[4])  # data column
                skipped_tasks.append(data.get('skipped_task'))

        if skipped_tasks:
            print(f"Replanning due to {len(skipped_tasks)} skipped critical tasks")

        return self.generate_plan()

    def adjust_energy(self, level):
        return self.generate_plan(energy_level=level)

def main():
    parser = argparse.ArgumentParser(description='Daily Planner')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    subparsers.add_parser('plan', help='Generate daily plan')
    subparsers.add_parser('replan', help='Regenerate plan')

    energy_parser = subparsers.add_parser('energy', help='Adjust for energy level')
    energy_parser.add_argument('level', choices=['low', 'normal', 'high'])

    args = parser.parse_args()
    planner = DailyPlanner()

    if args.command == 'plan':
        planner.generate_plan()
    elif args.command == 'replan':
        planner.replan()
    elif args.command == 'energy':
        planner.adjust_energy(args.level)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()