"""The offline driver must press a page control, never the title bar.

Measured on 2026-11-06 against the registered installation vehicle on Windows
x64. Every window of this bootstrapper carries a title bar button whose
accessible name is the same as the page button beside it, and the title bar
button reports the automation id `Close`. A rule that only requires an id to be
present therefore admits exactly the control it was written to refuse, and the
driver closes the window instead of pressing the button. The run then reads as
finished.

Every page control of this bootstrapper carries the dialog control id as a
number: Install Vadgr 32768, Decline 111, the page Close 132, Uninstall 32773.

These tests read the driver source, so they run on any host with no window and
no installed product.
"""

import pathlib
import re

DRIVER = (pathlib.Path(__file__).resolve().parents[2]
          / "E2E" / "0.5.0" / "harness" / "windows_sandbox_o1_inside.ps1")

# What the live window reported. The title bar entry is the one the old rule
# admitted.
OBSERVED_CONTROLS = (
    {"name": "Close", "automation_id": "Close", "page_control": False},
    {"name": "Minimize", "automation_id": "Minimize", "page_control": False},
    {"name": "Maximize", "automation_id": "Maximize", "page_control": False},
    {"name": "Back by small amount", "automation_id": "SmallDecrement",
     "page_control": False},
    {"name": "Forward by large amount", "automation_id": "LargeIncrement",
     "page_control": False},
    {"name": "Install Vadgr", "automation_id": "32768", "page_control": True},
    {"name": "Decline", "automation_id": "111", "page_control": True},
    {"name": "Close", "automation_id": "132", "page_control": True},
    {"name": "Uninstall", "automation_id": "32773", "page_control": True},
)


def driver_source():
    return DRIVER.read_text(encoding="utf-8")


def page_control_rule():
    """The one line that decides whether a match is a page control."""
    for line in driver_source().splitlines():
        if "$PageControl -and" in line:
            return line.strip()
    raise AssertionError("the driver no longer tests the PageControl switch")


def test_the_driver_exists_where_the_runbook_points():
    assert DRIVER.is_file(), DRIVER


def test_the_rule_requires_a_number_rather_than_any_id():
    rule = page_control_rule()
    assert re.search(r"-notmatch\s+'\^\\d\+\$'", rule), rule


def test_the_rule_refuses_every_title_bar_id_the_window_reported():
    """The old rule kept an id of any shape, so it kept the title bar."""
    for control in OBSERVED_CONTROLS:
        keeps = bool(re.fullmatch(r"\d+", control["automation_id"]))
        assert keeps == control["page_control"], control
        kept_by_the_old_rule = bool(control["automation_id"])
        if not control["page_control"]:
            assert kept_by_the_old_rule, control


def test_the_switch_is_used_wherever_a_name_is_shared_with_the_title_bar():
    source = driver_source()
    shared_names = ("'Close'", "'Uninstall'", "'Repair'", "'Install Vadgr'")
    for call in re.findall(r"Find-Control[^\n]*", source):
        if "function" in call:
            continue
        if any(name in call for name in shared_names):
            assert "-PageControl" in call, call


def test_the_measurement_is_recorded_beside_the_rule():
    """A reader who finds the rule finds why it asks for a number."""
    source = driver_source()
    assert "reports the id `Close`" in source, \
        "the comment no longer records what the title bar button reported"
