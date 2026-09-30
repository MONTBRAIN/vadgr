#!/usr/bin/env python3
"""Inspect or invoke one explicitly selected native accessibility control."""
from __future__ import annotations

import argparse
import json
import sys


def walk(node, path=(), limit=4096):
    pending = [(node, path)]
    count = 0
    while pending:
        current, location = pending.pop()
        count += 1
        if count > limit:
            raise RuntimeError("Accessibility tree exceeded the bounded node count")
        yield current, location
        children = [current.get_child_at_index(i) for i in range(current.get_child_count())]
        pending.extend((child, location + (index,)) for index, child in reversed(list(enumerate(children))) if child is not None)


def select_app(desktop, pid):
    matches = [desktop.get_child_at_index(i) for i in range(desktop.get_child_count())]
    matches = [app for app in matches if app is not None and app.get_process_id() == pid]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one accessible application for PID; found {len(matches)}")
    return matches[0]


def select_node(rows, name, role, location, atspi):
    matches = []
    for node, path in rows:
        if location is not None and path != location:
            continue
        if name is not None and node.get_name() != name:
            continue
        if role is not None and node.get_role_name() != role:
            continue
        if not node.get_state_set().contains(atspi.StateType.ENABLED):
            continue
        matches.append(node)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one enabled exact control; found {len(matches)}")
    return matches[0]


def describe(node, path, atspi):
    state = node.get_state_set()
    role = node.get_role_name()
    protected = role == "password text"
    return {
        "path": "/".join(map(str, path)),
        "name": "<protected>" if protected else node.get_name(),
        "role": role,
        "actions": [node.get_action_name(i) for i in range(node.get_n_actions())],
        "enabled": state.contains(atspi.StateType.ENABLED),
        "checked": state.contains(atspi.StateType.CHECKED),
        "focused": state.contains(atspi.StateType.FOCUSED),
        "showing": state.contains(atspi.StateType.SHOWING),
        "editable": state.contains(atspi.StateType.EDITABLE),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("tree", "act", "set-text", "focus"))
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--name")
    parser.add_argument("--role")
    parser.add_argument("--path", help="Exact fresh tree path, such as 0/1/2")
    parser.add_argument("--action", help="Exact action name from the fresh tree")
    parser.add_argument("--window", help="Limit reads to one exact named frame or dialog")
    parser.add_argument("--value-stdin", action="store_true", help="Read replacement text from stdin; never print it")
    args = parser.parse_args(argv)
    if args.command != "tree" and args.name is None and args.path is None:
        parser.error("An exact --name or --path is required for an action")
    if args.command == "set-text" and not args.value_stdin:
        parser.error("Text must enter through --value-stdin")
    if args.command == "act" and args.action is None:
        parser.error("An exact --action is required")
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    Atspi.init()
    try:
        app = select_app(Atspi.get_desktop(0), args.pid)
        if args.window:
            windows = [node for node, _ in walk(app) if node.get_role_name() in ("frame", "dialog") and node.get_name() == args.window]
            if len(windows) != 1:
                raise RuntimeError(f"Expected one exact window; found {len(windows)}")
            app = windows[0]
        rows = list(walk(app))
        if args.command == "tree":
            print(json.dumps([describe(node, path, Atspi) for node, path in rows], indent=2))
            return 0
        location = tuple(map(int, args.path.split("/"))) if args.path else None
        node = select_node(rows, args.name, args.role, location, Atspi)
        if args.command == "focus":
            success = node.grab_focus()
        elif args.command == "set-text":
            value = sys.stdin.read()
            success = node.set_text_contents(value)
        else:
            actions = [i for i in range(node.get_n_actions()) if node.get_action_name(i) == args.action]
            if len(actions) != 1:
                raise RuntimeError("The control does not expose exactly the requested action")
            success = node.do_action(actions[0])
        if not success:
            raise RuntimeError("Native accessibility action was refused")
        print(json.dumps({"action": args.command, "accepted": True, "oracle": "reacquire the tree and inspect the independent product result"}))
        return 0
    finally:
        Atspi.exit()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Native errors can include window contents or paths. Do not echo them.
        print(f"Accessibility command failed ({type(error).__name__}).", file=sys.stderr)
        raise SystemExit(1)
