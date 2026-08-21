# What a vadgr binary may import on Windows: only libraries Windows itself
# ships. vcruntime140.dll must never appear; it belongs to the Visual C++
# redistributable, which is not part of Windows, and a binary that imports it
# fails to start on a machine that never installed it. The C runtime is linked
# in instead (-C target-feature=+crt-static) by the installer, by
# `vadgr update` and by CI alike, and this one list is the net under all of
# them: two copies of it would drift, and the copy that drifted would be the
# one that let the regression through.
#
# Usage, from a machine with Visual Studio's dumpbin:
#   .\scripts\check_windows_imports.ps1 <exe> [<exe> ...]
param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]]$Executables
)

$ErrorActionPreference = 'Stop'

$dumpbin = Get-ChildItem "C:\Program Files*\Microsoft Visual Studio\*\*\VC\Tools\MSVC\*\bin\Hostx64\x64\dumpbin.exe" |
    Select-Object -First 1
if (-not $dumpbin) { throw "dumpbin not found on this machine" }

# Every name here ships with Windows.
$guaranteed = @('kernel32.dll','advapi32.dll','ntdll.dll','ws2_32.dll','user32.dll',
                'bcrypt.dll','bcryptprimitives.dll','crypt32.dll','secur32.dll',
                'userenv.dll','shell32.dll','ole32.dll','oleaut32.dll','combase.dll',
                'powrprof.dll','psapi.dll','ncrypt.dll','ntoskrnl.exe','rpcrt4.dll',
                'iphlpapi.dll','shlwapi.dll','version.dll','winmm.dll')

foreach ($exe in $Executables) {
    if (-not (Test-Path $exe)) { throw "no binary at $exe" }
    $imports = & $dumpbin.FullName /dependents $exe |
        Select-String -Pattern '^\s+(\S+\.(dll|exe))$' |
        ForEach-Object { $_.Matches[0].Groups[1].Value.ToLower() } |
        Sort-Object -Unique
    Write-Host "${exe} imports:"
    $imports | ForEach-Object { Write-Host "  $_" }
    # A check that read nothing is not a check. This one inspected the wrong
    # path once and passed because the list was empty.
    if ($imports.Count -lt 3) { throw "read $($imports.Count) imports from $exe, which cannot be right" }
    foreach ($dll in $imports) {
        if ($guaranteed -notcontains $dll -and $dll -notlike 'api-ms-win-*') {
            throw "$exe imports $dll, which Windows does not guarantee"
        }
    }
}
Write-Host "every import is one Windows ships"
