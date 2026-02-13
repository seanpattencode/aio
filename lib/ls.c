/* ── ls ── */
static int cmd_ls(int argc, char **argv) {
    if (argc > 2 && argv[2][0] >= '0' && argv[2][0] <= '9') {
        /* Attach by number */
        char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
        char *lines[64]; int n = 0; char *p = out;
        while (*p && n < 64) { lines[n++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
        int idx = atoi(argv[2]);
        if (idx >= 0 && idx < n) tm_go(lines[idx]);
        return 0;
    }
    char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
    if (!out[0]) { puts("No sessions"); return 0; }
    char *p = out; int i = 0;
    while (*p) {
        char *e = strchr(p, '\n'); if (e) *e = 0;
        if (*p) {
            char c[B], path[512] = "";
            snprintf(c, B, "tmux display-message -p -t '%s' '#{pane_current_path}' 2>/dev/null", p);
            pcmd(c, path, 512); path[strcspn(path,"\n")] = 0;
            printf("  %d  %s: %s\n", i++, p, path);
        }
        if (e) p = e + 1; else break;
    }
    puts("\nSelect:\n  a ls 0"); return 0;
}

/* ── kill ── */
static int cmd_kill(int argc, char **argv) {
    const char *sel = argc > 2 ? argv[2] : NULL;
    if ((sel && !strcmp(sel, "all")) || (argc > 1 && !strcmp(argv[1], "killall"))) {
        (void)!system("pkill -9 -f tmux 2>/dev/null"); (void)!system("clear");
        puts("\xe2\x9c\x93"); return 0;
    }
    char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
    char *lines[64]; int n = 0; char *p = out;
    while (*p && n < 64) { lines[n++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
    if (!n) { puts("No sessions"); return 0; }
    if (sel && sel[0] >= '0' && sel[0] <= '9') {
        int idx = atoi(sel);
        if (idx >= 0 && idx < n) {
            char c[B]; snprintf(c, B, "tmux kill-session -t '%s'", lines[idx]); (void)!system(c);
            printf("\xe2\x9c\x93 %s\n", lines[idx]); return 0;
        }
    }
    for (int i = 0; i < n; i++) printf("  %d  %s\n", i, lines[i]);
    puts("\nSelect:\n  a kill 0\n  a kill all"); return 0;
}

/* ── copy ── */
static int cmd_copy(int argc, char **argv) { (void)argc;(void)argv;
    if (!getenv("TMUX")) { puts("x Not in tmux"); return 1; }
    (void)!system("tmux capture-pane -pJ -S -99 > /tmp/ac_copy.tmp");
    /* Simplified: copy last output block */
    char *d = readf("/tmp/ac_copy.tmp", NULL);
    if (!d) return 1;
    /* Find last prompt line (contains $ and @) */
    char *lines[1024]; int nl = 0; char *p = d;
    while (*p && nl < 1024) { lines[nl++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
    int last_prompt = -1;
    for (int i = nl - 1; i >= 0; i--)
        if (strstr(lines[i], "$") && strstr(lines[i], "@")) {
            if (strstr(lines[i], "copy")) { last_prompt = i; continue; }
            /* Find output between this prompt and the 'copy' prompt */
            char out[B]=""; int ol=0;
            for(int j=i+1;j<last_prompt&&j<nl;j++) ol+=snprintf(out+ol,(size_t)(B-ol),"%s%s",ol?"\n":"",lines[j]);
            /* Try to copy to clipboard */
            FILE *fp = popen("wl-copy 2>/dev/null || xclip -selection clipboard -i 2>/dev/null", "w");
            if (fp) { fputs(out, fp); pclose(fp); }
            char s[54]; snprintf(s, 54, "%s", out); for (char *c=s;*c;c++) if(*c=='\n')*c=' ';
            printf("\xe2\x9c\x93 %s\n", s);
            free(d); return 0;
        }
    free(d); puts("x No output found"); return 0;
}

/* ── dash ── */
static int cmd_dash(int argc, char **argv) { (void)argc;(void)argv;
    char wd[P]; if(!getcwd(wd,P)) snprintf(wd,P,"%s",HOME);
    if (!tm_has("dash")) {
        char c[B];
        snprintf(c, B, "tmux new-session -d -s dash -c '%s'", wd); (void)!system(c);
        snprintf(c, B, "tmux split-window -h -t dash -c '%s' 'sh -c \"a jobs; exec $SHELL\"'", wd); (void)!system(c);
    }
    tm_go("dash"); return 0;
}

/* ── attach ── */
static int cmd_attach(int argc, char **argv) { fallback_py("attach", argc, argv); }

/* ── watch ── */
static int cmd_watch(int argc, char **argv) {
    if (argc < 3) { puts("Usage: a watch <session> [duration]"); return 1; }
    const char *sn = argv[2]; int dur = argc > 3 ? atoi(argv[3]) : 0;
    printf("Watching '%s'%s\n", sn, dur ? "" : " (once)");
    time_t start = time(NULL);
    char last[B] = "";
    while (1) {
        if (dur && time(NULL) - start > dur) break;
        char c[B], out[B]; snprintf(c, B, "tmux capture-pane -t '%s' -p 2>/dev/null", sn);
        if (pcmd(c, out, B) != 0) { printf("x Session %s not found\n", sn); return 1; }
        if (strcmp(out, last)) {
            if (strstr(out, "Are you sure?") || strstr(out, "Continue?") || strstr(out, "[y/N]") || strstr(out, "[Y/n]")) {
                snprintf(c, B, "tmux send-keys -t '%s' y Enter", sn); (void)!system(c);
                puts("\xe2\x9c\x93 Auto-responded");
            }
            snprintf(last, B, "%s", out);
        }
        usleep(100000);
        if (!dur) break;
    }
    return 0;
}

/* ── send ── */
static int cmd_send(int argc, char **argv) {
    if (argc < 4) { puts("Usage: a send <session> <prompt> [--wait] [--no-enter]"); return 1; }
    const char *sn = argv[2];
    if (!tm_has(sn)) { printf("x Session %s not found\n", sn); return 1; }
    char prompt[B]=""; int pl=0,wait=0,enter=1;
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i],"--wait")) wait = 1;
        else if (!strcmp(argv[i],"--no-enter")) enter = 0;
        else { pl+=snprintf(prompt+pl,(size_t)(B-pl),"%s%s",pl?" ":"",argv[i]); }
    }
    tm_send(sn, prompt);
    if (enter) { usleep(100000); char c[B]; snprintf(c, B, "tmux send-keys -t '%s' Enter", sn); (void)!system(c); }
    printf("\xe2\x9c\x93 %s '%s'\n", enter?"Sent to":"Inserted into", sn);
    if (wait) {
        printf("Waiting..."); fflush(stdout);
        time_t last_active = time(NULL);
        while (1) {
            char c[B]; snprintf(c, B, "tmux display-message -p -t '%s' '#{window_activity}' 2>/dev/null", sn);
            char out[64]; pcmd(c, out, 64);
            int act = atoi(out);
            if (time(NULL) - act < 2) { last_active = time(NULL); printf("."); fflush(stdout); }
            else if (time(NULL) - last_active > 3) { puts("\n+ Done"); break; }
            usleep(500000);
        }
    }
    return 0;
}

/* ── jobs ── */
static int cmd_jobs(int argc, char **argv) { fallback_py("jobs", argc, argv); }

/* ── cleanup ── */
static int cmd_cleanup(int argc, char **argv) { fallback_py("cleanup", argc, argv); }

/* ── tree ── */
static int cmd_tree(int argc, char **argv) {
    init_db(); load_cfg(); load_proj();
    const char *wt = cfget("worktrees_dir"); if (!wt[0]) { char d[P]; snprintf(d,P,"%s/projects/aWorktrees",HOME); wt=d; }
    char cwd[P]; if(!getcwd(cwd,P)) snprintf(cwd,P,"%s",HOME);
    const char *proj = cwd;
    if (argc > 2 && argv[2][0]>='0' && argv[2][0]<='9') { int idx=atoi(argv[2]); if(idx<NPJ) proj=PJ[idx].path; }
    if (!git_in_repo(proj)) { puts("x Not a git repo"); return 1; }
    char ts[32]; time_t now = time(NULL); strftime(ts, 32, "%Y%m%d-%H%M%S", localtime(&now));
    char wp[P]; snprintf(wp, P, "%s/%s-%s", wt, bname(proj), ts);
    char c[B]; snprintf(c, B, "mkdir -p '%s' && git -C '%s' worktree add -b 'wt-%s-%s' '%s' HEAD", wt, proj, bname(proj), ts, wp);
    if (system(c) != 0) { puts("x Failed"); return 1; }
    printf("\xe2\x9c\x93 %s\n", wp);
    const char *sh = getenv("SHELL"); if (!sh) sh = "/bin/bash";
    if (chdir(wp) == 0) execlp(sh, sh, (char*)NULL);
    return 0;
}
