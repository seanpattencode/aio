#!/usr/bin/env python3
import subprocess, sys, signal, os

cmd_str = ' '.join(sys.argv[1:]).lower()

timeout_map = {
    'web.py': 999999, 'aios_api.py': 999999, 'scheduler.py': 999999,
    'poll': 999999, 'watch': 999999, 'serve': 999999,
    'autollm': 999999, 'claude': 999999, 'codex': 999999,
    'wiki_fetcher': 5.0, 'scraper': 5.0, 'gdrive': 5.0,
    'curl': 5.0, 'wget': 5.0, 'git': 5.0, 'npm': 5.0, 'pip': 5.0
}

matches = [timeout_map.get(p, 0) * (p in cmd_str) for p in timeout_map.keys()]
timeout = float(os.getenv('AIOS_TIMEOUT', str(max(matches + [0.1]))))

signal.signal(signal.SIGALRM, lambda *_: sys.exit(1))
signal.setitimer(signal.ITIMER_REAL, timeout)

result = subprocess.run(sys.argv[1:], capture_output=True, text=True)

signal.alarm(0)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
