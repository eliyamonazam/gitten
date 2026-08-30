from gitten.status_badge import Badge, StatusBadgeTracker


def make_tracker(**kwargs):
    return StatusBadgeTracker(**kwargs)


def test_no_badge_when_nothing_crosses_threshold():
    t = make_tracker()
    badge = t.update(battery_percent=80, plugged_in=False, cpu_percent=10, mem_percent=20, disk_percent=50)
    assert badge == Badge.NONE


def test_critical_battery_badge():
    t = make_tracker()
    badge = t.update(battery_percent=5, plugged_in=False, cpu_percent=10, mem_percent=10, disk_percent=10)
    assert badge == Badge.CRITICAL_BATTERY


def test_low_battery_badge():
    t = make_tracker()
    badge = t.update(battery_percent=15, plugged_in=False, cpu_percent=10, mem_percent=10, disk_percent=10)
    assert badge == Badge.LOW_BATTERY


def test_charging_badge():
    t = make_tracker()
    badge = t.update(battery_percent=50, plugged_in=True, cpu_percent=10, mem_percent=10, disk_percent=10)
    assert badge == Badge.CHARGING


def test_fully_charged_and_plugged_in_shows_no_badge():
    t = make_tracker()
    badge = t.update(battery_percent=100, plugged_in=True, cpu_percent=10, mem_percent=10, disk_percent=10)
    assert badge == Badge.NONE


def test_no_battery_present_never_shows_battery_badges():
    t = make_tracker()
    badge = t.update(battery_percent=None, plugged_in=False, cpu_percent=10, mem_percent=10, disk_percent=10)
    assert badge == Badge.NONE


def test_low_disk_badge():
    t = make_tracker()
    badge = t.update(battery_percent=80, plugged_in=True, cpu_percent=10, mem_percent=10, disk_percent=95)
    assert badge == Badge.LOW_DISK


def test_single_cpu_spike_does_not_trigger_high_resource():
    t = make_tracker(sample_window=10)
    for _ in range(9):
        t.update(battery_percent=80, plugged_in=False, cpu_percent=5, mem_percent=5, disk_percent=10)
    badge = t.update(battery_percent=80, plugged_in=False, cpu_percent=99, mem_percent=5, disk_percent=10)
    assert badge == Badge.NONE


def test_sustained_high_cpu_triggers_high_resource():
    t = make_tracker(sample_window=10)
    badge = Badge.NONE
    for _ in range(10):
        badge = t.update(battery_percent=80, plugged_in=True, cpu_percent=95, mem_percent=5, disk_percent=10)
    assert badge == Badge.HIGH_RESOURCE


def test_sustained_high_memory_triggers_high_resource():
    t = make_tracker(sample_window=10)
    badge = Badge.NONE
    for _ in range(10):
        badge = t.update(battery_percent=80, plugged_in=True, cpu_percent=5, mem_percent=95, disk_percent=10)
    assert badge == Badge.HIGH_RESOURCE


def test_priority_critical_battery_beats_everything():
    t = make_tracker(sample_window=10)
    for _ in range(10):
        badge = t.update(battery_percent=5, plugged_in=False, cpu_percent=99, mem_percent=99, disk_percent=99)
    assert badge == Badge.CRITICAL_BATTERY


def test_priority_low_disk_beats_high_resource_and_low_battery():
    t = make_tracker(sample_window=10)
    for _ in range(10):
        badge = t.update(battery_percent=15, plugged_in=False, cpu_percent=99, mem_percent=99, disk_percent=95)
    assert badge == Badge.LOW_DISK


def test_priority_high_resource_beats_charging_and_low_battery():
    t = make_tracker(sample_window=10)
    for _ in range(10):
        badge = t.update(battery_percent=15, plugged_in=True, cpu_percent=99, mem_percent=99, disk_percent=10)
    assert badge == Badge.HIGH_RESOURCE


def test_priority_charging_beats_low_battery():
    # plugged_in with a low percent satisfies both "charging" and would-be
    # "low battery" (were it unplugged) -- charging must win.
    t = make_tracker(sample_window=10)
    badge = t.update(battery_percent=15, plugged_in=True, cpu_percent=5, mem_percent=5, disk_percent=10)
    assert badge == Badge.CHARGING
