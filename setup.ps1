# Agent Forge Installer for Windows
# Usage: irm https://raw.githubusercontent.com/MONTBRAIN/Agent-Forge/master/setup.ps1 | iex

$ErrorActionPreference = "Stop"

# Allow child .ps1 shims (npm.ps1, npx.ps1, etc.) to run inside this process.
# Without this, `irm ... | iex` works but spawning npm fails under Restricted policy.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

$FORGE_HOME = "$env:USERPROFILE\.forge"
$FORGE_BIN = "$FORGE_HOME\bin"
$FORGE_REPO = "$FORGE_HOME\Agent-Forge"
$REPO_URL = "https://github.com/MONTBRAIN/Agent-Forge.git"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Info($msg)  { Write-Host "[forge] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[forge] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[forge] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[forge] $msg" -ForegroundColor Red; exit 1 }

function CommandExists($cmd) {
    $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue)
}

function EnsureWinget {
    if (CommandExists "winget") { return }
    Fail "winget is not available. Please install App Installer from the Microsoft Store, then re-run this script."
}

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------

function InstallGit {
    if (CommandExists "git") { return }
    Info "Installing git..."
    EnsureWinget
    winget install --id Git.Git --accept-source-agreements --accept-package-agreements --silent
    $env:PATH = "$env:ProgramFiles\Git\cmd;$env:PATH"
    if (-not (CommandExists "git")) { Fail "Git installation failed." }
}

function InstallPython {
    if (CommandExists "python") {
        $ver = python -c "import sys; print(sys.version_info.minor)" 2>$null
        if ($ver -ge 12) {
            Info "Python 3.$ver already installed."
            return
        }
    }
    Info "Installing Python 3.12..."
    EnsureWinget
    winget install --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
    # Refresh PATH to find new Python
    $pyPath = "$env:LOCALAPPDATA\Programs\Python\Python312"
    $env:PATH = "$pyPath;$pyPath\Scripts;$env:PATH"
    if (-not (CommandExists "python")) { Fail "Python installation failed." }
}

function InstallNode {
    if (CommandExists "node") {
        Info "Node.js already installed: $(node --version)"
        return
    }
    Info "Installing Node.js LTS..."
    EnsureWinget
    winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
    # Refresh PATH
    $env:PATH = "$env:ProgramFiles\nodejs;$env:PATH"
    if (-not (CommandExists "node")) { Fail "Node.js installation failed." }
}

# ---------------------------------------------------------------------------
# Setup Agent Forge
# ---------------------------------------------------------------------------

function SetupRepo {
    if (Test-Path "$FORGE_REPO\.git") {
        Info "Agent Forge repo already exists, pulling latest..."
        $pullOut = & git -C $FORGE_REPO pull --ff-only origin master 2>&1
        if ($LASTEXITCODE -ne 0) { Warn "Could not pull latest (offline?)" }
    } else {
        Info "Cloning Agent Forge..."
        New-Item -ItemType Directory -Force -Path $FORGE_HOME | Out-Null
        git clone $REPO_URL $FORGE_REPO
    }
}

function SetupApi {
    Info "Setting up API..."
    Set-Location $FORGE_REPO
    if (-not (Test-Path "api\.venv")) {
        python -m venv api\.venv
    }
    & api\.venv\Scripts\pip.exe install -q -r api\requirements.txt
    New-Item -ItemType Directory -Force -Path data | Out-Null
}

function SetupForgeScripts {
    Info "Setting up forge scripts..."
    Set-Location $FORGE_REPO
    if (-not (Test-Path "forge\scripts\.venv")) {
        python -m venv forge\scripts\.venv
    }
    & forge\scripts\.venv\Scripts\pip.exe install -q -r forge\scripts\requirements.txt
}

function SetupFrontend {
    Info "Setting up frontend..."
    Set-Location "$FORGE_REPO\frontend"
    npm install --silent
}

# ---------------------------------------------------------------------------
# Generate forge CLI
# ---------------------------------------------------------------------------

function GenerateForgeCli {
    Info "Creating forge CLI..."
    New-Item -ItemType Directory -Force -Path $FORGE_BIN | Out-Null

    $forgeScript = @'
# Agent Forge CLI for Windows
param(
    [string]$Command = "help",
    [string]$ApiPort = "",
    [string]$FrontendPort = ""
)

$FORGE_HOME = "$env:USERPROFILE\.forge"
$FORGE_REPO = "$FORGE_HOME\Agent-Forge"
$PID_DIR = "$FORGE_HOME\pids"

# Ports -- flags > env vars > defaults
$API_PORT = if ($ApiPort) { $ApiPort } elseif ($env:AGENT_FORGE_PORT) { $env:AGENT_FORGE_PORT } else { "8000" }
$FRONTEND_PORT = if ($FrontendPort) { $FrontendPort } elseif ($env:AGENT_FORGE_FRONTEND_PORT) { $env:AGENT_FORGE_FRONTEND_PORT } else { "3000" }

function Info($msg)  { Write-Host "[forge] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[forge] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[forge] $msg" -ForegroundColor Yellow }

# Parse actual frontend port from Vite log output
function DetectFrontendPort {
    $log = "$FORGE_HOME\frontend.log"
    for ($i = 0; $i -lt 20; $i++) {
        if (Test-Path $log) {
            $match = Select-String -Path $log -Pattern 'localhost:(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($match) {
                return $match.Matches[0].Groups[1].Value
            }
        }
        Start-Sleep -Milliseconds 250
    }
    return $FRONTEND_PORT
}

function Start-Forge {
    New-Item -ItemType Directory -Force -Path $PID_DIR | Out-Null

    # Check if already running
    $apiPidFile = "$PID_DIR\api.pid"
    if (Test-Path $apiPidFile) {
        $procId = Get-Content $apiPidFile
        if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
            Warn "Agent Forge is already running. Use 'forge stop' first."
            return
        }
    }

    Set-Location $FORGE_REPO

    # Start API
    Info "Starting API server (port $API_PORT)..."
    $env:PYTHONPATH = $FORGE_REPO
    $env:AGENT_FORGE_PORT = $API_PORT
    $env:AGENT_FORGE_FRONTEND_PORT = $FRONTEND_PORT
    $apiProc = Start-Process -FilePath "api\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", $API_PORT `
        -WorkingDirectory $FORGE_REPO `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput "$FORGE_HOME\api.log" `
        -RedirectStandardError "$FORGE_HOME\api.err"
    $apiProc.Id | Out-File $apiPidFile

    # Wait for API
    for ($i = 0; $i -lt 15; $i++) {
        try {
            $null = Invoke-RestMethod "http://127.0.0.1:${API_PORT}/api/health" -TimeoutSec 2
            break
        } catch { Start-Sleep 1 }
    }

    # Start frontend (pass ports so Vite reads them)
    Info "Starting frontend..."
    $env:AGENT_FORGE_PORT = $API_PORT
    $env:AGENT_FORGE_FRONTEND_PORT = $FRONTEND_PORT
    $frontProc = Start-Process -FilePath "npm" `
        -ArgumentList "run", "dev" `
        -WorkingDirectory "$FORGE_REPO\frontend" `
        -WindowStyle Hidden `
        -PassThru
    $frontProc.Id | Out-File "$PID_DIR\frontend.pid"

    # Detect actual port from Vite output (handles auto-increment)
    $actualFePort = DetectFrontendPort

    Ok "Agent Forge is running!"
    Ok "  Frontend: http://localhost:$actualFePort"
    Ok "  API:      http://localhost:$API_PORT"
    Ok ""
    Ok "Run 'forge stop' to stop, 'forge logs' to see API logs."
}

function Stop-Forge {
    $stopped = $false
    foreach ($service in @("api", "frontend")) {
        $pidFile = "$PID_DIR\$service.pid"
        if (Test-Path $pidFile) {
            $procId = Get-Content $pidFile
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                Stop-Process -Id $procId -Force
                Info "Stopped $service (PID $procId)"
                $stopped = $true
            }
            Remove-Item $pidFile
        }
    }
    if (-not $stopped) { Warn "Agent Forge is not running." }
    else { Ok "Agent Forge stopped." }
}

function Get-ForgeStatus {
    foreach ($service in @("api", "frontend")) {
        $pidFile = "$PID_DIR\$service.pid"
        if ((Test-Path $pidFile) -and (Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue)) {
            Ok "$service is running (PID $(Get-Content $pidFile))"
        } else {
            Warn "$service is not running"
        }
    }
}

function Update-Forge {
    Info "Updating Agent Forge..."
    Set-Location $FORGE_REPO

    $apiHash = (Get-FileHash api\requirements.txt -ErrorAction SilentlyContinue).Hash
    $frontHash = (Get-FileHash frontend\package.json -ErrorAction SilentlyContinue).Hash

    git pull --ff-only origin master
    if ($LASTEXITCODE -ne 0) { Warn "Could not pull (check your network)"; return }

    $newApiHash = (Get-FileHash api\requirements.txt -ErrorAction SilentlyContinue).Hash
    $newFrontHash = (Get-FileHash frontend\package.json -ErrorAction SilentlyContinue).Hash

    if ($apiHash -ne $newApiHash) {
        Info "API dependencies changed, reinstalling..."
        & api\.venv\Scripts\pip.exe install -q -r api\requirements.txt
    }
    if ($frontHash -ne $newFrontHash) {
        Info "Frontend dependencies changed, reinstalling..."
        Set-Location frontend; npm install --silent; Set-Location ..
    }

    Ok "Update complete. Run 'forge start' to start."
}

function Restart-Forge {
    Stop-Forge
    Start-Sleep 1
    Start-Forge
}

function Start-ForgeApi {
    New-Item -ItemType Directory -Force -Path $PID_DIR | Out-Null
    $apiPidFile = "$PID_DIR\api.pid"
    if (Test-Path $apiPidFile) {
        $procId = Get-Content $apiPidFile
        if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
            Warn "API is already running. Use 'forge stop' first."
            return
        }
    }
    Set-Location $FORGE_REPO
    Info "Starting API server (port $API_PORT)..."
    $env:PYTHONPATH = $FORGE_REPO
    $env:AGENT_FORGE_PORT = $API_PORT
    $env:AGENT_FORGE_FRONTEND_PORT = $FRONTEND_PORT
    $apiProc = Start-Process -FilePath "api\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", $API_PORT `
        -WorkingDirectory $FORGE_REPO `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput "$FORGE_HOME\api.log" `
        -RedirectStandardError "$FORGE_HOME\api.err"
    $apiProc.Id | Out-File $apiPidFile
    for ($i = 0; $i -lt 15; $i++) {
        try {
            $null = Invoke-RestMethod "http://127.0.0.1:${API_PORT}/api/health" -TimeoutSec 2
            break
        } catch { Start-Sleep 1 }
    }
    Ok "API is running at http://localhost:$API_PORT"
}

function Get-ForgeHealth {
    try {
        $response = Invoke-RestMethod "http://127.0.0.1:${API_PORT}/api/health" -TimeoutSec 5
        $response | ConvertTo-Json -Depth 5
    } catch {
        Warn "API is not responding. Run 'forge start' first."
    }
}

function Get-ForgeAgents {
    try {
        $agents = Invoke-RestMethod "http://127.0.0.1:${API_PORT}/api/agents" -TimeoutSec 5
        if ($agents.Count -eq 0) {
            Write-Host "No agents found."
        } else {
            Write-Host "$($agents.Count) agent(s):"
            Write-Host ""
            foreach ($a in $agents) {
                $steps = if ($a.steps) { $a.steps.Count } else { 0 }
                $cu = if ($a.computer_use) { " [desktop]" } else { "" }
                Write-Host "  $($a.name)"
                Write-Host "    ID: $($a.id)  Status: $($a.status)  Steps: $steps$cu"
                Write-Host ""
            }
        }
    } catch {
        Warn "API is not responding. Run 'forge start' first."
    }
}

function Get-ForgeProviders {
    try {
        $providers = Invoke-RestMethod "http://127.0.0.1:${API_PORT}/api/providers" -TimeoutSec 5
        foreach ($p in $providers) {
            $avail = if ($p.available) { "available" } else { "not found" }
            Write-Host "  $($p.name) ($($p.id)) -- $avail"
            foreach ($m in $p.models) {
                Write-Host "    - $($m.name) ($($m.id))"
            }
            Write-Host ""
        }
    } catch {
        Warn "API is not responding. Run 'forge start' first."
    }
}

function Get-ForgeInfo {
    Write-Host "Agent Forge"
    Write-Host ""
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:${API_PORT}/api/health" -TimeoutSec 5
        Write-Host "  Version:       $($health.version)"
        Write-Host "  Platform:      $($health.platform)"
        $forgeAvail = if ($health.modules.forge) { "available" } else { "not found" }
        $cuAvail = if ($health.modules.computer_use) { "available" } else { "not found" }
        Write-Host "  Forge:         $forgeAvail"
        Write-Host "  Computer Use:  $cuAvail"
        Ok "  API:           running"
    } catch {
        Warn "  API:           not running"
    }
    $apiPidFile = "$PID_DIR\frontend.pid"
    if ((Test-Path $apiPidFile) -and (Get-Process -Id (Get-Content $apiPidFile) -ErrorAction SilentlyContinue)) {
        Ok "  Frontend:      running"
    } else {
        Warn "  Frontend:      not running"
    }
    Write-Host "  Install:       $FORGE_REPO"
    Write-Host ""
}

function Get-ForgeLogs {
    if (Test-Path "$FORGE_HOME\api.log") {
        Get-Content "$FORGE_HOME\api.log" -Wait -Tail 50
    } else {
        Warn "No logs found. Is Agent Forge running?"
    }
}

function Show-Help {
    Write-Host "Agent Forge CLI"
    Write-Host ""
    Write-Host "Usage: forge <command> [-ApiPort <port>] [-FrontendPort <port>]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  start      Start API and frontend servers"
    Write-Host "  stop       Stop all services"
    Write-Host "  restart    Restart all services"
    Write-Host "  api        Start only the API server"
    Write-Host "  status     Show if services are running"
    Write-Host "  health     Check API health"
    Write-Host "  agents     List all agents"
    Write-Host "  providers  List available providers and models"
    Write-Host "  info       Show system information"
    Write-Host "  update     Pull latest code and reinstall deps if changed"
    Write-Host "  logs       Tail API server logs"
    Write-Host "  help       Show this help message"
    Write-Host ""
    Write-Host "Flags:"
    Write-Host "  -ApiPort <port>       API server port (default: 8000)"
    Write-Host "  -FrontendPort <port>  Frontend server port (default: 3000)"
    Write-Host ""
    Write-Host "Environment variables:"
    Write-Host "  AGENT_FORGE_PORT            Same as -ApiPort"
    Write-Host "  AGENT_FORGE_FRONTEND_PORT   Same as -FrontendPort"
}

switch ($Command) {
    "start"     { Start-Forge }
    "stop"      { Stop-Forge }
    "restart"   { Restart-Forge }
    "api"       { Start-ForgeApi }
    "status"    { Get-ForgeStatus }
    "health"    { Get-ForgeHealth }
    "agents"    { Get-ForgeAgents }
    "providers" { Get-ForgeProviders }
    "info"      { Get-ForgeInfo }
    "update"    { Update-Forge }
    "logs"      { Get-ForgeLogs }
    "help"      { Show-Help }
    default     { Warn "Unknown command: $Command"; Show-Help }
}
'@

    $forgeScript | Out-File -FilePath "$FORGE_BIN\forge.ps1" -Encoding UTF8

    # Create a batch wrapper so 'forge' works from cmd.exe too
    $batchWrapper = "@echo off`r`npowershell -ExecutionPolicy Bypass -File `"%USERPROFILE%\.forge\bin\forge.ps1`" %*"
    $batchWrapper | Out-File -FilePath "$FORGE_BIN\forge.bat" -Encoding ASCII
}

# ---------------------------------------------------------------------------
# Add to PATH
# ---------------------------------------------------------------------------

function AddToPath {
    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($currentPath -notlike "*$FORGE_BIN*") {
        [Environment]::SetEnvironmentVariable("PATH", "$FORGE_BIN;$currentPath", "User")
        $env:PATH = "$FORGE_BIN;$env:PATH"
        Info "Added forge to user PATH"
    }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Main {
    Write-Host ""
    Write-Host "  ___                _     ___"
    Write-Host " / _ | ___ ____ ___ | |_  / __/__  _______ ____"
    Write-Host "/ __ |/ _ ``/ -_) _ \| __// _// _ \/ __/ _ ``/ -_)"
    Write-Host "\/_/ |\_,_/\__, /\___|_\__\/ /_//_/\_ /\_, /\__/"
    Write-Host "         /___/                       /___/"
    Write-Host ""

    InstallGit
    InstallPython
    InstallNode
    SetupRepo
    SetupApi
    SetupForgeScripts
    SetupFrontend
    GenerateForgeCli
    AddToPath

    Write-Host ""
    Ok "Agent Forge installed successfully!"
    Write-Host ""
    Ok "To get started:"
    Ok "  1. Restart your terminal"
    Ok "  2. Install a CLI provider (e.g. npm install -g @anthropic-ai/claude-code)"
    Ok "  3. Run: forge start"
    Write-Host ""
}

Main
