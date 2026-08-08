"""
session.py - ViperOS session entrypoint.

This is what the `viperos-session` OpenRC service execs into once Alpine
has finished its normal boot. From here on, the running system is
"ViperOS" from the user's point of view, even though the kernel and base
OS underneath are stock Alpine.

Responsibilities, in order:
  1. Set up logging.
  2. Register and start critical services (registry.py). Any failure
     here is fatal - it propagates and the OpenRC service is expected
     to fail/respawn, same as any other init-managed service.
  3. Initialize modman and run configured startup modules through
     modman.call(), so a broken user module degrades gracefully instead
     of blocking the rest of session startup.
  4. Hand off to whatever the configured run mode is (currently: just
     the `viper` CLI, run in the foreground).

Run manually for local testing with:
    python3 -m viperos.core.session
"""

import sys
from datetime import datetime, timezone

from viperos.core import modman
from viperos.core.registry import Registry

# Modules modman should try to run at session startup, in order.
# Each must exist in modman's store (i.e. `modman init <name> <path>`
# has been run at some point - by the image build, or by the user).
STARTUP_MODULES = [
    "greeter",
]


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _start_core_placeholder() -> None:
    # Placeholder critical service - real critical services (e.g. a
    # config loader, a device manager, whatever ViperOS ends up needing
    # at its core) get registered the same way this one is.
    log("[core] placeholder critical service started")


def build_registry() -> Registry:
    registry = Registry()
    registry.register("core-placeholder", _start_core_placeholder)
    return registry


def run_startup_modules() -> None:
    for name in STARTUP_MODULES:
        result, used_fallback = modman.call(name, "run", log=log)
        if used_fallback:
            log(f"[session] module '{name}' ran from stock fallback "
                f"(active version had a problem - check `modman versions {name}`)")


def main() -> int:
    log("ViperOS session starting")

    registry = build_registry()
    try:
        registry.start_all(log=log)
    except Exception as exc:
        log(f"[session] CRITICAL: a core service failed to start: {exc}")
        # Critical failures are fatal by design - let OpenRC's supervision
        # handle recovery rather than trying to limp forward.
        return 1

    run_startup_modules()

    log("ViperOS session ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
