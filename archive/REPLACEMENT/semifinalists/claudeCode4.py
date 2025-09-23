#!/usr/bin/env python3
"""
ClaudeCode4: Full-featured Orchestrator with Monitoring, Metrics, and Web UI
Production-ready system with health checks, alerting, and comprehensive observability
"""

import os
import sys
import time
import sqlite3
import json
import subprocess
import threading
import signal
import logging
import psutil
from pathlib import Path
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple, Set, Callable
from dataclasses import dataclass, field
from contextlib import contextmanager
from datetime import datetime, timedelta
from collections import defaultdict, deque
import hashlib
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("aios_orchestrator")

BASE_DIR = Path(__file__).parent.absolute()
DB_PATH = BASE_DIR / "aios_full.db"
UNIT_PREFIX = "aios-"
WEB_PORT = 8080

class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    RATE = "rate"

@dataclass
class Metric:
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

class MetricsCollector:
    """Comprehensive metrics collection and aggregation"""

    def __init__(self):
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.rates: Dict[str, deque] = defaultdict(lambda: deque(maxlen=60))
        self.lock = threading.Lock()

    def increment(self, name: str, value: float = 1, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        key = self._make_key(name, labels)
        with self.lock:
            self.counters[key] += value
            self._record(name, MetricType.COUNTER, self.counters[key], labels)

    def gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric"""
        key = self._make_key(name, labels)
        with self.lock:
            self.gauges[key] = value
            self._record(name, MetricType.GAUGE, value, labels)

    def histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Add to histogram metric"""
        key = self._make_key(name, labels)
        with self.lock:
            self.histograms[key].append(value)
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]
            self._record(name, MetricType.HISTOGRAM, value, labels)

    def rate(self, name: str, labels: Dict[str, str] = None):
        """Track rate metric"""
        key = self._make_key(name, labels)
        now = time.time()
        with self.lock:
            self.rates[key].append(now)
            # Calculate rate over last minute
            cutoff = now - 60
            while self.rates[key] and self.rates[key][0] < cutoff:
                self.rates[key].popleft()
            rate = len(self.rates[key]) / 60.0
            self._record(name, MetricType.RATE, rate, labels)

    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Create unique key for metric"""
        if not labels:
            return name
        label_str = ','.join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def _record(self, name: str, type: MetricType, value: float, labels: Dict[str, str] = None):
        """Record metric value"""
        metric = Metric(name, type, value, labels or {})
        self.metrics[name].append(metric)

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        with self.lock:
            summary = {
                'counters': dict(self.counters),
                'gauges': dict(self.gauges),
                'histograms': {},
                'rates': {}
            }

            # Calculate histogram percentiles
            for key, values in self.histograms.items():
                if values:
                    sorted_vals = sorted(values)
                    summary['histograms'][key] = {
                        'p50': sorted_vals[len(sorted_vals) // 2],
                        'p95': sorted_vals[int(len(sorted_vals) * 0.95)],
                        'p99': sorted_vals[int(len(sorted_vals) * 0.99)],
                        'min': sorted_vals[0],
                        'max': sorted_vals[-1]
                    }

            # Calculate rates
            now = time.time()
            for key, timestamps in self.rates.items():
                if timestamps:
                    cutoff = now - 60
                    recent = [t for t in timestamps if t > cutoff]
                    summary['rates'][key] = len(recent) / 60.0

            return summary

class HealthChecker:
    """System health monitoring"""

    def __init__(self, metrics: MetricsCollector):
        self.metrics = metrics
        self.checks: Dict[str, Callable] = {}
        self.status: Dict[str, bool] = {}
        self.last_check: Dict[str, float] = {}

    def register_check(self, name: str, check_fn: Callable[[], bool]):
        """Register a health check"""
        self.checks[name] = check_fn

    def run_checks(self) -> Dict[str, Any]:
        """Run all health checks"""
        results = {}
        overall_healthy = True

        for name, check_fn in self.checks.items():
            try:
                start = time.time()
                healthy = check_fn()
                duration = time.time() - start

                self.status[name] = healthy
                self.last_check[name] = time.time()

                results[name] = {
                    'healthy': healthy,
                    'duration_ms': duration * 1000,
                    'last_check': self.last_check[name]
                }

                self.metrics.gauge(f"health.{name}", 1 if healthy else 0)
                self.metrics.histogram(f"health.{name}.duration", duration)

                if not healthy:
                    overall_healthy = False

            except Exception as e:
                results[name] = {
                    'healthy': False,
                    'error': str(e),
                    'last_check': time.time()
                }
                overall_healthy = False
                self.metrics.gauge(f"health.{name}", 0)

        results['overall'] = overall_healthy
        return results

class AlertManager:
    """Alert generation and management"""

    def __init__(self, metrics: MetricsCollector):
        self.metrics = metrics
        self.alerts: List[Dict[str, Any]] = []
        self.thresholds: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def set_threshold(self, metric: str, threshold: float,
                     comparator: str = 'gt', duration: int = 60):
        """Set alert threshold for metric"""
        self.thresholds[metric] = {
            'threshold': threshold,
            'comparator': comparator,
            'duration': duration,
            'violations': deque(maxlen=duration)
        }

    def check_thresholds(self):
        """Check all thresholds and generate alerts"""
        summary = self.metrics.get_summary()

        for metric, config in self.thresholds.items():
            # Get current value
            value = None
            if metric in summary['gauges']:
                value = summary['gauges'][metric]
            elif metric in summary['counters']:
                value = summary['counters'][metric]
            elif metric in summary['rates']:
                value = summary['rates'][metric]

            if value is not None:
                # Check threshold
                violated = False
                if config['comparator'] == 'gt' and value > config['threshold']:
                    violated = True
                elif config['comparator'] == 'lt' and value < config['threshold']:
                    violated = True
                elif config['comparator'] == 'eq' and value == config['threshold']:
                    violated = True

                # Track violations
                config['violations'].append((time.time(), violated))

                # Check if alert should fire
                if len(config['violations']) >= config['duration']:
                    recent_violations = sum(1 for _, v in config['violations'] if v)
                    if recent_violations >= config['duration'] * 0.8:  # 80% threshold
                        self._fire_alert(metric, value, config['threshold'])

    def _fire_alert(self, metric: str, value: float, threshold: float):
        """Fire an alert"""
        with self.lock:
            alert = {
                'id': hashlib.md5(f"{metric}{time.time()}".encode()).hexdigest()[:8],
                'metric': metric,
                'value': value,
                'threshold': threshold,
                'timestamp': time.time(),
                'severity': 'warning'
            }
            self.alerts.append(alert)
            logger.warning(f"Alert: {metric} = {value} (threshold: {threshold})")

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts"""
        with self.lock:
            # Keep only recent alerts (last hour)
            cutoff = time.time() - 3600
            self.alerts = [a for a in self.alerts if a['timestamp'] > cutoff]
            return list(self.alerts)

class FullFeaturedQueue:
    """Complete task queue with all features"""

    def __init__(self, db_path: str = str(DB_PATH), metrics: MetricsCollector = None):
        self.db_path = db_path
        self.metrics = metrics or MetricsCollector()
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA mmap_size=30000000000")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    args TEXT DEFAULT '{}',
                    priority INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
                    started_at INTEGER,
                    completed_at INTEGER,
                    worker_id TEXT,
                    result TEXT,
                    error TEXT,
                    cpu_time_ms INTEGER,
                    memory_mb REAL,
                    retries INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3
                );

                CREATE INDEX IF NOT EXISTS idx_status_priority
                    ON tasks(status, priority DESC, created_at);

                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    started_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
                    last_heartbeat INTEGER,
                    status TEXT DEFAULT 'running',
                    tasks_completed INTEGER DEFAULT 0,
                    tasks_failed INTEGER DEFAULT 0,
                    cpu_percent REAL,
                    memory_mb REAL
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    labels TEXT,
                    timestamp INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
                );

                CREATE INDEX IF NOT EXISTS idx_metrics_name_time
                    ON metrics(name, timestamp DESC);
            """)

    def add_task(self, name: str, command: str, args: Dict = None,
                priority: int = 0, max_retries: int = 3) -> int:
        """Add task and track metrics"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO tasks (name, command, args, priority, max_retries)
                VALUES (?, ?, ?, ?, ?)
            """, (name, command, json.dumps(args or {}), priority, max_retries))
            conn.commit()

            self.metrics.increment('tasks.created')
            self.metrics.increment('tasks.created.by_priority', labels={'priority': str(priority)})

            return cursor.lastrowid

    def get_next_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get next task with metrics tracking"""
        with self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute("""
                    SELECT * FROM tasks
                    WHERE status = 'pending'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                """)
                row = cursor.fetchone()

                if row:
                    task_id = row['id']
                    now = int(time.time() * 1000)

                    conn.execute("""
                        UPDATE tasks
                        SET status = 'running', started_at = ?, worker_id = ?
                        WHERE id = ?
                    """, (now, worker_id, task_id))

                    # Track queue time
                    queue_time = (now - row['created_at']) / 1000.0
                    self.metrics.histogram('tasks.queue_time', queue_time)
                    self.metrics.increment('tasks.started')

                    conn.commit()
                    return dict(row)

                conn.commit()
                return None

            except Exception as e:
                conn.rollback()
                raise

    def complete_task(self, task_id: int, success: bool, result: str = None,
                     cpu_time_ms: int = 0, memory_mb: float = 0):
        """Complete task with metrics"""
        with self._get_conn() as conn:
            now = int(time.time() * 1000)

            if success:
                conn.execute("""
                    UPDATE tasks
                    SET status = 'completed', completed_at = ?, result = ?,
                        cpu_time_ms = ?, memory_mb = ?
                    WHERE id = ?
                """, (now, result, cpu_time_ms, memory_mb, task_id))

                self.metrics.increment('tasks.completed')
                self.metrics.histogram('tasks.cpu_time_ms', cpu_time_ms)
                self.metrics.histogram('tasks.memory_mb', memory_mb)

            else:
                # Check for retry
                cursor = conn.execute("""
                    SELECT retries, max_retries FROM tasks WHERE id = ?
                """, (task_id,))
                row = cursor.fetchone()

                if row['retries'] < row['max_retries']:
                    conn.execute("""
                        UPDATE tasks
                        SET status = 'pending', retries = retries + 1, error = ?
                        WHERE id = ?
                    """, (result, task_id))
                    self.metrics.increment('tasks.retried')
                else:
                    conn.execute("""
                        UPDATE tasks
                        SET status = 'failed', completed_at = ?, error = ?
                        WHERE id = ?
                    """, (now, result, task_id))
                    self.metrics.increment('tasks.failed')

            conn.commit()

    def update_worker(self, worker_id: str, hostname: str, pid: int,
                     cpu_percent: float = 0, memory_mb: float = 0):
        """Update worker status"""
        with self._get_conn() as conn:
            now = int(time.time() * 1000)
            conn.execute("""
                INSERT OR REPLACE INTO workers
                (id, hostname, pid, last_heartbeat, cpu_percent, memory_mb)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (worker_id, hostname, pid, now, cpu_percent, memory_mb))
            conn.commit()

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        with self._get_conn() as conn:
            # Task statistics
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM tasks
                GROUP BY status
            """)
            task_stats = {row['status']: row['count'] for row in cursor.fetchall()}

            # Worker statistics
            cursor = conn.execute("""
                SELECT COUNT(*) as count,
                       AVG(cpu_percent) as avg_cpu,
                       AVG(memory_mb) as avg_memory
                FROM workers
                WHERE last_heartbeat > ?
            """, (int(time.time() * 1000) - 60000,))  # Active in last minute
            worker_stats = dict(cursor.fetchone())

            # Recent tasks
            cursor = conn.execute("""
                SELECT name, status, created_at, completed_at, worker_id
                FROM tasks
                ORDER BY created_at DESC
                LIMIT 20
            """)
            recent_tasks = [dict(row) for row in cursor.fetchall()]

            # Performance metrics
            cursor = conn.execute("""
                SELECT AVG(cpu_time_ms) as avg_cpu_time,
                       AVG(memory_mb) as avg_memory,
                       AVG((completed_at - started_at) / 1000.0) as avg_duration
                FROM tasks
                WHERE status = 'completed'
                AND completed_at > ?
            """, (int(time.time() * 1000) - 3600000,))  # Last hour
            performance = dict(cursor.fetchone())

            return {
                'task_stats': task_stats,
                'worker_stats': worker_stats,
                'recent_tasks': recent_tasks,
                'performance': performance,
                'metrics': self.metrics.get_summary()
            }

class WebDashboard(http.server.SimpleHTTPRequestHandler):
    """Web dashboard for monitoring"""

    orchestrator = None  # Will be set by main

    def do_GET(self):
        """Handle GET requests"""
        url = urlparse(self.path)

        if url.path == '/':
            self._serve_dashboard()
        elif url.path == '/api/status':
            self._serve_api_status()
        elif url.path == '/api/metrics':
            self._serve_api_metrics()
        elif url.path == '/api/health':
            self._serve_api_health()
        elif url.path == '/api/alerts':
            self._serve_api_alerts()
        else:
            self.send_error(404)

    def _serve_dashboard(self):
        """Serve HTML dashboard"""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>AIOS Orchestrator Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric { display: inline-block; margin: 10px 20px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #2196F3; }
        .metric-label { color: #666; font-size: 14px; }
        .status-ok { color: #4CAF50; }
        .status-error { color: #F44336; }
        .alert { background: #fff3cd; border: 1px solid #ffc107; padding: 10px; margin: 10px 0; border-radius: 4px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f0f0f0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 AIOS Orchestrator Dashboard</h1>

        <div class="card">
            <h2>System Status</h2>
            <div id="status"></div>
        </div>

        <div class="card">
            <h2>Metrics</h2>
            <div id="metrics"></div>
        </div>

        <div class="card">
            <h2>Health Checks</h2>
            <div id="health"></div>
        </div>

        <div class="card">
            <h2>Active Alerts</h2>
            <div id="alerts"></div>
        </div>

        <div class="card">
            <h2>Recent Tasks</h2>
            <div id="tasks"></div>
        </div>
    </div>

    <script>
        function updateDashboard() {
            // Fetch status
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    let html = '';
                    for (const [key, value] of Object.entries(data.task_stats || {})) {
                        html += `<div class="metric"><div class="metric-value">${value}</div><div class="metric-label">${key} tasks</div></div>`;
                    }
                    document.getElementById('status').innerHTML = html;
                });

            // Fetch metrics
            fetch('/api/metrics')
                .then(r => r.json())
                .then(data => {
                    let html = '<table>';
                    for (const [key, value] of Object.entries(data.gauges || {})) {
                        html += `<tr><td>${key}</td><td>${value.toFixed(2)}</td></tr>`;
                    }
                    html += '</table>';
                    document.getElementById('metrics').innerHTML = html;
                });

            // Fetch health
            fetch('/api/health')
                .then(r => r.json())
                .then(data => {
                    let html = '';
                    for (const [key, value] of Object.entries(data)) {
                        if (key !== 'overall') {
                            const status = value.healthy ? 'ok' : 'error';
                            html += `<div>✓ ${key}: <span class="status-${status}">${status.toUpperCase()}</span></div>`;
                        }
                    }
                    document.getElementById('health').innerHTML = html;
                });

            // Fetch alerts
            fetch('/api/alerts')
                .then(r => r.json())
                .then(data => {
                    if (data.length === 0) {
                        document.getElementById('alerts').innerHTML = '<p>No active alerts</p>';
                    } else {
                        let html = '';
                        for (const alert of data) {
                            html += `<div class="alert">⚠️ ${alert.metric}: ${alert.value} (threshold: ${alert.threshold})</div>`;
                        }
                        document.getElementById('alerts').innerHTML = html;
                    }
                });
        }

        // Update every 5 seconds
        updateDashboard();
        setInterval(updateDashboard, 5000);
    </script>
</body>
</html>
"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_api_status(self):
        """Serve status API"""
        data = self.orchestrator.queue.get_dashboard_data()
        self._serve_json(data)

    def _serve_api_metrics(self):
        """Serve metrics API"""
        data = self.orchestrator.metrics.get_summary()
        self._serve_json(data)

    def _serve_api_health(self):
        """Serve health API"""
        data = self.orchestrator.health_checker.run_checks()
        self._serve_json(data)

    def _serve_api_alerts(self):
        """Serve alerts API"""
        data = self.orchestrator.alert_manager.get_active_alerts()
        self._serve_json(data)

    def _serve_json(self, data):
        """Serve JSON response"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def log_message(self, format, *args):
        """Suppress request logging"""
        pass

class ProductionOrchestrator:
    """Production-ready orchestrator with full monitoring"""

    def __init__(self):
        self.metrics = MetricsCollector()
        self.health_checker = HealthChecker(self.metrics)
        self.alert_manager = AlertManager(self.metrics)
        self.queue = FullFeaturedQueue(metrics=self.metrics)
        self.web_server = None
        self._running = False

        # Register health checks
        self.health_checker.register_check('database', self._check_database)
        self.health_checker.register_check('disk_space', self._check_disk_space)
        self.health_checker.register_check('memory', self._check_memory)

        # Set alert thresholds
        self.alert_manager.set_threshold('tasks.failed', 10, 'gt', 60)
        self.alert_manager.set_threshold('health.database', 0.5, 'lt', 30)

    def _check_database(self) -> bool:
        """Check database connectivity"""
        try:
            with self.queue._get_conn() as conn:
                conn.execute("SELECT 1")
            return True
        except:
            return False

    def _check_disk_space(self) -> bool:
        """Check disk space"""
        usage = psutil.disk_usage('/')
        self.metrics.gauge('system.disk.usage_percent', usage.percent)
        return usage.percent < 90

    def _check_memory(self) -> bool:
        """Check memory usage"""
        memory = psutil.virtual_memory()
        self.metrics.gauge('system.memory.usage_percent', memory.percent)
        return memory.percent < 90

    def start_web_server(self):
        """Start web dashboard"""
        WebDashboard.orchestrator = self
        handler = WebDashboard
        self.web_server = socketserver.TCPServer(("", WEB_PORT), handler)

        thread = threading.Thread(target=self.web_server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Web dashboard started on http://localhost:{WEB_PORT}")

    def run_monitoring_loop(self):
        """Run monitoring in background"""
        while self._running:
            # Run health checks
            self.health_checker.run_checks()

            # Check alert thresholds
            self.alert_manager.check_thresholds()

            # Collect system metrics
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            self.metrics.gauge('system.cpu.percent', cpu)
            self.metrics.gauge('system.memory.available_mb', memory.available / 1024 / 1024)

            time.sleep(10)

    def start(self):
        """Start orchestrator"""
        self._running = True

        # Start web server
        self.start_web_server()

        # Start monitoring
        monitor_thread = threading.Thread(target=self.run_monitoring_loop, daemon=True)
        monitor_thread.start()

        logger.info("Production orchestrator started")

    def stop(self):
        """Stop orchestrator"""
        self._running = False
        if self.web_server:
            self.web_server.shutdown()
        logger.info("Production orchestrator stopped")

def main():
    """Main entry point"""
    orchestrator = ProductionOrchestrator()
    orchestrator.start()

    print(f"✨ Production Orchestrator Started")
    print(f"📊 Dashboard: http://localhost:{WEB_PORT}")
    print()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "add":
            if len(sys.argv) < 4:
                print("Usage: add <name> <command> [priority]")
                sys.exit(1)

            priority = int(sys.argv[4]) if len(sys.argv) > 4 else 0
            task_id = orchestrator.queue.add_task(sys.argv[2], sys.argv[3], priority=priority)
            print(f"Added task {task_id}")

        elif cmd == "worker":
            # Run worker
            worker_id = f"worker-{os.getpid()}"
            hostname = os.uname().nodename

            print(f"Worker {worker_id} started")
            while True:
                try:
                    # Update worker status
                    process = psutil.Process()
                    orchestrator.queue.update_worker(
                        worker_id, hostname, os.getpid(),
                        process.cpu_percent(), process.memory_info().rss / 1024 / 1024
                    )

                    # Get next task
                    task = orchestrator.queue.get_next_task(worker_id)
                    if task:
                        print(f"Processing task {task['id']}: {task['name']}")
                        start = time.time()
                        start_cpu = time.process_time()

                        # Execute
                        result = subprocess.run(
                            task['command'],
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=300
                        )

                        cpu_time = int((time.process_time() - start_cpu) * 1000)
                        memory = process.memory_info().rss / 1024 / 1024

                        orchestrator.queue.complete_task(
                            task['id'],
                            result.returncode == 0,
                            result.stdout[:1000] if result.returncode == 0 else result.stderr[:1000],
                            cpu_time,
                            memory
                        )
                    else:
                        time.sleep(1)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logger.error(f"Worker error: {e}")
                    time.sleep(5)

        elif cmd == "test":
            # Add test tasks
            print("Adding test tasks...")
            for i in range(10):
                orchestrator.queue.add_task(
                    f"test_{i}",
                    f"sleep {i % 3 + 1} && echo 'Task {i} complete'",
                    priority=i % 3
                )
            print("Added 10 test tasks")

        else:
            print(f"Unknown command: {cmd}")
            print("Commands: add, worker, test")

    else:
        print("Commands:")
        print("  add <name> <command> [priority] - Add a task")
        print("  worker - Start a worker")
        print("  test - Add test tasks")
        print()

        # Keep running for web dashboard
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    orchestrator.stop()

if __name__ == "__main__":
    main()