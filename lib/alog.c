/* ═══ ACTIVITY LOG ═══ */
static void alog(const char *cmd, const char *cwd, const char *extra) { (void)extra;
    pid_t p=fork();if(p<0)return;if(p>0){waitpid(p,NULL,WNOHANG);return;} /* parent returns instantly */
    if(fork()>0)_exit(0); setsid(); /* double-fork, child is orphan */
    char dir[P]; snprintf(dir, P, "%s/git/activity", AROOT);
    mkdirp(dir);
    time_t t = time(NULL); struct tm *tm = localtime(&t);
    struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
    char lf[P]; snprintf(lf, P, "%s/%04d%02d%02dT%02d%02d%02d.%03ld_%s.txt", dir,
        tm->tm_year+1900, tm->tm_mon+1, tm->tm_mday, tm->tm_hour, tm->tm_min, tm->tm_sec,
        ts.tv_nsec / 1000000, DEV);
    FILE *f = fopen(lf, "w"); if (!f) _exit(0);
    char repo[512] = "";
    if (git_in_repo(cwd)) {
        char c[B], out[512];
        snprintf(c, B, "git -C '%s' remote get-url origin 2>/dev/null", cwd);
        pcmd(c, out, 512); out[strcspn(out, "\n")] = 0;
        if (out[0]) snprintf(repo, 512, " git:%s", out);
    }
    fprintf(f, "%02d/%02d %02d:%02d %s %s %s%s\n",
        tm->tm_mon+1, tm->tm_mday, tm->tm_hour, tm->tm_min,
        DEV, cmd, cwd, repo);
    fclose(f); _exit(0);
}
