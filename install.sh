#!/usr/bin/env bash

set -e

REPO="mrsixw/five-clis"
BINARY_NAME="five-clis"
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

echo -e "${BOLD}${BLUE}🍔 Firing up five-clis...${RESET}"

echo -e "${YELLOW}Finding the latest version...${RESET}"
LATEST_RELEASE_JSON=$(curl -sf "https://api.github.com/repos/${REPO}/releases/latest") || {
    echo -e "${BOLD}\033[31m❌ Failed to fetch release info for ${REPO}.${RESET}"
    exit 1
}
LATEST_TAG=$(printf '%s' "${LATEST_RELEASE_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])") || {
    echo -e "${BOLD}\033[31m❌ Failed to parse release tag.${RESET}"
    exit 1
}
RELEASE_BASE_URL="https://github.com/${REPO}/releases/download/${LATEST_TAG}"
LATEST_RELEASE_URL=$(printf '%s' "${LATEST_RELEASE_JSON}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
urls = [a['browser_download_url'] for a in data.get('assets', []) if a['name'] == '${BINARY_NAME}']
print(urls[0] if urls else '')
")

if [ -z "${LATEST_RELEASE_URL}" ]; then
    echo -e "${BOLD}\033[31m❌ Failed to find the latest release binary.${RESET}"
    exit 1
fi

echo -e "${GREEN}Found latest release! Downloading...${RESET}"
mkdir -p "${INSTALL_DIR}"

if ! curl -sfL "${LATEST_RELEASE_URL}" -o "${EXECUTABLE_PATH}"; then
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
if curl -sfL "${RELEASE_BASE_URL}/five-clis.1.gz" -o "${MAN_DIR}/five-clis.1.gz"; then
    echo -e "${GREEN}📖 Man page installed. Run: ${BOLD}man five-clis${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install man page (non-fatal).${RESET}"
fi

echo -e "${YELLOW}Installing shell completions...${RESET}"
mkdir -p "${BASH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/five-clis.bash" -o "${BASH_COMPLETION_DIR}/five-clis"; then
    echo -e "${GREEN}✅ Bash completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install bash completion (non-fatal).${RESET}"
fi

mkdir -p "${ZSH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/_five-clis" -o "${ZSH_COMPLETION_DIR}/_five-clis"; then
    echo -e "${GREEN}✅ Zsh completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install zsh completion (non-fatal).${RESET}"
fi

mkdir -p "${FISH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/five-clis.fish" -o "${FISH_COMPLETION_DIR}/five-clis.fish"; then
    echo -e "${GREEN}✅ Fish completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install fish completion (non-fatal).${RESET}"
fi

if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    echo -e "\n${BOLD}${YELLOW}⚠️  Warning: ${INSTALL_DIR} is not in your PATH.${RESET}"
    echo -e "Add this to your ~/.bashrc or ~/.zshrc:"
    echo -e "  ${BOLD}export PATH=\"${INSTALL_DIR}:\$PATH\"${RESET}"
fi

echo -e "\n${BOLD}Try running it now:${RESET}"
echo -e "  ${BINARY_NAME} --help"
