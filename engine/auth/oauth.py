"""The OAuth strategy -- token cache, refresh-on-expiry / on-401, per-OS store.

Owns the access-token cache, the refresh-token exchange (through the shared
``HttpClient``), and the credentials read/write. For the first provider it is
constructed with the Claude Code credentials path, the refresh endpoint, and
the public Claude Code client id.

Per-OS credential resolution (four platforms, non-negotiable): on
**Linux / Windows / WSL** the token store is the credentials **file**
(``~/.claude/.credentials.json`` -- on WSL that is the *Linux-side* home, never
``/mnt/c``); on **macOS** the token lives in the login **Keychain**, read/written
through ``security`` (or ``keyring``). The store is resolved by OS behind one
``inject_headers`` / refresh path -- the read is branched, never assumed.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

# Refresh a token once it is within this window of expiry (ms). Claude Code
# tokens are long-lived; this just avoids sending one about to expire mid-run.
REFRESH_WINDOW_MS = 5 * 60 * 1000

# The macOS login-Keychain coordinates Claude Code stores its token under.
_KEYCHAIN_SERVICE = "Claude Code-credentials"


class CredentialsError(RuntimeError):
    """Base for credential-store failures."""


class CredentialsMissingError(CredentialsError):
    """No credentials found -- the user must run ``claude setup-token``."""


class FileTokenStore:
    """The Linux / Windows / WSL token store: the credentials JSON file.

    The file wraps the token block under ``claudeAiOauth`` (Claude Code's
    layout); ``load`` returns that block, ``save`` writes it back, preserving
    the wrapper."""

    WRAPPER_KEY = "claudeAiOauth"

    def __init__(self, path: str):
        # Expand ``~`` against the *current* home -- on WSL that is the
        # Linux-side home, exactly as intended.
        self.path = str(Path(path).expanduser())

    def load(self) -> dict | None:
        p = Path(self.path)
        if not p.is_file():
            return None
        data = json.loads(p.read_text())
        return data.get(self.WRAPPER_KEY, data)

    def save(self, block: dict) -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if p.is_file():
            try:
                existing = json.loads(p.read_text())
            except json.JSONDecodeError:
                existing = {}
        existing[self.WRAPPER_KEY] = block
        p.write_text(json.dumps(existing, indent=2))


class KeychainTokenStore:
    """The macOS token store: the login Keychain, via ``security``.

    macOS is host-unreachable from a Linux/WSL dev host, so this backend is
    proven by unit branch + the design's stated behavior, not live -- the
    ``security`` invocation is isolated behind ``_run`` so a test can inject a
    fake."""

    def __init__(
        self,
        service: str = _KEYCHAIN_SERVICE,
        account: str | None = None,
        runner: Callable[[list[str]], str] | None = None,
    ):
        self._service = service
        self._account = account or _current_user()
        self._run = runner or _run_security

    def load(self) -> dict | None:
        try:
            raw = self._run(
                [
                    "security", "find-generic-password",
                    "-s", self._service, "-a", self._account, "-w",
                ]
            )
        except CredentialsError:
            return None
        raw = raw.strip()
        if not raw:
            return None
        data = json.loads(raw)
        return data.get(FileTokenStore.WRAPPER_KEY, data)

    def save(self, block: dict) -> None:
        payload = json.dumps({FileTokenStore.WRAPPER_KEY: block})
        # -U updates the item if it already exists.
        self._run(
            [
                "security", "add-generic-password",
                "-s", self._service, "-a", self._account, "-w", payload, "-U",
            ]
        )


def _current_user() -> str:
    import getpass

    try:
        return getpass.getuser()
    except Exception:
        return ""


def _run_security(argv: list[str]) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError as exc:  # no ``security`` binary -> not macOS
        raise CredentialsError("security binary not available") from exc
    if proc.returncode != 0:
        raise CredentialsError(proc.stderr.strip() or "security failed")
    return proc.stdout


def resolve_token_store(os_name: str, credentials_path: str):
    """Pick the token store by OS. macOS -> Keychain; everything else (Linux /
    Windows / WSL) -> the credentials file."""
    if os_name == "Darwin":
        return KeychainTokenStore()
    return FileTokenStore(credentials_path)


class OAuthStrategy:
    """``Authorization: Bearer <cached token>`` with refresh-on-expiry and
    refresh-on-401. Composed into a provider by reference."""

    def __init__(
        self,
        credentials_path: str,
        refresh_url: str,
        client_id: str,
        *,
        http=None,
        now: Callable[[], int] | None = None,
        os_name: str | None = None,
        store=None,
    ):
        self._credentials_path = credentials_path
        self._refresh_url = refresh_url
        self._client_id = client_id
        self._http = http
        self._now_ms = now or (lambda: int(time.time() * 1000))
        if store is not None:
            self._store = store
        else:
            import platform

            self._store = resolve_token_store(
                os_name or platform.system(), credentials_path
            )
        self._block: dict | None = None

    # -- public port ---------------------------------------------------------

    async def inject_headers(self, request: dict) -> None:
        token = await self._access_token()
        request.setdefault("headers", {})["Authorization"] = f"Bearer {token}"

    async def handle_401(self, response: Any) -> bool:
        """Drop the cached token, refresh once, and signal the caller to retry.
        Returns ``False`` if the refresh itself fails -- a terminal auth error."""
        self._block = None
        try:
            await self._refresh()
            return True
        except Exception:
            return False

    async def ensure_ready(self) -> None:
        """Fail-fast preflight for ``provider.setup()``: load the credentials
        (raising the ``setup-token`` error if absent) and refresh if inside the
        window, so a run never starts on a token about to expire."""
        await self._access_token()

    # -- internals -----------------------------------------------------------

    def _load(self) -> dict:
        if self._block is None:
            block = self._store.load()
            if not block or not block.get("accessToken"):
                raise CredentialsMissingError(
                    "No Claude credentials found -- run `claude setup-token` first."
                )
            self._block = block
        return self._block

    async def _access_token(self) -> str:
        block = self._load()
        expires_at = block.get("expiresAt", 0)
        if self._now_ms() >= expires_at - REFRESH_WINDOW_MS:
            await self._refresh()
            block = self._block
        return block["accessToken"]

    async def _refresh(self) -> None:
        block = self._load()
        refresh_token = block.get("refreshToken")
        if not refresh_token:
            raise CredentialsError("No refresh token available")
        if self._http is None:
            from engine.http import HttpClient

            self._http = HttpClient()
        response = await self._http.post(
            self._refresh_url,
            headers={"Content-Type": "application/json"},
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
            },
        )
        if response.status_code != 200:
            raise CredentialsError(
                f"Token refresh failed (HTTP {response.status_code})"
            )
        payload = response.json()
        new_block = dict(block)
        new_block["accessToken"] = payload["access_token"]
        new_block["refreshToken"] = payload.get("refresh_token", refresh_token)
        expires_in = payload.get("expires_in")
        if expires_in is not None:
            new_block["expiresAt"] = self._now_ms() + int(expires_in) * 1000
        self._store.save(new_block)
        self._block = new_block
