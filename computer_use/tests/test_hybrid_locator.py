"""Tests for the hybrid element locator (accessibility-first, vision fallback)."""

from unittest.mock import MagicMock, patch

from computer_use.core.types import Element, Platform, Region, ScreenState


def _make_screen():
    return ScreenState(image_bytes=b"fake", width=1920, height=1080)


def _make_element(name="Submit", confidence=0.9, source="accessibility"):
    return Element(
        name=name,
        role="button",
        region=Region(x=100, y=200, width=80, height=30),
        confidence=confidence,
        source=source,
    )


class TestFindElement:
    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_returns_accessibility_result_when_confident(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = True
        expected = _make_element(confidence=0.9)
        mock_a11y.find_element.return_value = expected
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        result = loc.find_element("Submit", _make_screen())
        assert result is expected

    @patch("computer_use.grounding.hybrid.VisionLocator")
    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_falls_back_to_vision_on_low_confidence(self, mock_a11y_cls, mock_vision_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = True
        mock_a11y.find_element.return_value = _make_element(confidence=0.3)
        mock_a11y_cls.return_value = mock_a11y

        vision_element = _make_element(name="Vision Submit", source="vision")
        mock_vision = MagicMock()
        mock_vision.find_element.return_value = vision_element
        mock_vision_cls.return_value = mock_vision

        loc = HybridLocator(Platform.LINUX, provider_name="anthropic", config={"key": "val"})
        screen = _make_screen()
        result = loc.find_element("Submit", screen)
        assert result is vision_element

    @patch("computer_use.grounding.hybrid.VisionLocator")
    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_falls_back_to_vision_when_a11y_not_available(self, mock_a11y_cls, mock_vision_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = False
        mock_a11y_cls.return_value = mock_a11y

        vision_element = _make_element(source="vision")
        mock_vision = MagicMock()
        mock_vision.find_element.return_value = vision_element
        mock_vision_cls.return_value = mock_vision

        loc = HybridLocator(Platform.LINUX, provider_name="anthropic", config={"key": "val"})
        result = loc.find_element("Button", _make_screen())
        assert result is vision_element

    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_returns_none_when_a11y_not_found_and_no_vision(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = True
        mock_a11y.find_element.return_value = None
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        assert loc.find_element("Ghost", _make_screen()) is None

    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_returns_none_without_screen_and_no_a11y(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = False
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        assert loc.find_element("Button", screen=None) is None


class TestFindAllElements:
    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_returns_a11y_elements(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = True
        elements = [_make_element("A"), _make_element("B")]
        mock_a11y.find_all_elements.return_value = elements
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        result = loc.find_all_elements(_make_screen())
        assert result == elements

    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_returns_empty_when_a11y_finds_nothing(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = True
        mock_a11y.find_all_elements.return_value = []
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        assert loc.find_all_elements(_make_screen()) == []

    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_returns_empty_when_a11y_not_available(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = False
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        assert loc.find_all_elements(_make_screen()) == []


class TestFindElementAt:
    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_delegates_to_a11y(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        expected = _make_element()
        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = True
        mock_a11y.find_element_at.return_value = expected
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        screen = _make_screen()
        result = loc.find_element_at(100, 200, screen)
        assert result is expected
        mock_a11y.find_element_at.assert_called_once_with(100, 200, screen)

    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_returns_none_when_a11y_not_available(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = False
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        assert loc.find_element_at(100, 200, _make_screen()) is None


class TestIsAvailable:
    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_true_when_a11y_available(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = True
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        assert loc.is_available() is True

    @patch("computer_use.grounding.hybrid.VisionLocator")
    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_true_when_only_vision_available(self, mock_a11y_cls, mock_vision_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = False
        mock_a11y_cls.return_value = mock_a11y
        mock_vision_cls.return_value = MagicMock()

        loc = HybridLocator(Platform.LINUX, provider_name="anthropic", config={"key": "val"})
        assert loc.is_available() is True

    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_false_when_nothing_available(self, mock_a11y_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = False
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX)
        assert loc.is_available() is False


class TestVisionInitFailure:
    @patch("computer_use.grounding.hybrid.VisionLocator", side_effect=Exception("no key"))
    @patch("computer_use.grounding.hybrid.AccessibilityLocator")
    def test_handles_vision_init_failure_gracefully(self, mock_a11y_cls, mock_vision_cls):
        from computer_use.grounding.hybrid import HybridLocator

        mock_a11y = MagicMock()
        mock_a11y.is_available.return_value = False
        mock_a11y_cls.return_value = mock_a11y

        loc = HybridLocator(Platform.LINUX, provider_name="anthropic", config={})
        assert loc._vision is None
        assert loc.is_available() is False
