"""Action execution via the bridge daemon."""

import logging

from computer_use.bridge.client import BridgeClient, BridgeError
from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError

logger = logging.getLogger("computer_use.bridge.actions")


class BridgeActionExecutor(ActionExecutor):
    """Implements ActionExecutor by delegating to the bridge daemon over TCP.

    Accepts an optional *fallback* ActionExecutor (typically WSL2ActionExecutor).
    When the bridge raises an error for text-input methods (type_text, key_press),
    the fallback executor is tried before propagating the failure.
    """

    def __init__(self, client: BridgeClient, fallback: ActionExecutor | None = None):
        self._client = client
        self._fallback = fallback

    def _act(self, method: str, params: dict) -> None:
        try:
            self._client.call(method, params, timeout=10.0)
        except BridgeError as e:
            raise ActionError(f"Bridge {method} failed: {e}") from e

    def move_mouse(self, x: int, y: int, hit_count: int = 0) -> None:
        params = {"x": x, "y": y}
        if hit_count > 0:
            params["hit_count"] = hit_count
        self._act("move_mouse", params)

    def click(self, x: int, y: int, button: str = "left", hit_count: int = 0) -> None:
        params = {"x": x, "y": y, "button": button}
        if hit_count > 0:
            params["hit_count"] = hit_count
        self._act("click", params)

    def double_click(self, x: int, y: int, hit_count: int = 0) -> None:
        params = {"x": x, "y": y}
        if hit_count > 0:
            params["hit_count"] = hit_count
        self._act("double_click", params)

    def type_text(self, text: str) -> None:
        try:
            self._act("type_text", {"text": text})
        except ActionError:
            if self._fallback is not None:
                logger.warning("Bridge type_text failed, using PowerShell fallback")
                self._fallback.type_text(text)
            else:
                raise

    def key_press(self, keys: list[str]) -> None:
        try:
            self._act("key_press", {"keys": keys})
        except ActionError:
            if self._fallback is not None:
                logger.warning("Bridge key_press failed, using PowerShell fallback")
                self._fallback.key_press(keys)
            else:
                raise

    def scroll(self, x: int, y: int, amount: int) -> None:
        self._act("scroll", {"x": x, "y": y, "amount": amount})

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
        hit_count: int = 0,
    ) -> None:
        params = {
            "start_x": start_x,
            "start_y": start_y,
            "end_x": end_x,
            "end_y": end_y,
            "duration": duration,
        }
        if hit_count > 0:
            params["hit_count"] = hit_count
        self._act("drag", params)
