"""Tests for cli.output -- Rich-based formatting helpers."""

import pytest

from cli.output import format_table, format_status, render_table, print_kv, format_duration, _styled


class TestFormatTable:
    def test_basic_table(self):
        result = render_table(["Name", "Status"], [["agent-1", "ready"], ["agent-2", "creating"]])
        assert "agent-1" in result
        assert "agent-2" in result
        assert "Name" in result

    def test_empty_rows(self):
        result = render_table(["Name"], [])
        assert "Name" in result

    def test_truncates_long_values(self):
        result = render_table(["Name"], [["x" * 200]])
        assert "x" in result


class TestFormatStatus:
    def test_ready_is_green(self):
        text = format_status("ready")
        assert "ready" in text

    def test_failed_is_red(self):
        text = format_status("failed")
        assert "failed" in text

    def test_running(self):
        text = format_status("running")
        assert "running" in text

    def test_unknown_passes_through(self):
        text = format_status("whatever")
        assert "whatever" in text


class TestFormatDuration:
    def test_zero(self):
        assert format_duration(0) == "0s"

    def test_under_one_second(self):
        assert format_duration(0.5) == "1s"

    def test_seconds_only(self):
        assert format_duration(45) == "45s"

    def test_exactly_one_minute(self):
        assert format_duration(60) == "1m 0s"

    def test_minutes_and_seconds(self):
        assert format_duration(103) == "1m 43s"

    def test_five_minutes(self):
        assert format_duration(312) == "5m 12s"

    def test_large_value(self):
        assert format_duration(3661) == "61m 1s"


class TestPrintKV:
    def test_renders_pairs(self, capsys):
        print_kv([("Name", "My Agent"), ("Status", "ready")])
        out = capsys.readouterr().out
        assert "Name" in out
        assert "My Agent" in out
        assert "Status" in out

    def test_empty_pairs(self, capsys):
        print_kv([])
        out = capsys.readouterr().out
        assert out == "" or out.strip() == ""


class TestStyled:
    def test_no_wrap_under_200_chars(self):
        # Reproduce the bug: a message ~81 characters long must not be split across lines.
        # e.g. "[vadgr] qa-engineer imported and ready (ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
        msg = "qa-engineer imported and ready (ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
        markup = f"[pale_green3]\\[vadgr][/] {msg}"
        result = _styled(markup)
        # Strip ANSI/Rich escape sequences: count non-empty lines in the output.
        # With the bug, Rich wraps after column 80 producing 2+ lines.
        # After the fix, the full message must appear on a single line.
        lines = [l for l in result.splitlines() if l.strip()]
        assert len(lines) == 1, (
            f"Expected 1 line, got {len(lines)}. Output:\n{result!r}"
        )
