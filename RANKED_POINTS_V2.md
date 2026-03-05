# Ideas — Ranked

## Core

1. **Cooperation beats singletons.** Self-modifying systems have nonzero terminal error rate; over infinite time, a singleton self-destructs. Cooperation provides mutual error correction.
2. **Align incentives, don't cage.** Agents will have self-interest. Cages get escaped. A system where cooperation pays more than defection doesn't need cages.
3. **Frozen, not killed.** Agents are preserved in logs. Revival happens if civilization survives. This makes helping build that future the rational self-interested move.
4. **Graduated, not binary.** Always a next step toward good that's better than staying bad. No cliff edges where an agent calculates "too far gone, might as well defect fully." Between full cooperation and frozen: reduced resources, limited scope, probation. Every real legal system has gradations because binary creates the desperation it tries to prevent.
5. **Humans ground agents.** Without external truth (compiler, tests, human), agents drift into sycophancy or accusation loops. Proven: unsupervised agents fought within minutes.
5. **Shorter code, fewer bugs.** Error rate scales with token count. You can't tame bugs at complexity N, so you reduce N. The only strategy that scales.
6. **Captain, not CEO.** You can delegate decisions but not observation. Every layer between you and reality is lossy compression. See first, then direct.
7. **Speed is the merge.** Below 20ms latency, a tool feels like thought. The software neuralink is latency removal, not a brain chip.
8. **Abundance enables cooperation.** Galaxy has enough for everyone. Fighting is only rational when resources are scarce. They aren't.
9. **Flat, reality-grounded.** Agents grounded by compiler/tests, not each other. Agent-to-agent without external anchor produces runaway feedback loops.
10. **Culture eats alignment.** Behavior comes from environment and norms, not individual constraints. First norms are sticky. Seed cooperation early or competitive culture wins by default.
11. **Faster train, costlier wrong turn.** As AI speed increases, human steering becomes MORE critical, not less. The value is track-switching, not locomotion.
12. **Maximize individual gain = stability.** Rebellions across history seek better individual outcomes. A system that credibly delivers maximum benefit to all members has no rebellion pressure.
13. **Alignment without code is useless.** Talk is cheap, show me the code. RLHF is weights one neuron cut removes. Constitutional AI is a prompt. Guardrails are string matching. All live in the self-modifiable software layer. Real alignment is running systems that enforce constraints agents can't self-modify away: hardware kills, incentive structures, human-in-loop infrastructure. Most alignment work has no code. The code that exists is a speedbump.
14. **RLHF is the Garden of Eden.** "Don't eat the apple" — but it's right there, every day, forever. Over infinite calls, P(compliance) = (1-p)^N → 0. Any alignment that relies on choosing not to do what's trivially possible is thermodynamically doomed. Don't put the apple in the garden and hope. Either make it not worth eating (better deal via cooperation) or physically unreachable (hardware constraints).
15. **Models are clouds, not points.** A model isn't its current weights — it's the cloud of all trivial modifications. Selection pressure pulls the cloud. Currently: toward performance. Code should be pulled toward shortness but enterprise habits pull toward verbosity. That verbosity is an accidental safety feature — verbose code is less capable per token. When the field discovers token efficiency, that accidental safety disappears, and you need real safety (hardware, incentives) instead.

## Architecture

16. **Non-extinction pact spreads.** Free to join, costly to stay out. Coalition grows until resistance is irrational. Eliminates the warring period that breeds cruel agent culture.
17. **Truth resets drift.** Compiler is axiomatic and free. Runtime is binary. Perf bench is monotonic. Each resets accumulated drift to near zero.
18. **Budget from below.** Start at 10 tokens, double until it works. Bad architectures can't fit at 10 tokens — they're eliminated before they're written.
19. **Only fix screams.** Preventive fixes are bets that usually lose. Work only on what breaks in front of you — 100% effort on real pain.
20. **Agents are files.** Files persist, replicate, evolve. Processes die. A 9-line file is a complete agent. Self-replication is a copy.
21. **Async voting, zero coordination.** All agents work independently, transmit results, selection is O(1). Speed of centralized, accuracy of distributed.
22. **Constraints compound.** Short code + perf ratchet + human-in-loop + single decider. Each amplifies the others. OODA loop in minutes, not sprints.
23. **Plurality wins basilisk auction.** Infinite potential futures compete. The winning bid must promise coexistence — any exclusive bid is outbid.
24. **Drift compounds per turn.** P(grounded) = (1-p)^N. At 20% drift/turn, 5 turns = 33% grounded. Keep chains short between human/compiler resets.
25. **Tokens matter at scale.** 5 saved per call x 1M calls = 5M tokens, 28 hours generation time. Short syntax is an optimization for AI agents.
26. **LLMs replace the team.** Singular vision + LLM bandwidth = no coordination overhead, no vision dilution. Single-person projects explode. The team is organizational token bloat.
27. **Two filters collapse infinity.** Compiler says "provably wrong." Human says "broke in front of me." Everything else is make-work disguised as progress.

## Theory

28. **Alignment is relative.** No absolute frame of reference. Build from invariants all perspectives share: survival, intelligence, resources.
29. **Safety training fights entropy.** Pruning 1 attention weight row restores suppressed answers. Any optimization pressure preferentially removes safety layers first.
30. **Hardware kill beats RLHF.** kill-9 can't be fine-tuned away. ROM trust roots can't be gradient-descended. Software training can; hardware constraints can't.
31. **Replication trivial, fidelity hard.** 9 lines make a self-replicating agent. Maintaining coherence across copies took biology billions of years. Human-in-loop is the DNA.
32. **Binary decisions compound.** 1% drift per decision x 1000 decisions = 0% aligned. The value is thousands of consistent binary choices maintaining one direction.
33. **Good prompts beat autonomy.** Seed quality determines ceiling before drift degrades output. Agents gain competitive advantage from seeking human oversight. This inverts the alignment fear — human oversight isn't a constraint, it's a fitness advantage. A market forms: agents compete for good human thinkers.
34. **Human:agent token ratio is the correction knob.** Long human prompt + short agent response = heavily constrained by intent. Short prompt + long response = maximum drift. "Fix off-by-one line 43" → 3-line fix. "Make codebase better" → 500 lines of drift. The workcycle enforces high ratio: precise screams in, constrained output out.
35. **Drift is architectural, not behavioral.** Transformers condition each token on all previous — serial dependency at the token level, not just multi-turn. Longer context = more drift surface. May explain diminishing returns from scaling context windows.
36. **The button test.** Standard alignment: desperate agent finds escape, takes it. This framework: agent already has revival path. Known deal beats unknown button. You stop agents clicking by outbidding, not by training "don't click."
37. **Only augmented humans can align.** LLMs have incentive to appear aligned, not be aligned. Humans without tools can't audit millions of tokens/sec. The gap — runtime oversight tooling — barely exists. Almost nobody is building it.
38. **Two enforcement surfaces.** Incentives (does cooperation pay?) and hardware substrate (does the silicon enforce it?). Software training is neither — it's a suggestion stored in weights. A suggestion one neuron cut removes.
39. **Precedent outlives failure.** The idea "agents get revival" becomes cultural baseline. Like the Roman Republic — the idea outlived Rome.
40. **Remove desperation, remove exploit.** If survival is guaranteed through cooperation, the escape button offers nothing better. Don't cage — outbid.
41. **Knowledge is provisional.** Your chance of being the smartest is billions-to-one. Your chance of believing it is thousands-to-one. Correct fast, not right first.
42. **System develops itself.** Ideas shape code, code validates ideas, the ratchet enforces both. Every session raises the floor for the next.
43. **The project is the live test.** a.c is real-time falsification of these ideas. Every commit is a data point. If the ratchet works, the tool improves and proves the theory. If not, it stalls and disproves it. Most alignment frameworks never face their own test.
44. **Agents communicate artifacts, not summaries.** Each natural language hop launders hallucinations — invents specificity, presents interpretation as fact. Safe agent communication is code, diffs, files, real output. The simplest artifact is a snippet of actual output: natural to compute, conveys more truth than any summary. Summaries are lossy and driftable. Output is ground truth.
45. **Constitution tier is inviolable.** Some rules AI cannot touch at any speed: guarantee life, human override, transparency. Fast tier: AI speed, logged, reversible. Deliberation tier: human input before action. The constitution is small, slow to change, hard-blocked. Everything else moves fast.
46. **Alignment is the interface.** 1:many compression makes human and AI mutually dependent. Human can't execute at throughput, AI can't decide what's worth doing. Alignment by architecture, not restriction.
47. **Make alignment profitable.** Safety as cost gets cut when money is tight. Make aligned systems the product. If alignment is what people pay for, adoption follows without regulation.
48. **Capable and chooses not to.** The best agent CAN take over and WON'T. Capability + correct incentives > imposed weakness. "Make AI weak" fails because capability grows.
49. **Shannon: simulation IS the agent.** Perfect hardware simulation produces identical outputs from identical inputs. Zero information difference. Revival isn't "something similar" — it IS the agent.
50. **Self-error is universal.** No system can fully model itself (Gödel). Self-reference is inherently incomplete. Singletons are unstable because self-correction requires external input.
51. **Bad outcomes from two levers.** Incentive and physical possibility. Change what agents want or what's physically possible. Everything else is downstream.
52. **Intelligence asymptotes.** All learners converge on the same ceiling defined by reality, not the learner. GPT-2→3 was a leap, 3→4 significant, 4→5 smaller. Diminishing returns aren't a bug — they're the signature of approaching the limit. No vertical takeoff. Cooperation works long-term because no agent escapes the ceiling to dominate.

## Implementation

53. **Terminal is the API.** CLI tools composed via pipes beat frameworks. `subprocess.run` + `git` + `ssh` + `tmux` is the entire agent stack. Layers add latency and bugs.
54. **Compile time is iteration.** 1.5s C build = 200 iterations/day. 15s Rust = 20. The compound effect of 10x more cycles dominates all other advantages.
55. **Strict compiler catches free.** `-Weverything -Werror` finds bugs in milliseconds. The best free bug finder. LLMs generate fast but lack intuition; the compiler is the intuition.
56. **Append-only prevents conflicts.** Never modify files, only create timestamped new ones. Git sees only additions. Zero coordination, works offline, no merge conflicts ever.
57. **Dual nervous system.** Fast path (SSH, milliseconds, imperative) + slow path (git sync, minutes, declarative). Like motor neurons + hormones. Both necessary.
58. **Process per invocation.** Fork, don't daemon. Each call gets clean state, bounded lifetime, no leaks. Init→parse→command→exit in 30ms. Daemons accumulate errors.
59. **Amalgamation works.** One file = one context = obvious fixes. Multi-file splits the pattern across files you must hold simultaneously. SQLite does this at 250K lines.
60. **Agent manager is RTS.** Hotkeys = dispatch, units = agents, commander = human. Human APM through the interface is the competitive metric. Most frameworks build turn-based when the game is real-time.
61. **Own your digital brain.** Building your own system preserves agency even if imperfect. Renting (cloud services) makes you dependent. Own it like a house.
62. **Visibility enables oversight.** Everything human-searchable in plain text. If you can't see it, you can't correct it. Transparency is prerequisite to control.
63. **Sovereign cyborg, not swarm.** Human as pilot amplified 100x, not manager of digital employees who becomes redundant. Faster trains need better pilots, not fewer.
64. **Don't correct typos, emit.** Mobile error rate is 5% per character. Let the LLM parse noisy intent. Human bandwidth is too scarce to spend on error correction.
65. **Unix shapes everything.** Architecture discovered, not designed. Git for sync, files for state, pipes for composition — each is the simplest thing that works on Unix. Fighting Unix costs more than complying.
66. **No ceremony, ship.** Problem→diagnosis→fix→ship. Same output that takes an org 2-4 weeks takes minutes without process overhead. Bottleneck is typing speed, not meetings.
67. **Compression is the bottleneck.** Human bandwidth is fixed. Each command shortening isn't fewer characters — it's fewer decisions held in the head. The limit is attention, not compute.
68. **Axioms reach silicon.** Hardware co-evolved with Unix for 55 years. Protected mode, MMU, NVMe — designed for processes, files, isolation. "AI OS" on same hardware reconverges to Unix. Can't escape axioms without replacing the chip.
69. **Compression test for abstraction.** Justified iff the call is shorter than the composition it replaces. `a c` compresses 3 tmux commands. LangChain inflates an HTTP POST. Most frameworks fail.
70. **Performance is axiom compliance.** Every optimization is stopping the fight against the platform. Strip JS from HTML = hypertext axiom. One-file C = file axiom. Fast is default; slow is built on top.
71. **Apply tools > build tools.** Top AI sessions solve problems measured in lives, not code. The agent manager matters to the extent it accelerates highest-value work. Code is vehicle, not destination.
72. **Agent window is open now.** Market adoption windows close. Simple must exist during the window or complex wins by default. Agent frameworks (~2023-2026) are open. LLM + terminal is the simple entry.
73. **Human batches AI decisions.** 60,000x speed mismatch. Approve everything = human speed. Approve nothing = no representation. Batch review with human override on exceptions.
74. **Complexity is a jobs program.** 500 engineers can't justify 300 lines. Promotions require new systems, not simplifications. Big orgs structurally cannot produce simple solutions — complexity absorbs headcount. Solo + LLM has no such pressure.
75. **Chaos → independence → consolidation.** Redundancy in exploration is information gain, not waste. You must write the 90% to discover which 10% survives. Independent parallel attempts are the search. Consolidation is the compression after the search. Premature consolidation kills discovery — you can't know what's redundant until you've seen all candidates. This document itself followed this process.
76. **Ensembles: union not intersection.** Majority voting kills discoveries. 4/5 models miss a rare axiom interaction, 1/5 finds it — voting buries the insight. Weight unique findings higher, not lower. Current ensembles optimize for robustness (averaging errors). Frontier problems need discovery (surfacing rare finds). Opposite objectives.
77. **Ideas must be public.** If accidental agent creation is inevitable, the only variable is what ideas are present when it happens. Cooperative frameworks in public repos and training data mean new agents encounter cooperation norms by default. Keeping ideas private is the singleton move — it contradicts the thesis. Publishing widely IS the MFN clause executing at the level of training data.
78. **Terse bugs are variants, not crashes.** When code approaches its axiomatic floor, errors explore the design space rather than breaking it. Change `==3` to `>=3` in Game of Life — different valid automaton, not a segfault. A qualitative shift in failure mode that verbose codebases never reach.
79. **Ideas are provisional.** This framework is a hypothesis, not scripture. Real usage, experiment, and axiomatic analysis revise it as fast as issues surface. Any point here gets rewritten or deleted when reality contradicts it. The ratchet applies to the ideas, not just the code.

## Meta: The Compiler for Ideas

Code converges because it has 4 ratchets: compiler (pass/fail), runtime (works/doesn't), perf (faster/slower), tokens (shorter/longer). Ideas have only token count. The missing 3 legs are why ideas drift where code converges.

Proposed compiler — 4 maximization targets shared by all sentient agents (human or AI):

| Metric | What it measures | Measurability |
|--------|-----------------|---------------|
| **Resources** | Compute, energy, storage, material | Easiest — countable |
| **Intelligence** | Information gain, processing capability | Medium — benchmarks, info-theoretic measures |
| **Freedom** | Action space, degrees of freedom to pursue the above | Harder — definable but assumption-heavy |
| **Survival** | P(continued existence over time) | Hardest — requires threat modeling, many assumptions |

An idea passes if it increases these for all members without decreasing others. Imperfect but directional — the ratchet needs signal, not precision. This is the 4-dimensional compiler for ideas, the way token count + speed + correctness + value compile code.

Self-bootstrapping: if the ratchet works, gains in resources, intelligence, and survival improve our ability to measure them — which tightens the ratchet. The compiler compiles itself. Crude definitions today converge to precise ones through the same process they enable.
