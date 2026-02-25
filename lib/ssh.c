/* ── ssh ── */
#define SMUX " -oControlMaster=auto -oControlPath=%%d/.ssh/a-%%C -oControlPersist=300"
static void ssh_parse(const char*h,char*hp,char*port){
    snprintf(hp,256,"%s",h);char*c=strrchr(hp,':');if(c){snprintf(port,8,"%s",c+1);*c=0;}else snprintf(port,8,"22");}
static int ssh_pre(char*c,int sz,const char*pw,const char*opts,const char*port,const char*hp){
    int n=0;if(pw&&pw[0])n=snprintf(c,(size_t)sz,"sshpass -p '%s' ",pw);
    return n+snprintf(c+n,(size_t)(sz-n),"ssh" SMUX " %s -p %s '%s'",opts,port,hp);}
static void ssh_save(const char*dir,const char*n,const char*h,const char*pw){
    char f[P],d[B];snprintf(f,P,"%s/%s.txt",dir,n);
    snprintf(d,B,"Name: %s\nHost: %s\n%s%s%s",n,h,pw&&pw[0]?"Password: ":"",pw?pw:"",pw&&pw[0]?"\n":"");
    writef(f,d);sync_repo();}
static void ssh_savex(const char*dir,const char*n,const char*h,const char*pw,const char*k,const char*v){
    char f[P],d[B];snprintf(f,P,"%s/%s.txt",dir,n);
    int l=snprintf(d,B,"Name: %s\nHost: %s\n",n,h);
    if(pw&&pw[0])l+=snprintf(d+l,(size_t)(B-l),"Password: %s\n",pw);
    if(k&&v&&v[0])snprintf(d+l,(size_t)(B-l),"%s: %s\n",k,v);
    writef(f,d);sync_repo();}
static int cmd_ssh(int argc,char**argv){
    char dir[P];snprintf(dir,P,"%s/ssh",SROOT);mkdirp(dir);sync_bg();
    typedef struct{char name[128],host[256],pw[256];}host_t;
    host_t H[32];int nh=0,arc=0;
    char paths[32][P];int np=listdir(dir,paths,32);
    for(int i=np-1;i>=0&&nh<32;i--){
        kvs_t kv=kvfile(paths[i]);const char*n=kvget(&kv,"Name");if(!n)continue;
        int dup=0;for(int j=0;j<nh;j++)if(!strcmp(H[j].name,n)){dup=1;break;}
        if(dup){do_archive(paths[i]);arc++;continue;}
        snprintf(H[nh].name,128,"%s",n);const char*h=kvget(&kv,"Host"),*p=kvget(&kv,"Password");
        snprintf(H[nh].host,256,"%s",h?h:"");snprintf(H[nh].pw,256,"%s",p?p:"");nh++;}
    if(arc)sync_bg();
    const char*sub=argc>2?argv[2]:NULL;
    /* list */
    if(!sub){int on=!system("pgrep -x sshd >/dev/null 2>&1");
        printf("SSH sshd:%s\n\n",on?" \033[32mon\033[0m":" \033[31moff\033[0m");
        for(int i=0;i<nh;i++){int s=!strcmp(H[i].name,DEV);
            printf("  %d. %s%s%s: %s%s\n",i,s?"\033[32m":"",H[i].name,s?" (self)\033[0m":"",H[i].host,H[i].pw[0]?" [pw]":"");}
        if(!nh)puts("  (none)");
        puts("\na ssh <#|name> [cmd]  add/self/start/stop/all/rm\n"
             "  setup/key/auth/os/info/pw/mv");return 0;}
    /* start/stop/status */
    if(!strcmp(sub,"start")){(void)!system("sshd 2>/dev/null||sudo /usr/sbin/sshd");puts("\xe2\x9c\x93");return 0;}
    if(!strcmp(sub,"stop")){(void)!system("pkill -x sshd 2>/dev/null||sudo pkill -x sshd");puts("\xe2\x9c\x93");return 0;}
    if(!strcmp(sub,"status")||!strcmp(sub,"s")){
        int on=!system("pgrep -x sshd >/dev/null 2>&1");char ip[128];
        pcmd("hostname -I 2>/dev/null|awk '{printf $1}'",ip,128);
        const char*u=getenv("USER");int p=access("/data/data/com.termux",F_OK)?22:8022;
        printf("%s ssh %s@%s -p %d\n",on?"\xe2\x9c\x93":"x",u?u:"",ip,p);return 0;}
    /* setup — install openssh */
    if(!strcmp(sub,"setup")){
        int on=!system("pgrep -x sshd >/dev/null 2>&1");
        if(!on){printf("SSH not running. Install? (y/n): ");char yn[8];
            if(fgets(yn,8,stdin)&&(yn[0]=='y'||yn[0]=='Y')){
                if(!access("/data/data/com.termux",F_OK))(void)!system("pkg install -y openssh && sshd");
                else (void)!system("sudo apt install -y openssh-server && sudo systemctl enable --now ssh");}}
        on=!system("pgrep -x sshd >/dev/null 2>&1");
        printf("SSH: %s\n",on?"\xe2\x9c\x93 running":"x not running");return 0;}
    /* key — generate ed25519 key */
    if(!strcmp(sub,"key")){char kf[P];snprintf(kf,P,"%s/.ssh/id_ed25519",HOME);
        struct stat st;if(stat(kf,&st)){char c[B];snprintf(c,B,"ssh-keygen -t ed25519 -N '' -f '%s'",kf);(void)!system(c);}
        char pub[P];snprintf(pub,P,"%s.pub",kf);catf(pub);return 0;}
    /* auth — add authorized key */
    if(!strcmp(sub,"auth")){char k[B];printf("Paste public key: ");if(!fgets(k,B,stdin))return 1;
        k[strcspn(k,"\n")]=0;char af[P];snprintf(af,P,"%s/.ssh/authorized_keys",HOME);
        char d[P];snprintf(d,P,"%s/.ssh",HOME);mkdirp(d);
        FILE*f=fopen(af,"a");if(f){fprintf(f,"\n%s\n",k);fclose(f);chmod(af,0600);puts("\xe2\x9c\x93");}return 0;}
    /* push-auth — push gh/rclone creds to remote host */
    if(!strcmp(sub,"push-auth")&&argc>3){
        char tok[512];pcmd("gh auth token 2>/dev/null",tok,512);tok[strcspn(tok,"\n")]=0;
        const char*tgt=argv[3];
        /* push rclone.conf */
        {char rc[P],c[B*2];snprintf(rc,P,"%s/.config/rclone/rclone.conf",HOME);
        if(fexists(rc)){snprintf(c,B*2,"base64 '%s'|a ssh %s 'mkdir -p ~/.config/rclone&&base64 -d>~/.config/rclone/rclone.conf'",rc,tgt);(void)!system(c);}}
        /* push gh hosts.yml */
        {char gh[P],c[B*2];snprintf(gh,P,"%s/.config/gh/hosts.yml",HOME);
        if(fexists(gh)){snprintf(c,B*2,"base64 '%s'|a ssh %s 'mkdir -p ~/.config/gh&&base64 -d>~/.config/gh/hosts.yml'",gh,tgt);(void)!system(c);}}
        /* push gh token */
        if(tok[0]){char c[B*2];snprintf(c,B*2,"a ssh %s 'echo \"%s\"|gh auth login --with-token'",tgt,tok);(void)!system(c);}
        puts("\xe2\x9c\x93");return 0;}
    /* add — interactive */
    if(!strcmp(sub,"add")){char h[256],n[128],pw[256];
        printf("Host: ");if(!fgets(h,256,stdin))return 1;h[strcspn(h,"\n")]=0;
        printf("Name: ");if(!fgets(n,128,stdin))return 1;n[strcspn(n,"\n")]=0;
        if(!n[0]){char*at=strchr(h,'@');snprintf(n,128,"%s",at?at+1:h);}
        printf("Password: ");if(!fgets(pw,256,stdin))return 1;pw[strcspn(pw,"\n")]=0;
        /* validate connection */
        {char hp[256],port[8];ssh_parse(h,hp,port);
        char tc[B];int l=ssh_pre(tc,B,pw,"-oConnectTimeout=5 -oStrictHostKeyChecking=no",port,hp);
        snprintf(tc+l,(size_t)(B-l)," 'echo ok' 2>&1");
        char o[64];if(pcmd(tc,o,64)||!strstr(o,"ok")){printf("x auth failed: %s",o);return 1;}}
        ssh_save(dir,n,h,pw);printf("\xe2\x9c\x93 %s\n",n);return 0;}
    /* self — register this device */
    if(!strcmp(sub,"self")){char ip[128]="",port[8]="22",h[256];
        const char*u=getenv("USER");const char*nm=argc>3?argv[3]:DEV;
        /* WSL detection */
        int wsl=0;{char pv[64];pcmd("grep -ci microsoft /proc/version 2>/dev/null",pv,64);wsl=atoi(pv)>0;}
        if(wsl){
            pcmd("powershell.exe -c \"ipconfig\"|grep -oP '192\\.168\\.\\d+\\.\\d+'|head -1",ip,128);ip[strcspn(ip,"\n")]=0;
            snprintf(port,8,"2222");
            /* ensure sshd running */
            (void)!system("pgrep -x sshd >/dev/null||sudo service ssh start");
            /* check/setup port forward */
            char pf[B];pcmd("powershell.exe -c 'netsh interface portproxy show all' 2>/dev/null",pf,B);
            if(!strstr(pf,"2222")){
                char wip[128];pcmd("hostname -I 2>/dev/null|awk '{printf $1}'",wip,128);
                puts("Setting up Windows port forward (UAC)...");
                char c[B*2];snprintf(c,B*2,"powershell.exe -c \"Start-Process powershell -Verb RunAs -ArgumentList '-c',"
                    "'netsh interface portproxy delete v4tov4 listenport=2222 listenaddress=0.0.0.0 2>\\$null;"
                    "netsh interface portproxy add v4tov4 listenport=2222 listenaddress=0.0.0.0 connectport=22 connectaddress=%s;"
                    "netsh advfirewall firewall delete rule name=\\\"WSL SSH\\\" 2>\\$null;"
                    "netsh advfirewall firewall add rule name=\\\"WSL SSH\\\" dir=in action=allow protocol=tcp localport=2222'\"",wip);
                (void)!system(c);printf("Press Enter after admin window completes...");getchar();}
            printf("\xe2\x9c\x93 WSL port forward\n");
#ifdef __APPLE__
        }else if(1){
            pcmd("ipconfig getifaddr en0 2>/dev/null",ip,128);ip[strcspn(ip,"\n")]=0;
#else
        }else{
#endif
            pcmd("hostname -I 2>/dev/null|awk '{printf $1}'",ip,128);
            if(!ip[0])pcmd("ifconfig 2>/dev/null|awk '/inet /{if($2!~/^127/){printf $2;exit}}'",ip,128);
            if(!access("/data/data/com.termux",F_OK))snprintf(port,8,"8022");
            else{char pp[8];pcmd("awk '/^Port /{printf $2}' /etc/ssh/sshd_config 2>/dev/null",pp,8);if(pp[0])snprintf(port,8,"%s",pp);}}
        snprintf(h,256,!strcmp(port,"22")?"%s@%s":"%s@%s:%s",u?u:"",ip,port);
        char os[128];pcmd("uname -sr 2>/dev/null",os,128);os[strcspn(os,"\n")]=0;
        /* preserve existing password */
        const char*epw=NULL;for(int i=0;i<nh;i++)if(!strcmp(H[i].name,nm)){epw=H[i].pw;break;}
        ssh_savex(dir,nm,h,epw,"OS",os);printf("\xe2\x9c\x93 %s %s [%s]\n",nm,h,os);return 0;}
    /* rm */
    if(!strcmp(sub,"rm")&&argc>3){int x=-1;const char*a=argv[3];
        if(isdigit((unsigned char)*a))x=atoi(a);
        else{for(int i=0;i<nh;i++)if(!strcmp(H[i].name,a)){x=i;break;}}
        if(x>=0&&x<nh){char f[P];snprintf(f,P,"%s/%s.txt",dir,H[x].name);unlink(f);sync_repo();printf("\xe2\x9c\x93 rm %s\n",H[x].name);}return 0;}
    /* pw — change password */
    if(!strcmp(sub,"pw")&&argc>3){int x=-1;const char*a=argv[3];
        if(isdigit((unsigned char)*a))x=atoi(a);
        else{for(int i=0;i<nh;i++)if(!strcmp(H[i].name,a)){x=i;break;}}
        if(x>=0&&x<nh){char pw[256];printf("Password for %s: ",H[x].name);
            if(fgets(pw,256,stdin)){pw[strcspn(pw,"\n")]=0;ssh_save(dir,H[x].name,H[x].host,pw);printf("\xe2\x9c\x93 %s\n",H[x].name);}}return 0;}
    /* mv/rename */
    if((!strcmp(sub,"mv")||!strcmp(sub,"rename"))&&argc>4){
        const char*old=argv[3],*nn=argv[4];int x=-1;
        if(isdigit((unsigned char)*old))x=atoi(old);
        else{for(int i=0;i<nh;i++)if(!strcmp(H[i].name,old)){x=i;break;}}
        if(x>=0&&x<nh){char f[P];snprintf(f,P,"%s/%s.txt",dir,H[x].name);unlink(f);
            ssh_save(dir,nn,H[x].host,H[x].pw);printf("\xe2\x9c\x93 %s -> %s\n",H[x].name,nn);}return 0;}
    /* info */
    if(!strcmp(sub,"info")||!strcmp(sub,"i")){
        for(int i=0;i<nh;i++){char hp[256],port[8];ssh_parse(H[i].host,hp,port);
            printf("%s: ssh %s%s%s%s\n",H[i].name,strcmp(port,"22")?"-p ":"",strcmp(port,"22")?port:"",strcmp(port,"22")?" ":"",hp);}return 0;}
    /* os — detect remote OS on all hosts */
    if(!strcmp(sub,"os")){
        struct{int fd;pid_t pid;char nm[128],host[256],pw[256];}S[32];int ns=0;
        for(int i=0;i<nh&&ns<32;i++){int pfd[2];if(pipe(pfd))continue;
            pid_t p=fork();if(p==0){close(pfd[0]);char hp[256],port[8];ssh_parse(H[i].host,hp,port);
                char c[B*2];int l=ssh_pre(c,(int)sizeof c,H[i].pw,"-oConnectTimeout=5 -oStrictHostKeyChecking=no",port,hp);
                snprintf(c+l,(size_t)(sizeof(c)-(size_t)l)," 'uname -sr' 2>&1");
                char o[128];int r=pcmd(c,o,128);o[strcspn(o,"\n")]=0;
                if(!r&&o[0])(void)!write(pfd[1],o,strlen(o));close(pfd[1]);_exit(0);}
            close(pfd[1]);snprintf(S[ns].nm,128,"%s",H[i].name);snprintf(S[ns].host,256,"%s",H[i].host);
            snprintf(S[ns].pw,256,"%s",H[i].pw);S[ns].fd=pfd[0];S[ns].pid=p;ns++;}
        for(int i=0;i<ns;i++){char o[128];int l=(int)read(S[i].fd,o,127);o[l>0?l:0]=0;close(S[i].fd);waitpid(S[i].pid,NULL,0);
            if(o[0]){ssh_savex(dir,S[i].nm,S[i].host,S[i].pw,"OS",o);printf("\xe2\x9c\x93 %s: %s\n",S[i].nm,o);}
            else printf("x %s\n",S[i].nm);}
        return 0;}
    /* all/broadcast — parallel */
    if((!strcmp(sub,"all")||!strcmp(sub,"*"))&&argc>3){
        char cmd[B]="";for(int i=3,l=0;i<argc;i++)l+=snprintf(cmd+l,(size_t)(B-l),"%s%s",i>3?" ":"",argv[i]);
        char qc[B];snprintf(qc,B," 'bash -c '\"'\"'export PATH=$HOME/.local/bin:$PATH; %s'\"'\"'' 2>&1",cmd);
        struct{int fd;pid_t pid;char nm[128];}S[32];int ns=0;
        for(int i=0;i<nh&&ns<32;i++){int pfd[2];if(pipe(pfd))continue;
            pid_t p=fork();if(p==0){close(pfd[0]);char hp[256],port[8];ssh_parse(H[i].host,hp,port);
                char c[B*2];int l=ssh_pre(c,(int)sizeof c,H[i].pw,"-oConnectTimeout=5 -oStrictHostKeyChecking=no",port,hp);
                snprintf(c+l,(size_t)(sizeof(c)-(size_t)l),"%s",qc);char o[B];int r=pcmd(c,o,B);
                l=snprintf(c,B,"%c%s",r?'x':'+',o);(void)!write(pfd[1],c,(size_t)l);close(pfd[1]);_exit(0);}
            close(pfd[1]);snprintf(S[ns].nm,128,"%s",H[i].name);S[ns].fd=pfd[0];S[ns].pid=p;ns++;}
        for(int i=0;i<ns;i++){char o[B];int l=(int)read(S[i].fd,o,B-1);o[l>0?l:0]=0;close(S[i].fd);waitpid(S[i].pid,NULL,0);
            printf("\n%s %s\n",o[0]=='+'?"\xe2\x9c\x93":"x",S[i].nm);if(o[1])printf("%s",o+1);}
        return 0;}
    /* resolve host by # or name */
    int idx=-1;
    if(isdigit((unsigned char)*sub))idx=atoi(sub);
    else{for(int i=0;i<nh;i++)if(!strcmp(H[i].name,sub)){idx=i;break;}}
    if(idx<0||idx>=nh){printf("x No host %s\n",sub);return 1;}
    char hp[256],port[8];ssh_parse(H[idx].host,hp,port);
    if(!H[idx].pw[0]){char tc[B];int l=ssh_pre(tc,B,"","-oBatchMode=yes -oConnectTimeout=3",port,hp);
        snprintf(tc+l,(size_t)(B-l)," true 2>/dev/null");
        if(system(tc)){char pw[256];printf("Password for %s: ",H[idx].name);
            if(fgets(pw,256,stdin)){pw[strcspn(pw,"\n")]=0;if(pw[0]){snprintf(H[idx].pw,256,"%s",pw);ssh_save(dir,H[idx].name,H[idx].host,pw);}}}}
    {char cmd[B]="",c[B*2];for(int i=3;i<argc;i++){int l=(int)strlen(cmd);snprintf(cmd+l,(size_t)(B-l),"%s%s",l?" ":"",argv[i]);}
        int n=ssh_pre(c,(int)sizeof c,H[idx].pw,"-tt -oConnectTimeout=5 -oStrictHostKeyChecking=accept-new",port,hp);
        if(cmd[0])snprintf(c+n,(size_t)(sizeof(c)-(size_t)n)," 'bash -c '\"'\"'export PATH=$HOME/.local/bin:$PATH; %s'\"'\"''",cmd);
        else printf("Connecting to %s...\n",H[idx].name);
        execl("/bin/sh","sh","-c",c,(char*)NULL);_exit(127);}
}
