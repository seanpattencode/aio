/* ── push ── */
static int cmd_push(int argc, char **argv) {
    char cwd[P]; if(!getcwd(cwd,P)) snprintf(cwd,P,".");
    char msg[B]="";
    if(argc>2)for(int i=2,l=0;i<argc;i++) l+=snprintf(msg+l,(size_t)(B-l),"%s%s",i>2?" ":"",argv[i]);
    else snprintf(msg, B, "Update %s", bname(cwd));

    if (!git_in_repo(cwd)) {
        /* Check for sub-repos */
        DIR *d = opendir(cwd); struct dirent *e; int nsub = 0;
        char subs[32][256];
        if (d) { while ((e = readdir(d)) && nsub < 32) { char gp[P]; snprintf(gp,P,"%s/%s/.git",cwd,e->d_name); if (dexists(gp)) snprintf(subs[nsub++],256,"%s",e->d_name); } closedir(d); }
        if (nsub) {
            printf("Push %d repos? ", nsub);
            for (int i = 0; i < nsub; i++) printf("%s%s", subs[i], i<nsub-1?", ":"");
            printf(" [y/n]: "); char buf[8]; if (!fgets(buf,8,stdin) || buf[0]!='y') return 0;
            for (int i = 0; i < nsub; i++) {
                char c[B]; snprintf(c, B, "cd '%s/%s' && git add -A && git commit -m '%s' --allow-empty 2>/dev/null && git push 2>/dev/null", cwd, subs[i], msg);
                int r = system(c); printf("%s %s\n", r==0?"\xe2\x9c\x93":"x", subs[i]);
            }
            return 0;
        }
        printf("Not a git repo. Set up as private GitHub repo? [y/n]: ");
        char buf2[8]; if (fgets(buf2,8,stdin) && buf2[0]=='y') return cmd_setup(argc, argv);
        return 0;
    }
    /* Check dirty */
    char dirty[64] = ""; pcmd("git status --porcelain 2>/dev/null", dirty, 64);
    const char *tag = dirty[0] ? "\xe2\x9c\x93" : "\xe2\x97\x8b";

    /* Check instant mode */
    char ok[P]; snprintf(ok, P, "%s/logs/push.ok", DDIR);
    struct stat st;
    if (stat(ok, &st) == 0 && time(NULL) - st.st_mtime < 600) {
        char c[B*2]; snprintf(c, sizeof(c),
            "cd '%s' && git add -A && git commit -m \"%s\" --allow-empty 2>/dev/null; git push 2>/dev/null; touch '%s'",
            cwd, msg, ok);
        if (fork() == 0) { setsid();
            int n=open("/dev/null",O_RDWR); if(n>=0){dup2(n,0);dup2(n,1);dup2(n,2);close(n);}
            execl("/bin/sh","sh","-c",c,(char*)NULL); _exit(1);
        }
        printf("%s %s\n", tag, msg); return 0;
    }
    /* Real push */
    char c[B];
    snprintf(c, B, "git -C '%s' config remote.origin.url 2>/dev/null", cwd);
    if (system(c) != 0) {
        snprintf(c, B, "cd '%s' && gh repo create --private --source . --push", cwd); (void)!system(c);
    }
    snprintf(c, B, "cd '%s' && git add -A && git commit -m '%s' --allow-empty 2>/dev/null", cwd, msg); (void)!system(c);
    snprintf(c, B, "cd '%s' && git push -u origin HEAD 2>&1", cwd);
    char out[B]; pcmd(c, out, B);
    if (strstr(out, "->") || strstr(out, "up-to-date") || strstr(out, "Everything")) {
        mkdirp(DDIR); snprintf(c, B, "%s/logs", DDIR); mkdirp(c);
        int fd = open(ok, O_CREAT|O_WRONLY|O_TRUNC, 0644); if(fd>=0)close(fd);
        printf("%s %s\n", tag, msg);
    } else printf("\xe2\x9c\x97 %s\n", out);
    return 0;
}

/* ── pr ── */
static void sq(const char *s, char *o, int sz) { int j=0; o[j++]='\'';
    for(;*s&&j<sz-4;s++){if(*s=='\''){o[j++]='\'';o[j++]='\\';o[j++]='\'';o[j++]='\'';}else o[j++]=*s;} o[j++]='\'';o[j]=0; }
static int cmd_pr(int argc, char **argv) {
    char cwd[P]; if(!getcwd(cwd,P)) snprintf(cwd,P,".");
    if (!git_in_repo(cwd)) { puts("x Not a git repo"); return 1; }
    char br[128]; pcmd("git rev-parse --abbrev-ref HEAD 2>/dev/null",br,128); br[strcspn(br,"\n")]=0;
    if (!strcmp(br,"main")||!strcmp(br,"master")) { puts("x On main — create a branch first"); return 1; }
    char title[256]=""; if(argc>2){int l=0;for(int i=2;i<argc;i++)l+=snprintf(title+l,(size_t)(256-l),"%s%s",i>2?" ":"",argv[i]);}
    else snprintf(title,256,"%s",br);
    char qt[512],qb[512]; sq(title,qt,512); sq(br,qb,512);
    /* commit + push if needed */
    char dirty[64]=""; pcmd("git status --porcelain 2>/dev/null",dirty,64);
    if(dirty[0]){char c[B];snprintf(c,B,"git add -A && git commit -m %s",qt);(void)!system(c);}
    char c[B]; snprintf(c,B,"git push -u origin %s 2>&1",br);
    char out[B]; pcmd(c,out,B);
    if(!strstr(out,"->")&&!strstr(out,"up-to-date")&&!strstr(out,"Everything")){printf("x Push: %s\n",out);return 1;}
    snprintf(c,B,"gh pr create --title %s --body '' --head %s 2>&1",qt,qb); pcmd(c,out,B);
    out[strcspn(out,"\n")]=0;
    if(strstr(out,"github.com")&&strstr(out,"/pull/")) printf("+ %s\n",out);
    else if(strstr(out,"already exists")) printf("+ PR exists for %s\n",br);
    else printf("x %s\n",out);
    return 0;
}

/* ── pull ── */
static int cmd_pull(int argc, char **argv) {
    char cwd[P]; if (!getcwd(cwd, P)) strcpy(cwd, ".");
    if (!git_in_repo(cwd)) { puts("x Not a git repo"); return 1; }
    char c[B], out[B];
    snprintf(c, B, "git -C '%s' fetch origin 2>/dev/null", cwd); (void)!system(c);
    snprintf(c, B, "git -C '%s' rev-parse --verify origin/main 2>/dev/null", cwd);
    const char *ref = (system(c) == 0) ? "origin/main" : "origin/master";
    snprintf(c, B, "git -C '%s' log -1 --format='%%h %%s' %s", cwd, ref); pcmd(c, out, B);
    out[strcspn(out,"\n")] = 0;
    printf("! DELETE local changes -> %s\n", out);
    if (argc < 3 || (strcmp(argv[2],"--yes") && strcmp(argv[2],"-y"))) {
        printf("Continue? (y/n): "); char buf[8]; if (!fgets(buf,8,stdin) || buf[0]!='y') { puts("x Cancelled"); return 1; }
    }
    snprintf(c, B, "git -C '%s' reset --hard %s && git -C '%s' clean -f -d", cwd, ref, cwd); (void)!system(c);
    printf("\xe2\x9c\x93 Synced: %s\n", out); return 0;
}

/* ── diff ── */
static int cmd_diff(int argc, char **argv) {
    const char *sel = argc > 2 ? argv[2] : NULL;
    /* Token history mode */
    if (sel && sel[0] >= '0' && sel[0] <= '9') {
        int n = atoi(sel); char c[256]; snprintf(c, 256, "git log -%d --pretty=%%H\\ %%cd\\ %%s --date=format:%%I:%%M%%p", n);
        FILE *fp = popen(c, "r"); if (!fp) return 1;
        char line[512]; int total = 0, i = 0;
        while (fgets(line, 512, fp)) {
            line[strcspn(line,"\n")] = 0;
            char *sp = strchr(line, ' '); if (!sp) continue;
            *sp = 0; char *hash = line, *ts = sp + 1;
            sp = strchr(ts, ' '); if (!sp) continue;
            *sp = 0; char *msg = sp + 1;
            char dc[256]; snprintf(dc, 256, "git show %.40s --pretty=", hash);
            FILE *dp = popen(dc, "r"); int ab = 0, db_ = 0;
            if (dp) { char dl[4096]; while (fgets(dl, 4096, dp)) { int l = (int)strlen(dl);
                if (dl[0]=='+' && dl[1]!='+') ab += l-1;
                else if (dl[0]=='-' && dl[1]!='-') db_ += l-1;
            } pclose(dp); }
            int tok = (ab - db_) / 4; total += tok;
            if (strlen(msg) > 55) { msg[52]='.'; msg[53]='.'; msg[54]='.'; msg[55]=0; }
            printf("  %d  %s  %+6d  %s\n", i++, ts, tok, msg);
        }
        pclose(fp); printf("\nTotal: %+d tokens\n", total); return 0;
    }
    /* Full diff — colored + stats */
    char cwd[P]; if(!getcwd(cwd,P)) snprintf(cwd,P,".");
    (void)!system("git fetch origin 2>/dev/null");
    char br[128]; pcmd("git rev-parse --abbrev-ref HEAD 2>/dev/null",br,128); br[strcspn(br,"\n")]=0;
    char tgt[256]; snprintf(tgt,256,"origin/%s",sel?sel:strncmp(br,"wt-",3)?br:"main");
    char ts[64]; pcmd("git log -1 --format=%cd --date=format:'%Y-%m-%d %I:%M:%S %p' 2>/dev/null",ts,64); ts[strcspn(ts,"\n")]=0;
    if(sel) printf("%s -> %s\n",br,tgt); else printf("%s\n%s -> %s\n%s\n",cwd,br,tgt,ts);
    struct{char name[256];int al,dl,ab,db;}fs[256]; int nf=0,cf=-1;
    #define FS(fn) do{cf=-1;for(int _i=0;_i<nf;_i++)if(!strcmp(fs[_i].name,fn)){cf=_i;break;} \
        if(cf<0&&nf<256){cf=nf;memset(&fs[nf],0,sizeof(fs[0]));snprintf(fs[nf].name,256,"%s",fn);nf++;}}while(0)
    #define DS(cmd) do{FILE*_f=popen(cmd,"r");if(_f){char _l[4096];while(fgets(_l,4096,_f)){_l[strcspn(_l,"\n")]=0; \
        if(!strncmp(_l,"diff --git",10)){char*_b=strstr(_l," b/");if(_b)FS(_b+3);} \
        else if(_l[0]=='@'&&_l[1]=='@'){char*_p=strchr(_l,'+');int _n=_p?(int)strtol(_p+1,NULL,10):0; \
            if(cf>=0&&_n)printf("\n%s line %d:\n",fs[cf].name,_n);} \
        else if(_l[0]=='+'&&_l[1]!='+'){printf("  \033[48;2;26;84;42m+ %s\033[0m\n",_l+1);if(cf>=0){fs[cf].al++;fs[cf].ab+=(int)strlen(_l)-1;}} \
        else if(_l[0]=='-'&&_l[1]!='-'){printf("  \033[48;2;117;34;27m- %s\033[0m\n",_l+1);if(cf>=0){fs[cf].dl++;fs[cf].db+=(int)strlen(_l)-1;}}} \
        pclose(_f);}}while(0)
    {char c[B];snprintf(c,B,"git diff '%s..HEAD' 2>/dev/null",tgt);DS(c);}
    {char c[B];snprintf(c,B,"git diff HEAD 2>/dev/null");DS(c);}
    char ut[B]; pcmd("git ls-files --others --exclude-standard 2>/dev/null",ut,B); int nut=0;
    if(ut[0]){printf("\nUntracked:\n");char*p=ut;while(*p){char*e=strchr(p,'\n');if(e)*e=0;if(*p){
        printf("  \033[48;2;26;84;42m+ %s\033[0m\n",p);nut++;size_t sz;char*d=readf(p,&sz);
        if(d){int nl=1;for(size_t j=0;j<sz;j++)if(d[j]=='\n')nl++;FS(p);if(cf>=0){fs[cf].al=nl;fs[cf].ab=(int)sz;}free(d);}
    }if(e)p=e+1;else break;}}
    if(!nf){puts("No changes");return 0;}
    #define HR for(int _j=0;_j<60;_j++){putchar(0xe2);putchar(0x94);putchar(0x80);}putchar('\n')
    int ti=0,td=0,ta=0,tb=0,nd=0; printf("\n"); HR;
    for(int j=0;j<nf;j++){printf("%s: +%d/-%d lines, %+d tok\n",bname(fs[j].name),fs[j].al,fs[j].dl,(fs[j].ab-fs[j].db)/4);
        ti+=fs[j].al;td+=fs[j].dl;ta+=fs[j].ab;tb+=fs[j].db;if(!fs[j].al&&fs[j].dl)nd++;}
    HR; printf("%d file%s, +%d/-%d lines",nf,nf!=1?"s":"",ti,td);
    if(nut)printf(" (incl. untracked)");if(nd)printf(", %d deleted",nd);
    printf(" | Net: %+d lines, %+d tok\n",ti-td,(ta-tb)/4);
    if(!sel) puts("\ndiff # = last #");
    return 0;
    #undef FS
    #undef DS
    #undef HR
}

/* ── revert ── */
static int cmd_revert(int argc, char **argv) { (void)argc; (void)argv;
    char cwd[P]; if (!getcwd(cwd, P)) strcpy(cwd, ".");
    if (!git_in_repo(cwd)) { puts("x Not a git repo"); return 1; }
    char c[B], out[B*4]; snprintf(c, B, "git -C '%s' log --format='%%h %%ad %%s' --date=format:'%%m/%%d %%H:%%M' -15", cwd);
    pcmd(c, out, sizeof(out));
    char *lines[15]; int nl = 0; char *p = out;
    while (*p && nl < 15) { lines[nl++] = p; char *e = strchr(p, '\n'); if (e) { *e = 0; p = e+1; } else break; }
    for (int i = 0; i < nl; i++) printf("  %d. %s\n", i, lines[i]);
    printf("\nRevert to #/q: "); char buf[8]; if (!fgets(buf,8,stdin) || buf[0]=='q') return 0;
    int idx = atoi(buf); if (idx < 0 || idx >= nl) { puts("x Invalid"); return 1; }
    char hash[16]; sscanf(lines[idx], "%s", hash);
    snprintf(c, B, "git -C '%s' revert --no-commit '%s..HEAD'", cwd, hash); (void)!system(c);
    snprintf(c, B, "git -C '%s' commit -m 'revert to %s'", cwd, hash); (void)!system(c);
    printf("\xe2\x9c\x93 Reverted to %s\n", hash);
    printf("Push to main? (y/n): "); if (fgets(buf,8,stdin) && buf[0]=='y') {
        snprintf(c, B, "git -C '%s' push", cwd); (void)!system(c); puts("\xe2\x9c\x93 Pushed");
    }
    return 0;
}
