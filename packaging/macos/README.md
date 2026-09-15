# macOS package

`build.sh` assembles the unsigned architecture-specific app. It includes the
Vadgr backend, local console, and the separately signed
`Vadgr Computer Use.app` responsible-process host. CUA always starts below that
host, so Accessibility and Screen Recording attach to the stable
`com.montbrain.vadgr.cua` designated requirement across updates.

The protected candidate job signs nested code inside-out, signs the outer app,
builds and signs the product package, notarizes the exact package, staples it,
and verifies every layer. This source provides no ad hoc or self-signed path.

Package inputs are architecture-specific: `packaging/inputs/macos-arm64/` and
`packaging/inputs/macos-x86_64/`. Each contains its legal files, SBOM, offline
README, component inventory and exact-byte approval record. The source gate
checks both input sets. The builder checks the selected set against its actual
payload. The signer checks the copied resources again before signing.

Signing rejects draft terms, incomplete notices, changed source inputs and
unapproved package bytes. Generating a legal bundle does not approve it.

Prepare public UTF-8 terms and disclosures, exact target component metadata,
and verbatim license, NOTICE and required source-offer files as local inputs.
The input JSON maps those files to relative paths and SHA-256 hashes. Then run:

```sh
python3 scripts/generate_legal_bundle.py --input public-inputs.json --output new-draft
```

The output directory must be new and owned by the current user. Generation
copies the supplied bytes and produces escaped terms RTF and SPDX 2.3 JSON.
It creates a draft review with every review question open, not an approval.
Resolve actual target dependencies and inspect the assembled package before
approving its inventory. Synthetic test fixtures are not legal inputs.

The validator checks inventory-to-SBOM and file/hash consistency. Protected
source review and the owner's per-run environment approval authenticate the
signing decision; JSON booleans alone do not prove legal completeness.
