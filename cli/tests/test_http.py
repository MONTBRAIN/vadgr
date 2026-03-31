"""Tests for cli.client -- HTTP client for the API."""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from unittest import mock

import click
import pytest

from cli.client import api_get, api_post, api_delete, api_put, is_api_running


@pytest.fixture
def ctx():
    """Click context with default API URL."""
    c = click.Context(click.Command("test"))
    c.ensure_object(dict)
    c.obj["api_url"] = "http://127.0.0.1:18765"
    return c


class _TestHandler(BaseHTTPRequestHandler):
    """Minimal handler for test HTTP server."""

    def do_GET(self):
        if self.path == "/api/health":
            self._json(200, {"status": "healthy"})
        elif self.path == "/api/agents":
            self._json(200, [{"id": "1", "name": "test"}])
        elif self.path == "/api/missing":
            self._json(404, {"detail": "Not found"})
        else:
            self._json(404, {"detail": "Not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        self._json(200, {"received": body})

    def do_DELETE(self):
        self._json(200, {"deleted": True})

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        self._json(200, {"updated": body})

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def test_server():
    """Start a test HTTP server for the module."""
    server = HTTPServer(("127.0.0.1", 18765), _TestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


class TestApiGet:
    def test_returns_json(self, ctx, test_server):
        result = api_get(ctx, "/api/health")
        assert result["status"] == "healthy"

    def test_returns_list(self, ctx, test_server):
        result = api_get(ctx, "/api/agents")
        assert isinstance(result, list)
        assert result[0]["name"] == "test"

    def test_raises_on_404(self, ctx, test_server):
        with pytest.raises(click.ClickException, match="Not found"):
            api_get(ctx, "/api/missing")

    def test_raises_on_connection_refused(self, ctx):
        ctx.obj["api_url"] = "http://127.0.0.1:19999"
        with pytest.raises(click.ClickException, match="API is not running"):
            api_get(ctx, "/api/health")


class TestApiPost:
    def test_sends_json_body(self, ctx, test_server):
        result = api_post(ctx, "/api/agents", {"name": "new-agent"})
        assert result["received"]["name"] == "new-agent"

    def test_empty_body(self, ctx, test_server):
        result = api_post(ctx, "/api/agents")
        assert result["received"] == {}


class TestApiDelete:
    def test_returns_response(self, ctx, test_server):
        result = api_delete(ctx, "/api/agents/1")
        assert result["deleted"] is True


class TestApiPut:
    def test_sends_json_body(self, ctx, test_server):
        result = api_put(ctx, "/api/settings", {"enabled": True})
        assert result["updated"]["enabled"] is True


class TestTimeout:
    def test_timeout_shows_timeout_not_api_down(self, ctx, test_server):
        """socket.timeout should say 'timed out', not 'API is not running'."""
        import socket
        with mock.patch("cli.client.urllib.request.urlopen") as m:
            m.side_effect = socket.timeout("timed out")
            with pytest.raises(click.ClickException, match="timed out") as exc_info:
                api_get(ctx, "/api/health")
            assert "API is not running" not in str(exc_info.value)


class TestIsApiRunning:
    def test_returns_true_when_running(self, ctx, test_server):
        assert is_api_running(ctx) is True

    def test_returns_false_when_down(self, ctx):
        ctx.obj["api_url"] = "http://127.0.0.1:19999"
        assert is_api_running(ctx) is False
