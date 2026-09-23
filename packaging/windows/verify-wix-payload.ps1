[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('msi', 'bundle')][string] $Kind,
    [Parameter(Mandatory)][ValidateSet('x64', 'arm64')][string] $Architecture,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# WiX 7 supplies signed native code. Preserve the upstream signature instead of
# spending a publisher-signing operation or silently embedding an unsigned BA.
$name = if ($Kind -eq 'bundle') { 'wixstdba.exe' } else { 'utilca.dll' }
$project = if ($Kind -eq 'bundle') { 'VadgrBundle' } else { 'VadgrMsi' }
$suffix = if ($Kind -eq 'bundle') { '' } else { '-neutral' }
$tracking = Join-Path $PSScriptRoot "obj/$Architecture/Release/$project.wixproj.BindTracking$suffix.txt"
$paths = @(Get-Content -LiteralPath $tracking | ForEach-Object {
    $parts = $_ -split "`t", 2
    if ($parts.Count -eq 2 -and $parts[0] -eq 'Intermediate' -and
        [IO.Path]::GetFileName($parts[1]) -match ('^' + [regex]::Escape($name) + '(-[0-9]+)?$')) {
        $parts[1]
    }
})
if ($paths.Count -ne 1) { throw 'The expected WiX native payload is missing or duplicated.' }
$bytes = [IO.File]::ReadAllBytes($paths[0])
if ($bytes.Length -lt 64 -or $bytes[0] -ne 77 -or $bytes[1] -ne 90) { throw 'The WiX PE header is invalid.' }
$offset = [BitConverter]::ToUInt32($bytes, 60)
if ($offset -gt ($bytes.Length - 6) -or [BitConverter]::ToUInt32($bytes, $offset) -ne 17744) {
    throw 'The WiX PE signature is invalid.'
}
$machine = [BitConverter]::ToUInt16($bytes, $offset + 4)
$expected = if ($Architecture -eq 'x64') { 34404 } else { 43620 }
if ($machine -ne $expected) { throw 'The WiX native payload has the wrong architecture.' }
$sig = Get-AuthenticodeSignature -LiteralPath $paths[0]
if ($sig.Status -ne 'Valid' -or -not $sig.TimeStamperCertificate -or
    $sig.SignerCertificate.Subject -ne 'CN=FireGiant, O=FireGiant, L=San Diego, S=California, C=US') {
    throw 'The WiX upstream publisher signature or timestamp is invalid.'
}
$native = if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'Arm64') { 'arm64' } else { 'x64' }
$tool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/$native/signtool.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $tool) { throw 'Windows SDK SignTool is required for the WiX payload.' }
$verification = & $tool.FullName verify /pa /all /tw $paths[0] 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Independent WiX signature verification failed.' }
@{
    schema = 1; wix_version = '7.0.0'; name = $name; architecture = $Architecture;
    size = $bytes.Length; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $paths[0]).Hash.ToLowerInvariant();
    status = 'valid'; publisher = 'FireGiant'; timestamp = $true
} | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath (Join-Path $OutputDirectory "wix-vendor-$Kind.json")
Write-Output "Verified WiX native payload: $name ($Architecture)."
