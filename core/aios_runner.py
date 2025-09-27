#!/usr/bin/env python3
import subprocess
import sys
import signal

WHITELIST_5SEC = {'wiki_fetcher', 'scraper', 'gdrive', 'curl', 'wget', 'git', 'npm', 'pip'}
WHITELIST_FOREVER = {'web.py', 'aios_api.py', 'scheduler.py', 'poll', 'watch', 'serve', 'autollm', 'claude', 'codex'}

cmd_str = ' '.join(sys.argv[1:]).lower()
def check_forever(p): return 999999 * min(1, cmd_str.find(p) + 1)
def check_5sec(p): return 5.0 * min(1, cmd_str.find(p) + 1)
timeout = max([max(list(map(check_forever, WHITELIST_FOREVER))), max(list(map(check_5sec, WHITELIST_5SEC))), 0.1])

def timeout_handler(s, f): sys.exit(124)
signal.signal(signal.SIGALRM, timeout_handler)
signal.setitimer(signal.ITIMER_REAL, timeout)
result = subprocess.run(sys.argv[1:], capture_output=True, text=True)
signal.alarm(0)
print(result.stdout, end='')
sys.stderr.write(str(result.stderr))
sys.exit(result.returncode)