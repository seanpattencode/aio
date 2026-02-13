/* ═══ INIT PATHS ═══ */
static void init_paths(void) {
    const char *h = getenv("HOME"); if (!h) h = "/tmp";
    snprintf(HOME, P, "%s", h);
    char self[P]; ssize_t n = -1;
#ifdef __APPLE__
    uint32_t sz = P - 1;
    if (_NSGetExecutablePath(self, &sz) == 0) { n = (ssize_t)strlen(self); char rp[P]; if (realpath(self, rp)) { snprintf(self, P, "%s", rp); n = (ssize_t)strlen(self); } }
#else
    n = readlink("/proc/self/exe", self, P - 1);
#endif
    if (n > 0) {
        self[n] = 0;
        char *s = strrchr(self, '/');
        if (s) { *s = 0; snprintf(SDIR, P, "%s", self);
            /* Von Neumann: code and data in the same space. adata/ lives inside
             * the project dir (.gitignored) — one directory, one world. VS Code
             * users see everything, LLMs see everything, 'a push' and data sync
             * are independent git operations on the same tree. */
            snprintf(AROOT, P, "%s/adata", self);
            snprintf(SROOT, P, "%s/git", AROOT);
        }
    }
    if (!SROOT[0]) { snprintf(AROOT, P, "%s/projects/a/adata", h); snprintf(SROOT, P, "%s/git", AROOT); }
    /* All local state lives in adata/ — if it's not in adata, nobody knows
     * where it is. Maximum visibility for humans and LLMs. */
    snprintf(DDIR, P, "%s/local", AROOT);
    { char tmp[P]; snprintf(tmp,P,"%s",DDIR); for(char*p=tmp+1;*p;p++) if(*p=='/'){*p=0;mkdir(tmp,0755);*p='/';} mkdir(tmp,0755); }
    /* One-time migration: old sibling ~/projects/adata/ → inside project dir */
    char old_sib[P]; snprintf(old_sib, P, "%.*s/adata", (int)(strlen(SDIR) - strlen("/a")), SDIR);
    /* only migrate if old sibling exists and new doesn't have .device yet */
    char new_dev[P]; snprintf(new_dev, P, "%s/.device", DDIR);
    struct stat mst;
    if (strcmp(old_sib, AROOT) != 0 && stat(old_sib, &mst) == 0 && stat(new_dev, &mst) != 0) {
        char mc[B]; snprintf(mc, B, "cp -rn '%s/'* '%s/' 2>/dev/null", old_sib, AROOT);
        (void)!system(mc);
    }
    /* Also migrate from old ~/.local/share/a/ */
    char old_local[P]; snprintf(old_local, P, "%s/.local/share/a/.device", h);
    if (stat(old_local, &mst) == 0 && stat(new_dev, &mst) != 0) {
        char mc[B]; snprintf(mc, B, "cp -rn '%s/.local/share/a/'* '%s/' 2>/dev/null", h, DDIR);
        (void)!system(mc);
    }
    /* device id */
    char df[P]; snprintf(df, P, "%s/.device", DDIR);
    FILE *f = fopen(df, "r");
    if (f) { if (fgets(DEV, 128, f)) DEV[strcspn(DEV, "\n")] = 0; fclose(f); }
    if (!DEV[0]) {
        gethostname(DEV, 128);
        char c[P]; snprintf(c, P, "mkdir -p '%s'", DDIR); (void)!system(c);
        f = fopen(df, "w"); if (f) { fputs(DEV, f); fclose(f); }
    }
    snprintf(LOGDIR, P, "%s/backup/%s", AROOT, DEV);
    /* ensure adata README exists */
    char rm[P]; snprintf(rm, P, "%s/README", AROOT);
    struct stat st;
    if (stat(rm, &st) != 0) {
        f = fopen(rm, "w");
        if (f) {
            fputs("adata/ - 4-tier data sync\n\n"
                  "  git/      git push/pull       all devices     text <15M\n"
                  "  sync/     rclone copy <->      all devices     large files <5G\n"
                  "  vault/    rclone copy on-demand big devices     models/datasets\n"
                  "  backup/   rclone move ->        all devices     logs+state, upload+purge\n", f);
            fclose(f);
        }
    }
}
