#!/usr/bin/env python3
"""Gemini & Claude analyze all Sean's notes for actionable insights"""
import subprocess,shutil,os,re,sys,sqlite3
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from agent_base import send

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
claude=shutil.which('claude')or os.path.expanduser('~/.local/bin/claude')

# Get all notes
ndb=sqlite3.connect(os.path.expanduser("~/.local/share/aios/aio.db"))
notes=ndb.execute("SELECT t,c FROM notes WHERE s=0 AND length(t)>15 AND t NOT GLOB '[A-Z][0-9]*' ORDER BY c DESC").fetchall()
ndb.close()
NOTES="\n".join(f"- {n[0]}" for n in notes) if notes else "(no notes)"

CONTEXT=f"""Sean's goals: AIOS (AI workflow CLI), billion-dollar solo startup, AGI alignment, learn from experts, maximize value.

ALL NOTES ({len(notes)} total):
{NOTES}"""

def ask_gemini(prompt):
    r=subprocess.run([gemini,prompt],capture_output=True,text=True,timeout=300)
    return r.stdout.strip()

def ask_claude(prompt):
    r=subprocess.run([claude,'-p','--allowedTools',''],input=prompt,capture_output=True,text=True,timeout=180)
    return r.stdout.strip()

# Gemini analyzes
print(f"=== Analyzing {len(notes)} notes ===\n")
g=ask_gemini(f"{CONTEXT}\n\nAnalyze these notes. What patterns emerge? What's Sean neglecting? What should be prioritized? Reply: <patterns>key themes</patterns><neglected>what's missing</neglected><priority>top 3 actions</priority>")
print(f"Gemini:\n{g}\n")

# Claude synthesizes
c=ask_claude(f"{CONTEXT}\n\nGemini's analysis: {g}\n\nSynthesize into ONE clear directive for this week. Reply ONLY: <directive>specific focus</directive><why>reasoning</why>")
print(f"Claude:\n{c}")

d=re.search(r'<directive>([^<]+)</directive>',c)
w=re.search(r'<why>([^<]+)</why>',c)

msg=f"Notes Analysis ({len(notes)} notes)\n\n{g}\n\n{'='*40}\nDIRECTIVE: {d[1] if d else 'See above'}\nWHY: {w[1] if w else ''}"
print(f"\n{'='*40}\n{msg}")
if "--send" in sys.argv: send("📝 Notes Analysis",msg)
