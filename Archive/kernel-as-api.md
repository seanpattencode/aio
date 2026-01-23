# The Kernel is a Better API

One of the few APIs that is Turing complete.

| Property | Kernel (syscalls) | Typical "Modern" APIs |
|----------|-------------------|----------------------|
| Stability | 30+ years backward compat | Breaking changes every major version |
| Turing complete | Yes (fork/exec + pipes + files) | Usually no (REST? GraphQL? No computation) |
| State | Filesystem, memory, processes | "Call our endpoint, hope server is up" |
| Composition | Pipes, signals, shared memory | SDK du jour, dependency hell |
| Docs | man pages, never move | Link rot, paywalls, deprecated tutorials |
| Auth | File permissions, uid/gid | OAuth flows, API keys, token refresh |
| Latency | Microseconds | Milliseconds to seconds (network) |
| Failure modes | Predictable (errno) | Timeout? Rate limit? 500? Who knows |

## Why devs avoid it

- Abstraction addiction ("I need a library for that")
- Fear of C/pointers (even though Python's `os` module exposes it all)
- Cargo culting ("nobody does it that way anymore")
- Tutorials start at HTTP, never go down

## What you get by embracing it

- `fork()` is a better job queue than Redis
- `inotify` is a better file watcher than any npm package
- `mmap` is a better shared cache than most databases
- Unix sockets are faster than localhost HTTP
- Pipes are the original streaming API

## aio's approach

Uses: sqlite (file), subprocess (fork/exec), tmux (pty/pipes), signals. No web server needed for local tool.
