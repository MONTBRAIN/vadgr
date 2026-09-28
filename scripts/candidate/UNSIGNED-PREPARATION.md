# Unsigned Windows legal preparation

The manual `unsigned-windows-preparation.yml` workflow produces exact unsigned
Windows observations before package approval exists. Legal reviewers need the
assembled payload and executable hashes to complete the package inventory and
outer-file policies. Requiring that completed approval before these observations
exist creates a cycle. This separate producer supplies the observations only.

It creates no candidate authorization, claim, signature, attestation, installer,
release or publication. Every output is explicitly **unapproved and
nonpublishable**. The candidate workflow and its preflight remain unchanged.

## Source and execution boundary

Dispatch the workflow from `master` with `source_branch` equal to
`feature/0.5.0-distribution` and the exact 40-character `source_sha`. The source
must be the current pushed branch head, in this repository, with successful
required checks bound to the trusted CI workflow and actual jobs. An open
implementation PR is optional; when present, its exact head and base must agree.
Reruns are refused. A new attempt requires a new dispatch and produces new bytes.

Trusted code reads the source as data. It checks the complete Git tree for links,
submodules, unsafe Windows paths and case aliases before materialization. The
build tree contains the exact Git blobs, excluding only the result-only
`E2E/0.5.0/e2e.md`. The source cannot replace the CI workflows used for its checks.
Source admission does not load or execute a feature script or build hook.

Each build materializes the independently reviewed CUA profile wheelhouse with
step-scoped read-only GitHub access. Existing provenance, catalog, lock, wheel
hash, target and profile checks all apply. There is no dependency resolution or
development-lock fallback. The build helper verifies the complete wheelhouse
again offline before Cargo executes feature code.

The two build jobs run on native `windows-latest` x64 and `windows-11-arm` ARM64.
The helper checks both the runner architecture and the native operating-system
architecture. It runs every source test in the full admitted checkout, including
the result-only runbook. An offline check binds that clean checkout to the
admitted commit, complete tree and input digest before any source code executes.
The test output directory is separate from the release output directory.
No test filter or skip replaces this source suite.

Release compilation uses only the separate materialized build tree. The helper
checks that the runbook is absent before source testing and again before release
compilation. It never copies the runbook into that tree, even temporarily.
A source test failure prevents release compilation. The helper then compiles
the daemon and application with
the selected release profile, and assembles the private payload through
`__payload-setup`. It does not launch the application or perform an installation.
Before capture, the native build moves the complete payload to a different
absolute root and removes the assembly root. It runs the private Python version
and imports the pinned CUA command through the bundled bootstrap there. It then
restores the same bytes for observation. A build path that remains in the
Windows runtime therefore fails before the output can become review input.

The bootstrapper DLL is built only when the exact source file
`packaging/legal/TERMS.txt` supplies one explicit version `1.0`. Its compile-time
terms hash binds the original bytes, including line endings. Those bytes remain
a proposal. An absent or unsupported terms version leaves the DLL explicitly
unbuilt, without blocking the daemon and runtime observations. A compiler or
payload error fails the job; it never produces a successful partial observation.

No job has a protected environment, repository secret, write permission or OIDC
permission. Compilation clears both GitHub token variables and refuses known
signing and identity credentials. As with the existing candidate source build,
the hosted action context still has a read-only job token and artifact-upload
capability. This is credential-free compilation, not absolute token isolation.
No upload result grants signing or release authority.

## Independent observations

A fresh Linux job downloads each exact raw artifact from the same run. It runs
only trusted code and treats every downloaded file as data. It rechecks source
admission, the reviewed wheelhouse, installed inventory, profile identity and PE
architecture. It also refuses an embedded Authenticode certificate table in the
daemon, application or bootstrapper. Existing upstream runtime signatures remain
unchanged; this check is not certificate or platform-trust qualification.

The observer records the artifact ID and digest, producing job ID and native
runner labels from GitHub. It then retains:

- `preparation-observation.json`: exact source, tooling, workflow run, profile,
  producer artifact, payload/inventory hashes and every observed file hash.
- `unsigned-inputs/payload/`: the full unsigned payload, including original
  `lib/cua/payload.json` and `lib/cua/installed-inventory.json`.
- `unsigned-inputs/ba-functions.dll` and `proposed-terms/TERMS.txt`, when built.
- `unsigned-inputs/wheelhouse/`: the closed wheels and their reviewed bindings,
  retaining supplied license and notice bytes inside the wheels.
- Cargo metadata and supplied dependency licenses/notices for the daemon and
  bootstrapper. These are reported build inputs, not legal conclusions.
- `source/source-inputs.zip` and `source/source-inventory.json`: exact Git bytes
  and hashes from a fresh source checkout, including Cargo locks, proposed legal
  text, CUA catalogs, policies, installer assets and toolchain inputs.
- `UNAPPROVED-NONPUBLISHABLE.txt`, which states the output's limited purpose.

Final artifact names are `unapproved-windows-preparation-x64` and
`unapproved-windows-preparation-arm64`. Intermediate artifact names include
`-raw-`; they have not passed independent observation. Artifacts expire after
30 days. Retain the exact review inputs before expiration if review continues.
The workflow preserves hidden files because the runtime inventory includes them.

The owner and legal review can use these exact observations to prepare the outer
policies and complete package inventory, notices, SBOM and proposed approvals.
Missing rights, source offers or notice duties remain review work. This producer
does not infer them from a package's declared license. The existing legal bundle
generator still emits a draft. Candidate admission still requires all approved
inputs, protected assent, provenance, claims and signing gates.

## Qualification

Run `python -m pytest scripts/tests/test_unsigned_windows_prep.py -q` for the
source, workflow, path, terms, architecture and inventory refusal cases. These
tests use isolated synthetic fixtures and need no credentials or paid operation.
Run the complete `scripts/tests` suite before handoff. Parse the PowerShell
helper with the native parser, and inspect the workflow with the repository's
workflow checks.

After this tooling reaches `master`, dispatch it against one exact green feature
head. Confirm both native jobs and both fresh observers succeed. Download both
final artifacts, match the recorded run/source/artifact identities, and verify
their retained file hashes. Record failures without changing candidate gates.
The native workflow pass remains `not run` until that dispatch occurs. Unit
tests and a local x64 payload inspection do not prove the hosted ARM64 build.
