#!/usr/bin/env bash

set -e

REPO="mrsixw/jeeves"
BINARY_NAME="jeeves"
INSTALL_DIR="${HOME}/.local/bin"
EXECUTABLE_PATH="${INSTALL_DIR}/${BINARY_NAME}"
MAN_DIR="${HOME}/.local/share/man/man1"
BASH_COMPLETION_DIR="${HOME}/.local/share/bash-completion/completions"
ZSH_COMPLETION_DIR="${HOME}/.local/share/zsh/site-functions"
FISH_COMPLETION_DIR="${HOME}/.config/fish/completions"

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
RESET="\033[0m"

echo -e "${BOLD}${BLUE}🍔 Firing up jeeves...${RESET}"

# jeeves is a Python zipapp — python3 >= 3.11 must be present at runtime,
# so check up front rather than failing cryptically after the download.
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${BOLD}\033[31m❌ jeeves requires Python 3.11 or newer, but python3 was not found.${RESET}"
    echo -e "Install Python 3.11+ (e.g. ${BOLD}apt-get install python3${RESET}) and re-run this installer."
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    echo -e "${BOLD}\033[31m❌ jeeves requires Python 3.11 or newer, but found: $(python3 --version 2>&1).${RESET}"
    echo -e "Install Python 3.11+ and re-run this installer."
    exit 1
fi

echo -e "${YELLOW}Finding the latest version...${RESET}"
RELEASE_BASE_URL="https://github.com/${REPO}/releases/latest/download"

echo -e "${GREEN}Found latest release! Downloading...${RESET}"
mkdir -p "${INSTALL_DIR}"

if ! curl -sfL "${RELEASE_BASE_URL}/${BINARY_NAME}" -o "${EXECUTABLE_PATH}"; then
    echo -e "${BOLD}\033[31m❌ Failed to download binary.${RESET}"
    exit 1
fi
chmod +x "${EXECUTABLE_PATH}"
echo -e "${BOLD}${GREEN}✅ Installed ${BINARY_NAME} to ${EXECUTABLE_PATH}!${RESET}"

echo -ne "${BLUE}Installed version: ${RESET}"
"${EXECUTABLE_PATH}" --version

echo -e "${YELLOW}Initializing default configuration...${RESET}"
"${EXECUTABLE_PATH}" --init-config

echo -e "${YELLOW}Installing man page...${RESET}"
mkdir -p "${MAN_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/jeeves.1.gz" -o "${MAN_DIR}/jeeves.1.gz"; then
    echo -e "${GREEN}📖 Man page installed. Run: ${BOLD}man jeeves${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install man page (non-fatal).${RESET}"
fi

echo -e "${YELLOW}Installing shell completions...${RESET}"
mkdir -p "${BASH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/jeeves.bash" -o "${BASH_COMPLETION_DIR}/jeeves"; then
    echo -e "${GREEN}✅ Bash completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install bash completion (non-fatal).${RESET}"
fi

mkdir -p "${ZSH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/_jeeves" -o "${ZSH_COMPLETION_DIR}/_jeeves"; then
    echo -e "${GREEN}✅ Zsh completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install zsh completion (non-fatal).${RESET}"
fi

mkdir -p "${FISH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/jeeves.fish" -o "${FISH_COMPLETION_DIR}/jeeves.fish"; then
    echo -e "${GREEN}✅ Fish completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install fish completion (non-fatal).${RESET}"
fi

# Dropping the completion files into place is only half the job — bash and zsh
# both need a line in the user's rc file before they will load them. Print the
# snippet for the shell they are actually using rather than all three.
echo -e "\n${BOLD}To finish enabling completions:${RESET}"
case "${SHELL##*/}" in
    *bash*)
        echo -e "Add this to your ${BOLD}~/.bashrc${RESET}:"
        echo -e "  ${BOLD}source \"${BASH_COMPLETION_DIR}/${BINARY_NAME}\"${RESET}"
        echo -e "(If you already have the ${BOLD}bash-completion${RESET} package installed, it will be picked up automatically and you can skip this.)"
        echo -e "Then restart your shell."
        ;;
    *zsh*)
        echo -e "Add this to your ${BOLD}~/.zshrc${RESET}, above any existing ${BOLD}compinit${RESET} call:"
        echo -e "  ${BOLD}fpath=(\"${ZSH_COMPLETION_DIR}\" \$fpath)${RESET}"
        echo -e "If you don't already initialise completions (Oh My Zsh and friends do), add this too:"
        echo -e "  ${BOLD}autoload -Uz compinit && compinit${RESET}"
        echo -e "Then restart your shell."
        ;;
    *fish*)
        echo -e "${GREEN}Nothing to do — fish loads completions from ${FISH_COMPLETION_DIR} automatically.${RESET}"
        echo -e "New shells will pick them up."
        ;;
    *)
        echo -e "bash — add to ${BOLD}~/.bashrc${RESET}:"
        echo -e "  ${BOLD}source \"${BASH_COMPLETION_DIR}/${BINARY_NAME}\"${RESET}"
        echo -e "zsh  — add to ${BOLD}~/.zshrc${RESET}, above any existing ${BOLD}compinit${RESET} call:"
        echo -e "  ${BOLD}fpath=(\"${ZSH_COMPLETION_DIR}\" \$fpath)${RESET}"
        echo -e "  ${BOLD}autoload -Uz compinit && compinit${RESET}  ${RESET}# only if you don't already initialise completions"
        echo -e "fish — nothing to do, they load automatically."
        echo -e "Then restart your shell."
        ;;
esac
echo -e "You can also load them ad hoc with ${BOLD}eval \"\$(${BINARY_NAME} completions <shell>)\"${RESET}."

if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    echo -e "\n${BOLD}${YELLOW}⚠️  Warning: ${INSTALL_DIR} is not in your PATH.${RESET}"
    echo -e "Add this to your ~/.bashrc or ~/.zshrc:"
    echo -e "  ${BOLD}export PATH=\"${INSTALL_DIR}:\$PATH\"${RESET}"
fi

# Resolve a path to its real location, following symlinked directories, so a
# ~/.local/bin that is itself a symlink does not read as a different install.
# Only the directory is resolved: the binary we install may legitimately be a
# symlink, and replacing the link is what an install is supposed to do.
resolve_path() {
    local target="${1}" dir base
    dir="$(dirname "${target}")"
    base="$(basename "${target}")"
    if [ -d "${dir}" ]; then
        dir="$(cd -P "${dir}" 2>/dev/null && pwd)" || dir="$(dirname "${target}")"
    fi
    printf '%s/%s' "${dir}" "${base}"
}

# Having ${INSTALL_DIR} on PATH is not the same as winning on PATH. A stale copy
# earlier in the search order silently takes every invocation, and the installer
# above has just reported complete success — so the user runs an old binary and
# blames the features that appear to be missing: `completions` reports "No such
# command", `update` rewrites a copy they never invoke. Check what the shell
# would actually resolve, not merely where we put the file.
#
# `hash -r` first: this shell ran ${EXECUTABLE_PATH} by absolute path earlier,
# and a cached lookup here would describe bash's memory rather than PATH.
SHADOW_STATUS=0
hash -r 2>/dev/null || true
RESOLVED_PATH="$(command -v "${BINARY_NAME}" 2>/dev/null || true)"
if [ -n "${RESOLVED_PATH}" ] \
    && [ "$(resolve_path "${RESOLVED_PATH}")" != "$(resolve_path "${EXECUTABLE_PATH}")" ]; then
    echo -e "\n${BOLD}\033[31m❌ Another ${BINARY_NAME} shadows this install.${RESET}"
    echo -e "   ${BOLD}Installed:${RESET} ${EXECUTABLE_PATH}"
    echo -e "   ${BOLD}Shadowed by:${RESET} ${RESOLVED_PATH}  ${YELLOW}← this is what runs${RESET}"
    echo -e "\nThe rogue copy wins because it comes first in your PATH. Until it is"
    echo -e "removed or your PATH is reordered, ${BINARY_NAME} will keep running the"
    echo -e "old binary — which is how a missing ${BOLD}completions${RESET} command, or"
    echo -e "an ${BOLD}update${RESET} that never seems to take effect usually shows up."
    echo -e "\nRemove it with:"
    echo -e "  ${BOLD}rm \"${RESOLVED_PATH}\"${RESET}"
    echo -e "then re-run this installer to confirm."
    SHADOW_STATUS=1
fi

# Suppressed when shadowed: pointing the user at `${BINARY_NAME} --help` directly
# below a warning that `${BINARY_NAME}` runs something else would be telling them
# to invoke the very binary we just said is the wrong one.
if [ "${SHADOW_STATUS}" -eq 0 ]; then
    echo -e "\n${BOLD}Try running it now:${RESET}"
    echo -e "  ${BINARY_NAME} --help"
fi

# Non-zero when shadowed: the install did put the binary in place, but the
# command the user is about to type still is not it. Reporting success there is
# the bug this exits for.
exit ${SHADOW_STATUS}
