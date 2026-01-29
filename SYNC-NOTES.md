# Sync System Notes

## Token Sharing

### Problem
Chicken-and-egg: can't pull gdrive tokens without gdrive access.

### Solution: `a ssh push-auth <host>`
Push tokens from authenticated device to remote via SSH:
1. Base64-encodes `~/.config/rclone/rclone.conf` and `~/.config/gh/hosts.yml`
2. Sends via `a ssh <host>` (handles passwords/ports)
3. Creates `.auth_shared` marker on remote

### Token Types
- `(local)` - created via `a gdrive login` on this device
- `(shared)` - pushed via `a ssh push-auth` or pulled via `a gdrive init`
- `(?)` - unknown origin (legacy)

### Token Formats
**GitHub** (`~/.config/gh/hosts.yml`):
```yaml
github.com:
    oauth_token: gho_xxxxxxxxxxxx  # ~40 chars, long-lived
```

**GDrive** (`~/.config/rclone/rclone.conf`):
```ini
[aio-gdrive]
token = {"access_token":"ya29...","refresh_token":"1//05...","expiry":"..."}
# access_token expires ~1hr, refresh_token is long-lived
```

Both are plain text, no device binding. Revoke = all devices using that token lose access.

---

## Log Backup Issues

### Current Behavior
```python
rclone sync LOG_DIR remote:path/logs/{DEVICE_ID}
```

### Issues

| Issue | Impact |
|-------|--------|
| Uses `sync` not `copy` | Local delete = gdrive delete (history lost) |
| Per-device paths | No cross-device log consolidation |
| Requires gdrive | Devices without gdrive = no backup |
| 30min hub job interval | Silent additions delayed up to 30min |

### Potential Fixes
1. **sync → copy**: Preserves deleted logs but never cleans up
2. **Central log aggregation**: Merge all device logs to single location
3. **Fallback to git**: Commit logs to a-sync repo if no gdrive
