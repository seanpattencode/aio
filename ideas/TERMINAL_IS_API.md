# Terminal is API

The core architectural principle: treat CLI tools as APIs, not libraries.

## The Pattern

```python
# What most projects do:
from anthropic import Anthropic
client = Anthropic()
response = client.messages.create(...)

# What this project does:
sp.run(['claude', '--dangerously-skip-permissions'])
```

## How It's Applied

### AI Agents - CLI over SDK
```python
'claude --dangerously-skip-permissions'
'codex -c model_reasoning_effort="high" --model gpt-5-codex'
'gemini --yolo'
'aider --model ollama_chat/mistral'
```
Agents launch as tmux sessions running CLI tools. No API calls.

### Git - Direct CLI
```python
def _git(path, *a): return sp.run(['git', '-C', path] + list(a), ...)
sp.run(['gh', 'api', 'user'], ...)  # Even GitHub API via gh CLI
```

### Tmux - State Manager
```python
sp.run(['tmux', 'new-session', '-d', '-s', name, ...])
sp.run(['tmux', 'send-keys', '-l', '-t', session, text])
sp.run(['tmux', 'capture-pane', '-t', session, '-p'])
```
Tmux IS the session database. No custom state management.

### Cloud Sync - rclone CLI
```python
sp.run([rc, 'sync', DATA_DIR, f'{rem}:{path}', ...])
```

### Data Storage - Text Files
Projects stored as `Name: value\nRepo: url` text files, synced via git.

## Why Others Don't Do This

### 1. "Proper Engineering" Culture
SDKs look professional. subprocess looks hacked together.

### 2. Control Anxiety
SDKs give typed responses, error handling, retries. CLI gives stdout and exit codes.

### 3. Dependency Inversion Dogma
"Don't depend on concrete implementations" - but CLIs ARE the stable interface. `git` CLI hasn't broken in 20 years. GitHub SDK breaks monthly.

### 4. Testing Theater
SDKs are mockable. `sp.run(['tmux', ...])` requires integration tests. This scares people.

### 5. Resume-Driven Development
"Built microservices with Redis pub/sub" > "orchestrated CLI tools with subprocess"

## Why It Works Better

| SDK Approach | Terminal-as-API |
|-------------|-----------------|
| Breaks when provider updates | CLI is stable contract |
| Must update deps | Tools update independently |
| Debug by reading library source | Debug by running command manually |
| Mocking complexity | Just run it |
| Language-locked | Works from any language, any device |

## The Rare Combination

Most devs are either old Unix guards OR modern developers. This project requires both:

**Old Unix Guard knows:**
- Pipes are APIs
- Text is universal interchange
- Small tools composed > monoliths
- Shell is the IDE
- Everything is a file

**Modern Dev knows:**
- AI agents are useful
- Mobile is a real dev environment
- Git is distributed state sync
- Cloud CLIs (gh, rclone) are mature
- tmux survives disconnects

**The insight:** Unix philosophy wasn't wrong, it was waiting for tools to catch up. Now `claude` and `gemini` are just more commands to pipe.

## The Result

Zero dependencies on provider SDKs. Any tool with a CLI becomes usable. Same interface on phone as desktop. Debuggable by running commands manually. Resilient - tmux survives disconnects.

The terminal literally IS the API.

## Most Code is This in Disguise

Most code is just worse versions of:

```bash
tool1 | tool2 | tool3
```

**What "real" code often does:**
```python
# 500 lines of Python
import requests
response = requests.get(url)
data = json.loads(response.text)
filtered = [x for x in data if x['status'] == 'active']
with open('out.json', 'w') as f:
    json.dump(filtered, f)
```

**What it actually is:**
```bash
curl url | jq '.[] | select(.status == "active")' > out.json
```

**Examples hidden everywhere:**

| "Application" | Actually just |
|---------------|---------------|
| CI/CD pipeline | Shell scripts with yaml |
| Docker | tar + chroot + cgroups |
| Kubernetes | SSH to machines + run containers |
| Most web backends | Transform HTTP → database query → HTTP |
| Electron apps | Chrome + Node subprocess |
| "AI platforms" | Wrap API call, add UI |

**This project makes it explicit:**
- Don't hide that you're calling `claude`
- Don't wrap `git` in abstraction
- Don't build "session management" when tmux exists
- Don't build "sync infrastructure" when git + rclone exist

The honesty is: we're just orchestrating tools. The lie is: pretending we're doing something more sophisticated.

Most codebases are shell scripts ashamed of themselves.

## Why This Knowledge is Rare

Modern CS education:
```
Python → Java → "Data Structures" → Web Framework → Get Job
```

What's skipped: How does the computer actually work? What is a process? A pipe? Why does Unix work the way it does?

The books that transmitted this knowledge:
- "Just for Fun" - Torvalds
- "The Unix Programming Environment" - Kernighan & Pike
- "The Art of Unix Programming" - ESR

Nobody assigns these anymore. They assign "Clean Code" and framework tutorials.

The irony: The "obsolete" shell knowledge became essential again when AI agents turned out to be CLI tools you orchestrate from terminal. But a generation of devs doesn't have it.

## Torvalds' Influence in This Project

You can trace it everywhere:

| This Project | Torvalds Influence |
|--------------|-------------------|
| Git for sync | He literally created git |
| Text files over database | Unix "everything is a file" |
| `a push` / `a pull` | Git's distributed model as state sync |
| No central server | Peer-to-peer via git remotes |
| Shell functions in .bashrc | Shell as extension point |
| tmux as session manager | Terminal-centric computing |
| CLI tools composed | Small tools, one job each |
| install.sh per-platform | Portable by adaptation, not abstraction |

**Git as sync infrastructure:**

Most people would build: REST API + database + auth + websockets + conflict resolution

This project: `git push` / `git pull`

Torvalds solved distributed state sync for Linux kernel development. We just use it for config files. The tool is absurdly overpowered for the job - which means it will never break.

**The philosophy absorbed from "Just for Fun":**
- Small tools doing one thing
- Text as interface
- Composition over complexity
- "Good enough" > "perfect abstraction"
- Solve your own problem first

You can't get this from Stack Overflow. It's transmitted through books by people who built the foundations.

## None of This Was Planned

This architecture wasn't designed. It emerged.

No one sat down and said "let's use git as a sync protocol" or "terminal should be our API layer." The decisions just happened because the mental models were internalized:

- Need to sync? `git push`
- Need to run claude? `subprocess`
- Need session state? tmux already exists
- Need to store config? Text file

When Unix philosophy is in your head, you don't "decide" to use pipes. You just reach for them like you reach for a glass of water.

This is why the knowledge transmission matters. You can't teach someone "use git for sync" as a rule. They'll apply it wrong. But if they've absorbed *why* Unix works the way it does, they'll independently arrive at the same solutions.

The architecture is an emergent property of the philosophy.

## Python is Super Bash

The original split:

**Programming languages** (C, Fortran)
- Build the tools
- Performance critical
- Compiled, optimized

**Scripting languages** (sh, Perl, Python)
- Glue tools together
- Dev speed critical
- Interpreted, flexible

Python IS super bash:
- Variables that aren't insane
- Real data structures
- Error handling that works
- But still `subprocess.run()` at its core

**What went wrong:**

People started building *applications* in Python. Web backends, ML pipelines, entire products. Python became "a programming language" and forgot it was supposed to be glue.

Then you get Python apps that are slow, rewrites to Go/Rust "for performance", ecosystem of heavy libraries, people treating Python like Java.

**This project uses Python correctly:**

```python
# This is scripting
sp.run(['git', 'push'])
sp.run(['tmux', 'new-session', ...])
sp.run(['claude', '--dangerously-skip-permissions'])
```

The "real work" is done by C programs (git, tmux) or external services (claude). Python just orchestrates.

**In this project**, Python is used as orchestrator. Not a statement about what Python should be - Python is a great general-purpose language. But here, the architecture happens to use it as super bash, and that's the right fit for CLI tool composition.
