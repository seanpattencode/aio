#!/usr/bin/env python3
import subprocess,shutil,os
gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
result = subprocess.run([gemini, 'Check current weather in NYC in 2 sentences'], capture_output=True, text=True, timeout=60)
print(result.stdout or result.stderr)
