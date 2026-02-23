/* ── email ── */
static int cmd_email(int argc, char **argv) {
    char bp[P]; snprintf(bp,P,"%s/personal/base.py",SDIR);
    char **na=malloc(((unsigned)argc+2)*sizeof(char*));
    na[0]="python3"; na[1]=bp;
    for(int i=2;i<argc;i++) na[i]=argv[i];
    na[argc]=NULL;
    execvp("python3",na); perror("python3"); return 1;
}

/* ── log ── */
static int cmd_log(int argc, char **argv) {
    const char *sub = argc > 2 ? argv[2] : NULL;
    if (sub && !strcmp(sub, "sync")) { fallback_py("log", argc, argv); }
    if (sub && !strcmp(sub, "grab")) { fallback_py("log", argc, argv); }
    if (sub && !strcmp(sub, "backup")) { perf_disarm();
        char c[B], cnt[64], bdir[P]; snprintf(bdir, P, "%s/backup", AROOT);
        char jdir[P]; snprintf(jdir, P, "%s/git/jobs", AROOT);
        snprintf(c, B, "ls '%s'/*.log 2>/dev/null | wc -l", jdir);
        pcmd(c, cnt, 64); printf("Tmux logs: %d (git-synced in adata/git/jobs/)\n\n", atoi(cnt));
        snprintf(c, B, "ls -d '%s'/*/ 2>/dev/null", bdir);
        char dirs[B]; pcmd(c, dirs, B); char *dp = dirs;
        printf("%-16s %6s %6s  %s\n", "DEVICE", "LOCAL", "JSONL", "STATUS");
        while (*dp) {
            char *nl = strchr(dp, '\n'); if (nl) *nl = 0;
            char dp2[P]; snprintf(dp2, P, "%s", dp); { int l=(int)strlen(dp2); if(l>1&&dp2[l-1]=='/')dp2[l-1]=0; }
            char dn[128]; snprintf(dn, 128, "%s", bname(dp2));
            if (!dn[0]||!strcmp(dn,".")||!strcmp(dn,"..")) { if(nl)dp=nl+1;else break;continue; }
            snprintf(c, B, "ls '%s/%s' 2>/dev/null | wc -l", bdir, dn);
            pcmd(c, cnt, 64); int loc = atoi(cnt);
            if (!strcmp(dn, DEV)) { printf("%-16s %6d %6s  local (this device)\n", dn, loc, "-"); }
            else {
                snprintf(c, B, "'%s/a' ssh '%s' 'ls ~/projects/a/adata/backup/%s/*.jsonl 2>/dev/null | wc -l' 2>/dev/null", SDIR, dn, dn);
                pcmd(c, cnt, 64); int rn = atoi(cnt);
                printf("%-16s %6d %6d  %s\n", dn, loc, rn, rn ? "remote \xe2\x9c\x93" : "remote (no JSONL)");
            }
            if (nl) dp = nl + 1; else break;
        }
        return 0;
    }

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
    printf("%-5s %-8s %-12s %-40s %s\n", "DATE", "TIME", "DEVICE", "CMD", "DIR");
    fflush(stdout);
    snprintf(c, B, "cat $(ls '%s'/*.txt 2>/dev/null | sort 2>/dev/null | tail -30) 2>/dev/null"
        " | awk '/^[0-9][0-9]\\/[0-9][0-9] /{"
        "split($2,t,\":\");h=int(t[1]);m=t[2];ap=\"AM\";"
        "if(h>=12){ap=\"PM\";if(h>12)h-=12}if(h==0)h=12;"
        "c=\"\";for(i=4;i<NF;i++){if(i>4)c=c\" \";c=c$i}"
        "if(length(c)>40)c=substr(c,1,18)\"...\"substr(c,length(c)-14);"
        "n=split($NF,p,\"/\");d=p[n];"
        "printf \"%%5s %%2d:%%s%%s  %%-12s %%-40s %%s\\n\",$1,h,m,ap,$3,c,d}'", adir);
    (void)!system(c);

    /* Status footer: ✓ active, x not configured, last sync time */
    #define AGO(buf,sz,sec) do { int _s=(int)(sec); if(_s<60)snprintf(buf,sz,"%ds ago",_s); \
        else if(_s<3600)snprintf(buf,sz,"%dm ago",_s/60); \
        else if(_s<86400)snprintf(buf,sz,"%dh ago",_s/3600); \
        else snprintf(buf,sz,"%dd ago",_s/86400); } while(0)
    mkdirp(LOGDIR);
    snprintf(c, B, "ls '%s'/*.log 2>/dev/null | wc -l", LOGDIR);
    pcmd(c, out, 256); int nlogs = atoi(out);
    char jdir[P]; snprintf(jdir, P, "%s/git/jobs", AROOT);
    snprintf(c, B, "ls '%s'/*.log 2>/dev/null | wc -l", jdir);
    char nout[64]; pcmd(c, nout, 64); int jlogs = atoi(nout);
    snprintf(c, B, "git -C '%s/git' remote get-url origin 2>/dev/null", AROOT);
    char gurl[256]; pcmd(c, gurl, 256); gurl[strcspn(gurl,"\n")] = 0;
    int git_ok = gurl[0] != 0;
    snprintf(c, B, "ls -d '%s/backup'/*/ 2>/dev/null | wc -l", AROOT);
    pcmd(c, nout, 64); int nbak = atoi(nout);
    time_t now = time(NULL); char ago[32]; struct stat fst;
    /* gdrive folder ID from cache */
    char gdid[64]=""; { char gp[P]; snprintf(gp,P,"%s/backup/%s/.gdrive_id",AROOT,DEV);
        FILE *gf=fopen(gp,"r"); if(gf){if(fgets(gdid,64,gf))gdid[strcspn(gdid,"\n")]=0; fclose(gf);} }
    /* LLM transcripts: newest .log in LOGDIR */
    snprintf(c, B, "ls -t '%s'/*.log 2>/dev/null | head -1", LOGDIR);
    pcmd(c, out, 256); out[strcspn(out,"\n")] = 0;
    int llm_age = (out[0] && !stat(out, &fst)) ? (int)(now - fst.st_mtime) : -1;
    if (llm_age >= 0) AGO(ago, 32, llm_age); else snprintf(ago, 32, "never");
    printf("\n%s LLM transcripts  %3d  adata/backup/%s/  last: %s\n",
        nlogs ? "\xe2\x9c\x93" : "x", nlogs, DEV, ago);
    if (gdid[0]) printf("  %s https://drive.google.com/drive/folders/%s\n", "\xe2\x86\x92", gdid);
    /* Job tmux logs: newest .log in git/jobs */
    snprintf(c, B, "ls -t '%s'/*.log 2>/dev/null | head -1", jdir);
    pcmd(c, out, 256); out[strcspn(out,"\n")] = 0;
    int job_age = (out[0] && !stat(out, &fst)) ? (int)(now - fst.st_mtime) : -1;
    if (job_age >= 0) AGO(ago, 32, job_age); else snprintf(ago, 32, "never");
    printf("%s Job tmux logs    %3d  adata/git/jobs/  last: %s\n",
        git_ok && jlogs ? "\xe2\x9c\x93" : "x", jlogs, ago);
    if (git_ok) printf("  %s %s\n", "\xe2\x86\x92", gurl);
    /* JSONL backup: newest .jsonl in backup dirs (not .log — those are old session logs) */
    snprintf(c, B, "find '%s/backup' -name '*.jsonl' -maxdepth 3 -printf '%%T@ %%p\\n' 2>/dev/null | sort -rn 2>/dev/null | head -1 | cut -d' ' -f2-", AROOT);
    pcmd(c, out, 256); out[strcspn(out,"\n")] = 0;
    int bak_age = (out[0] && !stat(out, &fst)) ? (int)(now - fst.st_mtime) : -1;
    if (bak_age >= 0) AGO(ago, 32, bak_age); else snprintf(ago, 32, "never");
    snprintf(c, B, "pgrep -x rclone >/dev/null 2>&1");
    int syncing = system(c) == 0;
    printf("%s JSONL backup          adata/backup/%s/  last: %s%s\n",
        nbak ? "\xe2\x9c\x93" : "x", DEV, ago, syncing ? "  (syncing)" : "");
    if (gdid[0]) printf("  %s https://drive.google.com/drive/folders/%s\n", "\xe2\x86\x92", gdid);
    #undef AGO
    return 0;
}

/* ── login ── */
static int cmd_login(int argc, char **argv) { fallback_py("login", argc, argv); }

/* ── sync ── */
static int cmd_sync(int argc, char **argv) {
    if (getenv("A_BENCH")) return 0;
    printf("%s\n", SROOT);
    ensure_adata();
    sync_repo();
    char c[B], out[256];
    snprintf(c, B, "git -C '%s' remote get-url origin 2>/dev/null", SROOT);
    pcmd(c, out, 256); out[strcspn(out,"\n")] = 0;
    char t[256]; snprintf(c, B, "git -C '%s' log -1 --format='%%cd %%s' --date=format:'%%Y-%%m-%%d %%I:%%M:%%S %%p' 2>/dev/null", SROOT);
    pcmd(c, t, 256); t[strcspn(t,"\n")] = 0;
    const char *status = "synced";
    if (!out[0]) status = "no remote (run: gh auth login, then: a sync)";
    else if (!t[0]) status = "empty (no commits yet)";
    printf("  %s\n  Last: %s\n  Status: %s\n", out[0] ? out : "(no remote)", t[0] ? t : "(none)", status);
    /* Count files per folder */
    const char *folders[] = {"common","ssh","login","agents","notes","workspace","docs","tasks"};
    for (int i = 0; i < 8; i++) {
        char d[P]; snprintf(d, P, "%s/%s", SROOT, folders[i]);
        if (!dexists(d)) continue;
        char cnt_cmd[P]; snprintf(cnt_cmd, P, "find '%s' -name '*.txt' -maxdepth 2 2>/dev/null | wc -l", d);
        char cnt[16]; pcmd(cnt_cmd, cnt, 16); cnt[strcspn(cnt,"\n")] = 0;
        printf("  %s: %s files\n", folders[i], cnt);
    }
    /* collect JSONL from ~/.claude/projects/ then push to gdrive (background) */
    snprintf(c, B, "nohup sh -c '"
        "mkdir -p %s/backup/%s && "
        "find ~/.claude/projects -name \"*.jsonl\" 2>/dev/null "
        "| while read f; do cp -n \"$f\" %s/backup/%s/ 2>/dev/null; done; "
        "r=$(rclone listremotes 2>/dev/null | grep \"^a-gdrive\" | head -1 | tr -d \":\"); "
        "[ -n \"$r\" ] && rclone copy %s/backup/%s \"$r:adata/backup/%s/\" --include \"*.jsonl\" -q"
        "' </dev/null >/dev/null 2>&1 &",
        AROOT, DEV, AROOT, DEV, AROOT, DEV, DEV);
    (void)!system(c);
    if (argc > 2 && !strcmp(argv[2], "all")) {
        puts("\n--- Broadcasting to SSH hosts ---");
        char bc[B]; snprintf(bc, B, "%s/lib/a.py", SDIR);
        char cmd[B]; snprintf(cmd, B, "python3 '%s' ssh all 'a sync'", bc); (void)!system(cmd);
    }
    return 0;
}

/* ── update ── */
static int cmd_update(int argc, char **argv) {
    if (getenv("A_BENCH")) return 0;
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
    /* Pull, rebuild, exec new */
    char c[B]; snprintf(c, B, "git -C '%s' rev-parse --git-dir >/dev/null 2>&1", SDIR);
    if (system(c) != 0) { puts("x Not in git repo"); return 0; }
    snprintf(c, B, "git -C '%s' checkout -- a-i 2>/dev/null", SDIR); (void)!system(c);
    snprintf(c, B, "git -C '%s' fetch 2>/dev/null", SDIR); (void)!system(c);
    snprintf(c, B, "git -C '%s' status -uno 2>/dev/null", SDIR);
    char out[B]; pcmd(c, out, B);
    if (strstr(out, "diverged")) {
        puts("Diverged — rebasing...");
        snprintf(c, B, "git -C '%s' pull --rebase 2>/dev/null", SDIR); (void)!system(c);
    } else if (strstr(out, "behind")) {
        puts("Downloading...");
        snprintf(c, B, "git -C '%s' pull --ff-only 2>/dev/null", SDIR); (void)!system(c);
    } else {
        printf("\xe2\x9c\x93 Up to date\n");
    }
    snprintf(c, B, "sh '%s/a.c'", SDIR);
    if (system(c) == 0) puts("\xe2\x9c\x93 Built"); else puts("x Build failed");
    { char ai[P]; snprintf(ai,P,"%s/a-i",SDIR); if(!access(ai,X_OK)){snprintf(c,B,"'%s' --stop",ai);(void)!system(c);} }
    snprintf(c, B, "ln -sf '%s/a' '%s/.local/bin/a'", SDIR, getenv("HOME"));
    (void)!system(c);
    { char vp[P]; snprintf(vp, P, "%s/venv/bin/pip", AROOT);
      if (access(vp, X_OK) == 0) {
          snprintf(c, B, "'%s' install -q pexpect prompt_toolkit aiohttp 2>/dev/null", vp);
          if (system(c) == 0) puts("\xe2\x9c\x93 Python deps"); else puts("x pip failed");
      }
    }
    snprintf(c, B, "bash '%s/a.c' shell 2>/dev/null", SDIR); (void)!system(c);
    /* Termux: ensure Claude Code sandbox dir + tmux env on update */
    if (access("/data/data/com.termux",F_OK)==0) {
        char td[P]; snprintf(td,P,"%s/.tmp",HOME); mkdirp(td);
        snprintf(c,B,"tmux set-environment -g CLAUDE_CODE_TMPDIR '%s' 2>/dev/null",td); (void)!system(c);
    }
    snprintf(c, B, "'%s/a' update cache", SDIR); (void)!system(c);
    ensure_adata();
    sync_repo();
    /* collect JSONL from ~/.claude/projects/ then push to gdrive (background) */
    snprintf(c, B, "nohup sh -c '"
        "mkdir -p %s/backup/%s && "
        "find ~/.claude/projects -name \"*.jsonl\" 2>/dev/null "
        "| while read f; do cp -n \"$f\" %s/backup/%s/ 2>/dev/null; done; "
        "r=$(rclone listremotes 2>/dev/null | grep \"^a-gdrive\" | head -1 | tr -d \":\"); "
        "[ -n \"$r\" ] && rclone copy %s/backup/%s \"$r:adata/backup/%s/\" --include \"*.jsonl\" -q"
        "' </dev/null >/dev/null 2>&1 &",
        AROOT, DEV, AROOT, DEV, AROOT, DEV, DEV);
    (void)!system(c);
    if (sub && !strcmp(sub, "all")) {
        puts("\n--- Broadcasting to SSH hosts ---");
        snprintf(c, B, "python3 '%s/lib/ssh.py' ssh all 'a update'", SDIR); (void)!system(c);
    }
    return 0;
}
