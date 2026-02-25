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

## The trick

`-Weverything` with `-Werror`. That's it. Treat warnings as bugs. The tooling has
been there since 2010. The only thing missing was the willingness to use it.
