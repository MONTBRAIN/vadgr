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
    if ([Environment]::GetEnvironmentVariable($name)) { throw 'Unsigned preparation must have no signing or identity credential.' }
}
$expectedNative = if ($Architecture -eq 'x64') { 'X64' } else { 'ARM64' }
$native = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToUpperInvariant()
if ($native -ne $expectedNative -or $env:RUNNER_ARCH -ne $expectedNative) {
    throw 'Unsigned preparation requires the selected native Windows runner.'
}
$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path
$sourceTestRoot = (Resolve-Path -LiteralPath $SourceTestDirectory).Path
if ($sourceRoot -eq $sourceTestRoot -or
    $sourceRoot.StartsWith($sourceTestRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
    $sourceTestRoot.StartsWith($sourceRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Source tests and release compilation require separate source directories.'
}
$wheelhouse = (Resolve-Path -LiteralPath $WheelhouseDirectory).Path
$sourceRecordPath = (Resolve-Path -LiteralPath $SourceRecord).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
$trustedRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$tool = Join-Path $trustedRoot 'scripts/unsigned_windows_prep.py'
$target = if ($Architecture -eq 'x64') { 'x86_64-pc-windows-msvc' } else { 'aarch64-pc-windows-msvc' }
$profile = if ($Architecture -eq 'x64') { 'windows-x86_64' } else { 'windows-aarch64' }
if (Test-Path -LiteralPath $output) { throw 'Unsigned preparation output must be a new directory.' }
if (Test-Path -LiteralPath (Join-Path $sourceRoot 'E2E/0.5.0/e2e.md')) {
    throw 'The result-only runbook must be absent from the materialized build.'
}
& python $tool verify-test-source --source-root $sourceTestRoot --source-record $sourceRecordPath
if ($LASTEXITCODE -ne 0) { throw 'Exact source test checkout verification failed.' }
& python (Join-Path $trustedRoot 'scripts/cua_wheelhouse.py') --source $sourceRoot --target $target --release-profile $profile --verify $wheelhouse
if ($LASTEXITCODE -ne 0) { throw 'Reviewed profile wheelhouse verification failed.' }
New-Item -ItemType Directory -Path $output | Out-Null
$payload = Join-Path $output 'payload'
New-Item -ItemType Directory -Path $payload | Out-Null
$linkMaps = Join-Path $output 'link-maps'
New-Item -ItemType Directory -Path $linkMaps | Out-Null
Copy-Item -LiteralPath $sourceRecordPath -Destination (Join-Path $output 'preparation-source.json')
Copy-Item -LiteralPath $wheelhouse -Destination (Join-Path $output 'wheelhouse') -Recurse
& python $tool terms --source-root $sourceRoot --out (Join-Path $output 'terms-input.json')
if ($LASTEXITCODE -ne 0) { throw 'Proposed terms inspection failed.' }
$terms = Get-Content -Raw -LiteralPath (Join-Path $output 'terms-input.json') | ConvertFrom-Json
$cargoHome = Join-Path $env:RUNNER_TEMP 'unsigned-preparation-cargo'
$env:CARGO_HOME = $cargoHome
$env:CARGO_TARGET_DIR = Join-Path $sourceTestRoot 'target'
$env:RUSTFLAGS = '-C target-feature=+crt-static'
& rustc --version --verbose | Set-Content -LiteralPath (Join-Path $output 'rustc-version.txt') -Encoding utf8NoBOM
if ($LASTEXITCODE -ne 0) { throw 'Rust compiler identity failed.' }
& cargo --version --verbose | Set-Content -LiteralPath (Join-Path $output 'cargo-version.txt') -Encoding utf8NoBOM
if ($LASTEXITCODE -ne 0) { throw 'Cargo identity failed.' }
Push-Location $sourceTestRoot
try {
    foreach ($name in @('VADGR_RELEASE_PROFILE', 'VADGR_RELEASE_PAYLOAD_BUILD', 'VADGR_BUILD_WHEELHOUSE')) {
        # PowerShell 7.5 converts $null to an empty string in the .NET setter.
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath "Env:$name") { throw 'Unsigned source test environment was not cleared.' }
    }
    & cargo test --locked --all-targets --features native-gui --target $target
    if ($LASTEXITCODE -ne 0) { throw 'Unsigned preparation source tests failed.' }
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
    $env:VADGR_RELEASE_PROFILE = $profile
    foreach ($name in @('vadgr', 'vadgr-app')) {
        $mapPath = Join-Path $linkMaps "$name.map"
        & cargo rustc --locked --release --features native-gui --bin $name --target $target -- -C "link-arg=/MAP:$mapPath"
        if ($LASTEXITCODE -ne 0) { throw 'Unsigned daemon or application compilation failed.' }
    }
    $binary = Join-Path $sourceRoot "target/$target/release"
    & "$binary/vadgr.exe" __payload-setup --install-root $payload --payload-only --wheelhouse $wheelhouse
    if ($LASTEXITCODE -ne 0) { throw 'Unsigned private runtime assembly failed.' }
    Copy-Item -LiteralPath "$binary/vadgr.exe", "$binary/vadgr-app.exe" -Destination $payload
    $relocated = Join-Path $env:RUNNER_TEMP "vadgr-relocated-$Architecture"
    if (Test-Path -LiteralPath $relocated) { throw 'Relocation probe destination already exists.' }
    Move-Item -LiteralPath $payload -Destination $relocated
    try {
        if (Test-Path -LiteralPath $payload) { throw 'Private runtime assembly root still exists.' }
        $cuaManifest = Get-Content -Raw -LiteralPath (Join-Path $relocated 'lib/cua/payload.json') | ConvertFrom-Json
        $privatePython = Join-Path $relocated "lib/cua/python/$($cuaManifest.python_version)/python.exe"
        $bootstrap = Join-Path $relocated 'lib/cua/bootstrap.py'
        $pythonVersion = & $privatePython --version 2>&1
        if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch "^Python $([Regex]::Escape($cuaManifest.python_version))$") {
            throw 'Relocated private Python version probe failed.'
        }
        $cuaVersion = & $privatePython -I -B $bootstrap computer_use.mcp_server --version 2>&1
        if ($LASTEXITCODE -ne 0 -or $cuaVersion -notmatch " $([Regex]::Escape($cuaManifest.cua_version))$") {
            throw 'Relocated private CUA import probe failed.'
        }
    } finally {
        if (Test-Path -LiteralPath $relocated) {
            if (Test-Path -LiteralPath $payload) { throw 'Private runtime output was recreated during relocation.' }
            Move-Item -LiteralPath $relocated -Destination $payload
        }
    }
    & cargo metadata --locked --format-version 1 --features native-gui --filter-platform $target |
        Set-Content -LiteralPath (Join-Path $output 'cargo-metadata.json') -Encoding utf8NoBOM
    if ($LASTEXITCODE -ne 0) { throw 'Daemon dependency metadata failed.' }
    & python $tool cargo-notices --metadata (Join-Path $output 'cargo-metadata.json') --source-root $sourceRoot --cargo-home $cargoHome --out (Join-Path $output 'cargo-notices')
    if ($LASTEXITCODE -ne 0) { throw 'Daemon dependency notices failed.' }
    $baStatus = 'not-built-exact-terms-unavailable'
    if ($terms.status -eq 'unapproved') {
        $termsRoot = Join-Path $output 'proposed-terms'
        New-Item -ItemType Directory -Path $termsRoot | Out-Null
        Copy-Item -LiteralPath (Join-Path $sourceRoot $terms.path) -Destination (Join-Path $termsRoot 'TERMS.txt')
        $env:VADGR_TERMS_VERSION = $terms.version
        $env:VADGR_TERMS_SHA256 = $terms.sha256
        $baMapPath = Join-Path $linkMaps 'ba-functions.map'
        & cargo rustc --locked --manifest-path packaging/windows/ba-functions/Cargo.toml --release --target $target -- -C target-feature=+crt-static -C "link-arg=/MAP:$baMapPath"
        if ($LASTEXITCODE -ne 0) { throw 'Unsigned bootstrapper compilation failed.' }
        Copy-Item -LiteralPath (Join-Path $binary 'vadgr_windows_ba_functions.dll') -Destination (Join-Path $output 'ba-functions.dll')
        & cargo metadata --locked --manifest-path packaging/windows/ba-functions/Cargo.toml --format-version 1 --filter-platform $target |
            Set-Content -LiteralPath (Join-Path $output 'ba-cargo-metadata.json') -Encoding utf8NoBOM
        if ($LASTEXITCODE -ne 0) { throw 'Bootstrapper dependency metadata failed.' }
        & python $tool cargo-notices --metadata (Join-Path $output 'ba-cargo-metadata.json') --source-root $sourceRoot --cargo-home $cargoHome --out (Join-Path $output 'ba-cargo-notices')
        if ($LASTEXITCODE -ne 0) { throw 'Bootstrapper dependency notices failed.' }
        $baStatus = 'built-unsigned-unapproved'
    }
    & python (Join-Path $trustedRoot 'scripts/windows_runtime_evidence.py') capture --raw-root $output --architecture $Architecture
    if ($LASTEXITCODE -ne 0) { throw 'Native runtime evidence capture failed.' }
    @{ schema = 1; status = 'unapproved'; publishable = $false; architecture = $Architecture;
       native_architecture = $native; bootstrapper = $baStatus; terms = $terms } |
        ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $output 'build-observation.json') -Encoding utf8NoBOM
    'Unsigned preparation only. Unapproved and nonpublishable.' |
        Set-Content -LiteralPath (Join-Path $output 'UNAPPROVED-NONPUBLISHABLE.txt') -Encoding utf8NoBOM
} finally {
    Pop-Location
}
Write-Output 'Unsigned Windows observations assembled. No candidate or legal approval was created.'
