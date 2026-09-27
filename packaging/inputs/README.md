# Windows legal review inputs

The Windows directories contain reproducible **drafts**, not approved package
inputs. Their review status and coverage remain incomplete. The existing package
validator must reject them. No signature, publication or release is authorized.

This is the **superseded preparation baseline**, retained for reproducibility.
The CUA signed-to-signed repair requires a new profile artifact, wheel/payload
identities and unsigned observations. These directories must not be promoted to
candidate inputs by approving their old hashes.

The original Version 1.0 public terms remain unchanged. Exact third-party grants,
notices and upstream source archives are retained separately. These drafts do
not change any component's license or assert that a declared license proves
all redistribution duties have been met.

Reproduce each directory from the final native preparation observations for run
`36313384412`, not from the intermediate raw artifacts:

```powershell
python scripts/inspect_legal_crate_sources.py --source-root . --cache C:/review/crates --cargo-cache C:/review/cargo-cache --wheelhouse C:/review/observations/x64/unsigned-inputs/wheelhouse --wheelhouse C:/review/observations/arm64/unsigned-inputs/wheelhouse --output C:/review/crate-observations.json
python scripts/synthesize_windows_legal.py --source-root . --observation C:/review/observations/x64 --architecture x64 --created 2026-09-27T14:47:24Z --source-archives C:/review/sources --crate-cache C:/review/crates --observation-bindings packaging/inputs/windows-observation-bindings.json --output packaging/inputs/windows-x86_64
python scripts/synthesize_windows_legal.py --source-root . --observation C:/review/observations/arm64 --architecture arm64 --created 2026-09-27T14:47:24Z --source-archives C:/review/sources --crate-cache C:/review/crates --observation-bindings packaging/inputs/windows-observation-bindings.json --output packaging/inputs/windows-aarch64
```

Output directories must be absent. Add `--verify` to compare an existing packet
without changing it. Every recorded observation file is checked by size and hash;
profile inputs are compared against the exact source Git blobs, not checkout
line endings. Original notice bytes are never normalized.
The explicit observation-binding record pins each observation digest, target,
source revision, trusted producer revision and run. Rebaselining requires
independently verifying the new retained artifact and updating that record;
self-consistent claims inside an observation do not establish its identity.

The source directory needs these exact archives:

| File | SHA-256 | Source |
| --- | --- | --- |
| `nodriver-0.50.3.tar.gz` | `24ca688d8646ef8ffad5c8ce65804e5e7671a779ad26a24d76f6465d5666c631` | [PyPI source distribution](https://files.pythonhosted.org/packages/1a/ad/b8b7472ddbf8c28e4ae37ef46d863400ea2688569f3178a083dda8531f3f/nodriver-0.50.3.tar.gz) |
| `wix-b8977d6.tar.gz` | `aef765da7c8051919081235840a8fca10e6bc4f37aab83764a80974ffd1fe09b` | [Exact WiX revision](https://codeload.github.com/wixtoolset/wix/tar.gz/b8977d6f88e7b68e000bac226a2814f236770570) |
| `epaint_default_fonts-0.36.1.crate` | `18dee69613aac468922cf28a32025eb7d7ed6985b61f73245848e58f37876c98` | [Exact font crate](https://static.crates.io/crates/epaint_default_fonts/epaint_default_fonts-0.36.1.crate) |
| `pydantic_core-2.46.5.tar.gz` | `10416c15b8839ecc4ef4d0885da76da6fd0f67333a0eb8aff6d93c4b8f2910fc` | Exact PyPI source URL in `scripts/windows_legal_source_evidence.py` |
| `rpds_py-2026.6.3.tar.gz` | `1cebd1337c242e4ec2293e541f712b2da849b29f48f0c293684b71c0632625d4` | Exact PyPI source URL in `scripts/windows_legal_source_evidence.py` |
| `cryptography-50.0.1.tar.gz` | `5dd9bda1c12b4162f6ff568eeb5e0ff956c28d14406e875cfe8a63a2d414ff20` | Exact PyPI source URL in `scripts/windows_legal_source_evidence.py` |

The crate inspector acquires only exact digest-matching archives named by the
inventories, without executing source. The synthesizer independently re-reads
and re-hashes those archives. `source-archive-observations.json` retains original
statement locations, archive/member-set digests and Cargo manifests.
The observed wheel SBOM catalogue supplies any newer exact crate versions absent
from earlier acquisition lists. Conflicting crate identities are rejected;
neither an old supplement nor another target's catalogue replaces observed bytes.
`nested-source-scope.json` classifies wheel SBOM edges using exact source
dependency kinds and Windows target predicates; it does not claim linker-map
precision. `python-native-source-mapping.json` retains actual PE imports as well
as producer metadata, including the producer's stale OpenSSL 1.1 path correction.

`copyright_absence.py` permits proposed SPDX `NONE` only for a complete decoded
archive with no ambiguous ownership markers outside exact standard-license
boilerplate. Undecoded members and nonstandard notices remain unresolved. The
exact source archive and per-file audit must be delivered in the package; both
the generator and validator recompute the audit. An approved package review is
still mandatory. This is not a public-domain declaration or an author-to-owner
inference. These validator/generator changes need the normal trusted-source
review before a protected candidate can rely on them.

Each `review-ledger.json` names exact component questions. `cargo-scope.json`
separates normal target dependencies from development, build and proc-macro
contexts; it is not a linker map. Nested wheel catalogues remain distinguished
from binary-linkage proof. All four complete font byte sequences must occur in
the observed daemon before they enter the asset inventory. Runtime pip's own
vendored packages are enumerated from the installed vendor catalogue and trees.
The exact broker members and relay are also compared with the existing
helper-only redistribution record. That original record and all named nested
notices are retained. Its authority is not extended to unrelated outer files.
`helper-spdx-mapping.json` records each exact helper member's component grants.
The custom Windows redistribution identifier contains the SHA-256 of its exact
included conditions, also retained as an SPDX extracted license. A custom
identifier never substitutes for review or permits a source-duty inference.

The pywin32 wheel's adodbapi subtree is separately inventoried under its exact
LGPL declaration. Its deterministic source ZIP includes every shipped subtree
member, including the license, setup file and tests. This does not conclude the
license scope of unrelated native pywin32 modules. Source copyright records keep
the original member path, hash and statement line rather than inventing ownership
from package author metadata. Native notice classifications retain upstream
statements separating libffi build tools and XZ command-line tools from the
mapped runtime libraries.

The included nodriver archive supplies its exact upstream source. Whether a
larger covered combination requires additional source, build instructions or
AGPL coverage remains an explicit question. Including only that archive does
not answer it. The WiX archive likewise supplies actual source rather than a
future promise; final distributed-runtime mapping, any modifications and the
official-build terms remain separate checks.

License choices backed by retained grant text are proposals. Unknown copyright,
license or scope remains `NOASSERTION` or an explicit unresolved field. Do not
turn these values into an approval by mass substitution. Finish the ledger,
then feed concluded inputs to `scripts/generate_legal_bundle.py` and validate
the exact generated package before approving its review. The candidate legal
proposal is intentionally not emitted while these input bundles are incomplete.
