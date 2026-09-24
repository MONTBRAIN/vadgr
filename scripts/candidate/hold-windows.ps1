[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('x64', 'arm64')][string] $Architecture,
    [Parameter(Mandatory)][string] $InputDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][string] $Authorization
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
    if ([Environment]::GetEnvironmentVariable($name)) { throw 'Final verification must have no vendor credentials.' }
}
$approved = Get-Content -Raw -LiteralPath $Authorization | ConvertFrom-Json
$identity = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../signing/publisher.json') | ConvertFrom-Json
$inputRoot = (Resolve-Path -LiteralPath $InputDirectory).Path
$output = (Resolve-Path -LiteralPath $OutputDirectory).Path
$held = Join-Path $PWD 'held'
if (Test-Path -LiteralPath $held) { throw 'Held output must not exist.' }
New-Item -ItemType Directory -Path $held | Out-Null
$native = if ($Architecture -eq 'arm64') { 'arm64' } else { 'x64' }
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/$native/signtool.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw 'Windows SDK SignTool is required.' }
$layers = @(Get-ChildItem (Join-Path $inputRoot 'payload') -Recurse -File | Where-Object Extension -In '.exe','.dll','.pyd')
$layers += Get-Item -LiteralPath (Join-Path $inputRoot 'ba-functions.dll')
$layers += Get-Item -LiteralPath (Join-Path $output "Vadgr-0.5.0-windows-$Architecture.msi"), (Join-Path $output "Vadgr-0.5.0-windows-$Architecture-setup.exe"), (Join-Path $output 'burn-engine.exe')
if ($layers.Count -ne $approved.budget) { throw 'Final layer count differs from approval.' }
$reports = @()
foreach ($layer in $layers) {
    & $signTool.FullName verify /pa /all /tw $layer.FullName
    if ($LASTEXITCODE -ne 0) { throw 'Held layer signature verification failed.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $layer.FullName
    if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) {
        throw 'Held layer has no valid timestamped signature.'
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $fingerprint = ([BitConverter]::ToString($sha.ComputeHash($signature.SignerCertificate.RawData))).Replace('-', '') }
    finally { $sha.Dispose() }
    if ($fingerprint -ne $identity.sha256 -or $signature.SignerCertificate.Thumbprint -ne $identity.sha1) {
        throw 'Held layer has the wrong publisher.'
    }
    $reports += @{ name = $layer.Name; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $layer.FullName).Hash.ToLowerInvariant(); certificate_sha256 = $fingerprint; status = 'valid' }
}
Copy-Item -LiteralPath (Join-Path $output "Vadgr-0.5.0-windows-$Architecture.msi"), (Join-Path $output "Vadgr-0.5.0-windows-$Architecture-setup.exe") -Destination $held
Copy-Item -LiteralPath (Join-Path $inputRoot 'payload/legal'), (Join-Path $inputRoot 'payload/sbom') -Destination $held -Recurse
Copy-Item -LiteralPath $Authorization -Destination (Join-Path $held 'authorization.json')
Copy-Item -LiteralPath (Join-Path $output 'wix-vendor-msi.json'), (Join-Path $output 'wix-vendor-bundle.json') -Destination $held
$reports | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 -LiteralPath (Join-Path $held 'signature-verification.json')
$setup = Get-Item -LiteralPath (Join-Path $held "Vadgr-0.5.0-windows-$Architecture-setup.exe")
$target = if ($Architecture -eq 'x64') { 'windows-x86_64' } else { 'windows-aarch64' }
$legalHashes = @{}
$sbomHashes = @{}
foreach ($path in Get-ChildItem (Join-Path $held 'legal') -File -Recurse) {
    $legalHashes[[IO.Path]::GetRelativePath($held, $path.FullName).Replace('\', '/')] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path.FullName).Hash.ToLowerInvariant()
}
foreach ($path in Get-ChildItem (Join-Path $held 'sbom') -File -Recurse) {
    $sbomHashes[[IO.Path]::GetRelativePath($held, $path.FullName).Replace('\', '/')] = (Get-FileHash -Algorithm SHA256 -LiteralPath $path.FullName).Hash.ToLowerInvariant()
}
@{
    schema = 1; product = 'vadgr'; version = '0.5.0'; release_sequence = 500; tag = 'v0.5.0';
    source_commit = $approved.source_sha; terms_version = '1.0';
    terms_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $held 'legal/TERMS.txt')).Hash.ToLowerInvariant();
    legal_hashes = $legalHashes; sbom_hashes = $sbomHashes;
    cua_version = $approved.cua_version; python_version = $approved.python_version;
    artifacts = @(@{ name = $setup.Name; target = $target; kind = 'burn'; size = $setup.Length;
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $setup.FullName).Hash.ToLowerInvariant(); native_signature = 'authenticode' })
} | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 -LiteralPath (Join-Path $held 'release-manifest.json')
$files = @(Get-ChildItem $held -Recurse -File | ForEach-Object {
    @{ name = [IO.Path]::GetRelativePath($held, $_.FullName).Replace('\', '/'); size = $_.Length; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
})
@{
    schema = 1; product = 'vadgr'; version = '0.5.0'; target = "windows-$Architecture";
    source_commit = $approved.source_sha; source_tree = $approved.source_tree;
    trusted_tooling_commit = $approved.trusted_sha; input_digest = $approved.input_digest;
    candidate_id = $approved.candidate_id; run_id = $approved.run_id; run_attempt = $approved.run_attempt;
    cua_inputs = $approved.cua_inputs; pre_signing_cua_payload = $approved.cua_payload;
    status = 'held-unpublished'; scope = 'single-target-qualification'; complete_distribution = $false; artifacts = $files
} | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 -LiteralPath (Join-Path $held 'candidate-manifest.json')
Write-Output 'Verified signed bytes held without publication. Keyless manifest attestation and native installation tests remain required.'
