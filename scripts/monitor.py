#!/usr/bin/env python3
"""Monitor a data directory for stale or undersized SuperDARN files.

Designed for cron. Example:

    */5 * * * * python3 /path/scripts/monitor.py /path/monitor.conf

Config (INI):

    [monitor]
    directory = /var/data/superdarn
    mask = YYYYMMDD.HHMM.*.fitacf.bz2
    utc_offset_hours = 0
    stale_threshold_minutes = 30
    min_file_size_bytes = 15
    max_alerts_per_incident = 3
    state_file = /var/lib/superdarn-monitor.state
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from configparser import ConfigParser
from datetime import datetime, timedelta

TIMESTAMP_RE = re.compile(r"^(\d{8})\.(\d{4})")

DEFAULT_MIN_SIZE = 15
DEFAULT_MAX_ALERTS = 3

INCIDENT_STALE = "stale"
INCIDENT_SMALL = "small_file"


def default_state():
    return {
        INCIDENT_STALE: {"active": False, "alert_count": 0},
        INCIDENT_SMALL: {"active": False, "alert_count": 0},
    }


def load_config(path):
    parser = ConfigParser()
    read = parser.read(path)
    if not read:
        raise FileNotFoundError(f"Config not found: {path}")

    if not parser.has_section("monitor"):
        raise ValueError("Config must contain a [monitor] section")

    section = parser["monitor"]
    required = ("directory", "mask", "stale_threshold_minutes", "state_file")
    missing = [key for key in required if not section.get(key)]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    return {
        "directory": section["directory"],
        "mask": section["mask"],
        "utc_offset_hours": section.getfloat("utc_offset_hours", fallback=0.0),
        "stale_threshold_minutes": section.getfloat("stale_threshold_minutes"),
        "min_file_size_bytes": section.getint(
            "min_file_size_bytes", fallback=DEFAULT_MIN_SIZE
        ),
        "max_alerts_per_incident": section.getint(
            "max_alerts_per_incident", fallback=DEFAULT_MAX_ALERTS
        ),
        "state_file": section["state_file"],
    }


def parse_timestamp(filename):
    match = TIMESTAMP_RE.match(filename)
    if not match:
        return None

    date_part, time_part = match.groups()
    try:
        return datetime(
            int(date_part[0:4]),
            int(date_part[4:6]),
            int(date_part[6:8]),
            int(time_part[0:2]),
            int(time_part[2:4]),
        )
    except ValueError:
        return None


def scan_directory(directory, mask):
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    matched = []
    for name in os.listdir(directory):
        if not fnmatch.fnmatch(name, mask):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        timestamp = parse_timestamp(name)
        if timestamp is None:
            continue
        matched.append((timestamp, name, path))

    matched.sort(key=lambda item: (item[0], item[1]))
    return matched


def load_state(path):
    if not os.path.exists(path):
        return default_state()

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    state = default_state()
    for key in (INCIDENT_STALE, INCIDENT_SMALL):
        if key in data and isinstance(data[key], dict):
            state[key]["active"] = bool(data[key].get("active", False))
            state[key]["alert_count"] = int(data[key].get("alert_count", 0))
    return state


def save_state(path, state):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def server_now():
    return datetime.now()


def utc_now_for_comparison(utc_offset_hours):
    return server_now() - timedelta(hours=utc_offset_hours)


def handle_incident(*, condition, incident_key, message, state, max_alerts):
    incident = state[incident_key]
    alerted = False

    if condition:
        if not incident["active"]:
            incident["active"] = True
            incident["alert_count"] = 0

        if incident["alert_count"] < max_alerts:
            print(f"[ALERT] {message}", flush=True)
            incident["alert_count"] += 1
            alerted = True
    elif incident["active"]:
        incident["active"] = False
        incident["alert_count"] = 0

    return alerted


def run_monitor(config, state):
    files = scan_directory(config["directory"], config["mask"])
    max_alerts = config["max_alerts_per_incident"]
    stale_threshold = timedelta(minutes=config["stale_threshold_minutes"])
    offset_hours = config["utc_offset_hours"]
    min_size = config["min_file_size_bytes"]
    now_utc = utc_now_for_comparison(offset_hours)

    any_alert = False

    if not files:
        any_alert |= handle_incident(
            condition=True,
            incident_key=INCIDENT_STALE,
            message=(
                f"No files matching '{config['mask']}' with a valid timestamp "
                f"in {config['directory']}"
            ),
            state=state,
            max_alerts=max_alerts,
        )
        handle_incident(
            condition=False,
            incident_key=INCIDENT_SMALL,
            message="",
            state=state,
            max_alerts=max_alerts,
        )
        return any_alert

    newest_ts, newest_name, newest_path = files[-1]
    newest_utc = newest_ts
    age = now_utc - newest_utc
    stale = age > stale_threshold

    any_alert |= handle_incident(
        condition=stale,
        incident_key=INCIDENT_STALE,
        message=(
            f"No new file within {config['stale_threshold_minutes']:g} min: "
            f"newest={newest_name} "
            f"(filename_time={newest_ts:%Y-%m-%d %H:%M}, "
            f"age={age.total_seconds() / 60:.1f} min)"
        ),
        state=state,
        max_alerts=max_alerts,
    )

    file_size = os.path.getsize(newest_path)
    too_small = file_size < min_size

    any_alert |= handle_incident(
        condition=too_small,
        incident_key=INCIDENT_SMALL,
        message=(
            f"Newest file too small: {newest_name} "
            f"({file_size} bytes < {min_size} bytes minimum)"
        ),
        state=state,
        max_alerts=max_alerts,
    )

    return any_alert


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Monitor SuperDARN data directory for stale or small files."
    )
    parser.add_argument(
        "config",
        help="Path to INI config file with a [monitor] section",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        state = load_state(config["state_file"])
        alerted = run_monitor(config, state)
        save_state(config["state_file"], state)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        return 2

    return 1 if alerted else 0


if __name__ == "__main__":
    sys.exit(main())
