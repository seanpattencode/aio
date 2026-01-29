# Latency

The command is `a`. One character.

## The 20ms barrier

Human neuron reaction time is ~15-25ms. A skilled typist can press a single key in under 20ms from intent to keystroke.

At this speed, the command stops being "a thing you type" and becomes "a thought that executes." The interface disappears. You think, it happens.

This is the sovereign cyborg thesis measured in milliseconds.

## The math

| Command | Chars | Time at 100ms/char | Time at 20ms/char |
|---------|-------|-------------------|-------------------|
| `aio c` | 5 | 500ms | 100ms |
| `a c` | 3 | 300ms | 60ms |

The difference isn't 2 characters. It's the difference between "typing a command" and "expressing intent."

## Annual time savings

```
2 chars saved × 100ms/char × 50 cmds/day × 365 days
= 3,650,000ms
= 3,650 seconds
≈ 1 hour/year
```

One hour isn't much. But it's one hour of pure friction - the worst kind of time.

## LLM token & binary savings

Tokenization varies by model. "a" is always 1 token. "aio" might be 1-2 tokens depending on the tokenizer's vocabulary. "ai" vs "aio" can tokenize differently even though the absolute difference is small - tokenizers have cliffs where adding one character creates a new token.

Even when token count is equal, fewer characters = fewer bytes everywhere:

```
"aio" = 3 bytes per occurrence
"a"   = 1 byte per occurrence
Savings: 2 bytes × every log line, script, prompt, response
```

At scale:

```
2 bytes × 1 billion agent invocations/day × 365 = 730 GB/year
```

That's 730 GB less storage, bandwidth, and context window consumed annually - just from the command name. Multiply across every agent framework adopting short names and the savings compound.

The rename from `aio` to `a` isn't just UX. It's infrastructure efficiency.

## Mobile error probability

Phone keyboards have ~5% error rate per character. Errors compound:

```
P(at least one error) = 1 - (0.95)^n

Command   Chars   P(error)
─────────────────────────
a           1       5%
aio         3      14%
a c         3      14%
aio c       5      23%
```

`aio` has **2.9× higher error probability** than `a` on mobile.

For a command you type 50 times daily:
- `a`: 2.5 errors/day, 912 errors/year
- `aio`: 7 errors/day, 2,555 errors/year

Each error costs ~3 seconds to notice and fix. That's:
- `a`: 45 min/year in error recovery
- `aio`: 2.1 hours/year in error recovery

Total mobile penalty for `aio` over `a`: **~1.5 hours/year** in error recovery alone, plus the base typing time.

## The real user

The 20ms barrier is about neural integration for someone with a mechanical keyboard and 4K monitor. They can absorb friction.

The real user is the genius in Nairobi typing on glass, paying per megabyte, coding between power outages. For them, 5% error rate per character isn't an annoyance - it's a filter that determines who gets to build things.

`aio` → `a` cut their error rate by 2.9×. That's not optimization. That's the difference between finishing the project and giving up.

Every design decision that seems like micro-optimization for a power user is accessibility for the most constrained user.

And you don't need to know English to type `a`. It's just a letter - universal, no vocabulary required. `aio` means nothing unless you know it stands for "all-in-one." `a` means nothing, and that's the point.

## Assistive technology

For users with motor disabilities, every character is costly:

- **Single switch** - 1 char vs 3 is 3× the selections
- **Eye gaze** - fewer dwell targets, fewer saccades
- **Voice control** - "a" is one phoneme, "aio" is three syllables
- **Tremors** - fewer keys to hit means fewer misses
- **Sip-and-puff** - each character is a breath
- **Morse input** - `a` is `·−`, `aio` is `·−/··/−−−`

For someone using assistive tech, `aio` → `a` isn't 1 hour/year. It's the difference between usable and not.

## Why this matters

Friction shapes behavior. Every millisecond of latency between thought and action is a chance for distraction, hesitation, context switch.

At sub-20ms, the tool becomes an extension of the nervous system. Above it, the tool remains a tool - something external you operate.

The goal isn't saving time. The goal is removing the gap between thinking and doing.

## Dominance

`a` strictly dominates `aio`. In every state where you can type `aio`, you can type `a`. `a` is never worse. `a` is often strictly better (speed, errors, accessibility, prewarming, bytes).

No tradeoff. No "it depends." The only costs are one-time: migration pain, discoverability, communication awkwardness. Transition costs, not ongoing. Once paid, `a` dominates forever.

Remapping to a different command name? Will add when someone yells at me to do it.

## Prewarming

Single character = unambiguous intent signal. Eye tracking sees gaze move to `a`, system starts prewarming before the keystroke lands. Longer commands can't do this - "ai" could become "aim", "aio" could become "aioli". But `a` followed by nothing is `a`.

Predictive systems need short, unambiguous tokens. `a` is as short as it gets.

## The end state

Today: `a` + Enter. Two actions, ~40ms.

Tomorrow: Eye gaze hits `a`, system prewarms. Keystroke confirms. Latency hidden.

Eventually: single key (caps lock or similar). One action, ~15ms.

At 15ms, there's no interface. Just thought → result.
