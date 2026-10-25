"""Credentials plugin support — metadata only, never secrets.

Not part of base Jenkins, though near-universal: the ``credentials`` plugin
serves a ``ViewCredentialsAction`` at ``/credentials/`` on the root and on
every folder. Its export lists ``stores`` (keyed by store name, e.g.
``system`` or ``folder``), each with ``domains`` (keyed by url name, ``_`` for
the global domain), each with ``credentials``.

Two upstream facts shape the design:

- A context exports **only its own stores**, not the ones it inherits. So
  "what can this folder see?" means reading the folder and every ancestor up
  to the root, nearest first.
- The plugin exports ``id``, ``displayName``, ``typeName``, ``description`` and
  ``fullName`` — no secret material. The ``tree`` query below pins exactly
  those fields, so a future upstream export cannot widen what jeeves fetches.
"""

from urllib.parse import quote

from .jenkins import (
    JenkinsClient,
    JenkinsError,
    JenkinsHTTPError,
    normalize_jenkins_path,
)

__all__ = ["CredentialStores", "CredentialsError", "credential_records"]

_ROOT = "credentials"

# Stapler hands each map value the same subtree, so one query reaches through
# both the stores map and each store's domains map.
_TREE = (
    "stores[domains[urlName,displayName,"
    "credentials[id,displayName,typeName,description]]]"
)


class CredentialsError(JenkinsError):
    """A credentials call that failed for a reason worth naming.

    ``reason`` is one of ``plugin-missing``, ``no-folder`` or ``unknown``;
    ``detail`` carries the folder path or credential id concerned.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"credentials: {reason}")
        self.reason = reason
        self.detail = detail


def credential_records(entries: list[dict], base_url: str) -> list[dict]:
    """Shape flattened credential entries into jeeves display records."""
    base = base_url.rstrip("/")
    return [_record(e, base) for e in entries]


def _record(entry: dict, base: str) -> dict:
    folder = entry["folder"]
    context = f"{normalize_jenkins_path(folder)}/" if folder else ""
    url = (
        f"{base}/{context}{_ROOT}/store/{quote(entry['store'], safe='')}"
        f"/domain/{quote(entry['domain_key'], safe='')}"
        f"/credential/{quote(entry['id'], safe='')}/"
    )
    return {
        "id": entry["id"],
        "name": entry["name"],
        "type": entry["type"],
        "description": entry["description"],
        "store": entry["store"],
        "domain": entry["domain"],
        "folder": folder,
        "url": url,
    }


def _ancestry(folder: str | None) -> list[str]:
    """``a/b`` → ``["a/b", "a", ""]``: the folder, its parents, then the root."""
    parts = [p for p in (folder or "").split("/") if p]
    return ["/".join(parts[:n]) for n in range(len(parts), 0, -1)] + [""]


class CredentialStores:
    """The credential stores visible from one place in the Jenkins tree."""

    def __init__(self, client: JenkinsClient) -> None:
        self._client = client

    def visible(self, folder: str | None = None) -> list[dict]:
        """Every credential visible from ``folder`` (or the root), nearest first.

        Each entry is flat: the credential's own fields plus ``store``,
        ``domain`` (display name), ``domain_key`` (url name) and ``folder``
        (the context that holds it, ``""`` for the root).
        """
        contexts = _ancestry(folder)
        # The root is read first so a missing plugin is reported as such,
        # rather than blamed on the folder.
        payloads = {"": self._read("")}
        for ctx in contexts[:-1]:
            payloads[ctx] = self._read(ctx)
        return [e for ctx in contexts for e in _flatten(ctx, payloads[ctx])]

    def credential(self, credential_id: str, folder: str | None = None) -> list[dict]:
        """Every visible credential with this id — more than one if shadowed."""
        found = [e for e in self.visible(folder) if e["id"] == credential_id]
        if not found:
            raise CredentialsError("unknown", credential_id)
        return found

    def _read(self, context: str) -> dict:
        path = f"{normalize_jenkins_path(context)}/{_ROOT}" if context else _ROOT
        try:
            return self._client.get_json(path, params={"tree": _TREE})
        except JenkinsHTTPError as exc:
            if exc.status != 404:
                raise
            if not context:
                raise CredentialsError("plugin-missing") from exc
            raise CredentialsError("no-folder", context) from exc


def _flatten(context: str, payload: dict) -> list[dict]:
    entries = []
    for store, store_body in sorted((payload.get("stores") or {}).items()):
        domains = (store_body or {}).get("domains") or {}
        for key, domain in sorted(domains.items(), key=_global_first):
            for cred in (domain or {}).get("credentials") or []:
                entries.append(
                    {
                        "id": str(cred.get("id") or ""),
                        "name": cred.get("displayName") or "",
                        "type": cred.get("typeName") or "",
                        "description": cred.get("description") or "",
                        "store": store,
                        "domain": (domain or {}).get("displayName") or key,
                        "domain_key": (domain or {}).get("urlName") or key,
                        "folder": context,
                    }
                )
    return entries


def _global_first(item: tuple[str, dict]) -> tuple[bool, str]:
    """Order domains with the global one (``_``) first, then by name."""
    key = item[0]
    return (key != "_", key)
