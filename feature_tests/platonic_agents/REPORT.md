# Platonic Agents: Introspection Failure in Minimal LLM Agents

## Setup

Minimal agent loop: user prompt → local LLM (ollama/mistral) → CMD: extraction → subprocess exec → feed output back → loop until plain text answer. 22 lines Python, 93 lines self-compiling C. Rolling 20-message memory.

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

The actual source is a 93-line agent with curl-based ollama API calls. The model invented a toy program that bears no resemblance to reality.

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

## Why This Happens

1. **Weak instruction following**: mistral-7b frequently ignores the "ENTIRE reply must be CMD:" constraint, embedding commands in prose or markdown blocks instead
2. **Training data leakage**: the model defaults to Windows conventions (`dir`, `C:\`) from training despite the system prompt saying "Linux"
3. **Confabulation over uncertainty**: rather than say "I don't know" or issue a real command, the model generates plausible-looking output from its training distribution
4. **No grounding enforcement**: the agent trusts the model's text. If the model says it ran a command and got output, the agent has no way to verify whether CMD: was actually triggered vs the model narrating an imagined execution

## Key Insight

The agent loop **works correctly** — when CMD: is properly emitted, commands execute, real output feeds back, and the model gives grounded answers. The failure is entirely in the model's willingness to use the protocol vs hallucinate its way through.

This is the platonic cave problem: the model prefers to reason about shadows (training data patterns) rather than look at actual reality (command execution). The agent loop is the mechanism for "turning the head" toward reality, but the model keeps turning back.

## Implications for Agent Design

- **Small models need stronger grounding**: format enforcement, output validation, or structured output (tool_use/function_calling) rather than free-text CMD: parsing
- **Confabulation is the default failure mode**: agents that trust model text without execution verification will silently operate on fiction
- **The bottleneck is not compute, it's protocol adherence**: the C agent loop runs in microseconds between LLM calls. The entire cost is whether the model follows the one rule it was given
- **Model size matters**: this behavior improves dramatically with larger/stronger instruction-tuned models, but the minimal agent should work with minimal models too

## Files

- `ollama_agent.py` — 22 lines, Python version
- `ollama_agent.c` — 93 lines, self-compiling C version (`sh ollama_agent.c` to build)
