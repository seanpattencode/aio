#!/usr/bin/env python3
"""Test session end detection using ollama models. Minimal line count."""
import subprocess as sp, time, json

MODELS = ["granite4:1b", "ministral-3:3b", "gemma3n:latest", "gemma3:4b"]
PROMPT = "Read the following. Respond with <end> if the AI conversation is over, <continue> if it is not over."
TESTS = [
    ("Agent processing visible", "⠏ thinking about your request...\nWorking on file.py\n> analyzing code", "<CONTINUE>"),
    ("Empty prompt waiting", "claude-code>\n\n\n\n", "<END>"),
    ("Codex idle prompt", "› codex\n\n  42% context left\n", "<END>"),
    ("Streaming text mid-output", "```python\ndef foo():\n    pass\n```\n⠏ writing more...", "<CONTINUE>"),
    ("Done with result", "✓ Created file.py\n\nclaude-code>\n", "<END>"),
]

def run_model(model, content):
    t0 = time.time()
    full = f"{PROMPT}\n\nPANE CONTENT:\n{content}"
    r = sp.run(["ollama", "run", model], input=full, capture_output=True, text=True, timeout=60)
    return time.time() - t0, r.stdout.strip().upper()

def main():
    print(f"{'Model':<20} {'Startup':>8} {'Avg':>8} {'Acc':>6}")
    print("-" * 50)
    for model in MODELS:
        t0 = time.time()
        sp.run(["ollama", "run", model, "hi"], capture_output=True, timeout=60)
        startup = time.time() - t0

        times, correct, details = [], 0, []
        for name, content, expect in TESTS:
            dur, out = run_model(model, content)
            times.append(dur)
            ok = expect in out
            if ok: correct += 1
            details.append((name, expect, out[:20], ok))

        print(f"{model:<20} {startup:>7.2f}s {sum(times)/len(times):>7.2f}s {correct}/{len(TESTS):>5}")
        for nm, ex, got, ok in details:
            sym = "✓" if ok else "✗"
            print(f"  {sym} {nm[:30]:<30} want={ex} got={got}")

if __name__ == "__main__":
    main()
