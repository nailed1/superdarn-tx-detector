import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "scripts"))


@pytest.fixture
def make_config(tmp_path):
    def _make(monitor_opts, alerts_opts=None, filename="test_instance.conf"):
        conf = tmp_path / filename
        lines = ["[monitor]\n"]
        for k, v in monitor_opts.items():
            lines.append(f"{k} = {v}\n")
        if alerts_opts:
            lines.append("[alerts]\n")
            for k, v in alerts_opts.items():
                lines.append(f"{k} = {v}\n")
        conf.write_text("".join(lines))
        return str(conf)

    return _make


@pytest.fixture
def make_smtp_config(tmp_path):
    def _make(opts=None):
        opts = opts or {
            "host": "smtp.test.com",
            "port": "465",
            "user": "bot@test.com",
            "password": "secret",
            "sender": "bot@test.com",
        }
        conf = tmp_path / "smtp.conf"
        lines = ["[smtp]\n"]
        for k, v in opts.items():
            lines.append(f"{k} = {v}\n")
        conf.write_text("".join(lines))
        return str(tmp_path)

    return _make


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def state_dir(tmp_path):
    d = tmp_path / "state"
    d.mkdir()
    return d
