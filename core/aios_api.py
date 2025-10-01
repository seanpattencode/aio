#!/usr/bin/env python3
from fastapi import FastAPI, Request
import sys
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db, uvicorn
app = FastAPI()
@app.get("/data/{name}")
async def get_data(name: str):
    return aios_db.read(name)
@app.post("/data/{name}")
async def post_data(name: str, request: Request):
    return aios_db.write(name, await request.json())
@app.post("/event/{target}")
async def emit_event(target: str, request: Request):
    aios_db.execute("events", "INSERT INTO events(target, data) VALUES (?, ?)", (target, (await request.body()).decode()))
    return {"status": "ok"}
@app.get("/status")
async def status():
    aios_db.write("services", {})
    aios_db.write("tasks", [])
    aios_db.write("schedule", {})
    return {"services": aios_db.read("services"), "tasks": aios_db.read("tasks"), "schedule": aios_db.read("schedule")}
uvicorn.run(app, host="0.0.0.0", port=8000)