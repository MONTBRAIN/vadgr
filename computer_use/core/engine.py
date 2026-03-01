"""Main engine facade -- the public API for the computer use engine."""

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import yaml

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ConfigError, PlatformNotSupportedError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.spatial_cache import MuscleMemoryCache, CacheEntry
from computer_use.core.types import (
    Action,
    Element,
    ForegroundWindow,
    Platform,
    Region,
    ScreenState,
    StepResult,
)
from computer_use.platform.base import PlatformBackend
from computer_use.platform.detect import detect_platform, get_backend

logger = logging.getLogger("computer_use.engine")

# Percentage grid resolution for Layer 1 synthetic hints.
# 3% grid = ~33 buckets per axis, balances precision vs. tolerance.
_PCT_BUCKET = 3

# TTL for foreground window cache (seconds).
_FG_WINDOW_TTL = 0.05  # 50ms

# Apps that are remote desktop shells -- the foreground window is a container
# for a remote session, NOT the actual app the user is interacting with.
# When detected, we fall back to platform-level caching (no window context).
# Navigation batch timing (seconds).
# Uses poll-until-change pattern (like AutoHotkey WinWaitActive / pywinauto wait).
_NAV_POLL_INTERVAL = 0.05      # 50ms: fg window poll frequency
_NAV_SAME_APP_MIN = 0.05       # 50ms: minimum dwell (covers same-app transitions fully)
_NAV_CROSS_APP_MAX = 1.0       # 1s: ceiling for fresh app launches (Notepad warm ~400-700ms)
_NAV_CROSS_APP_SETTLE = 0.08   # 80ms: settle after fg changes (window finishes painting)
_NAV_POST_CLICK_DELAY = 0.05   # 50ms: final step dwell (already at destination)

_PASSTHROUGH_APPS = frozenset({
    "mstsc.exe",        # Windows Remote Desktop
    "msrdc.exe",        # Modern Remote Desktop client
    "vmconnect.exe",    # Hyper-V VM Connect
    "vmware-vmx.exe",   # VMware Workstation
    "virtualboxvm.exe", # VirtualBox
    "vncviewer.exe",    # VNC Viewer
    "tvnviewer.exe",    # TightVNC
    "putty.exe",        # PuTTY (terminal, no spatial UI)
    "wezterm-gui.exe",  # Terminal (scrolling content, bad for spatial)
    "windowsterminal.exe",  # Windows Terminal
})


@dataclass
class _CacheContext:
    """Resolved cache context for a mouse action."""
    app_name: str       # real app name (e.g. "notepad.exe") or platform fallback
    hint: str           # element hint for cache key (may be synthetic "@300,200")
    cache_x: int        # window-relative X for cache storage
    cache_y: int        # window-relative Y for cache storage
    layer: int          # which layer resolved: 1, 2, or 3

# Default cache location (platform-appropriate).
_CACHE_DIR_ENV = "AGENT_FORGE_DATA"


def _default_cache_path() -> str:
    """Pick a cross-platform data directory for the muscle memory DB."""
    env = os.environ.get(_CACHE_DIR_ENV)
    if env:
        base = env
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", "."), "AgentForge")
    elif os.environ.get("XDG_DATA_HOME"):
        base = os.path.join(os.environ["XDG_DATA_HOME"], "agent-forge")
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share", "agent-forge")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "muscle_memory.db")


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

        # Muscle memory cache (cross-platform).
        db_path = _default_cache_path()
        self._cache = MuscleMemoryCache(db_path)
        self._last_hint: str = ""
        self._last_app: str = ""
        logger.info("Muscle memory cache: %s", db_path)

        # Foreground window cache (TTL-based).
        self._fg_window: Optional[ForegroundWindow] = None
        self._fg_window_ts: float = 0.0

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

    # --- 3-Layer Cache Resolution ---

    def _get_fg_window(self) -> Optional[ForegroundWindow]:
        """Get foreground window info with TTL cache."""
        now = time.monotonic()
        if now - self._fg_window_ts < _FG_WINDOW_TTL and self._fg_window is not None:
            return self._fg_window
        try:
            self._fg_window = self._backend.get_foreground_window()
        except Exception:
            self._fg_window = None
        self._fg_window_ts = now
        return self._fg_window

    def _resolve_cache_context(
        self, element_hint: Optional[str], x: int, y: int
    ) -> _CacheContext:
        """3-layer resolution for cache context.

        Layer 3: Model-provided element_hint (highest precision).
        Layer 2: Accessibility API auto-detect (role:name).
        Layer 1: App name + percentage-bucketed window-relative coords.

        Passthrough apps (RDP, VNC, terminals) are excluded — their
        foreground window is a shell, not the actual UI being controlled.
        """
        fg = self._get_fg_window()

        # Exclude passthrough apps — treat as if no window info
        if fg and fg.app_name and fg.app_name.lower() in _PASSTHROUGH_APPS:
            fg = None

        # Real app name from foreground window, or platform fallback
        if fg and fg.app_name:
            app_name = fg.app_name.lower()
        else:
            app_name = self._platform.value

        # Convert to window-relative coords (survives window moves)
        if fg and fg.width > 0 and fg.height > 0:
            cache_x = x - fg.x + self._vs_offset_x
            cache_y = y - fg.y + self._vs_offset_y
        else:
            # No window info — use absolute coords as fallback
            cache_x = x
            cache_y = y

        # Layer 3: caller-provided hint
        if element_hint:
            return _CacheContext(
                app_name=app_name, hint=element_hint,
                cache_x=cache_x, cache_y=cache_y, layer=3,
            )

        # Layer 2: accessibility API
        locator = self._get_locator()
        if locator is not None:
            try:
                ax, ay = self._to_abs(x, y)
                el = locator.find_element_at(ax, ay)
                if el and el.name:
                    hint = f"{el.role}:{el.name}"
                    return _CacheContext(
                        app_name=app_name, hint=hint,
                        cache_x=cache_x, cache_y=cache_y, layer=2,
                    )
            except Exception:
                pass

        # Layer 1: percentage-bucketed coords (survives resize)
        if fg and fg.width > 0 and fg.height > 0:
            pct_x = int(cache_x * 100 / fg.width)
            pct_y = int(cache_y * 100 / fg.height)
            bx = (pct_x // _PCT_BUCKET) * _PCT_BUCKET
            by = (pct_y // _PCT_BUCKET) * _PCT_BUCKET
            hint = f"@{bx}%,{by}%"
        else:
            # No window dims — use pixel coords with a fixed bucket
            bx = (cache_x // 25) * 25
            by = (cache_y // 25) * 25
            hint = f"@{bx},{by}"
        return _CacheContext(
            app_name=app_name, hint=hint,
            cache_x=cache_x, cache_y=cache_y, layer=1,
        )

    def _cache_lookup(self, ctx: _CacheContext) -> int:
        """Look up in muscle memory. Returns hit_count (0 on miss)."""
        entry = self._cache.lookup(
            ctx.app_name, ctx.hint, ctx.cache_x, ctx.cache_y
        )
        return entry.hit_count if entry else 0

    def _cache_record(self, ctx: _CacheContext) -> None:
        """Record a successful interaction in muscle memory."""
        self._cache.record_hit(
            ctx.app_name, ctx.hint, ctx.cache_x, ctx.cache_y,
            prev_hint=self._last_hint,
            prev_app=self._last_app,
        )
        self._last_hint = ctx.hint
        self._last_app = ctx.app_name

    def click(self, x: int, y: int, element_hint: str = None) -> None:
        """Left-click at screenshot coordinates (auto-translated for multi-monitor)."""
        ctx = self._resolve_cache_context(element_hint, x, y)
        ax, ay = self._to_abs(x, y)
        hit_count = self._cache_lookup(ctx)
        if hit_count > 0:
            try:
                self._executor.click(ax, ay, hit_count=hit_count)
            except TypeError:
                self._executor.click(ax, ay)
        else:
            self._executor.click(ax, ay)
        self._cache_record(ctx)

    def double_click(self, x: int, y: int, element_hint: str = None) -> None:
        """Double-click at screenshot coordinates."""
        ctx = self._resolve_cache_context(element_hint, x, y)
        ax, ay = self._to_abs(x, y)
        hit_count = self._cache_lookup(ctx)
        if hit_count > 0:
            try:
                self._executor.double_click(ax, ay, hit_count=hit_count)
            except TypeError:
                self._executor.double_click(ax, ay)
        else:
            self._executor.double_click(ax, ay)
        self._cache_record(ctx)

    def right_click(self, x: int, y: int, element_hint: str = None) -> None:
        """Right-click at screenshot coordinates."""
        ctx = self._resolve_cache_context(element_hint, x, y)
        ax, ay = self._to_abs(x, y)
        hit_count = self._cache_lookup(ctx)
        if hit_count > 0:
            try:
                self._executor.click(ax, ay, button="right", hit_count=hit_count)
            except TypeError:
                self._executor.click(ax, ay, button="right")
        else:
            self._executor.click(ax, ay, button="right")
        self._cache_record(ctx)

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

    def move_mouse(self, x: int, y: int, element_hint: str = None) -> None:
        """Move mouse without clicking."""
        ctx = self._resolve_cache_context(element_hint, x, y)
        ax, ay = self._to_abs(x, y)
        hit_count = self._cache_lookup(ctx)
        if hit_count > 0:
            try:
                self._executor.move_mouse(ax, ay, hit_count=hit_count)
            except TypeError:
                self._executor.move_mouse(ax, ay)
        else:
            self._executor.move_mouse(ax, ay)
        self._cache_record(ctx)

    # --- Navigation Batch API ---

    def _cache_to_screen(
        self, cache_x: float, cache_y: float
    ) -> Optional[tuple[int, int]]:
        """Convert window-relative cache coords to absolute screen coords.

        Uses the current foreground window position. Returns None if
        no foreground window is available.
        """
        fg = self._get_fg_window()
        if fg is None or fg.width <= 0:
            return None
        screen_x = int(fg.x + cache_x) - self._vs_offset_x
        screen_y = int(fg.y + cache_y) - self._vs_offset_y
        return screen_x, screen_y

    def _wait_for_nav_transition(self, prev_app: str) -> None:
        """Wait for the UI to settle between navigation steps.

        Uses a poll-until-change pattern (like AutoHotkey WinWaitActive):
        - Same-app: waits _NAV_SAME_APP_MIN then returns (~55ms total).
        - Cross-app: polls fg window every _NAV_POLL_INTERVAL until it
          changes, then adds _NAV_CROSS_APP_SETTLE settle time.
        - Timeout: gives up after _NAV_CROSS_APP_MAX (~1s). The next
          step's cache lookup will fail naturally on app mismatch.
        """
        start = time.monotonic()

        # Mandatory minimum dwell -- covers same-app transitions fully
        time.sleep(_NAV_SAME_APP_MIN)

        # Check if fg window already changed (fast cross-app transition)
        self._fg_window_ts = 0.0
        fg = self._get_fg_window()
        new_app = (fg.app_name.lower() if (fg and fg.app_name) else "")

        if new_app and new_app != prev_app:
            # Cross-app transition already complete, brief settle and return
            time.sleep(_NAV_CROSS_APP_SETTLE)
            return

        if new_app == prev_app:
            # Same app still in foreground -- either same-app step (done)
            # or cross-app launch still in progress. Poll until change or timeout.
            max_end = start + _NAV_CROSS_APP_MAX
            while time.monotonic() < max_end:
                time.sleep(_NAV_POLL_INTERVAL)
                self._fg_window_ts = 0.0
                fg = self._get_fg_window()
                new_app = (fg.app_name.lower() if (fg and fg.app_name) else "")
                if new_app and new_app != prev_app:
                    time.sleep(_NAV_CROSS_APP_SETTLE)
                    return

        # Timeout or no fg info -- proceed anyway; next step handles failure

    def navigate_chain(
        self,
        app_name: str,
        hints: list[str],
        verify_fg: bool = True,
    ) -> dict:
        """Execute a sequence of cached clicks without LLM verification.

        Supports cross-app flows: if a single app_name is given, it is used
        for the first step only. After each click, the foreground window is
        polled via _wait_for_nav_transition() and subsequent lookups use the
        current foreground app. This allows chains like
        ["Windows Search", "Notepad app", "text area"] to work even though
        each hint lives under a different app.

        For each hint:
        1. Determine current app (from fg window or parameter)
        2. Look up in cache (strict nav thresholds)
        3. Convert to screen coords
        4. Click with muscle memory adaptation
        5. Smart wait for UI transition (adaptive polling)

        Returns dict with:
        - completed: number of steps executed
        - total: total steps requested
        - last_hint: last successfully clicked hint
        - stopped: whether it stopped early
        - reason: why it stopped (if stopped)
        """
        if not hints:
            return {
                "completed": 0, "total": 0, "last_hint": "",
                "stopped": False, "reason": "",
            }

        completed = 0
        last_hint = ""
        current_app = app_name.lower() if app_name else ""

        for i, hint in enumerate(hints):
            # Step 1: determine current app from foreground window
            if i > 0 or not current_app:
                self._fg_window_ts = 0.0
                fg = self._get_fg_window()
                if fg and fg.app_name:
                    current_app = fg.app_name.lower()

            if not current_app:
                current_app = self._platform.value

            # Step 2: strict cache lookup under current app
            # lookup_for_nav falls back to hint-only search across all apps
            # when exact app+hint misses (handles wsl2 app name mismatch).
            entry = self._cache.lookup_for_nav(current_app, hint)
            if entry is None:
                return {
                    "completed": completed, "total": len(hints),
                    "last_hint": last_hint, "stopped": True,
                    "reason": f"cache miss on step {i}: '{hint}' "
                              f"(app='{current_app}')",
                }

            # Adopt the entry's real app_name for coord conversion and
            # subsequent steps. This is critical when the fallback found
            # the entry under a different app (e.g. 'notepad.exe' instead
            # of the auto-detected 'wsl2').
            if entry.app_name and entry.app_name.lower() != current_app:
                current_app = entry.app_name.lower()

            # Step 3: convert cache coords to screen coords
            coords = self._cache_to_screen(entry.x, entry.y)
            if coords is None:
                coords = (int(entry.x), int(entry.y))

            sx, sy = coords

            # Step 4: click with muscle memory adaptation
            ax, ay = self._to_abs(sx, sy)
            try:
                self._executor.click(ax, ay, hit_count=entry.hit_count)
            except TypeError:
                self._executor.click(ax, ay)

            # Record the hit and update sequence tracking
            ctx = _CacheContext(
                app_name=current_app, hint=hint,
                cache_x=int(entry.x), cache_y=int(entry.y), layer=3,
            )
            self._cache_record(ctx)

            completed += 1
            last_hint = hint

            # Step 5: smart wait for UI transition
            if i < len(hints) - 1:
                self._wait_for_nav_transition(current_app)
            else:
                time.sleep(_NAV_POST_CLICK_DELAY)

        return {
            "completed": completed, "total": len(hints),
            "last_hint": last_hint, "stopped": False, "reason": "",
        }

    def navigate_to(
        self,
        target_hint: str,
        target_app: str = "",
        current_hint: str = "",
    ) -> dict:
        """Navigate to a cached UI target, finding the path automatically.

        If current_hint is provided, uses BFS path finding through the
        sequences and cross_sequences tables. Path finding works across
        app boundaries automatically.

        Otherwise, attempts a direct cached click.

        Returns same dict as navigate_chain().
        """
        # Auto-detect app from foreground window
        if not target_app:
            fg = self._get_fg_window()
            if fg and fg.app_name:
                target_app = fg.app_name.lower()
            else:
                target_app = self._platform.value

        # Try path finding if we know where we are
        if current_hint:
            path = self._cache.find_path(target_app, current_hint, target_hint)
            if path and len(path) > 1:
                # path is list of (app, hint) tuples; skip first (current pos).
                # Extract just the hints -- navigate_chain auto-detects app
                # per step via fg window polling.
                step_hints = [hint for _app, hint in path[1:]]
                # Use the app from the first step as initial app_name
                first_app = path[1][0]
                return self.navigate_chain(first_app, step_hints)

        # Direct: just try clicking the target
        return self.navigate_chain(target_app, [target_hint])

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
