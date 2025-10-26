#!/usr/bin/env python3
import os, sys, subprocess as sp
from datetime import datetime

CLAUDE_PROMPT = "tell me a joke"
CODEX_PROMPT = "tell me a joke"
GEMINI_PROMPT = "tell me a joke"

sessions = {
    'h': ('htop', 'htop'),
    't': ('top', 'top'),
    'g': ('gemini', 'gemini --yolo'),
    'gp': ('gemini-p', f'gemini --yolo "{GEMINI_PROMPT}"'),
    'c': ('codex', 'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox'),
    'cp': ('codex-p', f'codex -c model_reasoning_effort="high" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox "{CODEX_PROMPT}"'),
    'l': ('claude', 'claude --dangerously-skip-permissions'),
    'lp': ('claude-p', f'claude --dangerously-skip-permissions "{CLAUDE_PROMPT}"')
}

arg = sys.argv[1] if len(sys.argv) > 1 else None

if not arg:
    sp.run(['tmux', 'ls'])
elif arg.startswith('+'):
    key = arg[1:]
    if key in sessions:
        base_name, cmd = sessions[key]
        ts = datetime.now().strftime('%H%M%S')
        name = f"{base_name}-{ts}"
        sp.run(['tmux', 'new', '-d', '-s', name, cmd])
        os.execvp('tmux', ['tmux', 'switch-client' if "TMUX" in os.environ else 'attach', '-t', name])
else:
    name, cmd = sessions.get(arg, (arg, None))
    sp.run(['tmux', 'new', '-d', '-s', name, cmd or arg], capture_output=True)
    os.execvp('tmux', ['tmux', 'switch-client' if "TMUX" in os.environ else 'attach', '-t', name])
