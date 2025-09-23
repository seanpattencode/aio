#!/usr/bin/env python3
"""claudeCodeE: Zero-overhead SQLite queue optimized for AIOS"""
import sqlite3, subprocess, json, time, sys, os, signal, threading

# Ultimate minimalism: Direct SQL, no abstractions
def init_db(path="tasks_e.db"):
    """Initialize with best pragmas from all implementations"""
    c = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    c.row_factory = sqlite3.Row
    for p in ["PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL",
              "PRAGMA cache_size=-8000", "PRAGMA temp_store=MEMORY",
              "PRAGMA mmap_size=268435456", "PRAGMA busy_timeout=5000"]:
        c.execute(p)
    c.execute("""CREATE TABLE IF NOT EXISTS t(
        id INTEGER PRIMARY KEY, c TEXT, p INT DEFAULT 0,
        s CHAR DEFAULT 'q', at INT DEFAULT 0, w TEXT, r INT DEFAULT 0,
        d TEXT, res TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix ON t(s,p DESC,at) WHERE s='q'")
    return c

class Queue:
    """Lightning-fast queue with all essential features"""
    def __init__(self, db="tasks_e.db"):
        self.c = init_db(db)
        self.l = threading.Lock()

    def add(self, cmd, pri=0, at=None, deps=None):
        """Add with optional dependencies (JSON)"""
        with self.l:
            return self.c.execute("INSERT INTO t(c,p,at,d) VALUES(?,?,?,?)",
                (cmd, pri, at or int(time.time()*1000), json.dumps(deps) if deps else None)).lastrowid

    def pop(self, wid=None):
        """Atomic pop with dependency check"""
        wid = wid or str(os.getpid())
        now = int(time.time()*1000)
        with self.l:
            # Check dependencies inline - no subqueries
            r = self.c.execute("""
                SELECT id,c FROM t WHERE s='q' AND at<=? AND (
                    d IS NULL OR NOT EXISTS(
                        SELECT 1 FROM json_each(t.d) j, t t2
                        WHERE t2.id=j.value AND t2.s!='d'))
                ORDER BY p DESC,at LIMIT 1""", (now,)).fetchone()
            if not r: return None
            # Atomic claim
            u = self.c.execute("UPDATE t SET s='r',w=? WHERE id=? AND s='q'",
                              (wid, r[0])).rowcount
            return {'id':r[0], 'cmd':r[1]} if u else None

    def done(self, tid, ok=True, res=None, err=None):
        """Complete with retry logic"""
        with self.l:
            if ok:
                self.c.execute("UPDATE t SET s='d',res=?,w=NULL WHERE id=?",
                              (json.dumps(res) if res else None, tid))
            else:
                r = self.c.execute("SELECT r FROM t WHERE id=?", (tid,)).fetchone()
                if r and r[0] < 3:
                    self.c.execute("UPDATE t SET s='q',r=r+1,at=?,w=NULL WHERE id=?",
                                  (int(time.time()*1000) + 1000*(2**r[0]), tid))
                else:
                    self.c.execute("UPDATE t SET s='f',res=?,w=NULL WHERE id=?",
                                  (err, tid))

    def stats(self):
        """Quick stats"""
        return dict(self.c.execute("SELECT s,COUNT(*) FROM t GROUP BY s"))

    def reclaim(self, timeout=300000):
        """Reclaim stalled tasks"""
        cutoff = int(time.time()*1000) - timeout
        with self.l:
            return self.c.execute("UPDATE t SET s='q',w=NULL WHERE s='r' AND at<?",
                                 (cutoff,)).rowcount

def worker(q=None, batch=1):
    """Fast worker loop"""
    q = q or Queue()
    stop = False
    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__('stop', True))
    signal.signal(signal.SIGINT, lambda *_: globals().__setitem__('stop', True))

    while not stop:
        tasks = [q.pop() for _ in range(batch)]
        any_work = False

        for t in tasks:
            if not t: continue
            any_work = True
            try:
                r = subprocess.run(t['cmd'], shell=True, capture_output=True,
                                 text=True, timeout=300)
                q.done(t['id'], r.returncode==0,
                      {'out':r.stdout[:500],'err':r.stderr[:500]})
            except Exception as e:
                q.done(t['id'], False, err=str(e))

        if not any_work:
            if int(time.time())%60 == 0:
                q.reclaim()
            time.sleep(0.05)

def bench():
    """Performance test"""
    import os
    db = "bench_e.db"
    if os.path.exists(db): os.unlink(db)
    q = Queue(db)

    # Inserts
    t0 = time.perf_counter()
    for i in range(1000):
        q.add(f"echo {i}", i%10)
    t1 = (time.perf_counter()-t0)*1000

    # Dependencies
    t0 = time.perf_counter()
    p = q.add("parent", 10)
    for i in range(100):
        q.add(f"child{i}", 5, deps=[p])
    t2 = (time.perf_counter()-t0)*1000

    # Pops
    t0 = time.perf_counter()
    for _ in range(100):
        q.pop()
    t3 = (time.perf_counter()-t0)*1000

    print(f"""claudeCodeE Benchmark:
1000 inserts: {t1:.2f}ms ({t1/1000:.4f}ms/op)
101 w/deps:   {t2:.2f}ms ({t2/101:.4f}ms/op)
100 pops:     {t3:.2f}ms ({t3/100:.4f}ms/op)""")

def main():
    if len(sys.argv) < 2:
        print("Usage: add <cmd> [pri] [deps] | worker [batch] | stats | bench")
        sys.exit(1)

    cmd = sys.argv[1]
    q = Queue()

    if cmd == 'add':
        if len(sys.argv) < 3:
            print("Need command"); sys.exit(1)
        pri = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        deps = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
        tid = q.add(sys.argv[2], pri, deps=deps)
        print(f"Task {tid}")

    elif cmd == 'worker':
        batch = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        print(f"Worker started (batch={batch})")
        worker(q, batch)

    elif cmd == 'stats':
        print(json.dumps(q.stats()))

    elif cmd == 'bench':
        bench()

    else:
        print(f"Unknown: {cmd}")

if __name__ == "__main__":
    main()