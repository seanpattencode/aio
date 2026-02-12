# Agent Manager Evaluation

## Prompt

> Eval the biggest blocker keeping this from being a real and useful and optimal agent manager. Is it that my tasks need more context? That I need more continuously running jobs that I review iterations of?

## Response

The biggest blocker is **no feedback loop**. Everything else is secondary.

### #1 Blocker: Agent output doesn't feed back into anything

The current flow is:

```
task -> prompt -> spawn claude in tmux -> ??? -> human checks manually
```

The system has no idea what happened. Session files track *that* an agent ran, not *what it produced*. The `task r` flow carefully assembles context and spawns claude, then nothing comes back. There's no:
- Structured result capture (did it succeed? what did it produce?)
- Automatic status update on the task (still shows "1 sess" forever)
- Output feeding into the next run's context

Every iteration requires manually: attach to tmux, read output, decide if it's done, and if not, manually craft the next prompt. That's not agent management -- it's session launching.

### #2 Blocker: No context accumulation across runs

Each agent run starts from scratch. If you ran task #5 three times, run #4 doesn't know what runs #1-3 produced. The `context/` dir is global and static. A real agent manager would auto-include:
- Previous run outputs for this task
- What failed last time and why
- What was already tried

### #3 Blocker: No task state machine

Tasks are either "exists" or "archived". There's no `running -> completed -> needs_revision` flow. Without this, you can't build automation on top (auto-retry failed tasks, skip completed ones, prioritize stuck ones).

### What you DON'T need more of

- More context files (the context system works, it just isn't wired to results)
- More continuously running jobs (spawning is easy, the gap is *after* they run)
- More tasks (120+ exist, the problem isn't capture, it's execution tracking)

### The minimal change that unlocks real agent management

One thing: **when a claude session ends, capture its last output into `task_dir/result_TIMESTAMP.txt` and update task status**. Wrap the tmux launch script to append a capture step after claude exits:

```sh
claude --session-id ... --model ... "$prompt"
# agent done, capture result
tmux capture-pane -p -S -100 > task_dir/result_TS.txt
```

Then `task_show` already displays all `.txt` files chronologically -- the result automatically appears in the next review. The next `r` run picks it up in the body collection (lines 1338-1352). Feedback loop closed with ~2 lines of change.
