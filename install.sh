#!/usr/bin/env bash
set -e

# Vadgr Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/MONTBRAIN/vadgr/master/install.sh | bash

# One install root, named after the product. A machine's durable state does not
# live here: the daemon resolves that from the platform's own local-state
# directory, so this holds the binaries and the checkout they are built from.
VADGR_HOME="$HOME/.vadgr"
VADGR_BIN="$VADGR_HOME/bin"
VADGR_REPO="$VADGR_HOME/src"
# The source and the ref, overridable so a release can be installed and driven
# before it is merged. An end to end pass has to install the same script a user
# runs; without these it could only ever test what is already on the default
# branch, which is never the release being proven.
REPO_URL="${VADGR_REPO_URL:-https://github.com/MONTBRAIN/vadgr.git}"
REPO_REF="${VADGR_REF:-master}"

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

# Package installs need root. A desktop user has sudo and no root shell; a
# container is the reverse, and the installer runs on both.
as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command_exists sudo; then
        sudo "$@"
    else
        fail "Installing packages needs root. Run as root or install sudo first."
    fi
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
                as_root apt-get update -qq && as_root apt-get install -y -qq git
            elif command_exists dnf; then
                as_root dnf install -y -q git
            elif command_exists pacman; then
                as_root pacman -S --noconfirm git
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

install_build_tools() {
    # rustup installs the compiler but not the system linker it drives, and a
    # desktop machine rarely has one: without this the build fails minutes in
    # with "linker `cc` not found".
    case "$OS" in
        linux|wsl)
            if command_exists cc; then return; fi
            info "Installing the C toolchain the build links with..."
            if command_exists apt-get; then
                as_root apt-get update -qq && as_root apt-get install -y -qq build-essential
            elif command_exists dnf; then
                as_root dnf install -y -q gcc
            elif command_exists pacman; then
                as_root pacman -S --noconfirm --needed base-devel
            else
                fail "No supported package manager found. Install a C compiler (cc) manually."
            fi
            command_exists cc || fail "Installed a C toolchain but cc is still not on PATH."
            ;;
        macos)
            # A fresh macOS ships /usr/bin/cc and /usr/bin/git as shims that
            # only open an install dialog, so command -v cannot answer this;
            # xcode-select can.
            if xcode-select -p >/dev/null 2>&1; then return; fi
            info "The Xcode Command Line Tools are missing. Asking macOS to install them..."
            xcode-select --install >/dev/null 2>&1 || true
            fail "Finish the Command Line Tools install in the dialog macOS opened, then run this script again."
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Setup Vadgr
# ---------------------------------------------------------------------------

install_rust() {
    if command_exists cargo; then return; fi
    info "Installing the Rust toolchain..."
    # The official installer, non-interactive. The product is one binary and
    # this is what builds it; nothing else here needs a compiler.
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
    command_exists cargo || fail "Rust installed but cargo is not on PATH. Open a new shell and run this again."
}

build_and_install() {
    info "Building vadgr (this takes a few minutes the first time)..."
    if ! command_exists cargo; then
        # shellcheck disable=SC1091
        [ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
    fi
    ( cd "$VADGR_REPO" && cargo build --locked --release --bins ) || fail "The build failed. Nothing was installed."

    mkdir -p "$VADGR_BIN"
    # Installed only after the build succeeded, so a failed build leaves the
    # installation that was already working exactly as it was.
    for binary in vadgr vadgr-daemon; do
        install -m 0755 "$VADGR_REPO/target/release/$binary" "$VADGR_BIN/$binary" \
            || fail "Could not install $binary into $VADGR_BIN"
    done
    ok "Installed vadgr and vadgr-daemon into $VADGR_BIN"
}

setup_repo() {
    if [ -d "$VADGR_REPO/.git" ]; then
        info "Vadgr repo already exists, pulling latest..."
        git -C "$VADGR_REPO" fetch --quiet origin "$REPO_REF" 2>/dev/null || warn "Could not fetch latest (offline?)"
        git -C "$VADGR_REPO" checkout --quiet "$REPO_REF" 2>/dev/null || true
        git -C "$VADGR_REPO" pull --ff-only origin "$REPO_REF" || warn "Could not pull latest (offline?)"
        # Restore tracked files that were deleted locally
        local deleted
        deleted=$(git -C "$VADGR_REPO" diff --name-only --diff-filter=D 2>/dev/null)
        if [ -n "$deleted" ]; then
            (cd "$VADGR_REPO" && echo "$deleted" | while IFS= read -r f; do git checkout -- "$f" 2>/dev/null; done)
        fi
    else
        info "Cloning Vadgr..."
        mkdir -p "$VADGR_HOME"
        git clone "$REPO_URL" "$VADGR_REPO"
        if [ "$REPO_REF" != "master" ]; then
            git -C "$VADGR_REPO" checkout --quiet "$REPO_REF" \
                || fail "The ref $REPO_REF is not in $REPO_URL. Nothing was installed."
        fi
    fi
}

# ---------------------------------------------------------------------------
# Generate vadgr CLI
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Add to PATH
# ---------------------------------------------------------------------------

add_to_path() {
    local line="export PATH=\"$VADGR_BIN:\$PATH\""
    local found=0

    for rcfile in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ ! -f "$rcfile" ]; then continue; fi
        if ! grep -qF "$VADGR_BIN" "$rcfile" 2>/dev/null; then
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
        info "Created $(basename "$default_rc") with the vadgr PATH"
    fi

    export PATH="$VADGR_BIN:$PATH"
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

    install_build_tools
    install_git
    install_rust
    setup_repo
    build_and_install
    add_to_path

    echo ""
    ok "VADGR installed successfully!"
    echo ""
    ok "To get started:"
    ok "  1. Restart your terminal (or run: source ~/.bashrc)"
    ok "  2. Run: vadgr provider login"
    ok "  3. Run: vadgr start, then vadgr pair"
    echo ""
}

main "$@"
