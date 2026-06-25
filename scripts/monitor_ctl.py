#!/usr/bin/env python3
"""Operator CLI for SuperDARN file monitor instances.

Commands (from scripts/):
    monitor-pause <instance>
    monitor-resume <instance>
    monitor-status <instance>
    monitor-test <instance>

Instance config: MONITOR_CONFIG_DIR/<instance>.conf
SMTP config: MONITOR_SMTP_CONFIG or MONITOR_CONFIG_DIR/smtp.conf
State: MONITOR_STATE_DIR/<instance>.state
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from monitor import (
    default_config_dir,
    default_state_dir,
    format_age,
    inspect_instance,
    is_paused,
    load_config,
    load_smtp_config,
    load_state,
    send_email,
    set_paused,
)

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def color_status(status):
    ok = status == "ACTIVE"
    if not sys.stdout.isatty():
        return status
    color = GREEN if ok else RED
    return f"{color}{status}{RESET}"


def resolve_instance(name, config_dir, state_dir):
    return load_config(name, config_dir, state_dir)


def cmd_pause(instance, config, smtp_config=None):
    if is_paused(config["state_file"]):
        print(f"{instance}: already paused")
        return 0
    set_paused(config["state_file"], True)
    print(f"{instance}: alerts paused")
    return 0


def cmd_resume(instance, config, smtp_config=None):
    if not is_paused(config["state_file"]):
        print(f"{instance}: already active")
        return 0
    set_paused(config["state_file"], False)
    print(f"{instance}: alerts resumed")
    return 0


def cmd_status(instance, config, smtp_config=None):
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

    print(f"threshold: {config['threshold']}")
    print(f"alerts sent: {info['alert_count']} / {info['max_alerts']}")
    return 0


def cmd_test(instance, config, smtp_config=None):
    subject = "[TEST] SuperDARN monitor alert"
    body = f"Test alert from monitor instance '{instance}'"
    result = send_email(config, smtp_config, subject, body)
    if result is True:
        print("Email sent successfully")
        return 0
    if result is False:
        print("Email delivery failed (see stderr)")
        return 1
    print("Email skipped: recipient or SMTP user not configured")
    return 1


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


def add_common_args(parser):
    parser.add_argument(
        "--config-dir",
        default=default_config_dir(),
        help="Directory with <instance>.conf files",
    )
    parser.add_argument(
        "--state-dir",
        default=default_state_dir(),
        help="Directory for <instance>.state and pause flags",
    )


def main(argv=None):
    if argv is None:
        full_argv = sys.argv
    else:
        full_argv = ["monitor_ctl.py"] + argv

    command, rest = parse_operator_args(full_argv)

    parser = argparse.ArgumentParser(description="SuperDARN monitor operator CLI")
    add_common_args(parser)

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
        config = resolve_instance(args.instance, args.config_dir, args.state_dir)
        smtp_config = load_smtp_config(args.config_dir)
        return COMMANDS[cmd](args.instance, config, smtp_config)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
