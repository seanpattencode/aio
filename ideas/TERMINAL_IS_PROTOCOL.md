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

Implementation (already in a.c):
  a send <session> <prompt> --wait       local agent-to-agent
  a ssh <host> a send <session> <prompt>  cross-device agent-to-agent
  tmux send-keys / capture-pane           raw primitives for any composition
