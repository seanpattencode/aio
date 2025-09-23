#!/usr/bin/env python3
"""
claudeCode1: Ultra-Minimal Systemd Orchestrator (<100 lines)
Core pattern: systemd-run for transient units + subprocess
Best for: Quick prototypes, simple workflows
"""
import subprocess
import sys
import json
from pathlib import Path

UNIT_PREFIX = "aios-"

class MinimalOrchestrator:
    """Absolute minimum viable systemd orchestrator"""

    def __init__(self):
        self.units = {}

    def run(self, name: str, command: str, realtime: bool = False) -> bool:
        """Execute command as transient systemd unit"""
        unit = f"{UNIT_PREFIX}{name}"
        args = ["systemd-run", "--user", "--unit", unit, "--collect"]

        if realtime:
            args.extend(["--property=CPUSchedulingPolicy=rr",
                        "--property=CPUSchedulingPriority=80"])

        args.extend(["--", "sh", "-c", command])

        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode == 0:
            self.units[name] = unit
            return True
        return False

    def status(self, name: str) -> str:
        """Check unit status"""
        if name not in self.units:
            return "unknown"

        result = subprocess.run(
            ["systemctl", "--user", "is-active", self.units[name]],
            capture_output=True, text=True
        )
        return result.stdout.strip()

    def stop(self, name: str) -> bool:
        """Stop a unit"""
        if name not in self.units:
            return False

        result = subprocess.run(
            ["systemctl", "--user", "stop", self.units[name]],
            capture_output=True
        )
        return result.returncode == 0

    def list_active(self) -> dict:
        """List all active AIOS units"""
        result = subprocess.run(
            ["systemctl", "--user", "list-units", f"{UNIT_PREFIX}*",
             "--no-legend", "--plain"],
            capture_output=True, text=True
        )

        active = {}
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if parts:
                    name = parts[0].replace('.service', '').replace(UNIT_PREFIX, '')
                    active[name] = parts[3]  # active/inactive
        return active

def main():
    """CLI interface"""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <run|status|stop|list> [args...]")
        sys.exit(1)

    orch = MinimalOrchestrator()
    cmd = sys.argv[1]

    if cmd == "run" and len(sys.argv) >= 4:
        name, command = sys.argv[2], sys.argv[3]
        realtime = "--realtime" in sys.argv
        if orch.run(name, command, realtime):
            print(f"Started: {name}")
        else:
            print(f"Failed to start: {name}")

    elif cmd == "status" and len(sys.argv) >= 3:
        print(orch.status(sys.argv[2]))

    elif cmd == "stop" and len(sys.argv) >= 3:
        if orch.stop(sys.argv[2]):
            print(f"Stopped: {sys.argv[2]}")

    elif cmd == "list":
        for name, state in orch.list_active().items():
            print(f"{name}: {state}")

if __name__ == "__main__":
    main()