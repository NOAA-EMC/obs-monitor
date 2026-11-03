"""Tests for obs_monitor.io.timewindow."""

from datetime import datetime, timezone, timedelta
import pytest
from obs_monitor.io.timewindow import CycleError, cycle_range, format_cycle, parse_cycle, trailing_window


class TestParseCycle:

    @pytest.mark.parametrize("value", ["2026093018", 2026093018, "202609301800", " 2026093018 "])
    def test_formats(self, value):
        assert parse_cycle(value) == datetime(2026, 9, 30, 18)

    def test_datetime_passthrough_and_tz(self):
        assert parse_cycle(datetime(2026, 9, 30, 18)) == datetime(2026, 9, 30, 18)
        est = timezone(timedelta(hours=-4))
        assert parse_cycle(datetime(2026, 9, 30, 14, tzinfo=est)) == datetime(2026, 9, 30, 18)

    @pytest.mark.parametrize("bad", ["20260930", "2026093018Z", "2026133018", "2026093025", ""])
    def test_bad(self, bad):
        with pytest.raises(CycleError):
            parse_cycle(bad)

    def test_format_roundtrip(self):
        assert format_cycle(parse_cycle("2026100100")) == "2026100100"


class TestCycleRange:

    def test_inclusive(self):
        cyc = cycle_range("2026093000", "2026100100", 6)
        assert [format_cycle(c) for c in cyc] == ["2026093000", "2026093006", "2026093012", "2026093018", "2026100100"]

    def test_single_cycle(self):
        assert cycle_range("2026093018", "2026093018") == [datetime(2026, 9, 30, 18)]

    def test_end_before_start(self):
        with pytest.raises(CycleError, match="before start"):
            cycle_range("2026100100", "2026093000")

    def test_misaligned_end(self):
        with pytest.raises(CycleError, match="whole number"):
            cycle_range("2026093000", "2026093017", 6)

    @pytest.mark.parametrize("interval", [0, -6, 1.5, True])
    def test_bad_interval(self, interval):
        with pytest.raises(CycleError, match="interval_hours"):
            cycle_range("2026093000", "2026093018", interval)


class TestTrailingWindow:

    def test_window(self):
        cyc = trailing_window("2026100100", 4, 6)
        assert [format_cycle(c) for c in cyc] == ["2026093006", "2026093012", "2026093018", "2026100100"]

    def test_matches_range(self):
        assert trailing_window("2026100100", 5, 6) == cycle_range("2026093000", "2026100100", 6)

    @pytest.mark.parametrize("n", [0, -1, 2.0])
    def test_bad_n(self, n):
        with pytest.raises(CycleError, match="n_cycles"):
            trailing_window("2026100100", n)
