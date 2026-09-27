param(
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $Root = (Join-Path $env:RUNNER_TEMP "certificate-inspection-$env:GITHUB_RUN_ID")
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:GITHUB_ACTIONS -ne 'true' -or $env:GITHUB_REPOSITORY -ne 'MONTBRAIN/vadgr' -or
    $env:GITHUB_REF -ne 'refs/heads/master' -or $env:GITHUB_RUN_ATTEMPT -ne '1') {
    throw 'Certificate inspection is restricted to the first trusted default-branch attempt.'
}
if ($env:ES_TOTP_SECRET) { throw 'Certificate inspection must not receive a signing secret.' }
if ((Test-Path -LiteralPath $Root) -or (Test-Path -LiteralPath $OutputDirectory)) {
    throw 'Certificate inspection requires new isolated directories.'
}

$jarHash = 'CAA356347AA64BA04666545D548DAD87211C9AA960F16DB8797A880A67BA91D1'
$zipHash = '317D429BE3AA12A5F2C1FFDD575EAB0CB0CE5E2408AB0056BCDCAAB29875F73D'
$source = $PSScriptRoot
$jar = Join-Path $Root 'code_sign_tool-1.3.3.jar'
$classes = Join-Path $Root 'classes'
$publicCertificates = Join-Path $OutputDirectory 'certificates'

function Assert-Hash([string] $Path, [string] $Expected) {
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Expected) {
        throw 'The pinned signing tool hash does not match.'
    }
}

try {
    New-Item -ItemType Directory -Path $Root, $classes, (Join-Path $Root 'conf'), $OutputDirectory, $publicCertificates | Out-Null
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
    if ($LASTEXITCODE -ne 0) { throw 'The credential-safe inspector did not compile.' }

    $identity = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $source 'publisher.json') | ConvertFrom-Json
    $env:EXPECTED_CERT_SHA256 = $identity.sha256
    $env:EXPECTED_CERT_SUBJECT = $identity.subject
    $env:CERTIFICATE_OUTPUT = (Resolve-Path -LiteralPath $publicCertificates).Path
    $env:SIGNING_LOG_CONFIG = Join-Path $source 'log4j2-off.xml'
    foreach ($name in @('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    Push-Location -LiteralPath $Root
    try {
        [string[]]$report = @(& java '-Dfile.encoding=UTF-8' '-XX:-HeapDumpOnOutOfMemoryError' '-XX:ErrorFile=NUL' '-cp' "$classes;$jar" CodeSignRunner inspect)
        $javaExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($javaExit -ne 0 -or $report[-1] -ne 'Public certificate inspection complete. Signatures requested: 0.') {
        $safeFailure = [string]$report[-1]
        if ($safeFailure -notmatch '^Signing stopped at safe stage (startup|authentication|credential-list|credential-inspection|certificate-export|signing)\. Authentication, certificate, configuration or vendor check failed\. No retry performed\.$') {
            $safeFailure = 'Signing stopped without an allowlisted diagnostic stage.'
        }
        throw "Public certificate inspection failed. $safeFailure"
    }
    [IO.File]::WriteAllLines((Join-Path $OutputDirectory 'inspection.txt'), [string[]]$report,
        [Text.UTF8Encoding]::new($false))
    $report
} finally {
    foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET', 'EXPECTED_CERT_SHA256',
                         'EXPECTED_CERT_SUBJECT', 'CERTIFICATE_OUTPUT', 'SIGNING_LOG_CONFIG')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}
