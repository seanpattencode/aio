# The Great Filters of Agent Managers

## Bottlenecks to Success

| Filter | Why it kills projects | One-night solve | Complexity |
|--------|----------------------|-----------------|------------|
| **1. Message passing** | Agents are isolated processes | SQLite queue table + poll loop | Low |
| **2. Shared memory** | Context lost between runs | SQLite key-value + vector store | Medium |
| **3. Task decomposition** | Can't break down complex work | Prompt template + recursive spawn | Medium |
| **4. Output → Input chain** | Manual copy-paste between agents | Pipe stdout to next agent's stdin | Low |
| **5. Error recovery** | One failure = full stop | Try/retry wrapper + fallback agent | Medium |
| **6. Trust boundaries** | Too safe = useless, too free = dangerous | Tiered permissions per task type | Medium |
| **7. Feedback loop** | No learning from success/failure | Log outcomes + adjust prompts | Hard |
| **8. Self-modification** | Can suggest but can't implement | Agent with Edit permission on own code | Scary |

## Why Each is a Great Filter

1. **Message passing** - Everyone builds isolated agents, few connect them
2. **Shared memory** - Stateless is easy, stateful is where complexity explodes
3. **Task decomposition** - Requires the AI to plan, not just execute
4. **Chaining** - Unix solved this in 1970, yet most agent frameworks ignore it
5. **Error recovery** - Happy path is easy, resilience is hard
6. **Trust** - The unsolved problem. Too much thought → paralysis
7. **Feedback** - Closing the loop requires measuring success (hard to define)
8. **Self-modification** - The ultimate test. Most stop here out of fear

## One-Night Ambitious Plan

```
Hour 1: Message queue (sqlite table: id, from_agent, to_agent, payload, status)
Hour 2: Agent wrapper that reads queue, runs claude, writes result
Hour 3: Task decomposer prompt + spawn logic
Hour 4: Chain syntax: aio pipe "agent1 | agent2 | agent3"
Hour 5: Error handler + retry logic
Hour 6: Permission tiers in config (read-only, read-write, full)
Hour 7: Outcome logger + success criteria
Hour 8: Agent that can edit aio.py with approval gate
```

## The Real Filter

Not technical - it's *deciding what agents should do*. The infrastructure is a weekend project. The taste for what to automate takes longer.

## Current Status (aio)

- [x] Session manager for AI agents
- [x] Scheduled tasks (aio hub)
- [x] Cross-device sync
- [x] Self-analysis (daily insight email)
- [ ] Message passing between agents
- [ ] Shared memory
- [ ] Task decomposition
- [ ] Output chaining
- [ ] Error recovery
- [ ] Trust tiers
- [ ] Feedback loops
- [ ] Self-modification
