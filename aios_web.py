#!/usr/bin/env python3
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import psutil
from datetime import datetime
from typing import Dict
import anthropic
import os

app = FastAPI()
services_db = Path.home() / ".aios" / "services.json"
services_db.parent.mkdir(exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>AIOS Control Center</title>
    <style>
        body { font-family: monospace; background: #1a1a1a; color: #0f0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .service { background: #2a2a2a; padding: 10px; margin: 10px 0; border-radius: 5px; display: flex; justify-content: space-between; }
        button { background: #0f0; color: #000; border: none; padding: 5px 15px; cursor: pointer; margin: 0 5px; }
        input { background: #2a2a2a; color: #0f0; border: 1px solid #0f0; padding: 10px; width: 100%; margin: 10px 0; }
        #terminal { background: #000; padding: 10px; height: 300px; overflow-y: scroll; margin: 20px 0; border: 1px solid #0f0; }
        .status-running { color: #0f0; }
        .status-stopped { color: #f00; }
    </style>
</head>
<body>
    <div class="container">
        <h1>AIOS Control Center</h1>
        <div id="services"></div>
        <input type="text" id="aiPrompt" placeholder="Ask AI to manage services...">
        <button onclick="sendAI()">Send</button>
        <div id="terminal"></div>
    </div>
    <script>
        async function loadServices() {
            const resp = await fetch('/api/services');
            const services = await resp.json();
            const html = Object.entries(services).map(([name, data]) =>
                `<div class="service">
                    <span>${name} - <span class="${data.status === 'running' ? 'status-running' : 'status-stopped'}">${data.status || 'stopped'}</span></span>
                    <div>
                        <button onclick="controlService('${name}', 'start')">Start</button>
                        <button onclick="controlService('${name}', 'stop')">Stop</button>
                        <button onclick="controlService('${name}', 'restart')">Restart</button>
                    </div>
                </div>`
            ).join('');
            document.getElementById('services').innerHTML = html;
        }

        async function controlService(name, action) {
            await fetch(`/api/service/${name}/${action}`, {method: 'POST'});
            loadServices();
        }

        async function sendAI() {
            const prompt = document.getElementById('aiPrompt').value;
            const resp = await fetch('/ai', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({prompt})
            });
            const data = await resp.json();
            document.getElementById('terminal').innerHTML += `<div>&gt; ${prompt}</div><div>${data.response}</div>`;
            document.getElementById('aiPrompt').value = '';
            loadServices();
        }

        setInterval(loadServices, 2000);
        loadServices();
    </script>
</body>
</html>
"""

@app.get("/api/services")
async def get_services():
    data = json.loads(services_db.read_text() or '{}')
    return data

@app.post("/api/service/{name}/{action}")
async def control_service(name: str, action: str):
    data = json.loads(services_db.read_text() or '{}')
    data.setdefault(name, {})['status'] = 'running' if action == 'start' else 'stopped'
    data[name]['updated'] = datetime.now().isoformat()
    services_db.write_text(json.dumps(data))
    return {"status": "ok"}

@app.post("/ai")
async def ai_endpoint(request: Request):
    body = await request.json()
    data = json.loads(services_db.read_text() or '{}')
    prompt_lower = body['prompt'].lower()
    actions = [w for w in prompt_lower.split() if w in ['start', 'stop', 'restart', 'status']]
    services = [w for w in body['prompt'].split() if w in data.keys()]

    [data.update({s: {'status': 'running' if a == 'start' else 'stopped' if a == 'stop' else 'running', 'updated': datetime.now().isoformat()}}) for s in services for a in actions[:1]]

    response_text = f"Executed: {actions[0]} {services[0]}" if actions and services else (
        f"Available services: {', '.join(data.keys())}. Commands: start, stop, restart, status. Example: 'start backup'"
        if 'how' in prompt_lower or 'help' in prompt_lower or 'what' in prompt_lower else
        f"Services: {', '.join([f'{k}({v.get('status', 'stopped')})' for k,v in data.items()])}" if 'status' in prompt_lower else
        "Please specify: [action] [service]. Actions: start/stop/restart. Services: " + ', '.join(data.keys())
    )

    services_db.write_text(json.dumps(data))
    return {"response": response_text}