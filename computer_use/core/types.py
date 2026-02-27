"""Shared data types for the computer use engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class Platform(Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    WSL2 = "wsl2"


class ActionType(Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE_TEXT = "type_text"
    KEY_PRESS = "key_press"
    SCROLL = "scroll"
    MOVE = "move"
    DRAG = "drag"
    WAIT = "wait"


@dataclass(frozen=True)
class Region:
    """A rectangular region on screen."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True)
class Element:
    """A UI element found by grounding."""

    name: str
    role: str  # button, text_field, menu_item, etc.
    region: Region
    confidence: float  # 0.0 to 1.0
    source: str  # "accessibility" or "vision"
    properties: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Action:
    """A single action to execute on the desktop."""

    action_type: ActionType
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None  # for TYPE_TEXT
    keys: Optional[list[str]] = None  # for KEY_PRESS, e.g. ["ctrl", "c"]
    scroll_amount: int = 0  # positive = up, negative = down
    duration: float = 0.0  # for WAIT or DRAG animation
    target_x: Optional[int] = None  # for DRAG end position
    target_y: Optional[int] = None  # for DRAG end position


@dataclass
class ScreenState:
    """A captured screenshot with metadata."""

    image_bytes: bytes  # image bytes (PNG or JPEG)
    width: int
    height: int
    timestamp: float = field(default_factory=time.time)
    scale_factor: float = 1.0  # for HiDPI displays
    offset_x: int = 0  # virtual screen X origin (for multi-monitor)
    offset_y: int = 0  # virtual screen Y origin (for multi-monitor)


@dataclass
class StepResult:
    """Result of one iteration of the core loop."""

    action_taken: Action
    screenshot_before: ScreenState
    screenshot_after: ScreenState
    success: bool
    reasoning: str  # LLM explanation (autonomous mode)
    error: Optional[str] = None
    elements_found: list[Element] = field(default_factory=list)
