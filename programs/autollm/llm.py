#!/usr/bin/env python3
import subprocess, sys
command, model, task = (sys.argv + ["claude"])[1], (sys.argv + ["", "claude-3-5-sonnet-20241022"])[2], " ".join(sys.argv[3:]) or "Improve this code"
subprocess.run({"claude": ["claude", "--dangerously-skip-permissions", task], "codex": ["codex", "-c", "model_reasoning_effort=high", "--model", model, "--dangerously-bypass-approvals-and-sandbox", task]}.get(command, ["claude", "--dangerously-skip-permissions", task]), timeout=999999)