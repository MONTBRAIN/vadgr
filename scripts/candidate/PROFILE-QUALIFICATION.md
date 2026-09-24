# Profile candidate boundary

Profile candidates extend schema 2; the released input path is not silently
rewritten. `packaging/cua/profile-inputs.json`, the exact CUA catalog and bundle,
and each selected `profile-locks/<profile>.lock` must match trusted master.
The mapping contains all eight profiles. A `held` binding permits unpublished
qualification only. A `released` binding also requires the reviewed publication
record and immutable release asset identities.

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
default branch through a separate trusted-tooling bootstrap. Current schema-2
tooling cannot run feature-supplied schema-3 policy with credentials.

CUA's development qualification precedes its implementation PR and merge. Its
trusted producer then needs actual reviewed native build/adoption inputs, pinned
to the landed signer/tooling commits. Produced held artifacts require a separate
Vadgr input promotion with real catalog, lock, policy and legal hashes. Only then
can the protected paired signing qualification run. Publishing those retained
CUA bytes and promoting their real publication binding precedes final Vadgr
release qualification. The full Vadgr implementation PR still follows a formal
real-target pass; no bootstrap, synthetic test or inert signing smoke substitutes
for that pass.
