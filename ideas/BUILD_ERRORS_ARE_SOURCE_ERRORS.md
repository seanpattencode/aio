# Build Errors Are Source Errors

If something prevents a.c from building, the fix belongs in a.c.

It doesn't matter if the root cause is the compiler, the OS, the terminal,
or an AI agent's sandbox. If it blocks the build, it's a.c's problem.

The source file is the single source of truth. Workarounds, env quirks,
platform-specific notes — they go in the file that fails to build.
That way whoever hits the issue next (human or agent) finds the answer
exactly where they need it.

One file. Zero external docs to hunt down.
