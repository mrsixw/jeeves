"""JUnit plugin support (a build's ``testReport`` action).

Not part of base Jenkins: the ``junit`` plugin attaches a ``TestResultAction``
at ``/job/x/N/testReport/`` once a build publishes results. Multi-configuration
builds get an ``AggregatedTestResultAction`` there instead, whose payload is a
list of ``childReports`` rather than suites.

Two upstream facts shape the design:

- A 404 on ``testReport`` means "no results recorded" **or** "plugin absent",
  and the build alone cannot tell which. The plugin manager can, but only for
  callers with SYSTEM_READ, so it is consulted on the error path and its
  silence is reported as "undetermined" rather than guessed.
- Cases export their full ``stdout``/``stderr``, which can run to megabytes
  per test. The ``tree`` below names only the fields jeeves shows.
"""

from .jenkins import (
    JenkinsClient,
    JenkinsError,
    JenkinsHTTPError,
    normalize_jenkins_path,
)

__all__ = ["JUnitError", "TestReport", "case_records", "summarise"]

_CASE = "className,name,status,duration,age,errorDetails"
_RESULT = f"failCount,passCount,skipCount,duration,suites[name,cases[{_CASE}]]"
_TREE = f"{_RESULT},childReports[child[fullDisplayName,url],result[{_RESULT}]]"

# CaseResult.Status values that count as failing, as the plugin defines them.
_FAILING = frozenset({"FAILED", "REGRESSION"})


class JUnitError(JenkinsError):
    """A test-report call that failed for a reason worth naming.

    ``reason`` is one of ``no-build``, ``no-tests`` (the plugin is installed
    but the build published nothing), ``plugin-missing``, or ``no-report``
    (one of the latter two, and this caller may not ask which).
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"junit: {reason}")
        self.reason = reason
        self.detail = detail


class TestReport:
    """One build's JUnit report over one Jenkins client."""

    # Keep pytest from collecting this as a test class by its name.
    __test__ = False

    def __init__(
        self, client: JenkinsClient, job: str, build: int | str = "lastBuild"
    ) -> None:
        self._client = client
        self._job_path = normalize_jenkins_path(job)
        self._build = build
        self.number: int | None = None
        self.url = ""

    def fetch(self) -> dict:
        """The raw report, with the build resolved to a number first."""
        self._resolve()
        try:
            return self._client.get_json(
                f"{self._job_path}/{self.number}/testReport",
                params={"tree": _TREE},
            )
        except JenkinsHTTPError as exc:
            if exc.status != 404:
                raise
            raise JUnitError(self._why_no_report()) from exc

    def _resolve(self) -> None:
        if self.number is not None:
            return
        try:
            info = self._client.get_json(
                f"{self._job_path}/{self._build}", params={"tree": "number,url"}
            )
        except JenkinsHTTPError as exc:
            if exc.status == 404:
                raise JUnitError("no-build", str(self._build)) from exc
            raise
        self.number = int(info.get("number"))
        self.url = str(info.get("url") or "")

    def _why_no_report(self) -> str:
        """Tell "published nothing" from "plugin absent", where permitted."""
        try:
            payload = self._client.get_json(
                "pluginManager", params={"tree": "plugins[shortName,active]"}
            )
        except JenkinsError:
            return "no-report"
        installed = {
            p.get("shortName")
            for p in payload.get("plugins") or []
            if p.get("active", True)
        }
        return "no-tests" if "junit" in installed else "plugin-missing"


def _results(report: dict) -> list[tuple[str, dict]]:
    """``(configuration, result)`` pairs: one, or one per matrix child."""
    children = report.get("childReports")
    if children:
        return [(_child_name(c), c.get("result") or {}) for c in children]
    return [("", report)]


def _child_name(child_report: dict) -> str:
    return str((child_report.get("child") or {}).get("fullDisplayName") or "")


def summarise(report: dict) -> dict:
    """Totals across the whole report, matrix children included."""
    totals = {"passed": 0, "failed": 0, "skipped": 0, "duration": 0.0}
    for _config, result in _results(report):
        totals["passed"] += int(result.get("passCount") or 0)
        totals["failed"] += int(result.get("failCount") or 0)
        totals["skipped"] += int(result.get("skipCount") or 0)
        totals["duration"] += float(result.get("duration") or 0.0)
    return totals


def case_records(
    report: dict, *, failed_only: bool = False, suite: str | None = None
) -> list[dict]:
    """One record per test case, optionally only failing ones or one suite."""
    records = []
    for config, result in _results(report):
        for s in result.get("suites") or []:
            suite_name = str(s.get("name") or "")
            if suite is not None and suite_name != suite:
                continue
            for case in s.get("cases") or []:
                status = str(case.get("status") or "")
                failing = status in _FAILING
                if failed_only and not failing:
                    continue
                records.append(
                    {
                        "suite": suite_name,
                        "class_name": str(case.get("className") or ""),
                        "name": str(case.get("name") or ""),
                        "status": status,
                        "failing": failing,
                        "duration": float(case.get("duration") or 0.0),
                        # Builds this case has been failing for; 0 when passing.
                        "age": int(case.get("age") or 0) if failing else 0,
                        "error": str(case.get("errorDetails") or "") if failing else "",
                        "configuration": config,
                    }
                )
    return records
