#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
import anthropic
from datetime import datetime

cache = aios_db.read("llm_cache") or {}
command = sys.argv[1] if len(sys.argv) > 1 else "list"
question = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else ""

client = anthropic.Anthropic(api_key=aios_db.read("api_keys").get("anthropic", ""))

actions = {
    "ask": lambda: aios_db.write("llm_cache", {**cache, question: {"response": client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=500,
        messages=[{"role": "user", "content": question}]
    ).content[0].text, "time": datetime.now().isoformat()}}),
    "list": lambda: [print(f"Q: {q[:50]}... A: {a['response'][:50]}...") for q, a in cache.items()],
    "clear": lambda: aios_db.write("llm_cache", {}),
    "stats": lambda: print(f"Cached queries: {len(cache)}")
}

result = actions.get(command, actions["list"])()
print(cache.get(question, {}).get("response", "") if command == "ask" else "")