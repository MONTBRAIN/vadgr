# Vadgr 0.5.0 E2E harness

These helpers observe and drive the written cells. They do not replace a cell,
its oracle or the product under test.

## Linux diagnostic accessibility and window capture

The primary Linux driver is the separately installed Vadgr CUA MCP server
specified by the runbook. The current agent session must expose and call its
actual tools. These direct Linux helpers are diagnostic only; their output
does not establish MCP accessibility or capture coverage. Keep diagnostic
observations separate from the installed public-tool results.

For a diagnostic probe, use `linux_atspi.py` with system Python and the AT-SPI
GI bindings. Select the exact application PID. Reacquire its tree after each
transition, then invoke one enabled control by its exact name or fresh tree
path. The helper refuses ambiguous controls. Supply text through stdin with
`--value-stdin`; never put
credentials in command arguments or retain a secret-bearing tree.
The native interaction test is `SENSITIVE` and not `DEFUNCT`; GTK can omit the
separate `ENABLED` state. Tree output preserves both states. For a shared
portal chooser, repeat `--tree-allow-name` with only known test-window and
control names. All other nonempty names are redacted without changing exact
action targeting.
Use `select` for a list item whose parent exposes native Selection. The helper
checks the exact parent and child identity and reads selection back before
reporting acceptance. It never substitutes a click or keyboard event. If a
tree's advertised Action interface fails, that node has `actions: null` and
an `actions_error` class. Other nodes remain visible, but the tree command
exits nonzero. Preserve the error; do not treat it as an empty action list or
a passing oracle.

```sh
/usr/bin/python3 E2E/0.5.0/harness/linux_atspi.py tree --pid "$E2E_APP_PID"
/usr/bin/python3 E2E/0.5.0/harness/linux_atspi.py act --pid "$E2E_APP_PID" --name Settings --action click
```

Use the action name exposed by the fresh tree, not an assumed action name.
An accepted accessibility call is not a product verdict: inspect the visible
result and the cell's independent machine oracle. Do not substitute keyboard
or coordinate input for a refused semantic action. The diagnostic helper is
not a replacement for the runbook's primary exposed CUA MCP tools.

For a Wayland diagnostic, `linux_portal_capture.py` requests exactly one WINDOW
through the XDG Desktop Portal and reads its scoped PipeWire stream. It requires
GI, GStreamer, `pipewiresrc`, `videoconvert`, `pngenc`, and `appsink`. Drive the
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
A successful direct-helper capture remains diagnostic. It does not satisfy a
cell that requires the released public MCP capture path. The current Linux
runbook separately permits owner-approved focused `screenshot_region` visual
inspection through actual MCP tools. Follow its fresh bounds, before/after
focus and privacy checks. That exception does not make this diagnostic helper
qualifying, and never proves unfocused window capture.

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

### The `scroll` action, and why it proves a point rather than an element

`act --action scroll` performs one real wheel gesture over the selected
element. Use `--scroll-clicks`: a negative count scrolls down and a positive
count scrolls up, which is the sign the operating system uses. It prints the
point it used, the notch count, and every named row whose top edge moved,
read from the accessibility tree before and after the gesture.

Use it only when the cell asks for the user gesture. A product that scrolls its
own list to a selection is driven through `select` or `invoke`, which cannot
reach another application at all.

A wheel event goes to the window under the pointer, so the element it was aimed
at proves nothing about where it lands. Before every notch the helper proves
that the target window is the foreground window, that the window under the
point has the same top level window, and that UI Automation reads that point as
the target process. Any one of those failing exits non zero and sends nothing.
The pointer returns to where the owner left it.

This action needs the physical console session. A remote session reports no
foreground window, and `SPI_SETFOREGROUNDLOCKTIMEOUT` refuses with error 87
there, so the proof above cannot pass and the helper refuses rather than
sending a notch into another window.

### Use `--full-content`, and read `flat_share`

`capture` passes `PW_RENDERFULLCONTENT` only with `--full-content`. Pass it for
every surface this product draws, the console and the installer alike.

Without it, the installer's composited areas come back with their colour intact
and their alpha zeroed. Measured on 2026-10-23, 97.1 percent of such a capture
was fully transparent: it looks blank in any viewer, while the colour data
underneath still looks busy to anything that ignores alpha. With the flag, the
same window comes back whole and fully opaque once it has finished painting.

Give the window that moment. A capture taken while it is still painting shows
part of itself, and that is what a previous pass filed as an unexplained
observation, and what then produced a second wrong explanation about the flags.

Every capture prints `flat_share`, the share of the image a reader would see as
the single most common colour, counting a transparent pixel as the background
that shows through it. A capture that is entirely one colour is refused
outright, because it never rendered. A high but incomplete share is reported
rather than refused, so read the number before filing the image.

## `windows_sandbox_o1.ps1` and `windows_sandbox_o1_inside.ps1`

These two run the O1 offline lifecycle on Windows. O1 needs an isolated
snapshot whose external network is already unavailable, and it forbids any
change to the host firewall, DNS, routes, proxy or VPN. A Windows Sandbox
session configured with no network adapter satisfies both: the guest has no
route to anything, the host keeps every setting it had, and the snapshot is
discarded when its window closes.

`windows_sandbox_o1.ps1` stays on the host. It proves the feature is present,
assembles the single folder the guest can see, writes the configuration, starts
the session and waits for the record the guest writes back. The guest sees that
one folder: no owner profile, no credential file and no source tree.

`windows_sandbox_o1_inside.ps1` runs as the logon command inside the snapshot.
It measures the isolation before anything is installed, drives the installation
vehicle through its own window, because a new installation refuses a quiet
install by design, then launches the CLI and the console, reads the bundled
legal notices, restarts the daemon twice, repairs, reads the rollback state and
uninstalls. Every step appends to `o1-record.json` as it happens, because the
snapshot can be closed at any moment and a step with no record is not a result.

```powershell
powershell -NoProfile -File E2E\0.5.0\harness\windows_sandbox_o1.ps1 `
    -Vehicle <pass root>\vehicle\Vadgr-0.5.0-windows-x64-setup.exe `
    -WorkRoot <pass root>\o1
```

Windows Sandbox needs the optional feature `Containers-DisposableClientVM`,
which an administrator enables once and which needs a restart. That is an
elevated prompt and a restart, so it belongs to the owner. The host script
refuses with the feature state rather than asking for elevation itself.
