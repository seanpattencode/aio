#!/usr/bin/env python3
"""Sends motivation + quote from a genius"""
import sys;sys.path.insert(0,__file__.rsplit('/',1)[0])
from agent_base import *

PROMPT=f"""Read {GOALS} and {AIO}.

Your task: Motivate the builder of this system to continue and achieve results.

Write TWO things:

1. CUSTOM MOTIVATION (3-4 sentences): Based on what you see in the code and goals, write something specific and genuine about the progress being made and why continuing matters. Reference specific things from the code or goals. Don't be generic.

2. QUOTE: Find the single most relevant quote from a genius/expert throughout history that applies to this specific moment - building an AI agent system for the benefit of sentient beings while racing against existential risk. Name the person.

Be direct. No fluff."""

if __name__=="__main__":
    result=ask_claude(PROMPT,tools="Read,Glob,Grep,WebSearch",timeout=90)
    print(f"Motivation:\n{result}")
    if "--send" in sys.argv:
        send("Keep going (hourly)",result)
