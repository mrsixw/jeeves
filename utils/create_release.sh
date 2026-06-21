#!/usr/bin/env bash
set -euo pipefail

version="$1"
tag="v${version}"

gh release create "${tag}" ./five-clis \
  man1/five-clis.1.gz \
  completions/five-clis.bash \
  completions/_five-clis \
  completions/five-clis.fish \
  --title "${tag}" \
  --generate-notes \
  --target "$(git rev-parse HEAD)"
