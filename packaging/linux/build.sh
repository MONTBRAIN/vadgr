#!/bin/sh
set -eu

version=${1:-0.5.0}
arch=${2:-$(uname -m)}
case "$version" in 0.5.0) ;; *) echo "This package source is only for 0.5.0." >&2; exit 2;; esac
case "$arch" in x86_64|aarch64) ;; *) echo "Unsupported Linux architecture: $arch" >&2; exit 2;; esac

repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
public_key=$(tr -d '\r\n' < "$repo/packaging/release-public-key.txt")
[ "$public_key" != UNCONFIGURED ] || { echo "The reviewed release public key is not configured." >&2; exit 2; }

: "${APPIMAGETOOL:?Set APPIMAGETOOL to the reviewed pinned appimagetool binary.}"
[ -x "$APPIMAGETOOL" ] || { echo "APPIMAGETOOL is not executable." >&2; exit 2; }
[ -d "$repo/packaging/legal" ] || { echo "The generated legal bundle is missing." >&2; exit 2; }
[ -d "$repo/packaging/sbom" ] || { echo "The generated SBOM bundle is missing." >&2; exit 2; }
[ -f "$repo/packaging/README-OFFLINE.txt" ] || { echo "The offline README is missing." >&2; exit 2; }
[ -d "$repo/dist/payload" ] || { echo "The pinned private CUA payload is missing." >&2; exit 2; }

case "$arch" in aarch64) rust_target=aarch64-unknown-linux-gnu;; *) rust_target=x86_64-unknown-linux-gnu;; esac
cargo build --locked --release --features native-gui --target "$rust_target" --bin vadgr
target="target/$rust_target/release"

work="$repo/target/package/linux-$arch"
appdir="$work/Vadgr.AppDir"
rm -rf -- "$appdir"
mkdir -p "$appdir/usr/bin" "$appdir/usr/lib" "$appdir/usr/share/metainfo" "$appdir/legal" "$appdir/sbom"
install -m 0755 "$repo/$target/vadgr" "$appdir/usr/bin/vadgr"
cp -R -- "$repo/dist/payload/." "$appdir/usr/"
cp -R -- "$repo/packaging/legal/." "$appdir/legal/"
cp -R -- "$repo/packaging/sbom/." "$appdir/sbom/"
cp -- "$repo/packaging/README-OFFLINE.txt" "$appdir/README-OFFLINE.txt"
install -m 0755 "$repo/packaging/linux/AppRun" "$appdir/AppRun"
install -m 0644 "$repo/packaging/linux/com.montbrain.vadgr.desktop" "$appdir/com.montbrain.vadgr.desktop"

output="$repo/target/package/Vadgr-$version-linux-$arch-installer.AppImage"
ARCH="$arch" "$APPIMAGETOOL" "$appdir" "$output"
printf '%s\n' "$output"
