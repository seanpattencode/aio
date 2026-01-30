# a
Human AI interaction accelerator.
AI agent manager. 

## Prerequisites

**Mac:** Install Homebrew first:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Windows (WSL):** [Video guide](https://www.youtube.com/watch?v=WD7swbRpwKM)
1. Press Windows key, type `powershell`, right-click → "Run as administrator"
2. Run: `wsl --install -d Ubuntu`
3. Restart PC, Ubuntu opens—create username (lowercase) and password (won't show as you type)
4. In Ubuntu, run Install (Mac/Linux/WSL) below

Troubleshooting: To reopen Ubuntu, press Windows key and search "Ubuntu". To reset: `wsl --unregister Ubuntu` then `wsl --install -d Ubuntu`

Other distros: `wsl --list --online` to see options, `wsl --install -d <distro>`



**Termux (Android):**
```bash
pkg update -y && pkg install -y git gh python
gh auth login
gh auth setup-git
git clone https://github.com/seanpattencode/aio ~/aio && cd ~/aio && bash install.sh
source ~/.bashrc
a update
```

## Install (Mac/Linux/WSL)

```bash
git clone https://github.com/seanpattencode/aio.git && cd aio && ./install.sh
```

Installs: tmux, node, claude, codex, gemini, a. Prompts for sudo if needed. Works without root (installs to ~/.local).

## Simple start
Type in terminal

a g
sign in

ask

"Run a help and explore codebase and explain how to use it for the project I want to do."

"Explain how i can build and run my own a ui"

## Core Commands

```bash
a c              # Start Claude (co=codex, g=gemini, a=aider)
a push           # Checkpoint: commit + push
a pull           # Nuke local: reset to remote
a revert         # Interactive: pick commit to restore
a <#>            # cd to project by number
a prompt         # Set default prompt for all agents
a ui             # Open user interface selection
```

## More Commands

```bash
a help           # Full command list
a add            # Add current dir as project
a scan           # Add your repos fast
a ssh            # Manage remote hosts
a jobs           # View active sessions
a n "text"       # Quick note
```

## The Point

This isn't a tool you just use. It's a tool you **evolve**.

- Simple code - you can read all of it
- AI-native - ask your agent to modify a itself
- Hackable - fork it, change it, make it yours

The workflow:
1. Hit friction
2. Ask agent to fix a
3. Now a handles that
4. Repeat

## Philosophy

Sovereign computing. A personal productivity layer small enough to own completely. Unlike Linux or Chromium, you can understand the whole thing and bend it to your will.

## Why Not Aliases?

"I could build this with aliases" means "I could, but I didn't, and it wouldn't sync across machines, and I'd forget the syntax."

**The math with 20 projects:**

```
cd ~/projects/company/apps/frontend-dashboard
= 47 characters × 20 projects = mass you'll never memorize

a 7
= 3 characters × 20 projects = muscle memory
```

**Mobile/Termux reality:**

Every character on a phone keyboard has ~5% error rate. A 47-character path means you'll mistype 2-3 times per command. With `a 7`, you're done before autocorrect kicks in.

**The real cost:**

Each command alone saves seconds. But friction changes behavior:

- You checkpoint more because `a push` is trivial
- You nuke bad runs faster because `a pull` has no mental overhead
- You try other agents because switching is one letter
- You work from anywhere because state lives in tmux + git

We could dev more, push more, nuke bad runs more. But we don't, because the tools we have make the right thing annoying. `a` doesn't save time on any single action. It changes which actions you take.
