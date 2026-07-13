.ONESHELL:
SHELL = /bin/bash

PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin
DESTDIR ?=

.PHONY: build release test lint docs-lint format man completions install uninstall

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

lint: .venv docs-lint
	uv sync --extra lint
	uv run ruff check .
	uv run black --check .

docs-lint:
	npx --yes markdownlint-cli2 "docs/**/*.md" "README.md" "CONTRIBUTING.md"

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
