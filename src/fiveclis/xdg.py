import os
from pathlib import Path

_APP_NAME = "fiveclis"


def _xdg_override(env_var: str) -> Path | None:
    """Return ``Path($env_var)`` only if it is set to an absolute path.

    Per the XDG Base Directory Specification, relative paths in
    ``$XDG_*_HOME`` variables must be considered invalid and ignored.
    """
    value = os.getenv(env_var)
    if value and Path(value).is_absolute():
        return Path(value)
    return None


def get_cache_dir() -> Path:
    """XDG cache directory: $XDG_CACHE_HOME/<app> or ~/.cache/<app>."""
    override = _xdg_override("XDG_CACHE_HOME")
    if override is not None:
        return override / _APP_NAME
    return Path.home() / ".cache" / _APP_NAME


def get_config_dir() -> Path:
    """XDG config directory: $XDG_CONFIG_HOME/<app> or ~/.config/<app>."""
    override = _xdg_override("XDG_CONFIG_HOME")
    if override is not None:
        return override / _APP_NAME
    return Path.home() / ".config" / _APP_NAME


def get_config_paths() -> list[Path]:
    """Return config file search paths in priority order (highest → lowest).

    Resolution order:
      1. ./.fiveclis.toml               (current directory)
      2. ~/.config/fiveclis/config.toml (XDG default)
      3. ~/.fiveclis.toml               (legacy home directory)
    """
    return [
        Path.cwd() / f".{_APP_NAME}.toml",
        get_config_dir() / "config.toml",
        Path.home() / f".{_APP_NAME}.toml",
    ]


def get_state_dir() -> Path:
    """XDG state directory: $XDG_STATE_HOME/<app> or ~/.local/state/<app>."""
    override = _xdg_override("XDG_STATE_HOME")
    if override is not None:
        return override / _APP_NAME
    return Path.home() / ".local" / "state" / _APP_NAME
