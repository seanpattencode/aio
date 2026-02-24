# Token Efficiency

> over long sessions of ssh its actually lower token count than ssh commands direct right

> but i mean imagine a million calls and token counts

> calc at current rates and also estimate total tokens because thats also time to gen

---

## Analysis

Short commands aren't just ergonomics anymore when AI is the user. `a ssh 4 "cmd"` vs `ssh seanpatten@192.168.1.183 "cmd"` - token efficiency becomes a design consideration.

Example savings per call: ~5 tokens

At 1 million calls:

```
Tokens saved: 5,000,000

Cost savings (output tokens - what AI generates):
  Sonnet: $75
  Opus: $375

Generation time saved:
  @ 50 tok/s: 28 hours
  @ 100 tok/s: 14 hours
```

Short CLI syntax is basically an optimization for AI agents at scale.

## Error Rate Scales with Token Count

Approximate error rate by magnitude of change: 1 token change introduces an error? No. 10? No. 100? Yes — seems like the right threshold. So if your fix fixes one issue but adds ~100 tokens, you've on average introduced a new error. Net negative — on average killed future progress.

And it's worse than just bugs. Misalignment with value — does the program do useful work? — is error rate of the program *plus* deviation from valuable behavior. So you need to be even more aggressive on shortening. Token reduction must outpace the fix to drive net value increase, not just break even on bugs.
