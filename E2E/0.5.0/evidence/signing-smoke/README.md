# Signing probe record

The inspect-only service call and one-file signing test succeeded.
This directory existed before S1. Independent certificate comparison completed
after the owner restored the portal session. S1 and S2 passed.

## Attempt 1: setup failure

Actions run [35160875240](https://github.com/MONTBRAIN/vadgr/actions/runs/35160875240)
tested commit `ba2474f`. The Java setup action rejected `17.0.20.1+1` as invalid
SemVer syntax. The job failed before the credential-bearing inspection step.
S1 did not pass. No SSL.com authentication or signing was attempted.

## Attempt 2: inspection and independent identity comparison passed

Actions run [35161663373](https://github.com/MONTBRAIN/vadgr/actions/runs/35161663373)
tested exact commit `c160b5f94f891e450477658f29fa8b8344e7604d` on native Windows.
The job and each step concluded `success`. The correction used the published
Temurin `17.0.20+8` release. Setup, the dummy credential test and the live
inspect-only step passed.

The following public certificate lines are copied from the inspect step's
output. The replacement characters in the subject are present in the Actions
log; this record does not guess the missing characters.

```text
Public certificate subject: CN=Victor Santiago Monta�o Diaz,O=Victor Santiago Monta�o Diaz,L=Pasto,ST=Nari�o,C=CO
Public certificate issuer: CN=SSL.com Code Signing Intermediate CA RSA R1,O=SSL Corp,L=Houston,ST=Texas,C=US
Public certificate validity: 2026-09-16T19:11:10Z to 2027-09-16T19:11:10Z
Public certificate SHA256: 2DBA70DB8174B6FAB9002ED906C0076E5321C5BE82C9B4B6C1775456FEF90D22
Public certificate SHA1: 57C1C20806BD6DD3ED5099237A1A62192FF624D2
Public certificate inspection complete. Signatures requested: 0.
```

The portal session initially expired, so this attempt was first recorded as
partial. After the owner logged in again, the operator downloaded the public
DER certificate independently through the issued certificate's portal entry.
The response was HTTP 200 with 1,692 bytes and DER prefix `30820698`. Its
SHA-256 was
`2DBA70DB8174B6FAB9002ED906C0076E5321C5BE82C9B4B6C1775456FEF90D22`,
which exactly matches the inspection result. This completes S1's independent
oracle. No private key, enrollment QR, account credential or OTP was accessed
for that comparison.

S1 passed. This proves certificate discovery and independently matched public
identity. The following separately approved run proves signing acceptance.

## Attempt 3: one-file signing and independent Windows verification passed

Actions run [35168877860](https://github.com/MONTBRAIN/vadgr/actions/runs/35168877860)
tested exact commit `75c70d1307e969dc5541edd74f68322d29e3b07e` on native Windows.
The job concluded `success` on 2026-09-17 UTC after protected environment
approval. The vendor signing command returned zero without a retry. Windows
SignTool independently verified the file; the PowerShell verifier checked
trusted signature status, timestamp presence and the pinned certificate hash.

Public output copied from the signing step:

```text
Vendor signing exit code: 0. No retry performed.
Verified public publisher: CN=Victor Santiago Montaño Diaz, O=Victor Santiago Montaño Diaz, L=Pasto, S=Nariño, C=CO
Verified public certificate SHA256: 2DBA70DB8174B6FAB9002ED906C0076E5321C5BE82C9B4B6C1775456FEF90D22
Verified public certificate SHA1: 57C1C20806BD6DD3ED5099237A1A62192FF624D2
Verified timestamp authority: CN=SSL.com Timestamping Unit 2025 E1, O=SSL Corp, L=Houston, S=Texas, C=US
Signed sample SHA256: D0D009F0140F7AEF2F649F1022F705D4A66B610665A4082D21AF640F566A69D0
One-file signing probe verified. No release created; no artifact uploaded.
```

S2 passed. One inert EXE was signed and timestamped. This confirms unattended
CodeSignTool signing with this issued certificate, not CKA compatibility,
installer acceptance or operating-system reputation. No production release
workflow changed. No signed binary or credential-bearing artifact was uploaded.

Cleanup: the temporary signing branch allowance was removed from
`release-windows`. A read-only policy check returned only the `v*` tag rule.
The smoke branch can no longer obtain this environment's credentials.

## Recording boundaries

Record the exact tested commit, Actions run URL, job conclusion and public
certificate verification facts at each cell boundary. Add only sanitized
public results. Do not add credentials, credential identifiers, authentication
responses, vendor debug logs, process environments or signed binaries.

The local dummy checks do not establish service acceptance or a valid signature.
