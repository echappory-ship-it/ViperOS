"""
viper.py - `viper` command entrypoint, the user-facing CLI for ViperOS.

Skeleton stage: currently just exposes modman's CLI under `viper mod ...`.
As more of the OS gets built, this becomes the top-level command users
actually run (`viper status`, `viper mod list`, etc.).
"""

import sys

from viperos.core import modman


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if not argv or argv[0] != "mod":
        print("Usage: viper mod <modman-subcommand> [args...]")
        print("  (only 'mod' is wired up so far - see viperos/core/modman.py)")
        return 1

    # Delegate everything after 'mod' straight to modman's own CLI parser.
    sys.argv = ["modman"] + argv[1:]
    modman.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
