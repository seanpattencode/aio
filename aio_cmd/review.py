"""aio review - Show GitHub PRs"""
import subprocess as sp
def run():
    prs = sp.run(['gh', 'search', 'prs', '--author', '@me', '--state', 'open', '--json', 'repository,number,title'], capture_output=True, text=True).stdout
    items = __import__('json').loads(prs) if prs.strip() else []
    [print(f"  {i}. {p['repository']['nameWithOwner']}#{p['number']} {p['title']}") for i, p in enumerate(items)] or print("  (none)")
    if items and (c := input("> ").strip()).isdigit() and int(c) < len(items): p = items[int(c)]; sp.run(['gh', 'pr', 'view', '--repo', p['repository']['nameWithOwner'], str(p['number']), '--web'])
