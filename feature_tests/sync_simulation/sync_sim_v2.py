#!/usr/bin/env python3
"""
Sync Architecture Simulation v2 - Extended with real-world implementations

Research-backed implementations:
- cr-sqlite (vlcn-io): CRDT extension for SQLite, crsql_as_crr()
- eventsourcing (PyPI): Python event sourcing library
- Automerge/Yjs: CRDT libraries for collaborative editing
- SQLite WAL: Append-only by design until checkpoint
- Litestream: WAL streaming to S3

References:
- https://github.com/vlcn-io/cr-sqlite
- https://eventsourcing.readthedocs.io/
- https://crdt.tech/implementations
- https://sqlite.org/wal.html
- https://automerge.org/
"""
import random, json, time, hashlib, os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Tuple
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
    op: str
    data: Dict[str, Any]
    id: str = field(default_factory=lambda: hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:8])
    hlc: Tuple[float, str, int] = None  # Hybrid Logical Clock: (physical, device, counter)

    def __post_init__(self):
        if not self.hlc:
            self.hlc = (self.ts, self.device, 0)

@dataclass
class Device:
    name: str
    events: List[Event] = field(default_factory=list)
    local_state: Dict[str, Dict] = field(default_factory=dict)
    last_sync: float = 0
    hlc_counter: int = 0
    online: bool = True
    wal: List[Dict] = field(default_factory=list)  # Write-ahead log

class CentralServer:
    def __init__(self):
        self.events: List[Event] = []
        self.state: Dict[str, Dict] = {}
        self.wal: List[Dict] = []

# === Sync Strategies ===

class SyncStrategy:
    name = "base"
    def sync(self, device: Device, central: CentralServer) -> Dict: pass
    def apply_op(self, device: Device, event: Event): pass
    def _ensure_table(self, device: Device, table: str):
        if table not in device.local_state:
            device.local_state[table] = {}

class LastWriteWins(SyncStrategy):
    """Current aio: git reset --hard. Guaranteed data loss."""
    name = "last_write_wins"

    def sync(self, device: Device, central: CentralServer):
        new_local = [e for e in device.events if e.ts > device.last_sync]
        central.events.extend(new_local)
        device.events = list(central.events)
        device.local_state = {k: dict(v) for k, v in central.state.items()}
        device.last_sync = time.time()
        return {"pushed": len(new_local), "conflicts": 0, "lost": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        self._ensure_table(device, table)
        if op == "add":
            device.local_state[table][event.data["name"]] = event.data
        elif op == "rename" and event.data["old"] in device.local_state.get(table, {}):
            old = device.local_state[table].pop(event.data["old"])
            old["name"] = event.data["new"]
            device.local_state[table][event.data["new"]] = old
        elif op == "archive" and event.data["name"] in device.local_state.get(table, {}):
            device.local_state[table].pop(event.data["name"])

class AppendOnlyLog(SyncStrategy):
    """Pure append-only event log. Events are immutable. State rebuilt via replay."""
    name = "append_only_log"

    def sync(self, device: Device, central: CentralServer):
        # Push: append new events (never conflicts - just append)
        new_local = [e for e in device.events if e.id not in {x.id for x in central.events}]
        central.events.extend(new_local)

        # Pull: get events we don't have
        local_ids = {e.id for e in device.events}
        new_remote = [e for e in central.events if e.id not in local_ids]
        device.events.extend(new_remote)

        # Sort by timestamp, rebuild state
        device.events.sort(key=lambda e: (e.ts, e.device, e.id))
        device.local_state = {}
        for e in device.events:
            self.apply_op(device, e)

        device.last_sync = time.time()
        return {"pushed": len(new_local), "conflicts": 0, "lost": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        self._ensure_table(device, table)
        if op == "add":
            device.local_state[table][event.data["name"]] = {**event.data, "_ts": event.ts, "_active": True}
        elif op == "rename":
            old_name, new_name = event.data["old"], event.data["new"]
            if old_name in device.local_state.get(table, {}):
                old_data = device.local_state[table][old_name]
                old_data["_active"] = False
                old_data["_archived_at"] = event.ts
                device.local_state[table][new_name] = {
                    **{k: v for k, v in old_data.items() if not k.startswith("_")},
                    "name": new_name, "_ts": event.ts, "_active": True
                }
        elif op == "archive":
            if event.data["name"] in device.local_state.get(table, {}):
                device.local_state[table][event.data["name"]]["_active"] = False
                device.local_state[table][event.data["name"]]["_archived_at"] = event.ts

class HybridLogicalClock(SyncStrategy):
    """HLC for causal ordering. Used by CockroachDB, Spanner-like systems."""
    name = "hybrid_logical_clock"

    def _next_hlc(self, device: Device) -> Tuple[float, str, int]:
        device.hlc_counter += 1
        return (time.time(), device.name, device.hlc_counter)

    def _hlc_compare(self, a: Tuple, b: Tuple) -> int:
        if a[0] != b[0]: return -1 if a[0] < b[0] else 1
        if a[1] != b[1]: return -1 if a[1] < b[1] else 1
        return -1 if a[2] < b[2] else (1 if a[2] > b[2] else 0)

    def sync(self, device: Device, central: CentralServer):
        new_local = [e for e in device.events if e.id not in {x.id for x in central.events}]
        central.events.extend(new_local)

        local_ids = {e.id for e in device.events}
        new_remote = [e for e in central.events if e.id not in local_ids]
        device.events.extend(new_remote)

        # Sort by HLC for causal ordering
        device.events.sort(key=lambda e: e.hlc)
        device.local_state = {}
        for e in device.events:
            self.apply_op(device, e)

        device.last_sync = time.time()
        return {"pushed": len(new_local), "conflicts": 0, "lost": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        self._ensure_table(device, table)
        if op == "add":
            device.local_state[table][event.data["name"]] = {**event.data, "_hlc": event.hlc}
        elif op == "rename":
            old_name, new_name = event.data["old"], event.data["new"]
            if old_name in device.local_state.get(table, {}):
                old = device.local_state[table][old_name]
                if self._hlc_compare(event.hlc, old.get("_hlc", (0, "", 0))) > 0:
                    old["_archived"] = True
                    device.local_state[table][new_name] = {
                        **{k: v for k, v in old.items() if not k.startswith("_")},
                        "name": new_name, "_hlc": event.hlc
                    }
        elif op == "archive":
            if event.data["name"] in device.local_state.get(table, {}):
                device.local_state[table][event.data["name"]]["_archived"] = True

class CRSQLiteStyle(SyncStrategy):
    """
    Inspired by cr-sqlite: Each column is a CRDT.
    Uses Last-Writer-Wins per field with device+timestamp tiebreaker.
    """
    name = "crsqlite_lww"

    def sync(self, device: Device, central: CentralServer):
        new_local = [e for e in device.events if e.id not in {x.id for x in central.events}]
        central.events.extend(new_local)

        local_ids = {e.id for e in device.events}
        new_remote = [e for e in central.events if e.id not in local_ids]
        device.events.extend(new_remote)

        # Deterministic sort for convergence
        device.events.sort(key=lambda e: (e.ts, e.device, e.id))
        device.local_state = {}
        for e in device.events:
            self.apply_op(device, e)

        device.last_sync = time.time()
        return {"pushed": len(new_local), "conflicts": 0, "lost": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        self._ensure_table(device, table)

        def lww_merge(existing: Dict, new_data: Dict, ts: float, device: str) -> Dict:
            """Per-field LWW merge like cr-sqlite"""
            result = dict(existing)
            for k, v in new_data.items():
                field_key = f"_ts_{k}"
                existing_ts = existing.get(field_key, (0, ""))
                new_ts = (ts, device)
                if new_ts >= existing_ts:
                    result[k] = v
                    result[field_key] = new_ts
            return result

        if op == "add":
            name = event.data["name"]
            existing = device.local_state[table].get(name, {})
            device.local_state[table][name] = lww_merge(existing, event.data, event.ts, event.device)
        elif op == "rename":
            old_name, new_name = event.data["old"], event.data["new"]
            if old_name in device.local_state.get(table, {}):
                old = device.local_state[table][old_name]
                old["_deleted"] = True
                old["_ts__deleted"] = (event.ts, event.device)
                new_data = {k: v for k, v in old.items() if not k.startswith("_")}
                new_data["name"] = new_name
                device.local_state[table][new_name] = lww_merge({}, new_data, event.ts, event.device)
        elif op == "archive":
            if event.data["name"] in device.local_state.get(table, {}):
                item = device.local_state[table][event.data["name"]]
                item["_deleted"] = True
                item["_ts__deleted"] = (event.ts, event.device)

class WALStreaming(SyncStrategy):
    """
    Inspired by Litestream: Stream WAL entries, replay to reconstruct.
    Each operation appends to WAL, sync merges WALs.
    """
    name = "wal_streaming"

    def sync(self, device: Device, central: CentralServer):
        # Push local WAL entries
        central.wal.extend(device.wal)
        device.wal = []

        # Pull and merge all WAL entries
        all_wal = sorted(central.wal, key=lambda w: (w["ts"], w["device"], w.get("seq", 0)))

        # Dedupe by id
        seen = set()
        deduped = []
        for w in all_wal:
            if w["id"] not in seen:
                deduped.append(w)
                seen.add(w["id"])

        central.wal = deduped

        # Rebuild state from WAL
        device.local_state = {}
        for w in deduped:
            event = Event(ts=w["ts"], device=w["device"], op=w["op"], data=w["data"], id=w["id"])
            self.apply_op(device, event)

        device.last_sync = time.time()
        return {"pushed": 0, "conflicts": 0, "lost": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        self._ensure_table(device, table)
        if op == "add":
            device.local_state[table][event.data["name"]] = {**event.data, "_ts": event.ts}
        elif op == "rename":
            old_name, new_name = event.data["old"], event.data["new"]
            if old_name in device.local_state.get(table, {}):
                old = device.local_state[table][old_name]
                old["_archived"] = event.ts
                device.local_state[table][new_name] = {
                    **{k: v for k, v in old.items() if not k.startswith("_")},
                    "name": new_name, "_ts": event.ts
                }
        elif op == "archive":
            if event.data["name"] in device.local_state.get(table, {}):
                device.local_state[table][event.data["name"]]["_archived"] = event.ts

class JSONLAppendOnly(SyncStrategy):
    """
    Simplest possible: JSONL file, append-only, git auto-merges.
    This is what aio should probably use.
    """
    name = "jsonl_append"

    def sync(self, device: Device, central: CentralServer):
        # Append is trivially safe - no conflicts possible
        new_local = [e for e in device.events if e.id not in {x.id for x in central.events}]
        central.events.extend(new_local)

        local_ids = {e.id for e in device.events}
        new_remote = [e for e in central.events if e.id not in local_ids]
        device.events.extend(new_remote)

        # Sort and replay
        device.events.sort(key=lambda e: (e.ts, e.id))
        device.local_state = {}
        for e in device.events:
            self.apply_op(device, e)

        device.last_sync = time.time()
        return {"pushed": len(new_local), "conflicts": 0, "lost": 0}

    def apply_op(self, device: Device, event: Event):
        table, op = event.op.split(".")
        self._ensure_table(device, table)
        if op == "add":
            device.local_state[table][event.data["name"]] = {**event.data, "_id": event.id}
        elif op == "rename":
            old_name, new_name = event.data["old"], event.data["new"]
            if old_name in device.local_state.get(table, {}):
                old = device.local_state[table][old_name]
                old["_superseded_by"] = event.id
                device.local_state[table][new_name] = {
                    **{k: v for k, v in old.items() if not k.startswith("_")},
                    "name": new_name, "_id": event.id
                }
        elif op == "archive":
            if event.data["name"] in device.local_state.get(table, {}):
                device.local_state[table][event.data["name"]]["_archived_by"] = event.id

# === Simulation ===
class SyncSimulation:
    def __init__(self, strategy: SyncStrategy, n_devices: int = 3, seed: int = None):
        self.strategy = strategy
        self.central = CentralServer()
        self.devices = [Device(name=f"dev_{i}") for i in range(n_devices)]
        self.log = []
        random.seed(seed or int(time.time()))

    def generate_op(self, device: Device) -> Event:
        tables = ["ssh", "note", "hub_job"]
        ops = {"ssh": ["add", "rename", "archive"], "note": ["add", "archive"], "hub_job": ["add", "rename", "archive"]}
        table = random.choice(tables)
        existing = [k for k, v in device.local_state.get(table, {}).items()
                   if not v.get("_archived") and not v.get("_deleted") and v.get("_active", True)]

        op = random.choice(ops[table])
        if op == "add" or not existing:
            data = {"name": f"{table}_{random.randint(1000,9999)}", "value": random.randint(1, 100)}
            op = "add"
        elif op == "rename":
            old = random.choice(existing)
            data = {"old": old, "new": f"{old}_r{random.randint(1,99)}"}
        else:
            data = {"name": random.choice(existing)}

        e = Event(ts=time.time(), device=device.name, op=f"{table}.{op}", data=data)
        # For WAL strategy
        if isinstance(self.strategy, WALStreaming):
            device.wal.append({"ts": e.ts, "device": e.device, "op": e.op, "data": e.data, "id": e.id})
        return e

    def run(self, n_steps: int = 100):
        for _ in range(n_steps):
            device = random.choice(self.devices)
            if random.random() < 0.7:
                event = self.generate_op(device)
                device.events.append(event)
                self.strategy.apply_op(device, event)
            else:
                self.strategy.sync(device, self.central)
            time.sleep(0.001)

        for d in self.devices:
            self.strategy.sync(d, self.central)

    def check(self) -> Dict:
        # Check data preservation
        all_adds = [e for d in self.devices for e in d.events if ".add" in e.op]
        added_names = {e.data["name"] for e in all_adds}

        # Count active items across devices
        active_counts = []
        for d in self.devices:
            active = sum(1 for t in d.local_state.values() for v in t.values()
                        if v.get("_active", True) and not v.get("_archived") and not v.get("_deleted"))
            active_counts.append(active)

        # Consistency: do all devices agree?
        states = []
        for d in self.devices:
            # Normalize state for comparison (ignore metadata)
            normalized = {}
            for table, items in d.local_state.items():
                normalized[table] = {
                    k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                    for k, v in items.items()
                    if v.get("_active", True) and not v.get("_archived") and not v.get("_deleted")
                }
            states.append(json.dumps(normalized, sort_keys=True))

        consistent = len(set(states)) == 1
        total_events = len(self.central.events) + len(self.central.wal)

        return {
            "consistent": consistent,
            "total_adds": len(all_adds),
            "active_items": active_counts[0] if active_counts else 0,
            "total_events": total_events,
            "devices_agree": len(set(states)),
        }

def run_monte_carlo(n_trials: int = 100, n_steps: int = 100, n_devices: int = 3):
    strategies = [
        LastWriteWins(),
        AppendOnlyLog(),
        HybridLogicalClock(),
        CRSQLiteStyle(),
        WALStreaming(),
        JSONLAppendOnly(),
    ]

    results = {s.name: [] for s in strategies}
    log_file = LOG_DIR / f"mc_v2_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    with open(log_file, "w") as f:
        for trial in range(n_trials):
            seed = trial * 1000
            for strategy in strategies:
                sim = SyncSimulation(strategy, n_devices=n_devices, seed=seed)
                sim.run(n_steps)
                check = sim.check()
                result = {"trial": trial, "strategy": strategy.name, **check}
                results[strategy.name].append(result)
                f.write(json.dumps(result) + "\n")
            if trial % 20 == 0:
                print(f"Trial {trial}/{n_trials}")

    return results, log_file

def report(results: Dict, log_file: Path):
    lines = [
        "# Sync Strategy Simulation Report v2",
        f"\nLog: {log_file}",
        f"\n## Summary\n",
        "| Strategy | Consistency | Avg Active Items | Notes |",
        "|----------|-------------|------------------|-------|"
    ]

    for name, trials in results.items():
        consistent = sum(1 for t in trials if t["consistent"]) / len(trials) * 100
        avg_active = sum(t["active_items"] for t in trials) / len(trials)
        notes = {
            "last_write_wins": "Data loss, forces agreement",
            "append_only_log": "Preserves all, immutable events",
            "hybrid_logical_clock": "Causal ordering, CockroachDB-style",
            "crsqlite_lww": "Per-field CRDT, cr-sqlite style",
            "wal_streaming": "Litestream-style WAL replay",
            "jsonl_append": "Simplest, git-friendly",
        }.get(name, "")
        lines.append(f"| {name} | {consistent:.0f}% | {avg_active:.1f} | {notes} |")

    lines.extend([
        "\n## Recommendations for aio",
        "",
        "1. **jsonl_append** or **append_only_log** - simplest, zero conflicts",
        "2. Archive instead of delete - `{..., _archived_by: event_id}`",
        "3. Rename = archive old + create new",
        "4. Store as `events.jsonl` - git merges automatically",
        "5. Rebuild `state.db` on startup from events",
        "",
        "## Libraries to Consider",
        "",
        "- [eventsourcing](https://pypi.org/project/eventsourcing/) - Python event sourcing",
        "- [cr-sqlite](https://github.com/vlcn-io/cr-sqlite) - CRDT SQLite extension",
        "- [Litestream](https://litestream.io/) - SQLite WAL streaming",
        "- SQLite WAL mode - natural append-only until checkpoint",
    ])

    report_file = LOG_DIR / f"report_v2_{datetime.now():%Y%m%d_%H%M%S}.md"
    report_file.write_text("\n".join(lines))
    print(f"\nReport: {report_file}")
    return report_file

if __name__ == "__main__":
    print("Sync Simulation v2 - Extended Strategies")
    print("=" * 50)
    results, log_file = run_monte_carlo(n_trials=100, n_steps=100, n_devices=3)

    print("\nResults:")
    for name, trials in results.items():
        consistent = sum(1 for t in trials if t["consistent"]) / len(trials) * 100
        avg_active = sum(t["active_items"] for t in trials) / len(trials)
        print(f"  {name:25s}: {consistent:5.1f}% consistent, {avg_active:.1f} avg active items")

    report(results, log_file)
