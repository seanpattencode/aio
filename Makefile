# clang: 0.34s compile, 67KB binary
# system sqlite3 (no ICU) = 2.5ms startup; micromamba sqlite3 (ICU) = 3.5ms
CC = clang
SQLITE_INC = $(HOME)/micromamba/include
CFLAGS = -std=c17 -O2 -Werror -Weverything \
         -Wno-padded -Wno-disabled-macro-expansion -Wno-reserved-id-macro \
         -Wno-documentation -Wno-declaration-after-statement \
         -Wno-unsafe-buffer-usage \
         --system-header-prefix=/usr/include \
         -isystem /usr/local/include -isystem $(SQLITE_INC)
SYS_SQLITE = /usr/lib/x86_64-linux-gnu/libsqlite3.so.0
LDFLAGS = $(if $(wildcard $(SYS_SQLITE)),$(SYS_SQLITE),-L$(HOME)/micromamba/lib -lsqlite3 -Wl$(comma)-rpath$(comma)$(HOME)/micromamba/lib)
comma := ,

a: a.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f a

.PHONY: clean
