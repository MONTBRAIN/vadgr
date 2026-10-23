# Held Windows candidate tools

[Unsigned Windows legal preparation](UNSIGNED-PREPARATION.md) supplies exact
unapproved x64 and native ARM64 observations before package approval. Its separate
default-branch workflow has no signing or approval authority. Candidate preflight
still requires the complete reviewed inputs described below.

The manual candidate workflow runs only from the default branch. It builds the
exact merged protected `master` commit without signing credentials and validates
the uploaded bytes independently. An open implementation branch cannot become a
production signing subject. Product source does not supply signing scripts or
WiX projects to the protected signer.

CI also runs on pushes to `feature/0.5.0-distribution` for release-equivalent
unsigned functional qualification. Those runs never satisfy the production
candidate gate. The protected candidate requires successful post-merge `push`
checks on the exact `master` commit. This adds runner use, not secret access.

The authorization environment approves the exact artifact and quota. Before that
approval, the ordinary workflow token qualifies both immutable claim namespaces.
After approval, the same protected job inspects their complete ruleset, creates
both durable claims with the ordinary token, then repeats the full inspection.
The Windows signing environment then approves one signing attempt. Failed or
uncertain attempts stay spent. Recovery needs a reconciled quota and a new
explicit authorization.

Ruleset `23578357` must cover exactly `refs/tags/signing-claims/**` and
`refs/tags/cua-signing-claims/**`, with update and deletion protection, no
exclusions, and an explicitly empty bypass list. Ordinary-token probes prove
competing creation and rule-denied update/deletion for both namespaces. Missing
hidden fields are not treated as proof that the bypass list is empty.

The protected `candidate-authorize` environment supplies `RULESET_INSPECT_TOKEN`
only to the inspection command. This separate, repository-scoped credential
needs ruleset-write visibility, currently the fine-grained `Administration:
write` permission. It needs no contents-write permission. Its client allows only
the exact ruleset GET endpoints and refuses reuse of `GH_TOKEN`. This limits the
client, not the administrative credential's underlying capability. Keep the
credential short-lived and outside source builds, signers, and job-wide variables.

The immutable claim artifact contains both exact claim receipts and the full
pre/post inspection witness. Signers verify its producer and digest, the approved
run and authorization, both exact refs and tag objects, and the current visible
policy projection. Viewer-dependent fields do not enter the policy digest.
Repository administrators and GitHub remain trusted. Separate API calls cannot
make policy inspection atomic with signing; the post-inspection proves no bypass
actor existed at that inspection, not that an administrator cannot later change
the rules. An uncertain claim creation is never retried or deleted.

`build-windows.ps1` runs without signing or write credentials on its build runner.
It verifies the exact complete source checkout against the preflight record and
runs source tests there. Release compilation uses a separate materialized tree
that excludes the result-only runbook. The two trees cannot contain each other.
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
every wheel again offline before executing feature code. Read-only GitHub access
can still exist in the hosted runner's action context; this is not absolute
token isolation. Signing and write credentials remain on separate protected
runners, which consume product artifacts only as data. No job-scoped GitHub
token is restored to later upload or cleanup steps. Missing or partial
inputs never select a development lock. These source gates are not signed
installation qualification.

The candidate workflow applies the same preparation and offline verification to
its seven additional native builds. Both Windows architecture calls receive
the prepared wheelhouse, complete test checkout and exact preflight record;
Unix builds receive the wheelhouse as their fourth argument. These additional
jobs also run from trusted default-branch workflow code. They do not extend the
reviewed Windows-only signing producer.

Common clean-install CI uses `prepare_cua_build.py` before compilation.
Development mode requires explicit permission and no reviewed wheel inputs.
Once any reviewed input exists, the complete selected closure must satisfy the
trusted admission rules. Schema-2 inputs match the default branch; held profile
inputs use the independent provenance and protected-authorization boundary in
[Profile qualification](PROFILE-QUALIFICATION.md). Missing inputs cannot fall
back to the development lock.

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

For schema-2 candidates, the default branch must contain the reviewed
`candidate-legal-approval.json` under `packaging/`, with exact legal, inventory, generator and
SBOM hashes. The candidate source must carry approved package inputs, the public
root and the matching manifest schema. Missing approval is a hard refusal, not
permission to sign fixture or unsigned release bytes.

Held profile candidates carry the canonical legal proposal on the exact merged
source. Trusted tooling binds it into the immutable authorization artifact;
direct owner approval in the protected environment supplies assent. Product
source cannot change trusted code, roots, publisher identity or an existing
trusted copy. No proposal field grants signing permission by itself.

Protected `candidate-authorize` and `candidate-windows` approvals, successful
claim qualification, the native certificate and available signing quota still
gate the producer. These checks have not been relaxed by keyless attestation.
The attested Windows output explicitly has single-target qualification scope.
This bootstrap adds no build path for other operating systems. A complete
distribution still requires every target's native signing, integrity and
installation gates. There is no general-purpose upload-and-attest endpoint.

See [keyless bootstrap qualification](KEYLESS-QUALIFICATION.md) for the bounded
acceptance checks and the unclaimed live signing boundary.
