#include "main.h"

// TODO: calibrate thresholds on labeled files from Berngardt
#define NOISE_SEARCH_THRESHOLD 60.0
#define NONZERO_RATIO_THRESHOLD 0.01

static int is_bz2(const char *fname) {
    return strstr(fname, ".bz2") != NULL;
}

static FILE *open_file(const char *fname) {
    if (is_bz2(fname)) {
        char cmd[512];
        snprintf(cmd, sizeof(cmd), "bzip2 -dc %s", fname);
        return popen(cmd, "r");
    }
    return fopen(fname, "r");
}

static void close_file(FILE *fp, const char *fname) {
    if (is_bz2(fname)) pclose(fp);
    else fclose(fp);
}

static void mode_csv(FILE *fp, struct RadarParm *prm, struct FitData *fit) {
    printf("time,range,power,velocity,spec_width,noise_search,stat_agc,stat_lopwr\n");
    while (FitFread(fp, prm, fit) != -1) {
        for (long i = 0; i < prm->nrang; i++) {
            printf("%.4f,%ld,%.2f,%.2f,%.2f,%.2f,%d,%d\n",
                (double)prm->time.hr + (double)prm->time.mt/60. + (double)prm->time.sc/3600.,
                (long)(prm->frang + prm->rsep * i),
                (double)fit->rng[i].p_l,
                (double)fit->rng[i].v,
                (double)fit->rng[i].w_l,
                (double)prm->noise.search,
                prm->stat.agc,
                prm->stat.lopwr
            );
        }
    }
}

static void mode_detect(FILE *fp, struct RadarParm *prm, struct FitData *fit) {
    double noise_sum = 0.0;
    long noise_count = 0;
    long total_ranges = 0;
    long nonzero_ranges = 0;

    while (FitFread(fp, prm, fit) != -1) {
        noise_sum += prm->noise.search;
        noise_count++;

        for (long i = 0; i < prm->nrang; i++) {
            total_ranges++;
            if (fit->rng[i].p_l != 0.0)
                nonzero_ranges++;
        }
    }

    if (noise_count == 0) {
        fprintf(stderr, "No records found.\n");
        exit(-1);
    }

    double avg_noise = noise_sum / noise_count;
    double nonzero_ratio = (total_ranges > 0)
        ? (double)nonzero_ranges / total_ranges
        : 0.0;

    int tx_off = (avg_noise < NOISE_SEARCH_THRESHOLD)
        && (nonzero_ratio < NONZERO_RATIO_THRESHOLD);

    printf("%d\n", tx_off ? 0 : 1);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <fname> [--csv]\n", argv[0]);
        exit(1);
    }

    int csv_mode = (argc >= 3 && strcmp(argv[2], "--csv") == 0);

    FILE *fp = open_file(argv[1]);
    if (fp == NULL) {
        fprintf(stderr, "File %s not found.\n", argv[1]);
        exit(-1);
    }

    struct RadarParm *prm = RadarParmMake();
    struct FitData *fit = FitMake();

    if (csv_mode) mode_csv(fp, prm, fit);
    else mode_detect(fp, prm, fit);

    close_file(fp, argv[1]);
    return 0;
}
