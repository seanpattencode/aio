# Budget From Below

## The Two Approaches to Token-Optimal Code

### Squeeze From Above (traditional)
Write the first thing that works. Then cut repeatedly until you can't.

Tested on `a cat` (concat .py files + headers + clipboard + dir param):
```
312 → 92 → 72 → 50 → 46 → 41 tokens
Six iterations. Each cut forced an architectural rethink:
  312→92:  killed Python runtime, rewrote in C
  92→72:   dropped find exclusion patterns
  72→50:   discovered git ls-files replaces find (git already knows .gitignore)
  50→46:   discovered tail -n+1 auto-prints ==> file <== headers
  46→41:   discovered xclip -o reads clipboard back, eliminating temp file
```

The architectural discoveries were accidental — side effects of trying to cut
characters. You don't set out to discover `tail -n+1` prints headers. You
discover it because nothing else fits after you've cut enough.

Pros: always produces working code at each step. Safe.
Cons: slow convergence. Explores the entire space above the answer first.
The initial version sets an anchor that biases all subsequent thinking.

### Budget From Below (new)
Start at 10 tokens. If it doesn't work, double. Accept first working version.

Same feature, same result:
```
10 tokens: git ls-files '*.py'|xargs cat
           Works. No headers, no dir param, no clipboard. Screams.
12 tokens: + tail -n+1 (headers)
           Scream: can't tell files apart. Fixed.
15 tokens: + chdir (dir param)
           Scream: have to cd first. Fixed.
22 tokens: + xclip pipe (clipboard)
           Scream: can't paste into LLM. Fixed.
Three iterations. Each added exactly one scream.
```

The architectural choices were forced — at 10 tokens you can't reach for Python.
You can't write find exclusion patterns. The only thing that fits is the shortest
unix pipeline for the job. Bad architectures are eliminated before they're written.

Pros: 2x faster convergence. Finds optimal architecture immediately.
Cons: early versions are broken (by design — that's how you discover what screams).

## Why From-Below Works

At any given budget N, only the architecturally optimal approach fits. There is
no room for the wrong tool. The constraint does the architectural thinking for you.

From-above: you must recognize waste to cut it. Requires insight.
From-below: waste can't exist because there's no room. Requires nothing.

Both converge to the same code. From-below gets there in log₂(optimal/10)
rounds. From-above gets there in however many rounds it takes you to see the fat.

## Convergence Math

From-below: 10 → 20 → 40 → 80. Reaches any target in ceil(log₂(target/10)) steps.
From-above: unpredictable. Depends on how bloated the initial version is and how
fast you spot waste. In practice 2-3x more iterations than from-below.

On subsequent fix touches, squeeze 2x (from-above). This is fine because the
code is already near-optimal — you're cutting 20% not 80%. The approaches
complement: from-below for creation, from-above for maintenance.

## Relationship to Workcycle

The workcycle is preemptive deletion at the feature level:
- Don't build until scream
- Delete everything, only what screams survives
- Add minimal fix

Budget-from-below is the same principle at the token level:
- Don't budget until impossible
- Start from nothing, only what screams gets tokens
- Accept first working version

Same structure, three scales:
- Feature: don't build until scream
- Code: don't write until deletion fails
- Token: don't budget until impossible

## Information Theory

A 2x budget increase asks: "does this feature need 1 more bit of decision?"
Each bit is one binary architectural choice: headers or not, dir param or not,
clipboard or not. These are yes/no decisions with roughly 2x cost each.

Base 2 matches the structure of design decisions (include/exclude a capability).
Base 3+ overshoots — grants budget for decisions not yet proven necessary.
Base 10 is the escape hatch for genuinely hard problems, not the default.

## Rule

1. Budget 10 tokens for any new feature
2. Attempt implementation
3. If broken: 2x budget, retry
4. Accept first working version
5. On fix touches: squeeze 2x (maintenance ratchet)
