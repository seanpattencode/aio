/* ═══ ACTIVITY LOG ═══ */
static void alog(const char *cmd, const char *cwd, const char *extra) { (void)extra;
    char dir[P]; snprintf(dir, P, "%s/git/activity", AROOT);
    time_t t = time(NULL); struct tm *tm = localtime(&t);
    struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
    char lf[P]; snprintf(lf, P, "%s/%04d%02d%02dT%02d%02d%02d.%03ld_%s.txt", dir,
        tm->tm_year+1900, tm->tm_mon+1, tm->tm_mday, tm->tm_hour, tm->tm_min, tm->tm_sec,
        ts.tv_nsec / 1000000, DEV);
    FILE *f = fopen(lf, "w"); if (!f) return;
    fprintf(f, "%02d/%02d %02d:%02d %s %s %s\n",
        tm->tm_mon+1, tm->tm_mday, tm->tm_hour, tm->tm_min,
        DEV, cmd, cwd);
    fclose(f);
}
