"""Pure logic for the system-status badge overlay. No Qt imports -- easy to
unit test, following the exact same pattern as ``mood.py``.

This is intentionally a SEPARATE, independent signal from the git-driven
``mood.py`` state machine: the badge is a small icon layered on top of
whatever mood is currently showing, not a replacement for it. All inputs
(battery percentage, plugged-in flag, cpu/mem/disk readings) are passed in
by the caller on each ``update()`` -- nothing here reads the system itself.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class Badge(Enum):
    NONE = "none"
    CRITICAL_BATTERY = "critical_battery"
    LOW_DISK = "low_disk"
    HIGH_RESOURCE = "high_resource"
    CHARGING = "charging"
    LOW_BATTERY = "low_battery"


DEFAULT_SAMPLE_WINDOW = 10
DEFAULT_RESOURCE_THRESHOLD_PERCENT = 85.0
DEFAULT_LOW_BATTERY_PERCENT = 20.0
DEFAULT_CRITICAL_BATTERY_PERCENT = 10.0
DEFAULT_LOW_DISK_PERCENT = 90.0

# Priority order when several conditions are true at once (highest first).
_PRIORITY = (
    Badge.CRITICAL_BATTERY,
    Badge.LOW_DISK,
    Badge.HIGH_RESOURCE,
    Badge.CHARGING,
    Badge.LOW_BATTERY,
)


@dataclass
class StatusBadgeTracker:
    """Tracks which status badge (if any) should be shown, from periodic
    system samples fed in by the caller via ``update()``.

    CPU and memory readings are smoothed over a rolling window so a single
    spike doesn't trigger the "high resource usage" badge -- only sustained
    load does.
    """

    sample_window: int = DEFAULT_SAMPLE_WINDOW
    resource_threshold_percent: float = DEFAULT_RESOURCE_THRESHOLD_PERCENT
    low_battery_percent: float = DEFAULT_LOW_BATTERY_PERCENT
    critical_battery_percent: float = DEFAULT_CRITICAL_BATTERY_PERCENT
    low_disk_percent: float = DEFAULT_LOW_DISK_PERCENT

    badge: Badge = Badge.NONE
    _cpu_samples: deque = field(default_factory=deque, init=False, repr=False)
    _mem_samples: deque = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        self._cpu_samples = deque(maxlen=self.sample_window)
        self._mem_samples = deque(maxlen=self.sample_window)

    def update(
        self,
        battery_percent: float | None,
        plugged_in: bool,
        cpu_percent: float,
        mem_percent: float,
        disk_percent: float,
    ) -> Badge:
        """Feed in the latest system sample and get back the badge to show."""
        self._cpu_samples.append(cpu_percent)
        self._mem_samples.append(mem_percent)

        avg_cpu = sum(self._cpu_samples) / len(self._cpu_samples)
        avg_mem = sum(self._mem_samples) / len(self._mem_samples)

        has_battery = battery_percent is not None
        conditions = {
            Badge.CRITICAL_BATTERY: (
                has_battery
                and not plugged_in
                and battery_percent < self.critical_battery_percent
            ),
            Badge.LOW_DISK: disk_percent > self.low_disk_percent,
            Badge.HIGH_RESOURCE: (
                avg_cpu > self.resource_threshold_percent
                or avg_mem > self.resource_threshold_percent
            ),
            Badge.CHARGING: has_battery and plugged_in and battery_percent < 100,
            Badge.LOW_BATTERY: (
                has_battery
                and not plugged_in
                and battery_percent < self.low_battery_percent
            ),
        }

        self.badge = next((b for b in _PRIORITY if conditions[b]), Badge.NONE)
        return self.badge
