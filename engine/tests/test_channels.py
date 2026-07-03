"""Where a HITL request or a notify reaches a human: CLI + desktop channels.

``ChannelRouter`` picks the active channel and forwards; a per-call ``channel``
override redirects one request/notify. ``CLIChannel`` prompts on the TTY (with a
timeout) and maps ``importance`` to loudness; ``DesktopChannel`` selects the
right native command per OS.
"""

import pytest

from engine.channels.base import ChannelRouter, Delivery, HumanPrompt
from engine.channels.cli import CLIChannel
from engine.channels.desktop import DesktopChannel


class FakeChannel:
    def __init__(self, name, answer=None):
        self.name = name
        self._answer = answer or {"choice": "approve", "text": None, "timed_out": False}
        self.requests = []
        self.notes = []

    async def request(self, prompt):
        self.requests.append(prompt)
        return self._answer

    async def notify(self, message, *, importance):
        self.notes.append((message, importance))
        return Delivery(delivered=[self.name])


# ---- ChannelRouter ---------------------------------------------------------

@pytest.mark.asyncio
async def test_router_forwards_to_active_channel():
    cli = FakeChannel("cli")
    desktop = FakeChannel("desktop")
    router = ChannelRouter({"cli": cli, "desktop": desktop}, active="cli")

    resp = await router.request(HumanPrompt(kind="approval", text="ok?"))
    assert resp["choice"] == "approve"
    assert len(cli.requests) == 1 and len(desktop.requests) == 0


@pytest.mark.asyncio
async def test_router_per_call_channel_override():
    cli = FakeChannel("cli")
    desktop = FakeChannel("desktop")
    router = ChannelRouter({"cli": cli, "desktop": desktop}, active="cli")

    d = await router.notify("hi", importance="high", channel="desktop")
    assert d.delivered == ["desktop"]
    assert desktop.notes == [("hi", "high")]
    assert cli.notes == []


# ---- CLIChannel ------------------------------------------------------------

@pytest.mark.asyncio
async def test_cli_approval_maps_yes_to_approve():
    ch = CLIChannel(input_fn=lambda prompt: "y", writer=lambda s: None)
    resp = await ch.request(HumanPrompt(kind="approval", text="run rm?", risk="high"))
    assert resp["choice"] == "approve"
    assert resp["timed_out"] is False


@pytest.mark.asyncio
async def test_cli_approval_maps_no_to_reject():
    ch = CLIChannel(input_fn=lambda prompt: "n", writer=lambda s: None)
    resp = await ch.request(HumanPrompt(kind="approval", text="run rm?"))
    assert resp["choice"] == "reject"


@pytest.mark.asyncio
async def test_cli_question_returns_the_raw_answer():
    ch = CLIChannel(input_fn=lambda prompt: "blue", writer=lambda s: None)
    resp = await ch.request(HumanPrompt(kind="question", text="colour?"))
    assert resp["choice"] == "blue"


@pytest.mark.asyncio
async def test_cli_timeout_returns_timed_out():
    async def slow_reader(text, timeout):
        import asyncio

        raise asyncio.TimeoutError

    ch = CLIChannel(reader=slow_reader, writer=lambda s: None)
    resp = await ch.request(HumanPrompt(kind="approval", text="q", timeout=0.01))
    assert resp["timed_out"] is True
    assert resp["choice"] is None


@pytest.mark.asyncio
async def test_cli_notify_writes_and_maps_importance():
    written = []
    ch = CLIChannel(input_fn=lambda p: "", writer=written.append)
    d = await ch.notify("build done", importance="high")
    assert d.delivered == ["cli"]
    assert any("build done" in w for w in written)


# ---- DesktopChannel (per-OS command selection) -----------------------------

@pytest.mark.asyncio
async def test_desktop_notify_uses_osascript_on_macos():
    calls = []

    def runner(argv):
        calls.append(argv)
        return ""

    ch = DesktopChannel(os_name="Darwin", runner=runner)
    await ch.notify("hello", importance="normal")
    assert any("osascript" in argv[0] for argv in calls)


@pytest.mark.asyncio
async def test_desktop_notify_uses_notify_send_on_linux():
    calls = []
    ch = DesktopChannel(os_name="Linux", runner=lambda a: calls.append(a) or "")
    await ch.notify("hello", importance="normal")
    assert calls and "notify-send" in calls[0][0]


@pytest.mark.asyncio
async def test_desktop_notify_uses_powershell_on_windows():
    calls = []
    ch = DesktopChannel(os_name="Windows", runner=lambda a: calls.append(a) or "")
    await ch.notify("hello", importance="normal")
    assert calls and "powershell" in calls[0][0].lower()


@pytest.mark.asyncio
async def test_desktop_request_returns_choice_from_runner():
    ch = DesktopChannel(os_name="Linux", runner=lambda a: "approve")
    resp = await ch.request(HumanPrompt(kind="approval", text="run?"))
    assert resp["choice"] == "approve"
    assert resp["timed_out"] is False
