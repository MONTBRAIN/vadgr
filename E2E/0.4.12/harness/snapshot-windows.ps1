param(
    [Parameter(Mandatory = $true)][string]$Label,
    [Parameter(Mandatory = $true)][string]$Output
)

$ErrorActionPreference = 'Stop'

function Hash-Text([string]$Text) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = $algorithm.ComputeHash($bytes)
    } finally {
        $algorithm.Dispose()
    }
    return ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
}

function Hash-FileOrAbsent([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return 'absent' }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Hash-TreeOrAbsent([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return 'absent' }
    $rows = Get-ChildItem -LiteralPath $Path -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName |
        ForEach-Object { $_.FullName }
    return Hash-Text ($rows -join "`n")
}

$pythonRegistry = reg.exe query HKCU\Software\Python /s 2>$null
$network = Get-NetRoute -ErrorAction SilentlyContinue |
    Sort-Object DestinationPrefix, InterfaceIndex |
    Select-Object DestinationPrefix, NextHop, InterfaceIndex |
    ConvertTo-Json -Compress
$selectedEnvironment = @(
    'VIRTUAL_ENV', 'PYTHONHOME', 'PYTHONPATH', 'PIP_CONFIG_FILE', 'UV_CONFIG_FILE'
) | ForEach-Object { "${_}=$([Environment]::GetEnvironmentVariable($_, 'Process'))" }
$profileHash = Hash-FileOrAbsent $PROFILE
$pythonUserHash = Hash-TreeOrAbsent (Join-Path $env:APPDATA 'Python')
$pipCacheHash = Hash-TreeOrAbsent (Join-Path $env:LOCALAPPDATA 'pip\Cache')
$uvCacheHash = Hash-TreeOrAbsent (Join-Path $env:LOCALAPPDATA 'uv\cache')
$pythonEnvironmentHash = Hash-Text ($selectedEnvironment -join [Environment]::NewLine)
$pythonRegistryHash = Hash-Text ($pythonRegistry -join [Environment]::NewLine)
$networkHash = Hash-Text $network

@(
    "label=$Label"
    "profile=$profileHash"
    "python_user=$pythonUserHash"
    "pip_cache=$pipCacheHash"
    "uv_cache=$uvCacheHash"
    "python_env=$pythonEnvironmentHash"
    "python_registry=$pythonRegistryHash"
    "network=$networkHash"
) | Set-Content -LiteralPath $Output -Encoding utf8
