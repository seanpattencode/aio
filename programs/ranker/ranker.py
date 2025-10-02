#!/usr/bin/env python3
import sys
from datetime import datetime
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
aios_db.write("ideas", [])
ideas, command = aios_db.read("ideas"), (sys.argv + ["list"])[1]
score = lambda i: len(i.get('description', '')) * i.get('impact', 1) / max(i.get('effort', 1), 1)
commands = {
    "add": lambda: aios_db.write("ideas", ideas + [{"description": ' '.join(sys.argv[2:]), "impact": 5, "effort": 5, "added": datetime.now().isoformat()}]),
    "rank": lambda: list(map(lambda x: print(f"{x[0]+1}. [{score(x[1]):.1f}] {x[1]['description']}"), enumerate(sorted(ideas, key=score, reverse=True)))),
    "list": lambda: list(map(lambda x: print(f"{x[0]+1}. {x[1]['description']}"), enumerate(ideas))),
    "pick": lambda: print(f"Best: {sorted(ideas, key=lambda x: score(x)/x.get('effort', 5), reverse=True)[0]['description']}") if ideas else None
}
commands.get(command, commands["list"])()