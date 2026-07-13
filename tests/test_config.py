import pytest

from jeeves.config import (
    _DEFAULT_CONFIG_CONTENT,
    UnknownProfileError,
    add_profile,
    get_jenkins_config,
    list_profiles,
    load_config,
    remove_profile,
    resolve_config_write_path,
    set_default_profile,
    show_config,
    write_default_config,
)


def test_load_config_no_file_returns_empty(tmp_path):
    result = load_config(str(tmp_path / "nonexistent.toml"))
    assert result == {}


def test_load_config_reads_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('theme = "rainbow"\ncache = true\n')
    result = load_config(str(cfg_file))
    assert result["theme"] == "rainbow"
    assert result["cache"] is True


def test_load_config_invalid_toml_raises(tmp_path):
    cfg_file = tmp_path / "bad.toml"
    cfg_file.write_text("not = [valid toml")
    with pytest.raises(ValueError, match="Config parse error"):
        load_config(str(cfg_file))


def test_write_default_config_creates_file(tmp_path, monkeypatch):
    from jeeves import xdg

    monkeypatch.setattr(xdg, "get_config_dir", lambda: tmp_path / "jeeves")
    from jeeves import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path / "jeeves")
    path = write_default_config()
    assert path.exists()
    assert "theme" in path.read_text()


def test_default_config_content_has_all_keys():
    assert "theme" in _DEFAULT_CONFIG_CONTENT
    assert "cache" in _DEFAULT_CONFIG_CONTENT
    assert "seasonal-colours" in _DEFAULT_CONFIG_CONTENT
    assert "no-update-check" in _DEFAULT_CONFIG_CONTENT


def test_show_config_empty():
    output = show_config({})
    assert "no config keys set" in output


def test_show_config_with_values():
    output = show_config({"theme": "rainbow", "cache": True})
    assert "theme" in output
    assert "rainbow" in output


# ── connection profiles ───────────────────────────────────────────────────────

_TWO_PROFILES = {
    "profiles": {
        "prod": {
            "url": "http://prod.example.com",
            "username": "steve",
            "token": "prod-tok",
        },
        "staging": {"url": "http://staging.example.com"},
    }
}


def _no_jeeves_env(monkeypatch):
    for var in ("JEEVES_URL", "JEEVES_USER", "JEEVES_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_load_config_parses_profiles(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[profiles.prod]\nurl = "http://prod.example.com"\ntoken = "abc"\n'
        '\n[profiles.staging]\nurl = "http://staging.example.com"\n'
    )
    result = load_config(str(cfg_file))
    assert result["profiles"]["prod"]["url"] == "http://prod.example.com"
    assert result["profiles"]["staging"]["url"] == "http://staging.example.com"


def test_get_jenkins_config_flat_backcompat(monkeypatch):
    _no_jeeves_env(monkeypatch)
    cfg = {"jenkins-url": "http://flat.example.com", "jenkins-username": "bertie"}
    url, username, token = get_jenkins_config(cfg)
    assert url == "http://flat.example.com"
    assert username == "bertie"
    assert token == ""


def test_get_jenkins_config_profile_fields(monkeypatch):
    _no_jeeves_env(monkeypatch)
    url, username, token = get_jenkins_config(_TWO_PROFILES, "prod")
    assert url == "http://prod.example.com"
    assert username == "steve"
    assert token == "prod-tok"


def test_get_jenkins_config_profile_never_falls_back_to_flat_keys(monkeypatch):
    _no_jeeves_env(monkeypatch)
    cfg = {"jenkins-url": "http://flat.example.com", **_TWO_PROFILES}
    url, username, token = get_jenkins_config(cfg, "staging")
    assert url == "http://staging.example.com"
    # staging has no username/token; flat keys must not leak in
    cfg["jenkins-username"] = "flat-user"
    cfg["jenkins-token"] = "flat-tok"
    url, username, token = get_jenkins_config(cfg, "staging")
    assert username == ""
    assert token == ""


def test_get_jenkins_config_profile_env_fallback(monkeypatch):
    _no_jeeves_env(monkeypatch)
    monkeypatch.setenv("JEEVES_USER", "env-user")
    monkeypatch.setenv("JEEVES_TOKEN", "env-tok")
    url, username, token = get_jenkins_config(_TWO_PROFILES, "staging")
    assert url == "http://staging.example.com"
    assert username == "env-user"
    assert token == "env-tok"


def test_get_jenkins_config_profile_missing_url_uses_default(monkeypatch):
    _no_jeeves_env(monkeypatch)
    cfg = {"profiles": {"bare": {"token": "abc"}}}
    url, _username, _token = get_jenkins_config(cfg, "bare")
    assert url == "http://localhost:8080"


def test_get_jenkins_config_unknown_profile_raises():
    with pytest.raises(ValueError, match="Unknown profile"):
        get_jenkins_config(_TWO_PROFILES, "bogus")


def test_get_jenkins_config_profiles_not_a_table():
    with pytest.raises(ValueError, match="Unknown profile"):
        get_jenkins_config({"profiles": "oops"}, "prod")


def test_list_profiles_sorted():
    assert list_profiles(_TWO_PROFILES) == ["prod", "staging"]


def test_list_profiles_empty_config():
    assert list_profiles({}) == []


def test_list_profiles_ignores_non_table_entries():
    cfg = {"profiles": {"prod": {"url": "http://x"}, "oops": "scalar"}}
    assert list_profiles(cfg) == ["prod"]


def test_list_profiles_profiles_not_a_table():
    assert list_profiles({"profiles": "oops"}) == []


def test_default_config_content_has_profiles():
    assert "[profiles.prod]" in _DEFAULT_CONFIG_CONTENT
    assert "default-profile" in _DEFAULT_CONFIG_CONTENT


def test_show_config_renders_profiles_and_masks_tokens():
    cfg = {"jenkins-token": "flat-secret", **_TWO_PROFILES}
    output = show_config(cfg)
    assert "prod" in output
    assert "http://prod.example.com" in output
    assert "staging" in output
    assert "prod-tok" not in output
    assert "flat-secret" not in output
    assert "***" in output


def test_show_config_profiles_not_a_table_falls_through():
    output = show_config({"profiles": "oops"})
    assert "profiles = 'oops'" in output


# ── profile writing ───────────────────────────────────────────────────────────


def test_add_profile_creates_file_and_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "config.toml"
    path = add_profile("prod", url="http://prod", config_path=str(target))
    assert path == target.resolve()
    cfg = load_config(str(target))
    assert cfg["profiles"]["prod"]["url"] == "http://prod"


def test_add_profile_new_file_is_private(tmp_path):
    target = tmp_path / "config.toml"
    add_profile("prod", url="http://prod", token="secret", config_path=str(target))
    assert (target.stat().st_mode & 0o777) == 0o600


def test_add_profile_preserves_comments_and_root_key_placement(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text(
        "# my precious comment\n"
        'theme = "rainbow"\n\n[profiles.prod]\nurl = "http://prod"\n'
    )
    add_profile(
        "staging", url="http://staging", make_default=True, config_path=str(target)
    )
    text = target.read_text()
    assert "# my precious comment" in text
    cfg = load_config(str(target))
    # default-profile must land at the document root, not inside a table
    assert cfg["default-profile"] == "staging"
    assert cfg["profiles"]["prod"]["url"] == "http://prod"
    assert cfg["profiles"]["staging"]["url"] == "http://staging"


def test_add_profile_existing_without_force_raises(tmp_path):
    target = tmp_path / "config.toml"
    add_profile("prod", url="http://prod", config_path=str(target))
    with pytest.raises(ValueError, match="already exists"):
        add_profile("prod", url="http://other", config_path=str(target))


def test_add_profile_force_merges_fields(tmp_path):
    target = tmp_path / "config.toml"
    add_profile(
        "prod",
        url="http://prod",
        username="steve",
        token="old",
        config_path=str(target),
    )
    add_profile("prod", token="new", force=True, config_path=str(target))
    cfg = load_config(str(target))
    # token rotated; url and username survive the update
    assert cfg["profiles"]["prod"] == {
        "url": "http://prod",
        "username": "steve",
        "token": "new",
    }


def test_add_profile_bad_toml_raises_value_error(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text("not = [valid toml")
    with pytest.raises(ValueError, match="Config parse error"):
        add_profile("prod", url="http://prod", config_path=str(target))


def test_remove_profile_deletes_and_clears_dangling_default(tmp_path):
    target = tmp_path / "config.toml"
    add_profile("prod", url="http://prod", make_default=True, config_path=str(target))
    add_profile("staging", url="http://staging", config_path=str(target))
    _path, cleared = remove_profile("prod", config_path=str(target))
    assert cleared is True
    cfg = load_config(str(target))
    assert "default-profile" not in cfg
    assert list(cfg["profiles"]) == ["staging"]
    _path, cleared = remove_profile("staging", config_path=str(target))
    assert cleared is False


def test_remove_profile_unknown_raises(tmp_path):
    target = tmp_path / "config.toml"
    add_profile("prod", url="http://prod", config_path=str(target))
    with pytest.raises(UnknownProfileError, match="Unknown profile"):
        remove_profile("bogus", config_path=str(target))


def test_remove_profile_parse_error_is_not_unknown_profile(tmp_path):
    # a corrupt config must surface as a parse error, not "unknown profile"
    target = tmp_path / "config.toml"
    target.write_text("not = [valid toml")
    with pytest.raises(ValueError, match="Config parse error") as excinfo:
        remove_profile("prod", config_path=str(target))
    assert not isinstance(excinfo.value, UnknownProfileError)


def test_set_default_profile_sets_and_clears(tmp_path):
    target = tmp_path / "config.toml"
    add_profile("prod", url="http://prod", config_path=str(target))
    set_default_profile("prod", config_path=str(target))
    assert load_config(str(target))["default-profile"] == "prod"
    set_default_profile(None, config_path=str(target))
    assert "default-profile" not in load_config(str(target))


def test_set_default_profile_unknown_raises(tmp_path):
    target = tmp_path / "config.toml"
    add_profile("prod", url="http://prod", config_path=str(target))
    with pytest.raises(ValueError, match="Unknown profile"):
        set_default_profile("bogus", config_path=str(target))


def test_resolve_config_write_path_explicit_wins(tmp_path):
    target = tmp_path / "mine.toml"
    assert resolve_config_write_path(str(target)) == target.resolve()


def test_resolve_config_write_path_prefers_existing_then_xdg(tmp_path, monkeypatch):
    from jeeves import config as cfg_mod

    existing = tmp_path / "found.toml"
    missing = tmp_path / "missing.toml"
    monkeypatch.setattr(cfg_mod, "get_config_paths", lambda: [missing, existing])
    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path / "xdg")
    # nothing exists yet → XDG default
    expected = (tmp_path / "xdg" / "config.toml").resolve()
    assert resolve_config_write_path(None) == expected
    existing.write_text("")
    assert resolve_config_write_path(None) == existing.resolve()


def test_resolve_config_write_path_follows_symlink(tmp_path):
    real = tmp_path / "real.toml"
    real.write_text('theme = "rainbow"\n')
    link = tmp_path / "link.toml"
    link.symlink_to(real)
    add_profile("prod", url="http://prod", config_path=str(link))
    assert link.is_symlink()  # the link survives; the real file was edited
    assert load_config(str(real))["profiles"]["prod"]["url"] == "http://prod"
