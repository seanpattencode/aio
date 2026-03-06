#if 0
#!/bin/sh
set -e

echo "=== System Check ==="
tcc -v || echo "TCC not found"
clang --version | head -n 1 || echo "Clang not found"

echo "\n=== 1. TCC Interpreter/Script Mode (-run) ==="
# -run compiles instantly to memory and executes it.
# We time the entire process: compilation + execution
/usr/bin/time -p tcc -run "$0" bench

echo "\n=== 2. TCC Compile to Disk then Execute ==="
/usr/bin/time -p tcc -o bench_tcc "$0"
/usr/bin/time -p ./bench_tcc bench
rm -f bench_tcc

echo "\n=== 3. Clang (-O0) Compile then Execute ==="
/usr/bin/time -p clang -O0 -o bench_clang0 "$0"
/usr/bin/time -p ./bench_clang0 bench
rm -f bench_clang0

echo "\n=== 4. Clang (-O3) Compile then Execute ==="
/usr/bin/time -p clang -O3 -o bench_clang3 "$0"
/usr/bin/time -p ./bench_clang3 bench
rm -f bench_clang3

exit 0
#endif

#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    if (argc < 2) return 0;
    
    // A simple compute-bound loop to show the difference between
    // TCC's unoptimized machine code vs Clang's highly optimized code
    unsigned long sum = 0;
    for (unsigned long i = 0; i < 1000000000; i++) {
        sum += i;
        // Prevent complete dead-code elimination in -O3 without making it too complex
        if (sum % 1000000007 == 0) {
            sum ^= i;
        }
    }
    
    printf("Computed Sum: %lu\n", sum);
    return 0;
}
