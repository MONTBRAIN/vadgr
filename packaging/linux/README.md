# Native Linux package

`build.sh` creates the unsigned AppDir and then the AppImage. The AppImage is
the graphical installer vehicle. It verifies the offline keyless attestation
bundle for the release manifest against its pinned trust policy
manifest before it enables installation. The installed generation lives below
`$XDG_DATA_HOME/vadgr`, or `$HOME/.local/share/vadgr` when that variable is not
set. The stable `current` link owns desktop, CLI and autostart launch.

The build intentionally fails when the reviewed legal bundle, pinned AppImage
tools, native binary or private CUA payload is absent. The protected release
workflow attests the exact manifest after final artifacts are held. This
directory contains no release signing key or unsigned installation fallback.

## Unsigned development preparation

An open implementation branch prepares its private runtime before Linux package
review. Use a clean committed checkout and a new output directory outside it.
Materialize the reviewed wheelhouse with `scripts/cua_wheelhouse.py`, selecting
`x86_64-unknown-linux-gnu` and `linux-x86_64` on an x86_64 Linux host. This step
may use read-only GitHub authentication to retrieve the pinned CUA artifacts.
Clear GitHub, signing and identity credentials before compilation.

```sh
python3 scripts/prepare_unsigned_linux.py prepare \
  --source-commit <exact-40-character-commit> --architecture x86_64 \
  --wheelhouse <verified-wheelhouse> --preparation <new-output-directory>
```

The producer uses the final workflow's pinned Rust toolchain and the reviewed
Linux CUA profile. Install that toolchain before the command. The output retains
the native executable, private Python/CUA payload, and a canonical receipt with
every file digest, mode and relative link. The receipt identifies the source
commit, source tree, platform and architecture. Preparation does not create
legal approval. Failed attempts remain available for diagnosis.

The install-only Python archive omits the producer's native-library license
metadata. `scripts/inspect_python_runtime_licenses.py` accepts that pinned
archive and the matching full producer archive with its independently verified
SHA-256. It requires every install-only file, mode and link to match the full
archive's installation subtree before retaining `PYTHON.json` and license files.
Extra producer tests and build libraries are counted separately. The observation
does not approve redistribution or establish which native libraries are shipped.

After the exact Linux package-input packet is reviewed and committed, prepare
again at that commit and build the registered AppImage:

```sh
python3 scripts/prepare_unsigned_linux.py package \
  --source-commit <exact-40-character-commit> --architecture x86_64 \
  --preparation <matching-output-directory> --appimagetool <pinned-executable> \
  --runtime <pinned-AppImage-runtime>
```

Packaging rechecks every prepared byte and the appimagetool digest. It verifies
the runtime's exact size, SHA-256 and architecture against `runtime.json`, then
passes it explicitly with `--runtime-file`. The AppImage tool must not download
an untracked runtime implicitly. Direct `build.sh` callers set `APPIMAGE_RUNTIME`
to these same verified bytes; the candidate builder retrieves the immutable
asset ID in the pin. Runtime pinning is not native E2E qualification. The producer invokes
the final package builder and its existing approved-input validator. The
AppImage keeps the registered filename. Its adjacent `.development.json`
receipt records its size, SHA-256 and full AppDir inventory. Both receipts mark
the output as development and nonpublishable, with signing disabled and no
attestation. These receipts cannot replace the protected release manifest.
Use `aarch64` with its corresponding native target/profile only on an aarch64
Linux host. Preparation and packaging do not establish desktop E2E results.

The registered x86_64 producer uses Ubuntu 24.04. The
`unsigned-linux-preparation.yml` workflow builds the exact feature commit on
that native runner with read-only acquisition and no signing credentials. It
retains preparation observations while reviewed package inputs are absent;
once they exist, their validation must succeed before the AppImage is built.
CI production is not a native desktop E2E pass. Download and verify the retained
bytes before exercising them on the qualification host.

A newer Linux workstation can prepare diagnostic inputs but must not raise the
registered package baseline. Packaging rejects a binary requiring GLIBC newer
than 2.39, the Ubuntu 24.04 producer baseline, or private/unknown GLIBC versions.
For example, the Ubuntu 26.04 build's GLIBC 2.43 math symbols make that binary
preparation-only. Do not qualify it as the release-equivalent installer.
