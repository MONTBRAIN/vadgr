#!/bin/sh
# Secret-free native builds. Source is the sealed materialization, never signing tooling.
set -eu
[ -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}${ES_USERNAME:-}${ES_PASSWORD:-}${ES_TOTP_SECRET:-}${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ] || {
  echo 'Source build must have no GitHub, signing or identity credential.' >&2; exit 2;
}
target=$1
source=$2
output=$3
wheelhouse=$4
trusted=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
case "$target" in macos-*|linux-*|wsl-*) ;; *) echo 'Unsupported native build target.' >&2; exit 2;; esac
[ ! -e "$output" ] || { echo 'Build output must not exist.' >&2; exit 2; }
mkdir -p "$output"
output=$(CDPATH= cd -- "$output" && pwd)
cd "$source"
[ ! -f E2E/0.5.0/e2e.md ] || { echo 'Unsealed runbook input refused.' >&2; exit 2; }
arch=${target#*-}
platform=${target%%-*}
case "$target" in
  macos-aarch64) package_arch=arm64; rust_target=aarch64-apple-darwin;;
  macos-x86_64) package_arch=x86_64; rust_target=x86_64-apple-darwin;;
  *) package_arch=$arch; rust_target=$arch-unknown-linux-gnu;;
esac
python3 "$trusted/scripts/cua_wheelhouse.py" --source "$PWD" --target "$rust_target" --verify "$wheelhouse"
export VADGR_RELEASE_PAYLOAD_BUILD=1
export SOURCE_DATE_EPOCH=1609459200
export RUSTFLAGS="--remap-path-prefix=$PWD=/vadgr-source"
payload_root="$RUNNER_TEMP/vadgr-payload"
if [ "$platform" = macos ]; then
  cargo build --locked --release --features macos-cua-host --target "$rust_target" --bin vadgr --bin vadgr-cua-host
  payload_bundle="$payload_root/Vadgr.app"
  payload_root="$payload_bundle/Contents/Resources"
  host="$payload_bundle/Contents/Library/LoginItems/Vadgr Computer Use.app/Contents/MacOS/vadgr-cua-host"
  mkdir -p "$(dirname -- "$host")"
  install -m 0755 "target/$rust_target/release/vadgr-cua-host" "$host"
else
  cargo build --locked --release --target "$rust_target" --bin vadgr
fi
"target/$rust_target/release/vadgr" __payload-setup --install-root "$payload_root" --payload-only --wheelhouse "$wheelhouse"
python3 "$trusted/scripts/distribution_matrix.py" binary --target "$target" --file "target/$rust_target/release/vadgr"
python3 "$trusted/scripts/distribution_matrix.py" payload --target "$target" --root "$payload_root" --pins packaging/cua/pins.toml
mkdir -p dist/payload
cp -R "$payload_root/lib" dist/payload/
if [ "$platform" = linux ]; then
  tool="$RUNNER_TEMP/appimagetool"
  id=$(python3 -c 'import json,sys; print(json.load(open("packaging/toolchain.json"))["appimagetool"][sys.argv[1]]["asset_id"])' "$arch")
  digest=$(python3 -c 'import json,sys; print(json.load(open("packaging/toolchain.json"))["appimagetool"][sys.argv[1]]["sha256"])' "$arch")
  curl --fail --location --proto '=https' --tlsv1.2 -H 'Accept: application/octet-stream' \
    "https://api.github.com/repos/AppImage/appimagetool/releases/assets/$id" -o "$tool"
  printf '%s  %s\n' "$digest" "$tool" | sha256sum --check --strict -
  chmod 0755 "$tool"
  export APPIMAGETOOL="$tool" APPIMAGE_EXTRACT_AND_RUN=1
fi
sh "packaging/$platform/build.sh" 0.5.0 "$package_arch"
case "$platform" in
  macos)
    vehicle="target/package/Vadgr-0.5.0-macos-$package_arch-unsigned.pkg"
    expanded="$RUNNER_TEMP/vadgr-package-expanded"
    pkgutil --expand-full "$vehicle" "$expanded"
    distribution="$expanded/Distribution"
    grep -q "hostArchitectures=\"$package_arch\"" "$distribution"
    installed=$(find "$expanded" -path '*/Applications/Vadgr.app/Contents/MacOS/vadgr' -type f -print)
    [ -n "$installed" ]
    python3 "$trusted/scripts/distribution_matrix.py" binary --target "$target" --file "$installed"
    cp "target/package/Vadgr-0.5.0-macos-$package_arch-unsigned-root.tar.gz" "$output/"
    ;;
  linux)
    vehicle="target/package/Vadgr-0.5.0-linux-$arch-installer.AppImage"
    python3 "$trusted/scripts/distribution_matrix.py" binary --target "$target" --file "$vehicle"
    expanded="$RUNNER_TEMP/vadgr-appimage-expanded"
    mkdir "$expanded"
    absolute_vehicle="$PWD/$vehicle"
    (cd "$expanded" && "$absolute_vehicle" --appimage-extract >/dev/null)
    python3 "$trusted/scripts/distribution_matrix.py" binary --target "$target" --file "$expanded/squashfs-root/usr/bin/vadgr"
    python3 "$trusted/scripts/distribution_matrix.py" payload --target "$target" --root "$expanded/squashfs-root/usr" --pins packaging/cua/pins.toml
    ;;
  wsl)
    vehicle="target/package/Vadgr-0.5.0-wsl-$arch.tar.gz"
    expanded="$RUNNER_TEMP/vadgr-wsl-expanded"
    mkdir "$expanded"
    # This archive was built in this secret-free process. The installer separately
    # enforces untrusted archive safety before it can install released bytes.
    tar -xzf "$vehicle" -C "$expanded"
    python3 "$trusted/scripts/distribution_matrix.py" binary --target "$target" --file "$expanded/bin/vadgr"
    python3 "$trusted/scripts/distribution_matrix.py" payload --target "$target" --root "$expanded" --pins packaging/cua/pins.toml
    if [ "$arch" = x86_64 ]; then key=VERIFIER_SHA_X86_64; else key=VERIFIER_SHA_AARCH64; fi
    expected=$(sed -n "s/^$key=//p" install.sh)
    printf '%s  %s\n' "$expected" "target/package/vadgr-release-verify-$arch" | sha256sum --check --strict -
    cp "target/package/vadgr-release-verify-$arch" "$output/"
    ;;
esac
cp "$vehicle" "$output/"
echo "Native $target package built and architecture checked. This is unsigned development output."
