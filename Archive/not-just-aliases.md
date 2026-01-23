# Why aio is not "just an alias list"

The "it's just aliases" take misses the point:

| Feature | Bash Aliases | aio |
|---------|--------------|-----|
| State | None | SQLite (projects, notes, jobs, config, sync across devices) |
| Logic | String substitution | Turing complete (conditionals, loops, error handling) |
| Data processing | Pipe to awk/sed | Python stdlib (json, re, pathlib, sqlite3) |
| Structured output | Text parsing | Direct API access (gh --json, parsed internally) |
| Cross-command state | Environment vars (fragile) | DB queries, config lookups |
| Conditional behavior | Clunky `&&`/`||` chains | Real if/else, try/except |
| Interactive prompts | `read` + manual validation | Input with parsing, defaults, validation |
| Background coordination | Manual `&` + pidfiles | Tmux session tracking, ghost pre-spawn |
| Sync | None | Git-backed DB sync, rclone cloud backup |

## Example: `aio scan`

An alias version:
```bash
alias scan='gh repo list --json name,url | jq ...'  # no state, no "already added" filter, no clone+add
```

What aio scan actually does:
1. Query existing projects from SQLite
2. Fetch repos with metadata from GitHub API
3. Sort by activity
4. Filter out already-cloned
5. Interactive selection with range parsing (`0-5`, `all`)
6. Clone + register + backup in one flow

## The distinction

Aliases compose text. aio composes *operations with state*.
