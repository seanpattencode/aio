"""aio update - Update aio"""
import os, subprocess as sp
from pathlib import Path
from . _common import _sg, list_all, init_db, SCRIPT_DIR, DATA_DIR, load_proj, load_apps, HELP_SHORT

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
    if _sg('rev-parse', '--git-dir').returncode != 0: print("x Not in git repo"); return
    print("Checking..."); before = _sg('rev-parse', 'HEAD').stdout.strip()[:8]
    if not before or _sg('fetch').returncode != 0: return
    _sh=f'bash {SCRIPT_DIR}/install.sh --shell>/dev/null'
    if 'behind' not in _sg('status', '-uno').stdout: print(f"✓ Up to date ({before})"); os.system(_sh); init_db(); list_all(); setup_all(); __import__('a_cmd.sync',fromlist=['']).run(); return
    print("Downloading..."); _sg('pull', '--ff-only'); after = _sg('rev-parse', 'HEAD').stdout.strip()[:8]; print(f"✓ {before} -> {after}" if after else "✓ Done")
    os.system(_sh); init_db(); list_all(); setup_all(); __import__('a_cmd.sync',fromlist=['']).run()
    if arg == 'all': print("\n--- Broadcasting to SSH hosts ---"); sp.run('a ssh all "a update"', shell=True)
