# Flat Architecture: Everything Is a File, Every Command Is a File

## Original design note

> I am considering keeping it flat to make it super modular. I want to be able to
> have the system be made up of flat hierarchy independent units. It would possibly
> support drag drop in future for adding files as commands. Everything is a file >
> every command is a file > the script you have is the program just stick it in >
> universal compatibility with more software than anyone else in world.

## The principle

A program is a flat directory of files. Each file is a command. The extension is
the language. Adding a command is copying a file in. Removing a command is deleting
a file. No registration, no imports, no build config, no framework.

```
lib/
  push.c        ← push command (C)
  push.py       ← push command (Python)
  ssh.c         ← ssh command (C)
  jobs.py       ← jobs command (Python only)
  util.c        ← shared infrastructure
  a.h           ← shared types
```

The concatenation script assembles C files into a single `a.c` amalgamation (like
SQLite's `sqlite3.c`). Python dispatches by filename. Each language's toolchain
touches only its own files. Future languages (Rust, Go, Shell) slot in with zero
structural changes.

## Independence and bootability

Every component must fight to stay alive by its own merit of value.

**Bootability** = the ability to reject any component. If a file can be deleted and
the system still builds and runs (with that one feature missing), the architecture
is correct. If deleting one file breaks unrelated commands, the architecture has
coupling that must be removed.

This means:
- **No hidden dependencies.** A command file depends on infrastructure (util, kv,
  tmux helpers) and nothing else. Commands never depend on other commands.
- **No registration.** The dispatch table in `main.c` and the concatenation script
  are the only places that know about commands. Remove a file, remove its line
  from dispatch — done.
- **No framework lock-in.** Files don't inherit from base classes, don't implement
  interfaces, don't register with a plugin system. They're just functions.
- **Natural selection.** If a command isn't useful, delete it. If a better
  implementation exists in a different language, replace it. The file is the unit
  of competition. Bad code doesn't hide inside abstractions — it sits in a file
  with its name on it, accountable.

The test: can someone who has never seen the project understand the structure by
running `ls`? Can they add a command by copying a file? Can they remove one by
deleting? If yes, the architecture is right.

## Why flat beats nested

Nested hierarchies (`src/commands/git/push.c`) create:
- **Navigation tax.** You pay `cd` costs to find anything.
- **Artificial grouping.** Is `push` a "git command" or a "sync command"? The
  hierarchy forces a single taxonomy. Flat doesn't.
- **Coupling pressure.** Directories encourage shared state within the group.
  Files in `commands/git/` start sharing `git_common.h`. Now you can't move
  `push` without breaking `pull`. Flat prevents this — shared code lives in
  named infrastructure files that everything can use equally.
- **Tool incompatibility.** Many tools (file managers, sync, drag-drop, mobile
  file browsers) handle flat directories naturally. Nested structures require
  tree-aware tools.

## Universal compatibility

A flat directory of files is compatible with:
- Every file manager (GUI drag-and-drop works)
- Every sync tool (rsync, rclone, git, Dropbox)
- Every editor and IDE
- Every operating system
- Every build system
- Every programming language's import/include mechanism
- Every CI/CD system
- Mobile file browsers
- Non-programmers ("each file is a command")

No other source structure can make this claim. Nested directories, monorepos,
plugin registries, package manifests — all require tool-specific knowledge.
A flat directory requires only `ls`.

## Precedent

- **Plan 9 `/bin/`** — flat, one binary per command, no subdirectories
- **CGI-bin** — drop a script in, it's a web endpoint
- **`/etc/init.d/`** — each service is a file
- **`/usr/bin/`** — thousands of commands, flat, works fine
- **SQLite amalgamation** — many source files concatenated into one, distributed
  as a single file
- **Unix philosophy** — small programs that do one thing, composed via pipes

## How it works for `a`

The C side: individual `.c` files get concatenated by `mka.sh` into a single
`a.c` amalgamation. The Makefile builds `a.c` as one translation unit (like
SQLite). All functions are `static`, all in one binary — maximum optimization,
zero linking overhead.

The Python side: `a.py` dispatches by filename. `import push` loads `push.py`.

The boundary: C is the fast path (the compiled binary handles most commands).
Python is the fallback for commands not yet ported or that benefit from Python
libraries. Both coexist in the same flat directory, distinguished only by
extension.

Adding a new command in any language:
1. Write `mycommand.py` (or `.c`, `.sh`, `.rs`)
2. Drop it in `lib/`
3. Add one dispatch line
4. Done

Removing:
1. Delete the file
2. Remove the dispatch line
3. Done

No other system is this simple.
