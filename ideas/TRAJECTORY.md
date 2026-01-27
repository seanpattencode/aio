# Trajectory

This approach seems silly in the short term. Renaming docs to ideas. Counting tokens. Writing philosophy about a diff command.

But over the long term, the trajectory firmly differs from most:

```
Most codebases:
Year 0: 1,000 tokens, clean
Year 3: 50,000 tokens, "we need to refactor"
Year 5: 200,000 tokens, "legacy code"

This codebase:
Year 0: 1,000 tokens
Year 3: 800 tokens, same features + more
Year 5: 600 tokens, ideas/ folder explains why
```

The `ideas/` folder isn't silly - it's the record of *why* the trajectory differs. When you forget, or someone else looks at it, the thinking is there.

Most projects document *what*. This documents *why the approach*. That's the difference between code that grows and code that distills.

## Human vs LLM division of labor

**[SEAN]:** In the medium and short term humans take advantage over LLMs here. They can operate with greater flops on a smaller set of tokens than LLMs, which means they are naturally most suited for dealing with the axioms. LLMs handle the complex interactions due to their speed. LLMs can't bear the same flops on a small set.

**[CLAUDE]:** Humans think deep on few tokens (axiom design). LLMs think shallow on many tokens (combinatorial expansion). Terse code plays to human strengths at the axiom level, then hands off to LLMs for the grunt work.

**[SEAN]:** It all seems obvious when you think about it.

**[CLAUDE]:** That's the mark of good insight - obvious in retrospect, not practiced anywhere. Most teams do the opposite: humans write verbose code, LLMs struggle with context limits, everyone loses.

**[SEAN]:** Because the thing must ship and before that meant low quality code because rejection is too time consuming in the short term.

**[CLAUDE]:** Ship pressure → accept cruft → cruft accumulates → "legacy code". The rejection loop (send it back, make it terse) was too slow for human-only teams. But LLMs can enforce token discipline instantly. The economics just changed.

**[SEAN]:** Is this how a mathematician should think to write code? Isn't code mathematical algorithm that happens to execute?

**[CLAUDE]:** Yes. Mathematicians seek minimal, elegant proofs - no verbose steps, distill to axioms. Code *is* math that runs. Verbose code is like a proof with unnecessary lemmas - each one a place for errors to hide. APL was designed by a mathematician (Iverson). Terse code is mathematical code. We just forgot because "engineering" meant plumbing.
