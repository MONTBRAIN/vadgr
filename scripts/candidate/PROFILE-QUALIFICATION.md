# Profile candidate boundary

Profile candidates extend schema 2; the released input path is not silently
rewritten. `packaging/cua/profile-inputs.json`, the exact CUA catalog and bundle,
and each selected `profile-locks/<profile>.lock` are unexecuted candidate data.
If trusted master contains a copy, the feature copy must be byte-identical.
Inputs may exist only on the exact same-repository feature source. Trusted
code independently verifies the catalog attestation's subject, master workflow,
issuer, hosted runner, tooling commit and exact run/attempt. GitHub repository,
workflow, jobs, artifact IDs/digests and the producer's committed source descriptor
must agree. The producer tooling commit identifies the workflow; the distinct
product source commit identifies the CUA code it packages. Retained archive
members must match the complete catalog before any wheel is used.

Only the CUA wheel pin may change from the trusted target dependency lock.
Native-wheel manifests, trust roots, verification code and publisher identity
remain trusted-master inputs. A profile catalog cannot authorize a different
dependency, root or publisher.
The mapping contains all eight profiles. A `held` binding permits unpublished
qualification only. A `released` binding also requires the reviewed publication
record and independently verified immutable release asset identities. The
publication record follows the same existing-trusted-copy equality rule. Moving
from held to published bytes does not require changing the adopted signer commit.

The canonical legal proposal and exact helper, outer-file and predecessor
policies may also be feature data. Existing trusted copies still require exact
equality. The source preflight validates their schemas, legal and SBOM hashes,
dependency inventory and trusted legal-generator hash. Artifact validation
rechecks the assembled bytes. Helper preparation binds the exact source tree,
both measured consumer closures, each file's signing class, publisher identity
and exact operation budget. It executes no feature code.

These records are proposals, not owner assent. The trusted workflow emits one
immutable authorization artifact before `candidate-authorize`. That protected
environment must have a direct owner reviewer, allow only master, and prohibit
administrator bypass. The claim code checks the real GitHub approval and
completed protected job for this run. Its one-use claim binds the complete
authorization, including the legal proposal, policy hashes, input bytes and
quota. A changed proposal cannot reuse a claim. Credential jobs consume only
these verified artifacts and trusted code, never a feature checkout.

`VADGR_RELEASE_PROFILE` is a build-only selection derived from the verified
wheelhouse. It is compiled into the executable. It is not a runtime environment
override. The source build cannot fall back when a selected profile is missing.
The payload records schema 3, `release_profile` and
`cua_profile_manifest_sha256`, in addition to schema 2's identities.

## Signed helper transaction

The protected coordinator authorizes one exact input closure per Windows
architecture for both Windows and WSL. It must independently measure both
consumer candidates, verify their shared input bytes, reserve the durable shared
claim and spend the approved quota once. An uncertain vendor outcome remains
spent. It is not retried through the other consumer profile.

`cua_helpers.py` accepts exact policy and signature reports; it cannot approve
policy or perform signing. `publisher-sign` permits only an unsigned PE's
certificate/checksum transformation. `vendor-preserve` keeps exact upstream
bytes and independently verifies the reviewed native signer. Unknown files,
missing rights, wrong native architecture or a SignTool warning fail closed.

After signing, the trusted tooling freezes the deterministic broker ZIP, final
manifest and input/output mapping. The final manifest binds only the prior
claim, never a later authorization or receipt. After immutable output upload,
the coordinator validates the real signer ledger and separately observed
Windows and WSL closures, emits the helper authorization, and attests it.
Each consumer receives its own receipt for those exact bytes.

The retained helper directory contains exactly:

- `pre-signing-claim.json`
- `broker-final-manifest.json`
- `helper-closure-authorization.json`
- `authorization.sigstore.json`
- `input-output.json`
- `publisher-policy.json`
- `signature-reports.json`
- `receipt-windows.json` and `receipt-wsl.json`
- `relay.exe` and `broker.zip`

The last two names are transport wrapper names. Installation uses the exact
package-relative paths in the reviewed input role manifest. The other records
are installed under `lib/cua/managed-helpers/<architecture>/`. The final broker
manifest is also placed beside the broker archive, where CUA verifies it.
Reports use a canonical object from exact member path to verified report; no
filename encoding can alias two members.

## Installed authorization

`cua_signing.py reseal-profile` validates the attested helper output and every
allowed transformation, then reseals the complete private inventory. It emits
`cua-runtime-authorization.json` at the installed product root, outside the
inventory's self-hash domain. A fresh default-branch job attests those exact
bytes as `cua-runtime-authorization.sigstore.json` before package assembly.
The envelope binds the compiled profile/version/generation, final payload and
inventory hashes, helper authorization and final manifest, and exact relay.

The installed parent verifies its pinned offline trust root, candidate workflow
identity, issuer, hosted-runner certificate and attested subject. It checks the
entire runtime again immediately before every launch. The child receives a
bounded canonical authorization over an inherited anonymous read-only pipe.
No owner-selected digest or manifest path is an authority. An installed managed
profile cannot fall back to standalone or unsigned helper bytes.

The shared finalizer qualifies the selected Windows/WSL architecture only.
Other native matrix artifacts remain unsigned development outputs. A Linux or
macOS schema-3 payload without its authenticated installed authorization is not
launchable release output. Its finalizer and native trust checks must complete
before that target can be admitted as final; a successful source build does not
supply them. The unselected Windows/WSL architecture requires its own exact
one-use signing transaction and paired receipts.

## Landing order

Development tests do not authorize signing. Before protected profile work runs,
the coordinator, verifier and signer changes must be reviewed and landed on the
default branch through a separate trusted-tooling bootstrap. Credentialed jobs
must execute only trusted default-branch tooling.

CUA functional qualification uses exact release-equivalent unsigned artifacts
and gates its implementation merge. After that merge, its protected producer
packages and signs the exact merged default-branch commit. Actual reviewed
native build and adoption inputs pin the landed signer and tooling commits.
Complete independent provenance and inventory checks, obtain protected approval
of the exact authorization, then run only the targeted signing, attestation and
adoption assertions that need held bytes. Those trust assertions gate tag and
publication; they are not a second full functional host E2E pass. Publishing
the retained CUA bytes and binding their real publication record precedes final
Vadgr release qualification. Vadgr follows the same lifecycle: functional E2E
gates merge, then protected CD signs the exact merged commit. No bootstrap,
synthetic test or inert signing smoke substitutes for either required lane.

## Tooling regression qualification

The admission repair changes trusted release tooling, not installed runtime
behavior. These offline checks use synthetic, secret-free data. They are not
signed candidates or a product E2E pass.

| Check | Exact command | Required observation |
| --- | --- | --- |
| Feature-held catalog | `python -m pytest scripts/tests/test_cua_profile_admission.py -q` | Separate product/tooling commits pass; changed roots, subjects, runs, branches, source pins, archives and trusted copies fail |
| Legal proposal | `python -m pytest scripts/tests/test_candidate_approval.py -q` | Canonical exact hashes pass; unsafe paths, unknown fields, changed publisher and trusted-copy conflicts fail |
| Protected claim | `python -m pytest scripts/tests/test_candidate_claims.py -q` | Missing owner approval stops before writes; changed legal proposal cannot reuse a claim |
| Workflow boundary | `python -m pytest scripts/tests/test_candidate_workflow.py -q` | Feature checkouts occur only in non-credential data jobs; protected authorization and credential separation remain |

These checks need native Python and the repository's test dependencies. They
need no account, phone, credential, paid operation or owner action. They create
only isolated test fixtures; remove generated test caches after qualification.
