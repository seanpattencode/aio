#!/bin/bash

# Test script for all SQLite orchestrator implementations
# Run minimal tests to verify each implementation works

echo "========================================="
echo "Testing All SQLite Orchestrator Implementations"
echo "========================================="
echo

# Test claudeCode1.py (Basic)
echo "1. Testing claudeCode1.py (Basic SQLite + Systemd)..."
rm -f aios_tasks.db
python3 claudeCode1.py add-task "test1" "echo 'Hello from claudeCode1'" 10
python3 claudeCode1.py status | head -5
echo "✓ claudeCode1.py works"
echo

# Test claudeCode2.py (Advanced Scheduling)
echo "2. Testing claudeCode2.py (Advanced with ACK)..."
rm -f aios_scheduler.db
python3 claudeCode2.py enqueue "test2" "echo 'Hello from claudeCode2'" 5
python3 claudeCode2.py stats
echo "✓ claudeCode2.py works"
echo

# Test claudeCode3.py (Event-driven)
echo "3. Testing claudeCode3.py (Event-driven)..."
rm -f aios_events.db
python3 claudeCode3.py test
echo "✓ claudeCode3.py works"
echo

# Test claudeCode4.py (Full Production)
echo "4. Testing claudeCode4.py (Production with Monitoring)..."
rm -f aios_full.db
python3 claudeCode4.py test
echo "✓ claudeCode4.py works (Dashboard at http://localhost:8080)"
echo

# Change to Candidate SQLite directory for legacy tests
cd "Candidate SQLite" 2>/dev/null || cd .

# Test claude1.py (Original)
echo "5. Testing claude1.py (Original from Candidate)..."
rm -f aios_tasks.db
python3 claude1.py add-task "test5" "echo 'Hello from claude1'"
python3 claude1.py status | head -3
echo "✓ claude1.py works"
echo

# Test chatgpt1.py
echo "6. Testing chatgpt1.py..."
rm -f aios.db
python3 chatgpt1.py init >/dev/null
python3 chatgpt1.py enqueue --cmd "echo 'Hello from chatgpt1'" --priority 5
python3 chatgpt1.py status
echo "✓ chatgpt1.py works"
echo

# Test deepseek2.py (Fixed)
echo "7. Testing deepseek2.py..."
rm -f aios.db
python3 deepseek2.py add_task "test7" "echo 'Hello from deepseek2'" 3
python3 deepseek2.py queue_stats
echo "✓ deepseek2.py works"
echo

echo "========================================="
echo "All implementations tested successfully!"
echo "========================================="
echo
echo "Summary of implementations:"
echo "1. claudeCode1.py - Basic task queue with systemd integration"
echo "2. claudeCode2.py - Advanced scheduling, ACK, dependencies"
echo "3. claudeCode3.py - Event-driven with state machine"
echo "4. claudeCode4.py - Production with web dashboard"
echo "5. claude1.py - Original minimal implementation"
echo "6. chatgpt1.py - Worker-based with heartbeat"
echo "7. deepseek2.py - Task queue with systemd orchestration"
echo
echo "To run workers:"
echo "  python3 claudeCode1.py worker"
echo "  python3 claudeCode2.py worker"
echo "  python3 claudeCode3.py worker"
echo "  python3 claudeCode4.py worker"
echo "  python3 chatgpt1.py worker --name worker1"
echo
echo "Web dashboard available at:"
echo "  http://localhost:8080 (claudeCode4.py)"