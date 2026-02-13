/* ── hub ── */
static int cmd_hub(int argc, char **argv) { fallback_py(argc, argv); }

/* ── log ── */
static int cmd_log(int argc, char **argv) {
    const char *sub = argc > 2 ? argv[2] : NULL;
    if (sub && !strcmp(sub, "sync")) { fallback_py(argc, argv); }
    if (sub && !strcmp(sub, "grab")) { fallback_py(argc, argv); }

    char adir[P]; snprintf(adir, P, "%s/git/activity", AROOT);

    if (sub && !strcmp(sub, "all")) {
        char c[B]; snprintf(c, B, "cat $(ls '%s'/*.txt 2>/dev/null | sort) 2>/dev/null", adir);
        (void)!system(c); return 0;
    }

    if (sub && sub[0] >= '0' && sub[0] <= '9') {
        /* View transcript by number */
        mkdirp(LOGDIR);
        char c[B], out[B*4];
        snprintf(c, B, "ls -t '%s'/*.log 2>/dev/null | head -20", LOGDIR);
        pcmd(c, out, sizeof(out));
        char *lines[20]; int n = 0; char *p = out;
        while (*p && n < 20) { lines[n++] = p; char *e = strchr(p,'\n'); if(e){*e=0;p=e+1;}else break; }
        int idx = atoi(sub);
        if (idx >= 0 && idx < n) {
            snprintf(c, B, "tmux new-window 'cat \"%s\"; read'", lines[idx]); return (void)!system(c), 0;
        }
        return 0;
    }

    /* Default: recent activity with AM/PM display + header */
    char c[B], out[256];
    printf("%-5s %-7s %-16s %-20s %-30s %s\n", "DATE", "TIME", "DEVICE", "CMD", "CWD", "GIT");
    fflush(stdout);
    snprintf(c, B, "cat $(ls '%s'/*.txt 2>/dev/null | sort | tail -30) 2>/dev/null"
        " | awk '{split($2,t,\":\"); h=int(t[1]); m=t[2]; ap=\"AM\"; if(h>=12){ap=\"PM\"; if(h>12)h-=12} if(h==0)h=12; $2=h\":\"m ap} 1'", adir);
    (void)!system(c);

    /* Git remote for activity log */
    snprintf(c, B, "git -C '%s/git' remote get-url origin 2>/dev/null", AROOT);
    pcmd(c, out, 256); out[strcspn(out, "\n")] = 0;
    snprintf(c, B, "ls '%s'/*.txt 2>/dev/null | wc -l", adir);
    char nout[64]; pcmd(c, nout, 64);
    printf("\nActivity: %s/ (%d files)\n  git: %s\n  gdrive: adata/backup/git.tar.zst (via a gdrive sync)\n", adir, atoi(nout), out[0] ? out : "(no remote)");

    /* LLM transcript count + gdrive info */
    mkdirp(LOGDIR);
    snprintf(c, B, "ls '%s'/*.log 2>/dev/null | wc -l", LOGDIR);
    pcmd(c, out, 256); int nlogs = atoi(out);
    if (nlogs) printf("LLM transcripts: %s/ (%d files)\n  gdrive: adata/backup/%s/\n  view: a log <#> | sync: a log sync\n", LOGDIR, nlogs, DEV);

    return 0;
}

/* ── login ── */
static int cmd_login(int argc, char **argv) { fallback_py(argc, argv); }

/* ── sync ── */
static int cmd_sync(int argc, char **argv) {
    printf("%s\n", SROOT);
    sync_repo();
    char c[B], out[256];
    snprintf(c, B, "git -C '%s' remote get-url origin 2>/dev/null", SROOT);
    pcmd(c, out, 256); out[strcspn(out,"\n")] = 0;
    char t[256]; snprintf(c, B, "git -C '%s' log -1 --format='%%cd %%s' --date=format:'%%Y-%%m-%%d %%I:%%M:%%S %%p' 2>/dev/null", SROOT);
    pcmd(c, t, 256); t[strcspn(t,"\n")] = 0;
    printf("  %s\n  Last: %s\n  Status: synced\n", out, t);
    /* Count files per folder */
    const char *folders[] = {"common","ssh","login","agents","notes","workspace","docs","tasks"};
    for (int i = 0; i < 8; i++) {
        char d[P]; snprintf(d, P, "%s/%s", SROOT, folders[i]);
        if (!dexists(d)) continue;
        char cnt_cmd[P]; snprintf(cnt_cmd, P, "find '%s' -name '*.txt' -maxdepth 2 2>/dev/null | wc -l", d);
        char cnt[16]; pcmd(cnt_cmd, cnt, 16); cnt[strcspn(cnt,"\n")] = 0;
        printf("  %s: %s files\n", folders[i], cnt);
    }
    if (argc > 2 && !strcmp(argv[2], "all")) {
        puts("\n--- Broadcasting to SSH hosts ---");
        char bc[B]; snprintf(bc, B, "%s/lib/a.py", SDIR);
        char cmd[B]; snprintf(cmd, B, "python3 '%s' ssh all 'a sync'", bc); (void)!system(cmd);
    }
    return 0;
}

/* ── update ── */
static int cmd_update(int argc, char **argv) {
    const char *sub = argc > 2 ? argv[2] : NULL;
    if (sub && (!strcmp(sub,"help")||!strcmp(sub,"-h"))) {
        puts("a update - Update a from git + refresh caches\n  a update        Pull latest\n  a update shell  Refresh shell config\n  a update cache  Refresh caches");
        return 0;
    }
    if (sub && (!strcmp(sub,"bash")||!strcmp(sub,"zsh")||!strcmp(sub,"shell")||!strcmp(sub,"cache"))) {
        init_db(); load_cfg(); list_all(1, 1);
        gen_icache();
        puts("\xe2\x9c\x93 Cache"); return 0;
    }
    /* Full update */
    char c[B]; snprintf(c, B, "git -C '%s' rev-parse --git-dir >/dev/null 2>&1", SDIR);
    if (system(c) != 0) { puts("x Not in git repo"); return 0; }
    snprintf(c, B, "git -C '%s' fetch 2>/dev/null", SDIR); (void)!system(c);
    snprintf(c, B, "git -C '%s' status -uno 2>/dev/null", SDIR);
    char out[B]; pcmd(c, out, B);
    if (!strstr(out, "behind")) {
        printf("\xe2\x9c\x93 Up to date\n");
    } else {
        puts("Downloading...");
        snprintf(c, B, "git -C '%s' pull --ff-only 2>/dev/null", SDIR); (void)!system(c);
    }
    /* Self-build: prefer clang, fall back to gcc */
    snprintf(c, B, "cd '%s' && { command -v clang >/dev/null 2>&1 && clang -O2 -o a a.c || gcc -O2 -o a a.c; }", SDIR);
    if (system(c) == 0) puts("\xe2\x9c\x93 Built"); else puts("x Build failed");
    /* Refresh shell + caches */
    snprintf(c, B, "bash '%s/install.sh' --shell 2>/dev/null", SDIR); (void)!system(c);
    init_db(); load_cfg(); list_all(1, 1);
    /* Also sync */
    sync_repo();
    if (sub && !strcmp(sub, "all")) {
        puts("\n--- Broadcasting to SSH hosts ---");
        snprintf(c, B, "python3 '%s' ssh all 'a update'", PYPATH); (void)!system(c);
    }
    return 0;
}
