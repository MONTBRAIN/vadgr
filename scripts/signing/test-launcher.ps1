param([Parameter(Mandatory)][string] $VendorRoot)
$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('vadgr-signing-dummy-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
New-Item -ItemType Directory -Path (Join-Path $root 'conf') | Out-Null
Copy-Item (Join-Path $VendorRoot 'conf/code_sign_tool.properties') (Join-Path $root 'conf/code_sign_tool.properties')
$jar = Join-Path $VendorRoot 'jar/code_sign_tool-1.3.3.jar'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $jar).Hash -ne 'CAA356347AA64BA04666545D548DAD87211C9AA960F16DB8797A880A67BA91D1') {
    throw 'The dummy test JAR does not match the reviewed tool.'
}
$javac = Join-Path $VendorRoot 'jdk-11.0.2/bin/javac.exe'
$java = Join-Path $VendorRoot 'jdk-11.0.2/bin/java.exe'
& $javac '-encoding' 'UTF-8' '-proc:none' '-cp' $jar '-d' $root (Join-Path $PSScriptRoot 'CodeSignRunner.java')
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
$env:SIGNING_LOG_CONFIG = Join-Path $PSScriptRoot 'log4j2-off.xml'
$env:ES_USERNAME = 'dummy-user-not-a-real-account'
$env:ES_PASSWORD = 'dummy-password-not-a-real-secret'
$env:ES_TOTP_SECRET = 'ZHVtbXktc2VlZC1ub3QtYS1yZWFsLXNlY3JldA=='
foreach ($name in @('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS')) {
    [Environment]::SetEnvironmentVariable($name, $null, 'Process')
}
$saved = Get-Location
try {
    Set-Location $root
    $output = & $java '-cp' "$root;$jar" CodeSignRunner 'self-test' 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Dummy test exited $code." }
    $text = $output | Out-String
    foreach ($name in @('ES_USERNAME','ES_PASSWORD','ES_TOTP_SECRET')) {
        if ($text.Contains([Environment]::GetEnvironmentVariable($name))) { throw 'Raw output leaked dummy material.' }
    }
    if ($text.Trim() -ne 'Dummy credential suppression: PASS; vendor missing-file refusal verified.') { throw 'Unexpected raw output.' }
    if (Test-Path (Join-Path $root 'logs')) { throw 'Vendor created logs.' }
    $release = Join-Path $PSScriptRoot 'release.ps1'
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($release, [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw 'Production PowerShell did not parse.' }
    $reserve = $ast.Find({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Reserve-Attempt'
    }, $true)
    if (-not $reserve) { throw 'The one-shot ledger function is missing.' }
    . ([scriptblock]::Create($reserve.Extent.Text))
    $ledgerPath = Join-Path $root 'test-ledger.json'
    @{ budget = 2; attempts = @() } | ConvertTo-Json | Set-Content -LiteralPath $ledgerPath
    Reserve-Attempt 'first.exe'
    $refused = $false
    try { Reserve-Attempt 'FIRST.EXE' } catch { $refused = $true }
    if (-not $refused) { throw 'Duplicate signing was not refused.' }
    Reserve-Attempt 'second.msi'
    $refused = $false
    try { Reserve-Attempt 'third.exe' } catch { $refused = $true }
    if (-not $refused) { throw 'Quota overrun was not refused.' }
    $ledger = Get-Content -Raw -LiteralPath $ledgerPath | ConvertFrom-Json
    if ($ledger.attempts.Count -ne 2) { throw 'Refused attempts modified the ledger.' }
    $env:GITHUB_ACTIONS = 'true'
    $env:GITHUB_REPOSITORY = 'MONTBRAIN/vadgr'
    $env:GITHUB_REF_TYPE = 'branch'
    $env:GITHUB_REF = 'refs/heads/test'
    $env:GITHUB_RUN_ATTEMPT = '1'
    $refused = $false
    try { & $release -Mode sign -Root $root -Files @('missing.exe') } catch { $refused = $true }
    if (-not $refused) { throw 'Branch signing was not refused.' }
    $env:GITHUB_REF_TYPE = 'tag'
    $env:GITHUB_REF = 'refs/tags/v0.5.0'
    $env:GITHUB_RUN_ATTEMPT = '2'
    $refused = $false
    try { & $release -Mode sign -Root $root -Files @('missing.exe') } catch { $refused = $true }
    if (-not $refused) { throw 'A signing rerun was not refused.' }
    # No credential may become a persisted artifact, even when stdout is safe.
    foreach ($file in Get-ChildItem -LiteralPath $root -File -Recurse) {
        $bytes = [IO.File]::ReadAllBytes($file.FullName)
        $contents = [Text.Encoding]::UTF8.GetString($bytes)
        foreach ($name in @('ES_USERNAME','ES_PASSWORD','ES_TOTP_SECRET')) {
            if ($contents.Contains([Environment]::GetEnvironmentVariable($name))) { throw 'File leaked dummy material.' }
        }
    }
    Write-Output 'PASS: native Windows compilation, real vendor missing-file error, raw output suppression, no log directory, no dummy secrets in files.'
    Write-Output 'PASS: production script parsing, case-insensitive duplicate refusal, quota enforcement, branch refusal, rerun refusal.'
    Write-Output "Isolated test directory: $root"
} finally {
    Set-Location $saved
    foreach ($name in @('ES_USERNAME','ES_PASSWORD','ES_TOTP_SECRET')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}
