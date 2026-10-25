"""Tests for the JUnit plugin surface."""

import pytest
import requests_mock as req_mock

from jeeves.jenkins import JenkinsClient, JenkinsHTTPError
from jeeves.junit import JUnitError, TestReport, case_records, summarise

BASE = "http://jenkins.example.com"
RESOLVE = f"{BASE}/job/api/lastBuild/api/json"
REPORT = f"{BASE}/job/api/42/testReport/api/json"
PLUGINS = f"{BASE}/pluginManager/api/json"


@pytest.fixture
def report() -> TestReport:
    return TestReport(JenkinsClient(BASE, "admin", "secret"), "api")


def _resolve(m: req_mock.Mocker) -> None:
    m.get(RESOLVE, json={"number": 42, "url": f"{BASE}/job/api/42/"})


def _case(name: str, status: str = "PASSED", **overrides) -> dict:
    case = {
        "className": "app.AuthTest",
        "name": name,
        "status": status,
        "duration": 0.5,
        "age": 0,
        "errorDetails": None,
    }
    case.update(overrides)
    return case


def _result(*cases: dict, suite: str = "app.AuthTest", **counts) -> dict:
    body = {
        "passCount": 0,
        "failCount": 0,
        "skipCount": 0,
        "duration": 1.5,
        "suites": [{"name": suite, "cases": list(cases)}],
    }
    body.update(counts)
    return body


# ── fetch ────────────────────────────────────────────────────────────────────


def test_fetch_resolves_the_permalink_then_reads_the_report(report) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(REPORT, json=_result(_case("ok")))
        report.fetch()
        assert m.last_request.url.startswith(REPORT)
    assert (report.number, report.url) == (42, f"{BASE}/job/api/42/")


def test_fetch_never_asks_for_captured_output(report) -> None:
    """stdout/stderr can run to megabytes per case; the tree names neither."""
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(REPORT, json=_result())
        report.fetch()
        tree = m.last_request.qs["tree"][0]
    assert "stdout" not in tree and "stderr" not in tree
    assert "errorstacktrace" not in tree
    assert "childreports[child[" in tree


def test_fetch_of_an_unknown_build_is_named(report) -> None:
    with req_mock.Mocker() as m:
        m.get(RESOLVE, status_code=404)
        with pytest.raises(JUnitError) as exc:
            report.fetch()
    assert (exc.value.reason, exc.value.detail) == ("no-build", "lastBuild")


def test_404_with_the_plugin_installed_means_no_tests(report) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(REPORT, status_code=404)
        m.get(PLUGINS, json={"plugins": [{"shortName": "junit", "active": True}]})
        with pytest.raises(JUnitError) as exc:
            report.fetch()
    assert exc.value.reason == "no-tests"


def test_404_with_the_plugin_absent_means_plugin_missing(report) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(REPORT, status_code=404)
        m.get(PLUGINS, json={"plugins": [{"shortName": "git", "active": True}]})
        with pytest.raises(JUnitError) as exc:
            report.fetch()
    assert exc.value.reason == "plugin-missing"


def test_an_inactive_plugin_counts_as_missing(report) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(REPORT, status_code=404)
        m.get(PLUGINS, json={"plugins": [{"shortName": "junit", "active": False}]})
        with pytest.raises(JUnitError) as exc:
            report.fetch()
    assert exc.value.reason == "plugin-missing"


def test_404_without_plugin_manager_access_is_undetermined(report) -> None:
    """Only SYSTEM_READ may list plugins; a 403 there is no evidence either way."""
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(REPORT, status_code=404)
        m.get(PLUGINS, status_code=403)
        with pytest.raises(JUnitError) as exc:
            report.fetch()
    assert exc.value.reason == "no-report"


def test_the_plugin_manager_is_only_asked_on_the_error_path(report) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(REPORT, json=_result())
        report.fetch()
        assert not any("pluginManager" in r.url for r in m.request_history)


def test_fetch_propagates_other_errors(report) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(REPORT, status_code=500)
        with pytest.raises(JenkinsHTTPError) as exc:
            report.fetch()
    assert exc.value.status == 500


def test_nested_job_paths_are_encoded() -> None:
    client = JenkinsClient(BASE, "admin", "secret")
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/team/job/api/7/api/json", json={"number": 7})
        m.get(f"{BASE}/job/team/job/api/7/testReport/api/json", json=_result())
        TestReport(client, "team/api", 7).fetch()


# ── summarise ────────────────────────────────────────────────────────────────


def test_summarise_reads_the_counts() -> None:
    raw = _result(passCount=312, failCount=2, skipCount=4, duration=102.5)
    assert summarise(raw) == {
        "passed": 312,
        "failed": 2,
        "skipped": 4,
        "duration": 102.5,
    }


def test_summarise_adds_up_matrix_children() -> None:
    raw = {
        "childReports": [
            {"child": {}, "result": _result(passCount=3, failCount=1, duration=2)},
            {"child": {}, "result": _result(passCount=5, skipCount=2, duration=3)},
        ]
    }
    assert summarise(raw) == {
        "passed": 8,
        "failed": 1,
        "skipped": 2,
        "duration": 5.0,
    }


# ── case_records ─────────────────────────────────────────────────────────────


def test_records_shape_a_failing_case() -> None:
    raw = _result(
        _case("test_refresh", "REGRESSION", age=1, errorDetails="expected 200")
    )
    assert case_records(raw) == [
        {
            "suite": "app.AuthTest",
            "class_name": "app.AuthTest",
            "name": "test_refresh",
            "status": "REGRESSION",
            "failing": True,
            "duration": 0.5,
            "age": 1,
            "error": "expected 200",
            "configuration": "",
        }
    ]


def test_records_blank_error_and_age_on_a_passing_case() -> None:
    """A FIXED case can still carry stale detail; only failures show it."""
    raw = _result(_case("t", "FIXED", age=3, errorDetails="old"))
    (record,) = case_records(raw)
    assert (record["failing"], record["age"], record["error"]) == (False, 0, "")


def test_failed_only_keeps_failed_and_regression() -> None:
    raw = _result(
        _case("a"),
        _case("b", "FAILED"),
        _case("c", "SKIPPED"),
        _case("d", "REGRESSION"),
        _case("e", "FIXED"),
    )
    assert [r["name"] for r in case_records(raw, failed_only=True)] == ["b", "d"]


def test_suite_filter_matches_the_suite_name_exactly() -> None:
    raw = {
        "suites": [
            {"name": "app.AuthTest", "cases": [_case("a")]},
            {"name": "app.AuthTestExtra", "cases": [_case("b")]},
        ]
    }
    assert [r["name"] for r in case_records(raw, suite="app.AuthTest")] == ["a"]


def test_records_name_the_matrix_configuration() -> None:
    raw = {
        "childReports": [
            {
                "child": {"fullDisplayName": "api » jdk=21 #5", "url": "u"},
                "result": _result(_case("t", "FAILED")),
            }
        ]
    }
    (record,) = case_records(raw)
    assert record["configuration"] == "api » jdk=21 #5"


def test_records_tolerate_missing_and_null_fields() -> None:
    raw = {"suites": [{"name": None, "cases": [{"name": "t", "status": None}]}]}
    (record,) = case_records(raw)
    assert (record["suite"], record["status"], record["duration"]) == ("", "", 0.0)


def test_an_empty_report_has_no_records() -> None:
    assert case_records({"suites": []}) == []
    assert case_records({}) == []
