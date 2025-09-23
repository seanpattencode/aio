# hybridTODO.py Test Report

## Summary
Tested hybridTODO.py with each orchestrator implementation to verify process management and cleanup.

## Test Results

### 1. systemdOrchestrator.py
**Status:** ❌ Failed to start
- **Issue:** hybridTODO.py fails with exit code 2 when started via systemd unit
- **Restart:** Attempted but keeps failing
- **Cleanup:** N/A (never started successfully)
- **Note:** Hardcoded path in line 142 may be incorrect

### 2. chatgpt2.py
**Status:** ✅ Works perfectly
- **Start:** Successfully starts hybridTODO.py (PID verified)
- **Stop:** Cleanly terminates process
- **Restart:** Creates new process with new PID
- **Cleanup:** No orphaned/zombie processes after stop
- **Child processes:** Properly handled by systemd's KillMode=control-group

### 3. claudeCode3.py
**Status:** ⚠️ Cannot test
- **Issue:** Requires sudo to create /var/lib/aios directory
- **Error:** PermissionError: [Errno 13] Permission denied: '/var/lib/aios'
- **Fix needed:** Either run with sudo or modify DB_PATH to use user directory

### 4. claudeResearch2.py
**Status:** ✅ Works perfectly
- **Start:** Successfully starts with auto-approve flag
- **Stop:** Clean termination via systemctl
- **Cleanup:** No orphaned processes
- **Child processes:** Properly managed through systemd transient units
- **Note:** Creates wrapper sh process, but both are cleaned up properly

## Process Cleanup Analysis

### Clean Shutdown (✅)
- **chatgpt2.py:** Excellent - systemd handles all cleanup via control-group
- **claudeResearch2.py:** Excellent - transient units clean up automatically

### Zombie Prevention
All implementations that work use systemd which automatically:
- Reaps zombie processes
- Kills entire process groups on stop
- Handles signal propagation correctly

## Recommendations

1. **Best for hybridTODO:** chatgpt2.py
   - Simple to use
   - Reliable process management
   - Clean shutdown with no orphans

2. **Fix systemdOrchestrator.py:**
   - Check hardcoded path on line 142
   - May need full path to Python interpreter

3. **Fix claudeCode3.py:**
   - Change DB_PATH to ~/.aios/orchestrator.db
   - Or document sudo requirement

## Command Reference

```bash
# chatgpt2 (recommended)
python3 chatgpt2.py add todo python3 /full/path/to/hybridTODO.py --start
python3 chatgpt2.py stop todo

# claudeResearch2
python3 claudeResearch2.py submit todo "python3 /full/path/to/hybridTODO.py" --auto
systemctl --user stop aios-wf-xxxxx.service
```