/* ── bg backup ── */
static void bg_backup_jsonl(void) {
    char c[B]; snprintf(c, B, "nohup sh -c '"
        "mkdir -p %s/backup/%s && "
        "find ~/.claude/projects -name \"*.jsonl\" 2>/dev/null "
        "| while read f; do cp -n \"$f\" %s/backup/%s/ 2>/dev/null; done; "
        "r=$(rclone listremotes 2>/dev/null | grep \"^a-gdrive\" | head -1 | tr -d \":\"); "
        "[ -n \"$r\" ] && rclone copy %s/backup/%s \"$r:adata/backup/%s/\" --include \"*.jsonl\" -q"
        "' </dev/null >/dev/null 2>&1 &",
        AROOT, DEV, AROOT, DEV, AROOT, DEV, DEV);
    (void)!system(c);
}

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

    if (sub && !strcmp(sub, "all")) { perf_disarm();
        char c[B]; snprintf(c, B, "cat '%s'/*.txt 2>/dev/null", adir);
        (void)!system(c); return 0; }

    /* Default: recent activity — opendir+awk, 1 fork vs 5 */
    char c[B];
    printf("%-5s %-8s %-12s %-40s %s\n","DATE","TIME","DEVICE","CMD","DIR");fflush(stdout);
    { DIR*d=opendir(adir);struct dirent*e;char*fn[512];int nf=0;
    if(d){while((e=readdir(d))&&nf<512)if(strstr(e->d_name,".txt"))fn[nf++]=strdup(e->d_name);closedir(d);}
    for(int i=1;i<nf;i++){char*t=fn[i];int j=i;while(j&&strcmp(fn[j-1],t)>0){fn[j]=fn[j-1];j--;}fn[j]=t;}
    int o=snprintf(c,B,"awk '/^[0-9][0-9]\\//{split($2,t,\":\");h=int(t[1]);m=t[2];ap=\"AM\";"
        "if(h>=12){ap=\"PM\";if(h>12)h-=12}if(h==0)h=12;"
        "c=\"\";for(i=4;i<NF;i++){if(i>4)c=c\" \";c=c$i}"
        "if(length(c)>40)c=substr(c,1,18)\"...\"substr(c,length(c)-14);"
        "n=split($NF,p,\"/\");d=p[n];printf \"%%5s %%2d:%%s%%s  %%-12s %%-40s %%s\\n\",$1,h,m,ap,$3,c,d}'");
    for(int i=nf>30?nf-30:0;i<nf;i++)o+=snprintf(c+o,(size_t)(B-o)," '%s/%s'",adir,fn[i]);
    (void)!system(c);for(int i=0;i<nf;i++)free(fn[i]);}

    /* Status footer — pure C, no shell-outs */
    #define AGO(buf,sz,sec) do { int _s=(int)(sec); if(_s<60)snprintf(buf,sz,"%ds ago",_s); \
        else if(_s<3600)snprintf(buf,sz,"%dm ago",_s/60); \
        else if(_s<86400)snprintf(buf,sz,"%dh ago",_s/3600); \
        else snprintf(buf,sz,"%dd ago",_s/86400); } while(0)
    /* count .ext files in dir, track newest mtime */
    #define DCOUNT(dir,ext,cnt,newest) do { DIR*_d=opendir(dir); struct dirent*_e; struct stat _s; char _p[P]; \
        cnt=0; newest=0; if(_d){while((_e=readdir(_d))){int _l=(int)strlen(_e->d_name); int _el=(int)strlen(ext); \
        if(_l>_el&&!strcmp(_e->d_name+_l-_el,ext)){cnt++;snprintf(_p,P,"%s/%s",dir,_e->d_name); \
        if(!stat(_p,&_s)&&_s.st_mtime>newest)newest=_s.st_mtime;}}closedir(_d);} } while(0)
    mkdirp(LOGDIR);
    int nlogs; time_t llm_new; DCOUNT(LOGDIR,".log",nlogs,llm_new);
    char jdir[P]; snprintf(jdir,P,"%s/git/jobs",AROOT);
    int jlogs; time_t job_new; DCOUNT(jdir,".log",jlogs,job_new);
    char gurl[256]=""; { char gp[P]; snprintf(gp,P,"%s/git/.git/config",AROOT);
        char *gc=readf(gp,NULL); if(gc){char *u=strstr(gc,"url = ");if(u){u+=6;char*nl=strchr(u,'\n');if(nl)*nl=0;snprintf(gurl,256,"%s",u);}free(gc);} }
    int git_ok=gurl[0]!=0;
    /* count backup subdirs + newest .jsonl across them */
    int nbak=0; time_t bak_new=0; { char bd[P]; snprintf(bd,P,"%s/backup",AROOT);
        DIR*d=opendir(bd); struct dirent*e; if(d){while((e=readdir(d))){if(e->d_name[0]=='.')continue;
        char sd[P]; snprintf(sd,P,"%s/%s",bd,e->d_name); struct stat ss; if(!stat(sd,&ss)&&S_ISDIR(ss.st_mode)){
        nbak++; int _n; time_t _t; DCOUNT(sd,".jsonl",_n,_t); (void)_n; if(_t>bak_new)bak_new=_t;}}closedir(d);} }
    time_t now=time(NULL); char ago[32];
    /* gdrive folder ID: try local, then git-synced from any device */
    char gdid[64]=""; { char gp[P];
        snprintf(gp,P,"%s/backup/%s/.gdrive_id",AROOT,DEV);
        FILE *gf=fopen(gp,"r");
        if(!gf){snprintf(gp,P,"%s/git/gdrive.id",AROOT);gf=fopen(gp,"r");}
        if(gf){if(fgets(gdid,64,gf))gdid[strcspn(gdid,"\n")]=0;fclose(gf);} }
    char bpath[P]; snprintf(bpath,P,"adata/backup/%s/",DEV);
    char gdu[256]=""; if(gdid[0])snprintf(gdu,256,"https://drive.google.com/drive/folders/%s",gdid);
    #define ROW(t,n,l,p,u) { int a=t?(int)(now-t):-1; if(a>=0)AGO(ago,32,a);else snprintf(ago,32,"never"); \
        printf("%s %-18s %3d  %-28s last: %s\n",n?"\xe2\x9c\x93":"x",l,n,p,ago); if(u)printf("  \xe2\x86\x92 %s\n",u); }
    putchar('\n');
    ROW(llm_new,nlogs,"LLM transcripts",bpath,gdu[0]?gdu:NULL)
    ROW(job_new,jlogs,"Job tmux logs","adata/git/jobs/",git_ok?gurl:NULL)
    ROW(bak_new,nbak,"JSONL backup",bpath,gdu[0]?gdu:NULL)
    #undef ROW
    #undef DCOUNT
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
    bg_backup_jsonl();
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
    {char g[P];snprintf(g,P,"%s/.git",SDIR);if(access(g,F_OK)!=0){puts("x Not in git repo");init_db();load_cfg();list_all(1,1);gen_icache();return 0;}}
    char c[B];snprintf(c, B, "git -C '%s' checkout -- a-i 2>/dev/null", SDIR); (void)!system(c);
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
    /* rclone: append-only timestamped */
    { char ld[P];snprintf(ld,P,"%s/git/login",AROOT);mkdirp(ld);
      char t[64];pcmd("rclone listremotes 2>/dev/null|grep a-gdrive|head -1",t,64);
      if(t[0]&&t[0]!='\n'){struct timespec ts;clock_gettime(CLOCK_REALTIME,&ts);struct tm*tm=localtime(&ts.tv_sec);char tf[32];strftime(tf,32,"%Y%m%dT%H%M%S",tm);
        snprintf(c,B,"cp ~/.config/rclone/rclone.conf '%s/rclone_%s.%09ld.conf'",ld,tf,ts.tv_nsec);(void)!system(c);
      } else {char ps[16][P];int np=listdir(ld,ps,16);char*lp=NULL;
        for(int i=np-1;i>=0;i--)if(strstr(ps[i],"rclone_")&&strstr(ps[i],".conf")){lp=ps[i];break;}
        if(lp){snprintf(c,B,"mkdir -p ~/.config/rclone&&cp '%s' ~/.config/rclone/rclone.conf",lp);
          if(!system(c))puts("\xe2\x9c\x93 rclone config from sync");}}}
    bg_backup_jsonl();
    if (sub && !strcmp(sub, "all")) {
        puts("\n--- Broadcasting to SSH hosts ---");
        snprintf(c, B, "'%s/a' ssh all 'a update'", SDIR); (void)!system(c);
    }
    return 0;
}
