"""Pipeline: Input Step plugin support (a build's ``input`` action).

Not part of base Jenkins: the ``pipeline-input-step`` plugin attaches an
``InputAction`` at ``/job/x/N/input/`` the first time a build reaches an
``input`` step, and each pending step is reachable beneath it by its id.

Four upstream quirks shape the design:

- **There is no ``/input/api/json``.** ``InputAction`` has no ``getApi()``, so
  Stapler hands ``api`` to ``getDynamic`` as an input id and answers 404. The
  pending steps are read from the build's own ``actions[]`` export instead,
  where ``InputAction`` appears as an exported bean. The first end-to-end run
  against the real plugin caught this; every mocked test had assumed the URL.
- A build only gains an ``InputAction`` once it reaches an ``input`` step, so
  none among its actions means "nothing has ever been asked" — and also
  "plugin absent". Both truthfully mean nothing awaits a decision.
- ``proceed`` and ``abort`` refuse with ``hudson.model.Failure`` ("already
  given", "You need to be X"), whose status code is not a stable contract.
  Every verb therefore reads the pending list before posting and re-reads it
  afterwards, so a refusal is reported as one rather than as a success.
- ``proceedEmpty`` on an input that declares parameters hands the pipeline
  ``null``, skipping their defaults. A parameterised input always goes through
  ``proceed`` with every parameter filled in.
"""

import json
from urllib.parse import quote

from .jenkins import (
    JenkinsClient,
    JenkinsError,
    JenkinsHTTPError,
    normalize_jenkins_path,
)

__all__ = ["InputError", "PipelineInput", "input_records"]

# Everything the CLI shows, and nothing else. Explicit rather than depth-based,
# because InputStepExecution's default export visibility would otherwise
# decide the payload's shape for us.
_TREE = (
    "actions[executions[id,settled,input[id,message,ok,cancel,submitter,"
    "parameters[name,type,description,choices,defaultParameterValue[value]]]]]"
)

# Codes a refused settlement may answer with. Failure's status has varied
# across core releases, so these are read as "check again" rather than trusted.
_REFUSAL_CODES = (400, 500)


class InputError(JenkinsError):
    """An input-step call that failed for a reason worth naming.

    ``reason`` is machine-readable so the prose stays in the CLI: one of
    ``no-build``, ``ambiguous``, ``unknown``, ``unknown-param``,
    ``bad-param``, ``refused``, ``unauthenticated`` or ``forbidden``.
    ``detail`` carries the offending id or parameter name, and ``value`` the
    offending value. ``options`` lists what the reader may pick from instead:
    the pending input ids, or the parameter names an input declares.
    ``submitter`` is who an input is reserved for, when it says.
    """

    def __init__(
        self,
        reason: str,
        *,
        detail: str = "",
        value: str = "",
        options: tuple[str, ...] = (),
        submitter: str = "",
    ) -> None:
        super().__init__(f"pipeline-input: {reason}")
        self.reason = reason
        self.detail = detail
        self.value = value
        self.options = options
        self.submitter = submitter


def input_records(executions: list[dict], build_url: str) -> list[dict]:
    """Shape pending input executions into jeeves display records."""
    page = f"{build_url.rstrip('/')}/input/"
    return [_record(item, page) for item in executions]


def _record(item: dict, page: str) -> dict:
    step = item.get("input") or {}
    return {
        "id": str(item.get("id") or step.get("id") or ""),
        "message": step.get("message") or "",
        "ok": step.get("ok") or "Proceed",
        "cancel": step.get("cancel") or "Abort",
        "submitter": step.get("submitter") or "",
        "parameters": [_parameter(p) for p in step.get("parameters") or []],
        "url": page,
    }


def _parameter(raw: dict) -> dict:
    default = raw.get("defaultParameterValue")
    return {
        "name": raw.get("name", ""),
        "type": _type_label(raw.get("type", "")),
        "description": raw.get("description") or "",
        "choices": list(raw.get("choices") or []),
        "default": default.get("value") if isinstance(default, dict) else None,
    }


def _type_label(raw_type: str) -> str:
    """``BooleanParameterDefinition`` → ``boolean``; unknown types kept whole."""
    suffix = "ParameterDefinition"
    if raw_type.endswith(suffix) and raw_type != suffix:
        return raw_type[: -len(suffix)].lower()
    return raw_type


class PipelineInput:
    """The input steps of one build, as three verbs over one Jenkins client.

    The build is resolved to a number on first use, so a permalink such as
    ``lastBuild`` cannot drift to a newer build between reading and posting.
    Mutators return ``"approved"``, ``"rejected"`` or ``"already"`` — the last
    when nothing was pending to begin with.
    """

    def __init__(
        self, client: JenkinsClient, job: str, build: int | str = "lastBuild"
    ) -> None:
        self._client = client
        self._job_path = normalize_jenkins_path(job)
        self._build = build
        self._number: int | None = None
        self._url = ""

    @property
    def number(self) -> int:
        """The resolved build number."""
        self._resolve()
        assert self._number is not None
        return self._number

    @property
    def resolved(self) -> int | None:
        """The build number if already resolved, without fetching it."""
        return self._number

    @property
    def url(self) -> str:
        """The resolved build's absolute URL, as Jenkins reports it."""
        self._resolve()
        return self._url

    # ── reading ──────────────────────────────────────────────────────────────

    def pending(self) -> list[dict]:
        """Every input step in this build still awaiting a decision."""
        payload = self._client.get_json(self._build_path(), params={"tree": _TREE})
        executions = [
            e
            for action in payload.get("actions") or []
            for e in (action or {}).get("executions") or []
        ]
        return [e for e in executions if not e.get("settled")]

    # ── deciding ─────────────────────────────────────────────────────────────

    def approve(self, input_id: str | None = None, params: dict | None = None) -> str:
        """Let the build proceed, supplying any parameters the input asks for."""
        execution = self._choose(input_id)
        if execution is None:
            return "already"
        step = execution.get("input") or {}
        declared = step.get("parameters") or []
        if declared:
            body = {"json": json.dumps(_proceed_payload(declared, params or {}))}
            self._settle(execution, "proceed", body)
        else:
            if params:
                raise InputError("unknown-param", detail=next(iter(params)))
            self._settle(execution, "proceedEmpty", None)
        return "approved"

    def reject(self, input_id: str | None = None) -> str:
        """Abort the build at this input step."""
        execution = self._choose(input_id)
        if execution is None:
            return "already"
        self._settle(execution, "abort", None)
        return "rejected"

    # ── internals ────────────────────────────────────────────────────────────

    def _resolve(self) -> None:
        if self._number is not None:
            return
        path = f"{self._job_path}/{self._build}"
        try:
            info = self._client.get_json(path, params={"tree": "number,url"})
        except JenkinsHTTPError as exc:
            if exc.status == 404:
                raise InputError("no-build", detail=str(self._build)) from exc
            raise
        self._number = int(info.get("number"))
        self._url = str(info.get("url") or "")

    def _build_path(self) -> str:
        return f"{self._job_path}/{self.number}"

    def _choose(self, input_id: str | None) -> dict | None:
        """The execution to act on, or ``None`` when nothing is pending."""
        pending = self.pending()
        ids = tuple(_execution_id(e) for e in pending)
        if input_id is not None:
            for execution in pending:
                if _execution_id(execution) == input_id:
                    return execution
            if not pending:
                return None
            raise InputError("unknown", detail=input_id, options=ids)
        if len(pending) > 1:
            raise InputError("ambiguous", options=ids)
        return pending[0] if pending else None

    def _settle(self, execution: dict, endpoint: str, data: dict | None) -> None:
        """POST a decision, then confirm Jenkins actually took it."""
        target = _execution_id(execution)
        submitter = str((execution.get("input") or {}).get("submitter") or "")
        path = f"{self._build_path()}/input/{quote(target, safe='')}/{endpoint}"
        try:
            self._client.post_action(path, data=data, allow=_REFUSAL_CODES)
        except JenkinsHTTPError as exc:
            if exc.status == 401:
                raise InputError("unauthenticated") from exc
            if exc.status == 403:
                raise InputError("forbidden", submitter=submitter) from exc
            if exc.status != 404:
                raise
            # 404: the step vanished between our read and our POST — settled
            # by someone else. The re-read below decides what that means.
        still = tuple(_execution_id(e) for e in self.pending())
        if target in still:
            raise InputError("refused", detail=target, submitter=submitter)


def _execution_id(execution: dict) -> str:
    return str(execution.get("id") or (execution.get("input") or {}).get("id") or "")


def _proceed_payload(declared: list[dict], supplied: dict) -> dict:
    """The ``json`` form body ``proceed`` parses, defaults filled in.

    Unknown names are refused before anything is posted, since upstream would
    reject the whole submission with "No such parameter definition".
    """
    names = [str(p.get("name", "")) for p in declared]
    for name in supplied:
        if name not in names:
            raise InputError("unknown-param", detail=name, options=tuple(names))
    entries = []
    for p in declared:
        name = str(p.get("name", ""))
        if name in supplied:
            value = _coerce(p, supplied[name])
        else:
            default = p.get("defaultParameterValue")
            if not isinstance(default, dict) or "value" not in default:
                continue
            value = default["value"]
        entries.append({"name": name, "value": value})
    return {"parameter": entries}


def _coerce(declared: dict, raw: str):
    """Booleans travel as JSON booleans; everything else as the string given."""
    if _type_label(str(declared.get("type", ""))) != "boolean":
        return raw
    lowered = raw.strip().lower()
    if lowered in ("true", "yes", "1"):
        return True
    if lowered in ("false", "no", "0"):
        return False
    raise InputError("bad-param", detail=str(declared.get("name", "")), value=raw)
