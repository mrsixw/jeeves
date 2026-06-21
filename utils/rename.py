"""Interactive onboarding script: rename five-clis to your own project."""

import re
import shutil
import sys
from pathlib import Path

import click

ROOT = Path(__file__).parent.parent

_OLD_REPO = "mrsixw/five-clis"
_OLD_BIN_UPPER = "FIVE_CLIS"
_OLD_BIN = "five-clis"
_OLD_PKG = "fiveclis"

_SKIP_DIRS = {".git", ".venv", "__pycache__"}
_SKIP_FILES = {Path(__file__).resolve()}

_TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".yml",
    ".yaml",
    ".md",
    ".sh",
    ".txt",
    ".cfg",
    ".conf",
}
_MAKEFILE_NAMES = {"Makefile", "makefile"}


def _should_process(path: Path) -> bool:
    for part in path.parts:
        if part in _SKIP_DIRS or part.endswith(".egg-info"):
            return False
    if path.resolve() in _SKIP_FILES:
        return False
    return path.suffix in _TEXT_SUFFIXES or path.name in _MAKEFILE_NAMES


def _apply(path: Path, subs: list[tuple[str, str]]) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return False
    new_text = text
    for old, new in subs:
        new_text = new_text.replace(old, new)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def _validate_pkg(ctx, param, value):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise click.BadParameter(
            "must be lowercase letters, digits, and underscores only (e.g. myapp)"
        )
    return value


def _validate_bin(ctx, param, value):
    if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise click.BadParameter(
            "must be lowercase letters, digits, and hyphens only (e.g. my-app)"
        )
    return value


def _validate_repo(ctx, param, value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise click.BadParameter("must be in owner/repo format (e.g. you/myapp)")
    return value


@click.command()
@click.option(
    "--pkg",
    prompt="Python package name (e.g. myapp)",
    callback=_validate_pkg,
    is_eager=True,
    help="Python package name (no hyphens).",
)
@click.option(
    "--bin",
    "bin_name",
    prompt="CLI binary name (e.g. my-app)",
    callback=_validate_bin,
    is_eager=True,
    help="CLI binary/command name.",
)
@click.option(
    "--repo",
    prompt="GitHub repo (e.g. you/myapp)",
    callback=_validate_repo,
    is_eager=True,
    help="GitHub owner/repo slug.",
)
def main(pkg: str, bin_name: str, repo: str) -> None:
    """Rename five-clis to your own project name.

    Replaces all occurrences of the template names across source files,
    renames src/fiveclis/ to src/<pkg>/, and removes the stale egg-info.
    """
    bin_upper = bin_name.upper().replace("-", "_")

    # Most specific substitutions first to avoid partial matches
    subs = [
        (_OLD_REPO, repo),
        (_OLD_BIN_UPPER, bin_upper),
        (_OLD_BIN, bin_name),
        (_OLD_PKG, pkg),
    ]

    click.echo()

    # Text substitution across all relevant files
    changed: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and _should_process(path):
            if _apply(path, subs):
                changed.append(path.relative_to(ROOT))

    # Rename src/fiveclis/ → src/{pkg}/
    old_src = ROOT / "src" / _OLD_PKG
    new_src = ROOT / "src" / pkg
    if old_src.exists() and old_src != new_src:
        shutil.move(str(old_src), str(new_src))
        click.echo(f"📁 Renamed src/{_OLD_PKG}/ → src/{pkg}/")

    # Remove stale egg-info (uv sync will regenerate it)
    for egg_info in (ROOT / "src").glob("*.egg-info"):
        shutil.rmtree(egg_info)
        click.echo(f"🗑️  Removed {egg_info.relative_to(ROOT)}")

    # Report changed files
    if changed:
        click.echo(f"\n✏️  Updated {len(changed)} files:")
        for f in changed:
            click.echo(f"   {f}")
    else:
        click.echo("⚠️  No files changed — already renamed?")
        sys.exit(1)

    click.echo(f"""
✅ Done! {pkg} / {bin_name} is ready.

Next steps:
  1. Replace the demo business logic in src/{pkg}/cli.py
  2. Add GH_TOKEN secret: github.com/{repo}/settings/secrets/actions
  3. Run: make format && make lint && make test
""")


if __name__ == "__main__":
    main()
