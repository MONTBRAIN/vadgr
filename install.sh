#!/bin/sh
set -eu

VERSION=0.5.0
TERMS_VERSION=1.0
VERIFIER_SHA_X86_64=UNCONFIGURED
VERIFIER_SHA_AARCH64=UNCONFIGURED
ORIGIN=https://github.com/MONTBRAIN/vadgr/releases/download/v0.5.0
ACTION=install
ACCEPTED=

usage() {
  echo "Usage: install.sh [--source URL-or-directory] [--accept-terms 1.0] [--action install|repair|rollback|uninstall] [--delete-owner-state]"
}

DELETE_STATE=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source) [ "$#" -ge 2 ] || { usage >&2; exit 64; }; ORIGIN=$2; shift 2 ;;
    --accept-terms) [ "$#" -ge 2 ] || { usage >&2; exit 64; }; ACCEPTED=$2; shift 2 ;;
    --action) [ "$#" -ge 2 ] || { usage >&2; exit 64; }; ACTION=$2; shift 2 ;;
    --delete-owner-state) DELETE_STATE=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

if [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then :; else
  echo "This installer is for WSL. Native Linux uses the graphical AppImage installer." >&2
  exit 2
fi

case "$(uname -m)" in
  x86_64) ARCH=x86_64; VERIFIER_SHA=$VERIFIER_SHA_X86_64 ;;
  aarch64|arm64) ARCH=aarch64; VERIFIER_SHA=$VERIFIER_SHA_AARCH64 ;;
  *) echo "This WSL architecture is unsupported." >&2; exit 2 ;;
esac

[ "$VERIFIER_SHA" != UNCONFIGURED ] || { echo "The reviewed verifier hash is not configured. This candidate cannot install." >&2; exit 2; }

DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
ROOT="$DATA_HOME/vadgr"
VERSIONS="$ROOT/versions"
CURRENT="$ROOT/current"
BIN="$HOME/.local/bin/vadgr"
STATE_HOME=${XDG_STATE_HOME:-"$HOME/.local/state"}/vadgr

case "$ACTION" in
  rollback)
    [ -L "$CURRENT" ] || { echo "No active Vadgr generation was found." >&2; exit 1; }
    active=$(basename -- "$(readlink -- "$CURRENT")")
    active_backend="$CURRENT/bin/vadgr"
    candidate=
    for receipt in "$VERSIONS"/*/install-receipt.json; do
      [ -f "$receipt" ] || continue
      version=$(basename -- "$(dirname -- "$receipt")")
      [ "$version" = "$active" ] || candidate=$version
    done
    [ -n "$candidate" ] || { echo "No retained Vadgr generation is available." >&2; exit 1; }
    set -- "$VERSIONS/$candidate/cache/"Vadgr-*-wsl-"$ARCH".tar.gz
    [ "$#" -eq 1 ] && [ -f "$1" ] || { echo "The retained generation has no unique archive." >&2; exit 1; }
    "$active_backend" __verify-release-artifact \
      --manifest "$VERSIONS/$candidate/release-manifest.json" \
      --signature "$VERSIONS/$candidate/release-manifest.json.minisig" \
      --target "wsl-$ARCH" --artifact "$1"
    link="$ROOT/.current-$$"
    ln -s "versions/$candidate" "$link"
    mv -Tf "$link" "$CURRENT"
    if ! "$CURRENT/bin/vadgr" restart; then
      ln -s "versions/$active" "$link"
      mv -Tf "$link" "$CURRENT"
      "$CURRENT/bin/vadgr" start || true
      echo "The retained generation failed its health check. The prior generation remains active." >&2
      exit 1
    fi
    echo "Vadgr rolled back to $candidate."
    exit 0
    ;;
  uninstall)
    "$CURRENT/bin/vadgr" stop 2>/dev/null || true
    if [ "$DELETE_STATE" = true ]; then
      printf 'Type DELETE OWNER DATA to delete %s: ' "$STATE_HOME"
      IFS= read -r confirmation
      [ "$confirmation" = "DELETE OWNER DATA" ] || { echo "Owner data was preserved."; exit 1; }
      "$CURRENT/bin/vadgr" __purge-owner-state
    fi
    if [ -L "$BIN" ] && [ "$(readlink -- "$BIN")" = "$CURRENT/bin/vadgr" ]; then rm -f -- "$BIN"; fi
    rm -rf -- "$ROOT"
    echo "Vadgr package files were removed."
    exit 0
    ;;
  install|repair) ;;
  *) usage >&2; exit 64 ;;
esac

TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/vadgr-install.XXXXXXXX")
cleanup() { rm -rf -- "$TMP_ROOT"; }
trap cleanup EXIT HUP INT TERM

fetch() {
  name=$1
  destination=$2
  case "$ORIGIN" in
    https://*) curl --fail --location --proto '=https' --tlsv1.2 --output "$destination" "$ORIGIN/$name" ;;
    http://*) echo "An update origin must use HTTPS or a local directory." >&2; exit 2 ;;
    *) cp -- "$ORIGIN/$name" "$destination" ;;
  esac
}

MANIFEST="$TMP_ROOT/release-manifest.json"
SIGNATURE="$TMP_ROOT/release-manifest.json.minisig"
VERIFIER="$TMP_ROOT/vadgr-release-verify"
ARCHIVE_NAME="Vadgr-$VERSION-wsl-$ARCH.tar.gz"
ARCHIVE="$TMP_ROOT/$ARCHIVE_NAME"
if [ "$ACTION" = repair ]; then
  [ -L "$CURRENT" ] || { echo "No installed Vadgr generation is available to repair." >&2; exit 1; }
  cp -- "$CURRENT/release-manifest.json" "$MANIFEST"
  cp -- "$CURRENT/release-manifest.json.minisig" "$SIGNATURE"
  cp -- "$CURRENT/cache/vadgr-release-verify-$ARCH" "$VERIFIER"
  cp -- "$CURRENT/cache/$ARCHIVE_NAME" "$ARCHIVE"
else
  fetch release-manifest.json "$MANIFEST"
  fetch release-manifest.json.minisig "$SIGNATURE"
  fetch "vadgr-release-verify-$ARCH" "$VERIFIER"
  fetch "$ARCHIVE_NAME" "$ARCHIVE"
fi
printf '%s  %s\n' "$VERIFIER_SHA" "$VERIFIER" | sha256sum --check --status -
chmod 0755 "$VERIFIER"
"$VERIFIER" --manifest "$MANIFEST" --signature "$SIGNATURE" --target "wsl-$ARCH" >/dev/null
"$VERIFIER" --manifest "$MANIFEST" --signature "$SIGNATURE" --target "wsl-$ARCH" --artifact "$ARCHIVE" >/dev/null

PAYLOAD="$TMP_ROOT/payload"
mkdir "$PAYLOAD"
tar -xzf "$ARCHIVE" -C "$PAYLOAD" --no-same-owner --no-same-permissions
[ -x "$PAYLOAD/bin/vadgr" ] || { echo "The verified archive has no Vadgr executable." >&2; exit 1; }
[ -f "$PAYLOAD/legal/TERMS.txt" ] || { echo "The verified archive has no terms." >&2; exit 1; }

if [ "$ACTION" = install ]; then
  if [ "$ACCEPTED" != "$TERMS_VERSION" ]; then
    cat "$PAYLOAD/legal/TERMS.txt"
    if [ -t 0 ]; then
      printf '\nType ACCEPT %s to continue: ' "$TERMS_VERSION"
      IFS= read -r answer
      [ "$answer" = "ACCEPT $TERMS_VERSION" ] || { echo "Terms declined. Nothing was installed."; exit 1; }
    else
      echo "Non-interactive installation requires --accept-terms $TERMS_VERSION." >&2
      exit 2
    fi
  fi
fi

mkdir -p "$VERSIONS" "$(dirname -- "$BIN")"
previous=
[ ! -L "$CURRENT" ] || previous=$(readlink -- "$CURRENT")
generation="$VERSIONS/$VERSION"
staging="$ROOT/.stage-$$"
rm -rf -- "$staging"
mv -- "$PAYLOAD" "$staging"
cp -- "$MANIFEST" "$staging/release-manifest.json"
cp -- "$SIGNATURE" "$staging/release-manifest.json.minisig"
mkdir -p "$staging/cache"
cp -- "$ARCHIVE" "$staging/cache/$ARCHIVE_NAME"
cp -- "$VERIFIER" "$staging/cache/vadgr-release-verify-$ARCH"
cp -- "$0" "$staging/install.sh"

aside=
if [ -e "$generation" ]; then
  [ "$ACTION" = repair ] || { echo "This version is already installed. Use --action repair." >&2; exit 1; }
  "$CURRENT/bin/vadgr" stop 2>/dev/null || true
  aside="$ROOT/.previous-$$"
  mv -- "$generation" "$aside"
  mv -- "$staging" "$generation"
else
  mv -- "$staging" "$generation"
fi

link="$ROOT/.current-$$"
ln -s "versions/$VERSION" "$link"
mv -Tf "$link" "$CURRENT"
bin_link="$HOME/.local/bin/.vadgr-$$"
ln -s "$CURRENT/bin/vadgr" "$bin_link"
mv -Tf "$bin_link" "$BIN"

if ! "$CURRENT/bin/vadgr" restart; then
  if [ -n "$aside" ]; then rm -rf -- "$generation"; mv -- "$aside" "$generation"; fi
  if [ -n "$previous" ]; then
    ln -s "$previous" "$link"; mv -Tf "$link" "$CURRENT"; "$CURRENT/bin/vadgr" start || true
  else
    rm -f -- "$CURRENT" "$BIN"
    rm -rf -- "$generation"
  fi
  echo "The new generation failed its health check. The previous generation remains active." >&2
  exit 1
fi
if [ -n "$aside" ]; then rm -rf -- "$aside"; fi

if [ "$ACTION" = install ]; then
  "$CURRENT/bin/vadgr" __record-terms-acceptance --terms-version "$TERMS_VERSION" --installer-version "$VERSION" --terms-file "$CURRENT/legal/TERMS.txt" --installer-file "$CURRENT/cache/$ARCHIVE_NAME"
fi
"$CURRENT/bin/vadgr" __accept-release-sequence --manifest "$CURRENT/release-manifest.json" --signature "$CURRENT/release-manifest.json.minisig"
echo "Vadgr $VERSION is installed and healthy."
