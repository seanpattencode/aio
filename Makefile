# clang: 0.34s compile, 67KB binary
# sqlite3 loaded via dlopen on first use (saves ~0.5ms for non-db commands)
CC = clang
CFLAGS = -O2 -Wall -Wextra -Wno-unused-parameter -Wno-unused-result
LDFLAGS = -ldl
comma := ,

a: a.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f a

.PHONY: clean
