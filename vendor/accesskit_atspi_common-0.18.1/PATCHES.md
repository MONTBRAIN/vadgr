# Local Linux accessibility patch

This is the published `accesskit_atspi_common` 0.18.1 crate, with a bounded
local modification for Vadgr. It is not an unmodified upstream release.

- Archive: https://static.crates.io/crates/accesskit_atspi_common/accesskit_atspi_common-0.18.1.crate
- Original archive SHA-256: `1e8c61bee90b42a772d39d06a740207dc71a4e780004ace1db8d99fb1baaa954`
- Upstream repository: https://github.com/AccessKit/accesskit
- Upstream commit: `f40dfc01a0c0e76de535969f82fb35e19513737d`
- Upstream path: `platforms/atspi-common`

All files from the published archive are retained, including the original
manifest, lockfile and VCS record. No dependency version is changed.

## Modifications

`src/node.rs` corrects disabled AT-SPI state and click-action exposure/dispatch,
and exposes native EditableText whole-value replacement only for enabled,
writable text nodes advertising AccessKit SetValue. It includes focused
regressions for these mappings and action guards. The local changes use the
existing AccessKit tree and action path; they do not bypass application checks.

`PATCHES.md` is a local provenance addition. The complete file manifest is
external, under `packaging/rust-patches`, to avoid a self-referential hash.

## Retained licenses

The upstream declaration is `MIT OR Apache-2.0`. The shipped-source conclusion
is `Apache-2.0 AND BSD-3-Clause`, retaining the Chromium-derived source grants.
Original copyright headers remain in the modified file.

The following exact retained grant texts were added because the published
crate refers to repository-root files that are not inside its archive:

- `LICENSE-APACHE`: existing Linux legal notice
  `cargo-accesskit-atspi-common-0.18.1/000-000-LICENSE-APACHE`.
- `LICENSE-MIT`: existing Linux legal notice
  `cargo-accesskit-atspi-common-0.18.1/001-001-LICENSE-MIT`.
- `LICENSE.chromium`: existing Linux legal notice
  `cargo-accesskit-atspi-common-0.18.1/002-002-LICENSE.chromium`.

Those notice records remain under `packaging/inputs/linux-x86_64/legal/NOTICES`.
The external patch registry and source manifest bind the actual modified
source bytes separately from the original archive identity. Previous
unmodified-source delivery proofs do not prove this patched source.
