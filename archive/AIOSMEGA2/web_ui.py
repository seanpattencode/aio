#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AIOS Dashboard</title>
    <meta charset="utf-8">
    <style>
        body { font-family: monospace; background: #1a1a1a; color: #0f0; margin: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .section { background: #000; border: 1px solid #0f0; padding: 15px; margin: 10px 0; }
        h1, h2 { color: #0f0; }
        .task { padding: 5px; margin: 2px 0; }
        .task.done { color: #666; text-decoration: line-through; }
        .task.progress { color: #ff0; }
        .task.failed { color: #f00; }
        .terminal { background: #000; color: #0f0; padding: 10px; height: 300px;
                   overflow-y: scroll; font-size: 14px; border: 1px solid #0f0; }
        input { background: #111; color: #0f0; border: 1px solid #0f0; padding: 5px; width: 80%; }
        button { background: #0f0; color: #000; border: none; padding: 5px 15px; cursor: pointer; }
        button:hover { background: #0a0; }
        .status { position: fixed; top: 10px; right: 10px; padding: 10px; background: #111;
                 border: 1px solid #0f0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🖥️ AIOS Dashboard</h1>

        <div class="status" id="status">
            Last Update: <span id="lastUpdate">-</span>
        </div>

        <div class="section">
            <h2>📋 Tasks</h2>
            <div id="tasks">Loading...</div>
        </div>

        <div class="section">
            <h2>📅 Daily Plan</h2>
            <div id="plan">Loading...</div>
        </div>

        <div class="section">
            <h2>💻 Terminal</h2>
            <div class="terminal" id="terminal"></div>
            <input type="text" id="command" placeholder="Enter command..." onkeypress="if(event.key=='Enter')runCommand()">
            <button onclick="runCommand()">Run</button>
        </div>
    </div>

    <script>
        function loadTasks() {
            fetch('/api/tasks').then(r => r.json()).then(data => {
                let html = '';
                data.tasks.forEach(task => {
                    let cls = task.includes('[x]') ? 'done' : task.includes('[>]') ? 'progress' :
                             task.includes('[!]') ? 'failed' : '';
                    html += '<div class="task ' + cls + '">' + task + '</div>';
                });
                document.getElementById('tasks').innerHTML = html || 'No tasks';
            });
        }

        function loadPlan() {
            fetch('/api/plan').then(r => r.json()).then(data => {
                document.getElementById('plan').innerHTML = '<pre>' + (data.plan || 'No plan') + '</pre>';
            });
        }

        function loadStatus() {
            fetch('/api/status').then(r => r.json()).then(data => {
                document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
            });
        }

        function runCommand() {
            let cmd = document.getElementById('command').value;
            if (!cmd) return;

            fetch('/api/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({command: cmd})
            }).then(r => r.json()).then(data => {
                let term = document.getElementById('terminal');
                term.innerHTML += '$ ' + cmd + '\\n' + data.output + '\\n';
                term.scrollTop = term.scrollHeight;
                document.getElementById('command').value = '';
            });
        }

        setInterval(() => { loadTasks(); loadPlan(); loadStatus(); }, 5000);
        loadTasks(); loadPlan(); loadStatus();
    </script>
</body>
</html>
"""

class WebUI:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"

    def get_tasks(self):
        tasks_file = self.aios_dir / "tasks.txt"
        if tasks_file.exists():
            with open(tasks_file) as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def get_plan(self):
        plan_file = self.aios_dir / "daily_plan.md"
        if plan_file.exists():
            with open(plan_file) as f:
                return f.read()
        return "No plan available"

    def get_status(self):
        status_file = self.aios_dir / "status.json"
        if status_file.exists():
            with open(status_file) as f:
                return json.load(f)
        return {}

web_ui = WebUI()

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/tasks')
def api_tasks():
    return jsonify({'tasks': web_ui.get_tasks()})

@app.route('/api/plan')
def api_plan():
    return jsonify({'plan': web_ui.get_plan()})

@app.route('/api/status')
def api_status():
    return jsonify(web_ui.get_status())

@app.route('/api/run', methods=['POST'])
def api_run():
    cmd = request.json.get('command', '')
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        output = result.stdout + result.stderr
    except Exception as e:
        output = f"Error: {e}"
    return jsonify({'output': output[:1000]})  # Limit output

if __name__ == '__main__':
    import socket
    # Find available port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()

    print(f"🌐 AIOS Web UI running at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)