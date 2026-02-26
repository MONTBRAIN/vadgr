"""Abstract screenshot capture interface."""

from abc import ABC, abstractmethod
from typing import Optional

from computer_use.core.types import Region, ScreenState


class ScreenCapture(ABC):
    """Abstract base for capturing screenshots."""

    @abstractmethod
    def capture_full(self) -> ScreenState:
        """Capture the entire screen. Returns PNG bytes in a ScreenState."""
        ...

    @abstractmethod
    def capture_region(self, region: Region) -> ScreenState:
        """Capture a specific rectangular region."""
        ...

    @abstractmethod
    def get_screen_size(self) -> tuple[int, int]:
        """Return (width, height) of the primary display."""
        ...

    @abstractmethod
    def get_scale_factor(self) -> float:
        """Return the display scale factor (1.0 for standard, 2.0 for HiDPI)."""
        ...
