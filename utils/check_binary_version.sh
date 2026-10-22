#!/usr/bin/env bash
set -euo pipefail

# The version this release is supposed to be...
expected_version="$(cat VERSION)"

# ...and the one the built binary actually reports. `--version` prints
# "<name>, version X", so the version is the last field. Comparing the whole
# line — or matching a substring, as this once did — lets 1.2.30 pass for
# 1.2.3, and waves through exactly the mismatch this check exists to catch.
actual_version="$(./dist/jeeves --version 2>&1 | awk '{print $NF}')"

if [[ "${actual_version}" != "${expected_version}" ]]; then
    echo "Binary version mismatch. Expected: ${expected_version}, got: ${actual_version}" >&2
    exit 1
fi

echo "Binary version OK: ${actual_version}"
