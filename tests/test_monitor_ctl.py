import pytest

import monitor
import monitor_ctl


class TestParseOperatorArgs:
    def test_symlink_pause(self):
        cmd, rest = monitor_ctl.parse_operator_args(["monitor-pause", "ekb"])
        assert cmd == "pause"
        assert rest == ["ekb"]

    def test_symlink_status(self):
        cmd, rest = monitor_ctl.parse_operator_args(["monitor-status", "ekb"])
        assert cmd == "status"
        assert rest == ["ekb"]

    def test_no_prefix(self):
        cmd, rest = monitor_ctl.parse_operator_args(["monitor_ctl.py", "status", "ekb"])
        assert cmd is None
        assert rest == ["monitor_ctl.py", "status", "ekb"]

    def test_empty(self):
        cmd, rest = monitor_ctl.parse_operator_args([])
        assert cmd is None


class TestColorStatus:
    def test_active_no_tty(self):
        assert monitor_ctl.color_status("ACTIVE") == "ACTIVE"

    def test_alert_no_tty(self):
        assert monitor_ctl.color_status("ALERT") == "ALERT"


class TestCmdPause:
    def test_pause(self, tmp_path):
        state_file = str(tmp_path / "inst.state")
        config = {"state_file": state_file}

        rc = monitor_ctl.cmd_pause("inst", config)
        assert rc == 0
        assert monitor.is_paused(state_file)

    def test_already_paused(self, tmp_path):
        state_file = str(tmp_path / "inst.state")
        config = {"state_file": state_file}
        monitor.set_paused(state_file, True)

        rc = monitor_ctl.cmd_pause("inst", config)
        assert rc == 0


class TestCmdResume:
    def test_resume(self, tmp_path):
        state_file = str(tmp_path / "inst.state")
        config = {"state_file": state_file}
        monitor.set_paused(state_file, True)

        rc = monitor_ctl.cmd_resume("inst", config)
        assert rc == 0
        assert not monitor.is_paused(state_file)

    def test_already_active(self, tmp_path):
        state_file = str(tmp_path / "inst.state")
        config = {"state_file": state_file}

        rc = monitor_ctl.cmd_resume("inst", config)
        assert rc == 0


class TestCmdStatus:
    def test_status_active(self, data_dir, state_dir, make_config, capsys):
        from datetime import datetime
        from unittest.mock import patch

        now = datetime.now()
        fname = now.strftime("%Y%m%d.%H%M.00.ekb.fitacf.bz2")
        (data_dir / fname).write_bytes(b"x" * 100)

        path = make_config(
            {"directory": str(data_dir), "mask": "*.fitacf.bz2", "threshold": "3h"},
        )
        config = monitor.load_config(path, state_dir=str(state_dir))

        with patch.object(monitor, "server_now", return_value=now):
            rc = monitor_ctl.cmd_status(config["instance"], config)

        assert rc == 0
        out = capsys.readouterr().out
        assert "ACTIVE" in out

    def test_status_no_files(self, data_dir, state_dir, make_config, capsys):
        path = make_config(
            {"directory": str(data_dir), "mask": "*.fitacf.bz2", "threshold": "1h"},
        )
        config = monitor.load_config(path, state_dir=str(state_dir))
        rc = monitor_ctl.cmd_status(config["instance"], config)

        assert rc == 0
        out = capsys.readouterr().out
        assert "ALERT" in out
        assert "(none)" in out


class TestCmdTest:
    def test_no_smtp(self, tmp_path):
        config = {"recipient": "", "state_file": str(tmp_path / "t.state")}
        rc = monitor_ctl.cmd_test("inst", config, smtp_config=None)
        assert rc == 1
