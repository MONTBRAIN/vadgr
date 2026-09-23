#!/bin/sh
set -eu

version=${1:-0.5.0}
arch=${2:-$(uname -m)}
case "$version" in 0.5.0) ;; *) echo "This package source is only for 0.5.0." >&2; exit 2;; esac
case "$arch" in x86_64|aarch64) ;; *) echo "Unsupported Linux architecture: $arch" >&2; exit 2;; esac

repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)

: "${APPIMAGETOOL:?Set APPIMAGETOOL to the reviewed pinned appimagetool binary.}"
[ -x "$APPIMAGETOOL" ] || { echo "APPIMAGETOOL is not executable." >&2; exit 2; }
[ -d "$repo/dist/payload" ] || { echo "The pinned private CUA payload is missing." >&2; exit 2; }

case "$arch" in aarch64) rust_target=aarch64-unknown-linux-gnu;; *) rust_target=x86_64-unknown-linux-gnu;; esac
inputs="$repo/packaging/inputs/linux-$arch"
python3 "$repo/scripts/validate_package_inputs.py" --root "$inputs" --source-root "$repo" --version "$version" --target "$rust_target" \
  --payload-manifest "$repo/dist/payload/lib/cua/payload.json"
cargo build --locked --release --features native-gui --target "$rust_target" --bin vadgr
target="target/$rust_target/release"

work="$repo/target/package/linux-$arch"
appdir="$work/Vadgr.AppDir"
rm -rf -- "$appdir"
mkdir -p "$appdir/usr/bin" "$appdir/usr/lib" "$appdir/usr/share/metainfo" "$appdir/legal" "$appdir/sbom"
install -m 0755 "$repo/$target/vadgr" "$appdir/usr/bin/vadgr"
cp -R -- "$repo/dist/payload/." "$appdir/usr/"
cp -R -- "$inputs/legal/." "$appdir/legal/"
cp -R -- "$inputs/sbom/." "$appdir/sbom/"
cp -- "$inputs/README-OFFLINE.txt" "$appdir/README-OFFLINE.txt"
cp -- "$inputs/package-input-inventory.json" "$inputs/package-input-review.json" "$appdir/"
install -m 0755 "$repo/packaging/linux/AppRun" "$appdir/AppRun"
install -m 0644 "$repo/packaging/linux/com.montbrain.vadgr.desktop" "$appdir/com.montbrain.vadgr.desktop"
install -m 0644 "$repo/docs/pet.svg" "$appdir/com.montbrain.vadgr.svg"

output="$repo/target/package/Vadgr-$version-linux-$arch-installer.AppImage"
ARCH="$arch" "$APPIMAGETOOL" "$appdir" "$output"
printf '%s\n' "$output"
