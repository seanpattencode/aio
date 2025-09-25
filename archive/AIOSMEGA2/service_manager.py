#!/usr/bin/env python3
import json
import sqlite3
import argparse
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime

class ServiceManager:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.aios_dir.mkdir(exist_ok=True)
        self.services_file = self.aios_dir / "services.json"
        self.events_db = self.aios_dir / "events.db"
        self.running_services = {}
        self.init_db()
        self.load_services()

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

    def load_services(self):
        if not self.services_file.exists():
            default_services = {
                "backup": {"cmd": "python backup_local.py now", "schedule": "0 2 * * *"},
                "scraper": {"cmd": "python web_scraper.py run", "schedule": "0 */6 * * *"},
                "planner": {"cmd": "python daily_planner.py plan", "schedule": "0 8 * * *"}
            }
            with open(self.services_file, 'w') as f:
                json.dump(default_services, f, indent=2)

        with open(self.services_file) as f:
            self.services_config = json.load(f)

    def run_service(self, name):
        if name in self.services_config:
            service = self.services_config[name]
            cmd = service.get('cmd') or service.get('command', f'echo "No command for {name}"')

            def run_in_thread():
                try:
                    process = subprocess.Popen(cmd, shell=True,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)
                    self.running_services[name] = process
                    stdout, stderr = process.communicate()

                    if process.returncode == 0:
                        print(f"✓ {name} completed successfully")
                    else:
                        print(f"✗ {name} failed: {stderr.decode()}")

                except Exception as e:
                    print(f"✗ {name} error: {e}")

                finally:
                    if name in self.running_services:
                        del self.running_services[name]

            thread = threading.Thread(target=run_in_thread)
            thread.daemon = True
            thread.start()
            print(f"🚀 Started service: {name}")

    def start_service(self, name):
        if name not in self.services_config:
            print(f"Service '{name}' not found")
            return

        if name in self.running_services:
            print(f"Service '{name}' is already running")
            return

        self.run_service(name)

    def stop_service(self, name):
        if name in self.running_services:
            process = self.running_services[name]
            process.terminate()
            time.sleep(1)
            if process.poll() is None:
                process.kill()
            del self.running_services[name]
            print(f"⏹ Stopped service: {name}")
        else:
            print(f"Service '{name}' is not running")

    def show_status(self):
        print("\n=== Service Status ===")
        for name, config in self.services_config.items():
            status = "🟢 Running" if name in self.running_services else "⚫ Stopped"
            schedule = config.get('schedule', 'manual')
            print(f"{name}: {status} | Schedule: {schedule}")

        if self.running_services:
            print(f"\nActive processes: {len(self.running_services)}")

    def restart_service(self, name):
        self.stop_service(name)
        time.sleep(1)
        self.start_service(name)

def main():
    parser = argparse.ArgumentParser(description='Service Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    start_parser = subparsers.add_parser('start', help='Start a service')
    start_parser.add_argument('name', help='Service name')

    stop_parser = subparsers.add_parser('stop', help='Stop a service')
    stop_parser.add_argument('name', help='Service name')

    restart_parser = subparsers.add_parser('restart', help='Restart a service')
    restart_parser.add_argument('name', help='Service name')

    subparsers.add_parser('status', help='Show service status')

    args = parser.parse_args()
    manager = ServiceManager()

    if args.command == 'start':
        manager.start_service(args.name)
    elif args.command == 'stop':
        manager.stop_service(args.name)
    elif args.command == 'restart':
        manager.restart_service(args.name)
    elif args.command == 'status':
        manager.show_status()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()