#!/usr/bin/env bash
set -e

# Agent Forge Installer
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

info()  { printf "\033[1;34m[forge]\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m[forge]\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m[forge]\033[0m %s\n" "$*"; }
fail()  { printf "\033[1;31m[forge]\033[0m %s\n" "$*" >&2; exit 1; }

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
            sudo apt-get update -qq && sudo apt-get install -y -qq git
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
            sudo apt-get update -qq
            sudo apt-get install -y -qq software-properties-common
            sudo add-apt-repository -y ppa:deadsnakes/ppa
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
            # Make python3.12 the default python3 if current one is too old
            if ! python_ok; then
                sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
            fi
            ;;
        macos)
            install_homebrew
            brew install python@3.12
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
        curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" | bash
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
# Setup Agent Forge
# ---------------------------------------------------------------------------

setup_repo() {
    if [ -d "$FORGE_REPO/.git" ]; then
        info "Agent Forge repo already exists, pulling latest..."
        git -C "$FORGE_REPO" pull --ff-only origin master || warn "Could not pull latest (offline?)"
    else
        info "Cloning Agent Forge..."
        mkdir -p "$FORGE_HOME"
        git clone "$REPO_URL" "$FORGE_REPO"
    fi
}

setup_api() {
    info "Setting up API..."
    cd "$FORGE_REPO"
    if [ ! -d "api/.venv" ]; then
        python3 -m venv api/.venv
    fi
    api/.venv/bin/pip install -q -r api/requirements.txt
    mkdir -p data
}

setup_forge_scripts() {
    info "Setting up forge scripts..."
    cd "$FORGE_REPO"
    if [ ! -d "forge/scripts/.venv" ]; then
        python3 -m venv forge/scripts/.venv
    fi
    forge/scripts/.venv/bin/pip install -q -r forge/scripts/requirements.txt
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
    info "Creating forge CLI..."
    mkdir -p "$FORGE_BIN"
    cat > "$FORGE_BIN/forge" << 'FORGE_SCRIPT'
#!/usr/bin/env bash
set -e

FORGE_HOME="$HOME/.forge"
FORGE_REPO="$FORGE_HOME/Agent-Forge"
PID_DIR="$FORGE_HOME/pids"

# Ports -- flags > env vars > defaults
API_PORT="${AGENT_FORGE_PORT:-8000}"
FRONTEND_PORT="${AGENT_FORGE_FRONTEND_PORT:-3000}"

info()  { printf "\033[1;34m[forge]\033[0m %s\n" "$*"; }
ok()    { printf "\033[1;32m[forge]\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m[forge]\033[0m %s\n" "$*"; }
fail()  { printf "\033[1;31m[forge]\033[0m %s\n" "$*" >&2; exit 1; }

# Parse flags from arguments (mutates API_PORT / FRONTEND_PORT)
parse_flags() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --api-port)      API_PORT="$2"; shift 2 ;;
            --frontend-port) FRONTEND_PORT="$2"; shift 2 ;;
            *)               shift ;;
        esac
    done
}

# Parse actual frontend port from Vite log output
detect_frontend_port() {
    local log="$FORGE_HOME/frontend.log"
    local actual_port=""
    for i in $(seq 1 20); do
        actual_port=$(grep -oP 'localhost:\K[0-9]+' "$log" 2>/dev/null | head -1)
        if [ -n "$actual_port" ]; then
            echo "$actual_port"
            return
        fi
        sleep 0.25
    done
    echo "$FRONTEND_PORT"
}

cmd_start() {
    mkdir -p "$PID_DIR"

    # Check if already running
    if [ -f "$PID_DIR/api.pid" ] && kill -0 "$(cat "$PID_DIR/api.pid")" 2>/dev/null; then
        warn "Agent Forge is already running. Use 'forge stop' first."
        return 1
    fi

    cd "$FORGE_REPO"

    # Load NVM if available
    if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
        . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
    fi

    # Start API
    info "Starting API server (port $API_PORT)..."
    PYTHONPATH=. AGENT_FORGE_PORT="$API_PORT" AGENT_FORGE_FRONTEND_PORT="$FRONTEND_PORT" \
        "$FORGE_REPO/api/.venv/bin/python" -m uvicorn api.main:app \
        --host 127.0.0.1 --port "$API_PORT" > "$FORGE_HOME/api.log" 2>&1 &
    echo $! > "$PID_DIR/api.pid"

    # Wait for API to be ready
    local api_ready=0
    for i in $(seq 1 15); do
        if curl -s "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then
            api_ready=1
            break
        fi
        sleep 1
    done
    if [ "$api_ready" -eq 0 ]; then
        warn "API failed to start. Check $FORGE_HOME/api.log for details."
        return 1
    fi

    # Start frontend (pass ports so Vite reads them)
    info "Starting frontend..."
    cd "$FORGE_REPO/frontend"
    AGENT_FORGE_PORT="$API_PORT" AGENT_FORGE_FRONTEND_PORT="$FRONTEND_PORT" \
        npm run dev > "$FORGE_HOME/frontend.log" 2>&1 &
    local front_pid=$!
    echo $front_pid > "$PID_DIR/frontend.pid"

    # Give it a moment to fail fast (e.g. missing node_modules)
    sleep 1
    if ! kill -0 "$front_pid" 2>/dev/null; then
        warn "Failed to start frontend. Check $FORGE_HOME/frontend.log"
        ok "API is running at http://localhost:$API_PORT (frontend failed)"
        return
    fi

    # Detect actual port from Vite output (handles auto-increment)
    local actual_fe_port
    actual_fe_port=$(detect_frontend_port)

    ok "Agent Forge is running!"
    ok "  Frontend: http://localhost:$actual_fe_port"
    ok "  API:      http://localhost:$API_PORT"
    ok ""
    ok "Run 'forge stop' to stop, 'forge logs' to see API logs."
}

cmd_stop() {
    local stopped=0
    for service in api frontend; do
        local pidfile="$PID_DIR/$service.pid"
        if [ -f "$pidfile" ]; then
            local pid
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null
                info "Stopped $service (PID $pid)"
                stopped=1
            fi
            rm -f "$pidfile"
        fi
    done
    if [ "$stopped" -eq 0 ]; then
        warn "Agent Forge is not running."
    else
        ok "Agent Forge stopped."
    fi
}

cmd_status() {
    local running=0
    for service in api frontend; do
        local pidfile="$PID_DIR/$service.pid"
        if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
            ok "$service is running (PID $(cat "$pidfile"))"
            running=1
        else
            warn "$service is not running"
        fi
    done
    return $(( 1 - running ))
}

cmd_update() {
    info "Updating Agent Forge..."
    cd "$FORGE_REPO"

    # Track file hashes before pull
    local api_hash frontend_hash
    api_hash=$(md5sum api/requirements.txt 2>/dev/null | cut -d' ' -f1)
    frontend_hash=$(md5sum frontend/package.json 2>/dev/null | cut -d' ' -f1)

    git pull --ff-only origin master || { warn "Could not pull (check your network)"; return 1; }

    # Reinstall deps if changed
    local new_api_hash new_frontend_hash
    new_api_hash=$(md5sum api/requirements.txt 2>/dev/null | cut -d' ' -f1)
    new_frontend_hash=$(md5sum frontend/package.json 2>/dev/null | cut -d' ' -f1)

    if [ "$api_hash" != "$new_api_hash" ]; then
        info "API dependencies changed, reinstalling..."
        api/.venv/bin/pip install -q -r api/requirements.txt
    fi

    if [ "$frontend_hash" != "$new_frontend_hash" ]; then
        info "Frontend dependencies changed, reinstalling..."
        if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
            . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
        fi
        cd frontend && npm install --silent && cd ..
    fi

    # Restart if running
    if [ -f "$PID_DIR/api.pid" ] && kill -0 "$(cat "$PID_DIR/api.pid")" 2>/dev/null; then
        info "Restarting services..."
        cmd_stop
        cmd_start
    else
        ok "Update complete. Run 'forge start' to start."
    fi
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_api() {
    mkdir -p "$PID_DIR"

    if [ -f "$PID_DIR/api.pid" ] && kill -0 "$(cat "$PID_DIR/api.pid")" 2>/dev/null; then
        warn "API is already running. Use 'forge stop' first."
        return 1
    fi

    cd "$FORGE_REPO"

    info "Starting API server (port $API_PORT)..."
    PYTHONPATH=. AGENT_FORGE_PORT="$API_PORT" AGENT_FORGE_FRONTEND_PORT="$FRONTEND_PORT" \
        "$FORGE_REPO/api/.venv/bin/python" -m uvicorn api.main:app \
        --host 127.0.0.1 --port "$API_PORT" > "$FORGE_HOME/api.log" 2>&1 &
    echo $! > "$PID_DIR/api.pid"

    local api_ready=0
    for i in $(seq 1 15); do
        if curl -s "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then
            api_ready=1
            break
        fi
        sleep 1
    done

    if [ "$api_ready" -eq 1 ]; then
        ok "API is running at http://localhost:$API_PORT"
    else
        warn "API failed to start. Check $FORGE_HOME/api.log for details."
    fi
}

cmd_health() {
    local response
    response=$(curl -s "http://127.0.0.1:$API_PORT/api/health" 2>/dev/null) || {
        fail "API is not responding. Run 'forge start' first."
    }
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
}

cmd_agents() {
    local response
    response=$(curl -s "http://127.0.0.1:$API_PORT/api/agents" 2>/dev/null) || {
        fail "API is not responding. Run 'forge start' first."
    }
    echo "$response" | python3 -c "
import sys, json
agents = json.load(sys.stdin)
if not agents:
    print('No agents found.')
else:
    print(f'{len(agents)} agent(s):')
    print()
    for a in agents:
        status = a['status']
        steps = len(a.get('steps', []))
        cu = ' [desktop]' if a.get('computer_use') else ''
        print(f'  {a[\"name\"]}')
        print(f'    ID: {a[\"id\"]}  Status: {status}  Steps: {steps}{cu}')
        print()
" 2>/dev/null || echo "$response"
}

cmd_providers() {
    local response
    response=$(curl -s "http://127.0.0.1:$API_PORT/api/providers" 2>/dev/null) || {
        fail "API is not responding. Run 'forge start' first."
    }
    echo "$response" | python3 -c "
import sys, json
providers = json.load(sys.stdin)
if not providers:
    print('No providers configured.')
else:
    for p in providers:
        available = 'available' if p.get('available') else 'not found'
        print(f'  {p[\"name\"]} ({p[\"id\"]}) -- {available}')
        for m in p.get('models', []):
            print(f'    - {m[\"name\"]} ({m[\"id\"]})')
        print()
" 2>/dev/null || echo "$response"
}

cmd_info() {
    echo "Agent Forge"
    echo ""

    # Version
    local health
    health=$(curl -s "http://127.0.0.1:$API_PORT/api/health" 2>/dev/null)
    if [ -n "$health" ]; then
        echo "$health" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  Version:       {d.get(\"version\", \"unknown\")}')
print(f'  Platform:      {d.get(\"platform\", \"unknown\")}')
print(f'  Forge:         {\"available\" if d.get(\"modules\", {}).get(\"forge\") else \"not found\"}')
print(f'  Computer Use:  {\"available\" if d.get(\"modules\", {}).get(\"computer_use\") else \"not found\"}')
" 2>/dev/null
        ok "  API:           running"
    else
        warn "  API:           not running"
    fi

    # Check frontend
    if [ -f "$PID_DIR/frontend.pid" ] && kill -0 "$(cat "$PID_DIR/frontend.pid")" 2>/dev/null; then
        ok "  Frontend:      running"
    else
        warn "  Frontend:      not running"
    fi

    echo "  Install:       $FORGE_REPO"
    echo ""
}

cmd_logs() {
    if [ -f "$FORGE_HOME/api.log" ]; then
        tail -f "$FORGE_HOME/api.log"
    else
        warn "No logs found. Is Agent Forge running?"
    fi
}

cmd_help() {
    echo "Agent Forge CLI"
    echo ""
    echo "Usage: forge <command> [flags]"
    echo ""
    echo "Commands:"
    echo "  start      Start API and frontend servers"
    echo "  stop       Stop all services"
    echo "  restart    Restart all services"
    echo "  api        Start only the API server"
    echo "  status     Show if services are running"
    echo "  health     Check API health"
    echo "  agents     List all agents"
    echo "  providers  List available providers and models"
    echo "  info       Show system information"
    echo "  update     Pull latest code and reinstall deps if changed"
    echo "  logs       Tail API server logs"
    echo "  help       Show this help message"
    echo ""
    echo "Flags:"
    echo "  --api-port <port>       API server port (default: 8000)"
    echo "  --frontend-port <port>  Frontend server port (default: 3000)"
    echo ""
    echo "Environment variables:"
    echo "  AGENT_FORGE_PORT            Same as --api-port"
    echo "  AGENT_FORGE_FRONTEND_PORT   Same as --frontend-port"
}

CMD="${1:-help}"
shift 2>/dev/null || true
parse_flags "$@"

case "$CMD" in
    start)     cmd_start ;;
    stop)      cmd_stop ;;
    restart)   cmd_restart ;;
    api)       cmd_api ;;
    status)    cmd_status ;;
    health)    cmd_health ;;
    agents)    cmd_agents ;;
    providers) cmd_providers ;;
    info)      cmd_info ;;
    update)    cmd_update ;;
    logs)      cmd_logs ;;
    help)      cmd_help ;;
    *)         warn "Unknown command: $CMD"; cmd_help; exit 1 ;;
esac
FORGE_SCRIPT
    chmod +x "$FORGE_BIN/forge"
}

# ---------------------------------------------------------------------------
# Add to PATH
# ---------------------------------------------------------------------------

add_to_path() {
    local line="export PATH=\"$FORGE_BIN:\$PATH\""

    for rcfile in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ -f "$rcfile" ] || [ "$(basename "$rcfile")" = ".bashrc" ]; then
            if ! grep -qF "$FORGE_BIN" "$rcfile" 2>/dev/null; then
                echo "" >> "$rcfile"
                echo "# Agent Forge" >> "$rcfile"
                echo "$line" >> "$rcfile"
                info "Added forge to PATH in $(basename "$rcfile")"
            fi
        fi
    done

    # Add to current session
    export PATH="$FORGE_BIN:$PATH"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo ""
    echo "  ___                _     ___"
    echo " / _ | ___ ____ ___ | |_  / __/__  _______ ____"
    echo "/ __ |/ _ \`/ -_) _ \| __// _// _ \/ __/ _ \`/ -_)"
    echo "\/_/ |\_,_/\__, /\___|_\__\/ /_//_/\_ /\_, /\__/"
    echo "         /___/                       /___/"
    echo ""

    OS=$(detect_os)
    info "Detected OS: $OS"

    install_git
    install_python
    install_nvm_and_node
    setup_repo
    setup_api
    setup_forge_scripts
    setup_frontend
    generate_forge_cli
    add_to_path

    echo ""
    ok "Agent Forge installed successfully!"
    echo ""
    ok "To get started:"
    ok "  1. Restart your terminal (or run: source ~/.bashrc)"
    ok "  2. Install a CLI provider (e.g. curl -fsSL https://claude.ai/install.sh | bash)"
    ok "  3. Run: forge start"
    echo ""
}

main "$@"
