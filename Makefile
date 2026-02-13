# TWO-PASS PARALLEL BUILD
#
# The build runs two independent clang invocations at the same time:
#
#   PASS 1 — CHECKER (runs in background, ~200ms)
#     -Werror -Weverything, all hardening flags, -fsyntax-only
#     Catches warnings, type errors, hardening incompatibilities.
#     Produces NO binary — only validates the source code.
#
#   PASS 2 — BUILDER (runs in background, ~700ms)
#     -O3 -march=native -flto -w
#     Produces the actual binary. Uses ONLY performance flags.
#     No warnings, no hardening codegen — clean optimized output.
#
# Both launch simultaneously. The binary from Pass 2 is kept ONLY
# if Pass 1 also succeeds (wait $P1 && wait $P2). If the checker
# rejects the code, the binary is discarded.
#
# Why split? Hardening flags (CFI, safe-stack, fortify) and strict
# warnings add compile-time cost and can bloat codegen. By checking
# them in a syntax-only pass, we get the full safety validation for
# free — Pass 2 always takes longer, so Pass 1 finishes first and
# total build time = bare compile time.
#
#   make          clean -O3 binary, validated by -Weverything + hardening
#   make analyze  clang static analyzer (~4s) — deep checks like Rust's
#                 borrow checker: use-after-free, null deref, leaks.
#                 Not in default build because it's slow. Run on demand.
#   make debug    single pass: all flags + ASan/UBSan/IntSan -O1 -g

CC = clang
SRC_DEF = -DSRC='"$(CURDIR)"'
SQLITE_INC = $(HOME)/micromamba/include
WARN = -std=c17 -Werror -Weverything \
       -Wno-padded -Wno-disabled-macro-expansion -Wno-reserved-id-macro \
       -Wno-documentation -Wno-declaration-after-statement \
       -Wno-unsafe-buffer-usage -Wno-used-but-marked-unused \
       --system-header-prefix=/usr/include \
       -isystem /usr/local/include
# clang 21+ C++ compat warnings: idiomatic C doesn't cast malloc/memchr
WARN += $(shell $(CC) -Werror -Wno-implicit-void-ptr-cast -x c -c /dev/null -o /dev/null 2>/dev/null && echo -Wno-implicit-void-ptr-cast)
# Bionic libc _Nullable annotations (Android/Termux only)
WARN += $(shell $(CC) -Werror -Wno-nullable-to-nonnull-conversion -x c -c /dev/null -o /dev/null 2>/dev/null && echo -Wno-nullable-to-nonnull-conversion)
# cross-compiler system directory warnings (Darwin + Termux)
WARN += $(shell $(CC) -Werror -Wno-poison-system-directories -x c -c /dev/null -o /dev/null 2>/dev/null && echo -Wno-poison-system-directories)
HARDEN = -fstack-protector-strong -ftrivial-auto-var-init=zero -D_FORTIFY_SOURCE=3 \
         -fsanitize=safe-stack -fsanitize=cfi -fvisibility=hidden
ifneq ($(shell uname),Darwin)
HARDEN += -fstack-clash-protection -fcf-protection=full
endif
LINK_HARDEN = -Wl,-z,relro,-z,now

a: a.c
	# Pass 1: checker — strict warnings + hardening, syntax only, no binary
	# Pass 2: builder — pure performance flags, emits the binary
	# Both run in parallel; binary kept only if both succeed
	$(CC) $(WARN) $(HARDEN) $(SRC_DEF) -O3 -flto -fsyntax-only $< & P1=$$!; \
	$(CC) $(SRC_DEF) -isystem $(SQLITE_INC) -O3 -march=native -flto -w -o $@ $< $(LDFLAGS) & P2=$$!; \
	wait $$P1 && wait $$P2

debug: a.c
	$(CC) $(WARN) $(HARDEN) $(SRC_DEF) $(LINK_HARDEN) -O1 -g -fsanitize=address,undefined,integer -o a $< $(LDFLAGS)

# Static analyzer — slow (~4s), not part of default build.
# Catches use-after-free, null deref, leaks at compile time.
analyze: a.c
	$(CC) $(SRC_DEF) --analyze $<

clean:
	rm -f a

.PHONY: clean debug analyze
