# superdarn-tx-detector

CLI tool for SuperDARN FITACF files: CSV export and transmitter state detection (ON/OFF).

## Usage

```
tx_detector <file> [...] [--csv] [--auto] [--threshold N]
```

| Flag | Description |
|---|---|
| *(none)* | Detect mode. Outputs `0` (OFF) or `1` (ON) per file to stdout. Diagnostics go to stderr. |
| `--csv` | CSV mode. Dumps all range-gate measurements to stdout. |
| `--auto` | Automatic threshold detection. See below. |
| `--threshold N` | Use custom noise threshold instead of the default 60.0. |

Input files can be `.fitacf` or `.fitacf.bz2` (decompressed on the fly).

## Detect mode (default)

One line per file on stdout: `0` (transmitter OFF) or `1` (transmitter ON).

Detection uses two conditions:
- Average `noise.search` across all records **< threshold**
- Global `nonzero_ratio` across all range gates **< 0.01**

Both must be true for OFF; otherwise ON. Default threshold is 60.0, overridable with `--threshold`.

## CSV mode (`--csv`)

One row per range gate per time step:

```
time,range,power,velocity,spec_width,noise_search,stat_agc,stat_lopwr
```

| Column | Description |
|---|---|
| `time` | Fractional hours (UTC) |
| `range` | Range gate distance (km) |
| `power` | Backscatter power (dB), `p_l` |
| `velocity` | Doppler velocity (m/s) |
| `spec_width` | Spectral width (m/s), `w_l` |
| `noise_search` | Noise level from search phase |
| `stat_agc` | AGC status flag |
| `stat_lopwr` | Low power status flag |

## Automatic threshold (`--auto`)

For unlabeled datasets — finds the ON/OFF noise boundary adaptively.

**Algorithm:** Maximum Relative Gap on per-file medians.

1. For each file, compute the **median** `noise.search` (robust to within-file outliers)
2. Sort the per-file medians
3. Find the largest **relative** jump between adjacent values: `(a[i] - a[i-1]) / a[i-1]`
4. Threshold = midpoint of that gap
5. Classify each file by majority of its records above/below the threshold

Two modes:

- **Global** (`tx_detector data/* --auto`) — one threshold across all files, per-file classification on stdout, threshold on stderr
- **Single-file** (`tx_detector file --auto`) — finds internal split within one file; add `--csv` for per-record cluster labels

## Quick start

### 1. Install RSTLite

```bash
git clone https://github.com/vtsuperdarn/RSTLite
cd RSTLite && ./install.sh && cd ..
```

### 2. Build

```bash
make
```

Produces `./tx_detector`.

### 3. Examples

```bash
# Detect with default threshold
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2

# Adaptively find threshold across a batch
./tx_detector data/*.fitacf.bz2 --auto

# Custom threshold
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2 --threshold 76.86

# Parse to CSV
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2 --csv > out.csv
```

### 4. Batch operations

```bash
# Batch detection → results.txt
bash scripts/detect_all.sh

# Batch CSV export → csv/
mkdir -p csv
bash scripts/parse_all.sh

# Visualize CSV
python scripts/visualize.py csv/20260614.0001.06.ekb.csv
```

### 5. Monitor system

See `monitor/` for the continuous monitoring daemon (multi-instance, email alerts, CLI control).

## Project structure

```
superdarn-tx-detector/
├── src/
│   ├── viewer.c         # CSV parser, detection logic, auto-threshold
│   ├── main.h           # RST includes
│   └── defs.h           # Integer typedefs, zlib
├── scripts/
│   ├── detect_all.sh    # Batch tx detection → results.txt
│   ├── parse_all.sh     # Batch CSV export → csv/
│   └── visualize.py     # Plot power/velocity/spec_width from CSV
├── monitor/             # Continuous monitoring daemon
├── data/                # FITACF inputs (git-ignored)
├── csv/                 # CSV outputs (git-ignored)
├── results.txt          # Batch detection output (git-ignored)
├── RSTLite/             # RST Lite library (git-ignored)
├── Makefile
└── README.md
```
