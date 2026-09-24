[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('x64', 'arm64')][string] $Architecture,
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][string] $WheelhouseDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
foreach ($name in @('GH_TOKEN', 'GITHUB_TOKEN', 'ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN')) {
    if ([Environment]::GetEnvironmentVariable($name)) { throw 'Source build must have no signing or identity credential.' }
}
$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Build output must be a new directory.' }
if (Test-Path -LiteralPath (Join-Path $sourceRoot 'E2E/0.5.0/e2e.md')) {
    throw 'The result-only runbook must be absent from the materialized build.'
}
$target = if ($Architecture -eq 'x64') { 'x86_64-pc-windows-msvc' } else { 'aarch64-pc-windows-msvc' }
$complianceTarget = if ($Architecture -eq 'x64') { 'windows-x86_64' } else { 'windows-aarch64' }
$compliance = Join-Path $sourceRoot "packaging/inputs/$complianceTarget"
$trustedRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
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
Push-Location $sourceRoot
try {
    $env:RUSTFLAGS = '-C target-feature=+crt-static'
    [Environment]::SetEnvironmentVariable('VADGR_RELEASE_PROFILE', $null)
    [Environment]::SetEnvironmentVariable('VADGR_RELEASE_PAYLOAD_BUILD', $null)
    & cargo test --locked --all-targets --features native-gui --target $target
    if ($LASTEXITCODE -ne 0) { throw 'Candidate tests failed.' }
    $env:VADGR_RELEASE_PAYLOAD_BUILD = '1'
    [Environment]::SetEnvironmentVariable('VADGR_RELEASE_PROFILE', $releaseProfile)
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
