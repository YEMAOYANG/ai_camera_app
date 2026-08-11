#!/usr/bin/env bash
# Install the pinned local-development go2rtc binary outside the repository.
#
# Usage:
#   ./scripts/install-go2rtc.sh
#   ./scripts/install-go2rtc.sh /absolute/path/to/go2rtc-v1.9.14

set -euo pipefail

VERSION="1.9.14"
DEFAULT_DEST="/tmp/guardian-dev/bin/go2rtc-v${VERSION}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

case "${1:-}" in
  --help|-h)
    echo "Usage: ./scripts/install-go2rtc.sh [/absolute/path/to/go2rtc-v${VERSION}]"
    exit 0
    ;;
esac
if [ $# -gt 1 ]; then
  echo "Only one optional destination path is supported." >&2
  exit 1
fi

DEST="${1:-$DEFAULT_DEST}"
case "$DEST" in
  /*) ;;
  *)
    echo "Destination must be an absolute path outside the repository." >&2
    exit 1
    ;;
esac
case "$DEST" in
  "$BACKEND_DIR"/*)
    echo "Refusing to install a media binary inside the repository." >&2
    exit 1
    ;;
esac

OS="$(uname -s)"
ARCH="$(uname -m)"
ASSET=""
SHA256=""
ARCHIVE_KIND="binary"

case "${OS}/${ARCH}" in
  Darwin/arm64)
    ASSET="go2rtc_mac_arm64.zip"
    SHA256="919b78adc759d6b3883d1e1b2ac915ac0985bb903ff1897b4d228527bd64690c"
    ARCHIVE_KIND="zip"
    ;;
  Darwin/x86_64)
    ASSET="go2rtc_mac_amd64.zip"
    SHA256="9b0b9a27a4dc3a5b8b93376e7e8fc2787c6af624a512842622be84aec0171c7a"
    ARCHIVE_KIND="zip"
    ;;
  Linux/aarch64|Linux/arm64)
    ASSET="go2rtc_linux_arm64"
    SHA256="359fabade8a7a51e81a55fe6df6b0ef81764a5e1d63179577534eaaa71904b50"
    ;;
  Linux/x86_64|Linux/amd64)
    ASSET="go2rtc_linux_amd64"
    SHA256="32d616af226bd731678ffde328b94cfb94e30339bfefc469cfb76323144615a6"
    ;;
  *)
    echo "Unsupported platform: ${OS}/${ARCH}" >&2
    exit 1
    ;;
esac

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi
if [ "$ARCHIVE_KIND" = "zip" ] && ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required for the macOS release archive." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

DOWNLOAD="$TMP_DIR/$ASSET"
PAYLOAD="$TMP_DIR/go2rtc"
URL="https://github.com/AlexxIT/go2rtc/releases/download/v${VERSION}/${ASSET}"

echo "Downloading go2rtc v${VERSION} for ${OS}/${ARCH}..."
curl --fail --location --proto '=https' --tlsv1.2 "$URL" --output "$DOWNLOAD"

if command -v shasum >/dev/null 2>&1; then
  ACTUAL_SHA256="$(shasum -a 256 "$DOWNLOAD" | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA256="$(sha256sum "$DOWNLOAD" | awk '{print $1}')"
else
  echo "shasum or sha256sum is required to verify the download." >&2
  exit 1
fi

if [ "$ACTUAL_SHA256" != "$SHA256" ]; then
  echo "Checksum verification failed for $ASSET." >&2
  exit 1
fi

if [ "$ARCHIVE_KIND" = "zip" ]; then
  unzip -p "$DOWNLOAD" > "$PAYLOAD"
else
  cp "$DOWNLOAD" "$PAYLOAD"
fi

mkdir -p "$(dirname "$DEST")"
install -m 0755 "$PAYLOAD" "$DEST"

VERSION_OUTPUT="$("$DEST" -version 2>&1 || true)"
case "$VERSION_OUTPUT" in
  *"version ${VERSION}"*) ;;
  *)
    echo "Installed binary did not report go2rtc v${VERSION}: $VERSION_OUTPUT" >&2
    exit 1
    ;;
esac

echo "Installed: $DEST"
echo "Set APP_MEDIA_GATEWAY_BINARY=$DEST"
