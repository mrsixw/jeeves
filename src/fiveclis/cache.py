import json
import os
from datetime import datetime, timezone
from pathlib import Path

import click

from .logger import logger
from .xdg import get_cache_dir

_CACHE_DIR = get_cache_dir()
_SUFFIX_MAP = {"s": 1, "m": 60, "h": 3600}


def _atomic_write_text(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via temp file + os.replace."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def parse_ttl(value: str | int) -> int:
    """Parse a TTL value into seconds.

    Accepts: bare int, string int (e.g. ``"300"``), or suffixed string
    (``"5m"``, ``"2h"``, ``"30s"``).
    Raises ``ValueError`` for invalid or non-positive values.
    """
    if isinstance(value, bool):
        raise ValueError(f"Invalid TTL: {value!r}")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"TTL must be positive, got {value}")
        return value

    s = str(value).strip()
    if not s:
        raise ValueError("TTL must not be empty")

    if s[-1] in _SUFFIX_MAP:
        suffix = s[-1]
        try:
            n = int(s[:-1])
        except ValueError:
            raise ValueError(f"Invalid TTL: {value!r}")
        if n <= 0:
            raise ValueError(f"TTL must be positive, got {value!r}")
        return n * _SUFFIX_MAP[suffix]

    try:
        n = int(s)
    except ValueError:
        raise ValueError(f"Invalid TTL: {value!r}")
    if n <= 0:
        raise ValueError(f"TTL must be positive, got {value!r}")
    return n


def read_cache(key: str, ttl: int) -> dict | None:
    """Return cached data for *key* if present and within *ttl* seconds, else None."""
    path = _CACHE_DIR / f"{key}.json"
    try:
        if not path.exists():
            logger.debug("cache_miss key=%s reason=file_not_found", key)
            return None
        data = json.loads(path.read_text())
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if age > ttl:
            logger.debug(
                "cache_miss key=%s reason=expired age=%.0fs ttl=%ss", key, age, ttl
            )
            return None
        logger.debug("cache_hit key=%s age=%.0fs", key, age)
        return data.get("payload")
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning("cache_read_error key=%s error=%r", key, str(exc))
        click.echo(
            click.style(f"Warning: failed to read cache ({key}): {exc}", fg="yellow"),
            err=True,
        )
        return None


def write_cache(key: str, payload: dict | list) -> None:
    """Write *payload* to disk cache under *key*."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"{key}.json"
        data = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        _atomic_write_text(path, json.dumps(data))
        logger.debug("cache_write key=%s", key)
    except OSError as exc:
        logger.warning("cache_write_error key=%s error=%r", key, str(exc))
        click.echo(
            click.style(f"Warning: failed to write cache ({key}): {exc}", fg="yellow"),
            err=True,
        )


def clear_cache(key: str) -> bool:
    """Delete the cache file for *key*. Returns True if deleted, False if not found."""
    path = _CACHE_DIR / f"{key}.json"
    try:
        path.unlink()
        logger.debug("cache_cleared key=%s", key)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("cache_clear_error key=%s error=%r", key, str(exc))
        return False
