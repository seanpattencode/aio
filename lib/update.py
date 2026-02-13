"""aio update - Update aio"""
import os, subprocess as sp
from pathlib import Path
from _common import _sg, list_all, init_db, SCRIPT_DIR, DATA_DIR, load_proj, load_apps, HELP_SHORT, SYNC_ROOT, ADATA_ROOT

ADATA_REMOTE = 'https://github.com/seanpattencode/a-git.git'

# === Unified cache & shell setup ===
CMDS = ['help','update','jobs','kill','attach','cleanup','config','ls','diff','send','watch',
        'push','pull','revert','set','install','uninstall','deps','prompt','gdrive',
        'add','remove','move','dash','all','backup','scan','copy','log','done','agent','tree',
        'dir','web','ssh','run','hub','task','ui','review','note']

def refresh_caches():
    """Refresh all caches: help_cache.txt + i_cache.txt"""
    p, a = load_proj(), load_apps()
    # help_cache.txt - formatted help
    pmark = lambda x,r: '+' if os.path.exists(x) else ('~' if r else 'x')
    out = [f"PROJECTS:"] + [f"  {i}. {pmark(x,r)} {x}" for i,(x,r) in enumerate(p)]
    out += [f"COMMANDS:"] + [f"  {len(p)+i}. {n} -> {c.replace(os.path.expanduser('~'),'~')[:60]}" for i,(n,c) in enumerate(a)] if a else []
    Path(f"{DATA_DIR}/help_cache.txt").write_text(HELP_SHORT + '\n' + '\n'.join(out) + '\n')
    # i_cache.txt - interactive menu
    items = [f"{i}: {os.path.basename(x)} ({x})" for i,(x,_) in enumerate(p)] + [f"{len(p)+i}: {n}" for i,(n,_) in enumerate(a)] + CMDS
    Path(f"{DATA_DIR}/i_cache.txt").write_text('\n'.join(items))

def refresh_shell(ln='export PATH="$HOME/.local/bin:$PATH"'):
    """Update shell rc file with managed block"""
    sh = os.environ.get('SHELL','').split('/')[-1] or 'bash'
    rc = os.path.expanduser('~/.zshrc' if sh == 'zsh' else '~/.bashrc')
    m, c = "# aio", open(rc).read() if os.path.exists(rc) else ""
    n = __import__('re').sub(rf'{m}-start.*?{m}-end\n?','',c,flags=16).rstrip()+f"\n\n{m}-start\n{ln}\n{m}-end\n" if ln else c
    updated = n != c and open(rc,'w').write(n)
    return sh, updated

def setup_all():
    """Run all setup: shell + caches"""
    sh, updated = refresh_shell()
    print(f"✓ {sh.title()} (updated)" if updated else f"• {sh.title()} (ok)")
    refresh_caches(); print("✓ Cache")

def ensure_adata():
    """Ensure adata/git exists, has correct remote, and is synced"""
    git_dir = SYNC_ROOT / '.git'

    # Clone if missing
    if not git_dir.exists():
        SYNC_ROOT.mkdir(parents=True, exist_ok=True)
        r = sp.run(f'gh repo clone seanpattencode/a-git {SYNC_ROOT}',
                   shell=True, capture_output=True, text=True)
        if r.returncode == 0:
            print(f"✓ Cloned adata/git")
        else:
            print(f"x Failed to clone adata/git: {r.stderr.strip()[:100]}")
        return

    # Fix remote if pointing at wrong repo
    r = sp.run(['git', '-C', str(SYNC_ROOT), 'remote', 'get-url', 'origin'],
               capture_output=True, text=True)
    current = r.stdout.strip()
    if current and 'a-git' not in current:
        sp.run(['git', '-C', str(SYNC_ROOT), 'remote', 'set-url', 'origin', ADATA_REMOTE],
               capture_output=True)
        print(f"✓ Fixed adata remote: {current} -> a-git")

    # Fetch and reset if behind or diverged
    sp.run(['git', '-C', str(SYNC_ROOT), 'fetch', 'origin'], capture_output=True)
    status = sp.run(['git', '-C', str(SYNC_ROOT), 'status', '-uno'], capture_output=True, text=True).stdout
    log = sp.run(['git', '-C', str(SYNC_ROOT), 'log', '--oneline', '-1'], capture_output=True, text=True).stdout.strip()
    remote_log = sp.run(['git', '-C', str(SYNC_ROOT), 'log', '--oneline', '-1', 'origin/main'],
                        capture_output=True, text=True).stdout.strip()

    if 'diverged' in status or (remote_log and log != remote_log and 'behind' in status):
        sp.run(['git', '-C', str(SYNC_ROOT), 'reset', '--hard', 'origin/main'], capture_output=True)
        print(f"✓ Reset adata/git to remote")
    elif 'behind' in status:
        sp.run(['git', '-C', str(SYNC_ROOT), 'pull', '--ff-only', 'origin', 'main'], capture_output=True)
        print(f"✓ Updated adata/git")

HELP = """a update - Update a from git + refresh caches
  a update        Pull latest, refresh shell/caches, sync repos
  a update all    Update local + broadcast to all SSH hosts
  a update shell  Refresh shell config + caches only
  a update cache  Refresh caches only
  a update help   Show this help"""

def run():
    import sys; arg = sys.argv[2] if len(sys.argv) > 2 else None
    if arg in ('help', '-h', '--help'): print(HELP); return
    if arg in ('bash', 'zsh', 'shell'): setup_all(); return
    if arg == 'cache': refresh_caches(); print("✓ Cache"); return
    ensure_adata()
    if _sg('rev-parse', '--git-dir').returncode != 0: print("x Not in git repo"); return
    print("Checking..."); before = _sg('rev-parse', 'HEAD').stdout.strip()[:8]
    if not before or _sg('fetch').returncode != 0: return
    _sh=f'sh {SCRIPT_DIR}/../a.c shell>/dev/null'
    if 'behind' not in _sg('status', '-uno').stdout: print(f"✓ Up to date ({before})"); os.system(_sh); init_db(); list_all(); setup_all(); __import__('sync',fromlist=['']).run(); return
    print("Downloading..."); _sg('pull', '--ff-only'); after = _sg('rev-parse', 'HEAD').stdout.strip()[:8]; print(f"✓ {before} -> {after}" if after else "✓ Done")
    os.system(_sh); init_db(); list_all(); setup_all(); __import__('sync',fromlist=['']).run()
    if arg == 'all': print("\n--- Broadcasting to SSH hosts ---"); sp.run('a ssh all "a update"', shell=True)
