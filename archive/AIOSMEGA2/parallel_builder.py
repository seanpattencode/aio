#!/usr/bin/env python3
import json
import sqlite3
import argparse
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime

class ParallelBuilder:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.aios_dir.mkdir(exist_ok=True)
        self.components_dir = self.aios_dir / "components"
        self.components_dir.mkdir(exist_ok=True)
        self.events_db = self.aios_dir / "events.db"
        self.build_status = {}
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
            ("parallel_builder", target, event_type, json.dumps(data))
        )
        conn.commit()
        conn.close()

    def build_component(self, name):
        self.build_status[name] = "building"
        output_file = self.components_dir / f"{name}.py"

        try:
            # Simulate building with cli_ai.py (placeholder)
            cmd = f'echo "# Component: {name}\nprint(\\"{name} running\\")" > {output_file}'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                self.build_status[name] = "completed"
                self.emit_event("ALL", "build_completed", {"component": name})
                print(f"✓ {name} built successfully")
            else:
                self.build_status[name] = "failed"
                print(f"✗ {name} build failed")

        except Exception as e:
            self.build_status[name] = f"error: {e}"
            print(f"✗ {name} error: {e}")

    def build_multiple(self, components):
        threads = []
        print(f"\n🚀 Building {len(components)} components in parallel...\n")

        for comp in components:
            thread = threading.Thread(target=self.build_component, args=(comp,))
            thread.start()
            threads.append(thread)
            self.build_status[comp] = "queued"

        # Display progress
        while any(t.is_alive() for t in threads):
            self.show_progress()
            time.sleep(1)

        for thread in threads:
            thread.join()

        self.show_progress()
        print("\n✅ Build process complete!")

    def show_progress(self):
        print("\r", end="")
        status_icons = {"queued": "⏳", "building": "🔨", "completed": "✅", "failed": "❌"}

        for comp, status in self.build_status.items():
            icon = status_icons.get(status.split(":")[0], "❓")
            print(f"{icon} {comp} ", end="")

    def show_status(self):
        print("\n=== Build Status ===")
        if not self.build_status:
            # Check existing components
            for comp_file in self.components_dir.glob("*.py"):
                print(f"✅ {comp_file.stem} - exists")
        else:
            for comp, status in self.build_status.items():
                print(f"{comp}: {status}")

def main():
    parser = argparse.ArgumentParser(description='Parallel Component Builder')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    build_parser = subparsers.add_parser('build', help='Build components')
    build_parser.add_argument('components', nargs='+', help='Component names')

    subparsers.add_parser('status', help='Show build status')

    args = parser.parse_args()
    builder = ParallelBuilder()

    if args.command == 'build':
        builder.build_multiple(args.components)
    elif args.command == 'status':
        builder.show_status()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()