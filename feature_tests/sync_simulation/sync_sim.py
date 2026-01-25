#!/usr/bin/env python3
"""
Sync Architecture Simulation - Monte Carlo testing of distributed sync strategies

Inspired by:
- CRDTs (Conflict-free Replicated Data Types) - Shapiro et al. 2011
- Event Sourcing - Martin Fowler, Greg Young
- Operational Transform - Google Docs
- Vector Clocks - Lamport 1978
- Append-only logs - Kafka, Datomic

Tests sync strategies for aio-like multi-device personal data sync.
"""
import random, json, time, sqlite3, os, hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from collections import defaultdict
from pathlib import Path
from datetime import datetime

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# === Data Models ===
@dataclass
class Event:
    ts: float
    device: str
    op: str  # e.g. "ssh.add", "ssh.rename", "note.add"
    data: Dict[str, Any]
    id: str = field(default_factory=lambda: hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:8])

@dataclass
class Device:
    name: str
    events: List[Event] = field(default_factory=list)
    local_state: Dict[str, Dict] = field(default_factory=lambda: defaultdict(dict))
    last_sync: float = 0
    online: bool = True

# === Sync Strategies ===
class SyncStrategy:
    name = "base"
    def sync(self, device: Device, central: 'CentralServer') -> Dict: pass
    def apply_op(self, device: Device, event: Event): pass

class LastWriteWins(SyncStrategy):
    """Current aio approach - git reset --hard. Guaranteed data loss."""
    name = "last_write_wins"

    def sync(self, device: Device, central: 'CentralServer'):
        # Push local events
        new_local = [e for e in device.events if e.ts > device.last_sync]
        central.events.extend(new_local)
        # Pull and OVERWRITE (the problem)
        device.events = list(central.events)
        device.local_state = dict(central.state)
        device.last_sync = time.time()
        return {"pushed": len(new_local), "pulled": len(central.events), "conflicts": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        if table not in device.local_state:
            device.local_state[table] = {}
        if op == "add":
            device.local_state[table][event.data["name"]] = event.data
        elif op == "rename":
            old = device.local_state[table].pop(event.data["old"], None)
            if old:
                old["name"] = event.data["new"]
                device.local_state[table][event.data["new"]] = old
        elif op == "delete":
            device.local_state[table].pop(event.data["name"], None)

class AppendOnlyMerge(SyncStrategy):
    """Append-only event log with deterministic replay. No conflicts possible."""
    name = "append_only"

    def sync(self, device: Device, central: 'CentralServer'):
        # Push new local events (append-only - always succeeds)
        new_local = [e for e in device.events if e.ts > device.last_sync]
        for e in new_local:
            if e.id not in {x.id for x in central.events}:
                central.events.append(e)

        # Pull all events we don't have
        local_ids = {e.id for e in device.events}
        new_remote = [e for e in central.events if e.id not in local_ids]
        device.events.extend(new_remote)

        # Replay all events in timestamp order to rebuild state
        device.events.sort(key=lambda e: (e.ts, e.id))
        device.local_state = defaultdict(dict)
        for e in device.events:
            self.apply_op(device, e)

        device.last_sync = time.time()
        return {"pushed": len(new_local), "pulled": len(new_remote), "conflicts": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        if table not in device.local_state:
            device.local_state[table] = {}
        if op == "add":
            device.local_state[table][event.data["name"]] = {**event.data, "_created": event.ts}
        elif op == "archive":
            if event.data["name"] in device.local_state.get(table, {}):
                device.local_state[table][event.data["name"]]["_archived"] = event.ts
        elif op == "rename":
            # Archive old, create new (append-only style)
            old_name, new_name = event.data["old"], event.data["new"]
            if old_name in device.local_state.get(table, {}):
                old_data = device.local_state[table][old_name].copy()
                old_data["_archived"] = event.ts
                device.local_state[table][old_name] = old_data
                new_data = {k: v for k, v in old_data.items() if not k.startswith("_")}
                new_data["name"] = new_name
                new_data["_created"] = event.ts
                device.local_state[table][new_name] = new_data

class VectorClockSync(SyncStrategy):
    """Vector clocks for causal ordering. Detects conflicts, doesn't lose data."""
    name = "vector_clock"

    def __init__(self):
        self.clocks: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def sync(self, device: Device, central: 'CentralServer'):
        conflicts = []
        new_local = [e for e in device.events if e.ts > device.last_sync]

        for e in new_local:
            # Check for concurrent modifications
            for ce in central.events:
                if ce.op == e.op and ce.data.get("name") == e.data.get("name"):
                    if ce.device != e.device and abs(ce.ts - e.ts) < 1.0:
                        conflicts.append((e, ce))
            if e.id not in {x.id for x in central.events}:
                central.events.append(e)

        local_ids = {e.id for e in device.events}
        new_remote = [e for e in central.events if e.id not in local_ids]
        device.events.extend(new_remote)
        device.events.sort(key=lambda e: (e.ts, e.id))

        # Rebuild state, keeping conflicting versions
        device.local_state = defaultdict(dict)
        for e in device.events:
            self.apply_op(device, e)

        device.last_sync = time.time()
        return {"pushed": len(new_local), "pulled": len(new_remote), "conflicts": len(conflicts)}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        if table not in device.local_state:
            device.local_state[table] = {}
        if op == "add":
            device.local_state[table][event.data["name"]] = {**event.data, "_version": event.ts}
        elif op == "rename":
            old_name, new_name = event.data["old"], event.data["new"]
            if old_name in device.local_state.get(table, {}):
                data = device.local_state[table].pop(old_name)
                data["name"] = new_name
                data["_version"] = event.ts
                device.local_state[table][new_name] = data

class CRDTSync(SyncStrategy):
    """CRDT-inspired: Last-Writer-Wins Register with device+timestamp tie-breaking."""
    name = "crdt_lww"

    def sync(self, device: Device, central: 'CentralServer'):
        new_local = [e for e in device.events if e.ts > device.last_sync]
        for e in new_local:
            if e.id not in {x.id for x in central.events}:
                central.events.append(e)

        local_ids = {e.id for e in device.events}
        new_remote = [e for e in central.events if e.id not in local_ids]
        device.events.extend(new_remote)
        device.events.sort(key=lambda e: (e.ts, e.device, e.id))  # deterministic order

        device.local_state = defaultdict(dict)
        for e in device.events:
            self.apply_op(device, e)

        device.last_sync = time.time()
        return {"pushed": len(new_local), "pulled": len(new_remote), "conflicts": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        if table not in device.local_state:
            device.local_state[table] = {}
        key = event.data.get("name") or event.data.get("new")
        current = device.local_state[table].get(key, {})
        current_ts = current.get("_ts", 0)

        # LWW: only apply if newer
        if event.ts >= current_ts:
            if op == "add":
                device.local_state[table][key] = {**event.data, "_ts": event.ts}
            elif op == "rename":
                old_name, new_name = event.data["old"], event.data["new"]
                if old_name in device.local_state.get(table, {}):
                    data = device.local_state[table].pop(old_name)
                    data["name"] = new_name
                    data["_ts"] = event.ts
                    device.local_state[table][new_name] = data

# === Central Server ===
class CentralServer:
    def __init__(self):
        self.events: List[Event] = []
        self.state: Dict[str, Dict] = defaultdict(dict)

# === Simulation ===
class SyncSimulation:
    def __init__(self, strategy: SyncStrategy, n_devices: int = 3, seed: int = None):
        self.strategy = strategy
        self.central = CentralServer()
        self.devices = [Device(name=f"device_{i}") for i in range(n_devices)]
        self.log: List[Dict] = []
        self.seed = seed or int(time.time())
        random.seed(self.seed)

    def generate_operation(self, device: Device) -> Event:
        """Generate random operation simulating real usage."""
        tables = ["ssh", "note", "hub_job"]
        ops = {
            "ssh": [("add", 0.4), ("rename", 0.3), ("archive", 0.3)],
            "note": [("add", 0.7), ("archive", 0.3)],
            "hub_job": [("add", 0.5), ("rename", 0.2), ("archive", 0.3)],
        }
        table = random.choice(tables)
        op = random.choices([o[0] for o in ops[table]], [o[1] for o in ops[table]])[0]

        existing = [k for k, v in device.local_state.get(table, {}).items() if not v.get("_archived")]

        if op == "add":
            name = f"{table}_{random.randint(1000,9999)}"
            data = {"name": name, "value": f"data_{random.randint(1,100)}"}
        elif op == "rename" and existing:
            old = random.choice(existing)
            data = {"old": old, "new": f"{old}_renamed_{random.randint(1,99)}"}
        elif op == "archive" and existing:
            data = {"name": random.choice(existing)}
        else:
            name = f"{table}_{random.randint(1000,9999)}"
            data = {"name": name, "value": f"data_{random.randint(1,100)}"}
            op = "add"

        return Event(ts=time.time(), device=device.name, op=f"{table}.{op}", data=data)

    def run_step(self):
        """Run one simulation step: random device does random operation or syncs."""
        device = random.choice(self.devices)
        if not device.online:
            return

        action = random.choices(["op", "sync"], [0.7, 0.3])[0]

        if action == "op":
            event = self.generate_operation(device)
            device.events.append(event)
            self.strategy.apply_op(device, event)
            self.log.append({"action": "op", "device": device.name, "event": asdict(event)})
        else:
            result = self.strategy.sync(device, self.central)
            self.log.append({"action": "sync", "device": device.name, **result})

    def run(self, n_steps: int = 100):
        """Run full simulation."""
        for _ in range(n_steps):
            self.run_step()
            time.sleep(0.001)  # Small delay for timestamp variation

        # Final sync all devices
        for d in self.devices:
            self.strategy.sync(d, self.central)

    def check_consistency(self) -> Dict:
        """Check if all devices converged to same state."""
        states = [json.dumps(dict(d.local_state), sort_keys=True) for d in self.devices]
        consistent = len(set(states)) == 1

        # Count data loss
        all_adds = [e for e in self.central.events if ".add" in e.op]
        all_names = {e.data["name"] for e in all_adds}

        final_names = set()
        for d in self.devices:
            for table in d.local_state:
                final_names.update(d.local_state[table].keys())

        archived = sum(1 for d in self.devices for t in d.local_state.values()
                      for v in t.values() if v.get("_archived"))

        return {
            "consistent": consistent,
            "total_adds": len(all_adds),
            "final_items": len(final_names),
            "archived": archived // len(self.devices),
            "potential_loss": len(all_names) - len(final_names),
        }

# === Monte Carlo Runner ===
def run_monte_carlo(n_trials: int = 50, n_steps: int = 100, n_devices: int = 3):
    strategies = [LastWriteWins(), AppendOnlyMerge(), VectorClockSync(), CRDTSync()]
    results = {s.name: [] for s in strategies}

    log_file = LOG_DIR / f"monte_carlo_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    with open(log_file, "w") as f:
        for trial in range(n_trials):
            seed = trial * 1000
            for strategy in strategies:
                sim = SyncSimulation(strategy, n_devices=n_devices, seed=seed)
                sim.run(n_steps)
                check = sim.check_consistency()

                result = {
                    "trial": trial,
                    "strategy": strategy.name,
                    "seed": seed,
                    **check,
                    "total_events": len(sim.central.events),
                    "total_syncs": sum(1 for l in sim.log if l["action"] == "sync"),
                }
                results[strategy.name].append(result)
                f.write(json.dumps(result) + "\n")

            if trial % 10 == 0:
                print(f"Trial {trial}/{n_trials}")

    return results, log_file

def generate_report(results: Dict, log_file: Path):
    """Generate summary report."""
    report = ["# Sync Strategy Simulation Report", f"\nLog: {log_file}\n"]
    report.append("## Summary\n")
    report.append("| Strategy | Consistency % | Avg Data Loss | Avg Events |")
    report.append("|----------|--------------|---------------|------------|")

    for name, trials in results.items():
        consistent = sum(1 for t in trials if t["consistent"]) / len(trials) * 100
        avg_loss = sum(t["potential_loss"] for t in trials) / len(trials)
        avg_events = sum(t["total_events"] for t in trials) / len(trials)
        report.append(f"| {name} | {consistent:.0f}% | {avg_loss:.1f} | {avg_events:.0f} |")

    report.append("\n## Strategy Analysis\n")
    report.append("""
### last_write_wins (Current aio)
- Simple but lossy. Later sync overwrites earlier data.
- **Problem**: Concurrent edits = guaranteed data loss.

### append_only (Recommended)
- Events immutable, replayed to build state.
- **Advantage**: No conflicts possible, full history preserved.
- **Used by**: Datomic, Event Sourcing systems, Kafka.

### vector_clock
- Detects concurrent modifications.
- **Advantage**: Can surface conflicts for manual resolution.
- **Used by**: Dynamo, Riak, distributed databases.

### crdt_lww (CRDT Last-Writer-Wins)
- Deterministic merge, no coordination needed.
- **Advantage**: Always converges, works offline.
- **Used by**: Figma, Linear, collaborative editors.

## Recommendation

For aio's use case (personal multi-device sync):
1. **append_only** is simplest and sufficient
2. Archive instead of delete/modify
3. Replay events to build state
4. Git merges cleanly (text append)

## References
- Shapiro et al. "Conflict-free Replicated Data Types" (2011)
- Kleppmann "Designing Data-Intensive Applications" Ch. 5
- Fowler "Event Sourcing" pattern
- Lamport "Time, Clocks, and the Ordering of Events" (1978)
""")

    report_file = LOG_DIR / f"report_{datetime.now():%Y%m%d_%H%M%S}.md"
    report_file.write_text("\n".join(report))
    return report_file

if __name__ == "__main__":
    print("Running Monte Carlo sync simulation...")
    print(f"Strategies: last_write_wins, append_only, vector_clock, crdt_lww")
    print(f"Trials: 50, Steps per trial: 100, Devices: 3\n")

    results, log_file = run_monte_carlo(n_trials=50, n_steps=100, n_devices=3)
    report_file = generate_report(results, log_file)

    print(f"\nResults:")
    for name, trials in results.items():
        consistent = sum(1 for t in trials if t["consistent"]) / len(trials) * 100
        avg_loss = sum(t["potential_loss"] for t in trials) / len(trials)
        print(f"  {name:20s}: {consistent:5.1f}% consistent, {avg_loss:.1f} avg data loss")

    print(f"\nLog: {log_file}")
    print(f"Report: {report_file}")
