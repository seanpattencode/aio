# Compressed C vs Python

Porting ssh.py (91 lines) to C resulted in -1281 net tokens despite adding features (mux, parallel fork, ConnectTimeout). Common belief is C is always more verbose than Python. This is wrong for compressed C.

Normal C vs Python — Python wins. Compressed C vs Python — C wins. The difference: most people compare enterprise C (malloc checks, verbose error handling, header boilerplate) against Python's concise stdlib. Compressed C that leans on `system()`/`snprintf()`/`pcmd()` is shell scripting with C control flow at zero startup cost.

What compressed C does better:
- `fork()`+`pipe()` parallel SSH in ~12 lines vs Python's ThreadPoolExecutor + argument list building
- `execl()` for zero-overhead process replacement vs `os.execvp` with list construction
- `#define` for compile-time string concatenation vs runtime string formatting
- `snprintf` format strings vs f-string + list concatenation

What Python pays that C doesn't:
- Import/runtime init overhead
- Verbose subprocess argument list construction (`['ssh', '-o', 'ConnectTimeout=5', ...]`)
- String building for shell commands is longer than C format strings
- ThreadPoolExecutor boilerplate for what C does with fork()

The convergence: compressed C approaches shell scripting density while retaining type safety, native speed, and syscall access. The gap people imagine between C and Python assumes you're writing C the way textbooks teach it.
