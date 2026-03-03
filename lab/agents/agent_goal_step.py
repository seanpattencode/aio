#!/usr/bin/env python3
"""Proposes simplest first step toward goals"""
import sys;sys.path.insert(0,__file__.rsplit('/',1)[0])
from agent_base import *

PROMPT=f"""Read {GOALS} and {AIO}.

Given these goals and where aio.py currently is, what is the SIMPLEST first step that would move toward one of these goals?

Requirements:
- Must be achievable in <1 hour of work
- Must be concrete and specific (not "improve X" but "add Y to Z")
- Explain which goal it serves and why this step specifically

Be concise. 3-5 sentences max."""

if __name__=="__main__":
    result=ask_claude(PROMPT)
    print(f"Goal Step:\n{result}")
    if "--send" in sys.argv:
        send("Next step toward goals (hourly)",f"What's the simplest next step toward your goals?\n\n{result}")
