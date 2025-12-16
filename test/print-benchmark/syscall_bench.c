#include <stdio.h>
#include <unistd.h>
#include <time.h>
#include <string.h>

int main() {
    const char *msg = "Hello, World!\n";
    int len = 14;
    int runs = 1000;
    struct timespec start, end;
    long total_ns = 0;
    long min_ns = 999999999;
    long max_ns = 0;

    // Warmup
    for (int i = 0; i < 10; i++) {
        write(1, msg, len);
    }

    // Redirect stdout to /dev/null for timing
    freopen("/dev/null", "w", stdout);

    // Benchmark
    for (int i = 0; i < runs; i++) {
        clock_gettime(CLOCK_MONOTONIC, &start);
        write(1, msg, len);
        clock_gettime(CLOCK_MONOTONIC, &end);

        long ns = (end.tv_sec - start.tv_sec) * 1000000000L + (end.tv_nsec - start.tv_nsec);
        total_ns += ns;
        if (ns < min_ns) min_ns = ns;
        if (ns > max_ns) max_ns = ns;
    }

    // Report to stderr
    fprintf(stderr, "\n=== write() syscall benchmark ===\n");
    fprintf(stderr, "Runs: %d\n", runs);
    fprintf(stderr, "Min:  %ld ns (%.3f ms)\n", min_ns, min_ns / 1000000.0);
    fprintf(stderr, "Max:  %ld ns (%.3f ms)\n", max_ns, max_ns / 1000000.0);
    fprintf(stderr, "Avg:  %ld ns (%.3f ms)\n", total_ns / runs, (total_ns / runs) / 1000000.0);
    fprintf(stderr, "Total: %ld ns (%.3f ms)\n", total_ns, total_ns / 1000000.0);

    return 0;
}
