/* ═══ TMUX HELPERS ═══ */
static int tm_has(const char *s) {
    /* direct fork/exec: no shell, no timeout wrapper — perf_arm is the guard */
    pid_t p=fork();if(p==0){int fd=open("/dev/null",O_WRONLY);
        if(fd>=0){dup2(fd,STDERR_FILENO);close(fd);}
        execlp("tmux","tmux","has-session","-t",s,(char*)0);_exit(1);}
    int st;waitpid(p,&st,0);return WIFEXITED(st)&&WEXITSTATUS(st)==0;
}

static void tm_go(const char *s) {
    perf_disarm(); /* interactive session — no timeout */
    if (getenv("TMUX")) execlp("tmux", "tmux", "switch-client", "-t", s, (char*)NULL);
    else execlp("tmux", "tmux", "attach", "-t", s, (char*)NULL);
}

static int tm_new(const char *s, const char *wd, const char *cmd) {
    char c[B*2];
    if (cmd && cmd[0]) snprintf(c, sizeof(c), "tmux new-session -d -s '%s' -c '%s' '%s'", s, wd, cmd);
    else snprintf(c, sizeof(c), "tmux new-session -d -s '%s' -c '%s'", s, wd);
    return system(c);
}

static void tm_send(const char *s, const char *text) {
    pid_t p = fork();
    if (p == 0) { execlp("tmux", "tmux", "send-keys", "-l", "-t", s, text, (char*)NULL); _exit(1); }
    if (p > 0) waitpid(p, NULL, 0);
}

static int tm_read(const char *s, char *buf, int len) {
    char c[B]; snprintf(c, B, "tmux capture-pane -t '%s' -p -S -50 2>/dev/null", s);
    return pcmd(c, buf, len);
}

static void tm_key(const char *s, const char *key) {
    pid_t p = fork();
    if (p == 0) { execlp("tmux", "tmux", "send-keys", "-t", s, key, (char*)NULL); _exit(1); }
    if (p > 0) waitpid(p, NULL, 0);
}

/* ═══ DIRECTING SESSIONS ═══
 * a watch <s>           — read pane    a send <s> <prompt> --wait — send + wait
 * Example: a c proj "task" → a send claude-proj "next" --wait → a watch claude-proj
 * C: tm_read(sn,buf,B) inspect, tm_send(sn,text) literal, tm_key(sn,"Enter") key */

/* ═══ TMUX CONFIG ═══ */

static void tm_ensure_conf(void) {
    if (strcmp(cfget("tmux_conf"), "y") != 0) return;
    char adir[P]; snprintf(adir, P, "%s/.a", HOME);
    mkdirp(adir);
    char cpath[P]; snprintf(cpath, P, "%s/tmux.conf", adir);
    FILE *f = fopen(cpath, "w");
    if (!f) return;
    const char *cc = clip_cmd();
    fputs("# aio-managed-config\n"
        "set -ga update-environment \"WAYLAND_DISPLAY\"\n"
        "set -g mouse on\n"
        "set -g focus-events on\n"
        "set -g set-titles on\n"
        "set -g set-titles-string \"#S:#W\"\n"
        "set -s set-clipboard on\n"
        "set -g visual-bell off\n"
        "set -g bell-action any\n"
        "set -g status-position bottom\n"
        "set -g status 3\n"
        "set -g status-right \"\"\n"
        "set -g status-format[0] \"#[align=left][#S]#[align=centre]#{W:#[range=window|#{window_index}]#I:#W#{?window_active,*,}#[norange] }\"\n"
        "set -g status-format[1] \"#[align=centre]#{?#{e|<:#{client_width},70},"
        "#[range=user|agent]Agent#[norange] #[range=user|win]Win#[norange] #[range=user|new]Pane#[norange] #[range=user|side]Side#[norange] #[range=user|close]Close#[norange] #[range=user|edit]Edit#[norange] #[range=user|detach]Quit#[norange],"
        "#[range=user|agent]Ctrl+A:Agent#[norange] #[range=user|win]Ctrl+N:Win#[norange] #[range=user|new]Ctrl+T:Pane#[norange] #[range=user|side]Ctrl+Y:Side#[norange] #[range=user|close]Ctrl+W:Close#[norange] #[range=user|edit]Ctrl+E:Edit#[norange] #[range=user|detach]Ctrl+Q:Quit#[norange]}\"\n"
        "set -g status-format[2] \"#[align=left]#[range=user|esc]Esc#[norange]#[align=centre]#[range=user|kbd]Keyboard#[norange]\"\n"
        /* TODO: add -c '#{pane_current_path}' to splits/windows below + mouse handler
         * so new panes in worktrees open in worktree dir, not session start dir */
        "bind-key -n C-n new-window\n"
        "bind-key -n C-t split-window\n"
        "bind-key -n C-y split-window -fh\n"
        "bind-key -n C-a split-window -h 'claude --dangerously-skip-permissions'\n"
        "bind-key -n C-w kill-pane\n"
        "bind-key -n C-q detach\n"
        "bind-key -n C-x confirm-before -p \"Kill session? (y/n)\" kill-session\n"
        "bind-key -n C-e split-window -fh -c '#{pane_current_path}' ~/.local/bin/e\n"
        "bind-key -T root MouseDown1Status if -F '#{==:#{mouse_status_range},window}' "
        "{ select-window } { run-shell 'r=\"#{mouse_status_range}\"; case \"$r\" in "
        "agent) tmux split-window -h \"claude --dangerously-skip-permissions\";; "
        "win) tmux new-window;; new) tmux split-window;; side) tmux split-window -fh;; "
        "close) tmux kill-pane;; edit) tmux split-window -fh -c \"#{pane_current_path}\" ~/.local/bin/e;; "
        "detach) tmux detach;; esc) tmux send-keys Escape;; "
        "kbd) tmux set -g mouse off; tmux display-message \"Mouse off 3s\"; "
        "(sleep 3; tmux set -g mouse on) &;; esac' }\n", f);
    /* Termux: /tmp is owned by shell:shell (0771), Termux app user can't mkdir
     * inside it. Claude Code sandbox does mkdir /tmp/claude-* before every tool
     * call, failing with EACCES. CLAUDE_CODE_TMPDIR redirects to writable dir */
    if (access("/data/data/com.termux",F_OK)==0)
        fprintf(f,"set-environment -g CLAUDE_CODE_TMPDIR \"%s/.tmp\"\n",HOME);
    if (cc) fprintf(f, "set -s copy-command \"%s\"\n", cc);
    if (cc) {
        fprintf(f, "bind -T copy-mode MouseDragEnd1Pane send -X copy-pipe-and-cancel \"%s\"\n", cc);
        fprintf(f, "bind -T copy-mode-vi MouseDragEnd1Pane send -X copy-pipe-and-cancel \"%s\"\n", cc);
    } else {
        fputs("bind -T copy-mode MouseDragEnd1Pane send -X copy-pipe-and-cancel\n"
              "bind -T copy-mode-vi MouseDragEnd1Pane send -X copy-pipe-and-cancel\n", f);
    }
    /* tmux >= 3.6: scrollbar support */
    char vbuf[64] = ""; int vmaj = 0, vmin = 0;
    pcmd("tmux -V 2>/dev/null", vbuf, 64);
    { char *v = strstr(vbuf, "tmux "); if (v) sscanf(v + 5, "%d.%d", &vmaj, &vmin); }
    if (vmaj > 3 || (vmaj == 3 && vmin >= 6))
        fputs("set -g pane-scrollbars on\nset -g pane-scrollbars-position right\n", f);
    fclose(f);
    /* Append source line to ~/.tmux.conf if not present */
    char uconf[P]; snprintf(uconf, P, "%s/.tmux.conf", HOME);
    char *uc = readf(uconf, NULL);
    if (!uc || !strstr(uc, "~/.a/tmux.conf")) {
        FILE *uf = fopen(uconf, "a");
        if (uf) { fputs("\nsource-file ~/.a/tmux.conf  # a\n", uf); fclose(uf); }
    }
    free(uc);
    /* Source config in running tmux server */
    if (system("tmux info >/dev/null 2>&1") != 0) return;
    char cmd[B]; snprintf(cmd, B, "tmux source-file '%s' 2>/dev/null", cpath);
    (void)!system(cmd);
    (void)!system("tmux refresh-client -S 2>/dev/null");
}
