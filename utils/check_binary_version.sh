#!/usr/bin/env bash
set -euo pipefail
VERSION=$(cat VERSION)
OUTPUT=$(./five-clis --version 2>&1)
if ! echo "${OUTPUT}" | grep -q "${VERSION}"; then
    echo "Binary version mismatch. Expected: ${VERSION}, got: ${OUTPUT}" >&2
    exit 1
fi
echo "Binary version OK: ${OUTPUT}"
