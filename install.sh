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
    # This installer owns the toolchain now, so the shell startup line below is
    # written for a machine that had none of its own.
    VADGR_INSTALLED_TOOLCHAIN=1
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

    local candidate="$VADGR_REPO/target/release/vadgr"
    info "Assembling vadgr's private computer-use runtime..."
    if [ "$OS" = "macos" ]; then
        # macOS asks for Accessibility and Screen Recording through a dialog,
        # and grants a running application the moment you allow them. It still
        # says the application cannot record "until it is quit", because the
        # already-running process keeps its old answer until it restarts. An
        # owner who takes that literally quits the terminal mid-install and
        # kills it, so say plainly what to click and when to restart.
        info "macOS will ask for Accessibility and Screen Recording next."
        info "  Allow both. If it says the terminal cannot record until it is"
        info "  quit, choose Later: quitting now would stop this installation."
        info "  Restart your terminal once the install finishes."
    fi
    "$candidate" __payload-setup --install-root "$VADGR_HOME" \
        || fail "Computer use could not be prepared. The installed binary was not changed."
    if [ "$OS" = "linux" ]; then
        local apply_deps="${VADGR_CUA_APPLY_SYSTEM_DEPS:-}"
        if [ -z "$apply_deps" ] && [ -t 0 ]; then
            printf "Apply the printed Linux computer-use system plan? [y/N] "
            read -r apply_deps
        fi
        case "$apply_deps" in
            1|y|Y|yes|YES)
                "$candidate" __payload-setup --install-root "$VADGR_HOME" --apply-system-deps \
                    || fail "The approved Linux computer-use setup failed. The installed binary was not changed."
                ;;
        esac
    fi

    mkdir -p "$VADGR_BIN"
    # Installed only after the build succeeded, so a failed build leaves the
    # installation that was already working exactly as it was.
    for binary in vadgr; do
        install -m 0755 "$candidate" "$VADGR_BIN/$binary" \
            || fail "Could not install $binary into $VADGR_BIN"
    done
    ok "Installed vadgr into $VADGR_BIN"
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

# The line that makes the toolchain reachable in later shells.
#
# **Only when this installer set the toolchain up.** rustup is invoked with
# `--no-modify-path` so the installer owns this decision, and the `. cargo/env`
# it runs during the install lasts for that process alone. Without this a
# machine installs cleanly and then fails on its first `vadgr update` with
# "Could not run cargo", naming the toolchain the installer had just left
# unreachable. A machine that already had cargo keeps its own arrangement.
cargo_path_line() {
    if [ ! -f "$HOME/.cargo/env" ]; then return 1; fi
    if [ -z "$VADGR_INSTALLED_TOOLCHAIN" ]; then return 1; fi
    printf '%s' '. "$HOME/.cargo/env"'
}

add_to_path() {
    local line="export PATH=\"$VADGR_BIN:\$PATH\""
    local cargo_line
    cargo_line="$(cargo_path_line || true)"
    local found=0

    for rcfile in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ ! -f "$rcfile" ]; then continue; fi
        if ! grep -qF "$VADGR_BIN" "$rcfile" 2>/dev/null; then
            echo "" >> "$rcfile"
            echo "# VADGR" >> "$rcfile"
            echo "$line" >> "$rcfile"
            info "Added vadgr to PATH in $(basename "$rcfile")"
        fi
        if [ -n "$cargo_line" ] && ! grep -qF '.cargo/env' "$rcfile" 2>/dev/null; then
            echo "$cargo_line" >> "$rcfile"
            info "Added the Rust toolchain to PATH in $(basename "$rcfile"), which vadgr update needs"
        fi
        found=1
    done

    if [ "$found" -eq 0 ]; then
        local default_rc="$HOME/.bashrc"
        if [ "$OS" = "macos" ]; then default_rc="$HOME/.zshrc"; fi
        echo "# VADGR" >> "$default_rc"
        echo "$line" >> "$default_rc"
        if [ -n "$cargo_line" ]; then echo "$cargo_line" >> "$default_rc"; fi
        info "Created $(basename "$default_rc") with the vadgr PATH"
        # Named so the closing step can tell the owner to source the file that
        # was actually written. It said `source ~/.bashrc` on a machine where
        # it had just created `.zshrc`, which is the default shell on macOS.
        VADGR_PROFILE="$default_rc"
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
    if [ "$OS" = "macos" ]; then
        # The grants only take effect for a process started after they were
        # given, so on macOS the restart is the step that makes computer use
        # work rather than a convenience for PATH.
        ok "  1. Restart your terminal. On macOS this is what makes the"
        ok "     Accessibility and Screen Recording grants take effect, not"
        ok "     just a PATH refresh."
    else
        if [ -n "${VADGR_PROFILE:-}" ]; then
            ok "  1. Restart your terminal (or run: . $VADGR_PROFILE)"
        else
            ok "  1. Restart your terminal so the vadgr PATH applies"
        fi
    fi
    ok "  2. Run: vadgr provider login"
    ok "  3. Run: vadgr start, then vadgr pair"
    echo ""
}

main "$@"
