"""Jenkins HTTP API client."""

import requests
from requests.auth import HTTPBasicAuth


class JenkinsError(Exception):
    """Raised when a Jenkins API call fails."""


class JenkinsClient:
    def __init__(self, url: str, username: str = "", token: str = "") -> None:
        self._base = url.rstrip("/")
        self._session = requests.Session()
        if username and token:
            self._session.auth = HTTPBasicAuth(username, token)

    def _get(self, path: str) -> dict:
        suffix = f"/{path.strip('/')}" if path else ""
        url = f"{self._base}{suffix}/api/json"
        try:
            resp = self._session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as exc:
            raise JenkinsError(f"Cannot reach Jenkins at {self._base}") from exc
        except requests.exceptions.HTTPError as exc:
            raise JenkinsError(f"Jenkins returned {resp.status_code}") from exc
        except requests.exceptions.RequestException as exc:
            raise JenkinsError(str(exc)) from exc

    def _post(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{self._base}/{path.lstrip('/')}"
        try:
            resp = self._session.post(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as exc:
            raise JenkinsError(f"Jenkins returned {resp.status_code}") from exc
        except requests.exceptions.RequestException as exc:
            raise JenkinsError(str(exc)) from exc

    def status(self) -> dict:
        return self._get("")

    def jobs(self, folder: str | None = None) -> list[dict]:
        path = f"job/{folder}" if folder else ""
        return self._get(path).get("jobs", [])

    def build(self, job: str, params: dict | None = None) -> None:
        endpoint = f"job/{job}/buildWithParameters" if params else f"job/{job}/build"
        self._post(endpoint, params=params)

    def log(self, job: str, build: int | str = "lastBuild") -> str:
        url = f"{self._base}/job/{job}/{build}/consoleText"
        try:
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.HTTPError as exc:
            raise JenkinsError(f"Jenkins returned {resp.status_code}") from exc
        except requests.exceptions.RequestException as exc:
            raise JenkinsError(str(exc)) from exc

    def queue(self) -> list[dict]:
        return self._get("queue").get("items", [])

    def cancel(self, job: str, build: int) -> None:
        self._post(f"job/{job}/{build}/stop")

    def nodes(self) -> list[dict]:
        return self._get("computer").get("computer", [])
