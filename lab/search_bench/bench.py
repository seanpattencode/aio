#!/usr/bin/env python3
"""Search method benchmarks - filename and content search"""
import os, time, subprocess, sqlite3, tempfile, shutil

def bench(name, fn, n=10):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    avg = sum(times) / len(times) * 1000
    print(f"{name:30} {avg:6.2f}ms")
    return avg

def main():
    # Setup test dir
    d = tempfile.mkdtemp()
    os.chdir(d)
    print(f"Test dir: {d}\n")

    # Create 10k files
    print("Creating 10k files...")
    for i in range(10000):
        open(f"file_{i}.txt", "w").write(f"line: unique_{i}_data " * 100)

    # Compile C search
    src = os.path.dirname(__file__) + "/search.c"
    subprocess.run(["gcc", "-O3", "-o", "search", src], check=True)

    print("\n=== FILENAME SEARCH (10k files) ===\n")

    bench("bash glob", lambda: subprocess.run("printf '%s\\n' *5000*", shell=True, capture_output=True))
    bench("C readdir+strstr", lambda: subprocess.run(["./search", "5000"], capture_output=True))
    bench("find", lambda: subprocess.run(["find", ".", "-name", "*5000*"], capture_output=True))
    bench("ls | grep", lambda: subprocess.run("ls | grep 5000", shell=True, capture_output=True))
    bench("Python os.scandir", lambda: [e.name for e in os.scandir(".") if "5000" in e.name])
    bench("Python os.listdir", lambda: [f for f in os.listdir(".") if "5000" in f])

    print("\n=== CONTENT SEARCH (10k files, 1M words) ===\n")

    rg = shutil.which("rg") or "/usr/local/lib/node_modules/@anthropic-ai/claude-code/vendor/ripgrep/x64-linux/rg"
    if os.path.exists(rg):
        bench("ripgrep", lambda: subprocess.run([rg, "unique_5000_", "."], capture_output=True))
    bench("grep -r", lambda: subprocess.run(["grep", "-r", "unique_5000_", "."], capture_output=True))
    bench("Python read all", lambda: [f for f in os.listdir(".") if f.endswith(".txt") and "unique_5000_" in open(f).read()])

    print("\n=== SQLITE (10k rows) ===\n")

    # Build SQLite DB
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE f (id INT, name TEXT, content TEXT)")
    db.executemany("INSERT INTO f VALUES (?,?,?)", [(i, f"file_{i}.txt", open(f"file_{i}.txt").read()) for i in range(10000)])
    db.execute("CREATE INDEX idx_name ON f(name)")
    db.commit()

    bench("SQLite exact (indexed)", lambda: list(db.execute("SELECT name FROM f WHERE name=?", ("file_5000.txt",))))
    bench("SQLite LIKE (scan)", lambda: list(db.execute("SELECT name FROM f WHERE content LIKE ?", ("%unique_5000_%",))))

    # FTS5
    db.execute("CREATE VIRTUAL TABLE fts USING fts5(name, content)")
    db.execute("INSERT INTO fts SELECT name, content FROM f")
    db.commit()

    bench("SQLite FTS5", lambda: list(db.execute("SELECT name FROM fts WHERE fts MATCH ?", ("unique_5000_",))))

    # Cleanup
    os.chdir("/")
    shutil.rmtree(d)
    print(f"\nCleaned up {d}")

if __name__ == "__main__":
    main()
