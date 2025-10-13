# AIOS Testing Folder

This folder contains all test files, documentation, and screenshots from development.

## Contents

### Test Scripts
- `test_*.py` - Various test scripts used during development
- `debug_terminal.py` - Debugging utilities
- `*.sh` - Shell scripts for testing

### Documentation
- `README.md` - Main project documentation
- `ATTACH.md` - Terminal attachment feature docs
- `FIXED.md`, `COMPLETE_FIX.md`, `SUCCESS.md` - Fix documentation
- `TERMINAL_FIX.md` - Terminal fix details
- `TEST_DEMO.md` - Demo instructions
- `QUICKSTART.md` - Quick start guide

### Screenshots
- `screenshot_*.png` - Test execution screenshots
- `proof_*.png` - Final verification screenshots

## Integrated Testing

**All essential tests are now integrated into aios.py**

Run built-in tests:
```bash
./aios.py --test
```

Tests included:
1. PTY terminal creation and I/O
2. WebSocket server connection
3. HTTP server with query strings

## Test Files

These files were used during development and debugging but are no longer needed for regular use. They are kept for reference and additional testing if needed.

### Usage

To run archived tests (from testing folder):
```bash
cd testing
python3 test_final.py
```

## Main Testing

**For regular testing, use the integrated tests:**
```bash
cd ..  # Back to main directory
./aios.py --test
```

This runs all essential tests in a single command, git-style.
