#if 0
cc -O2 -w -o "${0%.c}" "$0" && echo "built ${0%.c}" && exit 0
exit 1
#endif
/* Minimal ollama agent: cmd exec, memory, loop, feedback. Self-compiling. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define URL "http://localhost:11434/api/chat"
#define B 65536
#define MAXMEM 20

static char *mem[MAXMEM*2];
static int nm;

static void madd(const char *role, const char *content) {
    if (nm >= MAXMEM*2) { free(mem[0]); free(mem[1]); memmove(mem, mem+2, (MAXMEM*2-2)*sizeof(char*)); nm -= 2; }
    mem[nm++] = strdup(role); mem[nm++] = strdup(content);
}

static char *jesc(const char *s, char *o, int max) {
    char *p = o, *e = o+max-2;
    for (; *s && p < e; s++) {
        if (*s == '"' || *s == '\\') { *p++ = '\\'; *p++ = *s; }
        else if (*s == '\n') { *p++ = '\\'; *p++ = 'n'; }
        else if (*s == '\t') { *p++ = '\\'; *p++ = 't'; }
        else if ((unsigned char)*s >= 0x20) *p++ = *s;
    }
    *p = 0; return o;
}

static char *chat(const char *model) {
    static char body[B], resp[B], esc[B];
    int n = snprintf(body, B, "{\"model\":\"%s\",\"stream\":false,\"messages\":["
        "{\"role\":\"system\",\"content\":\"Linux CLI agent. To run a command, your ENTIRE reply must be: CMD: <command>\\nNothing else. One command per reply. After seeing output, answer in plain text.\"},", model);
    for (int i = 0; i < nm; i += 2)
        n += snprintf(body+n, B-n, "{\"role\":\"%s\",\"content\":\"%s\"},", mem[i], jesc(mem[i+1], esc, B));
    if (body[n-1] == ',') n--;
    snprintf(body+n, B-n, "]}");
    FILE *tmp = fopen("/tmp/.ollama_body", "w");
    if (!tmp) return NULL;
    fputs(body, tmp); fclose(tmp);
    FILE *f = popen("curl -s '" URL "' -d @/tmp/.ollama_body", "r");
    if (!f) return NULL;
    int len = fread(resp, 1, B-1, f); resp[len] = 0; pclose(f);
    char *p = strstr(resp, "\"content\":\"");
    if (!p) return NULL;
    p += 11;
    char *out = resp, *w = out;
    for (; *p && !(*p == '"' && *(p-1) != '\\'); p++) {
        if (*p == '\\' && p[1] == 'n') { *w++ = '\n'; p++; }
        else if (*p == '\\' && p[1] == '"') { *w++ = '"'; p++; }
        else if (*p == '\\' && p[1] == '\\') { *w++ = '\\'; p++; }
        else *w++ = *p;
    }
    *w = 0;
    while (*out == ' ' || *out == '\n') out++;
    return strdup(out);
}

int main(int argc, char **argv) {
    const char *model = argc > 1 ? argv[1] : "mistral";
    char input[B], out[B];
    for (;;) {
        printf("\n> "); fflush(stdout);
        if (!fgets(input, B, stdin)) break;
        input[strcspn(input, "\n")] = 0;
        if (!*input) continue;
        madd("user", input);
        for (;;) {
            char *t = chat(model);
            if (!t) { puts("(ollama error)"); break; }
            /* find CMD: anywhere (models sometimes add preamble) */
            char *cp = strstr(t, "CMD:");
            if (!cp) { puts(t); madd("assistant", t); free(t); break; }
            char *cmd = cp + 4; while (*cmd == ' ' || *cmd == '`') cmd++;
            char *nl = strchr(cmd, '\n'); if (nl) *nl = 0;
            { char *e = cmd+strlen(cmd)-1; while (e>cmd && *e=='`') *e--=0; }
            printf("CMD: %s\n$ %s\n", cmd, cmd);
            madd("assistant", t);
            FILE *p = popen(cmd, "r");
            int len = 0;
            if (p) { len = fread(out, 1, B-1, p); pclose(p); }
            out[len] = 0;
            if (!*out) strcpy(out, "(no output)");
            printf("%s", out);
            char fb[B]; snprintf(fb, B, "Output of `%s`:\n%s", cmd, out);
            madd("user", fb);
            free(t);
        }
    }
}
