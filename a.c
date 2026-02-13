/*
 * a.c - AI agent session manager
 *
 * Amalgamation: a.c is the program — includes, constants, and dispatch.
 * The compiler follows #include "lib/foo.c" to build one translation unit.
 * No header file, no concatenation script. Ordering = dependency resolution.
 *
 * Build:
 *   make          two clang passes in parallel (check + build)
 *   make debug    ASan/UBSan/IntSan -O1 -g
 *
 * Add a command:  write lib/foo.c, add #include + dispatch line here.
 * Remove:         delete the file, delete two lines.
 */
#ifndef __APPLE__
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <dirent.h>
#include <time.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <ctype.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

#define P 1024
#define B 4096
#define MP 256
#define MA 64
#define MS 48

static void alog(const char *cmd, const char *cwd, const char *extra);

/* ═══ AMALGAMATION ═══ */
#include "lib/globals.c"
#include "lib/init.c"
#include "lib/util.c"
#include "lib/kv.c"
#include "lib/data.c"
#include "lib/tmux.c"
#include "lib/git.c"
#include "lib/session.c"
#include "lib/alog.c"
#include "lib/help.c"
#include "lib/project.c"
#include "lib/config.c"
#include "lib/push.c"
#include "lib/ls.c"
#include "lib/note.c"
#include "lib/ssh.c"
#include "lib/net.c"
#include "lib/agent.c"
#include "lib/sess.c"

/* ═══ MAIN DISPATCH ═══ */
int main(int argc, char **argv) {
    init_paths();
    G_argc = argc; G_argv = argv;

    if (argc < 2) return cmd_help(argc, argv);

    /* Log every command */
    char acmd[B]="";for(int i=1,l=0;i<argc;i++) l+=snprintf(acmd+l,(size_t)(B-l),"%s%s",i>1?" ":"",argv[i]);
    char wd[P]; if(!getcwd(wd,P)) snprintf(wd,P,"%s",HOME);
    alog(acmd, wd, NULL);

    const char *arg = argv[1];

    /* Numeric = project number */
    { const char *p = arg; while (*p >= '0' && *p <= '9') p++;
      if (*p == '\0' && p != arg) { init_db(); return cmd_project_num(argc, argv, atoi(arg)); } }

    /* Special aliases from CMDS dict */
    if (!strcmp(arg,"help")||!strcmp(arg,"hel")||!strcmp(arg,"--help")||!strcmp(arg,"-h"))
        return cmd_help_full(argc, argv);
    if (!strcmp(arg,"killall")) return cmd_kill(argc, argv);
    if (!strcmp(arg,"p")) return cmd_push(argc, argv);
    if (!strcmp(arg,"rm")) return cmd_remove(argc, argv);
    if (!strcmp(arg,"n")) return cmd_note(argc, argv);
    if (!strcmp(arg,"t")) return cmd_task(argc, argv);
    if (!strcmp(arg,"a")||!strcmp(arg,"ai")||!strcmp(arg,"aio")) return cmd_all(argc, argv);
    if (!strcmp(arg,"i")) return cmd_i(argc, argv);
    if (!strcmp(arg,"gdrive")||!strcmp(arg,"gdr")) fallback_py(argc, argv);
    if (!strcmp(arg,"ask")) fallback_py(argc, argv);
    if (!strcmp(arg,"ui")) fallback_py(argc, argv);
    if (!strcmp(arg,"mono")||!strcmp(arg,"monolith")) fallback_py(argc, argv);
    if (!strcmp(arg,"rebuild")) return cmd_rebuild();
    if (!strcmp(arg,"logs")) return cmd_log(argc, argv);

    /* Exact + alias match */
    if (!strcmp(arg,"push")||!strcmp(arg,"pus")) return cmd_push(argc, argv);
    if (!strcmp(arg,"pull")||!strcmp(arg,"pul")) return cmd_pull(argc, argv);
    if (!strcmp(arg,"diff")||!strcmp(arg,"dif")) return cmd_diff(argc, argv);
    if (!strcmp(arg,"revert")||!strcmp(arg,"rev")) return cmd_revert(argc, argv);
    if (!strcmp(arg,"ls")) return cmd_ls(argc, argv);
    if (!strcmp(arg,"kill")||!strcmp(arg,"kil")) return cmd_kill(argc, argv);
    if (!strcmp(arg,"config")||!strcmp(arg,"con")) return cmd_config(argc, argv);
    if (!strcmp(arg,"prompt")||!strcmp(arg,"pro")) return cmd_prompt(argc, argv);
    if (!strcmp(arg,"set")||!strcmp(arg,"settings")) return cmd_set(argc, argv);
    if (!strcmp(arg,"add")) return cmd_add(argc, argv);
    if (!strcmp(arg,"remove")||!strcmp(arg,"rem")) return cmd_remove(argc, argv);
    if (!strcmp(arg,"move")||!strcmp(arg,"mov")) return cmd_move(argc, argv);
    if (!strcmp(arg,"scan")||!strcmp(arg,"sca")) return cmd_scan(argc, argv);
    if (!strcmp(arg,"done")) return cmd_done();
    if (!strcmp(arg,"hi")) return cmd_hi();
    if (!strcmp(arg,"dir")) return cmd_dir();
    if (!strcmp(arg,"backup")||!strcmp(arg,"bak")) return cmd_backup();
    if (!strcmp(arg,"web")) return cmd_web(argc, argv);
    if (!strcmp(arg,"repo")) return cmd_repo(argc, argv);
    if (!strcmp(arg,"setup")||!strcmp(arg,"set up")) return cmd_setup(argc, argv);
    if (!strcmp(arg,"install")||!strcmp(arg,"ins")) return cmd_install();
    if (!strcmp(arg,"uninstall")||!strcmp(arg,"uni")) return cmd_uninstall();
    if (!strcmp(arg,"deps")||!strcmp(arg,"dep")) return cmd_deps();
    if (!strcmp(arg,"e")) return cmd_e(argc, argv);
    if (!strcmp(arg,"x")) return cmd_x();
    if (!strcmp(arg,"copy")||!strcmp(arg,"cop")) return cmd_copy();
    if (!strcmp(arg,"dash")||!strcmp(arg,"das")) return cmd_dash();
    if (!strcmp(arg,"attach")||!strcmp(arg,"att")) return cmd_attach(argc, argv);
    if (!strcmp(arg,"watch")||!strcmp(arg,"wat")) return cmd_watch(argc, argv);
    if (!strcmp(arg,"send")||!strcmp(arg,"sen")) return cmd_send(argc, argv);
    if (!strcmp(arg,"jobs")||!strcmp(arg,"job")) return cmd_jobs(argc, argv);
    if (!strcmp(arg,"cleanup")||!strcmp(arg,"cle")) return cmd_cleanup(argc, argv);
    if (!strcmp(arg,"tree")||!strcmp(arg,"tre")) return cmd_tree(argc, argv);
    if (!strcmp(arg,"note")) return cmd_note(argc, argv);
    if (!strcmp(arg,"task")||!strcmp(arg,"tas")) return cmd_task(argc, argv);
    if (!strcmp(arg,"ssh")) return cmd_ssh(argc, argv);
    if (!strcmp(arg,"hub")) return cmd_hub(argc, argv);
    if (!strcmp(arg,"log")) return cmd_log(argc, argv);
    if (!strcmp(arg,"login")) return cmd_login(argc, argv);
    if (!strcmp(arg,"sync")||!strcmp(arg,"syn")) return cmd_sync(argc, argv);
    if (!strcmp(arg,"update")||!strcmp(arg,"upd")) return cmd_update(argc, argv);
    if (!strcmp(arg,"review")) return cmd_review(argc, argv);
    if (!strcmp(arg,"docs")||!strcmp(arg,"doc")) return cmd_docs(argc, argv);
    if (!strcmp(arg,"run")) return cmd_run(argc, argv);
    if (!strcmp(arg,"agent")) return cmd_agent(argc, argv);
    if (!strcmp(arg,"work")||!strcmp(arg,"wor")) { fallback_py(argc, argv); }
    if (!strcmp(arg,"all")) return cmd_all(argc, argv);

    /* x.* experimental commands */
    if (arg[0] == 'x' && arg[1] == '.') fallback_py(argc, argv);

    /* Worktree: key++ */
    { size_t l = strlen(arg);
      if (l >= 3 && arg[l-1] == '+' && arg[l-2] == '+' && arg[0] != 'w')
          return cmd_wt_plus(argc, argv); }

    /* Worktree: w* */
    if (arg[0] == 'w' && strcmp(arg,"watch") && strcmp(arg,"web") && !fexists(arg))
        return cmd_wt(argc, argv);

    /* Directory or file */
    if (dexists(arg) || fexists(arg)) return cmd_dir_file(argc, argv);
    { char ep[P]; snprintf(ep, P, "%s%s", HOME, arg);
      if (arg[0] == '/' && dexists(ep)) return cmd_dir_file(argc, argv); }

    /* Session key check */
    { init_db(); load_cfg(); load_sess();
      if (find_sess(arg)) return cmd_sess(argc, argv); }

    /* Short session-like keys (1-3 chars) */
    if (strlen(arg) <= 3 && arg[0] >= 'a' && arg[0] <= 'z')
        return cmd_sess(argc, argv);

    /* Unknown - try python */
    fallback_py(argc, argv);
}
