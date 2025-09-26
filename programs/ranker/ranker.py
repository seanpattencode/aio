#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from datetime import datetime

ideas = aios_db.read("ideas")
command = (sys.argv + ["list"])[1]

def score(idea):
    return len(idea.get('description', '')) * idea.get('impact', 1) / max(idea.get('effort', 1), 1)

def add():
    return aios_db.write("ideas", ideas + [{"description": ' '.join(sys.argv[2:]), "impact": 5, "effort": 5, "added": datetime.now().isoformat()}])

def print_item(x):
    print(f"{x[0]+1}. {x[1]['description']}")

def print_scored(x):
    print(f"{x[0]+1}. [{score(x[1]):.1f}] {x[1]['description']}")

def rank():
    list(map(print_scored, enumerate(sorted(ideas, key=score, reverse=True))))

def list_ideas():
    list(map(print_item, enumerate(ideas)))

def efficiency(x):
    return score(x)/x.get('effort', 5)

def pick():
    assert ideas, "No ideas"
    print(f"Best: {sorted(ideas, key=efficiency, reverse=True)[0]['description']}")

{"add": add, "rank": rank, "list": list_ideas, "pick": pick}.get(command, list_ideas)()