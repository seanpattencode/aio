# clang: 0.34s compile, 67KB binary
# gcc:   0.53s compile, 70KB binary
# runtime identical — dominated by process startup, not codegen
CC = clang
SQLITE_INC = $(HOME)/micromamba/include
SQLITE_LIB = $(HOME)/micromamba/lib
CFLAGS = -O2 -Wall -Wextra -Wno-unused-parameter -Wno-unused-result -I$(SQLITE_INC)
LDFLAGS = -L$(SQLITE_LIB) -lsqlite3 -Wl,-rpath,$(SQLITE_LIB)

a: a.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f a

.PHONY: clean
