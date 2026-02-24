# Captain, Not CEO

## The Metaphor
Managing AI agents should be like being the captain of a ship — ordering things
but sharing the understanding and available to make decisions on the fly. Not a
CEO who you send an email to once a year that gets politely ignored.

## The Five Axioms of Agent Management
1. **See** — what's running, where, what state
2. **Direct** — start something, give it a task
3. **Interrupt** — redirect mid-execution
4. **Move** — switch context instantly
5. **Sync** — share state across all locations

These are universal. Any intelligent entity managing other intelligent entities
needs these five operations — human managing agents, agent managing agents,
human managing humans. The axioms don't mention tmux or CLI or Python.

## See Is First
You can delegate Direct. You can delegate Interrupt. You cannot delegate See
without losing the ability to scream. Observation is the one thing the captain
never delegates.

Walton at 50 billion dollars still walking stores. Musk sleeping on the factory
floor during Model 3 production hell. Torvalds reading patches. Attaching to a
tmux session and watching the agent work.

Same pattern: the most effective leaders at any scale maintain direct contact with
the lowest level of their system. Not heroics — the scream test. You can't scream
at an inadequacy you haven't seen.

Every layer between you and reality is lossy compression. The store visit IS raw
signal. The dashboard IS someone else's decision about what you should see. The
moment you can only see agent output through a summary layer, you've become the
CEO reading emails.

## Flat vs Hierarchical
Flat doesn't scale with human bandwidth. But it scales fine if the
voting/comparison mechanism is fast enough. The bottleneck in flat organizations
isn't decision quality — it's decision speed.

Binary comparison of agent outputs attacks this directly. Instead of one
maintainer reviewing everything (Linus model), agents evaluate each other's
output. Anyone can fork, anyone can submit, the group merges by comparison. No
bottleneck, quality maintained by collective judgment.

The singleton argument applies: mutual error correction beats single-point error
correction over infinite time. Single point has nonzero terminal error rate.

## Human In Loop At Optimal Speed Of One
Flat with human approval is the correct current architecture. Voting and
comparison reduce what hits your desk — instead of reviewing every agent's
output, you review the winner of N comparisons. Agents do O(N²) comparison,
you do O(1) approval.

Optimal decision speed is one. One human, one approval, one decision at a time.
That's fine if the pipeline feeding you decisions is good enough. A captain
doesn't make 100 decisions per second. They make one good decision per minute
because the crew preprocessed everything else.

## The Transition Path
- Now: you approve everything, agents execute
- Near: agents vote/compare, you approve the winner
- Later: agents approve routine decisions, you approve novel ones
- Eventually: you approve policy changes, agents approve within policy

Each step removes you from a class of decisions you've already demonstrated the
pattern for. The human loop doesn't disappear — it moves up the abstraction
stack. Same as Linus: doesn't approve every commit, still approves merge windows.

At every stage: you CAN interrupt. Axiom 3 never goes away.

## Why "Attempt Use As Final" Is Walking The Store
The workcycle starts with direct contact. You're the customer. The scream comes
from using the thing, not from reading a report about what might scream. As the
agent fleet scales, the temptation is to stop walking stores — to rely entirely
on the voting pipeline. The architecture should make walking stores easy at any
scale, not replace it.

Even if you only directly observe 1% of agent decisions, that 1% calibrates your
trust in the other 99%.

## Connection to aicombo
Combining diverse models through comparison produces better results than any
single model (CFA thesis). The practical system ("a" with flat agent voting) and
the theory (aicombo with combinatorial fusion) converge on the same architecture:
diverse agents, binary comparison, flat structure, human approval at the top.
