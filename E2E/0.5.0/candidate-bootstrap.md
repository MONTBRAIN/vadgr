# Held Windows candidate: bootstrap verification

Status: not run. This check covers the candidate tooling, not an installer pass.
The implementation branch is `feat/trusted-candidate-bootstrap`.
Record the exact pushed commit and the evidence destination before live execution.

## Requirements

| Requirement | Cells | Availability check | Cost and cleanup |
|---|---|---|---|
| WSL and native Windows Python 3.12; Windows PowerShell | B01-B05 | Print executable version and platform without environment values | No paid calls; remove only isolated fixture roots after filing output |
| Java 17 and reviewed CodeSignTool archive | B06 | Verify the pinned archive and JAR hashes | Dummy inputs only; no authentication or quota use |
| Trusted default-branch workflow and exact pushed source | B07-B10 | Verify workflow SHA, source SHA and effective branch rules through GitHub | GitHub-hosted runner allowance; retain immutable artifacts |
| Protected claim namespace and tested creation permissions | B07 | Read active rules without changing them | Probe creates one permanent test claim; update/delete attempts must fail |
| Exact approved legal files, SBOM and configured public key | B08-B10 | Trusted hashes and preflight validation | Missing approval blocks the cells; do not substitute draft text |
| Protected candidate authorization and Windows environments | B09-B10 | Inspect reviewers, default-branch restriction and bypass setting | Owner approval required; no environment changes in this pass |
| Signing account and exact approved quota | B10 | Protected secret names only; never read or print their values | Every uncertain request consumes quota; never rerun automatically |

No test changes a firewall, DNS setting, normal browser profile or installed product.
No signing credential enters a workstation. Owner-dependent B07-B10 stay blocked
until their prerequisites exist; the no-secret group does not imply their approval.

## Automated gate

Run `python3 -m pytest scripts/tests -q`, `cargo test --locked`,
`cargo clippy --all-targets -- -D warnings`, and `cargo fmt --check`.
Record each exit code. The suite does not replace the cells below.

## Part B: candidate boundaries

B01-B06 are the bootstrap pull-request gate. B07-B10 are the activation gate
after the reviewed bootstrap reaches the default branch. They remain blocked
until the owner supplies the listed protections, inputs and approvals. A pass
for B01-B06 does not authorize signing or satisfy a product installation gate.

Each cell starts with a new isolated fixture directory and an unmodified checkout.
Capture the exact command, stdout, stderr, exit code and relevant before/after
file hashes at the cell boundary. No command reads the workspace environment file.
Delete only that cell's fixture directory after its records are filed.

| Cell | Precondition and setup | Action | Expected observable | Independent oracle | Result |
|---|---|---|---|---|---|
| B01-WSL | WSL Python, no signing variables; record commit and script hashes | Invoke the public preflight command with a non-default workflow ref and dummy SHA | Nonzero refusal; no materialized source | Filesystem listing shows no output; API is not contacted | not run: exact pushed head and evidence boundary required |
| B01-Windows | Native Windows Python; same setup as B01-WSL | Invoke the same preflight command through Windows Python | Same refusal and no materialized source | Native process exit and Windows filesystem listing | not run: exact pushed head and evidence boundary required |
| B02-traversal-WSL | New traversal ZIP fixture on WSL; dummy authorization binds this commit | Invoke `extract-verified` for this fixture | Refusal names the unsafe archive property before extraction | No extraction directory or outside file exists; fixture SHA256 unchanged | not run: exact pushed head and evidence boundary required |
| B02-symlink-WSL | New symlink ZIP fixture on WSL; dummy authorization binds this commit | Invoke `extract-verified` for this fixture | Refusal names the unsafe archive property before extraction | No extraction directory or outside file exists; fixture SHA256 unchanged | not run: exact pushed head and evidence boundary required |
| B02-case-WSL | New case ZIP fixture on WSL; dummy authorization binds this commit | Invoke `extract-verified` for this fixture | Refusal names the unsafe archive property before extraction | No extraction directory or outside file exists; fixture SHA256 unchanged | not run: exact pushed head and evidence boundary required |
| B02-reserved-WSL | New reserved ZIP fixture on WSL; dummy authorization binds this commit | Invoke `extract-verified` for this fixture | Refusal names the unsafe archive property before extraction | No extraction directory or outside file exists; fixture SHA256 unchanged | not run: exact pushed head and evidence boundary required |
| B02-traversal-Windows | New traversal ZIP fixture on Windows; dummy authorization binds this commit | Invoke `extract-verified` for this fixture | Refusal names the unsafe archive property before extraction | No extraction directory or outside file exists; fixture SHA256 unchanged | not run: exact pushed head and evidence boundary required |
| B02-symlink-Windows | New symlink ZIP fixture on Windows; dummy authorization binds this commit | Invoke `extract-verified` for this fixture | Refusal names the unsafe archive property before extraction | No extraction directory or outside file exists; fixture SHA256 unchanged | not run: exact pushed head and evidence boundary required |
| B02-case-Windows | New case ZIP fixture on Windows; dummy authorization binds this commit | Invoke `extract-verified` for this fixture | Refusal names the unsafe archive property before extraction | No extraction directory or outside file exists; fixture SHA256 unchanged | not run: exact pushed head and evidence boundary required |
| B02-reserved-Windows | New reserved ZIP fixture on Windows; dummy authorization binds this commit | Invoke `extract-verified` for this fixture | Refusal names the unsafe archive property before extraction | No extraction directory or outside file exists; fixture SHA256 unchanged | not run: exact pushed head and evidence boundary required |
| B03-WSL | A one-member authorization ZIP and a second ZIP with an extra member | Extract each through `scripts/candidate/record.py` | Valid record extracted exactly; extra member refused | Compare source/extracted SHA256 and absent second output | not run: exact pushed head and evidence boundary required |
| B03-Windows | Native Windows paths, same two record cases | Run the record command with Windows Python | Same exact-copy success and extra-member refusal | Native SHA256 and process exit | not run: exact pushed head and evidence boundary required |
| B04-Windows | Production PowerShell script and dummy non-default ref | Invoke signer with missing input and no vendor variables | Refuse before vendor access or file mutation | Native exit, script output, unchanged isolated directory | not run: exact pushed head and evidence boundary required |
| B05-Windows | Production PowerShell script, attempt two, default-branch context | Invoke signer with missing input and no vendor variables | Refuse the rerun before reading a signing ledger | Native exit and absent ledger | not run: exact pushed head and evidence boundary required |
| B06-Windows | Pinned JAR, Java compiler and dummy inputs only | Run the credential-safe launcher's missing-file self-test | Fixed safe output, no secret values, no log directory | Inspect raw captured output and all created files for dummy values | blocked: native Java 17 and the pinned vendor archive must be available |
| B07 | Merged trusted workflow, protected claim namespace and create permission | Dispatch the same-run secret-free claim probe | One competing create wins; later create/update/delete fail | GitHub response codes, exact ref read-back, live active rules | blocked: reviewed bootstrap must reach master and claim protection must be configured |
| B08 | Exact pushed feature head with approved legal inventory and public key | Dispatch unsigned build and independent validation | Sealed source excludes only result file; independent payload inventory and quota match | Git tree inventory, immutable artifact digest, independently read PE machine headers and legal hashes | blocked: reviewed bootstrap, approved legal inputs and public key required |
| B09 | B07/B08 outputs and candidate-authorize protection | Approve the displayed exact tuple; create the durable signing claim without vendor secrets | One claim binds approved source, artifact, target, tooling, run and quota | Protected approval API and exact annotated Git object | blocked: protected environment, actual probe and validated candidate required |
| B10 | B09 and separate candidate-windows approval for the displayed quota | Run protected signing once, verify final bytes, hold artifacts | Every layer carries the approved publisher/timestamp; exact quota; no release exists | SignTool, certificate hashes, final artifact digest and verified attestation | blocked: signing approval and complete candidate prerequisites required; not authorized by local tests |

## Handoff and results

The next host fetches the exact implementation branch and records its head before
running a cell. Native Windows means Windows Python and PowerShell, not WSL.
Never turn a skipped or blocked cell into a pass from a unit-test result.

| Part | WSL | Windows | Linux | macOS |
|---|---|---|---|---|
| Part B | not run: evidence boundary required | not run: evidence boundary required | Not-Needed: Windows-only workflow; portable refusals covered on WSL | Not-Needed: Windows-only workflow; portable refusals covered on WSL |
| Overall | not run: live tooling checks owed | not run: protected workflow prerequisites absent | Not-Needed: no native Linux surface changed | Not-Needed: no native macOS surface changed |

Final signed installation and platform-trust cells belong to the product runbook.
These bootstrap checks do not award those results. No implementation PR opens
until its applicable first-host gate and exact-head branch checks are green.
