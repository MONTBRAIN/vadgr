# Vadgr 0.5.0 E2E harness

These helpers observe and drive the written cells. They do not replace a cell,
its oracle or the product under test.

## `windows_uia.py`

Use this helper on native Windows with Python, `pywinauto`, `comtypes` and
Pillow. It discovers and invokes semantic controls through Windows UI
Automation. Its `capture` command uses `PrintWindow(PW_CLIENTONLY)` under a
per-monitor-aware DPI context to save only the target application's client
area. The capture does not focus the target window.

Select one window with `--pid` or `--title-regex`. Use `--focus-window` only
when a visible interactive action needs focus. Use `--restore-window` when the
target is hidden or minimized but focus is not part of the action. Use
`--enabled-only` when a modal and its disabled background expose controls with
the same accessible name. Use `--automation-id` when enabled controls share a
name; pass the literal value `<empty>` only when the intended element has an
empty automation ID.

Examples:

```powershell
python E2E\0.5.0\harness\windows_uia.py tree --title-regex '^Vadgr$'
python E2E\0.5.0\harness\windows_uia.py act --title-regex '^Vadgr$' --name Settings --control-type Button --action toggle
python E2E\0.5.0\harness\windows_uia.py capture --title-regex '^Vadgr$' --output .\vadgr-client.png
```

Never use a screenshot to locate a control. Reacquire the UI Automation tree
after every transition, and verify mutations with the independent oracle named
by the cell. Do not file captures that contain credentials or owner-private
identifiers.
