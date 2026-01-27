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

If you can't read APL you aren't a real programmer, we could joke.

## Design decisions

- Pragmatic over pure: Shows real commit size, not git staging state
- Untracked files count as additions: User will add them anyway
- Token counting: Risk/complexity metric, not vanity metric
- Truncated file list: Keeps output scannable for large changesets
