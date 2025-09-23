#\!/bin/bash
# Performance test script

echo "=== Testing systemdOrchestrator.py ==="
time python3 systemdOrchestrator.py restart

echo -e "\n=== Testing chatgpt2.py ==="
# Add and run a quick job
python3 chatgpt2.py add perf_test echo "test" --start
sleep 1
time python3 chatgpt2.py stop perf_test

echo -e "\n=== Testing claudeResearch2.py ===" 
time python3 claudeResearch2.py submit perf "echo test" --auto

echo -e "\nMemory usage:"
ps aux | grep -E "(systemd|chatgpt2|claudeResearch2)" | head -5

