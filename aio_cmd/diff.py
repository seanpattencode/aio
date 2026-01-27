"""aio diff [#] - Show git changes or token history"""
import sys, os, subprocess as sp, re

def _tok(d):
    try: enc = __import__('tiktoken').get_encoding('cl100k_base').encode; t = lambda s: len(enc(s))
    except: t = lambda s: len(s) // 4
    return t(''.join(L[1:] for L in d.split('\n') if L[:1]=='+' and L[1:2]!='+')) - t(''.join(L[1:] for L in d.split('\n') if L[:1]=='-' and L[1:2]!='-'))

def run():
    sel = sys.argv[2] if len(sys.argv) > 2 else None
    if sel and sel.isdigit():
        for i, L in enumerate(sp.run(['git', 'log', f'-{sel}', '--pretty=%H %s'], capture_output=True, text=True).stdout.strip().split('\n')):
            h, m = L.split(' ', 1); print(f"  {i}  {_tok(sp.run(['git', 'show', h, '--pretty='], capture_output=True, text=True).stdout):>+6}  {m[:55]}")
        return
    sp.run(['git', 'fetch', 'origin'], capture_output=True); cwd = os.getcwd()
    b = sp.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True).stdout.strip()
    target = 'origin/main' if b.startswith('wt-') else f'origin/{b}'
    committed = sp.run(['git', 'diff', f'{target}..HEAD'], capture_output=True, text=True).stdout
    uncommitted = sp.run(['git', 'diff', 'HEAD', '--diff-filter=d'], capture_output=True, text=True).stdout
    diff = committed + uncommitted
    untracked = sp.run(['git', 'ls-files', '--others', '--exclude-standard'], capture_output=True, text=True).stdout.strip()
    print(f"{cwd}\n{b} -> {target}")
    if not diff and not untracked: print("No changes\n\naio diff 5 = last 5 commits"); return
    try: enc = __import__('tiktoken').get_encoding('cl100k_base').encode; tok = lambda s: len(enc(s))
    except: tok = lambda s: len(s) // 4
    G, R, X, f, fstats = '\033[48;2;26;84;42m', '\033[48;2;117;34;27m', '\033[0m', '', {}
    for L in diff.split('\n'):
        if L.startswith('diff --git'): f = L.split(' b/')[-1]; fstats[f] = {'add': [], 'del': []}
        elif L.startswith('@@'): m = re.search(r'\+(\d+)', L); print(f"\n{f} line {m.group(1)}:" if m else "")
        elif L.startswith('+') and not L.startswith('+++'): print(f"  {G}+ {L[1:]}{X}"); fstats.get(f, {}).get('add', []).append(L[1:])
        elif L.startswith('-') and not L.startswith('---'): print(f"  {R}- {L[1:]}{X}"); fstats.get(f, {}).get('del', []).append(L[1:])
    ut = {f: open(f).read() for f in untracked.split() if f and os.path.isfile(f)} if untracked else {}
    if untracked: print(f"\nUntracked:\n" + '\n'.join(f"  {G}+ {u}{X}" for u in untracked.split('\n')))
    # Per-file stats
    print(f"\n{'─'*60}")
    for fn, st in fstats.items():
        a, d = '\n'.join(st['add']), '\n'.join(st['del'])
        print(f"{os.path.basename(fn)}: +{len(st['add'])}/-{len(st['del'])} lines, {tok(a)-tok(d):+} tokens")
    for fn, content in ut.items():
        lines = content.count('\n') + 1
        print(f"{os.path.basename(fn)}: +{lines} lines, +{tok(content)} tokens (untracked)")
    # Total
    ins = sum(len(s['add']) for s in fstats.values()) + sum(c.count('\n')+1 for c in ut.values())
    dels = sum(len(s['del']) for s in fstats.values())
    added = '\n'.join('\n'.join(s['add']) for s in fstats.values()) + '\n'.join(ut.values())
    removed = '\n'.join('\n'.join(s['del']) for s in fstats.values())
    ta, tr = tok(added), tok(removed)
    files = list(fstats.keys()) + list(ut.keys())
    flist = ' '.join(os.path.basename(f) for f in files[:5]) + (' ...' if len(files) > 5 else '')
    unt = f" (incl. {len(ut)} untracked)" if ut else ""
    print(f"{'─'*60}\n{len(files)} file{'s' if len(files)!=1 else ''} ({flist}), +{ins}/-{dels} lines{unt} | Net: {ins-dels:+} lines, {ta-tr:+} tokens\n\naio diff 5 = last 5 commits")
