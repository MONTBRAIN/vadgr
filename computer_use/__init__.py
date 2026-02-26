"""Computer Use Engine -- gives LLM agents eyes and hands.

Library mode (agent calls engine):
    from computer_use import ComputerUseEngine
    engine = ComputerUseEngine()
    screen = engine.screenshot()
    engine.click(500, 300)
    engine.type_text("hello")

Autonomous mode (engine calls LLM):
    from computer_use import ComputerUseEngine
    engine = ComputerUseEngine(provider="anthropic")
    results = engine.run_task("Open Notepad and type hello")
"""

from computer_use.core.engine import ComputerUseEngine
from computer_use.core.errors import (
    ActionError,
    ActionTimeoutError,
    ComputerUseError,
    ConfigError,
    ElementNotFoundError,
    GroundingError,
    PlatformNotSupportedError,
    ProviderError,
    ScreenCaptureError,
)
from computer_use.core.types import (
    Action,
    ActionType,
    Element,
    Platform,
    Region,
    ScreenState,
    StepResult,
)

__all__ = [
    "ComputerUseEngine",
    "Action",
    "ActionType",
    "Element",
    "Platform",
    "Region",
    "ScreenState",
    "StepResult",
    "ComputerUseError",
    "ScreenCaptureError",
    "ActionError",
    "ActionTimeoutError",
    "GroundingError",
    "ElementNotFoundError",
    "ProviderError",
    "ConfigError",
    "PlatformNotSupportedError",
]
