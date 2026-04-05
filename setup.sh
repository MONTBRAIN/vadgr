#!/usr/bin/env bash
set -e

# Vadgr Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/MONTBRAIN/Agent-Forge/master/setup.sh | bash

FORGE_HOME="$HOME/.forge"
FORGE_BIN="$FORGE_HOME/bin"
FORGE_REPO="$FORGE_HOME/Agent-Forge"
REPO_URL="https://github.com/MONTBRAIN/Agent-Forge.git"
NVM_VERSION="v0.40.3"
REQUIRED_PYTHON_MINOR=12

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { printf "\033[1;34m[vadgr]\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m[vadgr]\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m[vadgr]\033[0m %s\n" "$*"; }
fail()  { printf "\033[1;31m[vadgr]\033[0m %s\n" "$*" >&2; exit 1; }

detect_os() {
    case "$(uname -s)" in
        Linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        Darwin*) echo "macos" ;;
        *)       fail "Unsupported OS: $(uname -s). Use WSL on Windows." ;;
    esac
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

# Check if Python 3.12+ is available
python_ok() {
    if ! command_exists python3; then return 1; fi
    local ver
    ver=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null) || return 1
    [ "$ver" -ge "$REQUIRED_PYTHON_MINOR" ]
}

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------

install_homebrew() {
    if command_exists brew; then return; fi
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add to current session
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
}

install_git() {
    if command_exists git; then return; fi
    info "Installing git..."
    case "$OS" in
        linux|wsl)
            if command_exists apt-get; then
                sudo apt-get update -qq && sudo apt-get install -y -qq git
            elif command_exists dnf; then
                sudo dnf install -y -q git
            elif command_exists pacman; then
                sudo pacman -S --noconfirm git
            else
                fail "No supported package manager found. Install git manually."
            fi
            ;;
        macos)
            install_homebrew
            brew install git
            ;;
    esac
}

install_python() {
    if python_ok; then return; fi
    info "Installing Python 3.12+..."
    case "$OS" in
        linux|wsl)
            if command_exists apt-get; then
                sudo apt-get update -qq
                sudo apt-get install -y -qq software-properties-common
                sudo add-apt-repository -y ppa:deadsnakes/ppa
                sudo apt-get update -qq
                sudo apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
                if ! python_ok; then
                    sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
                fi
            elif command_exists dnf; then
                sudo dnf install -y -q python3.12 python3.12-devel
            elif command_exists pacman; then
                sudo pacman -S --noconfirm python
            else
                fail "No supported package manager found. Install Python 3.12+ manually."
            fi
            ;;
        macos)
            install_homebrew
            brew install python@3.12
            if ! python_ok; then
                export PATH="$(brew --prefix python@3.12)/bin:$PATH"
            fi
            ;;
    esac
    python_ok || fail "Python 3.12+ installation failed."
}

install_nvm_and_node() {
    if command_exists node; then
        info "Node.js already installed: $(node --version)"
        return
    fi

    # Install NVM if not present
    if [ -z "${NVM_DIR:-}" ] || [ ! -d "${NVM_DIR:-}" ]; then
        info "Installing NVM..."
        export NVM_DIR="$HOME/.nvm"
        local nvm_tmp
        nvm_tmp=$(mktemp)
        curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" -o "$nvm_tmp"
        bash "$nvm_tmp"
        rm -f "$nvm_tmp"
        # Load NVM into current session
        [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    else
        [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
    fi

    info "Installing Node.js LTS via NVM..."
    nvm install --lts
    nvm use --lts
}

# ---------------------------------------------------------------------------
# Setup Vadgr
# ---------------------------------------------------------------------------

setup_repo() {
    if [ -d "$FORGE_REPO/.git" ]; then
        info "Vadgr repo already exists, pulling latest..."
        git -C "$FORGE_REPO" pull --ff-only origin master || warn "Could not pull latest (offline?)"
        # Restore tracked files that were deleted locally
        local deleted
        deleted=$(git -C "$FORGE_REPO" diff --name-only --diff-filter=D 2>/dev/null)
        if [ -n "$deleted" ]; then
            (cd "$FORGE_REPO" && echo "$deleted" | while IFS= read -r f; do git checkout -- "$f" 2>/dev/null; done)
        fi
    else
        info "Cloning Vadgr..."
        mkdir -p "$FORGE_HOME"
        git clone "$REPO_URL" "$FORGE_REPO"
    fi
}

ensure_venv_module() {
    if python3 -m venv --help >/dev/null 2>&1; then return; fi
    info "Installing python3-venv package..."
    local py_minor
    py_minor=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
    if command_exists apt-get; then
        sudo apt-get install -y -qq "python3.${py_minor}-venv" || sudo apt-get install -y -qq python3-venv
    elif command_exists dnf; then
        sudo dnf install -y -q python3-libs
    elif command_exists pacman; then
        sudo pacman -S --noconfirm python
    fi
    python3 -m venv --help >/dev/null 2>&1 || fail "python3 venv module not available. Install it manually."
}

setup_venv() {
    local dir="$1" req="$2"
    if [ ! -d "$dir" ] || ! "$dir/bin/python3" -m pip --version >/dev/null 2>&1; then
        rm -rf "$dir"
        ensure_venv_module
        python3 -m venv "$dir" || fail "Failed to create venv at $dir"
    fi
    "$dir/bin/pip" install -q -r "$req"
}

setup_api() {
    info "Setting up API..."
    cd "$FORGE_REPO"
    setup_venv "api/.venv" "api/requirements.txt"
    mkdir -p data
}

setup_forge_scripts() {
    info "Setting up vadgr scripts..."
    cd "$FORGE_REPO"
    setup_venv "forge/scripts/.venv" "forge/scripts/requirements.txt"
}

setup_cli() {
    info "Setting up CLI..."
    cd "$FORGE_REPO"
    setup_venv "cli/.venv" "cli/requirements.txt"
}

setup_frontend() {
    info "Setting up frontend..."
    cd "$FORGE_REPO/frontend"

    # Load NVM if available (needed for npm)
    if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
        . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
    fi

    npm install --silent
}

# ---------------------------------------------------------------------------
# Generate forge CLI
# ---------------------------------------------------------------------------

generate_forge_cli() {
    info "Creating vadgr CLI..."
    mkdir -p "$FORGE_BIN"
    cat > "$FORGE_BIN/vadgr" << 'FORGE_SCRIPT'
#!/usr/bin/env bash
FORGE_REPO="$HOME/.forge/Agent-Forge"
cli_python="$FORGE_REPO/cli/.venv/bin/python"
[ -f "$cli_python" ] || { echo "[vadgr] CLI not found. Run setup.sh first." >&2; exit 1; }
PYTHONPATH="$FORGE_REPO" exec "$cli_python" -m cli "$@"
FORGE_SCRIPT
    chmod +x "$FORGE_BIN/vadgr"
}

# ---------------------------------------------------------------------------
# Add to PATH
# ---------------------------------------------------------------------------

add_to_path() {
    local line="export PATH=\"$FORGE_BIN:\$PATH\""
    local found=0

    for rcfile in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ ! -f "$rcfile" ]; then continue; fi
        if ! grep -qF "$FORGE_BIN" "$rcfile" 2>/dev/null; then
            echo "" >> "$rcfile"
            echo "# VADGR" >> "$rcfile"
            echo "$line" >> "$rcfile"
            info "Added vadgr to PATH in $(basename "$rcfile")"
        fi
        found=1
    done

    if [ "$found" -eq 0 ]; then
        local default_rc="$HOME/.bashrc"
        if [ "$OS" = "macos" ]; then default_rc="$HOME/.zshrc"; fi
        echo "# VADGR" >> "$default_rc"
        echo "$line" >> "$default_rc"
        info "Created $(basename "$default_rc") with forge PATH"
    fi

    export PATH="$FORGE_BIN:$PATH"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    OS=$(detect_os)
    echo ""
    # Detect dark/light terminal background
    LIGHT_MODE=0
    if [ -n "${COLORFGBG:-}" ]; then
        BG_VAL="${COLORFGBG##*;}"
        [ "$BG_VAL" -gt 6 ] 2>/dev/null && LIGHT_MODE=1
    fi
    if [ "$LIGHT_MODE" -eq 0 ]; then
        TC="\033[1;38;2;200;200;200m"
    else
        TC="\033[1;38;2;60;60;60m"
    fi
    R="\033[0m"
    printf "${TC}█  █ █▀▀█ █▀▀▄ █▀▀▀ █▀▀█${R}\n"
    printf "${TC}█  █ █▀▀█ █  █ █ ▀█ █▀▀▄${R}\n"
    printf "${TC}▀▀▀▀ ▀  ▀ ▀▀▀  ▀▀▀▀ ▀  ▀${R}\n"
    echo ""

    info "Detected OS: $OS"

    install_git
    install_python
    install_nvm_and_node
    setup_repo
    setup_api
    setup_forge_scripts
    setup_cli
    setup_frontend
    generate_forge_cli
    add_to_path

    echo ""
    ok "VADGR installed successfully!"
    echo ""
    ok "To get started:"
    ok "  1. Restart your terminal (or run: source ~/.bashrc)"
    ok "  2. Install a CLI provider (e.g. curl -fsSL https://claude.ai/install.sh | bash)"
    ok "  3. Run: vadgr start"
    echo ""
}

main "$@"
