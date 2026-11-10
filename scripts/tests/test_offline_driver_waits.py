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
    # One unbounded wait is correct and only one: after a bounded wait has
    # already returned, it reads the exit code of a process that has ended.
    # Any other would be a wait on something that may never happen.
    unbounded = [w for w in re.findall(r"WaitForExit\(([^)]*)\)", source) if not w.strip()]
    assert len(unbounded) == 1, \
        f"expected exactly one exit-code read, found {len(unbounded)} unbounded waits"
    after_bounded = source.split("$finished = $process.WaitForExit(", 1)
    assert len(after_bounded) == 2 and "$process.WaitForExit()" in after_bounded[1], \
        "the unbounded wait must follow the bounded one, not replace it"


def test_a_command_that_passes_its_budget_is_recorded_rather_than_hidden():
    source = guest_source()
    capture = source.split("function Invoke-Capture", 1)[1].split("\nfunction ", 1)[0]
    assert "timed_out" in capture, "a step must be able to say that it ran out of budget"
    # The whole tree: a child of the stopped command keeps the redirected
    # files open, so stopping the command alone leaves them locked.
    assert "taskkill.exe /T /F" in capture, \
        "a command past its budget must have its whole process tree stopped"
    assert "$null = $process.Handle" in capture, \
        "the handle must be cached before the wait, or every exit code reads back empty"


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


def test_the_wait_loop_beats_while_it_waits():
    """A long wait and a stopped guest look identical without a pulse."""
    source = guest_source()
    loop = source.split("function Wait-ForText", 1)[1].split("\nfunction ", 1)[0]
    assert "Write-Heartbeat" in loop, "the wait loop must report that it is still waiting"


def test_the_wait_loop_reads_an_installer_error_instead_of_waiting_it_out():
    """Windows Installer reports a failed action in a dialog and then waits."""
    source = guest_source()
    loop = source.split("function Wait-ForText", 1)[1].split("\nfunction ", 1)[0]
    assert "Read-InstallerProblem" in loop, \
        "the wait must notice an error dialog rather than spend its whole budget"
    assert "return $problem" in loop, \
        "the failure text must reach the step, which decides pass or fail"


def test_an_installer_error_is_only_read_from_the_setup_process():
    """Any application can own a dialog of this class, including the owner's."""
    source = guest_source()
    reader = source.split("function Read-InstallerProblem", 1)[1].split("\nfunction ", 1)[0]
    assert "ProcessId -ne $Window.element.Current.ProcessId" in reader, \
        "a dialog of another process must be ignored"
    assert "files in use" in reader, \
        "the files in use prompt is answered elsewhere and must not be read as a failure"


def test_the_host_waits_for_a_previous_virtual_machine_before_starting():
    """Two sessions cannot coexist, and the second is logged off with the first."""
    source = host_source()
    assert "vmmemWindowsSandbox" in source, \
        "the host must notice a previous session's virtual machine"
    assert re.search(r"\$PreviousSessionMinutes\s*=\s*\d+", source), \
        "that wait needs its own named limit"
    start = source.index("vmmemWindowsSandbox")
    launch = source.index("Start-Process -FilePath $sandbox")
    assert start < launch, "the check must come before the session is started"


def test_the_daemon_count_is_never_read_from_an_unwrapped_result():
    """One daemon counted as two: a hashtable's Count is its number of keys."""
    calls = []
    for line in guest_source().splitlines():
        if "Get-DaemonProcesses" not in line:
            continue
        if line.strip().startswith("function "):
            continue
        if "@(Get-DaemonProcesses)" not in line:
            calls.append(line.strip())
    assert not calls, f"every call must be wrapped in @(): {calls}"
    assert guest_source().count("@(Get-DaemonProcesses)") >= 5, \
        "each call site must keep its result an array"


def test_the_held_files_prompt_is_answered_in_both_its_shapes():
    """Eight applications held files and the radio the driver required was absent."""
    source = guest_source()
    answer = source.split("function Answer-FilesInUse", 1)[1].split("\nfunction ", 1)[0]
    assert "if (-not $ok)" in answer, \
        "a prompt without the restart radio must still be answered through OK"
    assert "could not be answered" in answer, \
        "a dialog this driver cannot answer must be recorded, not skipped in silence"
    assert "$radio" in answer and "SelectionItemPattern" in answer, \
        "the restart choice is still taken when the prompt offers it"


def test_the_repair_wait_is_shorter_than_the_default():
    """A repair that is stuck should be reported in minutes, not in half an hour."""
    source = guest_source()
    repair = source.split("$repairReached = Wait-ForText", 1)[1][:200]
    assert "-TimeoutSeconds" in repair, "the repair wait must carry its own budget"


def test_a_stalled_step_does_not_end_the_whole_run():
    """Repair stalled twice and took the uninstall cells down with it."""
    source = guest_source()
    assert "$repairStall" in source, "a stalled repair must be caught and recorded"
    repair = source.split("$repairReached = $null", 1)[1].split("Add-Step", 1)[0]
    assert "try {" in repair and "catch {" in repair, \
        "the wait must be caught so the cells after it still run"


def test_a_stalled_step_records_everything_on_the_guest_screen():
    """The snapshot is discarded, so an unfiltered inventory is the only record."""
    source = guest_source()
    assert "function Get-TopLevelWindows" in source
    assert "windows_on_screen" in source, \
        "the stalled step must record what was on screen when it stalled"
    inventory = source.split("function Get-TopLevelWindows", 1)[1].split("\nfunction ", 1)[0]
    assert "TrueCondition" in inventory, "the inventory must not filter by name or class"


def test_the_console_is_stopped_by_what_actually_holds_the_files():
    """The launcher exits; the console that holds the installed files does not."""
    source = guest_source()
    before_repair = source.split("$repairLog = Join-Path", 1)[0]
    tail = before_repair[-2000:]
    assert "nothing of the product holds its own files before the repair" in tail, \
        "the run must prove the product released its files before repairing"
    assert "'vadgr', 'vadgr-app'" in tail, \
        "both the console process and the launcher must be stopped by name"
