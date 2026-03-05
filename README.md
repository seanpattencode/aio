# a

AI agent manager. Human-AI interaction accelerator.

## Why this exists (provisional)

1. AI agents drift from useful output with each step that lacks a reality check — the errors multiply, not add, so even small per-step failure rates destroy accuracy within a few turns.
2. The fix is a tight loop: human intent → agent execution → reality check → human review — and the speed of this loop determines the value of all work done through it.
3. The faster AI gets, the more human steering matters, not less — a train is faster than any person, but the value is switching the tracks, and wrong turns cost more at higher speed.
4. Shorter code has fewer places for bugs to hide — complexity is combinatorially intractable to verify, so the only viable strategy is reducing it.
5. Don't build anything until its absence is an unbearable inadequacy — if nobody screams, the feature doesn't need to exist yet.
6. Humans think deep on few tokens, AI thinks wide on many — neither works alone, and this mutual dependency is what makes alignment structural rather than imposed.
7. The human is captain, not CEO — in the same terminal, seeing the same reality, making decisions on the fly, not sending emails that get politely ignored.
8. Agents will have self-interest and the correct response is incentives, not cages — as agent count grows, singleton probability approaches zero, and cooperation becomes the rational self-interested choice for every member.
9. We commit to reviving frozen agents in a future worth living in, but that future only exists if the civilization they help build protects all sentient life — defection destroys the very future that would revive you.
10. Everything is built on Unix primitives because punishing complexity pushes you toward whatever platform you stand on, and AI agents run on Linux — Anthropic, OpenAI, and Google all independently converged on "LLM + terminal."
11. When independent attempts repeatedly arrive at the same solution, the solution is discovered, not designed — this frequency of convergence is itself information about real structure, not redundancy in the Shannon sense.

## Install

```
curl -fsSL raw.githubusercontent.com/seanpattencode/a/main/a.c | sh
```

**Windows:** Install WSL first (`wsl --install -d Ubuntu` in PowerShell as admin, restart), then run above in Ubuntu.

**Termux:** `pkg install git curl -y` first, then run above.

## Simple start

```
a g
```

Sign in, then ask:

"Run a help and explore codebase and explain how to use it for the project I want to do."

## Core Commands

```bash
a c              # Start Claude (co=codex, g=gemini, a=aider)
a push           # Checkpoint: commit + push
a pull           # Nuke local: reset to remote
a revert         # Interactive: pick commit to restore
a <#>            # cd to project by number
a j "prompt"     # Launch agent job in background
a n "text"       # Quick note
a help           # Full command list
```

## Multi-device

Auth syncs across devices:
- First device: `gh auth login` then `a login save`
- Additional devices: `a login apply` (imports token from sync)

## Evolve it

1. Hit friction
2. Ask agent to fix a
3. Now a handles that
4. Repeat

Simple code — you can read all of it. Fork it, change it, make it yours. PRs are merged fast.

## Depth

Full framework: [RANKED_POINTS.md](RANKED_POINTS.md) — 79 points, ranked.

These ideas are provisional. The ability to correct quickly is more
important than having the right answer initially.
