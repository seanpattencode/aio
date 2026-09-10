/* tmux — one session "a", windows are jobs */
#define TMS "a"
#define ACAT "A_NOPROMPT=1 a cat"  /* dprompt() already wrote default.txt at the top of the ctx file */
static void tm_gc(void){(void)!system("tmux ls -F'#{session_name}:#{session_attached}' 2>/dev/null|awk -F: '/^"TMS"-[0-9]+:0/{print$1}'|xargs -I{} tmux kill-session -t{} 2>/dev/null");
    (void)!system("tmux list-clients -F'#{client_tty}' 2>/dev/null|while read t;do [ -e \"$t\" ]||tmux detach-client -t \"$t\" 2>/dev/null;done");
    (void)!system("tmux list-clients -t '"TMS"' -F'#{client_pid} #{client_tty}' 2>/dev/null|while read p t;do g='"TMS"'-$p;tmux has-session -t \"$g\" 2>/dev/null||tmux new-session -d -t '"TMS"' -s \"$g\" 2>/dev/null;tmux switch-client -c \"$t\" -t \"$g\" 2>/dev/null;done");}
static void tm_ensure_sess(void){
    tm_gc();
    if(system("tmux has-session -t '"TMS"' 2>/dev/null")){
    /* own scope: `a ui reload` cgroup-kill must not take tmux down; diag: my/tmuxlog.sh */
    (void)!system("{ command -v systemd-run >/dev/null 2>&1&&systemctl --user show-environment >/dev/null 2>&1&&Z='systemd-run --user --scope -q --'||Z=;"
        "$Z tmux new-session -d -s '"TMS"' 'while a i 2>/dev/null;do sleep 1;done';tmux set -gs exit-empty off;tmux set -gs exit-unattached off;} </dev/null >/dev/null 2>&1");}
    /* restore once per SERVER (@res dies with it) — raw creators (ssh tmux new -A -s a) no longer skip it; 2026-08-14: 7 agents lost */
    (void)!system("tmux show -gv @res 2>/dev/null|grep -qx 1||{ tmux set -g @res 1;(a snap restore >>\"$HOME/a/adata/local/restore.log\" 2>&1 &);} 2>/dev/null");}
static int tm_has(const char *w) {
    char c[B];snprintf(c,B,"tmux list-windows -t '"TMS"' -F '#{window_name}' 2>/dev/null|grep -qx '%s'",w);
    return !system(c);
}
/* agent window name = <pre>-<base>-Sep4-346p: who, where, WHEN, readable on the bar (Sean 2026-09-04). taken → +seconds, still taken → +pid */
static const char*tm_name(const char*pre,const char*base,time_t t){static char b[256];struct tm*l=localtime(&t);char m[6];strftime(m,6,"%b",l);
    int n=snprintf(b,256,"%.64s-%.64s-%s%d-%d%02d",pre,base,m,l->tm_mday,l->tm_hour%12?l->tm_hour%12:12,l->tm_min),ap=l->tm_hour<12?'a':'p';
    snprintf(b+n,256-(size_t)n,"%c",ap);if(tm_has(b))snprintf(b+n,256-(size_t)n,"%02d%c",l->tm_sec,ap);if(tm_has(b))snprintf(b+n,256-(size_t)n,"%02d%c-%d",l->tm_sec,ap,(int)getpid());return b;}
static void tm_go(const char *w) {
    perf_disarm();tm_gc();tm_ensure_sess();char g[64];snprintf(g,64,TMS"-%d",(int)getpid());
    char c[B];const char*op=getenv("TMUX")?"switch-client":"attach-session";
    snprintf(c,B,"exec tmux new-session -d -t '"TMS"' -s '%s' \\; %s -t '%s%s%s'",g,op,g,w?":":"",w?w:"");
    execl("/bin/sh","sh","-c",c,(char*)0);}
static void tm_rename(const char*n){const char*p=getenv("TMUX_PANE");char c[200];snprintf(c,200,"tmux rename-window -t '%s' '%s'",p?p:"",n);(void)!system(c);}  /* -t pane: bare rename hits session-current window (clobbered keeper on restore) */
static void ram_park(void){                                             /* low RAM at window spawn → park LRU claude window; tmux server = the agent registry, pane child-check spots agents under any name (Sean 7/9: spawn freely, RAM never bottlenecks; parked = resumable via a res). gate: MemAvailable, mac vm_stat free+inactive+purgeable (7/15); neither → av 0 → no-op */
    long need=4096;{const char*e=getenv("A_RAM_MIN_MB");if(e)need=atol(e);}
    char b[192]="";pcmd("a=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo 2>/dev/null);[ -n \"$a\" ]||a=$(vm_stat 2>/dev/null|awk '/page size of/{ps=$8}/Pages (free|inactive|purgeable):/{s+=$NF}END{if(s*ps)print int(s*ps/1048576)}');printf %s \"$a\"",b,192);
    long av=atol(b);if(av<=0||av>=need)return;
    pcmd("mw=$(tmux display -p -t \"$TMUX_PANE\" '#{window_id}' 2>/dev/null);tmux list-panes -s -t '"TMS"' -F '#{window_activity} #{window_active} #{window_id} #{pane_pid} #{window_name}' 2>/dev/null|sort -n|awk -v mw=\"$mw\" '$2==0&&$3!=mw{print $3\" \"$4\" \"$5}'|while read i p n;do pgrep -x -P $p 'claude|grok|codex' >/dev/null&&{ tmux kill-window -t \"$i\";echo \"$n\";break;};done",b,192);
    b[strcspn(b,"\n")]=0;
    if(b[0])printf("\xe2\x8f\xb8 parked %s (RAM %ldM < %ldM) \xe2\x80\x94 resume: a res\n",b,av,need);
}
static int tm_new(const char *w, const char *wd, const char *cmd) {
    tm_ensure_sess();if(tm_has(w))return 1;ram_park();char c[B*2],ev[P+16]="";
    const char*xa=getenv("A_CTX");if(xa&&xa[0])snprintf(ev,sizeof(ev),"-e A_CTX='%s' ",xa);
    if(cmd&&*cmd)snprintf(c,sizeof(c),"tmux new-window -d %s-t '"TMS":' -n '%s' -c '%s' '%s'",ev,w,wd,cmd);
    else snprintf(c,sizeof(c),"tmux new-window -d %s-t '"TMS":' -n '%s' -c '%s'",ev,w,wd);
    return system(c);
}
/* write default prompt + tools info to file. source=off skips intro+a-cat. */
#define SRC_ON strcmp(cfget("source"),"off")
static void prompt_freshness(FILE*f){
    char c[B],b[256]="";
    snprintf(c,B,"cd '%s';(git fetch -q origin main &);B=$(git rev-list --count HEAD..origin/main 2>/dev/null);U=$(git status -s 2>/dev/null|wc -l);[ \"${B:-0}$U\" != \"00\" ]&&echo \"a: $B behind origin/main, $U dirty. pull: git -C %s pull --ff-only\"",SDIR,SDIR);
    pcmd(c,b,256);if(b[0])fprintf(f,"%s\n",b);
}
static int write_prompt_file(const char *path, const char *wd, const char *extra) {
    FILE *f=fopen(path,"w");if(!f)return 0;
    prompt_freshness(f);
    {struct timespec ts;clock_gettime(CLOCK_REALTIME,&ts);struct tm*lt=localtime(&ts.tv_sec);char d[40],z[8];strftime(d,40,"%a %Y-%m-%d %H:%M:%S",lt);strftime(z,8,"%Z",lt);fprintf(f,"Current time: %s.%09ld %s (check vs market hours)\n",d,ts.tv_nsec,z);}
    const char *dp=dprompt(),*cp=cfget("claude_prefix");
    if(dp[0])fprintf(f,"%s\n",dp);
    if(cp[0])fprintf(f,"%s\n",cp);
    fprintf(f,"When work finished, run a done \"[<test>cmd</test>][<diff>files</diff>][<do>key::label::cmd||key::label::cmd</do>] msg\""
        " — msg: one simple sentence. Quoted test output: beginning...end, 4 lines max. No spacing between report sections (diff shows better). Spawns diff + live-PTY test panes; <do> keys run cmd on keypress."
        " a tools: a done a help a diff a push [msg] a note <text> a cat 2|3 a ssh\n");
    char af[P];snprintf(af,P,"%s/AGENTS.md",wd);
    char *amd=readf(af,NULL);if(amd){fprintf(f,"%s\n",amd);free(amd);}
    if(extra&&extra[0])fprintf(f,"\nTask: %s\n",extra);
    {char ip[P];snprintf(ip,P,"%s/mem/index.txt",SROOT);char *iv=readf(ip,NULL);
     if(iv){fprintf(f,"\n==> mem index <==\n%s\n",iv);free(iv);}}
    fprintf(f,"\nInstalled tools on this device:\n");
    FILE*tp=popen("ls $(echo \"$PATH\"|tr : ' ') 2>/dev/null|sort -u","r");
    if(tp){char b[8192];size_t n;while((n=fread(b,1,8192,tp))>0)fwrite(b,1,n,f);pclose(tp);}
    fclose(f);return 1;
}
/* job cmd */
static void jcmd_fill(char*b,int cont,const char*wd,const char*extra){
    char ctxf[P],xsuf[512]="";snprintf(ctxf,P,"%s/a_ctx_%d.txt",TMP,(int)getpid());
    write_prompt_file(ctxf,wd,NULL);
    if(extra&&extra[0]){char xf[P];snprintf(xf,P,"%s/a_xtra_%d.txt",TMP,(int)getpid());writef(xf,extra);
        snprintf(xsuf,512," \"$(cat '%s')\"",xf);}
    const char*ag=cfget("m_agent");if(!*ag)ag="claude";const char*md=cfget("m_model"),*ef=cfget("m_effort");char run[B];
    if(strstr(ag,"codex"))snprintf(run,B,"codex -c model_reasoning_effort=\"%s\" --model %s --dangerously-bypass-approvals-and-sandbox%s",*ef?ef:"xhigh",*md?md:"gpt-5.5",xsuf);
    else if(strstr(ag,"gemini"))snprintf(run,B,"gemini --yolo%s",xsuf);
    else{const char*sid=getenv("SID");char sp[96]="";if(sid&&*sid)snprintf(sp,96,"--session-id %s ",sid);
        snprintf(run,B,ACAT " >>%s 2>/dev/null;claude %s--dangerously-skip-permissions --model %s --effort %s --append-system-prompt-file %s%s%s",ctxf,sp,*md?md:"claude-fable-5",*ef?ef:"max",ctxf,cont?" --continue":"",xsuf);}
    snprintf(b,B,"tmux splitw -vd -p50 -t $TMUX_PANE;%s;e=$?;[ $e -ne 0 ]&&echo \"$(date) $e $(pwd)\">>%s/crashes.log;exec bash",run,LOGDIR);}

static void tm_ensure_conf(void) {
    if (strcmp(cfget("tmux_conf"), "y") != 0) return;
    if(fork())return;setsid();
    char adir[P]; snprintf(adir, P, "%s/.a", HOME);
    mkdirp(adir);
    char cpath[P]; snprintf(cpath, P, "%s/tmux.conf", adir);
    FILE *f = fopen(cpath, "w");
    if (!f) return;
    const char *cc = clip_cmd();
    fputs("# aio-managed-config\nset-hook -gu after-new-window\nset-hook -gu session-created\nset -wg pane-scrollbars on\n"
        "set -g history-limit 10000\n"   /* 50000 x 15 windows x grouped sessions = 11.5G tmux server RSS (2026-07-01 lag incident) */
        "set -ga update-environment \"WAYLAND_DISPLAY\"\n"
        "set -ga update-environment \"SWAYSOCK\"\n"
        "set -g mouse on\n"
        "set -g focus-events on\n"
        "set -g set-titles on\n"
        "set -g set-titles-string \"#S:#W\"\n"
        "set -s set-clipboard on\n"
        "set -g visual-bell off\n"
        "set -g bell-action any\n"
        "set-hook -g alert-bell 'run-shell \"osascript -e \\\"display notification \\\\\\\"#{hook_window_name}\\\\\\\" with title \\\\\\\"a: done\\\\\\\"\\\"\"'\n"
        "set -g window-size latest\n"
        "set -g automatic-rename off\n"
        "set -g repeat-time 0\n"
        "set -s extended-keys on\n"
        "set -as terminal-features 'xterm*:extkeys:overline'\n"
        "set -as terminal-overrides ',*:Smol=\\E[53m:Rmol=\\E[55m'\n"
        "set -as terminal-overrides ',*:Ms=\\E]52;%p1%s;%p2%s\\007'\n"   /* OSC52 to every client on copy — foot+xterm terminfo lack Ms here */
        "set -g assume-paste-time 0\n"
        "set -g window-style bg=default\n"
        "set -g window-active-style bg=default\n"
        "set -g pane-border-style fg=colour238\n"
        "set -g pane-active-border-style fg=green\n"
        "set -g status-style 'bg=default,fg=white,fill=default'\n"
        "set -g status-position bottom\n"
        "set -g status 2\n"
        "set -g status-right \"\"\n"
/* hints (^key) only when client wide enough to be a desktop; mobile/narrow shows clean labels */
#define WH(x) "#{?#{e|>:#{client_width},70}," x ",}"
        "set -g status-format[0] \"#[align=left,bg=black,fg=colour231,nobold]#[range=user|prev]  <" WH(" ^J") " #[norange]#[range=user|next]  >" WH(" ^K") " #[norange]#[align=right]#[range=user|aa] a" WH(" M-a") " #[norange] #[range=user|new] Pane" WH(" ^O") " #[norange] #[range=user|win] Win" WH(" ^T") " #[norange]#[range=user|x] X" WH(" ^X") " #[norange] #[range=user|close]Close" WH(" ^W") "#[norange] #[range=user|menu] ..." WH(" ^.") " #[norange] #[range=user|kbd]Kb#[norange] \"\n"
#undef WH
        "set -g status-format[1] \"#[align=left]#{?#{e|>:#{session_windows},1},#[fg=white bg=default bold#,range=user|prev]  <  #[norange]#[range=user|next]  >  #[norange] ,}#{W:#[range=window|#{window_index}]#{?window_bell_flag,#[fg=white bg=red bold],#[fg=colour231 bg=black]} #{?window_bell_flag,\\U0001F534 ,}#I:#W #[default]#[norange] ,#[fg=#000000 bg=#ffffff bold] #I:#W #[default] }\"\n"
        /* C-Tab/C-S-Tab won't work: Tab=0x09=C-i, so C-Tab is indistinguishable from Tab */
#define SSHIF "if-shell 'ps -o comm= -t #{pane_tty} 2>/dev/null|grep -qE \"^ssh\"' "
        "bind -n M-Right " SSHIF "'if-shell \"a fl n #{pane_id}\" next-window' 'next-window'\n"
        "bind -n M-Left " SSHIF "'if-shell \"a fl p #{pane_id}\" previous-window' 'previous-window'\n"
        "bind -n C-k " SSHIF "'send C-k' 'next-window'\n"
        "bind -n C-j " SSHIF "'send C-j' 'previous-window'\n"
        "bind -n C-PageDown " SSHIF "'if-shell \"a fl n #{pane_id}\" next-window' 'next-window'\n"
        "bind -n C-PageUp " SSHIF "'if-shell \"a fl p #{pane_id}\" previous-window' 'previous-window'\n"
        "bind -n PPage if -F '#{alternate_on}' 'send PPage' 'copy-mode -e ; send -X -N \"#{pane_height}\" scroll-up'\n"
        "bind-key -n C-n new-window\n"
        "bind -n C-t " SSHIF "'send C-t' 'new-window'\n"
        "bind -n C-o " SSHIF "'send C-o' 'splitw -v -c \"#{pane_current_path}\"'\n"
        "bind -n C-w " SSHIF "'send C-w' 'selectw -n;killw -t:!'\n"
        "bind -n C-x " SSHIF "'send C-x' 'kill-pane'\n"
/* the panel's ... menu; shared by the C-. key and the click case below */
#define AMENU "menu Pane 1 \"splitw -fh\" Zoom 2 \"resizep -Z\" Sync 3 \"set synchronize-panes\" Rename 4 \"command-prompt \\\"renamew %%\\\"\" Quit 5 detach Kill 6 kills"
        "bind -n C-. " SSHIF "'send C-.' {" AMENU "}\n"
#undef SSHIF
        "bind-key -n C-q detach\n"
        "bind -n WheelUpStatus selectw -p\n"
        "bind -n WheelDownStatus selectw -n\n", f);
    fputs(
        "bind-key -n M-a new-window 'while a i 2>/dev/null;do sleep 1;done'\n"
        "bind -T root MouseDown1Status if -F '#{==:#{mouse_status_range},window}' "
        "{ selectw } { run-shell 'case \"#{mouse_status_range}\" in "
        "win) tmux new-window;;"
        "prev) tmux prev;; next) tmux next;; aa) tmux neww a;; new) tmux splitw;; "
        "x) tmux killp;; close) tmux killw;; "
        "menu) tmux " AMENU ";; "
        "kbd) tmux set -g mouse off; tmux display \"Mouse off 3s\"; "
        "(sleep 3; tmux set -g mouse on) &;; esac;:' }\n",
        f);
#undef AMENU
    if (access("/data/data/com.termux",F_OK)==0)
        fprintf(f,"set-environment -g CLAUDE_CODE_TMPDIR \"%s/.tmp\"\n",HOME);
    if (cc) fprintf(f, "set -s copy-command \"%s\"\n", cc);
    {const char*cm[]={"copy-mode","copy-mode-vi",NULL};const char*wn="#{?#{e|>:#{client_width},100},#{pane_height},3}";
    for(int i=0;cm[i];i++){ cc?fprintf(f,"bind -T %s MouseDragEnd1Pane send -X copy-pipe-and-cancel \"%s\"\n",cm[i],cc)
        :fprintf(f,"bind -T %s MouseDragEnd1Pane send -X copy-pipe-and-cancel\n",cm[i]);
        static const char*K[]={"PPage","NPage","WheelUpPane","WheelDownPane"};for(int k=0;k<4;k++)fprintf(f,"bind -T %s %s send -X -N '%s' scroll-%s\n",cm[i],K[k],k<2?"#{pane_height}":wn,k&1?"down":"up");}}
    fclose(f);
    char uconf[P]; snprintf(uconf, P, "%s/.tmux.conf", HOME);
    char *uc = readf(uconf, NULL);
    if (!uc || !strstr(uc, "~/.a/tmux.conf")) {
        FILE *uf = fopen(uconf, "a");
        if (uf) { fputs("\nsource-file -q ~/.a/tmux.conf  # a\n", uf); fclose(uf); }
    }
    free(uc);
    {char cmd[B];snprintf(cmd,B,"tmux source-file '%s' 2>/dev/null&&tmux refresh-client -S 2>/dev/null",cpath);(void)!system(cmd);}
    _exit(0);
}
