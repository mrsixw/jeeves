"""Tests for the structured output rendering engine."""

import json

from jeeves.render import (
    Column,
    render,
    render_delimited,
    render_json,
    render_markdown,
    render_ndjson,
    render_table,
    render_template,
    strip_ansi,
)

RECORDS = [
    {"name": "deploy", "status": "passed", "health": 90},
    {"name": "build", "status": "failed", "health": None},
]
COLUMNS = [
    Column("name", "Job"),
    Column("status", "Status"),
    Column("health", "Health"),
]


def test_strip_ansi_removes_colour_and_hyperlinks():
    s = "\x1b[31mred\x1b[0m \x1b]8;;http://x\x1b\\link\x1b]8;;\x1b\\"
    assert strip_ansi(s) == "red link"


def test_render_json_emits_semantic_values():
    out = render_json(RECORDS)
    data = json.loads(out)
    assert data[0]["status"] == "passed"
    assert data[1]["health"] is None


def test_render_ndjson_one_object_per_line():
    out = render_ndjson(RECORDS)
    lines = out.splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "deploy"


def test_render_markdown_has_pipes_and_headers():
    out = render_markdown(RECORDS, COLUMNS)
    assert "| Job" in out or "|Job" in out
    assert "passed" in out
    assert "---" in out


def test_render_csv_semantic_values():
    out = render_delimited(RECORDS, COLUMNS, ",")
    lines = out.splitlines()
    assert lines[0] == "Job,Status,Health"
    assert lines[1] == "deploy,passed,90"
    # None renders as an empty cell
    assert lines[2] == "build,failed,"


def test_render_tsv_uses_tabs():
    out = render_delimited(RECORDS, COLUMNS, "\t")
    assert "\t" in out.splitlines()[0]


def test_render_template_substitutes_fields():
    out = render_template(RECORDS, "{name}={status}")
    assert out.splitlines() == ["deploy=passed", "build=failed"]


def test_render_template_unknown_field_raises():
    try:
        render_template(RECORDS, "{nope}")
    except ValueError as exc:
        assert "unknown template field" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_render_table_uses_table_callable():
    col = Column("name", "Job", table=lambda r, i: f"[{i}]{r['name']}")
    out = render_table([{"name": "x"}], [col])
    assert "[0]x" in out


def test_render_dispatch_tree_requires_tree_fn():
    try:
        render("tree", RECORDS, COLUMNS)
    except ValueError as exc:
        assert "tree" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_render_dispatch_tree_uses_callable():
    out = render("tree", RECORDS, COLUMNS, tree_fn=lambda recs: f"{len(recs)} nodes")
    assert out == "2 nodes"


def test_render_empty_json_is_array():
    assert render("json", [], COLUMNS) == "[]"
