CC = clang
SQLITE_INC = $(HOME)/micromamba/include
WARN = -std=c17 -Werror -Weverything \
       -Wno-padded -Wno-disabled-macro-expansion -Wno-reserved-id-macro \
       -Wno-documentation -Wno-declaration-after-statement \
       -Wno-unsafe-buffer-usage -Wno-used-but-marked-unused \
       --system-header-prefix=/usr/include \
       -isystem /usr/local/include -isystem $(SQLITE_INC)
HARDEN = -fstack-protector-strong -ftrivial-auto-var-init=zero -D_FORTIFY_SOURCE=2
CFLAGS = $(WARN) $(HARDEN) -O2
SYS_SQLITE = /usr/lib/x86_64-linux-gnu/libsqlite3.so.0
LDFLAGS = $(if $(wildcard $(SYS_SQLITE)),$(SYS_SQLITE),-L$(HOME)/micromamba/lib -lsqlite3 -Wl$(comma)-rpath$(comma)$(HOME)/micromamba/lib)
comma := ,

a: a.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

debug: a.c
	$(CC) $(WARN) $(HARDEN) -O1 -g -fsanitize=address,undefined,integer -o a $< $(LDFLAGS)

clean:
	rm -f a

.PHONY: clean debug
