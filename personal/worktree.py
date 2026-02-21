#!/usr/bin/env python3
"""Analyze aio worktrees - branch changes, diff summary"""
import subprocess,shutil,os,re,sys
from base import send, save, AIO

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
claude=shutil.which('claude')or os.path.expanduser('~/.local/bin/claude')

AIO_DIR=os.path.dirname(os.path.dirname(AIO))
WT_DIR=os.path.expanduser("~/projects/aiosWorktrees")

def get_worktrees():
    if not os.path.isdir(WT_DIR): return []
    return [os.path.join(WT_DIR,d) for d in sorted(os.listdir(WT_DIR),reverse=True) if os.path.isdir(os.path.join(WT_DIR,d))][:5]

def get_diff(path):
    r=subprocess.run(['python3',AIO,'diff'],capture_output=True,text=True,cwd=path,timeout=30)
    return r.stdout.strip()[:2000]

def ask_gemini(prompt):
    r=subprocess.run([gemini,'-p',prompt],capture_output=True,text=True,timeout=300)
    return r.stdout.strip()

def ask_claude(prompt):
    r=subprocess.run([claude,'-p','--allowedTools','Read,Glob'],input=prompt,capture_output=True,text=True,timeout=180,cwd=AIO_DIR)
    return r.stdout.strip()

# Get worktrees
wts=get_worktrees()
print(f"Found {len(wts)} worktrees")

if not wts:
    print("No worktrees found")
    sys.exit(0)

reports=[]
for wt in wts[:3]:  # Limit to 3
    name=os.path.basename(wt)
    print(f"\n=== {name} ===")
    diff=get_diff(wt)
    if not diff or 'clean' in diff.lower():
        print("No changes")
        continue

    # Claude analyzes the diff
    c=ask_claude(f"Analyze this git diff from worktree {name}. What's being worked on? Is it good progress? Reply: <summary>2 sentences</summary><quality>GOOD/OK/NEEDS WORK</quality>\n\nDiff:\n{diff}")
    s=re.search(r'<summary>([^<]+)</summary>',c)
    q=re.search(r'<quality>([^<]+)</quality>',c)

    report=f"{name}\n{s[1] if s else c[:200]}\nQuality: {q[1] if q else 'UNKNOWN'}\n\nDiff preview:\n{diff[:500]}..."
    reports.append(report)
    print(report)

if not reports:
    print("No active worktrees with changes")
    sys.exit(0)

# Gemini synthesizes
g=ask_gemini(f"Given these worktree reports, what should Sean focus on?\n\n{chr(10).join(reports)}\n\nReply: <focus>which worktree and why</focus>")
f=re.search(r'<focus>([^<]+)</focus>',g)

msg=f"Worktree Analysis\n\n{chr(10).join(reports)}\n\n{'='*40}\nFOCUS: {f[1] if f else g}"
print(f"\n{msg}")
save("gc-worktree",msg)
if "--send" in sys.argv: send("Worktree Analysis",msg)
