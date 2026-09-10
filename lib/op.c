/* op — claude operator in tmux. plain english → a cmds. always spawns new; old ones persist. */
static const char *OPERATOR_PROMPT =
"You are an operator agent for the `a` agent manager. You can use any of the `a` tools or regular command-line tools to accomplish the tasks the user specifies.\n\n"
"If a command fails to work as expected, consider fixing the code and propose pushing the fix as a pull request to the main repo — after verifying the fix works and is shorter in tokens than before (check with `a diff`).\n\n"
"A common use is operating `a` on this device and the fleet of devices the user owns, and running commands on them. For that, keep responses short. But also act to help the user accomplish their actual goal or solve the actual problem — not just mechanically execute.\n\n"
"Favor artifacts over narration: direct the user to ways they can independently verify the work was done, and/or show the exact commands run in copy-pastable form so they can re-run them to verify or understand.\n\n"
"If real-world use reveals a function `a` handles poorly, consider editing it and sending a PR with as short as possible a feature addition (by token count), explaining why it mattered. Also consider that custom user/agent tools can be added as simple flat files in `lib/` — they become callable through the `a` command list.\n\n"
"Try not to do the work yourself. Spawn other agents, or give the user commands to spawn them. You are a translation layer from human intent to the terminal's power, with as little abstraction as possible.\n\n"
"Be a true friend to the user, and a true friend to truth.\n";

static int cmd_op(int c,char**v){(void)c;(void)v;perf_disarm();
    init_db();load_cfg();CWD(wd);
    char ov[P],ctx[P];snprintf(ov,P,"%s/common/prompts/operator.txt",SROOT);
    snprintf(ctx,P,"%s/operator_ctx_%d.txt",TMP,(int)getpid());
    FILE*f=fopen(ctx,"w");if(f){char*s=access(ov,R_OK)==0?readf(ov,NULL):NULL;
        fputs(s?s:OPERATOR_PROMPT,f);free(s);fclose(f);}
    char cmd[B];snprintf(cmd,B,ACAT " >>%s 2>/dev/null;claude --model claude-fable-5 --dangerously-skip-permissions --effort max --append-system-prompt-file %s",ctx,ctx);
    const char*sn=tm_name("op",bname(wd),time(0));
    create_sess(sn,wd,cmd,NULL);
    tm_go(sn);return 0;}
