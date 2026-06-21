.ONESHELL:
SHELL = /bin/bash

.PHONY: build release test lint docs-lint format man completions

.venv:
	uv venv .venv
	uv sync --extra dev

build: .venv
	uv sync --extra build
	uv run shiv -c five-clis -o five-clis --python '/usr/bin/env python3' --preamble utils/preamble.py .

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
	gzip -f man1/five-clis.1

completions: .venv
	uv sync
	mkdir -p completions
	_FIVE_CLIS_COMPLETE=bash_source uv run five-clis > completions/five-clis.bash
	sed -i.bak 's/_FIVE_CLIS_COMPLETE=bash_complete $$1)/_FIVE_CLIS_COMPLETE=bash_complete "$$1")/' completions/five-clis.bash
	sed -i.bak 's/COMPREPLY+=($$value)/COMPREPLY+=("$$value")/' completions/five-clis.bash
	rm -f completions/five-clis.bash.bak
	_FIVE_CLIS_COMPLETE=zsh_source uv run five-clis > completions/_five-clis
	_FIVE_CLIS_COMPLETE=fish_source uv run five-clis > completions/five-clis.fish
