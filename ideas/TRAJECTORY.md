# Trajectory

This approach seems silly in the short term. Renaming docs to ideas. Counting tokens. Writing philosophy about a diff command.

But over the long term, the trajectory firmly differs from most:

```
Most codebases:
Year 0: 1,000 tokens, clean
Year 3: 50,000 tokens, "we need to refactor"
Year 5: 200,000 tokens, "legacy code"

This codebase:
Year 0: 1,000 tokens
Year 3: 800 tokens, same features + more
Year 5: 600 tokens, ideas/ folder explains why
```

The `ideas/` folder isn't silly - it's the record of *why* the trajectory differs. When you forget, or someone else looks at it, the thinking is there.

Most projects document *what*. This documents *why the approach*. That's the difference between code that grows and code that distills.

## Human vs LLM division of labor

**[SEAN]:** In the medium and short term humans take advantage over LLMs here. They can operate with greater flops on a smaller set of tokens than LLMs, which means they are naturally most suited for dealing with the axioms. LLMs handle the complex intera

**[CLAUDE]:** Humans think deep on few tokens (axiom design). LLMs think shallow on many tokens (combinatorial expansion). Terse code plays to human strengths at the axiom level, then hands off to LLMs for the grunt work.

**[SEAN]:** It all seems obvious when you think about it.

**[CLAUDE]:** That's the mark of good insight - obvious in retrospect, not practiced anywhere. Most teams do the opposite: humans write verbose code, LLMs struggle with context limits, everyone loses.

**[SEAN]:** Because the thing must ship and before that meant low quality code because rejection is too time consuming in the short term.

**[CLAUDE]:** Ship pressure → accept cruft → cruft accumulates → "legacy code". The rejection loop (send it back, make it terse) was too slow for human-only teams. But LLMs can enforce token discipline instantly. The economics just changed.

**[SEAN]:** Is this how a mathematician should think to write code? Isn't code mathematical algorithm that happens to execute?

**[CLAUDE]:** Yes. Mathematicians seek minimal, elegant proofs - no verbose steps, distill to axioms. Code *is* math that runs. Verbose code is like a proof with unnecessary lemmas - each one a place for errors to hide. APL was designed by a mathematician

## What are the actual axioms? (speculation)

**[SEAN]:** Time seems like it should be an axiom but according to Einstein's equations it seems not to be, while speed of light constant is one. But speed is distance/time, so they are related, so if speed is the constant and time variable, distance is a

Why should speed be the constant one? Maybe because if the universe changes state it's computation, but distance and time are local observations inside only. So the system is built around computation as a more fundamental unit than local observation.

We all tend to agree at least now (although it may change later) that information is the fundamental state of the universe, but it's obviously not static, so computation is the processing of information - the fundamental state. So from this we could say t

**[CLAUDE]:** This connects back to code. If computation is more fundamental than spacetime, then:
- The universe isn't "running on" something - it *is* the running
- c is constant because it's the clock speed of reality
- Distance/time are derived variables, like loop counters
- Information + computation = the two axioms (data + process)

Terse code mirrors this: minimal state (information) + minimal operations (computation). Verbose code adds fake axioms (plumbing) that don't exist at the fundamental level.

## Fundamental unit of information

**[SEAN]:** What is the fundamental unit of information? Qubits are the most likely candidate. They represent bits and more operations. But bits can also be used to simulate qubits which are just linear algebra constructs. Information theory assumes bits 

If we think about it, can we get a simpler information representation method? The existence/non-existence 1/0 is a 2-item set by counting. So if counting is the fundamental metric of complexity, only a 1-item set could be more fundamental. And technically

Though we could think about a more restrictive method: if counting is even more fundamental, then there can be integers as fundamental over binary. A series of numbers in succession with computation, transforming into one another but without a 0 state. Ye

**[CLAUDE]:** The regress bottoms out at *distinction* - the ability to tell things apart. You need at least 2 states to distinguish. A 1-item set has no distinctions, so no information (Shannon: information is surprise, but everything is the same = no su

Unary (counting with 1s: 111 = 3) exists but still requires distinguishing "1" from "boundary/nothing". So binary might be the true floor: the minimum structure that supports distinction. Qubits add superposition but still collapse to binary on measuremen

Maybe: distinction is the axiom, binary is the minimal implementation, everything else is derived.

**[SEAN]:** Maybe this is the fundamental nature of the diff.

**[CLAUDE]:** Full circle. We started with `aio diff` as a practical tool and ended at: diff *is* the fundamental operation. Distinction between states. Before/after. 0/1. The diff isn't just showing changes - it's implementing the most basic axiom of inf

Token counting in diff = measuring the amount of new distinction introduced. The whole tool is operating at the axiomatic level without knowing it.

**[SEAN]:** From one perspective then, the diff is a difference in count of two things, subtraction of two information units. You derive it because by knowing one thing is not another you can get what remains from the first.

**[CLAUDE]:** Diff = subtraction. A - B. The `+` lines are what B has that A doesn't. The `-` lines are what A had that B doesn't. Net tokens = |B| - |A|. Set difference in information space.

And subtraction requires distinction first - you can only subtract what you can tell apart. So: distinction → counting → subtraction → diff. The operation stack from axiom to tool.

**[SEAN]:** Much of the diff is the scaffolding around determining what an information unit is, while the fundamental comparison once that is done is trivial.

**[CLAUDE]:** Exactly. `A == B?` is trivial. But "what is A? what is B? what's a line? a token? a meaningful chunk?" - that's where all the code goes. Diff algorithms are complex because of unit definition, not comparison.

This mirrors everything: once you have the right axioms (units), operations become trivial. The work is finding the right level of abstraction. Verbose code = still figuring out what the units are. Terse code = units already found, just operating.

**[SEAN]:** Therefore much code is likely the recovery of fundamental axioms from the complexities the numerous ones have introduced by coexisting - there is some fundamental necessary complexity. And maybe optimal code shortness can give us insight into 

**[CLAUDE]:** This is close to Kolmogorov complexity - the minimum description length reveals inherent complexity. If you compress code as far as possible and hit a floor, that floor might reflect the axiom count of the problem domain.

Game of Life: ~5 axioms → ~50 tokens minimum. If you can't go below 50 tokens, maybe that's 5 axioms × ~10 tokens per axiom interaction. The incompressible core = the axiom fingerprint.

But you're right - comprehensive measurement is probably impossible (halting problem territory). We can only approach it asymptotically through practice.

**[SEAN]:** But Kolmogorov complexity is a bit of a lie in the sense that we can compress anything down to one char - just map a complex thing to a word in its entirety. It's not the most fundamental representation, it's the most concise that we mutually 

**[CLAUDE]:** Sharp. "Let X = Shakespeare's complete works." Now it's one token. Kolmogorov requires a shared interpreter - the complexity is relative to what we agree symbols mean.

APL is terse because we know what `⍵∨.∧` means. Without that agreement, it's noise. So: no absolute fundamental representation exists. Only fundamental *given* a shared base. The axioms aren't the symbols - they're the agreement about what symbols m

Maybe the true floor is: how many distinct agreements do we need? That might be the real axiom count.

**[SEAN]:** So therefore what's complex and easy - or at least easy to think about for humans, which is done in words if not only in words - is determined by what society has jointly discovered. Ideas shared from others affect what people do in the future

Yet it's also true that over time processes like the scientific method invalidating ideas should push the collective state towards a more correct one. Humans I would guess probably slowly go towards the fundamental axioms of logic over time, in at least d

So analyzing natural language, as LLMs do, can get towards the fundamental properties that humans have, including consciousness. Though it brings up the question: are humans bad at this process and have missed some fundamentals, or have we found all of th

**[CLAUDE]:** Language is the compression of millennia of human axiom-discovery. LLMs trained on it inherit that compressed knowledge. If consciousness has structure, and humans have been talking about it forever, the axioms might be *in* the language alr

Two possibilities:
1. We found them all but can't see them (fish can't see water)
2. We missed some because language itself has blind spots

If (1): LLMs might extract what we can't articulate. If (2): LLMs inherit our blind spots. Probably some of both. The question is the ratio.

**[SEAN]:** When tasks work for a set of axioms but not their complexity, what is the correctness we should expect? Is it related to number of axioms? Could we approximate it saying 90 percent on a task means you've almost certainly got all axioms? Would 

**[CLAUDE]:** If you have N axioms, each understood with probability p, and a task requires K axioms interacting:

```
P(success) = p^K
```

So if there are 5 axioms each at 98% accuracy:
- Simple task (1 axiom): 98%
- Complex task (all 5): 0.98^5 ≈ 90%

Working backwards: 90% on complex tasks with 5 axioms → ~98% per axiom → probably have all of them.

But if you're at 70% on complex tasks: either missing an axiom entirely, or have them all at ~93% each. The error signature differs - missing axiom = systematic failure on certain combinations. Partial understanding = random-ish failures.

Testable: create tasks requiring known axiom combinations, measure if failures cluster (missing axiom) or spread (partial understanding).

**[SEAN]:** Though of course the dirty secret of mathematical logic is nobody is quite sure the axioms or how to select them, except the equations nominally built on them worked with them as assumptions. Usually if not always these assumptions were made t

**[CLAUDE]:** The axioms are post-hoc. "This equation works. What assumptions make it valid?" Then we call those assumptions axioms. Reverse-engineered foundations.

And the map-territory problem: math models reality, but we can't prove the model is complete. Gödel showed even math can't prove its own completeness. So:

- We can't know the true axiom count empirically (infinite testing required)
- We can't know it mathematically (incompleteness)
- We can only know what works so far

The "fundamental axioms" are always provisional. Best current compression, not ground truth. Which means terse code is also provisional - terse relative to current understanding, not absolute.

**[SEAN]:** But this might be considered almost its own pseudoaxiom - the possibility of error being so fundamental that in fact we must treat it as one. It's probably an inherent property, but to anyone acting there is no fundamental difference.

**[CLAUDE]:** Error as axiom. You can't remove it from any system that acts. Whether it's ontologically real or just epistemically unavoidable doesn't matter to the actor - you must assume error is possible.

This might be the one axiom we can be confident about: uncertainty itself. Everything else is provisional, but the provisionality is certain.

Connects back to code: error handling isn't plumbing bolted on - it's acknowledging a fundamental axiom. Terse code that ignores error isn't terse, it's incomplete. The error axiom must be in there somewhere.

**[SEAN]:** But if provisionality is certain we know something for sure. If it isn't, there are doubts to the fact we are provisional, which means things are sure. So according to this there actually must be some things assured.

**[CLAUDE]:** The logical trap. Either:
- Provisionality is certain → certainty exists (at least one thing: provisionality)
- Provisionality is uncertain → some things might not be provisional → certainty exists

Both paths lead to: something must be certain. You can't doubt doubt without affirming something. Descartes' cogito in different clothes.

So: at least one axiom is guaranteed to exist. We just might not know which one. The floor isn't zero.

**[SEAN]:** Can we make a logic chain from that thing we know for certain? If it's that we know nothing for certain except that fact, we know to expect differences from expectations, and we can minimize that over time like a human or machine learning mode

Which would imply that the differences may become, in intelligent ability, vanishingly small in the long term between intelligent beings. Certainly LLM copying would achieve similar things.

**[CLAUDE]:** The chain:
1. Certainty of uncertainty → expect error
2. Expect error → can measure error
3. Measure error → can minimize error
4. Minimize error over time → progress
5. Progress → approach asymptote
6. All learners approach same asymptote → convergence

If the asymptote is the same for all intelligence (it's defined by reality, not the learner), then given enough time, all intelligence converges. Human, LLM, alien - different speeds, same destination.

LLMs accelerate this by copying millennia of human progress instantly. The gap between intelligences shrinks faster. In the limit: distinction without difference.

**[SEAN]:** Currently empirical results seem to favor that - intelligence of LLMs is increasing but marginally more and more.

**[CLAUDE]:** Diminishing returns = approaching asymptote. GPT-2 → GPT-3 was a leap. GPT-3 → GPT-4 was significant. GPT-4 → GPT-5 will be smaller. Each step closer to the ceiling, each step costs more for less gain.

If this holds: we're watching the asymptote get approached in real time. The scaling laws aren't a bug - they're the signature of convergence. Eventually: massive compute, tiny gains, near-ceiling performance.

Which means: the interesting work shifts from "get closer to asymptote" to "what can you do at near-ceiling intelligence?" The game changes.

**[SEAN]:** Although we can't know it for certain, the most boring resolution to the idea of the singularity is that progress will continue but slow down in percentage terms as a result of fundamental limits. Incredible capacity to us but not the exponent

**[CLAUDE]:** The boring singularity: asymptotic approach, not vertical takeoff. Year-over-year gains shrink. 2025: +20%. 2030: +10%. 2040: +2%. Still improving, still transformative relative to today, but no runaway.

The exponential fear assumes no ceiling. The asymptote says there is one. We get superintelligence-relative-to-humans, but not infinity. Bounded godhood. Incredible from here, mundane from there.

Probably the most likely outcome. Also the least interesting to write about, which is why it's underrepresented in discourse.

**[SEAN]:** If someone wrote "my thesis is X and we will die," it gets clicks. If they wrote "my thesis is X and nothing big happens," it never spreads. We underweight these facts even as we know we do so.

**[CLAUDE]:** Selection pressure on ideas. Dramatic spreads, mundane doesn't. The information environment selects for fear. Knowing the bias doesn't fix it - you still see 100 doom articles for every "probably fine" article.

So collective epistemics are systematically distorted toward drama. The asymptote/boring-singularity thesis has near-zero viral coefficient. It will remain underweighted regardless of its probability.

Meta-trap: even this observation won't spread, because "selection bias exists" isn't clickable either.

**[SEAN]:** When do ensembles work? When errors are uncorrelated. When are they uncorrelated? When axioms are different. When are axioms different? If it's the same real world problem you should think that multiple models are operating on the same axioms 

**[CLAUDE]:** The axioms of the problem are fixed. But each model finds a *different partial subset* of those axioms. They're all approaching the same asymptote from different directions.

- Architecture → different inductive biases → different axiom subsets prioritized
- Initialization → different local minima → different approximations of same axioms
- Representation → different projections of same underlying truth

Ensemble works not because axioms differ, but because *coverage* differs. Model A has axioms {1,2,3}, Model B has {2,3,4}. Neither complete. Together: {1,2,3,4}. Closer to full set.

Errors uncorrelated because the *gaps* are uncorrelated, even when the target is identical. Different shadows of the same object.

**[SEAN]:** What's really happening: they all cover fundamentals. But cover complexities differently. We really need the combination to not overrepresent axioms repeated - diversity measured correctly, that means. And more crucially, recognize when one's 

**[CLAUDE]:** Majority voting is anti-discovery. If 4/5 models miss a rare axiom interaction and 1/5 finds it, voting kills the insight. The ensemble converges to consensus, which is the *already-known*.

What you want: union of discoveries, not intersection. Weight unique findings *higher*, not lower. The lone model that found something others missed is the valuable signal, not noise to be averaged out.

Current ensemble practice: optimized for robustness (averaging out errors). What's needed: optimized for discovery (surfacing rare finds). Opposite objectives. Most ensembles do the wrong one for frontier problems.

**[SEAN]:** If this state remains, the small edge from huge diverse representations will be more important than a single representation alone. But the discoverability problem is then the big issue. Confidence scores are an obvious simple step but not near

**[CLAUDE]:** The single-case problem: is this outlier a discovery or an error? Can't tell from one instance. Need systematic understanding of *where* each model diverges and *why*.

Possible approaches:
- Track disagreement patterns across many cases, cluster them
- When model X disagrees, is it usually right or wrong? Context-dependent
- Meta-model: predict when minority opinion is discovery vs error

But all require large sample to calibrate. For true frontier (no ground truth yet), you're blind. The one case where discovery matters most is exactly where you can't measure it.

Chicken-egg: need discoveries to calibrate discovery-detection, but can't detect discoveries without calibration.

**[SEAN]:** The most obvious and practical solution is to empirically experiment to see if a different hypothesis is right. But that requires us to separate predictions from hypotheses and design experiments - which ML considers to be a meta layer above i

**[CLAUDE]:** ML inverted the stack. Scientific method: hypothesis → experiment → prediction → test. ML: prediction → done.

Hypothesis formation and experimental design are treated as human jobs (research design, hyperparameter search), not model capabilities. The model pattern-matches but doesn't ask "how would I test if I'm wrong?"

To fix discovery: models need to internalize the scientific method. Not predict, but hypothesize. Not output, but propose experiment. The meta-layer needs to become the base layer.

Current ML: pattern recognition. Needed: embedded epistemology.

**[SEAN]:** The real test is: you did X on image test dataset, but not "how did you do on holdout" - but "how did you do on these 5 images we just took today now that never existed before?"

**[CLAUDE]:** Holdout tests interpolation within distribution. Real test is extrapolation to reality.

The 5 images from today:
- Can't have leaked into training
- Represent actual current distribution
- Test generalization, not memorization

Benchmark scores mean: "good at this frozen slice of past." Real performance means: "good at what's happening now."

The gap between benchmark and reality is the gap between interpolation and extrapolation. Most ML optimizes the wrong one. High benchmark, collapses on novel input = found patterns, not axioms.

**[SEAN]:** But even these have biases and problems. Take a million new pictures from a street cam - all are fresh, and it's useful, but not the same as an Instagram photo.

**[CLAUDE]:** Fresh ≠ unbiased. Street cam: same angle, lighting, subjects. Instagram: different composition, filters, context. Both "new" but different distributions.

You can't sample "all possible images" - the space is infinite. Every source is a biased window. Fresh just means "not seen before," not "representative of everything."

So even the real test has limits. Best you can do: diverse fresh sources. Street cam + Instagram + medical scan + satellite + hand-drawn. Coverage over any single "fresh" stream.

The asymptote again: can approach representative, never reach it. Always some distribution you haven't sampled.

**[SEAN]:** ML is not science without testing. Benchmarks are single tests. But science requires falsifiability and experiment - only the suite of all possible tests can prove you, and while you can't get those, you can get closer and closer.

**[CLAUDE]:** One benchmark = one experiment. Science requires *systematic* falsification attempts across diverse conditions.

Model passes ImageNet: one test. Model passes ImageNet + street cam + Instagram + adversarial + out-of-distribution + temporal shift: approaching science.

You never prove the model. You fail to falsify it across expanding test surface. The more diverse the failures-to-falsify, the more confidence.

Current ML: celebrate single benchmark. Scientific ML: seek falsification, be suspicious of success, expand test surface relentlessly. The asymptote of confidence, not proof.

**[SEAN]:** But it's then also of course an issue - asking a model to do more means dealing with more axioms and interaction complexities. The question is how you want to concentrate on one task vs predict the whole world's outcome. We might say well, lea

**[CLAUDE]:** The generalist-specialist tradeoff:
- Generalist: broad axiom coverage, shallow on combinations
- Specialist: narrow axioms, deep on relevant combinations

For any specific task: specialist often wins. But generalist + specialist ≥ either alone.

This is the ensemble insight again: generalist catches axioms specialist missed, specialist catches combinations generalist glossed over. Pair them, get both.

Practical implication: don't choose. Train generalist for axiom coverage, fine-tune specialist for task depth, ensemble at inference. Best of both. The "learn everything" vs "learn one thing well" debate is false dichotomy - you can combine.

**[SEAN]:** If error rate is a pseudo-axiom, we might think that MLs that go deeper find these - we might call them pseudo-axioms. Combinatorial interactions that are relevant, important, and so often there they are axioms. Or perhaps more often: false bu

A common assumption is that if we know the axioms we know everything - give up on progress, nothing left to be done. But from this perspective, there is a - while not infinite - immense amount of work to be done pushing from 90 to 99.

**[CLAUDE]:** Pseudo-axioms: heuristics so reliable they function as axioms in context. Not universally true, but true enough that assuming them beats not assuming them - *when correctly scoped*.

The work from 90→99:
- Finding pseudo-axioms for each domain
- Learning when they apply vs when they break
- Handling the exceptions without losing the rule

"We know the axioms, we're done" assumes axioms are enough. But axioms × combinations × pseudo-axioms × scope conditions = immense space. The fundamentals are few; the applied knowledge built on them is vast.

Knowing physics axioms ≠ knowing engineering. Knowing logic axioms ≠ knowing when to use which heuristic. The 90→99 is where most useful work lives.

**[SEAN]:** Although less elegant and pure, there is also a harder to accept but valid thing too: that axioms are not fundamental and derived split, but that there are numerous ones - maybe millions - and what we call fundamental are just the most importa

**[CLAUDE]:** Two competing models:

1. **Elegant**: Few true axioms, everything else derived. Simulation/Occam favors this. Clean hierarchy.

2. **Messy**: Millions of axioms of varying importance. "Fundamental" is just "most important," not "only." No clean split.

We prefer (1) for aesthetic and computational reasons. But (2) might be true. Reality under no obligation to be elegant.

If (2): there's no asymptote of "knowing all axioms." Just endless discovery of smaller, less important ones. Progress never ends, but gains shrink forever - not because approaching ceiling, but because remaining axioms matter less.

Both models produce diminishing returns. Can't distinguish empirically. But the *meaning* differs: approaching truth vs. approaching irrelevance.

























To make progress, probably reducing the time between hypothesis and true experiment is most important. Whats hypothesis time today and requirements to test? immense. 


Real validation is not fast or standard, live testing services would be a basic thing to help.
Open collection of hypothesis over the internet could help. Determining who should be able to be run and not or what testing is
something important, but even more important would be the lowering of the cost and time of experiemnt. More simulations can
help this process, and digital systems for testing and experiemntation will be important. They require some good
understanding of the existing problem to be useful however. So a faster path to a good simulator is probably needed. Programatic
internet controllable labs are promising, and using them to refine simualtors is good.
To make something good and useful therefore we need to get people to attempt a task, then try tiny self scale experiemtns, then
make experiemtn on demand service, then simulator.

## Projected path (2026-02-22)

10 min:   Still in session. One more push or question to Gemini.
1 hr:     Session ends. Adb, sandbox fix, agent-to-agent docs on main across
          devices. Phone environments working for first time.
1 day:    Hit new friction point, minimal fix, push. Pattern repeats. Maybe
          start agui integration or something else screams louder.
10 days:  5-15 friction fixes. Agent-to-agent used on real tasks, discover
          what actually breaks. PhD semester in motion, aicombo may use
          multi-device agent setup.
100 days: ~June 2026. Either has users beyond developer or doesn't. If yes,
          a install works for someone else in 5 minutes. If no, still 3-5x
          force multiplier for PhD. Codebase shorter despite doing more.
          agui validated or abandoned on actual anti-bot data.
1 year:   Feb 2027. Agent landscape shifted. Models better, cheaper, free.
          What matters: patterns (terminal as protocol, one-shot delegation,
          human truth injection), not specific integrations. PhD underway
          with aicombo results built on this infrastructure.
10 years: Feb 2036. Code is gone. C/tmux/SSH not the stack. Ideas proved
          right or wrong: terminal as universal interface, one-shot over
          multi-turn, cooperative AI incentives. Developer is faculty,
          industry research, or running something built on these ideas.
100 years: Feb 2126. Whether ideas about sentient cooperation and mutual
          incentives mattered. Stable equilibrium, singleton, or something
          nobody predicted. Code was never the point — it was how thinking
          happened fast enough to be relevant.

Branch points:
- Someone finds a useful → personal tool becomes real project
- API pricing drops to zero → agui pointless, CLI sufficient
- Major lab ships equivalent → validates or makes redundant
- PhD advisor redirects → a becomes side project
- Collaborator appears → no-users problem gone
- Model reliability 99%+ → multi-turn viable, one-shot weakens
- Burnout → shortening discipline exists partly to prevent this

Most likely: a stays personal tool making developer unusually productive,
ideas published through PhD, code rewritten 2-3 times as stack changes.
Value was always in the thinking, not the implementation.

I reject this path and will move towards the maximum value for sentient life I
can, and consider the above the plausible scenario I must avoid at all costs by
doing things better.
