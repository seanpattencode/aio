/*
 * Benchmark: dispatcher overhead vs direct function call
 * Tests 3 approaches:
 *   1. Direct function call (baseline)
 *   2. switch on first char + strcmp (current ac.c hybrid)
 *   3. Binary search on sorted array (current ac.c fallback)
 *   4. Linear scan like git's get_builtin()
 *   5. Giant if-else chain
 */
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <stdlib.h>

#define ITERS 10000000

static int fn_done(void) { return 0; }
static int fn_help(void) { return 0; }
static int fn_push(void) { return 0; }
static int fn_diff(void) { return 0; }
static int fn_config(void) { return 0; }
static int fn_ssh(void) { return 0; }
static int fn_sync(void) { return 0; }
static int fn_task(void) { return 0; }
static int fn_note(void) { return 0; }
static int fn_watch(void) { return 0; }

/* --- Approach 1: direct call --- */
static int direct_call(const char *cmd) {
    (void)cmd;
    return fn_done();
}

/* --- Approach 2: switch on first char + strcmp --- */
static int switch_dispatch(const char *cmd) {
    switch (cmd[0]) {
    case 'c': if (!strcmp(cmd, "config")) return fn_config(); break;
    case 'd': if (!strcmp(cmd, "done")) return fn_done();
              if (!strcmp(cmd, "diff")) return fn_diff(); break;
    case 'h': if (!strcmp(cmd, "help")) return fn_help(); break;
    case 'n': if (!strcmp(cmd, "note")) return fn_note(); break;
    case 'p': if (!strcmp(cmd, "push")) return fn_push(); break;
    case 's': if (!strcmp(cmd, "ssh")) return fn_ssh();
              if (!strcmp(cmd, "sync")) return fn_sync(); break;
    case 't': if (!strcmp(cmd, "task")) return fn_task(); break;
    case 'w': if (!strcmp(cmd, "watch")) return fn_watch(); break;
    }
    return -1;
}

/* --- Approach 3: binary search --- */
typedef int (*cmd_fn)(void);
struct cmd { const char *name; cmd_fn fn; };
static struct cmd cmds[] = {
    {"config", fn_config}, {"diff", fn_diff}, {"done", fn_done},
    {"help", fn_help}, {"note", fn_note}, {"push", fn_push},
    {"ssh", fn_ssh}, {"sync", fn_sync}, {"task", fn_task},
    {"watch", fn_watch},
};
#define NCMDS (sizeof(cmds)/sizeof(cmds[0]))

static int bsearch_dispatch(const char *cmd) {
    int lo = 0, hi = NCMDS - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        int c = strcmp(cmd, cmds[mid].name);
        if (c == 0) return cmds[mid].fn();
        if (c < 0) hi = mid - 1; else lo = mid + 1;
    }
    return -1;
}

/* --- Approach 4: linear scan (git style) --- */
static int linear_dispatch(const char *cmd) {
    for (int i = 0; i < (int)NCMDS; i++)
        if (!strcmp(cmd, cmds[i].name)) return cmds[i].fn();
    return -1;
}

/* --- Approach 5: if-else chain --- */
static int ifelse_dispatch(const char *cmd) {
    if (!strcmp(cmd, "done")) return fn_done();
    if (!strcmp(cmd, "help")) return fn_help();
    if (!strcmp(cmd, "push")) return fn_push();
    if (!strcmp(cmd, "diff")) return fn_diff();
    if (!strcmp(cmd, "config")) return fn_config();
    if (!strcmp(cmd, "ssh")) return fn_ssh();
    if (!strcmp(cmd, "sync")) return fn_sync();
    if (!strcmp(cmd, "task")) return fn_task();
    if (!strcmp(cmd, "note")) return fn_note();
    if (!strcmp(cmd, "watch")) return fn_watch();
    return -1;
}

static double bench(const char *label, int (*fn)(const char*), const char **inputs, int ninputs) {
    struct timespec t0, t1;
    volatile int r = 0;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (int i = 0; i < ITERS; i++)
        r += fn(inputs[i % ninputs]);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    printf("  %-22s %6.1f ns/call  (%d M calls)\n", label, ns / ITERS, ITERS/1000000);
    (void)r;
    return ns / ITERS;
}

int main(void) {
    /* Test with various commands to simulate real usage */
    const char *inputs[] = {"done", "help", "push", "config", "ssh", "task", "watch", "sync", "note", "diff"};
    int n = sizeof(inputs)/sizeof(inputs[0]);

    printf("Dispatch benchmark (%d commands, %dM iterations)\n\n", n, ITERS/1000000);

    double t_direct = bench("direct call", direct_call, inputs, n);
    double t_switch = bench("switch+strcmp (ac.c)", switch_dispatch, inputs, n);
    double t_bsearch = bench("binary search", bsearch_dispatch, inputs, n);
    double t_linear = bench("linear scan (git)", linear_dispatch, inputs, n);
    double t_ifelse = bench("if-else chain", ifelse_dispatch, inputs, n);

    printf("\nOverhead vs direct call:\n");
    printf("  switch+strcmp:  %+.1f ns  (%.1fx)\n", t_switch - t_direct, t_switch/t_direct);
    printf("  binary search: %+.1f ns  (%.1fx)\n", t_bsearch - t_direct, t_bsearch/t_direct);
    printf("  linear (git):  %+.1f ns  (%.1fx)\n", t_linear - t_direct, t_linear/t_direct);
    printf("  if-else:       %+.1f ns  (%.1fx)\n", t_ifelse - t_direct, t_ifelse/t_direct);

    printf("\nContext: a single file read() = ~1,000 ns, fork+exec = ~1,000,000 ns\n");
    printf("         Python startup = ~27,000,000 ns\n");
    return 0;
}
