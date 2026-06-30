#include "main.h"

#define NOISE_SEARCH_THRESHOLD 60.0
#define NONZERO_RATIO_THRESHOLD 0.01

typedef struct {
    double noise;
    int file_idx;
} Record;

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

static void mode_detect(FILE *fp, struct RadarParm *prm, struct FitData *fit, double noise_threshold) {
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

    int tx_off = (avg_noise < noise_threshold) && (nonzero_ratio < NONZERO_RATIO_THRESHOLD);

    printf("%d\n", tx_off ? 0 : 1);
}

static int cmp_double(const void *a, const void *b) {
    double da = *(double *)a, db = *(double *)b;
    return (da > db) - (da < db);
}

static double find_maxgap_threshold(double *vals, int n) {
    double *sorted = malloc(n * sizeof(double));
    if (!sorted) { fprintf(stderr, "malloc failed.\n"); exit(-1); }
    memcpy(sorted, vals, n * sizeof(double));
    qsort(sorted, n, sizeof(double), cmp_double);

    double threshold = sorted[0];
    double max_rgap = 0;
    for (int i = 1; i < n; i++) {
        double rgap = (sorted[i] - sorted[i - 1]) / sorted[i - 1];
        if (rgap > max_rgap) {
            max_rgap = rgap;
            threshold = (sorted[i] + sorted[i - 1]) / 2.0;
        }
    }

    free(sorted);
    return threshold;
}

static int read_records(const char *fname, struct RadarParm *prm, struct FitData *fit,
                        Record **recs_out, int *n_out, int *cap_out) {
    FILE *fp = open_file(fname);
    if (!fp) { fprintf(stderr, "File %s not found.\n", fname); return -1; }

    int cap = *cap_out > 0 ? *cap_out : 1024;
    Record *recs = *recs_out;
    if (!recs) {
        recs = malloc(cap * sizeof(Record));
        if (!recs) { fprintf(stderr, "malloc failed.\n"); exit(-1); }
    }
    int n = *n_out;

    while (FitFread(fp, prm, fit) != -1) {
        if (n >= cap) {
            cap *= 2;
            recs = realloc(recs, cap * sizeof(Record));
            if (!recs) { fprintf(stderr, "realloc failed.\n"); exit(-1); }
        }

        recs[n].noise = prm->noise.search;
        recs[n].file_idx = -1;
        n++;
    }

    close_file(fp, fname);
    *recs_out = recs;
    *n_out = n;
    *cap_out = cap;
    return 0;
}

static void mode_auto_single(const char *fname, struct RadarParm *prm, struct FitData *fit, int csv_out) {
    Record *recs = NULL;
    int n = 0, cap = 0;
    if (read_records(fname, prm, fit, &recs, &n, &cap) != 0) exit(-1);
    if (n == 0) { fprintf(stderr, "No records found.\n"); exit(-1); }

    double *noise_vals = malloc(n * sizeof(double));
    if (!noise_vals) { fprintf(stderr, "malloc failed.\n"); exit(-1); }
    for (int i = 0; i < n; i++) noise_vals[i] = recs[i].noise;

    double threshold = find_maxgap_threshold(noise_vals, n);

    int below = 0, above = 0;
    for (int i = 0; i < n; i++) {
        if (recs[i].noise < threshold) below++;
        else above++;
    }

    int tx_on = (above >= below) ? 1 : 0;

    if (csv_out) {
        printf("noise,cluster\n");
        for (int i = 0; i < n; i++) {
            printf("%.2f,%d\n", recs[i].noise, (recs[i].noise < threshold) ? 0 : 1);
        }
    }

    fprintf(stderr, "# maxgap_threshold=%.2f\n", threshold);
    fprintf(stderr, "# records: below=%d above=%d\n", below, above);
    printf("%d\n", tx_on);

    free(noise_vals);
    free(recs);
}

static void mode_auto_global(int nfiles, char **fnames, struct RadarParm *prm, struct FitData *fit) {
    Record *recs = NULL;
    int n = 0, cap = 0;
    int *file_starts = malloc((nfiles + 1) * sizeof(int));
    if (!file_starts) { fprintf(stderr, "malloc failed.\n"); exit(-1); }

    int total_records = 0;
    file_starts[0] = 0;

    for (int f = 0; f < nfiles; f++) {
        int prev_n = n;
        if (read_records(fnames[f], prm, fit, &recs, &n, &cap) != 0) exit(-1);
        file_starts[f + 1] = n;
        for (int i = prev_n; i < n; i++) recs[i].file_idx = f;

        int rec_cnt = n - prev_n;
        total_records += rec_cnt;
        fprintf(stderr, "# loaded %s: %d records\n", fnames[f], rec_cnt);
    }

    if (n == 0) { fprintf(stderr, "No records found.\n"); exit(-1); }

    double *file_medians = malloc(nfiles * sizeof(double));
    if (!file_medians) { fprintf(stderr, "malloc failed.\n"); exit(-1); }

    for (int f = 0; f < nfiles; f++) {
        int cnt = file_starts[f + 1] - file_starts[f];
        double *vals = malloc(cnt * sizeof(double));
        if (!vals) { fprintf(stderr, "malloc failed.\n"); exit(-1); }
        for (int i = file_starts[f]; i < file_starts[f + 1]; i++)
            vals[i - file_starts[f]] = recs[i].noise;
        qsort(vals, cnt, sizeof(double), cmp_double);
        file_medians[f] = vals[cnt / 2];
        free(vals);
    }

    double threshold = find_maxgap_threshold(file_medians, nfiles);
    fprintf(stderr, "# maxgap_threshold=%.2f (from %d files, %d records)\n",
        threshold, nfiles, total_records);
    free(file_medians);

    for (int f = 0; f < nfiles; f++) {
        int below = 0, above = 0;
        for (int i = file_starts[f]; i < file_starts[f + 1]; i++) {
            if (recs[i].noise < threshold) below++;
            else above++;
        }
        printf("%s %d\n", fnames[f], (above >= below) ? 1 : 0);
    }

    free(recs);
    free(file_starts);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <fname> [...] [--csv] [--auto] [--threshold <value>]\n", argv[0]);
        exit(1);
    }

    int csv_mode = 0;
    int auto_mode = 0;
    double noise_threshold = NOISE_SEARCH_THRESHOLD;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--csv") == 0) {
            csv_mode = 1;
        } else if (strcmp(argv[i], "--auto") == 0) {
            auto_mode = 1;
        } else if (strcmp(argv[i], "--threshold") == 0 && i + 1 < argc) {
            noise_threshold = atof(argv[i + 1]);
            i++;
        } else if (argv[i][0] == '-') {
            fprintf(stderr, "Unknown flag: %s\n", argv[i]);
            exit(1);
        }
    }

    int nfiles = 0;
    char *fnames[argc];
    for (int i = 1; i < argc; i++) {
        if (argv[i][0] != '-') {
            fnames[nfiles++] = argv[i];
        } else if (strcmp(argv[i], "--threshold") == 0) {
            i++;
        }
    }

    if (nfiles == 0) {
        fprintf(stderr, "No input files.\n");
        exit(1);
    }

    struct RadarParm *prm = RadarParmMake();
    struct FitData *fit = FitMake();

    if (auto_mode && nfiles >= 2) {
        mode_auto_global(nfiles, fnames, prm, fit);
        return 0;
    }

    if (auto_mode) {
        mode_auto_single(fnames[0], prm, fit, csv_mode);
        return 0;
    }

    if (csv_mode) {
        for (int f = 0; f < nfiles; f++) {
            FILE *fp = open_file(fnames[f]);
            if (!fp) { fprintf(stderr, "File %s not found.\n", fnames[f]); continue; }
            mode_csv(fp, prm, fit);
            close_file(fp, fnames[f]);
        }
        return 0;
    }

    for (int f = 0; f < nfiles; f++) {
        FILE *fp = open_file(fnames[f]);
        if (!fp) { fprintf(stderr, "File %s not found.\n", fnames[f]); continue; }
        mode_detect(fp, prm, fit, noise_threshold);
        close_file(fp, fnames[f]);
    }

    return 0;
}
