#include <dirent.h>
#include <string.h>
#include <stdio.h>
int main(int argc, char **argv) {
    DIR *d = opendir(".");
    struct dirent *e;
    while ((e = readdir(d))) if (strstr(e->d_name, argv[1])) puts(e->d_name);
    closedir(d);
    return 0;
}
