"""Main engine facade -- the public API for the computer use engine."""

import logging
import os
from typing import Optional

import yaml

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ConfigError, PlatformNotSupportedError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import (
    Action,
    Element,
    Platform,
    Region,
    ScreenState,
    StepResult,
)
from computer_use.platform.base import PlatformBackend
from computer_use.platform.detect import detect_platform, get_backend

logger = logging.getLogger("computer_use.engine")


class ComputerUseEngine:
    """Primary API for the computer use engine.

    Library mode (agent calls engine directly):
        engine = ComputerUseEngine()
        screen = engine.screenshot()
        engine.click(500, 300)
        engine.type_text("hello world")

    Autonomous mode (engine calls LLM):
        engine = ComputerUseEngine(provider="anthropic")
        results = engine.run_task("Open Chrome and go to google.com")
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        self._config = self._load_config(config_path)
        self._platform = detect_platform()
        logger.info("Detected platform: %s", self._platform.value)

        self._backend: PlatformBackend = get_backend(self._platform)
        if not self._backend.is_available():
            raise PlatformNotSupportedError(
                f"Platform {self._platform.value} backend is not available. "
                "Check that required system tools are installed."
            )

        self._capture: ScreenCapture = self._backend.get_screen_capture()
        self._executor: ActionExecutor = self._backend.get_action_executor()
        self._provider_name = provider or self._config.get("provider")
        self._provider = None
        self._locator = None
        self._history: list[dict] = []
        # Virtual screen offset for multi-monitor coordinate translation.
        # Populated on first screenshot. Screenshot pixel (x, y) maps to
        # absolute screen coordinate (x + offset_x, y + offset_y).
        self._vs_offset_x: int = 0
        self._vs_offset_y: int = 0

    # --- Library Mode API ---

    def screenshot(self) -> ScreenState:
        """Capture and return the full virtual screen (all monitors)."""
        state = self._capture.capture_full()
        self._vs_offset_x = state.offset_x
        self._vs_offset_y = state.offset_y
        return state

    def _to_abs(self, x: int, y: int) -> tuple[int, int]:
        """Translate screenshot pixel coords to absolute screen coords."""
        return (x + self._vs_offset_x, y + self._vs_offset_y)

    def screenshot_region(
        self, x: int, y: int, width: int, height: int
    ) -> ScreenState:
        """Capture a rectangular region of the screen."""
        return self._capture.capture_region(Region(x, y, width, height))

    def click(self, x: int, y: int) -> None:
        """Left-click at screenshot coordinates (auto-translated for multi-monitor)."""
        ax, ay = self._to_abs(x, y)
        self._executor.click(ax, ay)

    def double_click(self, x: int, y: int) -> None:
        """Double-click at screenshot coordinates."""
        ax, ay = self._to_abs(x, y)
        self._executor.double_click(ax, ay)

    def right_click(self, x: int, y: int) -> None:
        """Right-click at screenshot coordinates."""
        ax, ay = self._to_abs(x, y)
        self._executor.click(ax, ay, button="right")

    def type_text(self, text: str) -> None:
        """Type a string of text."""
        self._executor.type_text(text)

    def key_press(self, *keys: str) -> None:
        """Press a key combination. e.g. engine.key_press('ctrl', 'c')"""
        self._executor.key_press(list(keys))

    def scroll(self, x: int, y: int, amount: int) -> None:
        """Scroll at a position. Positive = up, negative = down."""
        ax, ay = self._to_abs(x, y)
        self._executor.scroll(ax, ay, amount)

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        """Drag from one position to another."""
        asx, asy = self._to_abs(start_x, start_y)
        aex, aey = self._to_abs(end_x, end_y)
        self._executor.drag(asx, asy, aex, aey, duration)

    def move_mouse(self, x: int, y: int) -> None:
        """Move mouse without clicking."""
        ax, ay = self._to_abs(x, y)
        self._executor.move_mouse(ax, ay)

    def execute_action(self, action: Action) -> None:
        """Execute an Action dataclass directly."""
        self._executor.execute_action(action)

    def find_element(self, description: str) -> Optional[Element]:
        """Find a UI element by natural-language description.

        Uses accessibility API first, falls back to LLM vision.
        Requires grounding layer to be initialized.
        """
        locator = self._get_locator()
        if locator is None:
            return None
        screen = self.screenshot()
        return locator.find_element(description, screen)

    def find_all_elements(self) -> list[Element]:
        """List all visible UI elements via accessibility API."""
        locator = self._get_locator()
        if locator is None:
            return []
        screen = self.screenshot()
        return locator.find_all_elements(screen)

    def click_element(self, element: Element) -> None:
        """Click the center of a found UI element."""
        cx, cy = element.region.center
        self.click(cx, cy)

    def get_screen_size(self) -> tuple[int, int]:
        """Return (width, height) of the primary display."""
        return self._capture.get_screen_size()

    def get_platform(self) -> Platform:
        """Return the detected platform."""
        return self._platform

    def get_platform_info(self) -> dict:
        """Return platform and accessibility information."""
        return {
            "platform": self._platform.value,
            "backend_available": self._backend.is_available(),
            "accessibility": self._backend.get_accessibility_info(),
        }

    # --- Autonomous Mode API ---

    def run_task(
        self,
        task: str,
        max_steps: int = 50,
        verify: bool = True,
    ) -> list[StepResult]:
        """Execute a task autonomously using the configured LLM provider.

        Runs the core loop: screenshot -> decide -> act -> verify.
        Stops when the LLM says the task is complete, an error is
        unrecoverable, or max_steps is reached.
        """
        provider = self._get_provider()
        locator = self._get_locator()
        from computer_use.core.loop import run_core_loop

        return run_core_loop(
            capture=self._capture,
            executor=self._executor,
            locator=locator,
            provider=provider,
            task=task,
            max_steps=max_steps,
            verify=verify,
            history=self._history,
        )

    # --- Internal ---

    def _get_provider(self):
        """Lazy-load the LLM provider."""
        if self._provider is None:
            if not self._provider_name:
                raise ConfigError(
                    "No LLM provider configured. Pass provider='anthropic' "
                    "to the constructor or set 'provider' in config.yaml."
                )
            from computer_use.providers.registry import get_provider

            self._provider = get_provider(self._provider_name, self._config)
        return self._provider

    def _get_locator(self):
        """Lazy-load the grounding locator."""
        if self._locator is None:
            try:
                from computer_use.grounding.hybrid import HybridLocator

                self._locator = HybridLocator(
                    platform=self._platform,
                    provider_name=self._provider_name,
                    config=self._config,
                )
            except ImportError:
                logger.debug("Grounding layer not available")
                return None
        return self._locator

    def _load_config(self, path: Optional[str]) -> dict:
        """Load config from YAML file."""
        if path is None:
            default = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "config.yaml"
            )
            if os.path.exists(default):
                path = default
            else:
                return {}
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            raise ConfigError(f"Cannot load config from {path}: {e}") from e
