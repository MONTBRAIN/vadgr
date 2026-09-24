# Distribution builds

`distribution-matrix.json` is the executable eight-target build matrix. The
trusted candidate workflow selects one Windows signing target and generates the
other seven native builds from this file. Each architecture runs on its native
runner. Native headers and the private CUA/Python target pins are checked before
upload. Build output excludes compiler caches and debug symbols.

Windows uses WiX 7.0.0. Its out-of-process standard bootstrapper and MSI custom
action retain their timestamped FireGiant signatures. The packaging gate checks
their architecture and signature with PowerShell and SignTool. Product files,
the custom bootstrapper DLL, MSI, Burn engine and setup still use the separately
approved publisher signature budget.

## Holding and publication

The current protected producer can hold one Windows target at a time. Its
record explicitly says `single-target-qualification` and
`complete_distribution: false`. The unsigned native builds are not final held
vehicles. A successful native build is not an installation or E2E verdict.

Full distribution holding remains unavailable until the trusted macOS producer
exists and every target's final signature or integrity verification is complete.
The legacy macOS signing job remains disabled. An aggregate must retain separate
target-specific legal and SBOM bindings; concatenating their inventories into
one target's manifest is not valid. No current job manufactures that aggregate.

`scripts/distribution_matrix.py complete --records <verified-records.json>` checks
an eight-target producer inventory. It is not a signature verifier or an
authorization. The publication workflow separately rejects missing, duplicate,
renamed and cross-architecture vehicles, verifies immutable bytes, and preserves
the protected publication approval. None of these changes enables publication.

## Compilation fixture

On native Windows with the pinned .NET SDK, set `VADGR_TEST_WIX_BUILD=1` and run
`python -m pytest scripts/tests/test_wix7_packaging.py -q`. This compiles synthetic
MSI and setup inputs, checks the upstream native signatures, and never installs
the fixture. Its text is not approved legal content or a release input. Remove
the isolated pytest output after the checks and run the build systems' clean
commands for the worktree's output directories.
