# Native dependency producer

`native-wheels-input.json` pins cryptography 50.0.1, OpenSSL 4.0.2, Rust 1.97.1,
Python 3.12.14, uv 0.12.7 and the complete Python build/test wheel closure.
Windows ARM64 and Intel macOS use native GitHub-hosted runners. macOS retains
the product's 13.0 deployment floor. A runner image or compiler update requires
an input change; a moving runner label is not an approval.
The explicit `pyo3/abi3-py311` feature matches upstream's limited-API build
family; its `cp311-abi3` wheels are tested on the bundled Python 3.12.14.

The Cargo lock and canonical package-list digests come from the hash-verified
source archive. Installed Rust component metadata must match the hash-verified
release manifest; compiler host/commit and Cargo binary identity are also checked.
Both comparisons are repeated by the independent output validator.

Test inputs include bcrypt 5.0.0 and the exact Wycheproof and x509-limbo snapshots
selected by the pinned upstream source. The producer verifies archive hashes,
checks populated data roots, passes both roots to pytest and records the inputs
in its source report and build-only inventory. These data and test dependencies
do not enter the produced wheel or become shipped-component claims.

The test policy requires exactly 4,681 unique named cases. It binds every skip
to its exact class, parameterized name and reason, separately for each target.
Intel macOS requires 4,654 passes and 27 classified skips. Windows ARM64 requires
4,651 passes and 30 classified skips; its four memory-allocation tests must run.
Missing test data or bcrypt never qualifies for a skip. Unknown, duplicate,
changed or missing expected skips refuse output attestation. Failed runs may
retain only test-report diagnostics, never an approved wheel artifact.

The macOS classification comes from run `35950945693`: 173 of 199 skips lacked
inputs (154 Wycheproof, five limbo, 14 bcrypt). The other 26 were negative tests
for unavailable features, FIPS-only cases, deliberately unsupported fixtures,
and four host memory-allocation cases. Installing bcrypt enables its 14 tests
and makes the one bcrypt-absence negative case inapplicable. The Windows policy
does not copy macOS memory behavior: different native results remain a refusal.
These expected results are not a claim that a corrected native run has passed.

Run `35955082393` subsequently completed all Windows upstream tests with 4,651
passes and 30 skips, but the earlier 23-case policy correctly refused output.
The seven additional identities are six AEAD `test_data_too_large` cases and
`test_ciphers.test_update_auto_chunking`. The pinned upstream source explicitly
limits those tests to Linux and macOS because their helper uses Unix-only
`mmap.PROT_READ`. The generic skip message does not mean Windows is 32-bit or
missing a dependency. Only those exact Windows class/name/reason rows are
included; the macOS policy is unchanged. This policy update does not retroactively
qualify a failed run or replace a new two-target build and attestation.

The snapshots match the [upstream fetch action](https://github.com/pyca/cryptography/blob/ffde75a2b594822c740a2e4748b56c00548302bf/.github/actions/fetch-vectors/action.yml):
Wycheproof `b61843a9a5115bb758134b6a1f5d5e502d445342` and x509-limbo
`341400395157bcd720afc37c8fdf026fcc7a88e9`. Skip predicates are in that same
source commit's [tests](https://github.com/pyca/cryptography/tree/ffde75a2b594822c740a2e4748b56c00548302bf/tests/hazmat/primitives)
and [memory probe](https://github.com/pyca/cryptography/blob/ffde75a2b594822c740a2e4748b56c00548302bf/tests/conftest.py).
Upstream's custom vector subtests do not log individual subtest skips to JUnit;
the 4,681 count is the named pytest collection, not the number of vector cases.

The manual `Native dependency wheels` workflow runs only on `master`, attempt 1.
The checked-out commit is the input commit. It accepts no alternate source ref,
URL, command or hash. Source jobs have read-only repository access and no signing
environment. The fresh validation job downloads those two exact run artifacts,
checks their GitHub digests, parses wheel metadata/native headers and upstream
test results as data, checks the input inventory, and attests the wheel manifest.

Input hashes use sorted, indented UTF-8 JSON plus a final LF. Recipe hashes use
UTF-8 text with LF line endings so native Git checkout settings do not alter
identity. Artifact and wheel hashes cover their exact unmodified bytes.

The output contains the wheel files, original build artifact archives, manifest
and offline attestation bundle. Each archive also retains its test report,
compiler/source report and build-input inventory. The inventory includes all
Cargo lock packages, not a claim that every build dependency ships. Package
legal review must separately classify the shipped static dependency closure.

To check inputs and the data validators locally:

```console
python scripts/validate_native_wheels.py
python -m pytest scripts/tests/test_native_wheels.py -q
```

A producer success is not a product pass. Review and freeze the exact output
manifest and wheel hashes before connecting target-specific runtime locks or
payload assembly. The consumer must verify the attestation, producer identity
and frozen bytes; it must never select a latest artifact. Signing, final legal
inventory and native installed-product tests remain separate requirements.

## Retained output identity


Run [35957405519](https://github.com/MONTBRAIN/vadgr/actions/runs/35957405519),
attempt 1, completed successfully at source commit
`4624073d81f44bf8ae88ca4fbe482d7f138095f1` on `master`.
`native-wheel-manifest.json` retains its exact canonical bytes. Its SHA-256 is
`2f86c4d2c6493d32019a617c669e3c0babefc565f9da73c6182475286ad499b8`.
The adjacent verification bundle has SHA-256
`8e8f9ec6f85662872c06b15b0e9d205fbff6a62d02fad1121b0ee00fe71f3708`.
[Attestation 49747958](https://github.com/MONTBRAIN/vadgr/attestations/49747958)
binds that manifest to the exact source and signer commit, GitHub Actions issuer,
default-branch workflow and hosted-runner identity. Independent verification
checked the certificate and statement identities as well as the signature.

| Target | Artifact ID | Job ID | Wheel SHA-256 | Passed / skipped |
| --- | --- | --- | --- | --- |
| Windows ARM64 | 10790957494 | 107498542111 | `900c3a689b80ca7c3f0c0846af6c1023f8c02cc4b1555f0126adb4e9789fce70` | 4651 / 30 |
| Intel macOS | 10791711091 | 107498542241 | `e414d09a63dca5056ed46bcb915ecd5a27c3c08a23a540337d5f061b09c8c665` | 4654 / 27 |

The manifest binds original artifact digests, wheel sizes, exact skip identities,
source/tool inputs and report hashes. Validated artifact `10791402002` contains
13,917,611 bytes, SHA-256
`8c6e69ec29661d78369d4759b599c82279b9497f91c0dcf350b3d6236a5258ff`.
Its validation job is `107501687012`; repository ID is `1158230114` and workflow
ID is `365688750`. No wheel binary is committed here. The consumer downloads
only the manifest's exact immutable artifact IDs and refuses unavailable bytes.
The original artifact retention ends on 2026-12-23; a rebuild needs new review.

Both targets had zero test failures or errors and four deprecation warnings from
certificate fixtures. macOS also had 14 upstream CFFI const-qualifier compiler
warnings. The artifact uploader reported Node deprecations. These results are
native producer tests, not installed-product qualification or legal approval.

`locks/x86_64-pc-windows-msvc.lock` selects the complete 40-distribution Windows
x64 runtime closure for CPython 3.12.14 and CUA 0.7.8. Its SHA-256 is
`83bdf9d395ea701f032e30cba1537483ebfefe8cdac03f30b9eccdccb4e98292`.
Each entry selects one downloaded, hash-verified upstream wheel. Package metadata,
platform markers, extras and version constraints were checked for a complete
active closure. This target uses upstream cryptography 50.0.1, not either custom
wheel. The development lock is unchanged. This input record is not a legal
approval, signed candidate or installed-product pass.

Windows ARM64 and macOS target locks are not promoted. The released
`vadgr_computer_use-0.7.8-py3-none-any.whl` includes the x64 PE member
`computer_use/browser/winhost/vadgr-cua-host.exe`. The unchanged native-member
validator rejects it for both Windows ARM64 and macOS. A complete target-native
CUA packaging repair is required before either runtime lock can be admitted.
No file removal, architecture exception or emulation approval is implied here.

A Windows x64 candidate source must synchronize the manifest, bundle and selected
lock without changing their bytes. Missing reviewed target locks still refuse
consumption on other targets. The trusted materializer must
verify origin and attestation, download and inspect every selected wheel, and
produce the offline wheelhouse before compilation. Signing, legal closure and
native installation tests remain separate gates.
