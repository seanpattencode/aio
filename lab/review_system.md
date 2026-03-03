# Job Review System

## Problem
Jobs fire off, finish, worktrees pile up, never get reviewed. PRs are a multi-person ritual — solo dev doesn't need them. But auto-merge is wrong because:
- LLMs say "done" when code doesn't actually work
- Implementation may not be minimal enough
- May want to change direction entirely
- Review is about "is this the right thing, done the simplest way" — no test catches that

## Design

### Agent side: `.a_done`
When agent finishes work in a worktree, it writes `.a_done` with:
- What changed (summary, not full diff)
- Shell commands to verify it works (e.g. `a n "test"`, `sh a.c build`)
- Device ID that ran the job

Replace current `a done` PR instruction with: "When finished, write `.a_done` with a summary of changes and commands to verify."

### Review UI: `a job` review mode
One-key flow through finished worktrees:

```
── project-mar03-104505am ──  [device: ubuntuSSD4Tb]
  Changed: lib/note.c (+3 lines) — added rapid mode to notes
  Verify: a n "test note"

  [m]erge  [r]esume  [d]elete  [j]next
```

Shows:
- Worktree name + originating device
- `.a_done` contents (summary + verify commands)
- Compact diff stat
- One-key actions

### Actions
- **m (merge)**: merge worktree branch to main, delete worktree
  1. Try `git merge` — clean merge completes instantly
  2. If conflict → claude resolves automatically in the worktree
  3. Human only involved if claude can't resolve (essentially never with small codebase)
  - Risk is low: wrong merge = build fails or functionally broken = noticed immediately
  - `a revert` is one command if anything slips through
  - Enables parallel multi-machine workflow where jobs A B C merge as they finish out of order
- **d (delete)**: delete worktree, discard work
- **r (resume)**: resume conversation with the agent to request changes
  - Local session: `claude -r <session-id>` directly
  - Remote session: `a ssh <device> claude -r <session-id>`
  - SSH fail fallback: "x can't reach <device>, start new session? [y/n]"
  - New session fallback: opens claude in the worktree (has full code context)
- **j (next)**: skip, review later
- **Saved review prompts**: one-key sends a canned prompt, resumes agent, returns to review when done
  - Built-in defaults: `n` = "make it negative tokens", `s` = "shorten, same or fewer tokens"
  - Custom prompts: user saves their own (e.g. "extract to existing util", "use pcmd instead")
  - Stored in `adata/git/review_prompts/` — syncs across devices
  - Library grows organically from patterns you actually repeat

### Token gate
- Net new features: diff must be under 200 tokens
- Replacements/refactors: diff must be net negative tokens
- Deletions: no limit
- On merge, check `a diff` token count — over limit blocks merge
- Agent gets one auto-pass to simplify, then human reviews
- Not an autonomous halving loop — single "too big, shrink it" pass to avoid runaway deletion

### Cross-device
- `.a_done` is in the worktree, syncs via git — review from any device
- Merge and delete work from any device (git operations)
- Resume shows device origin, attempts SSH to remote if needed
- Session IDs are device-local — fallback is new session in worktree with full context

### Code quality criteria
1. **Minimize length** — measurable, automatable (token gate)
2. **Minimize execution time** — measurable, automatable (perf benchmarks)
3. **Maximize value produced** — human judgment, not automatable

The review system automates gates for 1 and 2. The review UI exists solely for 3 — glance at what it does, decide if you even want it.

### Why this is safe
- Daily user and dev — bugs surface immediately through usage, not test suites
- Tight feedback loop: bad merge → hit the bug same day → `a revert` → move on
- Cost of a bad merge is minutes, not days
- Tests are a substitute for human attention in orgs where nobody touches code for weeks
- Solo daily user already has the human attention — tests would just be overhead
- Minimal diffs = minimal blast radius — a 3-line change has a 3-line traceback
- `a diff` token counting is itself a safety mechanism: fewer tokens = fewer things that can break
- Worst case: logic breaks, but error points straight at the small change

### What this replaces
- Drop `a done` PR creation entirely
- Drop the "When done, run: a done" prompt append
- Worktree sitting in `a job` review IS the notification
- No GitHub PRs for solo dev workflow
