# Shared CI workflow bootstrap

Candidate admission requires the source's `ci.yml` and `secret-scan.yml` to be
byte-identical to trusted default-branch copies. A successful feature workflow
alone cannot meet this boundary. Promote the reviewed CI tooling separately from
the product implementation, then run the identical workflow on the exact feature
head. Do not relax workflow equality or merge product code to satisfy it.

## Source behavior

The shared workflow accepts only the named package at versions `0.4.12` and
`0.5.0`. Unknown versions and a failed layout job fail the required jobs.

| Source | Installer checks | Reviewed payload assembly |
| --- | --- | --- |
| `0.4.12` | Existing native and WSL source installers | Unpromoted; no wheelhouse, compilation or assembly in this job. The source does not implement the newer profile format. |
| `0.5.0` | Native graphical-installer refusals and the WSL verifier boundary | Exact reviewed wheelhouse and profile. An incomplete present closure fails. The established absent-target refusal remains explicitly not an install pass. |

Reviewed profile records may already exist on the default branch before the
product implements that format. Their presence must not cause a `0.4.12` build
to consume them. `check_cua_ci_boundary.py` reads the actual `Cargo.toml`; no
caller flag can select legacy behavior for a `0.5.0` source. The legacy path also
refuses inherited release-profile, release-build or wheelhouse selections.

The job IDs and names remain `clean-install (<runner>)`, matching branch rules
and trusted check admission. An unavailable assembly is stated in the step
output and job summary as **not run**. This status never grants a signed install
or authorized CUA runtime result. For an assembled unsigned profile, independent
inventory verification requires the runtime to remain unavailable until its
protected installed authorization exists.

## Exact tooling promotion

Copy the reviewed feature bytes of these files into a new trusted-tooling branch
based on the current default branch:

- `.github/workflows/ci.yml`
- `.github/workflows/.gitattributes`
- `scripts/check_cua_ci_boundary.py`
- `scripts/check_cua_ci_readiness.py`
- `scripts/check_windows_installer_boundary.py`
- `scripts/prepare_cua_build.py`
- `scripts/tests/test_ci_release_layout.py`
- `scripts/tests/test_cua_ci_boundary.py`
- `scripts/tests/test_cua_ci_readiness.py`
- `scripts/candidate/CI-BOOTSTRAP.md`

The default branch already supplies the reviewed CUA wheelhouse, profile and
payload validators that these helpers import. Preserve those current trusted
implementations. Do not replace them with older feature copies. No `src/`,
`build.rs`, Cargo package version, installer, profile pin or approval record is
part of this tooling promotion.

`secret-scan.yml` must also remain identical, but needs no change when its bytes
already match. The scoped attributes keep workflow checkouts byte-identical to
their Git blobs even with Windows `core.autocrlf=true`. No normalization is added
to admission itself. The candidate policy, unsigned preparation admission, protected
workflow, signing environments and required check rules do not change.

Run the Python gate on both the feature and an isolated default-branch tree
with only these files copied in. Verify legacy selection for every supported
target without downloading or materializing anything, and verify the feature's
reviewed profile selection and independent readiness checks. Then merge the
tooling PR through the normal required checks. Push the identical workflow on
the feature, wait for all required checks on that exact commit, and dispatch
unsigned preparation from the newly trusted default-branch commit. Hosted
native builds and legal review remain separate gates.
