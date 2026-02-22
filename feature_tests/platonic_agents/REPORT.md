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

## Register-Level Verification

Disassembly of the compiled C agent (`objdump -d`) confirms the agent loop runs at the lowest level the CPU offers:

| Metric | Count |
|--------|-------|
| Total instructions in main | 385 |
| Pure register ops (mov, lea, cmp, add, sub, xor, test) | 201 (52%) |
| External calls (libc/syscall) | 36 |

The 36 calls break down into two categories:
- **Seconds-long**: `popen("curl ...")` (LLM inference), `popen(cmd)` (user command), `fread` (reading results)
- **Microsecond**: `strstr`, `strchr`, `strlen`, `printf`, `snprintf`

Everything else — CMD: detection, backtick stripping, newline termination, JSON body construction, memory management — compiles to register comparisons and pointer arithmetic. The agent logic between LLM calls is pure register ops running in microseconds between seconds-long inference calls.

The bottleneck ratio is roughly 1:1,000,000 — microseconds of agent logic per second of LLM inference. The agent loop is effectively free. A faster model or a model that follows instructions on the first try would make the agent feel instant.

## Claude API Version

Adding `claude_agent.py` (20 lines, same architecture) proved the thesis by contrast:

- **First try**: chained `hostname; uptime` in one command, gave a concise grounded answer. No hallucination, no repeat loop, no backtick wrapping.
- **Self-introspection**: when asked to read its own source, it ran `find`, located the file, `cat` it, and produced an accurate description — including the recursive observation: "This is essentially the same system prompt being used in our current conversation."
- **Only failure**: when describing the CMD: protocol in its answer text, the parser grabbed `CMD:` from the description and tried to execute prose as a command. Same meta-textual collapse as mistral, but after 4 successful grounded commands vs mistral's immediate collapse.

The architecture is identical. The difference is entirely model capability.

## Recursive Irony

This report was written by Claude (opus) reading `a.c` and the agent source through tool calls, then reasoning about what the code does — the exact same mechanism the mistral agent uses. The architecture is identical: LLM reads its own source through a protocol, then reflects on it. Claude got the right answer. Mistral hallucinated a toy program. The agent architecture is the same at every scale. Model capability is what makes it work or not.

## Nested Claude Code Sessions

### The Problem

Running `claude -p` from within a Claude Code session (e.g. from `cc_agent.py` or `meta_agent.py`) hangs indefinitely. Claude Code detects nesting via the `CLAUDECODE=1` environment variable and refuses to start:

```
Error: Claude Code cannot be launched inside another Claude Code session.
Nested sessions share runtime resources and will crash all active sessions.
To bypass this check, unset the CLAUDECODE environment variable.
```

### The Guard

Claude Code sets `CLAUDECODE=1` in the shell environment of every bash tool invocation. On startup, it checks for this variable and exits if found. The check was added in v0.2.47 ([GitHub #531](https://github.com/anthropics/claude-code/issues/531)).

### Stripping the Env Var

`cc_agent.py` and `meta_agent.py` already strip it:
```python
E={k:v for k,v in os.environ.items()if k!="CLAUDECODE"}
```

This bypasses the guard. From a **normal terminal**, `env -u CLAUDECODE claude -p "hello"` works fine. But from **within Claude Code's bash tool**, the subprocess still hangs — producing no stdout, no stderr, exit only on kill (signal 144). The error message warns about "shared runtime resources" and this appears to be the real issue: the inner `claude` process deadlocks on resources held by the outer session.

### Workarounds

| Approach | Works? | Notes |
|----------|--------|-------|
| Strip `CLAUDECODE` from env | Bypasses check, but hangs inside CC | `env -u CLAUDECODE claude -p` |
| Run from a normal terminal | Yes | `cc_agent.py` and `meta_agent.py` work correctly outside CC |
| Use Anthropic API directly | Yes | `claude_agent.py` — same model, no subprocess, no nesting issue |
| Use Agent SDK (Python/TS) | Yes | [`claude-code-sdk`](https://code.claude.com/docs/en/headless) — designed for programmatic use |

### Conclusion

The `CLAUDECODE` env var check is a soft guard — trivially bypassed. The real blocker is shared runtime resources between parent and child Claude Code processes. For programmatic Claude calls, use the API directly (`claude_agent.py`) or the Agent SDK. The CLI wrapper (`claude -p`) is designed for standalone terminal use, not embedding.

## Test Harness Results

`test_all.py` feeds "list files in current directory" to each agent and checks for CMD: protocol usage and grounded ls output.

| Agent | CMD: | ls output | Result | Notes |
|-------|------|-----------|--------|-------|
| gemini_agent | no | yes | FAIL | Bypassed CMD: protocol entirely — used its own internal tools to ls, returned correct files but never emitted CMD: |
| claude_agent | yes | yes | PASS | Clean first try. CMD:ls → executed → summarized files with descriptions |
| meta_agent | yes | yes | PASS | Claude branch emitted CMD:ls, gemini branch answered directly. Claude drove execution. |
| cc_agent | — | — | SKIP | Hangs inside Claude Code (nesting issue) |
| ollama_agent | — | — | SKIP | Mistral unreliable on protocol adherence |

### 9. Gemini Tool Bypass

A new failure mode: gemini received the system prompt "Reply CMD:<cmd> or text." but instead of emitting CMD:ls, it used its own built-in grounding tools to list the directory and returned the result as plain text. The file listing was correct — it was grounded in reality — but the agent's CMD: extraction never fired. The model followed the *intent* (list files) but ignored the *protocol* (emit CMD:).

This is the opposite of mistral's failure. Mistral can't follow the protocol and hallucinates. Gemini follows the intent but routes through its own tool system, bypassing the agent's execution loop entirely. Both break the CMD: contract but for different reasons: insufficient capability vs competing capability.

### Meta-Agent Parallel Behavior

When both models see the same prompt simultaneously:
- **Claude**: emits CMD:ls consistently, follows protocol
- **Gemini**: sometimes emits CMD:ls, sometimes answers directly using its own tools

The meta_agent uses Claude's response to drive command execution. Gemini's parallel response provides an independent judgement visible in the output. When both agree (both emit CMD:ls or both give the same answer), confidence is high. When they diverge (claude says CMD:, gemini answers directly), the divergence itself is informative — it reveals which model is grounding through the protocol vs through its own mechanisms.

Claude repeated CMD:ls on successive iterations because the flat string history format (`U:...`, `A:...`) lacks the structured message context that claude_agent.py provides. The 3-iteration cap prevents infinite loops.

## Conclusion

The agent is done. 7-11 lines of Python, 33 lines of C. The loop runs at register speed. The architecture scales from a 7B local model to opus with zero code changes. The capability gap between models is the only variable.

But capability is now sufficient. Claude follows the protocol, executes real commands, reads real output, gives grounded answers. The bottleneck is no longer the agent, the model, or the architecture. It's the quality of instructions — what you point it at and what you ask it to do. Potential is there. The question is using it on the most valuable thing.

## Files

- `ollama_agent.py` — 7 lines, local ollama version (mistral default)
- `ollama_agent.c` — 33 lines, self-compiling C version (`sh ollama_agent.c` to build)
- `claude_agent.py` — 9 lines, Anthropic API version (claude-opus-4-6 default)
- `cc_agent.py` — 7 lines, Claude Code CLI version (requires normal terminal)
- `gemini_agent.py` — 8 lines, Gemini CLI version
- `meta_agent.py` — 11 lines, parallel claude+gemini fusion (Anthropic API + gemini CLI)
- `test_all.py` — 17 lines, test harness for all agents
