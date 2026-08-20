# Vadgr Installer for Windows
# Usage: irm https://raw.githubusercontent.com/MONTBRAIN/vadgr/master/install.ps1 | iex

$ErrorActionPreference = "Stop"

# One install root, named after the product. A machine's durable state does not
# live here: the daemon resolves that from the platform's own local-state
# directory, so this holds the binaries and the checkout they are built from.
$VADGR_HOME = "$env:USERPROFILE\.vadgr"
$VADGR_BIN = "$VADGR_HOME\bin"
$VADGR_REPO = "$VADGR_HOME\src"
# The source and the ref, overridable so a release can be installed and driven
# before it is merged. An end to end pass has to install the same script a user
# runs; without these it could only ever test what is already on the default
# branch, which is never the release being proven.
$REPO_URL = if ($env:VADGR_REPO_URL) { $env:VADGR_REPO_URL } else { "https://github.com/MONTBRAIN/vadgr.git" }
$REPO_REF = if ($env:VADGR_REF) { $env:VADGR_REF } else { "master" }

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


# ---------------------------------------------------------------------------
# Setup Vadgr
# ---------------------------------------------------------------------------

function MsvcToolsPresent {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $false }
    $path = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    return -not [string]::IsNullOrWhiteSpace("$path")
}

function InstallBuildTools {
    # rustup installs the compiler but not the MSVC linker it drives, and
    # Windows does not ship one: without this the build fails minutes in with
    # "link.exe not found". The Build Tools carry the linker and the Windows
    # SDK the static C runtime is linked from.
    if (MsvcToolsPresent) { return }
    Info "Installing the Visual Studio Build Tools (the MSVC linker; this is the largest download)..."
    EnsureWinget
    winget install --id Microsoft.VisualStudio.2022.BuildTools --accept-source-agreements --accept-package-agreements --silent `
        --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    if (-not (MsvcToolsPresent)) {
        Fail "The Build Tools did not install. Install 'Visual Studio Build Tools' with the 'Desktop development with C++' workload, then re-run this script."
    }
}

function InstallRust {
    if (CommandExists cargo) { return }
    Info "Installing the Rust toolchain..."
    # The official installer, non-interactive. The product is one binary and
    # this is what builds it.
    $installer = "$env:TEMP\rustup-init.exe"
    Invoke-WebRequest -Uri "https://win.rustup.rs/x86_64" -OutFile $installer -UseBasicParsing
    & $installer -y --no-modify-path | Out-Null
    $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
    if (-not (CommandExists cargo)) { Fail "Rust installed but cargo is not on PATH. Open a new terminal and run this again." }
}

function BuildAndInstall {
    Info "Building vadgr (this takes a few minutes the first time)..."
    if (-not (CommandExists cargo)) { $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH" }
    Push-Location $VADGR_REPO
    # The C runtime is linked in rather than imported. A binary that imports
    # vcruntime140.dll needs the Visual C++ redistributable, which is not part
    # of Windows, so it would fail to start on a machine that never installed
    # it. The target is named explicitly so these flags reach the binary and
    # not the build scripts and proc macros that run on the host.
    $env:RUSTFLAGS = "-C target-feature=+crt-static"
    & cargo build --locked --release --bins --target x86_64-pc-windows-msvc
    $built = $LASTEXITCODE
    Remove-Item Env:\RUSTFLAGS
    Pop-Location
    if ($built -ne 0) { Fail "The build failed. Nothing was installed." }

    New-Item -ItemType Directory -Force -Path $VADGR_BIN | Out-Null
    # Installed only after the build succeeded, so a failed build leaves the
    # installation that was already working exactly as it was.
    foreach ($binary in @("vadgr.exe")) {
        Copy-Item "$VADGR_REPO\target\x86_64-pc-windows-msvc\release\$binary" "$VADGR_BIN\$binary" -Force
    }
    Ok "Installed vadgr into $VADGR_BIN"
}

function SetupRepo {
    if (Test-Path "$VADGR_REPO\.git") {
        Info "Vadgr repo already exists, pulling latest..."
        & { $ErrorActionPreference = 'SilentlyContinue'; git -C $VADGR_REPO fetch --quiet origin $REPO_REF 2>$null }
        & { $ErrorActionPreference = 'SilentlyContinue'; git -C $VADGR_REPO checkout --quiet $REPO_REF 2>$null }
        & { $ErrorActionPreference = 'SilentlyContinue'; git -C $VADGR_REPO pull --ff-only origin $REPO_REF 2>$null }
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
        if ($REPO_REF -ne "master") {
            git -C $VADGR_REPO checkout --quiet $REPO_REF
            if ($LASTEXITCODE -ne 0) { Fail "The ref $REPO_REF is not in $REPO_URL. Nothing was installed." }
        }
    }
}

# ---------------------------------------------------------------------------
# Generate vadgr CLI
# ---------------------------------------------------------------------------

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
    InstallBuildTools
    InstallRust
    SetupRepo
    BuildAndInstall
    AddToPath

    Write-Host ""
    Ok "VADGR installed successfully!"
    Write-Host ""
    Ok "To get started:"
    Ok "  1. Restart your terminal"
    Ok "  2. Run: vadgr provider login"
    Ok "  3. Run: vadgr start, then vadgr pair"
    Write-Host ""
}

Main
