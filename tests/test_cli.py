from click.testing import CliRunner

from fiveclis import cli as cli_mod
from fiveclis.cli import main


def _invoke(*args, **kwargs):
    runner = CliRunner()
    return runner.invoke(main, list(args), **kwargs)


def test_version():
    result = _invoke("--version")
    assert result.exit_code == 0
    assert "fiveclis" in result.output or "0." in result.output


def test_help():
    result = _invoke("--help")
    assert result.exit_code == 0
    assert "--theme" in result.output
    assert "--completion" in result.output


def test_greet_default(monkeypatch):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **_kw: None)
    result = _invoke("--no-colour")
    assert result.exit_code == 0
    assert "Hello" in result.output


def test_greet_with_name(monkeypatch):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **_kw: None)
    result = _invoke("--name", "Alice", "--no-colour")
    assert result.exit_code == 0
    assert "Alice" in result.output


def test_completion_bash():
    result = _invoke("--completion", "bash")
    assert result.exit_code == 0
    assert "_FIVE_CLIS_COMPLETE" in result.output


def test_completion_zsh():
    result = _invoke("--completion", "zsh")
    assert result.exit_code == 0


def test_completion_fish():
    result = _invoke("--completion", "fish")
    assert result.exit_code == 0


def test_init_config(tmp_path, monkeypatch):
    from fiveclis import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path / "fiveclis")
    result = _invoke("--init-config")
    assert result.exit_code == 0
    assert "config.toml" in result.output


def test_show_config(monkeypatch):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **_kw: None)
    result = _invoke("--show-config")
    assert result.exit_code == 0
    assert "Config file" in result.output


def test_theme_rainbow(monkeypatch):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **_kw: None)
    result = _invoke("--theme", "rainbow")
    assert result.exit_code == 0


def test_no_update_check_skips_update(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    _invoke("--no-update-check", "--no-colour")
    assert called["n"] == 0


def test_update_check_runs_by_default(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    _invoke("--no-colour")
    assert called["n"] == 1


def test_invalid_config_exits_with_error(tmp_path):
    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("not = [valid toml")
    result = _invoke("--config", str(bad_cfg))
    assert result.exit_code == 1
