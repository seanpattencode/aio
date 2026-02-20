/* ═══ TMUX HELPERS ═══ */
static int tm_has(const char *s) {
    char c[B]; snprintf(c, B, "timeout 2 tmux has-session -t '%s' 2>/dev/null", s);
    int r = system(c);
    if (r != -1 && WIFEXITED(r) && WEXITSTATUS(r) == 124) {
        /* server unresponsive (stuck at 100% CPU = tmux bug) — kill + retry */
        (void)!system("tmux kill-server 2>/dev/null");
        usleep(200000);
        return system(c) == 0;
    }
    return r == 0;
}

static void tm_go(const char *s) {
    perf_disarm(); /* interactive session — no timeout */
    if (getenv("TMUX")) execlp("tmux", "tmux", "switch-client", "-t", s, (char*)NULL);
    else execlp("tmux", "tmux", "attach", "-t", s, (char*)NULL);
}

static int tm_new(const char *s, const char *wd, const char *cmd) {
    char c[B*2];
    if (cmd && cmd[0]) snprintf(c, sizeof(c), "tmux new-session -d -s '%s' -c '%s' '%s'", s, wd, cmd);
    else snprintf(c, sizeof(c), "tmux new-session -d -s '%s' -c '%s'", s, wd);
    return system(c);
}

static void tm_send(const char *s, const char *text) {
    /* Use tmux send-keys -l for literal text */
    pid_t p = fork();
    if (p == 0) { execlp("tmux", "tmux", "send-keys", "-l", "-t", s, text, (char*)NULL); _exit(1); }
    if (p > 0) waitpid(p, NULL, 0);
}
