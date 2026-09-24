param(
    [Parameter(Mandatory)][ValidateSet('prepare', 'sign', 'complete')][string] $Mode,
    [string[]] $Files,
    [int] $Budget = 0,
    [string] $Authorization,
    [string] $Claim,
    [string] $Qualification,
    [string] $PayloadRoot,
    [string] $Receipt,
    [string] $HelperInputs,
    [string] $SharedClaim,
    [string] $HelperOutput,
    [string] $ResumeLedger,
    [string] $Root = (Join-Path $env:RUNNER_TEMP "release-signing-$env:GITHUB_RUN_ID")
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$jarHash = 'CAA356347AA64BA04666545D548DAD87211C9AA960F16DB8797A880A67BA91D1'
$zipHash = '317D429BE3AA12A5F2C1FFDD575EAB0CB0CE5E2408AB0056BCDCAAB29875F73D'
$source = $PSScriptRoot
$jar = Join-Path $Root 'code_sign_tool-1.3.3.jar'
$classes = Join-Path $Root 'classes'
$sharedTool = Join-Path $source '../candidate/cua_shared.py'
. (Join-Path $source 'verify-policy.ps1')

function Assert-Hash([string] $Path, [string] $Expected) {
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Expected) {
        throw 'The pinned signing tool hash does not match.'
    }
}

function Invoke-Wrapper([string] $Operation) {
    # Neither the vendor runtime nor Java option injection can enable secret-bearing diagnostics.
    foreach ($name in @('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $env:SIGNING_LOG_CONFIG = Join-Path $source 'log4j2-off.xml'
    & java '-Dfile.encoding=UTF-8' '-XX:-HeapDumpOnOutOfMemoryError' '-XX:ErrorFile=NUL' '-cp' "$classes;$jar" CodeSignRunner $Operation
    if ($LASTEXITCODE -ne 0) { throw 'The signing operation failed. No retry is permitted.' }
}

if ($Mode -eq 'prepare') {
    if (Test-Path -LiteralPath $Root) { throw 'The isolated signing directory already exists.' }
    New-Item -ItemType Directory -Path $Root | Out-Null
    New-Item -ItemType Directory -Path $classes | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Root 'conf') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Root 'signed') | Out-Null
    $archive = Join-Path $Root 'vendor.zip'
    Invoke-WebRequest -Uri 'https://ssl.com/download/codesigntool-for-windows/' -OutFile $archive
    Assert-Hash $archive $zipHash
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach ($pair in @(
            @('jar/code_sign_tool-1.3.3.jar', $jar),
            @('conf/code_sign_tool.properties', (Join-Path $Root 'conf/code_sign_tool.properties'))
        )) {
            $entry = $zip.GetEntry($pair[0])
            if (-not $entry) { throw 'A pinned vendor package member is missing.' }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $pair[1], $false)
        }
    } finally { $zip.Dispose() }
    Assert-Hash $jar $jarHash
    & javac '-encoding' 'UTF-8' '-proc:none' '-cp' $jar '-d' $classes (Join-Path $source 'CodeSignRunner.java')
    if ($LASTEXITCODE -ne 0) { throw 'The credential-safe launcher did not compile.' }
    Push-Location $Root
    try {
        $env:ES_USERNAME = 'dummy-user-not-a-real-account'
        $env:ES_PASSWORD = 'dummy-password-not-a-real-secret'
        $env:ES_TOTP_SECRET = 'ZHVtbXktc2VlZC1ub3QtYS1yZWFsLXNlY3JldA=='
        $output = Invoke-Wrapper 'self-test' | Out-String
        foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
            if ($output.Contains([Environment]::GetEnvironmentVariable($name))) {
                throw 'Dummy credential appeared in raw launcher output.'
            }
        }
        if ($output.Trim() -ne 'Dummy credential suppression: PASS; vendor missing-file refusal verified.') {
            throw 'Unexpected launcher self-test output.'
        }
        if (Test-Path -LiteralPath (Join-Path $Root 'logs')) { throw 'Vendor file logging was not disabled.' }
        Write-Output $output.Trim()
    } finally {
        foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
        Pop-Location
    }
    if ($Budget -lt 5) { throw 'The approved signature budget is missing.' }
    if (-not $Authorization) { throw 'An exact authorization is required before ledger initialization.' }
    if ($ResumeLedger) {
        Copy-Item -LiteralPath $ResumeLedger -Destination (Join-Path $Root 'ledger.json')
    } else {
        & python $sharedTool ledger-init --authorization $Authorization --ledger (Join-Path $Root 'ledger.json')
        if ($LASTEXITCODE -ne 0) { throw 'Signer ledger initialization failed.' }
    }
    return
}

if ($env:GITHUB_ACTIONS -ne 'true' -or $env:GITHUB_REPOSITORY -ne 'MONTBRAIN/vadgr' -or
    $env:GITHUB_REF_TYPE -ne 'branch' -or $env:GITHUB_REF -ne 'refs/heads/master' -or
    $env:GITHUB_RUN_ATTEMPT -ne '1') {
    throw 'Signing is restricted to the first attempt of an approved default-branch candidate.'
}
if (-not $Authorization -or -not $Claim -or -not $Qualification) { throw 'The protected authorization and durable claim are required.' }
$policy = Join-Path (Split-Path -Parent $PSScriptRoot) 'candidate_claims.py'
& python $policy verify --authorization $Authorization --qualification $Qualification --claim $Claim
if ($LASTEXITCODE -ne 0) { throw 'The protected signing claim did not verify.' }
$approved = Get-Content -Raw -LiteralPath $Authorization | ConvertFrom-Json
$ledgerPath = Join-Path $Root 'ledger.json'
$ledger = Get-Content -Raw -LiteralPath $ledgerPath | ConvertFrom-Json
if ($ledger.budget -ne $approved.budget) { throw 'The local budget differs from the protected authorization.' }
if ($Mode -eq 'complete') {
    & python $sharedTool ledger-complete --authorization $Authorization --ledger $ledgerPath
    if ($LASTEXITCODE -ne 0) { throw 'The signature quota contains missing or uncertain operations.' }
    Write-Output "Verified signing attempts: $($ledger.attempts.Count). No retry performed."
    return
}
$transitions = @{}
$beforeFiles = @{}
$reports = @{}
$classPolicy = $null
$unit = 'vehicle'
$claimHash = (Get-FileHash -LiteralPath $Authorization -Algorithm SHA256).Hash.ToLowerInvariant()
if ($HelperInputs) {
    if (-not $SharedClaim -or -not $HelperOutput -or $PayloadRoot -or $Receipt -or $Files -or
        (Test-Path -LiteralPath $HelperOutput)) { throw 'Shared helper signing requires fresh isolated output.' }
    & python $sharedTool verify-claim --authorization $Authorization --qualification $Qualification --helper-inputs $HelperInputs --shared-claim $SharedClaim
    if ($LASTEXITCODE -ne 0) { throw 'The architecture-scoped durable claim did not verify.' }
    Assert-Hash (Join-Path $HelperInputs 'publisher-policy.json') $approved.helper_policy_sha256
    Copy-Item -LiteralPath (Join-Path $HelperInputs 'members') -Destination $HelperOutput -Recurse
    $payloadBoundary = (Resolve-Path -LiteralPath $HelperOutput).Path
    $classPolicy = (Get-Content -Raw -LiteralPath (Join-Path $HelperInputs 'publisher-policy.json') | ConvertFrom-Json).files
    $claimHash = (Get-FileHash -LiteralPath (Join-Path $HelperInputs 'pre-signing-claim.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    $unit = 'shared-helper'
} elseif ($PayloadRoot -or $Receipt) {
    if (-not $PayloadRoot -or -not $Receipt -or (Test-Path -LiteralPath $Receipt) -or $Files) {
        throw 'Installed signing derives its exact file set from the approved class policy.'
    }
    $payloadBoundary = (Resolve-Path -LiteralPath $PayloadRoot).Path
    $classPolicy = $approved.signing_policy.files
    $unit = 'outer'
}
if ($classPolicy) {
    $Files = @()
    foreach ($entry in $classPolicy.PSObject.Properties) {
        $relative = $entry.Name
        $absolute = [IO.Path]::GetFullPath((Join-Path $payloadBoundary $relative))
        if (-not $absolute.StartsWith($payloadBoundary + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
            $relative.Contains('\') -or $relative.Contains('..')) { throw 'Policy input escapes its root.' }
        $cursor = Get-Item -LiteralPath $absolute
        while ($cursor.FullName -ne $payloadBoundary) {
            if ($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked signing input is forbidden.' }
            $cursor = Get-Item -LiteralPath (Split-Path -Parent $cursor.FullName)
        }
        $inputHash = (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash.ToLowerInvariant()
        $size = (Get-Item -LiteralPath $absolute).Length
        if ($inputHash -ne $entry.Value.input_sha256) { throw 'Class-policy input digest differs.' }
        if ($unit -eq 'outer') {
            $authorized = $approved.files.PSObject.Properties[$relative]
            if (-not $authorized -or $authorized.Value.sha256 -ne $inputHash -or $authorized.Value.size -ne $size) {
                throw 'Outer input is absent from exact authorization.'
            }
        }
        $beforeFiles[$relative] = @{ sha256 = $inputHash; size = $size }
        if ($entry.Value.trust_class -eq 'publisher-sign') { $Files += $absolute }
        elseif ($entry.Value.trust_class -notin @('vendor-preserve', 'data') -or
                ($unit -eq 'outer' -and $entry.Value.trust_class -eq 'data')) { throw 'Unknown or misplaced trust class.' }
    }
} elseif (-not $Files -or $Files.Count -ne 1) {
    throw 'Exactly one explicit vehicle layer is required.'
}
$identity = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $source 'publisher.json') | ConvertFrom-Json
$env:EXPECTED_CERT_SHA256 = $identity.sha256
$env:EXPECTED_CERT_SHA1 = $identity.sha1
$env:EXPECTED_CERT_SUBJECT = $identity.subject
Assert-Hash $jar $jarHash
$native = if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'Arm64') { 'arm64' } else { 'x64' }
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/$native/signtool.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw 'Windows SDK SignTool is required before signing.' }

function Reserve-Attempt([string] $Relative, [string] $InputHash) {
    # Persist BEFORE authentication. Uncertain attempts consume the same carried ledger.
    & python $sharedTool ledger-reserve --authorization $Authorization --ledger $ledgerPath --unit $unit --path $Relative --input-sha256 $InputHash --claim-sha256 $claimHash
    if ($LASTEXITCODE -ne 0) { throw 'A duplicate signing attempt or quota overrun was refused.' }
}
try {
    # Preserved signatures are prerequisites, checked before any paid request.
    if ($classPolicy) {
        foreach ($entry in $classPolicy.PSObject.Properties) {
            if ($entry.Value.trust_class -eq 'vendor-preserve') {
                $reports[$entry.Name] = Get-PolicySignatureReport (Join-Path $payloadBoundary $entry.Name) $entry.Value $signTool.FullName
            }
        }
    }
    foreach ($file in $Files) {
        $inputFile = (Resolve-Path -LiteralPath $file).Path
        $relative = [IO.Path]::GetFileName($inputFile)
        $inputHash = (Get-FileHash -LiteralPath $inputFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $selected = $null
        if ($classPolicy) {
            $relative = [IO.Path]::GetRelativePath($payloadBoundary, $inputFile).Replace('\', '/')
            $selected = $classPolicy.PSObject.Properties[$relative].Value
            if ($selected.trust_class -ne 'publisher-sign' -or $selected.input_sha256 -ne $inputHash -or
                $selected.certificate_sha256 -ne $identity.sha256.ToLowerInvariant() -or $selected.signer -ne $identity.subject) {
                throw 'Publisher signing is not permitted for this exact input.'
            }
        } elseif ($relative -notin @("Vadgr-0.5.0-windows-$($approved.architecture).msi", 'burn-engine.exe',
                                    "Vadgr-0.5.0-windows-$($approved.architecture)-final.exe")) {
            throw 'Unapproved vehicle signing layer.'
        }
        if ([IO.Path]::GetExtension($inputFile) -notin @('.exe', '.dll', '.pyd', '.msi')) {
            throw 'The signing input is not a supported release layer.'
        }
        $output = Join-Path $Root ([Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $output | Out-Null
        $env:SIGNING_INPUT = $inputFile
        # The vendor dispatches by suffix; only the temporary basename changes.
        if ([IO.Path]::GetExtension($inputFile) -eq '.pyd') {
            $temporaryInput = Join-Path $output 'python-extension.dll'
            Copy-Item -LiteralPath $inputFile -Destination $temporaryInput
            $env:SIGNING_INPUT = $temporaryInput
        }
        $vendorName = [IO.Path]::GetFileName($env:SIGNING_INPUT)
        $vendorOutput = Join-Path $output 'signed'
        New-Item -ItemType Directory -Path $vendorOutput | Out-Null
        $env:SIGNING_OUTPUT = $vendorOutput
        Reserve-Attempt $relative $inputHash
        Push-Location $Root
        try { Invoke-Wrapper 'sign' } finally { Pop-Location }
        $signed = Join-Path $vendorOutput $vendorName
        if ([IO.Path]::GetExtension($inputFile) -eq '.pyd') {
            $restoredName = Join-Path $vendorOutput ([IO.Path]::GetFileName($inputFile))
            Move-Item -LiteralPath $signed -Destination $restoredName
            $signed = $restoredName
        }
        $env:SIGNING_INPUT = $signed
        Invoke-Wrapper 'verify-metadata'
        $verification = & $signTool.FullName verify /pa /all /tw /v $signed 2>&1
        if ($LASTEXITCODE -ne 0) { throw 'Independent Windows verification failed. No retry permitted.' }
        if (($verification | Out-String) -notmatch 'Hash of file \(sha256\)') { throw 'The file digest algorithm is not SHA256.' }
        $signature = Get-AuthenticodeSignature -LiteralPath $signed
        if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) { throw 'A trusted signature and timestamp are required.' }
        $cert = $signature.SignerCertificate
        $fingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cert.RawData))
        if ($fingerprint -ne $identity.sha256 -or $cert.Thumbprint -ne $identity.sha1) { throw 'The signed layer has the wrong publisher certificate.' }
        if ($selected) { $reports[$relative] = Get-PolicySignatureReport $signed $selected $signTool.FullName }
        Move-Item -LiteralPath $signed -Destination $inputFile -Force
        $outputHash = (Get-FileHash -LiteralPath $inputFile -Algorithm SHA256).Hash.ToLowerInvariant()
        & python $sharedTool ledger-verify --authorization $Authorization --ledger $ledgerPath --unit $unit --path $relative --input-sha256 $inputHash --claim-sha256 $claimHash --output-sha256 $outputHash
        if ($LASTEXITCODE -ne 0) { throw 'The exact reserved operation did not complete.' }
        if ($unit -eq 'outer') {
            $transitions[$relative] = @{ input = $beforeFiles[$relative]; output = @{
                size = (Get-Item -LiteralPath $inputFile).Length; sha256 = $outputHash
            }; trust_class = 'publisher-sign'; signature_report = $reports[$relative] }
        }
        Write-Output "Verified layer: $([IO.Path]::GetFileName($inputFile)); certificate SHA256: $fingerprint"
    }
    if ($classPolicy) {
        foreach ($entry in $classPolicy.PSObject.Properties) {
            if ($entry.Value.trust_class -eq 'publisher-sign') { continue }
            $relative = $entry.Name
            $absolute = Join-Path $payloadBoundary $relative
            if ((Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash.ToLowerInvariant() -ne $beforeFiles[$relative].sha256) {
                throw 'Vendor-preserve or data bytes changed.'
            }
            if ($entry.Value.trust_class -eq 'vendor-preserve') {
                $reports[$relative] = Get-PolicySignatureReport $absolute $entry.Value $signTool.FullName
                if ($unit -eq 'outer') {
                    $transitions[$relative] = @{ input = $beforeFiles[$relative]; output = $beforeFiles[$relative];
                        trust_class = 'vendor-preserve'; signature_report = $reports[$relative] }
                }
            }
        }
        $rawReports = Join-Path $Root "$unit-signature-reports.native.json"
        $reports | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 -LiteralPath $rawReports
        $reportDestination = if ($unit -eq 'shared-helper') { Join-Path $HelperOutput 'signature-reports.json' } else { $Receipt + '.reports.json' }
        & python $sharedTool canonical-reports --input $rawReports --out $reportDestination
        if ($LASTEXITCODE -ne 0) { throw 'Canonical policy reports failed.' }
        if ($unit -eq 'outer') {
            $rawReceipt = Join-Path $Root 'outer-receipt.native.json'
            $transitions | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 -LiteralPath $rawReceipt
            & python $sharedTool canonical-receipt --input $rawReceipt --out $Receipt
            if ($LASTEXITCODE -ne 0) { throw 'Canonical outer receipt failed.' }
        }
    }
} finally {
    foreach ($name in @('ES_USERNAME', 'ES_PASSWORD', 'ES_TOTP_SECRET')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}
