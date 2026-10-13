"""Lockable Resources plugin support (the ``lockable-resources`` root action).

Not part of base Jenkins. The endpoints exist only when the plugin is
installed, and ``createResource``/``deleteResource`` are UI-facing
(``@Restricted(NoExternalUse.class)`` upstream), so they are absent from older
plugin releases. Everything this module knows that the base client does not is
how to tell those cases apart from an ordinary missing resource.

Two upstream quirks shape the design. Mutators answer by forwarding to the
previous page rather than returning JSON, so only the status code is
meaningful; and each takes a single resource, since the request parameter is
``resource`` with no list support.
"""

from .jenkins import JenkinsClient, JenkinsError, JenkinsHTTPError

__all__ = ["LockableError", "LockableResources", "resource_records"]

# The plugin's root action, i.e. everything hangs off /lockable-resources/.
_ROOT = "lockable-resources"

# Endpoints present in every plugin release jeeves can meet, so a 404 from one
# of these means the named resource is absent rather than the endpoint.
_STABLE = frozenset({"reserve", "unreserve", "unlock", "reset"})


class LockableError(JenkinsError):
    """A lockable-resources call that failed for a reason worth naming.

    ``reason`` is machine-readable so the prose stays in the CLI: one of
    ``plugin-missing``, ``endpoint-missing``, ``unknown``, ``busy``,
    ``unauthenticated`` or ``forbidden``. ``holder`` carries who has the
    resource when that is known. Anything outside this set stays a plain
    :class:`~jeeves.jenkins.JenkinsHTTPError` and gets the CLI's generic
    treatment.
    """

    def __init__(self, reason: str, resource: str = "", holder: str = "") -> None:
        super().__init__(f"lockable-resources: {reason}")
        self.reason = reason
        self.resource = resource
        self.holder = holder


def resource_records(raw: list[dict], base_url: str) -> list[dict]:
    """Shape the plugin's resource payloads into jeeves display records.

    ``state`` is derived once from the plugin's three overlapping booleans so
    consumers get one field instead of having to know their precedence.
    """
    page = f"{base_url}/{_ROOT}/"
    return [_record(item, page) for item in raw]


def _record(item: dict, page: str) -> dict:
    if item.get("locked"):
        state = "locked"
    elif item.get("reservedBy") or item.get("reserved"):
        state = "reserved"
    else:
        state = "free"
    return {
        "name": item.get("name", ""),
        "description": item.get("description") or "",
        "note": item.get("note") or "",
        "labels": _labels(item),
        "state": state,
        "reserved_by": item.get("reservedBy") or "",
        "reserved_by_email": item.get("reservedByEmail") or "",
        # Kept raw: plugin versions differ on ISO string versus epoch millis.
        "reserved_at": item.get("reservedTimestamp"),
        "lock_reason": item.get("lockReason") or "",
        "lock_cause": item.get("lockCause") or "",
        "build_name": item.get("buildName") or "",
        "ephemeral": bool(item.get("ephemeral")),
        "stolen": bool(item.get("stolen")),
        # There is no per-resource page, so every record points at the roster.
        "url": page,
    }


def _labels(item: dict) -> list[str]:
    """A resource's labels, preferring the list the plugin exposes."""
    listed = item.get("labelsAsList")
    if isinstance(listed, list):
        return [str(label) for label in listed]
    return str(item.get("labels") or "").split()


class LockableResources:
    """The plugin's resources, as seven verbs over one Jenkins client.

    Every mutator returns an outcome string — its own past tense, or
    ``"already"`` when the resource was in the requested state to begin with —
    so callers pick their wording without re-deriving state.
    """

    def __init__(self, client: JenkinsClient) -> None:
        self._client = client
        self._identity: str | None = None

    # ── reading ──────────────────────────────────────────────────────────────

    def resources(self) -> list[dict]:
        """Every resource on the register.

        A 404 here is unambiguous: the root action itself is absent, so the
        plugin is not installed.
        """
        try:
            payload = self._client.get_json(_ROOT)
        except JenkinsHTTPError as exc:
            if exc.status == 404:
                raise LockableError("plugin-missing") from exc
            raise
        return payload.get("resources", [])

    def resource(self, name: str) -> dict | None:
        """One resource by name, or ``None``.

        The plugin exposes no per-resource endpoint, so this filters the
        roster client-side.
        """
        for item in self.resources():
            if item.get("name") == name:
                return item
        return None

    # ── changing state ───────────────────────────────────────────────────────

    def reserve(self, name: str, reason: str = "") -> str:
        data = {"resource": name}
        if reason:
            data["reason"] = reason
        return self._mutate("reserve", name, data, "reserved")

    def unreserve(self, name: str) -> str:
        return self._mutate("unreserve", name, {"resource": name}, "unreserved")

    def unlock(self, name: str) -> str:
        if not self._state(name).get("locked"):
            return "already"
        return self._mutate("unlock", name, {"resource": name}, "unlocked")

    def reset(self, name: str) -> str:
        if self._state(name).get("free"):
            return "already"
        return self._mutate("reset", name, {"resource": name}, "reset")

    # ── adding and removing ──────────────────────────────────────────────────

    def create(
        self, name: str, description: str = "", labels: tuple[str, ...] = ()
    ) -> str:
        data = {
            "name": name,
            "description": description,
            # The plugin parses labels out of one space-separated string.
            "labels": " ".join(labels),
        }
        return self._mutate("createResource", name, data, "created", allow=(409,))

    def delete(self, name: str) -> str:
        return self._mutate("deleteResource", name, {"resource": name}, "deleted")

    # ── internals ────────────────────────────────────────────────────────────

    def _mutate(
        self,
        endpoint: str,
        name: str,
        data: dict,
        outcome: str,
        *,
        allow: tuple[int, ...] = (),
    ) -> str:
        try:
            status = self._client.post_action(
                f"{_ROOT}/{endpoint}", data=data, allow=allow
            )
        except JenkinsHTTPError as exc:
            return self._interpret(exc, endpoint, name)
        # 409 reaches here only when the caller allowed it: already exists.
        return "already" if status == 409 else outcome

    def _interpret(self, exc: JenkinsHTTPError, endpoint: str, name: str) -> str:
        """Turn a failed mutator into an outcome or a named error.

        Probes the roster only on this path, so the happy path costs no extra
        request.
        """
        if exc.status == 401:
            raise LockableError("unauthenticated", name) from exc
        if exc.status == 404:
            return self._interpret_404(exc, endpoint, name)
        if exc.status == 403:
            # Unreserving a resource nobody holds is a 403 for anyone short of
            # an administrator, which is really "there was nothing to release".
            # Reserved-ness, not freeness: a resource locked by a build is not
            # free, yet still carries no reservation to release.
            if endpoint == "unreserve" and not self._reserved_by(name):
                return "already"
            raise LockableError("forbidden", name) from exc
        if exc.status == 423:
            if endpoint == "reserve":
                holder = str((self.resource(name) or {}).get("reservedBy") or "")
                if holder and holder == self._who():
                    return "already"
                raise LockableError("busy", name, holder) from exc
            raise LockableError("busy", name) from exc
        raise exc

    def _interpret_404(self, exc: JenkinsHTTPError, endpoint: str, name: str) -> str:
        """Tell plugin-absent from plugin-too-old from resource-unknown.

        A 404 is ambiguous on every mutator: with the plugin absent there is no
        ``/lockable-resources/reserve`` either, so Jenkins answers exactly as
        it does for a resource that is not on the register. The roster settles
        it — and if the roster read fails for its own reasons, that exception is
        better than a guess.
        """
        roster = self.resources()  # raises LockableError("plugin-missing") on 404
        if endpoint in _STABLE:
            raise LockableError("unknown", name) from exc
        if endpoint == "deleteResource" and not any(
            item.get("name") == name for item in roster
        ):
            # Nothing to strike off, which is the state the caller wanted.
            return "already"
        # The root action answers but the mutator does not: an old plugin.
        raise LockableError("endpoint-missing", name) from exc

    def _reserved_by(self, name: str) -> str:
        """Who holds this resource's reservation, if anyone."""
        item = self.resource(name)
        return str((item or {}).get("reservedBy") or "")

    def _state(self, name: str) -> dict:
        """The resource as it stands, for verbs whose POST cannot report it.

        Unlocking or resetting something already in good order is a silent
        no-op upstream, answering 200 indistinguishably from real work. These
        two therefore read before they write, rather than claim to have done
        something they did not do.
        """
        item = self.resource(name)
        if item is None:
            raise LockableError("unknown", name)
        return item

    def _who(self) -> str:
        """The authenticated user's id, for spotting a reservation as our own.

        An unreadable ``/me`` degrades to the non-idempotent message rather
        than failing the command outright.
        """
        if self._identity is None:
            try:
                self._identity = str(self._client.whoami().get("id") or "")
            except JenkinsError:
                self._identity = ""
        return self._identity
