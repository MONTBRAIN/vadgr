"""The generic native driver must not pick another process or ambiguous control."""
import importlib.util
import json
import sys
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
    record = DRIVER.describe(node, (), ATSPI)
    assert record["actions"] is None
    assert record["actions_error"] == "NativeFailure"
    assert "synthetic transport failure" not in str(record)
    with pytest.raises(NativeFailure):
        DRIVER.action_names(node.get_action_iface())


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


def selection_fixture():
    child = Node("fixture", role="list item", states={"sensitive"})
    parent = Node(role="list", children=[Node(), child])
    calls = []
    selected = set()

    def select(index):
        calls.append(index)
        selected.add(index)
        return True

    selection = SimpleNamespace(select_child=select, is_child_selected=lambda index: index in selected)
    parent.get_selection_iface = lambda: selection
    child.get_parent = lambda: parent
    child.get_index_in_parent = lambda: 1
    return child, parent, selection, calls


def test_native_selection_uses_exact_parent_child_index_and_readback():
    child, parent, selection, calls = selection_fixture()
    assert DRIVER.select_child(child, ATSPI)
    assert calls == [1]
    assert selection.is_child_selected(1)


@pytest.mark.parametrize("invalid", ["missing-parent", "foreign-parent", "negative-index", "large-index", "wrong-child", "missing-interface", "insensitive", "defunct"])
def test_selection_rejects_invalid_identity_or_capability_before_action(invalid):
    child, parent, selection, calls = selection_fixture()
    if invalid == "missing-parent":
        child.get_parent = lambda: None
    elif invalid == "foreign-parent":
        parent.pid = 456
    elif invalid == "negative-index":
        child.get_index_in_parent = lambda: -1
    elif invalid == "large-index":
        child.get_index_in_parent = lambda: 2
    elif invalid == "wrong-child":
        parent.children[1] = Node()
    elif invalid == "missing-interface":
        parent.get_selection_iface = lambda: None
    elif invalid == "insensitive":
        child.states = {"enabled"}
    else:
        child.states.add("defunct")
    with pytest.raises(RuntimeError):
        DRIVER.select_child(child, ATSPI)
    assert calls == []


@pytest.mark.parametrize("failure", ["refused", "unselected", "reparented", "reindexed", "replaced"])
def test_selection_requires_success_and_stable_selected_readback(failure):
    child, parent, selection, calls = selection_fixture()
    original = selection.select_child

    def select(index):
        original(index)
        if failure == "reparented":
            child.get_parent = lambda: Node()
        elif failure == "reindexed":
            child.get_index_in_parent = lambda: 0
        elif failure == "replaced":
            parent.children[1] = Node()
        return failure != "refused"

    selection.select_child = select
    if failure == "unselected":
        selection.is_child_selected = lambda index: False
    with pytest.raises(RuntimeError):
        DRIVER.select_child(child, ATSPI)
    assert calls == [1]


def fake_gi(monkeypatch, app):
    atspi = SimpleNamespace(StateType=ATSPI.StateType, init=lambda: None, exit=lambda: None,
                            get_desktop=lambda index: Node(children=[app]))
    monkeypatch.setitem(sys.modules, "gi", SimpleNamespace(require_version=lambda *args: None))
    monkeypatch.setitem(sys.modules, "gi.repository", SimpleNamespace(Atspi=atspi))


def test_tree_emits_remaining_nodes_but_returns_failure_on_action_query_error(monkeypatch, capsys):
    broken = Node("private", role="label")

    def fail():
        raise RuntimeError("private native error text")

    broken.get_n_actions = fail
    fake_gi(monkeypatch, Node(role="application", children=[broken, Node("Share")]))
    assert DRIVER.main(["tree", "--pid", "123", "--tree-allow-name", "Share"]) == 1
    output = capsys.readouterr().out
    records = json.loads(output)
    assert len(records) == 3
    assert records[1]["actions"] is None and records[1]["actions_error"] == "RuntimeError"
    assert records[2]["name"] == "Share" and records[2]["actions"] == []
    assert "private" not in output


def test_select_command_requires_one_exact_match_and_reports_verified_acceptance(monkeypatch, capsys):
    child, parent, selection, calls = selection_fixture()
    fake_gi(monkeypatch, parent)
    assert DRIVER.main(["select", "--pid", "123", "--path", "1", "--name", "fixture", "--role", "list item"]) == 0
    assert calls == [1]
    assert json.loads(capsys.readouterr().out)["accepted"] is True
    parent.children.append(Node("fixture", role="list item"))
    with pytest.raises(RuntimeError, match="found 2"):
        DRIVER.main(["select", "--pid", "123", "--name", "fixture"])
    assert calls == [1]


def test_action_invocation_errors_still_fail_without_acceptance(monkeypatch, capsys):
    node = Node("Share")
    node.get_n_actions = lambda: 1
    node.get_action_name = lambda index: "click"

    def fail(index):
        raise RuntimeError("synthetic native failure")

    node.do_action = fail
    fake_gi(monkeypatch, Node(children=[node]))
    with pytest.raises(RuntimeError):
        DRIVER.main(["act", "--pid", "123", "--name", "Share", "--action", "click"])
    assert not capsys.readouterr().out
