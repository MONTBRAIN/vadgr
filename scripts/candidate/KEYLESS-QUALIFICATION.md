# Keyless bootstrap qualification

This is tooling acceptance, not installed-product E2E. It exercises the trusted
producer's refusal boundary without vendor credentials, production artifacts,
OIDC tokens, or signing requests. No installer is run and no signature quota is
spent. The complete signed-candidate E2E remains required before release.

## Requirements

| Requirement | Cells | Availability check | Cost or mutation | Cleanup |
|---|---|---|---|---|
| WSL Python 3.12 and this exact branch | K1, K2 | `python3 --version`, Git head | None; read-only refusal | None |
| Native Windows Python 3.12 | K3 | `python --version` in PowerShell | None; read-only refusal | None |
| No trusted legal approval file yet | K2, K3 | File absence | No missing input is substituted | None |
| Protected signed candidate | K4 | Actual protected producer run and artifact ID | Signing quota; owner approvals | Retain exact held artifact |

K4 cannot run until approved legal inputs and protected native signing complete.
It is not replaced by an attestation of an unsigned artifact. This bootstrap
can establish only that this absent approval remains fail-closed.

## Cells written before invocation

| Cell | Precondition and setup | Action | Expected observable and independent oracle | Evidence | Cleanup | Result |
|---|---|---|---|---|---|---|
| K1 | No GitHub workflow identity; read-only checkout | Invoke `validate_manifest.py --directory absent-held --architecture x64` | Exit 1, untrusted workflow refusal; no `absent-held` created | Tool output and exit code below | None | Pass: refusal observed |
| K2 | Isolated process env names repository, master, attempt 1; trusted approval absent | Same command | Exit 1, missing reviewed legal approval; no output created and no network tool invoked | Tool output and exit code below | Process env expires | Pass: refusal observed |
| K3 | Native Windows, same source and missing approval; isolated process env | Same command with native Python | Same refusal as K2; no output created | Tool output and exit code below | Process env expires | Pass: refusal observed |
| K4 | Approved real signed held installer from protected candidate job | Download exact held artifact, validate compliance, verify Authenticode, attest manifest, verify offline bundle | Hosted/default workflow identity; single manifest subject; complete final legal and SBOM hash maps; no publication | GitHub run and immutable artifact metadata | Retain held artifact | Blocked: reviewed legal approval absent; not dispatched |

The synthetic test matrix additionally covers changed version, source, release
sequence, terms, CUA pin, extra fields, unsigned claim, wrong target, duplicate
artifacts, byte size/hash changes, legal/SBOM tampering, extra legal files,
wrong repository/ref/run/attempt/tooling SHA, duplicate JSON fields, altered
public trust root, and missing trusted approval. These are not vendor signing
or native installation claims.

No application surface is changed by this bootstrap. Hosted Python CI covers
the parser on Windows, macOS and Linux. K1-K3 cover direct CLI refusal on the
local WSL/native Windows boundary; none changes the daemon's E2E status.

## Direct command observations

K1, WSL Python, exit 1:

```text
REFUSED: untrusted attestation workflow
```

K2, WSL Python, exit 1:

```text
REFUSED: reviewed legal approval is not configured in trusted tooling
```

K3, native Windows Python 3.12, invoked through Windows PowerShell, exit 1:

```text
REFUSED: reviewed legal approval is not configured in trusted tooling
```

Independent filesystem check: `test ! -e absent-held && test ! -e
packaging/candidate-legal-approval.json` exited 0. No directory, attestation,
authorization, signer process or vendor request was created. The function has
no subprocess or network calls; the real command-line entry point reached the
missing-approval refusal before reading a candidate.
