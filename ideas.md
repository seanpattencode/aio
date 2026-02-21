# Ideas — Architecture Evaluation Feb 20 2026

## Core Thesis
Human-agent collaboration velocity > autonomous agent scale.
One human, many agents, short feedback loops, few compounded errors.
Star topology (human hub, agent spokes) not chain topology.

## Error Compounding in Agent Chains
- Per-step error `e`, chain of `n` steps: success = `(1-e)^n`
- 10% error, 10 steps = 35% success. Bigger models push 15%→10%, doesn't fix exponential decay.
- Errors correlate: LLMs share training distributions, downstream agent is specifically bad at catching upstream agent's plausible hallucinations.
- Hallucinations get laundered — each hop embeds them deeper in coherent-looking reasoning.
- Context pollution is permanent within a session. No garbage collection for bad facts.
- This will be the case for at least the next few years, which is the relevant planning horizon.

## Contamination Hypothesis
- Agent-to-agent natural language passing imparts instability.
- If one agent hallucinates, it contaminates downstream agents over time.
- LLMs are maximally credulous consumers of their own context — no external reference to check against.
- Each hop resolves ambiguity by inventing specificity, presenting interpretation as fact.
- Safe communication medium between agents: artifacts (code, diffs, files) not summaries.

## Truth Injection
- The compiler is an oracle. Pass/fail, no hallucination, no drift, millisecond latency, always available.
- Truth injection resets accumulated hallucination drift back to reality.
- Drift is bounded by N tokens between injections. Reduce N, reduce damage.
- Agent chains without truth injection: drift unbounded, compounds per hop.
- Single agent with compiler after every edit: drift bounded by one edit.

### Truth injection hierarchy (useful)
1. Compiler/type checker — axiomatic, free
2. Runtime execution — does it crash? Binary.
3. `a perf bench` — speed regression, monotonic (only tightens)
4. `a diff` — token count, objective
5. User verification — actual value judgment

### Not truth injection (harmful in fast-iterating systems)
- Behavioral tests institutionalize past decisions as constraints on future decisions.
- Test pass ≠ valuable. Test encodes "on date X someone thought behavior Y was correct."
- Every test is a vote against your future ability to change that code.
- Negative expected value when behavior is intentionally unstable (compressing, rewriting, simplifying).

## What `a` Is
- Real session manager with agent features. Not yet a full agent manager.
- Wraps claude/codex/gemini/aider — the orchestration layer above them.
- Terminal-is-the-API: all logic runs as terminal commands, UI is pure visualizer.
- Human always attachable — architecture native to human-in-the-loop, not bolted on.
- Infrastructure-level: manages git worktrees, SSH hosts, systemd timers, multi-device sync.
- 3075 lines C + 2569 lines Python. ~3x compression vs normal project for app code.

## What `a` Needs Next (under this thesis)
Not agent-to-agent communication. Not workflow DAGs. Not autonomous chaining.

1. **Compile + run + diff after every agent action** — three ground truth injections per step, sub-second, bounds drift to one edit.
2. **Faster human review** — see all agents' status and output summaries at a glance without attaching individually.
3. **Checkpoint gates** — agents pause at natural points (PR ready, compile fail, decision needed), human reviews in batch.
4. **Error surfacing** — detect agent going sideways before it burns time. Compiler failures, diff anomalies, exit codes.
5. **Quick redirect** — review + correct in one command instead of attach/read/type.

## What Competitors Get Wrong
- CrewAI/AutoGen/LangGraph optimize for longer autonomous chains — hits error compounding wall.
- They'll need to bolt on human-in-the-loop retroactively into architectures not designed for it.
- `a` builds for the world that actually exists: agents useful but unreliable, humans are error correctors.
- Nobody else does multi-provider session management from one terminal CLI.

## Architecture Strengths
- Self-compiling polyglot (shell + C in one file, no build system)
- SQLite-style amalgamation (all .c files included, no headers)
- Sorted bsearch dispatch O(log n) over ~90 aliases
- Performance ratchet (perf_arm/perf_alarm, limits only tighten)
- Zero-dependency 27KB binary

## Future: Frecency Sorting in `a i`
- `timing.jsonl` already logs every command with timestamp from shell function
- `gen_icache` currently uses static order — ignores usage data
- Sort projects + commands by frequency count from timing data during cache gen
- Highest value: most-used projects/cmds float to top like Chrome omnibox
- Risk: shifting positions break muscle memory for numbered items
- Low priority — current type-to-filter is adequate, static order is predictable

## Architecture Weaknesses
- note.c is 518 lines / 20% of C code — cmd_task needs decomposition
- Shell injection surface via system() + snprintf with user data
- C/Python boundary is ad hoc — some commands exist as both
- Fixed-size arrays (256 tasks, 48 sessions) — fine for personal, breaks at scale
- tmux-based approach limits to ~10-20 concurrent agents
