/* ═══ INIT PATHS ═══ */
static void init_paths(void) {
    const char *h = getenv("HOME"); if (!h) h = "/tmp";
    snprintf(HOME, P, "%s", h);
    snprintf(DDIR, P, "%s/.local/share/a", h);
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
            /* binary is at projects/a/a → strip to projects/ */
            s = strrchr(self, '/');
            if (s) { *s = 0; snprintf(AROOT, P, "%s/adata", self); snprintf(SROOT, P, "%s/git", AROOT); }
        }
    }
    if (!SROOT[0]) { snprintf(AROOT, P, "%s/projects/adata", h); snprintf(SROOT, P, "%s/git", AROOT); }
    snprintf(PYPATH, P, "%s/lib/a.py", SDIR);
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
