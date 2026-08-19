import json as _json
import re
from urllib.parse import parse_qs

import pytest
import requests
from click.testing import CliRunner
from conftest import JENKINS_URL, api, url

from jeeves import cli as cli_mod
from jeeves.cli import _hyperlink, main
from jeeves.updater import UpdateStatus


def _invoke(*args, **kwargs):
    runner = CliRunner()
    return runner.invoke(main, list(args), **kwargs)


def _listed_commands(help_output: str) -> set[str]:
    """Command names listed in a --help output's Commands section."""
    names = set()
    in_commands = False
    for line in help_output.splitlines():
        if line.strip() == "Commands:":
            in_commands = True
            continue
        if in_commands:
            match = re.match(r"\s+(\S+)\s", line)
            if match:
                names.add(match.group(1))
            elif line.strip() == "":
                break
    return names


# ── endpoint registration helpers ─────────────────────────────────────────────

_STATUS_JSON = {
    "mode": "NORMAL",
    "nodeDescription": "master",
    "numExecutors": 2,
    "jobs": [],
}


def _jobs_http(jenkins, jobs, folder=None):
    path = f"job/{folder}" if folder else ""
    jenkins.get(api(path), json={"jobs": jobs})


def _queue_http(jenkins, items):
    jenkins.get(api("queue"), json={"items": items})


def _nodes_http(jenkins, computers):
    jenkins.get(api("computer"), json={"computer": computers})


def _job_detail_http(jenkins, job_json):
    jenkins.get(api("job/deploy"), json=job_json)


def _builds_list_http(jenkins, builds):
    jenkins.get(api("job/deploy"), json={"builds": builds})


def _build_info_http(jenkins, mapping):
    """Register per-permalink build endpoints; None registers a 404."""
    for permalink, info in mapping.items():
        if info is None:
            jenkins.get(api(f"job/deploy/{permalink}"), status_code=404)
        else:
            jenkins.get(api(f"job/deploy/{permalink}"), json=info)


def _trigger_http(jenkins, job_path="job/my-pipeline"):
    """Register the endpoints a build trigger touches (crumb + both POSTs)."""
    jenkins.get(url("crumbIssuer/api/json"), status_code=404)
    jenkins.post(url(f"{job_path}/build"), status_code=201)
    jenkins.post(url(f"{job_path}/buildWithParameters"), status_code=201)


def _rebuild_http(jenkins, info):
    _build_info_http(jenkins, {"lastBuild": info})
    _trigger_http(jenkins, job_path="job/deploy")


def _last_post(jenkins):
    posts = [r for r in jenkins.request_history if r.method == "POST"]
    assert posts, "expected a build POST"
    return posts[-1]


def _login_redirect_http(jenkins):
    jenkins.get(
        api(),
        status_code=302,
        headers={"Location": url("securityRealm/commenceLogin?from=%2F")},
    )
    jenkins.get(url("securityRealm/commenceLogin"), text="sign in")


# ── Infrastructure ───────────────────────────────────────────────────────────


def test_version():
    result = _invoke("--version")
    assert result.exit_code == 0
    assert "jeeves" in result.output or "0." in result.output


def test_help():
    result = _invoke("--help")
    assert result.exit_code == 0
    assert "--theme" in result.output
    assert "completions" in result.output
    listed = _listed_commands(result.output)
    assert {"status", "job", "build", "node", "queue", "whoami"} <= listed


def test_help_shows_five_clis_credit():
    result = _invoke("--help")
    assert result.exit_code == 0
    assert "five-clis" in result.output
    assert "github.com/mrsixw/five-clis" in result.output


def test_bare_invocation_shows_greeting():
    result = _invoke("--no-colour")
    assert result.exit_code == 0
    assert "Good morning" in result.output or "Jeeves" in result.output


def test_completion_bash():
    result = _invoke("completions", "bash")
    assert result.exit_code == 0
    assert "_JEEVES_COMPLETE" in result.output


def test_completion_zsh():
    result = _invoke("completions", "zsh")
    assert result.exit_code == 0


def test_completion_fish():
    result = _invoke("completions", "fish")
    assert result.exit_code == 0


def test_completion_rejects_unknown_shell():
    result = _invoke("completions", "powershell")
    assert result.exit_code != 0


def test_completion_works_with_invalid_default_profile(tmp_path, monkeypatch):
    """completions must not require a valid profile/config (mirrors old eager flag)."""
    from jeeves import config as cfg_mod

    config_path = tmp_path / "jeeves.toml"
    config_path.write_text('default-profile = "nonexistent"\n')
    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path)
    result = _invoke("--config", str(config_path), "completions", "zsh")
    assert result.exit_code == 0
    assert "_JEEVES_COMPLETE" in result.output


def test_init_config(tmp_path, monkeypatch):
    from jeeves import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "get_config_dir", lambda: tmp_path / "jeeves")
    result = _invoke("--init-config")
    assert result.exit_code == 0
    assert "config.toml" in result.output


def test_show_config():
    result = _invoke("--show-config")
    assert result.exit_code == 0
    assert "Config file" in result.output


def test_no_update_check_skips_update(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    _invoke("--no-update-check", "--no-colour", "status", catch_exceptions=False)
    assert called["n"] == 0


def test_update_check_runs_by_default(monkeypatch, jenkins):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    jenkins.get(api(), json=_STATUS_JSON)
    _invoke("--no-colour", "status")
    assert called["n"] == 1


def test_invalid_config_exits_with_error(tmp_path):
    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("not = [valid toml")
    result = _invoke("--config", str(bad_cfg))
    assert result.exit_code == 1


# ── status ───────────────────────────────────────────────────────────────────


def test_status_shows_butler_greeting(jenkins):
    jenkins.get(api(), json=_STATUS_JSON)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 0
    assert "Certainly" in result.output or "fine form" in result.output


def test_status_connection_error_shows_butler_error(jenkins):
    jenkins.get(api(), exc=requests.exceptions.ConnectionError)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "unreachable" in result.output


def test_error_403_shows_credentials_message(jenkins):
    jenkins.get(api(), status_code=403)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "403" in result.output
    assert "credentials" in result.output


def test_error_404_shows_not_found_message(jenkins):
    jenkins.get(api(), status_code=404)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "404" in result.output


def test_error_generic_shows_bother_message(jenkins):
    jenkins.get(api(), exc=requests.exceptions.RequestException("something went wrong"))
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "bother" in result.output


# ── browser-login redirect handling ──────────────────────────────────────────


def test_login_required_non_interactive_prints_url(monkeypatch, jenkins):
    _login_redirect_http(jenkins)
    monkeypatch.setattr(cli_mod, "_isatty", lambda: False)
    opened = {"n": 0}
    monkeypatch.setattr(
        cli_mod.webbrowser, "open", lambda *a, **k: opened.__setitem__("n", 1)
    )

    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "browser" in result.output
    assert "http://jenkins.example.com" in result.output
    # non-interactive: must NOT open a browser
    assert opened["n"] == 0


def test_login_required_interactive_opens_browser(monkeypatch, jenkins):
    _login_redirect_http(jenkins)
    monkeypatch.setattr(cli_mod, "_isatty", lambda: True)
    opened = {"url": None}

    def _fake_open(url, *a, **k):
        opened["url"] = url
        return True

    monkeypatch.setattr(cli_mod.webbrowser, "open", _fake_open)

    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert opened["url"] == "http://jenkins.example.com"
    assert "opened" in result.output


# ── jobs ─────────────────────────────────────────────────────────────────────


def test_jobs_shows_roster(jenkins):
    _jobs_http(jenkins, [{"name": "deploy-prod", "color": "blue"}])
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "deploy-prod" in result.output
    assert "roster" in result.output


# ── output formats (--format) ─────────────────────────────────────────────────


def test_jobs_format_json(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "deploy",
                "color": "blue",
                "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
                "healthReport": [{"score": 90}],
            }
        ],
    )
    result = _invoke("--no-update-check", "--format", "json", "job", "list")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["name"] == "deploy"
    assert data[0]["type"] == "pipeline"
    assert data[0]["status"] == "passed"
    assert data[0]["health"] == 90
    # no decorative header on stdout in json mode
    assert "roster" not in result.stdout


def test_jobs_format_ndjson_one_per_line(jenkins):
    _jobs_http(
        jenkins,
        [{"name": "a", "color": "blue"}, {"name": "b", "color": "red"}],
    )
    result = _invoke(
        "--no-update-check", "--format", "ndjson", "job", "list", "--no-weather"
    )
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert _json.loads(lines[0])["name"] == "a"


def test_jobs_format_csv(jenkins):
    _jobs_http(jenkins, [{"name": "deploy", "color": "blue"}])
    result = _invoke(
        "--no-update-check", "--format", "csv", "job", "list", "--no-weather"
    )
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0] == "Job,Type,Status"
    assert lines[1].startswith("deploy,job,passed")


def test_jobs_format_markdown(jenkins):
    _jobs_http(jenkins, [{"name": "deploy", "color": "blue"}])
    result = _invoke(
        "--no-update-check", "--format", "markdown", "job", "list", "--no-weather"
    )
    assert result.exit_code == 0
    assert "|" in result.stdout
    assert "passed" in result.stdout


def test_jobs_format_template(jenkins):
    _jobs_http(jenkins, [{"name": "deploy", "color": "blue"}])
    result = _invoke(
        "--no-update-check",
        "--format",
        "template",
        "--template",
        "{name}={status}",
        "job",
        "list",
        "--no-weather",
    )
    assert result.exit_code == 0
    assert "deploy=passed" in result.stdout


def test_jobs_format_template_requires_template(jenkins):
    _jobs_http(jenkins, [{"name": "deploy", "color": "blue"}])
    result = _invoke("--no-update-check", "--format", "template", "job", "list")
    assert result.exit_code == 1
    assert "template" in result.output


def test_jobs_format_tree_expand(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "platform",
                "_class": "com.cloudbees.hudson.plugins.folder.Folder",
            }
        ],
    )
    _jobs_http(jenkins, [{"name": "api", "color": "blue"}], folder="platform")
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--format",
        "tree",
        "job",
        "list",
        "--expand",
    )
    assert result.exit_code == 0
    assert "jenkins" in result.stdout
    assert "platform" in result.stdout
    assert "api" in result.stdout
    # tree branch glyphs present
    assert "└──" in result.stdout or "├──" in result.stdout


def test_jobs_format_json_empty_is_array(jenkins):
    _jobs_http(jenkins, [])
    result = _invoke("--no-update-check", "--format", "json", "job", "list")
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"


def test_nodes_format_json_labels_as_list(jenkins):
    _nodes_http(
        jenkins,
        [
            {
                "displayName": "agent1",
                "offline": False,
                "numExecutors": 4,
                "assignedLabels": [
                    {"name": "agent1"},
                    {"name": "linux"},
                    {"name": "docker"},
                ],
            }
        ],
    )
    result = _invoke("--no-update-check", "--format", "json", "node", "list")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["labels"] == ["linux", "docker"]
    assert data[0]["status"] == "online"


def test_queue_format_json_stuck_bool(jenkins):
    _queue_http(
        jenkins, [{"why": "blocked", "stuck": True, "task": {"name": "deploy"}}]
    )
    result = _invoke("--no-update-check", "--format", "json", "queue")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["name"] == "deploy"
    assert data[0]["stuck"] is True


# ── decoration routing (stdout vs stderr) ─────────────────────────────────────


def test_jobs_header_on_stderr_data_on_stdout(jenkins):
    _jobs_http(jenkins, [{"name": "deploy-prod", "color": "blue"}])
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    # decorative butler header goes to stderr only
    assert "roster" in result.stderr
    assert "roster" not in result.stdout
    # data lands on stdout
    assert "deploy-prod" in result.stdout


def test_jobs_empty_state_on_stderr(jenkins):
    _jobs_http(jenkins, [])
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "bare" in result.stderr
    assert result.stdout.strip() == ""


def test_queue_header_on_stderr_data_on_stdout(jenkins):
    _queue_http(
        jenkins, [{"why": "waiting", "stuck": False, "task": {"name": "deploy"}}]
    )
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "pending requests" in result.stderr
    assert "pending requests" not in result.stdout
    assert "deploy" in result.stdout


def test_nodes_header_on_stderr_data_on_stdout(jenkins):
    _nodes_http(
        jenkins, [{"displayName": "agent1", "offline": False, "numExecutors": 2}]
    )
    result = _invoke("--no-colour", "--no-update-check", "node", "list")
    assert result.exit_code == 0
    assert "household staff" in result.stderr
    assert "household staff" not in result.stdout
    assert "agent1" in result.stdout


def test_status_header_on_stderr_table_on_stdout(jenkins):
    jenkins.get(api(), json=_STATUS_JSON)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 0
    assert "fine form" in result.stderr
    assert "fine form" not in result.stdout
    # the data table stays on stdout
    assert "Mode" in result.stdout


def test_greeting_on_stderr():
    result = _invoke("--no-colour", "--no-update-check")
    assert result.exit_code == 0
    assert "Good morning" in result.stderr
    assert result.stdout.strip() == ""


def test_jobs_shows_status_labels(jenkins):
    _jobs_http(
        jenkins,
        [
            {"name": "a", "color": "blue"},
            {"name": "b", "color": "red"},
            {"name": "c", "color": "yellow"},
            {"name": "d", "color": "grey"},
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "passed" in result.output
    assert "failed" in result.output
    assert "unstable" in result.output
    assert "disabled" in result.output


def test_jobs_shows_folder_icon(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "my-folder",
                "_class": "com.cloudbees.hudson.plugins.folder.Folder",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "my-folder" in result.output
    assert "folder" in result.output


def test_jobs_shows_type_icons(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "pipe",
                "color": "blue",
                "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
            },
            {
                "name": "free",
                "color": "blue",
                "_class": "hudson.model.FreeStyleProject",
            },
            {
                "name": "unknown",
                "color": "blue",
                "_class": "some.UnknownClass",
            },
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "🔧" in result.output
    assert "🔨" in result.output


def test_jobs_type_workflow_job(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "pipe",
                "color": "blue",
                "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "pipeline" in result.output


def test_jobs_type_freestyle_project(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "free",
                "color": "blue",
                "_class": "hudson.model.FreeStyleProject",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "🔧" in result.output
    assert "freestyle" in result.output


def test_jobs_type_matrix_project(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "matrix",
                "color": "blue",
                "_class": "hudson.matrix.MatrixProject",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "🔢" in result.output
    assert "matrix" in result.output


def test_jobs_type_unknown_fallback(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "mystery",
                "color": "blue",
                "_class": "com.example.SomeUnknownJobType",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "🔨" in result.output
    assert "job" in result.output


def test_jobs_type_folder_icon(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "my-folder",
                "_class": "com.cloudbees.hudson.plugins.folder.Folder",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "📁" in result.output
    assert "folder" in result.output


def test_jobs_type_key_flag(jenkins):
    _jobs_http(jenkins, [])
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--type-key")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "🔧" in result.output
    assert "🔢" in result.output
    assert "🔨" in result.output
    assert "📁" in result.output
    assert "pipeline" in result.output


def test_swatch_shows_iconography():
    result = _invoke("--no-colour", "--no-update-check", "swatch")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "🔧" in result.output
    assert "☀️" in result.output
    assert "⛈️" in result.output


def test_update_installs_new_release(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "perform_update",
        lambda executable_path: (UpdateStatus.UPDATED, "1.0.0", "2.0.0"),
    )
    result = _invoke("--no-colour", "update")
    assert result.exit_code == 0
    assert "refreshed to v2.0.0" in result.output


def test_update_already_up_to_date(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "perform_update",
        lambda executable_path: (UpdateStatus.UP_TO_DATE, "2.0.0", "2.0.0"),
    )
    result = _invoke("--no-colour", "update")
    assert result.exit_code == 0
    assert "Already wearing the latest fashion, v2.0.0" in result.output


def test_update_unknown_latest_version_errors(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "perform_update",
        lambda executable_path: (UpdateStatus.UNKNOWN, "1.0.0", None),
    )
    result = _invoke("--no-colour", "update")
    assert result.exit_code == 1
    assert "🎩" in result.output


def test_update_download_error_reports_detail(monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "perform_update",
        lambda executable_path: (UpdateStatus.ERROR, "1.0.0", "Permission denied"),
    )
    result = _invoke("--no-colour", "update")
    assert result.exit_code == 1
    assert "Permission denied" in result.output


def test_update_does_not_also_run_trailing_update_check(monkeypatch):
    def fake_perform_update(executable_path):
        return UpdateStatus.UPDATED, "1.0.0", "2.0.0"

    def failing_check_for_update(*args, **kwargs):
        raise AssertionError("check_for_update should not run after 'update'")

    monkeypatch.setattr(cli_mod, "perform_update", fake_perform_update)
    monkeypatch.setattr(cli_mod, "check_for_update", failing_check_for_update)
    result = _invoke("--no-colour", "update")
    assert result.exit_code == 0


def test_jobs_expand_recurses_into_folders(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "my-folder",
                "_class": "com.cloudbees.hudson.plugins.folder.Folder",
            }
        ],
    )
    _jobs_http(
        jenkins,
        [
            {
                "name": "child-job",
                "color": "blue",
                "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
            }
        ],
        folder="my-folder",
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "job", "list", "--expand", "--no-weather"
    )
    assert result.exit_code == 0
    assert "my-folder" in result.output
    assert "my-folder/child-job" in result.output


def test_jobs_shows_weather_column(jenkins):
    _jobs_http(
        jenkins,
        [
            {
                "name": "healthy",
                "color": "blue",
                "healthReport": [{"score": 90}],
            },
            {
                "name": "sick",
                "color": "red",
                "healthReport": [{"score": 10}],
            },
            {
                "name": "no-report",
                "color": "grey",
                "healthReport": [],
            },
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "list")
    assert result.exit_code == 0
    assert "Weather" in result.output
    assert "sunny" in result.output
    assert "stormy" in result.output
    assert "—" in result.output


def test_jobs_no_weather_skips_column(jenkins):
    _jobs_http(jenkins, [{"name": "x", "color": "blue"}])
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "Weather" not in result.output


def test_jobs_empty_shows_butler_message(jenkins):
    _jobs_http(jenkins, [])
    result = _invoke("--no-colour", "--no-update-check", "job", "list")
    assert result.exit_code == 0
    assert "bare" in result.output or "positions" in result.output
    # every Jeeves-voiced message leads with an emoji (no double space after it)
    assert "🗒️ The staff roster" in result.output


# ── hyperlinks ────────────────────────────────────────────────────────────────


def test_hyperlink_helper_colour():
    result = _hyperlink("my-job", "http://jenkins/job/my-job", colour=True)
    assert "\x1b]8;;" in result
    assert "http://jenkins/job/my-job" in result
    assert "my-job" in result


def test_hyperlink_helper_no_colour():
    result = _hyperlink("my-job", "http://jenkins/job/my-job", colour=False)
    assert result == "my-job"


def test_jobs_hyperlinks_job_url(jenkins):
    _jobs_http(jenkins, [{"name": "deploy-prod", "color": "blue"}])
    result = _invoke(
        "--no-update-check",
        "--url",
        "http://jenkins.example.com",
        "job",
        "list",
        "--no-weather",
        color=True,
    )
    assert result.exit_code == 0
    assert "http://jenkins.example.com" in result.output
    assert "deploy-prod" in result.output


def test_jobs_no_colour_no_hyperlinks(jenkins):
    _jobs_http(jenkins, [{"name": "deploy-prod", "color": "blue"}])
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert "\x1b]8;;" not in result.output


def test_queue_hyperlinks_task_url(jenkins):
    _queue_http(
        jenkins,
        [
            {
                "why": "waiting",
                "stuck": False,
                "task": {
                    "name": "deploy",
                    "url": "http://jenkins.example.com/job/deploy/",
                },
            }
        ],
    )
    result = _invoke("--no-update-check", "queue", color=True)
    assert result.exit_code == 0
    assert "http://jenkins.example.com/job/deploy/" in result.output


def test_nodes_hyperlinks_node_url(jenkins):
    _nodes_http(
        jenkins, [{"displayName": "agent1", "offline": False, "numExecutors": 2}]
    )
    result = _invoke(
        "--no-update-check",
        "--url",
        "http://jenkins.example.com",
        "node",
        "list",
        color=True,
    )
    assert result.exit_code == 0
    assert "http://jenkins.example.com/computer/agent1/" in result.output


# ── build ─────────────────────────────────────────────────────────────────────


def test_build_success_shows_dispatch_message(jenkins):
    _trigger_http(jenkins)
    result = _invoke(
        "--no-colour", "--no-update-check", "job", "trigger", "my-pipeline"
    )
    assert result.exit_code == 0
    assert (
        "dispatch" in result.output
        or "forthwith" in result.output
        or "at once" in result.output
    )
    assert _last_post(jenkins).url.lower().endswith("/build")


def test_build_bad_param_format():
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "job",
        "trigger",
        "my-pipeline",
        "--param",
        "no-equals-sign",
    )
    assert result.exit_code == 1


# ── builds ────────────────────────────────────────────────────────────────────


def test_builds_summary_table(jenkins):
    _build_info_http(
        jenkins,
        {
            "lastBuild": {
                "number": 142,
                "result": "SUCCESS",
                "building": False,
                "timestamp": 0,
                "duration": 192000,
                "url": "http://x/142/",
            },
            "lastSuccessfulBuild": {
                "number": 142,
                "result": "SUCCESS",
                "building": False,
            },
            "lastFailedBuild": None,
        },
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "summary", "deploy")
    assert result.exit_code == 0
    assert "#142" in result.stdout
    assert "Success" in result.stdout
    # the absent lastFailedBuild renders a dash
    assert "—" in result.stdout
    # header is decoration -> stderr
    assert "build record" in result.stderr


def test_builds_summary_json(jenkins):
    _build_info_http(
        jenkins,
        {
            "lastBuild": {"number": 9, "result": "FAILURE", "building": False},
            "lastSuccessfulBuild": None,
            "lastFailedBuild": {"number": 9, "result": "FAILURE", "building": False},
        },
    )
    result = _invoke(
        "--no-update-check", "--format", "json", "build", "summary", "deploy"
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    by_permalink = {r["permalink"]: r for r in data}
    assert by_permalink["last"]["number"] == 9
    assert by_permalink["last"]["result"] == "FAILURE"
    assert by_permalink["successful"]["number"] is None


def test_builds_summary_none_shows_empty_state(jenkins):
    _build_info_http(
        jenkins,
        {"lastBuild": None, "lastSuccessfulBuild": None, "lastFailedBuild": None},
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "summary", "deploy")
    assert result.exit_code == 0
    assert "no builds on record" in result.stderr
    assert result.stdout.strip() == ""


def test_builds_list_table(jenkins):
    _builds_list_http(
        jenkins,
        [
            {"number": 142, "result": "SUCCESS", "building": False},
            {"number": 141, "result": "FAILURE", "building": False},
            {"number": 140, "result": "SUCCESS", "building": False},
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "list", "deploy")
    assert result.exit_code == 0
    assert "#142" in result.stdout
    assert "#141" in result.stdout
    assert "#140" in result.stdout
    # no Permalink column in list view
    assert "Permalink" not in result.stdout


def test_builds_list_result_filter(jenkins):
    _builds_list_http(
        jenkins,
        [
            {"number": 142, "result": "SUCCESS", "building": False},
            {"number": 141, "result": "FAILURE", "building": False},
        ],
    )
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "build",
        "list",
        "deploy",
        "--result",
        "failure",
    )
    assert result.exit_code == 0
    assert "#141" in result.stdout
    assert "#142" not in result.stdout


def test_builds_list_passes_limit(jenkins):
    _builds_list_http(jenkins, [])
    result = _invoke("--no-update-check", "build", "list", "deploy", "--limit", "5")
    assert result.exit_code == 0
    assert "{0,5}" in jenkins.last_request.qs["tree"][0]


def test_builds_show_single(jenkins):
    _build_info_http(
        jenkins, {"7": {"number": 7, "result": "SUCCESS", "building": False}}
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "show", "deploy", "7")
    assert result.exit_code == 0
    assert "#7" in result.stdout


def test_builds_show_missing(jenkins):
    _build_info_http(jenkins, {"999": None})
    result = _invoke(
        "--no-colour", "--no-update-check", "build", "show", "deploy", "999"
    )
    assert result.exit_code == 0
    assert "could find no build" in result.stderr


def test_builds_show_exposes_params_and_causes_table(jenkins):
    _build_info_http(
        jenkins,
        {
            "7": {
                "number": 7,
                "result": "SUCCESS",
                "building": False,
                "actions": [
                    {
                        "_class": "hudson.model.ParametersAction",
                        "parameters": [
                            {"name": "CHANGE_ID", "value": "12345"},
                            {"name": "WAVE", "value": "2"},
                        ],
                    },
                    {
                        "_class": "hudson.model.CauseAction",
                        "causes": [
                            {
                                "shortDescription": "Started by user bob",
                                "userId": "bob",
                            }
                        ],
                    },
                ],
            }
        },
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "show", "deploy", "7")
    assert result.exit_code == 0
    assert "CHANGE_ID=12345" in result.stdout
    assert "WAVE=2" in result.stdout
    assert "Started by user bob" in result.stdout


def test_builds_show_exposes_params_and_causes_json(jenkins):
    _build_info_http(
        jenkins,
        {
            "7": {
                "number": 7,
                "result": "SUCCESS",
                "building": False,
                "actions": [
                    {
                        "_class": "hudson.model.ParametersAction",
                        "parameters": [{"name": "CHANGE_ID", "value": "12345"}],
                    },
                    {
                        "_class": "hudson.model.CauseAction",
                        "causes": [
                            {
                                "shortDescription": "Started by project foo #3",
                                "upstreamProject": "foo",
                                "upstreamBuild": 3,
                            }
                        ],
                    },
                ],
            }
        },
    )
    result = _invoke(
        "--no-update-check", "--format", "json", "build", "show", "deploy", "7"
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["params"] == {"CHANGE_ID": "12345"}
    assert data[0]["causes"][0]["upstreamProject"] == "foo"
    assert data[0]["causes"][0]["upstreamBuild"] == 3


# ── build blame ──────────────────────────────────────────────────────────────

_BLAME_PIPELINE_BUILD = {
    "number": 12,
    "culprits": [
        {"fullName": "Bertie Wooster", "absoluteUrl": f"{JENKINS_URL}/user/bertie/"}
    ],
    "changeSets": [
        {
            "items": [
                {
                    "commitId": "deadbeefcafe1234",
                    "msg": "fix the boiler",
                    "timestamp": 1700000000000,
                    "authorEmail": "bertie@drones.example",
                    "author": {
                        "fullName": "Bertie Wooster",
                        "absoluteUrl": f"{JENKINS_URL}/user/bertie/",
                    },
                }
            ]
        }
    ],
}


def test_build_blame_lists_changes_and_culprits(jenkins):
    _build_info_http(jenkins, {"lastBuild": _BLAME_PIPELINE_BUILD})
    result = _invoke("--no-colour", "--no-update-check", "build", "blame", "deploy")
    assert result.exit_code == 0
    assert "deadbee" in result.stdout  # abbreviated commit id
    assert "deadbeefcafe1234" not in result.stdout
    assert "Bertie Wooster" in result.stdout
    assert "fix the boiler" in result.stdout
    assert "build #12 of 'deploy'" in result.stderr
    assert "Persons of interest: Bertie Wooster" in result.stderr


def test_build_blame_requests_blame_tree(jenkins):
    _build_info_http(jenkins, {"lastBuild": _BLAME_PIPELINE_BUILD})
    result = _invoke("--no-colour", "--no-update-check", "build", "blame", "deploy")
    assert result.exit_code == 0
    tree = jenkins.last_request.qs["tree"][0].lower()
    assert "culprits[" in tree
    assert "changesets[" in tree


def test_build_blame_freestyle_changeset_shape(jenkins):
    _build_info_http(
        jenkins,
        {
            "5": {
                "number": 5,
                "culprits": [],
                "changeSet": {
                    "items": [
                        {
                            "commitId": "0123abcd",
                            "msg": "polish the silver",
                            "author": {"fullName": "Jeeves"},
                        }
                    ]
                },
            }
        },
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "build", "blame", "deploy", "5"
    )
    assert result.exit_code == 0
    assert "polish the silver" in result.stdout
    assert "Jeeves" in result.stdout
    assert "Persons of interest" not in result.stderr


def test_build_blame_empty_changeset(jenkins):
    _build_info_http(
        jenkins, {"lastBuild": {"number": 3, "culprits": [], "changeSets": []}}
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "blame", "deploy")
    assert result.exit_code == 0
    assert "Not a single change aboard build #3" in result.stderr


def test_build_blame_no_scm_build(jenkins):
    # A job with no SCM at all: neither changeSet nor changeSets in the JSON.
    _build_info_http(jenkins, {"lastBuild": {"number": 4}})
    result = _invoke("--no-colour", "--no-update-check", "build", "blame", "deploy")
    assert result.exit_code == 0
    assert "Not a single change aboard build #4" in result.stderr


def test_build_blame_missing_build(jenkins):
    _build_info_http(jenkins, {"lastFailedBuild": None})
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "build",
        "blame",
        "deploy",
        "lastFailedBuild",
    )
    assert result.exit_code == 0
    assert "could find no build 'lastFailedBuild'" in result.stderr


def test_build_blame_json_exposes_semantic_records(jenkins):
    _build_info_http(jenkins, {"lastBuild": _BLAME_PIPELINE_BUILD})
    result = _invoke(
        "--no-update-check", "--format", "json", "build", "blame", "deploy"
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["commit"] == "deadbeefcafe1234"  # full id in structured output
    assert data[0]["author"] == "Bertie Wooster"
    assert data[0]["email"] == "bertie@drones.example"
    assert data[0]["message"] == "fix the boiler"


def test_builds_list_param_filter(jenkins):
    _builds_list_http(
        jenkins,
        [
            {
                "number": 142,
                "result": "SUCCESS",
                "building": False,
                "actions": [
                    {
                        "_class": "hudson.model.ParametersAction",
                        "parameters": [{"name": "CHANGE_ID", "value": "abc"}],
                    }
                ],
            },
            {
                "number": 141,
                "result": "SUCCESS",
                "building": False,
                "actions": [
                    {
                        "_class": "hudson.model.ParametersAction",
                        "parameters": [{"name": "CHANGE_ID", "value": "xyz"}],
                    }
                ],
            },
        ],
    )
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "build",
        "list",
        "deploy",
        "--param",
        "CHANGE_ID=abc",
    )
    assert result.exit_code == 0
    assert "#142" in result.stdout
    assert "#141" not in result.stdout


def test_builds_list_param_filter_bad_format(jenkins):
    _builds_list_http(jenkins, [])
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "build",
        "list",
        "deploy",
        "--param",
        "not-a-kv",
    )
    assert result.exit_code == 1
    assert "KEY=VALUE" in result.stderr


# ── params ────────────────────────────────────────────────────────────────────


def test_params_table(jenkins):
    _job_detail_http(
        jenkins,
        {
            "property": [
                {
                    "_class": "hudson.model.ParametersDefinitionProperty",
                    "parameterDefinitions": [
                        {
                            "_class": "hudson.model.StringParameterDefinition",
                            "name": "BRANCH",
                            "description": "git branch",
                            "defaultParameterValue": {"value": "main"},
                        },
                        {
                            "_class": "hudson.model.ChoiceParameterDefinition",
                            "name": "ENV",
                            "choices": ["dev", "prod"],
                            "defaultParameterValue": {"value": "dev"},
                        },
                    ],
                }
            ]
        },
    )
    result = _invoke("--no-colour", "--no-update-check", "job", "params", "deploy")
    assert result.exit_code == 0
    assert "BRANCH" in result.stdout
    assert "string" in result.stdout
    assert "choice" in result.stdout
    assert "dev, prod" in result.stdout


def test_params_json_types(jenkins):
    _job_detail_http(
        jenkins,
        {
            "property": [
                {
                    "_class": "hudson.model.ParametersDefinitionProperty",
                    "parameterDefinitions": [
                        {
                            "_class": "hudson.model.BooleanParameterDefinition",
                            "name": "DEBUG",
                            "defaultParameterValue": {"value": False},
                        }
                    ],
                }
            ]
        },
    )
    result = _invoke("--no-update-check", "--format", "json", "job", "params", "deploy")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["name"] == "DEBUG"
    assert data[0]["type"] == "boolean"
    assert data[0]["default"] is False


def test_params_unparameterised_empty_state(jenkins):
    _job_detail_http(jenkins, {"property": []})
    result = _invoke("--no-colour", "--no-update-check", "job", "params", "deploy")
    assert result.exit_code == 0
    assert "no special instructions" in result.stderr
    assert result.stdout.strip() == ""


# ── rebuild ───────────────────────────────────────────────────────────────────


def test_rebuild_carries_previous_params(jenkins):
    info = {
        "actions": [
            {
                "_class": "hudson.model.ParametersAction",
                "parameters": [
                    {"name": "BRANCH", "value": "main"},
                    {"name": "DEBUG", "value": "false"},
                ],
            }
        ]
    }
    _rebuild_http(jenkins, info)
    result = _invoke("--no-colour", "--no-update-check", "build", "rebuild", "deploy")
    assert result.exit_code == 0
    post = _last_post(jenkins)
    assert post.url.lower().endswith("/buildwithparameters")
    assert parse_qs(post.text) == {"BRANCH": ["main"], "DEBUG": ["false"]}


def test_rebuild_override_wins(jenkins):
    info = {
        "actions": [
            {
                "_class": "hudson.model.ParametersAction",
                "parameters": [{"name": "BRANCH", "value": "main"}],
            }
        ]
    }
    _rebuild_http(jenkins, info)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "build",
        "rebuild",
        "deploy",
        "--param",
        "BRANCH=dev",
    )
    assert result.exit_code == 0
    assert parse_qs(_last_post(jenkins).text) == {"BRANCH": ["dev"]}


def test_rebuild_no_params_plain(jenkins):
    _rebuild_http(jenkins, {"actions": []})
    result = _invoke("--no-colour", "--no-update-check", "build", "rebuild", "deploy")
    assert result.exit_code == 0
    post = _last_post(jenkins)
    assert post.url.lower().endswith("/build")
    assert not post.text


def test_rebuild_missing_build_errors(jenkins):
    _rebuild_http(jenkins, None)
    result = _invoke("--no-colour", "--no-update-check", "build", "rebuild", "deploy")
    assert result.exit_code == 1
    assert "no build on record" in result.output


# ── job trigger --wait ────────────────────────────────────────────────────────

_QUEUED = {"why": "Waiting for next available executor"}
_ASSIGNED = {"executable": {"number": 42}}


def _wait_http(jenkins, queue_responses, build_responses):
    """Register trigger + queue-item + build-info endpoints for --wait tests."""
    location = {"Location": url("queue/item/55/")}
    jenkins.get(url("crumbIssuer/api/json"), status_code=404)
    jenkins.post(url("job/my-pipeline/build"), status_code=201, headers=location)
    jenkins.post(
        url("job/my-pipeline/buildWithParameters"), status_code=201, headers=location
    )
    jenkins.get(api("queue/item/55"), queue_responses)
    if build_responses:
        jenkins.get(api("job/my-pipeline/42"), build_responses)


def _invoke_wait(*extra):
    return _invoke(
        "--no-colour",
        "--no-update-check",
        "job",
        "trigger",
        "my-pipeline",
        "--wait",
        "--poll-interval",
        "0.1",
        *extra,
    )


def test_trigger_wait_success_exit_0(jenkins, monkeypatch):
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)
    _wait_http(
        jenkins,
        [{"json": _QUEUED}, {"json": _ASSIGNED}],
        [
            {"json": {"building": True, "result": None}},
            {"json": {"building": False, "result": "SUCCESS"}},
        ],
    )
    result = _invoke_wait()
    assert result.exit_code == 0
    assert "SUCCESS" in result.stdout
    assert "Held in the queue" in result.stderr
    assert "under way" in result.stderr


def test_trigger_wait_failure_exit_1(jenkins, monkeypatch):
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)
    _wait_http(
        jenkins,
        [{"json": _ASSIGNED}],
        [{"json": {"building": False, "result": "FAILURE"}}],
    )
    result = _invoke_wait()
    assert result.exit_code == 1
    assert "FAILURE" in result.stdout


def test_trigger_wait_unstable_exit_2(jenkins, monkeypatch):
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)
    _wait_http(
        jenkins,
        [{"json": _ASSIGNED}],
        [{"json": {"building": False, "result": "UNSTABLE"}}],
    )
    result = _invoke_wait()
    assert result.exit_code == 2
    assert "UNSTABLE" in result.stdout


def test_trigger_wait_aborted_exit_3(jenkins, monkeypatch):
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)
    _wait_http(
        jenkins,
        [{"json": _ASSIGNED}],
        [{"json": {"building": False, "result": "ABORTED"}}],
    )
    result = _invoke_wait()
    assert result.exit_code == 3
    assert "aborted" in result.stdout


def test_trigger_wait_cancelled_in_queue_exit_3(jenkins):
    _wait_http(jenkins, [{"json": {"cancelled": True}}], [])
    result = _invoke_wait()
    assert result.exit_code == 3
    assert "dismissed" in result.stderr


def test_trigger_wait_timeout_exit_124(jenkins, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(cli_mod.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(
        cli_mod.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s)
    )
    _wait_http(jenkins, [{"json": _QUEUED}], [])
    result = _invoke_wait("--timeout", "3")
    assert result.exit_code == 124
    assert "patience" in result.stderr


def test_trigger_wait_why_emitted_once_per_change(jenkins, monkeypatch):
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)
    _wait_http(
        jenkins,
        [{"json": _QUEUED}, {"json": _QUEUED}, {"json": _ASSIGNED}],
        [{"json": {"building": False, "result": "SUCCESS"}}],
    )
    result = _invoke_wait()
    assert result.exit_code == 0
    assert result.stderr.count("Held in the queue") == 1


def test_trigger_wait_with_params_uses_buildwithparameters(jenkins, monkeypatch):
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)
    _wait_http(
        jenkins,
        [{"json": _ASSIGNED}],
        [{"json": {"building": False, "result": "SUCCESS"}}],
    )
    result = _invoke_wait("--param", "ENV=prod")
    assert result.exit_code == 0
    assert _last_post(jenkins).url.lower().endswith("/buildwithparameters")


def test_trigger_wait_without_location_errors(jenkins):
    _trigger_http(jenkins)  # registers the POSTs without a Location header
    result = _invoke(
        "--no-colour", "--no-update-check", "job", "trigger", "my-pipeline", "--wait"
    )
    assert result.exit_code == 1
    assert "cannot follow" in result.stderr


def test_trigger_wait_queue_error_exits_1(jenkins):
    jenkins.get(url("crumbIssuer/api/json"), status_code=404)
    jenkins.post(
        url("job/my-pipeline/build"),
        status_code=201,
        headers={"Location": url("queue/item/55/")},
    )
    jenkins.get(api("queue/item/55"), status_code=500)
    result = _invoke_wait()
    assert result.exit_code == 1
    assert "500" in result.stderr


def test_trigger_without_wait_does_not_poll(jenkins):
    _trigger_http(jenkins)
    result = _invoke(
        "--no-colour", "--no-update-check", "job", "trigger", "my-pipeline"
    )
    assert result.exit_code == 0
    assert all("queue/item" not in r.url for r in jenkins.request_history)


# ── queue ─────────────────────────────────────────────────────────────────────


def test_queue_shows_items(jenkins):
    _queue_http(
        jenkins, [{"why": "waiting", "stuck": False, "task": {"name": "deploy"}}]
    )
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "waiting" in result.output or "pending" in result.output


def test_queue_shows_stuck_label(jenkins):
    _queue_http(
        jenkins, [{"why": "blocked", "stuck": True, "task": {"name": "deploy"}}]
    )
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "yes" in result.output


def test_queue_empty_shows_butler_message(jenkins):
    _queue_http(jenkins, [])
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "empty" in result.output or "leisure" in result.output
    assert "😴 The queue" in result.output


# ── cancel ────────────────────────────────────────────────────────────────────


def test_cancel_shows_dismissed_message(jenkins):
    jenkins.get(url("crumbIssuer/api/json"), status_code=404)
    jenkins.post(url("job/my-pipeline/5/stop"), status_code=200)
    result = _invoke(
        "--no-colour", "--no-update-check", "build", "cancel", "my-pipeline", "5"
    )
    assert result.exit_code == 0
    assert "dismissed" in result.output
    assert _last_post(jenkins).url.lower().endswith("/5/stop")


# ── nodes ─────────────────────────────────────────────────────────────────────


def test_nodes_shows_household_staff(jenkins):
    _nodes_http(
        jenkins, [{"displayName": "agent1", "offline": False, "numExecutors": 2}]
    )
    result = _invoke("--no-colour", "--no-update-check", "node", "list")
    assert result.exit_code == 0
    assert "agent1" in result.output
    assert "household" in result.output


def test_nodes_shows_online_offline_labels(jenkins):
    _nodes_http(
        jenkins,
        [
            {"displayName": "up", "offline": False, "numExecutors": 2},
            {"displayName": "down", "offline": True, "numExecutors": 0},
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "node", "list")
    assert result.exit_code == 0
    assert "online" in result.output
    assert "offline" in result.output


def test_nodes_empty_shows_butler_message(jenkins):
    _nodes_http(jenkins, [])
    result = _invoke("--no-colour", "--no-update-check", "node", "list")
    assert result.exit_code == 0
    assert "absented" in result.output or "notice" in result.output
    assert "🚪 The household" in result.output


_GB = 1024**3


def _stats_node(**monitors):
    return {
        "displayName": "agent-1",
        "offline": False,
        "numExecutors": 4,
        "assignedLabels": [{"name": "agent-1"}, {"name": "linux"}],
        "monitorData": monitors,
    }


def test_nodes_stats_table(jenkins):
    node = _stats_node(
        **{
            "hudson.node_monitors.DiskSpaceMonitor": {"size": 3 * _GB, "path": "/"},
            "hudson.node_monitors.TemporarySpaceMonitor": {"size": 50 * _GB},
            "hudson.node_monitors.SwapSpaceMonitor": {"availableSwapSpace": 2 * _GB},
            "hudson.node_monitors.ResponseTimeMonitor": {"average": 42},
            "hudson.node_monitors.ArchitectureMonitor": "Linux (amd64)",
        }
    )
    _nodes_http(jenkins, [node])
    result = _invoke("--no-colour", "--no-update-check", "node", "list", "--stats")
    assert result.exit_code == 0
    # stats columns present, executors/labels columns dropped
    assert "Disk" in result.stdout
    assert "Response" in result.stdout
    assert "3.0 GB" in result.stdout
    assert "42ms" in result.stdout
    assert "Linux (amd64)" in result.stdout
    assert "Labels" not in result.stdout


def test_nodes_stats_handles_missing_monitors(jenkins):
    _nodes_http(jenkins, [_stats_node()])  # no monitorData entries
    result = _invoke("--no-colour", "--no-update-check", "node", "list", "--stats")
    assert result.exit_code == 0
    # unreported monitors render as a dash, no crash
    assert "—" in result.stdout


def test_nodes_stats_json_raw_values(jenkins):
    node = _stats_node(
        **{
            "hudson.node_monitors.DiskSpaceMonitor": {"size": 3 * _GB},
            "hudson.node_monitors.ResponseTimeMonitor": {"average": 42},
        }
    )
    _nodes_http(jenkins, [node])
    result = _invoke("--no-update-check", "--format", "json", "node", "list", "--stats")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["disk"] == 3 * _GB
    assert data[0]["response_ms"] == 42
    assert data[0]["swap"] is None


def test_nodes_stats_requests_depth(jenkins):
    _nodes_http(jenkins, [])
    _invoke("--no-update-check", "node", "list", "--stats")
    assert jenkins.last_request.qs == {"depth": ["1"]}
    _invoke("--no-update-check", "node", "list")
    assert jenkins.last_request.qs == {}


def test_nodes_shows_labels(jenkins):
    _nodes_http(
        jenkins,
        [
            {
                "displayName": "agent-1",
                "offline": False,
                "numExecutors": 4,
                "assignedLabels": [
                    {"name": "agent-1"},
                    {"name": "linux"},
                    {"name": "docker"},
                ],
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "node", "list")
    assert result.exit_code == 0
    assert "Labels" in result.output
    assert "linux" in result.output
    assert "docker" in result.output


def test_nodes_filters_own_name_from_labels(jenkins):
    _nodes_http(
        jenkins,
        [
            {
                "displayName": "build-node",
                "offline": False,
                "numExecutors": 2,
                "assignedLabels": [{"name": "build-node"}, {"name": "java"}],
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "node", "list")
    assert result.exit_code == 0
    assert "java" in result.output
    # node name appears once (Node column) but not again in Labels column
    assert result.output.count("build-node") == 1


def test_nodes_empty_labels_renders_blank(jenkins):
    _nodes_http(
        jenkins,
        [
            {
                "displayName": "agent-1",
                "offline": False,
                "numExecutors": 2,
                "assignedLabels": [{"name": "agent-1"}],
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "node", "list")
    assert result.exit_code == 0
    assert "Labels" in result.output


_SSH_NODE_XML = """<slave>
  <name>ssh-agent</name>
  <launcher class="hudson.plugins.sshslaves.SSHLauncher">
    <host>10.0.4.17</host>
    <port>22</port>
  </launcher>
</slave>"""

_JNLP_NODE_XML = """<slave>
  <name>inbound-agent</name>
  <launcher class="hudson.slaves.JNLPLauncher"/>
</slave>"""


def test_nodes_address_shows_ssh_host(jenkins):
    _nodes_http(
        jenkins,
        [
            {"displayName": "Built-In Node", "offline": False, "numExecutors": 2},
            {"displayName": "ssh-agent", "offline": False, "numExecutors": 4},
        ],
    )
    jenkins.get(url("computer/ssh-agent/config.xml"), text=_SSH_NODE_XML)
    result = _invoke("--no-colour", "--no-update-check", "node", "list", "--address")
    assert result.exit_code == 0
    assert "Address" in result.output
    assert "10.0.4.17" in result.output
    assert "(local)" in result.output


def test_nodes_address_inbound_agent_shows_dash(jenkins):
    _nodes_http(
        jenkins,
        [{"displayName": "inbound-agent", "offline": False, "numExecutors": 1}],
    )
    jenkins.get(url("computer/inbound-agent/config.xml"), text=_JNLP_NODE_XML)
    result = _invoke("--no-colour", "--no-update-check", "node", "list", "--address")
    assert result.exit_code == 0
    assert "—" in result.stdout


def test_nodes_address_permission_error_degrades_to_dash(jenkins):
    _nodes_http(
        jenkins,
        [{"displayName": "locked-agent", "offline": False, "numExecutors": 1}],
    )
    jenkins.get(url("computer/locked-agent/config.xml"), status_code=403)
    result = _invoke("--no-colour", "--no-update-check", "node", "list", "--address")
    assert result.exit_code == 0
    assert "locked-agent" in result.stdout
    assert "—" in result.stdout


def test_nodes_address_works_with_stats(jenkins):
    node = _stats_node(**{"hudson.node_monitors.ResponseTimeMonitor": {"average": 42}})
    _nodes_http(jenkins, [node])
    jenkins.get(url("computer/agent-1/config.xml"), text=_SSH_NODE_XML)
    result = _invoke(
        "--no-colour", "--no-update-check", "node", "list", "--stats", "--address"
    )
    assert result.exit_code == 0
    assert "Response" in result.stdout
    assert "10.0.4.17" in result.stdout


def test_nodes_address_json_semantic_value(jenkins):
    _nodes_http(
        jenkins, [{"displayName": "ssh-agent", "offline": False, "numExecutors": 4}]
    )
    jenkins.get(url("computer/ssh-agent/config.xml"), text=_SSH_NODE_XML)
    result = _invoke(
        "--no-update-check", "--format", "json", "node", "list", "--address"
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["address"] == "10.0.4.17"


def test_nodes_no_address_flag_skips_config_fetch(jenkins):
    _nodes_http(
        jenkins, [{"displayName": "ssh-agent", "offline": False, "numExecutors": 4}]
    )
    result = _invoke("--no-colour", "--no-update-check", "node", "list")
    assert result.exit_code == 0
    assert "Address" not in result.output
    assert not any("config.xml" in r.url for r in jenkins.request_history)


def test_nodes_address_malformed_xml_degrades_to_dash(jenkins):
    _nodes_http(
        jenkins, [{"displayName": "odd-agent", "offline": False, "numExecutors": 1}]
    )
    jenkins.get(url("computer/odd-agent/config.xml"), text="<not-xml")
    result = _invoke("--no-colour", "--no-update-check", "node", "list", "--address")
    assert result.exit_code == 0
    assert "—" in result.stdout


# ── whoami ────────────────────────────────────────────────────────────────────


def test_whoami_authenticated(jenkins):
    jenkins.get(api("me"), json={"id": "alice", "fullName": "Alice Smith"})
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 0
    assert "alice" in result.output
    assert "Alice Smith" in result.output


def test_whoami_anonymous(jenkins):
    jenkins.get(api("me"), json={"id": "anonymous", "fullName": "anonymous"})
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 0
    assert "anonymous" in result.output


def test_whoami_error_shows_butler_message(jenkins):
    jenkins.get(api("me"), exc=requests.exceptions.ConnectionError)
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 1
    assert "unreachable" in result.output


# ── connection profiles ───────────────────────────────────────────────────────


def _profiles_config(tmp_path, head=""):
    """Write a two-profile config; ``head`` prepends top-level keys."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        head + '[profiles.prod]\nurl = "http://prod.example.com"\n'
        'token = "prod-secret"\n'
        '\n[profiles.staging]\nurl = "http://staging.example.com"\n'
    )
    return str(cfg_file)


def test_profile_flag_routes_to_profile_url(jenkins, tmp_path):
    jenkins.get("http://prod.example.com/api/json", json=_STATUS_JSON)
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        cfg,
        "--profile",
        "prod",
        "status",
    )
    assert result.exit_code == 0
    # the fixture's JEEVES_URL is demoted; the profile URL wins
    assert jenkins.last_request.url.startswith("http://prod.example.com")


def test_profile_env_var_selects_profile(jenkins, tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_PROFILE", "staging")
    jenkins.get("http://staging.example.com/api/json", json=_STATUS_JSON)
    cfg = _profiles_config(tmp_path)
    result = _invoke("--no-colour", "--no-update-check", "--config", cfg, "status")
    assert result.exit_code == 0
    assert jenkins.last_request.url.startswith("http://staging.example.com")


def test_profile_flag_beats_env_profile(jenkins, tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_PROFILE", "staging")
    jenkins.get("http://prod.example.com/api/json", json=_STATUS_JSON)
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        cfg,
        "--profile",
        "prod",
        "status",
    )
    assert result.exit_code == 0
    assert jenkins.last_request.url.startswith("http://prod.example.com")


def test_default_profile_config_key(jenkins, tmp_path):
    jenkins.get("http://prod.example.com/api/json", json=_STATUS_JSON)
    cfg = _profiles_config(tmp_path, head='default-profile = "prod"\n\n')
    result = _invoke("--no-colour", "--no-update-check", "--config", cfg, "status")
    assert result.exit_code == 0
    assert jenkins.last_request.url.startswith("http://prod.example.com")


def test_explicit_url_flag_overrides_profile(jenkins, tmp_path):
    jenkins.get(api(), json=_STATUS_JSON)
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        cfg,
        "--profile",
        "prod",
        "--url",
        "http://jenkins.example.com",
        "status",
    )
    assert result.exit_code == 0
    assert jenkins.last_request.url.startswith("http://jenkins.example.com")


def test_profile_missing_field_falls_back_to_env(jenkins, tmp_path):
    # profile has no url; the fixture's JEEVES_URL fills the gap
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[profiles.bare]\ntoken = "abc"\n')
    jenkins.get(api(), json=_STATUS_JSON)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        str(cfg_file),
        "--profile",
        "bare",
        "status",
    )
    assert result.exit_code == 0
    assert jenkins.last_request.url.startswith("http://jenkins.example.com")


def test_unknown_profile_butler_error(tmp_path):
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        cfg,
        "--profile",
        "bogus",
        "status",
    )
    assert result.exit_code == 1
    assert "🎩" in result.stderr
    assert "bogus" in result.stderr
    assert "prod" in result.stderr
    assert "staging" in result.stderr


def test_unknown_default_profile_errors(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('default-profile = "gone"\n')
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", str(cfg_file), "status"
    )
    assert result.exit_code == 1
    assert "gone" in result.stderr
    assert "No profiles are configured" in result.stderr


def test_show_config_lists_profiles_and_masks_tokens(tmp_path, monkeypatch):
    # --show-config must work even when JEEVES_PROFILE points at nothing
    monkeypatch.setenv("JEEVES_PROFILE", "bogus")
    cfg = _profiles_config(tmp_path)
    result = _invoke("--config", cfg, "--show-config")
    assert result.exit_code == 0
    assert "prod" in result.output
    assert "staging" in result.output
    assert "prod-secret" not in result.output
    assert "***" in result.output


def test_flat_config_still_works(jenkins, tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_URL", raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('jenkins-url = "http://flat.example.com"\n')
    jenkins.get("http://flat.example.com/api/json", json=_STATUS_JSON)
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", str(cfg_file), "status"
    )
    assert result.exit_code == 0
    assert jenkins.last_request.url.startswith("http://flat.example.com")


def test_complete_profile_returns_matching_names(tmp_path):
    from types import SimpleNamespace

    cfg = _profiles_config(tmp_path)
    ctx = SimpleNamespace(params={"config_path": cfg})
    items = cli_mod._complete_profile(ctx, None, "")
    assert [i.value for i in items] == ["prod", "staging"]
    items = cli_mod._complete_profile(ctx, None, "st")
    assert [i.value for i in items] == ["staging"]


def test_complete_profile_bad_config_returns_empty(tmp_path):
    from types import SimpleNamespace

    bad = tmp_path / "bad.toml"
    bad.write_text("not = [valid toml")
    ctx = SimpleNamespace(params={"config_path": str(bad)})
    assert cli_mod._complete_profile(ctx, None, "") == []


# ── profile management commands ───────────────────────────────────────────────


def test_profile_list_table_masks_and_marks_default(tmp_path):
    cfg = _profiles_config(tmp_path, head='default-profile = "prod"\n\n')
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", cfg, "profile", "list"
    )
    assert result.exit_code == 0
    assert "ledger" in result.stderr
    assert "prod" in result.stdout
    assert "staging" in result.stdout
    assert "prod-secret" not in result.output
    assert "***" in result.stdout
    assert "✓" in result.stdout


def test_profile_list_json_never_leaks_tokens(tmp_path):
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-update-check", "--format", "json", "--config", cfg, "profile", "list"
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    by_name = {r["name"]: r for r in data}
    assert by_name["prod"]["token_set"] is True
    assert by_name["staging"]["token_set"] is False
    assert "prod-secret" not in result.stdout


def test_profile_list_empty_shows_butler_message(tmp_path):
    empty = tmp_path / "config.toml"
    empty.write_text('theme = "default"\n')
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", str(empty), "profile", "list"
    )
    assert result.exit_code == 0
    assert "🗂️ The ledger" in result.stderr


def test_profile_add_creates_profile(tmp_path):
    cfg_file = tmp_path / "config.toml"
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        str(cfg_file),
        "profile",
        "add",
        "prod",
        "--url",
        "http://prod.example.com",
        "--username",
        "steve",
        "--token",
        "abc",
        "--default",
    )
    assert result.exit_code == 0
    assert "📇 Very good. Profile 'prod'" in result.stdout
    assert "as the default" in result.stdout
    from jeeves.config import load_config

    cfg = load_config(str(cfg_file))
    assert cfg["profiles"]["prod"]["url"] == "http://prod.example.com"
    assert cfg["default-profile"] == "prod"


def test_profile_add_existing_needs_force(tmp_path):
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        cfg,
        "profile",
        "add",
        "prod",
        "--url",
        "http://elsewhere",
    )
    assert result.exit_code == 1
    assert "already on the books" in result.stderr
    assert "--force" in result.stderr


def test_profile_add_force_updates(tmp_path):
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        cfg,
        "profile",
        "add",
        "prod",
        "--token",
        "rotated",
        "--force",
    )
    assert result.exit_code == 0
    from jeeves.config import load_config

    loaded = load_config(cfg)
    assert loaded["profiles"]["prod"]["token"] == "rotated"
    assert loaded["profiles"]["prod"]["url"] == "http://prod.example.com"


def test_profile_add_token_dash_reads_stdin(tmp_path):
    cfg_file = tmp_path / "config.toml"
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        str(cfg_file),
        "profile",
        "add",
        "prod",
        "--url",
        "http://prod",
        "--token",
        "-",
        input="hush-hush\n",
    )
    assert result.exit_code == 0
    from jeeves.config import load_config

    assert load_config(str(cfg_file))["profiles"]["prod"]["token"] == "hush-hush"
    assert "hush-hush" not in result.stdout


def test_profile_remove_clears_dangling_default(tmp_path):
    cfg = _profiles_config(tmp_path, head='default-profile = "prod"\n\n')
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", cfg, "profile", "remove", "prod"
    )
    assert result.exit_code == 0
    assert "🗑️ Profile 'prod'" in result.stdout
    assert "default cleared" in result.stdout
    from jeeves.config import load_config

    loaded = load_config(cfg)
    assert "default-profile" not in loaded
    assert "prod" not in loaded["profiles"]


def test_profile_remove_unknown_lists_profiles(tmp_path):
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "--config",
        cfg,
        "profile",
        "remove",
        "bogus",
    )
    assert result.exit_code == 1
    assert "🎩" in result.stderr
    assert "prod, staging" in result.stderr


def test_profile_use_sets_default(tmp_path):
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", cfg, "profile", "use", "staging"
    )
    assert result.exit_code == 0
    assert "'staging' shall be the default" in result.stdout
    from jeeves.config import load_config

    assert load_config(cfg)["default-profile"] == "staging"


def test_profile_use_clear_unsets_default(tmp_path):
    cfg = _profiles_config(tmp_path, head='default-profile = "prod"\n\n')
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", cfg, "profile", "use", "--clear"
    )
    assert result.exit_code == 0
    assert "reverts to the flat keys" in result.stdout
    from jeeves.config import load_config

    assert "default-profile" not in load_config(cfg)


def test_profile_use_unknown_errors(tmp_path):
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", cfg, "profile", "use", "bogus"
    )
    assert result.exit_code == 1
    assert "no profile called 'bogus'" in result.stderr


def test_profile_use_requires_name_or_clear(tmp_path):
    cfg = _profiles_config(tmp_path)
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", cfg, "profile", "use"
    )
    assert result.exit_code == 1
    assert "one or the other" in result.stderr


def test_profile_commands_survive_broken_default_profile(tmp_path):
    # a dangling default-profile must not brick the repair commands…
    broken = tmp_path / "config.toml"
    broken.write_text('default-profile = "gone"\n')
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", str(broken), "profile", "list"
    )
    assert result.exit_code == 0
    # …while other commands still refuse it up front
    result = _invoke(
        "--no-colour", "--no-update-check", "--config", str(broken), "status"
    )
    assert result.exit_code == 1
    assert "gone" in result.stderr


# ── deprecated aliases ────────────────────────────────────────────────────────

_NOTICE = "has moved to"


def test_alias_jobs_works_and_warns(jenkins):
    _jobs_http(jenkins, [{"name": "deploy-prod", "color": "blue"}])
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "deploy-prod" in result.stdout
    assert _NOTICE in result.stderr
    assert "🎩" in result.stderr
    assert _NOTICE not in result.stdout


def test_alias_params_works_and_warns(jenkins):
    _job_detail_http(jenkins, {"property": []})
    result = _invoke("--no-colour", "--no-update-check", "params", "deploy")
    assert result.exit_code == 0
    assert "'jeeves job params JOB'" in result.stderr


def test_alias_builds_group_works_and_warns(jenkins):
    _builds_list_http(jenkins, [{"number": 3, "result": "SUCCESS", "building": False}])
    result = _invoke("--no-colour", "--no-update-check", "builds", "list", "deploy")
    assert result.exit_code == 0
    assert "#3" in result.stdout
    assert "'jeeves build list JOB'" in result.stderr


def test_alias_rebuild_works_and_warns(jenkins):
    _rebuild_http(jenkins, {"actions": []})
    result = _invoke("--no-colour", "--no-update-check", "rebuild", "deploy")
    assert result.exit_code == 0
    assert "'jeeves build rebuild JOB'" in result.stderr


def test_alias_log_keeps_old_option_signature(jenkins):
    jenkins.get(url("job/deploy/7/consoleText"), text="the log")
    result = _invoke(
        "--no-colour", "--no-update-check", "log", "deploy", "--build", "7"
    )
    assert result.exit_code == 0
    assert "the log" in result.stdout
    assert "'jeeves build log JOB [BUILD]'" in result.stderr


def test_alias_cancel_keeps_old_option_signature(jenkins):
    jenkins.get(url("crumbIssuer/api/json"), status_code=404)
    jenkins.post(url("job/deploy/5/stop"), status_code=200)
    result = _invoke(
        "--no-colour", "--no-update-check", "cancel", "deploy", "--build", "5"
    )
    assert result.exit_code == 0
    assert _last_post(jenkins).url.lower().endswith("/5/stop")
    assert "'jeeves build cancel JOB BUILD'" in result.stderr


def test_alias_nodes_works_and_warns(jenkins):
    _nodes_http(jenkins, [{"displayName": "agent-1", "offline": False}])
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "agent-1" in result.stdout
    assert "'jeeves node list'" in result.stderr


def test_legacy_build_verb_falls_back_to_trigger(jenkins):
    _trigger_http(jenkins)
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "build",
        "my-pipeline",
        "--param",
        "ENV=prod",
    )
    assert result.exit_code == 0
    assert "dispatch" in result.stdout
    post = _last_post(jenkins)
    assert post.url.lower().endswith("/buildwithparameters")
    assert parse_qs(post.text) == {"ENV": ["prod"]}
    assert "'jeeves job trigger JOB'" in result.stderr


def test_legacy_build_verb_nested_job_path(jenkins):
    _trigger_http(jenkins, job_path="job/folder/job/nested-job")
    result = _invoke("--no-colour", "--no-update-check", "build", "folder/nested-job")
    assert result.exit_code == 0
    assert "/job/folder/job/nested-job/build" in _last_post(jenkins).url
    assert _NOTICE in result.stderr


def test_build_subcommand_takes_priority_over_fallback(jenkins):
    _builds_list_http(jenkins, [])
    result = _invoke("--no-colour", "--no-update-check", "build", "list", "deploy")
    assert result.exit_code == 0
    assert _NOTICE not in result.stderr


def test_new_spellings_emit_no_notice(jenkins):
    _jobs_http(jenkins, [{"name": "deploy", "color": "blue"}])
    result = _invoke("--no-colour", "--no-update-check", "job", "list", "--no-weather")
    assert result.exit_code == 0
    assert _NOTICE not in result.stderr


def test_bare_build_shows_group_usage():
    result = _invoke("--no-colour", "--no-update-check", "build")
    assert result.exit_code == 2


def test_build_group_help_lists_subcommands():
    result = _invoke("--no-colour", "--no-update-check", "build", "--help")
    assert result.exit_code == 0
    listed = _listed_commands(result.output)
    assert {"list", "summary", "show", "log", "cancel", "rebuild"} <= listed
    assert "build" not in listed


def test_aliases_hidden_from_help():
    result = _invoke("--help")
    assert result.exit_code == 0
    listed = _listed_commands(result.output)
    old = {"jobs", "builds", "params", "rebuild", "log", "cancel", "nodes"}
    assert not listed & old


def test_build_log_new_positional_form(jenkins):
    jenkins.get(url("job/deploy/7/consoleText"), text="console output")
    result = _invoke("--no-colour", "--no-update-check", "build", "log", "deploy", "7")
    assert result.exit_code == 0
    assert "console output" in result.stdout


def test_build_log_defaults_to_last_build(jenkins):
    jenkins.get(url("job/deploy/lastBuild/consoleText"), text="")
    result = _invoke("--no-colour", "--no-update-check", "build", "log", "deploy")
    assert result.exit_code == 0


# ── build log --follow ────────────────────────────────────────────────────────


def test_build_log_follow_streams_until_complete(jenkins, monkeypatch):
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)
    jenkins.get(
        url("job/deploy/lastBuild/logText/progressiveText"),
        [
            {
                "text": "line one\n",
                "headers": {"X-Text-Size": "9", "X-More-Data": "true"},
            },
            {
                "text": "line two\n",
                "headers": {"X-Text-Size": "18", "X-More-Data": "true"},
            },
            {"text": "", "headers": {"X-Text-Size": "18"}},
        ],
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "build", "log", "deploy", "--follow"
    )
    assert result.exit_code == 0
    assert result.stdout == "line one\nline two\n"
    starts = [r.qs["start"][0] for r in jenkins.request_history]
    assert starts == ["0", "9", "18"]


def test_build_log_follow_short_flag(jenkins, monkeypatch):
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)
    jenkins.get(
        url("job/deploy/lastBuild/logText/progressiveText"),
        text="done\n",
        headers={"X-Text-Size": "5"},
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "log", "deploy", "-f")
    assert result.exit_code == 0
    assert result.stdout == "done\n"


def test_build_log_follow_already_finished_single_poll(jenkins, monkeypatch):
    sleeps = {"n": 0}
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: sleeps.__setitem__("n", 1))
    jenkins.get(
        url("job/deploy/7/logText/progressiveText"),
        text="all done\n",
        headers={"X-Text-Size": "9"},
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "build", "log", "deploy", "7", "--follow"
    )
    assert result.exit_code == 0
    assert result.stdout == "all done\n"
    assert sleeps["n"] == 0


def test_build_log_follow_error_shows_butler_message(jenkins):
    jenkins.get(
        url("job/deploy/lastBuild/logText/progressiveText"),
        exc=requests.exceptions.ConnectionError,
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "build", "log", "deploy", "--follow"
    )
    assert result.exit_code == 1
    assert "unreachable" in result.output


def test_build_log_follow_ctrl_c_exits_cleanly(jenkins, monkeypatch):
    def _raise_interrupt(_s):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_mod.time, "sleep", _raise_interrupt)
    jenkins.get(
        url("job/deploy/lastBuild/logText/progressiveText"),
        text="still running\n",
        headers={"X-Text-Size": "14", "X-More-Data": "true"},
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "build", "log", "deploy", "--follow"
    )
    assert result.exit_code == 130
    assert "still running" in result.stdout
    assert "cease following" in result.stderr


# ── Environment-variable presence semantics (issue #115) ───────────────────


def _update_check_calls(monkeypatch, jenkins, env=None):
    """Run `jeeves status` and return how many times the update check fired."""
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    for name, value in (env or {}).items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    jenkins.get(api(), json=_STATUS_JSON)
    _invoke("--no-colour", "status")
    return called["n"]


@pytest.mark.parametrize("value", ["1", "0", "false", "off", "banana"])
def test_no_update_check_env_any_non_empty_value_suppresses(
    monkeypatch, jenkins, value
):
    # Presence is the signal, per no-color.org: the value is never parsed.
    env = {"JEEVES_NO_UPDATE_CHECK": value}
    assert _update_check_calls(monkeypatch, jenkins, env) == 0


def test_no_update_check_env_empty_leaves_check_enabled(monkeypatch, jenkins):
    env = {"JEEVES_NO_UPDATE_CHECK": ""}
    assert _update_check_calls(monkeypatch, jenkins, env) == 1


def test_no_update_check_env_unset_leaves_check_enabled(monkeypatch, jenkins):
    env = {"JEEVES_NO_UPDATE_CHECK": None}
    assert _update_check_calls(monkeypatch, jenkins, env) == 1


@pytest.mark.parametrize("value", ["1", "0", "false", "banana"])
def test_no_colour_env_any_non_empty_value_disables_colour(monkeypatch, jenkins, value):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **kw: None)
    monkeypatch.setenv("JEEVES_NO_COLOUR", value)
    jenkins.get(api(), json=_STATUS_JSON)
    result = CliRunner().invoke(main, ["status"], color=True)
    assert result.exit_code == 0, result.output
    assert "\033[" not in result.output, f"{value!r} should disable colour"


def test_no_colour_env_empty_leaves_colour_enabled(monkeypatch, jenkins):
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **kw: None)
    monkeypatch.setenv("JEEVES_NO_COLOUR", "")
    jenkins.get(api(), json=_STATUS_JSON)
    result = CliRunner().invoke(main, ["status"], color=True)
    assert result.exit_code == 0
    assert "\033[" in result.output


@pytest.mark.parametrize("var", ["JEEVES_NO_UPDATE_CHECK", "JEEVES_NO_COLOUR"])
def test_unparsable_env_value_never_aborts_the_run(monkeypatch, jenkins, var):
    # The regression: Click's envvar= on a flag rejected unrecognised values,
    # so a typo in a shell profile broke every invocation.
    monkeypatch.setattr(cli_mod, "check_for_update", lambda **kw: None)
    monkeypatch.setenv(var, "banana")
    jenkins.get(api(), json=_STATUS_JSON)
    result = _invoke("status")
    assert result.exit_code == 0, result.output
    assert "not a valid boolean" not in result.output
