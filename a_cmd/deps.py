"""aio deps - Install dependencies"""
import sys, os, subprocess as sp, shutil

def run():
    _run = lambda c: sp.run(c, shell=True).returncode == 0
    sudo = '' if os.environ.get('TERMUX_VERSION') else 'sudo '
    for p, a in [('pexpect','python3-pexpect'),('prompt_toolkit','python3-prompt-toolkit')]:
        try: __import__(p); ok = True
        except: ok = _run(f'{sudo}apt-get install -y {a}') or _run(f'{sys.executable} -m pip install --user {p}')
        print(f"{'✓' if ok else 'x'} {p}")
    shutil.which('tmux') or _run(f'{sudo}apt-get install -y tmux') or _run('brew install tmux'); print(f"{'✓' if shutil.which('tmux') else 'x'} tmux")
    shutil.which('npm') or _run(f'{sudo}apt-get install -y nodejs npm') or _run('brew install node')
    nv = int(sp.run(['node','-v'],capture_output=True,text=True).stdout.strip().lstrip('v').split('.')[0]) if shutil.which('node') else 0
    nv < 25 and _run(f'{sudo}npm i -g n && {sudo}n latest'); print(f"{'✓' if shutil.which('node') else 'x'} node")
    for c, p in [('codex','@openai/codex'),('claude','@anthropic-ai/claude-code'),('gemini','@google/gemini-cli')]:
        shutil.which(c) or _run(f'{sudo}npm i -g {p}'); print(f"{'✓' if shutil.which(c) else 'x'} {c}")
    shutil.which('aider') or _run(f'{sys.executable} -m pip install --user aider-chat'); print(f"{'✓' if shutil.which('aider') else 'x'} aider")
