"""Thin wrapper around psutil that reads the raw system signals used by the
status badge feature. Kept separate from ``status_badge.py`` so that pure
logic module stays free of any real system I/O (and therefore trivially
testable) -- this module is the only thing that actually touches psutil.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import psutil

from gitten.focus import matches_focus_process


@dataclass
class SystemSample:
    battery_percent: float | None
    plugged_in: bool
    cpu_percent: float
    mem_percent: float
    disk_percent: float


def _system_drive() -> str:
    return os.environ.get("SystemDrive", "C:") + "\\"


def sample_system() -> SystemSample:
    battery = psutil.sensors_battery()
    return SystemSample(
        battery_percent=battery.percent if battery is not None else None,
        plugged_in=bool(battery.power_plugged) if battery is not None else False,
        cpu_percent=psutil.cpu_percent(interval=None),
        mem_percent=psutil.virtual_memory().percent,
        disk_percent=psutil.disk_usage(_system_drive()).percent,
    )


def is_focus_process_running(substrings: list[str] | None = None) -> bool:
    """Whether any currently running process's command line matches one of
    the watched dev-tool substrings (default: pytest/npm test/etc, or a
    user-supplied list -- see ``focus.load_focus_substrings``).

    Gitten only *observes* these processes rather than launching them
    itself, so this can only ever answer "is a matching run currently in
    progress", never whether it passed or failed -- that would require
    Gitten to wrap and launch the command itself, which is out of scope
    here. Each process is checked defensively: one that disappears or
    denies access mid-scan is skipped rather than aborting the whole sweep.
    """
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = proc.info["cmdline"] or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if matches_focus_process(" ".join(cmdline), substrings):
            return True
    return False
