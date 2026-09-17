# Signing probe record

The inspect-only service call succeeded. No signature has been requested.
This directory existed before S1. Independent certificate comparison completed
after the owner restored the portal session, so S1 passed. S2 has not run.

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
identity, not signing acceptance. S2 still requires a separate protected job
approval. Its reviewed configuration pins this exact certificate, permits at
most one signature, and publishes nothing.

## Recording boundaries

Record the exact tested commit, Actions run URL, job conclusion and public
certificate verification facts at each cell boundary. Add only sanitized
public results. Do not add credentials, credential identifiers, authentication
responses, vendor debug logs, process environments or signed binaries.

The local dummy checks do not establish service acceptance or a valid signature.
