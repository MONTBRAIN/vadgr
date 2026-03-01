"""Tests for the grounding layer: accessibility, hybrid locator, and dispatch."""

from unittest.mock import MagicMock, patch

import pytest

from computer_use.core.types import Element, Platform, Region


# ---------------------------------------------------------------------------
# TestWindowsA11yParsing -- unit tests for _parse_element()
# ---------------------------------------------------------------------------

class TestWindowsA11yParsing:
    """Test _WindowsA11y._parse_element() with various inputs."""

    def _parser(self):
        from computer_use.grounding.accessibility import _WindowsA11y
        return _WindowsA11y()

    def test_valid_element(self):
        impl = self._parser()
        el = impl._parse_element("Save|ControlType.Button|100|200|80|30")
        assert el is not None
        assert el.name == "Save"
        assert el.role == "Button"
        assert el.region.x == 100
        assert el.region.y == 200
        assert el.region.width == 80
        assert el.region.height == 30
        assert el.confidence == 1.0
        assert el.source == "accessibility"

    def test_control_type_prefix_stripped(self):
        impl = self._parser()
        el = impl._parse_element("OK|ControlType.Button|0|0|50|25")
        assert el.role == "Button"

    def test_no_control_type_prefix(self):
        """If ControlType. prefix is absent, role is used as-is."""
        impl = self._parser()
        el = impl._parse_element("Title|Edit|10|20|300|30")
        assert el.role == "Edit"

    def test_float_coordinates(self):
        """PowerShell sometimes returns float coords."""
        impl = self._parser()
        el = impl._parse_element("X|Button|10.5|20.7|80.0|30.0")
        assert el.region.x == 10
        assert el.region.y == 20
        assert el.region.width == 80
        assert el.region.height == 30

    def test_missing_fields_returns_none(self):
        impl = self._parser()
        assert impl._parse_element("Save|Button|100") is None

    def test_empty_string_returns_none(self):
        impl = self._parser()
        assert impl._parse_element("") is None

    def test_garbage_coords_returns_none(self):
        impl = self._parser()
        assert impl._parse_element("Name|Button|abc|def|ghi|jkl") is None


# ---------------------------------------------------------------------------
# TestWindowsA11yMocked -- mock _run_ps to test full find_element_at flow
# ---------------------------------------------------------------------------

class TestWindowsA11yMocked:
    """Test _WindowsA11y methods with mocked PowerShell."""

    def test_find_element_at_success(self):
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch("computer_use.grounding.accessibility._WindowsA11y.find_element_at") as mock_method:
            # Test at the higher level instead -- mock _run_ps
            pass

        # Direct approach: mock _run_ps at import point
        with patch(
            "computer_use.platform.wsl2._run_ps",
            return_value="Save|ControlType.Button|100|200|80|30",
        ):
            el = impl.find_element_at(100, 200)
        assert el is not None
        assert el.name == "Save"
        assert el.role == "Button"

    def test_find_element_at_not_found(self):
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch(
            "computer_use.platform.wsl2._run_ps",
            return_value="NOT_FOUND",
        ):
            el = impl.find_element_at(500, 500)
        assert el is None

    def test_find_element_at_exception(self):
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch(
            "computer_use.platform.wsl2._run_ps",
            side_effect=RuntimeError("PowerShell crashed"),
        ):
            el = impl.find_element_at(100, 200)
        assert el is None

    def test_find_element_success(self):
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch(
            "computer_use.platform.wsl2._run_ps",
            return_value="File|ControlType.MenuItem|10|5|60|25",
        ):
            el = impl.find_element("File")
        assert el is not None
        assert el.name == "File"
        assert el.role == "MenuItem"

    def test_find_element_not_found(self):
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch(
            "computer_use.platform.wsl2._run_ps",
            return_value="NOT_FOUND",
        ):
            el = impl.find_element("nonexistent")
        assert el is None

    def test_find_element_at_uses_timeout(self):
        """Verify _run_ps is called with _A11Y_PS_TIMEOUT."""
        from computer_use.grounding.accessibility import _WindowsA11y, _A11Y_PS_TIMEOUT

        impl = _WindowsA11y()
        with patch("computer_use.platform.wsl2._run_ps", return_value="NOT_FOUND") as mock_ps:
            impl.find_element_at(100, 200)
            _, kwargs = mock_ps.call_args
            assert kwargs["timeout"] == _A11Y_PS_TIMEOUT

    def test_find_element_uses_timeout(self):
        """Verify find_element calls _run_ps with _A11Y_PS_TIMEOUT."""
        from computer_use.grounding.accessibility import _WindowsA11y, _A11Y_PS_TIMEOUT

        impl = _WindowsA11y()
        with patch("computer_use.platform.wsl2._run_ps", return_value="NOT_FOUND") as mock_ps:
            impl.find_element("Save")
            _, kwargs = mock_ps.call_args
            assert kwargs["timeout"] == _A11Y_PS_TIMEOUT


# ---------------------------------------------------------------------------
# TestAccessibilityLocatorDispatch -- platform dispatch
# ---------------------------------------------------------------------------

class TestAccessibilityLocatorDispatch:
    """Test that AccessibilityLocator dispatches to the right platform impl."""

    def test_wsl2_dispatches_to_windows(self):
        from computer_use.grounding.accessibility import AccessibilityLocator, _WindowsA11y

        loc = AccessibilityLocator(Platform.WSL2)
        assert isinstance(loc._impl, _WindowsA11y)

    def test_windows_dispatches_to_windows(self):
        from computer_use.grounding.accessibility import AccessibilityLocator, _WindowsA11y

        loc = AccessibilityLocator(Platform.WINDOWS)
        assert isinstance(loc._impl, _WindowsA11y)

    def test_linux_dispatches_to_linux(self):
        from computer_use.grounding.accessibility import AccessibilityLocator, _LinuxA11y

        loc = AccessibilityLocator(Platform.LINUX)
        assert isinstance(loc._impl, _LinuxA11y)

    def test_macos_dispatches_to_macos(self):
        from computer_use.grounding.accessibility import AccessibilityLocator, _MacOSA11y

        loc = AccessibilityLocator(Platform.MACOS)
        assert isinstance(loc._impl, _MacOSA11y)


# ---------------------------------------------------------------------------
# TestHybridLocator -- accessibility + vision integration
# ---------------------------------------------------------------------------

class TestHybridLocator:
    """Test HybridLocator delegation and fallback behavior."""

    def _make_locator(self, a11y_available=True, a11y_element=None):
        from computer_use.grounding.hybrid import HybridLocator

        loc = HybridLocator.__new__(HybridLocator)
        loc._a11y = MagicMock()
        loc._a11y.is_available.return_value = a11y_available
        loc._a11y.find_element.return_value = a11y_element
        loc._a11y.find_element_at.return_value = a11y_element
        loc._vision = None
        return loc

    def test_find_element_delegates_to_a11y(self):
        el = Element(
            name="Save", role="Button",
            region=Region(100, 200, 80, 30),
            confidence=0.95, source="accessibility",
        )
        loc = self._make_locator(a11y_element=el)
        result = loc.find_element("Save")
        assert result is not None
        assert result.name == "Save"

    def test_find_element_returns_none_when_unavailable(self):
        loc = self._make_locator(a11y_available=False)
        result = loc.find_element("Save")
        assert result is None

    def test_find_element_filters_low_confidence(self):
        """HybridLocator.find_element rejects confidence <= 0.7."""
        el = Element(
            name="Maybe", role="Button",
            region=Region(100, 200, 80, 30),
            confidence=0.5, source="accessibility",
        )
        loc = self._make_locator(a11y_element=el)
        result = loc.find_element("Maybe")
        assert result is None  # 0.5 < 0.7 threshold in hybrid.py

    def test_find_element_at_delegates(self):
        el = Element(
            name="OK", role="Button",
            region=Region(50, 100, 60, 25),
            confidence=1.0, source="accessibility",
        )
        loc = self._make_locator(a11y_element=el)
        result = loc.find_element_at(80, 112)
        assert result is not None
        assert result.name == "OK"

    def test_find_element_at_returns_none_when_unavailable(self):
        loc = self._make_locator(a11y_available=False)
        result = loc.find_element_at(100, 200)
        assert result is None

    def test_is_available_true_when_a11y_available(self):
        loc = self._make_locator(a11y_available=True)
        assert loc.is_available() is True

    def test_is_available_false_when_nothing_available(self):
        loc = self._make_locator(a11y_available=False)
        assert loc.is_available() is False


# ---------------------------------------------------------------------------
# TestWindowsA11yDpiAndChildWalking -- DPI awareness + SmallestElementFromPoint
# ---------------------------------------------------------------------------

class TestWindowsA11yDpiAndChildWalking:
    """Test that PowerShell scripts include DPI awareness and child-walking."""

    def test_find_element_at_script_has_dpi_awareness(self):
        """find_element_at sends a script with SetProcessDPIAware."""
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch("computer_use.platform.wsl2._run_ps", return_value="NOT_FOUND") as mock_ps:
            impl.find_element_at(100, 200)
            script = mock_ps.call_args[0][0]
            assert "SetProcessDPIAware" in script

    def test_find_element_at_script_has_child_walking(self):
        """find_element_at sends a script with SmallestElementFromPoint loop."""
        from computer_use.grounding.accessibility import _WindowsA11y, _A11Y_MAX_CHILD_DEPTH

        impl = _WindowsA11y()
        with patch("computer_use.platform.wsl2._run_ps", return_value="NOT_FOUND") as mock_ps:
            impl.find_element_at(100, 200)
            script = mock_ps.call_args[0][0]
            assert f"$maxDepth = {_A11Y_MAX_CHILD_DEPTH}" in script
            assert "$bestArea" in script
            assert "FindAll" in script

    def test_find_element_at_substitutes_coordinates(self):
        """find_element_at correctly substitutes x, y in the script."""
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch("computer_use.platform.wsl2._run_ps", return_value="NOT_FOUND") as mock_ps:
            impl.find_element_at(1854, 216)
            script = mock_ps.call_args[0][0]
            assert "$px = 1854" in script
            assert "$py = 216" in script

    def test_find_element_script_has_dpi_awareness(self):
        """find_element sends a script with SetProcessDPIAware."""
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch("computer_use.platform.wsl2._run_ps", return_value="NOT_FOUND") as mock_ps:
            impl.find_element("Save")
            script = mock_ps.call_args[0][0]
            assert "SetProcessDPIAware" in script

    def test_find_all_elements_script_has_dpi_awareness(self):
        """find_all_elements sends a script with SetProcessDPIAware."""
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        with patch("computer_use.platform.wsl2._run_ps", return_value="") as mock_ps:
            impl.find_all_elements()
            script = mock_ps.call_args[0][0]
            assert "SetProcessDPIAware" in script

    def test_find_element_at_returns_deepest_child(self):
        """When PS child-walking resolves a deeper child, it's returned correctly."""
        from computer_use.grounding.accessibility import _WindowsA11y

        impl = _WindowsA11y()
        # Simulate PS returned a button (the deepest child) instead of toolbar pane
        with patch(
            "computer_use.platform.wsl2._run_ps",
            return_value="Bold|ControlType.Button|450|169|30|30",
        ):
            el = impl.find_element_at(465, 184)
        assert el is not None
        assert el.name == "Bold"
        assert el.role == "Button"

    def test_max_child_depth_constant_bounds(self):
        """_A11Y_MAX_CHILD_DEPTH is within sane bounds."""
        from computer_use.grounding.accessibility import _A11Y_MAX_CHILD_DEPTH

        assert _A11Y_MAX_CHILD_DEPTH > 0
        assert _A11Y_MAX_CHILD_DEPTH <= 10

    def test_dpi_setup_uses_dedicated_class_name(self):
        """DPI setup uses A11yDpi (not DpiHelper) to avoid collisions with wsl2.py."""
        from computer_use.grounding.accessibility import _A11Y_DPI_SETUP

        assert "A11yDpi" in _A11Y_DPI_SETUP
        assert "DpiHelper" not in _A11Y_DPI_SETUP

    def test_dpi_setup_is_idempotent(self):
        """DPI setup uses -ErrorAction SilentlyContinue for re-entrant calls."""
        from computer_use.grounding.accessibility import _A11Y_DPI_SETUP

        assert "-ErrorAction SilentlyContinue" in _A11Y_DPI_SETUP

    def test_dpi_setup_suppresses_return_value(self):
        """SetProcessDPIAware() return value must be suppressed to avoid
        polluting PowerShell stdout with 'True', which would contaminate
        the element name parsed by _parse_element()."""
        from computer_use.grounding.accessibility import _A11Y_DPI_SETUP

        assert "[void]" in _A11Y_DPI_SETUP or "Out-Null" in _A11Y_DPI_SETUP or "$null" in _A11Y_DPI_SETUP
