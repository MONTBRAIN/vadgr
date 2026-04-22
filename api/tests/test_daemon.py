"""Tests for daemon management delegation to ``vadgr-cua`` CLI.

The Windows-side bridge daemon is owned by the published vadgr-computer-use
package. The setup service only wraps ``vadgr-cua doctor / install-daemon /
stop-daemon`` so the API can surface status and front-load first-launch
latency without duplicating the lifecycle logic.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

import api.services.computer_use_setup as cu_setup
from api.utils.platform import venv_bin_dir


def _create_fake_venv_with_cua(venv_path):
    bin_dir = venv_bin_dir(venv_path)
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "pip").touch()
    (bin_dir / "vadgr-cua").touch()


@pytest.fixture
def venv(tmp_path):
    v = tmp_path / ".cu_venv"
    _create_fake_venv_with_cua(v)
    with patch.object(cu_setup, "CU_VENV_DIR", v):
        yield v


class TestRunCua:
    def test_returns_none_when_binary_missing(self, tmp_path):
        with patch.object(cu_setup, "CU_VENV_DIR", tmp_path / "no_venv"):
            assert cu_setup._run_cua("doctor", timeout=5) is None

    def test_invokes_binary_with_args(self, venv):
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0, "stdout": "{}", "stderr": "",
            })()
            cu_setup._run_cua("doctor", timeout=5)
            cmd = run.call_args[0][0]
            assert cmd[0].endswith("vadgr-cua")
            assert cmd[1:] == ["doctor"]

    def test_returns_none_on_timeout(self, venv):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="vadgr-cua", timeout=5),
        ):
            assert cu_setup._run_cua("doctor", timeout=5) is None

    def test_returns_none_on_os_error(self, venv):
        with patch("subprocess.run", side_effect=OSError("nope")):
            assert cu_setup._run_cua("doctor", timeout=5) is None


class TestDoctorStatus:
    def test_running(self, venv):
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0,
                "stdout": json.dumps({"daemon_running": True, "port": 19542}),
                "stderr": "",
            })()
            assert cu_setup._doctor_status() == "running"

    def test_stopped(self, venv):
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0,
                "stdout": json.dumps({"daemon_running": False}),
                "stderr": "",
            })()
            assert cu_setup._doctor_status() == "stopped"

    def test_none_when_cli_not_installed(self, tmp_path):
        with patch.object(cu_setup, "CU_VENV_DIR", tmp_path / "none"):
            assert cu_setup._doctor_status() is None

    def test_none_when_doctor_exits_nonzero(self, venv):
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 1, "stdout": "", "stderr": "no python",
            })()
            assert cu_setup._doctor_status() is None

    def test_none_when_doctor_returns_junk(self, venv):
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0, "stdout": "not json", "stderr": "",
            })()
            assert cu_setup._doctor_status() is None


class TestInstallDaemon:
    def test_invokes_install_daemon_subcommand(self, venv):
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0, "stdout": "ok", "stderr": "",
            })()
            cu_setup._install_daemon()
            cmd = run.call_args[0][0]
            assert cmd[1] == "install-daemon"

    def test_tolerates_failure(self, venv):
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 1, "stdout": "", "stderr": "no python on host",
            })()
            cu_setup._install_daemon()

    def test_tolerates_missing_cli(self, tmp_path):
        with patch.object(cu_setup, "CU_VENV_DIR", tmp_path / "none"):
            cu_setup._install_daemon()


class TestStopDaemon:
    def test_invokes_stop_daemon_subcommand(self, venv):
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0, "stdout": "", "stderr": "",
            })()
            cu_setup._stop_daemon()
            cmd = run.call_args[0][0]
            assert cmd[1] == "stop-daemon"

    def test_tolerates_missing_cli(self, tmp_path):
        with patch.object(cu_setup, "CU_VENV_DIR", tmp_path / "none"):
            cu_setup._stop_daemon()
