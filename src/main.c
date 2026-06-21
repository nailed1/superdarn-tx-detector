#include <stdio.h>
#include <stdlib.h>
#include <zlib.h>
#include "rtypes.h"
#include "dmap.h"
#include "rprm.h"
#include "fitblk.h"
#include "fitdata.h"
#include "fitread.h"

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <filename.fitacf>\n", argv[0]);
        return 1;
    }

    FILE *fp = fopen(argv[1], "r");
    if (fp == NULL) {
        fprintf(stderr, "Error: cannot open file %s\n", argv[1]);
        return 1;
    }

    struct RadarParm *prm = RadarParmMake();
    struct FitData *fit = FitMake();

    int record = 0;
    while (FitFread(fp, prm, fit) != -1) {
        record++;
        printf("rec=%d noise.search=%.2f stat.agc=%d stat.lopwr=%d\n",
               record,
               prm->noise.search,
               prm->stat.agc,
               prm->stat.lopwr);
    }

    printf("Total records: %d\n", record);

    RadarParmFree(prm);
    FitFree(fit);
    fclose(fp);
    return 0;
}