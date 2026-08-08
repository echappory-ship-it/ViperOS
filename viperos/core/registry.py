"""
registry.py - Critical service registry for ViperOS.

Unlike modman-managed modules, critical services are NOT user-swappable
at runtime. They're plain Python and are started, in order, every boot.
If one fails to start, that's a boot-blocking problem the OS surfaces
loudly rather than silently working around.

A "critical service" here is a name, a zero-argument start function, and
an optional zero-argument stop function used during graceful shutdown
(see shutdown.py). Keep these minimal - anything that can reasonably be
optional belongs in modman instead.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass
class CriticalService:
    name: str
    start: Callable[[], None]
    stop: Optional[Callable[[], None]] = None


class Registry:
    """
    Ordered collection of critical services.

    start_all() runs each one in registration order and lets exceptions
    propagate - a critical service failing to start is meant to stop the
    boot, not be silently swallowed.

    stop_all() runs each registered stop hook in REVERSE registration
    order (last-started, first-stopped - the usual shutdown convention),
    and does NOT let one service's failure to stop cleanly block the
    others from getting a chance to clean up too. Services with no stop
    hook are just skipped.
    """

    def __init__(self):
        self._services: List[CriticalService] = []

    def register(self, name: str, start_fn: Callable[[], None],
                 stop_fn: Optional[Callable[[], None]] = None) -> None:
        self._services.append(CriticalService(name=name, start=start_fn, stop=stop_fn))

    def start_all(self, log=print) -> None:
        for service in self._services:
            log(f"[registry] starting critical service: {service.name}")
            service.start()
            log(f"[registry] started: {service.name}")

    def stop_all(self, log=print) -> None:
        for service in reversed(self._services):
            if service.stop is None:
                continue
            try:
                log(f"[registry] stopping critical service: {service.name}")
                service.stop()
                log(f"[registry] stopped: {service.name}")
            except Exception as exc:
                log(f"[registry] WARNING: '{service.name}' failed to stop cleanly: {exc}")
