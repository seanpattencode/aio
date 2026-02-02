"""aio update - Update aio"""
import os, subprocess as sp, shutil
from pathlib import Path
from . _common import _sg, list_all, init_db, SCRIPT_DIR, DATA_DIR, load_proj, load_apps, HELP_SHORT

# === Unified cache & shell setup ===
CMDS = ['help','update','jobs','kill','attach','cleanup','config','ls','diff','send','watch',
        'push','pull','revert','set','install','uninstall','deps','prompt','gdrive',
        'add','remove','move','dash','all','backup','scan','copy','log','done','agent','tree',
        'dir','web','ssh','run','hub','task','daemon','ui','review','note']

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
    n = __import__('re').sub(rf'{m}-start.*?{m}-end\n?','',c,flags=8).rstrip()+f"\n\n{m}-start\n{ln}\n{m}-end\n" if ln else c
    updated = n != c and open(rc,'w').write(n)
    return sh, updated

def setup_all():
    """Run all setup: shell + caches"""
    sh, updated = refresh_shell()
    print(f"✓ {sh.title()} (updated)" if updated else f"• {sh.title()} (ok)")
    refresh_caches(); print("✓ Cache")

def _setup_sync():
    if not shutil.which('gh') or sp.run(['gh','auth','status'],capture_output=True).returncode!=0: return
    sp.run('hp=~/.local/bin/git-credential-gh;mkdir -p $(dirname $hp);echo "#!/bin/sh\nexec $(which gh) auth git-credential \\\"\\$@\\\"">$hp;chmod +x $hp;git config --global credential.helper $hp',shell=True,capture_output=True)
    if os.path.isdir(f"{DATA_DIR}/.git"): print("✓ Sync"); return
    url = sp.run(['gh','repo','view','aio-sync','--json','url','-q','.url'],capture_output=True,text=True).stdout.strip() or sp.run(['gh','repo','create','aio-sync','--private','-y'],capture_output=True,text=True).stdout.strip()
    url and sp.run(f'mkdir -p "{DATA_DIR}"&&cd "{DATA_DIR}"&&git init -b main -q;git remote add origin {url} 2>/dev/null;echo "*.db*\n*.log\nlogs/\n*cache*\ntiming.jsonl\nnotebook/\n.device">.gitignore;git fetch origin&&git reset --hard origin/main 2>/dev/null||(git add -A&&git -c user.name=aio -c user.email=a@a commit -m init -q&&git push -u origin main)',shell=True,capture_output=True) and print("✓ Sync")

def run():
    import sys; arg = sys.argv[2] if len(sys.argv) > 2 else None
    if arg in ('bash', 'zsh', 'shell'): setup_all(); return
    if arg == 'cache': refresh_caches(); print("✓ Cache"); return
    if _sg('rev-parse', '--git-dir').returncode != 0: print("x Not in git repo"); return
    print("Checking..."); before = _sg('rev-parse', 'HEAD').stdout.strip()[:8]
    if not before or _sg('fetch').returncode != 0: return
    _sh=f'bash {SCRIPT_DIR}/install.sh --shell>/dev/null'
    if 'behind' not in _sg('status', '-uno').stdout: print(f"✓ Up to date ({before})"); os.system(_sh); init_db(); list_all(); setup_all(); _setup_sync(); return
    print("Downloading..."); _sg('pull', '--ff-only'); after = _sg('rev-parse', 'HEAD').stdout.strip()[:8]; print(f"✓ {before} -> {after}" if after else "✓ Done")
    os.system(_sh); init_db(); list_all(); setup_all(); _setup_sync()
