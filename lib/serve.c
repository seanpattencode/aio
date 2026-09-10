/* a serve [port] — pure C HTTP server for UI. no python dependency. */
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#ifndef __APPLE__
#include <pty.h>
#else
#include <util.h>
#endif
static void sha1(const unsigned char*d,size_t n,unsigned char out[20]){
    uint32_t h0=0x67452301,h1=0xEFCDAB89,h2=0x98BADCFE,h3=0x10325476,h4=0xC3D2E1F0;
    size_t pl=((56-((n+1)%64))%64),tl=n+1+pl+8;
    unsigned char m[256]={0};memcpy(m,d,n);m[n]=0x80;
    size_t ml=n*8;for(size_t i=0;i<8;i++)m[tl-1-i]=(unsigned char)(ml>>(i*8));
    for(size_t i=0;i<tl;i+=64){
        uint32_t w[80],a=h0,b=h1,c=h2,dd2=h3,e=h4;
        for(size_t j=0;j<16;j++)w[j]=(uint32_t)(m[i+j*4]<<24|m[i+j*4+1]<<16|m[i+j*4+2]<<8|m[i+j*4+3]);
        for(int j=16;j<80;j++){uint32_t t=w[j-3]^w[j-8]^w[j-14]^w[j-16];w[j]=(t<<1)|(t>>31);}
        for(int j=0;j<80;j++){uint32_t f,k;
            if(j<20){f=(b&c)|((~b)&dd2);k=0x5A827999;}else if(j<40){f=b^c^dd2;k=0x6ED9EBA1;}
            else if(j<60){f=(b&c)|(b&dd2)|(c&dd2);k=0x8F1BBCDC;}else{f=b^c^dd2;k=0xCA62C1D6;}
            uint32_t t=((a<<5)|(a>>27))+f+e+k+w[j];e=dd2;dd2=c;c=(b<<30)|(b>>2);b=a;a=t;}
        h0+=a;h1+=b;h2+=c;h3+=dd2;h4+=e;}
    uint32_t hh[]={h0,h1,h2,h3,h4};
    for(int i=0;i<5;i++)for(int j=0;j<4;j++)out[i*4+j]=(unsigned char)(hh[i]>>(24-j*8));
}
static char shtml[4<<20];static int shlen;static time_t sgen_t;
static char sdr[P]; /* a serve <port> <dir> = static site only; UI (incl /ws shell) never exposed */
static const char*mime(const char*p,const char*d){const char*e=strrchr(p,'.');e=e?e+1:"";   /* d = type for an unknown extension */
    return !strcmp(e,"html")?"text/html; charset=utf-8":!strcmp(e,"css")?"text/css":!strcmp(e,"js")?"text/javascript":
        !strcmp(e,"png")?"image/png":!strcmp(e,"svg")?"image/svg+xml":!strcmp(e,"jpg")||!strcmp(e,"jpeg")?"image/jpeg":
        !strcmp(e,"ico")?"image/x-icon":!strcmp(e,"json")?"application/json":!strcmp(e,"pdf")?"application/pdf":!strcmp(e,"epub")?"application/epub+zip":!strcmp(e,"txt")?"text/plain; charset=utf-8":d;}
static void sfile(int c,const char*ct,const char*b,size_t bl,const char*cache){   /* whole file, body looped: source.pdf can be tens of MB, one write() may be short */
    char h[224];int hl=snprintf(h,224,"HTTP/1.1 200 OK\r\nContent-Type:%s\r\nContent-Length:%zu\r\nConnection:close\r\nCache-Control:%s\r\n\r\n",ct,bl,cache);
    (void)!write(c,h,(size_t)hl);for(size_t o=0;o<bl;){ssize_t w=write(c,b+o,bl-o);if(w<=0)break;o+=(size_t)w;}}
#define SYNC_HTML "<span style=color:#888>sync <span class=sa>%s</span></span> <button style=\"background:#000;color:#888;border:1px solid #333;padding:0 6px;font:inherit;cursor:pointer\" onclick=\"fetch('/api/sync',{method:'POST'});let p=setInterval(()=>fetch('/api/sync-status').then(r=>r.text()).then(t=>{document.querySelectorAll('.sa').forEach(s=>s.textContent=t);if(t!='syncing')clearInterval(p)}),1000)\">sync</button>"
/* ARCH #32: list pages navigate on finger/mouse DOWN, not lift-off. delegated so it covers links added later (e.g. /dash EventSource). skips #/onclick links. */
#define TAPJS "<script>addEventListener('pointerdown',function(e){var a=e.target.closest('a[href]');if(a&&!a.onclick&&a.getAttribute('href')[0]!='#'){e.preventDefault();a.click()}},true)</script>"
static int ncmp(const void*a,const void*b){const char*x=strrchr((const char*)a,'_'),*y=strrchr((const char*)b,'_');return strcmp(y?y:"",x?x:"");}
static int notes_build(char*h,int cap,const char*kind){   /* kind = "notes" or "prompts" */
    char nd[P];snprintf(nd,P,"%s/git/%s",AROOT,kind);const char*arc=!strcmp(kind,"prompts")?"arcp":"arcn";
    int hl=snprintf(h,(size_t)cap,SYNC_HTML,sync_age());
    DIR*d=opendir(nd);if(!d)return hl;struct dirent*e;
    char(*names)[64]=NULL;int nn=0,ncp=0;  /* a static[2048] dropped the newest */
    while((e=readdir(d))){if(e->d_name[0]=='.'||!strstr(e->d_name,".txt"))continue;
        if(nn>=ncp){ncp=ncp?ncp*2:2048;char(*t)[64]=realloc(names,(size_t)ncp*64);if(!t)break;names=t;}
        snprintf(names[nn++],64,"%s",e->d_name);}closedir(d);
    qsort(names,(size_t)nn,64,ncmp);   /* ncmp = newest first */
    int lim=!strcmp(kind,"prompts")?24:4;   /* prompts = the daily 11+11 candidates (Sean 7/10: visible in flow); notes stay a 4-newest glimpse */
    for(int i=0,shown=0;i<nn&&shown<lim&&hl<cap-4096;i++){   /* newest first with text (skip malformed) */
        char fp[P];snprintf(fp,P,"%s/%s",nd,names[i]);
        FILE*f=fopen(fp,"r");if(!f)continue;char ln[4096];int got=0;
        while(fgets(ln,4096,f)){if(!strncmp(ln,"Text: ",6)){ln[strcspn(ln,"\n")]=0;
            const char*u=strrchr(names[i],'_');char hu[48]="";if(u){char ts[16];snprintf(ts,16,"%.15s",u+1);ts_human(ts,hu,48);}
            hl+=snprintf(h+hl,(size_t)(cap-1-hl),"<div class=ni><button onclick=\"%s('%s',this)\" class=nx>x</button><span style=\"color:#888;display:inline-block;width:104px\">%s</span><span style=\"flex:1\">%s</span><a href=\"/doc?f=%s/%s\" style=\"color:#888;margin-left:8px;text-decoration:none\">edit</a></div>",arc,names[i],hu,ln+6,kind,names[i]);got=1;break;}}
        fclose(f);shown+=got;}free(names);return hl;
}
static void html_gen(void){
    char tf[P];snprintf(tf,P,"%s/lib/ui_full.html",SDIR);sgen_t=time(NULL);
    char*src=readf(tf,NULL);if(!src)return;
    char*s=src;
    /* substitute placeholders */
    shlen=0;
    #define EMIT(p,n) {if(shlen+(n)<(int)sizeof shtml){memcpy(shtml+shlen,p,(size_t)(n));shlen+=(n);}}
    for(char*p=s;*p;){
        if(*p=='_'&&p[1]=='_'){
            char*end=strstr(p+2,"__");
            if(end&&(end-p)<16){
                char tag[16];memcpy(tag,p+2,(size_t)(end-p-2));tag[end-p-2]=0;
                if(!strcmp(tag,"CMDS")){FILE*f=popen("a i","r");char l[16384],e[16400];   /* ["name","desc"], per `a i` line, unbounded (64K buffers cut it mid-string = blank page); " and \ neutered — one raw " kills the router script; JS ignores the trailing comma */
                    while(f&&fgets(l,16384,f)){l[strcspn(l,"\n")]=0;for(char*q=l;*q;q++)if(*q=='"')*q='\'';else if(*q=='\\')*q='/';
                        char*t=strchr(l,'\t');if(t)*t=0;if(*l){int el=snprintf(e,16400,"[\"%s\",\"%s\"],",l,t?t+1:"");EMIT(e,el)}}
                    if(f)pclose(f);}
                else if(!strcmp(tag,"DO")){char h[64]="";gethostname(h,64);char lo[128];int ll=snprintf(lo,128,"<option value=\"\">local: %s</option>",h);EMIT(lo,ll)
                    char hbr[300]="";/* homebox is a role pointer (ssh.c hb): label it with the real entry sharing its Host so the picker says which box it is */
                    {char ddir[P];snprintf(ddir,P,"%s/ssh",SROOT);char paths[64][P];int m=listdir(ddir,paths,64);char hbh[512]="";
                        for(int i=0;i<m&&!hbh[0];i++){kvs_t kv=kvfile(paths[i]);const char*nm=kvget(&kv,"Name"),*ho=kvget(&kv,"Host");
                            if(nm&&ho&&!strcasecmp(nm,"homebox"))snprintf(hbh,512,"%s",ho);}
                        if(hbh[0]){snprintf(hbr,300,"%s",hbh); /* no named sibling -> show the raw user@host */
                            for(int i=0;i<m;i++){kvs_t kv=kvfile(paths[i]);const char*nm=kvget(&kv,"Name"),*ho=kvget(&kv,"Host");
                                if(nm&&ho&&strcasecmp(nm,"homebox")&&!strcmp(ho,hbh)){snprintf(hbr,300,"%s",nm);break;}}}}
                    char gc[B];snprintf(gc,B,"grep -h '^Name:' '%s/ssh/'*.txt 2>/dev/null|sed 's/Name: //'|sort -u",SROOT);
                    FILE*df=popen(gc,"r");char dln[256];while(df&&fgets(dln,256,df)){dln[strcspn(dln,"\n")]=0;if(!dln[0])continue;
                        char o[640];int ol=!strcasecmp(dln,"homebox")&&hbr[0]
                            ?snprintf(o,640,"<option value=\"%s\">%s → %s</option>",dln,dln,hbr)
                            :snprintf(o,640,"<option>%s</option>",dln);EMIT(o,ol)}if(df)pclose(df);}
                else if(!strcmp(tag,"NO")){static char nb[131072];int nl2=notes_build(nb,131072,"notes");EMIT(nb,nl2)}
                else{EMIT(p,(int)(end+2-p))p=end+2;continue;}
                p=end+2;continue;}}
        EMIT(p,1)p++;
    }
    #undef EMIT
    shtml[shlen]=0;free(src);
}
static void sresph(int c,int code,const char*ct,const char*body,int bl,const char*cache){
    char h[256];int hl=snprintf(h,256,"HTTP/1.1 %d OK\r\nContent-Type:%s\r\nContent-Length:%d\r\nConnection:close\r\nCache-Control:%s\r\nAccess-Control-Allow-Origin:*\r\n\r\n",code,ct,bl,cache);
    (void)!write(c,h,(size_t)hl);if(bl)(void)!write(c,body,(size_t)bl);
}
/* static doc pages: NOT no-store, so the browser back/forward cache restores them instantly (0ms, no refetch) */
static void sresp(int c,int code,const char*ct,const char*body,int bl){sresph(c,code,ct,body,bl,"no-store");}
/* latency surfaces (/op /fw): COOP+COEP => crossOriginIsolated => performance.now() at 5us instead of 100us —
   without this the sub-ms meters quantize to .x0. Scoped here, NOT global: COEP would break pages that load
   cross-origin subresources. Both pages are fully self-contained; /op iframes stay same-origin. */
static void siso(int c,const char*body,int bl){
    char h[320];int hl=snprintf(h,320,"HTTP/1.1 200 OK\r\nContent-Type:text/html\r\nContent-Length:%d\r\nConnection:close\r\nCache-Control:no-store\r\nCross-Origin-Opener-Policy:same-origin\r\nCross-Origin-Embedder-Policy:require-corp\r\n\r\n",bl);
    (void)!write(c,h,(size_t)hl);if(bl)(void)!write(c,body,(size_t)bl);
}
static void sdoc(int c,const char*body,int bl){sresph(c,200,"text/html; charset=utf-8",body,bl,"no-cache");}
static int scmp(const void*a,const void*b){return strcmp((const char*)a,(const char*)b);}
static const int*g_bc;   /* /book freq sort: serve.log opens desc, tie=alpha */
static int g_bccmp(const void*a,const void*b){int x=*(const int*)a,y=*(const int*)b,d=g_bc[y]-g_bc[x];return d?d:x-y;}
static void qn(const char*req,char*nm){nm[0]=0;const char*q=strstr(req,"?n=");if(!q)return;q+=3;int i=0;for(;q[i]&&q[i]!='&'&&q[i]!=' '&&i<127;i++)nm[i]=q[i];nm[i]=0;}
static int bkok(const char*nm){return nm[0]&&!strchr(nm,'/')&&!strstr(nm,"..");}   /* a book name from the query: non-empty, stays inside adata/books */
static void qp(const char*req,const char*k,char*d,int n){d[0]=0;const char*q=strstr(req,k);if(!q)return;q+=strlen(k);int i=0;for(;q[i]&&q[i]!=' '&&q[i]!='&'&&i<n-1&&(isalnum((unsigned char)q[i])||q[i]=='-'||q[i]=='_'||q[i]=='.');i++)d[i]=q[i];d[i]=0;}
static void redir(int c,const char*url){char h[768];int hl=snprintf(h,768,"HTTP/1.1 302 Found\r\nLocation: %s\r\nContent-Length:0\r\nConnection:close\r\n\r\n",url);(void)!write(c,h,(size_t)hl);}
/* ?f=<path> → rel (urldecoded). returns 1 if valid (non-empty, no ..) */
static int docrel(const char*req,char*rel){rel[0]=0;const char*q=strstr(req,"?f=");if(!q)q=strstr(req,"&f=");if(!q)return 0;q+=3;
    int j=0;for(;*q&&*q!=' '&&*q!='&'&&j<P-1;q++){if(*q=='%'&&q[1]&&q[2]){char x[3]={q[1],q[2],0};rel[j++]=(char)strtol(x,0,16);q+=2;}else rel[j++]=*q=='+'?' ':*q;}rel[j]=0;
    return rel[0]&&!strstr(rel,"..");}
/* editor page: form POST + save button + escaped textarea + optional saved-banner (zero JS) */
static int bkcol(const char*nm,int col,char*o,int osz){int r=-1;char ip[P];snprintf(ip,P,"%s/git/books/index.txt",AROOT);  /* tab-col text of row nm; -1 = no row */
    size_t il=0;char*ix=readf(ip,&il);if(!ix)return -1;size_t nl=strlen(nm);o[0]=0;
    for(char*l=ix;l<ix+il;){char*e=memchr(l,'\n',(size_t)(ix+il-l)),*lim=e?e:ix+il;
        char*t1=memchr(l,'\t',(size_t)(lim-l)),*t2=t1?memchr(t1+1,'\t',(size_t)(lim-t1-1)):0;
        if(t1&&t2&&(size_t)(t2-t1-1)==nl&&!strncmp(t1+1,nm,nl)){r=0;
            char*p=l;int cc=1;while(cc<col&&p<lim){char*nt=memchr(p,'\t',(size_t)(lim-p));if(!nt)break;p=nt+1;cc++;}
            if(cc==col){char*nt=memchr(p,'\t',(size_t)(lim-p));int L=(int)((nt&&nt<lim?nt:lim)-p);if(L>=osz)L=osz-1;memcpy(o,p,(size_t)L);o[L]=0;r=L;}
            break;}
        if(e)l=e+1;else break;}
    free(ix);return r;}
static long bkpos(const char*nm){char b[24];return bkcol(nm,5,b,24)<0?-1:atol(b);}  /* col5 saved offset; -1 = no row */
static void bkfile(const char*nm,char*tf){  /* reading text resolution order, shared by reader + say */
    snprintf(tf,P,"%s/books/%s/output/explained.txt",AROOT,nm);
    if(access(tf,R_OK))snprintf(tf,P,"%s/books/%s/output/%s.txt",AROOT,nm,nm);
    if(access(tf,R_OK))snprintf(tf,P,"%s/books/%s/output/transcript.txt",AROOT,nm);  /* canonical elsewhere: help.c chat context, sync filter */
    if(access(tf,R_OK))snprintf(tf,P,"%s/books/%s/source.txt",AROOT,nm);}
static void docpage(int c,const char*rel,const char*body,size_t bl,const char*saved,const char*ds){
    char*h=malloc(bl*6+2048);if(!h){sresp(c,500,"text/plain","oom",3);return;}
    int hl=snprintf(h,2048,"<!doctype html><meta name=viewport content=\"width=device-width,initial-scale=1\"><title>%s</title><style>body{margin:0;background:#0b0b0b;color:#ddd;font:22px/1.5 ui-monospace,monospace}form{height:100dvh;display:flex;flex-direction:column}#bar{background:#000;padding:12px 9vw;border-bottom:1px solid #222;display:flex;gap:12px;align-items:center;overflow-wrap:anywhere}#bar b{color:#fff}button{flex:none;background:#222;color:#fff;border:1px solid #555;padding:3px 14px;font:inherit;cursor:pointer}#s{color:#bbb}textarea{width:100%%;flex:1;box-sizing:border-box;background:#0b0b0b;color:#ddd;border:0;outline:none;padding:24px 9vw;font:inherit;resize:none}</style><form method=POST enctype=\"text/plain\" action=\"/doc?f=%s%s\"><div id=bar><b>%s</b><button>save</button><span id=s>%s</span></div><textarea name=b spellcheck=false>",rel,rel,ds,rel,saved?saved:"");
    for(size_t i=0;i<bl;i++){char k=body[i];
        if(k=='<'){memcpy(h+hl,"&lt;",4);hl+=4;}
        else if(k=='&'){memcpy(h+hl,"&amp;",5);hl+=5;}
        else h[hl++]=k;}
    memcpy(h+hl,"</textarea></form>",18);hl+=18;
    sdoc(c,h,hl);free(h);}
/* recursive doc lister: one <a> per file, descends folders; display strips the section prefix (off) */
static int docls(char*h,int hl,const char*rel,int off){
    char dp[P];snprintf(dp,P,"%s/%s",SROOT,rel);DIR*d=opendir(dp);if(!d)return hl;
    struct dirent*e;char nm[256][96];int n=0;
    while((e=readdir(d))&&n<256){if(e->d_name[0]=='.')continue;snprintf(nm[n++],96,"%s",e->d_name);}closedir(d);
    for(int i=1;i<n;i++){char t[96];snprintf(t,96,"%s",nm[i]);int j=i-1;while(j>=0&&strcmp(nm[j],t)>0){snprintf(nm[j+1],96,"%s",nm[j]);j--;}snprintf(nm[j+1],96,"%s",t);}
    for(int i=0;i<n&&hl<(1<<18)-512;i++){char r2[P];snprintf(r2,P,"%s/%s",rel,nm[i]);
        char fp[P];snprintf(fp,P,"%s/%s",SROOT,r2);struct stat st;
        if(!stat(fp,&st)&&S_ISDIR(st.st_mode)){if(!strcmp(nm[i],"archive"))continue; /* archived: reachable via /doc?f= + fs only */
            hl+=snprintf(h+hl,(size_t)((1<<18)-hl),"<div style=color:#777;padding:4px 16px>%s/</div>",r2+off);hl=docls(h,hl,r2,(int)strlen(r2)+1);}
        else if(strstr(r2,"/archive/"))hl+=snprintf(h+hl,(size_t)((1<<18)-hl),"<a href=\"/doc?f=%s\">%s</a>",r2,r2+off);
        else hl+=snprintf(h+hl,(size_t)((1<<18)-hl),"<div style=\"display:flex\"><a style=\"flex:1\" href=\"/doc?f=%s\">%s</a><a href=\"#\" style=\"color:#555\" onclick=\"fetch('/doc-arch?f=%s').then(function(){location.reload()});return false\">arch</a></div>",r2,r2+off,r2);}
    return hl;}
static int ws_upgrade(int c,const char*req){
    const char*k=strstr(req,"Sec-WebSocket-Key: ");if(!k)return 0;
    k+=19;char key[64];int i=0;while(k[i]&&k[i]!='\r'&&i<60){key[i]=k[i];i++;}
    snprintf(key+i,(size_t)(64-i),"258EAFA5-E914-47DA-95CA-C5AB0DC85B11");
    unsigned char sha[20];sha1((unsigned char*)key,(size_t)(i+36),sha);
    static const char*b64="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    char acc[32];int j=0;
    for(int p=0;p<18;p+=3){unsigned v=(unsigned)(sha[p]<<16|sha[p+1]<<8|sha[p+2]);
        acc[j++]=b64[v>>18&63];acc[j++]=b64[v>>12&63];acc[j++]=b64[v>>6&63];acc[j++]=b64[v&63];}
    {unsigned v=(unsigned)(sha[18]<<16|sha[19]<<8);acc[j++]=b64[v>>18&63];acc[j++]=b64[v>>12&63];acc[j++]=b64[v>>6&63];acc[j++]='=';}
    acc[j]=0;
    char r[256];int rl=snprintf(r,256,"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n",acc);
    (void)!write(c,r,(size_t)rl);return 1;
}
static void ws_send(int c,const char*d,int n,int op){ /* 0x82 binary for term (split UTF-8 must not kill the socket), 0x81 text for ext reload */
    unsigned char h[10];int hl=2;h[0]=(unsigned char)op;
    if(n<126){h[1]=(unsigned char)n;}else{h[1]=126;h[2]=(unsigned char)(n>>8);h[3]=(unsigned char)(n&0xFF);hl=4;}
    (void)!write(c,h,(size_t)hl);(void)!write(c,d,(size_t)n);
}
static int ws_recv(int c,char*buf,int bsz){
    unsigned char h[2];if(read(c,h,2)!=2)return -1;
    int op=h[0]&0x0F,mask=h[1]&0x80,len=h[1]&0x7F;
    if(op==8)return -1;
    if(len==126){unsigned char e[2];(void)!read(c,e,2);len=(e[0]<<8)|e[1];}
    if(len>=bsz)len=bsz-1;
    unsigned char mk[4]={0,0,0,0};if(mask)(void)!read(c,mk,4);
    (void)!read(c,buf,(size_t)len);
    if(mask)for(int i=0;i<len;i++)buf[i]^=(char)mk[i%4];
    buf[len]=0;return len;
}
static void ws_term(int c,const char*target){
    int m,s;if(openpty(&m,&s,NULL,NULL,NULL)<0)return;
    char cty[64];{const char*tn=ttyname(s);snprintf(cty,64,"%s",tn?tn:"");}
    pid_t p=fork();
    if(!p){close(m);setsid();ioctl(s,TIOCSCTTY,0);dup2(s,0);dup2(s,1);dup2(s,2);close(s);
        setenv("TERM","xterm-256color",0);
        unsetenv("TMUX");unsetenv("TMUX_PANE");  /* serve may live in a pane; inherited TMUX would make `a tmux` switch the real client instead of grouped-attaching this pty */
        if(target&&!strncmp(target,"ssh:",4)){char d2[160];snprintf(d2,160,"%s",target+4);char*cl=strchr(d2,':');
            if(cl){*cl=0;char ses[192];snprintf(ses,192,"a:%s",cl+1);setenv("A_TMUX_SESSION",ses,1);}
            execlp("a","a","ssh",d2,(char*)0);}
        if(target&&target[0])execlp("a","a","tmux",target,(char*)0);
        else execlp("a","a","tmux",(char*)0);
        char*b[]={"bash","-l",NULL};execvp("bash",b);
        char*cc[]={"sh","-l",NULL};execvp("sh",cc);execl("/system/bin/sh","sh",(char*)0);_exit(1);}
    close(s);
    struct pollfd pf[2]={{c,POLLIN,0},{m,POLLIN,0}};char buf[4096];
    while(poll(pf,2,-1)>0){
        if(pf[1].revents&POLLIN){int n=(int)read(m,buf,4096);if(n<=0)break;ws_send(c,buf,n,0x82);}
        if(pf[0].revents&POLLIN){int n=ws_recv(c,buf,4096);if(n<0)break;
            if(buf[0]=='{'){char*co=strstr(buf,"\"cols\":");char*ro=strstr(buf,"\"rows\":");
                if(co&&ro){struct winsize w={.ws_row=(unsigned short)atoi(ro+7),.ws_col=(unsigned short)atoi(co+7)};ioctl(m,TIOCSWINSZ,&w);continue;}
                /* claim (/fw): switch-client onto itself re-takes window-size latest hidden — never resize-window, it manual-locks (def3b2ee); non-tmux pty no-ops */
                if(strstr(buf,"\"claim\"")){char cc[300];snprintf(cc,300,"s=$(tmux lsc -f '#{==:#{client_tty},%s}' -F '#{session_name}' 2>/dev/null);[ -n \"$s\" ]&&tmux switch-client -c %s -t \"$s\" 2>/dev/null",cty,cty);(void)!system(cc);continue;}}
            (void)!write(m,buf,(size_t)n);}
        if(pf[0].revents&(POLLHUP|POLLERR)||pf[1].revents&(POLLHUP|POLLERR))break;
    }
    kill(p,SIGHUP);close(m);waitpid(p,NULL,0);
}
static char rql[160];
typedef struct{time_t t;char*p,*w,*n,*m;size_t i;}rv_t;static int rvcmp(const void*a,const void*b){time_t x=((const rv_t*)a)->t,y=((const rv_t*)b)->t;return y>x?1:y<x?-1:0;}   /* /review rows, newest first */
static int rvdoc(const char*m,const char*dir,int k,char*out,int n){   /* a review: k-th path of <doc>a,b</doc> in an a done message, relative to its dir; 1 = found */
    const char*a=strstr(m,"<doc>"),*b=a?strstr(a,"</doc>"):0;if(!a||!b)return 0;a+=5;
    for(int i=0;a<b;i++){const char*e=memchr(a,',',(size_t)(b-a));if(!e)e=b;if(i==k){while(a<e&&*a==' ')a++;int l=(int)(e-a);while(l&&a[l-1]==' ')l--;if(l<=0)return 0;if(*a=='/')snprintf(out,(size_t)n,"%.*s",l,a);else snprintf(out,(size_t)n,"%s/%.*s",dir,l,a);return 1;}a=e+1;}
    return 0;}
static char*rvline(int N,char*f[5]){   /* done.log line N (ts, tmux window, name, dir, message) split in place; returns the buffer to free, NULL when no such line */
    char lf[P];snprintf(lf,P,"%s/done.log",DDIR);char*rl=readf(lf,NULL),*l=rl;for(int i=0;l&&i<N;i++){l=strchr(l,'\n');if(l)l++;}
    int k=0;if(l&&*l){char*e=strchr(l,'\n');if(e)*e=0;f[k++]=l;for(char*q=l;*q&&k<5;q++)if(*q=='\t'){*q=0;f[k++]=q+1;}}
    if(k<5){free(rl);return 0;}return rl;}
static int rvfl(char*f[5],char*fl){   /* the <diff>files</diff> of that a done, path characters only: the list reaches a shell */
    char*da=strstr(f[4],"<diff>"),*db=da?strstr(da,"</diff>"):0;fl[0]=0;if(da&&db){*db=0;snprintf(fl,P,"%s",da+6);*db='<';}
    return fl[0]&&fl[0]!='-'&&!strstr(fl,"..")&&strspn(fl,"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./ -")==strlen(fl)&&!strchr(f[3],'\'');}
static int rvpath(int N,int K,char*fp,int n){char*f[5];fp[0]=0;char*rl=rvline(N,f);int ok=rl?rvdoc(f[4],f[3],K,fp,n):0;free(rl);return ok;}   /* a review: K-th <doc> path of done.log line N; 1 = found */
static void udec(const char*s,char*o,size_t n){size_t k=0;for(;*s&&*s!='&'&&k<n-1;s++){if(*s=='%'&&isxdigit((unsigned char)s[1])&&isxdigit((unsigned char)s[2])){char h[3]={s[1],s[2],0};o[k++]=(char)strtol(h,0,16);s+=2;}else o[k++]=*s=='+'?' ':*s;}o[k]=0;}   /* one urlencoded form value, stops at & */
static void handle(int c){
    static char req[262144];int rn=0;
    while(rn<262143){int r=(int)read(c,req+rn,(size_t)(262143-rn));if(r<=0)break;rn+=r;req[rn]=0;if(strstr(req,"\r\n\r\n"))break;}
    if(rn<=0)return;
    char*cl=strstr(req,"Content-Length:"),*bb=strstr(req,"\r\n\r\n");
    if(cl&&bb){int want=(int)(bb-req+4)+atoi(cl+15);
        while(rn<want&&rn<262143){int r=(int)read(c,req+rn,(size_t)(want-rn));if(r<=0)break;rn+=r;}}
    req[rn]=0;
    {char*e=strchr(req,'\r');int L=e?(int)(e-req):0;if(L>159)L=159;memcpy(rql,req,(size_t)L);rql[L]=0;}
    int one=1;setsockopt(c,IPPROTO_TCP,TCP_NODELAY,&one,4);
    if(sdr[0]){ /* static site mode: files only, no UI routes */
        if(!strncmp(req,"POST /",6)){ /* hook: executable site/.post/<name> gets body as $1, stdout back */
            char nm[64];int i=0;const char*q=req+6;
            for(;*q&&*q!=' '&&*q!='/'&&*q!='?'&&i<63;q++)nm[i++]=*q;nm[i]=0;
            char hp[P*2];snprintf(hp,P*2,"%s/.post/%s",sdr,nm);
            if(i&&!strchr(nm,'.')&&!access(hp,X_OK)){
                char*b=strstr(req,"\r\n\r\n");b=b?b+4:(char*)"";
                int pp[2];if(pipe(pp)){sresp(c,500,"text/plain","x",1);return;}
                pid_t ch=fork();
                if(!ch){dup2(pp[1],1);dup2(pp[1],2);close(pp[0]);close(pp[1]);signal(SIGCHLD,SIG_DFL);signal(SIGPIPE,SIG_DFL);execl(hp,hp,b,(char*)0);_exit(1);}
                close(pp[1]);
                {static const char SH[]="HTTP/1.1 200 OK\r\nContent-Type:text/plain; charset=utf-8\r\nCache-Control:no-store\r\nAccess-Control-Allow-Origin:*\r\nConnection:close\r\n\r\n";(void)!write(c,SH,sizeof SH-1);}
                char sb[4096];int r;while((r=(int)read(pp[0],sb,4096))>0)if(write(c,sb,(size_t)r)<0)break; /* stream as produced; client gone -> child SIGPIPEs */
                close(pp[0]);waitpid(ch,0,0);return;}}
        if(strncmp(req,"GET /",5)){sresp(c,404,"text/plain","x",1);return;}
        char rel[P];int i=0;const char*q=req+5;
        for(;*q&&*q!=' '&&*q!='?'&&i<P-12;q++)rel[i++]=*q;
        rel[i]=0;
        if(strstr(rel,"..")||rel[0]=='.'||strstr(rel,"/.")){sresp(c,400,"text/plain","x",1);return;}
        char fp[P*2];snprintf(fp,P*2,"%s/%s%s",sdr,rel,(!i||rel[i-1]=='/')?"index.html":"");
        size_t fl=0;char*fd2=readf(fp,&fl);
        if(!fd2){snprintf(fp,P*2,"%s/%s/index.html",sdr,rel);fd2=readf(fp,&fl);} /* /x -> /x/index.html */
        if(!fd2){sresp(c,404,"text/plain","not found",9);return;}
        sresph(c,200,mime(fp,"text/plain"),fd2,(int)fl,"no-cache");free(fd2);return;}
    /* new full-page route? add a GET handler below + one nav link in ui_full.html line 9 (<div id=wm>). docs auto-list via /docs. */
    if(!strncmp(req,"GET /tasks",10)&&(req[10]==' '||req[10]=='?')){char cmd[P];snprintf(cmd,P,"python3 '%s/lib/task.py' page",SDIR);FILE*pp=popen(cmd,"r");size_t oc=1<<22,ol=0;char*o=malloc(oc);if(pp){ol=fread(o,1,oc-1,pp);pclose(pp);}o[ol]=0;sdoc(c,o,(int)ol);free(o);return;}   /* the task board = lib/task.py page(), served here, no bridge to i (Sean 2026-09-05) */
    if(!strncmp(req,"POST /tasks/",12)||!strncmp(req,"GET /tasks/spawn?n=",19)||!strncmp(req,"GET /tasks/resume?n=",20)){   /* board actions, all a-side: run <cmd> | set N <text> -> lib/task.py web|set on stdin · spawn N | resume N */
        char*bd=strstr(req,"\r\n\r\n");bd=bd?bd+4:(char*)"";char v[B*4]="",cmd[P],tf[P]="",*p;int n=0;
        if(req[0]=='G'){n=atoi(strchr(req,'=')+1);snprintf(cmd,P,"python3 '%s/lib/task.py' %s %d",SDIR,req[11]=='s'?"spawn":"resume",n);}
        else{int set=req[12]=='s';if((p=strstr(bd,set?"b=":"c=")))udec(p+2,v,sizeof v);if(set&&(p=strstr(bd,"n=")))n=atoi(p+2);
            snprintf(tf,P,"%s/tasks_in_%d.txt",TMP,(int)getpid());FILE*f=fopen(tf,"w");if(f){fputs(v,f);fclose(f);}
            if(set)snprintf(cmd,P,"python3 '%s/lib/task.py' set %d <'%s'",SDIR,n,tf);else snprintf(cmd,P,"python3 '%s/lib/task.py' web <'%s'",SDIR,tf);}
        FILE*pp=popen(cmd,"r");char out[B*2]="";size_t ol=pp?fread(out,1,sizeof out-1,pp):0;if(pp)pclose(pp);out[ol]=0;if(tf[0])unlink(tf);sresp(c,200,"text/plain; charset=utf-8",out,(int)ol);return;}
    if(!strncmp(req,"GET / ",6)||!strncmp(req,"GET /note ",10)||!strncmp(req,"GET /term",9)){
        char uf[P];struct stat us;snprintf(uf,P,"%s/lib/ui_full.html",SDIR);   /* regen when page file newer than cache (boot-frozen bug, cf /prompt) */
        if(shlen&&!stat(uf,&us)&&us.st_mtime>=sgen_t)html_gen();
        if(shlen)sresp(c,200,"text/html",shtml,shlen);else sresp(c,503,"text/plain","starting",8);return;}
    if(!strncmp(req,"GET /ws",7)&&(strstr(req,"Upgrade: websocket")||strstr(req,"upgrade: websocket"))){
        char tgt[64]={0};const char*qw=strstr(req,"?w=");
        if(qw){qw+=3;int j=0;for(int i=0;qw[i]&&qw[i]!=' '&&qw[i]!='&'&&qw[i]!='\r'&&j<63;i++){
            if(qw[i]=='%'&&qw[i+1]&&qw[i+2]){char x[3]={qw[i+1],qw[i+2],0};tgt[j++]=(char)strtol(x,NULL,16);i+=2;}
            else tgt[j++]=qw[i]=='+'?' ':qw[i];}tgt[j]=0;}
        if(ws_upgrade(c,req))ws_term(c,tgt);return;}
    if(!strncmp(req,"GET /api/u-status",17)){sresp(c,200,"application/json","{\"ok\":true}",11);return;}
    if(!strncmp(req,"GET /bm",7)&&(req[7]==' '||req[7]=='?')){const char*q=req+7;int js=!strncmp(q,"?js",3),tx=!strncmp(q,"?txt",4),cr=!strncmp(q,"?chrome",7);char fp[P];
        snprintf(fp,P,cr?"%s/local/bm_chrome.json":tx?"%s/bookmarks.txt":js?"%s/common/bm.js":"%s/common/bm.html",cr?AROOT:SROOT);
        size_t fl=0;char*d=readf(fp,&fl);if(!d){sresp(c,404,"text/plain","x",1);return;}
        sresph(c,200,js?"application/javascript":tx||cr?"text/plain; charset=utf-8":"text/html",d,(int)fl,"no-cache");free(d);return;}
    if(!strncmp(req,"GET /doc",8)&&(req[8]=='?'||req[8]==' ')){
        char rel[P];const char*m="? GET /doc?f=<path under adata/git> [&d=code for the a repo]";
        if(!docrel(req,rel)){sresp(c,400,"text/plain",m,(int)strlen(m));return;}
        char*dc=strstr(req,"d=code"),*eol=strstr(req,"\r\n");const char*ds=(dc&&eol&&dc<eol)?"&d=code":"";const char*base=*ds?SDIR:SROOT;
        char fp[P];snprintf(fp,P,"%s/%s",base,rel);size_t fl=0;char*fd=readf(fp,&fl);
        docpage(c,rel,fd?fd:"",fl,NULL,ds);free(fd);return;}   /* missing path -> blank editor; save creates it */
    if(!strncmp(req,"POST /doc",9)){
        char rel[P];if(!docrel(req,rel)){sresp(c,400,"text/plain","bad path",8);return;}
        char*dc=strstr(req,"d=code"),*eol=strstr(req,"\r\n");const char*ds=(dc&&eol&&dc<eol)?"&d=code":"";const char*base=*ds?SDIR:SROOT;
        char*bd=strstr(req,"\r\n\r\n"),*clh=strstr(req,"Content-Length:");
        if(!bd||!clh){sresp(c,400,"text/plain","no body",7);return;}
        bd+=4;int blen=atoi(clh+15);
        if(blen>250000){sresp(c,413,"text/plain","too big (>250KB) for editor save",32);return;}
        char*ct=bd;if(blen>=2&&!strncmp(bd,"b=",2)){ct+=2;blen-=2;}              /* strip enctype=text/plain field name */
        while(blen>0&&(ct[blen-1]=='\n'||ct[blen-1]=='\r'))blen--;              /* drop the trailing CRLF the form appends */
        int w=0;for(int i=0;i<blen;i++)if(ct[i]!='\r')ct[w++]=ct[i];            /* CRLF -> LF */
        char fp[P];snprintf(fp,P,"%s/%s",base,rel);
        {char*sl=strrchr(fp,'/');if(sl){*sl=0;mkdirp(fp);*sl='/';}}   /* create parent folders */
        char bf[64];snprintf(bf,64,"/tmp/_b%d",(int)getpid());   /* merge base = pre-save file (what the editor loaded), not stale HEAD */
        {size_t o=0;char*d=readf(fp,&o);FILE*b=fopen(bf,"w");if(b){if(d)(void)!fwrite(d,1,o,b);fclose(b);}free(d);}
        FILE*wf=fopen(fp,"w");int ok=0;if(wf){fwrite(ct,1,(size_t)w,wf);ok=!ferror(wf);fclose(wf);}
        char saved[512],gurl[B]="";
        if(ok){  /* 3-way merge onto origin/main's latest, push just this file via plumbing (survives local divergence); url or ERR */
            char gc[B*3];snprintf(gc,B*3,"cd '%s'&&F='%s';T=/tmp/_t$$;M=/tmp/_m$$;I=/tmp/_i$$;git fetch origin -q;git show origin/main:\"$F\">$T 2>/dev/null||cp '%s' $T;"
                "if git merge-file -p \"$F\" '%s' $T>$M;then cp $M \"$F\";GIT_INDEX_FILE=$I git read-tree origin/main;GIT_INDEX_FILE=$I git update-index --add --cacheinfo 100644,$(git hash-object -w $M),\"$F\";"
                "n=$(git commit-tree $(GIT_INDEX_FILE=$I git write-tree) -p origin/main -m \"doc: $F\");e=$(git push origin $n:main 2>&1)&&{ u=$(git config remote.origin.url);u=${u#*github.com[:/]};echo \"https://github.com/${u%%.git}/commit/$(git rev-parse --short $n)\";}||printf 'ERR %%s' \"$e\";"
                "else echo 'ERR overlapping edit on origin — reopen & redo on latest';fi;rm -f $T $M $I '%s'",base,rel,bf,bf,bf);
            pcmd(gc,gurl,B);gurl[strcspn(gurl,"\n")]=0;
            char ts[16];time_t t=time(0);strftime(ts,16,"%H:%M:%S",localtime(&t));
            if(!strncmp(gurl,"https",5)){const char*h=strrchr(gurl,'/')+1;snprintf(saved,512,"✓ %s pushed · <a href=\"%s\" style=color:#fff>%s</a>",ts,gurl,h);}
            else snprintf(saved,512,"✓ %s saved locally · ✗ not pushed — %s",ts,gurl[0]?gurl:"no git output");
        }else snprintf(saved,512,"✗ SAVE FAILED");
        {char lg[P];snprintf(lg,P,"%s/local/serve.log",AROOT);FILE*l=fopen(lg,"a");if(l){fprintf(l,"save %s %s\n",rel,ok?gurl:"WRITEFAIL");fclose(l);}}
        size_t nl=0;char*nf=readf(fp,&nl);
        docpage(c,rel,nf?nf:ct,nf?nl:(size_t)w,saved,ds);free(nf);return;}
    if(!strncmp(req,"POST /book",10)&&(req[10]=='?'||req[10]==' ')){char nm[128];qn(req,nm);   /* guard: /bookmark shares the prefix */
        char po[24]="0";char*bd=strstr(req,"\r\n\r\n"),*pp=bd?strstr(bd+4,"pos="):0;
        if(pp){pp+=4;int i=0;for(;pp[i]>='0'&&pp[i]<='9'&&i<23;i++)po[i]=pp[i];po[i]=0;}
        if(bkok(nm)&&!fork()){int n=open("/dev/null",O_WRONLY);if(n>=0)dup2(n,1);execlp("a","a","book","pos",nm,po,(char*)0);_exit(1);}
        sresp(c,200,"text/plain","ok",2);return;}
    if(!strncmp(req,"GET /bookpos",12)){char nm[128];qn(req,nm);  /* readback: reader verifies its save landed (POST ok is pre-fork) */
        if(!bkok(nm)){sresp(c,400,"text/plain","x",1);return;}
        char b[24];int bl=snprintf(b,24,"%ld",bkpos(nm));sresp(c,200,"text/plain",b,bl);return;}
    if(!strncmp(req,"GET /bookmark",13)){char nm[128];qn(req,nm);  /* csv of col6 mark offsets */
        if(!bkok(nm)){sresp(c,400,"text/plain","x",1);return;}
        char b[512];int L=bkcol(nm,6,b,512);sresp(c,200,"text/plain",b,L>0?L:0);return;}
    if(!strncmp(req,"POST /bookmark",14)){char nm[128];qn(req,nm);  /* add=|del=<off> → RMW col6 under flock, reply authoritative csv */
        char*bd2=strstr(req,"\r\n\r\n"),*p=0;char op=0;long ov=-1;
        if(bd2){if((p=strstr(bd2+4,"add=")))op='a';else if((p=strstr(bd2+4,"del=")))op='d';if(p)ov=atol(p+4);}
        if(!bkok(nm)||!op||ov<0){sresp(c,400,"text/plain","x",1);return;}
        char ip[P];snprintf(ip,P,"%s/git/books/index.txt",AROOT);
        int lf=open(ip,O_RDWR|O_CREAT,0644);if(lf<0){sresp(c,500,"text/plain","x",1);return;}
        flock(lf,LOCK_EX);
        long mk[64];int km=0;char cur[512];
        if(bkcol(nm,6,cur,512)>0)for(char*q=cur;*q&&km<64;){long v=atol(q);if(v>=0)mk[km++]=v;char*cm=strchr(q,',');if(!cm)break;q=cm+1;}
        if(op=='d'){int w=0;for(int i=0;i<km;i++)if(mk[i]!=ov)mk[w++]=mk[i];km=w;}
        else{int dup=0;for(int i=0;i<km;i++)dup|=mk[i]==ov;if(!dup&&km<64)mk[km++]=ov;
            for(int i=1;i<km;i++){long x=mk[i];int j=i-1;for(;j>=0&&mk[j]>x;j--)mk[j+1]=mk[j];mk[j+1]=x;}}  /* panel = book order */
        char csv[512];int cv=0;for(int i=0;i<km;i++)cv+=snprintf(csv+cv,(size_t)(512-cv),"%s%ld",i?",":"",mk[i]);
        size_t il=0;char*ix=readf(ip,&il);size_t nl2=strlen(nm);int found=0;
        char*out=malloc(il+nl2+600);size_t ol=0;
        if(ix)for(char*l=ix;l<ix+il;){char*e=memchr(l,'\n',(size_t)(ix+il-l));size_t ll=e?(size_t)(e-l):(size_t)(ix+il-l);
            char*t1=memchr(l,'\t',ll),*t2=t1?memchr(t1+1,'\t',ll-(size_t)(t1+1-l)):0;
            if(!found&&t1&&t2&&(size_t)(t2-t1-1)==nl2&&!strncmp(t1+1,nm,nl2)){found=1;
                size_t k=0;int tabs=0;for(;k<ll&&tabs<5;k++){out[ol+k]=l[k];if(l[k]=='\t')tabs++;}ol+=k;   /* cols 1-5 verbatim */
                if(tabs<5){for(size_t z=0;z<ll-k;z++)out[ol+z]=l[k+z];ol+=ll-k;while(tabs++<5)out[ol++]='\t';}   /* short row: keep rest, pad */
                memcpy(out+ol,csv,(size_t)cv);ol+=(size_t)cv;}
            else{memcpy(out+ol,l,ll);ol+=ll;}
            out[ol++]='\n';l=e?e+1:ix+il;}
        if(!found)ol+=(size_t)snprintf(out+ol,nl2+600,"\t%s\t\t\t\t%s\n",nm,csv);
        char tp[P];snprintf(tp,P,"%s.new",ip);FILE*f=fopen(tp,"w");int ok=f&&fwrite(out,1,ol,f)==ol&&!fclose(f)&&!rename(tp,ip);
        free(ix);free(out);flock(lf,LOCK_UN);close(lf);
        if(!ok){sresp(c,500,"text/plain","x",1);return;}
        sresp(c,200,"text/plain",csv,cv);return;}
    if(!strncmp(req,"GET /booksay",12)){char nm[128];qn(req,nm);  /* speak from pos via `a say` (edge ryan); one group at a time, new play or stop=1 kills it */
        if(!bkok(nm)){sresp(c,400,"text/plain","x",1);return;}
        char sf2[P];snprintf(sf2,P,"%s/local/.booksay.pid",AROOT);   /* fork-per-conn: say-group pid must survive the request child */
        {size_t pl=0;char*ps=readf(sf2,&pl);
         if(ps){pid_t op=(pid_t)atol(ps);free(ps);
            if(op>1){char cp[64],cb[256];snprintf(cp,64,"/proc/%d/cmdline",op);   /* direct read: procfs st_size=0 so readf returns empty */
                int cf=open(cp,O_RDONLY);ssize_t cn=cf<0?-1:read(cf,cb,255);if(cf>=0)close(cf);
                if((cn>3&&memmem(cb,(size_t)cn,"say",3))||(cn<0&&!kill(-op,0)))kill(-op,SIGTERM);}   /* leader = exec-chained bash lib/say.sh (substring, reuse-guarded), or leader gone but group (uvx/ffplay) lives — ours by construction, reap */
            unlink(sf2);}}
        char*pq=strstr(req,"pos=");
        if(!pq||strstr(req,"stop=")){sresp(c,200,"text/plain","off",3);return;}
        char tf[P];bkfile(nm,tf);size_t tl=0;char*txt=readf(tf,&tl);
        if(!txt){sresp(c,404,"text/plain","x",1);return;}
        size_t o=(size_t)atol(pq+4);if(o>=tl)o=tl?tl-1:0;
        size_t e2=o+1400>tl?tl:o+1400,x=e2;   /* sentence-snap the tail within +300 */
        while(x<tl&&x<e2+300&&!(strchr(".!?",txt[x-1])&&(txt[x]==' '||txt[x]=='\n')))x++;
        if(x<tl)e2=x;
        char*ch=malloc(e2-o+1);memcpy(ch,txt+o,e2-o);ch[e2-o]=0;free(txt);
        pid_t k=fork();
        if(!k){setsid();int dn=open("/dev/null",O_WRONLY);if(dn>=0){dup2(dn,1);dup2(dn,2);}
            signal(SIGCHLD,SIG_DFL);execlp("a","a","say",ch,(char*)0);_exit(127);}
        free(ch);
        if(k>0){char pb[24];int pn=snprintf(pb,24,"%d",k);int pfd=open(sf2,O_WRONLY|O_CREAT|O_TRUNC,0644);if(pfd>=0){(void)!write(pfd,pb,(size_t)pn);close(pfd);}}
        sresp(c,200,"text/plain","on",2);return;}
    if(!strncmp(req,"GET /bookarchive",16)){char nm[128];qn(req,nm);  /* dot-prefix rename = archive; restore: a book archive <substr> */
        if(!bkok(nm)||nm[0]=='.'){sresp(c,400,"text/plain","bad book",8);return;}
        char fr[P],to[P];snprintf(fr,P,"%s/books/%s",AROOT,nm);snprintf(to,P,"%s/books/.%s",AROOT,nm);
        if(rename(fr,to)){sresp(c,404,"text/plain","x",1);return;}sresp(c,200,"text/plain","ok",2);return;}
    if(!strncmp(req,"POST /up?",9)){char nm[96];qp(req,"&n=",nm,96);char*bp=strstr(req,"\r\n\r\n");char f2[P];snprintf(f2,P,"%s/%s",TMP,nm);  /* <=200KB slices; qp bars / */
        int fd=*nm&&bp?open(f2,O_WRONLY|O_CREAT|(req[11]=='1'?O_TRUNC:O_APPEND),0644):-1;
        sresp(c,fd<0||write(fd,bp+4,(size_t)(rn-(bp+4-req)))<0?400:200,"text/plain","",0);return;}
    if(!strncmp(req,"GET /book",9)&&(req[9]=='?'||req[9]==' ')){char nm[128];qn(req,nm);
        if(!nm[0]){
            int au=!!strstr(req,"sort=author"),alp=!!strstr(req,"sort=name");   /* default = most-opened first; ?sort=name | ?sort=author */
            char bd[P];snprintf(bd,P,"%s/books",AROOT);
            static char names[4096][128];int n=0;DIR*d=opendir(bd);struct dirent*e;
            if(d){while((e=readdir(d))&&n<4096){if(e->d_name[0]=='.'||!strcmp(e->d_name,"book.py"))continue;
                char dp[P];snprintf(dp,P,"%s/%s",bd,e->d_name);struct stat st;if(!stat(dp,&st)&&S_ISDIR(st.st_mode))snprintf(names[n++],128,"%s",e->d_name);}closedir(d);}
            {char ip[P];snprintf(ip,P,"%s/git/books/index.txt",AROOT);size_t il=0;char*ix=readf(ip,&il);  /* merge synced index: registered-elsewhere books appear, pull on open */
             if(ix){for(char*l=ix;l<ix+il&&n<4096;){char*e2=memchr(l,'\n',(size_t)(ix+il-l)),*lim=e2?e2:ix+il;
                char*t1=memchr(l,'\t',(size_t)(lim-l)),*t2=t1?memchr(t1+1,'\t',(size_t)(lim-t1-1)):0;
                if(t1&&t2&&t2>t1+1&&(size_t)(t2-t1-1)<127){char bn[128];snprintf(bn,128,"%.*s",(int)(t2-t1-1),t1+1);
                    int dup=0;for(int i=0;i<n;i++)if(!strcmp(names[i],bn)){dup=1;break;}
                    if(!dup&&bn[0]&&bn[0]!='.')snprintf(names[n++],128,"%s",bn);}
                if(e2)l=e2+1;else break;}free(ix);}}
            static int idx[4096];   /* author mode sorts an index by resolved-author key (book.c) */
            if(au){bk_resolve(names,n);g_ak=bk_ak;for(int i=0;i<n;i++)idx[i]=i;qsort(idx,(size_t)n,sizeof(int),g_akcmp);}
            else{qsort(names,(size_t)n,128,scmp);for(int i=0;i<n;i++)idx[i]=i;
                if(!alp){static int cnt[4096];   /* fork-per-conn: fresh zeroed copy each request */
                    char lp[P];snprintf(lp,P,"%s/local/serve.log",AROOT);char*lg=readf(lp,NULL);
                    if(lg){for(char*p=lg;(p=strstr(p,"GET /book?n="));){p+=12;char bn[128];int j=0;
                        for(;*p&&*p!=' '&&*p!='&'&&j<127;p++){if(*p=='%'&&p[1]&&p[2]){char x[3]={p[1],p[2],0};bn[j++]=(char)strtol(x,0,16);p+=2;}else bn[j++]=*p;}
                        bn[j]=0;for(int i=0;i<n;i++)if(!strcmp(names[i],bn)){cnt[i]++;break;}}
                    free(lg);}g_bc=cnt;qsort(idx,(size_t)n,sizeof(int),g_bccmp);}}
            int cap=1<<20;char*h=malloc((size_t)cap);int hl=snprintf(h,(size_t)cap,
                "<!doctype html><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\">"
                "<style>body{background:#0b0b0b;color:#ddd;margin:0;font:18px/1.35 system-ui}h3{color:#fff;padding:14px 16px 6px;margin:0}"
                ".r{display:flex;align-items:center;gap:12px;padding:11px 16px;border-bottom:1px solid #1a1a1a}.r:hover{background:#161616}"
                ".t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fff;text-decoration:none}.r.x .t{color:#666}.r.x .s:before{content:\"no txt\";color:#c33;margin-right:7px}"
                ".c{flex:none;color:#999;text-decoration:none;font-size:18px}.s{flex:none;min-width:48px;text-align:right;color:#666;font:13px ui-monospace,monospace;text-transform:uppercase}.s a{color:#666;text-decoration:none}.s a:hover{color:#fff}"
                ".h{position:sticky;top:0;background:#0b0b0b;color:#fff;font-weight:700;font-size:15px;letter-spacing:.09em;text-transform:uppercase;padding:16px 16px 5px;border-bottom:1px solid #1a1a1a}"
                ".r.in{padding-left:30px}.nav{padding:4px 16px 10px;font-size:17px}.nav a{color:#888;text-decoration:none;margin-right:14px}.nav a.on{color:#fff;font-weight:600}"
                "#q,#ab{display:block;box-sizing:border-box;width:calc(100%% - 32px);margin:2px 16px 8px;padding:9px 12px;background:#161616;color:#fff;border:1px solid #2a2a2a;border-radius:8px;font:18px system-ui;outline:none}#qms{float:right;color:#555;font:11px ui-monospace,monospace}</style>"
                "<script>function _ax(e){var a=e.target.closest('a.x');if(!a)return;e.preventDefault();e.stopImmediatePropagation();"
                "if(e.type!='pointerdown')return;fetch(a.href).then(function(r){if(r.ok){a.closest('.r').style.opacity=.35;a.outerHTML='<span class=c>\xe2\x9c\x93 archived</span>'}else a.textContent='\xe2\x9c\x97'},function(){a.textContent='\xe2\x9c\x97'})}"
                "addEventListener('pointerdown',_ax,true);addEventListener('click',_ax,true)</script>" TAPJS
                "<h3>books (%d)</h3><div class=nav><a%s href=\"/book\">by freq</a><a%s href=\"/book?sort=name\">by name</a><a%s href=\"/book?sort=author\">by author</a><span id=qms></span></div>"
                "<input id=q placeholder=\"type to search\" autofocus>"
                "<script>q.oninput=function(){var t0=performance.now(),v=q.value.toLowerCase(),hd=0,vn=0,ht='';"
                "document.querySelectorAll('.h,.r').forEach(function(e){if(e.className=='h'){if(hd)hd.style.display=vn?'':'none';hd=e;ht=e.textContent.toLowerCase();vn=0}"
                "else{var m=(e.textContent+' '+ht).toLowerCase().indexOf(v)>=0;e.style.display=m?'':'none';vn+=m}});"
                "if(hd)hd.style.display=vn?'':'none';qms.textContent=(performance.now()-t0).toFixed(2)+'ms'};"
                "q.onkeydown=function(e){if(e.key=='Enter'){var r=document.querySelector('.r:not([style*=none]) a.t');if(r)location=r.href}};"
                "onkeydown=function(e){if(document.activeElement!=q&&!e.ctrlKey&&!e.metaKey&&(e.key.length==1||e.key=='Backspace'))q.focus()}</script>"
                "<button id=ab onpointerdown=af.click()>+ add book</button><input id=af type=file hidden><script>af.onchange=async()=>{var f=af.files[0],m=f.name.replace(/[^\\w.]+/g,'-');for(var o=0;o<f.size;o+=2e5)await fetch('/up?s='+ +!o+'&n='+m,{method:'POST',body:f.slice(o,o+2e5)}),ab.textContent=o;navigator.sendBeacon('/api/omni','q=cmd+a+book+add+${TMPDIR:-/tmp}/'+m);setTimeout(\"location=''\",999)}</script>",
                n,(au||alp)?"":" class=on",alp?" class=on":"",au?" class=on":"");
            const char*ex[]={"txt","pdf","epub","azw3","mobi","docx",0};char pk[96]="";
            for(int ii=0;ii<n&&hl<cap-2048;ii++){int i=idx[ii];
                if(au&&strcmp(bk_ak[i],pk)){strcpy(pk,bk_ak[i]);   /* sticky author header per run */
                    char ah[128];const char*a=bk_ad[i];int j=0;for(;a[j]&&j<120;j++)ah[j]=a[j]=='-'?' ':a[j];ah[j]=0;
                    hl+=snprintf(h+hl,(size_t)(cap-hl),"<div class=h>%s</div>",ah);}
                char tf[P];snprintf(tf,P,"%s/%s/output/explained.txt",bd,names[i]);int has=!access(tf,R_OK);
                if(!has){snprintf(tf,P,"%s/%s/output/%s.txt",bd,names[i],names[i]);has=!access(tf,R_OK);}
                if(!has){snprintf(tf,P,"%s/%s/output/transcript.txt",bd,names[i]);has=!access(tf,R_OK);}
                if(!has){snprintf(tf,P,"%s/%s/source.txt",bd,names[i]);has=!access(tf,R_OK);}
                char xt[512]="";int xl=0;   /* every source.* becomes a clickable badge (was: first ext, dead text) */
                for(int k=0;ex[k];k++){snprintf(tf,P,"%s/%s/source.%s",bd,names[i],ex[k]);
                    if(!access(tf,R_OK))xl+=snprintf(xt+xl,(size_t)(512-xl),"<a href=\"/bookfile?n=%s&f=source.%s\">%s</a> ",names[i],ex[k],ex[k]);}
                char lb[360];snprintf(lb,360,"%s",names[i]);bk_mid(lb,96);
                hl+=snprintf(h+hl,(size_t)(cap-hl),"<div class=\"r %s %s\"><a class=t href=\"/book?n=%s\">%s</a><a class=c href=\"/bookdir?n=%s\" title=\"all versions (file manager)\">\xf0\x9f\x97\x82</a><a class=c href=\"/bookcloud?n=%s\" title=\"open in cloud\">\xe2\x98\x81</a><a class=\"c x\" href=\"/bookarchive?n=%s\" title=\"archive (restorable)\">\xf0\x9f\x97\x84</a><span class=s>%s</span></div>",has?"":"x",au?"in":"",names[i],lb,names[i],names[i],names[i],xt);}
            sdoc(c,h,hl);free(h);return;}
        if(!bkok(nm)){sresp(c,400,"text/plain","bad book",8);return;}
        char tf[P];bkfile(nm,tf);
        size_t tl=0;char*txt=readf(tf,&tl);
        if(!txt){char ip[P];snprintf(ip,P,"%s/git/books/index.txt",AROOT);size_t il=0;char*ix=readf(ip,&il);int reg=0;  /* in synced index but not local: pull in bg, page retries */
            if(ix){char pat[140];snprintf(pat,140,"\t%s\t",nm);reg=!!strstr(ix,pat);free(ix);}
            if(reg){if(!fork()){signal(SIGCHLD,SIG_DFL);int z=open("/dev/null",O_WRONLY);if(z>=0){dup2(z,1);dup2(z,2);}execlp("a","a","book","pull",nm,(char*)0);_exit(1);}
                char b[512];int bl=snprintf(b,512,"<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=5><body style=\"background:#0b0b0b;color:#fff;font:16px ui-monospace,monospace;padding:40px\">syncing %s from cloud\xe2\x80\xa6 auto-retrying</body>",nm);
                sdoc(c,b,bl);return;}
            sresp(c,404,"text/plain","no text — a book transcribe first",34);return;}
        long pos=bkpos(nm);if(pos<0)pos=0;
        char*esc=malloc(tl*5+1);size_t el=0;  /* escape &<> so text node==exact file chars → caret offset==file offset */
        for(size_t i=0;i<tl;i++){char ch=txt[i];
            if(ch=='&'){memcpy(esc+el,"&amp;",5);el+=5;}
            else if(ch=='<'){memcpy(esc+el,"&lt;",4);el+=4;}
            else if(ch=='>'){memcpy(esc+el,"&gt;",4);el+=4;}
            else esc[el++]=ch;}
        free(txt);
        size_t cap=el+16384;char*pg=malloc(cap);int hl=snprintf(pg,cap,   /* head+tail JS ~6KB and growing; 4096 truncated the script (snprintf returns would-be len → heap garbage served) */
            "<!doctype html><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\">"
            "<style>html,body{margin:0;background:#0b0b0b;overflow:hidden;height:100%%;touch-action:none;overscroll-behavior:none}::-webkit-scrollbar{display:none}"
            /* true pagination: bk is a fixed full-screen clipped box; flipping sets bk.scrollTop by whole screens, body never scrolls */
            "#bk{position:fixed;top:0;bottom:0;left:0;right:0;max-width:760px;margin:0 auto;overflow:hidden;scrollbar-width:none;white-space:pre-wrap;overflow-wrap:break-word;color:#ddd;font:18px/1.75 Georgia,serif;padding:0 18px;box-sizing:border-box}"
            /* one top-right line: marks controls + hud share #tr so nothing stacks (Sean: only take one line) */
            "#tr{position:fixed;top:0;right:0;display:flex;align-items:center;background:#000;opacity:.85;z-index:9}"
            "#tr a{color:#fff;text-decoration:none;padding:5px 10px;font:14px ui-monospace,monospace}"
            "#hud{color:#fff;font:12px ui-monospace,monospace;padding:4px 8px 4px 0}"
            "#mp{display:none;position:fixed;top:28px;right:0;max-width:88vw;max-height:60vh;overflow:auto;background:#000;color:#fff;font:13px ui-monospace,monospace;z-index:9}"
            "#mp div{padding:9px 10px;border-bottom:1px solid #1a1a1a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#mp b{color:#ccc;font-weight:400;padding:0 8px}</style>"
            "<div id=tr><a id=ms>\xe2\x96\xb6</a><a id=ma>+\xe2\x9a\x91</a><a id=mt>\xe2\x9a\x91</a><div id=hud></div></div><div id=mp></div><pre id=bk>");
        memcpy(pg+hl,esc,el);hl+=(int)el;free(esc);
        hl+=snprintf(pg+hl,cap-(size_t)hl,  /* browsers split big text into 64K chunk nodes — map (chunk,local)<->global offset */
            "</pre><script>var N=\"%s\",P=%ld,K=bk,H=hud,ns=[].slice.call(K.childNodes),T=0,bs=[],co=P;"
            "for(var i=0;i<ns.length;i++){bs.push(T);T+=ns[i].length||0;}"
            "function C(x,y){var n,o,r;if(document.caretRangeFromPoint){r=document.caretRangeFromPoint(x,y);if(!r)return null;n=r.startContainer;o=r.startOffset;}else if(document.caretPositionFromPoint){r=document.caretPositionFromPoint(x,y);if(!r)return null;n=r.offsetNode;o=r.offset;}else return null;for(var j=0;j<ns.length;j++)if(ns[j]===n)return bs[j]+o;return null;}"
            "function O(){var r=K.getBoundingClientRect(),x=r.left+18,o;for(var y=2;y<120;y+=8){o=C(x,r.top+y);if(o!=null)return o;}return co;}"
            "function R(f){var i=ns.length-1;while(i>0&&f<bs[i])i--;var g=document.createRange();g.setStart(ns[i],Math.min(f-bs[i],ns[i].length));g.collapse(true);var c=g.getClientRects()[0]||g.getBoundingClientRect();K.scrollTop+=c.top-K.getBoundingClientRect().top;pg=Math.round(K.scrollTop/ph());}"
            /* sync truth by readback: POST, then after uv settles GET /bookpos and compare. Steady '✓' while verified
               (load counts: pos came from the index), '✗sync' while a save can't be confirmed (10s re-save loop) —
               absence would be ambiguous with the feature being broken, so healthy has a mark that never changes */
            /* time inline: T/D and most single letters are taken by the pager vars — a helper name here broke the whole script once */
            "var sx=' \xc2\xb7 \xe2\x9c\x93'+new Date().toTimeString().slice(0,5),sq=0,rt;function U(b){H.textContent=(b||'pg '+(pg+1)+'/'+(NP()+1))+sx;}"
            "function M(ok){clearTimeout(rt);if(!ok)rt=setTimeout(S,10000);var s=ok?' \xc2\xb7 \xe2\x9c\x93'+new Date().toTimeString().slice(0,5):' \xc2\xb7 \xe2\x9c\x97sync';if(s!=sx){sx=s;U();}}"
            "function V(v,q){fetch('/bookpos?n='+encodeURIComponent(N)).then(function(r){return r.text()}).then(function(t){if(q==sq)M(parseInt(t)===v)},function(){if(q==sq)M(0)})}"
            "function S(){co=O();var q=++sq,v=co,b='pos='+v,u='/book?n='+encodeURIComponent(N);fetch(u,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b}).then(function(r){if(q!=sq)return;if(r.ok)setTimeout(function(){V(v,q)},2000);else M(0)},function(){if(q==sq)M(0)})}"
            "function B(){var b='pos='+O();if(navigator.sendBeacon)navigator.sendBeacon('/book?n='+encodeURIComponent(N),new Blob([b],{type:'application/x-www-form-urlencoded'}))}"
            /* true pagination: whole-screen pages via bk.scrollTop (body can't scroll); flip on pointer DOWN (depress, not lift)/wheel/keys — scrollTop is sync = sub-ms, paints next vsync */
            "var lh=parseFloat(getComputedStyle(K).lineHeight),pg=0,fm=0,st;"
            "function ph(){return Math.max(lh,Math.floor(K.clientHeight/lh)*lh);}"
            "function NP(){return Math.max(0,Math.ceil((K.scrollHeight-K.clientHeight)/ph()));}"
            "function G(p){p=Math.max(0,Math.min(p,NP()));var t=performance.now();K.scrollTop=p*ph();pg=p;fm=performance.now()-t;U('pg '+(pg+1)+'/'+(NP()+1)+' · '+fm.toFixed(2)+'ms');clearTimeout(st);st=setTimeout(S,400);}"
            "addEventListener('pointerdown',function(e){G(pg+(e.clientX<innerWidth/3?-1:1));e.preventDefault();});"
            "addEventListener('wheel',function(e){G(pg+(e.deltaY>0?1:-1));e.preventDefault();},{passive:false});"
            "addEventListener('keydown',function(e){var k=e.key;if(k===' '||k==='PageDown'||k==='ArrowRight'||k==='ArrowDown')G(pg+1);else if(k==='b'||k==='PageUp'||k==='ArrowLeft'||k==='ArrowUp')G(pg-1);else return;e.preventDefault();});"
            "addEventListener('resize',function(){G(pg);});"
            "requestAnimationFrame(function(){if(P>0){R(P);K.scrollTop=pg*ph();}U();});"
            "addEventListener('pagehide',B);addEventListener('visibilitychange',function(){if(document.hidden)B();});"
            /* marks: col6 csv offsets, server reply is the authoritative list; rows self-label from the text at the offset.
               controls stopPropagation so the global pointerdown pager doesn't flip; TX = unescaped text, offsets == file offsets */
            "var TX=K.textContent,mks=[];"
            "function EH(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}"
            "function MR(t){mks=t?t.split(',').filter(Boolean).map(Number):[];mt.textContent='\xe2\x9a\x91'+(mks.length||'');"
            "mp.innerHTML=mks.map(function(o){return '<div data-o='+o+'><b data-x='+o+'>\xe2\x9c\x95</b>'+EH(TX.substr(o,44).replace(/\\s+/g,' '))+'</div>'}).join('')||'<div>no marks \xe2\x80\x94 +\xe2\x9a\x91 adds this page</div>'}"
            "function MW(b){fetch('/bookmark?n='+encodeURIComponent(N),{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b}).then(function(r){return r.text()}).then(MR)}"
            "ma.addEventListener('pointerdown',function(e){e.stopPropagation();e.preventDefault();MW('add='+O())});"
            "mt.addEventListener('pointerdown',function(e){e.stopPropagation();e.preventDefault();mp.style.display=mp.style.display=='block'?'none':'block'});"
            "mp.addEventListener('pointerdown',function(e){e.stopPropagation();e.preventDefault();var x=e.target.getAttribute('data-x');if(x){MW('del='+x);return}"
            "var r=e.target.closest('[data-o]');if(r){R(+r.getAttribute('data-o'));K.scrollTop=pg*ph();U();clearTimeout(st);st=setTimeout(S,400);mp.style.display='none'}});"
            "fetch('/bookmark?n='+encodeURIComponent(N)).then(function(r){return r.text()}).then(MR);"
            /* ▶ = speak from here via server-side `a say`; server owns the single say-group, reply is the state */
            "var sp=0;ms.addEventListener('pointerdown',function(e){e.stopPropagation();e.preventDefault();"
            "fetch('/booksay?n='+encodeURIComponent(N)+(sp?'&stop=1':'&pos='+O())).then(function(r){return r.text()}).then(function(t){sp=t=='on'?1:0;ms.textContent=sp?'\\u25a0':'\\u25b6'},function(){sp=0;ms.textContent='\\u25b6'})});"
            "</script>",nm,pos);
        sdoc(c,pg,hl);free(pg);return;}
    if(!strncmp(req,"GET /bookfile",13)){char nm[128];qn(req,nm);  /* raw book asset with real mime → pdf opens in the browser's viewer */
        char rel[P];if(!bkok(nm)||!docrel(req,rel)){sresp(c,400,"text/plain","bad book",8);return;}
        char fp[P];snprintf(fp,P,"%s/books/%s/%s",AROOT,nm,rel);
        size_t bl=0;char*b=readf(fp,&bl);if(!b){sresp(c,404,"text/plain","x",1);return;}
        sfile(c,mime(rel,"application/octet-stream"),b,bl,"max-age=300");free(b);return;}
    if(!strncmp(req,"GET /bookcloud",14)){char nm[128];qn(req,nm);  /* → exact Drive file URL for a-gdrive:books/<name>/source.* (else Drive search) */
        if(!bkok(nm)){sresp(c,400,"text/plain","bad book",8);return;}
        char path[256];snprintf(path,256,"a-gdrive:books/%s/",nm);char id[128]="";int pp[2];
        if(!pipe(pp)){pid_t ch=fork();
            if(!ch){dup2(pp[1],1);close(pp[0]);close(pp[1]);int z=open("/dev/null",O_WRONLY);if(z>=0)dup2(z,2);
                execlp("rclone","rclone","lsf","--files-only","--format","ip","--separator",";",path,(char*)0);_exit(1);}
            close(pp[1]);char o[8192];int ol=0,r;while(ol<8191&&(r=(int)read(pp[0],o+ol,(size_t)(8191-ol)))>0)ol+=r;close(pp[0]);waitpid(ch,NULL,0);o[ol]=0;
            for(char*l=o;l&&*l;){char*e=strchr(l,'\n');if(e)*e=0;char*s=strchr(l,';');
                if(s&&!strncmp(s+1,"source.",7)){*s=0;snprintf(id,128,"%s",l);break;}
                if(e)l=e+1;else break;}}
        char url[600];
        if(id[0])snprintf(url,600,"https://drive.google.com/file/d/%s/view",id);
        else{char q[256];int j=0;for(int i=0;nm[i]&&j<250;i++){char d=((nm[i]>='a'&&nm[i]<='z')||(nm[i]>='0'&&nm[i]<='9'))?nm[i]:'+';if(d=='+'&&j&&q[j-1]=='+')continue;q[j++]=d;}q[j]=0;
            snprintf(url,600,"https://drive.google.com/drive/search?q=%s",q);}
        redir(c,url);return;}
    if(!strncmp(req,"GET /bookdir",12)){char nm[128];qn(req,nm);  /* open the book's folder in the OS file manager — shows every version (epub/txt/…) */
        if(!bkok(nm)){sresp(c,400,"text/plain","bad book",8);return;}
        char dir[P];snprintf(dir,P,"%s/books/%s",AROOT,nm);
        if(access(dir,X_OK)){sresp(c,404,"text/plain","no such book",12);return;}
        if(!fork()){setsid();
            char rd[64];snprintf(rd,64,"/run/user/%d",(int)getuid());setenv("XDG_RUNTIME_DIR",rd,1);
            DIR*wd=opendir(rd);struct dirent*we;char wl[64]="";
            if(wd){while((we=readdir(wd)))if(!strncmp(we->d_name,"wayland-",8)&&!strstr(we->d_name,".lock")){snprintf(wl,64,"%s",we->d_name);break;}closedir(wd);}
            if(wl[0])setenv("WAYLAND_DISPLAY",wl,1);
            int z=open("/dev/null",O_RDWR);if(z>=0){dup2(z,0);dup2(z,1);dup2(z,2);}
            execlp("nautilus","nautilus",dir,(char*)0);_exit(1);}
        sresp(c,204,"text/plain","",0);return;}  /* 204 → browser stays put; the file-manager window pops up */
    if(!strncmp(req,"GET /docs",9)){
        /* auto-list: every file under these dirs links to /doc?f= — drop a file in, it appears, no menu upkeep */
        char*h=malloc(1<<18);if(!h){sresp(c,500,"text/plain","oom",3);return;}
        int hl=snprintf(h,1<<18,"<!doctype html><meta name=viewport content=\"width=device-width,initial-scale=1\"><title>docs</title><style>body{background:#0b0b0b;color:#ddd;margin:24px 9vw;overflow-wrap:anywhere;font:22px/1.6 ui-monospace,monospace}h3{color:#fff;padding:12px 16px 4px;margin:0}a{display:block;color:#fff;text-decoration:none;padding:4px 16px}a:hover{background:#161616}</style><a href=# onclick=\"var n=prompt('new adoc filename');if(n)location='/doc?f=adocs/'+n;return false\">+ new adoc</a> <a href=# onclick=\"var n=prompt('new folder name');if(n)fetch('/api/omni',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'q=docs mkdir '+encodeURIComponent(n)}).then(function(){location.reload()});return false\">+ new folder</a>" TAPJS);
        char*ar=strstr(req,"arch=1"),*eol=strstr(req,"\r\n");int arch=ar&&eol&&ar<eol;
        const char*dn[]={"mem","adocs"},*da[]={"mem/archive","adocs/archive"};const char**dirs=arch?da:dn;
        hl+=snprintf(h+hl,(size_t)((1<<18)-hl),arch?"<a href=\"/docs\" style=color:#fff>&#9666; back to docs</a>":"<a href=\"/docs?arch=1\" style=color:#555>&#9656; archived</a>");
        for(int k=0;k<2;k++){hl+=snprintf(h+hl,(size_t)((1<<18)-hl),"<h3>%s/</h3>",dirs[k]);
            hl=docls(h,hl,dirs[k],(int)strlen(dirs[k])+1);}
        sdoc(c,h,hl);free(h);return;}
    if(!strncmp(req,"GET /doc-arch",13)){ /* move doc into sibling archive/ folder; /docs hides those */
        char rel[P];if(!docrel(req,rel)){sresp(c,400,"text/plain","bad path",8);return;}
        char fp[P];snprintf(fp,P,"%s/%s",SROOT,rel);
        char*b=strrchr(rel,'/');if(!b){sresp(c,400,"text/plain","no dir",6);return;}
        *b=0;char ad[P];snprintf(ad,P,"%s/%s/archive",SROOT,rel);mkdirp(ad);
        char np[P];snprintf(np,P,"%s/%s",ad,b+1);
        if(rename(fp,np)){sresp(c,500,"text/plain","rename failed",13);return;}
        sresp(c,200,"text/plain","ok",2);return;}
    if(!strncmp(req,"POST /api/omni",14)||!strncmp(req,"POST /note",10)){
        char*body=strstr(req,"\r\n\r\n");if(!body){sresp(c,400,"text/plain","bad",3);return;}
        body+=4;
        /* POST /note: extract c= param, run a note */
        int isnote=!strncmp(req,"POST /note",10);
        char*q=strstr(body,isnote?"c=":"q=");if(!q){sresp(c,400,"text/plain","no param",8);return;}
        q+=2;char*cmd=q,*w=q;   /* in-place: decoded ≤ encoded */
        for(;*q&&*q!='&';q++){
            if(*q=='+')*w++=' ';
            else if(*q=='%'&&q[1]&&q[2]){char h[3]={q[1],q[2],0};*w++=(char)strtol(h,NULL,16);q+=2;}
            else *w++=*q;}*w=0;
        if(isnote){char nd[P];snprintf(nd,P,"%s/notes",SROOT);mkdirp(nd);char*nf=note_save(nd,cmd);
            char m[256]="";note_url(nf,"note",m); /* gh PUT → real url (works even when local trails); no fork, no 30s freeze */
            sresp(c,200,"text/plain",m,(int)strlen(m));return;}
        int pp[2];pipe(pp);pid_t ch=fork();
        if(!ch){close(pp[0]);dup2(pp[1],1);dup2(pp[1],2);close(pp[1]);
            signal(SIGALRM,SIG_DFL);signal(SIGPIPE,SIG_DFL);signal(SIGCHLD,SIG_DFL); /* SIG_DFL so child's git can waitpid (serve sets SIG_IGN) */
            char*args[32]={"a"};int ac=1;char*p2=cmd;
            while(*p2&&ac<31){while(*p2==' ')p2++;if(!*p2)break;args[ac++]=p2;while(*p2&&*p2!=' ')p2++;if(*p2)*p2++=0;}
            args[ac]=NULL;execvp("a",args);
            _exit(1);}
        close(pp[1]);char out[8192];int ol=0;
        {int r;while((r=(int)read(pp[0],out+ol,(size_t)(8191-ol)))>0)ol+=r;}
        close(pp[0]);waitpid(ch,NULL,0);out[ol]=0;
        {char resp[16384];int rl=ol?snprintf(resp,16384,"<pre style=\"color:#fff\">%.*s</pre>",ol,out):0;
            sresp(c,200,"text/html",resp,rl);}
        return;}
    if(!strncmp(req,"POST /api/savep",15)){char buf[1024];buf[0]=0;
        char*body=strstr(req,"\r\n\r\n");if(body){char*q=strstr(body+4,"q=");if(q){q+=2;int i=0;
            for(;q[i]&&q[i]!='&'&&i<1023;i++){if(q[i]=='+')buf[i]=' ';
                else if(q[i]=='%'&&q[i+1]&&q[i+2]){char x[3]={q[i+1],q[i+2],0};buf[i]=(char)strtol(x,NULL,16);q+=2;}
                else buf[i]=q[i];}buf[i]=0;}}
        char pf[P];snprintf(pf,P,"%s/prompts.log",SROOT);FILE*f=fopen(pf,"a");
        if(f){time_t t=time(NULL);char ts[32];strftime(ts,32,"%Y-%m-%d %H:%M",localtime(&t));fprintf(f,"%s\t%s\n",ts,buf);fclose(f);}
        sresp(c,200,"text/plain",pf,(int)strlen(pf));return;}
    if(!strncmp(req,"POST /api/sync",14)){sync_bg();sresp(c,200,"text/plain","ok",2);return;}
    if(!strncmp(req,"GET /fwins",10)){   /* fleet-wide tmux window list: serve cache instantly, refresh via lib/fwins.sh in bg (mirrors /fleet) */
        char fp[P];snprintf(fp,P,"%s/fleetwins.txt",DDIR);size_t fn=0;char*fb=readf(fp,&fn);struct stat ws;
        /* RATE LIMIT: a scan is an ssh fanout to the whole fleet + a tmux client per box. The page polls every 4s;
           refiring the scan on every poll ran 175 scans in 11min and kept N boxes + this tmux server under constant
           load. Cache age gates it — polls stay a 0.2ms file read and cost the fleet nothing. */
        if(stat(fp,&ws)||time(0)-ws.st_mtime>=20){
            if(!fork()){close(c);char sh[P];snprintf(sh,P,"%s/lib/fwins.sh",SDIR);execl("/bin/sh","sh",sh,DEV,DDIR,(char*)0);_exit(0);}}
        sresp(c,200,"text/plain",fb&&fn?fb:"",fb&&fn?(int)fn:0);if(fb)free(fb);return;}
    if(!strncmp(req,"GET /review/armed",17)){const char*rt=getenv("XDG_RUNTIME_DIR");char af[P];snprintf(af,P,"%s/a_pick",rt&&*rt?rt:"/tmp");char*q=readf(af,NULL);char out[P]="";
        for(char*l=q,*nl;l&&*l;l=nl?nl+1:l+strlen(l)){nl=strchr(l,'\n');if(nl)*nl=0;if(*l&&access(l,R_OK)==0){snprintf(out,P,"%s",strrchr(l,'/')?strrchr(l,'/')+1:l);break;}}
        free(q);sresp(c,200,"text/plain; charset=utf-8",out,(int)strlen(out));return;}   /* a review: what the e picker queue will attach next (i pick arm), for the banner */
    if(!strncmp(req,"GET /review/arm?n=",18)){int N=atoi(req+18);const char*kq=strstr(req,"&k=");int K=kq?atoi(kq+3):0;char fp[P]="",msg[P]="not found";
        if(rvpath(N,K,fp,P)&&access(fp,R_OK)==0){const char*rt=getenv("XDG_RUNTIME_DIR");char af[P];snprintf(af,P,"%s/a_pick",rt&&*rt?rt:"/tmp");FILE*f=fopen(af,"w");if(f){fprintf(f,"%s\n",fp);fclose(f);snprintf(msg,P,"armed %s",strrchr(fp,'/')?strrchr(fp,'/')+1:fp);}}
        sresp(c,200,"text/plain; charset=utf-8",msg,(int)strlen(msg));return;}   /* a review: arm the e file picker queue with this document: the next Attach/Upload click in any browser attaches it, no navigating (Sean 2026-09-03: auto arm like resume does) */
    if(!strncmp(req,"GET /review/push?n=",19)){char*f[5],fl[P],out[B*2]="";char*rl=rvline(atoi(req+19),f);   /* a review: the HUMAN's direct paths-only push of done.log line N (Sean 09-04): git add+commit -- <diff files> && push in that dir, message = the a done sentence; same shape as `a push -f`, same tok gate */
        if(!rl||!rvfl(f,fl))snprintf(out,B*2,"x no <diff> files on that a done");
        else{char v[B*2];if(tok_rule(f[3],v,(int)sizeof v,fl))snprintf(out,B*2,"x TOK INCREASE RULE\n%s",v);
            else{char*m=strrchr(f[4],']');m=m?m+1:f[4];while(*m==' ')m++;char mf[P];snprintf(mf,P,"%s/review_msg_%d.txt",DDIR,(int)getpid());FILE*mfp=fopen(mf,"w");if(mfp){fputs(*m?m:"a done",mfp);fclose(mfp);}   /* commit message = the done sentence, via -F: it is agent text, never a shell word */
                char cmd[B*2];snprintf(cmd,B*2,"cd '%s'&&git add -- %s&&{ git diff --quiet HEAD -- %s||git commit -F '%s' -- %s; }&&" PUSHCMD "&&{ git fetch -q origin 2>/dev/null;git branch -r --contains HEAD 2>/dev/null|grep -q origin&&echo PUSHED_OK $(git rev-parse --short HEAD); }",f[3],fl,fl,mf,fl);
                FILE*pp=popen(cmd,"r");size_t n=pp?fread(out,1,sizeof out-1,pp):0;if(pp)pclose(pp);out[n]=0;unlink(mf);}}
        free(rl);sresp(c,200,"text/plain; charset=utf-8",out,(int)strlen(out));return;}
    if(!strncmp(req,"GET /review/tell?w=",19)){int w=atoi(req+19);char cmd[B],out[128];snprintf(cmd,B,"tmux send -t a:%d -X cancel 2>/dev/null;tmux send -t a:%d -l '%s'&&sleep 0.4&&tmux send -t a:%d Enter",w,w,PP,w);   /* a review: the panel's [p], typed into that agent's window (copy-mode cancelled first, as the panel does) */
        strncat(cmd,"&&echo SENT",B-strlen(cmd)-1);FILE*pp=popen(cmd,"r");char r[16]="";if(pp){if(!fgets(r,16,pp))r[0]=0;pclose(pp);}   /* popen + marker, not system(): serve ignores SIGCHLD so system() returns -1 even on success (a.c snap trap) */
        snprintf(out,128,strstr(r,"SENT")?"told window %d: push just these changes":"x tmux window %d not reachable",w);sresp(c,200,"text/plain; charset=utf-8",out,(int)strlen(out));return;}
    if(!strncmp(req,"GET /review/go?w=",17)||!strncmp(req,"GET /problems/go?w=",19)){int w=atoi(strchr(req,'=')+1);char ln[256]="",out[512];FILE*pp=popen("tmux list-clients -F '#{client_activity}\t#{client_name}\t#{client_session}' 2>/dev/null|sort -n|tail -1","r");if(pp){if(!fgets(ln,256,pp))ln[0]=0;pclose(pp);}ln[strcspn(ln,"\n")]=0;   /* a review: the LOCAL terminal app (Sean 09-04): switch the most recently used attached tmux client to window INDEX w (the tasks board's go, i web.py /problems/go) and raise foot in sway */
        char*cn=strchr(ln,'\t'),*cs=cn?strchr(cn+1,'\t'):0;if(!cs)snprintf(out,512,"no attached local terminal: tmux switch-client -t :%d",w);
        else{*cn=0;*cs=0;char cmd[600],er[200]="";snprintf(cmd,600,"tmux switch-client -c '%s' -t '%s:%d' 2>&1 && SWAYSOCK=$(ls -t /run/user/$(id -u)/sway-ipc.* 2>/dev/null|head -1) swaymsg '[app_id=foot] focus' >/dev/null 2>&1",cn+1,cs+1,w);FILE*p2=popen(cmd,"r");if(p2){if(!fgets(er,200,p2))er[0]=0;pclose(p2);}er[strcspn(er,"\n")]=0;
            if(er[0])snprintf(out,512,"x %s",er);else snprintf(out,512,"window %d in %s on %s",w,cs+1,cn+1);}
        sresp(c,200,"text/plain; charset=utf-8",out,(int)strlen(out));return;}
    if(!strncmp(req,"GET /review/diff?n=",19)){char*f[5],fl[P];char*rl=rvline(atoi(req+19),f);int ok=rl&&rvfl(f,fl);   /* a review: the <diff>files</diff> of done.log line N as the a done panel shows it: cd <dir> && a diff -- files; its 24-bit ANSI backgrounds become spans, all else is escaped text (Sean 09-04) */
        char cmd[B];FILE*pp=0;if(ok){snprintf(cmd,B,"cd '%s' && a diff -- %s 2>&1",f[3],fl);pp=popen(cmd,"r");}
        size_t rc=1<<18,rz=0;char*raw=malloc(rc);if(pp){rz=fread(raw,1,rc-1,pp);pclose(pp);}raw[rz]=0;
        char*nt=strstr(raw,"net:");while(nt&&nt>raw&&nt[-1]!='\n'&&nt[-1]!='m')nt=strstr(nt+4,"net:");size_t nl=nt?strcspn(nt,"\n"):0;   /* the net tok line goes at the TOP too, and stays at the bottom (Sean 09-04: both places needed to review a diff) */
        size_t oc=(rz+nl)*8+1024,ol;char*o=malloc(oc);ol=(size_t)snprintf(o,oc,"<!doctype html><meta charset=utf-8><style>body{margin:0;padding:16px 16px 80px;background:#000;color:#fff;font:15px/1.4 ui-monospace,monospace;white-space:pre-wrap;word-break:break-word}</style>");
        for(int pass=0;pass<2;pass++){const char*s=pass?raw:nt;size_t sn=pass?rz:nl;if(!s||!sn)continue;
            for(size_t q=0;q<sn&&ol<oc-80;q++){int ch=(unsigned char)s[q];if(ch==27){char sq[32];int nq=0;for(q++;q<sn&&s[q]!='m'&&nq<31;q++)sq[nq++]=s[q];sq[nq]=0;int cr,cg,cb;
                    if(sscanf(sq,"[48;2;%d;%d;%d",&cr,&cg,&cb)==3)ol+=(size_t)snprintf(o+ol,oc-ol,"<span style=\"background:rgb(%d,%d,%d)\">",cr,cg,cb);else if(!strcmp(sq,"[0"))ol+=(size_t)snprintf(o+ol,oc-ol,"</span>");}
                else if(ch=='<')ol+=(size_t)snprintf(o+ol,oc-ol,"&lt;");else if(ch=='>')ol+=(size_t)snprintf(o+ol,oc-ol,"&gt;");else if(ch=='&')ol+=(size_t)snprintf(o+ol,oc-ol,"&amp;");else o[ol++]=(char)ch;}
            if(!pass)ol+=(size_t)snprintf(o+ol,oc-ol,"\n\n");}
        if(!ok)ol+=(size_t)snprintf(o+ol,oc-ol,"no &lt;diff&gt; files on that a done");free(raw);free(rl);sresp(c,200,"text/html; charset=utf-8",o,(int)ol);free(o);return;}
    if(!strncmp(req,"GET /review/doc?n=",18)){int N=atoi(req+18);const char*kq=strstr(req,"&k=");int K=kq?atoi(kq+3):0;char fp[P]="";rvpath(N,K,fp,P);size_t bl=0;char*b=fp[0]?readf(fp,&bl):0;if(!b){sresp(c,404,"text/plain","no such document",16);return;}   /* only paths an a done recorded: the server is on the LAN */
        const char*ct=mime(fp,"text/plain; charset=utf-8");
        if(!strncmp(ct,"text/plain",10)&&!strstr(req,"&raw=1")){size_t oc=bl*6+512;char*o=malloc(oc);int ol=snprintf(o,oc,"<!doctype html><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><style>body{margin:0;padding:16px 16px 80px;background:#000;color:#fff;font:18px/1.5 ui-monospace,monospace;white-space:pre-wrap;word-break:break-word}</style>");
            for(size_t q=0;q<bl&&ol<(int)oc-8;q++){char ch=b[q];if(ch=='<')ol+=snprintf(o+ol,oc-(size_t)ol,"&lt;");else if(ch=='>')ol+=snprintf(o+ol,oc-(size_t)ol,"&gt;");else if(ch=='&')ol+=snprintf(o+ol,oc-(size_t)ol,"&amp;");else o[ol++]=ch;}
            free(b);b=o;bl=(size_t)ol;ct="text/html; charset=utf-8";}   /* a text file in the black frame has a transparent body: black on black (Sean 09-03, "literally cant see text"). Wrap it dark, white, wrapping */
        sfile(c,ct,b,bl,"no-cache");free(b);return;}
    if(!strncmp(req,"GET /review/wsz?w=",18)){int w=atoi(req+18);char tc[160],sz[32]="";snprintf(tc,160,"tmux display-message -p -t a:%d '#{window_width} #{window_height}' 2>/dev/null",w);FILE*pp=popen(tc,"r");if(pp){if(fgets(sz,32,pp))sz[strcspn(sz,"\n")]=0;pclose(pp);}sresp(c,200,"text/plain",sz,(int)strlen(sz));return;}   /* host tmux window size, for the pull-up's fit-width scaling (a review) */
    if(!strncmp(req,"GET /review",11)){   /* a review: GUI review queue (Sean 2026-09-02), DDIR/done.log, one line per `a done` (ts\tidx\tname\tdir\tmsg, written by cmd_done), newest first; per AGENT (Sean 09-03); shell = lib/review.html */
        char tf[P];snprintf(tf,P,"%s/lib/review.html",SDIR);size_t tl=0;char*th=readf(tf,&tl);if(!th){sresp(c,404,"text/plain","no review.html",14);return;}
        char lf[P];snprintf(lf,P,"%s/done.log",DDIR);char*rl=readf(lf,NULL);size_t n=0,nc=0;rv_t*rs=NULL;
        size_t li=0;for(char*l=rl,*nl;l&&*l;l=nl?nl+1:l+strlen(l),li++){nl=strchr(l,'\n');if(nl)*nl=0;char*f[5]={l,0,0,0,0};int k=1;for(char*q=l;*q&&k<5;q++)if(*q=='\t'){*q=0;f[k++]=q+1;}if(k<5)continue;
            if(n>=nc){nc=nc?nc*2:64;rs=realloc(rs,nc*sizeof*rs);}rs[n].t=atol(f[0]);rs[n].w=f[1][0]&&strspn(f[1],"0123456789")==strlen(f[1])?f[1]:0;rs[n].n=f[2];rs[n].p=f[3];rs[n].i=li;rs[n++].m=f[4];}
        qsort(rs,n,sizeof*rs,rvcmp);int cap=1<<18;char*h=malloc((size_t)cap);int hl=snprintf(h,(size_t)cap,"%.*s",(int)tl,th);free(th);time_t now=time(NULL);
        for(size_t i=0;i<n&&hl<cap-4096;i++){long a=(long)(now-rs[i].t);char*m=strrchr(rs[i].m,']');m=m?m+1:rs[i].m;while(*m==' ')m++;for(char*q=m;*q;q++)if(*q=='<'||*q=='>')*q=' ';
            const char*rp=strncmp(rs[i].p,HOME,strlen(HOME))?rs[i].p:rs[i].p+strlen(HOME)+1;char ag[32];if(a<3600)snprintf(ag,32,"%ldm",a/60);else if(a<86400)snprintf(ag,32,"%ldh%02ldm",a/3600,a%3600/60);else snprintf(ag,32,"%ldd%ldh%02ldm",a/86400,a%86400/3600,a%3600/60);   /* age to the minute (Sean 09-03) */
            char nm[64]="";{int k=0;for(const char*q=rs[i].n;*q&&k<63;q++)if(isalnum((unsigned char)*q)||strchr("-_.",*q))nm[k++]=*q;nm[k]=0;}
            char bt[1280]="";if(rs[i].w)snprintf(bt,1280,"<div style=\"margin-top:8px\"><button class=op onpointerdown=\"op(this)\" data-w=\"%s\" data-n=\"%s\">web terminal: %s</button> <button class=op onpointerdown=\"go(this)\" data-w=\"%s\">local terminal: %s</button> <button class=op onpointerdown=\"tl(this)\" data-w=\"%s\">tell agent: push</button></div>",rs[i].w,nm,nm[0]?nm:"window",rs[i].w,nm[0]?nm:"window",rs[i].w);   /* three per entry: web terminal, local terminal, and the agent-push prompt; the human's own direct push is the button under the diff files below */   /* two terminals per entry (Sean 09-04): the pull-up web terminal, or the local terminal app switched to that tmux window; plain words (Sean 09-03: a play icon reads as music) */
            hl+=snprintf(h+hl,(size_t)(cap-hl),"<div style=\"padding:8px 0;border-bottom:1px solid #222\"><span style=color:#888>%s</span> <b>%s</b> <span style=color:#888>%s</span> %.300s%s",ag,nm[0]?nm:"(no window)",rp,m,bt);
            {char*da=strstr(rs[i].m,"<diff>"),*db=da?strstr(da,"</diff>"):0;if(da&&db){char sn[160];int z=0;for(const char*q=da+6;q<db&&z<159;q++)if(!strchr("<>\"&",*q))sn[z++]=*q;sn[z]=0;   /* <diff> files: the panel's focused diff, rendered in the same pull-up */
                hl+=snprintf(h+hl,(size_t)(cap-hl),"<div style=\"margin-top:8px\"><button class=op onpointerdown=\"dv(this)\" data-u=\"/review/diff?n=%zu\" data-n=\"diff %s\">show diff: %s</button> <button class=op onpointerdown=\"pu(this)\" data-n=\"%zu\" data-l=\"direct push, these files only: %s\">direct push, these files only: %s</button></div>",rs[i].i,sn,sn,rs[i].i,sn,sn);}}
            for(int k=0;k<8;k++){char dp[P];if(!rvdoc(rs[i].m,rs[i].p,k,dp,P))break;const char*bn=strrchr(dp,'/');bn=bn?bn+1:dp;char sn[96];int z=0;for(const char*q=bn;*q&&z<95;q++)if(!strchr("<>\"&",*q))sn[z++]=*q;sn[z]=0;   /* <doc> files: view in the same pull-up */
                hl+=snprintf(h+hl,(size_t)(cap-hl),"<div style=\"margin-top:8px\"><button class=op onpointerdown=\"dv(this)\" data-u=\"/review/doc?n=%zu&amp;k=%d\" data-n=\"%s\">view document: %s</button></div>",rs[i].i,k,sn,sn);}
            hl+=snprintf(h+hl,(size_t)(cap-hl),"</div>");}
        free(rs);free(rl);sdoc(c,h,hl);free(h);return;}
    if(!strncmp(req,"GET /music",10)){char mc[P],rel[P]="";snprintf(mc,P,"%s/music",DDIR);setenv("MC",mc,1);   /* a music web (page: adata/git/common/music.html, cli: adata/git/my/music.c — restored from the 5ad00bca cut, Sean 2026-09-10): /music page · /musics?f=q rows (empty q = cache) · /musicf?f=name stream · /musicg?f=id = a music get → stream */
        if(req[10]=='s'){docrel(req,rel);setenv("Q",rel,1);char b[8192];   /* cache matches, then 5 YouTube hits via ONE InnerTube call (0.45s; yt-dlp ytsearch was 9s) */
            FILE*p=popen(rel[0]?"ls \"$MC\"|grep -v '\\.part$'|grep -iF -- \"$Q\";jq -cn --arg q \"$Q\" '{context:{client:{clientName:\"WEB\",clientVersion:\"2.20250101.00.00\"}},query:$q,params:\"EgIQAQ%3D%3D\"}'|curl -s -m6 -d @- -H content-type:application/json 'https://www.youtube.com/youtubei/v1/search?prettyPrint=false'|jq -r '[..|.videoRenderer?|select(.)|\"\\(.videoId)\\t\\(.title.runs[0].text) \\(.lengthText.simpleText//\"\")\"]|.[:5][]'":"ls \"$MC\"|grep -v '\\.part$'","r");
            size_t n=p?fread(b,1,8191,p):0;if(p)pclose(p);sresp(c,200,"text/plain; charset=utf-8",b,(int)n);b[n]=0;
            char*ar[16];int an=0;ar[an++]="a";ar[an++]="music";ar[an++]="pre";   /* prefetch every hit at once (first first) so a tap plays instantly; ids come off the network → argv, never a shell, and only [A-Za-z0-9_-] */
            for(char*ln=b;*ln&&an<15;){char*e=strchr(ln,'\n'),*t=strchr(ln,'\t');
                if(t&&(!e||t<e)&&t-ln<16){int ok=1;for(char*z=ln;z<t;z++)if(!isalnum((unsigned char)*z)&&*z!='-'&&*z!='_')ok=0;
                    if(ok){*t=0;ar[an++]=ln;}}
                if(!e)break;ln=e+1;}
            ar[an]=0;if(an>3&&!fork()){close(c);execvp("a",ar);_exit(0);}
            return;}
        if(req[10]&&strchr("ctr",req[10])){docrel(req,rel);setenv("K",rel,1);char b[256],cm[32];   /* one shape, three subs — c=cfg "<cap-GB> <clip> <MB-now>" (?f=cap-8/trim-0 sets) · t=trim "<skip-in> <stop-at>" · r=rm one track's local bytes (.index keeps the how-to-get) */
            snprintf(cm,32,"a music %s \"$K\"",req[10]=='c'?"cfg":req[10]=='t'?"trim":"rm");
            FILE*p=popen(cm,"r");size_t n=p?fread(b,1,255,p):0;if(p)pclose(p);
            sresp(c,200,"text/plain",b,(int)n);return;}
        if(req[10]=='g'){char id[32];qp(req,"?f=",id,32);setenv("I",id,1);
            #define MIDX "sed -n \"s|^$I  ||p\" \"$MC/.index\" 2>&-|sed q"
            FILE*ip=popen(MIDX,"r");   /* the 10s head prefetch recorded the name */
            if(ip){if(fgets(rel,P,ip))rel[strcspn(rel,"\n")]=0;pclose(ip);}
            char fl[P+300],pt[P+308];snprintf(fl,sizeof fl,"%s/%s",mc,rel);snprintf(pt,sizeof pt,"%s.part",fl);
            if(!rel[0]||access(fl,F_OK)){   /* not complete on disk: stream as it downloads — was a blocking whole-file get when no .part (1hr track = minutes of dead air, Sean 2026-09-01) */
                pid_t sf=fork();if(sf)return;
                if(!rel[0]){if(!fork()){execlp("a","a","music","pre",id,(char*)0);_exit(0);}   /* head: resolves name -> .index row (written AFTER its 160KB curl, so get can't race the .part) */
                    for(int w=0;w<600&&!rel[0];w++){usleep(100000);FILE*p2=popen(MIDX,"r");if(p2){if(fgets(rel,P,p2))rel[strcspn(rel,"\n")]=0;pclose(p2);}}
                    if(!rel[0])_exit(0);
                    snprintf(fl,sizeof fl,"%s/%s",mc,rel);snprintf(pt,sizeof pt,"%s.part",fl);}
                if(!fork()){execlp("a","a","music","get",id,(char*)0);_exit(0);}
                char h[200];int hl=snprintf(h,200,"HTTP/1.1 200 OK\r\nContent-Type:%s\r\nConnection:close\r\nCache-Control:no-store\r\n\r\n",strstr(rel,".m4a")?"audio/mp4":strstr(rel,".opus")?"audio/ogg":"audio/webm");
                if(write(c,h,(size_t)hl)!=hl)_exit(0);
                off_t off=0;struct stat st;
                for(int idle=0;idle<600;idle++){int fd=open(access(fl,F_OK)?pt:fl,O_RDONLY);
                    if(fd>=0){char bu[65536];ssize_t r;
                        if(!fstat(fd,&st)&&st.st_size>off&&lseek(fd,off,SEEK_SET)>=0)
                            while((r=read(fd,bu,65536))>0){if(write(c,bu,(size_t)r)!=r)_exit(0);off+=r;idle=0;}
                        close(fd);}
                    if(!stat(fl,&st)&&off>=st.st_size)_exit(0);   /* renamed by yt-dlp + fully sent = done */
                    usleep(100000);}
                _exit(0);}
            #undef MIDX
            }
        else if(req[10]=='f')docrel(req,rel);
        else{char tf[P];snprintf(tf,P,"%s/common/music.html",SROOT);size_t tl=0;char*th=readf(tf,&tl);if(th){sdoc(c,th,(int)tl);free(th);}else sresp(c,404,"text/plain","x",1);return;}
        char fp[P];snprintf(fp,P,"%s/%s",mc,rel);size_t n=0;char*d=readf(fp,&n);
        if(d){const char*mt=strstr(rel,".m4a")?"audio/mp4":strstr(rel,".opus")?"audio/ogg":"audio/webm";   /* Range support: without Accept-Ranges/206 Chrome marks audio unseekable (seekable=0-0) — trim skip and the seek bar both clamp to 0 */
            char*rg=strstr(req,"Range: bytes=");size_t s0=0,e0=n?n-1:0;
            if(rg){s0=(size_t)atoll(rg+13);char*dh=strchr(rg+13,'-');if(dh&&isdigit((unsigned char)dh[1])){e0=(size_t)atoll(dh+1);if(e0>=n)e0=n?n-1:0;}}
            char h[256];int hl;
            if(rg&&s0<n){hl=snprintf(h,256,"HTTP/1.1 206 OK\r\nContent-Type:%s\r\nAccept-Ranges:bytes\r\nContent-Range:bytes %zu-%zu/%zu\r\nContent-Length:%zu\r\nConnection:close\r\n\r\n",mt,s0,e0,n,e0-s0+1);
                if(write(c,h,(size_t)hl)==hl)(void)!write(c,d+s0,e0-s0+1);}
            else{hl=snprintf(h,256,"HTTP/1.1 200 OK\r\nContent-Type:%s\r\nAccept-Ranges:bytes\r\nContent-Length:%zu\r\nConnection:close\r\n\r\n",mt,n);
                if(write(c,h,(size_t)hl)==hl)(void)!write(c,d,n);}
            free(d);}else sresp(c,404,"text/plain","x",1);return;}
    if(!strncmp(req,"GET /fw",7)&&(req[7]==' '||req[7]=='?'||req[7]=='\r')){   /* unified fleet tmux view: all devices' windows in one list, one inline terminal that re-points */
        char tf[P];snprintf(tf,P,"%s/lib/fleetview.html",SDIR);size_t tl=0;char*th=readf(tf,&tl);
        if(th){siso(c,th,(int)tl);free(th);}else sresp(c,404,"text/plain","no fleetview.html",16);return;}
    if(!strncmp(req,"GET /api/sync-status",20)){int fd=open("/tmp/.a_git.lock",O_RDONLY);
        int busy=fd>=0&&flock(fd,LOCK_EX|LOCK_NB)<0;if(fd>=0){if(!busy)flock(fd,LOCK_UN);close(fd);}
        const char*r=busy?"syncing":sync_age();sresp(c,200,"text/plain",r,(int)strlen(r));return;}
    if(!strncmp(req,"GET /note-list",14)){
        int cap=524288;char*html=malloc((size_t)cap);if(!html)return;
        int hl=notes_build(html,cap,"notes");sresp(c,200,"text/html",html,hl);free(html);return;}
    if(!strncmp(req,"GET /flow",9)&&(req[9]==' '||req[9]=='?'||req[9]=='\r')){   /* structured review surface: notes + tasks + prompts, full text, per-row archive/edit, add + suggest */
        int cap=1<<19;char*buf=malloc((size_t)cap);if(!buf){sresp(c,500,"text/plain","oom",3);return;}
        int bl=snprintf(buf,3200,"<!doctype html><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><title>flow</title><style>body{background:#111;color:#ddd;font:14px/1.5 ui-monospace,monospace;margin:0;padding:8px 12px 9em}h3{color:#fff;margin:16px 0 4px;font-size:15px}.ni{display:flex;align-items:flex-start;padding:6px 0;border-bottom:1px solid #1c1c1c;word-break:break-word}.nx{background:none;border:1px solid #555;color:#999;padding:5px 10px;margin-right:9px;border-radius:4px;cursor:pointer;flex:none}button{background:#111;color:#fff;border:1px solid #444;border-radius:6px;padding:6px 11px;margin:0 2px;cursor:pointer;font:13px monospace}a{color:#fff}</style><body><h3>NOTES <button onclick=\"fadd('note','note')\">+</button></h3>");
        bl+=notes_build(buf+bl,cap-bl,"notes");
        bl+=snprintf(buf+bl,(size_t)(cap-bl),"<h3>PROMPT CANDIDATES <button onclick=\"fadd('prompt c','prompt')\">+</button></h3>");
        bl+=notes_build(buf+bl,cap-bl,"prompts");
        bl+=snprintf(buf+bl,(size_t)(cap-bl),"<div style=\"position:fixed;left:0;right:0;bottom:0;background:#111;border-top:1px solid #333;padding:.6em;text-align:center\"><span id=fs style=color:#bbb></span></div><script>function omni(c){fs.textContent='\342\200\246';fetch('/api/omni',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'q='+encodeURIComponent(c)}).then(function(r){return r.text()}).then(function(){location.reload()})}function fadd(c,k){var v=prompt('new '+k);if(v)omni(c+' '+v)}function arc(u,key,f){var b={};b[key]=f;fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(function(){location.reload()})}function arcn(f){arc('/api/note/archive','f',f)}function arcp(f){arc('/api/prompt/archive','f',f)}</script>");
        sdoc(c,buf,bl);free(buf);return;}
    if(!strncmp(req,"POST /api/note/archive",22)||!strncmp(req,"POST /api/prompt/archive",24)){
        char kc=req[10];const char*kind=kc=='p'?"prompts":"notes";  /* n=notes p=prompts */
        char*body=strstr(req,"\r\n\r\n");if(!body){sresp(c,400,"text/plain","bad",3);return;}
        char*k=strstr(body+4,"\"f\":\"");if(!k){sresp(c,400,"text/plain","no name",7);return;}
        k+=5;char name[256];int ni=0;while(k[ni]&&k[ni]!='"'&&ni<255){name[ni]=k[ni];ni++;}name[ni]=0;
        for(char*p=name;*p;p++)if(*p=='/'){sresp(c,400,"text/plain","bad name",8);return;}
        char src[P],dst[P],ad[P];
        snprintf(ad,P,"%s/git/%s/.archive",AROOT,kind);mkdir(ad,0755);
        snprintf(src,P,"%s/git/%s/%s",AROOT,kind,name);
        snprintf(dst,P,"%s/%s",ad,name);rename(src,dst);
        sresp(c,200,"text/plain","ok",2);return;}
    if(!strncmp(req,"GET /op",7)&&(req[7]==' '||req[7]=='?'||req[7]=='\r')){
        const char*qw=strstr(req,"?w=");int idx=(qw&&isdigit((unsigned char)qw[3])&&!strstr(req,"&all"))?atoi(qw+3):-1;   /* &all = fleet view: skip agent-only gate, show any window */
        if(idx>=0){char tc[256];
            snprintf(tc,256,"p=$(tmux display-message -t a:%d -p '#{pane_pid}' 2>/dev/null);c=$(cat /proc/$p/task/$p/children 2>/dev/null|cut -d' ' -f1);[ -n \"$c\" ]&&cat /proc/$c/comm 2>/dev/null",idx);
            FILE*pp=popen(tc,"r");char nm[64]={0};
            if(pp){if(fgets(nm,64,pp))nm[strcspn(nm,"\n")]=0;pclose(pp);}
            if(strcmp(nm,"claude")&&strcmp(nm,"codex")&&strcmp(nm,"gemini")&&strcmp(nm,"aider")){
                static const char NO[]="<!doctype html><style>body{background:#000;color:#fff;font:16px system-ui;text-align:center;padding-top:40vh}a{color:#fff}</style>no agent<br><br><a href=/review>← review</a>";
                sresp(c,200,"text/html",NO,sizeof NO-1);return;}}
        char tf[P];snprintf(tf,P,"%s/lib/term.html",SDIR);size_t tl=0;char*th=readf(tf,&tl); /* direct-DOM terminal page (replaced xterm.js CDN 7/10) */
        if(th){siso(c,th,(int)tl);free(th);}
        else sresp(c,404,"text/plain","no term.html",12);
        return;}
    sresp(c,404,"text/plain","not found",9);
}
static int cmd_serve(int argc,char**argv){perf_disarm();signal(SIGPIPE,SIG_IGN);signal(SIGCHLD,SIG_IGN);
    {const char*op=getenv("PATH");if(!op)op="";char np[P];snprintf(np,P,"%s/.local/bin:/opt/homebrew/bin:/usr/local/bin:%s",HOME,op);setenv("PATH",np,1);}
    int port=argc>2?atoi(argv[2]):1111;
    if(argc>3){if(!realpath(argv[3],sdr)||!dexists(sdr)){printf("x no dir %s\n",argv[3]);return 1;}
        printf("+ site %s\n",sdr);}
    else{printf("> generating HTML...\n");html_gen();
        if(!shlen){puts("x HTML generation failed");return 1;}
        printf("+ %d bytes cached\n",shlen);}
    int fd=socket(AF_INET,SOCK_STREAM,0);fcntl(fd,F_SETFD,FD_CLOEXEC);
    setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&(int){1},4);
    struct sockaddr_in a={.sin_family=AF_INET,.sin_port=htons((uint16_t)port)};
    if(bind(fd,(void*)&a,sizeof a)<0){perror("bind");return 1;} /* lost the port race -> exit BEFORE any tmux touch, so N concurrent invokes can't stampede the dashboard bridge */
    listen(fd,64);printf("+ http://localhost:%d (C server, pid %d)\n",port,(int)getpid());
    for(;;){int c=accept(fd,0,0);if(c<0)continue;
        struct timeval tv={2,0};setsockopt(c,SOL_SOCKET,SO_RCVTIMEO,&tv,sizeof tv);
        if(!fork()){close(fd);
            struct timespec t0,t1;clock_gettime(CLOCK_MONOTONIC,&t0);
            handle(c);close(c);
            clock_gettime(CLOCK_MONOTONIC,&t1);
            double ms=(double)(t1.tv_sec-t0.tv_sec)*1e3+(double)(t1.tv_nsec-t0.tv_nsec)/1e6;
            fprintf(stderr,"%7.3fms  %s\n",ms,rql);
            char lg[P];snprintf(lg,P,"%s/local/serve.log",AROOT);FILE*lf=fopen(lg,"a");if(lf){fprintf(lf,"%.3f %s\n",ms,rql);fclose(lf);}
            _exit(0);}close(c);}
}
