"""Hybrid element locator: accessibility-first, vision fallback."""

import logging
from typing import Optional

from computer_use.core.types import Element, Platform, ScreenState
from computer_use.grounding.accessibility import AccessibilityLocator
from computer_use.grounding.base import ElementLocator
from computer_use.grounding.vision import VisionLocator

logger = logging.getLogger("computer_use.grounding.hybrid")


class HybridLocator(ElementLocator):
    """Try OS accessibility API first, fall back to LLM vision."""

    def __init__(
        self,
        platform: Platform,
        provider_name: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        self._a11y = AccessibilityLocator(platform)
        self._vision: Optional[VisionLocator] = None
        if provider_name and config:
            try:
                self._vision = VisionLocator(provider_name, config)
            except Exception as e:
                logger.debug("Vision locator not available: %s", e)

    def find_element(
        self, description: str, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        # Try accessibility first
        if self._a11y.is_available():
            element = self._a11y.find_element(description, screen)
            if element and element.confidence > 0.7:
                logger.debug("Found via accessibility: %s", element.name)
                return element

        # Fall back to vision
        if self._vision and screen:
            logger.debug("Falling back to vision for: %s", description)
            return self._vision.find_element(description, screen)

        return None

    def find_all_elements(
        self, screen: Optional[ScreenState] = None
    ) -> list[Element]:
        if self._a11y.is_available():
            elements = self._a11y.find_all_elements(screen)
            if elements:
                return elements
        return []

    def find_element_at(
        self, x: int, y: int, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        if self._a11y.is_available():
            return self._a11y.find_element_at(x, y, screen)
        return None

    def is_available(self) -> bool:
        return self._a11y.is_available() or self._vision is not None
