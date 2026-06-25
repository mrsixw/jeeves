"""Tests for the Jenkins API client."""

import pytest
import requests
import requests_mock as req_mock

from jeeves.jenkins import (
    JenkinsClient,
    JenkinsError,
    JenkinsLoginRequired,
    _normalize_jenkins_path,
)

BASE = "http://jenkins.example.com"


@pytest.fixture
def client() -> JenkinsClient:
    c = JenkinsClient(BASE, "admin", "secret")
    c._crumb_fetched = True  # skip crumb in non-crumb tests
    return c


@pytest.fixture
def anon_client() -> JenkinsClient:
    return JenkinsClient(BASE)


# ── _normalize_jenkins_path ──────────────────────────────────────────────────


def test_normalize_single_job() -> None:
    assert _normalize_jenkins_path("my-pipeline") == "job/my-pipeline"


def test_normalize_nested_job() -> None:
    assert _normalize_jenkins_path("folder/my-pipeline") == "job/folder/job/my-pipeline"


def test_normalize_deeply_nested() -> None:
    assert (
        _normalize_jenkins_path("team/project/deploy")
        == "job/team/job/project/job/deploy"
    )


def test_normalize_strips_leading_slash() -> None:
    assert _normalize_jenkins_path("/folder/job") == "job/folder/job/job"


# ── status ──────────────────────────────────────────────────────────────────


def test_status_returns_data(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/api/json", json={"mode": "NORMAL", "nodeDescription": "master"})
        data = client.status()
    assert data["mode"] == "NORMAL"
    assert data["nodeDescription"] == "master"


def test_status_connection_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/api/json", exc=requests.ConnectionError("refused"))
        with pytest.raises(JenkinsError, match="Cannot reach Jenkins"):
            client.status()


def test_status_http_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/api/json", status_code=403)
        with pytest.raises(JenkinsError, match="403"):
            client.status()


# ── browser-login redirect detection ────────────────────────────────────────


def test_too_many_redirects_raises_login_required(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/api/json", exc=requests.exceptions.TooManyRedirects())
        with pytest.raises(JenkinsLoginRequired, match="requires browser login"):
            client.status()


def test_commence_login_redirect_raises_login_required(
    client: JenkinsClient,
) -> None:
    login_url = f"{BASE}/securityRealm/commenceLogin?from=%2Fapi%2Fjson"
    with req_mock.Mocker() as m:
        m.get(
            f"{BASE}/api/json",
            status_code=302,
            headers={"Location": login_url},
        )
        m.get(login_url, text="<html>please log in</html>")
        with pytest.raises(JenkinsLoginRequired, match="requires browser login"):
            client.status()


def test_login_required_is_jenkins_error(client: JenkinsClient) -> None:
    # callers that catch JenkinsError still handle the login case
    assert issubclass(JenkinsLoginRequired, JenkinsError)


# ── jobs ────────────────────────────────────────────────────────────────────


def test_jobs_returns_list(client: JenkinsClient) -> None:
    payload = {"jobs": [{"name": "my-pipeline", "color": "blue"}]}
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/api/json", json=payload)
        result = client.jobs()
    assert len(result) == 1
    assert result[0]["name"] == "my-pipeline"


def test_jobs_empty_list(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/api/json", json={"jobs": []})
        result = client.jobs()
    assert result == []


def test_jobs_folder(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/myteam/api/json", json={"jobs": [{"name": "deploy"}]})
        result = client.jobs(folder="myteam")
    assert result[0]["name"] == "deploy"


def test_jobs_nested_folder(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(
            f"{BASE}/job/myteam/job/backend/api/json",
            json={"jobs": [{"name": "deploy"}]},
        )
        result = client.jobs(folder="myteam/backend")
    assert result[0]["name"] == "deploy"


def test_jobs_depth_passes_query_param(client: JenkinsClient) -> None:
    payload = {"jobs": [{"name": "x", "healthReport": [{"score": 80}]}]}
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/api/json", json=payload)
        result = client.jobs(depth=1)
    assert m.last_request.qs == {"depth": ["1"]}
    assert result[0]["healthReport"][0]["score"] == 80


# ── job / build_info ─────────────────────────────────────────────────────────


def test_job_returns_detail(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/my-pipeline/api/json", json={"name": "my-pipeline"})
        data = client.job("my-pipeline")
    assert data["name"] == "my-pipeline"


def test_builds_returns_list_with_tree_range(client: JenkinsClient) -> None:
    payload = {"builds": [{"number": 5, "result": "SUCCESS"}, {"number": 4}]}
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/my-pipeline/api/json", json=payload)
        result = client.builds("my-pipeline", limit=10)
    assert [b["number"] for b in result] == [5, 4]
    # the tree range selector caps the build list server-side
    tree = m.last_request.qs["tree"][0]
    assert "builds[" in tree
    assert "{0,10}" in tree


def test_build_info_returns_data(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(
            f"{BASE}/job/my-pipeline/lastBuild/api/json",
            json={"number": 42, "result": "SUCCESS"},
        )
        data = client.build_info("my-pipeline")
    assert data is not None
    assert data["number"] == 42


def test_build_info_specific_number(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/my-pipeline/7/api/json", json={"number": 7})
        data = client.build_info("my-pipeline", 7)
    assert data["number"] == 7


def test_build_info_404_returns_none(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/my-pipeline/lastFailedBuild/api/json", status_code=404)
        assert client.build_info("my-pipeline", "lastFailedBuild") is None


def test_build_info_other_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/my-pipeline/lastBuild/api/json", status_code=500)
        with pytest.raises(JenkinsError, match="500"):
            client.build_info("my-pipeline")


# ── build ───────────────────────────────────────────────────────────────────


def test_build_no_params(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/my-pipeline/build", status_code=201)
        client.build("my-pipeline")


def test_build_with_params(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/my-pipeline/buildWithParameters", status_code=201)
        client.build("my-pipeline", params={"ENV": "prod"})


def test_build_params_sent_as_form_body(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        adapter = m.post(f"{BASE}/job/my-pipeline/buildWithParameters", status_code=201)
        client.build("my-pipeline", params={"ENV": "prod", "BRANCH": "main"})
    # params must be in the request body, not the query string
    assert adapter.last_request.qs == {}
    assert "ENV=prod" in adapter.last_request.body
    assert "BRANCH=main" in adapter.last_request.body


def test_build_http_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/my-pipeline/build", status_code=404)
        with pytest.raises(JenkinsError, match="404"):
            client.build("my-pipeline")


def test_build_connection_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(
            f"{BASE}/job/my-pipeline/build",
            exc=requests.ConnectionError("refused"),
        )
        with pytest.raises(JenkinsError, match="Cannot reach Jenkins"):
            client.build("my-pipeline")


def test_build_nested_job(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/team/job/my-pipeline/build", status_code=201)
        client.build("team/my-pipeline")


# ── log ─────────────────────────────────────────────────────────────────────


def test_log_returns_text(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(
            f"{BASE}/job/my-pipeline/lastBuild/consoleText", text="Build started\nDone"
        )
        text = client.log("my-pipeline")
    assert "Build started" in text


def test_log_specific_build(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/my-pipeline/42/consoleText", text="ok")
        text = client.log("my-pipeline", build=42)
    assert text == "ok"


def test_log_http_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/my-pipeline/lastBuild/consoleText", status_code=404)
        with pytest.raises(JenkinsError, match="404"):
            client.log("my-pipeline")


def test_log_connection_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(
            f"{BASE}/job/my-pipeline/lastBuild/consoleText",
            exc=requests.ConnectionError("refused"),
        )
        with pytest.raises(JenkinsError, match="Cannot reach Jenkins"):
            client.log("my-pipeline")


def test_log_nested_job(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/job/team/job/my-pipeline/lastBuild/consoleText", text="ok")
        text = client.log("team/my-pipeline")
    assert text == "ok"


# ── queue ───────────────────────────────────────────────────────────────────


def test_queue_returns_items(client: JenkinsClient) -> None:
    payload = {
        "items": [
            {"why": "waiting for node", "stuck": False, "task": {"name": "deploy"}}
        ]
    }
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/queue/api/json", json=payload)
        items = client.queue()
    assert items[0]["why"] == "waiting for node"


def test_queue_empty(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/queue/api/json", json={"items": []})
        items = client.queue()
    assert items == []


# ── cancel ──────────────────────────────────────────────────────────────────


def test_cancel_posts_stop(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/my-pipeline/5/stop", status_code=200)
        client.cancel("my-pipeline", 5)


def test_cancel_http_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/my-pipeline/5/stop", status_code=404)
        with pytest.raises(JenkinsError, match="404"):
            client.cancel("my-pipeline", 5)


def test_cancel_connection_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(
            f"{BASE}/job/my-pipeline/5/stop",
            exc=requests.ConnectionError("refused"),
        )
        with pytest.raises(JenkinsError, match="Cannot reach Jenkins"):
            client.cancel("my-pipeline", 5)


def test_cancel_nested_job(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/team/job/my-pipeline/5/stop", status_code=200)
        client.cancel("team/my-pipeline", 5)


# ── nodes ───────────────────────────────────────────────────────────────────


def test_nodes_returns_list(client: JenkinsClient) -> None:
    payload = {
        "computer": [{"displayName": "agent1", "offline": False, "numExecutors": 4}]
    }
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/computer/api/json", json=payload)
        result = client.nodes()
    assert result[0]["displayName"] == "agent1"
    assert result[0]["offline"] is False


def test_nodes_empty(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/computer/api/json", json={"computer": []})
        result = client.nodes()
    assert result == []


def test_nodes_depth_passes_query_param(client: JenkinsClient) -> None:
    payload = {"computer": [{"displayName": "agent1", "monitorData": {}}]}
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/computer/api/json", json=payload)
        client.nodes(depth=1)
    assert m.last_request.qs == {"depth": ["1"]}


# ── auth ────────────────────────────────────────────────────────────────────


def test_no_auth_client_has_no_session_auth(anon_client: JenkinsClient) -> None:
    assert anon_client._session.auth is None


def test_auth_client_has_session_auth(client: JenkinsClient) -> None:
    assert client._session.auth is not None


# ── CSRF crumb ───────────────────────────────────────────────────────────────


def test_fetch_crumb_sets_session_header() -> None:
    fresh = JenkinsClient(BASE, "admin", "secret")
    with req_mock.Mocker() as m:
        m.get(
            f"{BASE}/crumbIssuer/api/json",
            json={"crumb": "abc123", "crumbRequestField": "Jenkins-Crumb"},
        )
        m.post(f"{BASE}/job/my-pipeline/build", status_code=201)
        fresh.build("my-pipeline")
    assert fresh._session.headers.get("Jenkins-Crumb") == "abc123"


def test_fetch_crumb_unavailable_silently_ignored() -> None:
    fresh = JenkinsClient(BASE, "admin", "secret")
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/crumbIssuer/api/json", status_code=404)
        m.post(f"{BASE}/job/my-pipeline/build", status_code=201)
        fresh.build("my-pipeline")
    assert "Jenkins-Crumb" not in fresh._session.headers


def test_fetch_crumb_only_called_once() -> None:
    fresh = JenkinsClient(BASE, "admin", "secret")
    with req_mock.Mocker() as m:
        crumb_adapter = m.get(
            f"{BASE}/crumbIssuer/api/json",
            json={"crumb": "tok", "crumbRequestField": "Jenkins-Crumb"},
        )
        m.post(f"{BASE}/job/my-pipeline/build", status_code=201)
        m.post(f"{BASE}/job/my-pipeline/5/stop", status_code=200)
        fresh.build("my-pipeline")
        fresh.cancel("my-pipeline", 5)
    assert crumb_adapter.call_count == 1


# ── whoami ───────────────────────────────────────────────────────────────────


def test_whoami_returns_user_data(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/me/api/json", json={"id": "alice", "fullName": "Alice Smith"})
        data = client.whoami()
    assert data["id"] == "alice"
    assert data["fullName"] == "Alice Smith"


def test_whoami_anonymous(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/me/api/json", json={"id": "anonymous", "fullName": "anonymous"})
        data = client.whoami()
    assert data["id"] == "anonymous"


def test_whoami_http_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/me/api/json", status_code=403)
        with pytest.raises(JenkinsError, match="403"):
            client.whoami()


def test_whoami_connection_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.get(f"{BASE}/me/api/json", exc=requests.ConnectionError("refused"))
        with pytest.raises(JenkinsError, match="Cannot reach Jenkins"):
            client.whoami()
