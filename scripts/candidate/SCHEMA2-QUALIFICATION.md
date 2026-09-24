# Reviewed wheelhouse and signing boundaries

This bootstrap changes trusted tooling only. It does not approve dependency
bytes, legal inputs, signing quota or a product installation. Run these native
Windows checks before offering the tooling update. Other hosts run the Python
gate and their own native build qualification; no host inherits a Windows pass.

## Native Windows checks

Prerequisites: native Python 3.12, PowerShell and this checkout. Use no provider
account, phone, signing credential or paid service. Each command runs from the
repository root. The `target/schema2-absent` path must not exist before or after
the commands. No command below creates a candidate or calls a signing service.

| Cell | Setup and action | Expected result and independent oracle | Cleanup |
|---|---|---|---|
| S01 | Run `python scripts/cua_wheelhouse.py --source . --target x86_64-pc-windows-msvc --verify target/schema2-absent` | Exit 1; closed wheelhouse refusal; the absent directory remains absent | Nothing created |
| S02 | Run `python scripts/cua_wheelhouse.py --source . --target x86_64-pc-windows-msvc --out target/schema2-absent/output` | Exit 1 before network access; missing reviewed output parent is refused; no output exists | Nothing created |
| S03 | Run `python scripts/candidate/cua_signing.py verify --authorization target/schema2-absent/authorization.json --records target/schema2-absent/records` | Exit 1; missing authorization is refused; no record directory exists | Nothing created |
| S04 | Run `python -m pytest scripts/tests/test_candidate_wheelhouse_boundary.py scripts/tests/test_cua_wheelhouse.py scripts/tests/test_cua_signing.py scripts/tests/test_distribution_matrix.py -q` | Every applicable test passes; native PowerShell subprocess rejects a dummy GitHub token before touching an absent feature path; the dummy value is absent from output | Pytest owns its isolated fixtures; retain no candidate output |

Run all repository gates after these checks. Record actual native command exits
and gate counts in the pull request. A hosted CI result is a source-gate result,
not a signed installation observation. If the local Rust gate cannot complete,
state its exact resource failure and obtain the exact-head hosted result.

## Protected activation remains separate

Before dispatch, review and merge the exact native-wheel manifest, attestation,
selected target locks and legal inventory approval into the default branch.
The feature source must carry identical reviewed inputs. The workflow downloads
and verifies these inputs using trusted code with read-only GitHub access.
It then clears GitHub credentials and verifies every wheel offline before
executing feature code. The protected signer never checks out feature code.

After independent artifact validation, protected authorization and a one-use
claim still precede paid signing. The signer binds every initial PE digest,
records every final digest, independently verifies native signatures, and
reseals the private runtime inventory before packaging. Tampering, missing
inputs or unapproved non-native changes stop the candidate. These gates do
not permit a retry of an uncertain paid signing request.

One held Windows target is explicitly not the complete eight-target release.
Formal native installation and signing cells remain owed until their exact
candidate exists. No merge, dispatch, signing, tag or release follows from
running S01-S04.
