"""aio review - Show GitHub PRs"""
import subprocess as sp
def run():
    prs = sp.run(['gh', 'search', 'prs', '--author', '@me', '--state', 'open', '--json', 'repository,number,title'], capture_output=True, text=True).stdout
    items = __import__('json').loads(prs) if prs.strip() else []
    [print(f"  {i}. {p['repository']['nameWithOwner']}#{p['number']} {p['title']}") for i, p in enumerate(items)] or print("  (none)")
    if not items: return
    c = input("> ").strip()
    if not c.split()[0].isdigit(): return
    p = items[int(c.split()[0])]; repo, num = p['repository']['nameWithOwner'], str(p['number'])
    sp.run(f'D=/tmp/pr-{num};rm -rf $D&&gh repo clone {repo} $D >/dev/null 2>&1&&cd $D&&gh pr checkout {num} >/dev/null 2>&1&&aio diff main', shell=True)
    act = input("[m]erge [c]lose [r]un > ").strip().lower()
    if act == 'm': sp.run(['gh', 'pr', 'merge', '--repo', repo, num, '--squash', '--delete-branch'])
    elif act == 'c': sp.run(['gh', 'pr', 'close', '--repo', repo, num, '--delete-branch'])
    elif act == 'r': sp.run(f"cd /tmp/pr-{num}&&python3 agent.py", shell=True)
