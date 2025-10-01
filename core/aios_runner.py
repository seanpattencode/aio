#!/usr/bin/env python3
import subprocess, sys, signal, os
cmd_str = ' '.join(sys.argv[1:]).lower()
timeout = float(os.getenv('AIOS_TIMEOUT', max([max([999999 * min(1, cmd_str.find(p) + 1) for p in ['web.py', 'aios_api.py', 'scheduler.py', 'poll', 'watch', 'serve', 'autollm', 'claude', 'codex']]), max([5.0 * min(1, cmd_str.find(p) + 1) for p in ['wiki_fetcher', 'scraper', 'gdrive', 'curl', 'wget', 'git', 'npm', 'pip']]), 0.1])))
signal.signal(signal.SIGALRM, sys.exit)
signal.setitimer(signal.ITIMER_REAL, timeout)
result = subprocess.run(sys.argv[1:], capture_output=True, text=True)
signal.alarm(0)
print(result.stdout, end='')
sys.stderr.write(str(result.stderr))
sys.exit(result.returncode)
