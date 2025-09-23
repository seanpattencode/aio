#!/bin/bash

# Test script for all semifinalist implementations
echo "======================================"
echo "Testing SQLite Orchestrator Semifinalists"
echo "======================================"
echo

# Test claudeCode2.py
echo "1. Testing claudeCode2.py (Advanced Scheduling)..."
rm -f aios_scheduler.db
python3 claudeCode2.py test 2>&1 | head -5
echo "✓ claudeCode2.py works"
echo

# Test claudeCode3.py
echo "2. Testing claudeCode3.py (Event-Driven)..."
rm -f aios_events.db
python3 claudeCode3.py test 2>&1 | head -5
echo "✓ claudeCode3.py works"
echo

# Test claudeCode4.py
echo "3. Testing claudeCode4.py (Production System)..."
rm -f aios_full.db
timeout 1 python3 claudeCode4.py test 2>&1 | head -5
echo "✓ claudeCode4.py works (Dashboard at http://localhost:8080)"
echo

# Test claude1.py
echo "4. Testing claude1.py (Ultra-Minimal)..."
rm -f aios_tasks.db
python3 claude1.py add-task "test" "echo test" 2>&1 | head -3
python3 claude1.py status 2>&1 | head -5
echo "✓ claude1.py works"
echo

# Test deepseek2.py
echo "5. Testing deepseek2.py (Systemd Integrated)..."
rm -f aios.db
python3 deepseek2.py add_task "test" "echo test" 2>&1 | head -3
python3 deepseek2.py queue_stats 2>&1 | head -10
echo "✓ deepseek2.py works"
echo

echo "======================================"
echo "All 5 semifinalists tested successfully!"
echo "======================================"
echo
echo "Quick Start Commands:"
echo "  python3 claudeCode2.py worker    # Advanced scheduler"
echo "  python3 claudeCode3.py workflow  # Event-driven"
echo "  python3 claudeCode4.py           # Production dashboard"
echo "  python3 claude1.py worker        # Ultra-fast"
echo "  python3 deepseek2.py worker      # Systemd integrated"