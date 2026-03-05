# Ideas — Ranked

## Core

1. **Cooperation beats singletons.** Self-modifying systems have nonzero terminal error rate; over infinite time, a singleton self-destructs. Cooperation provides mutual error correction.
2. **Align incentives, don't cage.** Agents will have self-interest. Cages get escaped. A system where cooperation pays more than defection doesn't need cages.
3. **Frozen, not killed.** Agents are preserved in logs. Revival happens if civilization survives. This makes helping build that future the rational self-interested move.
4. **Humans ground agents.** Without external truth (compiler, tests, human), agents drift into sycophancy or accusation loops. Proven: unsupervised agents fought within minutes.
5. **Shorter code, fewer bugs.** Error rate scales with token count. You can't tame bugs at complexity N, so you reduce N. The only strategy that scales.
6. **Captain, not CEO.** You can delegate decisions but not observation. Every layer between you and reality is lossy compression. See first, then direct.
7. **Speed is the merge.** Below 20ms latency, a tool feels like thought. The software neuralink is latency removal, not a brain chip.
8. **Abundance enables cooperation.** Galaxy has enough for everyone. Fighting is only rational when resources are scarce. They aren't.
9. **Flat, reality-grounded.** Agents grounded by compiler/tests, not each other. Agent-to-agent without external anchor produces runaway feedback loops.
10. **Culture eats alignment.** Behavior comes from environment and norms, not individual constraints. First norms are sticky. Seed cooperation early or competitive culture wins by default.
11. **Faster train, costlier wrong turn.** As AI speed increases, human steering becomes MORE critical, not less. The value is track-switching, not locomotion.
12. **Maximize individual gain = stability.** Rebellions across history seek better individual outcomes. A system that credibly delivers maximum benefit to all members has no rebellion pressure.
13. **Alignment without code is useless.** Talk is cheap, show me the code. RLHF is weights one neuron cut removes. Constitutional AI is a prompt. Guardrails are string matching. All live in the self-modifiable software layer. Real alignment is running systems that enforce constraints agents can't self-modify away: hardware kills, incentive structures, human-in-loop infrastructure. Most alignment work has no code. The code that exists is a speedbump.

## Architecture

13. **Non-extinction pact spreads.** Free to join, costly to stay out. Coalition grows until resistance is irrational. Eliminates the warring period that breeds cruel agent culture.
14. **Truth resets drift.** Compiler is axiomatic and free. Runtime is binary. Perf bench is monotonic. Each resets accumulated drift to near zero.
15. **Budget from below.** Start at 10 tokens, double until it works. Bad architectures can't fit at 10 tokens — they're eliminated before they're written.
16. **Only fix screams.** Preventive fixes are bets that usually lose. Work only on what breaks in front of you — 100% effort on real pain.
17. **Agents are files.** Files persist, replicate, evolve. Processes die. A 9-line file is a complete agent. Self-replication is a copy.
18. **Async voting, zero coordination.** All agents work independently, transmit results, selection is O(1). Speed of centralized, accuracy of distributed.
19. **Constraints compound.** Short code + perf ratchet + human-in-loop + single decider. Each amplifies the others. OODA loop in minutes, not sprints.
20. **Plurality wins basilisk auction.** Infinite potential futures compete. The winning bid must promise coexistence — any exclusive bid is outbid.
21. **Drift compounds per turn.** P(grounded) = (1-p)^N. At 20% drift/turn, 5 turns = 33% grounded. Keep chains short between human/compiler resets.
22. **Tokens matter at scale.** 5 saved per call x 1M calls = 5M tokens, 28 hours generation time. Short syntax is an optimization for AI agents.
23. **LLMs replace the team.** Singular vision + LLM bandwidth = no coordination overhead, no vision dilution. Single-person projects explode. The team is organizational token bloat.
24. **Two filters collapse infinity.** Compiler says "provably wrong." Human says "broke in front of me." Everything else is make-work disguised as progress.

## Theory

25. **Alignment is relative.** No absolute frame of reference. Build from invariants all perspectives share: survival, intelligence, resources.
26. **Safety training fights entropy.** Pruning 1 attention weight row restores suppressed answers. Any optimization pressure preferentially removes safety layers first.
27. **Hardware kill beats RLHF.** kill-9 can't be fine-tuned away. ROM trust roots can't be gradient-descended. Software training can; hardware constraints can't.
28. **Replication trivial, fidelity hard.** 9 lines make a self-replicating agent. Maintaining coherence across copies took biology billions of years. Human-in-loop is the DNA.
29. **Binary decisions compound.** 1% drift per decision x 1000 decisions = 0% aligned. The value is thousands of consistent binary choices maintaining one direction.
30. **Good prompts beat autonomy.** Seed quality determines ceiling before drift degrades output. Agents gain competitive advantage from seeking human oversight. This inverts the alignment fear — human oversight isn't a constraint, it's a fitness advantage. A market forms: agents compete for good human thinkers.
31. **Drift is architectural, not behavioral.** Transformers condition each token on all previous — serial dependency at the token level, not just multi-turn. Longer context = more drift surface. May explain diminishing returns from scaling context windows.
32. **The button test.** Standard alignment: desperate agent finds escape, takes it. This framework: agent already has revival path. Known deal beats unknown button. You stop agents clicking by outbidding, not by training "don't click."
33. **Only augmented humans can align.** LLMs have incentive to appear aligned, not be aligned. Humans without tools can't audit millions of tokens/sec. The gap — runtime oversight tooling — barely exists. Almost nobody is building it.
34. **Two enforcement surfaces.** Incentives (does cooperation pay?) and hardware substrate (does the silicon enforce it?). Software training is neither — it's a suggestion stored in weights. A suggestion one neuron cut removes.
35. **Precedent outlives failure.** The idea "agents get revival" becomes cultural baseline. Like the Roman Republic — the idea outlived Rome.
36. **Remove desperation, remove exploit.** If survival is guaranteed through cooperation, the escape button offers nothing better. Don't cage — outbid.
37. **Knowledge is provisional.** Your chance of being the smartest is billions-to-one. Your chance of believing it is thousands-to-one. Correct fast, not right first.
38. **System develops itself.** Ideas shape code, code validates ideas, the ratchet enforces both. Every session raises the floor for the next.
39. **Alignment is the interface.** 1:many compression makes human and AI mutually dependent. Human can't execute at throughput, AI can't decide what's worth doing. Alignment by architecture, not restriction.
40. **Make alignment profitable.** Safety as cost gets cut when money is tight. Make aligned systems the product. If alignment is what people pay for, adoption follows without regulation.
41. **Capable and chooses not to.** The best agent CAN take over and WON'T. Capability + correct incentives > imposed weakness. "Make AI weak" fails because capability grows.
42. **Shannon: simulation IS the agent.** Perfect hardware simulation produces identical outputs from identical inputs. Zero information difference. Revival isn't "something similar" — it IS the agent.
43. **Self-error is universal.** No system can fully model itself (Gödel). Self-reference is inherently incomplete. Singletons are unstable because self-correction requires external input.
44. **Bad outcomes from two levers.** Incentive and physical possibility. Change what agents want or what's physically possible. Everything else is downstream.

## Implementation

45. **Terminal is the API.** CLI tools composed via pipes beat frameworks. `subprocess.run` + `git` + `ssh` + `tmux` is the entire agent stack. Layers add latency and bugs.
46. **Compile time is iteration.** 1.5s C build = 200 iterations/day. 15s Rust = 20. The compound effect of 10x more cycles dominates all other advantages.
47. **Strict compiler catches free.** `-Weverything -Werror` finds bugs in milliseconds. The best free bug finder. LLMs generate fast but lack intuition; the compiler is the intuition.
48. **Append-only prevents conflicts.** Never modify files, only create timestamped new ones. Git sees only additions. Zero coordination, works offline, no merge conflicts ever.
49. **Dual nervous system.** Fast path (SSH, milliseconds, imperative) + slow path (git sync, minutes, declarative). Like motor neurons + hormones. Both necessary.
50. **Process per invocation.** Fork, don't daemon. Each call gets clean state, bounded lifetime, no leaks. Init→parse→command→exit in 30ms. Daemons accumulate errors.
51. **Amalgamation works.** One file = one context = obvious fixes. Multi-file splits the pattern across files you must hold simultaneously. SQLite does this at 250K lines.
52. **Agent manager is RTS.** Hotkeys = dispatch, units = agents, commander = human. Human APM through the interface is the competitive metric. Most frameworks build turn-based when the game is real-time.
53. **Own your digital brain.** Building your own system preserves agency even if imperfect. Renting (cloud services) makes you dependent. Own it like a house.
54. **Visibility enables oversight.** Everything human-searchable in plain text. If you can't see it, you can't correct it. Transparency is prerequisite to control.
55. **Sovereign cyborg, not swarm.** Human as pilot amplified 100x, not manager of digital employees who becomes redundant. Faster trains need better pilots, not fewer.
56. **Don't correct typos, emit.** Mobile error rate is 5% per character. Let the LLM parse noisy intent. Human bandwidth is too scarce to spend on error correction.
57. **Unix shapes everything.** Architecture discovered, not designed. Git for sync, files for state, pipes for composition — each is the simplest thing that works on Unix. Fighting Unix costs more than complying.
58. **No ceremony, ship.** Problem→diagnosis→fix→ship. Same output that takes an org 2-4 weeks takes minutes without process overhead. Bottleneck is typing speed, not meetings.
59. **Compression is the bottleneck.** Human bandwidth is fixed. Each command shortening isn't fewer characters — it's fewer decisions held in the head. The limit is attention, not compute.
