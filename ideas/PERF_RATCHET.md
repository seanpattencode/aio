PERF RATCHET — ever-tightening performance enforcement

The perf system kills any command that exceeds its timeout. Each benchmark
run tightens limits to 1.3x the measured time. Limits never loosen. This
creates a one-way ratchet that forces code toward its theoretical optimum.

THE MECHANISM

  Run 1: help takes 5ms  → limit set to 50ms (floor)
  Run 2: help takes 3ms  → limit tightens to 50ms (floor holds)
  Run 3: help takes 2ms  → limit stays 50ms

  Run 1: diff takes 200ms → limit set to 260ms
  Run 2: diff takes 150ms → limit tightens to 195ms
  Run 3: diff takes 140ms → limit tightens to 182ms
  Run 4: diff takes 145ms → no change (195ms > 182ms, already tighter)

The gap between measured time and limit shrinks with every bench. Eventually
the limit converges to the true cost of the operation plus 30% variance
headroom. At that point, any regression — even small — triggers a kill.

WHY IT FORCES OPTIMAL CODE

Most performance work is optional. You notice something is slow, add it to
a list, never fix it. The ratchet removes the option. If you add a feature
that makes `diff` take 300ms instead of 150ms, the next run kills it. You
must either:

  1. Make the new feature faster than the old code
  2. Remove the feature
  3. Manually raise the limit (visible in git as a loosening commit)

Option 3 is available but socially expensive — the commit history shows you
gave up. The path of least resistance becomes writing faster code.

THE COMPOUND EFFECT

Each optimization enables future tightening. If you optimize `scan` from
1400ms to 800ms, the next bench sets the limit to 1040ms. If you then
optimize further to 600ms, the limit drops to 780ms. The ceiling chases the
floor down. Over months of development:

  Month 1: scan limit 3000ms  (initial generous default)
  Month 2: scan limit 1800ms  (first bench)
  Month 3: scan limit 1040ms  (optimized filesystem walk)
  Month 4: scan limit  520ms  (switched to readdir instead of find)
  Month 5: scan limit  260ms  (cached results)

The tool gets faster without anyone deciding to make it faster. The system
decided. You just had to not break it.

PER-DEVICE PROFILES

Different hardware has different baselines. A phone running termux can't
match a desktop. The perf file lives at adata/git/perf/{device}.txt and
syncs across devices. Each device has its own ratchet:

  HSU.txt:   help:50   diff:182   scan:520
  pixel.txt: help:200  diff:800   scan:3000

The desktop forces tight limits. The phone gets more headroom. But both
ratchets only tighten. The phone gets faster too, just from a higher
starting point.

WHAT IT PREVENTS

  - Death by a thousand cuts. No single commit makes code slow. A hundred
    commits each adding 5ms do. The ratchet catches the 5ms.

  - "I'll optimize later." There is no later. The limit is now.

  - Slow dependencies. If a library update makes things slower, the bench
    catches it before it ships. You either pin the fast version or find a
    faster library.

  - Accidental quadratic. O(n²) hides in small datasets. As data grows,
    the command hits the wall. The ratchet makes this a build error, not a
    user complaint.

WHAT IT DOES NOT PREVENT

  - Algorithmic limits. Some operations have a minimum cost. The ratchet
    converges to that cost and stops tightening. This is correct — it found
    the floor.

  - Variance. System load, disk cache, network latency cause jitter. The
    30% headroom absorbs normal variance. Persistent slowdowns (new
    background process, degraded disk) require investigating the device,
    not the code.

THE PHILOSOPHY

Performance is not a feature you add. It is a constraint you maintain.
The ratchet converts "should be fast" into "must be fast" by making
slowness a crash. Crashes get fixed. Slowness gets ignored. So make
slowness a crash.
