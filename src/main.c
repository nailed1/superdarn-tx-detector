#include "main.h"

int main(int argc, char *argv[]) {
    FILE *fp;
    struct RadarParm prm;
    struct RadarParm *PRM;
    struct FitData fit;
    struct FitData *FIT;

    if (argc < 2) {
        fprintf(stderr, "usage %s fname\n", argv[0]);
        exit(1);
    }

    if (strstr(argv[1], ".bz2")) {
        char cmd[512];
        snprintf(cmd, sizeof(cmd), "bzip2 -dc %s", argv[1]);
        fp = popen(cmd, "r");
    } else {
        fp = fopen(argv[1], "r");
    }

    if (fp == NULL) {
        fprintf(stderr, "File %s not found.\n", argv[1]);
        exit(-1);
    }

    PRM = RadarParmMake();
    FIT = FitMake();
    prm = *PRM;
    fit = *FIT;

    printf("time,range,power,velocity,spec_width\n");

    while (FitFread(fp, &prm, &fit) != -1) {
        long i;
        for (i = 0; i < prm.nrang; i++) {
            printf("%.4f,%ld,%.2f,%.2f,%.2f\n",
                (double)prm.time.hr + (double)prm.time.mt/60. + (double)prm.time.sc/3600.,
                (long)(prm.frang + prm.rsep * i),
                (double)fit.rng[i].p_l,
                (double)fit.rng[i].v,
                (double)fit.rng[i].w_l
            );
        }
    }

    if (strstr(argv[1], ".bz2")) pclose(fp);
    else fclose(fp);

    return 0;
}