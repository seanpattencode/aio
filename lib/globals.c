/* ═══ GLOBALS ═══ */
static char HOME[P], TMP[P], DDIR[P], AROOT[P], SROOT[P], SDIR[P], DEV[128], LOGDIR[P];
static int G_argc; static char **G_argv;

typedef struct { char path[512], repo[512], name[128], file[P]; int order; } proj_t;
static proj_t PJ[MP]; static int NPJ;

typedef struct { char name[128], cmd[512]; } app_t;
static app_t AP[MA]; static int NAP;

typedef struct { char key[16], name[64], cmd[1024]; } sess_t;
static sess_t SE[MS]; static int NSE;

typedef struct { char k[64], v[1024]; } cfg_t;
static cfg_t CF[64]; static int NCF;
