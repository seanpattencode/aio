#!/usr/bin/env python3
"""
AIOS - AI Operating System
Systemd-based workflow and process manager for AI-generated programs
"""

import os
import sys
import json
import sqlite3
import signal
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum

# Configure logging to systemd journal if available
try:
    from systemd import journal
    handler = journal.JournalHandler(SYSLOG_IDENTIFIER='aios')
    logging.root.addHandler(handler)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WorkflowState(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"

class AIOS:
    def __init__(self, db_path: str = "/var/lib/aios/aios.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.shutdown = False
        self.processes: Dict[int, asyncio.subprocess.Process] = {}
        self._init_db()
        self._setup_signals()
        
    def _init_db(self):
        """Initialize SQLite database with required tables"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                code TEXT NOT NULL,
                state TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                pid INTEGER,
                exit_code INTEGER,
                output TEXT
            );
            
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                workflow_ids TEXT,
                state TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_workflow_state ON workflows(state);
            CREATE INDEX IF NOT EXISTS idx_workflow_priority ON workflows(priority);
        """)
        self.conn.commit()
        
    def _setup_signals(self):
        """Setup signal handlers for graceful shutdown"""
        for sig in [signal.SIGTERM, signal.SIGINT]:
            signal.signal(sig, self._handle_signal)
            
    def _handle_signal(self, signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self.shutdown = True
        
    async def submit_workflow(self, name: str, code: str, description: str = "", 
                             priority: int = 5) -> int:
        """Submit a new workflow for review"""
        cursor = self.conn.execute(
            "INSERT INTO workflows (name, description, code, priority) VALUES (?, ?, ?, ?)",
            (name, description, code, priority)
        )
        self.conn.commit()
        logger.info(f"Submitted workflow: {name} (ID: {cursor.lastrowid})")
        return cursor.lastrowid
        
    async def review_workflow(self, workflow_id: int, approved: bool) -> bool:
        """Review and approve/reject a workflow"""
        state = WorkflowState.APPROVED if approved else WorkflowState.REJECTED
        self.conn.execute(
            "UPDATE workflows SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (state.value, workflow_id)
        )
        self.conn.commit()
        logger.info(f"Workflow {workflow_id} {state.value}")
        return True
        
    async def _execute_workflow(self, workflow: sqlite3.Row):
        """Execute a single workflow with proper process management"""
        workflow_id = workflow['id']
        try:
            # Update state to running
            self.conn.execute(
                "UPDATE workflows SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (WorkflowState.RUNNING.value, workflow_id)
            )
            self.conn.commit()
            
            # Create temporary file for code execution
            code_path = Path(f"/tmp/aios_workflow_{workflow_id}.py")
            code_path.write_text(workflow['code'])
            
            # Execute with proper process management
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(code_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                limit=1024*1024  # 1MB output limit
            )
            
            self.processes[workflow_id] = process
            
            # Update PID in database
            self.conn.execute(
                "UPDATE workflows SET pid = ? WHERE id = ?",
                (process.pid, workflow_id)
            )
            self.conn.commit()
            
            # Wait for completion with timeout
            try:
                output, _ = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=300  # 5 minute timeout
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.terminate()
                await asyncio.sleep(1)
                if process.returncode is None:
                    process.kill()
                output = b"Process timed out"
                exit_code = -15
            
            # Update results
            state = WorkflowState.COMPLETED if exit_code == 0 else WorkflowState.FAILED
            self.conn.execute(
                """UPDATE workflows 
                   SET state = ?, exit_code = ?, output = ?, 
                       pid = NULL, updated_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (state.value, exit_code, output.decode('utf-8', errors='replace'), workflow_id)
            )
            self.conn.commit()
            
            # Cleanup
            code_path.unlink(missing_ok=True)
            del self.processes[workflow_id]
            
            logger.info(f"Workflow {workflow_id} completed with exit code {exit_code}")
            
        except Exception as e:
            logger.error(f"Error executing workflow {workflow_id}: {e}")
            self.conn.execute(
                "UPDATE workflows SET state = ?, output = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (WorkflowState.FAILED.value, str(e), workflow_id)
            )
            self.conn.commit()
            
    async def scheduler(self):
        """Main scheduler loop with priority-based execution"""
        while not self.shutdown:
            # Get approved workflows sorted by priority
            workflows = self.conn.execute(
                """SELECT * FROM workflows 
                   WHERE state = ? 
                   ORDER BY priority DESC, created_at ASC 
                   LIMIT 5""",
                (WorkflowState.APPROVED.value,)
            ).fetchall()
            
            # Execute workflows concurrently
            if workflows:
                tasks = [self._execute_workflow(w) for w in workflows]
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Clean up zombie processes
            for wid, proc in list(self.processes.items()):
                if proc.returncode is not None:
                    del self.processes[wid]
            
            await asyncio.sleep(1)
            
    async def cleanup(self):
        """Cleanup on shutdown"""
        logger.info("Cleaning up processes...")
        for proc in self.processes.values():
            proc.terminate()
        await asyncio.sleep(2)
        for proc in self.processes.values():
            if proc.returncode is None:
                proc.kill()
        self.conn.close()
        
    async def run(self):
        """Main entry point"""
        logger.info("AIOS starting...")
        try:
            await self.scheduler()
        finally:
            await self.cleanup()
            logger.info("AIOS shutdown complete")

async def main():
    aios = AIOS()
    await aios.run()

if __name__ == "__main__":
    asyncio.run(main())