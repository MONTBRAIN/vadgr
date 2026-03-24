"""MCP server for the computer use engine.

Run: python -m computer_use.mcp_server [--transport stdio|sse] [--max-width 1366]
"""

import argparse
import io
import logging
import os
import sys

_DEBUG = os.environ.get("AGENT_FORGE_DEBUG", "") == "1"

logging.basicConfig(
    level=logging.DEBUG if _DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("computer_use.mcp_server")
_DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".debug")
_debug_counter = 0


def _debug_save(data: bytes, prefix: str = "screenshot") -> None:
    """Save PNG to .debug/ when AGENT_FORGE_DEBUG=1."""
    if not _DEBUG:
        return
    global _debug_counter
    os.makedirs(_DEBUG_DIR, exist_ok=True)
    _debug_counter += 1
    path = os.path.join(_DEBUG_DIR, f"{prefix}_{_debug_counter:04d}.png")
    with open(path, "wb") as f:
        f.write(data)
    logger.info("Debug screenshot saved: %s", path)

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
        "For new/unfamiliar targets, use screenshot+click as usual.\n"
        "8. For REPEATED multi-step workflows (save file, new tab, copy-paste), "
        "use create_template to define them once, then execute_template to replay. "
        "Templates support click, type_text, key_press, and wait actions."
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
        cache_enabled = os.environ.get("AGENT_FORGE_CACHE_ENABLED", "1") != "0"
        _engine = ComputerUseEngine(cache_enabled=cache_enabled)
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

    IMPORTANT: The image pixel dimensions ARE the coordinate space for all
    tools (click, screenshot_region, etc.). Use get_screen_size() to know
    the dimensions. If the image is 1366x853, coordinates range from
    (0,0) to (1366,853).
    """
    engine = _get_engine()
    state = engine.screenshot()
    data = _downscale(state.image_bytes, state.offset_x, state.offset_y)
    _debug_save(data, "screenshot")
    return Image(data=data, format="png")


@mcp.tool()
def screenshot_region(x: int, y: int, width: int, height: int) -> Image:
    """Capture a rectangular region of the screen. Coordinates are in display space."""
    engine = _get_engine()
    rx, ry = _to_real(x, y)
    rw, rh = int(width * _scale_x), int(height * _scale_y)
    state = engine.screenshot_region(rx, ry, rw, rh)
    # Don't pass through _downscale — it would clobber the global scale factors
    # that screenshot() established. Just return the raw region bytes.
    _debug_save(state.image_bytes, "region")
    return Image(data=state.image_bytes, format="png")


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
    """Returns "WIDTHxHEIGHT" in display pixels (the coordinate space for all tools)."""
    if _display_w > 0 and _display_h > 0:
        return f"{_display_w}x{_display_h}"
    # No screenshot taken yet — compute what the display size would be.
    engine = _get_engine()
    w, h = engine.get_screen_size()
    if w <= _MAX_WIDTH:
        return f"{w}x{h}"
    ratio = _MAX_WIDTH / w
    return f"{_MAX_WIDTH}x{int(h * ratio)}"


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


@mcp.tool()
def create_template(name: str, app_name: str, steps: list) -> str:
    """Define a reusable action template for multi-step workflows.

    name: unique template name (e.g. "save-as-txt", "new-document")
    app_name: the application this template runs in (e.g. "notepad.exe")
    steps: ordered list of step dicts, each with:
        - action: "click", "type_text", "key_press", or "wait"
        - hint: element_hint for click steps (e.g. "File menu")
        - text: text for type_text, key combo for key_press (e.g. "ctrl+s")
        - wait_ms: pause after step in ms (default 100)

    Example step: {"action": "key_press", "text": "ctrl+s", "wait_ms": 200}
    """
    engine = _get_engine()
    if engine._cache is None:
        return "Error: cache is disabled, templates unavailable"
    step_dicts = [dict(s) if not isinstance(s, dict) else s for s in steps]
    try:
        tid = engine._cache.create_template(name, app_name, step_dicts)
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error creating template: {e}"
    return f"Template '{name}' created (id={tid}, {len(step_dicts)} steps)"


@mcp.tool()
def execute_template(name: str) -> str:
    """Execute a named action template (multi-step workflow without screenshots).

    Replays all steps in the template: clicks use cached positions,
    type_text types strings, key_press sends key combos.
    Returns completion status.
    """
    engine = _get_engine()
    result = engine.execute_template(name)
    if result["stopped"]:
        return (
            f"Template stopped: {result['reason']}. "
            f"Completed {result['completed']}/{result['total']} steps. "
            f"Take a screenshot to re-evaluate."
        )
    return (
        f"Template '{name}' complete: {result['completed']}/{result['total']} steps."
    )


@mcp.tool()
def list_templates(app_name: str = "") -> str:
    """List available action templates, optionally filtered by app.

    Returns a summary of each template with name, app, use count, and step count.
    """
    engine = _get_engine()
    if engine._cache is None:
        return "No templates (cache is disabled)."
    templates = engine._cache.list_templates(app_name=app_name or None)
    if not templates:
        return "No templates found."
    lines = []
    for t in templates:
        lines.append(
            f"  {t['name']} ({t['app_name']}) -- "
            f"{t['steps_count']} steps, used {t['use_count']}x"
        )
    return f"Templates ({len(templates)}):\n" + "\n".join(lines)


@mcp.tool()
def delete_template(name: str) -> str:
    """Delete an action template by name."""
    engine = _get_engine()
    if engine._cache is None:
        return "Error: cache is disabled, templates unavailable"
    if engine._cache.delete_template(name):
        return f"Template '{name}' deleted."
    return f"Template '{name}' not found."


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
