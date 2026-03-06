"""Tests for the CLI entry point (__main__.py)."""

import logging
from unittest.mock import MagicMock, mock_open, patch

import pytest

from computer_use.__main__ import main

ENGINE_PATH = "computer_use.core.engine.ComputerUseEngine"


def _make_step_result(success, action_type_value, reasoning, error=None):
    action_type = MagicMock()
    action_type.value = action_type_value
    action_taken = MagicMock()
    action_taken.action_type = action_type
    step = MagicMock()
    step.success = success
    step.action_taken = action_taken
    step.reasoning = reasoning
    step.error = error
    return step


class TestInfoMode:
    def test_prints_platform_info_and_screen_size(self, capsys):
        mock_engine = MagicMock()
        mock_engine.get_platform_info.return_value = {
            "platform": "linux",
            "backend_available": True,
            "accessibility": {
                "api_name": "AT-SPI",
                "available": True,
            },
        }
        mock_engine.get_screen_size.return_value = (1920, 1080)

        with (
            patch("sys.argv", ["computer_use", "--info"]),
            patch(ENGINE_PATH, return_value=mock_engine) as mock_cls,
        ):
            main()

        mock_cls.assert_called_once_with(config_path=None)
        out = capsys.readouterr().out
        assert "Platform: linux" in out
        assert "Backend available: True" in out
        assert "AT-SPI" in out
        assert "1920x1080" in out

    def test_info_prints_accessibility_notes_when_present(self, capsys):
        mock_engine = MagicMock()
        mock_engine.get_platform_info.return_value = {
            "platform": "wsl2",
            "backend_available": True,
            "accessibility": {
                "api_name": "AT-SPI",
                "available": False,
                "notes": "requires dbus",
            },
        }
        mock_engine.get_screen_size.return_value = (2560, 1440)

        with (
            patch("sys.argv", ["computer_use", "--info"]),
            patch(ENGINE_PATH, return_value=mock_engine),
        ):
            main()

        out = capsys.readouterr().out
        assert "requires dbus" in out


class TestScreenshotMode:
    def test_saves_screenshot_bytes_to_file(self, capsys):
        mock_screen = MagicMock()
        mock_screen.image_bytes = b"\x89PNG_FAKE_DATA"
        mock_screen.width = 1920
        mock_screen.height = 1080

        mock_engine = MagicMock()
        mock_engine.screenshot.return_value = mock_screen

        m = mock_open()
        with (
            patch("sys.argv", ["computer_use", "--screenshot", "/tmp/shot.png"]),
            patch(ENGINE_PATH, return_value=mock_engine),
            patch("builtins.open", m),
        ):
            main()

        m.assert_called_once_with("/tmp/shot.png", "wb")
        m().write.assert_called_once_with(b"\x89PNG_FAKE_DATA")
        out = capsys.readouterr().out
        assert "1920x1080" in out
        assert "/tmp/shot.png" in out


class TestTaskMode:
    def test_runs_task_and_prints_step_results(self, capsys):
        step1 = _make_step_result(True, "click", "Clicked the button")
        step2 = _make_step_result(False, "type_text", "Typed into field", "timeout")

        mock_engine = MagicMock()
        mock_engine.get_platform.return_value = MagicMock(value="linux")
        mock_engine.run_task.return_value = [step1, step2]

        with (
            patch(
                "sys.argv",
                ["computer_use", "--provider", "openai", "Open a browser"],
            ),
            patch(ENGINE_PATH, return_value=mock_engine) as mock_cls,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

        mock_cls.assert_called_once_with(config_path=None, provider="openai")
        mock_engine.run_task.assert_called_once_with(
            task="Open a browser",
            max_steps=50,
            verify=True,
        )

        out = capsys.readouterr().out
        assert "Step 1: [OK] click" in out
        assert "Step 2: [FAILED] type_text" in out
        assert "Error: timeout" in out
        assert "1/2 steps succeeded" in out

    def test_all_steps_succeed_exits_zero(self):
        step = _make_step_result(True, "click", "Done")
        mock_engine = MagicMock()
        mock_engine.get_platform.return_value = MagicMock(value="linux")
        mock_engine.run_task.return_value = [step]

        with (
            patch("sys.argv", ["computer_use", "Do something"]),
            patch(ENGINE_PATH, return_value=mock_engine),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0

    def test_default_provider_is_anthropic(self):
        step = _make_step_result(True, "click", "ok")
        mock_engine = MagicMock()
        mock_engine.get_platform.return_value = MagicMock(value="linux")
        mock_engine.run_task.return_value = [step]

        with (
            patch("sys.argv", ["computer_use", "Do it"]),
            patch(ENGINE_PATH, return_value=mock_engine) as mock_cls,
        ):
            with pytest.raises(SystemExit):
                main()

        assert mock_cls.call_args.kwargs["provider"] == "anthropic"

    def test_no_verify_flag_passes_verify_false(self):
        step = _make_step_result(True, "click", "ok")
        mock_engine = MagicMock()
        mock_engine.get_platform.return_value = MagicMock(value="linux")
        mock_engine.run_task.return_value = [step]

        with (
            patch("sys.argv", ["computer_use", "--no-verify", "Do it"]),
            patch(ENGINE_PATH, return_value=mock_engine),
        ):
            with pytest.raises(SystemExit):
                main()

        mock_engine.run_task.assert_called_once_with(
            task="Do it",
            max_steps=50,
            verify=False,
        )

    def test_max_steps_arg_forwarded(self):
        step = _make_step_result(True, "click", "ok")
        mock_engine = MagicMock()
        mock_engine.get_platform.return_value = MagicMock(value="linux")
        mock_engine.run_task.return_value = [step]

        with (
            patch(
                "sys.argv",
                ["computer_use", "--max-steps", "10", "Do it"],
            ),
            patch(ENGINE_PATH, return_value=mock_engine),
        ):
            with pytest.raises(SystemExit):
                main()

        assert mock_engine.run_task.call_args.kwargs["max_steps"] == 10


class TestNoArgs:
    def test_no_args_causes_system_exit(self):
        with patch("sys.argv", ["computer_use"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0


class TestVerboseFlag:
    def test_verbose_sets_debug_logging(self):
        mock_engine = MagicMock()
        mock_engine.get_platform_info.return_value = {
            "platform": "linux",
            "backend_available": True,
            "accessibility": {"api_name": "AT-SPI", "available": True},
        }
        mock_engine.get_screen_size.return_value = (1920, 1080)

        with (
            patch("sys.argv", ["computer_use", "--verbose", "--info"]),
            patch(ENGINE_PATH, return_value=mock_engine),
            patch("computer_use.__main__.logging") as mock_logging,
        ):
            mock_logging.DEBUG = logging.DEBUG
            mock_logging.INFO = logging.INFO
            main()

        mock_logging.basicConfig.assert_called_once()
        assert mock_logging.basicConfig.call_args.kwargs["level"] == logging.DEBUG

    def test_without_verbose_sets_info_logging(self):
        mock_engine = MagicMock()
        mock_engine.get_platform_info.return_value = {
            "platform": "linux",
            "backend_available": True,
            "accessibility": {"api_name": "AT-SPI", "available": True},
        }
        mock_engine.get_screen_size.return_value = (1920, 1080)

        with (
            patch("sys.argv", ["computer_use", "--info"]),
            patch(ENGINE_PATH, return_value=mock_engine),
            patch("computer_use.__main__.logging") as mock_logging,
        ):
            mock_logging.DEBUG = logging.DEBUG
            mock_logging.INFO = logging.INFO
            main()

        mock_logging.basicConfig.assert_called_once()
        assert mock_logging.basicConfig.call_args.kwargs["level"] == logging.INFO
