"""Thin wrapper around psutil that reads the raw system signals used by the
status badge feature. Kept separate from ``status_badge.py`` so that pure
logic module stays free of any real system I/O (and therefore trivially
testable) -- this module is the only thing that actually touches psutil.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import psutil


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
