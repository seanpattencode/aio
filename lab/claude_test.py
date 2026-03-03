#!/usr/bin/env python3
import subprocess,shutil,os
claude=shutil.which('claude')or os.path.expanduser('~/.local/bin/claude')
result = subprocess.run([claude, '-p', 'List files in current directory'], capture_output=True, text=True)
print(result.stdout or result.stderr)
