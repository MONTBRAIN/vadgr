# Linux Setup

System dependencies and setup for the computer use engine on Linux.

## Requirements

### Input automation

**X11 sessions:**

```
# Debian/Ubuntu
sudo apt install xdotool

# Fedora
sudo dnf install xdotool

# Arch
sudo pacman -S xdotool
```

**Wayland sessions (GNOME):**

The engine uses Mutter's RemoteDesktop DBus interface for input injection. This is the standard GNOME way -- no extra packages needed beyond `dbus-python` (preinstalled on GNOME desktops).

For text input, the engine pastes via clipboard for strings > 3 chars:

```
# Debian/Ubuntu
sudo apt install wl-clipboard

# Fedora
sudo dnf install wl-clipboard

# Arch
sudo pacman -S wl-clipboard
```

**Wayland sessions (other compositors: Sway, Hyprland, etc.):**

Falls back to `python-evdev` which writes directly to kernel input devices.

```
pip install evdev
sudo usermod -aG input $USER
```

Then **log out and back in** for the group change to take effect.

If xdotool is also installed, it's kept as a fallback for X11 sessions.

### Screenshots

The engine auto-detects your display server and picks the right tool.

| Display server | Tool | Install |
|---|---|---|
| X11 | `mss` (Python) | `pip install mss` |
| Wayland (GNOME) | `gnome-screenshot` | Pre-installed on GNOME desktops |
| Wayland (Sway, Hyprland, etc.) | `grim` | `sudo apt install grim` / `sudo pacman -S grim` |

On Wayland, the engine probes each tool at startup and uses the first one that works.

### Python packages

```
pip install mss Pillow PyYAML
```

`mss` is only needed on X11. `evdev` only needed on non-GNOME Wayland. Both are safe to install everywhere.

## Quick check

```bash
# Display server
echo $XDG_SESSION_TYPE

# Mutter RemoteDesktop (GNOME Wayland)
busctl --user introspect org.gnome.Mutter.RemoteDesktop /org/gnome/Mutter/RemoteDesktop 2>/dev/null && echo "Mutter OK"

# Clipboard tool (Wayland)
which wl-copy && echo "wl-copy OK"

# Python deps
python3 -c "import PIL, yaml; print('OK')"

# Screenshot tool (Wayland/GNOME)
gnome-screenshot -f /tmp/test.png && echo "OK" && rm /tmp/test.png

# Screenshot tool (Wayland/wlroots)
grim /tmp/test.png && echo "OK" && rm /tmp/test.png
```

## How it works

**X11:**
- Screenshots via `mss` (X11 shared memory)
- Input via `xdotool`

**Wayland (GNOME):**
- Screenshots via `gnome-screenshot`
- Input via Mutter RemoteDesktop DBus interface (`org.gnome.Mutter.RemoteDesktop`)
- Absolute pointer positioning via linked ScreenCast session (`org.gnome.Mutter.ScreenCast`)
- Text typing: clipboard paste via `wl-copy` + Ctrl+V for strings > 3 chars, direct keycodes for short strings

**Wayland (other compositors):**
- Screenshots via `grim`
- Input via `python-evdev` writing to kernel input devices (`/dev/input/event*`)
- On VirtualBox VMs: writes to the VBox USB Tablet device (absolute positioning)
- On bare metal: creates a virtual device via uinput (relative positioning)

The engine detects Wayland via `WAYLAND_DISPLAY` and `XDG_SESSION_TYPE` environment variables.

## Executor priority

1. **Mutter RemoteDesktop** -- GNOME Wayland (preferred, no extra deps)
2. **evdev** -- Other Wayland compositors (needs python-evdev + input group)
3. **xdotool** -- X11 (fallback)

## Troubleshooting

**"XGetImage() failed"** -- You're on Wayland but only `mss` is available. Install `gnome-screenshot` or `grim`.

**"grim failed: compositor doesn't support wlr-screencopy-unstable-v1"** -- You're on GNOME Wayland. grim only works on wlroots compositors (Sway, Hyprland). Install `gnome-screenshot` instead.

**"No working Wayland screenshot tool found"** -- None of the supported screenshot tools are installed or working. Install one from the table above.

**Mouse doesn't move on Wayland** -- `xdotool mousemove` is a no-op on Wayland. On GNOME, the engine uses Mutter RemoteDesktop (should work out of the box). On other compositors, install `python-evdev` and add yourself to the `input` group.

**Clipboard paste not working** -- Install `wl-clipboard`: `sudo apt install wl-clipboard`.
