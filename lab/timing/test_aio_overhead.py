#!/usr/bin/env python3
"""Test aio timing overhead - shell fast-path vs Python fallback"""
import subprocess as sp, tempfile, os, statistics, re, json

N = 5
AIO = os.path.expanduser("~/projects/aio/aio.py")
TIMING = os.path.expanduser("~/.local/share/aios/timing.jsonl")

def time_direct(cmd):
    times = []
    for _ in range(N):
        r = sp.run(f'time {cmd}', shell=True, capture_output=True, text=True)
        m = re.search(r'(\d+\.\d+) total', r.stderr) or re.search(r'real\t0m([\d.]+)s', r.stderr)
        if m: times.append(float(m.group(1)) * 1000)
    return statistics.mean(times) if times else 0

def time_shell_aio(path):
    times = []
    for _ in range(N):
        sp.run(['zsh', '-i', '-c', f'aio {path}'], capture_output=True, stdin=sp.DEVNULL)
        with open(TIMING) as f: last = json.loads(f.readlines()[-1])
        if last['cmd'] == path: times.append(last['ms'])
    return statistics.mean(times) if times else 0

def test():
    scripts = [("noop", "pass"), ("print", "print('x')"), ("sleep_100ms", "import time; time.sleep(0.1)"), ("sleep_500ms", "import time; time.sleep(0.5)")]
    print(f"{'Script':<12} {'Direct':>8} {'Shell aio':>10} {'Py aio':>8} {'Shell':>7} {'Py':>7}")
    print("-" * 58)
    for name, code in scripts:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code); path = f.name
        direct = time_direct(f"python3 {path}")
        shell = time_shell_aio(path)
        pyaio = time_direct(f"python3 {AIO} {path}")
        print(f"{name:<12} {direct:>6.0f}ms {shell:>8.0f}ms {pyaio:>6.0f}ms {shell-direct:>+5.0f}ms {pyaio-direct:>+5.0f}ms")
        os.unlink(path)

if __name__ == '__main__': test()
