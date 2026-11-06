"""The offline driver must never wait without a bound, and must show a pulse.

Two runs of the 0.5.0 offline cell were lost to the same shape. An installer
prompt nobody answered held the package for eleven minutes before Windows
Installer gave up. A command that had already exited left its caller holding a
pipe for thirty six, and because the snapshot is discarded when it closes, a
stall there destroys the only evidence the cell would have produced.

A host outside the snapshot cannot read the guest's screen, so a stalled guest
and a slow one look identical unless the guest writes a pulse the host can see.

These tests read the two driver sources, so they run on any host with no
snapshot and no installed product.
"""

import pathlib
import re

HARNESS = pathlib.Path(__file__).resolve().parents[2] / "E2E" / "0.5.0" / "harness"
GUEST = HARNESS / "windows_sandbox_o1_inside.ps1"
HOST = HARNESS / "windows_sandbox_o1.ps1"


def guest_source():
    return GUEST.read_text(encoding="utf-8")


def host_source():
    return HOST.read_text(encoding="utf-8")


def test_both_driver_halves_exist():
    assert GUEST.is_file(), GUEST
    assert HOST.is_file(), HOST


def test_the_guest_runs_no_command_through_a_pipeline():
    """A pipeline ends when every writer closes it, not when the command ends."""
    source = guest_source()
    body = source.split("function Invoke-Capture", 1)[1].split("\nfunction ", 1)[0]
    assert "Start-Process" in body, "the capture must not run the command in a pipeline"
    assert "WaitForExit(" in body, "the capture must wait with a bound"
    assert "RedirectStandardOutput" in body and "RedirectStandardError" in body, \
        "the streams must go to files, so no pipe can outlive the command"


def test_every_capture_bound_comes_from_a_named_budget():
    source = guest_source()
    assert re.search(r"\$script:CommandBudgetSeconds\s*=\s*\d+", source), \
        "the budget must be named rather than written at each call"
    for waited in re.findall(r"WaitForExit\(([^)]*)\)", source):
        assert waited.strip(), "WaitForExit() with no bound waits forever"


def test_a_command_that_passes_its_budget_is_recorded_rather_than_hidden():
    source = guest_source()
    capture = source.split("function Invoke-Capture", 1)[1].split("\nfunction ", 1)[0]
    assert "timed_out" in capture, "a step must be able to say that it ran out of budget"
    assert ".Kill()" in capture, "a command past its budget must be stopped"


def test_the_guest_writes_a_pulse_the_host_can_read():
    source = guest_source()
    assert "function Write-Heartbeat" in source
    assert "o1-heartbeat.txt" in source
    add_step = source.split("function Add-Step", 1)[1].split("\nfunction ", 1)[0]
    assert "Write-Heartbeat" in add_step, "every recorded step must move the pulse"


def test_the_host_gives_up_on_a_silent_guest_before_the_whole_budget():
    source = host_source()
    assert "o1-heartbeat.txt" in source, "the host must read the guest's pulse"
    assert re.search(r"\$StallMinutes\s*=\s*\d+", source), \
        "the host needs its own named limit on silence"
    assert "wrote nothing for" in source, \
        "a silent guest must be reported as silence, not as a finished run"


def test_the_record_keeps_the_detail_the_transcript_only_samples():
    """One run printed 47 MB of transcript, which buries the line that matters."""
    source = guest_source()
    add_step = source.split("function Add-Step", 1)[1].split("\nfunction ", 1)[0]
    assert "Substring(0, 2000)" in add_step, "the transcript line must be capped"
    assert "kept in the record" in add_step, "the cap must say where the rest went"
    assert "detail = $Detail" in add_step, "the record itself keeps the whole detail"
