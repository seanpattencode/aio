#!/usr/bin/env python3
import sys
sys.path.append("/home/seanpatten/projects/AIOS/core")
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
import anthropic
from datetime import datetime

cache = aios_db.read("llm_cache")
command = (sys.argv + ["list"])[1]
question = ' '.join(sys.argv[2:])

client = anthropic.Anthropic(api_key=aios_db.read("api_keys").get("anthropic", ""))

def ask():
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=500,
        messages=[{"role": "user", "content": question}]
    ).content[0].text
    cache[question] = {"response": response, "time": datetime.now().isoformat()}
    aios_db.write("llm_cache", cache)
    print(response)
    return cache

def print_item(item):
    q, a = item
    print(f"Q: {q[:50]}... A: {a['response'][:50]}...")

def list_cache():
    list(map(print_item, cache.items()))
    return cache

def clear():
    return aios_db.write("llm_cache", {})

def stats():
    print(f"Cached queries: {len(cache)}")
    return len(cache)

actions = {"ask": ask, "list": list_cache, "clear": clear, "stats": stats}
actions.get(command, list_cache)()