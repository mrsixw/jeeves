"""Tests for the Pipeline: Input Step plugin surface."""

import json
from urllib.parse import parse_qs

import pytest
import requests_mock as req_mock

from jeeves.jenkins import JenkinsClient, JenkinsHTTPError
from jeeves.pipeline_input import InputError, PipelineInput, input_records

BASE = "http://jenkins.example.com"
BUILD = f"{BASE}/job/deploy/42"
RESOLVE = f"{BASE}/job/deploy/lastBuild/api/json"
_INPUT_ACTION = "org.jenkinsci.plugins.workflow.support.steps.input.InputAction"
INPUTS = f"{BUILD}/api/json"


@pytest.fixture
def client() -> JenkinsClient:
    c = JenkinsClient(BASE, "admin", "secret")
    c._crumb_fetched = True  # skip crumb in non-crumb tests
    return c


@pytest.fixture
def inputs(client) -> PipelineInput:
    return PipelineInput(client, "deploy")


def _execution(input_id: str = "Ship", **step) -> dict:
    body = {
        "id": input_id,
        "message": "Ship it?",
        "ok": "Ship it",
        "cancel": None,
        "submitter": None,
        "parameters": [],
    }
    body.update(step)
    return {"id": input_id, "settled": False, "input": body}


def _resolve(m: req_mock.Mocker, number: int = 42) -> None:
    m.get(RESOLVE, json={"number": number, "url": f"{BASE}/job/deploy/{number}/"})


def _actions(executions: list[dict] | None) -> dict:
    """A build payload whose actions carry an InputAction, or none at all."""
    actions: list[dict] = [{"_class": "hudson.model.CauseAction"}, {}]
    if executions is not None:
        actions.append({"_class": _INPUT_ACTION, "executions": executions})
    return {"actions": actions}


def _pending(m: req_mock.Mocker, *responses: list[dict]) -> None:
    """Register successive pending lists: before the POST, then after it."""
    m.get(INPUTS, [{"json": _actions(r)} for r in responses])


def _string(name: str, default: str | None = "x") -> dict:
    p = {"name": name, "type": "StringParameterDefinition", "description": ""}
    if default is not None:
        p["defaultParameterValue"] = {"value": default}
    return p


def _boolean(name: str, default: bool = False) -> dict:
    return {
        "name": name,
        "type": "BooleanParameterDefinition",
        "defaultParameterValue": {"value": default},
    }


def _last_post(m: req_mock.Mocker):
    """The decision itself; ``last_request`` is the confirming re-read."""
    return [r for r in m.request_history if r.method == "POST"][-1]


def _posted_json(m: req_mock.Mocker) -> dict:
    body = parse_qs(_last_post(m).text)
    return json.loads(body["json"][0])


# ── input_records ────────────────────────────────────────────────────────────


def test_records_shape_a_pending_input() -> None:
    raw = [
        _execution(
            "Release",
            message="Ship to prod?",
            cancel="Not today",
            submitter="ops",
            parameters=[
                {
                    "name": "TARGET",
                    "type": "ChoiceParameterDefinition",
                    "description": "where",
                    "choices": ["eu", "us"],
                    "defaultParameterValue": {"value": "eu"},
                }
            ],
        )
    ]
    (record,) = input_records(raw, f"{BUILD}/")
    assert record == {
        "id": "Release",
        "message": "Ship to prod?",
        "ok": "Ship it",
        "cancel": "Not today",
        "submitter": "ops",
        "parameters": [
            {
                "name": "TARGET",
                "type": "choice",
                "description": "where",
                "choices": ["eu", "us"],
                "default": "eu",
            }
        ],
        "url": f"{BUILD}/input/",
    }


def test_records_fall_back_to_jenkins_button_labels() -> None:
    """Upstream defaults ok/cancel to Proceed/Abort when the step names none."""
    (record,) = input_records([_execution(ok=None)], BUILD)
    assert (record["ok"], record["cancel"]) == ("Proceed", "Abort")


def test_records_keep_an_unrecognised_parameter_type_whole() -> None:
    raw = [_execution(parameters=[{"name": "P", "type": "WeirdThing"}])]
    assert input_records(raw, BUILD)[0]["parameters"][0]["type"] == "WeirdThing"


# ── pending ──────────────────────────────────────────────────────────────────


def test_pending_resolves_the_permalink_to_a_number(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()])
        inputs.pending()
        assert m.request_history[-1].url.startswith(INPUTS)
    assert inputs.number == 42


def test_pending_asks_for_an_explicit_tree(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [])
        inputs.pending()
        tree = m.last_request.qs["tree"][0]
    assert tree.startswith("actions[executions[id,settled,input[")


def test_pending_drops_settled_executions(inputs) -> None:
    settled = _execution("Done")
    settled["settled"] = True
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [settled, _execution("Open")])
        assert [e["id"] for e in inputs.pending()] == ["Open"]


def test_pending_reads_the_build_actions_not_the_input_url(inputs) -> None:
    """InputAction has no getApi(): /input/api/json is getDynamic("api"), a 404.

    The real plugin settled this — the first e2e run saw every paused build
    reported as awaiting nothing. Its executions are exported on the build.
    """
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()])
        inputs.pending()
        urls = [r.url for r in m.request_history]
    assert not any("/input/" in u for u in urls)
    assert urls[-1].startswith(INPUTS)


def test_pending_without_an_input_action_means_nothing_was_asked(inputs) -> None:
    """No input step has run, or the plugin is absent: either way, nothing."""
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, None)
        assert inputs.pending() == []


def test_pending_of_an_unknown_build_is_named(inputs) -> None:
    with req_mock.Mocker() as m:
        m.get(RESOLVE, status_code=404)
        with pytest.raises(InputError) as exc:
            inputs.pending()
    assert (exc.value.reason, exc.value.detail) == ("no-build", "lastBuild")


def test_pending_propagates_a_forbidden_read(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        m.get(INPUTS, status_code=403)
        with pytest.raises(JenkinsHTTPError) as exc:
            inputs.pending()
    assert exc.value.status == 403


def test_explicit_build_number_is_used_as_given(client) -> None:
    with req_mock.Mocker() as m:
        m.get(
            f"{BASE}/job/deploy/7/api/json",
            json={"number": 7, "url": "", **_actions([])},
        )
        assert PipelineInput(client, "deploy", 7).pending() == []


def test_nested_job_paths_are_encoded(client) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/team/job/app/lastBuild/api/json", json={"number": 3})
        m.get(f"{BASE}/job/team/job/app/3/api/json", json=_actions([]))
        assert PipelineInput(client, "team/app").pending() == []


# ── approve ──────────────────────────────────────────────────────────────────


def test_approve_without_parameters_posts_proceed_empty(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()], [])
        m.post(f"{BUILD}/input/Ship/proceedEmpty", status_code=200)
        assert inputs.approve() == "approved"
        posts = [r for r in m.request_history if r.method == "POST"]
    assert [r.url for r in posts] == [f"{BUILD}/input/Ship/proceedEmpty"]


def test_approve_with_parameters_posts_proceed_json(inputs) -> None:
    ex = _execution(parameters=[_string("TARGET", "eu"), _boolean("DRY")])
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [ex], [])
        m.post(f"{BUILD}/input/Ship/proceed", status_code=200)
        inputs.approve(params={"TARGET": "us", "DRY": "true"})
        sent = _posted_json(m)
    assert sent == {
        "parameter": [{"name": "TARGET", "value": "us"}, {"name": "DRY", "value": True}]
    }


def test_approve_fills_unspecified_parameters_from_defaults(inputs) -> None:
    """proceedEmpty would hand the pipeline null and skip these defaults."""
    ex = _execution(parameters=[_string("TARGET", "eu"), _boolean("DRY", True)])
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [ex], [])
        m.post(f"{BUILD}/input/Ship/proceed", status_code=200)
        inputs.approve()
        sent = _posted_json(m)
    assert sent["parameter"] == [
        {"name": "TARGET", "value": "eu"},
        {"name": "DRY", "value": True},
    ]


def test_approve_omits_a_parameter_with_no_default_and_no_value(inputs) -> None:
    ex = _execution(parameters=[_string("NOTE", default=None), _string("T", "a")])
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [ex], [])
        m.post(f"{BUILD}/input/Ship/proceed", status_code=200)
        inputs.approve()
        sent = _posted_json(m)
    assert sent["parameter"] == [{"name": "T", "value": "a"}]


def test_approve_refuses_an_unknown_parameter_before_posting(inputs) -> None:
    ex = _execution(parameters=[_string("TARGET")])
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [ex])
        with pytest.raises(InputError) as exc:
            inputs.approve(params={"TARGETX": "us"})
        assert not [r for r in m.request_history if r.method == "POST"]
    assert exc.value.reason == "unknown-param"
    assert (exc.value.detail, exc.value.options) == ("TARGETX", ("TARGET",))


def test_approve_refuses_parameters_for_an_input_that_takes_none(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()])
        with pytest.raises(InputError) as exc:
            inputs.approve(params={"X": "1"})
        assert not [r for r in m.request_history if r.method == "POST"]
    assert (exc.value.reason, exc.value.options) == ("unknown-param", ())


@pytest.mark.parametrize("raw", ["maybe", ""])
def test_approve_refuses_a_non_boolean_for_a_boolean(inputs, raw) -> None:
    ex = _execution(parameters=[_boolean("DRY")])
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [ex])
        with pytest.raises(InputError) as exc:
            inputs.approve(params={"DRY": raw})
    assert (exc.value.reason, exc.value.detail, exc.value.value) == (
        "bad-param",
        "DRY",
        raw,
    )


@pytest.mark.parametrize(
    ("raw", "expected"), [("yes", True), ("1", True), ("FALSE", False), ("no", False)]
)
def test_approve_accepts_common_boolean_spellings(inputs, raw, expected) -> None:
    ex = _execution(parameters=[_boolean("DRY")])
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [ex], [])
        m.post(f"{BUILD}/input/Ship/proceed", status_code=200)
        inputs.approve(params={"DRY": raw})
        assert _posted_json(m)["parameter"] == [{"name": "DRY", "value": expected}]


def test_approve_with_nothing_pending_is_idempotent(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [])
        assert inputs.approve() == "already"
        assert not [r for r in m.request_history if r.method == "POST"]


def test_approve_with_an_id_but_nothing_pending_is_idempotent(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [])
        assert inputs.approve("Ship") == "already"


def test_approve_needs_an_id_when_several_are_pending(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution("A"), _execution("B")])
        with pytest.raises(InputError) as exc:
            inputs.approve()
    assert (exc.value.reason, exc.value.options) == ("ambiguous", ("A", "B"))


def test_approve_picks_the_named_input_among_several(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution("A"), _execution("B")], [_execution("A")])
        m.post(f"{BUILD}/input/B/proceedEmpty", status_code=200)
        assert inputs.approve("B") == "approved"


def test_approve_of_an_unknown_id_names_the_pending_ones(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution("A")])
        with pytest.raises(InputError) as exc:
            inputs.approve("Z")
    assert (exc.value.reason, exc.value.detail, exc.value.options) == (
        "unknown",
        "Z",
        ("A",),
    )


def test_approve_url_encodes_the_input_id(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution("a b/c")], [])
        m.post(f"{BUILD}/input/a%20b%2Fc/proceedEmpty", status_code=200)
        inputs.approve()
        assert _last_post(m).url.endswith("/input/a%20b%2Fc/proceedEmpty")


@pytest.mark.parametrize("status", [200, 400, 500])
def test_approve_still_pending_afterwards_is_a_refusal(inputs, status) -> None:
    """Failure's status is no contract, so the re-read is what decides."""
    ex = _execution(submitter="ops")
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [ex], [ex])
        m.post(f"{BUILD}/input/Ship/proceedEmpty", status_code=status)
        with pytest.raises(InputError) as exc:
            inputs.approve()
    assert (exc.value.reason, exc.value.submitter) == ("refused", "ops")


def test_approve_403_is_forbidden(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()])
        m.post(f"{BUILD}/input/Ship/proceedEmpty", status_code=403)
        with pytest.raises(InputError) as exc:
            inputs.approve()
    assert exc.value.reason == "forbidden"


def test_approve_401_is_unauthenticated(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()])
        m.post(f"{BUILD}/input/Ship/proceedEmpty", status_code=401)
        with pytest.raises(InputError) as exc:
            inputs.approve()
    assert exc.value.reason == "unauthenticated"


def test_approve_404_after_someone_else_settled_it_succeeds(inputs) -> None:
    """The step vanished between read and POST; the re-read finds it gone."""
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()], [])
        m.post(f"{BUILD}/input/Ship/proceedEmpty", status_code=404)
        assert inputs.approve() == "approved"


def test_approve_propagates_an_unexpected_status(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()])
        m.post(f"{BUILD}/input/Ship/proceedEmpty", status_code=502)
        with pytest.raises(JenkinsHTTPError) as exc:
            inputs.approve()
    assert exc.value.status == 502


def test_approve_fetches_a_crumb_first() -> None:
    client = JenkinsClient(BASE, "admin", "secret")
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()], [])
        m.get(
            f"{BASE}/crumbIssuer/api/json",
            json={"crumbRequestField": "Jenkins-Crumb", "crumb": "c0ffee"},
        )
        m.post(f"{BUILD}/input/Ship/proceedEmpty", status_code=200)
        PipelineInput(client, "deploy").approve()
        assert _last_post(m).headers["Jenkins-Crumb"] == "c0ffee"


# ── reject ───────────────────────────────────────────────────────────────────


def test_reject_posts_abort(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()], [])
        m.post(f"{BUILD}/input/Ship/abort", status_code=200)
        assert inputs.reject() == "rejected"
        assert _last_post(m).url == f"{BUILD}/input/Ship/abort"


def test_reject_with_nothing_pending_is_idempotent(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [])
        assert inputs.reject() == "already"


def test_reject_still_pending_afterwards_is_a_refusal(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution()], [_execution()])
        m.post(f"{BUILD}/input/Ship/abort", status_code=200)
        with pytest.raises(InputError) as exc:
            inputs.reject()
    assert exc.value.reason == "refused"


def test_reject_needs_an_id_when_several_are_pending(inputs) -> None:
    with req_mock.Mocker() as m:
        _resolve(m)
        _pending(m, [_execution("A"), _execution("B")])
        with pytest.raises(InputError) as exc:
            inputs.reject()
    assert exc.value.reason == "ambiguous"
