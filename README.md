# AIO - Task Manager

Ultra-fast, event-driven task execution system with git-inspired design, strict performance enforcement, and automatic updates.


## Install

**Termux (Android):** `pkg install git python && git clone https://github.com/seanpattencode/aio && cd aio && python aio.py install`

**Ubuntu/Mac/Windows:** Clone repo, run `python3 aio.py install` (installs all deps automatically)

##Candidate internal rules
the most complex command should be
aio push "message"
there should never be more parameters than 3 as above and one should be custom
no main parameter should be more than 4 characters ex aio dash not aio dashboard
3 stages:
main command 0-1ms target
preinstalled deps only (20ms target)
longer loading items.
This ensures that the most important commands work on most systems in least time while also allowing more complex behavior
bug fixes and simply improvements should be shorter in total line count, readable, as fast or faster than previous code


## Warning:
the aio command may not work properly if your directory has a . in the front of it.
aio push may say failure on mac but work.

## Features

- **Event-Driven Execution**: Zero polling, subprocess.run() blocks on completion (270x faster)
- **0.5ms Performance Enforcement**: SIGKILL on any AIOS overhead regression >0.5ms
- **Global Installation**: Call `aios` from anywhere, like git
- **Auto-Update**: Keeps itself updated automatically (like Chrome/VS Code)
- **Interactive TUI**: Running tasks view with live status updates
- **Web Terminal Access**: Attach to running jobs via xterm.js
- **Git Worktree Support**: Isolate tasks in separate worktrees
- **Template Variables**: Parameterized workflows with `{{variables}}`
- **Todo Management**: Deadline tracking with virtual/real deadlines
- **Single File**: All logic in 959 lines of Python (includes install)

## Installation

### Quick Install

```bash
cd /path/to/AIOS
python3 aios.py --install

This will:
1. Check dependencies (Python 3.9+, pip, tmux)
2. Generate pyproject.toml
3. Install AIOS with pip
4. Make `aios` command available globally

### Verify Installation

```bash
aios --test
```

## Auto-Update

Enable automatic updates (checks once per week):

```bash
aios --auto-update-on
```

Now AIOS will keep itself updated automatically in the background. No SSH key required - automatically switches to HTTPS if needed.

**How it works:**
- Runs in background thread (zero startup impact)
- Checks for updates once per week
- Automatically switches from SSH to HTTPS if needed
- Caches credentials for 1 week
- Silent failure (never blocks or hangs)

**Manual update:**
```bash
aios --update
```

**Disable auto-update:**
```bash
aios --auto-update-off
```

## Quick Start

```bash
# Run interactive TUI (default)
aios

# Load and run a task
aios tasks/example.json

# Batch mode (non-interactive)
aios --simple tasks/example.json

# Profile performance
aios --profile

# Run tests
aios --test
```

## TUI Commands

```
m                - Show workflow menu
a <#|name>       - Attach terminal to job (e.g., "a 1" or "a jobname")
r <job>          - Run job from builder
c <job>          - Clear job from builder
t +<title> <dl>  - Add todo (dl: 2h, 1d, 2025-01-15)
t ✓<id>          - Complete todo
t ✗<id>          - Delete todo
q                - Quit
```

## Task Format

### Simple Task (No Variables)

```json
{
  "name": "simple-test",
  "steps": [
    {"desc": "Echo test", "cmd": "echo 'Hello World'"},
    {"desc": "List files", "cmd": "ls -la"}
  ]
}
```

### Worktree Task

```json
{
  "name": "git-task",
  "repo": "/path/to/repo",
  "branch": "main",
  "steps": [
    {"desc": "Show status", "cmd": "git status"},
    {"desc": "Run tests", "cmd": "pytest"}
  ]
}
```

### Template Task (With Variables)

```json
{
  "name": "template-task",
  "repo": "{{repo_path}}",
  "branch": "{{branch_name}}",
  "variables": {
    "repo_path": "/default/path",
    "branch_name": "main"
  },
  "steps": [
    {"desc": "Task description", "cmd": "echo {{message}}"}
  ]
}
```

## Architecture

### Performance Enforcement

**Timed (Strict 0.5ms SIGKILL):**
- `extract_variables` - Template variable extraction
- `substitute_variables` - Variable substitution
- `parse_and_route_command` - Command parsing
- `get_status_text` - UI rendering
- `get_todos` - Database queries
- `load_todos` - Todo loading
- `get_urgency_style` - Deadline styling

**Untimed (Variable I/O):**
- `execute_task` - subprocess.run() execution
- `cleanup_old_jobs` - Filesystem operations
- All user-interactive functions

### Event-Driven Design

**Execution Flow:**
```
1. Build bash script with all commands
2. Execute via subprocess.run() - blocks until complete
3. Check return code
4. Display output to tmux session
```

**No Polling:**
- Old: Check every 2s if command finished (slow, wastes CPU)
- New: subprocess.run() blocks on completion (instant, zero overhead)

**File Watching:**
- Uses watchdog library (inotify-based)
- Zero polling for task file changes
- Auto-executes simple tasks (no variables)

### Auto-Update System

**How It Works:**
```
1. Background thread starts on aios launch
2. Checks if 1 week passed since last check
3. If yes: git fetch in background (non-blocking)
4. If SSH fails: auto-switch to HTTPS
5. If updates available: git pull + pip install
6. Update timestamp, continue normally
```

**Non-Interactive Git:**
- Sets GIT_TERMINAL_PROMPT=0
- Sets GIT_ASKPASS=echo
- Sets SSH_ASKPASS=echo
- Sets GIT_SSH_COMMAND='ssh -oBatchMode=yes'
- stdin=subprocess.DEVNULL
- Never prompts or hangs

**HTTPS Fallback:**
- Detects SSH remotes (git@host:user/repo)
- Converts to HTTPS (https://host/user/repo)
- Configures credential cache (1 week)
- Permanent switch (survives restarts)

### Menu System

**Template Tasks:**
- Detected by `extract_variables()`
- Require user input via menu (`m` command)
- Prompt for each `{{variable}}`
- Show preview before execution

**Simple Tasks:**
- No variables detected
- Auto-execute from watch_folder
- Immediate queue on file drop

### Web Terminal

**Access:**
```bash
# In TUI, type:
a 1   # Opens browser to job #1 terminal
a 2   # Opens browser to job #2 terminal
```

**Implementation:**
- HTTP server on port 7681 (terminal.html)
- WebSocket server on port 7682 (PTY bridge)
- xterm.js frontend with binary WebSocket
- Persistent PTY sessions via os.fork()

### Todo System

**Features:**
- SQLite database (aios.db)
- Real deadlines (when truly due)
- Virtual deadlines (self-imposed)
- Event-driven notifications (no polling)
- Urgency styling (overdue, <1h, <1d)

**Usage:**
```bash
# Add todo with real deadline
t +Fix bug 2h

# Add todo with real and virtual deadline
t +Deploy feature 1d 4h

# Complete todo
t ✓1

# Delete todo
t ✗2
```

## Directory Structure

```
AIOS/
├── aios.py              # Single file - all code (959 lines, includes install)
├── README.md            # This file
├── CHANGELOG.md         # Version history
├── data/                # All state files
│   ├── config.json      # Auto-update configuration
│   ├── aios.db          # Todo database
│   └── timings.json     # Performance baseline
├── tasks/               # Task definitions (.json)
├── jobs/                # Execution directories (max 20)
│   └── task-timestamp/
│       └── worktree/    # Git worktree (if repo specified)
└── terminal.html        # Generated web terminal (temp)
```

## Performance

**Baseline (AIOS Overhead Only):**
```
extract_variables:       0.00ms
substitute_variables:    0.00ms
parse_and_route_command: 0.00ms
get_status_text:         0.00ms
get_todos:               0.00ms
load_todos:              0.00ms
```

**Enforcement:**
- Tolerance: 0.5ms (500μs)
- Any regression triggers SIGKILL immediately
- Forces ultra-disciplined development

**Speedup vs Polling:**
- execute_task: 254x faster (12.6s → 0.05s)
- Event-driven: zero CPU waste

**Auto-Update Overhead:**
- Disabled: 0ms
- Enabled (recent check): <1ms
- Enabled (due for check): ~5ms startup + background

## Design Principles

**Inspired by git:**
- Plumbing vs porcelain separation
- Event-driven (not polling)
- Fast operation required
- Single file simplicity
- Self-update mechanism

**Inspired by top/htop:**
- Live status display
- Minimal key commands
- Clear visual hierarchy

**Inspired by Claude Code:**
- Immediate feedback
- Command-driven workflow
- Professional efficiency
- Zero-friction updates

**Inspired by Chrome:**
- Silent background updates
- Automatic credential handling
- No user intervention needed

## Line Count Evolution

```
Original (v0.9):  986 lines
Optimized (v1.0): 760 lines (-23% optimization)
+ Auto-Update:    801 lines (+41 lines for auto-update)
+ HTTPS Fallback: 870 lines (+69 lines for automatic HTTPS)
+ Worker Fix:     880 lines (+10 lines for error handling)
+ Integrated:     959 lines (+79 lines for data/ and --install)
Net Result:       -27 lines (-3% from original, fully self-contained)
```

## Development

**Run Tests:**
```bash
aios --test
```

**Test Output:**
```
================================================================================
AIOS Built-in Tests
================================================================================

0. Testing AIOS overhead functions...
   ✓ All overhead functions working
   ✓ Timings: extract=0.00ms, substitute=0.00ms, parse=0.00ms, render=0.00ms

1. Testing PTY terminal creation...
   ✓ PTY creation and I/O working

2. Testing WebSocket server...
   ✓ Servers started (HTTP:7681, WS:7682)
   ✓ WebSocket connection and communication working

3. Testing HTTP server...
   ✓ HTTP server serving with query strings

================================================================================
✓ ALL TESTS PASSED
================================================================================
```

**Profile Performance:**
```bash
# Create baseline
aios --profile

# Run with enforcement (SIGKILL if >baseline + 0.5ms)
aios
```

**Key Code Sections:**
- Line 54-65: Data directory setup
- Line 67-76: Config management (auto-update)
- Line 86-99: Performance enforcement system
- Line 101-166: Todo database and notifications
- Line 168-180: Variable extraction/substitution
- Line 202-235: Event-driven execute_task
- Line 384-414: TUI status rendering
- Line 422-486: Command parsing and routing
- Line 488-498: Worker thread with error handling
- Line 500-527: Event-based file watcher (watchdog)
- Line 607-730: Self-update with HTTPS fallback
- Line 839-911: Install function (embedded pyproject.toml)
- Line 913-959: Main entry point

## Troubleshooting

**Command not found: aios**
```bash
export PATH="$HOME/.local/bin:$PATH"
# Add to ~/.bashrc or ~/.zshrc for persistence
```

**Auto-update asking for SSH key**
- This shouldn't happen with v2 (HTTPS fallback)
- If it does: `aios --update` to manually trigger HTTPS switch
- Or disable: `aios --auto-update-off`

**Auto-update not working**
```bash
# Check config
cat data/config.json

# Check last update time (Unix timestamp)
# If last_update_check is recent, wait 1 week or set to 0

# Force check by setting to 0
echo '{"auto_update": true, "last_update_check": 0, "check_interval": 604800}' > data/config.json

# Try manual update
aios --update
```

**Jobs stuck at "Initializing"**
- Fixed: Use absolute path for subprocess cwd
- Fixed: Command-line tasks call prompt_for_variables

**Menu freezes TUI**
- Fixed: Exit TUI, show menu, re-enter TUI
- Flow: TUI → 'm' → Exit → Menu → Re-enter

**"Exit 1" errors**
- Fixed: Show stderr context on failure
- Error message shows last line of stderr

**SIGKILL on performance regression**
- Check `data/timings.json` baseline
- Re-profile with `--profile` if needed
- Only pure AIOS overhead is timed (not I/O)

**Tests failing**
```bash
# Check tmux is installed
which tmux

# Reinstall
pip uninstall aios-cli
pip install -e . --user
```

## Comparison with Other Tools

| Feature | AIOS | Homebrew | VS Code | Chrome |
|---------|------|----------|---------|--------|
| Background updates | ✅ | ❌ (blocks) | ✅ | ✅ |
| No restart needed | ✅ | ✅ | ❌ | ❌ |
| Configurable | ✅ | ✅ | ✅ | ❌ |
| Auto HTTPS fallback | ✅ | ❌ | ❌ | N/A |
| Event-driven | ✅ | ❌ | ✅ | ✅ |
| Credential caching | ✅ | ❌ | ✅ | N/A |
| Non-blocking | ✅ | ❌ | ✅ | ✅ |
| Performance enforcement | ✅ | ❌ | ❌ | ❌ |

## Configuration

**Auto-Update Settings (data/config.json):**
```json
{
  "auto_update": true,           // Enable/disable auto-updates
  "last_update_check": 1234567,  // Unix timestamp of last check
  "check_interval": 604800       // Seconds between checks (1 week)
}
```

**Change check interval:**
```bash
# Check daily
echo '{"auto_update": true, "last_update_check": 0, "check_interval": 86400}' > data/config.json

# Check weekly (default)
echo '{"auto_update": true, "last_update_check": 0, "check_interval": 604800}' > data/config.json
```

## Security

**Auto-Update:**
- All git operations non-interactive (no prompts)
- HTTPS credentials cached in memory only
- Cache expires after 1 week (configurable)
- SSH keys never required
- Silent failure on network errors

**Credential Storage:**
- Method: git credential helper cache
- Location: Memory only (not disk)
- Expiration: 604800 seconds (1 week)
- Scope: Per-repository only
- Access: Requires local system access

## Philosophy

AIOS follows the **git philosophy**:
- Minimal, focused commands
- Event-driven (zero polling)
- Self-contained and updateable
- Fast and predictable (<1ms overhead)
- Extensive testing built-in
- Single file design

Inspired by the best practices of:
- **git**: Self-update, event-driven, performance
- **Claude Code**: Zero-friction UX, immediate feedback
- **top**: Live monitoring, minimal commands
- **Chrome**: Silent auto-updates, no user intervention

## Examples

### Example 1: Simple Task

Create `tasks/hello.json`:
```json
{
  "name": "hello",
  "steps": [
    {"desc": "Say hello", "cmd": "echo 'Hello AIOS!'"},
    {"desc": "Show date", "cmd": "date"}
  ]
}
```

Run:
```bash
aios
```

Task auto-executes because it has no variables.

### Example 2: Git Worktree Task

Create `tasks/test-branch.json`:
```json
{
  "name": "test-branch",
  "repo": "/path/to/repo",
  "branch": "feature-x",
  "steps": [
    {"desc": "Run tests", "cmd": "npm test"},
    {"desc": "Build", "cmd": "npm run build"}
  ]
}
```

Creates isolated worktree in `jobs/test-branch-timestamp/worktree/`.

### Example 3: Template Task

Create `tasks/deploy.json`:
```json
{
  "name": "deploy",
  "variables": {
    "env": "staging",
    "version": "1.0.0"
  },
  "steps": [
    {"desc": "Deploy {{env}}", "cmd": "deploy.sh {{env}} {{version}}"}
  ]
}
```

Prompts for variables before execution.

### Example 4: Todo Management

```bash
# Add todo
t +Fix authentication bug 2h

# Add todo with virtual deadline
t +Deploy to production 1d 4h

# Complete todo
t ✓1

# Delete todo
t ✗2
```

## Contributing

1. Run tests before committing: `aios --test`
2. Profile performance: `aios --profile`
3. Ensure all tests pass
4. Keep overhead functions under baseline + 0.5ms
5. Follow event-driven patterns (no polling)
6. Maintain single-file design

## License

MIT

## Credits

Inspired by:
- git (self-update, event-driven design)
- Claude Code (zero-friction UX)
- top/htop (live monitoring)
- Chrome (silent updates)
- VS Code (background updates)

Built following the principles of minimalism, performance, and user experience.
