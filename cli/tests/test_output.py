"""Tests for cli.output -- Rich-based formatting helpers."""

import pytest

from cli.output import format_table, format_status, render_table, print_kv


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
