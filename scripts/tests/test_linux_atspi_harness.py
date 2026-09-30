"""The generic native driver must not pick another process or ambiguous control."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[2] / "E2E/0.5.0/harness/linux_atspi.py"
SPEC = importlib.util.spec_from_file_location("linux_atspi_harness", PATH)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)
ATSPI = SimpleNamespace(StateType=SimpleNamespace(ENABLED="enabled", SENSITIVE="sensitive", DEFUNCT="defunct", CHECKED="checked", FOCUSED="focused", SHOWING="showing", EDITABLE="editable"))


class Node:
    def __init__(self, name="", role="button", pid=123, children=(), enabled=True, states=None):
        self.name, self.role, self.pid = name, role, pid
        self.children, self.enabled = children, enabled
        self.states = set(states) if states is not None else ({"enabled", "sensitive"} if enabled else set())

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
        return SimpleNamespace(contains=lambda state: state in self.states)

    def get_action_iface(self):
        return self

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


def test_sensitive_gtk_control_does_not_need_enabled_state():
    node = Node("OK", states={"sensitive", "showing"})
    assert DRIVER.select_node([(node, (0,))], "OK", "button", None, ATSPI) is node
    record = DRIVER.describe(node, (0,), ATSPI)
    assert record["sensitive"] and record["available"]
    assert not record["enabled"]


@pytest.mark.parametrize("states", [set(), {"enabled"}, {"enabled", "sensitive", "defunct"}])
def test_insensitive_or_defunct_controls_remain_unavailable(states):
    node = Node("OK", states=states)
    with pytest.raises(RuntimeError):
        DRIVER.select_node([(node, (0,))], "OK", "button", None, ATSPI)
    assert not DRIVER.describe(node, (0,), ATSPI)["available"]


def test_missing_action_interface_is_not_queried():
    class NoAction(Node):
        def get_action_iface(self):
            return None

        def get_n_actions(self):
            raise AssertionError("unsupported interface was queried")

    assert DRIVER.describe(NoAction(role="application"), (), ATSPI)["actions"] == []


def test_action_interface_is_used_instead_of_accessible_convenience_methods():
    class WithAction(Node):
        def get_action_iface(self):
            return SimpleNamespace(get_n_actions=lambda: 1, get_action_name=lambda index: "click")

        def get_n_actions(self):
            raise AssertionError("wrong interface was queried")

    assert DRIVER.describe(WithAction(), (), ATSPI)["actions"] == ["click"]


@pytest.mark.parametrize("stage", ["discovery", "count", "name"])
def test_advertised_action_errors_are_not_hidden(stage):
    class NativeFailure(Exception):
        pass

    def fail(*args):
        raise NativeFailure("synthetic transport failure")

    node = Node()
    if stage == "discovery":
        node.get_action_iface = fail
    elif stage == "count":
        node.get_n_actions = fail
    else:
        node.get_n_actions = lambda: 1
        node.get_action_name = fail
    with pytest.raises(NativeFailure):
        DRIVER.describe(node, (), ATSPI)


@pytest.mark.parametrize("name,expected", [
    ("Vadgr E2E capture fixture", "Vadgr E2E capture fixture"),
    ("Share", "Share"), ("Cancel", "Cancel"), ("", ""),
    ("share", "<redacted>"), ("unrelated private window", "<redacted>"),
])
def test_tree_name_allowlist_is_exact_and_output_only(name, expected):
    node = Node(name)
    allowed = {"Vadgr E2E capture fixture", "Share", "Cancel"}
    record = DRIVER.describe(node, (1,), ATSPI, allowed)
    assert record["name"] == expected
    assert record["path"] == "1" and record["role"] == "button"
    assert record["sensitive"] and record["available"]
    assert DRIVER.select_node([(node, (1,))], name, "button", None, ATSPI) is node
    assert DRIVER.describe(node, (1,), ATSPI)["name"] == name


def test_password_name_stays_protected_even_when_allowlisted():
    record = DRIVER.describe(Node("synthetic-secret", role="password text"), (), ATSPI, {"synthetic-secret"})
    assert record["name"] == "<protected>"
