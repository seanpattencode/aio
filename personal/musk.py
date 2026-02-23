#!/usr/bin/env python3
"""a agent run musk          — scan + accumulate
   a agent run musk --send   — digest + email"""
import sys
from rss import accumulate, digest
from base import send, save

if "--send" in sys.argv:
    arts = digest("g-musk")
    if not arts: print("No accumulated Musk articles"); sys.exit(0)
    out = f"{len(arts)} articles:\n\n"
    for t, p, l in arts: out += f"* {t}\n  {p}\n\n"
    print(out); save("g-musk", out); send(f"Musk News ({len(arts)})", out)
else:
    _, n = accumulate("elon musk", name="g-musk")
    print(f"{n} new" if n else "No new articles")
