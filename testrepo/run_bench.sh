#!/bin/sh
set -e

# Build the binary using various compilers
tcc -o bench_tcc testrepo/speed_bench.c
clang -O0 -o bench_clang0 testrepo/speed_bench.c
clang -O3 -o bench_clang3 testrepo/speed_bench.c

echo "\n=== 1. TCC Interpreter/Script Mode (-run) ==="
/usr/bin/time -p tcc -run testrepo/speed_bench.c bench

echo "\n=== 2. TCC Compiled Binary Execution ==="
/usr/bin/time -p ./bench_tcc bench

echo "\n=== 3. Clang (-O0) Compiled Binary Execution ==="
/usr/bin/time -p ./bench_clang0 bench

echo "\n=== 4. Clang (-O3) Compiled Binary Execution ==="
/usr/bin/time -p ./bench_clang3 bench

rm -f bench_tcc bench_clang0 bench_clang3
