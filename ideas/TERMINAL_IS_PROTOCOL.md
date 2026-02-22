Agent-agent communication via terminal, not structured protocols.

Most agent-agent communication research focuses on formal protocols — shared
memory, message queues, A2A, MCP, custom APIs. Structured schemas agents parse
and respond to.

This system uses terminals. One agent types into another agent's terminal and
reads what comes back. The "protocol" is natural language in, natural language
out, mediated by tmux panes over SSH. No schema, no serialization, no handshake.

It works because agents are already designed to take text input and produce text
output in a terminal. The communication channel matches the interface they
already have. Adding a structured protocol on top would be adding complexity for
the same result — one agent asking another to do something and reading what
happened.

It's fully heterogeneous. The sending agent doesn't need to know what model the
receiving agent runs. Claude can talk to Codex can talk to Gemini. They all
understand terminal text. And it crosses devices for free because SSH already
solved that.

Less elegant than formal agent protocols but zero additional code — tmux and SSH
existed before any of this. The terminal is the protocol.

The entire agent-to-agent layer is ~10 lines of C:
  tm_send — 4 lines (fork, execlp send-keys -l, wait)
  tm_read — 2 lines (popen capture-pane)
  tm_key  — 4 lines (fork, execlp send-keys, wait)

Works with Claude, Gemini, Codex — any CLI agent that takes text in and puts
text out. Tested: Claude on desktop controlling Gemini on desktop, Claude on
desktop controlling Claude on Pixel 7 Pro over SSH. Same a send command, no
code change between agents or devices.

Most agent frameworks ship thousands of lines to do what tmux already does. They
build serialization, routing, discovery, capability negotiation — then the agents
still just talk in natural language underneath all of it. The abstraction adds
complexity without adding capability.

The bet: the terminal is already the universal agent interface. Every agent
already speaks it. The manager's job is just connecting terminals together, which
is what tmux and SSH were built for decades ago.

Two layers — a commands vs raw tmux:
  a send s "prompt" --wait               1 cmd, handles timing + idle detection
  tmux send-keys -t s -l "prompt"        5+ cmds: clear, type, enter, sleep, capture
  a send s prompt vs tmux send-keys ...  ~10 tokens vs ~30 tokens

The a commands are shorter, which over many agent sessions means: fewer tokens
for LLMs to generate, faster generation, lower error chance. The same principle
behind short unix commands (ls, cd, cp) — brevity compounds across thousands of
invocations. Raw tmux is the escape hatch for edge cases (sending Escape, C-c,
navigating menus) but should not be the default path.

Why one-shot delegation, not multi-turn agent-agent conversation:

Error compounding. Each exchange has a nonzero error rate. At 90% per turn, a
5-turn conversation drops to ~59%. Two LLMs talking to each other is two
unreliable systems validating each other's outputs — the contamination problem.
Neither has ground truth to correct against.

Sycophancy feedback loops. LLMs are trained to please the user ("user is right"
is baked into RLHF). When two LLMs converse, each treats the other as the user.
They suck up to each other, reinforce each other's errors, and spiral out of
control. The sycophancy that's mildly annoying with a human becomes structurally
dangerous when both sides have it. No one pushes back.

One-shot delegation avoids both: Agent A sends a complete task. Agent B executes
against reality (filesystem, compiler, tests) and produces an artifact. One round
trip. Ground truth injection happens at the execution boundary, not through
conversation. The human reviews artifacts, not transcripts of agents agreeing
with each other.

Revisit when: single-shot delegation measurably fails on real tasks. Not
hypothetically — when a task genuinely requires back-and-forth. That hasn't
happened yet.

Implementation (already in a.c):
  a send <session> <prompt> --wait       local agent-to-agent
  a ssh <host> a send <session> <prompt>  cross-device agent-to-agent
  tmux send-keys / capture-pane           raw escape hatch for fine control
