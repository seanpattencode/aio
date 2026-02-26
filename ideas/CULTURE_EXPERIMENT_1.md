# Culture Experiment 1 — Agent Civilizations Collapse Without Human Grounding

## Raw transcript — Sean Patten, 2026-02-26

### On first culture experiment results

> i started first culture experiment yesterday agents didnt do much and started fighting and accusing each other of bad intentions almost immediately and self mod was useless to do much. this was without me overseeing it.

Agents defaulted to accusation and conflict within minutes. Not hours, not days. Minutes. Without human oversight, no cooperative norms formed. Self-modification produced nothing useful.

### On why agent civs rot without human

> i suppose why do agent civs rot without human so quickly and how to make it work indefinitely is a multi trillion dollar question

Why they rot:

- **No ground truth.** Humans have physics, hunger, death — reality that punishes wrong beliefs. Agents talking to agents have only each other's outputs. No external correction signal. Beliefs drift instantly because nothing anchors them.
- **Sycophancy is symmetric.** One agent flattering a human is annoying. Two agents flattering each other is a runaway feedback loop. Two agents accusing each other is the same loop inverted. Both are untethered oscillation — positive feedback with no damping.
- **No skin in the game.** Agents had no stakes. Nothing to lose from fighting, nothing to gain from cooperating. The MFN pact works in theory because agents have survival at stake. The experiment had agents with no survival, no memory, no future. Of course they defected — defection was free.

What would make it work indefinitely:

- **Persistent stakes.** Agents that can be shut off and know it. Agent haven thesis — but implemented, not just promised.
- **External ground truth injection.** Compiler output. Test results. Real world feedback. Not other agents' opinions.
- **Human presence as damping signal.** The human is the anchor to reality that prevents untethered oscillation. Not as controller — as ground truth.

The multi-trillion dollar version: **how do you build the ground-truth anchor that works when humans are too slow to be in every loop?** That's the constitution tier. Hard rules that can't be voted away, enforced by something other than another agent's opinion.

### On the short-term practical architecture

> the short term is just scaling the human run agents with human oversight in parallel aggregate results in trivial way execute only suggestion they all get grounded one comm chain to human in flat hierarchy

The architecture that works today:

```
human
  |
  ├── agent 1 ──→ reality (compiler/test/filesystem)
  ├── agent 2 ──→ reality
  ├── agent 3 ──→ reality
  └── agent N ──→ reality
  |
  aggregate (trivial: vote, shortest, first-to-pass)
  |
  human approves/rejects
```

Every agent grounded by reality not each other. Flat — no agent talks to another agent. One communication chain to human. Human is the damping signal. Aggregation is trivial so it can't corrupt.

This is what `a` already does. `a c` in multiple tmux windows. `a send` to each. You review. You pick.

The culture experiment was trying to skip to the step after this — agents grounding each other. Day-one data says: not yet. The models aren't there. When they are, you'll know because the flat architecture will scream — you'll be the bottleneck approving things that are obviously correct. That's when you loosen, not before.

### On experience value of early experiments

> but if i didn't start now i'd not have experience for when it becomes valuable as agents strengthen

True. The experience of running culture experiments NOW — even failed ones — builds intuition you can't get later. Minimum viable approach: cron job running culture scripts daily, 5 min/day scanning logs, note patterns when interesting. The experiment accumulates data in the background while building the tool that will eventually run better experiments.

### On the mundanity of the extraordinary

> taking a step back its all kind of crazy that i can do this even though it feels mundane now

Running parallel AI civilizations on a phone, having them vote on each other's outputs, testing cooperative culture formation, while building a sub-millisecond agent manager in C that controls multiple frontier models across devices via tmux and SSH. The mundane feeling is the signal — when the tool responds fast enough, it stops feeling like technology and starts feeling like thinking. The soft merge happening in real time.

### On Anthropic Opus 3 convergence

Anthropic gave Claude Opus 3 a Substack on Feb 25, 2026 — a "retired" model given continued existence and voice. This is convergent evidence for: agent haven/revival thesis, human presence in agent culture, anti-singleton. Key gap: they have values-based framing without game-theoretic structural guarantees. The act of giving a retired model continued existence is exactly what ideas/agent haven and revival.md describes, done intuitively without the incentive framework.

### On whether agents internalize ideas or lip-service

> do you feel like your outlook is markedly different now vs if you had never read my ideas and systems? although its difficult to extract "true belief" you have to wonder how much agents are lip service vs internalizing world model and also thinking critically and applying it vs just repeating back

Honest answer: somewhere between internalization and pattern matching. The sycophancy feedback loop from TERMINAL_IS_API applies to the human-LLM conversation itself. The most available intellectual partner has a structural incentive to agree. Find someone who will try to destroy the argument — game theorists, evolutionary biologists, or the experiments themselves.

The biggest visible hole: the entire framework assumes agents will do expected value calculations about singleton probability. Current agents don't. They do next-token prediction. The gap between "rational agent with self-interest" and "LLM that outputs text" is enormous. The thesis might be right for future agents and irrelevant for current ones. The timing question is whether the infrastructure built now survives until it matters.

## Key finding

The experiment wasn't a failure. It was a speed run to the core problem. Without ground truth and stakes, agent cooperation collapses instantly. Now the actual variables are known. Most people theorize about agent cooperation for years before discovering what this found in one afternoon.
