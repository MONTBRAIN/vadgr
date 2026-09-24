# Reports come from native verification, never from candidate assertions.
function Get-PolicySignatureReport {
    param([string] $Path, [object] $Policy, [string] $SignTool)
    if ($Policy.trust_class -notin @('publisher-sign', 'vendor-preserve')) { throw 'Unknown native trust class.' }
    $verification = & $SignTool verify /pa /all /tw /v $Path 2>&1
    $verificationExit = $LASTEXITCODE
    if ($verificationExit -ne 0) { throw 'Native verification failed, including warning exits.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) { throw 'Trusted signature and timestamp required.' }
    $certificate = $signature.SignerCertificate
    $fingerprint = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($certificate.RawData)).ToLowerInvariant()
    if ($fingerprint -cne $Policy.certificate_sha256 -or $certificate.Subject -cne $Policy.signer) { throw 'Class-specific certificate identity differs.' }
    $chain = [Security.Cryptography.X509Certificates.X509Chain]::new()
    try {
        # SignTool checks signature and timestamp validity above. This independent
        # chain traversal pins the root without rejecting a valid historical timestamp.
        $chain.ChainPolicy.VerificationFlags = [Security.Cryptography.X509Certificates.X509VerificationFlags]::IgnoreNotTimeValid
        $chain.ChainPolicy.RevocationMode = [Security.Cryptography.X509Certificates.X509RevocationMode]::Online
        if (-not $chain.Build($certificate)) { throw 'Certificate chain verification failed.' }
        $rootCertificate = $chain.ChainElements[$chain.ChainElements.Count - 1].Certificate
        $rootHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($rootCertificate.RawData)).ToLowerInvariant()
        if ($rootHash -cne $Policy.chain_root_sha256) { throw 'Certificate chain root differs.' }
    } finally { $chain.Dispose() }
    if (($verification | Out-String) -notmatch 'Hash of file \(sha256\)' -or
        $Policy.digest_algorithm -cne 'sha256' -or $Policy.timestamp_algorithm -cne 'rfc3161-sha256') { throw 'Signature algorithms differ.' }
    $env:SIGNING_INPUT = (Resolve-Path -LiteralPath $Path).Path
    Invoke-Wrapper 'verify-metadata' | Out-Null
    return @{
        schema = 1; file_sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant();
        trust_class = $Policy.trust_class; signer = $certificate.Subject; certificate_sha256 = $fingerprint;
        chain_root_sha256 = $rootHash; digest_algorithm = 'sha256'; timestamp_algorithm = 'rfc3161-sha256';
        signer_policy_sha256 = $Policy.signer_policy_sha256; legal_approval_sha256 = $Policy.legal_approval_sha256;
        signtool_exit = $verificationExit; authenticode_status = $signature.Status.ToString(); chain_valid = $true; timestamp_valid = $true
    }
}
