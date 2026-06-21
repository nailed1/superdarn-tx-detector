# superdarn-tx-detector

CLI tool for parsing SuperDARN FITACF radar observation files into CSV format.

## What it does

Reads FITACF files (including `.bz2` compressed) and extracts per-range-gate measurements into CSV with columns:

| Column | Description |
|---|---|
| `time` | Time of day in fractional hours (UTC) |
| `range` | Range gate distance in km |
| `power` | Backscatter power (dB), `p_l` |
| `velocity` | Doppler velocity (m/s) |
| `spec_width` | Spectral width (m/s), `w_l` |

## Quick start

### 1. Install RSTLite

The project depends on [RSTLite](https://github.com/SuperDARN/rst) for reading FITACF binary format.

```bash
git clone https://github.com/SuperDARN/rst RSTLite
cd RSTLite
./install.sh
cd ..
```

### 2. Build

```bash
make
```

This produces the `tx_detector` binary in the project root.

### 3. Parse a single file

```bash
./tx_detector data/20260614.0001.06.ekb.fitacf.bz2 > output.csv
```

Both `.fitacf` and `.fitacf.bz2` files are supported (bz2 is decompressed on the fly via `bzip2 -dc`).

### 4. Batch parse

To convert all FITACF files in `data/` to CSV files in `csv/`:

```bash
mkdir -p csv
bash scripts/parse_all.sh
```

Output files are named by stripping the `.fitacf.bz2` / `.fitacf` extension and adding `.csv`:
```
data/20260614.0001.06.ekb.fitacf.bz2  →  csv/20260614.0001.06.ekb.csv
```

## Project structure

```
superdarn-tx-detector/
├── src/
│   ├── main.c          # FITACF parser, CSV output
│   ├── main.h          # Includes and RST type imports
│   └── defs.h          # Type definitions
├── scripts/
│   └── parse_all.sh    # Batch processing script
├── data/               # FITACF input files (git-ignored)
├── csv/                # CSV output (git-ignored)
├── RSTLite/            # RST Lite library (git-ignored)
├── Makefile
└── README.md
```