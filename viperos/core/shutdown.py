"""
shutdown.py - ViperOS's graceful shutdown critical service.

Installs SIGTERM/SIGINT handlers that REQUEST a shutdown by setting a
threading.Event, rather than doing real work inside the signal handler
itself. This follows standard practice: signal handlers should do as
little as possible. The actual shutdown sequence - running every
critical service's stop() hook via registry.stop_all() - happens in
normal code, in session.py's foreground run loop, once that loop wakes
up from waiting on the event.

(Earlier version of this file called registry.stop_all() directly from
inside the signal handler. That worked in testing, but running arbitrary
I/O - file flushes, closes - inside a signal handler is fragile in
general, e.g. if the signal happens to interrupt another log write.
This version is the corrected, safer pattern.)
"""

import signal
import threading

_shutdown_event = threading.Event()
_installed = False


def install() -> None:
    """
    Critical-service entrypoint: install SIGTERM/SIGINT handlers. Takes
    no arguments and does no I/O - deliberately minimal, per the module
    docstring above.
    """
    global _installed
    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    _installed = True


def _request_shutdown(signum, frame) -> None:
    # Intentionally minimal: just record that a shutdown was requested.
    # No logging, no cleanup - that all happens in session.py's run loop,
    # outside of signal-handler context.
    _shutdown_event.set()


def wait_for_shutdown(timeout=None) -> bool:
    """
    Block the calling thread until a shutdown has been requested (or
    timeout elapses). Returns True if a shutdown was requested, False on
    timeout. This is what session.py's foreground loop blocks on.
    """
    return _shutdown_event.wait(timeout=timeout)


def is_shutdown_requested() -> bool:
    return _shutdown_event.is_set()


def reset() -> None:
    """Testing helper: clear the shutdown flag so it can be reused."""
    _shutdown_event.clear()
