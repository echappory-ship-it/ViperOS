#!/usr/bin/env python3
"""
modman - ViperOS Module Manager

Manages non-critical, user-replaceable scripts ("modules"). Users can swap
in their own version of any module; modman keeps every prior version so
nothing is ever lost, and the core OS always has a safe "stock" fallback
to use if a user-supplied version fails to load.

Layout on disk (ROOT_DIR below):

    <root>/
        registry.json
        modules/
            <module_name>/
                stock.py
                active.py
                versions/
                    v1_<timestamp>.py
                    v2_<timestamp>.py
                    ...

`active.py` is always what the rest of the OS imports. `registry.json`
just tracks metadata (which version is active, when things changed).
"""

import argparse
import importlib.util
import json
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Root of the modman data store. Override for testing via MODMAN_ROOT env var.
import os
ROOT_DIR = Path(os.environ.get("MODMAN_ROOT", "/var/viperos/modman"))
MODULES_DIR = ROOT_DIR / "modules"
REGISTRY_PATH = ROOT_DIR / "registry.json"


# --------------------------------------------------------------------------
# Registry helpers
# --------------------------------------------------------------------------

def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"modules": {}}
    with open(REGISTRY_PATH, "r") as f:
        return json.load(f)


def _save_registry(registry: dict) -> None:
    ROOT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = REGISTRY_PATH.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(registry, f, indent=2)
    tmp_path.replace(REGISTRY_PATH)


# --------------------------------------------------------------------------
# Public read-only API - safe for other ViperOS code (e.g. the CLI) to
# call directly, unlike the _load_registry/_save_registry helpers above,
# which are internal to modman's own read-modify-write operations.
# --------------------------------------------------------------------------

def list_modules() -> dict:
    """
    Return {module_name: active_version} for every module modman knows
    about. Read-only - callers should use the CLI subcommands (or the
    replace/activate functions below) to make changes, not edit the
    returned dict.
    """
    registry = _load_registry()
    modules = registry.get("modules", {})
    return {
        name: entry.get("active_version", "stock")
        for name, entry in modules.items()
    }


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _module_paths(name: str):
    mod_dir = MODULES_DIR / name
    return {
        "dir": mod_dir,
        "stock": mod_dir / "stock.py",
        "active": mod_dir / "active.py",
        "versions": mod_dir / "versions",
    }


def _module_exists(name: str) -> bool:
    return _module_paths(name)["dir"].exists()


def _ensure_module_registered(registry: dict, name: str) -> dict:
    modules = registry.setdefault("modules", {})
    if name not in modules:
        modules[name] = {"active_version": "stock", "history": []}
    return modules[name]


# --------------------------------------------------------------------------
# Core operations
# --------------------------------------------------------------------------

def cmd_init_module(name: str, stock_path: str) -> None:
    """Register a brand-new module from an initial stock script."""
    paths = _module_paths(name)
    if paths["dir"].exists():
        print(f"Module '{name}' already exists.")
        return

    src = Path(stock_path)
    if not src.exists():
        print(f"Error: source file '{stock_path}' does not exist.")
        sys.exit(1)

    paths["dir"].mkdir(parents=True)
    paths["versions"].mkdir()
    shutil.copyfile(src, paths["stock"])
    shutil.copyfile(src, paths["active"])

    registry = _load_registry()
    _ensure_module_registered(registry, name)
    _save_registry(registry)
    print(f"Initialized module '{name}' with stock script from '{stock_path}'.")


def cmd_replace(name: str, new_script_path: str, yes: bool = False) -> None:
    """Interactively replace a module's active script, archiving the old one."""
    if not _module_exists(name):
        print(f"Error: module '{name}' does not exist. Use 'init' first.")
        sys.exit(1)

    src = Path(new_script_path)
    if not src.exists():
        print(f"Error: source file '{new_script_path}' does not exist.")
        sys.exit(1)

    paths = _module_paths(name)
    registry = _load_registry()
    entry = _ensure_module_registered(registry, name)

    print(f"About to replace the active script for module '{name}'.")
    print(f"  Current active version: {entry['active_version']}")
    print(f"  New script source:      {new_script_path}")
    if not yes:
        confirm = input("Proceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    # Archive the current active version before overwriting it.
    ts = _timestamp()
    version_id = f"v{len(entry['history']) + 1}_{ts}"
    archived_path = paths["versions"] / f"{version_id}.py"
    if paths["active"].exists():
        shutil.copyfile(paths["active"], archived_path)
        entry["history"].append({
            "version": version_id,
            "archived_at": ts,
            "was_active_before_replacement": entry["active_version"],
        })

    # Install the new script as the new active version.
    new_version_id = f"v{len(entry['history']) + 1}_{ts}_user"
    new_version_path = paths["versions"] / f"{new_version_id}.py"
    shutil.copyfile(src, new_version_path)
    shutil.copyfile(src, paths["active"])

    entry["active_version"] = new_version_id
    _save_registry(registry)

    print(f"Replaced. New active version: {new_version_id}")
    print(f"Old version archived as:      {version_id if paths['active'].exists() else '(none, was empty)'}")


def cmd_list() -> None:
    modules = list_modules()
    if not modules:
        print("No modules registered yet.")
        return
    print(f"{'MODULE':<25} {'ACTIVE VERSION':<30}")
    for name, active_version in modules.items():
        print(f"{name:<25} {active_version:<30}")


def cmd_versions(name: str) -> None:
    if not _module_exists(name):
        print(f"Error: module '{name}' does not exist.")
        sys.exit(1)
    registry = _load_registry()
    entry = _ensure_module_registered(registry, name)
    active = entry["active_version"]

    print(f"Versions for module '{name}':")
    marker = " <- active" if active == "stock" else ""
    print(f"  stock{marker}")
    for h in entry["history"]:
        v = h["version"]
        marker = " <- active" if v == active else ""
        print(f"  {v}  (archived {h['archived_at']}){marker}")

    # Also list any raw versions on disk not yet in history (e.g. from replace's "new" copy)
    paths = _module_paths(name)
    known = {h["version"] for h in entry["history"]}
    known.add("stock")
    for f in sorted(paths["versions"].glob("*.py")):
        vid = f.stem
        if vid not in known:
            marker = " <- active" if vid == active else ""
            print(f"  {vid}{marker}")


def cmd_activate(name: str, version: str) -> None:
    if not _module_exists(name):
        print(f"Error: module '{name}' does not exist.")
        sys.exit(1)

    paths = _module_paths(name)
    if version == "stock":
        source = paths["stock"]
    else:
        source = paths["versions"] / f"{version}.py"

    if not source.exists():
        print(f"Error: version '{version}' not found for module '{name}'.")
        sys.exit(1)

    shutil.copyfile(source, paths["active"])
    registry = _load_registry()
    entry = _ensure_module_registered(registry, name)
    entry["active_version"] = version
    _save_registry(registry)
    print(f"Module '{name}' active version set to '{version}'.")


# --------------------------------------------------------------------------
# Runtime loading with automatic fallback (used by the rest of the OS)
# --------------------------------------------------------------------------

def load(name: str, log=print):
    """
    Import and return the given module by name, using its active version.
    If the active version fails to import or raises on import, automatically
    fall back to the stock version and record that the fallback happened.

    Returns the imported module object, or None if even stock fails.
    """
    if not _module_exists(name):
        log(f"[modman] module '{name}' is not registered; nothing to load.")
        return None

    paths = _module_paths(name)
    registry = _load_registry()
    entry = _ensure_module_registered(registry, name)

    def _import_from(path: Path, label: str):
        spec = importlib.util.spec_from_file_location(f"viperos_module_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    try:
        module = _import_from(paths["active"], "active")
        return module
    except Exception:
        log(f"[modman] module '{name}' (version={entry['active_version']}) "
            f"failed to load. Falling back to stock.")
        log(traceback.format_exc())

    try:
        module = _import_from(paths["stock"], "stock")
        log(f"[modman] module '{name}' loaded from stock as fallback.")
        return module
    except Exception:
        log(f"[modman] CRITICAL: stock version of module '{name}' also failed to load.")
        log(traceback.format_exc())
        return None


def call(name: str, func_name: str = "run", *args, log=print, **kwargs):
    """
    Load a module's active version and call one of its functions, with
    automatic fallback to stock if EITHER the import OR the function call
    itself raises. This is the entrypoint the rest of the OS should use
    instead of load() directly, whenever it wants "safe by default"
    behavior for a non-critical module.

    Returns (result, used_fallback: bool). If even stock fails, result is
    None and used_fallback is True.
    """
    if not _module_exists(name):
        log(f"[modman] module '{name}' is not registered; nothing to call.")
        return None, True

    paths = _module_paths(name)
    registry = _load_registry()
    entry = _ensure_module_registered(registry, name)

    def _import_from(path: Path):
        spec = importlib.util.spec_from_file_location(f"viperos_module_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _run(path: Path):
        module = _import_from(path)
        func = getattr(module, func_name)
        return func(*args, **kwargs)

    try:
        result = _run(paths["active"])
        return result, False
    except Exception:
        log(f"[modman] module '{name}' (version={entry['active_version']}) "
            f"failed during '{func_name}()'. Falling back to stock.")
        log(traceback.format_exc())

    try:
        result = _run(paths["stock"])
        log(f"[modman] module '{name}' ran from stock as fallback.")
        return result, True
    except Exception:
        log(f"[modman] CRITICAL: stock version of module '{name}' also failed during '{func_name}()'.")
        log(traceback.format_exc())
        return None, True


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="modman",
        description="ViperOS module manager for non-critical, user-replaceable scripts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Register a new module from a stock script.")
    p_init.add_argument("name")
    p_init.add_argument("stock_path")

    p_replace = sub.add_parser("replace", help="Replace a module's active script.")
    p_replace.add_argument("name")
    p_replace.add_argument("new_script_path")
    p_replace.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")

    sub.add_parser("list", help="List all registered modules and their active version.")

    p_versions = sub.add_parser("versions", help="List all saved versions of a module.")
    p_versions.add_argument("name")

    p_activate = sub.add_parser("activate", help="Set a module's active version.")
    p_activate.add_argument("name")
    p_activate.add_argument("version", help="Version id, or 'stock'.")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init_module(args.name, args.stock_path)
    elif args.command == "replace":
        cmd_replace(args.name, args.new_script_path, yes=args.yes)
    elif args.command == "list":
        cmd_list()
    elif args.command == "versions":
        cmd_versions(args.name)
    elif args.command == "activate":
        cmd_activate(args.name, args.version)


if __name__ == "__main__":
    main()
