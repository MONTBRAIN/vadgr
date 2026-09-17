# Public Sigstore verification fixtures

Copied without changes from `sigstore-verify` 0.11.0, published from
[sigstore-rust](https://github.com/sigstore/sigstore-rust), under Apache-2.0.
The conda artifact is base64 encoded to keep this fixture text-only.

The Rekor v1 bundle is from the public production instance. It is signed by a
different public GitHub repository, not Vadgr. Tests require full cryptographic
verification using the embedded public root, then rejection by Vadgr's fixed
publisher identity policy. The Rekor v2 bundle is from Sigstore's staging
instance and must fail cryptographic verification under the production root.
