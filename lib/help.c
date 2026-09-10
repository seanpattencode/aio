/* help */
static const char *HELP_SHORT =
    "a j \"prompt\"     Job: worktree + agent\n"
    "a a|c|co|g      Default/claude/codex/gemini\n"
    "a <#>           Open project by number\n"
    "a help          All commands";

static const char *HELP_FULL =
    "a - agent manager  c=claude co=codex g=gemini\n\n"
    "JOBS    a j \"prompt\"  a done \"msg\"\n"
    "AGENTS  a c|co|g  a <key>++  a agent\n"
    "PROJ    a <#>  a add/remove/move/scan  a create <name>\n"
    "GIT     a push [msg]  a pr [title]  a pull/diff/revert\n"
    "NOTES   a n \"text\"  a task\n"
    "REMOTE  a ssh [<#>]  a run <#> \"task\"\n"
    "CODE    a cat [1|3]  (3=100k index)\n"
    "SYSTEM  a ls/kill  a hub  a config/sync/update/perf";

static void list_all(int cache, int quiet) {
    load_proj(); load_apps();
    char pf[P];snprintf(pf,P,"%s/projects.txt",DDIR);
    FILE*fp=fopen(pf,"w");if(fp){for(int i=0;i<NPJ;i++)fprintf(fp,"%s\n",PJ[i].path);fclose(fp);}
    char out[B*4]="";int o=0;
    for(int i=0;i<NPJ;i++){char mk=dexists(PJ[i].path)?'+':(PJ[i].repo[0]?'~':'x');
        o+=sprintf(out+o,"%s%d. %c %s\n",i?"":"PROJECTS:\n",i,mk,PJ[i].path);}
    for(int i=0;i<NAP;i++)o+=sprintf(out+o,"%s%d. %s -> %.60s\n",i?"":"COMMANDS:\n",NPJ+i,AP[i].name,AP[i].cmd);
    if(!quiet)fputs(out,stdout);
    if(cache){char cf[P];snprintf(cf,P,"%s/help_list.txt",DDIR);
        FILE*f=fopen(cf,"w");if(f){fputs(out,f);fclose(f);}
        snprintf(cf,P,"%s/i_cache.txt",DDIR);unlink(cf);}
}

/* d/n's 1st comment/docstring → "≤4-word desc · t": clause-cut, no dangling stopword/punct; """ over # */
static void d4(const char*d,const char*n,const char*t,char*o){char fp[P],l[256],c[256]="",*p,*s;snprintf(fp,P,"%s/%s",d,n);FILE*f=fopen(fp,"r");
    for(int i=0;f&&i<3&&fgets(l,256,f);i++){int q=!strncmp(l,"\"\"\"",3);
        if(q||(!*c&&((*l=='#'&&l[1]==' ')||(*l=='/'&&strchr("/*",l[1]))))){strcpy(c,l+2+q);if(q)break;}}
    if(f)fclose(f);p=strstr(c," — ");p=p?p+5:(p=strstr(c," - "))?p+3:c;p+=strspn(p," *");
    p[strcspn(p,":;(|\"\n")]=0;if((s=strstr(p,". ")))*s=0;{int w=4;s=p;while((s=strchr(s,' '))&&--w)s++;if(s)*s=0;}
    {char*z=p+strlen(p);if(z>p&&strchr(",.",z[-1]))z[-1]=0;}
    for(char b[24];(s=strrchr(p,' '))&&snprintf(b,24,"%s ",s)&&(s[1]<'!'||strstr(" a an and for in into of on the to via with ",b));)*s=0;
    snprintf(o,128,"%s%s%s",p,*p?" · ":"",t);}
static void gen_icache(void){
    load_proj();load_apps();load_cfg();load_sess();
    char ic[P],ds[128];snprintf(ic,P,"%s/i_cache.txt",DDIR);
    FILE*f=fopen(ic,"w");if(!f)return;
    fputs("a\tdefault agent\n",f);
    {char bf[P];snprintf(bf,P,"%s/bookmarks.txt",SROOT);size_t bl;char*bd=readf(bf,&bl);if(bd){fwrite(bd,1,bl,f);if(bl&&bd[bl-1]!='\n')fputc('\n',f);free(bd);}}
    int i;size_t hl=strlen(HOME);for(i=0;i<NPJ;i++){const char*pp=PJ[i].path;int th=!strncmp(pp,HOME,hl);fprintf(f,"%d: %s\tproject\tcd %.*s%s\n",i,PJ[i].name,th,"~",th?pp+hl:pp);
        DIR*sd=opendir(PJ[i].path);struct dirent*se;if(sd){while((se=readdir(sd)))if(se->d_name[0]!='.'&&se->d_type==DT_DIR)fprintf(f,"%s/%s\tdir\n",PJ[i].path,se->d_name);closedir(sd);}}
    for(i=0;i<NAP;i++)fprintf(f,"%d: %s\tcmd\t%s\n",NPJ+i,AP[i].name,AP[i].cmd);
    for(i=0;i<NSE;i++)fprintf(f,"%s\tnew %s window\n",SE[i].key,SE[i].name);
#ifdef __ANDROID__
    {char af[P];snprintf(af,P,"%s/local/apps.txt",AROOT);
    size_t al;char*ad=readf(af,&al);if(ad){fwrite(ad,1,al,f);free(ad);}}
#endif
    {char ad[P];snprintf(ad,P,"%s/lib/platonic_agents",SDIR);DIR*d=opendir(ad);struct dirent*e;
    if(d){while((e=readdir(d))){char*p=strrchr(e->d_name,'.');
        if(p&&(p[1]=='p'||p[1]=='c')){*p=0;fprintf(f,"agent run %s\tagent\n",e->d_name);}}closedir(d);}}
    /* auto-discover lib .py — extract docstring desc */
    {char ld[P];snprintf(ld,P,"%s/lib",SDIR);DIR*d=opendir(ld);struct dirent*e;
    if(d){while((e=readdir(d))){char*dot=strrchr(e->d_name,'.');
        if(!dot||strcmp(dot,".py")||e->d_name[0]=='_')continue;d4(ld,e->d_name,"cmd",ds);*dot=0;
        fprintf(f,"%s\t%s\n",e->d_name,ds);}closedir(d);}}
    /* auto-discover my + lab + repos scripts */
    {const char*sr[]={SROOT,SDIR};const char*sl[]={"my","lab"};
    for(int si=0;si<2;si++){char md[P];snprintf(md,P,"%s/%s",sr[si],sl[si]);DIR*d=opendir(md);struct dirent*e;
    if(d){while((e=readdir(d))){if(e->d_name[0]=='.'||e->d_name[0]=='_')continue;
        char nm[64];snprintf(nm,64,"%s",e->d_name);char*dot=strrchr(nm,'.');
        if(si&&(!dot||(strcmp(dot,".py")&&strcmp(dot,".c")&&strcmp(dot,".sh")&&strcmp(dot,".html"))))continue;
        const char*tg=!si&&dot&&!strcmp(dot,".html")?"page":sl[si];if(!si&&dot)*dot=0;
        d4(md,e->d_name,tg,ds);fprintf(f,"%s\t%s\n",nm,ds);}closedir(d);}}
    /* repos: scan adata/repos/ scripts */
    {char rd[P];snprintf(rd,P,"%s/repos",AROOT);DIR*d=opendir(rd);struct dirent*re;
    if(d){while((re=readdir(d))){if(re->d_name[0]=='.')continue;
        char rp[P];snprintf(rp,P,"%s/%s",rd,re->d_name);DIR*sd=opendir(rp);struct dirent*se;
        if(sd){while((se=readdir(sd))){if(se->d_name[0]=='.'||se->d_name[0]=='_')continue;
            char*dot=strrchr(se->d_name,'.');
            if(dot&&(!strcmp(dot,".py")||!strcmp(dot,".c")||!strcmp(dot,".sh")))
                fprintf(f,"%.*s\t%s · repo\n",(int)(dot-se->d_name),se->d_name,re->d_name);}closedir(sd);}}closedir(d);}}}
    /* subcommands not discoverable from filenames */
    fputs("scp\tsend file to host\n"
    "diff\ttok diff vs main\ncat\twhole codebase as text\nfreq\tusage frequency\n"
    "perf\tcmd time caps\n"
    "ui\tweb dashboard\n"
    "web status\tLLM login status\nweb signin\tLLM auto sign-in\nweb log\tmanual sign-in mode\n"
    "hub add\tadd job\nhub run\trun job\nhub rm\tdrop job\nhub log\tjob logs\n"
    "note\tnotes\nnote l\tlist notes\nnote r\treview notes\nssh add\tadd host\nssh all\twindow per host\n"
    "prompt\tedit prompts\npow\tpower off/restart\npow o\tpower off\npow r\trestart\npow s\tsuspend\npow h\thibernate\n"
    "tutorial\tguided intro\noperator\tenglish → command\n",f);
    char sd[P];snprintf(sd,P,"%s/ssh",SROOT);
    char sp[32][P];int sn=listdir(sd,sp,32);
    for(i=0;i<sn;i++){kvs_t kv=kvfile(sp[i]);const char*nm=kvget(&kv,"Name"),*ho=kvget(&kv,"Host");
        if(nm)fprintf(f,"ssh %s\t%s%shost\n",nm,ho?ho:"",ho?" · ":"");}
#ifdef __APPLE__
    {const char*ad[]={"/Applications","/System/Applications"};
    for(int di=0;di<2;di++){DIR*d=opendir(ad[di]);if(!d)continue;struct dirent*e;
        while((e=readdir(d))){char*p=strstr(e->d_name,".app");
            if(p&&!p[4])fprintf(f,"open %.*s\tapp\n",(int)(p-e->d_name),e->d_name);}closedir(d);}
    fputs("open Finder\tapp\n",f);}
#else
    {char hp[P];snprintf(hp,P,"%s/.local/share/applications",HOME);
    const char*ad[]={"/usr/share/applications","/usr/local/share/applications",
        "/var/lib/flatpak/exports/share/applications",hp};
    for(int di=0;di<4;di++){const char*dp=ad[di];
        DIR*d=opendir(dp);if(!d)continue;struct dirent*e;
        while((e=readdir(d))){if(!strstr(e->d_name,".desktop"))continue;
            char fp[P],nm[128]="",ln[256];int ok=0;
            snprintf(fp,P,"%s/%s",dp,e->d_name);FILE*df=fopen(fp,"r");if(!df)continue;
            while(fgets(ln,256,df)){ln[strcspn(ln,"\n")]=0;
                if(!strncmp(ln,"Name=",5)&&!nm[0])snprintf(nm,128,"%s",ln+5);
                else if(!strcmp(ln,"Type=Application"))ok=1;
                else if(!strcmp(ln,"NoDisplay=true"))ok=0;}
            fclose(df);if(ok&&nm[0]){char dn[64];snprintf(dn,64,"%s",e->d_name);
                char*dd=strrchr(dn,'.');if(dd)*dd=0;
                fprintf(f,"open %s\t%s · app\n",dn,nm);}}
        closedir(d);}}
#endif
    fclose(f);
    if(!fork()){char ad[P],fp2[P],ln[256];snprintf(ad,P,"%s/local/activity",AROOT);
        char fc[P+64];snprintf(fc,sizeof(fc),"find '%s' -maxdepth 2 -name '*_*.txt' 2>/dev/null",ad);
        FILE*d=popen(fc,"r");if(!d)_exit(0);FC ct[1024]={0};int nc=0;
        while(fgets(fp2,P,d)){fp2[strcspn(fp2,"\n")]=0;FILE*af=fopen(fp2,"r");if(!af)continue;
            while(fgets(ln,256,af)){
            char*p=ln;for(int j=0;j<3&&*p;j++){while(*p&&*p!=' ')p++;while(*p==' ')p++;}
            char*end=p;while(*end&&*end!=' '&&*end!='\n')end++;
            if(*end==' '&&end[1]!='/'&&end[1]!='-'&&!memchr(p,':',(size_t)(end-p))){end++;while(*end&&*end!=' '&&*end!='\n')end++;}
            *end=0;if(!*p)continue;
            int j;for(j=0;j<nc;j++)if(!strcmp(ct[j].n,p)){ct[j].c++;break;}
            if(j==nc&&nc<1024){snprintf(ct[nc].n,64,"%s",p);ct[nc].c=1;nc++;}}
            fclose(af);}
        pclose(d);qsort(ct,(size_t)nc,sizeof(ct[0]),ctcmp);
        snprintf(fp2,P,"%s/freq_cache.txt",DDIR);
        FILE*ff=fopen(fp2,"w");if(ff){for(int j=0;j<nc;j++)if(ct[j].c>1)fprintf(ff,"%s:%d\n",ct[j].n,ct[j].c);fclose(ff);}  /* c==1 = one-shot noise: pollutes ranking + triples scoring buckets */
        {snprintf(fp2,P,"%s/web_cache.txt",DDIR);
        char cm[P*2];snprintf(cm,P*2,"T=/tmp/.a_h$$;Q=\"SELECT url,title FROM urls WHERE title<>'' ORDER BY visit_count DESC LIMIT 50\";"
#ifdef __APPLE__
            "for b in 'Google/Chrome' 'Google/Chrome Canary' 'BraveSoftware/Brave-Browser' "
            "'BraveSoftware/Brave-Browser-Beta' Chromium;do "
            "cp \"$HOME/Library/Application Support/\"$b'/Default/History' $T 2>/dev/null&&"
            "sqlite3 $T \"$Q\" 2>/dev/null;done;"
            "cp \"$HOME/Library/Safari/History.db\" $T 2>/dev/null&&"
            "sqlite3 $T \"SELECT h.url,v.title FROM history_items h,history_visits v WHERE h.id=v.history_item AND v.title<>'' ORDER BY h.visit_count DESC LIMIT 50\" 2>/dev/null;"
#else
            "for b in google-chrome google-chrome-unstable google-chrome-beta google-chrome-canary "
            "BraveSoftware/Brave-Browser-Beta chromium;do "
            "cp \"$HOME/.config/\"$b'/Default/History' $T 2>/dev/null&&"
            "sqlite3 $T \"$Q\" 2>/dev/null;done;"
#endif
            "rm -f $T");
        FILE*hf=popen(cm,"r");if(hf){char tp[P];snprintf(tp,P,"%s.tmp",fp2);FILE*wf=fopen(tp,"w");if(wf){
            unsigned char uh[4096]={0};char sl[1024];int nw=0;
            while(fgets(sl,1024,hf)){sl[strcspn(sl,"\n")]=0;
                char*u=sl,*t=strchr(sl,'|');if(!t)continue;*t++=0;
                char*hu=u;{char*s=strstr(u,"://");if(s){hu=s+3;if(!strncmp(hu,"www.",4))memmove(hu,hu+4,strlen(hu+4)+1);}}
                unsigned h=5381;for(char*p=hu;*p;p++)h=h*33+(unsigned char)*p;h%=32768;
                if(uh[h/8]&(1<<(h%8)))continue;uh[h/8]|=1<<(h%8);
                if(t[0]){fprintf(wf,"web %s\t%s · web\n",u,t);nw++;}}
            fclose(wf);if(nw)rename(tp,fp2);else unlink(tp);}  /* sticky: never wipe a good cache on a transient empty/locked query */
            pclose(hf);}}
        _exit(0);}
}

/* cached list: rescanning projects blew help's 879us budget. catf raw-write(2)s, so flush first */
static int help_p(const char*h){char p[P];snprintf(p,P,"%s/help_list.txt",DDIR);puts(h);fflush(stdout);
    if(catf(p)<0){init_db();load_cfg();list_all(1,0);}return 0;}
static int cmd_help(int c,char**v){(void)c;(void)v;return help_p(HELP_SHORT);}
static int cmd_help_full(int c,char**v){(void)c;(void)v;return help_p(HELP_FULL);}

static const char*PP="push just these changes, and stop if there is an issue with pushing and ask me how to proceed";   /* the [p] prompt; also sent by :1111/review "tell agent: push" */
static int cmd_done(int argc,char**argv){AB;
    char p[P],msg[B]="";snprintf(p,P,"%s/.done",DDIR);ajoin(msg,B,argc,argv,2);
    {FILE*f=fopen(p,"w");if(f){fputs(msg,f);fclose(f);}}
    {char wd[P];if(getcwd(wd,P)){char df[P];snprintf(df,P,"%s/.a_done",wd);
        FILE*f=fopen(df,"w");if(f){fputs(msg[0]?msg:"done",f);fclose(f);}}
        char lf[P];snprintf(lf,P,"%s/done.log",DDIR);char wi[128]="";const char*tp0=getenv("TMUX_PANE");   /* :1111/review (a review): one line per a done, ts, tmux window index, window name, dir, message. Per AGENT, not per repo (Sean 2026-09-03: many agents work one repo at once; .a_done above is per repo and overwrites) */
        if(tp0){char tc[256];snprintf(tc,256,"tmux display-message -p -t '%s' '#I\t#W' 2>/dev/null",tp0);FILE*tf=popen(tc,"r");if(tf){if(fgets(wi,128,tf))wi[strcspn(wi,"\n")]=0;pclose(tf);}}
        FILE*r=fopen(lf,"a");if(r){char*nm=strchr(wi,'\t');if(nm)*nm++=0;char em[B];int k=0;for(const char*q=msg[0]?msg:"done";*q&&k<B-1;q++)em[k++]=(*q=='\n'||*q=='\t')?' ':*q;em[k]=0;fprintf(r,"%ld\t%s\t%s\t%s\t%s\n",(long)time(NULL),wi,nm?nm:"",wd,em);fclose(r);}}   /* register this dir for :1111/review (a review) */
    if(getenv("TMUX")){char ts[B]="",dl[B]="",cu[B]="",dc[B]="",sp[P];const char*tp=getenv("TMUX_PANE");
        char ck[16];char*cc[16],*cx[16];int ncu=0;char*me=msg;
        #define TAG(o,t) {char*a=strstr(msg,"<"t">"),*b=a?strstr(a,"</"t">"):0;\
            if(a&&b){int n=(int)(b-a-(int)sizeof(t)-1);if(n>0&&n<B)snprintf(o,(size_t)n+1,"%s",a+sizeof(t)+1);if(b+sizeof(t)+2>me)me=b+sizeof(t)+2;}}
        TAG(ts,"test")TAG(dl,"diff")TAG(cu,"do")TAG(dc,"doc")   /* <doc>paths</doc>: documents for :1111/review to show (a review); stripped from the pane text like the others */
        #undef TAG
        while(*me==' '||*me==']')me++;int fl=(int)strcspn(dl," ");
        /* custom menu actions: <do>key::label::cmd||key::label::cmd</do> — menu prints the literal cmd, keypress runs it */
        for(char*ent=cu;*ent&&ncu<16;){char*nx=strstr(ent,"||");if(nx)*nx=0;
            char*p1=strstr(ent,"::"),*p2=p1?strstr(p1+2,"::"):0;
            if(p2){*p1=*p2=0;while(*ent==' ')ent++;ck[ncu]=*ent;cc[ncu]=p1+2;cx[ncu++]=p2+2;}
            if(!nx)break;ent=nx+2;}
        {char used[32]="pcseoyrnbv";   /* key colliding with built-ins/each other = both handlers fire on one press -> remap to first free */
            for(int i=0;i<ncu;i++){
                if(strchr(used,ck[i])){char o=ck[i];for(const char*q="123456789adfghijklmqtuvwxz";*q;q++)if(!strchr(used,*q)){ck[i]=*q;break;}
                    fprintf(stderr,"a done: key [%c] is built-in (p c s e o y r n b v) -> shown as [%c]; announce [%c]\n",o,ck[i],ck[i]);}
                used[strlen(used)]=ck[i];}}
        if(dl[0]){char cp[P];commit_path(cp);FILE*cf=fopen(cp,"w");if(cf){fprintf(cf,"%.*s\n%s\n",(int)strcspn(me,"\n"),me,dl);fclose(cf);}}
        char np[P];int dp=(int)getpid(); /* per-invocation: shared names let a later `a done` (other agent/project) clobber this pane's [r]/[n]/[b] */
        snprintf(sp,P,"%s/a_done_%d.sh",DDIR,dp);snprintf(np,P,"%s/a_next_%d.sh",DDIR,dp);
        FILE*sf=fopen(sp,"w");
        /* order = importance bottom-up (Sean 2026-08-31): a long pane isn't seen at once, the BOTTOM is —
           no scroll, so most important last. bottom→top: actions, diff (the real thing), test output (its
           output), agent report — least useful, not the real thing; maybe deleted later (undecided). */
        if(sf){fprintf(sf,"trap 'rm -f %s %s' EXIT\nAP='%s'\nw(){ printf '\\033[2many key to close\\033[0m';read -rsn1 </dev/tty;}\n",sp,np,tp?tp:"");fputs("echo '✓ done'\n",sf);
            if(*me)fprintf(sf,"printf '\\033[1;32m=== agent report ===\\033[0m\\n';cat<<'A_RPT'\n%s\nA_RPT\n",me);
            {FILE*nf=fopen(np,"w");if(nf){
                fprintf(nf,"EF=max;BOOK=\"\";BD='%s/books'\n[ \"$1\" = -i ]&&{ BOOK=$(ls -1 \"$BD\" 2>/dev/null|grep -v book.py|fzf --prompt='book (esc=none)> ' --height=40%% 2>/dev/null);read -p 'effort [max]: ' EF </dev/tty;EF=${EF:-max}; }\nprintf '\\033[1;36mgathering context, asking fable 5 (%%s)...\\033[0m\\n' \"$EF\"\n{ echo '=== CODE STATE ==='; a cat; echo; echo '=== DIFF ==='; a diff%s%s; echo; echo '=== PREVIOUS USER PROMPTS ==='; PJ=~/.claude/projects/$(pwd|sed 's#/#-#g'); ls -t \"$PJ\"/*.jsonl 2>/dev/null|head -1|xargs -r jq -r 'select(.type==\"user\" and (.message.content|type==\"string\"))|.message.content' 2>/dev/null; [ -n \"$BOOK\" ]&&{ echo; echo \"=== BOOK: $BOOK ===\"; cat \"$BD/$BOOK/output/explained.txt\" 2>/dev/null||cat \"$BD/$BOOK/output/transcript.txt\" 2>/dev/null; };",AROOT,dl[0]?" -- ":"",dl);
                if(ts[0])fprintf(nf," echo; echo '=== TEST CMD OUTPUT ==='; %s 2>&1;",ts);
                fprintf(nf," echo; echo '=== TASK ==='; cat '%s/common/prompts/next.txt'; } | claude -p --dangerously-skip-permissions --model claude-fable-5 --effort \"$EF\" --output-format stream-json --include-partial-messages --verbose 2>/dev/null | jq -jn --unbuffered 'foreach inputs as $e (0; if $e.event.delta.type==\"thinking_delta\" then .+$e.event.delta.estimated_tokens else . end; if $e.event.delta.type==\"thinking_delta\" then \"\\r\\u001b[2mthinking ~\\(.) tok\\u001b[0m   \" elif ($e.event.type==\"content_block_start\" and $e.event.content_block.type==\"text\") then \"\\n\\u001b[1;32m> \\u001b[0m\" elif $e.event.delta.type==\"text_delta\" then $e.event.delta.text else \"\" end)'\necho\nexec ${SHELL:-bash}\n",SROOT);fclose(nf);}}
            const char*CR="Crunch the code while keeping the same input output functionality exactly, reducing the number of tokens and verifying that with \"a diff\". Keep cutting until the code will break when cut more. Simplify and integrate logic as needed.";
            const char*KX="[ \"$k\" = %c ]&&{ tmux selectp -t $AP;tmux send -t $AP -X cancel 2>/dev/null;tmux send -t $AP -l '%s';sleep 0.4;tmux send -t $AP Enter; }\n"; /* copy-mode eats sent keys ('g'=goto-line) — cancel first */
            if(ts[0])fprintf(sf,"TS=$(cat<<'A_DONE'\n%s\nA_DONE\n)\nprintf '\\033[1;36m=== test output (auto-run \\xc2\\xb7 [r] re-runs) ===\\033[0m\\n\\033[1;33m$ \\033[0m%%s\\n' \"$TS\"\neval \"$TS\" 2>&1\n",ts);
            else fputs("printf '\\033[2mno test command\\033[0m\\n'\n",sf);
            fputs("printf '\\033[1;36m=== diff ===\\033[0m\\n';D=$(a diff 2>&1);printf '%s\\n' \"$D\";TK=$(printf '%s\\n' \"$D\"|grep -aE '^(net|fork):'|tail -1)\n",sf);
            if(dl[0])fprintf(sf,"printf '\\033[1;36m=== focused diff: %s ===\\033[0m\\n';a diff -- %s\n",dl,dl);
            fputs("while :;do\n",sf);
            fputs("[ -n \"$TK\" ]&&printf '%s\\n' \"$TK\"\n",sf);  /* tok line glued to actions: visible with no scroll (2026-08-30 intent kept) */
            fputs("if [ -z \"$M\" ];then printf '\\033[1;37m=== actions (key) ===\\033[0m\\n'\n",sf);
            if(dl[0]&&tp)fputs("printf '\\033[1;37m[p]\\033[0m tell agent to push (it commits + pushes its own changes)\\n'\n",sf);
            if(dl[0])fprintf(sf,"printf '\\033[1;37m[y]\\033[0m direct push, these files only: git add+commit -- %s && git push   (whole repo = a push)\\n'\n",dl);   /* the human's own paths-only push, first-class (Sean 09-04): distinct from telling the agent, distinct from a whole-repo a push */
            if(tp)fputs("printf '\\033[1;37m[c]\\033[0m crunch the code\\n\\033[1;37m[e]\\033[0m talk to agent\\n'\n",sf);
            fprintf(sf,"printf '\\033[1;37m[v]\\033[0m edit: %%s/%.*s\\n' \"$PWD\"\n",fl,dl);
            for(int i=0;i<ncu;i++)fprintf(sf,"printf '\\033[1;37m[%c]\\033[0m %%s: %%s\\n' '%s' '%s'\n",ck[i],cc[i],cx[i]);
            fputs("printf '\\033[1;37m[o]\\033[0m more\\n'\nelse printf '\\033[1;37m=== more (key) ===\\033[0m\\n'\n",sf);
            if(ts[0])fputs("printf '\\033[1;37m[r]\\033[0m re-run test\\n'\n",sf);
            fputs("printf '\\033[1;37m[n]\\033[0m suggest next step (opus)\\n'\nprintf '\\033[1;37m[b]\\033[0m suggest next + book/effort\\n'\nfi\n",sf);
            fputs("printf '\\033[1;37m[s]\\033[0m bash shell here (your own testing) \\033[2m· other key=close\\033[0m '\nread -rsn1 k </dev/tty;echo\n",sf);
            if(dl[0])fputs("[ \"$k\" = y ]&&{ A_PANE=$AP a push -f;w;}\n",sf);
            if(dl[0]&&tp)fprintf(sf,KX,'p',PP);
            if(tp)fprintf(sf,KX,'c',CR);
            if(ts[0])fputs("[ \"$k\" = r ]&&{ printf '\\033[1;33m$ \\033[0m%s\\n' \"$TS\";eval \"$TS\" 2>&1;}\n",sf);
            fprintf(sf,"[ \"$k\" = n ]&&tmux splitw -v -t \"$TMUX_PANE\" 'sh %s'\n",np);
            fprintf(sf,"[ \"$k\" = b ]&&tmux splitw -v -t \"$TMUX_PANE\" 'sh %s -i'\n",np);
            fputs("[ \"$k\" = s ]&&exec ${SHELL:-bash}\n",sf);
            if(tp)fputs("[ \"$k\" = e ]&&tmux selectp -t $AP\n",sf);
            fprintf(sf,"[ \"$k\" = v ]&&${EDITOR:-e} %.*s\n",fl,dl);
            for(int i=0;i<ncu;i++)fprintf(sf,"[ \"$k\" = %c ]&&{ %s;w;}\n",ck[i],cx[i]);
            fputs("case \"$k\" in o) M=1;; r|n|b|v) ;; *) break;; esac\ndone\n",sf);
            fclose(sf);
            char c[P*2];
            /* unify into ONE pane: clear prior output panes (keep the agent pane), then split one */
            if(tp){snprintf(c,P*2,"tmux killp -a -t '%s' 2>/dev/null",tp);(void)!system(c);}
            snprintf(c,P*2,"tmux splitw -v -l 70%% -t '%s' 'bash %s' 2>/dev/null",tp?tp:"",sp);(void)!system(c);}}
    (void)!write(STDERR_FILENO,"\a",1);
    puts("✓ done");return 0;}

static int cmd_dir(int c,char**v){(void)c;(void)v;char w[P];if(getcwd(w,P))puts(w);fflush(0);execlp("ls","ls",(char*)0);return 1;}  /* exec drops the buffer: unflushed, the cwd line is lost when stdout isn't a tty */
static int cmd_x(int c,char**v){
    if(!tmux_kill_gate("x",isatty(0)||(c>2&&!strcmp(v[2],"now"))))return 1;
    (void)!system("tmux kill-serv 2>/dev/null");puts("✓ All sessions killed");return 0;}
static int cmd_search(int c,char**v){AB;char u[B];
    int l=snprintf(u,B,"https://google.com%s",c>2?"/search?q=":"");
    for(int i=2;i<c&&l<B-1;i++)l+=snprintf(u+l,(size_t)(B-l),"%s%s",i>2?"+":"",v[i]);
    bg_exec(OPENER,u);return 0;}
