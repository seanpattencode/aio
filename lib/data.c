/* data */
static const char *dprompt(void) {
    static char b[B*64]; const char*a=cfget("prompt");if(!*a)a="default";  /* SILENTLY truncates default.txt past sizeof(b) — bit THRICE (16KB cut greats mid-name; 64KB cut tail at 67KB, 2026-07; 128KB cut tail at 148KB, 2026-09-02): keep ~2x file-size headroom */
    char p[P]; snprintf(p,P,"%s/common/prompts/%s.txt",SROOT,a);
    char *d=readf(p,NULL); b[0]=0; if(d){snprintf(b,sizeof(b),"%s ",d);free(d);} return b;
}
static void esc_nl(const char *s, char *o, int sz) {
    int j = 0;
    for (int i = 0; s[i] && j < sz - 2; i++) {
        if (s[i] == '\n') { o[j++] = '\\'; o[j++] = 'n'; } else o[j++] = s[i];
    }
    o[j] = 0;
}
static void unesc_nl(char *s) {
    char *r = s, *w = s;
    while (*r) { if (r[0] == '\\' && r[1] == 'n') { *w++ = '\n'; r += 2; } else *w++ = *r++; }
    *w = 0;
}

static void cfset(const char *key, const char *val) {
    int found = 0;
    for (int i = 0; i < NCF; i++) if (!strcmp(CF[i].k, key)) { snprintf(CF[i].v, 1024, "%s", val); found = 1; break; }
    if (!found && NCF < 64) { snprintf(CF[NCF].k, 64, "%s", key); snprintf(CF[NCF].v, 1024, "%s", val); NCF++; }
    char p[P]; snprintf(p, P, "%s/workspace/config.txt", SROOT);
    FILE *f = fopen(p, "w"); if (!f) return;
    for (int i = 0; i < NCF; i++) { char ev[2048]; esc_nl(CF[i].v, ev, 2048); fprintf(f, "%s: %s\n", CF[i].k, ev); }
    fclose(f);
}

static void init_db(void) {
    char d[P]; snprintf(d,P,"%s/workspace",SROOT); mkdirp(d);
    char p[P]; snprintf(p, P, "%s/workspace/config.txt", SROOT);
    if (!fexists(p)) {
        FILE*wf=fopen(p,"w");
        if(wf){fprintf(wf,"default_agent: c\nworktrees_dir: %s/worktrees\nclaude_prefix: Ultrathink. \ntmux_conf: y\n",AROOT);fclose(wf);}
    }
    snprintf(p, P, "%s/workspace/sessions.txt", SROOT);
    if (!fexists(p)) {
        /* c/claude pin the EXACT id claude-fable-5 max: Fable 5.1 = regression in real use (confirmed 2026-09-09), and the bare 'fable' alias now resolves to 5.1 — never alias, always exact. l/o stay plain = follow the claude default. */
        const char *C = "claude --dangerously-skip-permissions";
        const char *CM = "claude --dangerously-skip-permissions --model claude-fable-5 --effort max";
        const char *X = "codex --dangerously-bypass-approvals-and-sandbox"; /* ~/.codex/config.toml owns model/effort — pins here go stale */
        char buf[B*4]; snprintf(buf, sizeof(buf),
            "g|gemini|gemini --yolo\ngemini|gemini|gemini --yolo\n"
            "c|claude|%s\nclaude|claude|%s\nl|claude|%s\no|claude|%s\n"
            "co|codex|%s\ncodex|codex|%s\n"
            "grok|grok|grok --always-approve\n"
            "a|aider|OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral\n"
            "cp|claude-p|%s \"{CLAUDE_PROMPT}\"\nlp|claude-p|%s \"{CLAUDE_PROMPT}\"\n"
            "gp|gemini-p|gemini --yolo \"{GEMINI_PROMPT}\"\n"
            "cop|codex-p|%s \"{CODEX_PROMPT}\"\n", CM, CM, C, C, X, X, C, C, X);
        writef(p, buf);
    }
}

/* loaders */
static void load_cfg(void) {
    NCF = 0; char p[P]; snprintf(p, P, "%s/workspace/config.txt", SROOT);
    kvs_t kv = kvfile(p);
    for (int i = 0; i < kv.n; i++) { snprintf(CF[NCF].k, 64, "%s", kv.i[i].k); snprintf(CF[NCF].v, 1024, "%s", kv.i[i].v); unesc_nl(CF[NCF].v); NCF++; }
}

static char *cfget(const char *key) {
    for (int i = 0; i < NCF; i++) if (!strcmp(CF[i].k, key)) return CF[i].v;
    return "";
}

static int pj_cmp(const void *a, const void *b) { int d=((const proj_t*)a)->order-((const proj_t*)b)->order; return d?d:strcmp(((const proj_t*)a)->name,((const proj_t*)b)->name); }

static void load_proj(void) {
    NPJ = 0;
    char dir[P]; snprintf(dir, P, "%s/workspace/projects", SROOT);
    mkdirp(dir);
    char paths[MP][P]; int n = listdir(dir, paths, MP);
    for (int i = 0; i < n && NPJ < MP; i++) {
        kvs_t kv = kvfile(paths[i]);
        const char *nm = kvget(&kv, "Name"); if (!nm) continue;
        const char *pa = kvget(&kv, "Path"), *re = kvget(&kv, "Repo"), *gd = kvget(&kv, "Gdrive");
        proj_t *p=&PJ[NPJ];
        snprintf(p->name, 128, "%s", nm); snprintf(p->file, P, "%s", paths[i]);
        {char*pp=p->path;snprintf(pp,512,"%s/%s",HOME,nm);
        if(!dexists(pp)&&pa){if(pa[0]=='~')snprintf(pp,512,"%s%s",HOME,pa+1);
            else{char rp[512];if(isalpha(pa[0])&&pa[1]==':')snprintf(rp,512,"/mnt/%c%s",(char)tolower(pa[0]),pa+2);else snprintf(rp,512,"%s",pa);
                for(char*s=rp;*s;s++)if(*s=='\\') *s='/';if(dexists(rp))snprintf(pp,512,"%s",rp);}}}
        snprintf(p->repo, 512, "%s", re ? re : "");
        snprintf(p->gdrive, 512, "%s", gd ? gd : "");
        {const char *o=kvget(&kv,"Order");p->order=o?atoi(o):strcmp(p->path,SDIR)?9999:-1;}
        NPJ++;
    }
    qsort(PJ, (size_t)NPJ, sizeof(proj_t), pj_cmp);
}

static int ap_cmp(const void *a, const void *b) { return strcmp(((const app_t*)a)->name, ((const app_t*)b)->name); }

static void load_apps(void) {
    NAP = 0;
    char dir[P]; snprintf(dir, P, "%s/workspace/cmds", SROOT);
    mkdirp(dir);
    char paths[MA][P]; int n = listdir(dir, paths, MA);
    for (int i = 0; i < n && NAP < MA; i++) {
        kvs_t kv = kvfile(paths[i]);
        const char *nm = kvget(&kv, "Name");
        const char *cm = kvget(&kv, "Command");
        if (!nm || !cm) continue;
        snprintf(AP[NAP].name, 128, "%s", nm);
        snprintf(AP[NAP].cmd, 512, "%s", cm);
        NAP++;
    }
    qsort(AP, (size_t)NAP, sizeof(app_t), ap_cmp);
}

static void load_sess(void) {
    NSE = 0; char p[P]; snprintf(p, P, "%s/workspace/sessions.txt", SROOT);
    char *data = readf(p, NULL); if (!data) return;
    char *line = data;
    while (*line && NSE < MS) {
        char *nl = strchr(line, '\n'); if (nl) *nl = 0;
        char *d1 = strchr(line, '|'), *d2 = d1 ? strchr(d1 + 1, '|') : NULL;
        if (d1 && d2) {
            *d1 = 0; *d2 = 0;
            snprintf(SE[NSE].key, 16, "%s", line);
            snprintf(SE[NSE].name, 64, "%s", d1 + 1);
            char expanded[1024]; snprintf(expanded, 1024, "%s", d2 + 1);
            const char *keys[] = {"claude_prompt","codex_prompt","gemini_prompt"};
            const char *tags[] = {"{CLAUDE_PROMPT}","{CODEX_PROMPT}","{GEMINI_PROMPT}"};
            for (int j = 0; j < 3; j++) {
                char *pos = strstr(expanded, tags[j]);
                if (pos) {
                    const char *val = cfget(keys[j]);
                    char tmp[1024]; int pre = (int)(pos - expanded);
                    snprintf(tmp, 1024, "%.*s%s%s", pre, expanded, val, pos + strlen(tags[j]));
                    snprintf(expanded, 1024, "%s", tmp);
                }
            }
            const char *k = SE[NSE].key;
            if (!strcmp(k,"cp") || !strcmp(k,"lp") || !strcmp(k,"gp")) {
                char *dq = strstr(expanded, " \"");
                if (dq) *dq = 0;
            }
            snprintf(SE[NSE].cmd, 1024, "%s", expanded);
            NSE++;
        }
        if (!nl) break; line = nl + 1;
    }
    free(data);
}

static sess_t *find_sess(const char *key) {
    for (int i = 0; i < NSE; i++) if (!strcmp(SE[i].key, key)) return &SE[i];
    return NULL;
}
