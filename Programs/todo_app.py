#!/usr/bin/env python3
import os, json, time, logging, threading, asyncio, socket
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import deque
from dataclasses import dataclass, field
import sqlite3
import sys
from pathlib import Path

# Use orchestrator database
ROOT_DIR = Path(__file__).parent.parent
DB_PATH = ROOT_DIR / "orchestrator.db"

# Setup logging to work with orchestrator
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# --- Model ---
@dataclass
class Task:
    description: str
    recurrence_time: str | None = None
    essential: bool = False
    task_id: int | None = None
    id: int = field(init=False)
    completed_dates: list = field(default_factory=list)
    skipped_dates: list = field(default_factory=list)
    created: datetime = field(default_factory=datetime.now)
    archived: bool = False

    def __post_init__(self):
        self.id = self.task_id or int(time.time() * 1000)
        if not self.recurrence_time:
            self.recurrence_time = datetime.now().strftime("%H:%M")

    def to_dict(self):
        return {
            "id": self.id, "description": self.description,
            "recurrence_time": self.recurrence_time, "essential": self.essential,
            "completed_dates": list(self.completed_dates),
            "skipped_dates": list(self.skipped_dates),
            "created": self.created.isoformat(), "archived": self.archived
        }

    @classmethod
    def from_dict(cls, d):
        t = cls(d["description"], d["recurrence_time"], d["essential"], d["id"])
        t.completed_dates = d.get("completed_dates", [])
        t.skipped_dates = d.get("skipped_dates", [])
        t.created = datetime.fromisoformat(d["created"])
        t.archived = d.get("archived", False)
        return t

    @property
    def streak(self):
        if not self.completed_dates: return 0
        days = sorted({datetime.fromisoformat(x).date() for x in self.completed_dates})
        s = 1
        for i in range(len(days) - 1, 0, -1):
            if (days[i] - days[i - 1]).days == 1: s += 1
            else: break
        return s

    def next_occurrence(self):
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        t = datetime.strptime(self.recurrence_time, "%H:%M").time()
        dt = datetime.combine(now.date(), t)
        return dt + timedelta(days=1) if any(x.startswith(today) for x in self.completed_dates) or today in self.skipped_dates else dt

# --- App ---
class TodoApp:
    def __init__(self):
        self.tasks: list[Task] = []
        self.logs = deque(maxlen=100)
        self.db_path = DB_PATH
        self.init_db()
        self.load_tasks()
        self.log(f"Todo app initialized")

    def log(self, msg):
        self.logs.append(f"{datetime.now().isoformat()}: {msg}")
        logging.info(msg)

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Create todo_tasks table in orchestrator DB
        c.execute('''
            CREATE TABLE IF NOT EXISTS todo_tasks (
                id INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                recurrence_time TEXT,
                essential INTEGER DEFAULT 0,
                completed_dates TEXT DEFAULT '[]',
                skipped_dates TEXT DEFAULT '[]',
                created TEXT NOT NULL,
                archived INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()

    def add_task(self, desc, rt=None, essential=False):
        task = Task(desc, rt, essential)
        self.tasks.append(task)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT INTO todo_tasks (id, description, recurrence_time, essential,
            completed_dates, skipped_dates, created, archived)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (task.id, task.description, task.recurrence_time, int(task.essential),
              json.dumps(task.completed_dates), json.dumps(task.skipped_dates),
              task.created.isoformat(), int(task.archived)))
        conn.commit()
        conn.close()
        self.log(f"Added task: {desc}")

    def edit_task(self, task_id, description=None, recurrence_time=None, essential=None):
        for t in self.tasks:
            if t.id == task_id:
                if description is not None: t.description = description
                if recurrence_time is not None: t.recurrence_time = recurrence_time
                if essential is not None: t.essential = essential
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute('''
                    UPDATE todo_tasks SET description = ?, recurrence_time = ?, essential = ?
                    WHERE id = ?
                ''', (t.description, t.recurrence_time, int(t.essential), t.id))
                conn.commit()
                conn.close()
                self.log(f"Edited task {task_id}")
                return

    def complete_task(self, task_id, completed=True):
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        for t in self.tasks:
            if t.id == task_id:
                if completed:
                    t.completed_dates.append(now.isoformat())
                    if today in t.skipped_dates: t.skipped_dates.remove(today)
                    self.log(f"Completed task: {t.description}")
                else:
                    t.completed_dates = [d for d in t.completed_dates if not d.startswith(today)]
                    if today not in t.skipped_dates: t.skipped_dates.append(today)
                    self.log(f"Marked not complete: {t.description}")
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute('''
                    UPDATE todo_tasks SET completed_dates = ?, skipped_dates = ?
                    WHERE id = ?
                ''', (json.dumps(t.completed_dates), json.dumps(t.skipped_dates), t.id))
                conn.commit()
                conn.close()
                return

    def archive_task(self, task_id):
        for t in self.tasks:
            if t.id == task_id:
                t.archived = True
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute('UPDATE todo_tasks SET archived = 1 WHERE id = ?', (t.id,))
                conn.commit()
                conn.close()
                self.log(f"Archived task: {t.description}")
                return

    def get_tasks(self, flt="next"):
        now = datetime.now()
        vis = [t for t in self.tasks if not t.archived]
        if flt == "all": base = vis
        elif flt == "essential": base = [t for t in vis if t.essential]
        elif flt == "future": base = [t for t in vis if t.next_occurrence().date() > now.date()]
        else: base = vis
        out = sorted(base, key=lambda x: x.next_occurrence())
        return out[:4] if flt == "next" else out

    def load_tasks(self):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            rows = c.execute('SELECT * FROM todo_tasks').fetchall()
            for row in rows:
                d = {
                    "id": row[0],
                    "description": row[1],
                    "recurrence_time": row[2],
                    "essential": bool(row[3]),
                    "completed_dates": json.loads(row[4]),
                    "skipped_dates": json.loads(row[5]),
                    "created": row[6],
                    "archived": bool(row[7])
                }
                self.tasks.append(Task.from_dict(d))
            conn.close()
            if not self.tasks: self._seed_defaults()
        except Exception as e:
            self.log(f"Error loading tasks: {e}")
            self._seed_defaults()

    def _seed_defaults(self):
        defaults = ["coding","work task","gre prep question","physical therapy exercises","Plan next 24 hrs",
                    "Answer one top question","review/rank 16 tasks","ask future success method","start schedule usage",
                    "read one ai development","read bio book","read direct top material","noot 1, spices, creatine",
                    "noot 2, spices","noot 3, spices","noot 4, spices, garlic"]
        start_hour = 8
        for i, d in enumerate(defaults):
            self.add_task(d, f"{(start_hour+i)%24:02d}:00", i % 4 == 0)

# Global app instance
app = None

# --- HTTP ---
class TodoRequestHandler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        self.send_response(code)
        self.send_header('Content-type','application/json')
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def _html(self, html):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()
        self.wfile.write(html.encode())

    def do_GET(self):
        p = urlparse(self.path).path
        if p == '/':
            self._html(generate_html())
        elif p == '/api/tasks':
            flt = parse_qs(urlparse(self.path).query).get('filter',['next'])[0]
            ts = [{"id":t.id,"description":t.description,"recurrence_time":t.recurrence_time,
                   "essential":t.essential,"streak":t.streak,"next_occurrence":t.next_occurrence().isoformat()}
                  for t in app.get_tasks(flt)]
            self._json(ts)
        elif p == '/api/logs':
            self._json(list(app.logs))
        elif p.startswith('/api/task/'):
            tid = int(p.split('/')[-1])
            for t in app.tasks:
                if t.id == tid:
                    self._json({"completion_dates":t.completed_dates,"streak":t.streak,"created":t.created.isoformat()})
                    return
            self._json({"error":"not found"}, 404)
        else:
            self._json({"error":"not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        data = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
        if p == '/api/add_task':
            desc = data.get('description',[''])[0]
            rt = data.get('recurrence_time',[None])[0]
            if desc: app.add_task(desc, rt, False)
            self._json({"status":"ok"})
        elif p == '/api/complete_task':
            app.complete_task(int(data.get('task_id',[0])[0]),
                            data.get('completed',['true'])[0].lower()=='true')
            self._json({"status":"ok"})
        elif p == '/api/edit_task':
            tid = int(data.get('task_id',[0])[0])
            desc = data.get('description',[None])[0]
            rt = data.get('recurrence_time',[None])[0]
            e = data.get('essential',[None])[0]
            app.edit_task(tid, desc, rt, (e.lower()=='true') if e is not None else None)
            self._json({"status":"ok"})
        elif p == '/api/archive_task':
            app.archive_task(int(data.get('task_id',[0])[0]))
            self._json({"status":"ok"})
        else:
            self._json({"error":"not found"}, 404)

    def log_message(self, fmt, *args):
        pass  # Suppress default logging

# --- HTML ---
def generate_html():
    return """<!DOCTYPE html>
<html>
<head>
  <title>Todo App</title>
  <style>
    body{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#f5f5f5}
    .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    .card{background:#fff;padding:12px;border-radius:6px;box-shadow:0 2px 4px rgba(0,0,0,.1);margin:10px 0}
    .essential{border-left:4px solid #ff6b6b}
    .small{color:#666;font-size:13px}
    button{padding:6px 10px;border:0;border-radius:4px;cursor:pointer}
    .green{background:#4caf50;color:#fff}.orange{background:#ff9800;color:#fff}.blue{background:#03a9f4;color:#fff}
    .filter{background:#2196f3;color:#fff}.active{background:#0d47a1}
    #logs{background:#333;color:#fff;padding:12px;border-radius:6px;max-height:200px;overflow:auto;font:12px/1.4 monospace}
    .hidden{display:none}
    .dropdown{position:relative;display:inline-block}
    .menu{display:none;position:absolute;background:#f9f9f9;min-width:140px;box-shadow:0 8px 16px rgba(0,0,0,.2);border-radius:6px;z-index:2}
    .menu button{width:100%;background:none;color:#000;text-align:left;padding:10px}
    .menu button:hover{background:#f1f1f1}
    .time-editor{position:absolute;background:#fff;border:1px solid #ddd;padding:8px;border-radius:6px;box-shadow:0 2px 4px rgba(0,0,0,.1)}
  </style>
</head>
<body>
  <div class="row" style="justify-content:space-between;margin-bottom:10px">
    <h1>Todo App</h1>
  </div>
  <div class="row">
    <button class="filter active" onclick="setFilter('next',this)">Next 4</button>
    <button class="filter" onclick="setFilter('future',this)">Future</button>
    <button class="filter" onclick="setFilter('essential',this)">Essential</button>
    <button class="filter" onclick="setFilter('all',this)">All</button>
  </div>
  <div class="card row">
    <input id="desc" type="text" placeholder="Task description" style="flex:1;padding:6px;border:1px solid #ddd;border-radius:4px">
    <input id="time" type="time" style="padding:6px;border:1px solid #ddd;border-radius:4px">
    <button class="green" onclick="addTask()">Add Task</button>
  </div>
  <div id="tasks"></div>
  <div id="logs" class="hidden"></div>
<script>
const q = s => document.querySelector(s);
const qa = s => [...document.querySelectorAll(s)];
const get = p => fetch(p).then(r=>r.json());
const post = (p,o) => fetch(p,{method:'POST',body:new URLSearchParams(o)});
let filter='next', tasks=[], editor=null;

function toggleMenu(e){
  e.stopPropagation();
  const m=e.target.nextElementSibling;
  if(m) m.style.display = m.style.display==='block'?'none':'block';
}
window.onclick = e => {
  if(!e.target.matches('.dropdown button')) {
    qa('.menu').forEach(m => m.style.display='none');
  }
};
function setFilter(f,btn){
  filter=f;
  qa('.filter').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  load();
}
async function load(){
  tasks = await get(`/api/tasks?filter=${filter}`);
  render();
}
function render(){
  const c = q('#tasks');
  c.innerHTML='';
  tasks.forEach(t=>{
    const el = document.createElement('div');
    el.className = `card ${t.essential?'essential':''}`;
    el.innerHTML = `
      <div class="row" style="justify-content:space-between">
        <span style="font-weight:bold">${t.description}</span>
        <span class="small">${t.recurrence_time}</span>
      </div>
      <div class="small">Streak: ${t.streak} | Next: ${new Date(t.next_occurrence).toLocaleString()}</div>
      <div class="row" style="margin-top:8px">
        <button class="green" onclick="complete(${t.id},true)">Complete</button>
        <button class="orange" onclick="complete(${t.id},false)">Not Complete</button>
        <button class="blue" onclick="openTime(${t.id},event)">Edit Time</button>
        <div class="dropdown">
          <button onclick="toggleMenu(event)">More</button>
          <div class="menu">
            <button onclick="editName(${t.id})">Edit Name</button>
            <button onclick="toggleEssential(${t.id})">${t.essential?'Unmark Essential':'Mark Essential'}</button>
            <button onclick="showStats(${t.id})">Stats</button>
            <button onclick="archive(${t.id})">Archive</button>
          </div>
        </div>
      </div>`;
    c.appendChild(el);
  });
}
async function addTask(){
  const d=q('#desc').value.trim(), tm=q('#time').value;
  if(!d) return;
  await post('/api/add_task',{description:d,recurrence_time:tm});
  q('#desc').value='';
  q('#time').value='';
  load();
}
async function complete(id, done){
  await post('/api/complete_task',{task_id:id,completed:done});
  load();
}
async function toggleEssential(id){
  const t = tasks.find(x=>x.id===id);
  await post('/api/edit_task',{task_id:id,essential:!t.essential});
  load();
}
async function editName(id){
  const t = tasks.find(x=>x.id===id);
  const nd = prompt('Edit task description:', t.description);
  if(nd===null || nd.trim()==='' || nd===t.description) return;
  await post('/api/edit_task',{task_id:id,description:nd});
  load();
}
function openTime(id,ev){
  if(editor) closeEditor();
  const t = tasks.find(x=>x.id===id);
  if(!t) return;
  const ed = document.createElement('div');
  ed.className='time-editor';
  ed.innerHTML = `<input type="time" id="edit-time" value="${t.recurrence_time}"> <button onclick="saveTime(${id})">Save</button> <button onclick="closeEditor()">Cancel</button>`;
  ed.style.left = ev.pageX+'px';
  ed.style.top = ev.pageY+'px';
  document.body.appendChild(ed);
  editor=ed;
  q('#edit-time').focus();
  setTimeout(()=>document.addEventListener('click', outside),0);
  function outside(e){ if(!ed.contains(e.target)) closeEditor(); }
  ed.outside = outside;
}
async function saveTime(id){
  const v=q('#edit-time').value;
  const t=tasks.find(x=>x.id===id);
  if(v===t.recurrence_time){ closeEditor(); return; }
  await post('/api/edit_task',{task_id:id,recurrence_time:v});
  closeEditor();
  load();
}
function closeEditor(){
  if(editor){
    document.removeEventListener('click', editor.outside);
    editor.remove();
    editor=null;
  }
}
async function archive(id){
  if(!confirm('Archive this task?')) return;
  await post('/api/archive_task',{task_id:id});
  load();
}
async function showStats(id){
  const s = await get(`/api/task/${id}`);
  const times = s.completion_dates.map(d=>new Date(d).toLocaleString()).join('\\n');
  alert(`Completion Times:\\n${times}\\n\\nStreak: ${s.streak}`);
}
load();
setInterval(load,5000);
</script>
</body>
</html>"""

# --- Server entry point for orchestrator ---
def run_todo_server(*args, **kwargs):
    """Entry point for orchestrator to run the todo app"""
    global app

    # Get IP to bind to - use all interfaces for cloud deployment
    host = '0.0.0.0'
    port = 8080  # Standard port for web services

    app = TodoApp()

    server = HTTPServer((host, port), TodoRequestHandler)
    print(f"Todo app server started on http://{host}:{port}")
    logging.info(f"Todo app serving on {host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    return "Todo server stopped"