/* ═══ GIT HELPERS ═══ */
static int git_in_repo(const char *p) {
    char c[P]; snprintf(c, P, "%s/.git", p); return dexists(c);
}

/* ═══ SYNC ═══ */
static void sync_repo(void) {
    char c[B*2];
    snprintf(c, sizeof(c),
        "git -C '%s' add -A 2>/dev/null && git -C '%s' commit -qm sync 2>/dev/null;"
        "git -C '%s' pull --no-rebase --no-edit -q origin main 2>/dev/null;"
        "git -C '%s' push -q origin main 2>/dev/null", SROOT, SROOT, SROOT, SROOT);
    (void)!system(c);
}
static void sync_bg(void) {
    pid_t p=fork();if(p<0)return;if(p>0){waitpid(p,NULL,WNOHANG);return;}
    if(fork()>0)_exit(0);setsid();sync_repo();_exit(0);
}
