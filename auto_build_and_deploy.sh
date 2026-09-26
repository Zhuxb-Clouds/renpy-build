#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# uv (and other per-user tools) live outside the default PATH of
# non-interactive shells, e.g. when the script is run under nohup/ssh.
export PATH="$HOME/.local/bin:$PATH"

HOST="${HOST:-192.168.122.1}"
REMOTE_USER="${REMOTE_USER:-zhuxb}"
REMOTE_DIR="${REMOTE_DIR:-/home/${REMOTE_USER}/renpy-dev}"

PLATFORMS="${PLATFORMS:-linux,windows,mac}"
ARCHS="${ARCHS:-x86_64,arm64}"
PYTHONS="${PYTHONS:-3}"
PACKAGE_DIR="${PACKAGE_DIR:-${ROOT}/tmp/packages}"
PACKAGE_NAME="${PACKAGE_NAME:-renpy-$(date +%Y%m%d)}"
PACKAGE_FILE="${PACKAGE_DIR}/${PACKAGE_NAME}.tar.gz"
KEEP_PACKAGES="${KEEP_PACKAGES:-3}"
SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

has_csv_item() {
    local value="$1"
    local needle="$2"
    [[ ",${value}," == *",${needle},"* ]]
}

mac_sdk_archive=""

if [[ -f "$ROOT/tars/MacOSX12.3.sdk.tar.bz2" ]]; then
    mac_sdk_archive="$ROOT/tars/MacOSX12.3.sdk.tar.bz2"
elif [[ -f "$ROOT/tars/MacOSX12.3.sdk.tar.xz" ]]; then
    mac_sdk_archive="$ROOT/tars/MacOSX12.3.sdk.tar.xz"
fi

mkdir -p "$PACKAGE_DIR"

if has_csv_item "$PLATFORMS" "mac"; then
    if [[ -z "$mac_sdk_archive" ]]; then
        echo "mac platform requested, but missing SDK archive: $ROOT/tars/MacOSX12.3.sdk.tar.bz2 or $ROOT/tars/MacOSX12.3.sdk.tar.xz" >&2
        echo "Please place one of those SDK archives in tars/ before running full desktop build." >&2
        exit 2
    fi

    if ! has_csv_item "$ARCHS" "x86_64" || ! has_csv_item "$ARCHS" "arm64"; then
        echo "mac platform requested, but ARCHS must include both x86_64 and arm64 to produce py3-mac-universal." >&2
        echo "Current ARCHS: $ARCHS" >&2
        exit 2
    fi
fi

echo "[0/5] Removing old package artifacts from $PACKAGE_DIR"
find "$PACKAGE_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

echo "[0.5/5] Clearing cached Python dependency packaging tasks"
find "$ROOT/tmp/complete" -maxdepth 1 \( -name 'pip-python3.*' -o -name 'python3-pythonlib.py3' \) -delete 2>/dev/null || true

cd "$ROOT"

echo "[1/5] Building runtimes for platforms: $PLATFORMS"
./build.sh \
    --platforms "$PLATFORMS" \
    --archs "$ARCHS" \
    --pythons "$PYTHONS" \
    "$@"

echo "[2/5] Packing build outputs into $(basename "$PACKAGE_FILE")"
rm -f "$PACKAGE_FILE"
# Exclude patterns must match the member names as stored in the archive
# (relative to -C "$ROOT"): renpy/.git, renpy/.venv, renpy/.vscode.
tar --exclude="renpy/.git" --exclude="renpy/.venv" --exclude="renpy/.vscode" -C "$ROOT" -czf "$PACKAGE_FILE" renpy

if [[ ! -f "$PACKAGE_FILE" ]]; then
    echo "Failed to create archive: $PACKAGE_FILE" >&2
    exit 1
fi

echo "[3/5] Preparing remote directory: ${REMOTE_USER}@${HOST}:${REMOTE_DIR}"
ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${HOST}" "mkdir -p '${REMOTE_DIR}'"

echo "[4/5] Uploading $(basename "$PACKAGE_FILE") (resumable rsync)"
rsync --partial --times -e "ssh ${SSH_OPTS[*]}" "$PACKAGE_FILE" "${REMOTE_USER}@${HOST}:${REMOTE_DIR}/"

echo "[4.5/5] Pruning old packages on remote (keeping newest ${KEEP_PACKAGES})"
# No rsync --delete on purpose: REMOTE_DIR also holds the extracted renpy/ tree,
# so retention must only touch renpy-*.tar.gz files.
ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${HOST}" \
    "cd '${REMOTE_DIR}' && ls -1 renpy-*.tar.gz 2>/dev/null | sort | head -n -${KEEP_PACKAGES} | xargs -r rm -f --"

echo "[5/5] Remote files"
ssh "${SSH_OPTS[@]}" "${REMOTE_USER}@${HOST}" "ls -lh '${REMOTE_DIR}'"

echo "Deployment complete."
