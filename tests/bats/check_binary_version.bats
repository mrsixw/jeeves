#!/usr/bin/env bats
#
# 🔢 utils/check_binary_version.sh — the release gate that refuses to ship a
#    binary whose --version disagrees with the VERSION file.

setup() {
  load 'helpers/common'
  common_setup

  WORK="${BATS_TEST_TMPDIR}/work"
  mkdir -p "${WORK}/dist"
  cd "${WORK}" || return 1
}

# The script reads VERSION from the file and the actual version from the built
# binary under dist/, so both are planted here.
given_versions() { # <version-file contents> <what the binary prints>
  printf '%s\n' "$1" > "${WORK}/VERSION"
  cat > "${WORK}/dist/${BINARY_NAME}" <<BINARY
#!/usr/bin/env bash
printf '%s\n' "$2"
BINARY
  chmod +x "${WORK}/dist/${BINARY_NAME}"
}

@test "passes when the binary matches VERSION" {
  given_versions "1.2.3" "${BINARY_NAME}, version 1.2.3"

  run "${REPO_ROOT}/utils/check_binary_version.sh"

  [ "$status" -eq 0 ]
}

@test "fails when the versions disagree outright" {
  given_versions "1.2.3" "${BINARY_NAME}, version 9.9.9"

  run "${REPO_ROOT}/utils/check_binary_version.sh"

  [ "$status" -eq 1 ]
  assert_output_contains "1.2.3"
  assert_output_contains "9.9.9"
}

@test "fails when the binary cannot report a version at all" {
  printf '1.2.3\n' > "${WORK}/VERSION"
  cat > "${WORK}/dist/${BINARY_NAME}" <<'BINARY'
#!/usr/bin/env bash
echo "Traceback (most recent call last):" >&2
exit 1
BINARY
  chmod +x "${WORK}/dist/${BINARY_NAME}"

  run "${REPO_ROOT}/utils/check_binary_version.sh"

  [ "$status" -eq 1 ]
}

@test "reports both versions when it fails, so CI logs say what went wrong" {
  given_versions "2.0.0" "${BINARY_NAME}, version 1.0.0"

  run "${REPO_ROOT}/utils/check_binary_version.sh"

  [ "$status" -eq 1 ]
  assert_output_contains "Expected: 2.0.0"
}
