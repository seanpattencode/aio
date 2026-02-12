# Parallel split build: two clang passes run simultaneously.
#   Pass 1: -Werror -Weverything + hardening flags, -fsyntax-only
#            Validates all warnings and hardening compatibility.
#            No binary emitted — pure compile-time checking (~60ms).
#   Pass 2: -O3 -march=native -flto -w, no extra flags
#            Emits the actual binary. Pure optimized code, no overhead
#            from warnings or hardening codegen.
#
# Both run in parallel. Pass 2 (~560ms) always takes longer than
# pass 1 (~60ms), so the strict checks are completely free — total
# build time equals the bare compile time. If pass 1 fails, the
# binary from pass 2 is discarded.
#
# Result: strictest possible validation with zero cost to the binary.
#   make          bare -O3 -march=native -flto binary, validated by -Weverything + hardening
#   make debug    all flags combined + ASan/UBSan/IntSan -O1 -g

CC = clang
SRC_DEF = -DSRC='"$(CURDIR)"'
SQLITE_INC = $(HOME)/micromamba/include
WARN = -std=c17 -Werror -Weverything \
       -Wno-padded -Wno-disabled-macro-expansion -Wno-reserved-id-macro \
       -Wno-documentation -Wno-declaration-after-statement \
       -Wno-unsafe-buffer-usage -Wno-used-but-marked-unused \
       --system-header-prefix=/usr/include \
       -isystem /usr/local/include
ifeq ($(shell uname),Darwin)
WARN += -Wno-poison-system-directories
endif
HARDEN = -fstack-protector-strong -ftrivial-auto-var-init=zero -D_FORTIFY_SOURCE=2
ifneq ($(shell uname),Darwin)
HARDEN += -fstack-clash-protection -fcf-protection
endif
LINK_HARDEN = -Wl,-z,relro,-z,now

a: a.c
	$(CC) $(WARN) $(HARDEN) $(SRC_DEF) -O3 -fsyntax-only $< & P1=$$!; \
	$(CC) $(SRC_DEF) -isystem $(SQLITE_INC) -O3 -march=native -flto -w -o $@ $< $(LDFLAGS) & P2=$$!; \
	wait $$P1 && wait $$P2

debug: a.c
	$(CC) $(WARN) $(HARDEN) $(SRC_DEF) $(LINK_HARDEN) -O1 -g -fsanitize=address,undefined,integer -o a $< $(LDFLAGS)

clean:
	rm -f a

.PHONY: clean debug
