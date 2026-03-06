"""Tests for the bridge protocol, client, capture, and actions."""

import base64
import io
import json
import socket
import struct
import threading
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image as PILImage

from computer_use.bridge.protocol import (
    HEADER_SIZE,
    decode_header,
    encode_message,
    make_error,
    make_request,
    make_response,
)
from computer_use.bridge.client import BridgeClient, BridgeError
from computer_use.bridge.capture import BridgeScreenCapture
from computer_use.bridge.actions import BridgeActionExecutor
from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.types import ScreenState


def _make_jpeg_b64(width=100, height=100):
    img = PILImage.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


class TestProtocol:
    def test_encode_decode_roundtrip(self):
        msg = {"id": "abc", "method": "ping", "params": {}}
        encoded = encode_message(msg)
        assert len(encoded) > HEADER_SIZE
        length = decode_header(encoded[:HEADER_SIZE])
        payload = encoded[HEADER_SIZE:]
        assert len(payload) == length
        assert json.loads(payload) == msg

    def test_encode_empty_dict(self):
        encoded = encode_message({})
        length = decode_header(encoded[:HEADER_SIZE])
        assert json.loads(encoded[HEADER_SIZE:]) == {}

    def test_encode_large_payload(self):
        msg = {"data": "x" * 100000}
        encoded = encode_message(msg)
        length = decode_header(encoded[:HEADER_SIZE])
        assert length > 100000

    def test_make_request_has_id(self):
        req = make_request("ping")
        assert "id" in req
        assert req["method"] == "ping"
        assert req["params"] == {}

    def test_make_request_with_params(self):
        req = make_request("click", {"x": 100, "y": 200})
        assert req["params"] == {"x": 100, "y": 200}

    def test_make_response(self):
        resp = make_response("abc", {"width": 1920})
        assert resp["ok"] is True
        assert resp["result"]["width"] == 1920

    def test_make_error(self):
        resp = make_error("abc", "something broke")
        assert resp["ok"] is False
        assert "broke" in resp["error"]


class TestBridgeClient:
    def test_is_available_returns_false_on_refused(self):
        client = BridgeClient(port=19999)
        assert client.is_available() is False

    def test_call_raises_on_connection_refused(self):
        client = BridgeClient(port=19999)
        with pytest.raises(BridgeError, match="connection failed"):
            client.call("ping", timeout=1.0)

    def test_call_with_mock_server(self):
        """Spin up a minimal TCP server, verify client sends/receives correctly."""
        response_data = {"id": "", "ok": True, "result": {"pong": True}}

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve():
            conn, _ = server.accept()
            # Read request
            header = conn.recv(HEADER_SIZE)
            length = struct.unpack("!I", header)[0]
            payload = conn.recv(length)
            request = json.loads(payload)
            # Send response with matching id
            response_data["id"] = request["id"]
            resp_bytes = json.dumps(response_data, separators=(",", ":")).encode()
            conn.sendall(struct.pack("!I", len(resp_bytes)) + resp_bytes)
            conn.close()

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        client = BridgeClient(host="127.0.0.1", port=port)
        result = client.call("ping", timeout=3.0)
        assert result["pong"] is True
        client.close()
        server.close()

    def test_is_available_with_mock_server(self):
        response_data = {"id": "", "ok": True, "result": {"pong": True}}

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve():
            conn, _ = server.accept()
            header = conn.recv(HEADER_SIZE)
            length = struct.unpack("!I", header)[0]
            payload = conn.recv(length)
            request = json.loads(payload)
            response_data["id"] = request["id"]
            resp_bytes = json.dumps(response_data, separators=(",", ":")).encode()
            conn.sendall(struct.pack("!I", len(resp_bytes)) + resp_bytes)
            conn.close()

        t = threading.Thread(target=serve, daemon=True)
        t.start()

        client = BridgeClient(host="127.0.0.1", port=port)
        assert client.is_available() is True
        client.close()
        server.close()


class TestBridgeScreenCapture:
    def _make_client(self, result):
        client = MagicMock(spec=BridgeClient)
        client.call.return_value = result
        return client

    def test_capture_full(self):
        b64 = _make_jpeg_b64(1920, 1080)
        client = self._make_client({
            "width": 1920,
            "height": 1080,
            "offset_x": 0,
            "offset_y": 0,
            "scale_factor": 1.25,
            "image_b64": b64,
        })
        cap = BridgeScreenCapture(client)
        state = cap.capture_full()

        assert isinstance(state, ScreenState)
        assert state.width == 1920
        assert state.height == 1080
        assert state.scale_factor == 1.25
        assert state.offset_x == 0
        assert len(state.image_bytes) > 0
        client.call.assert_called_once()

    def test_capture_full_decodes_jpeg(self):
        b64 = _make_jpeg_b64(800, 600)
        client = self._make_client({
            "width": 800, "height": 600,
            "image_b64": b64,
        })
        cap = BridgeScreenCapture(client)
        state = cap.capture_full()
        # Verify it's valid JPEG
        img = PILImage.open(io.BytesIO(state.image_bytes))
        assert img.format == "JPEG"

    def test_capture_region(self):
        from computer_use.core.types import Region
        b64 = _make_jpeg_b64(200, 100)
        client = self._make_client({
            "width": 200, "height": 100, "image_b64": b64,
        })
        cap = BridgeScreenCapture(client)
        state = cap.capture_region(Region(10, 20, 200, 100))
        assert state.width == 200
        assert state.height == 100

    def test_get_screen_size(self):
        client = self._make_client({"width": 1920, "height": 1080})
        cap = BridgeScreenCapture(client)
        assert cap.get_screen_size() == (1920, 1080)

    def test_get_scale_factor(self):
        client = self._make_client({"factor": 1.5})
        cap = BridgeScreenCapture(client)
        assert cap.get_scale_factor() == 1.5

    def test_error_wraps_as_screen_capture_error(self):
        client = MagicMock(spec=BridgeClient)
        client.call.side_effect = BridgeError("timeout")
        cap = BridgeScreenCapture(client)
        with pytest.raises(ScreenCaptureError, match="Bridge screenshot failed"):
            cap.capture_full()


class TestBridgeActionExecutor:
    def _make_client(self):
        client = MagicMock(spec=BridgeClient)
        client.call.return_value = {}
        return client

    def test_move_mouse(self):
        client = self._make_client()
        exe = BridgeActionExecutor(client)
        exe.move_mouse(100, 200)
        client.call.assert_called_once_with("move_mouse", {"x": 100, "y": 200}, timeout=10.0)

    def test_click(self):
        client = self._make_client()
        exe = BridgeActionExecutor(client)
        exe.click(50, 75, "right")
        client.call.assert_called_once_with(
            "click", {"x": 50, "y": 75, "button": "right"}, timeout=10.0
        )

    def test_double_click(self):
        client = self._make_client()
        exe = BridgeActionExecutor(client)
        exe.double_click(10, 20)
        client.call.assert_called_once_with("double_click", {"x": 10, "y": 20}, timeout=10.0)

    def test_type_text(self):
        client = self._make_client()
        exe = BridgeActionExecutor(client)
        exe.type_text("hello")
        client.call.assert_called_once_with("type_text", {"text": "hello"}, timeout=10.0)

    def test_key_press(self):
        client = self._make_client()
        exe = BridgeActionExecutor(client)
        exe.key_press(["ctrl", "c"])
        client.call.assert_called_once_with(
            "key_press", {"keys": ["ctrl", "c"]}, timeout=10.0
        )

    def test_scroll(self):
        client = self._make_client()
        exe = BridgeActionExecutor(client)
        exe.scroll(100, 200, -3)
        client.call.assert_called_once_with(
            "scroll", {"x": 100, "y": 200, "amount": -3}, timeout=10.0
        )

    def test_drag(self):
        client = self._make_client()
        exe = BridgeActionExecutor(client)
        exe.drag(10, 20, 100, 200, 0.5)
        client.call.assert_called_once_with(
            "drag",
            {"start_x": 10, "start_y": 20, "end_x": 100, "end_y": 200, "duration": 0.5},
            timeout=10.0,
        )

    def test_error_wraps_as_action_error(self):
        client = MagicMock(spec=BridgeClient)
        client.call.side_effect = BridgeError("timeout")
        exe = BridgeActionExecutor(client)
        with pytest.raises(ActionError, match="Bridge click failed"):
            exe.click(0, 0)


class TestBridgeActionExecutorFallback:
    """Tests for the fallback mechanism: when bridge type_text/key_press fails,
    the executor should fall back to a secondary ActionExecutor (PowerShell)."""

    def _make_failing_client(self):
        """Create a mock client that raises BridgeError on call."""
        client = MagicMock(spec=BridgeClient)
        client.call.side_effect = BridgeError("access violation writing 0x0000000000000000")
        return client

    def _make_ok_client(self):
        client = MagicMock(spec=BridgeClient)
        client.call.return_value = {}
        return client

    def test_type_text_falls_back_on_bridge_error(self):
        client = self._make_failing_client()
        fallback = MagicMock(spec=ActionExecutor)
        exe = BridgeActionExecutor(client, fallback=fallback)
        exe.type_text("hello world")
        fallback.type_text.assert_called_once_with("hello world")

    def test_key_press_falls_back_on_bridge_error(self):
        client = self._make_failing_client()
        fallback = MagicMock(spec=ActionExecutor)
        exe = BridgeActionExecutor(client, fallback=fallback)
        exe.key_press(["ctrl", "c"])
        fallback.key_press.assert_called_once_with(["ctrl", "c"])

    def test_type_text_no_fallback_raises(self):
        client = self._make_failing_client()
        exe = BridgeActionExecutor(client)
        with pytest.raises(ActionError, match="Bridge type_text failed"):
            exe.type_text("hello")

    def test_key_press_no_fallback_raises(self):
        client = self._make_failing_client()
        exe = BridgeActionExecutor(client)
        with pytest.raises(ActionError, match="Bridge key_press failed"):
            exe.key_press(["enter"])

    def test_type_text_uses_bridge_when_it_works(self):
        client = self._make_ok_client()
        fallback = MagicMock(spec=ActionExecutor)
        exe = BridgeActionExecutor(client, fallback=fallback)
        exe.type_text("works fine")
        client.call.assert_called_once_with("type_text", {"text": "works fine"}, timeout=10.0)
        fallback.type_text.assert_not_called()

    def test_key_press_uses_bridge_when_it_works(self):
        client = self._make_ok_client()
        fallback = MagicMock(spec=ActionExecutor)
        exe = BridgeActionExecutor(client, fallback=fallback)
        exe.key_press(["alt", "tab"])
        client.call.assert_called_once_with("key_press", {"keys": ["alt", "tab"]}, timeout=10.0)
        fallback.key_press.assert_not_called()

    def test_click_does_not_fallback(self):
        """Non-text methods should NOT fall back -- they should raise directly."""
        client = self._make_failing_client()
        fallback = MagicMock(spec=ActionExecutor)
        exe = BridgeActionExecutor(client, fallback=fallback)
        with pytest.raises(ActionError):
            exe.click(100, 200)
        fallback.click.assert_not_called()

    def test_scroll_does_not_fallback(self):
        client = self._make_failing_client()
        fallback = MagicMock(spec=ActionExecutor)
        exe = BridgeActionExecutor(client, fallback=fallback)
        with pytest.raises(ActionError):
            exe.scroll(100, 200, -3)
        fallback.scroll.assert_not_called()


class TestWSL2BackendBridgeFallbackWiring:
    """Tests that WSL2Backend wires the PowerShell fallback into BridgeActionExecutor."""

    def test_bridge_executor_gets_ps_fallback(self):
        from computer_use.platform.wsl2 import WSL2Backend, WSL2ActionExecutor

        backend = WSL2Backend()
        # Simulate bridge available
        backend._use_bridge = True
        backend._bridge = MagicMock()

        executor = backend.get_action_executor()
        assert hasattr(executor, '_fallback')
        assert isinstance(executor._fallback, WSL2ActionExecutor)

    def test_no_bridge_returns_ps_executor(self):
        from computer_use.platform.wsl2 import WSL2Backend, WSL2ActionExecutor

        backend = WSL2Backend()
        backend._use_bridge = False

        executor = backend.get_action_executor()
        assert isinstance(executor, WSL2ActionExecutor)


class TestWSL2BackendFallback:
    def test_uses_bridge_when_available(self):
        from computer_use.platform.wsl2 import WSL2Backend

        backend = WSL2Backend()
        with patch("computer_use.bridge.client.BridgeClient") as MockClient:
            MockClient.return_value.is_available.return_value = True
            backend._probe_bridge()
            assert backend._use_bridge is True

    def test_falls_back_when_bridge_unavailable(self):
        from computer_use.platform.wsl2 import WSL2Backend

        backend = WSL2Backend()
        with (
            patch("computer_use.bridge.client.BridgeClient") as MockClient,
            patch.object(WSL2Backend, "_auto_launch_daemon", return_value=False),
        ):
            MockClient.return_value.is_available.return_value = False
            backend._probe_bridge()
            assert backend._use_bridge is False

    def test_probe_caches_result(self):
        from computer_use.platform.wsl2 import WSL2Backend

        backend = WSL2Backend()
        with (
            patch("computer_use.bridge.client.BridgeClient") as MockClient,
            patch.object(WSL2Backend, "_auto_launch_daemon", return_value=False),
        ):
            MockClient.return_value.is_available.return_value = False
            backend._probe_bridge()
            backend._probe_bridge()
            # Only one BridgeClient created despite two probes
            assert MockClient.call_count == 1
