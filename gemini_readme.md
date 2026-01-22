# 🤖 AIO: The Anti-Lock-in AI Agent Manager

> **🚧 DISCLAIMER: WIP / WORKS ON MY MACHINE**
> This is a personal tool I built to manage my own AI agent sessions. It works for me. It might break for you. I'm shipping it now because tools go down and I needed options. PRs are extremely welcome.

**Claude Code is down. You have deadlines. You need options *now*.**

AIO is a CLI wrapper that decouples your workflow from the specific AI provider. It manages persistent `tmux` sessions for **Claude, Gemini, Codex, and Aider**, allowing you to switch backends instantly without losing your terminal setup or learning a new CLI.

**Don't let a single vendor outage kill your productivity.**

## 🚀 The "Claude is Down" Playbook

Install AIO and pivot to whatever is working right now:

```bash
# 1. Install (Linux/macOS)
curl -fsSL https://raw.githubusercontent.com/seanpattencode/aio/main/install.sh | bash

# 2. Choose your weapon
aio g   # Start/Attach Gemini (Google)
aio c   # Start/Attach Claude (Anthropic)
aio co  # Start/Attach Codex (OpenAI)
aio a   # Start/Attach Aider (Open Source)
```

## 为什么 (Why)?
Because I hate:
1.  **Vendor Lock-in:** Today it's Claude. Tomorrow it's OpenAI. Next week it's Google. `aio` abstracts the CLI so `aio c`, `aio g`, and `aio co` all feel the same.
2.  **Losing Context:** Closing a terminal shouldn't kill my AI agent's memory. `aio` runs everything in `tmux` so sessions persist. Detach, go home, reattach.
3.  **SSH Headaches:** Running agents on remote servers is annoying. `aio ssh` handles the connection and session attachment automatically.

## 📦 Supported Agents
- **Gemini CLI** (`aio g`) - *Recommended alternative for speed*
- **Claude Code** (`aio c`) - *The default (when it works)*
- **OpenAI Codex** (`aio co`)
- **Aider** (`aio a`)

## ⚡ Command Reference

| Command | Action |
| :--- | :--- |
| `aio g` / `aio gemini` | **Start/Attach Gemini** |
| `aio c` / `aio claude` | Start/Attach Claude |
| `aio a` / `aio aider` | Start/Attach Aider |
| `aio co` / `aio codex` | Start/Attach Codex |
| `aio list` | Show all active sessions |
| `aio kill <id>` | Kill a stuck session |
| `aio ssh` | Manage remote dev servers |

## 🛠 Critical Config for Gemini Users
If you are switching to Gemini, use these settings to make it feel more like the Claude experience (fast, less nagging):

```yaml
# ~/.gemini/config.yaml
tools:
  shell:
    # PREVENTS HANGS: Stop it from waiting for user input on shell commands
    enableInteractiveShell: false
  # SPEED UP: Don't ask for permission every single time
  autoAccept: true
```

## 🤝 Contributing
This is a raw, fast wrapper.
- Found a bug? Open an issue.
- Fixed a bug? Send a PR.
- Want to roast my python? Go ahead, but fix it while you're there.
