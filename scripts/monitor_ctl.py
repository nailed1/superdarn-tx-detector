#!/usr/bin/env python3
"""Operator CLI for file monitor instances.

Usage:
    monitor_ctl.py pause <instance>
    monitor_ctl.py resume <instance>
    monitor_ctl.py status <instance>
    monitor_ctl.py test <instance>

Also works via symlinks: monitor-pause, monitor-resume, monitor-status, monitor-test.

Instances are listed in monitor_instances.ini (or MONITOR_INSTANCES env):

    [instances]
    ekb_fitacf = /etc/superdarn/ekb_fitacf.conf
"""

import argparse
import os
import sys
from configparser import ConfigParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from monitor import (
    format_age,
    format_threshold,
    inspect_instance,
    is_paused,
    load_config,
    load_state,
    set_paused,
)

DEFAULT_INSTANCES_FILE = os.path.join(SCRIPT_DIR, "monitor_instances.ini")

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def default_instances_file():
    return os.environ.get("MONITOR_INSTANCES", DEFAULT_INSTANCES_FILE)


def load_instances(path):
    parser = ConfigParser()
    read = parser.read(path)
    if not read:
        raise FileNotFoundError(f"Instances file not found: {path}")

    if not parser.has_section("instances"):
        raise ValueError("Instances file must contain an [instances] section")

    return dict(parser["instances"])


def resolve_instance(name, instances_path):
    instances = load_instances(instances_path)
    if name not in instances:
        known = ", ".join(sorted(instances)) or "(none)"
        raise ValueError(f"Unknown instance '{name}'. Known: {known}")
    return load_config(instances[name])


def color_status(status):
    ok = status == "ACTIVE"
    if not sys.stdout.isatty():
        return status
    color = GREEN if ok else RED
    return f"{color}{status}{RESET}"


def cmd_pause(instance, config):
    if is_paused(config["state_file"]):
        print(f"{instance}: already paused")
        return 0
    set_paused(config["state_file"], True)
    print(f"{instance}: alerts paused")
    return 0


def cmd_resume(instance, config):
    if not is_paused(config["state_file"]):
        print(f"{instance}: already active")
        return 0
    set_paused(config["state_file"], False)
    print(f"{instance}: alerts resumed")
    return 0


def cmd_status(instance, config):
    state = load_state(config["state_file"])
    info = inspect_instance(config, state)

    print(f"instance: {instance}")
    print(f"directory: {config['directory']}")
    print(f"mask: {config['mask']}")
    print(f"status: {color_status(info['status'])}")

    if info["last_file"]:
        print(f"last file: {info['last_file']} ({format_age(info['age'])})")
    else:
        print("last file: (none)")

    print(f"threshold: {format_threshold(config['stale_threshold_minutes'])}")
    print(f"alerts sent: {info['alert_count']} / {info['max_alerts']}")
    return 0


def cmd_test(instance, config):
    email = config.get("alert_email") or "(not configured)"
    print(f"instance: {instance}")
    print(f"to: {email}")
    print("subject: [TEST] SuperDARN monitor alert")
    print(f"body: Test alert from monitor instance '{instance}'")
    print("delivery: confirmed (stdout only, email not implemented yet)")
    return 0


COMMANDS = {
    "pause": cmd_pause,
    "resume": cmd_resume,
    "status": cmd_status,
    "test": cmd_test,
}


def parse_operator_args(argv):
    if not argv:
        return None, []

    prog = os.path.basename(argv[0])
    if prog.startswith("monitor-"):
        command = prog[len("monitor-") :]
        return command, argv[1:]

    return None, argv


def main(argv=None):
    if argv is None:
        full_argv = sys.argv
    else:
        full_argv = ["monitor_ctl.py"] + argv

    command, rest = parse_operator_args(full_argv)

    parser = argparse.ArgumentParser(description="SuperDARN monitor operator CLI")
    parser.add_argument(
        "--instances",
        default=default_instances_file(),
        help="Path to instances registry INI (default: monitor_instances.ini)",
    )

    if command and command in COMMANDS:
        parser.add_argument("instance", help="Monitor instance name")
        args = parser.parse_args(rest)
        cmd = command
    else:
        subparsers = parser.add_subparsers(dest="command", required=True)
        for name in COMMANDS:
            sub = subparsers.add_parser(name, help=f"monitor-{name}")
            sub.add_argument("instance", help="Monitor instance name")
        args = parser.parse_args(full_argv[1:])
        cmd = args.command

    try:
        config = resolve_instance(args.instance, args.instances)
        return COMMANDS[cmd](args.instance, config)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
