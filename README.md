# superdarn-tx-detector

CLI tool for detecting SuperDARN radar transmitter outages from FITACF observation data.

## Description

Program reads a FITACF file and outputs `1` if transmitters were active, `0` if they were off.
Detection is based on three parameters from `RadarParm`:
- `pwr0` — signal power
- `noise.search` — noise level
- `stat.agc` / `stat.lopwr` — transmitter status

## Usage

```bash
./tx_detector <filename.fitacf>
```

## Dependencies

- [RSTLite](https://github.com/SuperDARN/rst) — SuperDARN Radar Software Toolkit

## Installation

1. Clone the repository
2. Install RSTLite: `cd RSTLite && ./install.sh`
3. Build: `make`

## Project Structure

```
superdarn-tx-detector/
├── src/         # Source code
├── data/        # FITACF data files (ignored by git)
├── scripts/     # Visualization scripts
├── RSTLite/     # RST Lite library (ignored by git)
├── Makefile
└── README.md
```