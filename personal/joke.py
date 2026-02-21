#!/usr/bin/env python3
"""Gemini generates 10 jokes, judges them, sends the best one"""
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')

# Generate 10 jokes
r=subprocess.run([gemini,'-p','Write 10 short jokes (tech/programming/AI themed). Number them 1-10. One line each.'],capture_output=True,text=True,timeout=300)
jokes=r.stdout.strip()
print(f"Generated jokes:\n{jokes}\n")

# Judge them
r2=subprocess.run([gemini,'-p',f'Here are 10 jokes:\n{jokes}\n\nPick the FUNNIEST one. Reply ONLY: <winner>the joke text</winner><why>5 words why its funny</why>'],capture_output=True,text=True,timeout=300)
w,y=re.search(r'<winner>([^<]+)</winner>',r2.stdout),re.search(r'<why>([^<]+)</why>',r2.stdout)

best=w[1].strip() if w else jokes.split('\n')[0]
why=y[1].strip() if y else ""

out=f"Winner: {best}\nWhy: {why}\n\nAll jokes:\n{jokes}"
print(f"Winner: {best}\nWhy: {why}")
save("g-joke",out)
if "--send" in sys.argv: send("Daily Joke",f"{best}\n\n(Selected from 10 candidates: {why})")
