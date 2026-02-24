/* ═══ UTILITIES ═══ */
static int fexists(const char *p) { struct stat s; return stat(p, &s) == 0; }
static int dexists(const char *p) { struct stat s; return stat(p, &s) == 0 && S_ISDIR(s.st_mode); }
static void mkdirp(const char *p) { char t[P]; snprintf(t,P,"%s",p); for(char*s=t+1;*s;s++) if(*s=='/'){*s=0;mkdir(t,0755);*s='/';} mkdir(t,0755); }

static char *readf(const char *p, size_t *len) {
    int fd = open(p, O_RDONLY); if (fd < 0) return NULL;
    struct stat s; if (fstat(fd, &s) < 0) { close(fd); return NULL; }
    size_t sz = (size_t)s.st_size;
    char *b = malloc(sz + 1); if (!b) { close(fd); return NULL; }
    ssize_t n = read(fd, b, sz); close(fd);
    if (n < 0) { free(b); return NULL; }
    b[n] = 0; if (len) *len = (size_t)n; return b;
}

static int catf(const char *p) {
    int fd = open(p, O_RDONLY); if (fd < 0) return -1;
    char b[8192]; ssize_t n;
    while ((n = read(fd, b, sizeof(b))) > 0) (void)!write(STDOUT_FILENO, b, (size_t)n);
    close(fd); return 0;
}

static void writef(const char *p, const char *data) {
    FILE *f = fopen(p, "w"); if (f) { fputs(data, f); fclose(f); }
}

static int pcmd(const char *cmd, char *out, int sz) {
    if (out) out[0] = 0;
    FILE *f = popen(cmd, "r"); if (!f) return -1;
    if (out) { int n = 0; char b[B];
        while (fgets(b, B, f) && n + (int)strlen(b) < sz - 1) n += sprintf(out + n, "%s", b);
    } else { char b[B]; while (fgets(b, B, f)) ; }
    return pclose(f);
}


static const char *bname(const char *p) { const char *s = strrchr(p, '/'); return s ? s + 1 : p; }

static int inpath(const char *name) {
    char *p=getenv("PATH"); if(!p)return 0;
    char buf[P],pathc[B]; snprintf(pathc,B,"%s",p);
    for(char*d=strtok(pathc,":");d;d=strtok(NULL,":")){snprintf(buf,P,"%s/%s",d,name);if(!access(buf,X_OK))return 1;}
    return 0;
}
static const char *clip_cmd(void) {
    if (getenv("TERMUX_VERSION")) return "termux-clipboard-set";
    #ifdef __APPLE__
    return "pbcopy";
    #endif
    if (!access("/mnt/c/Windows/System32/clip.exe",X_OK)) return "clip.exe";
    if (inpath("wl-copy")) return "wl-copy";
    if (inpath("xclip")) return "xclip -selection clipboard -i";
    if (inpath("xsel")) return "xsel --clipboard --input";
    return NULL;
}
static void osc52(const char *data) {
    static const char b6[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    int fd=open("/dev/tty",O_WRONLY); if(fd<0)return;
    (void)!write(fd,"\033]52;c;",7); size_t len=strlen(data);
    for(size_t i=0;i<len;i+=3){unsigned v=(unsigned char)data[i]<<16;
        if(i+1<len)v|=(unsigned char)data[i+1]<<8; if(i+2<len)v|=(unsigned char)data[i+2];
        char o[4]={b6[v>>18&63],b6[v>>12&63],i+1<len?b6[v>>6&63]:'=',i+2<len?b6[v&63]:'='};
        (void)!write(fd,o,4);}
    (void)!write(fd,"\a",1); close(fd);
}
static int to_clip(const char *data) {
    const char *cc=clip_cmd();
    if(cc){FILE*fp=popen(cc,"w");if(fp){fputs(data,fp);return pclose(fp);}}
    osc52(data); return 0;
}
