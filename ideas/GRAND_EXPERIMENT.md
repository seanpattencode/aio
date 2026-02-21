# The Grand Experiment

Short code + fast ratchet + human-in-loop + single decision maker = compounding acceleration advantage.

## The Positive Feedback Loop

The constraints reinforce each other:

- **Short code** → LLM reads entire codebase in one context window → better AI modifications → code stays short
- **Fast compile** (1.5s) → 200 iterations/day vs ~20 for Rust/TS → 10x more improvement cycles
- **Perf ratchet** → code only gets faster, never slower → each optimization enables future tightening
- **Single decision maker** → zero coordination overhead → OODA loop = human think time, nothing else
- **Scream test** → 100% of work on real pain points → zero wasted effort

Each constraint amplifies the others. Short code enables the ratchet. The ratchet forces further shortening. LLMs modify short code better, which keeps it short. Single decision maker means fix ships in minutes, not sprint cycles. This compounds daily.

## Why This Beats Other Projects

AutoGen, CrewAI, LangChain: multi-contributor coordination, PR review, CI pipelines, architecture committees. Their OODA loop is weeks. Ours is minutes.

They grow code to add features. We shrink code while adding features. Their LLM context cost grows; ours shrinks. Their perf degrades silently. Ours kills regressions instantly.

## Risks

1. **Bus factor of 1.** Mitigated by codebase being LLM-readable — any competent person + Claude could pick it up.
2. **Kolmogorov floor.** Diminishing returns on shortening. But ~180KB for a full agent manager has room.
3. **Autonomous AI improves.** Human-in-loop infrastructure remains valuable — someone still steers.

## The Deep Insight

From DIFF.md: terse code bugs become *variants* rather than *crashes*. When a codebase approaches its axiomatic floor, errors explore the design space rather than breaking it. A qualitative advantage no amount of testing in verbose codebases achieves.
