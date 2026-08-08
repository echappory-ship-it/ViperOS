"""
session.py - ViperOS session entrypoint.

This is what the `viperos-session` OpenRC service execs into once Alpine
has finished its normal boot. From here on, the running system is
"ViperOS" from the user's point of view, even though the kernel and base
OS underneath are stock Alpine.

Responsibilities, in order:
  1. Register and start critical services (registry.py): config first
     (so everything after can read config values), then state_dirs (so
     every path other services need already exists with correct
     permissions), then logging_service (once it's up, everything else
     logs through it instead of print()), then shutdown (installs
     SIGTERM/SIGINT handlers). Any failure here is fatal - it propagates
     and the OpenRC service is expected to fail/respawn, same as any
     other init-managed service.
  2. Initialize modman and run configured startup modules through
     modman.call(), so a broken user module degrades gracefully instead
     of blocking the rest of session startup.
  3. Enter the foreground run loop: block until a shutdown is requested
     (SIGTERM/SIGINT, handled by shutdown.py), then run every critical
     service's stop() hook in reverse order via registry.stop_all().

This is a genuinely long-running foreground process now - `viper session
start` will block until you send it SIGTERM or hit Ctrl+C (SIGINT).

Run manually for local testing with:
    python3 -m viperos.core.session
"""

import sys

from viperos.core import config
from viperos.core import logging_service
from viperos.core import modman
from viperos.core import shutdown
from viperos.core import state_dirs
from viperos.core.registry import Registry


def _bootstrap_log(message: str) -> None:
    # Used before logging_service has started, AND after it has stopped
    # (during final shutdown, once logging's own stop() has already
    # closed its handlers) - anywhere we can't rely on a live logger.
    print(f"[bootstrap] {message}", flush=True)


def build_registry() -> Registry:
    registry = Registry()
    # config goes first: state_dirs, logging, and startup module
    # selection all potentially read from it.
    registry.register("config", config.start)
    # state_dirs next: logging (and modman, and everything after)
    # assumes its directories already exist with correct permissions.
    registry.register("state-dirs", state_dirs.start)
    # logging_service next: nothing else should log through print()
    # once this is up. Has a real stop hook - flushes/closes handlers
    # cleanly during graceful shutdown.
    registry.register("logging", logging_service.start, stop_fn=logging_service.stop)
    # shutdown goes last: installs signal handlers that just set a flag
    # (see shutdown.py) - the run loop below is what actually reacts to it.
    registry.register("shutdown", shutdown.install)
    return registry


def run_startup_modules(logger) -> None:
    startup_modules = config.get_config()["session"]["startup_modules"]
    for name in startup_modules:
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

    # Logging is now up - switch to it for everything else, until it
    # stops again during shutdown below.
    logger = logging_service.get_logger("session")
    logger.info("Critical services started successfully.")

    run_startup_modules(logger)

    logger.info("ViperOS session ready. Waiting for shutdown signal (SIGTERM/SIGINT)...")

    # Foreground run loop: block here until shutdown.py's signal handler
    # sets the shutdown flag. This is the actual "session" - everything
    # before this point was startup, everything after is shutdown.
    shutdown.wait_for_shutdown()

    logger.info("Shutdown requested - stopping critical services.")
    registry.stop_all(log=logger.info)
    # logging's stop() hook has now closed its own handlers as part of
    # stop_all() above - drop back to bootstrap-style printing for the
    # final line, same as we do before logging starts.
    _bootstrap_log("ViperOS session stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
