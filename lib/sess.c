#include <poll.h>
static int cmd_sess(int argc, char **argv) {
    init_db(); load_cfg(); load_proj(); load_apps(); load_sess();
    const char *key = argv[1];
    sess_t *s = find_sess(key);
    if (!s) return -1;  /* not a session key */
    perf_disarm();  /* sessions exec into long-running TUIs; perf timer is for `a` itself */
    CWD(wd);
    const char *wda = argc > 2 ? argv[2] : NULL;
    /* If wda is a project number */
    if (wda && wda[0] >= '0' && wda[0] <= '9') {
        int idx = atoi(wda);
        if (idx >= 0 && idx < NPJ) snprintf(wd, P, "%s", PJ[idx].path);
        else if (idx >= NPJ && idx < NPJ + NAP) {
            printf("> Running: %s\n", AP[idx-NPJ].name);
            const char *sh = getenv("SHELL"); if (!sh) sh = "/bin/bash";
            execlp(sh, sh, "-c", AP[idx-NPJ].cmd, (char*)NULL);
        }
    } else if (wda && dexists(wda)) {
        if (wda[0] == '~') snprintf(wd, P, "%s%s", HOME, wda+1);
        else snprintf(wd, P, "%s", wda);
    }
    /* Build prompt from remaining args */
    char prompt[B]=""; int is_prompt=0,pl=0;
    int start = wda ? 3 : 2;
    if (wda && !(wda[0]>='0'&&wda[0]<='9') && !dexists(wda)) { start = 2; is_prompt = 1; }
    for (int i = start; i < argc; i++) {
        if (!strcmp(argv[i],"-w")||!strcmp(argv[i],"--new-window")||!strcmp(argv[i],"-t")||!strcmp(argv[i],"--with-terminal")) continue;
        pl+=snprintf(prompt+pl,(size_t)(B-pl),"%s%s",pl?" ":"",argv[i]);
        is_prompt = 1;
    }
    const char*sn=tm_name(s->name,bname(wd),time(0)),*xp=is_prompt?prompt:NULL;   /* tm_name never returns a taken name, so the old attach-existing branch was unreachable: gone */
    if (create_sess(sn, wd, s->cmd, xp) != 2) { if(isatty(1))tm_go(sn);
        else {char q[160],wi[16]="?";snprintf(q,160,"tmux list-windows -t '" TMS "' -f '#{==:#{window_name},%s}' -F '#{window_index}' 2>/dev/null",sn);pcmd(q,wi,16);wi[strcspn(wi,"\n")]=0;
            printf("→ win %s · %s\n  tmux attach -t " TMS ":%s\n",wi[0]?wi:"?",sn,wi[0]?wi:sn);} }
    return 0;
}

static int cmd_dir_file(int argc, char **argv) { (void)argc;
    perf_disarm();  /* ITIMER_REAL survives exec: armed timer SIGALRM-kills the editor/viewer ~1s in */
    const char *arg = argv[1];
    char expanded[P];
    if (arg[0] == '~') snprintf(expanded, P, "%s%s", HOME, arg+1);
    else snprintf(expanded, P, "%s", arg);
    if (!dexists(expanded)&&!fexists(expanded)&&arg[0]=='/') snprintf(expanded,P,"%s%s",HOME,arg);
    if (dexists(expanded)) { printf("%s\n", expanded); execlp("ls", "ls", expanded, (char*)NULL); }
    else if (fexists(expanded)) {
        const char *ext = strrchr(expanded, '.');
        if (ext && !strcmp(ext, ".py")) {
            char py[P]="python3"; const char *ve=getenv("VIRTUAL_ENV");
            if(ve) snprintf(py,P,"%s/bin/python",ve);
            else if(!access(".venv/bin/python",X_OK)) snprintf(py,P,".venv/bin/python");
            execvp(py, (char*[]){ py, expanded, NULL });
        }
        else{int t=ext?ext[1]:0;const char*ed=t=='c'||t=='s'?"sh":t=='h'?OPENER:getenv("EDITOR");
            if(!ed)ed="e";execlp(ed,ed,expanded,(char*)NULL);}
    }
    return 0;
}

static FC fq[1024];static int nfq;
/* first-char index: a freq entry can only be a prefix of a line if their first chars match (case-insensit),
 * so bucket entries by lowercased first char and scan only that bucket — provably identical result, O(bucket)
 * not O(nfq). Most file/dir lines hit an empty bucket → instant. */
static int fqhead[256];static int fqnext[1024];static unsigned char fqlen[1024];
static void fq_index(void){for(int z=0;z<256;z++)fqhead[z]=-1;
    for(int i=0;i<nfq;i++){fqlen[i]=(unsigned char)strlen(fq[i].n);int c=(unsigned char)fq[i].n[0];if(c>='A'&&c<='Z')c+=32;fqnext[i]=fqhead[c];fqhead[c]=i;}}
static int fq_get(const char*s){int b=0,bl=0;int c=(unsigned char)s[0];if(c>='A'&&c<='Z')c+=32;
    for(int i=fqhead[c];i>=0;i=fqnext[i]){int l=fqlen[i];if(l>bl&&!strncasecmp(s,fq[i].n,(size_t)l)&&(!s[l]||s[l]=='\t')){b=fq[i].c;bl=l;}}return !strncmp(s,"home\t",5)?0x7fffffff:strstr(s,"\tproject")||(s[0]>='0'&&s[0]<='9'&&strstr(s,"\tcmd"))?(1<<30)-atoi(s):b;}  /* numbered user cmds pin with projects (digit gate: lib .py default tag is also "cmd") */
typedef struct{char*s;int k,i;}LNK;  /* decorate-sort: fq_get is O(nfq); call it once per line, not per qsort comparison */
static int lnk_cmp(const void*a,const void*b){const LNK*x=a,*y=b;return x->k!=y->k?y->k-x->k:x->i-y->i;}
/* i_frame: last run's first frame (winsize header + alt-enter + bytes), blasted by main() before any init
 * so the menu is visible at exec-floor speed (~0.3ms); the real render overwrites it ~1ms later, invisibly.
 * Replaces the old i_sorted data memo — caching pixels beats caching the sorted list. */
static int ifr_on;static double ifr_ms;  /* ifr_ms = when pixels hit the pty (true time-to-visible, shown as "seen") */
static void ifr_blast(void){struct winsize w;char p[P];size_t l;
    if(ioctl(1,TIOCGWINSZ,&w))return;snprintf(p,P,"%s/i_frame.%dx%d",DDIR,w.ws_row,w.ws_col);char*f=readf(p,&l);
    if(f&&l){(void)!write(1,f,l);ifr_on=1;
        struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);ifr_ms=(double)(t.tv_sec-T0.tv_sec)*1e3+(double)(t.tv_nsec-T0.tv_nsec)/1e6;}
    free(f);}
static int cmd_i(int argc, char **argv) { (void)argc; (void)argv;
    AB;
    perf_disarm(); init_db(); load_cfg();
    CWD(cwd);
    char cache[P],wc[P];snprintf(cache,P,"%s/i_cache.txt",DDIR);snprintf(wc,P,"%s/win_cache.txt",DDIR);time_t wcm=0;
    {struct stat c,s;char q[P];const char*F[]={"%s/bookmarks.txt","%s/ssh","%s/workspace/cmds","%s/workspace/projects","%.0s%s/.local/share/applications","%.0s/usr/share/applications"};  /* regen when a source is newer; >= = same-second; %.0s eats SROOT; dirs: mtime bumps on add/rm/rename incl. sync pulls */
    if(!stat(cache,&c))for(int i=0;i<6;i++){snprintf(q,P,F[i],SROOT,HOME);if(!stat(q,&s)&&s.st_mtime>=c.st_mtime){unlink(cache);break;}}}
    char*lines[2048];int n=0;const char*ft0=getenv("A_FILT_TAG");
    size_t len=0;char*raw=0;
    struct winsize ws;
    struct termios old,raw_t;
    if(isatty(0)){tcgetattr(STDIN_FILENO,&old);raw_t=old;
    raw_t.c_lflag&=~(tcflag_t)(ICANON|ECHO|ISIG);raw_t.c_cc[VMIN]=1;raw_t.c_cc[VTIME]=0;
    tcsetattr(STDIN_FILENO,TCSANOW,&raw_t);if(!ifr_on)write(STDOUT_FILENO,"\033[?1049h\033[?1000h\033[?1006h\033[?2004h",32);}
    int bcap=1024,blen=0,sel=0,pnm=-1,rotate=0,cfgmode=0,paste=0,sv=1;char*buf=calloc(1,(size_t)bcap);char prefix[256]="",jstat[96]="",lastwin[16]="",lastidx[8]="",lastpr[192]="",ltl[600]="",lastnote[P]="";time_t lastfire=0;
    static char*ICFG[]={"agent claude","agent codex","effort low","effort medium","effort high","effort max","effort xhigh",0};
    struct timespec tk=T0; const char*act="render";  /* tk = per-frame timer (first paint = cold render since T0; after a key = key→repaint); act = WHAT produced this frame, so the footer says what it just measured */
    bld:n=0;free(raw);  /* detached regen lands AFTER our read → mtime flip re-enters (typed buf survives): first launch matches live convo */
    {
    raw=readf(cache,&len);
    if(!raw){gen_icache();raw=readf(cache,&len);if(!raw)return 1;}
    {char fp[P];snprintf(fp,P,"%s/freq_cache.txt",DDIR);FILE*ff=fopen(fp,"r");if(ff){char ln[128];nfq=0;
        while(nfq<1024&&fgets(ln,128,ff)){char*c=strchr(ln,':');if(!c)continue;*c=0;
            snprintf(fq[nfq].n,64,"%s",ln);fq[nfq].c=atoi(c+1);nfq++;}fclose(ff);}}
    fq_index();
    for(char*p=raw,*end=raw+len;p<end&&n<2048;){char*nl=memchr(p,'\n',(size_t)(end-p));
        if(!nl)nl=end;if(nl>p&&!strchr("<=>#",*p)){*nl=0;lines[n++]=p;}p=nl+1;}
    {char wp[P];snprintf(wp,P,"%s/web_cache.txt",DDIR);size_t wl;static char*wr;free(wr);wr=readf(wp,&wl);
     if(wr)for(char*p=wr,*e=wr+wl;p<e&&n<2048;){char*nl=memchr(p,'\n',(size_t)(e-p));
        if(!nl)nl=e;if(nl>p){*nl=0;lines[n++]=p;}p=nl+1;}}
    static char wb[65536];size_t wl=0;
    {/* win rows (bare menu AND a-tmux view): fork-free read of one rich cache — NAME\twin\t@id START · …in-order tail of last output — detached ≤1/s bg regen keeps it warm. -t TMS not -a: grouped a-<pid> sessions re-list the same windows. START = first-pane pid birth (a done splits excluded; restored wins = restore time) */
        size_t cl;char*cw=readf(wc,&cl);
        if(cw){if(cl>65535)cl=65535;memcpy(wb,cw,cl);wb[cl]=0;wl=cl;free(cw);}
        else{pcmd("tmux lsw -t '"TMS"' -F '#W\twin' 2>/dev/null",wb,65536);wl=strlen(wb);}  /* first run: names now, rich on the mtime flip */
        struct stat st;int sr=stat(wc,&st);wcm=sr?0:st.st_mtime;if(sr||time(0)-st.st_mtime>=1){if(fork()==0){setsid();int dn=open("/dev/null",O_WRONLY);if(dn>=0){dup2(dn,1);dup2(dn,2);}
            char cm[P*3];snprintf(cm,sizeof cm,
                "td=$(date +%%b%%e|tr -d ' ');tmux lsp -s -t '"TMS"' -F '#{window_id} #{pane_id} #{pane_pid} #{window_name} #{pane_start_command}' 2>/dev/null|while read -r i d p w sc;do "
                "[ \"$i\" = \"$li\" ]&&continue;li=$i;"
                "st=$(ps -o lstart= -p \"$p\" 2>/dev/null|awk -v td=\"$td\" '{split($4,T,\":\");h=T[1]+0;a=h<12?\"a\":\"p\";h=h%%12;if(!h)h=12;t=sprintf(\"%%d%%02d%%s\",h,T[2],a);if(($2 $3)==td)print t;else print $2 $3\" \"t}');"
                "tl=$(tmux capturep -pJt \"$d\" -S -50 2>/dev/null|awk '{gsub(/^ +| +$/,\"\")}!/[a-z]/||/tokens|bypass|esc to interrupt|for shortcuts/{next}/^[^a-zA-Z0-9]/&&/ for [0-9]+[ms]/{next}{L[++i]=$0}END{s=\"\";for(j=i>8?i-7:1;j<=i;j++)s=s (s==\"\"?\"\":\" \")L[j];gsub(/\\(disable recaps in \\/config\\)/,\"\",s);gsub(/current: [0-9.]+ · latest: [0-9.]+/,\"\",s);gsub(/  +/,\" \",s);gsub(/ +$/,\"\",s);n=length(s);b=200;if(n>b){p=n-b+2;q=index(substr(s,p,30),\" \");if(q)p+=q;print \"…\"substr(s,p)}else print s}');"
                "sid=$(printf %%s \"$sc\"|grep -oE '[0-9a-f-]{36}'|head -1);sb=;"  /* convo-word bag mid-desc: filter sees it, display's middle-elision hides it. sid from --resume argv → transcript user-words; else deep scrollback */
                "[ -n \"$sid\" ]&&sb=$(tail -c 400000 \"$HOME\"/.claude/projects/*/\"$sid\".jsonl 2>/dev/null|grep -o '\"role\":\"user\",\"content\":\"[^\"]\\{3,200\\}'|tail -25|cut -c26-|tr -cs 'A-Za-z0-9' '\\n'|awk '!s[$0]++'|tr '\\n' ' '|cut -c1-900);"
                "[ -n \"$sb\" ]||sb=$(tmux capturep -pJt \"$d\" -S -1500 2>/dev/null|tr -cs 'A-Za-z0-9' ' '|tail -c 400);"
                "printf '%%s\twin\t%%s%%s · %%s %%s\n' \"$w\" \"$i\" \"${st:+ $st}\" \"$sb\" \"$tl\";done >'%s.%ld'&&mv '%s.%ld' '%s'",wc,(long)getpid(),wc,(long)getpid(),wc);
            execlp("sh","sh","-c",cm,(char*)0);_exit(0);}}}
    for(char*p=wb,*e=wb+wl;p<e&&n<2048;){char*nl=memchr(p,'\n',(size_t)(e-p));
        if(!nl)nl=e;if(nl>p){*nl=0;lines[n++]=p;}p=nl+1;}
    {static char*acts[]={"home\tssh into homebox","tmux split-window\tpane\tnew pane below","tmux new-window\twin\topen new window","tmux kill-pane\tpane\tclose this pane","tmux kill-window\twin\tclose this window","tmux detach\tquit\tdetach, session keeps running","tmux kill-session\tquit\tkill session + windows","tmux resize-pane -Z\tpane\ttoggle pane zoom","tmux set synchronize-panes\tpane\ttoggle sync all panes",
        "m main\tm\topen main m.txt","m new\tm\tnew agent file in agent/","m archive\tm\tarchive whole m.txt + push","m archive turn\tm\ttrim last turn","m archive undo\tm\trevert last archive","m restart\tm\tkill+respawn window (reload layout)","m edit\tm\topen m.txt in e",
        "m agent claude\tm\tswitch to Claude","m agent codex\tm\tswitch to Codex (GPT)","m agent gemini\tm\tswitch to Gemini",
        "m model opus\tm\tClaude Opus (1M ctx, deepest)","m model sonnet\tm\tClaude Sonnet (fast/cheap)","m model haiku\tm\tClaude Haiku (fastest)","m model gpt-5\tm\tCodex GPT-5","m model gpt-5.5\tm\tCodex GPT-5.5",
        "m model gemini-2.5-flash\tm\tGemini Flash","m model gemini-2.5-pro\tm\tGemini Pro","m model gemini-3-pro-preview\tm\tGemini 3 Pro preview",
        "m effort low\tm\tlow reasoning effort","m effort medium\tm\tmedium effort","m effort high\tm\thigh effort","m effort max\tm\tmax (Claude only)","m effort xhigh\tm\txhigh (Codex only)",
        "m tier default\tm\tdefault tier","m tier fast\tm\tpriority/fast tier","m tier flex\tm\tflex tier (cheap, slow)",0};
    for(int i=0;acts[i]&&n<2048;i++)lines[n++]=acts[i];}
    {static LNK lk[2048];for(int i=0;i<n;i++){lk[i].s=lines[i];lk[i].k=fq_get(lines[i]);lk[i].i=i;}
     qsort(lk,(size_t)n,sizeof*lk,lnk_cmp);for(int i=0;i<n;i++)lines[i]=lk[i].s;}
    }
    {char*t;int j=0;
    if(ft0){for(int i=0;i<n;i++){if((t=strchr(lines[i],'\t'))){
        char tg[64];char*t2=strchr(t+1,'\t');size_t tl=t2?(size_t)(t2-t-1):strlen(t+1);
        if(tl>63)tl=63;memcpy(tg,t+1,tl);tg[tl]=0;
        if(strstr(ft0,tg))lines[j++]=lines[i];}}n=j;}}
    int m_mode=ft0&&!strcmp(ft0,"m");
    if(!isatty(STDIN_FILENO)){for(int i=0;i<n;i++)puts(lines[i]);free(raw);return 0;}
    #define BFIT do{if(blen+2>bcap){bcap*=2;buf=realloc(buf,(size_t)bcap);}}while(0)  /* heap buf: paste of any length */
    #define SNIP do{int k2=blen<191?blen:191;if(k2<blen)while(k2>0&&(buf[k2]&0xC0)==0x80)k2--;for(int k=0;k<k2;k++)lastpr[k]=buf[k]=='\n'||buf[k]=='\t'?' ':buf[k];lastpr[k2]=0;}while(0)  /* receipt snippet: head of what went, UTF-8-safe cut */
    #define IRST write(STDOUT_FILENO,"\033[?1000l\033[?1006l\033[?2004l",24);tcflush(STDIN_FILENO,TCIFLUSH);tcsetattr(STDIN_FILENO,TCSANOW,&old);(void)!write(STDOUT_FILENO,"\033[?1049l",8);free(raw);free(buf)
    while (1) {
        {struct stat st;if(!stat(wc,&st)&&st.st_mtime!=wcm)goto bld;}
        ioctl(STDOUT_FILENO,TIOCGWINSZ,&ws);int maxshow=ws.ws_row>8?ws.ws_row-(m_mode?6:5):10;  /* +2: input-box rules */
        char*fm[2048]; int nm=0,ex=0,plen=(int)strlen(prefix);
        char*fb=buf;int fl=blen;if(fl>2&&*fb=='a'&&fb[1]==' '){fb+=2;fl-=2;}  /* he types the cmd he means: "a app" head-matches `app`; plain "app" unchanged */
        if(cfgmode){for(int i=0;ICFG[i]&&nm<2048;i++){if(blen&&!strcasestr(ICFG[i],fb))continue;fm[nm++]=ICFG[i];}}
        else for (int i=0;i<n&&nm<2048&&blen<256;i++) {  /* paste-scale buf can't be a filter (b2 cap) → prompt row only */
            if (plen && strncmp(lines[i], prefix, (size_t)plen)) continue;
            if(!blen&&(strstr(lines[i],"\tdir")||(!strncmp(lines[i],"web ",4)&&!strstr(lines[i]," · bm"))))continue;
            if(blen){char*s=lines[i]+plen,b2[256],*w;strcpy(b2,fb);int ok=1;
                for(w=strtok(b2," ");w&&ok;w=strtok(0," "))if(!strcasestr(s,w))ok=0;if(!ok)continue;
                if(s[fl]<=' '&&!strncasecmp(s,fb,(size_t)fl)){memmove(fm+ex+1,fm+ex,sizeof*fm*(size_t)(nm++-ex));fm[ex++]=lines[i];continue;}}
            fm[nm++]=lines[i];
        }
        const char*ag=cfget("i_agent");if(!*ag)ag="claude";const char*ef=cfget("i_effort");if(!*ef)ef=strstr(ag,"codex")?"xhigh":"max";
        int na=(lastwin[0]&&!cfgmode&&!blen&&!plen)?1:0,nn=(lastnote[0]&&!cfgmode&&!blen&&!plen)?2:0,pv=(blen&&!plen&&!cfgmode)?4:0,vo=na+nn+pv,tot=nm+vo;  /* virtual rows: last-win switch OR note/task receipt OR prompt actions; na/nn exclusive (last action wins) */
        if(rotate){sel=nm==pnm?sel+1:vo;if(!nm)sel=0;rotate=0;}pnm=nm;  /* keystroke that doesn't narrow (same nm) disambiguated nothing → next candidate; narrowed → first match; no match → claude row, never rotates into note/task/web */
        if(sel>=tot)sel=tot?tot-1:0;
        int fresh=lastfire&&time(0)-lastfire<180;if(!fresh)ltl[0]=0;  /* fired-win live tail: last 2 pane lines, refreshed by the poll below for 3min, then collapses */
        char*tl1=0,*tl2=0;int ll1=0,ll2=0;if(na){char*p2=ltl;while(*p2&&!tl2){char*e2=strchr(p2,'\n');int L2=e2?(int)(e2-p2):(int)strlen(p2);
            if(L2){if(!tl1){tl1=p2;ll1=L2;}else{tl2=p2;ll2=L2;}}if(!e2)break;p2=e2+1;}}
        int xtra=na?(tl2?2:(tl1||fresh)?1:0):0;  /* receipt rows under the switch row (snippet rides the row itself) */
        int hdr_rows=0;char hl[2048];int hll=0,Wc=ws.ws_col?ws.ws_col:80;
        if(m_mode){load_cfg();const char*cm=cfget("m_model");if(!*cm)cm="claude-fable-5";
            const char*cg=cfget("m_agent");if(!*cg)cg="claude";
            const char*cf=cfget("m_effort");if(!*cf)cf="low";
            struct stat st;long tsz=0;char hp[P];
            snprintf(hp,P,"%s/m/m.txt",SDIR);if(!stat(hp,&st))tsz+=st.st_size;
            snprintf(hp,P,"%s/local/a_cat.txt",AROOT);if(!stat(hp,&st))tsz+=st.st_size;
            snprintf(hp,P,"%s/mem/index.txt",SROOT);if(!stat(hp,&st))tsz+=st.st_size;
            snprintf(hp,P,"%s/m_status",DDIR);char*ms=readf(hp,NULL);
            if(ms)ms[strcspn(ms,"\n")]=0;
            hll=snprintf(hl,2048,"tok %ldk %s -m %s eff=%s%s%s",tsz/4/1000,cg,cm,cf,ms&&*ms?" │ ":"",ms?ms:"");
            free(ms); hdr_rows=hll>0?(hll+Wc-1)/Wc:1;}
        int em=m_mode?(ws.ws_row>hdr_rows+5?ws.ws_row-hdr_rows-5:1):maxshow;  /* -2 more: input box rules */
        int avail=em-vo-xtra>0?em-vo-xtra:1,ms=sel-vo,selm=ms<0?0:ms>=nm?(nm?nm-1:0):ms;
        int top=selm>=avail?selm-avail+1:0, show=nm-top<avail?nm-top:avail;
        double fms;{struct timespec _n;clock_gettime(CLOCK_MONOTONIC,&_n);fms=(_n.tv_sec-tk.tv_sec)*1e3+(_n.tv_nsec-tk.tv_nsec)/1e6;}
        {char rb[B*4];int rl=0;
        #define FP(...) rl+=snprintf(rb+rl,rl<B*4?(size_t)(B*4-rl):0,__VA_ARGS__)
        FP("\033[H\033[?25l");
        if(m_mode){int p=0;
            do{int ch=(hll-p)>Wc?Wc:(hll-p);
                FP("\033[36m%.*s\033[0m\033[K\n",ch,hl+p);
                p+=ch?ch:1;
            }while(p<hll);}
        int Wr=ws.ws_col>8?ws.ws_col:80,ccol=plen+blen+3;char hint[320]="";  /* input BOX: bar above+below the > line → safe to type long (prompts, note text) */
        #define RULE do{for(int _r=0;_r<Wr;_r++)FP("─");FP("\033[K\n");}while(0)
        RULE;
        if(cfgmode)FP("config> %s\033[90m  pick agent / effort · ESC back\033[0m\033[K\n",buf);
        else if(jstat[0]&&!blen&&!plen)FP("> \033[90m%s · \033[37m%s %.3fms\033[0m\033[K\n",jstat,act,fms);
        else if(!blen&&!plen){char sn2[32]="";if(ifr_ms>0)snprintf(sn2,32,"seen %.3f · ",ifr_ms);
            FP("> \033[90m↵ home · type to filter · ^G config · \033[37m%s%s %.3fms\033[0m\033[K\n",sn2,act,fms);}
        else{int W=ws.ws_col?ws.ws_col:80,aw=W-plen-4,off=0,cw=0;char cnt[24]="";  /* one row, tail-anchored: end stays visible; Nc count = proof the whole paste landed */
            if(aw>440)aw=440;if(aw<8)aw=8;
            if(blen>aw){cw=snprintf(cnt,24,"%dc…",blen)-2;aw-=cw;if(aw<8)aw=8;off=blen-aw;while(off<blen&&(buf[off]&0xC0)==0x80)off++;}
            char vis[512];int vl=0;for(int k=off;k<blen;k++,vl++)vis[vl]=(char)(buf[k]=='\n'||buf[k]=='\t'?' ':buf[k]);vis[vl]=0;
            FP("%s> \033[90m%s\033[0m%s\033[K\n",plen?prefix:"",cnt,vis);ccol=plen+3+cw+vl;
            if(!plen){int hw=W-31-(int)strlen(ag)-(int)strlen(ef);if(hw<8)hw=8;if(hw>vl)hw=vl;  /* live tail-follow, … marks the cut */
                snprintf(hint,320,"↵ new tmux win → %s eff=%s : \"%s%s\"",ag,ef,blen>hw?"…":"",vis+vl-hw);}}
        RULE;
        #undef RULE
        if(hint[0]){FP("%s \033[%dm%s\033[0m\033[K\n",sel?"  ":" >",sel?90:37,hint);  /* prompt row: selectable, bright when picked */
            static const char*PV[]={"✎ save note","☐ add task","⌕ web search"};
            for(int r=1;r<pv;r++)FP("%s \033[%dm%s\033[0m\033[K\n",sel==r?" >":"  ",sel==r?37:90,PV[r-1]);}
        if(na){int pl2=(int)strlen(lastpr),mx=Wc-22;if(mx<8)mx=8;int cut=pl2>mx;if(cut){pl2=mx;while(pl2>0&&(lastpr[pl2]&0xC0)==0x80)pl2--;}
            FP("%s \033[36m⮌ switch → win %s · %.*s%s\033[0m\033[K\n",sel==0?" >":"  ",lastidx,pl2,lastpr,cut?"…":"");
            if(!tl1&&fresh)FP("   \033[90m(no output yet)\033[0m\033[K\n");
            for(int r=0;r<2;r++){char*t3=r?tl2:tl1;int L3=r?ll2:ll1,mw=Wc-4;if(!t3)continue;if(mw<8)mw=8;
                if(L3>mw){L3=mw;while(L3>0&&(t3[L3]&0xC0)==0x80)L3--;}FP("   \033[90m%.*s\033[0m\033[K\n",L3,t3);}}
        if(nn){int pl2=(int)strlen(lastpr),mx=Wc-12;if(mx<8)mx=8;int cut=pl2>mx;if(cut){pl2=mx;while(pl2>0&&(lastpr[pl2]&0xC0)==0x80)pl2--;}  /* note receipt: row 0 opens the file in the editor, row 1 in web */
            FP("%s \033[36m✓ %s · %.*s%s\033[0m\033[K\n",sel==0?" >":"  ",strstr(lastnote,"/notes/")?"✎ note":"☐ task",pl2,lastpr,cut?"…":"");
            FP("%s \033[%dm⌕ open in web\033[0m\033[K\n",sel==1?" >":"  ",sel==1?37:90);}
        for(int i=0;i<show;i++){int j=top+i,gj=j+vo,W=ws.ws_col;char*t=strchr(fm[j],'\t'),*t2=t?strchr(t+1,'\t'):NULL;
            int ml=t?(int)(t-fm[j]):(int)strlen(fm[j]);if(ml>W-7)ml=W-7;
            char*desc=t2?t2+1:(t?t+1:"");int dc=W<110?W/2:W-60>200?200:W-60;  /* name never cut — desc gets the leftover */
            if(dc>W-7-ml)dc=W-7-ml;if(dc<8){desc="";dc=0;}
            static char db[320];int hm=0;
            if(t2&&!strncmp(t+1,"win\t",4)){char*hit=0;int wl2=0;char*mm=strstr(desc," · ");int hd=mm?(int)(mm-desc)+4:0;
                if(blen)for(char*pw=buf;*pw&&!hit;){while(*pw==' ')pw++;int L2=(int)strcspn(pw," ");if(!L2)break;
                    char wq[64];if(L2<64){memcpy(wq,pw,(size_t)L2);wq[L2]=0;if((hit=strcasestr(desc,wq)))wl2=L2;}pw+=L2;}
                if(hit&&hit>=desc+hd){char*st2=hit-20;if(st2<desc+hd)st2=desc+hd;while((*st2&0xC0)==0x80)st2++;  /* filter hit: snippet around the FIRST typed word found in the convo, match reversed — show WHY it matched (res.py _snip) */
                    int pre=(int)(hit-st2),rm=dc-hd-pre-wl2-4,tw=(int)strlen(hit+wl2);if(rm<0)rm=0;if(tw>rm)tw=rm;while(tw>0&&(hit[wl2+tw]&0xC0)==0x80)tw--;
                    snprintf(db,320,"%.*s%s%.*s\033[7m%.*s\033[27m%.*s",hd,desc,st2>desc+hd?"…":"",pre,st2,wl2,hit,tw,hit+wl2);desc=db;hm=9;}
                else if((int)strlen(desc)>dc&&mm){int rm=dc-hd-3;if(rm>8){char*tp=desc+strlen(desc)-(size_t)rm;while((*tp&0xC0)==0x80)tp++;snprintf(db,320,"%.*s…%s",hd,desc,tp);desc=db;}}}  /* no hit: old view — head + …convo tail end */
            int dl=(int)strnlen(desc,(size_t)dc+(size_t)hm),dv;while(dl>0&&(desc[dl]&0xC0)==0x80)dl--;dv=dl-hm;  /* never cut mid-UTF-8 */
            FP(cfgmode?"%s %.*s\033[K":"%s a %.*s\033[K",gj==sel?" >":"  ",ml,fm[j]);
            if(*desc)FP("\033[%dG\033[90m%.*s\033[0m",W-dv,dl,desc);FP("\n");}
        FP("\033[J\033[%d;%dH\033[?25h",m_mode?(hdr_rows+2):2,ccol);  /* +1: top rule of input box */
        #undef FP
        (void)!write(STDOUT_FILENO,rb,(size_t)rl);
        if(sv&&!ft0){sv=0;char sp[P];snprintf(sp,P,"%s/i_frame.%dx%d",DDIR,ws.ws_row,ws.ws_col);int fd=open(sp,O_WRONLY|O_CREAT|O_TRUNC,0644);  /* per-size frames: blast fires whenever this pane size recurs. non-atomic: torn read = one cosmetic frame */
            if(fd>=0){(void)!write(fd,"\033[?1049h\033[?1000h\033[?1006h\033[?2004h",32);(void)!write(fd,rb,(size_t)rl);close(fd);}}}
        char ch;
        int lw=na&&fresh;  /* live tail ticks only while the receipt is fresh (foreground, ≤3min) — then back to pure block-on-key */
        if(m_mode||lw){struct pollfd pf={.fd=0,.events=POLLIN};int pr=poll(&pf,1,m_mode?250:500);
            if(pr==0){if(lw){char q2[512];snprintf(q2,512,"tmux capturep -pt %s -S -40 2>/dev/null|awk '/[a-z]/&&!/tokens|bypass/{gsub(/^ +| +$/,\"\");if($0!=\"\")L[++i]=$0}END{for(j=i>1?i-1:1;j<=i;j++)print L[j]}'",lastwin);
                pcmd(q2,ltl,(int)sizeof ltl);act="live";}
                clock_gettime(CLOCK_MONOTONIC,&tk);continue;} if(pr<0)break;}
        rd: if(read(0,&ch,1)!=1) break;
        clock_gettime(CLOCK_MONOTONIC,&tk);  /* key arrived → time the repaint it triggers */
        int do_pick=0;
        if(ch=='\x1b'){int av;ioctl(0,FIONREAD,&av);if(!av){usleep(2000);ioctl(0,FIONREAD,&av);}  /* arrow-seq bytes are already buffered → instant; only a genuine lone ESC waits 2ms (was 50ms on every arrow) */
            if(!av){if(m_mode||prefix[0]||cfgmode){cfgmode=0;prefix[0]=0;buf[0]=0;blen=0;sel=0;continue;}break;}
            char seq[2];if(read(0,seq,1)!=1)break;
            if(seq[0]=='['){if(read(0,seq+1,1)!=1)break;
                if(seq[1]=='A'){if(sel>0)sel=sel==vo?0:sel-1;act="↑";}  /* first match ↑ jumps to row 0: "↑ = prompt row" muscle memory survives the extra action rows */
                else if(seq[1]=='B'){if(sel<tot-1)sel++;act="↓";}
                else if(seq[1]=='<'){int mb=0,my=0;char mc;act="mouse";
                    while(read(0,&mc,1)==1&&mc!=';')mb=mb*10+mc-'0';
                    while(read(0,&mc,1)==1&&mc!=';');
                    while(read(0,&mc,1)==1&&mc!='M'&&mc!='m')my=my*10+mc-'0';
                    if(mc=='M'){if(!mb){int rr=my-(m_mode?hdr_rows:0)-4;if(rr>=0&&rr<vo){sel=rr;do_pick=1;}  /* -4: 3 input-box rows + 1 (rows are 1-based); virtual rows clickable, tail rows aren't */
                        else{int ci=top+rr-vo-xtra;if(rr>=vo+xtra&&ci>=0&&ci<nm){sel=ci+vo;do_pick=1;}}}
                    else if(mb==64&&sel>0){sel--;}else if(mb==65&&sel<tot-1){sel++;}}}
                else if(seq[1]=='2'){char d0=0,d1=0;act="paste";  /* bracketed paste marks \033[200~ / \033[201~ */
                    if(read(0,&d0,1)==1&&d0!='~'&&read(0,&d1,1)==1){char t=d1;while(t!='~'&&read(0,&t,1)==1);
                        if(d0=='0'&&d1=='0')paste=1;else if(d0=='0'&&d1=='1')paste=0;}}
            } else if(prefix[0]||blen||cfgmode){cfgmode=0;prefix[0]=0;buf[0]=0;blen=0;sel=0;act="esc";} else if(!m_mode)break;
        } else if(ch=='\t'&&!paste){if(sel<tot-1)sel++;act="↓";}
        else if(ch=='\x7f'||ch=='\b'){while(blen&&(buf[blen-1]&0xC0)==0x80)blen--;if(blen)buf[--blen]=0;if(blen&&!prefix[0]&&!cfgmode){rotate=1;pnm=-2;}else sel=0;act="⌫";}  /* pnm=-2: re-resolve sel next frame with fresh nm (first match, or claude row when none) */
        else if(ch=='\r'||ch=='\n'){if(paste){if(blen){BFIT;buf[blen++]='\n';buf[blen]=0;}}else do_pick=1;}  /* pasted \n = kept literal, never Enter (pasted email fired web entry → firefox) */
        else if(ch==7&&!cfgmode){cfgmode=1;sel=0;buf[0]=0;blen=0;act="config";(void)!write(STDOUT_FILENO,"\033[2J\033[H",7);continue;}
        else if(ch==3){if(prefix[0]||blen||cfgmode){cfgmode=0;prefix[0]=0;buf[0]=0;blen=0;sel=0;}else if(!m_mode)break;}
        else if(ch==4)break;
        else if((unsigned char)ch>=32||(paste&&ch=='\t')){BFIT;buf[blen++]=ch;buf[blen]=0;rotate=1;act="filter";}  /* any byte: punctuation+UTF-8 paste intact; rotate resolves next frame; ↑ = prompt row */
        if(paste){int av=0;ioctl(0,FIONREAD,&av);if(av>0)goto rd;}  /* drain the paste burst before repainting: O(n), not a repaint per byte */
        if(do_pick&&cfgmode&&nm&&sel<nm){char fld[16]="",val[32]="",ck[24];
            sscanf(fm[sel],"%15s %31s",fld,val);snprintf(ck,24,"i_%s",fld);cfset(ck,val);load_cfg();
            buf[0]=0;blen=0;sel=0;continue;}
        if(do_pick&&!cfgmode&&!prefix[0]&&blen&&sel<vo){  /* prompt-action row picked (no match → clamp keeps sel<vo): 0=agent win 1=note 2=task 3=web */
            if(sel==1||sel==2){char nd[P];snprintf(nd,P,"%s/notes",SROOT);mkdirp(nd);
                if(sel==1)snprintf(lastnote,P,"%s",note_save(nd,buf));else{task_py("add",buf);snprintf(lastnote,P,"%s/tasks.txt",SROOT);}sync_bg();SNIP;
                snprintf(jstat,sizeof jstat,"✓ %s saved",sel==1?"note":"task");
                lastwin[0]=0;buf[0]=0;blen=0;sel=-1;continue;}  /* stay in loop: rapid capture; receipt row below replaces the fired-win tail (last action wins), one ↓ selects it */
            if(sel==3){char u[B*3];int l=snprintf(u,sizeof u,"https://google.com/search?q=");  /* same engine as a search; %%-encode so any typed/pasted bytes form a valid query */
                for(int k=0;k<blen&&l<(int)sizeof u-4;k++){unsigned char c2=(unsigned char)buf[k];
                    if(c2==' '||c2=='\n'||c2=='\t')u[l++]='+';
                    else if(isalnum(c2)||strchr("-_.~",c2))u[l++]=(char)c2;
                    else l+=snprintf(u+l,4,"%%%02X",(unsigned)c2);}
                u[l]=0;IRST;bg_exec(OPENER,u);return 0;}
            const char*ia=cfget("i_agent");if(!*ia)ia="claude";const char*ie=cfget("i_effort");if(!*ie)ie=strstr(ia,"codex")?"xhigh":"max";
            char run[B+64],cm[B+256],wi[16]="?",pf[P];
            snprintf(pf,P,"%s/i_prompt.txt",DDIR);writef(pf,buf);  /* prompt rides a file: any length, quotes/newlines can't break the two shell layers */
            if(strstr(ia,"codex"))snprintf(run,sizeof run,"codex -c model_reasoning_effort=%s --dangerously-bypass-approvals-and-sandbox \"$(cat %s)\"",ie,pf);
            else snprintf(run,sizeof run,"claude --dangerously-skip-permissions --effort %s \"$(cat %s)\"",ie,pf);
            snprintf(cm,sizeof cm,"tmux new-window -dP -F '#{window_index} #{window_id}' -c '%s' '%s;exec bash'",cwd,run);
            pcmd(cm,wi,16);sscanf(wi,"%7s %15s",lastidx,lastwin);SNIP;
            ltl[0]=0;lastnote[0]=0;lastfire=time(0);
            snprintf(jstat,sizeof jstat,"→ win %s · %s/%s",lastidx,ia,ie);buf[0]=0;blen=0;sel=-1;continue;}  /* sel=-1: nothing selected, so one ↓ lands on the switch row (no accidental switch) */
        if(do_pick&&na&&sel==0){IRST;char c[64];snprintf(c,64,"tmux select-window -t %s",lastwin);(void)!system(c);return 0;}
        if(do_pick&&nn&&sel>=0&&sel<nn){IRST;
            if(sel){char u[P+40];snprintf(u,sizeof u,"http://localhost:1111/doc?f=%s",lastnote+strlen(SROOT)+1);  /* /doc = serve's per-file editor page */
                (void)!system("a ui on >/dev/null 2>&1");bg_exec(OPENER,u);return 0;}
            execvp("a",(char*[]){"a",lastnote,NULL});return 0;}
        if(do_pick&&nm&&sel>=vo&&sel-vo<nm){char*m=fm[sel-vo],cmd[256];
            {char*wt=strstr(m,"\twin\t@");if(wt){IRST;char sw[64];snprintf(sw,64,"tmux selectw -t %.*s",(int)strcspn(wt+5," "),wt+5);(void)!system(sw);
                if(!getenv("TMUX"))execlp("tmux","tmux","attach","-t",TMS,(char*)0);return 0;}}  /* outside tmux selectw is invisible — attach */
            char*tab=strchr(m,'\t'),*colon=strchr(m,':');
            if(colon&&(!tab||colon<tab)&&strncmp(m,"web ",4)){snprintf(cmd,256,"%.*s",(int)(colon-m),m);char*s=cmd;while(*s==' ')s++;memmove(cmd,s,strlen(s)+1);}
            else{int cl=tab?(int)(tab-m):(int)strlen(m);snprintf(cmd,256,"%.*s",cl,m);}
            {char*e=cmd+strlen(cmd)-1;while(e>cmd&&*e==' ')*e--=0;}
            int hs=0,cl=(int)strlen(cmd);
            for(int i=0;i<n;i++)if(!strncmp(lines[i],cmd,(size_t)cl)&&lines[i][cl]==' '){hs=1;break;}
            if(hs){snprintf(prefix,256,"%s ",cmd);buf[0]=0;blen=0;sel=0;printf("\033[J");continue;}
            if(m_mode||!strncmp(cmd,"m model ",8)||!strncmp(cmd,"m agent ",8)||!strncmp(cmd,"m effort ",9)){char cs[512];snprintf(cs,512,"a %s >/dev/null 2>&1",cmd);(void)!system(cs);load_cfg();
                sel=0;buf[0]=0;blen=0;
                if(!strncmp(cmd,"m agent ",8))snprintf(prefix,256,"m effort ");
                else if(!strncmp(cmd,"m effort ",9))snprintf(prefix,256,"m model ");
                else prefix[0]=0;
                (void)!write(STDOUT_FILENO,"\033[2J\033[H",7);continue;}
            IRST;
            if(dexists(cmd)){char tf[P];snprintf(tf,P,"%s/cd_target",DDIR);writef(tf,cmd);return 0;}
            {int wo=!strncmp(cmd,"open ",5)?5:!strncmp(cmd,"web ",4)?4:0;
            if(wo){alog(cmd,"");if(wo==5){char ac[512];const char*app=cmd+5;
                if(getenv("SWAYSOCK")){
                    char df[P]="",hd[P];snprintf(hd,P,"%s/.local/share/applications",HOME);
                    const char*ad[]={"/usr/share/applications","/usr/local/share/applications","/var/lib/flatpak/exports/share/applications",hd};
                    for(int i=0;i<4;i++){snprintf(df,P,"%s/%s.desktop",ad[i],app);if(fexists(df))break;df[0]=0;}
                    if(df[0])snprintf(ac,512,"swaymsg exec \"gio launch '%s'\"",df);
                    else snprintf(ac,512,"swaymsg exec '%s'",app);
                } else snprintf(ac,512,APP_CMD " '%s'",app);
                (void)!system(ac);}
                else bg_exec(OPENER,cmd+4);return 0;}}
            char*args[32];int ac=0;args[ac++]="a";
            for(char*p=cmd;*p&&ac<31;){while(*p==' ')p++;if(!*p)break;args[ac++]=p;while(*p&&*p!=' ')p++;if(*p)*p++=0;}
            args[ac]=NULL;setenv("A_TUI","1",1);execvp("a",args);return 0;}
    }
    IRST;
    #undef IRST
    #undef BFIT
    #undef SNIP
    return 0;
}
