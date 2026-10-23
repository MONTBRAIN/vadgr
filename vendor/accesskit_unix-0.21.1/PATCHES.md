# Local Linux accessibility patch

This is the published `accesskit_unix` 0.21.1 crate, with a bounded local
modification for Vadgr. It is not an unmodified upstream release.

- Archive: https://static.crates.io/crates/accesskit_unix/accesskit_unix-0.21.1.crate
- Original archive SHA-256: `b016ca8db0ea0ea2ceff29a9d6240391492d960716aa471967c00e8cc8cb197c`
- Upstream repository: https://github.com/AccessKit/accesskit
- Upstream commit: `f40dfc01a0c0e76de535969f82fb35e19513737d`
- Upstream path: `platforms/unix`

All files from the published archive are retained, including the original
manifest, lockfile and VCS record. No dependency version is changed.

## Modifications

`src/atspi/interfaces/editable_text.rs` adds the native D-Bus EditableText
interface. Whole-value replacement uses the common adapter's checked SetValue
dispatch. Unsupported clipboard and partial-edit methods explicitly report
that they are unsupported rather than claiming a successful edit.

`src/atspi/interfaces/mod.rs` exports that interface and `src/atspi/bus.rs`
registers/unregisters it with the existing node lifecycle. The implementation
is local and follows the neighboring original interface structure.

`PATCHES.md` is a local provenance addition. The complete file manifest is
external, under `packaging/rust-patches`, to avoid a self-referential hash.

## Retained licenses

The upstream declaration is `MIT OR Apache-2.0`. The shipped-source conclusion
is `Apache-2.0 AND MIT`, including the zbus-derived executor grant. Original
copyright and license headers remain; the executor is unchanged.

The following exact retained grant texts were added because the published
crate refers to repository-root files that are not inside its archive:

- `LICENSE-APACHE`: existing Linux legal notice
  `cargo-accesskit-unix-0.21.1/000-000-LICENSE-APACHE`.
- `LICENSE-MIT`: existing Linux legal notice
  `cargo-accesskit-unix-0.21.1/001-001-LICENSE-MIT`.
- `LICENSE.chromium`: existing Linux legal notice
  `cargo-accesskit-unix-0.21.1/002-002-LICENSE.chromium` (retained without changing
  the reviewed component license conclusion).

Those notice records remain under `packaging/inputs/linux-x86_64/legal/NOTICES`.
The external patch registry and source manifest bind the actual modified
source bytes separately from the original archive identity. Previous
unmodified-source delivery proofs do not prove this patched source.
