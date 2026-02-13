# Migration Guide — adata 4-tier system
**Date: 2026-02-06**

## Overview

Data directory restructured from flat `a-sync/` to `adata/` with 4 tiers:

```
~/projects/adata/
  git/      git push/pull        all devices     text <15M (notes, tasks, docs)
  sync/     rclone copy <->      all devices     large files <5G
  vault/    rclone copy on-demand big devices     models, datasets
  backup/   rclone move ->        all devices     logs+state, upload+purge
```

## New device setup

### 1. Install the tool
```bash
gh repo clone seanpattencode/a ~/projects/a
cd ~/projects/a && bash a.c install
```

### 2. Pull auth from gdrive (if another device already set up)
```bash
# First, configure one gdrive account manually:
rclone config create a-gdrive drive

# Then pull shared auth (gh tokens, rclone config with all accounts):
a gdrive init
```

### 3. Clone the data repo
```bash
mkdir -p ~/projects/adata/{sync,vault,backup}
gh repo clone seanpattencode/a-git ~/projects/adata/git
```

### 4. Verify
```bash
a sync        # should show adata/git/ path + file counts
a gdrive      # should show all accounts with storage info
a note        # should list notes
```

## Migrating from a-sync (existing devices)

```bash
# Create new structure
mkdir -p ~/projects/adata/{sync,vault,backup}

# Move git repo
mv ~/projects/a-sync ~/projects/adata/git

# Move logs to backup
mv ~/projects/adata/git/logs ~/projects/adata/backup/$(cat ~/.local/share/a/.device)/

# Move old backup out of git
mv ~/projects/adata/git/backup ~/projects/adata/backup/local-archive

# Compat symlink (safe to remove after all sessions restart)
ln -s ~/projects/adata/git ~/projects/a-sync

# Update tool and rebuild
cd ~/projects/a && git pull && bash a.c install
```

## GDrive accounts

Unlimited accounts, two types:

```bash
a gdrive login          # shared rclone OAuth key (quick, slower transfers)
a gdrive login custom   # your own client_id (walks you through Google Cloud setup)
```

`a gdrive` shows all accounts with storage usage and key type:
```
✓ a-gdrive:  account1@gmail.com (1.0 TiB / 30.0 TiB) [shared key]
✓ a-gdrive2: account2@gmail.com (864.7 GiB / 2.0 TiB) [custom key]
```

### Multi-account strategy

| Account | Gets | Purpose |
|---------|------|---------|
| 30 TiB  | sync/ + vault/ + backup/ | Primary, everything |
| 2 TiB   | sync/ + backup/ | Redundant copy of critical data |

## What syncs where

| Tier | Command | Direction | What |
|------|---------|-----------|------|
| git/ | `a sync` | git push/pull to GitHub | notes, tasks, docs, workspace, ssh, login |
| git/ | `a gdrive sync` | tar.zst → gdrive | redundant backup of git/ |
| sync/ | (manual rclone) | rclone copy ↔ gdrive | large shared files, all devices |
| vault/ | (manual rclone) | rclone copy ← gdrive | models/datasets, big devices only |
| backup/ | `a gdrive sync` | rclone copy → gdrive | ~/.local/share/a/ state + auth |
| backup/ | `a log sync` | tar.zst → gdrive | session logs |
| backup/ | `a log grab` | copy ~/.claude/ history | then `a log sync` to upload |

## Architecture (C binary)

The `a` binary resolves paths at startup in `init_paths()`:
- `AROOT` = `~/projects/adata/` (derived from binary location)
- `SROOT` = `AROOT/git/` (where notes, tasks, etc. live)
- `LOGDIR` = `AROOT/backup/{device}/` (session logs)
- `SDIR` = `~/projects/a/` (the tool itself)

Python uses matching constants in `lib/a_cmd/_common.py`:
- `ADATA_ROOT`, `SYNC_ROOT`, `LOG_DIR`, `RCLONE_BACKUP_PATH`
