/* ═══ GIT HELPERS ═══ */
static int git_in_repo(const char *p) {
    char c[P]; snprintf(c, P, "%s/.git", p); return dexists(c)||fexists(c);
}

/* ═══ ADATA SETUP ═══ */
static void ensure_adata(void) {
    char c[B], out[512];
    if (!git_in_repo(SROOT)) {
        /* Clone adata/git if missing */
        snprintf(c, B, "command -v gh >/dev/null 2>&1 && gh repo clone seanpattencode/a-git '%s' 2>/dev/null", SROOT);
        if (system(c) == 0) {
            printf("\xe2\x9c\x93 Cloned adata/git\n"); return;
        }
        /* Fallback: init empty repo so sync_repo can work */
        mkdirp(SROOT);
        snprintf(c, B, "git -C '%s' init -q 2>/dev/null && git -C '%s' checkout -b main 2>/dev/null", SROOT, SROOT);
        (void)!system(c);
        printf("\xe2\x9c\x93 Initialized adata/git (gh auth login to enable sync)\n");
        return;
    }
    /* Repo exists — ensure it has the right remote */
    snprintf(c, B, "git -C '%s' remote get-url origin 2>/dev/null", SROOT);
    pcmd(c, out, sizeof(out)); out[strcspn(out, "\n")] = 0;
    if (!out[0]) {
        /* No remote — try to add one if gh is authed */
        snprintf(c, B, "command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1"
            " && git -C '%s' remote add origin https://github.com/seanpattencode/a-git.git 2>/dev/null", SROOT);
        if (system(c) == 0) printf("\xe2\x9c\x93 Added remote to adata/git\n");
    } else if (!strstr(out, "a-git")) {
        /* Wrong remote — fix it */
        snprintf(c, B, "git -C '%s' remote set-url origin https://github.com/seanpattencode/a-git.git", SROOT);
        (void)!system(c);
        printf("\xe2\x9c\x93 Fixed adata/git remote\n");
    }
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
