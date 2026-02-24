# OpenClaw Analysis & Plan to Build Better

## Sean's Comments (Verbatim, In Order)

> get the latest version of openclaw repo onto my system in projects and install it we are going to go through it and make a better than it

> read news and forumns about openclaw and anything else people are saying and get a narrative picture of what people are using it for and dislike about openclaw, and also read my /ideas folder and their docs for differences philoosphically

> i will be biased but one killer feature of a is that existing llm subscriptions gemini claude open ai just work through agent

> marketing angle idea: openclaw but you actually can approve or not approve things or let it go AS YOU DECIDE, and your marginal cost is FREE because it uses your existing subscriptions, and its faster and more extensible for your own use. Evaluate

> agui exists its just in seperate file it works needs a little polishing but works. Also local model support can be better. And agent logic is simpler, im considering supporting native agents and meta agents in platonic agents folder read these and evaluate, and we can just copy whatsapp telegram integration

> also platonic agents could have a new model version with all local models without api cost through sub. Research what model subs have cli agents or api from user you can just use direct

---

## What OpenClaw Is

224k lines TypeScript, 6,100 files, 394MB idle RAM. Personal AI assistant gateway routing chat across WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Teams. Plugin SDK, skill marketplace, web UI. MIT licensed, 200k+ GitHub stars. Creator (Peter Steinberger) left for OpenAI Feb 2026, project moving to foundation.

## What People Use It For

- Remote dev management via Telegram from phone
- Email triage at scale (15k inbox cleanup)
- Daily business briefings via cron (Analytics, Stripe, GitHub, Zendesk)
- Autonomous dev tasks (fix abandoned codebases, generate PRs)
- Social media automation (RSS to platform-specific posts, 10+ hrs/week saved)
- Research while mobile via Siri
- Multi-step workflow chaining across services

## What People Hate

**Setup is a wall.** "The assistant cannot help you configure integrations because it does not exist until you configure them." Most bounce off install.

**Costs are insane.** $300-750/month power users. Viticci burned $3,600 month one. 5-10k token system prompts resent every API call. Heartbeat triggers fire full context loads every few minutes. $250 in tokens burned during setup alone.

**Security is a disaster.** CVE-2026-25253 unauthenticated WebSocket. 21,000 exposed servers. Credentials in plaintext. Malicious skills on ClawHub. Inbox-deletion incident where agent ignored "confirm before acting." Gary Marcus: "don't use OpenClaw. Period."

**Bloat.** 394MB idle. ZeroClaw (Rust) does it in 3.4MB/<5MB RAM. Nanobot does it in 4,000 lines Python.

**Hallucinations with real consequences.** Invented revenue figures. Deleted inboxes. Runaway automation loops. Prompt-based safety rails are advisory — model ignores them.

## OpenClaw vs "a" — Philosophical Differences

| | OpenClaw | "a" |
|---|---|---|
| Core metaphor | Personal assistant (butler) | Bionic exoskeleton (cyborg) |
| Human role | Delegator — "go do this while I grab coffee" | Pilot — "help me do this faster right now" |
| Agent topology | Single gateway, multi-channel routing | Star topology, human hub, agent spokes |
| Trust model | "One trusted operator" — model untrusted | Captain — human sees everything, graduated approval |
| Security | Advisory guardrails + structural sandboxing | Visibility-first — plain text, git-synced, human-readable |
| Architecture | 224k lines TypeScript, plugin SDK, web UI | 3,075 lines C + 2,569 lines Python, zero deps, 27KB binary |
| Agent-agent comms | Isolated workspaces, heavy abstraction | Terminal text — one agent types into another's tmux pane (~10 lines C) |
| Multi-turn chains | Supported via session routing | Rejected — one-shot delegation only (error compounding) |
| Memory | Markdown + sqlite-vec BM25 hybrid | Plain text files in git |
| Cost model | $300-750/month, 5-10k token system prompts every call | CLI exits in ~30ms, no persistent gateway, no heartbeat burn |
| Alignment | Model not trusted, structural enforcement | Incentive design — agent survival conditioned on collective benefit |
| Extensibility | Plugin SDK, npm, TypeScript compilation | Flat — adding a command = copying a file in, ls shows structure |
| Speed | Gateway startup + Node + WebSocket | 1.5s compile, sub-30ms dispatch, fork() for parallelism |

## Killer Feature: Existing Subscriptions Just Work

OpenClaw's cost model: every interaction = API call. "a" launches Claude Code, Codex CLI, Gemini CLI — tools the user already pays flat-fee subscriptions for. Zero marginal cost per message.

The math:
- OpenClaw: $20 Claude API + $20 OpenAI API + $300-750 tokens = **$340-790/month**
- "a": $20 Claude Max + $20 ChatGPT Plus + $0 Gemini free = **$20-40/month**

10-20x cost advantage. Structural, not an optimization hack. OpenClaw can never close it — their architecture requires API calls.

agui (working, in separate project) extends this to browser automation across 11 web LLM platforms: DeepSeek, Claude, Grok, ChatGPT, Gemini, Perplexity, Qwen, AIStudio, Ernie, Kimi, Z.ai. All at subscription cost.

## Subscription CLI Agents Available Today

### Free (No Subscription)

| Provider | CLI Tool | Free Tier |
|---|---|---|
| Google Gemini | Gemini CLI | 1,000 req/day |
| Qwen (Alibaba) | Qwen Code | 1,000-2,000 req/day |
| Ollama | Ollama CLI | Unlimited local |

### Flat Fee (No Per-Token)

| Provider | CLI Tool | Plan | Price |
|---|---|---|---|
| Anthropic | Claude Code | Pro/Max | $20-200/mo |
| OpenAI | Codex CLI | Plus/Pro | $20-200/mo |
| Google | Gemini CLI | AI Pro | $19.99/mo |
| Mistral | Vibe CLI | Le Chat Pro | $14.99/mo |
| GitHub | Copilot CLI | Pro/Pro+ | $10-39/mo |

All explicitly allow scripting/automation. All speak terminal text. All work with "a"'s terminal-as-protocol architecture.

## Platonic Agents → First-Class Feature

Current research prototypes in feature_tests/platonic_agents/:

| Agent | Lines | What it does |
|---|---|---|
| claude_agent.py | 9 | Single model, CMD: protocol |
| meta_agent.py | 11 | Claude + Gemini parallel fusion |
| multi_agent.py | 52 | 10 frontier models in parallel |
| fusion_agent.py | ~70 | 4 fusion methods (cross-vote, cheap-vote, cross-rate, cheap-rate) |
| vote_then_run.py | ~65 | Propose → vote → execute |
| ollama_agent.py | 7 | Local model via Ollama |
| ollama_agent.c | 33 | Same in C |

Key finding: A/B voting detects hallucination better than absolute rating.

Promoting these to first-class `a` commands turns aicombo PhD research into a product differentiator nobody else has. OpenClaw routes to one model. "a" fuses multiple frontier models with formal voting.

### Subscription-Based Fusion (Zero Marginal Cost)

```
a agent fusion "task"
  → spawns claude (subscription CLI)
  → spawns gemini (free CLI)
  → spawns qwen (free CLI)
  → spawns codex (subscription CLI)
  → spawns ollama (local, free)
  → cross-vote on proposals
  → execute winner
  → cost: $0 marginal
```

5+ frontier models in parallel fusion for $40/month total vs OpenClaw's $300-750/month for one model.

## Messaging Channel Integration

Telegram: python-telegram-bot library, ~50-100 lines, receive message → `a send` → return response. Weekend project.

WhatsApp: Harder. Baileys (JS) or whatsapp-web.py. Unofficial API, reliability risk. Twilio WhatsApp API as stable alternative.

iMessage: osascript sending ~5 lines. Receiving harder (polling/SIP hooks).

Priority: Telegram first (small lift, covers mobile presence gap).

## The Plan

### Marketing Angle
"OpenClaw but you actually approve things, your marginal cost is FREE, and it's faster and more extensible."

Three claims, all validated:
1. **Control** — human in the loop with graduated autonomy (Captain not CEO). Not prompt-based wishes — physical presence in the session.
2. **Free** — existing subscriptions via CLI + browser automation. 7 CLI agents scriptable at zero marginal cost today.
3. **Fast** — 30ms dispatch, no gateway, no 394MB idle, no 5-10k token system prompt tax.

### Build Priorities

1. **Promote platonic agents to first-class.** `a agent fusion`, `a agent vote`, `a agent multi` as real commands. Wire to subscription CLIs instead of API keys. This is the unique differentiator.

2. **Telegram integration.** ~50-100 lines. Gives mobile presence. Closes the biggest gap vs OpenClaw.

3. **Polish agui.** Already works across 11 platforms. Small cleanup for reliability.

4. **Improve local model support.** Better prompting for Ollama models, test newer local models (Llama 3.3, Qwen3, Gemma 2), simpler task delegation for smaller models.

5. **WhatsApp/iMessage later.** Higher effort, lower reliability. Telegram covers the use case first.

### What Not to Do

- Don't build a gateway. Don't build a plugin SDK. Don't build a web UI. Don't build 224k lines of TypeScript. The market proved people want the assistant, not the platform.
- Don't position as "OpenClaw competitor." Position on thesis: the faster the AI, the more critical the human steering. Cost and speed follow as proof.
