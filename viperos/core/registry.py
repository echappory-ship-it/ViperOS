"""
registry.py - Critical service registry for ViperOS.

Unlike modman-managed modules, critical services are NOT user-swappable
at runtime. They're plain Python and are started, in order, every boot.
If one fails, that's a boot-blocking problem the OS surfaces loudly
rather than silently working around.

A "critical service" here is just a name plus a zero-argument start
function. Keep these minimal - anything that can reasonably be optional
belongs in modman instead.
"""

from dataclasses import dataclass
from typing import Callable, List


@dataclass
class CriticalService:
    name: str
    start: Callable[[], None]


class Registry:
    """
    Ordered collection of critical services. start_all() runs each one in
    registration order and lets exceptions propagate - a critical service
    failing is meant to stop the boot, not be silently swallowed.
    """

    def __init__(self):
        self._services: List[CriticalService] = []

    def register(self, name: str, start_fn: Callable[[], None]) -> None:
        self._services.append(CriticalService(name=name, start=start_fn))

    def start_all(self, log=print) -> None:
        for service in self._services:
            log(f"[registry] starting critical service: {service.name}")
            service.start()
            log(f"[registry] started: {service.name}")
