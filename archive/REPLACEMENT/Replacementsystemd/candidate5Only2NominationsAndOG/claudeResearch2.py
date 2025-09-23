#!/usr/bin/env python3
"""
AIOS Ultimate - Synthesized from all best practices
Combines: Android's reaping, transient units, async patterns, minimal overhead
"""
import os
import sys
import json
import sqlite3
import signal
import asyncio
import logging
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

# Setup logging (deepseek1 pattern)
try:
    from systemd import journal, daemon
    handler = journal.JournalHandler(SYSLOG_IDENTIFIER='aios')
    logging.root.addHandler(handler)
except ImportError:
    pass  # Fallback to standard logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('aios')

class State(Enum):
    PENDING = "pending"
    APPROVED = "approved" 
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Workflow:
    id: str
    name: str
    command: str
    state: State = State.PENDING
    priority: int = 0
    memory_mb: int = 512
    cpu_percent: int = 100
    realtime: bool = False
    auto_approve: bool = False

class AIOS:
    """Ultimate AIOS combining best patterns from all implementations"""
    
    def __init__(self, db_path: str = "~/.aios/state.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
        self.running = True
        self.tasks = {}  # Active async tasks
        
        # Initialize database (gemini WAL pattern)
        self.db = sqlite3.connect(str(self.db_path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                command TEXT NOT NULL,
                state TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                memory_mb INTEGER DEFAULT 512,
                cpu_percent INTEGER DEFAULT 100,
                realtime BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unit_name TEXT,
                exit_code INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_state ON workflows(state, priority DESC);
        """)
        
        # Signal handling (copilot1 + deepseek1 pattern)
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, 'running', False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, 'running', False))
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)  # Auto-reap zombies
    
    def submit(self, workflow: Workflow) -> str:
        """Submit workflow for review/execution"""
        if workflow.auto_approve:
            workflow.state = State.APPROVED
        
        self.db.execute(
            """INSERT INTO workflows (id, name, command, state, priority, 
               memory_mb, cpu_percent, realtime) VALUES (?,?,?,?,?,?,?,?)""",
            (workflow.id, workflow.name, workflow.command, workflow.state.value,
             workflow.priority, workflow.memory_mb, workflow.cpu_percent, workflow.realtime)
        )
        logger.info(f"Submitted workflow {workflow.id}")
        
        if workflow.auto_approve:
            asyncio.create_task(self._execute(workflow))
        
        return workflow.id
    
    def approve(self, workflow_id: str) -> bool:
        """Approve pending workflow"""
        cursor = self.db.execute(
            "UPDATE workflows SET state=? WHERE id=? AND state=? RETURNING *",
            (State.APPROVED.value, workflow_id, State.PENDING.value)
        )
        row = cursor.fetchone()
        if row:
            workflow = self._row_to_workflow(row)
            asyncio.create_task(self._execute(workflow))
            return True
        return False
    
    async def _execute(self, workflow: Workflow):
        """Execute using systemd transient units (kimi1 + chatgptResearch1 pattern)"""
        import subprocess
        
        # Update state
        self.db.execute(
            "UPDATE workflows SET state=? WHERE id=?",
            (State.RUNNING.value, workflow.id)
        )
        
        # Build systemd-run command (transient units are fastest)
        unit_name = f"aios-{workflow.id}"
        cmd = [
            "systemd-run", "--user", "--collect", "--unit", unit_name,
            f"--property=MemoryMax={workflow.memory_mb}M",
            f"--property=CPUQuota={workflow.cpu_percent}%",
            "--property=StandardOutput=journal",
            "--property=StandardError=journal"
        ]
        
        # Real-time scheduling (deepseek1 pattern)
        if workflow.realtime:
            cmd.extend([
                "--property=CPUSchedulingPolicy=fifo",
                "--property=CPUSchedulingPriority=90"
            ])
        
        # Execute command
        cmd.extend(["--", "/bin/sh", "-c", workflow.command])
        
        try:
            # Start the unit
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Store unit name for monitoring
                self.db.execute(
                    "UPDATE workflows SET unit_name=? WHERE id=?",
                    (unit_name, workflow.id)
                )
                
                # Monitor completion (async polling)
                await self._monitor_unit(workflow.id, unit_name)
            else:
                raise Exception(f"Failed to start: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Execution failed for {workflow.id}: {e}")
            self.db.execute(
                "UPDATE workflows SET state=?, exit_code=-1 WHERE id=?",
                (State.FAILED.value, workflow.id)
            )
    
    async def _monitor_unit(self, workflow_id: str, unit_name: str):
        """Monitor systemd unit status"""
        import subprocess
        
        while self.running:
            # Check unit status
            result = subprocess.run(
                ["systemctl", "--user", "show", unit_name, 
                 "--property=ActiveState,ExecMainStatus"],
                capture_output=True, text=True
            )
            
            props = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    props[k] = v
            
            state = props.get('ActiveState', '')
            
            if state in ('inactive', 'failed'):
                # Unit finished
                exit_code = int(props.get('ExecMainStatus', '-1'))
                final_state = State.COMPLETED if exit_code == 0 else State.FAILED
                
                self.db.execute(
                    "UPDATE workflows SET state=?, exit_code=? WHERE id=?",
                    (final_state.value, exit_code, workflow_id)
                )
                
                logger.info(f"Workflow {workflow_id} {final_state.value} (exit={exit_code})")
                break
            
            await asyncio.sleep(1)
    
    def _row_to_workflow(self, row) -> Workflow:
        """Convert DB row to Workflow"""
        return Workflow(
            id=row['id'], name=row['name'], command=row['command'],
            state=State(row['state']), priority=row['priority'],
            memory_mb=row['memory_mb'], cpu_percent=row['cpu_percent'],
            realtime=bool(row['realtime'])
        )
    
    async def scheduler(self):
        """Main scheduler loop (claude1 pattern)"""
        try:
            if hasattr(daemon, 'notify'):
                daemon.notify('READY=1')
        except:
            pass
        
        while self.running:
            # Get approved workflows
            rows = self.db.execute(
                """SELECT * FROM workflows WHERE state=? 
                   ORDER BY priority DESC, created_at LIMIT 5""",
                (State.APPROVED.value,)
            ).fetchall()
            
            # Execute in parallel
            if rows:
                tasks = [self._execute(self._row_to_workflow(row)) for row in rows]
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Status update
            stats = self.db.execute(
                "SELECT state, COUNT(*) as cnt FROM workflows GROUP BY state"
            ).fetchall()
            
            status = {row['state']: row['cnt'] for row in stats}
            logger.info(f"Status: {status}")
            
            if hasattr(daemon, 'notify'):
                active = status.get('running', 0)
                daemon.notify(f'STATUS=Running {active} workflows')
            
            await asyncio.sleep(2)
    
    def status(self, workflow_id: Optional[str] = None) -> Dict[str, Any]:
        """Get workflow status"""
        if workflow_id:
            row = self.db.execute(
                "SELECT * FROM workflows WHERE id=?", (workflow_id,)
            ).fetchone()
            return dict(row) if row else None
        else:
            return {
                row['id']: row['state'] for row in 
                self.db.execute("SELECT id, state FROM workflows")
            }

# CLI Interface (qwen1 + geminiWeb1 pattern)
async def main():
    """Main entry point with CLI"""
    aios = AIOS()
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "submit":
            # Example: ./aios.py submit "test" "echo hello" --auto
            wf = Workflow(
                id=f"wf-{os.urandom(4).hex()}",
                name=sys.argv[2] if len(sys.argv) > 2 else "test",
                command=sys.argv[3] if len(sys.argv) > 3 else "echo test",
                auto_approve="--auto" in sys.argv,
                realtime="--rt" in sys.argv
            )
            print(f"Submitted: {aios.submit(wf)}")
            
        elif cmd == "approve" and len(sys.argv) > 2:
            if aios.approve(sys.argv[2]):
                print(f"Approved: {sys.argv[2]}")
            else:
                print("Not found or already approved")
                
        elif cmd == "status":
            wf_id = sys.argv[2] if len(sys.argv) > 2 else None
            print(json.dumps(aios.status(wf_id), indent=2))
            
        else:
            print(f"Usage: {sys.argv[0]} [submit|approve|status|run]")
            sys.exit(1)
    else:
        # Run scheduler
        await aios.scheduler()

if __name__ == "__main__":
    asyncio.run(main())