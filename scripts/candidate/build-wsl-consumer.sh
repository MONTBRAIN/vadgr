#!/bin/sh
# Build the exact WSL runtime used to compare and finalize the shared CUA helper.
# This is not a WSL installation vehicle and carries no package approval claim.
set -eu
[ -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}${ES_USERNAME:-}${ES_PASSWORD:-}${ES_TOTP_SECRET:-}${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ] || {
  echo 'Consumer build must have no GitHub, signing or identity credential.' >&2; exit 2;
}
target=$1
source=$2
output=$3
wheelhouse=$4
trusted=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
case "$target" in
  wsl-x86_64) rust_target=x86_64-unknown-linux-gnu;;
  wsl-aarch64) rust_target=aarch64-unknown-linux-gnu;;
  *) echo 'Unsupported WSL consumer target.' >&2; exit 2;;
esac
[ ! -e "$output" ] || { echo 'Consumer output must not exist.' >&2; exit 2; }
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
mkdir -p "$output"
output=$(CDPATH= cd -- "$output" && pwd)
cd "$source"
[ ! -f E2E/0.5.0/e2e.md ] || { echo 'Unsealed runbook input refused.' >&2; exit 2; }
python3 "$trusted/scripts/cua_wheelhouse.py" --source "$PWD" --target "$rust_target" --release-profile "$target" --verify "$wheelhouse"
export VADGR_RELEASE_PROFILE="$target"
export VADGR_RELEASE_PAYLOAD_BUILD=1
export SOURCE_DATE_EPOCH=1609459200
export RUSTFLAGS="--remap-path-prefix=$PWD=/vadgr-source"
cargo build --locked --release --target "$rust_target" --bin vadgr
payload_root="$RUNNER_TEMP/vadgr-wsl-consumer-payload"
"target/$rust_target/release/vadgr" __payload-setup --install-root "$payload_root" --payload-only --wheelhouse "$wheelhouse"
python3 "$trusted/scripts/distribution_matrix.py" binary --target "$target" --file "target/$rust_target/release/vadgr"
python3 "$trusted/scripts/distribution_matrix.py" payload --target "$target" --root "$payload_root" --pins packaging/cua/pins.toml
runtime="$output/runtime"
mkdir -p "$runtime/bin"
install -m 0755 "target/$rust_target/release/vadgr" "$runtime/bin/vadgr"
cp -R "$payload_root/." "$runtime/"
python3 "$trusted/scripts/distribution_matrix.py" binary --target "$target" --file "$runtime/bin/vadgr"
python3 "$trusted/scripts/distribution_matrix.py" payload --target "$target" --root "$runtime" --pins packaging/cua/pins.toml
printf '%s\n' 'WSL helper consumer built and checked. This is not an installable or publishable vehicle.'
