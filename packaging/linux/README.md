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
