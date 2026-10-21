#!/usr/bin/env bats
#
# 🎩 install.sh — the published `curl | bash` install path.
#
# install.sh ships mode 644 and is documented as `curl ... | bash`, so the tests
# drive it through `bash` exactly as a user would.
#
# HOME is redirected into the test's temporary directory, so every path the
# installer writes to lands there and nothing touches the developer's machine.

setup() {
  load 'helpers/common'
  common_setup

  # The zipapp needs a python3 >= 3.11 at runtime, so the installer checks for
  # one before downloading anything. Stubbing python3 is how those branches
  # become testable at all.
  stub python3 <<'STUB'
if [[ -n "${PYTHON_TOO_OLD:-}" ]]; then
  # The guard runs a version comparison and reads its exit status.
  [[ "$1" == "-c" ]] && exit 1
  [[ "$1" == "--version" ]] && { printf 'Python 3.9.6\n'; exit 0; }
fi
[[ "$1" == "--version" ]] && { printf 'Python 3.11.9\n'; exit 0; }
exit 0
STUB

  stub curl <<'STUB'
url=""; out=""; prev=""
for arg in "$@"; do
  [[ "${prev}" == "-o" ]] && out="${arg}"
  [[ "${arg}" == http* ]] && url="${arg}"
  prev="${arg}"
done

case "${url}" in
  *.1.gz)
    [[ -n "${MAN_FAILS:-}" ]] && exit 22
    printf 'man page\n' > "${out}"; exit 0 ;;
  *.bash|*.fish|*/_*)
    [[ -n "${COMPLETIONS_FAIL:-}" ]] && exit 22
    printf 'completion\n' > "${out}"; exit 0 ;;
  *)
    [[ -n "${BINARY_FAILS:-}" ]] && exit 22
    {
      printf '#!/usr/bin/env bash\n'
      printf 'printf "%%s\\n" "$*" >> "%s/binary.log"\n' "${STUB_LOG}"
      printf 'if [[ "$1" == "--version" ]]; then printf "%%s, version 1.2.3\\n" "%s"; fi\n' "${BINARY_NAME}"
      printf 'exit 0\n'
    } > "${out}"
    exit 0 ;;
esac
STUB
}

binary_calls() { cat "${STUB_LOG}/binary.log" 2>/dev/null || true; }

# ---------------------------------------------------------------------------
# 🐍 The Python guard
# ---------------------------------------------------------------------------

@test "refuses to install when python3 is missing entirely" {
  # The binary is a zipapp: without python3 it would download cleanly and then
  # fail cryptically on first run.
  #
  # A stub cannot express "absent", so the interpreter is invoked by absolute
  # path and PATH is reduced to the stub directory alone — with the python3
  # stub removed, nothing can find one. The guard runs before the script needs
  # any other external command.
  rm -f "${STUB_BIN}/python3"

  PATH="${STUB_BIN}" run /bin/bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 1 ]
  assert_output_contains "python3 was not found"
  refute_called curl
}

@test "refuses to install against a python3 that is too old" {
  export PYTHON_TOO_OLD=1

  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 1 ]
  assert_output_contains "requires Python 3.11 or newer"
}

@test "names the version it actually found, so the user knows what to fix" {
  export PYTHON_TOO_OLD=1

  run bash "${REPO_ROOT}/install.sh"

  assert_output_contains "3.9.6"
}

@test "checks python before downloading anything" {
  # Ordering matters: failing after the download leaves a broken binary on disk.
  export PYTHON_TOO_OLD=1

  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 1 ]
  refute_called curl
  [ ! -e "${FAKE_HOME}/.local/bin/${BINARY_NAME}" ]
}

# ---------------------------------------------------------------------------
# 📦 The install itself
# ---------------------------------------------------------------------------

@test "installs the binary, executable, under ~/.local/bin" {
  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  [ -x "${FAKE_HOME}/.local/bin/${BINARY_NAME}" ]
}

@test "downloads from the latest-release directory" {
  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_called curl "/releases/latest/download/${BINARY_NAME}"
}

@test "reports the installed version and seeds a default config" {
  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "version 1.2.3"
  printf '%s\n' "$(binary_calls)" | grep -qx -- "--init-config"
}

@test "installs the man page and all three completions" {
  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  [ -f "${FAKE_HOME}/.local/share/man/man1/${BINARY_NAME}.1.gz" ]
  [ -f "${FAKE_HOME}/.local/share/bash-completion/completions/${BINARY_NAME}" ]
  [ -f "${FAKE_HOME}/.local/share/zsh/site-functions/_${BINARY_NAME}" ]
  [ -f "${FAKE_HOME}/.config/fish/completions/${BINARY_NAME}.fish" ]
}

@test "fails when the binary download fails" {
  export BINARY_FAILS=1

  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 1 ]
  assert_output_contains "Failed to download binary"
}

@test "treats a missing man page as non-fatal" {
  export MAN_FAILS=1

  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "Could not install man page"
  [ -x "${FAKE_HOME}/.local/bin/${BINARY_NAME}" ]
}

@test "treats missing completions as non-fatal" {
  export COMPLETIONS_FAIL=1

  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "Could not install bash completion"
  assert_output_contains "Could not install zsh completion"
  assert_output_contains "Could not install fish completion"
}

# ---------------------------------------------------------------------------
# 🐚 Completion instructions
# ---------------------------------------------------------------------------

@test "prints zsh instructions to a zsh user" {
  SHELL=/bin/zsh run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "Add this to your ~/.zshrc"
  assert_output_contains "fpath="
  # Not "~/.bashrc": the PATH warning below names both files, so a loose
  # assertion here would pass whichever branch ran.
  refute_output_contains "~/.bashrc:"
}

@test "prints bash instructions to a bash user" {
  SHELL=/bin/bash run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "Add this to your ~/.bashrc:"
  refute_output_contains "compinit"
}

@test "tells a fish user there is nothing to do" {
  SHELL=/usr/bin/fish run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "Nothing to do"
}

@test "falls back to all three when the shell is unrecognised" {
  SHELL=/bin/ksh run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "bash — add to"
  assert_output_contains "zsh  — add to"
  assert_output_contains "fish — nothing to do"
}

@test "warns when the install directory is not on PATH" {
  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "is not in your PATH"
}

@test "stays quiet about PATH when the install directory is already on it" {
  PATH="${FAKE_HOME}/.local/bin:${PATH}" run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  refute_output_contains "is not in your PATH"
}
