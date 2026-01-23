# Claude CLI Parameters Guide

## Basic Usage

```bash
# Interactive
claude

# Print mode (non-interactive, for scripts)
claude -p "prompt"
echo "prompt" | claude -p

# Continue last conversation
claude -c
```

## Permission Flags

### --allowedTools (Recommended)
Restrict Claude to specific tools only:

```bash
# Web search only
echo "NYC weather" | claude -p --allowedTools "WebSearch"

# Read files only (no write/edit)
echo "Analyze code" | claude -p --allowedTools "Read,Glob,Grep"

# Write new files only
echo "Create file" | claude -p --allowedTools "Write"

# Edit existing files (needs Read too)
echo "Fix typo" | claude -p --allowedTools "Read,Edit"

# Git operations only
echo "Show status" | claude -p --allowedTools "Bash(git:*)"
```

### --disallowedTools
Block specific tools:

```bash
# Everything except Bash
claude -p --disallowedTools "Bash" "analyze this"
```

### --dangerously-skip-permissions
Bypass all permission prompts. Use only in sandboxed environments:

```bash
claude -p --dangerously-skip-permissions "do something"
```

## Tool Reference

| Tool | Purpose | Example |
|------|---------|---------|
| `Read` | Read files | Analyze code |
| `Write` | Create new files | Generate config |
| `Edit` | Modify existing files | Fix bugs |
| `Glob` | Find files by pattern | Search codebase |
| `Grep` | Search file contents | Find usages |
| `Bash` | Run shell commands | Build, test |
| `Bash(git:*)` | Git commands only | Status, commit |
| `WebSearch` | Search the web | Current info |
| `WebFetch` | Fetch URL content | Read docs |

## Minimum Tools by Task

| Task | Minimum Tools |
|------|---------------|
| Weather/web info | `WebSearch` |
| Read & analyze code | `Read,Glob,Grep` |
| Create new file | `Write` |
| Edit existing file | `Read,Edit` |
| Git operations | `Bash(git:*)` |
| Full autonomy | `--dangerously-skip-permissions` |

## Directory Restrictions

**Claude has NO built-in directory sandboxing.** It can access any path the user can access.

```bash
# Even from /tmp, Claude can read anywhere:
cd /tmp && echo "Read /home/user/secrets.txt" | claude -p --allowedTools "Read"
# This WORKS - no restriction
```

### Workarounds

1. **Prompt-based** - Only mention paths in allowed directory
2. **OS sandboxing** - Docker, firejail, bubblewrap:
   ```bash
   docker run -v /safe/dir:/workspace claude ...
   firejail --whitelist=/safe/dir claude ...
   ```
3. **Tool restriction** - Remove Read/Write/Bash entirely for web-only tasks

## Examples

### Safe web query
```python
subprocess.run(['claude', '-p', '--allowedTools', 'WebSearch'],
               input='What is the weather?', capture_output=True, text=True)
```

### Safe code analysis (read-only)
```python
subprocess.run(['claude', '-p', '--allowedTools', 'Read,Glob,Grep'],
               input='Analyze aio.py', capture_output=True, text=True)
```

### File creation (write-only, no read)
```python
subprocess.run(['claude', '-p', '--allowedTools', 'Write'],
               input='Create /tmp/test.txt with hello', capture_output=True, text=True)
```
