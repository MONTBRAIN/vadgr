[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('msi', 'bundle', 'detach', 'reattach')][string] $Mode,
    [Parameter(Mandatory)][ValidateSet('x64', 'arm64')][string] $Architecture,
    [Parameter(Mandatory)][string] $InputDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
    if ([Environment]::GetEnvironmentVariable($name)) { throw 'Packaging must run without vendor credentials.' }
}
$trusted = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$project = Join-Path $trusted 'packaging/windows'
$inputRoot = (Resolve-Path -LiteralPath $InputDirectory).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
$payload = Join-Path $inputRoot 'payload'
$ba = Join-Path $inputRoot 'ba-functions.dll'
$terms = Join-Path $inputRoot 'TERMS.rtf'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$msi = Join-Path $output "Vadgr-0.5.0-windows-$Architecture.msi"
$bundle = Join-Path $output "Vadgr-0.5.0-windows-$Architecture-setup.exe"
$engine = Join-Path $output 'burn-engine.exe'
$final = Join-Path $output "Vadgr-0.5.0-windows-$Architecture-final.exe"
$generated = Join-Path $output 'PrivatePayload.wxs'
$generatedLegal = Join-Path $output 'LegalPayload.wxs'
$generatedSbom = Join-Path $output 'SbomPayload.wxs'
$common = @('--configuration', 'Release', '--nologo', '-p:ImportDirectoryBuildProps=false',
    '-p:ImportDirectoryBuildTargets=false', '-p:ImportDirectoryPackagesProps=false',
    "-p:Platform=$Architecture", '-p:VadgrVersion=0.5.0', "-p:OutputPath=$output")
Push-Location $trusted
try {
    switch ($Mode) {
        'msi' {
            & python (Join-Path $trusted 'scripts/generate_windows_payload_wxs.py') --payload-lib (Join-Path $payload 'lib') --output $generated
            if ($LASTEXITCODE -ne 0) { throw 'Trusted payload authoring failed.' }
            & python (Join-Path $trusted 'scripts/generate_windows_payload_wxs.py') --payload-lib (Join-Path $payload 'legal') --output $generatedLegal --directory-id LegalFolder --group-id LegalPayload
            if ($LASTEXITCODE -ne 0) { throw 'Trusted legal authoring failed.' }
            & python (Join-Path $trusted 'scripts/generate_windows_payload_wxs.py') --payload-lib (Join-Path $payload 'sbom') --output $generatedSbom --directory-id SbomFolder --group-id SbomPayload
            if ($LASTEXITCODE -ne 0) { throw 'Trusted SBOM authoring failed.' }
            & dotnet build (Join-Path $project 'VadgrMsi.wixproj') @common "-p:PayloadDir=$payload" "-p:GeneratedPayloadWxs=$generated" "-p:GeneratedLegalWxs=$generatedLegal" "-p:GeneratedSbomWxs=$generatedSbom"
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $msi)) { throw 'Trusted MSI packaging failed.' }
            & (Join-Path $project 'verify-wix-payload.ps1') -Kind msi -Architecture $Architecture -OutputDirectory $output
        }
        'bundle' {
            & dotnet build (Join-Path $project 'VadgrBundle.wixproj') @common "-p:MsiPath=$msi" "-p:TermsRtf=$terms" '-p:TermsVersion=1.0' `
                "-p:ThemeFile=$project/VadgrTheme.xml" "-p:ThemeLocalizationFile=$project/VadgrTheme.wxl" "-p:BAFunctionsPath=$ba"
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $bundle)) { throw 'Trusted Burn packaging failed.' }
            & (Join-Path $project 'verify-wix-payload.ps1') -Kind bundle -Architecture $Architecture -OutputDirectory $output
        }
        'detach' {
            & dotnet tool install wix --tool-path (Join-Path $output 'wix') --version 7.0.0
            if ($LASTEXITCODE -ne 0) { throw 'Pinned WiX installation failed.' }
            & "$output/wix/wix.exe" burn detach $bundle -engine $engine
            if ($LASTEXITCODE -ne 0) { throw 'Burn detach failed.' }
        }
        'reattach' {
            & "$output/wix/wix.exe" burn reattach $bundle -engine $engine -o $final
            if ($LASTEXITCODE -ne 0) { throw 'Burn reattach failed.' }
        }
    }
} finally { Pop-Location }
Write-Output "Trusted Windows packaging completed: $Mode. No payload executed."
