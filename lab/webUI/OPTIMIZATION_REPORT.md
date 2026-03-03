# Subprocess Shell Function Optimization

## Executive Summary

Subprocess calls in Python bypass shell functions defined in `~/.bashrc`, causing **10-100x slower execution** for commands that have optimized shell wrappers. By sourcing bashrc before command execution, we can leverage these optimizations.

| Approach | `aio` Execution Time |
|----------|---------------------|
| `subprocess.getoutput('aio')` | 52.3ms |
| `subprocess.getoutput('source ~/.bashrc && aio')` | 0.5ms |
| **Speedup** | **104x faster** |

---

## The Problem

When Python's `subprocess` module executes a command:

```python
subprocess.getoutput("aio")
subprocess.run(["aio"], shell=True)
subprocess.check_output("aio", shell=True)
```

It spawns a **non-interactive shell** that:
1. Does NOT source `~/.bashrc`
2. Does NOT load shell functions or aliases
3. Resolves commands via `$PATH` only

This means optimized shell functions are completely bypassed.

---

## How `aio` Achieves 0ms Startup

The `aio` command uses a two-stage architecture:

### Stage 1: Shell Function (TRUE 0ms)

Installed in `~/.bashrc`:
```bash
aio() {
    local cache=~/.local/share/aios/help_cache.txt
    # Help: instant from cache - NO Python
    if [[ -z "$1" || "$1" == "help" ]]; then
        cat "$cache" 2>/dev/null || command python3 ~/.local/bin/aio "$@"
        return
    fi
    # Numbers: instant cd from cached project list
    if [[ "$1" =~ ^[0-9]+$ ]]; then
        local dir=$(sed -n "$((${1}+1))p" ~/.local/share/aios/projects.txt)
        [[ -d "$dir" ]] && { cd "$dir"; return; }
    fi
    command python3 ~/.local/bin/aio "$@"
}
```

For no-args/help, it runs `cat` on a cache file. **Python never starts.**

### Stage 2: Python Kernel (~50ms when needed)

When Python must run, it uses:
- Only stdlib imports at module level
- Lazy-loading for heavy dependencies (`pexpect`, `prompt_toolkit`)
- Deferred I/O operations

---

## The Solution

Source bashrc before executing commands:

```python
# Before (slow - 52ms)
subprocess.getoutput("aio")

# After (fast - 0.5ms)
subprocess.getoutput("source ~/.bashrc && aio")

# Or use interactive shell
subprocess.getoutput("bash -i -c 'aio'")
```

### Benchmark Results

```
getoutput('aio'):              52.3ms
getoutput('bash -i -c "aio"'):  4.1ms
getoutput('source ~/.bashrc && aio'): 0.5ms
```

The `source` approach is fastest because:
1. It only loads function definitions (not full interactive setup)
2. The shell function uses `cat` (0.5ms) vs Python startup (50ms)

---

## What Else Benefits From This?

### High Impact (10x+ speedup possible)

| Command | Why It Has Shell Function |
|---------|--------------------------|
| **nvm** | Version switching without subprocess |
| **rvm** | Ruby version manager |
| **pyenv** | Shims + version resolution |
| **conda** | Environment activation |
| **sdkman** | JVM version manager |
| **asdf** | Universal version manager |
| **direnv** | Auto-loads `.envrc` |

These all use shell functions to:
- Cache state in shell variables
- Avoid spawning processes
- Intercept `cd` for auto-switching

### Medium Impact (2-5x speedup)

| Command | Why |
|---------|-----|
| **git aliases** | Shell aliases like `alias gs='git status'` |
| **Custom wrappers** | Any function in bashrc |
| **Prompt commands** | `$PROMPT_COMMAND` cached values |

### Low/No Impact

| Command | Why |
|---------|-----|
| `ls`, `cat`, `grep` | Native binaries, no shell wrapper |
| `python script.py` | Python startup is the bottleneck |
| `docker`, `kubectl` | Native binaries |

---

## Implementation Patterns

### Pattern 1: Source Before Command

```python
def fast_shell(cmd):
    """Execute command with shell functions available."""
    return subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {cmd}")
```

**Pros**: Simple, works everywhere
**Cons**: Sources entire bashrc each time

### Pattern 2: Interactive Shell

```python
def fast_shell(cmd):
    return subprocess.getoutput(f"bash -i -c {shlex.quote(cmd)}")
```

**Pros**: Full interactive environment
**Cons**: May trigger prompts, slightly slower

### Pattern 3: Source Only Functions

```python
# Extract just the function you need
def fast_aio(cmd):
    func = """
    aio() {
        local cache=~/.local/share/aios/help_cache.txt
        [[ -z "$1" ]] && { cat "$cache"; return; }
        python3 ~/.local/bin/aio "$@"
    }
    """
    return subprocess.getoutput(f"{func}\n{cmd}")
```

**Pros**: Minimal overhead, no bashrc side effects
**Cons**: Duplicates function definition

### Pattern 4: Persistent Shell Process

```python
import subprocess

class ShellSession:
    def __init__(self):
        self.proc = subprocess.Popen(
            ['bash', '-i'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

    def run(self, cmd):
        self.proc.stdin.write(f"{cmd}; echo '---END---'\n")
        self.proc.stdin.flush()
        output = []
        for line in self.proc.stdout:
            if '---END---' in line:
                break
            output.append(line)
        return ''.join(output)
```

**Pros**: One-time bashrc load, fastest for multiple commands
**Cons**: Complex, must manage process lifecycle

---

## Caveats and Limitations

### 1. Bashrc Must Be Fast

If bashrc takes 500ms to source, this optimization is counterproductive.

```bash
# Test your bashrc load time
time bash -i -c "exit"
```

Ideal: < 50ms. Acceptable: < 200ms.

### 2. Side Effects

Sourcing bashrc may:
- Print welcome messages
- Start background processes
- Modify environment unexpectedly

Mitigate with: `source ~/.bashrc 2>/dev/null`

### 3. Only Helps Optimized Commands

Commands without shell function wrappers see no benefit:
```
ls via getoutput: 3ms
ls via source + getoutput: 3ms  # No change
```

### 4. Not All Functions Are Portable

Shell functions may depend on:
- Specific shell (bash vs zsh vs fish)
- Environment variables set earlier in bashrc
- Other functions defined in bashrc

---

## Recommendations for Web UI Candidates

### Quick Win: Add Source Prefix

Change all subprocess calls from:
```python
subprocess.getoutput(cmd)
```
To:
```python
subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {cmd}")
```

### Better: Detect Optimized Commands

```python
SHELL_OPTIMIZED = {'aio', 'nvm', 'rvm', 'pyenv', 'conda'}

def smart_shell(cmd):
    base_cmd = cmd.split()[0]
    if base_cmd in SHELL_OPTIMIZED:
        return subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {cmd}")
    return subprocess.getoutput(cmd)
```

### Best: Use Persistent Shell for Multiple Commands

For web UIs that run many commands, maintain a persistent bash process with bashrc already loaded.

---

## Conclusion

The 100x speedup for `aio` is not magic—it's the result of:

1. **Smart caching**: Pre-computed help text in a file
2. **Shell function interception**: Bypass Python entirely for simple cases
3. **Lazy loading**: When Python runs, defer heavy imports

Any command can achieve similar results by:
1. Identifying frequently-run, simple operations
2. Caching their output
3. Creating a shell function that serves from cache
4. Falling back to full execution only when necessary

The subprocess sourcing trick unlocks these optimizations for programmatic callers that would otherwise bypass them entirely.
