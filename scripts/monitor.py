#!/usr/bin/env python3
"""Monitor a data directory for stale or undersized SuperDARN files.

Designed for cron. Example:

    */5 * * * * python3 /path/scripts/monitor.py ekb_fitacf
    */5 * * * * python3 /path/scripts/monitor.py /etc/confings-monitor/ekb_fitacf.conf

Config (INI, one file per instance):

    [monitor]
    directory  = /data/ekb/
    mask       = *.fitacf.bz2
    threshold  = 3h
    utc_offset = +5
    min_size   = 15

    [alerts]
    max_alerts = 3
    recipient  = oleg@example.com

SMTP credentials (shared, one file for all instances):

    /etc/confings-monitor/smtp.conf

    [smtp]
    host     = smtp.gmail.com
    port     = 465
    user     = monitor@example.com
    password = secret
    sender   = monitor@example.com

State and pause flag live under MONITOR_STATE_DIR (not in the config file).
Config path: argument or MONITOR_CONFIG_DIR/<instance>.conf
SMTP path: MONITOR_SMTP_CONFIG or MONITOR_CONFIG_DIR/smtp.conf
"""

import argparse
import fnmatch
import json
import os
import re
import smtplib
import ssl
import sys
from configparser import ConfigParser
from datetime import datetime, timedelta
from email.message import EmailMessage

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TIMESTAMP_RE = re.compile(r"^(\d{8})\.(\d{4})")
THRESHOLD_RE = re.compile(r"^(\d+(?:\.\d+)?)(h|min|m)?$", re.IGNORECASE)

DEFAULT_CONFIG_DIR = "/etc/confings-monitor"
DEFAULT_STATE_DIR = "/var/lib/states-monitor"
DEFAULT_SMTP_FILE = "smtp.conf"
DEFAULT_MIN_SIZE = 15
DEFAULT_MAX_ALERTS = 3
DEFAULT_SMTP_HOST = ""
DEFAULT_SMTP_PORT = 465

INCIDENT_STALE = "stale"
INCIDENT_SMALL = "small_file"


def default_config_dir():
    return os.environ.get("MONITOR_CONFIG_DIR", DEFAULT_CONFIG_DIR)


def default_state_dir():
    return os.environ.get("MONITOR_STATE_DIR", DEFAULT_STATE_DIR)


def smtp_config_path(config_dir=None):
    env_path = os.environ.get("MONITOR_SMTP_CONFIG")
    if env_path:
        return env_path
    config_dir = config_dir or default_config_dir()
    return os.path.join(config_dir, DEFAULT_SMTP_FILE)


def config_path_for_instance(instance, config_dir=None):
    config_dir = config_dir or default_config_dir()
    return os.path.join(config_dir, instance + ".conf")


def state_path_for_instance(instance, state_dir=None):
    state_dir = state_dir or default_state_dir()
    return os.path.join(state_dir, instance + ".state")


def instance_from_config_path(path):
    return os.path.splitext(os.path.basename(path))[0]


def resolve_target(target, config_dir=None):
    if os.path.sep in target or target.endswith(".conf") or target.endswith(".ini"):
        config_path = os.path.abspath(target)
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"Config not found: {config_path}")
        return instance_from_config_path(config_path), config_path
    return target, config_path_for_instance(target, config_dir)


def parse_threshold(value):
    match = THRESHOLD_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid threshold: {value!r} (use e.g. 3h, 30min, 90)")

    amount = float(match.group(1))
    unit = (match.group(2) or "").lower()
    if unit == "h":
        return amount * 60
    return amount


def parse_utc_offset(value):
    try:
        return float(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid utc_offset: {value!r}") from exc


def default_state():
    return {
        INCIDENT_STALE: {"active": False, "alert_count": 0},
        INCIDENT_SMALL: {"active": False, "alert_count": 0},
    }


def load_config(target, config_dir=None, state_dir=None):
    instance, config_path = resolve_target(target, config_dir)

    parser = ConfigParser()
    read = parser.read(config_path)
    if not read:
        raise FileNotFoundError(f"Config not found: {config_path}")

    if not parser.has_section("monitor"):
        raise ValueError(f"{config_path}: missing [monitor] section")

    monitor = parser["monitor"]
    if not parser.has_section("alerts"):
        parser.add_section("alerts")
    alerts = parser["alerts"]

    required = ("directory", "mask", "threshold")
    missing = [key for key in required if not monitor.get(key)]
    if missing:
        raise ValueError(f"{config_path}: missing keys: {', '.join(missing)}")

    threshold_raw = monitor["threshold"].strip()
    utc_offset_raw = monitor.get("utc_offset", "0").strip()

    return {
        "instance": instance,
        "config_path": config_path,
        "state_file": state_path_for_instance(instance, state_dir),
        "directory": monitor["directory"].strip(),
        "mask": monitor["mask"].strip(),
        "threshold": threshold_raw,
        "threshold_minutes": parse_threshold(threshold_raw),
        "utc_offset": utc_offset_raw,
        "utc_offset_hours": parse_utc_offset(utc_offset_raw),
        "min_size": monitor.getint("min_size", fallback=DEFAULT_MIN_SIZE),
        "max_alerts": alerts.getint("max_alerts", fallback=DEFAULT_MAX_ALERTS),
        "recipient": alerts.get("recipient", "").strip(),
    }


def load_smtp_config(config_dir=None):
    path = smtp_config_path(config_dir)
    if not os.path.isfile(path):
        return None

    parser = ConfigParser()
    if not parser.read(path):
        return None

    if not parser.has_section("smtp"):
        return None

    smtp = parser["smtp"]
    return {
        "path": path,
        "host": smtp.get("host", DEFAULT_SMTP_HOST).strip(),
        "port": smtp.getint("port", fallback=DEFAULT_SMTP_PORT),
        "user": smtp.get("user", "").strip(),
        "password": smtp.get("password", "").strip(),
        "sender": smtp.get("sender", "").strip(),
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


def pause_flag_path(state_file):
    base, _ = os.path.splitext(state_file)
    return base + ".pause"


def is_paused(state_file):
    return os.path.exists(pause_flag_path(state_file))


def set_paused(state_file, paused):
    path = pause_flag_path(state_file)
    if paused:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8"):
            pass
    elif os.path.exists(path):
        os.remove(path)


def format_age(age):
    total_minutes = int(age.total_seconds() // 60)
    if total_minutes < 60:
        return f"{total_minutes} min ago"
    hours = total_minutes // 60
    rem = total_minutes % 60
    if rem == 0:
        return f"{hours}h ago"
    return f"{hours}h {rem}min ago"


def send_email(config, smtp_config, subject, body):
    recipient = config.get("recipient", "")
    if not recipient or not smtp_config or not smtp_config.get("user"):
        return None

    sender = smtp_config.get("sender", "").strip() or smtp_config.get("user", "").strip()
    smtp_host = smtp_config.get("host", DEFAULT_SMTP_HOST)
    smtp_port = smtp_config.get("port", DEFAULT_SMTP_PORT)
    smtp_password = smtp_config.get("password", "")

    msg = EmailMessage()
    msg["To"] = recipient
    msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.login(smtp_config["user"], smtp_password)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"[ERROR] email: {exc}", file=sys.stderr, flush=True)
        return False


def inspect_instance(config, state):
    files = scan_directory(config["directory"], config["mask"])
    max_alerts = config["max_alerts"]
    stale_threshold = timedelta(minutes=config["threshold_minutes"])
    offset_hours = config["utc_offset_hours"]
    min_size = config["min_size"]
    now_utc = utc_now_for_comparison(offset_hours)
    paused = is_paused(config["state_file"])

    stale = False
    too_small = False
    last_file = None
    age = None

    if not files:
        stale = True
    else:
        newest_ts, newest_name, newest_path = files[-1]
        age = now_utc - newest_ts
        stale = age > stale_threshold
        file_size = os.path.getsize(newest_path)
        too_small = file_size < min_size
        last_file = newest_name

    alert_count = max(
        state[INCIDENT_STALE]["alert_count"],
        state[INCIDENT_SMALL]["alert_count"],
    )

    if paused:
        status = "PAUSED"
    elif stale or too_small:
        status = "ALERT"
    else:
        status = "ACTIVE"

    return {
        "paused": paused,
        "status": status,
        "stale": stale,
        "too_small": too_small,
        "last_file": last_file,
        "age": age,
        "alert_count": alert_count,
        "max_alerts": max_alerts,
    }


def handle_incident(
    *,
    condition,
    incident_key,
    message,
    state,
    max_alerts,
    paused=False,
    config=None,
    smtp_config=None,
    last_file=None,
    age=None,
):
    incident = state[incident_key]
    alerted = False

    if condition:
        if not incident["active"]:
            incident["active"] = True
            incident["alert_count"] = 0

        if incident["alert_count"] < max_alerts and not paused:
            print(f"[ALERT] {message}", flush=True)
            incident["alert_count"] += 1
            alerted = True

            if config is not None:
                age_str = format_age(age) if age is not None else "n/a"
                subject = f"[monitor] {config['instance']} - {incident_key} ({age_str})"
                body = (
                    f"Instance: {config['instance']}\n"
                    f"Directory: {config['directory']}\n"
                    f"Last file: {last_file or 'none'}\n"
                    f"Time since: {age_str}\n"
                    f"Alert: {incident['alert_count']} / {max_alerts}"
                )
                send_email(config, smtp_config, subject, body)
    elif incident["active"]:
        incident["active"] = False
        incident["alert_count"] = 0

    return alerted


def run_monitor(config, state, smtp_config=None):
    files = scan_directory(config["directory"], config["mask"])
    max_alerts = config["max_alerts"]
    stale_threshold = timedelta(minutes=config["threshold_minutes"])
    offset_hours = config["utc_offset_hours"]
    min_size = config["min_size"]
    now_utc = utc_now_for_comparison(offset_hours)
    paused = is_paused(config["state_file"])

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
            paused=paused,
            config=config,
            smtp_config=smtp_config,
        )
        handle_incident(
            condition=False,
            incident_key=INCIDENT_SMALL,
            message="",
            state=state,
            max_alerts=max_alerts,
            paused=paused,
            config=config,
            smtp_config=smtp_config,
        )
        return any_alert

    newest_ts, newest_name, newest_path = files[-1]
    age = now_utc - newest_ts
    stale = age > stale_threshold

    any_alert |= handle_incident(
        condition=stale,
        incident_key=INCIDENT_STALE,
        message=(
            f"No new file within {config['threshold']}: "
            f"newest={newest_name} "
            f"(filename_time={newest_ts:%Y-%m-%d %H:%M}, "
            f"age={age.total_seconds() / 60:.1f} min)"
        ),
        state=state,
        max_alerts=max_alerts,
        paused=paused,
        config=config,
        smtp_config=smtp_config,
        last_file=newest_name,
        age=age,
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
        paused=paused,
        config=config,
        smtp_config=smtp_config,
        last_file=newest_name,
        age=age,
    )

    return any_alert


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Monitor SuperDARN data directory for stale or small files."
    )
    parser.add_argument(
        "target",
        help="Instance name or path to instance config file",
    )
    parser.add_argument(
        "--config-dir",
        default=default_config_dir(),
        help=f"Config directory when target is instance name (default: {DEFAULT_CONFIG_DIR})",
    )
    parser.add_argument(
        "--state-dir",
        default=default_state_dir(),
        help=f"State directory (default: {DEFAULT_STATE_DIR})",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.target, args.config_dir, args.state_dir)
        smtp_config = load_smtp_config(args.config_dir)
        state = load_state(config["state_file"])
        alerted = run_monitor(config, state, smtp_config)
        save_state(config["state_file"], state)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        return 2

    return 1 if alerted else 0


if __name__ == "__main__":
    sys.exit(main())
