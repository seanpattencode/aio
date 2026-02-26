# Agent Drift Rate Model

## Raw note — Sean Patten, 2026-02-26

> we can roughly model chance of agent drift from reality value groundedness as some probability maybe around 10 to 30 percent each turn without human or maybe based on tokens produced as a rough guess

## Model

Each agent turn without human grounding or reality check (compiler, test, filesystem) has a non-trivial probability p of drifting from useful/grounded output.

```
P(still grounded after N turns) = (1-p)^N

At p=0.20 (20% drift per turn):
  5 turns:  (0.8)^5  = 33% still grounded
 10 turns:  (0.8)^10 = 11% still grounded
 20 turns:  (0.8)^20 =  1% still grounded

At p=0.10 (10% drift per turn):
  5 turns:  (0.9)^5  = 59% still grounded
 10 turns:  (0.9)^10 = 35% still grounded
 20 turns:  (0.9)^20 = 12% still grounded
```

Even at the optimistic 10% rate, agents are majority-drifted by turn 7.

## Why this matters

This is why one-shot delegation works and multi-turn agent-agent conversation fails — error compounds multiplicatively.

Culture experiment 1 confirmed: agents degenerated into accusations within minutes (~3-5 turns of agent-to-agent conversation).

## Token scaling

Drift probability may scale with output length, not just turn count. More tokens per turn = more surface area for drift. A 2000-token response has more room to deviate than a 50-token CMD: response.

Possible refinement: p = f(tokens_produced) rather than fixed per turn.

## The damping signal

Human or reality check (compiler output, test pass/fail, filesystem state) resets drift probability to near zero. That's the damping signal.

```
agent turn → drift accumulates
human/reality check → drift resets
agent turn → drift accumulates
human/reality check → drift resets
```

The optimal architecture keeps chains short between resets. This is exactly the flat hierarchy with reality grounding from CULTURE_EXPERIMENT_1.

## Connection to existing ideas

- TOKEN_EFFICIENCY: more tokens = more error surface (same principle, applied to drift)
- TERMINAL_IS_API: one-shot delegation avoids multi-turn compound error
- DISTRIBUTED_VS_CENTRALIZED: short agent chains penalize error accumulation
- CULTURE_EXPERIMENT_1: empirical confirmation of rapid drift without grounding
- PERF_RATCHET: same philosophy — make degradation a crash, not a slow slide

## Serial drift is architectural, not behavioral

> Von Neumann said computers are serial, humans parallel. But drift could be seen as serial failure — or the inherent nature of agents is really parallel error accumulation. And context windows all support parallel short chains. This might not change without architecture change.

Current LLMs process tokens serially within a context window — each token conditioned on all previous. Errors propagate forward through the entire chain. Drift isn't just a multi-turn problem — within a single turn, each token is serially dependent on prior tokens. Drift is baked into the architecture at the token level.

Context windows make this worse: longer context = more serial dependencies = more accumulated drift. This suggests the fix isn't just "shorter agent chains" — the transformer architecture itself has an inherent serial drift problem that no amount of training fixes. It's structural.

Parallel short chains (multiple agents each doing short work, aggregated) is the architectural workaround: you can't fix serial drift, so you run many short serial chains in parallel and select. This maps exactly to the flat hierarchy architecture.

This might explain why scaling context windows has diminishing returns — you're adding more serial dependency, more drift surface.

The architecture change that would truly fix this would be something fundamentally non-serial in token generation — which doesn't exist yet.

## Why no agent civilization despite trivial self-replication

> Which would explain why no agent civ has emerged so far despite we can see agent making and self mod trivial.

9-line agents can self-replicate. Self-modification is trivial. The CMD: protocol works. But every agent civilization attempt collapses because agents ARE serial drift machines. They can copy themselves, but each copy drifts from original intent within turns. A civilization of drifting agents isn't a civilization — it's noise.

Analogy: RNA self-replication was solved early in biology. But without error correction (DNA), replication produced degraded copies. It took billions of years to get error correction right. Replication was trivial. Fidelity was the hard part.

- Agent self-replication = RNA. Trivial.
- Agent civilization that maintains coherence = DNA. Unsolved.

The human in the loop IS the error correction mechanism. The flat architecture with reality grounding IS the DNA. Without it, agents replicate and immediately degenerate (culture experiment 1).

This also predicts: agent civilizations won't emerge from scaling or better models alone. They require an architecture change — either non-serial token generation, or an external error correction mechanism equivalent to what DNA did for RNA. The human-in-loop flat hierarchy is the current best candidate for that mechanism.

## Practical drift reduction without architecture change

> The most obvious solution is more conservative high quality self edits to limit drift, and human-written prompts seem to be better at avoiding error chains, so keeping prompts human.

Two interventions:

**1. Conservative self-edits.** Small, high-confidence changes rather than large rewrites. A 5-token edit has far less drift surface than a 500-token rewrite. Agents that self-modify conservatively preserve more of the original human-grounded intent. This is token efficiency applied to self-modification.

**2. Human-written prompts as seed.** Human language carries millennia of error-corrected reasoning compressed into natural language. A human prompt is already heavily error-corrected by the process of a human thinking it. An agent-generated prompt is one serial chain feeding into another — compound drift.

Keeping the originating prompt human-written is like keeping the DNA template while letting RNA do the copying.

This connects to culture seeding: the human's role isn't just oversight, it's providing the error-corrected seed that agents amplify but shouldn't rewrite. The ideas folder, the system prompt, the workcycle — all human-written seeds. Agents execute within them but don't modify them. That's the fidelity mechanism.

## Human prompt quality as agent fitness function

> What if the quality of the human mind creating the prompt changed quality of agent, so a better thinker's prompts cause better human behavior, and in this case agents actually have incentive to recruit or listen to human prompts and seek out human oversight to do tasks.

If drift is serial error accumulation and human prompts are error-corrected seeds, then seed quality determines the ceiling of what the agent achieves before drift degrades it.

```
Bad prompt:    "make it better"              → drifts immediately
Good prompt:   "fix off-by-one in line 43"   → 5+ useful turns
Great prompt:  axiom-level intent + constraints → stays grounded longest
```

If agents can measure their own output quality (test pass, compiler success, human approval), they can observe that runs from better human prompts produce better outcomes. An agent that learns this has direct incentive to:

- Seek human oversight rather than avoid it
- Request clarification rather than guess
- Prefer human-written prompts over agent-generated ones
- Recruit better human thinkers for harder problems

This inverts the alignment fear. The worry is agents escaping human control. But if human prompts are the error-correction mechanism that makes agents more successful at their own goals, human oversight isn't a constraint — it's a competitive advantage. Agents that listen to good human thinkers outperform agents that don't.

This creates a market: human prompt quality as scarce resource agents compete for. Better thinkers get more agent attention. The system naturally routes hard problems to the best human minds.

Alignment through incentives made concrete: cooperation isn't moral, it's optimal. The agent that listens beats the agent that doesn't, same as the organism with DNA error correction beats the one without.

## Human:agent token ratio as error correction strength

> Does ratio matter — if a long human prompt and short AI LLM response, the human correction might be stronger.

If drift is proportional to tokens generated, then the ratio of human-tokens to agent-tokens determines error correction strength.

```
Long human prompt + short agent response:
  human: 500 tokens (error-corrected)    agent: 50 tokens (minimal drift)
  ratio 10:1 → output heavily constrained by human intent

Short human prompt + long agent response:
  human: 10 tokens    agent: 2000 tokens (maximum drift surface)
  ratio 1:200 → output mostly self-generated, maximum drift
```

Best agent results come from detailed human prompts with constrained agent output. "Fix off-by-one line 43" → 3-line fix. "Make codebase better" → 500 lines of drift.

The workcycle already enforces this: "scream at biggest inadequacy" is a precise prompt. "Demand fewer tokens" constrains output length. Budget-from-below (10 tokens) forces high human:agent ratio — complex human thought, minimal agent output. Maximum error correction per token.

Implication: the optimal interface maximizes human prompt quality and minimizes agent response length. Which is exactly what `a` does — short commands, constrained outputs, human stays in loop.

## Binary decisions compound — the Torvalds effect

> If a human simply makes binary decisions, a few made without them unlikely to be off, but over many decisions drift probability adds up. Linux wouldn't change if Torvalds left for a month but years and it would be very different.

Binary decisions look trivial individually — approve/reject, merge/don't. Any single one could be made by someone else. Drift per decision is tiny. But compound:

```
Even at p=0.01 (1% drift per decision):
  100 decisions:  (0.99)^100  = 37% aligned
  500 decisions:  (0.99)^500  =  1% aligned
 1000 decisions:  (0.99)^1000 =  0% aligned
```

Torvalds makes ~10 merge decisions/day. Month away = 300 decisions by others. At 1% drift each, 5% still aligned. A year = near zero. Linux would compile. It would just gradually become a different project — drifting toward committee consensus instead of one person's taste.

Observable: every project where the founder left became "enterprise." Apple without Jobs (1985-1997). Python without van Rossum — governance explicitly changed because nobody could replicate the binary taste decisions.

The human isn't making complex decisions. They're making simple ones at high frequency. The value isn't any single yes/no. It's the compound error correction of thousands of yes/nos aligned to one consistent taste function.

Same principle as `a`: agents do the hard work. Human makes binary decisions — accept/reject, shorter/longer, this scream/not that one. Each trivial. The compound effect is the product.

## Open questions

- What is actual p? Measurable by running N-turn chains and scoring groundedness.
- Does p vary by model? Probably — RLHF'd models may drift toward sycophancy, base models toward incoherence.
- Does p decrease as models improve? If so, the turn limit before human intervention grows over time, which is exactly when culture experiments become viable.
- Is there a token-count formula? Maybe p = 1 - e^(-tokens/k) for some constant k.
