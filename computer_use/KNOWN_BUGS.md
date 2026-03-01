# Known Bugs

## Fixed

### 1. screenshot_region clobbers global scale factors
- **Found**: 2026-03-01
- **Impact**: After any `screenshot_region()` call, all subsequent `click()` calls landed at completely wrong positions (e.g., clicking at real pixel 480 instead of scaled 1349)
- **Root cause**: `screenshot_region()` passed its small region image through `_downscale()`, which reset `_scale_x`/`_scale_y` to 1.0 (since region < MAX_WIDTH). All action tools use `_to_real()` which depends on those globals.
- **Fix**: `screenshot_region()` no longer calls `_downscale()` — returns raw region bytes directly
- **Tests**: `TestScreenshotRegionScalePreservation` (5 tests) in `test_mcp_server.py`

### 2. get_screen_size returned real pixels instead of display pixels
- **Found**: 2026-03-01
- **Impact**: Reported 3840x2400 but all tools expected 1366x853 display coordinates. LLM used wrong coordinate space.
- **Root cause**: `get_screen_size()` called `engine.get_screen_size()` which returns real screen dims, but all tools work in downscaled display space.
- **Fix**: Returns display dims computed from `_MAX_WIDTH` (or cached `_display_w`/`_display_h` after first screenshot)
- **Tests**: 3 tests in `TestInfoTools` in `test_mcp_server.py`

## Open

### 3. Text selection is unreliable
- **Found**: 2026-02
- **Symptom**: Selecting text in applications (e.g., click-drag to highlight) is imprecise. The start/end coordinates don't always land at the right character positions.
- **Status**: Not yet investigated deeply

### 4. Layer 2 returns empty names for WinUI3/XAML toolbar elements
- **Found**: 2026-03-01
- **Symptom**: Notepad toolbar buttons (Bold, Italic, File, Edit, Settings) and Explorer sidebar items (Downloads, Documents) fall to Layer 1 despite child-walking finding the correct element at the coordinates. The UIA `.Name` property is empty for these WinUI3/XAML controls.
- **Affected apps**: New Notepad (WinUI3), File Explorer (WinUI3 command bar + navigation pane items)
- **Not affected**: Calculator (Win32 UIA, all buttons have names), classic Win32 apps
- **Workaround**: Layer 1 (pct-bucketed coords) handles these correctly. Clicks still land, just cached with `@45%,9%` instead of semantic hints.
- **Potential fix**: Fall back to `.AutomationId`, `.HelpText`, or `.ClassName` when `.Name` is empty. Many WinUI3 controls expose `AutomationId` (e.g., `"BoldButton"`) or `HelpText` (e.g., `"Bold (Ctrl+B)"`) even when `.Name` is blank. Alternatively, the native bridge daemon with `IUIAutomation6` COM interface has better WinUI3 support.
- **Status**: Open. Layer 1 fallback works, semantic caching deferred to property-fallback or daemon path.

### 5. First click in a session may miss Layer 2 (DPI initialization)
- **Found**: 2026-03-01
- **Symptom**: The very first click after MCP server start sometimes falls to Layer 1 even for elements with good UIA names (e.g., Calculator buttons). Subsequent clicks work.
- **Root cause**: `SetProcessDPIAware()` is called inside the PowerShell script. On the first invocation in a fresh persistent PowerShell session, the DPI context may not take effect until after the `FromPoint()` call.
- **Workaround**: None needed; only affects first click per session. All subsequent clicks are DPI-aware.
- **Status**: Open. Low impact (1 click per session).

### 6. Vision struggles with small/dense UI elements
- **Found**: 2026-03-01
- **Symptom**: LLM cannot reliably identify individual stickers, small icons, or dense grid items from screenshots. Zooming in via `screenshot_region` helps but adds roundtrips and the region coordinates themselves can be imprecise.
- **Status**: Inherent vision model limitation. Could potentially be improved with better region capture or element-level accessibility data for sticker grids.
