# Sync System Rewrite Summary

## Philosophy
Because we by default save things to git and version control it, we can be more fearless in what we attempt knowing we can revert it. This helps democratize information rollback for the user's own programs and files and is essential for agentic interaction with file systems. A db might be very powerful when it runs and fail infrequently but a merkle tree revives you every time. And that is the security you need to be able to rely on things you build personally in the long term.

## Overview
Massive simplification of the sync system - removed complex event-sourcing in favor of simple git-based file sync.

## Changes Made

### Deleted (-3892 tokens)
- `sync.py` - old folder-based sync (47 lines)
- `_common.py` - removed `emit_event`, `replay_events`, `db_sync`, `auto_backup`, `EVENTS_PATH` (74 lines)
- `backup.py`, `note.py`, `rebuild.py` - replaced with placeholders
- All sync calls from: `hub.py`, `ssh.py`, `scan.py`, `add.py`, `remove.py`, `log.py`
- Timing logging from `a.py`

### New Sync System
- **Location**: `~/projects/a-sync/` (sibling of `a`, dynamic per device)
- **Format**: RFC 5322 `.txt` files (human readable, machine searchable, doesn't break)
- **Structure**: Multiple isolated repos to prevent conflicts

```
~/projects/a-sync/
  common/  → github.com/user/a-common  (general files)
  ssh/     → github.com/user/a-ssh     (SSH hosts)
  logs/    → github.com/user/a-logs    (agent logs)
  login/   → github.com/user/a-login   (gh token sharing)
```

### Key Design Decisions
1. **Isolation** - sync conflict in notes doesn't bottleneck agent work logging
2. **Visibility** - a-sync added as project index 1, easy to browse/edit
3. **Dynamic paths** - works across devices regardless of install location
4. **RFC 5322 format** - doesn't hide information, doesn't break, machine searchable with metadata
5. **Foreground sync** - errors shown immediately, no silent failures
6. **Opt-in login sharing** - user must explicitly enable gh token sync

### SSH Storage (RFC 5322)
```
Name: hostname
Host: user@ip:port
Password: plaintext
```
- Plain text passwords (not base64 encoded)
- Invalid hosts show in numbered list: `1. x name: missing Name:/Host:`
- Auto-syncs on first run if `.git` doesn't exist

### Login Sharing (RFC 5322)
```
Token: gho_...
Source: hostname
Created: 2026-01-30T01:01:53
```
- Opt-in: asks "Enable gh token sharing across devices? [y/n]"
- Creates sync chain of trusted devices
- `a ssh push-auth` pushes token directly via SSH (bootstrap)

### Logs
- Now sync to `a-logs` repo
- Shows local path, GitHub URL, file paths
- Auto-syncs on first run

### Error Handling
Sync failures show helpful message:
```
x sync failed [a-ssh] - copy this to ai agent (hint: a copy):
  Sync conflict in /path/to/a-sync/ssh. Verify: https://github.com/user/a-ssh.git
  Run `cd /path && git status`, explain the issue, propose a fix plan for my approval.
```

### Commands
- `a sync` - syncs all repos, shows status
- `a ssh` - loads from `a-sync/ssh/*.txt`, validates hosts
- `a log` / `a logs` - view logs, synced to a-logs
- `a login` - manage gh token sharing
- `a push` - supports multi-repo folders (asks to push all)
- `a 1` - opens a-sync folder directly

## Files Modified
- `a_cmd/sync.py` - multi-repo sync, error handling, philosophy comment
- `a_cmd/ssh.py` - RFC 5322 storage, validation, plain text passwords
- `a_cmd/log.py` - syncs to a-logs, shows paths and URL
- `a_cmd/login.py` - new: gh token sharing across devices
- `a_cmd/push.py` - multi-repo push support
- `a_cmd/_common.py` - SYNC_ROOT, LOG_DIR moved here
- `a.py` - added sync, login, logs commands

## Status
- [x] Delete old sync logic
- [x] Create GitHub repo sync
- [x] Multi-repo isolation
- [x] SSH RFC 5322 storage
- [x] Dynamic paths
- [x] Add a-sync as project
- [x] Error handling with helpful messages
- [x] Login sharing system
- [x] Logs syncing
- [x] Host validation
- [ ] Notes migration
- [ ] Hub jobs migration
