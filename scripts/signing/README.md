# Windows cloud signing

The Windows signing steps are wired into the tag release workflow, but its
existing promotion gate deliberately stops before any signing job. This change
does not remove that gate or qualify a held-candidate promotion path.

`release.ps1` prepares the hash-pinned CodeSignTool 1.3.3 JAR, compiles the
in-process launcher and checks dummy-secret suppression without real credentials.
The release workflow uses Temurin 17.0.20+8, not the runtime bundled in the ZIP.
Only protected tag signing steps receive `ES_USERNAME`, `ES_PASSWORD` and
`ES_TOTP_SECRET`. Build tools receive none of these values.

`publisher.json` contains public certificate identity only. Its SHA-256 value was
compared independently with the issued certificate DER before use. Certificate
renewal requires a reviewed update and a new independently verified certificate.

The launcher suppresses vendor output before loading vendor classes. It uses
Java strings for the vendor command, never OS arguments. The ledger reserves
one attempt before authentication; duplicate files, budget overruns and workflow
reruns fail closed. A failed or uncertain signing operation is not retried.

Every signed output must pass SHA-256/RFC3161 metadata checks, SignTool trust
verification and the exact SHA-256/SHA-1 publisher comparison. The metadata
parser does not replace Windows cryptographic verification. A Python `.pyd`
module is copied unchanged to a temporary `.dll` basename because the vendor
dispatches by extension. Its original name is restored before verification.

Run `test-launcher.ps1 -VendorRoot <extracted-pinned-vendor-package>` on Windows
to test suppression and refusal paths with dummy credentials. Run
`test-metadata.ps1 -VendorRoot <package> -PeFile <already-signed-PE> -MsiFile
<already-signed-MSI>` to test existing public fixtures. These two local tests use
the package's bundled compiler/runtime only with dummy or absent credentials.
The fixtures are copied, never executed or signed. They must have an embedded
SHA-256 signature and RFC3161 SHA-256 timestamp. Both tests print their isolated
temporary directory for removal after inspection.

These checks do not authorize a release or prove installer behavior. Real
package signing still requires the protected environment review and its displayed
per-architecture quota. Final clean-machine installation checks remain required.
