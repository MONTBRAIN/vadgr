"""Tests for the vision-based element locator."""

from unittest.mock import MagicMock, patch

from computer_use.core.types import Element, Region, ScreenState


def _make_screen():
    return ScreenState(image_bytes=b"fake", width=1920, height=1080)


def _make_element(name="OK Button"):
    return Element(
        name=name,
        role="button",
        region=Region(x=100, y=200, width=80, height=30),
        confidence=0.9,
        source="vision",
    )


class TestVisionLocatorInit:
    @patch("computer_use.providers.registry.get_provider")
    def test_creates_provider_from_registry(self, mock_get):
        from computer_use.grounding.vision import VisionLocator

        mock_get.return_value = MagicMock()
        loc = VisionLocator("anthropic", {"providers": {"anthropic": {"api_key": "k"}}})
        mock_get.assert_called_once_with(
            "anthropic", {"providers": {"anthropic": {"api_key": "k"}}}
        )


class TestFindElement:
    @patch("computer_use.providers.registry.get_provider")
    def test_delegates_to_provider_locate_element(self, mock_get):
        from computer_use.grounding.vision import VisionLocator

        provider = MagicMock()
        expected = _make_element()
        provider.locate_element.return_value = expected
        mock_get.return_value = provider

        loc = VisionLocator("anthropic", {})
        screen = _make_screen()
        result = loc.find_element("OK button", screen)

        assert result is expected
        provider.locate_element.assert_called_once_with(screen, "OK button")

    @patch("computer_use.providers.registry.get_provider")
    def test_returns_none_without_screen(self, mock_get):
        from computer_use.grounding.vision import VisionLocator

        mock_get.return_value = MagicMock()
        loc = VisionLocator("anthropic", {})
        assert loc.find_element("something", screen=None) is None


class TestFindAllElements:
    @patch("computer_use.providers.registry.get_provider")
    def test_returns_empty_list(self, mock_get):
        from computer_use.grounding.vision import VisionLocator

        mock_get.return_value = MagicMock()
        loc = VisionLocator("anthropic", {})
        assert loc.find_all_elements(_make_screen()) == []


class TestFindElementAt:
    @patch("computer_use.providers.registry.get_provider")
    def test_delegates_with_coordinate_description(self, mock_get):
        from computer_use.grounding.vision import VisionLocator

        provider = MagicMock()
        expected = _make_element()
        provider.locate_element.return_value = expected
        mock_get.return_value = provider

        loc = VisionLocator("anthropic", {})
        screen = _make_screen()
        result = loc.find_element_at(150, 250, screen)

        assert result is expected
        provider.locate_element.assert_called_once_with(
            screen, "element at coordinates (150, 250)"
        )

    @patch("computer_use.providers.registry.get_provider")
    def test_returns_none_without_screen(self, mock_get):
        from computer_use.grounding.vision import VisionLocator

        mock_get.return_value = MagicMock()
        loc = VisionLocator("anthropic", {})
        assert loc.find_element_at(100, 200, screen=None) is None


class TestIsAvailable:
    @patch("computer_use.providers.registry.get_provider")
    def test_always_returns_true(self, mock_get):
        from computer_use.grounding.vision import VisionLocator

        mock_get.return_value = MagicMock()
        loc = VisionLocator("anthropic", {})
        assert loc.is_available() is True
