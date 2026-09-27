[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('x64', 'arm64')][string] $Architecture,
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $SourceTestDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][string] $WheelhouseDirectory,
    [Parameter(Mandatory)][string] $SourceRecord
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
foreach ($name in @('GH_TOKEN', 'GITHUB_TOKEN', 'ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN')) {
    if ([Environment]::GetEnvironmentVariable($name)) { throw 'Source build must have no signing or identity credential.' }
}
$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path
$sourceTestRoot = (Resolve-Path -LiteralPath $SourceTestDirectory).Path
if ($sourceRoot -eq $sourceTestRoot -or
    $sourceRoot.StartsWith($sourceTestRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
    $sourceTestRoot.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Source tests and release compilation require separate source directories.'
}
$sourceRecordPath = (Resolve-Path -LiteralPath $SourceRecord).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Build output must be a new directory.' }
if (Test-Path -LiteralPath (Join-Path $sourceRoot 'E2E/0.5.0/e2e.md')) {
    throw 'The result-only runbook must be absent from the materialized build.'
}
$target = if ($Architecture -eq 'x64') { 'x86_64-pc-windows-msvc' } else { 'aarch64-pc-windows-msvc' }
$complianceTarget = if ($Architecture -eq 'x64') { 'windows-x86_64' } else { 'windows-aarch64' }
$compliance = Join-Path $sourceRoot "packaging/inputs/$complianceTarget"
$trustedRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$sourceTool = Join-Path $trustedRoot 'scripts/unsigned_windows_prep.py'
& python $sourceTool verify-test-source --source-root $sourceTestRoot --source-record $sourceRecordPath
if ($LASTEXITCODE -ne 0) { throw 'Exact source test checkout verification failed.' }
$wheelhouse = (Resolve-Path -LiteralPath $WheelhouseDirectory).Path
& python (Join-Path $trustedRoot 'scripts/cua_wheelhouse.py') --source $sourceRoot --target $target --verify $wheelhouse
if ($LASTEXITCODE -ne 0) { throw 'Offline wheelhouse verification failed.' }
$closedInputs = Get-Content -Raw -LiteralPath (Join-Path $wheelhouse 'wheelhouse.json') | ConvertFrom-Json
if ($closedInputs.PSObject.Properties.Name -contains 'release_profile') {
    if ($closedInputs.release_profile -ne $complianceTarget) { throw 'Reviewed wheelhouse profile differs.' }
    $releaseProfile = $closedInputs.release_profile
} else {
    $releaseProfile = $null
}
New-Item -ItemType Directory -Path $output | Out-Null
$payload = Join-Path $output 'payload'
New-Item -ItemType Directory -Path $payload | Out-Null
$env:RUSTFLAGS = '-C target-feature=+crt-static'
$env:CARGO_TARGET_DIR = Join-Path $sourceTestRoot 'target'
Push-Location $sourceTestRoot
try {
    foreach ($name in @('VADGR_RELEASE_PROFILE', 'VADGR_RELEASE_PAYLOAD_BUILD', 'VADGR_BUILD_WHEELHOUSE')) {
        # PowerShell 7.5 converts $null to an empty string in the .NET setter.
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath "Env:$name") { throw 'Candidate source test environment was not cleared.' }
    }
    & cargo test --locked --all-targets --features native-gui --target $target
    if ($LASTEXITCODE -ne 0) { throw 'Candidate tests failed.' }
} finally {
    Pop-Location
}
# The complete source suite needs the runbook, but release inputs must never contain it.
if (Test-Path -LiteralPath (Join-Path $sourceRoot 'E2E/0.5.0/e2e.md')) {
    throw 'The result-only runbook must be absent from the materialized build.'
}
$env:CARGO_TARGET_DIR = Join-Path $sourceRoot 'target'
Push-Location $sourceRoot
try {
    $env:VADGR_RELEASE_PAYLOAD_BUILD = '1'
    if ($null -eq $releaseProfile) {
        Remove-Item -LiteralPath 'Env:VADGR_RELEASE_PROFILE' -ErrorAction SilentlyContinue
    } else {
        $env:VADGR_RELEASE_PROFILE = $releaseProfile
    }
    & cargo build --locked --release --features native-gui --bin vadgr --bin vadgr-app --target $target
    if ($LASTEXITCODE -ne 0) { throw 'Candidate compilation failed.' }
    $binary = Join-Path $sourceRoot "target/$target/release"
    & "$binary/vadgr.exe" __payload-setup --install-root $payload --payload-only --wheelhouse $wheelhouse
    if ($LASTEXITCODE -ne 0) { throw 'Private runtime assembly failed.' }
    Copy-Item -LiteralPath "$binary/vadgr.exe", "$binary/vadgr-app.exe" -Destination $payload
    Copy-Item -LiteralPath 'packaging/windows/install-receipt.json' -Destination $payload
    Copy-Item -LiteralPath (Join-Path $compliance 'README-OFFLINE.txt'), (Join-Path $compliance 'package-input-inventory.json'), (Join-Path $compliance 'package-input-review.json') -Destination $payload
    Copy-Item -LiteralPath (Join-Path $compliance 'legal'), (Join-Path $compliance 'sbom') -Destination $payload -Recurse
    $env:VADGR_TERMS_VERSION = '1.0'
    $env:VADGR_TERMS_SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $compliance 'legal/TERMS.txt')).Hash.ToLowerInvariant()
    & cargo rustc --locked --manifest-path packaging/windows/ba-functions/Cargo.toml --release --target $target -- -C target-feature=+crt-static
    if ($LASTEXITCODE -ne 0) { throw 'Bootstrapper DLL compilation failed.' }
    Copy-Item -LiteralPath "packaging/windows/ba-functions/target/$target/release/vadgr_windows_ba_functions.dll" -Destination (Join-Path $output 'ba-functions.dll')
    Copy-Item -LiteralPath (Join-Path $compliance 'legal/TERMS.rtf') -Destination (Join-Path $output 'TERMS.rtf')
} finally {
    Pop-Location
}
Write-Output 'Unsigned Windows payload and bootstrapper DLL assembled. No signing or publication occurred.'
