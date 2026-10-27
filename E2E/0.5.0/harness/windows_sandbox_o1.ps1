# Run the O1 offline lifecycle in a disposable Windows Sandbox snapshot.
#
# O1 needs an isolated snapshot whose external network is already unavailable,
# and it forbids changing the host firewall, DNS, routes or VPN. A Windows
# Sandbox session configured with no network adapter is exactly that: the guest
# has no route to anything, the host keeps every setting it had, and the whole
# snapshot is discarded when the window closes.
#
# This script stays on the host. It proves the feature is available, assembles
# the one folder the snapshot can see, writes the configuration, starts the
# session and waits for the record the guest writes back.
#
# Windows Sandbox needs the optional feature `Containers-DisposableClientVM`,
# which an administrator enables once and which needs a restart:
#
#   DISM /Online /Enable-Feature /FeatureName:Containers-DisposableClientVM /All
#
# That is an elevated prompt plus a restart, so it belongs to the owner. This
# script refuses rather than asking for elevation itself.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Vehicle,
    [Parameter(Mandatory)][string] $WorkRoot,
    [int] $TimeoutMinutes = 90
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$sandbox = Join-Path $env:SystemRoot 'System32\WindowsSandbox.exe'
if (-not (Test-Path -LiteralPath $sandbox)) {
    $state = (Get-CimInstance Win32_OptionalFeature -Filter "Name='Containers-DisposableClientVM'").InstallState
    throw ("Windows Sandbox is not available on this host (feature install state $state). " +
        'An administrator must enable Containers-DisposableClientVM and restart.')
}
if (-not (Test-Path -LiteralPath $Vehicle -PathType Leaf)) {
    throw "no installation vehicle at $Vehicle"
}

$shared = Join-Path $WorkRoot 'shared'
if (Test-Path -LiteralPath $shared) { Remove-Item -LiteralPath $shared -Recurse -Force }
New-Item -ItemType Directory -Path $shared -Force | Out-Null
Copy-Item -LiteralPath $Vehicle -Destination (Join-Path $shared 'Vadgr-0.5.0-windows-x64-setup.exe')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'windows_sandbox_o1_inside.ps1') -Destination $shared
Write-Output ('vehicle sha256 ' + (Get-FileHash -Algorithm SHA256 -LiteralPath $Vehicle).Hash.ToLowerInvariant())

# The guest sees this one folder and nothing else of the host. No owner profile,
# no credential file and no source tree is mapped.
$configuration = @"
<Configuration>
  <Networking>Disable</Networking>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <PrinterRedirection>Disable</PrinterRedirection>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <MemoryInMB>8192</MemoryInMB>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$shared</HostFolder>
      <SandboxFolder>C:\o1</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\o1\windows_sandbox_o1_inside.ps1</Command>
  </LogonCommand>
</Configuration>
"@
$configurationPath = Join-Path $WorkRoot 'o1.wsb'
Set-Content -LiteralPath $configurationPath -Value $configuration -Encoding utf8
Write-Output "configuration $configurationPath"

$done = Join-Path $shared 'o1-done.txt'
$record = Join-Path $shared 'o1-record.json'
Start-Process -FilePath $sandbox -ArgumentList @($configurationPath) | Out-Null
Write-Output 'the snapshot is starting; the guest drives the lifecycle from its logon command'

$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$lastCount = -1
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $done) { break }
    if (Test-Path -LiteralPath $record) {
        try {
            $current = (Get-Content -Raw -LiteralPath $record | ConvertFrom-Json).steps.Count
            if ($current -ne $lastCount) {
                Write-Output "  $current steps recorded"
                $lastCount = $current
            }
        }
        catch { }
    }
    Start-Sleep -Seconds 10
}
if (-not (Test-Path -LiteralPath $done)) {
    throw "the guest did not finish within $TimeoutMinutes minutes; the partial record is $record"
}

$result = Get-Content -Raw -LiteralPath $record | ConvertFrom-Json
foreach ($step in $result.steps) {
    "{0,-8} {1}" -f $step.result.ToUpperInvariant(), $step.name | Write-Output
}
$failed = @($result.steps | Where-Object { $_.result -eq 'fail' }).Count
Write-Output "steps $($result.steps.Count), failing $failed"
Write-Output "record $record"
if ($failed -ne 0) { throw "the O1 lifecycle recorded $failed failing steps" }
Write-Output 'O1 LIFECYCLE PASSED IN AN OFFLINE SNAPSHOT'
