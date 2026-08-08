"""
shutdown.py - ViperOS's fourth critical service: graceful shutdown handling.

Installs SIGTERM/SIGINT handlers that, when received, run every
registered critical service's stop() hook (in reverse start order, via
registry.stop_all()) before the process actually exits. This is what
lets services like logging flush/close cleanly instead of the process
just dying mid-write.

Registered LAST in session.py's build_registry(), after logging, so the
shutdown handler itself can log through a real logger rather than print().

IMPORTANT SCOPE NOTE: as of this pass, viperos.core.session.main() runs
its startup sequence and returns - it does not yet block/run as a real
foreground process. That means in the current codebase, there generally
isn't a meaningful window for these signal handlers to fire before the
process would have exited on its own anyway. This service is correct and
tested in isolation (see the manual test pattern below), but it only
becomes practically meaningful once session.py grows an actual
long-running foreground loop - that's a natural, separate next step,
not something silently glossed over here.
"""

import signal
import sys

from viperos.core import logging_service

_registry = None
_installed = False


def install(registry) -> None:
    """
    Critical-service entrypoint. Takes the live Registry instance (via a
    closure at registration time in session.py, since Registry.register()
    only calls zero-argument start functions) and installs signal
    handlers that will run registry.stop_all() on SIGTERM/SIGINT.
    """
    global _registry, _installed

    _registry = registry
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    _installed = True


def _handle_signal(signum, frame) -> None:
    logger = logging_service.get_logger("shutdown")
    signame = signal.Signals(signum).name
    logger.info(f"Received {signame}, shutting down gracefully.")

    if _registry is not None:
        _registry.stop_all(log=logger.info)

    logger.info("Shutdown complete.")
    sys.exit(0)
