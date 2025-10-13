#!/bin/bash
# Quick demo of AIOS terminal attach feature

echo "=========================================="
echo "AIOS Terminal Demo"
echo "=========================================="
echo
echo "This will demonstrate the terminal attach feature."
echo
echo "Commands to run in AIOS:"
echo "  demo: Create file | echo 'Hello World' > test.txt"
echo "  demo: Interactive shell | bash"
echo "  run demo"
echo "  attach demo"
echo
echo "Your browser will open with an interactive terminal!"
echo
echo "Press Enter to start AIOS, or Ctrl+C to cancel..."
read

./aios.py
