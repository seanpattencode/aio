# Claude Code Sandbox Noise

When running commands via Claude Code's Bash tool, you may see:

```
EACCES: permission denied, mkdir '/tmp/claude-XXXXX/.../tasks'
```

This is **not** from your command. It's Claude Code's internal task-tracking
trying to create directories in `/tmp/` which the Android/Termux sandbox blocks.

**Your command still runs and produces correct output.** The error is cosmetic.

Workaround: redirect output to a file, then read it:
```bash
a ssh > /tmp/out.txt 2>&1; cat /tmp/out.txt
```
