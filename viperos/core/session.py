"""
session.py - ViperOS session entrypoint.

This is what the `viperos-session` OpenRC service execs into once Alpine
has finished its normal boot. From here on, the running system is
"ViperOS" from the user's point of view, even though the kernel and base
OS underneath are stock Alpine.

Responsibilities, in order:
  1. Register and start critical services (registry.py), starting with
     logging_service - once it's up, everything else logs through it
     instead of print(). Any failure here is fatal - it propagates and
     the OpenRC service is expected to fail/respawn, same as any other
     init-managed service.
  2. Initialize modman and run configured startup modules through
     modman.call(), so a broken user module degrades gracefully instead
     of blocking the rest of session startup.
  3. Hand off to whatever the configured run mode is (currently: just
     the `viper` CLI, run in the foreground).

Run manually for local testing with:
    python3 -m viperos.core.session
"""

import sys

from viperos.core import logging_service
from viperos.core import modman
from viperos.core.registry import Registry

# Modules modman should try to run at session startup, in order.
# Each must exist in modman's store (i.e. `modman init <name> <path>`
# has been run at some point - by the image build, or by the user).
STARTUP_MODULES = [
    "greeter",
]


def _bootstrap_log(message: str) -> None:
    # Used ONLY before logging_service has started - there's a real
    # chicken-and-egg moment where the registry needs to report progress
    # on starting the logging service itself, before that service exists
    # to log through. Everything after logging_service.start() succeeds
    # should go through a real logger instead.
    print(f"[bootstrap] {message}", flush=True)


def build_registry() -> Registry:
    registry = Registry()
    # logging_service goes first: nothing else should log through print()
    # once this is up.
    registry.register("logging", logging_service.start)
    return registry


def run_startup_modules(logger) -> None:
    for name in STARTUP_MODULES:
        result, used_fallback = modman.call(name, "run", log=logger.info)
        if used_fallback:
            logger.warning(
                f"module '{name}' ran from stock fallback "
                f"(active version had a problem - check `modman versions {name}`)"
            )


def main() -> int:
    _bootstrap_log("ViperOS session starting")

    registry = build_registry()
    try:
        registry.start_all(log=_bootstrap_log)
    except Exception as exc:
        _bootstrap_log(f"CRITICAL: a core service failed to start: {exc}")
        # Critical failures are fatal by design - let OpenRC's supervision
        # handle recovery rather than trying to limp forward.
        return 1

    # Logging is now up - switch to it for everything else.
    logger = logging_service.get_logger("session")
    logger.info("Critical services started successfully.")

    run_startup_modules(logger)

    logger.info("ViperOS session ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
