#!/bin/bash
# Benchmark build time, binary size, and runtime across optimization levels
cd "$(dirname "$0")/.." || exit 1
SQLITE_INC="$HOME/micromamba/include"
LDFLAGS="-L$HOME/micromamba/lib -lsqlite3 -Wl,-rpath,$HOME/micromamba/lib"
SRCDEF="-DSRC=\"\\\"$PWD\\\"\""
N=200

printf "%-28s %8s %8s %10s\n" "flags" "build" "size" "${N}runs"
printf "%-28s %8s %8s %10s\n" "-----" "-----" "----" "------"

for OPT in "-O1" "-O2" "-O3 -march=native -flto"; do
	rm -f a_bench
	BUILD=$( { TIMEFORMAT='%3R'; time clang "$SRCDEF" -isystem "$SQLITE_INC" $OPT -w -o a_bench a.c $LDFLAGS; } 2>&1 )
	SIZE=$(stat -c%s a_bench)
	# warm
	for i in 1 2 3; do ./a_bench >/dev/null 2>&1; done
	RUN=$( { TIMEFORMAT='%3R'; time for i in $(seq 1 $N); do ./a_bench >/dev/null 2>&1; done; } 2>&1 )
	printf "%-28s %7ss %7s %9ss\n" "$OPT" "$BUILD" "$SIZE" "$RUN"
	rm -f a_bench
done
