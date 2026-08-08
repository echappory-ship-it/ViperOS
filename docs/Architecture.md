# ViperOS Architecture

## Summary

ViperOS boots as a normal Alpine Linux system (musl libc, busybox,
OpenRC) up through multi-user runlevel. The very last OpenRC service to
start hands control to a Python "session layer" — this is where ViperOS
actually begins, from the user's perspective. Everything below that layer
(kernel, busybox, OpenRC, core system services like networking) is
untouched stock Alpine. Everything above it is Python.

This keeps the risky, hard-to-get-right parts of an OS (init, device
bring-up, filesystem mounting) on infrastructure that already works, and
puts ViperOS's actual identity — the part users and admins interact with
— in Python, where it's easy to inspect, extend, and safely let users
customize.

```
 ┌─────────────────────────────────────────────┐
 │  Linux kernel (stock)                        │
 ├─────────────────────────────────────────────┤
 │  busybox + OpenRC (stock Alpine boot)        │
 │    - mounts filesystems                      │
 │    - brings up networking, syslog, etc.      │
 │    - starts standard runlevels               │
 ├─────────────────────────────────────────────┤
 │  openrc service: viperos-session  <-- last   │
 ├─────────────────────────────────────────────┤
 │  ViperOS Python layer                        │
 │    core/session.py   - entrypoint, sets up   │
 │                         core services        │
 │    core/registry.py  - critical service      │
 │                         registry             │
 │    core/modman.py    - non-critical,         │
 │                         user-replaceable      │
 │                         module manager        │
 │    modules/*         - actual functionality  │
 │                         (critical + optional) │
 │    cli/viper.py       - `viper` command,      │
 │                          user-facing CLI      │
 └─────────────────────────────────────────────┘
```

## Two classes of functionality

ViperOS draws a hard line between two kinds of Python code:

**Critical** — things the OS needs to keep functioning: the session
layer itself, the module manager, the registry, core CLI dispatch. These
live in `viperos/core/` and are NOT managed by modman. They're regular
source files. If a user wants to change them, that's a normal code
change/PR, not a runtime swap. Breaking these can break the OS.

**Non-critical** — everything else. Greeters, status displays, prompts,
notification formatting, optional services — anything where "this broke"
should mean "that one feature is degraded," never "the OS won't boot."
These are managed by `modman` (see `core/modman.py` and its own design
notes), which gives every such module version history and automatic
fallback to a known-good stock version if the active one fails.

The dividing line in practice: if `session.py` needs a piece of
functionality to finish booting or to keep other services alive, it's
critical. If it's something a user calls or that runs as a convenience
on top of an already-working system, it's a module.

## Boot sequence

1. Kernel boots, standard Alpine init (`/sbin/init` -> OpenRC) takes over.
2. OpenRC brings the system up through its normal runlevels
   (sysinit -> boot -> default), exactly as stock Alpine would.
3. As part of the `default` runlevel, the `viperos-session` OpenRC
   service starts. Its job is one line: exec into
   `python3 -m viperos.core.session`.
4. `session.py`:
   - Sets up logging.
   - Loads the critical service registry (`registry.py`) and starts
     each critical service in order.
   - Initializes `modman` and, per configuration, calls `modman.call()`
     for each non-critical module that should run at startup (e.g. a
     greeter, a status-bar service, etc.) — each wrapped in modman's
     fallback logic, so a broken user module never takes down session
     startup.
   - Hands off to the `viper` CLI / any long-running foreground service,
     depending on run mode (interactive shell vs daemon).

If `viperos-session` itself crashes, OpenRC's normal service supervision
takes over (respawn / fallback to a getty), the same as any other OpenRC
service. This is the main reason we don't run Python as PID 1 for now —
we get OpenRC's crash recovery for free instead of reimplementing it.

## Directory layout (in-repo)

```
viperos/
  core/
    session.py     - entrypoint, orchestrates startup
    registry.py     - critical service registry
    modman.py       - module manager (already built)
  modules/
    examples/        - example non-critical modules (installed into
                       modman's store at first boot / by installer)
  cli/
    viper.py         - `viper` command entrypoint
init/
  openrc/
    viperos-session  - OpenRC init script
docs/
  ARCHITECTURE.md    - this file
```

## Open questions / not yet decided

- Packaging: how does a built ViperOS image get from "Alpine + Python
  files" to a flashable/bootable artifact? (apk package? overlay on top
  of a stock Alpine image? Custom `mkimage`-style build script?)
- Config format for critical service registry and modman's startup list
  (leaning toward simple JSON/TOML, consistent with modman's existing
  `registry.json`).
- Update/rollback story at the OS level (modman handles per-module
  rollback already; OS-level rollback, e.g. of core/, is undecided).
