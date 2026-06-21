"""Print the version from the VERSION file."""

from pathlib import Path

print(Path(__file__).parent.parent.joinpath("VERSION").read_text().strip())
