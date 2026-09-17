param([Parameter(Mandatory)][string] $Directory)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$manifest = Get-Content -Raw -LiteralPath (Join-Path $Directory 'release-manifest.json') | ConvertFrom-Json
$identity = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../signing/publisher.json') | ConvertFrom-Json
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/x64/signtool.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw 'Windows SDK signature verifier required.' }
$files = @(Get-ChildItem -LiteralPath $Directory -File | Where-Object Extension -In '.exe','.msi')
if ($files.Count -ne 2) { throw 'Held installer set incomplete.' }
foreach ($file in $files) {
    & $signTool.FullName verify /pa /all /tw $file.FullName
    if ($LASTEXITCODE -ne 0) { throw 'Held installer signature refused.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate -or $signature.SignerCertificate.Thumbprint -ne $identity.sha1) {
        throw 'Held installer publisher or timestamp refused.'
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $fingerprint = ([BitConverter]::ToString($sha.ComputeHash($signature.SignerCertificate.RawData))).Replace('-', '') }
    finally { $sha.Dispose() }
    if ($fingerprint -ne $identity.sha256) { throw 'Held publisher certificate differs.' }
}
if ($manifest.artifacts.Count -ne 1 -or $manifest.artifacts[0].kind -ne 'burn') { throw 'Windows-only manifest expected.' }
$setup = Join-Path $Directory $manifest.artifacts[0].name
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $setup).Hash.ToLowerInvariant() -ne $manifest.artifacts[0].sha256) {
    throw 'Held setup and release manifest differ.'
}
Write-Output 'Held Windows installers independently verified without executing them.'
