"""Tests for the Jenkins API client."""

import pytest
import requests
import requests_mock as req_mock

from jeeves.jenkins import JenkinsClient, JenkinsError

BASE = "http://jenkins.example.com"


@pytest.fixture
def client() -> JenkinsClient:
    return JenkinsClient(BASE, "admin", "secret")


@pytest.fixture
def anon_client() -> JenkinsClient:
    return JenkinsClient(BASE)


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


# ── build ───────────────────────────────────────────────────────────────────


def test_build_no_params(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/my-pipeline/build", status_code=201)
        client.build("my-pipeline")


def test_build_with_params(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/my-pipeline/buildWithParameters", status_code=201)
        client.build("my-pipeline", params={"ENV": "prod"})


def test_build_http_error_raises(client: JenkinsClient) -> None:
    with req_mock.Mocker() as m:
        m.post(f"{BASE}/job/my-pipeline/build", status_code=404)
        with pytest.raises(JenkinsError, match="404"):
            client.build("my-pipeline")


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


# ── auth ────────────────────────────────────────────────────────────────────


def test_no_auth_client_has_no_session_auth(anon_client: JenkinsClient) -> None:
    assert anon_client._session.auth is None


def test_auth_client_has_session_auth(client: JenkinsClient) -> None:
    assert client._session.auth is not None
