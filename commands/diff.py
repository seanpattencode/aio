"""aio diff - show git changes"""
import subprocess as sp, os, re, sys

def run(args):
    sp.run(['git', 'fetch', 'origin'], capture_output=True)
    cwd = os.getcwd()
    b = sp.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True).stdout.strip()
    target = 'origin/main' if b.startswith('wt-') else f'origin/{b}'
    diff = sp.run(['git', 'diff', target], capture_output=True, text=True).stdout
    untracked = sp.run(['git', 'ls-files', '--others', '--exclude-standard'], capture_output=True, text=True).stdout.strip()
    print(f"{cwd}\n{b} -> {target}")
    if not diff and not untracked: print("No changes"); sys.exit(0)
    G, R, X, f = '\033[48;2;26;84;42m', '\033[48;2;117;34;27m', '\033[0m', ''
    for L in diff.split('\n'):
        if L.startswith('diff --git'): f = L.split(' b/')[-1]
        elif L.startswith('@@'): m = re.search(r'\+(\d+)', L); print(f"\n{f} line {m.group(1)}:" if m else "")
        elif L.startswith('+') and not L.startswith('+++'): print(f"  {G}+ {L[1:]}{X}")
        elif L.startswith('-') and not L.startswith('---'): print(f"  {R}- {L[1:]}{X}")
    if untracked: print(f"\nUntracked:\n" + '\n'.join(f"  {G}+ {u}{X}" for u in untracked.split('\n')))
    stat = sp.run(['git', 'diff', target, '--shortstat'], capture_output=True, text=True).stdout.strip()
    ins = int(re.search(r'(\d+) insertion', stat).group(1)) if 'insertion' in stat else 0
    dels = int(re.search(r'(\d+) deletion', stat).group(1)) if 'deletion' in stat else 0
    stat and print(f"\n{stat} | Net: {'+' if ins-dels >= 0 else ''}{ins-dels} lines")
