#!/usr/bin/env python3
import subprocess
import sys

command = (sys.argv + ["claude"])[1]
model = (sys.argv + ["", "claude-3-5-sonnet-20241022"])[2]
task = " ".join(sys.argv[3:]) or "Improve this code"

commands = {
    "claude": ["claude", "--dangerously-skip-permissions", task],
    "codex": ["codex", "-c", "model_reasoning_effort=high", "--model", model, "--dangerously-bypass-approvals-and-sandbox", task]
}

subprocess.run(commands.get(command, commands["claude"]), timeout=999999)