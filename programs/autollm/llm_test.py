#!/usr/bin/env python3
import sys
print(f"LLM called with: command={sys.argv[1]}, model={sys.argv[2]}, task={' '.join(sys.argv[3:])}")