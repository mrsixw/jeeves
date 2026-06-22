#!/usr/bin/env bash
set -euo pipefail

version="$1"
tag="v${version}"

gh release create "${tag}" ./dist/jeeves \
  man1/jeeves.1.gz \
  completions/jeeves.bash \
  completions/_jeeves \
  completions/jeeves.fish \
  --title "${tag}" \
  --generate-notes \
  --target "$(git rev-parse HEAD)"
