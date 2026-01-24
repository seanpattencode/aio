#!/usr/bin/env python3
"""Precise timing test for monolith vs split warming"""
import subprocess, time, socket, os, sys

os.chdir(os.path.dirname(__file__))

def cold_time(cmd, n=5):
    times = []
    for _ in range(n):
        s = time.time()
        subprocess.run(['python3'] + cmd, capture_output=True)
        times.append((time.time() - s) * 1000)
    return sum(times) / len(times)

def warm_time(arg, n=5):
    times = []
    for _ in range(n):
        s = time.time()
        c = socket.socket(socket.AF_UNIX)
        c.connect('/tmp/test_warm.sock')
        c.send(arg.encode())
        c.shutdown(socket.SHUT_WR)
        c.recv(4096)
        c.close()
        times.append((time.time() - s) * 1000)
    return sum(times) / len(times)

def start_daemon(target):
    subprocess.run(['pkill', '-f', 'warm.py'], capture_output=True)
    try: os.unlink('/tmp/test_warm.sock')
    except: pass
    subprocess.Popen(['python3', 'warm.py', target], stdout=subprocess.DEVNULL)
    time.sleep(2)

print("=== COLD ===")
print(f"Monolith: {cold_time(['monolith.py', 'a']):.1f}ms")
print(f"Split:    {cold_time(['split/main.py', 'a']):.1f}ms")

print("\n=== WARM: Monolith ===")
start_daemon('monolith.py')
print(f"cmd a: {warm_time('a'):.2f}ms")
print(f"cmd b: {warm_time('b'):.2f}ms")
print(f"cmd c: {warm_time('c'):.2f}ms")

print("\n=== WARM: Split ===")
start_daemon('split/main.py')
print(f"cmd a: {warm_time('a'):.2f}ms")
print(f"cmd b: {warm_time('b'):.2f}ms")
print(f"cmd c: {warm_time('c'):.2f}ms")

subprocess.run(['pkill', '-f', 'warm.py'], capture_output=True)
print("\nDone")
