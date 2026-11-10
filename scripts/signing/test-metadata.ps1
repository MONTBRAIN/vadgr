param(
    [Parameter(Mandatory)][string] $VendorRoot,
    [Parameter(Mandatory)][string] $PeFile,
    [Parameter(Mandatory)][string] $MsiFile
)
# Precondition: existing, independently signed public PE and MSI fixtures.
# This test never signs, authenticates, executes a fixture or changes the original.
$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('vadgr-metadata-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$jar = Join-Path $VendorRoot 'jar/code_sign_tool-1.3.3.jar'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $jar).Hash -ne 'CAA356347AA64BA04666545D548DAD87211C9AA960F16DB8797A880A67BA91D1') {
    throw 'The fixture parser JAR does not match the reviewed tool.'
}
$java = Join-Path $VendorRoot 'jdk-11.0.2/bin/java.exe'
$javac = Join-Path $VendorRoot 'jdk-11.0.2/bin/javac.exe'
foreach ($name in @('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
    [Environment]::SetEnvironmentVariable($name, $null, 'Process')
}
& $javac '-encoding' 'UTF-8' '-proc:none' '-cp' $jar '-d' $root (Join-Path $PSScriptRoot 'CodeSignRunner.java')
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
$env:SIGNING_LOG_CONFIG = Join-Path $PSScriptRoot 'log4j2-off.xml'
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/x64/signtool.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw 'Windows SDK SignTool is required.' }
foreach ($fixture in @(@($PeFile, 'fixture.exe'), @($PeFile, 'fixture.pyd'), @($MsiFile, 'fixture.msi'))) {
    $env:SIGNING_INPUT = Join-Path $root $fixture[1]
    Copy-Item -LiteralPath $fixture[0] -Destination $env:SIGNING_INPUT
    & $java '-cp' "$root;$jar" CodeSignRunner 'verify-metadata'
    if ($LASTEXITCODE -ne 0) { throw 'The existing signed fixture failed metadata verification.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $env:SIGNING_INPUT
    if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) {
        throw 'The Windows oracle did not accept the existing fixture.'
    }
    $verification = & $signTool.FullName verify /pa /all /tw /v $env:SIGNING_INPUT 2>&1
    if ($LASTEXITCODE -ne 0 -or ($verification | Out-String) -notmatch 'Hash of file \(sha256\)') {
        throw 'Independent SignTool SHA256 verification failed.'
    }
    Write-Output "PASS: $($fixture[1]) metadata and independent Windows trust/timestamp verification."
}
Write-Output 'No signatures requested. No fixture executed. No credentials supplied.'
Write-Output "Isolated test directory: $root"
