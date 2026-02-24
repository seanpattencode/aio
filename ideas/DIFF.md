# aio diff

Shows what will be pushed, not what git technically considers a "diff".

## Philosophy

Most users workflow:
```
aio diff    → see everything
aio push    → adds all, commits, pushes
```

Untracked files in the repo = "I made this, will commit it, just haven't `git add`ed yet". They get added with everything else on push. The diff tool reflects what will actually be pushed.

**aio diff answers:** "What's the total size of what I'm about to push?"

**Not:** "What does `git diff` technically show right now?"

## Output

```
2 files (diff.py test.txt), +10/-4 lines (incl. 1 untracked) | Net: +6 lines, +179 tokens
```

- **files**: All changed + untracked files, basenames truncated to 5
- **lines**: Insertions/deletions including untracked file contents
- **tokens**: Estimated using tiktoken (cl100k_base), falls back to len/4
- **incl. N untracked**: Notes when untracked files are counted

## Why tokens matter

> token counting is complexity counting is error probability counting

Token count is a proxy for:

```
tokens ≈ complexity ≈ surface area for bugs ≈ review difficulty
```

A +500 token commit isn't just "bigger" - it's statistically more likely to contain bugs, harder to review, and more likely to have unintended interactions.

**Implications:**
- High token commits deserve more testing
- Negative token commits (refactors that simplify) actively reduce risk
- Per-file token counts show where the risk concentrates
- "I'll split this" becomes a risk management decision, not just cleanliness

**The insight:** You're not counting words. You're counting potential failure points.

## Long-term token reduction

Over time with token-reduction pressure, a codebase evolves toward dense, terse functions with less boilerplate and fewer abstractions-for-abstraction's-sake.

**Trade-off:**
```
Verbose code:  Easy to read once, hard to maintain forever
Terse code:    Hard to read once, easy to maintain forever
```

**The math:**
- 10,000 token codebase vs 5,000 token codebase
- Same functionality
- Half the places for bugs to hide
- Half the code to understand when changing anything
- Half the context needed for LLM assistance

**You're optimizing for:**
- Velocity over onboarding
- Maintenance over first-read clarity
- Total error surface over local readability

It's anti-enterprise philosophy: "readable" 500-line Java class vs "cryptic" 50-line Python that does the same thing. The Python has 10x fewer failure points.

And if there's an error in terse code, you know what to do - count how many options you have. Single char error in 50 chars? That's 50 places to check, not 500.

## Bugs become variants

In terse code, "bugs" often become interesting variants rather than crashes.

```python
# Correct Game of Life - cells born with exactly 3 neighbors
life=lambda g:((c(g,np.ones((3,3)),mode='same')-g)==3)|(g&...)

# "Bug" - changed ==3 to >=3
life=lambda g:((c(g,np.ones((3,3)),mode='same')-g)>=3)|(g&...)
```

The "bug" still runs. Instead of a glider, you get an expanding blob - a different cellular automaton with different emergent behavior. You accidentally discovered an expansion rule.

**In verbose code, bugs are just broken:** NullPointerException, silent failure, hours of debugging for no creative payoff.

**In terse code, bugs become forks in possibility space:**
- 50 tokens = 50 possible single-char variants
- Each variant likely produces something that runs
- Each variant does something meaningfully different

You're not debugging, you're exploring a design space. Terse code is a creative medium. Verbose code is fragile scaffolding around the actual idea.

**Why?** Terse code plays closer to the fundamental axioms of the problem rather than abstractions on top of them. Each token is a rule of the system, not plumbing. Change a token, change a rule, get a different valid system. Change plumbing, get a crash.

## a diff does more work than anything else

`a diff` is the highest-leverage command in the system. Every other tool writes code — `a diff` is the only one that evaluates whether the code should exist. It enforces the token ratchet: after every change, you see whether the codebase grew or shrank. Without it, you're coding blind — you think you fixed something, but you may have net-added error surface. It turns an implicit gut feeling ("this seems bigger") into an explicit number that compounds across every commit.

## Design decisions

- Pragmatic over pure: Shows real commit size, not git staging state
- Untracked files count as additions: User will add them anyway
- Token counting: Risk/complexity metric, not vanity metric
- Truncated file list: Keeps output scannable for large changesets

## Appendix: Axioms of Game of Life

The APL-style code:
```python
life=lambda g:((c(g,np.ones((3,3)),mode='same')-g)==3)|(g&(c(g,np.ones((3,3)),mode='same')-g==2))
```

Derives from these axioms:

**A1. Space** — Discrete lattice Z², cells ∈ {0,1}

**A2. Neighborhood** — Moore neighborhood (8-connected)
```
N(x,y) = {(x+i, y+j) : i,j ∈ {-1,0,1}, (i,j) ≠ (0,0)}
```

**A3. Counting** — Neighbor sum via convolution
```
count(x,y) = Σ g(n) for n ∈ N(x,y)
           = (K * g)(x,y) - g(x,y)   where K = ones(3,3)
```

**A4. Transition** — Birth/survival predicate
```
g'(x,y) = 1  iff  count=3 ∨ (g(x,y)=1 ∧ count=2)
```

**A5. Synchrony** — All cells update simultaneously from state at t

**Mapping axioms → tokens:**

| Axiom | Token(s) |
|-------|----------|
| A1 | `g` (the grid) |
| A2 | `np.ones((3,3))` |
| A3 | `c(...)-g` |
| A4 | `==3`, `==2`, `\|`, `&` |
| A5 | `lambda` (pure function) |

Every token is an axiom. No plumbing. Change `==3` to `>=3`, you changed A4, you get a different valid cellular automaton.

## Verbose bug comparison

Verbose Game of Life (~50 lines, class-based):
```python
def count_neighbors(self, x, y):
    count = 0
    for dy in [-1, 0, 1]:
        for dx in [-1, 0, 1]:
            if dx == 0 or dy == 0:  # BUG: 'and' → 'or'
                continue
            count += self.get_cell(x + dx, y + dy)
    return count
```

Defensible change: "skip if on axis" vs "skip if at center". Result:
```
Gen 0: Glider
Gen 1: Single cell
Gen 2: Empty (dead forever)
```

Just dies. Only counts 4 diagonal neighbors, nothing satisfies birth condition.

| | Terse bug (`>=3`) | Verbose bug (`or`) |
|---|---|---|
| Runs? | Yes | Yes |
| Interesting? | Expanding blob | Dead grid |
| Valid variant? | Yes (different CA) | No (broken) |
| Bug location | Line 1, char 45 | Line 24, nested in class |

Verbose code buries axioms in plumbing. Change plumbing, get broken plumbing. Terse code exposes axioms. Change axiom, get different valid system.

**Speculation:** Maybe our universe is terse - a few fundamental constants, a handful of forces, and everything else emerges. Change the fine-structure constant slightly, you don't get a crash, you get a different valid universe. That's why physics is discoverable at all.

The inconsistencies we find (quantum weirdness, relativistic paradoxes) aren't signs of broken plumbing - they're the complex combinatorial interactions of simple rules. N simple axioms → N² interactions. The rules are terse; the combinations are vast. Exactly what should arise from a moderately numerous set of simple rules. The universe isn't buggy. It's a one-liner with emergent complexity.
