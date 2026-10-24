"""Tiny stderr logger. stdout is reserved for actions, so *all* diagnostics go here.

Logging must never be able to crash the bot, so every write is guarded.
"""
from __future__ import annotations

import sys

# Set to False to silence routine messages (warnings/errors are always printed).
VERBOSE = False


def log(msg: str, *, always: bool = False) -> None:
    """Write one line to stderr. Routine messages only print when VERBOSE is on."""
    if not (VERBOSE or always):
        return
    try:
        sys.stderr.write(f"[bot] {msg}\n")
        sys.stderr.flush()
    except Exception:  # stderr closed or broken: nothing sensible left to do
        pass


def warn(msg: str) -> None:
    """Always-printed warning (malformed input, brain errors, timeouts)."""
    log(f"WARN {msg}", always=True)
