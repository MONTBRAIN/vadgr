[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('x64', 'arm64')]
    [string] $Architecture,

    [Parameter(Mandatory = $true)]
    [string] $Version,

    [Parameter(Mandatory = $true)]
    [string] $PayloadDirectory,

    [Parameter(Mandatory = $true)]
    [string] $TermsRtf,

    [Parameter(Mandatory = $true)]
    [string] $TermsVersion,

    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory,

    [switch] $DevelopmentUnsigned
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Version -ne '0.5.0') {
    throw 'This package source is registered only for version 0.5.0.'
}
if ($TermsVersion -notmatch '^[0-9]+\.[0-9]+$') {
    throw 'TermsVersion must be an approved numeric terms version.'
}

$payload = (Resolve-Path -LiteralPath $PayloadDirectory).Path
$terms = (Resolve-Path -LiteralPath $TermsRtf).Path
$required = @(
    'vadgr.exe',
    'vadgr-app.exe',
    'install-receipt.json',
    'README-OFFLINE.txt',
    'legal\TERMS.txt',
    'legal\PRIVACY-NOTICE.txt',
    'legal\SECURITY-AND-PERMISSIONS.txt',
    'legal\THIRD-PARTY-NOTICES.txt',
    'legal\SUPPORT.txt',
    'legal\UNINSTALL-AND-DATA.txt',
    "sbom\vadgr-$Version.spdx.json"
)
foreach ($relative in $required) {
    $candidate = Join-Path $payload $relative
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Required package input is missing: $relative"
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $payload 'lib\cua') -PathType Container)) {
    throw 'The private CUA payload directory is missing.'
}

$termsPrefix = Get-Content -LiteralPath $terms -Raw
if (-not $termsPrefix.StartsWith('{\rtf')) {
    throw 'The reviewed installer terms must be an RTF document.'
}

$dotnet = Get-Command dotnet -ErrorAction Stop
$sdk = & $dotnet.Source --list-sdks
if (-not $sdk) {
    throw 'A .NET SDK is required to run the pinned WiX v4 build.'
}

$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $output -Force | Out-Null
$projectRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $projectRoot)
$themeFile = Join-Path $projectRoot 'VadgrTheme.xml'
$themeLocalizationFile = Join-Path $projectRoot 'VadgrTheme.wxl'
$generatedPayload = Join-Path $output 'PrivatePayload.wxs'
$python = Get-Command python -ErrorAction Stop
& $python.Source (Join-Path $repoRoot 'scripts\generate_windows_payload_wxs.py') `
    --payload-lib (Join-Path $payload 'lib') --output $generatedPayload
if ($LASTEXITCODE -ne 0) {
    throw 'The deterministic Windows payload authoring step failed.'
}

& $dotnet.Source build (Join-Path $projectRoot 'VadgrMsi.wixproj') `
    --configuration Release `
    --nologo `
    -p:Platform=$Architecture `
    -p:VadgrVersion=$Version `
    -p:PayloadDir=$payload `
    -p:GeneratedPayloadWxs=$generatedPayload `
    -p:DevelopmentUnsigned=$($DevelopmentUnsigned.IsPresent.ToString().ToLowerInvariant()) `
    -p:OutputPath=$output
if ($LASTEXITCODE -ne 0) {
    throw 'The MSI build failed.'
}

$msi = Join-Path $output "Vadgr-$Version-windows-$Architecture.msi"
if (-not (Test-Path -LiteralPath $msi -PathType Leaf)) {
    throw 'The MSI build did not produce the expected artifact.'
}

& $dotnet.Source build (Join-Path $projectRoot 'VadgrBundle.wixproj') `
    --configuration Release `
    --nologo `
    -p:Platform=$Architecture `
    -p:VadgrVersion=$Version `
    -p:MsiPath=$msi `
    -p:TermsRtf=$terms `
    -p:TermsVersion=$TermsVersion `
    -p:ThemeFile=$themeFile `
    -p:ThemeLocalizationFile=$themeLocalizationFile `
    -p:OutputPath=$output
if ($LASTEXITCODE -ne 0) {
    throw 'The Burn bundle build failed.'
}

Write-Output (Join-Path $output "Vadgr-$Version-windows-$Architecture-setup.exe")
