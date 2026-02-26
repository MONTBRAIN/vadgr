"""Abstract element locator interface."""

from abc import ABC, abstractmethod
from typing import Optional

from computer_use.core.types import Element, ScreenState


class ElementLocator(ABC):
    """Abstract base for finding UI elements on screen."""

    @abstractmethod
    def find_element(
        self, description: str, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        """Find a single element matching a natural-language description.
        Returns None if not found."""
        ...

    @abstractmethod
    def find_all_elements(
        self, screen: Optional[ScreenState] = None
    ) -> list[Element]:
        """Enumerate all visible/accessible UI elements."""
        ...

    @abstractmethod
    def find_element_at(
        self, x: int, y: int, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        """Identify the element at a given screen coordinate."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this locator's backend is available."""
        ...
