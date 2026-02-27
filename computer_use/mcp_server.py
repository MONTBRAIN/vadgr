"""MCP server for the computer use engine.

Run: python -m computer_use.mcp_server [--transport stdio|sse] [--max-width 1366]
"""

import argparse
import io
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("computer_use.mcp_server")

from mcp.server.fastmcp import FastMCP, Image
from PIL import Image as PILImage

mcp = FastMCP(
    name="computer-use",
    instructions=(
        "Desktop automation engine. Use screenshot() to see the screen, "
        "then click/type/scroll to interact with UI elements."
    ),
)

_MAX_WIDTH = int(os.environ.get("CU_MAX_WIDTH", "1366"))

# Coordinate mapping state. Updated after each screenshot.
# Display coords (what the agent sees) get mapped to real screen coords via _to_real().
_scale_x = 1.0
_scale_y = 1.0
_display_w = 0
_display_h = 0
_offset_x = 0  # primary monitor X origin in virtual screen space
_offset_y = 0  # primary monitor Y origin in virtual screen space

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from computer_use.core.engine import ComputerUseEngine
        _engine = ComputerUseEngine()
        logger.info("Engine initialized (platform=%s)", _engine.get_platform().value)
    return _engine


def _downscale(png_bytes: bytes, offset_x: int = 0, offset_y: int = 0) -> bytes:
    """Resize screenshot to fit _MAX_WIDTH, update global scale/offset state."""
    global _scale_x, _scale_y, _display_w, _display_h, _offset_x, _offset_y

    _offset_x = offset_x
    _offset_y = offset_y

    img = PILImage.open(io.BytesIO(png_bytes))
    real_w, real_h = img.size

    if real_w <= _MAX_WIDTH:
        _scale_x, _scale_y = 1.0, 1.0
        _display_w, _display_h = real_w, real_h
        return png_bytes

    ratio = _MAX_WIDTH / real_w
    new_w = _MAX_WIDTH
    new_h = int(real_h * ratio)

    _scale_x = real_w / new_w
    _scale_y = real_h / new_h
    _display_w, _display_h = new_w, new_h

    img = img.resize((new_w, new_h), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    logger.debug("Downscaled %dx%d -> %dx%d (scale %.2fx)", real_w, real_h, new_w, new_h, _scale_x)
    return buf.getvalue()


def _to_real(x: int, y: int) -> tuple[int, int]:
    """Convert display coordinates to absolute screen coordinates."""
    return int(x * _scale_x) + _offset_x, int(y * _scale_y) + _offset_y


def _from_real(x: int, y: int) -> tuple[int, int]:
    """Convert absolute screen coordinates to display coordinates."""
    return int((x - _offset_x) / _scale_x), int((y - _offset_y) / _scale_y)


@mcp.tool()
def screenshot() -> Image:
    """Capture the full virtual screen (all monitors). Returns PNG image.

    IMPORTANT: The image pixel dimensions are the real screen coordinates.
    Use get_screen_size() to know the coordinate space. When the image is
    displayed smaller in your UI, you must still pass coordinates in the
    original pixel space (e.g. if the screen is 4096x1440, a button visually
    at the center is at approximately x=2048, y=720).
    """
    engine = _get_engine()
    state = engine.screenshot()
    data = _downscale(state.image_bytes, state.offset_x, state.offset_y)
    return Image(data=data, format="png")


@mcp.tool()
def screenshot_region(x: int, y: int, width: int, height: int) -> Image:
    """Capture a rectangular region of the screen. Coordinates are in real screen pixels."""
    engine = _get_engine()
    rx, ry = _to_real(x, y)
    rw, rh = int(width * _scale_x), int(height * _scale_y)
    state = engine.screenshot_region(rx, ry, rw, rh)
    return Image(data=_downscale(state.image_bytes), format="png")


@mcp.tool()
def click(x: int, y: int) -> str:
    """Left-click at screen coordinates (pixels)."""
    engine = _get_engine()
    engine.click(*_to_real(x, y))
    return f"Clicked at ({x}, {y})"


@mcp.tool()
def double_click(x: int, y: int) -> str:
    """Double-click at screen coordinates."""
    engine = _get_engine()
    engine.double_click(*_to_real(x, y))
    return f"Double-clicked at ({x}, {y})"


@mcp.tool()
def right_click(x: int, y: int) -> str:
    """Right-click at screen coordinates."""
    engine = _get_engine()
    engine.right_click(*_to_real(x, y))
    return f"Right-clicked at ({x}, {y})"


@mcp.tool()
def move_mouse(x: int, y: int) -> str:
    """Move the mouse without clicking."""
    engine = _get_engine()
    engine.move_mouse(*_to_real(x, y))
    return f"Mouse moved to ({x}, {y})"


@mcp.tool()
def scroll(x: int, y: int, amount: int) -> str:
    """Scroll at position. Positive = up, negative = down."""
    engine = _get_engine()
    engine.scroll(*_to_real(x, y), amount)
    direction = "up" if amount > 0 else "down"
    return f"Scrolled {direction} {abs(amount)} notches at ({x}, {y})"


@mcp.tool()
def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> str:
    """Drag from one point to another."""
    engine = _get_engine()
    engine.drag(*_to_real(start_x, start_y), *_to_real(end_x, end_y), duration)
    return f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"


@mcp.tool()
def type_text(text: str) -> str:
    """Type text into the focused field."""
    engine = _get_engine()
    engine.type_text(text)
    preview = text[:50] + "..." if len(text) > 50 else text
    return f"Typed: {preview}"


@mcp.tool()
def key_press(keys: str) -> str:
    """Press a key combo, e.g. "ctrl+c", "alt+tab", "enter"."""
    engine = _get_engine()
    key_list = [k.strip() for k in keys.split("+")]
    engine.key_press(*key_list)
    return f"Pressed: {keys}"


@mcp.tool()
def get_screen_size() -> str:
    """Returns "WIDTHxHEIGHT" in pixels."""
    engine = _get_engine()
    w, h = engine.get_screen_size()
    return f"{w}x{h}"


@mcp.tool()
def get_platform() -> str:
    """Returns detected platform: wsl2, linux, windows, or macos."""
    engine = _get_engine()
    return engine.get_platform().value


@mcp.tool()
def get_platform_info() -> dict:
    """Returns platform details + accessibility info."""
    engine = _get_engine()
    return engine.get_platform_info()


@mcp.tool()
def find_element(description: str) -> str:
    """Find a UI element by description, e.g. "Save button". Returns position or not found."""
    engine = _get_engine()
    element = engine.find_element(description)
    if element is None:
        return f"Element not found: {description}"
    cx, cy = element.region.center
    dx, dy = _from_real(cx, cy)
    return (
        f"Found '{element.name}' (role={element.role}) at ({dx}, {dy}), "
        f"confidence={element.confidence:.2f}"
    )


def main():
    global _MAX_WIDTH

    parser = argparse.ArgumentParser(description="Computer Use MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=_MAX_WIDTH,
        help="Max screenshot width in pixels (default: 1366, env: CU_MAX_WIDTH)",
    )
    args = parser.parse_args()
    _MAX_WIDTH = args.max_width

    logger.info(
        "Starting Computer Use MCP server (transport=%s, max_width=%d)",
        args.transport,
        _MAX_WIDTH,
    )

    if args.transport == "sse":
        mcp.settings.port = args.port
        logger.info("SSE server on port %d", args.port)

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
