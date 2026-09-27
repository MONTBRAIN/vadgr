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
| `sqlite-autoconf-3530100.tar.gz` | `83e6b2020a034e9a7ad4a72feea59e1ad52f162e09cbd26735a3ffb98359fc4f` | [Exact SQLite source](https://www.sqlite.org/2026/sqlite-autoconf-3530100.tar.gz) |
| `iroh-f2eb930-LICENSE-APACHE.txt` | `903131e2786f073a942fbf8fae122d9e576e4dad758c6da7f9f2ba58fd8611ab` | [Exact Iroh source revision](https://raw.githubusercontent.com/n0-computer/iroh/f2eb930dda3779c6d852b72f3712aacd6e573ab1/LICENSE-APACHE) |
| `Apache-2.0-standard.txt` | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` | [Complete Apache license](https://www.apache.org/licenses/LICENSE-2.0.txt) |
| `MPL-2.0-standard.txt` | `3f3d9e0024b1921b067d6f7f88deb4a60cbe7a78e76c64e3f1d7fc3b779b9d04` | [Complete Mozilla license](https://www.mozilla.org/media/MPL/2.0/index.txt) |
| `certifi-2026.6.17.tar.gz` | `024c88eeec92ca068db80f02b8b07c9cef7b9fe261d1d535abfd5abd6f6af432` | [Exact certifi source distribution](https://files.pythonhosted.org/packages/c9/c7/424b75da314c1045981bd9777432fad05a9e0c69daa4ed7e308bbaffe405/certifi-2026.6.17.tar.gz) |
| `tix-8.4.3.6.tar.gz` | `f7b21d115867a41ae5fd7c635a4c234d3ca25126c3661eb36028c6e25601f85e` | [Exact Tix source archive](https://github.com/python/cpython-source-deps/archive/refs/tags/tix-8.4.3.6.tar.gz) |

The crate inspector acquires only exact digest-matching archives named by the
inventories, without executing source. The synthesizer independently re-reads
and re-hashes those archives. `source-archive-observations.json` retains original
statement locations, archive/member-set digests and Cargo manifests.
The observed wheel SBOM catalogue supplies any newer exact crate versions absent
from earlier acquisition lists. Conflicting crate identities are rejected;
neither an old supplement nor another target's catalogue replaces observed bytes.
External crate grants require the exact archive manifest, repository and VCS
revision. Their original declaration remains separate from the proposed choice.
Source-scope records retain the exact upstream statements for additional grants;
an unexpected grant or source reference leaves the component unresolved.
Feature-dependent exclusions also bind the exact observed Cargo feature graph.
Short vendored Apache application notices retain both their original wording
and the complete referenced grant. Python's cumulative terms and its explicitly
named documentation-code grant remain separate from upstream declarations.
`nested-source-scope.json` classifies wheel SBOM edges using exact source
dependency kinds and Windows target predicates; it does not claim linker-map
precision. `python-native-source-mapping.json` retains actual PE imports as well
as producer metadata, including the producer's stale OpenSSL 1.1 path correction.

`copyright_absence.py` permits proposed SPDX `NONE` only for a complete decoded
archive with no ambiguous ownership markers outside exact standard-license
boilerplate or a complete hash-pinned document whose generic compliance wording
was separately inspected. A changed document does not inherit that finding.
Two small pinned WebAssembly/archive records have complete byte-range reviews,
including all symbols, instructions, archive headers and padding. Their audits
retain every byte in hexadecimal alongside its interpretation. Any changed byte
loses that finding. This is not a generic binary-format or strings-scan exemption.
Other undecoded members and nonstandard notices remain unresolved. The
empty signed Conda test fixture also has an exact, complete decoding observation
in `scripts/legal_evidence/sigstore-empty-conda.json`. Both Zstandard frames were
decoded completely and all nine nested text records inspected. Their decoded
bytes, TAR headers and zero padding are rechecked without an optional decoder.
Changed compressed bytes do not inherit that review. The
exact source archive and per-file audit must be delivered in the package; both
the generator and validator recompute the audit. An approved package review is
still mandatory. This is not a public-domain declaration or an author-to-owner
inference. These validator/generator changes need the normal trusted-source
review before a protected candidate can rely on them.
For an observed runtime source tree, the deterministic source ZIP must reproduce
the entire component's canonical member-hash map. The validator checks every
member and rejects missing files, binary members, ambiguous ownership markers,
links, aliases and uninspected ZIP comments. This narrow path does not approve
opaque crate fixtures or infer ownership from an author or certificate subject.
Inconclusive copyright audits also retain the complete source archive and audit
in the offline packet. The exact positive fdeflate fixture fully decodes into
its documented numerical pattern. The two exact malformed negative fixtures have
complete bit-level observations of their dynamic Huffman tables and numerical
suffixes. Both omit the end-of-block symbol. Every bit is retained and accounted
for, without claiming successful decompression. Only those complete hash-pinned
vectors qualify; a decoder rejection or changed suffix never inherits the result.
Two CMS fixtures fully decode to the exact retained sample text, with the zlib
checksum and SHA-1 sample digest independently checked. The encrypted CMS fixture
retains typed envelope fields and its precise unresolved ciphertext range.
Two public test keys have complete numerical-field observations. Four
certificates and a certificate request are fully decoded, including the
misnamed EC key fixture's text, public point and ECDSA signature. Certificate
names are not copyright owners.
Encrypted content remains unresolved without sufficient plaintext or ownership
evidence. These new observations apply on regeneration; the superseded packet
hashes above do not change or gain approval.
Certifi's source comparison binds every observed member to the published source
distribution. Only exact pip import/resource namespace relocations are accepted;
both the complete upstream source and actual modified source are delivered.
The pywin32 composite retains all named directory grants and its separately
inventoried LGPL subtree. A native wheel source mapping is recorded only when
that target's own producer SBOM supplies the matching source hash and build data.
For the custom ARM64 cryptography wheel, the observed payload pins the exact
native producer manifest. Its offline attestation is verified independently,
then its wheel and source hashes are matched to the installed wheel and source
inventory. The manifest and bundle remain in the packet's producer evidence.
This producer binding does not approve redistribution or borrow x64 provenance.
The x64 cryptography binding instead retains upstream run `32890072935` and
native job `97940032724`, with the exact source and wheel artifact ZIPs. Both
members must equal the source inventory and installed wheel hashes. The pinned
workflow and composite action show that this native job builds that source
artifact. These primary API records are not represented as a new independently
verified build attestation. Acquire the retained inputs with:

```powershell
python -B scripts/windows_crypto_producer.py --output <source-archive-directory>/upstream-cryptography-50.0.1-x64
```

Keep that directory unchanged for offline packet reproduction. Synthesis rejects
a changed ZIP, source member, wheel member, producer identity or build procedure.
The reproduction host needs `gh attestation verify` and the retained trusted
root for this independent offline check.

New unsigned preparation builds also capture native Pillow feature results,
loaded module identities and the complete observed PIL tree. The private
interpreter runs with isolated startup, site initialization disabled and bytecode
writes disabled. Every non-system loaded binary must belong to the observed
payload. A fresh observer validates these records without executing build output.
Rust builds emit separate MSVC link maps for each executable and bootstrapper
library. The exact target sysroot is retained inside a ZIP, so build-only DLLs
do not enter the executable-signing set. The channel manifest pins its original
distribution. Add that exact `rust-std-<version>-<target>.tar.xz` to the supplied
source archive directory. Synthesis compares every library hash with that archive
and records named link-map symbols. This closes a binary-to-distribution binding,
not third-party grant scope or approval. Old observations without these records
remain incomplete; local probes cannot retroactively alter their trusted identity.
The Pillow catalogue's optional entries still need source/build scope matching;
a supported feature alone is not a complete transitive native-library inventory.
`pillow-native-scope.json` now matches each catalogue extension to installed
module bytes and records its native feature result separately. Unloaded modules
remain shipped. Unsupported features do not prove transitive-library absence.
Version differences remain explicit. Rust's `library_scope` records each exact
target library and the executables whose public-symbol maps reference it.
Libraries without those references are not declared build-only.

Unsigned WiX membership can be captured separately after the existing
`scripts/candidate/package-windows.ps1` MSI and bundle steps have produced both
containers and their `wix-vendor-*.json` reports. This does not require product
signatures. Do not construct approval records merely to obtain an extraction.
Keep the package output, complete WiX 7.0.0 tool directory and preparation
observation unchanged. Independently record the tool-directory hash before
capture. It is SHA-256 of the canonical JSON map from every relative file path
to its `size` and `sha256`, with no excluded tool files. For example:

```powershell
python -B -c "from pathlib import Path; from scripts.windows_wix_evidence import tree,file_record,canonical_json,sha256_bytes; print(sha256_bytes(canonical_json({p:file_record(b) for p,b in tree(Path('C:/review/wix-tool')).items()})))"
python -B scripts/windows_wix_evidence.py capture --architecture x64 --observation C:/review/observations/x64 --package-root C:/review/package-x64 --tool-root C:/review/wix-tool --tool-sha256 <independently-recorded-tool-digest> --root C:/review/wix-x64
python -B scripts/windows_wix_evidence.py validate --architecture x64 --observation C:/review/observations/x64 --expected-sha256 <retained-capture-digest> --root C:/review/wix-x64
```

The new capture directory must be outside all input directories. Capture runs
only the hash-pinned WiX extractor, with no signing credentials. It never
installs or executes the product. It retains decompiled MSI tables, every
extracted MSI/Burn member, the detached engine, command logs and all file hashes.
Manifest membership, exact observed payload hashes, architecture, vendor member
identities and the one embedded MSI must all match. Unknown native members,
missing files, extra files, aliases and changed inputs fail closed. The capture
record remains unapproved and nonpublishable.

Repeat for `arm64`. Retain the complete capture directories and their
independently recorded `wix-membership.json` digests. Add
`--wix-evidence C:/review/wix-x64 --wix-evidence-sha256 <retained-capture-digest>`
to the corresponding synthesis command above. Synthesis retains the producer
record and adds `wix-runtime-membership.json` without changing source duties,
license findings or approval fields. Offline validation reruns all membership
checks as data and never invokes the extractor. The record binds extraction to
the package and preparation bytes; it is not independent build attestation,
reproducible-build proof or a conclusion about WiX modifications or source
completeness. Old observations and synthetic test containers cannot qualify
a new candidate.

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
The SQLite library disclaimer is independently checked in the exact core
amalgamation, with member hash and header byte offsets retained. Its separate
autosetup build license is not assigned to the runtime library. The retained
Tcl/Tk terms retain their original named copyright parties.
The separately referenced Tix HTML Library grant is acquired from the exact
hash-pinned `tix-8.4.3.6.tar.gz` source archive. Its parent license must equal
the retained runtime notice after newline normalization. The distinct HTML
grant is an extracted custom license, not silently classified as standard TCL.
Its government-rights and source-duty review remains open. This reference
comparison does not establish a native binary's source revision.

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
