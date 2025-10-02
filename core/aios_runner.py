#!/usr/bin/env python3
import subprocess, sys, signal, os, operator

cmd_str = ' '.join(sys.argv[1:]).lower()

# Determine timeout based on command
long_running_cmds = ['web.py', 'aios_api.py', 'scheduler.py', 'poll',
                     'watch', 'serve', 'autollm', 'claude', 'codex']
medium_cmds = ['wiki_fetcher', 'scraper', 'gdrive',
               'curl', 'wget', 'git', 'npm', 'pip']

# Check for long running commands (essentially infinite timeout)
timeout_values = []
for p in long_running_cmds:
    if cmd_str.find(p) >= 0:
        timeout_values.append(999999)

# Check for medium timeout commands
for p in medium_cmds:
    if cmd_str.find(p) >= 0:
        timeout_values.append(5.0)

# Default short timeout
timeout_values.append(0.1)

timeout = float(os.getenv('AIOS_TIMEOUT', max(timeout_values)))

# Set timeout signal handler
signal.signal(signal.SIGALRM, lambda *_: sys.exit(1))
signal.setitimer(signal.ITIMER_REAL, timeout)

# Run command
result = subprocess.run(sys.argv[1:], capture_output=True, text=True)

# Clear alarm and output results
signal.alarm(0)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
