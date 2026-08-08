"""
config.py - ViperOS's config-loading critical service.

Loads /etc/viperos/config.toml (overridable via VIPEROS_CONFIG for
testing, same pattern as MODMAN_ROOT / VIPEROS_LOG_DIR) and makes it
available to the rest of the system via get_config().

This is the FIRST critical service to start - before state_dirs, before
logging - because those (and everything after them) may want to read
config values. If the config file is missing entirely, that's fine: we
fall back to built-in defaults. If the file exists but is malformed,
that's treated as fatal, same as any other critical service failure -
better to stop the boot loudly than silently run with a config the
admin thinks is being used but isn't.

Scope note: this currently controls session startup_modules and the
logging level. It does NOT control MODMAN_ROOT or VIPEROS_LOG_DIR - those
remain env-var-driven for now, since folding them in here would mean
restructuring how those modules resolve their paths at import time.
That's a reasonable follow-up, not done as part of this pass.
"""

import os
import tomllib
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("VIPEROS_CONFIG", "/etc/viperos/config.toml"))

DEFAULTS = {
    "session": {
        "startup_modules": ["greeter"],
    },
    "logging": {
        "level": "INFO",
    },
}

_config = None


def start() -> None:
    """
    Critical-service entrypoint: load config.toml if present, merge it
    over the defaults, and cache the result for get_config(). Raises if
    the file exists but fails to parse - a broken config file should
    stop the boot, not be silently ignored.
    """
    global _config

    if not CONFIG_PATH.exists():
        _config = _deep_copy_defaults()
        return

    with open(CONFIG_PATH, "rb") as f:
        loaded = tomllib.load(f)

    _config = _merge_over_defaults(loaded)


def get_config() -> dict:
    """
    Return the loaded config dict. Must be called after start() has run
    (i.e. after the config critical service has started) - calling it
    before that is a programming error, not a runtime condition to
    silently paper over, so it raises rather than returning defaults
    behind the caller's back.
    """
    if _config is None:
        raise RuntimeError(
            "config.get_config() called before config.start() has run. "
            "config must be the first critical service in the registry."
        )
    return _config


def _deep_copy_defaults() -> dict:
    return {
        "session": dict(DEFAULTS["session"]),
        "logging": dict(DEFAULTS["logging"]),
    }


def _merge_over_defaults(loaded: dict) -> dict:
    merged = _deep_copy_defaults()
    for section, values in loaded.items():
        if section not in merged:
            merged[section] = {}
        if isinstance(values, dict):
            merged[section].update(values)
        else:
            merged[section] = values
    return merged
