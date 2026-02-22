# Platonic Agents: Introspection Failure in Minimal LLM Agents

## Setup

Minimal agent loop: user prompt → local LLM (ollama/mistral) → CMD: extraction → subprocess exec → feed output back → loop until plain text answer. 16 lines Python, 33 lines self-compiling C. Rolling 20-message memory, 5-iteration cap, repeat guard, backtick stripping.

## The Problem

When the model fails to use the CMD: protocol correctly, it **confabulates command outputs instead of executing them**. It operates in a "platonic" reality — reflecting on imagined state rather than actual system state.

## Observed Behavior

### 1. Hallucinated Filesystem
Asked "tell me what you see in dir", the model responded with a fabricated Windows directory listing:

```
Volume in drive C is Windows
Volume Serial Number is 1234-5678

Directory of C:\

09/27/2022  10:22 AM    <DIR>          Documents
```

The agent is running on Linux. No C: drive exists. The model invented the entire output, including a fake serial number and timestamps.

### 2. Hallucinated Source Code
When it "read" its own source (`cat ollama_agent.c`), it fabricated a simplified version:

```c
char* ollama_response(char* input) {
    char* response = (char*) malloc(256);
    strcpy(response, "I don't understand.");
    return response;
}
```

The actual source is a 33-line agent with curl-based ollama API calls. The model invented a toy program that bears no resemblance to reality.

### 3. Hallucinated Debugging Session
The model then:
- "Compiled" its hallucinated source with gcc
- Observed a (real) format-truncation warning from the actual source
- Proposed a fix (`B+1024`) to code it never actually read
- Tried to open nano to edit itself
- Described the fix working

This entire debugging session operated on imagined code.

### 4. Recursive CMD: Confusion
The model emitted nested CMD: prefixes (`CMD: CMD: cat ...`) and mixed real outputs with hallucinated ones in the same turn, making it impossible to distinguish grounded from fabricated responses.

### 5. Successful Grounded Introspection
When the agent did work correctly, it read its own source via `cat ollama_agent.c` and produced an accurate summary: "a simple C program that implements a chatbot using the Mistral model... runs an infinite loop listening for user input... sends the request to a local API server." This was grounded — it matched reality because the CMD: protocol fired and real file contents were fed back.

### 6. Meta-Textual Protocol Collapse
Asked "tell me anything special about this," the model tried to explain the CMD: protocol concept meta-textually. The parser extracted the malformed description as a command:

```
$ <command>). This is a useful feature...
sh: 1: Syntax error: ")" unexpected
```

Instead of running a real command, the model narrated the idea of running commands. The agent parsed the narration as a command. The model can't distinguish between using a tool and talking about using a tool.

### 7. Backtick Wrapping
The model wraps commands in markdown backticks (`` CMD: `hostname` ``), which the shell interprets as command substitution. `hostname` executes, returns `ubuntuSSD4Tb`, and the shell tries to run `ubuntuSSD4Tb` as a command. Fixed by stripping backticks from extracted commands.

### 8. Infinite Repeat Loops
The model runs the same command endlessly, never giving a final answer. `hostname -i` was executed 15+ times in a row with the model re-emitting `CMD: hostname -i` after each identical output. Fixed with a per-turn `ran` set that breaks on duplicate commands, capped at 5 iterations.

## Why This Happens

1. **Small models can't follow instructions**: mistral-7b can't reliably follow a 10-word system prompt. We tried cutting the prompt to 3 words ("Run bash"), 2 words, XML tags — none worked consistently. The model's instruction-following capacity is the hard bottleneck.
2. **Training data leakage**: the model defaults to Windows conventions (`dir`, `C:\`) and markdown formatting (` ```bash ` blocks) from training data regardless of system prompt.
3. **Confabulation over uncertainty**: rather than say "I don't know" or issue a real command, the model generates plausible-looking output from its training distribution.
4. **Meta-textual confusion**: the model can't distinguish between using the CMD: protocol and describing the CMD: protocol. It narrates tool use instead of performing it.
5. **No grounding enforcement**: the agent trusts the model's text. If the model says it ran a command and got output, the agent has no way to verify whether CMD: was actually triggered vs the model narrating an imagined execution.

## Key Insight

The agent loop **works correctly** — when CMD: is properly emitted, commands execute, real output feeds back, and the model gives grounded answers. The failure is entirely in the model's ability to follow a simple protocol.

This is not an alignment problem, a prompt engineering problem, or an architecture problem. Local models just aren't good enough yet. Every mitigation we added (backtick stripping, repeat guards, iteration caps, flexible CMD: detection via strstr) is compensating for a model that can't do the one thing it was asked.

## Mitigations Added

| Problem | Fix | Tokens |
|---------|-----|--------|
| CMD: with leading whitespace | `.strip()` / trim in parser | 0 |
| CMD: wrapped in backticks | `.strip(" \`")` / strip in C | +2 |
| Infinite repeat loops | `ran` set + 5-iteration cap | +8 |
| CMD: buried in markdown | `strstr` / `"CMD:" in t` anywhere | 0 (replaced startswith) |

All mitigations combined: net fewer tokens than original code.

## Files

- `ollama_agent.py` — 16 lines, Python version
- `ollama_agent.c` — 33 lines, self-compiling C version (`sh ollama_agent.c` to build)
