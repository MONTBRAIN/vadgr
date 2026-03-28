# Agent Forge Installer for Windows
# Usage: irm https://raw.githubusercontent.com/MONTBRAIN/Agent-Forge/master/setup.ps1 | iex

$ErrorActionPreference = "Stop"

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

function PythonOk {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pyCmd) { return $false }
    if ($pyCmd.Source -like "*WindowsApps*") { return $false }
    try {
        $ver = & python -c "import sys; print(sys.version_info.minor)" 2>$null
        return ($null -ne $ver -and [int]$ver -ge 12)
    } catch { return $false }
}

function InstallPython {
    if (PythonOk) {
        $ver = python -c "import sys; print(sys.version_info.minor)" 2>$null
        Info "Python 3.$ver already installed."
        return
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
        & { $ErrorActionPreference = 'SilentlyContinue'; git -C $FORGE_REPO pull --ff-only origin master 2>$null }
        if ($LASTEXITCODE -ne 0) { Warn "Could not pull latest (offline?)" }
        $deleted = git -C $FORGE_REPO diff --name-only --diff-filter=D 2>$null
        if ($deleted) {
            Push-Location $FORGE_REPO
            $deleted | ForEach-Object { git checkout -- $_ 2>$null }
            Pop-Location
        }
    } else {
        Info "Cloning Agent Forge..."
        New-Item -ItemType Directory -Force -Path $FORGE_HOME | Out-Null
        git clone $REPO_URL $FORGE_REPO
    }
}

function EnsureVenv($dir, $req) {
    Push-Location $FORGE_REPO
    try {
        $venvPip = "$dir\Scripts\pip.exe"
        if (-not (Test-Path $dir) -or -not (Test-Path $venvPip)) {
            if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
            python -m venv $dir
            if (-not (Test-Path $venvPip)) { Fail "Failed to create venv at $dir" }
        }
        & $venvPip install -q -r $req
    } finally { Pop-Location }
}

function SetupApi {
    Info "Setting up API..."
    EnsureVenv "api\.venv" "api\requirements.txt"
    Push-Location $FORGE_REPO
    New-Item -ItemType Directory -Force -Path data | Out-Null
    Pop-Location
}

function SetupForgeScripts {
    Info "Setting up forge scripts..."
    EnsureVenv "forge\scripts\.venv" "forge\scripts\requirements.txt"
}

function SetupCli {
    Info "Setting up CLI..."
    EnsureVenv "cli\.venv" "cli\requirements.txt"
}

function SetupFrontend {
    Info "Setting up frontend..."
    Set-Location "$FORGE_REPO\frontend"
    npm.cmd install --silent
}

# ---------------------------------------------------------------------------
# Generate forge CLI
# ---------------------------------------------------------------------------

function GenerateForgeCli {
    Info "Creating forge CLI..."
    New-Item -ItemType Directory -Force -Path $FORGE_BIN | Out-Null


    $forgeScript = @'
param([Parameter(ValueFromRemainingArguments)]$Rest)
$FORGE_REPO = "$env:USERPROFILE\.forge\Agent-Forge"
$cliPython = "$FORGE_REPO\cli\.venv\Scripts\python.exe"
if (-not (Test-Path $cliPython)) { Write-Host "[forge] CLI not found. Run setup first." -ForegroundColor Red; exit 1 }
$env:PYTHONPATH = $FORGE_REPO
& $cliPython -m cli @Rest
'@

    # Save as _forge.ps1 (underscore prefix) so PowerShell doesn't resolve it
    # directly when user types "forge". The .bat wrapper calls it with -ExecutionPolicy Bypass.
    $forgeScript | Out-File -FilePath "$FORGE_BIN\_forge.ps1" -Encoding UTF8

    # Remove old forge.ps1 if present (from previous installs)
    if (Test-Path "$FORGE_BIN\forge.ps1") { Remove-Item "$FORGE_BIN\forge.ps1" }

    # Batch wrapper — entry point for both cmd.exe and PowerShell
    $batchWrapper = "@echo off`r`npowershell -ExecutionPolicy Bypass -File `"%USERPROFILE%\.forge\bin\_forge.ps1`" %*"
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
    SetupCli
    SetupFrontend
    GenerateForgeCli
    AddToPath

    Write-Host ""
    Ok "Agent Forge installed successfully!"
    Write-Host ""
    Ok "To get started:"
    Ok "  1. Restart your terminal"
    Ok "  2. Install a CLI provider (e.g. irm https://claude.ai/install.ps1 | iex)"
    Ok "  3. Run: forge start"
    Write-Host ""
}

Main
