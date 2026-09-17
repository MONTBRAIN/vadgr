param([Parameter(Mandatory)][string] $VendorRoot)
$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('vadgr-signing-dummy-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
New-Item -ItemType Directory -Path (Join-Path $root 'conf') | Out-Null
Copy-Item (Join-Path $VendorRoot 'conf/code_sign_tool.properties') (Join-Path $root 'conf/code_sign_tool.properties')
$jar = Join-Path $VendorRoot 'jar/code_sign_tool-1.3.3.jar'
$javac = Join-Path $VendorRoot 'jdk-11.0.2/bin/javac.exe'
$java = Join-Path $VendorRoot 'jdk-11.0.2/bin/java.exe'
& $javac '-proc:none' '-cp' $jar '-d' $root (Join-Path $PSScriptRoot 'SigningSmoke.java')
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
$env:SMOKE_LOG_CONFIG = Join-Path $PSScriptRoot 'log4j2-off.xml'
$env:ES_USERNAME = 'dummy-user-not-a-real-account'
$env:ES_PASSWORD = 'dummy-password-not-a-real-secret'
$env:ES_TOTP_SECRET = 'ZHVtbXktc2VlZC1ub3QtYS1yZWFsLXNlY3JldA=='
$saved = Get-Location
try {
    Set-Location $root
    $output = & $java '-cp' "$root;$jar" SigningSmoke 'self-test' 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Dummy test exited $code." }
    $text = $output | Out-String
    foreach ($name in @('ES_USERNAME','ES_PASSWORD','ES_TOTP_SECRET')) {
        if ($text.Contains([Environment]::GetEnvironmentVariable($name))) { throw 'Raw output leaked dummy material.' }
    }
    if ($text.Trim() -ne 'Dummy credential suppression: PASS; vendor missing-file refusal verified.') { throw 'Unexpected raw output.' }
    if (Test-Path (Join-Path $root 'logs')) { throw 'Vendor created logs.' }
    # No credential may become a persisted artifact, even when stdout is safe.
    foreach ($file in Get-ChildItem -LiteralPath $root -File -Recurse) {
        $bytes = [IO.File]::ReadAllBytes($file.FullName)
        $contents = [Text.Encoding]::UTF8.GetString($bytes)
        foreach ($name in @('ES_USERNAME','ES_PASSWORD','ES_TOTP_SECRET')) {
            if ($contents.Contains([Environment]::GetEnvironmentVariable($name))) { throw 'File leaked dummy material.' }
        }
    }
    Write-Output 'PASS: native Windows compilation, real vendor missing-file error, raw output suppression, no log directory, no dummy secrets in files.'
    Write-Output "Isolated test directory: $root"
} finally {
    Set-Location $saved
    foreach ($name in @('ES_USERNAME','ES_PASSWORD','ES_TOTP_SECRET')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}
