#!/usr/bin/env python3
"""
Compare bashrc loading strategies:
1. Current (already optimized)
2. Simulated heavy (conda, nvm, pyenv, etc)
3. Instant (essential first, early exit)
"""
import subprocess, time, os, shutil, statistics

BASHRC = os.path.expanduser("~/.bashrc")
BACKUP = os.path.expanduser("~/.bashrc.strat_backup")

# Simulate heavy bashrc additions (common in real-world setups)
HEAVY_ADDITIONS = '''
# Simulated heavy bashrc (nvm, pyenv, conda full load)
sleep 0.05  # Simulate 50ms of heavy loading
'''

def backup():
    shutil.copy(BASHRC, BACKUP)

def restore():
    if os.path.exists(BACKUP):
        shutil.copy(BACKUP, BASHRC)
        os.remove(BACKUP)

def bench(label, runs=30):
    """Benchmark source bashrc && aio"""
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        subprocess.getoutput("source ~/.bashrc 2>/dev/null && aio")
        times.append((time.perf_counter() - t) * 1000)
    return {"min": min(times), "avg": statistics.mean(times), "label": label}

def get_aio_func():
    """Extract aio function."""
    with open(BASHRC) as f:
        content = f.read()
    start = content.find("aio()")
    if start == -1: start = content.find("aio ()")
    if start == -1: return ""
    depth, end = 0, start
    for i, c in enumerate(content[start:], start):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: end = i + 1; break
    return content[start:end]

def main():
    backup()
    results = []

    try:
        # 1. Current (optimized)
        print("Testing current bashrc...")
        results.append(bench("Current (optimized)"))

        # 2. Heavy (simulated)
        print("Testing heavy bashrc (simulated 50ms load)...")
        with open(BASHRC, 'a') as f:
            f.write(HEAVY_ADDITIONS)
        results.append(bench("Heavy (+50ms sim)"))
        restore()
        backup()

        # 3. Instant strategy with heavy load
        print("Testing instant strategy (aio first, early exit, then heavy)...")
        aio_func = get_aio_func()
        with open(BASHRC) as f:
            original = f.read()

        instant = f'''# INSTANT: Essential functions BEFORE interactive check
{aio_func}

# Early exit for non-interactive (subprocess gets aio, skips rest)
[[ $- != *i* ]] && return

# Heavy stuff only for interactive shells
{HEAVY_ADDITIONS}
'''
        # Remove aio from original to avoid dupe
        rest = original.replace(aio_func, "").replace("# aio instant startup (Stage 1: true 0ms) - Added by aio install\n", "")
        with open(BASHRC, 'w') as f:
            f.write(instant + rest)

        results.append(bench("Instant (aio→exit→heavy)"))

    finally:
        restore()
        print("✓ Restored bashrc\n")

    # Results table
    print("=" * 60)
    print("BASHRC STRATEGY COMPARISON (30 runs, source && aio)")
    print("=" * 60)
    print(f"\n{'Strategy':<30} {'Min':>10} {'Avg':>10}")
    print("-" * 55)
    for r in results:
        print(f"{r['label']:<30} {r['min']:>8.2f}ms {r['avg']:>8.2f}ms")

    # Speedup
    if len(results) >= 3:
        heavy = results[1]["avg"]
        instant = results[2]["avg"]
        print(f"\n{'Heavy → Instant speedup:':<30} {heavy/instant:>8.1f}x")

    print("\n" + "=" * 60)
    print("THE INSTANT STRATEGY")
    print("=" * 60)
    print("""
# Put this at TOP of ~/.bashrc:

aio() {
    local cache=~/.local/share/aios/help_cache.txt
    [[ -z "$1" ]] && { cat "$cache" 2>/dev/null; return; }
    python3 ~/.local/bin/aio "$@"
}

# Early exit for non-interactive (subprocess/scripts)
[[ $- != *i* ]] && return

# === Everything below only runs for interactive shells ===
# conda init, nvm, pyenv, heavy stuff...
""")

if __name__ == "__main__":
    main()
