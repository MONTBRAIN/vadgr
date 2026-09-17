param(
    [Parameter(Mandatory)][ValidateSet('prepare', 'sign', 'complete')][string] $Mode,
    [string[]] $Files,
    [int] $Budget = 0,
    [string] $Authorization,
    [string] $Claim,
    [string] $Qualification,
    [string] $Root = (Join-Path $env:RUNNER_TEMP "release-signing-$env:GITHUB_RUN_ID")
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
    $env:SIGNING_LOG_CONFIG = Join-Path $source 'log4j2-off.xml'
    & java '-Dfile.encoding=UTF-8' '-XX:-HeapDumpOnOutOfMemoryError' '-XX:ErrorFile=NUL' '-cp' "$classes;$jar" CodeSignRunner $Operation
    if ($LASTEXITCODE -ne 0) { throw 'The signing operation failed. No retry is permitted.' }
}

if ($Mode -eq 'prepare') {
    if (Test-Path -LiteralPath $Root) { throw 'The isolated signing directory already exists.' }
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
    & javac '-encoding' 'UTF-8' '-proc:none' '-cp' $jar '-d' $classes (Join-Path $source 'CodeSignRunner.java')
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
    if ($Budget -lt 5) { throw 'The approved signature budget is missing.' }
    @{ budget = $Budget; attempts = @() } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Root 'ledger.json')
    return
}

if ($env:GITHUB_ACTIONS -ne 'true' -or $env:GITHUB_REPOSITORY -ne 'MONTBRAIN/vadgr' -or
    $env:GITHUB_REF_TYPE -ne 'branch' -or $env:GITHUB_REF -ne 'refs/heads/master' -or
    $env:GITHUB_RUN_ATTEMPT -ne '1') {
    throw 'Signing is restricted to the first attempt of an approved default-branch candidate.'
}
if (-not $Authorization -or -not $Claim -or -not $Qualification) { throw 'The protected authorization and durable claim are required.' }
$policy = Join-Path (Split-Path -Parent $PSScriptRoot) 'candidate_claims.py'
& python $policy verify --authorization $Authorization --qualification $Qualification --claim $Claim
if ($LASTEXITCODE -ne 0) { throw 'The protected signing claim did not verify.' }
$approved = Get-Content -Raw -LiteralPath $Authorization | ConvertFrom-Json
$ledgerPath = Join-Path $Root 'ledger.json'
$ledger = Get-Content -Raw -LiteralPath $ledgerPath | ConvertFrom-Json
if ($ledger.budget -ne $approved.budget) { throw 'The local budget differs from the protected authorization.' }
if ($Mode -eq 'complete') {
    if (@($ledger.attempts).Count -ne $ledger.budget) { throw 'The signature quota does not match the completed layers.' }
    Write-Output "Verified signing attempts: $($ledger.attempts.Count). No retry performed."
    return
}
if (-not $Files -or $Files.Count -eq 0) { throw 'Explicit input files are required.' }
$identity = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $source 'publisher.json') | ConvertFrom-Json
$env:EXPECTED_CERT_SHA256 = $identity.sha256
$env:EXPECTED_CERT_SHA1 = $identity.sha1
$env:EXPECTED_CERT_SUBJECT = $identity.subject
Assert-Hash $jar $jarHash
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/x64/signtool.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw 'Windows SDK SignTool is required before signing.' }

function Reserve-Attempt([string] $InputFile) {
    $ledger = Get-Content -Raw -LiteralPath $ledgerPath | ConvertFrom-Json
    if (@($ledger.attempts).Count -ge $ledger.budget -or $ledger.attempts -contains $InputFile) {
        throw 'A duplicate signing attempt or quota overrun was refused.'
    }
    $ledger.attempts = @($ledger.attempts) + $InputFile
    # Persist BEFORE authentication. Uncertain attempts consume the local budget too.
    $ledger | ConvertTo-Json | Set-Content -LiteralPath $ledgerPath
}

try {
    foreach ($file in $Files) {
        $inputFile = (Resolve-Path -LiteralPath $file).Path
        if ([IO.Path]::GetExtension($inputFile) -notin @('.exe', '.dll', '.pyd', '.msi')) {
            throw 'The signing input is not a supported release layer.'
        }
        $output = Join-Path $Root ([Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $output | Out-Null
        $env:SIGNING_INPUT = $inputFile
        # CPython extension modules are PE DLLs, but the vendor dispatches by suffix.
        # Only the temporary basename changes; the PE bytes and quota stay identical.
        if ([IO.Path]::GetExtension($inputFile) -eq '.pyd') {
            $temporaryInput = Join-Path $output 'python-extension.dll'
            Copy-Item -LiteralPath $inputFile -Destination $temporaryInput
            $env:SIGNING_INPUT = $temporaryInput
        }
        $vendorName = [IO.Path]::GetFileName($env:SIGNING_INPUT)
        $vendorOutput = Join-Path $output 'signed'
        New-Item -ItemType Directory -Path $vendorOutput | Out-Null
        $env:SIGNING_OUTPUT = $vendorOutput
        Reserve-Attempt $inputFile
        Push-Location $Root
        try { Invoke-Wrapper 'sign' } finally { Pop-Location }
        $signed = Join-Path $vendorOutput $vendorName
        if ([IO.Path]::GetExtension($inputFile) -eq '.pyd') {
            $restoredName = Join-Path $vendorOutput ([IO.Path]::GetFileName($inputFile))
            Move-Item -LiteralPath $signed -Destination $restoredName
            $signed = $restoredName
        }
        $env:SIGNING_INPUT = $signed
        Invoke-Wrapper 'verify-metadata'
        $verification = & $signTool.FullName verify /pa /all /tw /v $signed 2>&1
        if ($LASTEXITCODE -ne 0) { throw 'Independent Windows verification failed. No retry permitted.' }
        if (($verification | Out-String) -notmatch 'Hash of file \(sha256\)') {
            throw 'The file digest algorithm is not SHA256.'
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $signed
        if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) {
            throw 'A trusted signature and timestamp are required.'
        }
        $cert = $signature.SignerCertificate
        $fingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cert.RawData))
        if ($fingerprint -ne $identity.sha256 -or $cert.Thumbprint -ne $identity.sha1) {
            throw 'The signed layer has the wrong publisher certificate.'
        }
        Move-Item -LiteralPath $signed -Destination $inputFile -Force
        Write-Output "Verified layer: $([IO.Path]::GetFileName($inputFile)); certificate SHA256: $fingerprint; SHA1: $($cert.Thumbprint); timestamp: $($signature.TimeStamperCertificate.Subject)"
    }
} finally {
    foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}
