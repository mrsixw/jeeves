.ONESHELL:
SHELL = /bin/bash

# Pinned to the version the CI spell job uses. Floating it would reintroduce
# exactly the drift this target exists to remove.
TYPOS_VERSION := 1.48.0
# shellcheck-py ships the real shellcheck binary as a wheel, so this is the same
# tool npx would fetch — but pinned, the way TYPOS_VERSION is, so CI and a
# laptop run the identical version rather than whatever npm resolves today.
SHELLCHECK_VERSION := 0.11.0.1

# Every shell source we ship, plus the test helper, which is shell too and just
# as capable of being wrong.
SHELL_SOURCES := install.sh $(wildcard utils/*.sh) tests/bats/helpers/common.bash

# Required because of .ONESHELL above, which hands the whole recipe to one
# shell invocation. Without -e that shell runs on past a failing command and
# make sees only the LAST command's exit status, so a recipe can fail halfway
# and still report success — `make lint` would pass with a failing `ruff` so
# long as the `black` after it succeeded.
#
# It does not reproduce on macOS, which is the trap: Apple ships GNU Make
# 3.81, which predates both .ONESHELL and .SHELLFLAGS (3.82) and ignores them,
# running each line in its own shell and checking each status. So the bug is
# invisible locally and live in CI. On 3.81 this line is inert; on 3.82+ it
# restores stop-on-first-failure. See issue #139.
.SHELLFLAGS := -ec

PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin
DESTDIR ?=

.PHONY: build release test bats e2e e2e-offline e2e-ci lint docs-lint shellcheck spell format man completions install uninstall

.venv:
	uv venv .venv
	uv sync --extra dev

build: .venv
	uv sync --extra build
	mkdir -p dist
	uv run shiv -c jeeves -o dist/jeeves --python '/usr/bin/env python3' --preamble utils/preamble.py .

install: build
	install -d "$(DESTDIR)$(BINDIR)"
	install -m 755 dist/jeeves "$(DESTDIR)$(BINDIR)/jeeves"

uninstall:
	rm -f "$(DESTDIR)$(BINDIR)/jeeves"

release: build

test: .venv
	uv sync --extra test
	uv run pytest -v

# End-to-end: drives the built zipapp as a subprocess. Builds first so the
# binary under test is always current. `-m e2e` on the command line overrides
# the `-m 'not e2e'` in pyproject.toml.
e2e: build
	uv sync --extra test
	JEEVES_E2E_REQUIRE=1 uv run pytest -v -m e2e tests/e2e

# The container-free subset. Useful when you have no container runtime, or
# want the fast feedback without waiting on a Jenkins boot.
e2e-offline: build
	uv sync --extra test
	JEEVES_E2E_REQUIRE=1 uv run pytest -v -m "e2e and not docker" tests/e2e

# CI variant: deliberately does NOT depend on build, so it runs against the
# artifact the build job produced — the same bits the release ships. The
# REQUIRE flag turns "no binary" into a failure rather than a skip, so the
# suite cannot quietly rot to green. The test count check is the second half
# of that guarantee: a collection error would otherwise also report success.
e2e-ci: .venv
	uv sync --extra test
	mkdir -p dist
	JEEVES_E2E_REQUIRE=1 JEEVES_E2E_REQUIRE_DOCKER=1 \
		uv run pytest -v -m e2e tests/e2e --junitxml=dist/e2e-results.xml
	uv run python utils/assert_tests_ran.py dist/e2e-results.xml

lint: .venv docs-lint shellcheck spell
	uv sync --extra lint
	uv run ruff check .
	uv run black --check .

docs-lint:
	npx --yes markdownlint-cli2 "docs/**/*.md" "README.md" "CONTRIBUTING.md"

# Static analysis for every shell source.
shellcheck:
	uvx --from shellcheck-py==$(SHELLCHECK_VERSION) shellcheck $(SHELL_SOURCES)

# The shell test suite. bats arrives via npx, exactly as
# markdownlint-cli2 does above — nothing to install by hand.
bats:
	npx --yes bats tests/bats

# Spelling, the same check CI runs. uvx fetches typos on demand; uv is already
# this project's package manager.
spell:
	uvx --from typos==$(TYPOS_VERSION) typos

format: .venv
	uv sync --extra lint
	uv run ruff check --fix .
	uv run black .

man: .venv
	uv sync --extra build
	mkdir -p man1
	uv run python utils/generate_man_page.py man1
	gzip -f man1/jeeves.1

completions: .venv
	uv sync
	mkdir -p completions
	_JEEVES_COMPLETE=bash_source uv run jeeves > completions/jeeves.bash
	sed -i.bak 's/_JEEVES_COMPLETE=bash_complete $$1)/_JEEVES_COMPLETE=bash_complete "$$1")/' completions/jeeves.bash
	sed -i.bak 's/COMPREPLY+=($$value)/COMPREPLY+=("$$value")/' completions/jeeves.bash
	rm -f completions/jeeves.bash.bak
	_JEEVES_COMPLETE=zsh_source uv run jeeves > completions/_jeeves
	_JEEVES_COMPLETE=fish_source uv run jeeves > completions/jeeves.fish
