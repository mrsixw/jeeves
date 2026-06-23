"""Structured output rendering: records → table/tree/json/ndjson/markdown/csv/tsv.

Commands produce a list of **record** dicts (semantic values — the JSON
contract) plus a list of :class:`Column` specs describing the visible tabular
projection. A single :func:`render` dispatch turns those into the chosen
format. The ``table`` (and jeeves-specific ``tree``) renderer adds the rich
emoji/colour/hyperlink decoration; structured renderers emit semantic values
only.
"""

from __future__ import annotations

import csv as _csv
import io
import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass

from tabulate import tabulate

# Format names accepted by --format. ``tree`` is only meaningful for commands
# that supply a tree renderer (e.g. the hierarchical jobs roster).
FORMATS = ["table", "tree", "json", "ndjson", "markdown", "csv", "tsv", "template"]

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[a-zA-Z]|\]8;;.*?\x1b\\|\]8;;.*?\x07)")


def strip_ansi(s: str) -> str:
    """Remove ANSI colour and OSC 8 hyperlink escapes for width measurement."""
    return _ANSI_RE.sub("", s)


@dataclass
class Column:
    """A visible table column.

    ``key`` is the record field (and JSON contract name). ``table`` renders the
    decorated cell for table mode and receives ``(record, row_index)`` so it can
    apply per-row seasonal colour. ``plain`` renders the semantic string for
    markdown/csv/template; when omitted the raw record value is stringified.
    """

    key: str
    header: str
    table: Callable[[dict, int], str] | None = None
    plain: Callable[[dict], str] | None = None

    def render_table(self, record: dict, index: int) -> str:
        if self.table is not None:
            return self.table(record, index)
        return self.render_plain(record)

    def render_plain(self, record: dict) -> str:
        if self.plain is not None:
            return self.plain(record)
        val = record.get(self.key)
        return "" if val is None else str(val)


def _table_rows(records: list[dict], columns: list[Column]) -> list[list[str]]:
    return [[c.render_table(r, i) for c in columns] for i, r in enumerate(records)]


def _compress_col(rows: list[list[str]], col: int) -> list[list[str]]:
    """Strip all but the first token of a column's cells (keep the icon)."""
    result = []
    for row in rows:
        new_row = list(row)
        plain = strip_ansi(new_row[col])
        first = plain.split()[0] if plain.split() else plain
        if first != plain:
            new_row[col] = new_row[col].replace(plain, first, 1)
        result.append(new_row)
    return result


def render_table(
    records: list[dict],
    columns: list[Column],
    *,
    compress_col: int | None = None,
) -> str:
    """Render the rich, decorated table. ``compress_col`` strips that column's
    labels (leaving the icon) when the table would overflow the terminal."""
    headers = [c.header for c in columns]
    rows = _table_rows(records, columns)
    if compress_col is not None and rows:
        rendered = tabulate(
            rows, headers=headers, tablefmt="simple", disable_numparse=True
        )
        width = max((len(strip_ansi(ln)) for ln in rendered.splitlines()), default=0)
        if width > shutil.get_terminal_size().columns:
            rows = _compress_col(rows, compress_col)
    return tabulate(rows, headers=headers, tablefmt="simple", disable_numparse=True)


def render_json(records: list[dict]) -> str:
    return json.dumps(records, indent=2, ensure_ascii=False)


def render_ndjson(records: list[dict]) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in records)


def render_markdown(records: list[dict], columns: list[Column]) -> str:
    headers = [c.header for c in columns]
    rows = [[c.render_plain(r) for c in columns] for r in records]
    return tabulate(rows, headers=headers, tablefmt="github", disable_numparse=True)


def render_delimited(records: list[dict], columns: list[Column], delimiter: str) -> str:
    buf = io.StringIO()
    writer = _csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerow([c.header for c in columns])
    for r in records:
        writer.writerow([c.render_plain(r) for c in columns])
    return buf.getvalue().rstrip("\n")


def render_template(records: list[dict], template: str) -> str:
    lines = []
    for r in records:
        try:
            lines.append(template.format(**r))
        except (KeyError, IndexError) as exc:
            raise ValueError(f"unknown template field: {exc}") from exc
    return "\n".join(lines)


def render(
    fmt: str,
    records: list[dict],
    columns: list[Column],
    *,
    template: str | None = None,
    tree_fn: Callable[[list[dict]], str] | None = None,
    compress_col: int | None = None,
) -> str:
    """Dispatch ``records`` to the chosen format."""
    if fmt == "table":
        return render_table(records, columns, compress_col=compress_col)
    if fmt == "tree":
        if tree_fn is None:
            raise ValueError("the 'tree' format is not available for this command")
        return tree_fn(records)
    if fmt == "json":
        return render_json(records)
    if fmt == "ndjson":
        return render_ndjson(records)
    if fmt == "markdown":
        return render_markdown(records, columns)
    if fmt == "csv":
        return render_delimited(records, columns, ",")
    if fmt == "tsv":
        return render_delimited(records, columns, "\t")
    if fmt == "template":
        if not template:
            raise ValueError("--template is required when using --format template")
        return render_template(records, template)
    raise ValueError(f"unknown format: {fmt}")  # pragma: no cover
