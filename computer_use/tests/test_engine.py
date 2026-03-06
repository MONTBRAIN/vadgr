"""Tests for the ComputerUseEngine with mocked backends."""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from computer_use.core.engine import (
    ComputerUseEngine,
    _CacheContext,
    _LAYER2_MIN_CONFIDENCE,
    _PCT_BUCKET,
    _PASSTHROUGH_APPS,
    _default_cache_path,
)
from computer_use.core.errors import ConfigError, PlatformNotSupportedError
from computer_use.core.spatial_cache import CacheEntry, MIN_NAV_HIT_COUNT
from computer_use.core.types import (
    Action,
    ActionType,
    Element,
    ForegroundWindow,
    Platform,
    Region,
    ScreenState,
)


@pytest.fixture
def mock_backend():
    """Create a fully mocked platform backend."""
    backend = MagicMock()
    backend.is_available.return_value = True
    backend.get_accessibility_info.return_value = {
        "available": True,
        "api_name": "Mock",
        "notes": "",
    }

    capture = MagicMock()
    capture.capture_full.return_value = ScreenState(
        image_bytes=b"\x89PNG_MOCK",
        width=1920,
        height=1080,
    )
    capture.capture_region.return_value = ScreenState(
        image_bytes=b"\x89PNG_REGION",
        width=200,
        height=100,
    )
    capture.get_screen_size.return_value = (1920, 1080)
    capture.get_scale_factor.return_value = 1.0

    executor = MagicMock()

    backend.get_screen_capture.return_value = capture
    backend.get_action_executor.return_value = executor

    return backend, capture, executor


# ---------------------------------------------------------------------------
# TestDefaultCachePath -- _default_cache_path() coverage
# ---------------------------------------------------------------------------

class TestDefaultCachePath:
    """Covers lines 84-94: env var, Windows, XDG_DATA_HOME, default."""

    @patch("computer_use.core.engine.os.makedirs")
    @patch.dict("os.environ", {"AGENT_FORGE_DATA": "/custom/data"}, clear=False)
    def test_agent_forge_data_env(self, mock_makedirs):
        result = _default_cache_path()
        assert result.startswith("/custom/data")
        assert result.endswith("muscle_memory.db")
        mock_makedirs.assert_called_once_with("/custom/data", exist_ok=True)

    @patch("computer_use.core.engine.os.makedirs")
    @patch("computer_use.core.engine.os.name", "nt")
    @patch.dict("os.environ", {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}, clear=False)
    def test_windows_uses_appdata(self, mock_makedirs):
        # Remove AGENT_FORGE_DATA so it does not short-circuit
        with patch.dict("os.environ", {}, clear=False):
            if "AGENT_FORGE_DATA" in __import__("os").environ:
                del __import__("os").environ["AGENT_FORGE_DATA"]
            result = _default_cache_path()
        assert "AgentForge" in result
        assert result.endswith("muscle_memory.db")

    @patch("computer_use.core.engine.os.makedirs")
    @patch("computer_use.core.engine.os.name", "posix")
    @patch.dict(
        "os.environ",
        {"XDG_DATA_HOME": "/home/user/.data"},
        clear=False,
    )
    def test_xdg_data_home(self, mock_makedirs):
        with patch.dict("os.environ", {}, clear=False):
            if "AGENT_FORGE_DATA" in __import__("os").environ:
                del __import__("os").environ["AGENT_FORGE_DATA"]
            result = _default_cache_path()
        assert "agent-forge" in result
        assert result.endswith("muscle_memory.db")

    @patch("computer_use.core.engine.os.makedirs")
    @patch("computer_use.core.engine.os.name", "posix")
    @patch("computer_use.core.engine.os.path.expanduser", return_value="/home/testuser")
    def test_default_local_share(self, mock_expand, mock_makedirs):
        with patch.dict("os.environ", {}, clear=False):
            for key in ("AGENT_FORGE_DATA", "XDG_DATA_HOME"):
                __import__("os").environ.pop(key, None)
            result = _default_cache_path()
        assert ".local" in result
        assert "share" in result
        assert "agent-forge" in result
        assert result.endswith("muscle_memory.db")


# ---------------------------------------------------------------------------
# TestEngineInit -- __init__ and config loading coverage
# ---------------------------------------------------------------------------

class TestEngineInit:
    """Covers line 122, config loading paths, PlatformNotSupportedError."""

    def test_backend_not_available_raises(self, mock_backend):
        backend, _, _ = mock_backend
        backend.is_available.return_value = False
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.LINUX),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            with pytest.raises(PlatformNotSupportedError, match="not available"):
                ComputerUseEngine()

    def test_config_from_yaml_file(self, mock_backend):
        backend, _, _ = mock_backend
        yaml_content = "provider: anthropic\nfoo: bar\n"
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
            patch("builtins.open", mock_open(read_data=yaml_content)),
            patch("computer_use.core.engine.yaml.safe_load", return_value={"provider": "anthropic", "foo": "bar"}),
        ):
            engine = ComputerUseEngine(config_path="/fake/config.yaml")
        assert engine._config == {"provider": "anthropic", "foo": "bar"}
        assert engine._provider_name == "anthropic"

    def test_config_yaml_load_error_raises(self, mock_backend):
        backend, _, _ = mock_backend
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
            patch("builtins.open", side_effect=IOError("no such file")),
        ):
            with pytest.raises(ConfigError, match="Cannot load config"):
                ComputerUseEngine(config_path="/bad/path.yaml")

    def test_config_default_missing_returns_empty(self, mock_backend):
        backend, _, _ = mock_backend
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
            patch("computer_use.core.engine.os.path.exists", return_value=False),
            patch("computer_use.core.engine.yaml"),
        ):
            engine = ComputerUseEngine()
        assert engine._config == {}

    def test_provider_passed_in_constructor(self, mock_backend):
        backend, _, _ = mock_backend
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
            patch("computer_use.core.engine.yaml"),
        ):
            engine = ComputerUseEngine(provider="openai")
        assert engine._provider_name == "openai"


# ---------------------------------------------------------------------------
# TestEngine -- basic engine API
# ---------------------------------------------------------------------------

class TestEngine:
    def _make_engine(self, mock_backend):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = None
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def test_screenshot(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        screen = engine.screenshot()
        assert screen.width == 1920
        assert screen.height == 1080
        capture.capture_full.assert_called_once()

    def test_screenshot_stores_offset(self, mock_backend):
        """screenshot() records virtual screen offset for coordinate translation."""
        backend, capture, executor = mock_backend
        capture.capture_full.return_value = ScreenState(
            image_bytes=b"\x89PNG", width=1920, height=1080,
            offset_x=100, offset_y=50,
        )
        backend.get_foreground_window.return_value = None
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        engine.screenshot()
        assert engine._vs_offset_x == 100
        assert engine._vs_offset_y == 50

    def test_screenshot_region(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        screen = engine.screenshot_region(10, 20, 200, 100)
        assert screen.width == 200
        capture.capture_region.assert_called_once()

    def test_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.click(500, 300)
        executor.click.assert_called_once_with(500, 300, hit_count=0)

    def test_double_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.double_click(100, 200)
        executor.double_click.assert_called_once_with(100, 200, hit_count=0)

    def test_right_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.right_click(100, 200)
        executor.click.assert_called_once_with(100, 200, button="right", hit_count=0)

    def test_type_text(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.type_text("hello")
        executor.type_text.assert_called_once_with("hello")

    def test_key_press(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.key_press("ctrl", "c")
        executor.key_press.assert_called_once_with(["ctrl", "c"])

    def test_scroll(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.scroll(100, 200, -3)
        executor.scroll.assert_called_once_with(100, 200, -3)

    def test_drag(self, mock_backend):
        """Covers lines 345-347: drag translates coords and delegates."""
        engine, _, executor = self._make_engine(mock_backend)
        engine.drag(10, 20, 300, 400, duration=0.3)
        executor.drag.assert_called_once_with(10, 20, 300, 400, 0.3)

    def test_drag_with_offset(self, mock_backend):
        """drag() applies virtual screen offset to both start and end."""
        backend, capture, executor = mock_backend
        capture.capture_full.return_value = ScreenState(
            image_bytes=b"\x89PNG", width=1920, height=1080,
            offset_x=100, offset_y=50,
        )
        backend.get_foreground_window.return_value = None
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        engine.screenshot()
        engine.drag(10, 20, 300, 400)
        executor.drag.assert_called_once_with(110, 70, 400, 450, 0.5)

    def test_move_mouse(self, mock_backend):
        """move_mouse delegates to executor with hit_count from cache."""
        engine, _, executor = self._make_engine(mock_backend)
        engine.move_mouse(200, 300)
        executor.move_mouse.assert_called_once_with(200, 300, hit_count=0)

    def test_get_platform(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        assert engine.get_platform() == Platform.WSL2

    def test_get_screen_size(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        assert engine.get_screen_size() == (1920, 1080)

    def test_get_platform_info(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        info = engine.get_platform_info()
        assert info["platform"] == "wsl2"
        assert info["backend_available"] is True

    def test_execute_action(self, mock_backend):
        """Covers line 679: execute_action delegates to executor."""
        engine, _, executor = self._make_engine(mock_backend)
        action = Action(action_type=ActionType.CLICK, x=100, y=200)
        engine.execute_action(action)
        executor.execute_action.assert_called_once_with(action)

    def test_run_task_without_provider_raises(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        with pytest.raises(Exception):
            engine.run_task("Open Notepad")


# ---------------------------------------------------------------------------
# TestGetProvider -- _get_provider / _get_locator coverage
# ---------------------------------------------------------------------------

class TestProviderAndLocator:
    """Covers lines 757, 764, 777-779, 687-699."""

    def _make_engine(self, mock_backend, provider=None):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = None
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine(provider=provider)
        return engine, capture, executor

    def test_get_provider_no_name_raises(self, mock_backend):
        """No provider configured raises ConfigError (line 757)."""
        engine, _, _ = self._make_engine(mock_backend)
        # Force provider_name to None (yaml mock may set it to a MagicMock)
        engine._provider_name = None
        with pytest.raises(ConfigError, match="No LLM provider"):
            engine._get_provider()

    def test_get_provider_loads_from_registry(self, mock_backend):
        """Provider is lazy-loaded via get_provider registry (line 764)."""
        engine, _, _ = self._make_engine(mock_backend, provider="anthropic")
        mock_prov = MagicMock()
        with patch(
            "computer_use.providers.registry.get_provider",
            return_value=mock_prov,
        ):
            result = engine._get_provider()
        assert result is mock_prov
        # Second call returns cached instance
        assert engine._get_provider() is mock_prov

    def test_get_locator_import_error_returns_none(self, mock_backend):
        """Grounding import failure returns None (lines 777-779)."""
        engine, _, _ = self._make_engine(mock_backend)
        engine._locator = None
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def fake_import(name, *args, **kwargs):
            if "hybrid" in name:
                raise ImportError("no grounding")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = engine._get_locator()
        assert result is None

    def test_find_element_no_locator_returns_none(self, mock_backend):
        """find_element returns None when no locator available (lines 687-689)."""
        engine, _, _ = self._make_engine(mock_backend)
        engine._get_locator = lambda: None
        result = engine.find_element("Save button")
        assert result is None

    def test_find_element_delegates_to_locator(self, mock_backend):
        """find_element uses locator.find_element with screenshot (lines 690-691)."""
        engine, capture, _ = self._make_engine(mock_backend)
        locator = MagicMock()
        expected = Element(
            name="Save", role="Button",
            region=Region(10, 20, 80, 30),
            confidence=0.9, source="accessibility",
        )
        locator.find_element.return_value = expected
        engine._get_locator = lambda: locator
        result = engine.find_element("Save button")
        assert result is expected
        locator.find_element.assert_called_once()

    def test_find_all_elements_no_locator_returns_empty(self, mock_backend):
        """find_all_elements returns [] when no locator (lines 695-697)."""
        engine, _, _ = self._make_engine(mock_backend)
        engine._get_locator = lambda: None
        result = engine.find_all_elements()
        assert result == []

    def test_find_all_elements_delegates_to_locator(self, mock_backend):
        """find_all_elements uses locator (lines 698-699)."""
        engine, capture, _ = self._make_engine(mock_backend)
        locator = MagicMock()
        locator.find_all_elements.return_value = [
            Element(name="OK", role="Button", region=Region(0, 0, 50, 20),
                    confidence=1.0, source="accessibility"),
        ]
        engine._get_locator = lambda: locator
        result = engine.find_all_elements()
        assert len(result) == 1
        locator.find_all_elements.assert_called_once()

    def test_click_element(self, mock_backend):
        """click_element clicks center of element region (lines 703-704)."""
        engine, _, executor = self._make_engine(mock_backend)
        el = Element(
            name="OK", role="Button",
            region=Region(100, 200, 80, 40),
            confidence=1.0, source="accessibility",
        )
        engine.click_element(el)
        # center = (100 + 40, 200 + 20) = (140, 220)
        executor.click.assert_called_once_with(140, 220, hit_count=0)


# ---------------------------------------------------------------------------
# TestRunTask -- run_task coverage
# ---------------------------------------------------------------------------

class TestRunTask:
    """Covers lines 737-740: run_task imports and calls run_core_loop."""

    def _make_engine(self, mock_backend):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = None
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine(provider="anthropic")
        return engine, capture, executor

    def test_run_task_calls_core_loop(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        mock_provider = MagicMock()
        engine._provider = mock_provider
        engine._locator = MagicMock()

        with patch("computer_use.core.loop.run_core_loop", return_value=[]) as mock_loop:
            results = engine.run_task("Open Notepad", max_steps=10, verify=False)
        assert results == []
        mock_loop.assert_called_once()
        call_kwargs = mock_loop.call_args[1]
        assert call_kwargs["task"] == "Open Notepad"
        assert call_kwargs["max_steps"] == 10
        assert call_kwargs["verify"] is False


# ---------------------------------------------------------------------------
# TestConfigLoading -- _load_config coverage
# ---------------------------------------------------------------------------

class TestConfigLoading:
    """Covers lines 791, 795-796: default path missing, YAML load error."""

    def test_load_config_default_exists(self, mock_backend):
        backend, _, _ = mock_backend
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
            patch("computer_use.core.engine.os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="key: val\n")),
            patch("computer_use.core.engine.yaml.safe_load", return_value={"key": "val"}),
        ):
            engine = ComputerUseEngine()
        assert engine._config == {"key": "val"}

    def test_load_config_yaml_returns_none(self, mock_backend):
        """yaml.safe_load returning None should give empty dict (line 794)."""
        backend, _, _ = mock_backend
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
            patch("builtins.open", mock_open(read_data="")),
            patch("computer_use.core.engine.yaml.safe_load", return_value=None),
        ):
            engine = ComputerUseEngine(config_path="/some/config.yaml")
        assert engine._config == {}


# ---------------------------------------------------------------------------
# TestMuscleMemoryIntegration
# ---------------------------------------------------------------------------

class TestMuscleMemoryIntegration:
    """Tests that the engine's muscle memory cache integrates correctly."""

    def _make_engine(self, mock_backend, fg_window=None):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = fg_window
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def test_click_without_hint_auto_learns_layer1(self, mock_backend):
        """No element_hint => Layer 1 synthetic hint => still learns."""
        engine, _, executor = self._make_engine(mock_backend)
        # First click: cache miss, hit_count=0
        engine.click(100, 200)
        executor.click.assert_called_once_with(100, 200, hit_count=0)

        # Second click at same coords: cache hit from Layer 1
        executor.reset_mock()
        engine.click(100, 200)
        executor.click.assert_called_once_with(100, 200, hit_count=1)

    def test_click_with_hint_records_and_learns(self, mock_backend):
        """First click with hint records it; second click passes hit_count."""
        engine, _, executor = self._make_engine(mock_backend)

        # First click: cache miss, hit_count=0
        engine.click(100, 200, element_hint="Save button")
        executor.click.assert_called_with(100, 200, hit_count=0)

        executor.reset_mock()
        engine.click(100, 200, element_hint="Save button")
        executor.click.assert_called_once_with(100, 200, hit_count=1)

    def test_double_click_with_hint_passes_hit_count(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.double_click(50, 75, element_hint="icon")
        # First call: miss
        executor.double_click.assert_called_with(50, 75, hit_count=0)

        executor.reset_mock()
        engine.double_click(50, 75, element_hint="icon")
        executor.double_click.assert_called_once_with(50, 75, hit_count=1)

    def test_right_click_with_hint_passes_hit_count(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.right_click(300, 400, element_hint="context target")
        executor.click.assert_called_with(300, 400, button="right", hit_count=0)

        executor.reset_mock()
        engine.right_click(300, 400, element_hint="context target")
        executor.click.assert_called_once_with(300, 400, button="right", hit_count=1)

    def test_move_mouse_with_hint_passes_hit_count(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.move_mouse(200, 300, element_hint="hover target")
        executor.move_mouse.assert_called_with(200, 300, hit_count=0)

        executor.reset_mock()
        engine.move_mouse(200, 300, element_hint="hover target")
        executor.move_mouse.assert_called_once_with(200, 300, hit_count=1)

    def test_hit_count_increments_with_repeated_clicks(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)

        for i in range(5):
            engine.click(100, 200, element_hint="frequent button")

        # Last call should have hit_count=4 (recorded 4 times before the 5th)
        last_call = executor.click.call_args_list[-1]
        assert last_call == ((), {"hit_count": 4}) or last_call == ((100, 200,), {"hit_count": 4})

    def test_different_hints_are_independent(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)

        engine.click(100, 200, element_hint="button A")
        engine.click(100, 200, element_hint="button A")
        engine.click(300, 400, element_hint="button B")

        # button B is first time, hit_count=0
        last_call = executor.click.call_args_list[-1]
        assert last_call == ((300, 400,), {"hit_count": 0})


# ---------------------------------------------------------------------------
# TestThreeLayerResolution
# ---------------------------------------------------------------------------

class TestThreeLayerResolution:
    """Tests for the 3-layer cache resolution."""

    def _make_engine(self, mock_backend, fg_window=None):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = fg_window
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def test_layer3_overrides_layer1(self, mock_backend):
        """Model-provided hint (Layer 3) takes priority over coord-based Layer 1."""
        fg = ForegroundWindow(
            app_name="notepad.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # Click with hint "File menu"
        engine.click(50, 12, element_hint="File menu")
        engine.click(50, 12, element_hint="File menu")

        # The second click should use the "File menu" hint, not "@50,0"
        last_call = executor.click.call_args_list[-1]
        assert last_call == ((50, 12,), {"hit_count": 1})

    def test_layer1_auto_learns_from_coords(self, mock_backend):
        """Without any hint, Layer 1 uses bucketed coords and still learns."""
        fg = ForegroundWindow(
            app_name="chrome.exe", title="test", x=100, y=50,
            width=1200, height=800,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # Click at (300, 200) => window-relative (200, 150) => bucket @200,150
        engine.click(300, 200)
        executor.click.assert_called_with(300, 200, hit_count=0)

        # Same click again: cache hit
        executor.reset_mock()
        engine.click(300, 200)
        executor.click.assert_called_once_with(300, 200, hit_count=1)

    def test_foreground_failure_falls_back(self, mock_backend):
        """When get_foreground_window() returns None, fall back to platform name."""
        engine, _, executor = self._make_engine(mock_backend, fg_window=None)

        # Should still work with platform name as app and absolute coords
        engine.click(100, 200)
        executor.click.assert_called_with(100, 200, hit_count=0)

        executor.reset_mock()
        engine.click(100, 200)
        executor.click.assert_called_once_with(100, 200, hit_count=1)

    def test_foreground_exception_falls_back(self, mock_backend):
        """get_foreground_window raising an exception uses platform fallback (lines 182-183)."""
        backend, capture, executor = mock_backend
        backend.get_foreground_window.side_effect = RuntimeError("dbus failure")
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        engine.click(100, 200, element_hint="test")
        executor.click.assert_called_once_with(100, 200, hit_count=0)
        entry = engine._cache.lookup("wsl2", "test")
        assert entry is not None

    def test_window_relative_coords_stored(self, mock_backend):
        """Cache uses window-relative coords so entries survive window moves."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=200, y=100,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # Click at (300, 200) => window-relative (100, 100)
        engine.click(300, 200, element_hint="my button")

        # Verify it's stored with window-relative coords
        entry = engine._cache.lookup("app.exe", "my button", 100, 100)
        assert entry is not None
        assert entry.hit_count == 1

    def test_real_app_name_used(self, mock_backend):
        """Cache stores real app name from foreground window, not 'wsl2'."""
        fg = ForegroundWindow(
            app_name="firefox.exe", title="Mozilla Firefox", x=0, y=0,
            width=1920, height=1080,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        engine.click(500, 300, element_hint="New Tab")

        # Should be stored under "firefox.exe", not "wsl2"
        entry = engine._cache.lookup("firefox.exe", "New Tab")
        assert entry is not None

        # Should NOT be under "wsl2"
        entry_wsl = engine._cache.lookup("wsl2", "New Tab")
        assert entry_wsl is None

    def test_pct_bucket_alignment(self, mock_backend):
        """Nearby coords in the same pct bucket resolve to the same Layer 1 hint."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1000, height=1000,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # 1000px wide, 3% bucket => 30px per bucket
        # (100, 200) => 10%, 20% => bucket @9%, 18%
        # (105, 205) => 10.5%, 20.5% => bucket @9%, 18%  (same)
        engine.click(100, 200)
        executor.reset_mock()
        engine.click(105, 205)
        # Should be a cache hit because both map to the same pct bucket
        executor.click.assert_called_once_with(105, 205, hit_count=1)

    def test_resize_survives_with_pct_coords(self, mock_backend):
        """Percentage-based coords survive window resize."""
        backend, capture, executor = mock_backend

        # First: 800x600 window, click at (200, 150) = 25%, 25%
        fg1 = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        backend.get_foreground_window.return_value = fg1
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()

        # Disable locator so Layer 2 doesn't interfere with pure Layer 1 test
        engine._get_locator = lambda: None

        engine.click(200, 150)  # 25%, 25% -> bucket @24%,24%

        # Simulate resize to 1200x900
        fg2 = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1200, height=900,
        )
        backend.get_foreground_window.return_value = fg2
        engine._fg_window_ts = 0  # force refresh

        executor.reset_mock()
        # Same proportional position: 25% of 1200 = 300, 25% of 900 = 225
        engine.click(300, 225)  # 25%, 25% -> same bucket @24%,24%
        executor.click.assert_called_once_with(300, 225, hit_count=1)

    def test_passthrough_app_excluded(self, mock_backend):
        """RDP and terminal apps are excluded from window-based caching."""
        fg = ForegroundWindow(
            app_name="mstsc.exe", title="Remote Desktop", x=0, y=0,
            width=1920, height=1080,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)

        # Should fall back to platform name, not "mstsc.exe"
        engine.click(500, 300, element_hint="test button")
        entry = engine._cache.lookup("mstsc.exe", "test button")
        assert entry is None

        # Should be stored under platform name
        entry = engine._cache.lookup("wsl2", "test button")
        assert entry is not None


# ---------------------------------------------------------------------------
# TestNavigationBatch
# ---------------------------------------------------------------------------

class TestNavigationBatch:
    """Tests for the navigate_chain and navigate_to methods."""

    def _make_engine(self, mock_backend, fg_window=None):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = fg_window
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def _warm_cache(self, engine, app, hint, x, y, count=None,
                    win_w=0, win_h=0, screen_w=0, screen_h=0):
        """Record enough hits to make an entry nav-eligible."""
        n = count if count is not None else MIN_NAV_HIT_COUNT + 1
        for _ in range(n):
            engine._cache.record_hit(
                app, hint, x, y,
                win_w=win_w, win_h=win_h,
                screen_w=screen_w, screen_h=screen_h,
            )

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_all_cached(self, mock_time, mock_backend):
        """All hints cached -> all steps complete."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0  # Jump 2s per call so poll loops exit immediately
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "app.exe", "btn_a", 100, 200)
        self._warm_cache(engine, "app.exe", "btn_b", 300, 400)

        result = engine.navigate_chain("app.exe", ["btn_a", "btn_b"], verify_fg=False)
        assert result["completed"] == 2
        assert result["total"] == 2
        assert result["stopped"] is False
        assert result["last_hint"] == "btn_b"
        assert executor.click.call_count == 2

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_partial_miss(self, mock_time, mock_backend):
        """Second hint misses -> stops after 1 step."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "app.exe", "btn_a", 100, 200)
        # btn_b NOT warmed -> cache miss

        result = engine.navigate_chain("app.exe", ["btn_a", "btn_b"], verify_fg=False)
        assert result["completed"] == 1
        assert result["stopped"] is True
        assert "cache miss" in result["reason"]
        assert executor.click.call_count == 1

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_empty(self, mock_time, mock_backend):
        """Empty hints list -> no-op."""
        _t = [0.0]
        mock_time.monotonic.side_effect = lambda: (_t.__setitem__(0, _t[0] + 2.0) or _t[0])
        engine, _, executor = self._make_engine(mock_backend)
        result = engine.navigate_chain("app.exe", [])
        assert result["completed"] == 0
        assert result["stopped"] is False
        assert executor.click.call_count == 0

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_no_app_name_uses_platform(self, mock_time, mock_backend):
        """Empty app_name and fg with no app_name falls to platform value (line 496)."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        # fg window exists (needed for _cache_to_screen) but has empty app_name
        fg = ForegroundWindow(
            app_name="", title="", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "wsl2", "btn", 100, 200)

        result = engine.navigate_chain("", ["btn"])
        assert result["completed"] == 1
        assert result["stopped"] is False

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_click_typeerror_fallback(self, mock_time, mock_backend):
        """executor.click raises TypeError -> falls back without hit_count (lines 548-549)."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "app.exe", "btn_a", 100, 200)

        # First call with hit_count raises TypeError, second call without it succeeds
        call_count = [0]
        def click_side_effect(*args, **kwargs):
            call_count[0] += 1
            if "hit_count" in kwargs:
                raise TypeError("unexpected keyword argument 'hit_count'")
        executor.click.side_effect = click_side_effect

        result = engine.navigate_chain("app.exe", ["btn_a"])
        assert result["completed"] == 1
        assert result["stopped"] is False
        # Should have been called twice: once with hit_count (TypeError), once without
        assert executor.click.call_count == 2

    @patch("computer_use.core.engine.time")
    def test_navigate_to_direct(self, mock_time, mock_backend):
        """Direct lookup works for single target."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "app.exe", "target", 500, 300)

        result = engine.navigate_to("target", target_app="app.exe")
        assert result["completed"] == 1
        assert result["stopped"] is False

    @patch("computer_use.core.engine.time")
    def test_navigate_to_auto_detects_app(self, mock_time, mock_backend):
        """navigate_to with no target_app uses fg window (lines 592-596)."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "app.exe", "ok btn", 100, 50)

        result = engine.navigate_to("ok btn")
        assert result["completed"] == 1

    @patch("computer_use.core.engine.time")
    def test_navigate_to_no_fg_uses_platform(self, mock_time, mock_backend):
        """navigate_to with no fg app_name falls to platform name (line 596)."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        # fg window with empty app_name so navigate_to falls to platform value,
        # but still has dimensions so _cache_to_screen can convert coords.
        fg = ForegroundWindow(
            app_name="", title="", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "wsl2", "btn", 50, 50)

        result = engine.navigate_to("btn")
        assert result["completed"] == 1

    @patch("computer_use.core.engine.time")
    def test_navigate_to_with_path_finding(self, mock_time, mock_backend):
        """navigate_to uses BFS path finding when current_hint given (lines 600-608)."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        # Warm up entries
        self._warm_cache(engine, "app.exe", "step_a", 100, 100)
        self._warm_cache(engine, "app.exe", "step_b", 200, 200)

        # Mock find_path to return a path: current -> step_a -> step_b
        engine._cache.find_path = MagicMock(
            return_value=[("app.exe", "start"), ("app.exe", "step_a"), ("app.exe", "step_b")]
        )

        result = engine.navigate_to("step_b", target_app="app.exe", current_hint="start")
        assert result["completed"] == 2
        assert result["stopped"] is False
        engine._cache.find_path.assert_called_once()

    def test_cache_to_screen_roundtrip(self, mock_backend):
        """Window-relative cache coords convert correctly back to screen."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=200, y=100,
            width=800, height=600,
        )
        engine, _, _ = self._make_engine(mock_backend, fg_window=fg)
        # Cache coords are window-relative: e.g. (150, 250)
        # Screen coords should be: fg.x + cache_x = 200 + 150 = 350
        result = engine._cache_to_screen(150, 250)
        assert result is not None
        sx, sy = result
        assert sx == 350  # 200 + 150
        assert sy == 350  # 100 + 250

    def test_cache_to_screen_no_fg_returns_none(self, mock_backend):
        """No foreground window -> returns None (line 381)."""
        engine, _, _ = self._make_engine(mock_backend, fg_window=None)
        result = engine._cache_to_screen(100, 200)
        assert result is None

    def test_cache_to_screen_zero_width_returns_none(self, mock_backend):
        """fg window with width=0 -> returns None (line 380)."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=0, height=600,
        )
        engine, _, _ = self._make_engine(mock_backend, fg_window=fg)
        result = engine._cache_to_screen(100, 200)
        assert result is None

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_cross_app(self, mock_time, mock_backend):
        """Chain works across app boundaries by re-detecting fg per step."""
        # Use incrementing time so fg cache TTL expires between steps.
        call_count = [0]
        def monotonic_side_effect():
            call_count[0] += 1
            return call_count[0] * 1.0  # 1s, 2s, 3s, ...
        mock_time.monotonic.side_effect = monotonic_side_effect
        mock_time.sleep = MagicMock()

        backend, capture, executor = mock_backend
        fg_code = ForegroundWindow(
            app_name="code.exe", title="VS Code", x=0, y=0,
            width=800, height=600,
        )
        fg_search = ForegroundWindow(
            app_name="search.exe", title="Search", x=0, y=0,
            width=400, height=300,
        )
        # get_foreground_window returns code.exe initially, then search.exe.
        backend.get_foreground_window.side_effect = [
            fg_code,     # _cache_to_screen for step 0
            fg_code,     # rescale_coords fg for step 0
            fg_search,   # _wait_for_nav_transition poll (step 0->1)
            fg_search,   # step 1: fg detection (i > 0)
            fg_search,   # _cache_to_screen for step 1
            fg_search,   # rescale_coords fg for step 1
        ]

        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()

        # Warm cache: "search btn" under code.exe, "notepad app" under search.exe
        self._warm_cache(engine, "code.exe", "search btn", 50, 12)
        self._warm_cache(engine, "search.exe", "notepad app", 200, 100)

        result = engine.navigate_chain("code.exe", ["search btn", "notepad app"])
        assert result["completed"] == 2
        assert result["total"] == 2
        assert result["stopped"] is False
        assert result["last_hint"] == "notepad app"

    @patch("computer_use.core.engine.time")
    def test_cross_app_sequence_recorded_via_engine(self, mock_time, mock_backend):
        """Engine records cross-app sequences when app changes between clicks."""
        call_count = [0]
        def monotonic_side_effect():
            call_count[0] += 1
            return call_count[0] * 1.0
        mock_time.monotonic.side_effect = monotonic_side_effect
        mock_time.sleep = MagicMock()

        backend, capture, executor = mock_backend
        fg_code = ForegroundWindow(
            app_name="code.exe", title="VS Code", x=0, y=0,
            width=800, height=600,
        )
        fg_search = ForegroundWindow(
            app_name="search.exe", title="Search", x=0, y=0,
            width=400, height=300,
        )
        backend.get_foreground_window.side_effect = [
            fg_code,     # _cache_to_screen for step 0
            fg_code,     # rescale_coords fg for step 0
            fg_search,   # _wait_for_nav_transition poll (step 0->1)
            fg_search,   # step 1: fg detection (i > 0)
            fg_search,   # _cache_to_screen for step 1
            fg_search,   # rescale_coords fg for step 1
        ]

        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()

        self._warm_cache(engine, "code.exe", "search btn", 50, 12)
        self._warm_cache(engine, "search.exe", "notepad app", 200, 100)

        engine.navigate_chain("code.exe", ["search btn", "notepad app"])

        # Verify cross-app sequence was recorded
        cross = engine._cache._conn.execute(
            "SELECT * FROM cross_sequences "
            "WHERE from_app='code.exe' AND to_app='search.exe'"
        ).fetchone()
        assert cross is not None

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_fallback_finds_wsl2_entry(self, mock_time, mock_backend):
        """Chain finds entries stored under 'wsl2' when fg detects a different app."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        # fg window says calc.exe, but entry is stored under wsl2
        fg = ForegroundWindow(
            app_name="calculatorapp.exe", title="Calculator", x=0, y=0,
            width=400, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        # Warm under wsl2 (simulates the bug)
        self._warm_cache(engine, "wsl2", "calc close btn", 380, 10)

        result = engine.navigate_chain("calculatorapp.exe", ["calc close btn"])
        assert result["completed"] == 1
        assert result["stopped"] is False

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_prefers_exact_over_fallback(self, mock_time, mock_backend):
        """When exact app match exists, fallback is not used."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        # Warm both app.exe and wsl2 versions
        self._warm_cache(engine, "app.exe", "my button", 100, 200)
        self._warm_cache(engine, "wsl2", "my button", 110, 210)

        result = engine.navigate_chain("app.exe", ["my button"])
        assert result["completed"] == 1
        assert result["stopped"] is False
        # Should have clicked at app.exe coords, not wsl2 coords
        click_args = executor.click.call_args
        assert click_args[0][0] == 100  # x from app.exe entry
        assert click_args[0][1] == 200  # y from app.exe entry

    def test_cache_to_screen_rescales_on_screen_change(self, mock_backend):
        """_cache_to_screen rescales when screen resolution changed."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1600, height=1200,
        )
        engine, _, _ = self._make_engine(mock_backend, fg_window=fg)
        # Simulate current screen is 3840x2160
        engine._screen_w = 3840
        engine._screen_h = 2160
        # Cached at 800x600 window on 1920x1080 screen -> screen changed -> rescale
        result = engine._cache_to_screen(
            200, 150,
            stored_win_w=800, stored_win_h=600,
            stored_screen_w=1920, stored_screen_h=1080,
        )
        assert result is not None
        sx, sy = result
        assert sx == 400  # 200 * 1600/800
        assert sy == 300  # 150 * 1200/600

    def test_cache_to_screen_no_rescale_when_zero(self, mock_backend):
        """Legacy entries (stored_win_w=0) pass through without rescaling."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1600, height=1200,
        )
        engine, _, _ = self._make_engine(mock_backend, fg_window=fg)
        result = engine._cache_to_screen(200, 150, stored_win_w=0, stored_win_h=0)
        assert result is not None
        sx, sy = result
        assert sx == 200  # unchanged
        assert sy == 150  # unchanged

    def test_cache_to_screen_same_screen_no_rescale(self, mock_backend):
        """Same screen + window resize -> pass through without rescaling."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1600, height=1200,
        )
        engine, _, _ = self._make_engine(mock_backend, fg_window=fg)
        engine._screen_w = 1920
        engine._screen_h = 1080
        # Same screen, window resized from 800x600 to 1600x1200
        result = engine._cache_to_screen(
            200, 150,
            stored_win_w=800, stored_win_h=600,
            stored_screen_w=1920, stored_screen_h=1080,
        )
        assert result is not None
        sx, sy = result
        assert sx == 200  # NOT rescaled (same screen)
        assert sy == 150

    def test_cache_to_screen_bounds_check_returns_none(self, mock_backend):
        """Same screen + coords out of bounds -> returns None."""
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=400, height=300,
        )
        engine, _, _ = self._make_engine(mock_backend, fg_window=fg)
        engine._screen_w = 1920
        engine._screen_h = 1080
        # Coords (500, 400) cached at 800x600, now window is 400x300
        # 500 >= 400 -> out of bounds
        result = engine._cache_to_screen(
            500, 400,
            stored_win_w=800, stored_win_h=600,
            stored_screen_w=1920, stored_screen_h=1080,
        )
        assert result is None

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_rescales_on_screen_change(self, mock_time, mock_backend):
        """Screen changed -> rescales coords proportionally."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        # Window is now 1600x1200 on a 3840x2160 screen
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1600, height=1200,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        engine._screen_w = 3840
        engine._screen_h = 2160
        # Cache was recorded at 800x600 on a 1920x1080 screen
        self._warm_cache(engine, "app.exe", "btn_a", 200, 150,
                         win_w=800, win_h=600,
                         screen_w=1920, screen_h=1080)

        result = engine.navigate_chain("app.exe", ["btn_a"])
        assert result["completed"] == 1
        assert result["stopped"] is False
        # Should click at rescaled coords: (200*1600/800, 150*1200/600) = (400, 300)
        click_args = executor.click.call_args
        assert click_args[0][0] == 400  # rescaled x
        assert click_args[0][1] == 300  # rescaled y

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_same_screen_no_rescale(self, mock_time, mock_backend):
        """Same screen + window resize -> uses original coords (in bounds)."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=1600, height=1200,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        engine._screen_w = 1920
        engine._screen_h = 1080
        # Cached at 800x600 on SAME screen -> window-only resize
        self._warm_cache(engine, "app.exe", "btn_a", 200, 150,
                         win_w=800, win_h=600,
                         screen_w=1920, screen_h=1080)

        result = engine.navigate_chain("app.exe", ["btn_a"])
        assert result["completed"] == 1
        assert result["stopped"] is False
        # Same screen -> no rescale, uses original coords (200, 150)
        click_args = executor.click.call_args
        assert click_args[0][0] == 200  # original x
        assert click_args[0][1] == 150  # original y

    @patch("computer_use.core.engine.time")
    def test_navigate_chain_bounds_check_stops(self, mock_time, mock_backend):
        """Same screen + window shrunk + coords out of bounds -> stops."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.sleep = MagicMock()
        # Window shrunk to 400x300 (same screen)
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=400, height=300,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        engine._screen_w = 1920
        engine._screen_h = 1080
        # Cached at (500, 400) in 800x600 window on same screen
        # 500 >= 400 (current width) -> out of bounds
        self._warm_cache(engine, "app.exe", "far_btn", 500, 400,
                         win_w=800, win_h=600,
                         screen_w=1920, screen_h=1080)

        result = engine.navigate_chain("app.exe", ["far_btn"])
        assert result["completed"] == 0
        assert result["stopped"] is True
        assert "out of bounds" in result["reason"]
        assert executor.click.call_count == 0


# ---------------------------------------------------------------------------
# TestLayer2Integration
# ---------------------------------------------------------------------------

class TestLayer2Integration:
    """Tests that Layer 2 (accessibility API) integrates correctly with the engine."""

    def _make_engine(self, mock_backend, fg_window=None, locator=None):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = fg_window
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        if locator is not None:
            engine._locator = locator
            engine._get_locator = lambda: locator
        return engine, capture, executor

    def _mock_locator(self, element_at_result=None):
        """Create a mock locator that returns the given element from find_element_at."""
        locator = MagicMock()
        locator.find_element_at.return_value = element_at_result
        locator.is_available.return_value = True
        return locator

    def test_layer2_produces_semantic_hint(self, mock_backend):
        """When a11y returns an element, cache stores 'role:name' hint."""
        fg = ForegroundWindow(
            app_name="notepad.exe", title="Untitled", x=0, y=0,
            width=800, height=600,
        )
        el = Element(
            name="Save", role="Button",
            region=Region(100, 200, 80, 30),
            confidence=0.95, source="accessibility",
        )
        locator = self._mock_locator(element_at_result=el)
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg, locator=locator)

        engine.click(100, 200)
        # Should have stored under "Button:Save", not a pct-bucket
        entry = engine._cache.lookup("notepad.exe", "Button:Save", 100, 200)
        assert entry is not None
        assert entry.hit_count == 1

    def test_layer2_falls_to_layer1_on_none(self, mock_backend):
        """When a11y returns None, Layer 1 pct-bucket is used."""
        fg = ForegroundWindow(
            app_name="notepad.exe", title="Untitled", x=0, y=0,
            width=800, height=600,
        )
        locator = self._mock_locator(element_at_result=None)
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg, locator=locator)

        engine.click(100, 200)
        # Layer 1: pct_x = 100*100/800 = 12 -> bucket 12
        # pct_y = 200*100/600 = 33 -> bucket 33
        bx = (12 // _PCT_BUCKET) * _PCT_BUCKET
        by = (33 // _PCT_BUCKET) * _PCT_BUCKET
        layer1_hint = f"@{bx}%,{by}%"
        entry = engine._cache.lookup("notepad.exe", layer1_hint, 100, 200)
        assert entry is not None

    def test_layer2_falls_to_layer1_on_exception(self, mock_backend):
        """When a11y raises, click still happens and Layer 1 is used."""
        fg = ForegroundWindow(
            app_name="notepad.exe", title="Untitled", x=0, y=0,
            width=800, height=600,
        )
        locator = self._mock_locator()
        locator.find_element_at.side_effect = RuntimeError("PowerShell crashed")
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg, locator=locator)

        engine.click(100, 200)
        # Click should still execute
        executor.click.assert_called_once_with(100, 200, hit_count=0)
        # Layer 1 should be used as fallback
        bx = (12 // _PCT_BUCKET) * _PCT_BUCKET
        by = (33 // _PCT_BUCKET) * _PCT_BUCKET
        layer1_hint = f"@{bx}%,{by}%"
        entry = engine._cache.lookup("notepad.exe", layer1_hint, 100, 200)
        assert entry is not None

    def test_layer2_ignores_empty_name(self, mock_backend):
        """Element with empty name should fall through to Layer 1."""
        fg = ForegroundWindow(
            app_name="notepad.exe", title="Untitled", x=0, y=0,
            width=800, height=600,
        )
        el = Element(
            name="", role="Pane",
            region=Region(0, 0, 800, 600),
            confidence=1.0, source="accessibility",
        )
        locator = self._mock_locator(element_at_result=el)
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg, locator=locator)

        engine.click(400, 300)
        # Empty name -> Layer 2 miss -> Layer 1 pct-bucket stored
        entry = engine._cache.lookup("notepad.exe", "Pane:", 400, 300)
        # Spatial lookup finds the entry, but it should have a Layer 1 hint, not "Pane:"
        assert entry is not None
        assert entry.element_hint.startswith("@")  # Layer 1 pct-bucket, not a11y

    def test_layer2_ignores_low_confidence(self, mock_backend):
        """Element with confidence below threshold falls to Layer 1."""
        fg = ForegroundWindow(
            app_name="notepad.exe", title="Untitled", x=0, y=0,
            width=800, height=600,
        )
        el = Element(
            name="Maybe", role="Button",
            region=Region(100, 200, 80, 30),
            confidence=_LAYER2_MIN_CONFIDENCE - 0.1,
            source="accessibility",
        )
        locator = self._mock_locator(element_at_result=el)
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg, locator=locator)

        engine.click(100, 200)
        # Low confidence -> Layer 2 miss -> Layer 1 pct-bucket stored
        entry = engine._cache.lookup("notepad.exe", "Button:Maybe", 100, 200)
        # Spatial lookup finds the entry, but it should have a Layer 1 hint
        assert entry is not None
        assert entry.element_hint.startswith("@")  # Layer 1, not "Button:Maybe"

    def test_layer3_overrides_layer2(self, mock_backend):
        """Explicit element_hint (Layer 3) means a11y is never called."""
        fg = ForegroundWindow(
            app_name="notepad.exe", title="Untitled", x=0, y=0,
            width=800, height=600,
        )
        el = Element(
            name="Save", role="Button",
            region=Region(100, 200, 80, 30),
            confidence=1.0, source="accessibility",
        )
        locator = self._mock_locator(element_at_result=el)
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg, locator=locator)

        engine.click(100, 200, element_hint="My Custom Hint")
        # Layer 3 takes priority -> a11y never called
        locator.find_element_at.assert_not_called()
        # Stored under custom hint, not a11y hint
        entry = engine._cache.lookup("notepad.exe", "My Custom Hint", 100, 200)
        assert entry is not None


# ---------------------------------------------------------------------------
# TestTemplateExecution -- execute_template() integration tests
# ---------------------------------------------------------------------------

class TestTemplateExecution:
    """Tests for engine.execute_template() with mocked backends."""

    def _make_engine(self, mock_backend, fg_window=None):
        backend, capture, executor = mock_backend
        backend.get_foreground_window.return_value = fg_window
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def _warm_cache(self, engine, app, hint, x, y, count=None):
        """Record enough hits to make an entry nav-eligible."""
        n = count if count is not None else MIN_NAV_HIT_COUNT + 1
        for _ in range(n):
            engine._cache.record_hit(app, hint, x, y)

    def test_nonexistent_template(self, mock_backend):
        """execute_template returns stopped=True for unknown template."""
        engine, _, _ = self._make_engine(mock_backend)
        result = engine.execute_template("nonexistent")
        assert result["stopped"] is True
        assert "not found" in result["reason"]
        assert result["completed"] == 0

    @patch("computer_use.core.engine.time")
    def test_type_text_step(self, mock_time, mock_backend):
        """Template with type_text step calls engine.type_text."""
        mock_time.time.return_value = 1000.0
        mock_time.monotonic.return_value = 1000.0
        mock_time.sleep = MagicMock()
        engine, _, executor = self._make_engine(mock_backend)

        engine._cache.create_template("type-test", "app.exe", [
            {"action": "type_text", "text": "hello world", "wait_ms": 50},
        ])
        result = engine.execute_template("type-test")
        assert result["completed"] == 1
        assert result["stopped"] is False
        executor.type_text.assert_called_once_with("hello world")

    @patch("computer_use.core.engine.time")
    def test_key_press_step(self, mock_time, mock_backend):
        """Template with key_press step calls engine.key_press."""
        mock_time.time.return_value = 1000.0
        mock_time.monotonic.return_value = 1000.0
        mock_time.sleep = MagicMock()
        engine, _, executor = self._make_engine(mock_backend)

        engine._cache.create_template("key-test", "app.exe", [
            {"action": "key_press", "text": "ctrl+s", "wait_ms": 50},
        ])
        result = engine.execute_template("key-test")
        assert result["completed"] == 1
        assert result["stopped"] is False
        executor.key_press.assert_called_once_with(["ctrl", "s"])

    @patch("computer_use.core.engine.time")
    def test_wait_step(self, mock_time, mock_backend):
        """Template with wait step sleeps for the specified duration."""
        mock_time.time.return_value = 1000.0
        mock_time.monotonic.return_value = 1000.0
        mock_time.sleep = MagicMock()
        engine, _, _ = self._make_engine(mock_backend)

        engine._cache.create_template("wait-test", "app.exe", [
            {"action": "wait", "wait_ms": 500},
        ])
        result = engine.execute_template("wait-test")
        assert result["completed"] == 1
        assert result["stopped"] is False
        # wait step sleeps for 500ms = 0.5s
        mock_time.sleep.assert_any_call(0.5)

    @patch("computer_use.core.engine.time")
    def test_click_step_uses_cache(self, mock_time, mock_backend):
        """Template click step uses navigate_chain -> cache lookup."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.time.return_value = 1000.0
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "app.exe", "save button", 300, 400)

        engine._cache.create_template("click-test", "app.exe", [
            {"action": "click", "hint": "save button", "wait_ms": 50},
        ])
        result = engine.execute_template("click-test")
        assert result["completed"] == 1
        assert result["stopped"] is False
        assert executor.click.call_count >= 1

    @patch("computer_use.core.engine.time")
    def test_click_step_cache_miss_stops(self, mock_time, mock_backend):
        """Template click step with cache miss stops execution."""
        mock_time.time.return_value = 1000.0
        mock_time.monotonic.return_value = 1000.0
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="app.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, _ = self._make_engine(mock_backend, fg_window=fg)

        engine._cache.create_template("miss-test", "app.exe", [
            {"action": "click", "hint": "unknown button", "wait_ms": 50},
        ])
        result = engine.execute_template("miss-test")
        assert result["stopped"] is True
        assert result["completed"] == 0

    @patch("computer_use.core.engine.time")
    def test_mixed_steps(self, mock_time, mock_backend):
        """Template with mixed action types executes in order."""
        _t = [0.0]
        def _tick():
            _t[0] += 2.0
            return _t[0]
        mock_time.monotonic.side_effect = _tick
        mock_time.time.return_value = 1000.0
        mock_time.sleep = MagicMock()
        fg = ForegroundWindow(
            app_name="notepad.exe", title="test", x=0, y=0,
            width=800, height=600,
        )
        engine, _, executor = self._make_engine(mock_backend, fg_window=fg)
        self._warm_cache(engine, "notepad.exe", "file menu", 50, 10)
        self._warm_cache(engine, "notepad.exe", "save as", 60, 80)

        engine._cache.create_template("save-workflow", "notepad.exe", [
            {"action": "click", "hint": "file menu", "wait_ms": 100},
            {"action": "click", "hint": "save as", "wait_ms": 100},
            {"action": "type_text", "text": "output.txt", "wait_ms": 50},
            {"action": "key_press", "text": "enter", "wait_ms": 50},
        ])
        result = engine.execute_template("save-workflow")
        assert result["completed"] == 4
        assert result["stopped"] is False
        # 2 clicks (from navigate_chain), 1 type_text, 1 key_press
        assert executor.click.call_count >= 2
        executor.type_text.assert_called_once_with("output.txt")
        executor.key_press.assert_called_once_with(["enter"])

    @patch("computer_use.core.engine.time")
    def test_template_increments_use_count(self, mock_time, mock_backend):
        """Successful execution increments the template's use_count."""
        mock_time.time.return_value = 1000.0
        mock_time.monotonic.return_value = 1000.0
        mock_time.sleep = MagicMock()
        engine, _, _ = self._make_engine(mock_backend)

        engine._cache.create_template("counter", "app.exe", [
            {"action": "wait", "wait_ms": 10},
        ])
        engine.execute_template("counter")
        engine.execute_template("counter")

        info, _ = engine._cache.get_template("counter")
        assert info["use_count"] == 2

    @patch("computer_use.core.engine.time")
    def test_template_step_exception_stops(self, mock_time, mock_backend):
        """Exception during template step stops and reports reason (lines 654-659)."""
        mock_time.time.return_value = 1000.0
        mock_time.monotonic.return_value = 1000.0
        mock_time.sleep = MagicMock()
        engine, _, executor = self._make_engine(mock_backend)
        executor.type_text.side_effect = RuntimeError("keyboard locked")

        engine._cache.create_template("err-test", "app.exe", [
            {"action": "type_text", "text": "oops", "wait_ms": 0},
        ])
        result = engine.execute_template("err-test")
        assert result["stopped"] is True
        assert result["completed"] == 0
        assert "error" in result["reason"]
