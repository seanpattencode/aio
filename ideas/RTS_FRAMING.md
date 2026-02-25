AI agent manager with human correction IS a real-time strategy game.

Structural mapping:
- Command hotkeys = dispatch table (a c, a g, a 3 — ~90 aliases, O(log n) bsearch)
- Units = agents (claude, gemini, codex — execute autonomously once commanded)
- Commander = human (strategic decisions, corrections, scream test)
- Fog of war = a watch, a ls (observing agent state)
- Orders = a send <session> <prompt> --wait
- Supply cap = 4 concurrent claude jobs (~1.2GB RSS each)
- Multi-base = multi-device SSH, a ssh all, project index
- Build order = coding workcycle
- Tech tree = a install (playwright, ollama, uv = teching up)
- Economy = API credits, compute time, human attention
- APM = human decisions per minute through the interface

Perf benchmarks ARE frame times:
- HSU: 50us per command = 334x faster than a 60fps game frame
- ubuntuSSD4Tb: 0.7-1ms typical = 100x faster than StarCraft 2 input latency
- RTS "instant feel" standard: <100ms. a delivers <1ms.
- perf_kill at 1s = lag spike detector, same as RTS engine dropping frames

Most alignment/agent frameworks build turn-based chess when the game is StarCraft.
They optimize unit stats (smarter agent) and unit leash (safer agent).
They ignore:
- Human APM — how fast can the commander issue orders?
- Interface latency — microseconds vs seconds in the command loop?
- Multi-unit coordination — 4 agents across 3 devices simultaneously?
- Macro vs micro — strategic project selection vs tactical prompt correction

a is C with sub-ms dispatch because human APM in AI coordination IS the competitive metric.
The human bottleneck isn't thinking speed — it's interface friction.
Every ms of latency multiplies across thousands of daily interactions.

Cooperation requires real-time feedback loops.
Interface latency IS the alignment mechanism.
A human who corrects in 50us has fundamentally different control than one waiting 3s for a web UI.
Speed of the correction loop determines whether human remains commander or becomes observer.

Open problem: the auto-fix loop (perf bench fails -> spawns job to fix -> evaluated by perf bench)
is self-referential. Goodhart's law risk: optimizing the proxy not the real thing.
The real evaluation is the scream test — did the human feel it was faster?
Sub-ms differences are below perception, so the proxy is decent, but the auto-fix
has no scream test, just the number.
