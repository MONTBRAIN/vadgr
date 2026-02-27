"""Action execution via the bridge daemon."""

from computer_use.bridge.client import BridgeClient, BridgeError
from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError


class BridgeActionExecutor(ActionExecutor):
    """Implements ActionExecutor by delegating to the bridge daemon over TCP."""

    def __init__(self, client: BridgeClient):
        self._client = client

    def _act(self, method: str, params: dict) -> None:
        try:
            self._client.call(method, params, timeout=10.0)
        except BridgeError as e:
            raise ActionError(f"Bridge {method} failed: {e}") from e

    def move_mouse(self, x: int, y: int) -> None:
        self._act("move_mouse", {"x": x, "y": y})

    def click(self, x: int, y: int, button: str = "left") -> None:
        self._act("click", {"x": x, "y": y, "button": button})

    def double_click(self, x: int, y: int) -> None:
        self._act("double_click", {"x": x, "y": y})

    def type_text(self, text: str) -> None:
        self._act("type_text", {"text": text})

    def key_press(self, keys: list[str]) -> None:
        self._act("key_press", {"keys": keys})

    def scroll(self, x: int, y: int, amount: int) -> None:
        self._act("scroll", {"x": x, "y": y, "amount": amount})

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        self._act(
            "drag",
            {
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "duration": duration,
            },
        )
