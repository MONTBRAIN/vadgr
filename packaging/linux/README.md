# Native Linux package

`build.sh` creates the unsigned AppDir and then the AppImage. The AppImage is
the graphical installer vehicle. It verifies the offline Minisign release
manifest before it enables installation. The installed generation lives below
`$XDG_DATA_HOME/vadgr`, or `$HOME/.local/share/vadgr` when that variable is not
set. The stable `current` link owns desktop, CLI and autostart launch.

The build intentionally fails while `packaging/release-public-key.txt` contains
`UNCONFIGURED`, or when the reviewed legal bundle, pinned AppImage tools, native
binary or private CUA payload is absent. Signing is a separate offline release
step; this directory contains no signing key and no unsigned fallback.
