"""
viper.py - `viper` command entrypoint, the user-facing CLI for ViperOS.

This is the top-level command a user actually runs. Right now it wraps:
  - `viper session start` - runs the ViperOS session in the foreground,
    the same entrypoint OpenRC will eventually exec into. This is the
    main way to actually exercise ViperOS end-to-end before boot/OpenRC
    integration is tested for real.
  - `viper status`        - quick health check: are state dirs set up,
    is logging configured, what modules does modman know about.
  - `viper mod ...`        - proxies straight through to modman's own
    CLI (list/replace/versions/activate/init).
"""

import argparse
import sys

from viperos.core import logging_service
from viperos.core import modman
from viperos.core import session
from viperos.core import state_dirs


def _cmd_mod(args) -> int:
    # Delegate everything after 'mod' straight to modman's own CLI parser.
    sys.argv = ["modman"] + args.modman_args
    modman.main()
    return 0


def _cmd_session_start(args) -> int:
    return session.main()


def _cmd_status(args) -> int:
    print("ViperOS status")
    print("--------------")

    for path in state_dirs.REQUIRED_DIRS:
        exists = path.exists()
        marker = "OK" if exists else "MISSING"
        print(f"  state dir  [{marker:7}] {path}")

    log_file = logging_service.LOG_FILE
    log_marker = "OK" if log_file.exists() else "NOT YET WRITTEN"
    print(f"  log file   [{log_marker:7}] {log_file}")

    print()
    print("  modules (modman):")
    registry = modman._load_registry()
    modules = registry.get("modules", {})
    if not modules:
        print("    (none registered yet - see `viper mod init`)")
    else:
        for name, entry in modules.items():
            print(f"    {name:<20} active={entry.get('active_version', 'stock')}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="viper",
        description="ViperOS command-line interface.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show ViperOS state dir / logging / module status.")
    p_status.set_defaults(func=_cmd_status)

    p_session = sub.add_parser("session", help="Control the ViperOS session.")
    session_sub = p_session.add_subparsers(dest="session_command", required=True)
    p_session_start = session_sub.add_parser(
        "start", help="Run the ViperOS session in the foreground (what OpenRC will eventually exec)."
    )
    p_session_start.set_defaults(func=_cmd_session_start)

    p_mod = sub.add_parser(
        "mod", help="Manage non-critical modules (proxies to modman).",
        add_help=False,
    )
    p_mod.add_argument("modman_args", nargs=argparse.REMAINDER)
    p_mod.set_defaults(func=_cmd_mod)

    return parser


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
