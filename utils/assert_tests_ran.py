#!/usr/bin/env python3
"""Fail if a pytest run reported no executed tests.

A green CI job is only meaningful if it actually ran something. pytest already
exits 5 when it collects nothing, and ``JEEVES_E2E_REQUIRE`` turns a missing
binary into a failure rather than a skip — but neither covers a run where every
test was skipped for some *other* reason. That is the shape of rot this guards
against: an e2e job that quietly reports success having exercised nothing.

Reads a JUnit XML report (``pytest --junitxml``) and requires at least one
test, none of them skipped.

Usage:
    python3 utils/assert_tests_ran.py dist/e2e-results.xml
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def counts(report: Path) -> tuple[int, int]:
    """Return ``(tests, skipped)`` summed over every suite in the report.

    pytest emits a ``<testsuites>`` wrapper around one ``<testsuite>``, but
    reading whichever element carries the attributes keeps this working if that
    ever changes.
    """
    root = ET.parse(report).getroot()
    suites = root.iter("testsuite")
    totals = [(int(s.get("tests", 0)), int(s.get("skipped", 0))) for s in suites]
    return sum(t for t, _ in totals), sum(s for _, s in totals)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} <junit-xml>", file=sys.stderr)
        return 2

    report = Path(argv[1])
    if not report.is_file():
        print(
            f"❌ no JUnit report at {report} — did pytest run at all?",
            file=sys.stderr,
        )
        return 1

    try:
        total, skipped = counts(report)
    except ET.ParseError as exc:
        print(f"❌ {report} is not parseable XML: {exc}", file=sys.stderr)
        return 1

    if total == 0:
        print(
            f"❌ {report} reports zero tests — the job would pass vacuously.",
            file=sys.stderr,
        )
        return 1

    if skipped:
        print(
            f"❌ {skipped} of {total} tests were skipped. In CI every gate should"
            " be a hard failure — check the JEEVES_E2E_REQUIRE* flags.",
            file=sys.stderr,
        )
        return 1

    print(f"✅ {total} tests ran, none skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
