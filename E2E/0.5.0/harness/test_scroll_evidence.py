"""The scroll oracle must tell a scrolled list from a refused gesture.

The Windows probe on 2026-10-17 posted and sent wheel messages to the console
window and read every row back at the same coordinates. That is the exact
shape this oracle has to report as no movement, because a helper that calls a
refused gesture a pass turns an owed cell into a false one.

These tests use recorded row shapes rather than a live window, so they run on
any host.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from windows_uia import moved_rows  # noqa: E402


def row(name, top, control_type="ListItem"):
    return {"name": name, "control_type": control_type,
            "rectangle": [100, top, 400, top + 24]}


def test_an_unchanged_list_reports_no_movement():
    rows = [row("claude-sonnet-5", 200), row("claude-haiku-5-5", 224)]
    assert moved_rows(rows, [dict(item) for item in rows]) == []


def test_a_scrolled_list_reports_every_row_that_moved():
    before = [row("claude-sonnet-5", 200), row("claude-haiku-5-5", 224)]
    after = [row("claude-sonnet-5", 128), row("claude-haiku-5-5", 152)]
    moved = moved_rows(before, after)
    assert [item["name"] for item in moved] == ["claude-sonnet-5", "claude-haiku-5-5"]
    assert all(item["top_before"] - item["top_after"] == 72 for item in moved)


def test_a_row_that_only_appears_after_the_gesture_is_not_movement():
    # A row scrolled into view has no earlier position, so it cannot be
    # evidence of movement by itself.
    before = [row("claude-sonnet-5", 200)]
    after = [row("claude-sonnet-5", 200), row("gemini-2.5-flash-lite", 224)]
    assert moved_rows(before, after) == []


def test_a_repeated_name_is_not_followed_across_the_gesture():
    # Two rows with the same name cannot be matched one to one, and guessing
    # would report movement that was never observed.
    before = [row("Model", 200), row("Model", 224)]
    after = [row("Model", 128), row("Model", 152)]
    assert moved_rows(before, after) == []


def test_a_row_with_no_name_is_ignored():
    before = [{"name": "", "rectangle": [0, 10, 10, 20]}]
    after = [{"name": "", "rectangle": [0, 99, 10, 109]}]
    assert moved_rows(before, after) == []


def test_a_row_with_no_rectangle_is_ignored():
    before = [{"name": "Model"}]
    after = [{"name": "Model", "rectangle": [0, 99, 10, 109]}]
    assert moved_rows(before, after) == []


def test_horizontal_change_alone_is_not_a_scroll():
    before = [row("claude-sonnet-5", 200)]
    after = [{"name": "claude-sonnet-5", "control_type": "ListItem",
              "rectangle": [140, 200, 440, 224]}]
    assert moved_rows(before, after) == []


def test_the_wheel_gesture_proves_the_point_before_it_sends_anything():
    """The ownership proof is the rule this helper exists under.

    The incident on 2026-10-17 came from a helper that named its target and
    sent input anyway. A wheel event is delivered by position, so the check
    that matters is the window under the point, and it has to run inside the
    notch loop rather than once at the start.
    """
    source = (pathlib.Path(__file__).resolve().parent / "windows_uia.py").read_text(
        encoding="utf-8"
    )
    body = source.split("def scroll_over(")[1].split("\ndef ")[0]
    proof = body.index("require_pointer_ownership(window, x, y)")
    event = body.index("mouse_event(MOUSEEVENTF_WHEEL")
    assert proof < event, "the point must be proved before the notch is sent"
    assert "for _ in range(abs(clicks))" in body[:proof], "the proof runs per notch"
    assert "SetCursorPos(int(origin.x), int(origin.y))" in body, "the pointer is restored"
    # The list moves under the pointer, so each notch has its own recipient and
    # keeping only the last one reads as a contradiction of the rectangles.
    assert "received.append(" in body, "every notch records what received it"
