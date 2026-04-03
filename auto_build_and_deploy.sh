#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST="${HOST:-192.168.122.1}"
REMOTE_USER="${REMOTE_USER:-zhuxb}"
REMOTE_DIR="${REMOTE_DIR:-/home/${REMOTE_USER}/renpy-dev}"

PLATFORMS="${PLATFORMS:-linux,windows}"
ARCHS="${ARCHS:-x86_64}"
PYTHONS="${PYTHONS:-3}"
PACKAGE_DIR="${PACKAGE_DIR:-${ROOT}/tmp/packages}"

mkdir -p "$PACKAGE_DIR"

echo "[0/4] Removing old package artifacts from $PACKAGE_DIR"
find "$PACKAGE_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

echo "[0.5/4] Clearing cached Python dependency packaging tasks"
find "$ROOT/tmp/complete" -maxdepth 1 \( -name 'pip-python3.*' -o -name 'python3-pythonlib.py3' \) -delete 2>/dev/null || true

MARKER="$(mktemp)"
trap 'rm -f "$MARKER"' EXIT
touch "$MARKER"

cd "$ROOT"

echo "[1/4] Building and packaging for platforms: $PLATFORMS"
./build.sh \
    --platforms "$PLATFORMS" \
    --archs "$ARCHS" \
    --pythons "$PYTHONS" \
    --package \
    --package-dir "$PACKAGE_DIR" \
    "$@"

mapfile -t ARCHIVES < <(find "$PACKAGE_DIR" -maxdepth 1 -type f -name '*.tar.gz' -newer "$MARKER" | sort)

if [[ ${#ARCHIVES[@]} -eq 0 ]]; then
    echo "No new archives were produced in $PACKAGE_DIR" >&2
    exit 1
fi

echo "[2/4] Preparing remote directory: ${REMOTE_USER}@${HOST}:${REMOTE_DIR}"
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${REMOTE_USER}@${HOST}" "mkdir -p '${REMOTE_DIR}'"

echo "[3/4] Uploading ${#ARCHIVES[@]} archive(s)"
for archive in "${ARCHIVES[@]}"; do
    remote_name="$(basename "$archive")"

    case "$remote_name" in
        renpy-linux.tar.gz|renpy-linux-x86_64-*.tar.gz)
            remote_name="renpy-linux.tar.gz"
            ;;
    esac

    echo "Uploading $(basename "$archive") as $remote_name"
    scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$archive" "${REMOTE_USER}@${HOST}:${REMOTE_DIR}/${remote_name}"
done

echo "[4/4] Remote files"
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${REMOTE_USER}@${HOST}" "ls -lh '${REMOTE_DIR}'"

echo "Deployment complete."
