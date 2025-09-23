# Systemd Orchestrator Implementations

## systemdOrchestrator.py (Recommended - Simplest/Fastest)

**Run:**
```bash
python3 systemdOrchestrator.py status           # Show all jobs
python3 systemdOrchestrator.py start            # Start all jobs
python3 systemdOrchestrator.py stop             # Stop all jobs
python3 systemdOrchestrator.py restart          # Restart all (7ms!)
python3 systemdOrchestrator.py cleanup          # Remove all units
```

**Add custom job:** Edit main() function to add jobs before running.

---

## chatgpt2.py (Feature-rich with SQLite)

**Run:**
```bash
# Add and start a job
python3 chatgpt2.py add myjob echo "hello" --start

# Manage jobs
python3 chatgpt2.py list                        # List all jobs
python3 chatgpt2.py start myjob                 # Start existing job
python3 chatgpt2.py stop myjob                  # Stop job
python3 chatgpt2.py status myjob                # Check status

# Advanced features
python3 chatgpt2.py add scheduled ls --on-calendar="*:0/5" --start  # Run every 5 min
python3 chatgpt2.py add priority top --nice=-10 --start            # High priority
python3 chatgpt2.py set-rt myjob --prio 50                        # Set realtime
```

**Note:** The `add` command only registers jobs. Use `--start` flag or run `start` separately to execute. Output goes to systemd journal:
```bash
journalctl --user -u aios-myjob.service -n 10
```

---

## claudeCode3.py (Production-grade)

**Setup:**
```bash
sudo mkdir -p /var/lib/aios
sudo chown $USER /var/lib/aios
```

**Run:**
```bash
# Terminal 1: Start orchestrator
python3 claudeCode3.py run

# Terminal 2: Submit workflows
python3 claudeCode3.py submit "test" "echo hello"
python3 claudeCode3.py status
```

---

## claudeResearch2.py (Async with auto-approve)

**Run:**
```bash
# Quick test (auto-approved)
python3 claudeResearch2.py submit mytask "echo test" --auto

# Manual approval workflow
python3 claudeResearch2.py submit mytask "echo test"
python3 claudeResearch2.py approve wf-xxxxx
python3 claudeResearch2.py status

# Realtime priority
python3 claudeResearch2.py submit critical "important_task" --rt --auto

# Start scheduler (separate terminal)
python3 claudeResearch2.py
```

---

## Quick Comparison

| Feature | systemd | chatgpt2 | claudeCode3 | claudeResearch2 |
|---------|---------|----------|-------------|-----------------|
| **Lines** | 175 | 168 | 285 | 297 |
| **Speed** | 7ms | 45ms | 50ms | 102ms |
| **Database** | No | SQLite | SQLite | SQLite |
| **Scheduling** | No | Yes | No | No |
| **Priorities** | No | Yes | Yes | Yes |
| **Resource Limits** | No | Yes | Yes | Yes |
| **Auto-retry** | Via systemd | No | Yes | No |
| **Async** | No | No | No | Yes |
| **Best For** | Simple/Fast | Features | Production | Workflows |