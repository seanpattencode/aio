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

## Fix Depth: Why 2x Cuts Break Near the Floor

On fixes, 2x is too aggressive for code that's already been ratcheted.

`a cat` is 22 tokens of essential logic. A fix demanding 2x would mean: fix the
bug AND cut to 11 tokens. At 11 tokens you lose either clipboard, dir param, or
headers — all of which scream. The cut hits bone, not fat.

The difference is distance from floor:
- At 2x+ over optimal: 2x cuts hit fat. Plenty of waste to find.
- At 1.1x over optimal: 2x cuts hit bone. Essential functionality dies.

How do you know where you are? Fix cycle count. Fresh code has fat. Code that's
survived 3+ fix-and-shorten cycles is probably within 20% of optimal. Demanding
2x on that destroys function for marginal token savings.

Three regimes:
- **New features**: budget-from-below (10, 2x until works)
- **First fix on bloated code**: 2x cut (still fat to find)
- **Fix on ratcheted code**: any negative (near floor, preserve function)

The signal is history. Code with no cut history is bloated — demand 2x. Code
that's been cut repeatedly is near-optimal — accept any negative. The ratchet
tightens naturally: aggressive early, gentle late. Forcing 2x uniformly penalizes
code that's already been optimized, which is exactly the code you should trust.

## Diminishing Returns: When to Stop Cutting

Empirical data from the `a cat` session:

| Cut       | Saved | Time  | Tok/min | Insight required                    |
|-----------|-------|-------|---------|-------------------------------------|
| 312→92    | 220   | ~2min | ~110    | "don't use Python" — obvious        |
| 92→50     | 42    | ~3min | ~14     | "git knows your .gitignore" — moderate |
| 50→41     | 9     | ~5min | ~1.8    | "xclip -o reads clipboard" — obscure |

The first cut is 60x more efficient per minute than the last. The curve is ~1/x.

But the cost isn't just time — it's skill. Each deeper cut requires a harder
insight. An LLM reliably finds "don't use Python." Knowing `xclip -o` is obscure
unix trivia. The skill floor rises with depth. At some point you need a domain
expert, not more iterations.

The stopping rule isn't a fixed depth — it's when the cost of the next insight
exceeds the value of the tokens saved. For code that runs millions of times
(see TOKEN_EFFICIENCY.md), even 1 token matters. For code that runs once a day,
the 50→41 cut is probably not worth the session time.

Practical heuristic: **stop when the LLM proposes tradeoffs instead of pure cuts.**
Pure cuts (same function, fewer tokens) are always free wins. When the proposals
start saying "drop clipboard to save 7 tokens" — that's the floor. You're trading
function for size. Stop there, unless the function doesn't scream.

## Rule

1. Budget 10 tokens for any new feature
2. Attempt implementation
3. If broken: 2x budget, retry
4. Accept first working version
5. On fix touches:
   - Bloated (few prior cuts): demand 2x
   - Ratcheted (3+ prior cuts): accept any negative
6. Stop cutting when proposals trade function for size
