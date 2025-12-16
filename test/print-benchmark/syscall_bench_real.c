#include <stdio.h>
#include <unistd.h>
#include <time.h>
#include <fcntl.h>

int main() {
    const char *msg = "Hello, World!\n";
    int len = 14;
    int runs = 100;
    struct timespec start, end;
    long times[100];

    // Test 1: /dev/null (no I/O)
    int null_fd = open("/dev/null", O_WRONLY);
    for (int i = 0; i < runs; i++) {
        clock_gettime(CLOCK_MONOTONIC, &start);
        write(null_fd, msg, len);
        clock_gettime(CLOCK_MONOTONIC, &end);
        times[i] = (end.tv_sec - start.tv_sec) * 1000000000L + (end.tv_nsec - start.tv_nsec);
    }
    close(null_fd);

    long min1 = times[0], sum1 = 0;
    for (int i = 0; i < runs; i++) {
        if (times[i] < min1) min1 = times[i];
        sum1 += times[i];
    }

    // Test 2: real TTY (stdout)
    // Redirect to temp, measure, restore
    for (int i = 0; i < runs; i++) {
        clock_gettime(CLOCK_MONOTONIC, &start);
        write(2, msg, len);  // stderr = real TTY
        clock_gettime(CLOCK_MONOTONIC, &end);
        times[i] = (end.tv_sec - start.tv_sec) * 1000000000L + (end.tv_nsec - start.tv_nsec);
    }

    long min2 = times[0], sum2 = 0;
    for (int i = 0; i < runs; i++) {
        if (times[i] < min2) min2 = times[i];
        sum2 += times[i];
    }

    fprintf(stderr, "\n=== Syscall Floor Analysis ===\n");
    fprintf(stderr, "/dev/null: min=%ld ns, avg=%ld ns\n", min1, sum1/runs);
    fprintf(stderr, "Real TTY:  min=%ld ns, avg=%ld ns\n", min2, sum2/runs);
    fprintf(stderr, "TTY overhead: ~%ld ns\n", (sum2/runs) - (sum1/runs));

    return 0;
}
