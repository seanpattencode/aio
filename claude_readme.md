# aio

A 1200-line Python script that manages AI agents. Small enough to understand, modify, and make yours.

## Why

AI agents are high variance. They write brilliant code or garbage. You need to checkpoint constantly and nuke bad runs fast.

```bash
# Without aio
git add -A && git commit -m "checkpoint" && git push
git fetch origin && git reset --hard origin/main && git clean -fd

# With aio
aio push "checkpoint"
aio pull
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/seanpattencode/aio/main/install.sh | bash
```

## Core Commands

```bash
aio c              # Start Claude (co=codex, g=gemini, a=aider)
aio push           # Checkpoint: commit + push
aio pull           # Nuke local: reset to remote
aio revert         # Interactive: pick commit to restore
aio <#>            # cd to project by number
aio prompt         # Set default prompt for all agents
```

## The Point

This isn't a tool you just use. It's a tool you **evolve**.

- Single file, ~1200 lines - you can read all of it
- AI-native - ask your agent to modify aio itself
- Hackable - fork it, change it, make it yours

The workflow:
1. Hit friction
2. Ask agent to fix aio
3. Now aio handles that
4. Repeat

## More Commands

```bash
aio help           # Full command list
aio add .          # Add current dir as project
aio ssh            # Manage remote hosts
aio jobs           # View active sessions
aio n "text"       # Quick note
```

## Philosophy

Sovereign computing. A personal productivity layer small enough to own completely. Unlike Linux or Chromium, you can understand the whole thing and bend it to your will.
