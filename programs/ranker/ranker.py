#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime

ideas = aios_db.read("ideas") or []
command = sys.argv[1] if len(sys.argv) > 1 else "list"

def score(idea):
    return len(idea.get('description', '')) * idea.get('impact', 1) / max(idea.get('effort', 1), 1)

actions = {
    "add": lambda: aios_db.write("ideas", ideas + [{"description": ' '.join(sys.argv[2:]), "impact": 5, "effort": 5, "added": datetime.now().isoformat()}]),
    "rank": lambda: [print(f"{i+1}. [{score(idea):.1f}] {idea['description']}") for i, idea in enumerate(sorted(ideas, key=score, reverse=True))],
    "list": lambda: [print(f"{i+1}. {idea['description']}") for i, idea in enumerate(ideas)],
    "pick": lambda: print(f"Best: {sorted(ideas, key=lambda x: score(x)/x.get('effort', 5), reverse=True)[0]['description']}" if ideas else "No ideas")
}

actions.get(command, actions["list"])()