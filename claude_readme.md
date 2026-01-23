# aio

Git workflow for AI-assisted development. Also manages Claude, Codex, Gemini, and Aider sessions.

## The Problem

AI agents are high variance. They write brilliant code or garbage—rarely in between. You need to checkpoint constantly and nuke bad runs fast.

```bash
# Traditional git for this workflow
git add -A && git commit -m "before agent" && git push
# agent breaks everything
git fetch origin && git reset --hard origin/main && git clean -fd
```

```bash
# aio
aio push "before agent"
# agent breaks everything
aio pull
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/seanpattencode/aio/main/install.sh | bash
source ~/.bashrc
```

## Git Workflow

```bash
aio push           # Checkpoint: commit all + push
aio push "msg"     # Checkpoint with message
aio pull           # Nuke local: reset to remote
aio diff           # What changed?
aio revert         # Interactive: pick commit to restore
```

## Agents

Why type `claude --dangerously-skip-permissions` when you can type `aio c`?

```bash
aio c              # Claude
aio co             # Codex
aio g              # Gemini
aio a              # Aider
aio c 0            # Claude in project 0
```

## Projects

```bash
aio                # List projects
aio 0              # cd to project 0
aio add .          # Add current dir
aio remove 3       # Remove project 3
```

## Why aio?

- **4 keystrokes** - `aio c` vs 40+ character commands
- **Mobile usable** - Short commands work on phone keyboards (Termux)
- **Session persistence** - tmux sessions survive disconnects
- **Multi-device** - SSH into any host, run agents remotely

```bash
aio ssh            # List hosts
aio ssh 0          # Connect
aio run 0 "task"   # Run task remotely
```

## More

```bash
aio help           # Full command list
aio jobs           # Active sessions
aio n "text"       # Quick note
aio update         # Update aio
```
