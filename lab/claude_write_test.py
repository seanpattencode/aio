#!/usr/bin/env python3
import subprocess

# Minimum permissions to write a file
result = subprocess.run(
    ['claude', '-p', '--allowedTools', 'Write'],
    input='Create /tmp/claude_test.txt containing "test from claude"',
    capture_output=True, text=True
)
print(result.stdout or result.stderr)
