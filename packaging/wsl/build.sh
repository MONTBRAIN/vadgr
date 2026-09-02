#!/bin/sh
set -eu

version=${1:-0.5.0}
arch=${2:-$(uname -m)}
[ "$version" = 0.5.0 ] || { echo "This archive source is only for 0.5.0." >&2; exit 2; }
case "$arch" in x86_64) target=x86_64-unknown-linux-gnu;; aarch64) target=aarch64-unknown-linux-gnu;; *) echo "Unsupported architecture." >&2; exit 2;; esac
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
[ -d "$repo/packaging/legal" ] || { echo "The generated legal bundle is missing." >&2; exit 2; }
[ -d "$repo/packaging/sbom" ] || { echo "The generated SBOM bundle is missing." >&2; exit 2; }
[ -f "$repo/packaging/README-OFFLINE.txt" ] || { echo "The offline README is missing." >&2; exit 2; }
[ -d "$repo/dist/payload" ] || { echo "The pinned private CUA payload is missing." >&2; exit 2; }

cargo build --locked --release --target "$target" --bin vadgr
cargo build --locked --release --features release-verifier --target "$target" --bin vadgr-release-verify
stage="$repo/target/package/wsl-$arch/payload"
rm -rf -- "$stage"
mkdir -p "$stage/bin" "$stage/legal" "$stage/sbom"
install -m 0755 "$repo/target/$target/release/vadgr" "$stage/bin/vadgr"
cp -R -- "$repo/dist/payload/." "$stage/"
cp -R -- "$repo/packaging/legal/." "$stage/legal/"
cp -R -- "$repo/packaging/sbom/." "$stage/sbom/"
cp -- "$repo/packaging/README-OFFLINE.txt" "$stage/README-OFFLINE.txt"
printf '%s\n' '{"schema":1,"version":"0.5.0","package_kind":"wsl-archive","product_code":null,"release_sequence":500,"manifest_sha256":null,"update_origin":"https://github.com/MONTBRAIN/vadgr/releases/latest/download"}' > "$stage/install-receipt.json"
tar -C "$stage" --sort=name --mtime='UTC 2020-01-01' --owner=0 --group=0 --numeric-owner -czf "$repo/target/package/Vadgr-$version-wsl-$arch.tar.gz" .
cp "$repo/target/$target/release/vadgr-release-verify" "$repo/target/package/vadgr-release-verify-$arch"
