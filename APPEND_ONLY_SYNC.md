## Append-Only Sync System Explained

### Core Concept

Every file gets a timestamp: `{name}_{YYYYMMDDTHHMMSS.nnnnnnnnn}.{ext}`

Git only ever sees **new files being added** - never modifications to existing files. Since additions can't conflict, push always works.

---

### 1. Monte Carlo Simulation (`test_sync.py`)

**Simulates 3 devices locally** using bare git repo as "origin":

```
devices/
├── origin/          (bare git repo - simulates GitHub)
├── device_a/        (local clone)
├── device_b/        (local clone)
└── device_c/        (local clone)
```

**Operations tested:**
- `add` - Create new timestamped file
- `delete` - Remove file
- `archive` - Move to `.archive/` subfolder
- `edit` - Write new content (triggers re-timestamp via `sync_edit`)
- `toggle` - Simulate device going offline/online

**Key functions:**
- `sync()` - Add timestamps to unversioned files, pull, commit, push
- `sync_edit()` - Archives old version before re-timestamping edited files
- `_sync()` - Returns `(success, conflict_detected)` tuple

**Result:** 1000 random ops across 3 devices = 0 conflicts

---

### 2. Real Sync (`sync.py`)

**Flow for `_sync(path)`:**
```
1. Pull first       → Get remote changes (even if nothing local)
2. Add + Commit     → Stage and commit local changes (ok if nothing)
3. Push             → Push if we committed something
```

This order matters: original used `&&` chain that stopped on commit failure, preventing pulls when nothing local to commit.

**Conflict handling:**
- Detects `conflict`, `diverged`, `rejected` in git output
- Prints recovery command: `git push --force` (user decides)
- Returns `(False, True)` so caller knows conflict occurred

**Migration:**
```python
def add_timestamps(path):
    for p in path.glob('*.txt'):
        if '_20' not in p.stem:  # No timestamp yet
            p.rename(f'{p.stem}_{ts()}{p.suffix}')
```

---

### 3. Task Management (`task.py`)

**Storage:** `~/a-sync/tasks/*.txt` - one file per task

**Commands:**
- `a task add <text>` → Creates `{slug}_{timestamp}.txt`
- `a task l` → Lists all tasks (sorted by timestamp in filename)
- `a task d #` → Deletes task file
- `a task sync` → Explicit sync

**Auto-sync:** Every add/delete calls `_sync(d, silent=True)`

**Reading latest version:**
```python
def get_latest(path, name):
    matches = sorted(path.glob(f'{name}_*.txt'))
    return matches[-1] if matches else None
```

---

### 4. Monte Carlo vs Real Cross-Device Sync

| Aspect | Monte Carlo | WSL ↔ hsu |
|--------|-------------|-----------|
| **Origin** | Local bare git repo | GitHub (a-tasks) |
| **Network** | None (all local fs) | SSH + HTTPS |
| **Latency** | Nanoseconds | Seconds |
| **Devices** | 3 simulated | 2 real machines |
| **Clock sync** | Same clock | Different clocks |
| **Failure modes** | Simulated offline | Real network issues |

**Monte Carlo advantages:**
- Fast (1000 ops in seconds)
- Reproducible
- Can test edge cases (all files deleted → reseed)

**Real sync advantages:**
- Tests actual network/auth
- Different system clocks (nanosecond suffix prevents collision)
- Real concurrent access patterns

---

### Why It Works

1. **No same-file edits** → Files are immutable once created
2. **Timestamps unique** → Nanosecond precision + different clocks = no collision
3. **Git sees only additions** → `git merge` trivially succeeds
4. **App reads latest** → `get_latest()` finds newest by timestamp in filename

**Trade-off (CAP theorem):** This is an AP system - Available + Partition-tolerant, eventually consistent. Two devices editing "same" logical file create two versions; app shows most recent by timestamp.

---

## Unified Repository Structure

### Previous: 8 Separate Repos
```
~/a-sync/
├── common/   (.git → a-common)
├── ssh/      (.git → a-ssh)
├── login/    (.git → a-login)
├── hub/      (.git → a-hub)
├── notes/    (.git → a-notes)
├── workspace/(.git → a-workspace)
├── docs/     (.git → a-docs)
└── tasks/    (.git → a-tasks)
```
**Problem:** 8 repos to manage, 8 potential conflict points, complex sync logic.

### Current: Single `a-git` Repo
```
~/a-sync/                  ← single git repo: github.com/seanpattencode/a-git
├── .git/
├── .gitignore             ← ignores backup/, logs/, .archive/
├── common/
├── ssh/
├── login/
├── hub/
├── notes/
├── workspace/
├── docs/
├── tasks/
├── backup/                ← local only (gitignored)
└── logs/                  ← cloud only via rclone (gitignored)
```

**Benefits:**
- One `git pull && push` syncs everything
- One place to debug if issues
- Simpler mental model
- Append-only eliminates the risk that motivated separation

---

## Device Migration Guide

### Prerequisites
- `gh` CLI authenticated (`gh auth status`)
- Access to `seanpattencode/a-git` repo
- Updated `a` repo (`cd ~/projects/a && git pull`)

### Migration Checklist

```
[ ] 1. Backup current data
[ ] 2. Update a repo
[ ] 3. Replace a-sync with a-git clone
[ ] 4. Verify sync works
[ ] 5. Test task/note operations
```

### Step-by-Step Migration

**1. Backup current data**
```bash
cp -r ~/a-sync ~/a-sync-backup-$(date +%Y%m%d)
# or for ~/projects/a-sync:
cp -r ~/projects/a-sync ~/projects/a-sync-backup-$(date +%Y%m%d)
```

**2. Update a repo**
```bash
cd ~/projects/a && git pull origin main
# or wherever your a repo is located
```

**3. Replace a-sync with unified repo**
```bash
# Remove old structure (has individual .git folders)
rm -rf ~/projects/a-sync

# Clone unified repo
gh repo clone seanpattencode/a-git ~/projects/a-sync
```

**4. Verify sync works**
```bash
a sync
```
Expected output:
```
/home/<user>/projects/a-sync
  https://github.com/seanpattencode/a-git.git
  Last: <timestamp> sync
  Status: synced
  common: X files
  ssh: X files
  ...
```

**5. Test operations**
```bash
# Test task
a task add "migration test $(hostname)"
a task l | grep migration

# Test note
a n "migration test note $(hostname)"

# Sync and verify
a sync
```

### Rollback (if needed)
```bash
rm -rf ~/projects/a-sync
cp -r ~/projects/a-sync-backup-* ~/projects/a-sync
```

### Path Variations by Device

| Device | a-sync location |
|--------|-----------------|
| WSL (MSI) | `~/a-sync` |
| hsu | `~/projects/a-sync` |
| Phone (Termux) | `~/a-sync` |

The `SYNC_ROOT` in `_common.py` should resolve correctly based on device detection.

---

## Quick Reference

**Sync all data:**
```bash
a sync
```

**Add task:**
```bash
a task add "description"
```

**Add note:**
```bash
a n "note text"
```

**Check repo status:**
```bash
cd ~/a-sync && git status
```

**Force push (recovery):**
```bash
cd ~/a-sync && git add -A && git commit -m fix && git push --force
```

---

## Real-Time Sync

### How It Works

```
LOCAL WRITE (a task add, a n, etc.)
    ↓
1. Immediate push to GitHub
    ↓
2. Broadcast to all devices (non-blocking)
    ↓
3. Poll daemon pulls every 60s (fallback)
```

### Broadcast (Automatic)

When you push changes, all other devices are notified via SSH:

| Feature | Detail |
|---------|--------|
| Parallel | All hosts pinged simultaneously |
| 2s timeout | Offline devices don't block |
| 3 retries | Pings at 0s, 3s, 6s intervals |
| Non-blocking | Returns immediately |
| Password support | Uses sshpass for hosts with passwords |

**No setup required** - broadcast runs automatically on every sync.

### Poll Daemon (Manual Start)

Background process that pulls every 60 seconds as fallback.

**Start daemon:**
```bash
a sync poll
# Output: Poll daemon started (pid 12345, interval 60s)
```

**Stop daemon:**
```bash
a sync stop
# Output: Poll daemon stopped (pid 12345)
```

**Check status:**
```bash
a sync
# Shows at bottom:
#   Poll: running (60s) - stop with: a sync stop
# or:
#   Poll: not running - start with: a sync poll
```

### Auto-Start Poll Daemon (Optional)

**Option 1: Add to shell profile**
```bash
echo 'a sync poll 2>/dev/null' >> ~/.bashrc
```

**Option 2: Systemd user service**
```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/a-sync-poll.service << 'EOF'
[Unit]
Description=a-sync poll daemon

[Service]
ExecStart=/bin/bash -c 'while true; do sleep 60; cd ~/a-sync && git pull -q origin main; done'
Restart=always

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now a-sync-poll
```

### Sync Flow Summary

| Trigger | Action | Latency |
|---------|--------|---------|
| Local write | Push + broadcast | ~2-3s to online devices |
| Remote write | Poll daemon pulls | ≤60s |
| Manual | `a sync` | Immediate |
| Offline device | Catches up on next sync | Variable |

### Recommended Setup

1. **Active workstation:** Start poll daemon (`a sync poll`)
2. **Server/always-on:** Systemd service or cron
3. **Mobile/laptop:** Rely on broadcast + manual sync
