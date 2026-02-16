/* ── ssh ── */
static void ssh_save(const char*dir,const char*n,const char*h,const char*pw){
    char f[P],d[B];snprintf(f,P,"%s/%s.txt",dir,n);
    snprintf(d,B,"Name: %s\nHost: %s\n%s%s%s",n,h,pw&&pw[0]?"Password: ":"",pw?pw:"",pw&&pw[0]?"\n":"");
    writef(f,d);sync_repo();
}
static void ssh_parse(const char*h,char*hp,char*port){
    snprintf(hp,256,"%s",h);char*c=strrchr(hp,':');
    if(c){snprintf(port,8,"%s",c+1);*c=0;}else snprintf(port,8,"22");
}
static void ssh_cmd(const char*pw,const char*hp,const char*port,const char*opt,const char*cmd){
    char c[B*2];int n=0;
    if(pw&&pw[0])n=snprintf(c,sizeof c,"sshpass -p '%s' ",pw);
    snprintf(c+n,sizeof(c)-(size_t)n,"ssh %s -oStrictHostKeyChecking=accept-new -p %s '%s'%s%s",opt,port,hp,cmd?" ":"",cmd?cmd:"");
    if(cmd)(void)!system(c);else execl("/bin/sh","sh","-c",c,(char*)NULL);
}
static int cmd_ssh(int argc, char **argv) {
    char dir[P]; snprintf(dir,P,"%s/ssh",SROOT); mkdirp(dir); sync_bg();
    typedef struct{char name[128],host[256],pw[256];}host_t;
    host_t H[32];int nh=0,arc=0;
    char paths[32][P];int np=listdir(dir,paths,32);
    for(int i=np-1;i>=0&&nh<32;i--){
        kvs_t kv=kvfile(paths[i]);const char*n=kvget(&kv,"Name");if(!n)continue;
        int dup=0;for(int j=0;j<nh;j++)if(!strcmp(H[j].name,n)){dup=1;break;}
        if(dup){do_archive(paths[i]);arc++;continue;}
        snprintf(H[nh].name,128,"%s",n);
        const char*h=kvget(&kv,"Host"),*p=kvget(&kv,"Password");
        snprintf(H[nh].host,256,"%s",h?h:"");snprintf(H[nh].pw,256,"%s",p?p:"");nh++;
    }
    if(arc)sync_bg();
    const char*sub=argc>2?argv[2]:NULL;
    if(!sub){
        char u[512];{char c[B];snprintf(c,B,"git -C '%s' remote get-url origin 2>/dev/null",dir);pcmd(c,u,512);u[strcspn(u,"\n")]=0;}
        int on=!system("pgrep -x sshd >/dev/null 2>&1");
        printf("SSH  sshd: %s\n  %s\n  %s\n\n",on?"\033[32mon\033[0m":"\033[31moff\033[0m  a ssh start",dir,u);
        for(int i=0;i<nh;i++){int s=!strcmp(H[i].name,DEV);
            printf("  %d. %s%s%s: %s%s%s\n",i,s?"\033[32m":"",H[i].name,s?" (self)\033[0m":"",H[i].host,H[i].pw[0]?" [pw]":"",s&&!on?" [off]":"");}
        if(!nh)puts("  (none)");
        puts("\nConnect: a ssh <#>\nRun:     a ssh <#> <cmd>\nAdd:     a ssh add\nSelf:    a ssh self\nStart:   a ssh start\nStop:    a ssh stop\nSetup:   a ssh setup");return 0;}
    if(!strcmp(sub,"start")){(void)!system("sshd 2>/dev/null || sudo /usr/sbin/sshd");puts("\xe2\x9c\x93 sshd started");return 0;}
    if(!strcmp(sub,"stop")){(void)!system("pkill -x sshd 2>/dev/null || sudo pkill -x sshd");puts("\xe2\x9c\x93 sshd stopped");return 0;}
    if(!strcmp(sub,"add")){
        char h[256],n[128],pw[256];
        printf("Host (user@ip): ");if(!fgets(h,256,stdin))return 1;h[strcspn(h,"\n")]=0;
        printf("Name: ");if(!fgets(n,128,stdin))return 1;n[strcspn(n,"\n")]=0;
        if(!n[0]){char*at=strchr(h,'@');snprintf(n,128,"%s",at?at+1:h);}
        printf("Password? ");if(!fgets(pw,256,stdin))return 1;pw[strcspn(pw,"\n")]=0;
        ssh_save(dir,n,h,pw);printf("\xe2\x9c\x93 %s\n",n);return 0;}
    if(!strcmp(sub,"self")){
        char user[128]="",ip[128]="",port[8]="22",host[256];
        const char*u=getenv("USER");if(!u)u=getenv("LOGNAME");if(u)snprintf(user,128,"%s",u);
        pcmd("hostname -I 2>/dev/null | awk '{print $1}'",ip,128);ip[strcspn(ip,"\n")]=0;
        if(!ip[0]){pcmd("ifconfig 2>/dev/null | grep 'inet ' | grep -v 127 | grep '192\\.' | awk '{print $2}' | head -1",ip,128);ip[strcspn(ip,"\n")]=0;}
        if(!ip[0]){pcmd("ifconfig 2>/dev/null | grep 'inet ' | grep -v 127 | awk '{print $2}' | head -1",ip,128);ip[strcspn(ip,"\n")]=0;}
        if(access("/data/data/com.termux",F_OK)==0)snprintf(port,8,"8022");
        else{char pp[64];if(!pcmd("grep -m1 '^Port ' /etc/ssh/sshd_config 2>/dev/null",pp,64)){
            char*sp=pp;while(*sp&&!isdigit((unsigned char)*sp))sp++;pp[strcspn(pp,"\n")]=0;if(*sp)snprintf(port,8,"%s",sp);}}
        snprintf(host,256,!strcmp(port,"22")?"%s@%s":"%s@%s:%s",user,ip,port);
        ssh_save(dir,DEV,host,NULL);printf("\xe2\x9c\x93 %s %s\n",DEV,host);return 0;}
    if(!strcmp(sub,"rm")&&argc>3){int x=atoi(argv[3]);
        if(x>=0&&x<nh){char f[P];snprintf(f,P,"%s/%s.txt",dir,H[x].name);unlink(f);sync_repo();printf("\xe2\x9c\x93 rm %s\n",H[x].name);}return 0;}
    if(!strcmp(sub,"setup")){fallback_py("ssh",argc,argv);}
    if((!strcmp(sub,"all")||!strcmp(sub,"*"))&&argc>3){
        char cmd[B]="";for(int i=3,l=0;i<argc;i++) l+=snprintf(cmd+l,(size_t)(B-l),"%s%s",i>3?" ":"",argv[i]);
        char qc[B];snprintf(qc,B,"'bash -ic '\"'\"'%s'\"'\"''",cmd);
        for(int i=0;i<nh;i++){char hp[256],port[8];ssh_parse(H[i].host,hp,port);
            char c[B*2];int n=0;if(H[i].pw[0])n=snprintf(c,sizeof c,"sshpass -p '%s' ",H[i].pw);
            snprintf(c+n,sizeof(c)-(size_t)n,"ssh -oConnectTimeout=5 -oStrictHostKeyChecking=no -p %s '%s' %s 2>&1",port,hp,qc);
            char o[B];int r=pcmd(c,o,B);printf("\n%s %s\n",r==0?"\xe2\x9c\x93":"x",H[i].name);if(o[0])printf("%s",o);}
        return 0;}
    /* resolve host by # or name */
    int idx=-1;
    if(isdigit((unsigned char)*sub))idx=atoi(sub);
    else{for(int i=0;i<nh;i++)if(!strcmp(H[i].name,sub)){idx=i;break;}}
    if(idx<0||idx>=nh){printf("x No host %s\n",sub);return 1;}
    char hp[256],port[8];ssh_parse(H[idx].host,hp,port);
    /* auto-prompt + save password if key auth fails */
    if(!H[idx].pw[0]){char tc[B];snprintf(tc,B,"ssh -oBatchMode=yes -oConnectTimeout=3 -p %s '%s' true 2>/dev/null",port,hp);
        if(system(tc)){char pw[256];printf("Password for %s: ",H[idx].name);
            if(fgets(pw,256,stdin)){pw[strcspn(pw,"\n")]=0;if(pw[0]){snprintf(H[idx].pw,256,"%s",pw);ssh_save(dir,H[idx].name,H[idx].host,pw);}}}}
    if(argc>3){char cmd[B]="";for(int i=3,l=0;i<argc;i++) l+=snprintf(cmd+l,(size_t)(B-l),"%s%s",i>3?" ":"",argv[i]);
        char qc[B];snprintf(qc,B,"'bash -ic '\"'\"'%s'\"'\"''",cmd);
        ssh_cmd(H[idx].pw,hp,port,"-tt",qc);return 0;}
    printf("Connecting to %s...\n",H[idx].name);
    ssh_cmd(H[idx].pw,hp,port,"-tt",NULL);return 1;
}
