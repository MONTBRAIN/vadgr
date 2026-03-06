"""Unit tests for computer_use.grounding.accessibility."""

import unittest
from unittest.mock import MagicMock, patch

from computer_use.core.types import Element, Platform, Region
from computer_use.grounding.accessibility import (
    AccessibilityLocator,
    _LinuxA11y,
    _MacOSA11y,
    _WindowsA11y,
)


class TestAccessibilityLocatorInit(unittest.TestCase):
    """Test that _load_impl picks the correct backend for each Platform."""

    @patch("computer_use.grounding.accessibility.shutil")
    def test_load_impl_wsl2(self, _mock_shutil):
        loc = AccessibilityLocator(Platform.WSL2)
        self.assertIsInstance(loc._impl, _WindowsA11y)

    @patch("computer_use.grounding.accessibility.shutil")
    def test_load_impl_windows(self, _mock_shutil):
        loc = AccessibilityLocator(Platform.WINDOWS)
        self.assertIsInstance(loc._impl, _WindowsA11y)

    @patch("computer_use.grounding.accessibility.shutil")
    def test_load_impl_macos(self, _mock_shutil):
        loc = AccessibilityLocator(Platform.MACOS)
        self.assertIsInstance(loc._impl, _MacOSA11y)

    @patch("computer_use.grounding.accessibility.shutil")
    def test_load_impl_linux(self, _mock_shutil):
        loc = AccessibilityLocator(Platform.LINUX)
        self.assertIsInstance(loc._impl, _LinuxA11y)


class TestWindowsA11yIsAvailable(unittest.TestCase):
    """Test _WindowsA11y.is_available checks for powershell.exe."""

    def setUp(self):
        self.a11y = _WindowsA11y()

    @patch("computer_use.grounding.accessibility.shutil.which", return_value="/usr/bin/powershell.exe")
    def test_available_when_powershell_found(self, _mock_which):
        self.assertTrue(self.a11y.is_available())

    @patch("computer_use.grounding.accessibility.shutil.which", return_value=None)
    def test_unavailable_when_powershell_missing(self, _mock_which):
        self.assertFalse(self.a11y.is_available())


class TestWindowsA11yFindElement(unittest.TestCase):
    """Test _WindowsA11y.find_element with mocked _run_ps."""

    def setUp(self):
        self.a11y = _WindowsA11y()

    @patch("computer_use.platform.wsl2._run_ps")
    def test_find_element_success(self, mock_run_ps):
        mock_run_ps.return_value = "Save|ControlType.Button|100|200|80|30"
        result = self.a11y.find_element("Save")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Save")
        self.assertEqual(result.role, "Button")
        self.assertEqual(result.region, Region(x=100, y=200, width=80, height=30))
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.source, "accessibility")

    @patch("computer_use.platform.wsl2._run_ps")
    def test_find_element_not_found(self, mock_run_ps):
        mock_run_ps.return_value = "NOT_FOUND"
        result = self.a11y.find_element("NonExistent")
        self.assertIsNone(result)

    @patch("computer_use.platform.wsl2._run_ps")
    def test_find_element_empty_result(self, mock_run_ps):
        mock_run_ps.return_value = ""
        result = self.a11y.find_element("Empty")
        self.assertIsNone(result)

    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("ps failed"))
    def test_find_element_exception(self, _mock_run_ps):
        result = self.a11y.find_element("Broken")
        self.assertIsNone(result)


class TestWindowsA11yFindAllElements(unittest.TestCase):
    """Test _WindowsA11y.find_all_elements."""

    def setUp(self):
        self.a11y = _WindowsA11y()

    @patch("computer_use.platform.wsl2._run_ps")
    def test_multiple_elements(self, mock_run_ps):
        mock_run_ps.return_value = (
            "File|ControlType.MenuItem|0|0|60|25\n"
            "Edit|ControlType.MenuItem|60|0|60|25\n"
            "Help|ControlType.MenuItem|120|0|60|25"
        )
        result = self.a11y.find_all_elements()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].name, "File")
        self.assertEqual(result[1].name, "Edit")
        self.assertEqual(result[2].name, "Help")
        for el in result:
            self.assertEqual(el.role, "MenuItem")
            self.assertEqual(el.source, "accessibility")

    @patch("computer_use.platform.wsl2._run_ps")
    def test_empty_result(self, mock_run_ps):
        mock_run_ps.return_value = ""
        result = self.a11y.find_all_elements()
        self.assertEqual(result, [])

    @patch("computer_use.platform.wsl2._run_ps", side_effect=OSError("timeout"))
    def test_exception_returns_empty(self, _mock_run_ps):
        result = self.a11y.find_all_elements()
        self.assertEqual(result, [])

    @patch("computer_use.platform.wsl2._run_ps")
    def test_skips_malformed_lines(self, mock_run_ps):
        mock_run_ps.return_value = (
            "Good|ControlType.Button|10|20|30|40\n"
            "bad|line\n"
            "Also Good|ControlType.Text|50|60|70|80"
        )
        result = self.a11y.find_all_elements()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Good")
        self.assertEqual(result[1].name, "Also Good")


class TestWindowsA11yFindElementAt(unittest.TestCase):
    """Test _WindowsA11y.find_element_at."""

    def setUp(self):
        self.a11y = _WindowsA11y()

    @patch("computer_use.platform.wsl2._run_ps")
    def test_found(self, mock_run_ps):
        mock_run_ps.return_value = "Submit|ControlType.Button|200|300|100|40"
        result = self.a11y.find_element_at(250, 320)
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "Submit")
        self.assertEqual(result.role, "Button")
        self.assertEqual(result.region, Region(x=200, y=300, width=100, height=40))

    @patch("computer_use.platform.wsl2._run_ps")
    def test_not_found(self, mock_run_ps):
        mock_run_ps.return_value = "NOT_FOUND"
        result = self.a11y.find_element_at(0, 0)
        self.assertIsNone(result)

    @patch("computer_use.platform.wsl2._run_ps")
    def test_empty_result(self, mock_run_ps):
        mock_run_ps.return_value = ""
        result = self.a11y.find_element_at(10, 10)
        self.assertIsNone(result)

    @patch("computer_use.platform.wsl2._run_ps", side_effect=Exception("boom"))
    def test_exception(self, _mock_run_ps):
        result = self.a11y.find_element_at(10, 10)
        self.assertIsNone(result)


class TestWindowsA11yParseElement(unittest.TestCase):
    """Test _WindowsA11y._parse_element directly."""

    def setUp(self):
        self.a11y = _WindowsA11y()

    def test_valid_line(self):
        el = self.a11y._parse_element("OK|ControlType.Button|10|20|100|50")
        self.assertIsNotNone(el)
        self.assertEqual(el.name, "OK")
        self.assertEqual(el.role, "Button")
        self.assertEqual(el.region, Region(x=10, y=20, width=100, height=50))
        self.assertEqual(el.confidence, 1.0)
        self.assertEqual(el.source, "accessibility")

    def test_float_coordinates(self):
        el = self.a11y._parse_element("Btn|ControlType.Button|10.5|20.7|100.9|50.1")
        self.assertIsNotNone(el)
        self.assertEqual(el.region, Region(x=10, y=20, width=100, height=50))

    def test_too_few_parts(self):
        el = self.a11y._parse_element("Name|Role|10")
        self.assertIsNone(el)

    def test_empty_string(self):
        el = self.a11y._parse_element("")
        self.assertIsNone(el)

    def test_bad_numbers(self):
        el = self.a11y._parse_element("Name|Role|abc|def|ghi|jkl")
        self.assertIsNone(el)

    def test_strips_controltype_prefix(self):
        el = self.a11y._parse_element("X|ControlType.TextBox|0|0|10|10")
        self.assertEqual(el.role, "TextBox")

    def test_no_controltype_prefix(self):
        el = self.a11y._parse_element("X|Button|0|0|10|10")
        self.assertEqual(el.role, "Button")

    def test_extra_parts_ignored(self):
        el = self.a11y._parse_element("X|ControlType.Button|0|0|10|10|extra|stuff")
        self.assertIsNotNone(el)
        self.assertEqual(el.name, "X")


class TestMacOSA11y(unittest.TestCase):
    """Test _MacOSA11y stub behavior (AppKit not available in test env)."""

    def setUp(self):
        self.a11y = _MacOSA11y()

    @patch.dict("sys.modules", {"AppKit": None})
    def test_is_available_false_when_no_appkit(self):
        self.assertFalse(self.a11y.is_available())

    @patch.dict("sys.modules", {"AppKit": MagicMock()})
    def test_is_available_true_when_appkit_present(self):
        self.assertTrue(self.a11y.is_available())


class TestLinuxA11y(unittest.TestCase):
    """Test _LinuxA11y stub behavior (pyatspi not available in test env)."""

    def setUp(self):
        self.a11y = _LinuxA11y()

    @patch.dict("sys.modules", {"pyatspi": None})
    def test_is_available_false_when_no_pyatspi(self):
        self.assertFalse(self.a11y.is_available())

    @patch.dict("sys.modules", {"pyatspi": MagicMock()})
    def test_is_available_true_when_pyatspi_present(self):
        self.assertTrue(self.a11y.is_available())


if __name__ == "__main__":
    unittest.main()
