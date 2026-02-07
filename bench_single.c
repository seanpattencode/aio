/*
 * Benchmark: real end-to-end latency of a single `a <cmd>` invocation.
 *
 * Unlike bench_dispatch.c / bench_real.c which measure dispatch overhead
 * in tight loops (ns-scale), this measures what the user actually feels:
 * fork + exec + init_paths + dispatch + command + exit (ms-scale).
 *
 * Build & run:
 *   cc -O2 -o bench_single bench_single.c && ./bench_single
 *   (requires ./a binary in same directory)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include <time.h>
#include <fcntl.h>

#define WARMUP 2
#define RUNS   10

static double time_cmd(const char *bin, const char *arg) {
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    pid_t pid = fork();
    if (pid == 0) {
        int fd = open("/dev/null", O_WRONLY);
        if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); close(fd); }
        execl(bin, bin, arg, (char *)NULL);
        _exit(127);
    }
    int st;
    waitpid(pid, &st, 0);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    return (t1.tv_sec - t0.tv_sec) * 1e6 + (t1.tv_nsec - t0.tv_nsec) / 1e3;
}

static double bench(const char *bin, const char *cmd) {
    for (int i = 0; i < WARMUP; i++) time_cmd(bin, cmd);
    double total = 0, mn = 1e18, mx = 0;
    for (int i = 0; i < RUNS; i++) {
        double t = time_cmd(bin, cmd);
        total += t;
        if (t < mn) mn = t;
        if (t > mx) mx = t;
    }
    double avg = total / RUNS;
    printf("  %-12s  avg %7.0f us  min %7.0f us  max %7.0f us\n", cmd, avg, mn, mx);
    return avg;
}

int main(void) {
    /* find binary: ./a in current dir */
    const char *bin = "./a";
    if (access(bin, X_OK) != 0) {
        fprintf(stderr, "error: ./a not found (build with `make` first)\n");
        return 1;
    }

    printf("Single-invocation benchmark (%d warmup, %d runs each)\n", WARMUP, RUNS);
    printf("Measures: fork + exec + init + dispatch + cmd + exit\n\n");

    /* fast commands (no I/O beyond init) */
    printf("Fast commands (minimal work):\n");
    double t_help = bench(bin, "help");
    bench(bin, "dir");

    /* commands that read files */
    printf("\nCommands with file I/O:\n");
    bench(bin, "ls");
    bench(bin, "config");

    /* baseline: fork+exec overhead */
    printf("\nBaseline:\n");
    double t_true = time_cmd("/usr/bin/true", NULL);
    /* average over RUNS */
    double true_total = 0;
    for (int i = 0; i < RUNS; i++) true_total += time_cmd("/usr/bin/true", NULL);
    double t_base = true_total / RUNS;
    printf("  %-12s  avg %7.0f us  (fork+exec+exit overhead)\n", "/usr/bin/true", t_base);
    (void)t_true;

    printf("\nOverhead of `a` vs bare fork+exec: %.0f us (%.1fx)\n",
           t_help - t_base, t_help / t_base);
    printf("\nContext: human perception threshold = ~100,000 us (100ms)\n");
    printf("         keyboard-to-screen = ~50,000 us typical\n");

    return 0;
}
