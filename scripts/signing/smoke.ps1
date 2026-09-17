param(
    [ValidateSet('prepare', 'inspect', 'sign')][string] $Mode,
    [string] $Root = (Join-Path $env:RUNNER_TEMP "signing-smoke-$env:GITHUB_RUN_ID")
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$jarHash = 'CAA356347AA64BA04666545D548DAD87211C9AA960F16DB8797A880A67BA91D1'
$zipHash = '317D429BE3AA12A5F2C1FFDD575EAB0CB0CE5E2408AB0056BCDCAAB29875F73D'
$source = $PSScriptRoot
$jar = Join-Path $Root 'code_sign_tool-1.3.3.jar'
$classes = Join-Path $Root 'classes'

function Assert-Hash([string] $Path, [string] $Expected) {
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Expected) {
        throw 'The pinned signing tool hash does not match.'
    }
}

function Invoke-Wrapper([string] $Operation) {
    # Neither the vendor runtime nor Java option injection can enable secret-bearing diagnostics.
    foreach ($name in @('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $env:SMOKE_LOG_CONFIG = Join-Path $source 'log4j2-off.xml'
    & java '-Dfile.encoding=UTF-8' '-XX:-HeapDumpOnOutOfMemoryError' '-XX:ErrorFile=NUL' '-cp' "$classes;$jar" SigningSmoke $Operation
    if ($LASTEXITCODE -ne 0) { throw 'The signing probe failed. No retry is permitted.' }
}

if ($Mode -eq 'prepare') {
    if (Test-Path -LiteralPath $Root) { throw 'The isolated probe directory already exists.' }
    New-Item -ItemType Directory -Path $Root | Out-Null
    New-Item -ItemType Directory -Path $classes | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Root 'conf') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Root 'signed') | Out-Null
    $archive = Join-Path $Root 'vendor.zip'
    Invoke-WebRequest -Uri 'https://ssl.com/download/codesigntool-for-windows/' -OutFile $archive
    Assert-Hash $archive $zipHash
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach ($pair in @(
            @('jar/code_sign_tool-1.3.3.jar', $jar),
            @('conf/code_sign_tool.properties', (Join-Path $Root 'conf/code_sign_tool.properties'))
        )) {
            $entry = $zip.GetEntry($pair[0])
            if (-not $entry) { throw 'A pinned vendor package member is missing.' }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $pair[1], $false)
        }
    } finally { $zip.Dispose() }
    Assert-Hash $jar $jarHash
    & javac '-proc:none' '-cp' $jar '-d' $classes (Join-Path $source 'SigningSmoke.java')
    if ($LASTEXITCODE -ne 0) { throw 'The credential-safe launcher did not compile.' }
    Push-Location $Root
    try {
        $env:ES_USERNAME = 'dummy-user-not-a-real-account'
        $env:ES_PASSWORD = 'dummy-password-not-a-real-secret'
        $env:ES_TOTP_SECRET = 'ZHVtbXktc2VlZC1ub3QtYS1yZWFsLXNlY3JldA=='
        $output = Invoke-Wrapper 'self-test' | Out-String
        foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
            if ($output.Contains([Environment]::GetEnvironmentVariable($name))) {
                throw 'Dummy credential appeared in raw launcher output.'
            }
        }
        if ($output.Trim() -ne 'Dummy credential suppression: PASS; vendor missing-file refusal verified.') {
            throw 'Unexpected launcher self-test output.'
        }
        if (Test-Path -LiteralPath (Join-Path $Root 'logs')) { throw 'Vendor file logging was not disabled.' }
        Write-Output $output.Trim()
    } finally {
        foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
        Pop-Location
    }
    return
}

if ($env:GITHUB_ACTIONS -ne 'true' -or $env:GITHUB_REPOSITORY -ne 'MONTBRAIN/vadgr' -or
    $env:GITHUB_REF -ne 'refs/heads/signing-smoke-iv-20260916' -or $env:GITHUB_RUN_ATTEMPT -ne '1') {
    throw 'Live credentials are allowed only in the approved isolated hosted job.'
}
Assert-Hash $jar $jarHash
Push-Location $Root
try {
    if ($Mode -eq 'inspect') {
        if ($env:ES_TOTP_SECRET) { throw 'The inspect-only step must not receive the TOTP secret.' }
        Invoke-Wrapper 'inspect'
        return
    }
    if ($env:EXPECTED_CERT_SHA256 -notmatch '^[A-Fa-f0-9]{64}$' -or
        [string]::IsNullOrWhiteSpace($env:EXPECTED_CERT_SUBJECT) -or
        $env:APPROVED_SIGNATURE_COUNT -ne '1') {
        throw 'One signature and the independently verified public identity must be approved first.'
    }
    $signTool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/x64/signtool.exe" |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $signTool) { throw 'Windows SDK SignTool is required before signing.' }
    # A local compiler produces one inert program. No downloaded executable is signed.
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    $sample = Join-Path $Root 'smoke-input.cs'
    [IO.File]::WriteAllText($sample, 'internal static class Smoke { private static int Main() { return 0; } }')
    & $compiler /nologo /target:exe /out:smoke-input.exe $sample
    if ($LASTEXITCODE -ne 0) { throw 'The inert signing sample did not compile.' }
    if ((Get-AuthenticodeSignature -LiteralPath 'smoke-input.exe').Status -ne 'NotSigned') {
        throw 'The signing sample is not unsigned.'
    }
    Invoke-Wrapper 'sign'
    $signed = Join-Path $Root 'signed/smoke-input.exe'
    & $signTool.FullName verify /pa /all /tw $signed
    if ($LASTEXITCODE -ne 0) { throw 'Independent Windows signature verification failed.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $signed
    if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) {
        throw 'Windows did not verify a trusted, timestamped signature.'
    }
    $cert = $signature.SignerCertificate
    $fingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cert.RawData))
    if ($fingerprint -ne $env:EXPECTED_CERT_SHA256) {
        throw 'The signed sample has the wrong publisher identity.'
    }
    Write-Output "Verified public publisher: $($cert.Subject)"
    Write-Output "Verified public certificate SHA256: $fingerprint"
    Write-Output "Verified public certificate SHA1: $($cert.Thumbprint)"
    Write-Output "Verified timestamp authority: $($signature.TimeStamperCertificate.Subject)"
    Write-Output "Signed sample SHA256: $((Get-FileHash -Algorithm SHA256 -LiteralPath $signed).Hash)"
    Write-Output 'One-file signing probe verified. No release created; no artifact uploaded.'
} finally {
    foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    Pop-Location
}
