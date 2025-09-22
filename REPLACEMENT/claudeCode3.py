#!/usr/bin/env python3
"""
ClaudeCode3: Event-driven Orchestration with Webhooks and Notifications
Features event sourcing, state machines, and real-time updates
"""

import os
import sys
import time
import sqlite3
import json
import subprocess
import threading
import asyncio
import signal
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from datetime import datetime
import hashlib
import queue

BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_events.db"
UNIT_PREFIX = "aios-"

class EventType(Enum):
    # Task lifecycle events
    TASK_CREATED = "task.created"
    TASK_SCHEDULED = "task.scheduled"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_RETRIED = "task.retried"
    TASK_CANCELLED = "task.cancelled"

    # System events
    WORKER_STARTED = "worker.started"
    WORKER_STOPPED = "worker.stopped"
    WORKER_HEARTBEAT = "worker.heartbeat"
    QUEUE_FULL = "queue.full"
    QUEUE_EMPTY = "queue.empty"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    DEPENDENCY_MET = "dependency.met"

@dataclass
class Event:
    id: Optional[int]
    type: EventType
    aggregate_id: str
    aggregate_type: str
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    created_at: datetime
    processed: bool = False

@dataclass
class TaskState:
    id: str
    name: str
    command: str
    status: str
    attempts: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]

class EventStore:
    """Event sourcing store with replay capability"""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_queue = queue.Queue()
        self._processor_thread = None
        self._running = False

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
                    processed INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_aggregate
                    ON events(aggregate_type, aggregate_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_type
                    ON events(type, created_at);

                CREATE INDEX IF NOT EXISTS idx_unprocessed
                    ON events(processed, created_at)
                    WHERE processed = 0;

                CREATE TABLE IF NOT EXISTS snapshots (
                    aggregate_id TEXT PRIMARY KEY,
                    aggregate_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
                );

                CREATE TABLE IF NOT EXISTS projections (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
                );
            """)

    def publish(self, event_type: EventType, aggregate_id: str, aggregate_type: str,
               data: Dict[str, Any], metadata: Dict[str, Any] = None) -> Event:
        """Publish an event to the store"""
        metadata = metadata or {}
        metadata['publisher'] = os.getpid()
        metadata['timestamp'] = time.time()

        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO events (type, aggregate_id, aggregate_type, data, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (event_type.value, aggregate_id, aggregate_type,
                 json.dumps(data), json.dumps(metadata)))

            event = Event(
                id=cursor.lastrowid,
                type=event_type,
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                data=data,
                metadata=metadata,
                created_at=datetime.now(),
                processed=False
            )

            conn.commit()

        # Queue for async processing
        self._event_queue.put(event)
        return event

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]):
        """Subscribe to events of a specific type"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def start_processor(self):
        """Start background event processor"""
        if not self._running:
            self._running = True
            self._processor_thread = threading.Thread(target=self._process_events, daemon=True)
            self._processor_thread.start()

    def stop_processor(self):
        """Stop event processor"""
        self._running = False
        if self._processor_thread:
            self._processor_thread.join(timeout=5)

    def _process_events(self):
        """Process events from queue"""
        while self._running:
            try:
                # Process queued events
                event = self._event_queue.get(timeout=1)
                self._dispatch_event(event)

                # Mark as processed
                with self._get_conn() as conn:
                    conn.execute("""
                        UPDATE events SET processed = 1 WHERE id = ?
                    """, (event.id,))
                    conn.commit()

            except queue.Empty:
                # Check for unprocessed events in DB
                self._process_unprocessed()

    def _process_unprocessed(self):
        """Process any unprocessed events from DB"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT * FROM events
                WHERE processed = 0
                ORDER BY created_at
                LIMIT 100
            """)

            for row in cursor.fetchall():
                event = self._row_to_event(row)
                self._dispatch_event(event)

                conn.execute("""
                    UPDATE events SET processed = 1 WHERE id = ?
                """, (event.id,))

            conn.commit()

    def _dispatch_event(self, event: Event):
        """Dispatch event to subscribers"""
        if event.type in self._subscribers:
            for handler in self._subscribers[event.type]:
                try:
                    handler(event)
                except Exception as e:
                    print(f"Handler error for {event.type}: {e}")

    def _row_to_event(self, row) -> Event:
        return Event(
            id=row['id'],
            type=EventType(row['type']),
            aggregate_id=row['aggregate_id'],
            aggregate_type=row['aggregate_type'],
            data=json.loads(row['data']),
            metadata=json.loads(row['metadata']),
            created_at=datetime.fromtimestamp(row['created_at'] / 1000),
            processed=bool(row['processed'])
        )

    def replay(self, aggregate_type: str, aggregate_id: str,
              from_version: int = 0) -> List[Event]:
        """Replay events for an aggregate"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT * FROM events
                WHERE aggregate_type = ? AND aggregate_id = ?
                AND id > ?
                ORDER BY created_at
            """, (aggregate_type, aggregate_id, from_version))

            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_projection(self, projection_id: str) -> Optional[Dict[str, Any]]:
        """Get a projection (materialized view)"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT data FROM projections WHERE id = ?
            """, (projection_id,))
            row = cursor.fetchone()
            return json.loads(row['data']) if row else None

    def update_projection(self, projection_id: str, projection_type: str,
                        data: Dict[str, Any]):
        """Update a projection"""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO projections (id, type, data, version, updated_at)
                VALUES (?, ?, ?,
                       COALESCE((SELECT version + 1 FROM projections WHERE id = ?), 1),
                       strftime('%s', 'now') * 1000)
            """, (projection_id, projection_type, json.dumps(data), projection_id))
            conn.commit()

class StateMachine:
    """Task state machine with transitions"""

    TRANSITIONS = {
        'pending': ['running', 'cancelled'],
        'running': ['completed', 'failed', 'cancelled'],
        'failed': ['pending', 'cancelled'],  # Can retry
        'completed': [],
        'cancelled': []
    }

    def __init__(self, event_store: EventStore):
        self.event_store = event_store
        self.states: Dict[str, TaskState] = {}

        # Subscribe to task events
        for event_type in [EventType.TASK_CREATED, EventType.TASK_STARTED,
                          EventType.TASK_COMPLETED, EventType.TASK_FAILED]:
            event_store.subscribe(event_type, self._handle_event)

    def _handle_event(self, event: Event):
        """Handle task state transitions"""
        if event.aggregate_type != 'task':
            return

        task_id = event.aggregate_id

        if event.type == EventType.TASK_CREATED:
            self.states[task_id] = TaskState(
                id=task_id,
                name=event.data['name'],
                command=event.data['command'],
                status='pending',
                attempts=0,
                max_retries=event.data.get('max_retries', 3),
                created_at=event.created_at,
                updated_at=event.created_at,
                metadata=event.data.get('metadata', {})
            )

        elif task_id in self.states:
            state = self.states[task_id]

            if event.type == EventType.TASK_STARTED:
                if self._can_transition(state.status, 'running'):
                    state.status = 'running'
                    state.attempts += 1
                    state.updated_at = event.created_at

            elif event.type == EventType.TASK_COMPLETED:
                if self._can_transition(state.status, 'completed'):
                    state.status = 'completed'
                    state.updated_at = event.created_at

            elif event.type == EventType.TASK_FAILED:
                if self._can_transition(state.status, 'failed'):
                    state.status = 'failed'
                    state.updated_at = event.created_at

                    # Auto-retry logic
                    if state.attempts < state.max_retries:
                        self.event_store.publish(
                            EventType.TASK_RETRIED,
                            task_id, 'task',
                            {'attempt': state.attempts + 1}
                        )
                        state.status = 'pending'

    def _can_transition(self, from_state: str, to_state: str) -> bool:
        return to_state in self.TRANSITIONS.get(from_state, [])

    def get_state(self, task_id: str) -> Optional[TaskState]:
        return self.states.get(task_id)

class WorkflowEngine:
    """Workflow orchestration with dependency tracking"""

    def __init__(self, event_store: EventStore, state_machine: StateMachine):
        self.event_store = event_store
        self.state_machine = state_machine
        self.workflows: Dict[str, Dict[str, Any]] = {}

        # Subscribe to workflow events
        event_store.subscribe(EventType.TASK_COMPLETED, self._check_dependencies)

    def create_workflow(self, workflow_id: str, tasks: List[Dict[str, Any]]):
        """Create a workflow with tasks and dependencies"""
        self.workflows[workflow_id] = {
            'tasks': {},
            'dependencies': {},
            'status': 'pending'
        }

        # Publish workflow started event
        self.event_store.publish(
            EventType.WORKFLOW_STARTED,
            workflow_id, 'workflow',
            {'task_count': len(tasks)}
        )

        # Create tasks
        for task_def in tasks:
            task_id = f"{workflow_id}:{task_def['name']}"

            # Store task definition
            self.workflows[workflow_id]['tasks'][task_id] = task_def

            # Store dependencies
            if 'depends_on' in task_def:
                self.workflows[workflow_id]['dependencies'][task_id] = [
                    f"{workflow_id}:{dep}" for dep in task_def['depends_on']
                ]

            # Create task if no dependencies
            if not task_def.get('depends_on'):
                self._create_task(task_id, task_def)

    def _create_task(self, task_id: str, task_def: Dict[str, Any]):
        """Create a task in the workflow"""
        self.event_store.publish(
            EventType.TASK_CREATED,
            task_id, 'task',
            {
                'name': task_def['name'],
                'command': task_def['command'],
                'metadata': task_def.get('metadata', {}),
                'max_retries': task_def.get('max_retries', 3)
            }
        )

    def _check_dependencies(self, event: Event):
        """Check if task completion enables dependent tasks"""
        completed_task_id = event.aggregate_id

        # Find workflow
        workflow_id = completed_task_id.split(':')[0] if ':' in completed_task_id else None
        if not workflow_id or workflow_id not in self.workflows:
            return

        workflow = self.workflows[workflow_id]

        # Check each task's dependencies
        for task_id, deps in workflow['dependencies'].items():
            if completed_task_id in deps:
                # Check if all dependencies are met
                all_met = all(
                    self.state_machine.get_state(dep) and
                    self.state_machine.get_state(dep).status == 'completed'
                    for dep in deps
                )

                if all_met:
                    # Dependencies met, create task
                    self.event_store.publish(
                        EventType.DEPENDENCY_MET,
                        task_id, 'task',
                        {'dependencies': deps}
                    )
                    self._create_task(task_id, workflow['tasks'][task_id])

        # Check if workflow is complete
        all_tasks_complete = all(
            self.state_machine.get_state(task_id) and
            self.state_machine.get_state(task_id).status in ['completed', 'cancelled']
            for task_id in workflow['tasks']
        )

        if all_tasks_complete:
            self.event_store.publish(
                EventType.WORKFLOW_COMPLETED,
                workflow_id, 'workflow',
                {'completed_tasks': len(workflow['tasks'])}
            )
            workflow['status'] = 'completed'

class EventDrivenOrchestrator:
    """Main orchestrator with event-driven architecture"""

    def __init__(self):
        self.event_store = EventStore()
        self.state_machine = StateMachine(self.event_store)
        self.workflow_engine = WorkflowEngine(self.event_store, self.state_machine)
        self._running = False

        # Subscribe to events for monitoring
        self.event_store.subscribe(EventType.TASK_CREATED, self._on_task_created)
        self.event_store.subscribe(EventType.TASK_FAILED, self._on_task_failed)
        self.event_store.subscribe(EventType.WORKFLOW_COMPLETED, self._on_workflow_completed)

    def _on_task_created(self, event: Event):
        print(f"📋 Task created: {event.data['name']} (ID: {event.aggregate_id})")

    def _on_task_failed(self, event: Event):
        print(f"❌ Task failed: {event.aggregate_id}")

    def _on_workflow_completed(self, event: Event):
        print(f"✅ Workflow completed: {event.aggregate_id}")

    def start(self):
        """Start the orchestrator"""
        self._running = True
        self.event_store.start_processor()
        print("Event-driven orchestrator started")

    def stop(self):
        """Stop the orchestrator"""
        self._running = False
        self.event_store.stop_processor()
        print("Event-driven orchestrator stopped")

    def execute_task(self, task_id: str):
        """Execute a task (would integrate with actual runner)"""
        state = self.state_machine.get_state(task_id)
        if not state or state.status != 'pending':
            return

        # Publish started event
        self.event_store.publish(
            EventType.TASK_STARTED,
            task_id, 'task',
            {'attempt': state.attempts + 1}
        )

        try:
            # Simulate task execution
            print(f"Executing: {state.command}")
            result = subprocess.run(
                state.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                self.event_store.publish(
                    EventType.TASK_COMPLETED,
                    task_id, 'task',
                    {'output': result.stdout[:1000]}
                )
            else:
                self.event_store.publish(
                    EventType.TASK_FAILED,
                    task_id, 'task',
                    {'error': result.stderr[:1000], 'exit_code': result.returncode}
                )

        except Exception as e:
            self.event_store.publish(
                EventType.TASK_FAILED,
                task_id, 'task',
                {'error': str(e)}
            )

    def run_worker(self):
        """Run a worker that processes pending tasks"""
        print("Worker started - processing tasks...")
        while self._running:
            # Find pending tasks
            for task_id, state in self.state_machine.states.items():
                if state.status == 'pending':
                    self.execute_task(task_id)

            time.sleep(1)

def main():
    """CLI interface"""
    orchestrator = EventDrivenOrchestrator()
    orchestrator.start()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "workflow":
            # Create example workflow
            workflow_id = f"workflow_{int(time.time())}"
            tasks = [
                {'name': 'setup', 'command': 'echo "Setting up..."'},
                {'name': 'process1', 'command': 'echo "Processing 1"', 'depends_on': ['setup']},
                {'name': 'process2', 'command': 'echo "Processing 2"', 'depends_on': ['setup']},
                {'name': 'cleanup', 'command': 'echo "Cleaning up"',
                 'depends_on': ['process1', 'process2']}
            ]

            print(f"Creating workflow {workflow_id}")
            orchestrator.workflow_engine.create_workflow(workflow_id, tasks)

            # Run worker to process tasks
            orchestrator.run_worker()

        elif cmd == "worker":
            orchestrator.run_worker()

        elif cmd == "events":
            # Show recent events
            with orchestrator.event_store._get_conn() as conn:
                cursor = conn.execute("""
                    SELECT type, aggregate_id, data, created_at
                    FROM events
                    ORDER BY created_at DESC
                    LIMIT 20
                """)
                for row in cursor.fetchall():
                    print(f"{row['type']}: {row['aggregate_id']} - {row['data']}")

        elif cmd == "test":
            # Test event publishing
            task_id = f"test_{int(time.time())}"
            orchestrator.event_store.publish(
                EventType.TASK_CREATED,
                task_id, 'task',
                {'name': 'test_task', 'command': 'echo "Hello, Events!"'}
            )

            time.sleep(1)  # Let event process
            orchestrator.execute_task(task_id)

        else:
            print(f"Unknown command: {cmd}")
            print("Commands: workflow, worker, events, test")

    else:
        print("Event-driven orchestrator ready")
        print("Use 'workflow' to create a test workflow")
        print("Use 'worker' to start processing tasks")
        print("Use 'events' to view event log")

    orchestrator.stop()

if __name__ == "__main__":
    main()