#!/usr/bin/env python3
"""Minimal ollama agent: cmd exec, memory, loop, feedback."""
import subprocess,ollama,sys

MODEL=sys.argv[1]if len(sys.argv)>1 else"mistral"
SYS="Linux CLI agent. To run a command, your ENTIRE reply must be: CMD: <command>\nNothing else. One command per reply. After seeing output, answer in plain text."
mem=[]

while True:
    u=input("\n> ").strip()
    if not u:continue
    mem.append({"role":"user","content":u})
    while True:
        t=ollama.chat(MODEL,[{"role":"system","content":SYS}]+mem[-20:]).message.content.strip()
        print(t);mem.append({"role":"assistant","content":t})
        if not t.startswith("CMD:"):break
        cmd=t.split("\n")[0][4:].strip();print(f"$ {cmd}")
        try:o=subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=30)
        except Exception as e:o=type('',(),{'stdout':'','stderr':str(e)})()
        out=(o.stdout+o.stderr).strip()or"(no output)";print(out)
        mem.append({"role":"user","content":f"Output of `{cmd}`:\n{out}"})
