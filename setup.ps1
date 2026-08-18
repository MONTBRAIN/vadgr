# Vadgr Installer for Windows
# Usage: irm https://raw.githubusercontent.com/MONTBRAIN/vadgr/master/setup.ps1 | iex

$ErrorActionPreference = "Stop"

# The directory names are the ones a real installation already has, and
# renaming one moves a user's database. That belongs to the release that
# owns the paths, not to this one.
$VADGR_HOME = "$env:USERPROFILE\.forge"
$VADGR_BIN = "$VADGR_HOME\bin"
$VADGR_REPO = "$VADGR_HOME\Agent-Forge"
$REPO_URL = "https://github.com/MONTBRAIN/vadgr.git"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Info($msg)  { Write-Host "[vadgr] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "[vadgr] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[vadgr] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[vadgr] $msg" -ForegroundColor Red; exit 1 }

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

# ---------------------------------------------------------------------------
# Setup Vadgr
# ---------------------------------------------------------------------------

function SetupRepo {
    if (Test-Path "$VADGR_REPO\.git") {
        Info "Vadgr repo already exists, pulling latest..."
        & { $ErrorActionPreference = 'SilentlyContinue'; git -C $VADGR_REPO pull --ff-only origin master 2>$null }
        if ($LASTEXITCODE -ne 0) { Warn "Could not pull latest (offline?)" }
        $deleted = git -C $VADGR_REPO diff --name-only --diff-filter=D 2>$null
        if ($deleted) {
            Push-Location $VADGR_REPO
            $deleted | ForEach-Object { git checkout -- $_ 2>$null }
            Pop-Location
        }
    } else {
        Info "Cloning Vadgr..."
        New-Item -ItemType Directory -Force -Path $VADGR_HOME | Out-Null
        git clone $REPO_URL $VADGR_REPO
    }
}

function EnsureVenv($dir, $req) {
    Push-Location $VADGR_REPO
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
    Push-Location $VADGR_REPO
    New-Item -ItemType Directory -Force -Path data | Out-Null
    Pop-Location
}

function SetupCli {
    Info "Setting up CLI..."
    EnsureVenv "cli\.venv" "cli\requirements.txt"
}

# ---------------------------------------------------------------------------
# Generate vadgr CLI
# ---------------------------------------------------------------------------

function GenerateVadgrCli {
    Info "Creating vadgr CLI..."
    New-Item -ItemType Directory -Force -Path $VADGR_BIN | Out-Null


    $vadgrScript = @'
param([Parameter(ValueFromRemainingArguments)]$Rest)
$VADGR_REPO = "$env:USERPROFILE\.forge\Agent-Forge"
$cliPython = "$VADGR_REPO\cli\.venv\Scripts\python.exe"
if (-not (Test-Path $cliPython)) { Write-Host "[vadgr] CLI not found. Run setup first." -ForegroundColor Red; exit 1 }
$env:PYTHONPATH = $VADGR_REPO
& $cliPython -m cli @Rest
'@

    # Save as _vadgr.ps1 (underscore prefix) so PowerShell does not resolve it
    # directly when the user types "vadgr". The .bat wrapper calls it with
    # -ExecutionPolicy Bypass.
    $vadgrScript | Out-File -FilePath "$VADGR_BIN\_vadgr.ps1" -Encoding UTF8

    # Remove an old vadgr.ps1 if a previous install left one
    if (Test-Path "$VADGR_BIN\vadgr.ps1") { Remove-Item "$VADGR_BIN\vadgr.ps1" }

    # Batch wrapper — entry point for both cmd.exe and PowerShell
    $batchWrapper = "@echo off`r`npowershell -ExecutionPolicy Bypass -File `"%USERPROFILE%\.forge\bin\_vadgr.ps1`" %*"
    $batchWrapper | Out-File -FilePath "$VADGR_BIN\vadgr.bat" -Encoding ASCII
}

# ---------------------------------------------------------------------------
# Add to PATH
# ---------------------------------------------------------------------------

function AddToPath {
    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($currentPath -notlike "*$VADGR_BIN*") {
        [Environment]::SetEnvironmentVariable("PATH", "$VADGR_BIN;$currentPath", "User")
        $env:PATH = "$VADGR_BIN;$env:PATH"
        Info "Added vadgr to user PATH"
    }
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Main {
    Write-Host ""
    # Detect dark/light terminal background
    $LightMode = $false
    $bgColor = [Console]::BackgroundColor
    if ($bgColor -eq "White" -or $bgColor -eq "Gray" -or $bgColor -eq "Yellow") {
        $LightMode = $true
    }
    $R = "`e[0m"
    if (-not $LightMode) {
        $TC = "`e[1;38;2;200;200;200m"
    } else {
        $TC = "`e[1;38;2;60;60;60m"
    }
    Write-Host "${TC}█  █ █▀▀█ █▀▀▄ █▀▀▀ █▀▀█${R}"
    Write-Host "${TC}█  █ █▀▀█ █  █ █ ▀█ █▀▀▄${R}"
    Write-Host "${TC}▀▀▀▀ ▀  ▀ ▀▀▀  ▀▀▀▀ ▀  ▀${R}"
    Write-Host ""

    InstallGit
    InstallPython
    SetupRepo
    SetupApi
    SetupCli
    GenerateVadgrCli
    AddToPath

    Write-Host ""
    Ok "VADGR installed successfully!"
    Write-Host ""
    Ok "To get started:"
    Ok "  1. Restart your terminal"
    Ok "  2. Install a CLI provider (e.g. irm https://claude.ai/install.ps1 | iex)"
    Ok "  3. Run: vadgr start"
    Write-Host ""
}

Main
