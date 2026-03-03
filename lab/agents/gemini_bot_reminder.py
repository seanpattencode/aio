#!/usr/bin/env python3
"""Remind Sean to keep making bots for goals"""
import subprocess,shutil,os,re,sys,sqlite3
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from agent_base import send

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')

# Count bots
bot_dir=os.path.dirname(os.path.abspath(__file__))
bots=[f for f in os.listdir(bot_dir) if f.startswith('gemini_') and f.endswith('.py')]

r=subprocess.run([gemini,f'Sean has {len(bots)} email bots. His goals: AIOS, billion-dollar solo startup, AGI alignment. Suggest ONE new bot idea that would help these goals. Reply ONLY: <idea>bot name and purpose in 10 words</idea><why>how it helps goals</why>'],capture_output=True,text=True,timeout=300)
i,w=re.search(r'<idea>([^<]+)</idea>',r.stdout),re.search(r'<why>([^<]+)</why>',r.stdout)

msg=f"Bot Factory Reminder\n\nCurrent bots: {len(bots)}\n\nNEXT BOT IDEA: {i[1] if i else 'check output'}\nWHY: {w[1] if w else r.stdout[:200]}\n\nKeep building. Each bot compounds your leverage."
print(msg)
if "--send" in sys.argv: send("🤖 Make Another Bot",msg)
