#!/usr/bin/env python3
"""Gemini & Claude 4-turn convo to help Sean with goals"""
import subprocess,shutil,os,re,sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from agent_base import send

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
claude=shutil.which('claude')or os.path.expanduser('~/.local/bin/claude')

CONTEXT="""Sean's goals: 1) Build AIOS - AI workflow manager CLI 2) First billion-dollar solo startup 3) Help align AGI 4) Learn optimally from top experts 5) Maximize value from actions. Be direct, no needless praise, challenge wrong directions."""

convo=[]

def ask_gemini(prompt):
    r=subprocess.run([gemini,prompt],capture_output=True,text=True,timeout=300)
    return r.stdout.strip()

def ask_claude(prompt):
    r=subprocess.run([claude,'-p','--allowedTools',''],input=prompt,capture_output=True,text=True,timeout=120)
    return r.stdout.strip()

# Turn 1: Gemini opens
print("=== Turn 1: Gemini ===")
g1=ask_gemini(f"{CONTEXT}\n\nWhat's the ONE highest-leverage thing Sean should focus on TODAY to advance these goals? Be specific and actionable. 3 sentences max.")
convo.append(f"Gemini: {g1}")
print(g1)

# Turn 2: Claude responds
print("\n=== Turn 2: Claude ===")
c1=ask_claude(f"{CONTEXT}\n\nGemini suggested: {g1}\n\nDo you agree or disagree? What's missing or wrong? What would you prioritize instead? 3 sentences max.")
convo.append(f"Claude: {c1}")
print(c1)

# Turn 3: Gemini counters
print("\n=== Turn 3: Gemini ===")
g2=ask_gemini(f"{CONTEXT}\n\nYou said: {g1}\n\nClaude responded: {c1}\n\nConsidering Claude's points, refine your recommendation. What's the synthesis? 3 sentences max.")
convo.append(f"Gemini: {g2}")
print(g2)

# Turn 4: Claude concludes
print("\n=== Turn 4: Claude ===")
c2=ask_claude(f"{CONTEXT}\n\nConversation so far:\n{chr(10).join(convo)}\n\nGive Sean ONE clear action for today with expected outcome. Reply ONLY: <action>specific task</action><why>10 words</why><outcome>what success looks like</outcome>")
convo.append(f"Claude: {c2}")
print(c2)

# Extract final recommendation
action=re.search(r'<action>([^<]+)</action>',c2)
why=re.search(r'<why>([^<]+)</why>',c2)
outcome=re.search(r'<outcome>([^<]+)</outcome>',c2)

summary=f"Gemini x Claude Collab\n\n{chr(10).join(convo)}\n\n{'='*40}\nFINAL ACTION: {action[1] if action else 'See above'}\nWHY: {why[1] if why else ''}\nOUTCOME: {outcome[1] if outcome else ''}"

print(f"\n{'='*40}\n{summary}")
if "--send" in sys.argv: send("🧠 Gemini x Claude: Today's Focus",summary)
