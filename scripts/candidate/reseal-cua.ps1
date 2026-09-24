param(
    [Parameter(Mandatory)][string] $InputDirectory,
    [Parameter(Mandatory)][string] $Authorization,
    [Parameter(Mandatory)][string] $Receipt,
    [Parameter(Mandatory)][string] $Records,
    [Parameter(Mandatory)][string] $HelperRecords
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
    if ([Environment]::GetEnvironmentVariable($name)) { throw 'Inventory reseal must have no vendor credentials.' }
}
$root = (Resolve-Path -LiteralPath $InputDirectory).Path
# Native reports were measured by the class-specific verifier; the resealer
# validates their exact transforms and the separately attested helper closure.
& python (Join-Path $PSScriptRoot 'cua_signing.py') reseal-profile --root $root --authorization $Authorization --receipt $Receipt --records $Records --helper-records $HelperRecords
if ($LASTEXITCODE -ne 0) { throw 'Signed CUA inventory or input-output binding failed.' }
