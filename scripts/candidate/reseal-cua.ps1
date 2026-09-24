param(
    [Parameter(Mandatory)][string] $InputDirectory,
    [Parameter(Mandatory)][string] $Authorization,
    [Parameter(Mandatory)][string] $Receipt,
    [Parameter(Mandatory)][string] $Records
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
    if ([Environment]::GetEnvironmentVariable($name)) { throw 'Inventory reseal must have no vendor credentials.' }
}
$root = (Resolve-Path -LiteralPath $InputDirectory).Path
$identity = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../signing/publisher.json') | ConvertFrom-Json
$native = if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'Arm64') { 'arm64' } else { 'x64' }
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/$native/signtool.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw 'Windows SDK SignTool is required before inventory reseal.' }
$layers = @(Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object Extension -In '.exe','.dll','.pyd')
if ($layers.Count -eq 0) { throw 'Signed installed files are missing.' }
foreach ($layer in $layers) {
    & $signTool.FullName verify /pa /all /tw $layer.FullName
    if ($LASTEXITCODE -ne 0) { throw 'Native signature failed before inventory reseal.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $layer.FullName
    if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate -or
        $signature.SignerCertificate.Thumbprint -ne $identity.sha1) {
        throw 'Signed payload publisher or timestamp differs.'
    }
    $fingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($signature.SignerCertificate.RawData))
    if ($fingerprint -ne $identity.sha256) { throw 'Signed payload certificate differs.' }
}
& python (Join-Path $PSScriptRoot 'cua_signing.py') reseal --root $root --authorization $Authorization --receipt $Receipt --records $Records
if ($LASTEXITCODE -ne 0) { throw 'Signed CUA inventory or input-output binding failed.' }
