"""
state_dirs.py - ViperOS's second critical service: state directory setup.

Single source of truth for "where does ViperOS keep its stuff on disk."
Runs before anything else that touches the filesystem (logging, modman),
so those services can assume their directories already exist with
correct ownership/permissions instead of each silently mkdir-ing their
own with default modes.

Deliberately imports the *paths* other modules already define (rather
than having them import from here) so this file stays the one place
that knows the full list, without forcing a circular import - modman.py
and logging_service.py keep their own path constants as the source of
truth for "what path do I use", and state_dirs.py is just responsible
for making sure those paths exist correctly before anyone else runs.
"""

import os
import stat
from pathlib import Path

from viperos.core import logging_service
from viperos.core import modman

# Directories ViperOS needs to exist before the rest of the system can
# rely on them. Owner: rwx, group: rx, other: none - state data isn't
# meant to be world-readable (logs and module scripts could contain
# details you don't want every local user seeing).
DIR_MODE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP  # 0o750

REQUIRED_DIRS = [
    modman.ROOT_DIR,
    logging_service.LOG_DIR,
]


def start() -> None:
    """
    Critical-service entrypoint: create every required ViperOS state
    directory with consistent permissions. Raises if a directory can't
    be created or made to have the right permissions - this is critical,
    so failure here should stop the boot rather than let other services
    limp along with missing or wrongly-permissioned state dirs.
    """
    for path in REQUIRED_DIRS:
        _ensure_dir(path)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, DIR_MODE)
