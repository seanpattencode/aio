# Active Tasks - Tonight (12 hrs)

## 1. rclone gdrive sync (30 min)
- Local SSD (4TB, 1.8TB used) as primary, rclone sync to Google Drive (2TB plan, 1.1TB used)
- Use `rclone sync` local->drive (local is source of truth)
- Use `rclone sync --backup-dir` to prevent accidental deletes propagating
- Nightly `rclone sync` primary drive -> backup drive (a-gdrive2)
- Do NOT use `rclone mount` (adds latency). Sync to local folder, LLMs read local.
- Already have a-gdrive and a-gdrive2 configured in rclone
- Goal: all files (meetings, books, docs, ideas) accessible locally for LLMs

## 2. Clean task list (15 min) - parallel with #1
- 68 tasks remain after earlier cleanup (was 196)
- Many still vague or stale
- Need to reflect tonight's 6 priorities at top
- Location: ~/a-sync/tasks/

## 3. Web automation for Deep Think (2 hrs)
- Google AI Ultra plan ($250/mo) gives Deep Think - best first-round code gen
- Currently manual copy-paste between Deep Think and Claude Code
- Need: automated browser sends prompt to Deep Think + other LLMs in parallel
- Collect responses, save as candidates, Claude Code extends best one
- Related task in list: "get multiple ai agents to answer my questions in parallel"
- This justifies the $250/mo plan - must build before intro price ends this month

## 4. Restart trading, trade $1 (2 hrs)
- JUST DO IT. $1 trade regardless of system state.
- S&P went up 2% today, had intuition it would, couldn't act - that's the cost of delay
- Debug existing trading system to minimally functional state
- Don't optimize, don't perfect, just get a trade executing

## 5. Debug `a` on phone + home server (2 hrs)
- C binary rewrite just completed - needs testing on:
  - Phone (Termux/Android)
  - Home server
- May need cross-compilation or compile on device
- Python fallback still available for commands not yet in C
- install.sh updated: compiles a.c with clang/gcc, links sqlite3

## 6. Follow up quantum fusion group (30 min)
- Just had meeting earlier today
- Send follow-up message/email
- Related tasks: "get a training run working", "upload stuff to github for quantumfusion"
- Related tasks: "get CFA ensemble methods notes"

---

## Context for LLMs

### Project: `a` - AI agent session manager
- Vision: sovereign cyborg (human-piloted AI), not autonomous swarms
- Philosophy: minimal tokens, direct library calls, Unix tools as APIs
- Architecture: C binary (1ms dispatch) + Python fallback for complex commands
- Codebase: ~35K tokens Python in a_cmd/, plus new a.c monofile
- Sync: append-only git (~/a-sync/ -> github.com/seanpattencode/a-git)
- Ideas/philosophy: ideas/ folder in project root

### Key files
- a.c - C monofile (new, primary dispatcher)
- a.py - Python entry (fallback)
- a_cmd/_common.py - shared utils (8428 tokens, largest file)
- a_cmd/task/__init__.py - task CRUD
- a_cmd/task/t - bash TUI for task review
- a_cmd/sync.py - append-only git sync
- install.sh - builds C, installs deps, sets up shell function

### Dev workflow (from ideas/coding workcycle.md)
- Attempt use as final user
- Scream at biggest inadequacy
- Minimize solution to triviality
- Favor direct library calls over custom logic
- Write code as short as possible, readable, fast
- Use "a diff" to check token count
- Don't push without approval

### Nootropics: prepped for 3.5 weeks. Reminder Feb 10: prep spice bags + creatine.

### Decision: keep Google AI Ultra ($250/mo) one more month. If Deep Think automation built and used daily by month end, keep. If not, cancel.
