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
