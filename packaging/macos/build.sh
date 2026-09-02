#!/bin/sh
set -eu

version=${1:-0.5.0}
arch=${2:-$(uname -m)}
[ "$version" = 0.5.0 ] || { echo "This package source is only for 0.5.0." >&2; exit 2; }
case "$arch" in x86_64|arm64) ;; *) echo "Unsupported macOS architecture: $arch" >&2; exit 2;; esac

repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
[ "$(tr -d '\r\n' < "$repo/packaging/release-public-key.txt")" != UNCONFIGURED ] || { echo "The reviewed release public key is not configured." >&2; exit 2; }
[ -d "$repo/packaging/legal" ] || { echo "The generated legal bundle is missing." >&2; exit 2; }
[ -d "$repo/packaging/sbom" ] || { echo "The generated SBOM bundle is missing." >&2; exit 2; }
[ -f "$repo/packaging/README-OFFLINE.txt" ] || { echo "The offline README is missing." >&2; exit 2; }
[ -d "$repo/dist/payload" ] || { echo "The pinned private CUA payload is missing." >&2; exit 2; }

case "$arch" in arm64) rust_target=aarch64-apple-darwin;; *) rust_target=x86_64-apple-darwin;; esac
cargo build --locked --release --features native-gui,macos-cua-host --target "$rust_target" --bin vadgr --bin vadgr-app --bin vadgr-cua-host

work="$repo/target/package/macos-$arch"
root="$work/root"
app="$root/Applications/Vadgr.app"
cua="$app/Contents/Library/LoginItems/Vadgr Computer Use.app"
rm -rf -- "$root"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/legal" "$app/Contents/Resources/sbom" "$app/Contents/Resources/lib" "$app/Contents/Library/LaunchAgents" "$app/Contents/Helpers" "$cua/Contents/MacOS"
cp "$repo/packaging/macos/Vadgr-Info.plist" "$app/Contents/Info.plist"
cp "$repo/packaging/macos/CuaHost-Info.plist" "$cua/Contents/Info.plist"
install -m 0755 "$repo/target/$rust_target/release/vadgr" "$app/Contents/MacOS/vadgr"
install -m 0755 "$repo/target/$rust_target/release/vadgr-app" "$app/Contents/MacOS/vadgr-app"
install -m 0755 "$repo/target/$rust_target/release/vadgr-cua-host" "$cua/Contents/MacOS/vadgr-cua-host"
cp -R -- "$repo/dist/payload/." "$app/Contents/Resources/"
cp -R -- "$repo/packaging/legal/." "$app/Contents/Resources/legal/"
cp -R -- "$repo/packaging/sbom/." "$app/Contents/Resources/sbom/"
cp -- "$repo/packaging/README-OFFLINE.txt" "$app/Contents/Resources/README-OFFLINE.txt"
cp "$repo/packaging/macos/com.montbrain.vadgr.agent.plist" "$app/Contents/Library/LaunchAgents/"
install -m 0755 "$repo/packaging/macos/vadgr-lifecycle" "$app/Contents/Helpers/vadgr-lifecycle"
swiftc "$repo/packaging/macos/LoginItemController.swift" -o "$app/Contents/Helpers/vadgr-login-item"
mkdir -p "$root/usr/local/bin"
ln -s /Applications/Vadgr.app/Contents/MacOS/vadgr "$root/usr/local/bin/vadgr"
printf '%s\n' '{"schema":1,"version":"0.5.0","package_kind":"pkg","product_code":null,"release_sequence":500,"manifest_sha256":null,"update_origin":"https://github.com/MONTBRAIN/vadgr/releases/latest/download","publisher":null,"rollback_vehicle":"previous.pkg"}' > "$app/Contents/MacOS/install-receipt.json"

resources="$work/resources"
rm -rf -- "$resources"
mkdir -p "$resources"
cp -- "$repo/packaging/macos/resources/WELCOME.txt" "$resources/WELCOME.txt"
cp -- "$repo/packaging/macos/resources/CONCLUSION.txt" "$resources/CONCLUSION.txt"
cp -- "$repo/packaging/legal/TERMS.txt" "$resources/TERMS.txt"

component="$work/Vadgr-component.pkg"
unsigned="$repo/target/package/Vadgr-$version-macos-$arch-unsigned.pkg"
root_archive="$repo/target/package/Vadgr-$version-macos-$arch-unsigned-root.tar.gz"
pkgbuild --root "$root" --identifier com.montbrain.vadgr.pkg --version "$version" \
  --install-location / --scripts "$repo/packaging/macos/scripts" "$component"
productbuild --distribution "$repo/packaging/macos/Distribution.xml" \
  --resources "$resources" --package-path "$work" "$unsigned"
COPYFILE_DISABLE=1 tar -C "$root" -czf "$root_archive" .

printf '%s\n' "$unsigned"
printf '%s\n' "$root_archive"
echo "Signing, notarization, stapling and final package verification run only in the protected release job."
