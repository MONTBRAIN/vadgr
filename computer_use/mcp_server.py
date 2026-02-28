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
        "then click/type/scroll to interact with UI elements.\n\n"
        "CRITICAL RULES:\n"
        "1. ALWAYS take a screenshot BEFORE clicking or typing to verify "
        "the target is where you expect it to be.\n"
        "2. ALWAYS take a screenshot AFTER clicking to confirm the action "
        "had the intended effect (correct window opened, right element selected, etc.).\n"
        "3. NEVER click based on assumed coordinates from memory -- always "
        "use the latest screenshot to identify precise coordinates.\n"
        "4. When clicking on a list item, aim for the CENTER of the item's text, "
        "not near its edge, to avoid hitting adjacent items.\n"
        "5. If a click lands on the wrong target, take a screenshot, reassess "
        "coordinates, and retry.\n"
        "6. For REPEATED navigation (opening apps, clicking known menus you've "
        "used 3+ times), use navigate_to or navigate_chain instead of "
        "screenshot+click cycles. These skip LLM roundtrips for cached targets.\n"
        "7. Navigation tools only work for well-cached targets (3+ hits). "
        "For new/unfamiliar targets, use screenshot+click as usual."
    ),
)

_MAX_WIDTH = int(os.environ.get("CU_MAX_WIDTH", "0"))  # 0 = auto-detect

# Coordinate mapping state. Updated after each screenshot.
# Display coords (what the agent sees) get mapped to real screen coords via _to_real().
_scale_x = 1.0
_scale_y = 1.0
_display_w = 0
_display_h = 0
_offset_x = 0  # primary monitor X origin in virtual screen space
_offset_y = 0  # primary monitor Y origin in virtual screen space

_engine = None


def _compute_max_width(real_width: int) -> int:
    """Pick the largest target width that keeps coordinates accurate for vision models.

    Returns the highest standard resolution that is <= the real screen width.
    Standard targets (most universal across vision models): 1024, 1280, 1366.
    """
    targets = [1024, 1280, 1366]
    for t in reversed(targets):
        if real_width >= t:
            return t
    return real_width  # screen is smaller than 1024, no downscale


def _get_engine():
    global _engine, _MAX_WIDTH
    if _engine is None:
        from computer_use.core.engine import ComputerUseEngine
        _engine = ComputerUseEngine()
        logger.info("Engine initialized (platform=%s)", _engine.get_platform().value)
        if _MAX_WIDTH == 0:
            w, _ = _engine.get_screen_size()
            _MAX_WIDTH = _compute_max_width(w)
            logger.info("Auto-detected max width: %d (screen=%d)", _MAX_WIDTH, w)
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
def click(x: int, y: int, element_hint: str = "") -> str:
    """Left-click at screen coordinates (pixels).

    IMPORTANT: Always take a screenshot() first to confirm the target element's
    position. After clicking, take another screenshot() to verify the click
    landed correctly. Aim for the center of the target element.

    element_hint: optional label for the target (e.g. "File menu", "Save button").
    When provided, enables muscle memory -- repeated clicks become faster.
    """
    engine = _get_engine()
    kwargs = {}
    if element_hint:
        kwargs["element_hint"] = element_hint
    engine.click(*_to_real(x, y), **kwargs)
    return f"Clicked at ({x}, {y})"


@mcp.tool()
def double_click(x: int, y: int, element_hint: str = "") -> str:
    """Double-click at screen coordinates.

    element_hint: optional label for muscle memory learning.
    """
    engine = _get_engine()
    kwargs = {}
    if element_hint:
        kwargs["element_hint"] = element_hint
    engine.double_click(*_to_real(x, y), **kwargs)
    return f"Double-clicked at ({x}, {y})"


@mcp.tool()
def right_click(x: int, y: int, element_hint: str = "") -> str:
    """Right-click at screen coordinates.

    element_hint: optional label for muscle memory learning.
    """
    engine = _get_engine()
    kwargs = {}
    if element_hint:
        kwargs["element_hint"] = element_hint
    engine.right_click(*_to_real(x, y), **kwargs)
    return f"Right-clicked at ({x}, {y})"


@mcp.tool()
def move_mouse(x: int, y: int, element_hint: str = "") -> str:
    """Move the mouse without clicking.

    element_hint: optional label for muscle memory learning.
    """
    engine = _get_engine()
    kwargs = {}
    if element_hint:
        kwargs["element_hint"] = element_hint
    engine.move_mouse(*_to_real(x, y), **kwargs)
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


@mcp.tool()
def navigate_to(target_hint: str, target_app: str = "", current_hint: str = "") -> str:
    """Navigate to a cached UI target without screenshots.

    Uses muscle memory cache to click through known navigation paths.
    Only works for targets seen 3+ times. Falls back gracefully --
    if any step fails, returns a message for LLM re-evaluation.

    target_hint: where you want to go (e.g. "message input")
    target_app: app name (e.g. "whatsapp.exe"). Auto-detected if empty.
    current_hint: where you are now. Enables multi-step path finding.
    """
    engine = _get_engine()
    result = engine.navigate_to(
        target_hint=target_hint,
        target_app=target_app,
        current_hint=current_hint,
    )
    if result["stopped"]:
        return (
            f"Navigation stopped: {result['reason']}. "
            f"Completed {result['completed']}/{result['total']} steps. "
            f"Take a screenshot to re-evaluate."
        )
    if result["completed"] == 0:
        return "No navigation steps executed. Take a screenshot and use click instead."
    return (
        f"Navigated {result['completed']}/{result['total']} steps. "
        f"Now at: {result['last_hint']}"
    )


@mcp.tool()
def navigate_chain(hints: list, app_name: str = "") -> str:
    """Execute a sequence of cached clicks without screenshots.

    Each hint in the list is clicked in order using cached positions.
    Stops immediately if any hint is not in cache or if the foreground
    window changes unexpectedly.

    hints: ordered list of element hint strings to click through
    app_name: app name. Auto-detected from foreground window if empty.
    """
    engine = _get_engine()
    # Auto-detect app if not provided -- navigate_chain will also
    # re-detect per step for cross-app flows, but we need an initial value.
    if not app_name:
        fg = engine._get_fg_window()
        if fg and fg.app_name:
            app_name = fg.app_name.lower()
        else:
            app_name = engine.get_platform().value

    hint_strs = [str(h) for h in hints]
    result = engine.navigate_chain(app_name, hint_strs)
    if result["stopped"]:
        return (
            f"Chain stopped: {result['reason']}. "
            f"Completed {result['completed']}/{result['total']} steps. "
            f"Take a screenshot to re-evaluate."
        )
    if result["completed"] == 0:
        return "No steps executed. Take a screenshot and use click instead."
    return (
        f"Chain complete: {result['completed']}/{result['total']} steps. "
        f"Now at: {result['last_hint']}"
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
        help="Max screenshot width in pixels (0=auto, env: CU_MAX_WIDTH)",
    )
    args = parser.parse_args()
    _MAX_WIDTH = args.max_width

    logger.info(
        "Starting Computer Use MCP server (transport=%s, max_width=%s)",
        args.transport,
        _MAX_WIDTH or "auto",
    )

    if args.transport == "sse":
        mcp.settings.port = args.port
        logger.info("SSE server on port %d", args.port)

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
