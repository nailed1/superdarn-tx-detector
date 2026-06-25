import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import monitor


class TestParseThreshold:
    def test_hours(self):
        assert monitor.parse_threshold("3h") == 180.0

    def test_hours_float(self):
        assert monitor.parse_threshold("1.5h") == 90.0

    def test_minutes_min(self):
        assert monitor.parse_threshold("30min") == 30.0

    def test_minutes_m(self):
        assert monitor.parse_threshold("45m") == 45.0

    def test_bare_number(self):
        assert monitor.parse_threshold("90") == 90.0

    def test_whitespace(self):
        assert monitor.parse_threshold("  3h  ") == 180.0

    def test_invalid(self):
        with pytest.raises(ValueError, match="Invalid threshold"):
            monitor.parse_threshold("abc")

    def test_empty(self):
        with pytest.raises(ValueError):
            monitor.parse_threshold("")


class TestParseTimestamp:
    def test_valid(self):
        assert monitor.parse_timestamp("20250115.1430.00.ekb.fitacf.bz2") == datetime(
            2025, 1, 15, 14, 30
        )

    def test_no_match(self):
        assert monitor.parse_timestamp("random_file.txt") is None

    def test_invalid_date(self):
        assert monitor.parse_timestamp("20251301.0000.foo") is None

    def test_minimal(self):
        assert monitor.parse_timestamp("20200101.0000") == datetime(2020, 1, 1, 0, 0)


class TestParseUtcOffset:
    def test_positive(self):
        assert monitor.parse_utc_offset("+5") == 5.0

    def test_negative(self):
        assert monitor.parse_utc_offset("-3") == -3.0

    def test_zero(self):
        assert monitor.parse_utc_offset("0") == 0.0

    def test_float(self):
        assert monitor.parse_utc_offset("5.5") == 5.5

    def test_invalid(self):
        with pytest.raises(ValueError, match="Invalid utc_offset"):
            monitor.parse_utc_offset("abc")


class TestFormatAge:
    def test_minutes(self):
        assert monitor.format_age(timedelta(minutes=42)) == "42 min ago"

    def test_hours_exact(self):
        assert monitor.format_age(timedelta(hours=3)) == "3h ago"

    def test_hours_and_minutes(self):
        assert monitor.format_age(timedelta(hours=2, minutes=15)) == "2h 15min ago"

    def test_zero(self):
        assert monitor.format_age(timedelta(0)) == "0 min ago"


class TestResolveTarget:
    def test_instance_name(self, tmp_path):
        conf = tmp_path / "ekb.conf"
        conf.write_text("[monitor]\n")
        instance, path = monitor.resolve_target("ekb", str(tmp_path))
        assert instance == "ekb"
        assert path == str(conf)

    def test_explicit_path(self, tmp_path):
        conf = tmp_path / "custom.conf"
        conf.write_text("[monitor]\n")
        instance, path = monitor.resolve_target(str(conf))
        assert instance == "custom"
        assert path == str(conf)

    def test_missing_path(self):
        with pytest.raises(FileNotFoundError):
            monitor.resolve_target("/no/such/file.conf")


class TestLoadConfig:
    def test_full(self, make_config, state_dir):
        path = make_config(
            {"directory": "/data", "mask": "*.fitacf.bz2", "threshold": "3h", "utc_offset": "+5"},
            {"max_alerts": "5", "recipient": "user@test.com"},
        )
        cfg = monitor.load_config(path, state_dir=str(state_dir))
        assert cfg["directory"] == "/data"
        assert cfg["mask"] == "*.fitacf.bz2"
        assert cfg["threshold_minutes"] == 180.0
        assert cfg["utc_offset_hours"] == 5.0
        assert cfg["max_alerts"] == 5
        assert cfg["recipient"] == "user@test.com"

    def test_defaults(self, make_config, state_dir):
        path = make_config(
            {"directory": "/data", "mask": "*.fitacf", "threshold": "1h"},
        )
        cfg = monitor.load_config(path, state_dir=str(state_dir))
        assert cfg["min_size"] == 15
        assert cfg["max_alerts"] == 3
        assert cfg["recipient"] == ""

    def test_missing_keys(self, make_config, state_dir):
        path = make_config({"directory": "/data"})
        with pytest.raises(ValueError, match="missing keys"):
            monitor.load_config(path, state_dir=str(state_dir))

    def test_missing_file(self, state_dir):
        with pytest.raises(FileNotFoundError):
            monitor.load_config("/no/such.conf", state_dir=str(state_dir))


class TestLoadSmtpConfig:
    def test_valid(self, make_smtp_config):
        config_dir = make_smtp_config()
        smtp = monitor.load_smtp_config(config_dir)
        assert smtp["host"] == "smtp.test.com"
        assert smtp["port"] == 465
        assert smtp["user"] == "bot@test.com"

    def test_missing_file(self, tmp_path):
        assert monitor.load_smtp_config(str(tmp_path)) is None


class TestScanDirectory:
    def test_sorted_by_timestamp(self, data_dir):
        (data_dir / "20250110.0800.00.ekb.fitacf.bz2").write_bytes(b"x" * 100)
        (data_dir / "20250110.1200.00.ekb.fitacf.bz2").write_bytes(b"x" * 100)
        (data_dir / "20250110.0600.00.ekb.fitacf.bz2").write_bytes(b"x" * 100)

        result = monitor.scan_directory(str(data_dir), "*.fitacf.bz2")
        assert len(result) == 3
        timestamps = [r[0] for r in result]
        assert timestamps == sorted(timestamps)

    def test_mask_filter(self, data_dir):
        (data_dir / "20250110.0800.00.ekb.fitacf.bz2").write_bytes(b"data")
        (data_dir / "20250110.0800.00.ekb.rawacf.bz2").write_bytes(b"data")

        result = monitor.scan_directory(str(data_dir), "*.fitacf.bz2")
        assert len(result) == 1

    def test_empty_dir(self, data_dir):
        assert monitor.scan_directory(str(data_dir), "*.fitacf.bz2") == []

    def test_missing_dir(self):
        with pytest.raises(FileNotFoundError):
            monitor.scan_directory("/no/such/dir", "*")


class TestStateRoundtrip:
    def test_save_and_load(self, tmp_path):
        path = str(tmp_path / "test.state")
        state = monitor.default_state()
        state["stale"]["active"] = True
        state["stale"]["alert_count"] = 2

        monitor.save_state(path, state)
        loaded = monitor.load_state(path)

        assert loaded["stale"]["active"] is True
        assert loaded["stale"]["alert_count"] == 2
        assert loaded["small_file"]["active"] is False

    def test_load_missing(self, tmp_path):
        state = monitor.load_state(str(tmp_path / "missing.state"))
        assert state == monitor.default_state()

    def test_atomic_write(self, tmp_path):
        path = str(tmp_path / "test.state")
        monitor.save_state(path, monitor.default_state())
        assert not os.path.exists(path + ".tmp")


class TestPauseFlag:
    def test_pause_resume(self, tmp_path):
        state_file = str(tmp_path / "inst.state")
        assert not monitor.is_paused(state_file)

        monitor.set_paused(state_file, True)
        assert monitor.is_paused(state_file)

        monitor.set_paused(state_file, False)
        assert not monitor.is_paused(state_file)

    def test_double_pause(self, tmp_path):
        state_file = str(tmp_path / "inst.state")
        monitor.set_paused(state_file, True)
        monitor.set_paused(state_file, True)
        assert monitor.is_paused(state_file)


class TestHandleIncident:
    def test_activate_and_alert(self):
        state = monitor.default_state()
        alerted = monitor.handle_incident(
            condition=True,
            incident_key="stale",
            message="test alert",
            state=state,
            max_alerts=3,
        )
        assert alerted is True
        assert state["stale"]["active"] is True
        assert state["stale"]["alert_count"] == 1

    def test_max_alerts_reached(self):
        state = monitor.default_state()
        state["stale"]["active"] = True
        state["stale"]["alert_count"] = 3
        alerted = monitor.handle_incident(
            condition=True,
            incident_key="stale",
            message="should not alert",
            state=state,
            max_alerts=3,
        )
        assert alerted is False
        assert state["stale"]["alert_count"] == 3

    def test_resolve(self):
        state = monitor.default_state()
        state["stale"]["active"] = True
        state["stale"]["alert_count"] = 2
        monitor.handle_incident(
            condition=False,
            incident_key="stale",
            message="",
            state=state,
            max_alerts=3,
        )
        assert state["stale"]["active"] is False
        assert state["stale"]["alert_count"] == 0

    def test_paused_no_alert(self):
        state = monitor.default_state()
        alerted = monitor.handle_incident(
            condition=True,
            incident_key="stale",
            message="paused",
            state=state,
            max_alerts=3,
            paused=True,
        )
        assert alerted is False
        assert state["stale"]["active"] is True


class TestRunMonitor:
    def _make_config(self, data_dir, state_file, threshold="3h"):
        return {
            "instance": "test",
            "directory": str(data_dir),
            "mask": "*.fitacf.bz2",
            "threshold": threshold,
            "threshold_minutes": monitor.parse_threshold(threshold),
            "utc_offset_hours": 0,
            "min_size": 15,
            "max_alerts": 3,
            "recipient": "",
            "state_file": state_file,
        }

    def test_no_files_triggers_stale(self, data_dir, state_dir):
        state_file = str(state_dir / "test.state")
        config = self._make_config(data_dir, state_file)
        state = monitor.default_state()

        alerted = monitor.run_monitor(config, state)
        assert alerted is True
        assert state["stale"]["active"] is True

    def test_fresh_file_no_alert(self, data_dir, state_dir):
        now = datetime.now()
        fname = now.strftime("%Y%m%d.%H%M.00.ekb.fitacf.bz2")
        (data_dir / fname).write_bytes(b"x" * 100)

        state_file = str(state_dir / "test.state")
        config = self._make_config(data_dir, state_file)
        state = monitor.default_state()

        with patch.object(monitor, "server_now", return_value=now):
            alerted = monitor.run_monitor(config, state)

        assert alerted is False

    def test_stale_file_alert(self, data_dir, state_dir):
        old_time = datetime(2025, 1, 1, 0, 0)
        (data_dir / "20250101.0000.00.ekb.fitacf.bz2").write_bytes(b"x" * 100)

        state_file = str(state_dir / "test.state")
        config = self._make_config(data_dir, state_file, threshold="1h")
        state = monitor.default_state()

        fake_now = old_time + timedelta(hours=5)
        with patch.object(monitor, "server_now", return_value=fake_now):
            alerted = monitor.run_monitor(config, state)

        assert alerted is True
        assert state["stale"]["active"] is True

    def test_small_file_alert(self, data_dir, state_dir):
        now = datetime.now()
        fname = now.strftime("%Y%m%d.%H%M.00.ekb.fitacf.bz2")
        (data_dir / fname).write_bytes(b"x")

        state_file = str(state_dir / "test.state")
        config = self._make_config(data_dir, state_file)
        state = monitor.default_state()

        with patch.object(monitor, "server_now", return_value=now):
            alerted = monitor.run_monitor(config, state)

        assert alerted is True
        assert state["small_file"]["active"] is True

    def test_recovery_clears_state(self, data_dir, state_dir):
        now = datetime.now()
        fname = now.strftime("%Y%m%d.%H%M.00.ekb.fitacf.bz2")
        (data_dir / fname).write_bytes(b"x" * 100)

        state_file = str(state_dir / "test.state")
        config = self._make_config(data_dir, state_file)
        state = monitor.default_state()
        state["stale"]["active"] = True
        state["stale"]["alert_count"] = 2

        with patch.object(monitor, "server_now", return_value=now):
            alerted = monitor.run_monitor(config, state)

        assert alerted is False
        assert state["stale"]["active"] is False
        assert state["stale"]["alert_count"] == 0


class TestMain:
    def test_missing_config(self):
        rc = monitor.main(["nonexistent_instance", "--config-dir", "/no/such/dir"])
        assert rc == 2
