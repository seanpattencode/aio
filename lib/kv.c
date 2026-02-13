/* ═══ RFC 5322 KEY:VALUE PARSER ═══ */
typedef struct { char k[32], v[512]; } kv_t;
typedef struct { kv_t i[16]; int n; } kvs_t;

static kvs_t kvparse(const char *data) {
    kvs_t r = {.n = 0}; const char *p = data;
    while (*p && r.n < 16) {
        const char *nl = strchr(p, '\n'); if (!nl) nl = p + strlen(p);
        const char *c = memchr(p, ':', (size_t)(nl - p));
        if (c && c > p) {
            size_t kl = (size_t)(c - p); if (kl > 31) kl = 31;
            memcpy(r.i[r.n].k, p, kl); r.i[r.n].k[kl] = 0;
            const char *v = c + 1; while (*v == ' ' && v < nl) v++;
            size_t vl = (size_t)(nl - v); if (vl > 511) vl = 511;
            memcpy(r.i[r.n].v, v, vl); r.i[r.n].v[vl] = 0;
            r.n++;
        }
        p = *nl ? nl + 1 : nl;
    }
    return r;
}

static const char *kvget(kvs_t *kv, const char *key) {
    for (int i = 0; i < kv->n; i++) if (!strcmp(kv->i[i].k, key)) return kv->i[i].v;
    return NULL;
}

static kvs_t kvfile(const char *path) {
    char *d = readf(path, NULL);
    if (!d) return (kvs_t){.n = 0};
    kvs_t r = kvparse(d); free(d); return r;
}

static int listdir(const char *dir, char paths[][P], int max) {
    DIR *d = opendir(dir); if (!d) return 0;
    struct dirent *e; int n = 0;
    while ((e = readdir(d)) && n < max) {
        if (e->d_name[0] == '.') continue;
        char *dot = strrchr(e->d_name, '.'); if (!dot || strcmp(dot, ".txt")) continue;
        snprintf(paths[n++], P, "%s/%s", dir, e->d_name);
    }
    closedir(d); return n;
}
