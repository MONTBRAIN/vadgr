# Vadgr 0.5.0 E2E harness

These helpers observe and drive the written cells. They do not replace a cell,
its oracle or the product under test.

## Linux native accessibility and window capture

Use `linux_atspi.py` with system Python and the AT-SPI GI bindings. Select the
exact application PID. Reacquire its tree after each transition, then invoke
one enabled control by its exact name or fresh tree path. The helper refuses
ambiguous controls. Supply text through stdin with `--value-stdin`; never put
credentials in command arguments or retain a secret-bearing tree.

```sh
/usr/bin/python3 E2E/0.5.0/harness/linux_atspi.py tree --pid "$E2E_APP_PID"
/usr/bin/python3 E2E/0.5.0/harness/linux_atspi.py act --pid "$E2E_APP_PID" --name Settings --action click
```

Use the action name exposed by the fresh tree, not an assumed action name.
An accepted accessibility call is not a product verdict: inspect the visible
result and the cell's independent machine oracle. There is no keyboard,
coordinate-click, or Vadgr CUA fallback.

On Wayland, `linux_portal_capture.py` requests exactly one WINDOW through the
XDG Desktop Portal and reads its scoped PipeWire stream. It requires GI,
GStreamer, `pipewiresrc`, `videoconvert`, `pngenc`, and `appsink`. Drive the
portal's ordinary window chooser through native accessibility. Select only
the application under test; never select the desktop or an owner application.

```sh
/usr/bin/python3 E2E/0.5.0/harness/linux_portal_capture.py --output "$E2E_PRIVATE_CAPTURE" --timeout 120 --delay 15
```

After the `window_selected` event, focus a different test application during
the delay and independently record that focus state. The helper starts frame
acquisition after the delay; it does not establish the unfocused oracle on
its own. Inspect the image before retaining it. No desktop screenshot, crop,
or focused-only substitute is permitted. The output must be a new private
PNG path. Sessions, requests, the stream, and file descriptors are closed on
exit. A denied or protected portal action is recorded as its exact boundary,
not as a capture pass.

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
