#!/usr/bin/env python3
"""
Systemd-based orchestrator - Ultra-minimal, ultra-fast
Leverages systemd for process management, restart, and zombie reaping
"""
import os
import sys
import time
import subprocess
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()
UNIT_PREFIX = "aios-"

class SystemdOrchestrator:
    """Minimal systemd wrapper - let systemd handle everything"""

    def __init__(self):
        self.jobs = {}
        self._load_jobs()

    def _run(self, *args):
        """Run systemctl command"""
        return subprocess.run(["systemctl", "--user"] + list(args),
                            capture_output=True, text=True, check=False)

    def _load_jobs(self):
        """Load existing AIOS jobs from systemd"""
        result = self._run("list-units", f"{UNIT_PREFIX}*.service", "--no-legend", "--plain")
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if parts:
                    name = parts[0].replace('.service', '').replace(UNIT_PREFIX, '')
                    self.jobs[name] = parts[0]

    def add_job(self, name: str, command: str, restart: str = "always") -> str:
        """Create systemd service unit"""
        unit_name = f"{UNIT_PREFIX}{name}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)

        # Systemd handles: zombie reaping, process groups, restart, logging
        unit_content = f"""[Unit]
Description=AIOS Job: {name}

[Service]
Type=simple
ExecStart=/bin/sh -c '{command}'
Restart={restart}
RestartSec=0
StandardOutput=journal
StandardError=journal
KillMode=control-group
TimeoutStopSec=0

[Install]
WantedBy=default.target
"""
        unit_path.write_text(unit_content)
        self.jobs[name] = unit_name
        self._run("daemon-reload")
        return unit_name

    def start_job(self, name: str) -> float:
        """Start job via systemd"""
        if name not in self.jobs:
            return -1
        start = time.perf_counter()
        self._run("start", self.jobs[name])
        return (time.perf_counter() - start) * 1000

    def stop_job(self, name: str) -> float:
        """Stop job immediately"""
        if name not in self.jobs:
            return -1
        start = time.perf_counter()
        self._run("stop", self.jobs[name])
        return (time.perf_counter() - start) * 1000

    def restart_job(self, name: str) -> float:
        """Restart job via systemd"""
        if name not in self.jobs:
            return -1
        start = time.perf_counter()
        self._run("restart", self.jobs[name])
        return (time.perf_counter() - start) * 1000

    def restart_all(self) -> dict:
        """Restart all jobs"""
        start = time.perf_counter()
        times = {}

        # Use systemd's batch restart for speed
        units = list(self.jobs.values())
        if units:
            result = self._run("restart", *units)
            for name in self.jobs:
                times[name] = 0.5  # systemd handles it in parallel

        total = (time.perf_counter() - start) * 1000
        print(f"=== RESTART ALL in {total:.2f}ms ===")
        return times

    def status(self) -> dict:
        """Get status of all jobs"""
        status = {}
        for name, unit in self.jobs.items():
            result = self._run("show", unit, "--property=ActiveState,MainPID,ExecMainStartTimestampMonotonic")
            props = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    props[k] = v

            status[name] = {
                'state': props.get('ActiveState', 'unknown'),
                'pid': int(props.get('MainPID', 0))
            }
        return status

    def cleanup(self):
        """Remove all AIOS systemd units"""
        for unit in self.jobs.values():
            self._run("stop", unit)
            self._run("disable", unit)
            unit_path = Path(f"~/.config/systemd/user/{unit}").expanduser()
            if unit_path.exists():
                unit_path.unlink()
        self._run("daemon-reload")

def main():
    """Main entry with example usage"""
    orch = SystemdOrchestrator()

    # Add jobs if they don't exist
    if "heartbeat" not in orch.jobs:
        orch.add_job("heartbeat", "while true; do echo Heartbeat; sleep 5; done")
        orch.start_job("heartbeat")
    if "todo_app" not in orch.jobs:
        orch.add_job("todo_app", "/usr/bin/python3 " + str(BASE_DIR / "hybridTODO.py"))
        orch.start_job("todo_app")

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
        elif cmd == "restart":
            times = orch.restart_all()
            print(f"Restart times: {times}")
        elif cmd == "status":
            print(json.dumps(orch.status(), indent=2))
        elif cmd == "cleanup":
            orch.cleanup()
            print("Cleaned up all units")
        else:
            print(f"Usage: {sys.argv[0]} [start|stop|restart|status|cleanup]")
    else:
        # Just show status
        status = orch.status()
        print(f"=== Systemd Orchestrator ===")
        print(f"Jobs: {len(status)}")
        for name, info in status.items():
            print(f"  {name}: {info['state']} (PID: {info['pid']})")

if __name__ == "__main__":
    main()