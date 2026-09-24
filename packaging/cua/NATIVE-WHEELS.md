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
4,658 passes and 23 classified skips; its four memory-allocation tests must run.
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
