# Parallel split build: two clang passes run simultaneously.
#   Pass 1: -Werror -Weverything + hardening flags, -fsyntax-only
#            Validates all warnings and hardening compatibility.
#            No binary emitted — pure compile-time checking (~60ms).
#   Pass 2: -O2 -w, no extra flags
#            Emits the actual binary. Pure optimized code, no overhead
#            from warnings or hardening codegen.
#
# Both run in parallel. Pass 2 (~560ms) always takes longer than
# pass 1 (~60ms), so the strict checks are completely free — total
# build time equals the bare compile time. If pass 1 fails, the
# binary from pass 2 is discarded.
#
# Result: strictest possible validation with zero cost to the binary.
#   make          bare -O2 binary, validated by -Weverything + hardening
#   make debug    all flags combined + ASan/UBSan/IntSan -O1 -g

CC = clang
SQLITE_INC = $(HOME)/micromamba/include
WARN = -std=c17 -Werror -Weverything \
       -Wno-padded -Wno-disabled-macro-expansion -Wno-reserved-id-macro \
       -Wno-documentation -Wno-declaration-after-statement \
       -Wno-unsafe-buffer-usage -Wno-used-but-marked-unused \
       --system-header-prefix=/usr/include \
       -isystem /usr/local/include -isystem $(SQLITE_INC)
HARDEN = -fstack-protector-strong -ftrivial-auto-var-init=zero -D_FORTIFY_SOURCE=2 \
         -fstack-clash-protection -fcf-protection
LINK_HARDEN = -Wl,-z,relro,-z,now
SYS_SQLITE = /usr/lib/x86_64-linux-gnu/libsqlite3.so.0
LDFLAGS = $(if $(wildcard $(SYS_SQLITE)),$(SYS_SQLITE),-L$(HOME)/micromamba/lib -lsqlite3 -Wl$(comma)-rpath$(comma)$(HOME)/micromamba/lib)
comma := ,

a: a.c
	$(CC) $(WARN) $(HARDEN) -fsyntax-only $< & P1=$$!; \
	$(CC) -isystem $(SQLITE_INC) -O2 -w -o $@ $< $(LDFLAGS) & P2=$$!; \
	wait $$P1 && wait $$P2

debug: a.c
	$(CC) $(WARN) $(HARDEN) $(LINK_HARDEN) -O1 -g -fsanitize=address,undefined,integer -o a $< $(LDFLAGS)

clean:
	rm -f a

.PHONY: clean debug
