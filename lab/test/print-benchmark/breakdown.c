#include <stdio.h>
#include <unistd.h>
#include <time.h>

// Measure breakdown of process execution time
int main() {
    struct timespec start, after_main, after_write, end;
    const char *msg = "Hello, World!\n";

    clock_gettime(CLOCK_MONOTONIC, &start);

    // Simulate "arrived at main"
    clock_gettime(CLOCK_MONOTONIC, &after_main);

    // Do the write
    write(1, msg, 14);
    clock_gettime(CLOCK_MONOTONIC, &after_write);

    // "Exit" timing
    clock_gettime(CLOCK_MONOTONIC, &end);

    long main_time = (after_main.tv_sec - start.tv_sec) * 1000000000L +
                     (after_main.tv_nsec - start.tv_nsec);
    long write_time = (after_write.tv_sec - after_main.tv_sec) * 1000000000L +
                      (after_write.tv_nsec - after_main.tv_nsec);
    long exit_time = (end.tv_sec - after_write.tv_sec) * 1000000000L +
                     (end.tv_nsec - after_write.tv_nsec);
    long total = (end.tv_sec - start.tv_sec) * 1000000000L +
                 (end.tv_nsec - start.tv_nsec);

    fprintf(stderr, "\n=== In-process timing ===\n");
    fprintf(stderr, "Clock overhead:  %ld ns\n", main_time);
    fprintf(stderr, "write() syscall: %ld ns\n", write_time);
    fprintf(stderr, "Post-write:      %ld ns\n", exit_time);
    fprintf(stderr, "Total in-proc:   %ld ns (%.3f ms)\n", total, total/1000000.0);
    fprintf(stderr, "\nIf full exec = 10ms, process creation = %.2f%%\n",
            (1.0 - (total / 10000000.0)) * 100);

    return 0;
}
