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

The initial test policy permits no skips and requires at least 1,000 passing
upstream tests. Supported platform skips must first be classified from native
execution and committed as exact reason/count pairs for that target. An unknown
reason or changed count refuses output attestation. Failed runs may retain only
test-report diagnostics, never an approved wheel artifact. Diagnostic reports
are not evidence of a qualified dependency.

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
