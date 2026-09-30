"""The generic native driver must not pick another process or ambiguous control."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[2] / "E2E/0.5.0/harness/linux_atspi.py"
SPEC = importlib.util.spec_from_file_location("linux_atspi_harness", PATH)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)
ATSPI = SimpleNamespace(StateType=SimpleNamespace(ENABLED="enabled", CHECKED="checked", FOCUSED="focused", SHOWING="showing", EDITABLE="editable"))


class Node:
    def __init__(self, name="", role="button", pid=123, children=(), enabled=True):
        self.name, self.role, self.pid = name, role, pid
        self.children, self.enabled = children, enabled

    def get_child_count(self):
        return len(self.children)

    def get_child_at_index(self, index):
        return self.children[index]

    def get_process_id(self):
        return self.pid

    def get_name(self):
        return self.name

    def get_role_name(self):
        return self.role

    def get_state_set(self):
        return SimpleNamespace(contains=lambda state: state == "enabled" and self.enabled)

    def get_n_actions(self):
        return 0


def test_application_selection_is_pid_exact():
    owner = Node("Vadgr", pid=111)
    tested = Node("Vadgr", pid=222)
    assert DRIVER.select_app(Node(children=[owner, tested]), 222) is tested
    with pytest.raises(RuntimeError):
        DRIVER.select_app(Node(children=[owner]), 222)


def test_duplicate_control_names_require_exact_path():
    first, second = Node("Install"), Node("Install")
    rows = [(first, (0,)), (second, (1,))]
    with pytest.raises(RuntimeError):
        DRIVER.select_node(rows, "Install", "button", None, ATSPI)
    assert DRIVER.select_node(rows, "Install", "button", (1,), ATSPI) is second


def test_disabled_controls_are_not_invoked():
    with pytest.raises(RuntimeError):
        DRIVER.select_node([(Node("Install", enabled=False), (0,))], "Install", None, None, ATSPI)


def test_tree_is_bounded_and_preserves_paths():
    root = Node(children=[Node(children=[Node()])])
    assert [path for _, path in DRIVER.walk(root)] == [(), (0,), (0, 0)]
    with pytest.raises(RuntimeError):
        list(DRIVER.walk(root, limit=2))


def test_protected_control_name_is_not_printed():
    record = DRIVER.describe(Node("private-value", role="password text"), (1,), ATSPI)
    assert record["name"] == "<protected>"
    assert "private-value" not in str(record)
