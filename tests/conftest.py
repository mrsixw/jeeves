"""Shared pytest fixtures: HTTP-level Jenkins mocking for CLI tests."""

import pytest

# Base URL the CLI talks to in HTTP-mocked tests (injected via JEEVES_URL).
JENKINS_URL = "http://jenkins.example.com"


def api(path: str = "") -> str:
    """Mock-Jenkins URL for a path's /api/json endpoint."""
    suffix = f"/{path.strip('/')}" if path else ""
    return f"{JENKINS_URL}{suffix}/api/json"


def url(path: str) -> str:
    """Mock-Jenkins URL for a raw (non-JSON) path."""
    return f"{JENKINS_URL}/{path.lstrip('/')}"


@pytest.fixture
def jenkins(requests_mock, monkeypatch):
    """Point the CLI at a requests-mock Jenkins.

    Tests register endpoints on the returned mocker and the real
    ``JenkinsClient`` speaks HTTP to them; any unregistered request fails
    as a connection error rather than escaping to the network.
    """
    monkeypatch.setenv("JEEVES_URL", JENKINS_URL)
    return requests_mock
