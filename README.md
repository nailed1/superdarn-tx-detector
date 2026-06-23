# superdarn-tx-detector

CLI tool for detecting SuperDARN transmitter on/off state from FITACF radar observation files, with optional CSV export for analysis.

## What it does

By default, `tx_detector` reads a FITACF file (including `.bz2` compressed) and prints a single line: `0` if the transmitter appears off, `1` if on.

With `--csv`, it exports per-range-gate measurements instead:

| Column | Description |
|---|---|
| `time` | Time of day in fractional hours (UTC) |
| `range` | Range gate distance in km |
| `power` | Backscatter power (dB), `p_l` |
| `velocity` | Doppler velocity (m/s) |
| `spec_width` | Spectral width (m/s), `w_l` |
| `noise_search` | Noise search level from FITACF header (`noise.search`) |
| `stat_agc` | AGC status flag |
| `stat_lopwr` | Low-power status flag |

Both `.fitacf` and `.fitacf.bz2` files are supported (bz2 is decompressed on the fly via `bzip2 -dc`).

## Detection parameters

Detection uses two signals from each FITACF record:

| Parameter | Source | Role |
|---|---|---|
| `noise.search` | `prm->noise.search` | Averaged across all records in the file; low values suggest the transmitter is off |
| `p_l` | `fit->rng[i].p_l` | Backscatter power per range gate; the fraction of gates with non-zero `p_l` indicates whether real radar returns are present |

For each file the tool computes:

- **avg_noise** - mean of `noise.search` over all records
- **nonzero_ratio** - share of range gates where `p_l != 0`

The transmitter is classified as **off** (`0`) when both conditions hold:

```
avg_noise < noise_threshold
nonzero_ratio < NONZERO_RATIO_THRESHOLD
```

(`noise_threshold` defaults to `NOISE_SEARCH_THRESHOLD`; see below.)

Otherwise it is classified as **on** (`1`).

## Thresholds and calibration

Default thresholds (defined in `src/viewer.c`):

| Constant | Default | Meaning |
|---|---|---|
| `NOISE_SEARCH_THRESHOLD` | `60.0` | Upper bound on `avg_noise` for tx-off classification |
| `NONZERO_RATIO_THRESHOLD` | `0.01` | Upper bound on non-zero `p_l` gate fraction for tx-off classification |

Override the noise threshold at runtime with `--threshold`:

```bash
./tx_detector data/file.fitacf.bz2 --threshold 55.0
```

These values are initial estimates and still need calibration against labeled files (see TODO in `src/viewer.c`). `NONZERO_RATIO_THRESHOLD` is compile-time only and cannot be overridden from the CLI.

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

### 3. Detect transmitter state (single file)

```bash
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2
# -> 0 or 1
```

### 4. Export CSV (single file)

```bash
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2 --csv > output.csv
```

### 5. Batch detection

Run detection on all FITACF files in `data/`:

```bash
bash scripts/detect_all.sh
```

Writes per-file results and a summary to `results.txt`, and prints the same to stdout. Each line maps `tx_detector` output (`0`/`1`) to `off`/`on`:

```
20260614.0001.06.ekb: off
...
Summary: N files, X off, Y on
```

Run from the project root (the script uses `./tx_detector` and `data/`).

### 6. Batch CSV export

```bash
mkdir -p csv
bash scripts/parse_all.sh
```

`parse_all.sh` does not create `csv/` itself. Run from the project root.

Output files are named by stripping the `.fitacf.bz2` / `.fitacf` extension and adding `.csv`:

```
data/20260614.0001.06.ekb.fitacf.bz2  →  csv/20260614.0001.06.ekb.csv
```

### 7. Visualize CSV

```bash
python scripts/visualize.py 20260614.0001.06.ekb.csv
```

Expects the file under `csv/`; plots `power`, `velocity`, and `spec_width` (extra CSV columns are ignored).

## Usage

```
tx_detector <fname> [--csv] [--threshold <value>]
```

| Flag | Description |
|---|---|
| *(none)* | Detection mode - print `0` (tx off) or `1` (tx on) |
| `--csv` | CSV export mode |
| `--threshold <value>` | Override `NOISE_SEARCH_THRESHOLD` (detection mode only) |

## Project structure

```
superdarn-tx-detector/
├── src/
│   ├── viewer.c        # FITACF reader, detection and CSV output
│   ├── main.h          # Includes and RST type imports
│   └── defs.h          # Type definitions
├── scripts/
│   ├── detect_all.sh   # Batch tx on/off detection → results.txt
│   ├── parse_all.sh    # Batch CSV export → csv/
│   └── visualize.py    # Plot power/velocity/spec_width from CSV
├── data/               # FITACF input files (*.fitacf, *.bz2 git-ignored)
├── csv/                # CSV output (git-ignored)
├── results.txt         # Batch detection output (git-ignored)
├── RSTLite/            # RST Lite library (git-ignored)
├── Makefile
└── README.md
```
