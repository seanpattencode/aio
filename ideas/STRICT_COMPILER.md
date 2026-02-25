# The Strict Compiler is the Best Bug Finder Nobody Uses

## The headline vs the reality

Articles regularly celebrate "LLM finds 100 bugs in hardened open source project."
They forget that clang, coverity, and PVS-Studio have found tens of thousands of
bugs in the same codebases for over a decade. Developers just ignore the warnings.

An LLM finds bugs by reading code and reasoning about it. A compiler finds bugs by
*proving* them — no false confidence, no hallucination, deterministic. And it runs
in milliseconds, not minutes with API calls.

The problem was never detection. The tooling has been there for 15 years.

## Why nobody does it

C culture has a weird gap. Everyone agrees strict warnings catch bugs, but almost
nobody turns on `-Weverything -Werror`. It's painful to maintain — warnings from
system headers, false positives, breakage on compiler upgrades. So people settle
for `-Wall -Wextra` at best, which misses a lot.

Rust made strictness non-optional. Borrow checker, exhaustive matches, no implicit
conversions — it's the strict C checker people wanted, baked into the language so
you can't skip it. That's the whole pitch: "what if the compiler just wouldn't let
you ship the bug."

You can do the same in C. `-Weverything -Werror` as a parallel gatekeeper that
blocks the build. Same philosophy as Rust, enforced by the build script instead of
the language.

## It pays for itself day one

Turn it on. Fix the 20 warnings. At least a couple are real bugs you didn't know
about: implicit sign conversion hiding a negative-goes-huge, unused result from a
function that returns an error code, implicit fallthrough in a switch. Stuff that
"works" until it doesn't.

Every day after that it's free. New code just has to not introduce new warnings.
That's 30 seconds of fixing at write time vs hours debugging a subtle memory issue
at runtime.

## Agents make it even more valuable

AI agents generate a lot of code fast and don't have intuition about what "looks
sketchy." The strict compiler is the intuition. It catches the classes of bugs that
agents are most likely to introduce — implicit conversions, unused results, type
mismatches — at compile time, before the code ever runs.

The agent writes code, the checker proves it's clean, the build proceeds. No human
in the loop for the mechanical part. That's the whole point.

## Failed install is a dev bug, not a user problem

Most projects ship a README with 15 steps and if step 7 fails it's "check your
PATH" or "open an issue." The install broke but the developer considers it the
user's problem.

The install should be code, not documentation. Detect the OS, install missing deps,
set up shell functions, create symlinks, handle platform quirks, fall back
gracefully — and if something fails, tell the user exactly what to do. If the
install breaks, that's a bug to fix in the install code, not a support ticket.

Same philosophy as the strict compiler. Don't hope things work — prove they work.
If they don't, fix the code, not the docs.

## Only fix what breaks in front of you

If you identify 10 theoretical issues every turn, and nothing forces you to pick
one, you do 10x the work. Each "preventive fix" can introduce its own bug, creating
more theoretical issues, compounding in the wrong direction. One real bug that breaks
in front of you has a 100% hit rate. Ten theoretical bugs have maybe 10-20% each.
You do 10x the work for 1-2x the value. The discipline is saying no to the other 9.

## Two filters that collapse infinity

"Improve my code" is unbounded. An LLM will happily generate infinite refactors,
add error handling for impossible cases, write docstrings for self-evident code,
abstract one-time operations. Each looks productive in isolation. None of it moves
anything forward. You could have a million items of work and never get anything
useful. The compiler and the human are the only two filters that collapse infinity
into a finite list. The compiler says "this is provably wrong." The human says "this
broke in front of me." Everything else is make-work disguised as progress.

## Terminal is the tightest feedback loop

The bottleneck isn't the LLM — it's the time from fix to verified. Compile time,
run time, and verification time compound across every iteration of every agent on
every fix. What matters is the total round-trip: write → build → run → see result.
C compiles in milliseconds and runs in microseconds. Python starts instantly but
runs slower. The real metric is total cycle time, not any single phase.

Terminal development is the tightest possible loop because there's zero abstraction
between the agent and the system. No IDE, no GUI, no API wrapper. The agent runs the
same commands the human runs, sees the same output, hits the same errors. That's why
agents must test with `command a`, not `./a` — the agent has to experience the real
path, not a shortcut that hides the bug. The closer the agent's experience matches
the user's, the faster the loop closes. Terminal agents are the natural evolution
of AI on Unix: the shell is the universal interface that both humans and agents
speak natively.

## Abstraction cost vs frequency

`a` is 1 token. `./a` is 3-4. Across thousands of agent invocations that's real
cost — generation time, attention, error surface. The `./` prefix is meaningless
noise to the intent. The abstraction layers (shell function, symlink, path
resolution) exist to collapse a full path into `a`. The cost is paid once at
install, the savings compound on every invocation forever. But there's a threshold:
if the abstraction makes the command longer or harder to reason about, it's negative
value. Short command, high frequency = abstraction wins. Long command, low frequency
= just type it.

## The trick

`-Weverything` with `-Werror`. That's it. Treat warnings as bugs. The tooling has
been there since 2010. The only thing missing was the willingness to use it.
