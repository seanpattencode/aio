# aio

**Claude Code is down. You have deadlines. You need options.**

## Why

1. **Vendor lock-in** - Today it's Claude. Tomorrow it's OpenAI. Next week it's Google. `aio c`, `aio g`, and `aio co` all feel the same. Switch instantly.

2. **Typing paragraphs** - Switching projects and starting agents shouldn't require memorizing flags and paths.

3. **High variance** - AI agents write brilliant code or garbage. You need to checkpoint constantly and nuke bad runs fast.

```bash
# Without aio
claude --dangerously-skip-permissions
cd ~/projects/my-company/apps/frontend-dashboard
git add -A && git commit -m "checkpoint" && git push
git fetch origin && git reset --hard origin/main && git clean -fd

# With aio
aio c
aio 3
aio push "checkpoint"
aio pull
```

## What is aio

A ~1200-line Python script that manages AI coding agents. Runs on macOS, Linux, Windows (WSL), and Android (Termux). Small enough to understand, modify, and make yours.

## Prerequisites

**Mac:** Install Homebrew first:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Windows:** Install [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) first, then follow Linux instructions.

**Termux (Android):**
```bash
pkg update -y && pkg install -y git gh python
gh auth login
gh auth setup-git
git clone https://github.com/seanpattencode/aio ~/aio && cd ~/aio && bash install.sh
source ~/.bashrc
aio update
```

## Install (Mac/Linux/WSL)

```bash
git clone https://github.com/seanpattencode/aio.git && cd aio && ./install.sh
```

Installs: tmux, node, claude, codex, gemini, aio. Prompts for sudo if needed. Works without root (installs to ~/.local).

## Core Commands

```bash
aio c              # Start Claude (co=codex, g=gemini, a=aider)
aio push           # Checkpoint: commit + push
aio pull           # Nuke local: reset to remote
aio revert         # Interactive: pick commit to restore
aio <#>            # cd to project by number
aio prompt         # Set default prompt for all agents
```

## More Commands

```bash
aio help           # Full command list
aio add            # Add current dir as project
aio scan           # Add your repos fast
aio ssh            # Manage remote hosts
aio jobs           # View active sessions
aio n "text"       # Quick note
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

## Philosophy

Sovereign computing. A personal productivity layer small enough to own completely. Unlike Linux or Chromium, you can understand the whole thing and bend it to your will.

## Why Not Aliases?

"I could build this with aliases" means "I could, but I didn't, and it wouldn't sync across machines, and I'd forget the syntax."

**The math with 20 projects:**

```
cd ~/projects/company/apps/frontend-dashboard
= 47 characters × 20 projects = mass you'll never memorize

aio 7
= 5 characters × 20 projects = muscle memory
```

**Mobile/Termux reality:**

Every character on a phone keyboard has ~5% error rate. A 47-character path means you'll mistype 2-3 times per command. With `aio 7`, you're done before autocorrect kicks in.

**The real cost:**

Each command alone saves seconds. But friction changes behavior:

- You checkpoint more because `aio push` is trivial
- You nuke bad runs faster because `aio pull` has no mental overhead
- You try other agents because switching is one letter
- You work from anywhere because state lives in tmux + git

We could dev more, push more, nuke bad runs more. But we don't, because the tools we have make the right thing annoying. aio doesn't save time on any single action. It changes which actions you take.
