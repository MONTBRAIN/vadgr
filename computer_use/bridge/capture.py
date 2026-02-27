"""Screenshot capture via the bridge daemon."""

import base64

from computer_use.bridge.client import BridgeClient, BridgeError
from computer_use.core.errors import ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import Region, ScreenState


class BridgeScreenCapture(ScreenCapture):
    """Implements ScreenCapture by delegating to the bridge daemon over TCP."""

    def __init__(self, client: BridgeClient, quality: int = 85):
        self._client = client
        self._quality = quality

    def capture_full(self) -> ScreenState:
        try:
            result = self._client.call(
                "screenshot_full", {"quality": self._quality}, timeout=5.0
            )
        except BridgeError as e:
            raise ScreenCaptureError(f"Bridge screenshot failed: {e}") from e

        return ScreenState(
            image_bytes=base64.b64decode(result["image_b64"]),
            width=result["width"],
            height=result["height"],
            scale_factor=result.get("scale_factor", 1.0),
            offset_x=result.get("offset_x", 0),
            offset_y=result.get("offset_y", 0),
        )

    def capture_region(self, region: Region) -> ScreenState:
        try:
            result = self._client.call(
                "screenshot_region",
                {
                    "x": region.x,
                    "y": region.y,
                    "width": region.width,
                    "height": region.height,
                    "quality": self._quality,
                },
                timeout=5.0,
            )
        except BridgeError as e:
            raise ScreenCaptureError(f"Bridge region screenshot failed: {e}") from e

        return ScreenState(
            image_bytes=base64.b64decode(result["image_b64"]),
            width=result["width"],
            height=result["height"],
            scale_factor=result.get("scale_factor", 1.0),
        )

    def get_screen_size(self) -> tuple[int, int]:
        try:
            result = self._client.call("screen_size", timeout=3.0)
            return (result["width"], result["height"])
        except BridgeError as e:
            raise ScreenCaptureError(f"Bridge screen_size failed: {e}") from e

    def get_scale_factor(self) -> float:
        try:
            result = self._client.call("scale_factor", timeout=3.0)
            return result.get("factor", 1.0)
        except BridgeError:
            return 1.0
