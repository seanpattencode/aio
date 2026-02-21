## Amalgamation makes fixes obvious

a.c is a polyglot: shell build script + C program in one file.

When `a-i` (interactive picker daemon) wasn't picking up code changes after
rebuild, the fix was one line: add `a-i --stop` after the compile step. This
was obvious because the compile line and the existing `--stop` pattern (in
`cmd_update`, 70 lines away) were both visible in one read of one file.

With a separate Makefile + source files, you'd need to read three files across
two languages to connect: (1) what gets built, (2) that a-i is a persistent
daemon, (3) that --stop exists. The pattern to copy wouldn't be visible.

Same file = same context = obvious fix. This is why amalgamation works for
both humans and LLMs: fewer files to hold in working memory.
