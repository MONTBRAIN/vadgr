# Held Windows candidate tools

The manual candidate workflow runs only from the default branch. It builds an
exact pushed source commit without signing credentials and validates the uploaded
bytes independently. The source branch does not supply signing scripts or WiX
projects to the protected signer.

CI also runs on pushes to `feature/0.5.0-distribution`, so that exact source
commit can earn required checks before a pull request exists. Other feature
branches retain the pull-request trigger. This adds runner use, not secret access.

The authorization environment approves the exact artifact and quota. A separate
job consumes that authorization with an immutable Git claim. The Windows signing
environment then approves one signing attempt. Failed or uncertain attempts stay
spent. Recovery needs a reconciled quota and a new explicit authorization.

`build-windows.ps1` runs only on a secret-free source-build runner.
`package-windows.ps1` reads compiled payloads as data and uses trusted WiX
authoring. It never compiles or executes a candidate DLL.
`hold-windows.ps1` verifies the final signatures and writes the held inventory.
`cua_signing.py` preserves the authorized private-runtime metadata and records
the exact input/output identity of every installed file. The signer verifies
each input against authorization immediately before its paid operation.
`reseal-cua.ps1` independently verifies every signed PE file without credentials,
then rebuilds the final inventory before MSI packaging. The wheel and target-lock
hashes never change during signing. Non-native file changes are refused.
`record.py` extracts one bounded JSON record without extracting archive paths.

`read_held.py` checks the exact held ZIP, its file hashes and producing run.
`validate_manifest.py` then checks the default-branch workflow identity, exact
authorization, reviewed legal and SBOM bytes, and every release manifest field.
Fresh native verification follows before a separate credential-free job attests
the single `release-manifest.json` subject using SLSA provenance v1. The manifest
contains `legal_hashes`, `sbom_hashes` and `cua_hashes` maps keyed by relative
`legal/...`, `sbom/...` and `cua/...` paths. The terms digest must equal
`legal/TERMS.txt`. The CUA records bind both metadata generations and the complete
input/output mapping. Runtime file checks use the final signed inventory.

The trusted workflow materializes each reviewed wheelhouse in a separate step
with read-only GitHub access. Compilation receives only its directory, with both
GitHub token variables cleared. The build helpers refuse credentials and verify
every wheel again offline before executing feature code. Missing or partial
inputs never select a development lock. These source gates are not signed
installation qualification.

The public Sigstore root snapshot in `packaging/release-trusted-root.jsonl` was
obtained using `gh attestation trusted-root` on 2026-09-17. It excludes GitHub's
private-instance root. Its SHA-256 is pinned in `candidate_policy.py`; candidate
source cannot substitute another root. Root rotation is a reviewed tooling and
verifier change, not a workflow input. No owner manifest private key is needed.

The downloadable `held-windows-attested` artifact includes the exact native
installer, manifest, and `release-manifest.json.bundle.jsonl`. The workflow
verifies the bundle using the pinned root, GitHub issuer, this repository's
`candidate.yml` on `refs/heads/master`, and a GitHub-hosted runner constraint.
No online trust-root lookup is needed for that verification.

The output remains an unpublished Windows candidate, not an installation-test
pass. Native installer tests remain required. This workflow creates no release
and does not change any existing tag or environment protections.

## Fail-closed prerequisites

The default branch must contain the reviewed `candidate-legal-approval.json`
under `packaging/`, with exact per-architecture legal, inventory, generator and
SBOM hashes. The candidate source must carry approved package inputs, the public
root and the matching manifest schema. Missing approval is a hard refusal, not
permission to sign fixture or unsigned release bytes.

Protected `candidate-authorize` and `candidate-windows` approvals, successful
claim qualification, the native certificate and available signing quota still
gate the producer. These checks have not been relaxed by keyless attestation.
The selected Windows target and seven additional native jobs build the exact
eight-target matrix. The additional outputs are unsigned development packages,
not final release artifacts. The attested Windows output explicitly has
single-target qualification scope. A complete distribution still requires every
target's native signing, integrity and installation gates. There is no
general-purpose upload-and-attest endpoint.

See [keyless bootstrap qualification](KEYLESS-QUALIFICATION.md) for the bounded
acceptance checks and the unclaimed live signing boundary.
