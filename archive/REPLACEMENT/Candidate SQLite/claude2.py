#!/usr/bin/env python3
"""
AIOS Integrated System - SQLite Queue + Systemd Orchestrator
Combines task queue with systemd process management
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from aios_task_queue import AIOSWorkflowQueue, TaskStatus, TaskPriority

class AIOSIntegratedOrchestrator:
    """
    Integrated orchestrator combining SQLite queue with systemd management
    """
    
    def __init__(self):
        # Initialize components
        self.queue = AIOSWorkflowQueue("aios.db")
        self.systemd = SystemdOrchestrator()
        self.worker_unit_name = None
        
        # Create worker if not exists
        self._ensure_worker()
    
    def _ensure_worker(self):
        """Ensure queue worker is running"""
        worker_name = "aios_queue_worker"
        
        if worker_name not in self.systemd.jobs:
            # Create worker script path
            worker_script = Path(__file__).parent / "aios_worker.py"
            
            # Create worker unit
            self.systemd.add_job(
                name=worker_name,
                command=f"/usr/bin/python3 {worker_script}",
                restart="always"
            )
            self.systemd.start_job(worker_name)
            
        self.worker_unit_name = worker_name
    
    def submit_workflow(self, workflow: dict) -> str:
        """
        Submit a workflow to the queue
        
        Args:
            workflow: Workflow definition dict
            
        Returns:
            task_id: Unique task identifier
        """
        # Validate workflow
        required_fields = ['name', 'command', 'type']
        for field in required_fields:
            if field not in workflow:
                raise ValueError(f"Workflow missing required field: {field}")
        
        # Add to queue
        task_id = self.queue.add_task(
            task_type=workflow['type'],
            payload=workflow,
            priority=workflow.get('priority', TaskPriority.NORMAL),
            metadata={
                'submitted_by': os.getenv('USER', 'system'),
                'submitted_at': time.time()
            }
        )
        
        print(f"Workflow submitted: {task_id}")
        return task_id
    
    def process_workflows(self):
        """
        Process pending workflows (main worker loop)
        This would typically run in the worker process
        """
        print("Starting workflow processor...")
        
        while True:
            # Get next task
            task = self.queue.get_next_task()
            
            if not task:
                time.sleep(1)  # No tasks, wait
                continue
            
            print(f"Processing workflow: {task.task_id}")
            
            try:
                # Execute workflow based on type
                if task.task_type == 'ai_workflow':
                    result = self._execute_ai_workflow(task.payload)
                elif task.task_type == 'system_command':
                    result = self._execute_system_command(task.payload)
                elif task.task_type == 'scheduled_job':
                    result = self._execute_scheduled_job(task.payload)
                else:
                    raise ValueError(f"Unknown task type: {task.task_type}")
                
                # Mark complete
                self.queue.complete_task(task.task_id, result)
                print(f"Completed: {task.task_id}")
                
            except Exception as e:
                # Mark failed
                self.queue.fail_task(task.task_id, str(e))
                print(f"Failed: {task.task_id} - {e}")
    
    def _execute_ai_workflow(self, workflow: dict) -> dict:
        """Execute AI workflow"""
        # This would integrate with your AI models
        print(f"Executing AI workflow: {workflow['name']}")
        
        # Example: Run as systemd transient service
        job_name = f"ai_{workflow['name']}_{int(time.time())}"
        
        # Create temporary job
        self.systemd.add_job(
            name=job_name,
            command=f"python3 -c \"print('Running AI: {workflow['name']}')\"",
            restart="no"
        )
        
        # Start and wait
        self.systemd.start_job(job_name)
        time.sleep(0.5)  # Simulate processing
        
        return {
            'status': 'completed',
            'output': f"AI workflow {workflow['name']} executed",
            'job_name': job_name
        }
    
    def _execute_system_command(self, command_def: dict) -> dict:
        """Execute system command"""
        command = command_def['command']
        
        # Run command
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=command_def.get('timeout', 60)
        )
        
        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
    
    def _execute_scheduled_job(self, job_def: dict) -> dict:
        """Execute scheduled job"""
        # This would integrate with systemd timers
        return {
            'status': 'scheduled',
            'next_run': time.time() + job_def.get('interval', 3600)
        }
    
    def get_status(self) -> dict:
        """Get system status"""
        return {
            'queue_stats': self.queue.get_queue_stats(),
            'systemd_jobs': self.systemd.status(),
            'worker_status': self.systemd.status().get(self.worker_unit_name)
        }
    
    def cleanup(self):
        """Cleanup resources"""
        self.queue.close()
        # Don't cleanup systemd units - they persist


# Separate worker process file (aios_worker.py)
WORKER_SCRIPT = '''#!/usr/bin/env python3
"""
AIOS Queue Worker Process
Runs as a systemd service to process queue tasks
"""

import sys
import time
import signal
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from aios_task_queue import AIOSWorkflowQueue, TaskStatus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('aios_worker')

class AIOSWorker:
    """Queue worker process"""
    
    def __init__(self):
        self.queue = AIOSWorkflowQueue()
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Graceful shutdown"""
        logger.info("Shutdown signal received")
        self.running = False
    
    def run(self):
        """Main worker loop"""
        logger.info("AIOS Worker started")
        
        while self.running:
            try:
                # Get next task
                task = self.queue.get_next_task()
                
                if not task:
                    time.sleep(1)
                    continue
                
                logger.info(f"Processing task: {task.task_id} ({task.task_type})")
                
                # Process based on type
                if task.task_type == 'ai_workflow':
                    result = self._process_ai_workflow(task)
                else:
                    result = {'status': 'unsupported'}
                
                # Complete task
                self.queue.complete_task(task.task_id, result)
                logger.info(f"Completed task: {task.task_id}")
                
            except Exception as e:
                logger.error(f"Error processing task: {e}")
                if task:
                    self.queue.fail_task(task.task_id, str(e))
        
        logger.info("AIOS Worker stopped")
        self.queue.close()
    
    def _process_ai_workflow(self, task):
        """Process AI workflow task"""
        # This is where you'd integrate your AI processing
        workflow = task.payload
        
        # Simulate AI processing
        time.sleep(2)
        
        return {
            'status': 'completed',
            'model': workflow.get('model', 'unknown'),
            'result': f"Processed {workflow.get('name', 'workflow')}"
        }

if __name__ == "__main__":
    worker = AIOSWorker()
    worker.run()
'''

# CLI Interface
def main():
    """Main CLI interface for AIOS"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AIOS Orchestrator')
    parser.add_argument('command', choices=['submit', 'status', 'worker', 'test'],
                       help='Command to execute')
    parser.add_argument('--workflow', type=str, help='Workflow JSON file')
    parser.add_argument('--type', type=str, default='ai_workflow',
                       help='Workflow type')
    parser.add_argument('--name', type=str, help='Workflow name')
    
    args = parser.parse_args()
    
    orchestrator = AIOSIntegratedOrchestrator()
    
    if args.command == 'submit':
        # Submit workflow
        if args.workflow:
            with open(args.workflow, 'r') as f:
                workflow = json.load(f)
        else:
            workflow = {
                'name': args.name or 'test_workflow',
                'type': args.type,
                'command': 'echo "Test workflow"',
                'model': 'gpt-4'
            }
        
        task_id = orchestrator.submit_workflow(workflow)
        print(f"Submitted: {task_id}")
        
    elif args.command == 'status':
        # Show status
        status = orchestrator.get_status()
        print(json.dumps(status, indent=2))
        
    elif args.command == 'worker':
        # Run worker (usually done by systemd)
        orchestrator.process_workflows()
        
    elif args.command == 'test':
        # Run test workflows
        print("Running test workflows...")
        
        # Submit test workflows
        for i in range(3):
            orchestrator.submit_workflow({
                'name': f'test_workflow_{i}',
                'type': 'ai_workflow',
                'command': f'echo "Test {i}"',
                'priority': TaskPriority.NORMAL,
                'model': 'gpt-4'
            })
        
        # Check status
        time.sleep(1)
        status = orchestrator.get_status()
        print(f"\nQueue status: {status['queue_stats']}")
        
    orchestrator.cleanup()

# Include the original SystemdOrchestrator class here
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
        result = self._run("list-units", "aios-*.service", "--no-legend", "--plain")
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if parts:
                    name = parts[0].replace('.service', '').replace('aios-', '')
                    self.jobs[name] = parts[0]
    
    def add_job(self, name: str, command: str, restart: str = "always") -> str:
        """Create systemd service unit"""
        unit_name = f"aios-{name}.service"
        unit_path = Path(f"~/.config/systemd/user/{unit_name}").expanduser()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        
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
    
    def status(self) -> dict:
        """Get status of all jobs"""
        status = {}
        for name, unit in self.jobs.items():
            result = self._run("show", unit, 
                             "--property=ActiveState,MainPID")
            props = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    props[k] = v
            
            status[name] = {
                'state': props.get('ActiveState', 'unknown'),
                'pid': int(props.get('MainPID', 0))
            }