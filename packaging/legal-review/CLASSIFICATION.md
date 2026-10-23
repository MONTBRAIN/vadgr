# Windows component license classification

Checked on 2026-09-23 against `windows-x86_64/collection.json` and the exact
upstream revisions below. This report proposes component classifications and
identifies the files needed to complete the package. It does not approve a
package, change a review closure, or establish coverage of final installer bytes.
The ARM64 packet needs its own artifact comparison, even where source revisions
and license terms are shared.

The collected license and notice files remain verbatim. A metadata declaration
and a license text are separate records. A declaration can establish the license
choice, but it does not replace the copy that recipients must receive.

## License choices for the two crates without license files

| Component | Exact upstream grant | Proposed choice | Copyright and notice disposition |
|---|---|---|---|
| `cms 0.2.3` | [README at `5821a21553509dbd03eae593b0a1fad4e2083d4e`](https://github.com/RustCrypto/formats/blob/5821a21553509dbd03eae593b0a1fad4e2083d4e/cms/README.md) explicitly permits Apache-2.0 or MIT at the recipient's option. The published manifest agrees. | Apache-2.0 | Retain the upstream grant and any notices found in the selected source files. The author label is RustCrypto Developers; it is not an invented copyright notice. |
| `enum-assoc 1.4.1` | [Manifest at `351b306939b150601451df752a183b077b0de85a`](https://github.com/Eolu/enum-assoc/blob/351b306939b150601451df752a183b077b0de85a/Cargo.toml) declares `MIT OR Apache-2.0`. | Apache-2.0 | The manifest names Griffin O'Neill as author. Preserve that metadata without converting it into a copyright statement or supplying a guessed year. |

The crate archives have SHA-256 values
`7b77c319abfd5219629c45c34c89ba945ed3c5e49fcde9d16b6c3885f118a730`
and `0590c4a94da3372e83493b956755a6e2266830b6e4e3b101afe66e3f39477b91`,
respectively. Their embedded version-control records identify the revisions
above. Inspection found no applicable license file in the crate directory or
its repository ancestors at those revisions.

The missing-file remedy is to retain the exact grant record and include the
unmodified [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt).
Do not borrow a sibling crate's MIT copyright or use Vadgr's copyright-bearing
license as if it were a copyright notice for these crates. Apache redistribution
requires the license copy, preservation of applicable notices and identification
of modified files. It does not require a source offer for an unmodified binary.
An upstream NOTICE must be retained if present; an absent NOTICE is not a reason
to invent one. This proposed choice still needs entry in the component inventory.

`enum-assoc` is a procedural macro. Its presence in the build dependency graph
does not alone prove that its executable code is shipped. Keep build provenance
separate from the final payload inventory; do not silently omit generated code
or declare every build dependency a shipped binary.

## Embedded fonts

`epaint_default_fonts 0.36.1` comes from
[`4c1f2fae95475a40e524884ebb298bcb1714b08e`](https://github.com/emilk/egui/tree/4c1f2fae95475a40e524884ebb298bcb1714b08e/crates/epaint_default_fonts).
Its archive SHA-256 is
`18dee69613aac468922cf28a32025eb7d7ed6985b61f73245848e58f37876c98`.
The crate's source embeds four fonts with `include_bytes!`. Treat them as assets,
even if the compiler places their bytes inside a Rust executable.

| Asset | Applicable license | Copyright and required text |
|---|---|---|
| Hack Regular | MIT AND Bitstream-Vera; DejaVu contributions are identified as public domain | Preserve all of `fonts/Hack-Regular.txt`, including Source Foundry Authors (2018), Bitstream, Inc. (2003), the Bitstream trademark notice and the DejaVu statement. |
| Noto Emoji Regular | OFL-1.1 | Preserve `fonts/OFL.txt` and the embedded copyright: `Copyright 2013 Google Inc. All Rights Reserved.` |
| Ubuntu Light | Ubuntu-font-1.0 | Preserve `fonts/UFL.txt` and the embedded copyright: `Copyright 2011 Canonical Ltd.  Licensed under the Ubuntu Font Licence 1.0`. |
| emoji-icon-font | MIT | Preserve `fonts/emoji-icon-font-mit-license.txt`, including John Slegers (2014). |

The copyright strings for Hack, Noto and Ubuntu were read directly from the
published TTF name tables. The icon copyright appears in its supplied license.
The matching exact upstream [font files](https://github.com/emilk/egui/tree/4c1f2fae95475a40e524884ebb298bcb1714b08e/crates/epaint_default_fonts/fonts)
provide the source references for the packaged copies.

The crate-level expression is
`(MIT OR Apache-2.0) AND OFL-1.1 AND Ubuntu-font-1.0`. It does not enumerate
Hack's Bitstream-Vera duty. Selecting Apache-2.0 for the Rust wrapper cannot
replace any font license. Record the fonts separately, or retain a combined
conclusion that includes every applicable asset license.

Keep these font files unmodified. MIT requires retention of its notice. The
other font licenses also preserve their own license and attribution, restrict
some font naming and endorsement uses, and restrict selling the font alone.
They permit bundling fonts with software and do not require licensing Vadgr
itself under a font license. None of these unmodified assets requires a source
offer. A later font modification requires a separate check of the naming rules.

## Cryptography and its embedded OpenSSL

The selected `cryptography 50.0.1` Windows x64 wheel has SHA-256
`aed8db4f6d71c51efb89530e12d9464e7bf2923d46c3205dc794a2a93f8c0648`.
Upstream release `50.0.1` resolves to
[`ffde75a2b594822c740a2e4748b56c00548302bf`](https://github.com/pyca/cryptography/tree/ffde75a2b594822c740a2e4748b56c00548302bf).
Its license permits Apache-2.0 or BSD-3-Clause. A proposed BSD-3-Clause choice
requires the exact `LICENSE.BSD` text, its `Individual contributors` copyright,
conditions and disclaimer. Keep the supplied dual-license declaration as well.
This choice does not require a source offer.

The wheel's `sboms/sbom.json` identifies a separate, statically linked OpenSSL
component: version **4.0.2**, source archive SHA-256
`736b467530f916737b7031310ccb21d8218c6229e61e8e160cd1d3458cd543a8`.
Its build properties identify Windows `win64` and static build options. The
OpenSSL release tag resolves to
[`f089acdf4bc7ba94a79f4bf6eb7362c3e7d14aa9`](https://github.com/openssl/openssl/tree/f089acdf4bc7ba94a79f4bf6eb7362c3e7d14aa9).
The [license at that revision](https://github.com/openssl/openssl/blob/f089acdf4bc7ba94a79f4bf6eb7362c3e7d14aa9/LICENSE.txt)
is Apache-2.0. Include that text and retain applicable OpenSSL copyright and
attribution notices. Do not apply the historic OpenSSL/SSLeay license or infer
the OpenSSL version from the Python interpreter.

The wheel also includes `sboms/cryptography-rust.cyclonedx.json`. This identifies
the wheel's Rust components independently of Vadgr's Cargo lock. Resolve their
licenses and retain their required texts using that SBOM. In particular,
`self_cell 1.3.0` offers `Apache-2.0 OR GPL-2.0-only`; selecting Apache-2.0 avoids
making a GPL choice for that component. `target-lexicon 0.13.5` has
`Apache-2.0 WITH LLVM-exception`, and `unicode-ident 1.0.24` also requires
Unicode-3.0. Do not drop exceptions or conjunctive license terms.

Outstanding package work: add OpenSSL and the wheel's shipped Rust dependencies
to the final inventory, retain the matching license files, and compare the
ARM64 wheel's own SBOM. A wheel's top-level license file alone does not close
these nested obligations.

## WiX 7.0.0

The collected WiX packages identify source revision
[`b8977d6f88e7b68e000bac226a2814f236770570`](https://github.com/wixtoolset/wix/tree/b8977d6f88e7b68e000bac226a2814f236770570).
Its [LICENSE.TXT](https://github.com/wixtoolset/wix/blob/b8977d6f88e7b68e000bac226a2814f236770570/LICENSE.TXT)
states MS-RL and names `.NET Foundation and contributors`.

Retain the license and attribution for distributed WiX code. MS-RL section 3(A)
requires providing recipients the source for distributed files containing WiX
code, under MS-RL. Identify the Burn engine, bootstrapper application and any
extension runtime actually embedded in the final installer. Provide their exact
corresponding source with its license. If they are modified, include those
modifications. A generic link to the latest WiX tree does not identify the source
for these bytes.

[WiX's publisher clarification](https://docs.firegiant.com/wix/#source-code-license)
explains that producing an installer with WiX does not by itself make the
installer or the product's own code a derivative work. Keep that distinction;
it does not justify omitting the license and corresponding source for actual
WiX code that is redistributed. An SDK used only at build time has a different
distribution boundary from an embedded Burn runtime.

Record this as a positive corresponding-source duty, with actual delivery
details, not an invented promise to provide source later. The collected
`OSMFEULA.txt` addresses use of the official build releases and the maintenance
fee. It is a separate publisher obligation, not a replacement for MS-RL or a
new license to impose on Vadgr recipients. Its applicability and acceptance
remain outside this report's conclusions.

## CPython standalone and its bundled software

The x64 runtime is CPython `3.12.14`, standalone build `20260825`, archive
SHA-256 `15d25c455ea25d6b24d7e58eabdf744fd0db3cfb977934ae08fd2237acd8ccc1`.
The standalone build tag resolves to
[`c0aa3bbdc2fff56a77ad1ecec68b1e47794d8779`](https://github.com/astral-sh/python-build-standalone/tree/c0aa3bbdc2fff56a77ad1ecec68b1e47794d8779).
Retain the runtime archive's exact `python/LICENSE.txt`; do not replace it with
the build repository's older `LICENSE.cpython.txt` or just an SPDX identifier.
Its PSF terms require preservation of the license and copyright and a summary
of changes when distributing a derivative. The included historical licenses
remain part of the document.

The exact [Windows build script](https://github.com/astral-sh/python-build-standalone/blob/c0aa3bbdc2fff56a77ad1ecec68b1e47794d8779/cpython-windows/build.py)
and [download manifest](https://github.com/astral-sh/python-build-standalone/blob/c0aa3bbdc2fff56a77ad1ecec68b1e47794d8779/pythonbuild/downloads.py)
show that this runtime has further dependencies and upstream build changes.
The Windows script selects OpenSSL 3.5 for Python 3.12; the manifest pins
**OpenSSL 3.5.8**. This is separate from cryptography's OpenSSL 4.0.2.

| Runtime component family | License treatment |
|---|---|
| OpenSSL 3.5.8 | Apache-2.0; preserve its license and applicable notices. |
| bzip2 | Preserve its bzip2 license, copyright and redistribution terms. |
| libffi and Expat where included | Preserve the exact MIT license and copyright. |
| liblzma | The selected liblzma source is 0BSD; do not apply the other XZ utilities' licenses without proving those utilities ship. |
| SQLite | Retain the upstream public-domain statement and identify the exact included library. |
| zlib | Preserve its Zlib notice and any alteration notices; do not claim original authorship. |
| Tcl/Tk and Tix where included | Preserve their supplied copyright/license texts. The x64 and ARM64 build script selects different prebuilt Tcl/Tk inputs. |
| pip and its vendored packages | Enumerate the included versions and retain each applicable license. The runtime contains both distribution license files and vendored copies. |

The install-only archive is not the complete build archive. Its extracted legal
files do not alone prove all linked dependencies have been enumerated. Obtain
the full build's `PYTHON.json` and its licenses, or perform equivalent mapping
from the exact build inputs to the installed binaries. Retain a truthful
description of upstream standalone changes and any further packaging changes.
Do not label the entire runtime only `Python-2.0` and discard nested licenses.

The collected pip-vendored certifi notice identifies Mozilla-derived certificate
data under MPL-2.0. Preserve its notice and the covered source/data and check
source availability for any covered executable-form material. The build
repository's MPL-2.0 license does not automatically relicense every Python
runtime binary. Scope each duty to the material actually included.

The permissive runtime licenses above do not impose a general source-offer duty.
That is not a conclusion that all runtime contents have no source obligations:
the final list must retain the separate treatment of any covered MPL material
and any other nested components found in the full artifact comparison.

## Completion records

These classifications support preparation of the package inventory. Completion
still requires the selected license expressions, original copyright strings,
notice references, source-delivery references where required, and hashes for
the exact files delivered to recipients. The final legal and SBOM manifest must
describe the installer and installed payload, including embedded assets and
native components. Keep unresolved coverage explicit until that comparison
is complete. No row in this report changes a package's approval status.
