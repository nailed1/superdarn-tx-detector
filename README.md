# superdarn-tx-detector

CLI tool for parsing SuperDARN FITACF radar observation files and detecting transmitter state (ON/OFF).

## What it does

Reads FITACF files (including `.bz2` compressed) and either:
- **CSV mode** — extracts per-range-gate measurements
- **Detect mode** — determines whether the transmitter was ON or OFF

### CSV columns

| Column | Description |
|---|---|
| `time` | Time of day in fractional hours (UTC) |
| `range` | Range gate distance in km |
| `power` | Backscatter power (dB), `p_l` |
| `velocity` | Doppler velocity (m/s) |
| `spec_width` | Spectral width (m/s), `w_l` |
| `noise_search` | Noise level from search phase |
| `stat_agc` | AGC status |
| `stat_lopwr` | Low power status |

## Quick start

### 1. Install RSTLite

The project depends on [RSTLite](https://github.com/vtsuperdarn/RSTLite) for reading FITACF binary format.

```bash
git clone https://github.com/vtsuperdarn/RSTLite

cd RSTLite
./install.sh
cd ..
```

### 2. Build

```bash
make
```

This produces the `tx_detector` binary in the project root.

### 3. Detect transmitter state

```bash
# Default: fixed threshold (60.0)
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2
# → 0 (OFF) or 1 (ON)

# Custom threshold
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2 --threshold 76.86

# Automatic threshold — processes all files and finds adaptive boundary
./tx_detector data/*.fitacf.bz2 --auto
# → per-file classification + derived threshold on stderr
```

### 4. Parse to CSV

```bash
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2 --csv > output.csv
```

Both `.fitacf` and `.fitacf.bz2` files are supported (bz2 is decompressed on the fly via `bzip2 -dc`).

### 5. Batch parse

```bash
mkdir -p csv
bash scripts/parse_all.sh
```

Output files: `data/<name>.fitacf.bz2` → `csv/<name>.csv`.

## Automatic threshold detection (`--auto`)

When datasets are unlabeled, use `--auto` to find the ON/OFF noise boundary without manual tuning.

**Algorithm** — Maximum Relative Gap:

1. For each file, compute the **median** `noise.search` value (robust to outliers)
2. Sort the per-file medians
3. Find the largest **relative** jump `(a[i] - a[i-1]) / a[i-1]` between adjacent values
4. Threshold = midpoint of that gap
5. Classify each file by majority of records above/below the threshold

Two modes:

| Command | Behaviour |
|---|---|
| `tx_detector data/* --auto` | Global mode: single threshold across all files |
| `tx_detector file --auto` | Single-file mode: threshold from internal split |
| `tx_detector file --auto --csv` | Single-file with per-record cluster labels |

## Project structure

```
superdarn-tx-detector/
├── src/
│   ├── viewer.c         # FITACF parser, CSV output, transmitter detection
│   ├── main.h           # Includes and RST type imports
│   └── defs.h           # Type definitions
├── scripts/
│   └── parse_all.sh     # Batch processing script
├── data/                # FITACF input files (git-ignored)
├── csv/                 # CSV output (git-ignored)
├── RSTLite/             # RST Lite library (git-ignored)
├── Makefile
└── README.md
```
