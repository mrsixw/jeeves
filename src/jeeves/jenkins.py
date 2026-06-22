"""Jenkins HTTP API client."""

import requests
from requests.auth import HTTPBasicAuth


class JenkinsError(Exception):
    """Raised when a Jenkins API call fails."""


def _normalize_jenkins_path(path: str) -> str:
    """Normalize a slash-separated job/folder path to Jenkins URL format.

    Jenkins encodes nested paths with intermediate /job/ prefixes, e.g.
    'folder/subfolder/job' becomes 'job/folder/job/subfolder/job/job'.
    """
    parts = [p for p in path.split("/") if p]
    return "job/" + "/job/".join(parts)


class JenkinsClient:
    def __init__(self, url: str, username: str = "", token: str = "") -> None:
        self._base = url.rstrip("/")
        self._session = requests.Session()
        if username and token:
            self._session.auth = HTTPBasicAuth(username, token)
        self._crumb_fetched = False

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            resp = self._session.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.ConnectionError as exc:
            raise JenkinsError(f"Cannot reach Jenkins at {self._base}") from exc
        except requests.exceptions.HTTPError as exc:
            raise JenkinsError(f"Jenkins returned {resp.status_code}") from exc
        except requests.exceptions.RequestException as exc:
            raise JenkinsError(str(exc)) from exc

    def _get(self, path: str, params: dict | None = None) -> dict:
        suffix = f"/{path.strip('/')}" if path else ""
        url = f"{self._base}{suffix}/api/json"
        return self._request("GET", url, params=params, timeout=10).json()

    def _fetch_crumb(self) -> None:
        """Fetch the CSRF crumb and apply it to session headers.

        Silently no-ops if crumb issuer is unavailable (CSRF disabled).
        """
        url = f"{self._base}/crumbIssuer/api/json"
        try:
            resp = self._session.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                crumb = data.get("crumb")
                header_name = data.get("crumbRequestField")
                if crumb and header_name:
                    self._session.headers.update({header_name: crumb})
        except requests.exceptions.RequestException:
            pass
        finally:
            self._crumb_fetched = True

    def _post(self, path: str, data: dict | None = None) -> requests.Response:
        if not self._crumb_fetched:
            self._fetch_crumb()
        url = f"{self._base}/{path.lstrip('/')}"
        return self._request("POST", url, data=data, timeout=10)

    def status(self) -> dict:
        return self._get("")

    def jobs(self, folder: str | None = None, depth: int = 0) -> list[dict]:
        path = _normalize_jenkins_path(folder) if folder else ""
        params = {"depth": depth} if depth else None
        return self._get(path, params=params).get("jobs", [])

    def build(self, job: str, params: dict | None = None) -> None:
        job_path = _normalize_jenkins_path(job)
        endpoint = f"{job_path}/buildWithParameters" if params else f"{job_path}/build"
        self._post(endpoint, data=params)

    def log(self, job: str, build: int | str = "lastBuild") -> str:
        job_path = _normalize_jenkins_path(job)
        url = f"{self._base}/{job_path}/{build}/consoleText"
        return self._request("GET", url, timeout=30).text

    def queue(self) -> list[dict]:
        return self._get("queue").get("items", [])

    def cancel(self, job: str, build: int) -> None:
        job_path = _normalize_jenkins_path(job)
        self._post(f"{job_path}/{build}/stop")

    def nodes(self) -> list[dict]:
        return self._get("computer").get("computer", [])

    def whoami(self) -> dict:
        return self._get("me")
