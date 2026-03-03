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

### Cross-device
- `.a_done` is in the worktree, syncs via git — review from any device
- Merge and delete work from any device (git operations)
- Resume shows device origin, attempts SSH to remote if needed
- Session IDs are device-local — fallback is new session in worktree with full context

### What this replaces
- Drop `a done` PR creation entirely
- Drop the "When done, run: a done" prompt append
- Worktree sitting in `a job` review IS the notification
- No GitHub PRs for solo dev workflow
