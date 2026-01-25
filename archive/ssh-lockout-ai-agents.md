# SSH Lockout from AI Agent Auth Failures

**Date:** 2026-01-25
**Issue:** SSH password stopped working on HSU server

## Problem
AI agents running scheduled tasks via `aio hub` can trigger multiple SSH auth failures faster than humans. Linux `faillock` defaults (3 failures, 10min lockout) lock out the account before you realize what happened.

The error gives no indication of lockout - just "Permission denied" - making it hard to diagnose.

## Fix
Make faillock more permissive on servers used by AI agents:

```bash
sudo tee -a /etc/security/faillock.conf << 'EOF'
deny = 100
unlock_time = 10
EOF
```

Or to check/clear current lockouts:
```bash
faillock --user sean           # check status
sudo faillock --user sean --reset  # clear lockout
```

## Prevention
- Use SSH keys instead of passwords for AI agents
- Add retry limits/backoff to automated SSH commands
- Monitor auth failures: `journalctl -u sshd | grep Failed`
