#!/usr/bin/env bash
# Setup computer_use engine on Linux (Ubuntu/Debian, GNOME Wayland).
# Run from Vadgr root: bash computer_use/setup-linux.sh
#
# Use --no-apt to skip system packages if already installed.

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
SKIP_APT=false

for arg in "$@"; do
    case $arg in
        --no-apt) SKIP_APT=true ;;
    esac
done

echo "=== Computer Use: Linux Setup ==="
echo ""

# --- System packages ---
if [ "$SKIP_APT" = true ]; then
    echo "Skipping apt packages (--no-apt)."
else
    echo "Installing system packages..."
    sudo apt update -qq
    sudo apt install -y -qq \
        python3-venv \
        xdotool \
        gnome-screenshot \
        wl-clipboard \
        2>/dev/null
    echo "Done."
fi
echo ""

# --- Python venv ---
# --system-site-packages gives access to dbus-python, which is a system
# package that can't be pip installed. Required for Mutter RemoteDesktop.
if [ -d "$VENV" ]; then
    echo "Removing existing venv..."
    rm -rf "$VENV"
fi

echo "Creating venv (with system-site-packages for dbus-python)..."
python3 -m venv --system-site-packages "$VENV"

echo "Installing Python dependencies..."
"$VENV/bin/pip" install --quiet -r "$ROOT/computer_use/requirements.txt"
echo "Done."
echo ""

# --- .mcp.json ---
MCP_JSON="$ROOT/.mcp.json"
if [ ! -f "$MCP_JSON" ]; then
    echo "Creating .mcp.json..."
    cat > "$MCP_JSON" <<EOF
{
  "mcpServers": {
    "computer_use": {
      "type": "stdio",
      "command": "$VENV/bin/python",
      "args": ["-m", "computer_use.mcp_server"],
      "cwd": "$ROOT",
      "env": {
        "PYTHONPATH": "$ROOT",
        "AGENT_FORGE_DEBUG": "1"
      }
    }
  }
}
EOF
    echo "Done."
else
    echo ".mcp.json already exists, skipping."
fi
echo ""

# --- Verify ---
echo "Verifying..."
FAIL=0

"$VENV/bin/python" -c "import dbus" 2>/dev/null \
    && echo "  dbus-python: OK" \
    || { echo "  dbus-python: MISSING (Mutter input won't work)"; FAIL=1; }

"$VENV/bin/python" -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null \
    && echo "  mcp: OK" \
    || { echo "  mcp: FAILED"; FAIL=1; }

"$VENV/bin/python" -c "from PIL import Image" 2>/dev/null \
    && echo "  Pillow: OK" \
    || { echo "  Pillow: FAILED"; FAIL=1; }

"$VENV/bin/python" -c "
import sys; sys.path.insert(0, '$ROOT')
from computer_use.platform.linux import LinuxBackend
b = LinuxBackend()
assert b.is_available()
" 2>/dev/null \
    && echo "  Linux backend: OK" \
    || { echo "  Linux backend: FAILED"; FAIL=1; }

echo ""
if [ $FAIL -eq 0 ]; then
    echo "Setup complete. Restart Claude Code to load the MCP server."
else
    echo "Setup finished with warnings. Check the output above."
fi
