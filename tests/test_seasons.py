from datetime import date

from gitten.seasons import is_night_time, seasonal_accessory


def d(s):
    return date.fromisoformat(s)


# -- seasonal_accessory -------------------------------------------------------


def test_halloween():
    assert seasonal_accessory(d("2026-10-31")) == "halloween"


def test_yalda():
    assert seasonal_accessory(d("2026-12-21")) == "yalda"


def test_ordinary_day_with_no_birthday_set():
    assert seasonal_accessory(d("2026-03-14")) is None


def test_ordinary_day_with_birthday_set_but_not_today():
    assert seasonal_accessory(d("2026-03-14"), birthday=d("1990-05-17")) is None


def test_birthday_matches_month_and_day_regardless_of_birth_year():
    assert seasonal_accessory(d("2026-05-17"), birthday=d("1990-05-17")) == "birthday"


def test_halloween_takes_priority_over_a_birthday_on_the_same_day():
    assert seasonal_accessory(d("2026-10-31"), birthday=d("1990-10-31")) == "halloween"


def test_yalda_takes_priority_over_a_birthday_on_the_same_day():
    assert seasonal_accessory(d("2026-12-21"), birthday=d("1990-12-21")) == "yalda"


# -- is_night_time -------------------------------------------------------------


def test_night_hours():
    for hour in (23, 0, 1, 6):
        assert is_night_time(hour) is True


def test_day_hours():
    for hour in (7, 8, 12, 18, 22):
        assert is_night_time(hour) is False


def test_night_time_boundaries():
    assert is_night_time(22) is False
    assert is_night_time(23) is True
    assert is_night_time(6) is True
    assert is_night_time(7) is False
