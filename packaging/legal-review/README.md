# Upstream license source packets

These files are unreviewed source evidence for the Windows distribution. They
are not approved package inputs. `collection.json` binds each source archive to
its exact SHA-256 and preserves the original legal texts under `sources/`.
`unreviewed.spdx.json` deliberately records unresolved conclusions. It cannot
pass the package input validator or authorize signing.

The Cargo graph includes native GUI and bootstrapper dependencies, including
build dependencies. Review must distinguish compiled payload from build tools,
identify nested native libraries and assets, conclude licenses, reproduce all
required notices and resolve source distribution duties. A captured license
file alone does not close any of these obligations.

The Python wheel collector selects CPython 3.12 tags for the actual target,
evaluates Windows markers and accepts only hashes in the pinned requirements.
The Python runtime archive and Cargo archives must match their committed pins.
Cargo packages that omit legal texts use their embedded upstream Git commit
when an exact source repository is available. WiX archives are compared with
their upstream NuGet bytes and include the exact upstream source license.

Reproduce into a new, absent directory with Python 3.12, `packaging`, Cargo and
an authenticated GitHub CLI. WiX 7.0.0 packages must already be in the NuGet
cache. Run from the repository root:

```powershell
python scripts/collect_legal_sources.py --source-root . --output new-source-packet --cargo-home C:/path/to/.cargo --nuget-home C:/path/to/.nuget/packages --target x86_64-pc-windows-msvc
```

Use `aarch64-pc-windows-msvc` for ARM64. Downloaded archives are local cache
material, not committed legal files. Every failure remains in the collection
report. No command changes the review status to approved.

Source files preserve upstream bytes, including original whitespace and markup.
Git treats these copies as binary for diffs so it does not reinterpret license
formatting as whitespace defects or conflict markers. Each file remains readable
on disk, and its SHA-256 is recorded for direct review. Wheel metadata retains
its exact header block, including license fields, without unrelated README text.
