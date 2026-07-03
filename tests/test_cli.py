import json as _json

from click.testing import CliRunner

from jeeves import cli as cli_mod
from jeeves import jenkins as jenkins_mod
from jeeves.cli import _hyperlink, main
from jeeves.jenkins import JenkinsError


def _invoke(*args, **kwargs):
    runner = CliRunner()
    return runner.invoke(main, list(args), **kwargs)


# ── Infrastructure ───────────────────────────────────────────────────────────


def test_version():
    result = _invoke("--version")
    assert result.exit_code == 0
    assert "jeeves" in result.output or "0." in result.output


def test_help():
    result = _invoke("--help")
    assert result.exit_code == 0
    assert "--theme" in result.output
    assert "--completion" in result.output
    assert "status" in result.output
    assert "jobs" in result.output


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
    result = _invoke("--completion", "bash")
    assert result.exit_code == 0
    assert "_JEEVES_COMPLETE" in result.output


def test_completion_zsh():
    result = _invoke("--completion", "zsh")
    assert result.exit_code == 0


def test_completion_fish():
    result = _invoke("--completion", "fish")
    assert result.exit_code == 0


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


def test_update_check_runs_by_default(monkeypatch):
    called = {"n": 0}

    def counting_check(**kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(cli_mod, "check_for_update", counting_check)
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "status",
        lambda self: {
            "mode": "NORMAL",
            "nodeDescription": "master",
            "numExecutors": 2,
            "jobs": [],
        },
    )
    _invoke("--no-colour", "status")
    assert called["n"] == 1


def test_invalid_config_exits_with_error(tmp_path):
    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("not = [valid toml")
    result = _invoke("--config", str(bad_cfg))
    assert result.exit_code == 1


# ── status ───────────────────────────────────────────────────────────────────


def test_status_shows_butler_greeting(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "status",
        lambda self: {
            "mode": "NORMAL",
            "nodeDescription": "master",
            "numExecutors": 2,
            "jobs": [],
        },
    )
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 0
    assert "Certainly" in result.output or "fine form" in result.output


def test_status_connection_error_shows_butler_error(monkeypatch):
    def _raise(self):
        raise JenkinsError("Cannot reach Jenkins at http://jenkins.example.com")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "unreachable" in result.output


def test_error_403_shows_credentials_message(monkeypatch):
    def _raise(self):
        raise JenkinsError("Jenkins returned 403")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "403" in result.output
    assert "credentials" in result.output


def test_error_404_shows_not_found_message(monkeypatch):
    def _raise(self):
        raise JenkinsError("Jenkins returned 404")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "404" in result.output


def test_error_generic_shows_bother_message(monkeypatch):
    def _raise(self):
        raise JenkinsError("something went wrong")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 1
    assert "bother" in result.output


# ── browser-login redirect handling ──────────────────────────────────────────


def test_login_required_non_interactive_prints_url(monkeypatch):
    def _raise(self):
        raise jenkins_mod.JenkinsLoginRequired(
            "Jenkins requires browser login at http://jenkins.example.com"
        )

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
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


def test_login_required_interactive_opens_browser(monkeypatch):
    def _raise(self):
        raise jenkins_mod.JenkinsLoginRequired(
            "Jenkins requires browser login at http://jenkins.example.com"
        )

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "status", _raise)
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


def test_jobs_shows_roster(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [{"name": "deploy-prod", "color": "blue"}],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "deploy-prod" in result.output
    assert "roster" in result.output


# ── output formats (--format) ─────────────────────────────────────────────────


def _jobs_mock(monkeypatch, jobs):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "jobs", lambda self, folder=None, depth=0: jobs
    )


def test_jobs_format_json(monkeypatch):
    _jobs_mock(
        monkeypatch,
        [
            {
                "name": "deploy",
                "color": "blue",
                "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
                "healthReport": [{"score": 90}],
            }
        ],
    )
    result = _invoke("--no-update-check", "--format", "json", "jobs")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["name"] == "deploy"
    assert data[0]["type"] == "pipeline"
    assert data[0]["status"] == "passed"
    assert data[0]["health"] == 90
    # no decorative header on stdout in json mode
    assert "roster" not in result.stdout


def test_jobs_format_ndjson_one_per_line(monkeypatch):
    _jobs_mock(
        monkeypatch,
        [{"name": "a", "color": "blue"}, {"name": "b", "color": "red"}],
    )
    result = _invoke("--no-update-check", "--format", "ndjson", "jobs", "--no-weather")
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert _json.loads(lines[0])["name"] == "a"


def test_jobs_format_csv(monkeypatch):
    _jobs_mock(monkeypatch, [{"name": "deploy", "color": "blue"}])
    result = _invoke("--no-update-check", "--format", "csv", "jobs", "--no-weather")
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0] == "Job,Type,Status"
    assert lines[1].startswith("deploy,job,passed")


def test_jobs_format_markdown(monkeypatch):
    _jobs_mock(monkeypatch, [{"name": "deploy", "color": "blue"}])
    result = _invoke(
        "--no-update-check", "--format", "markdown", "jobs", "--no-weather"
    )
    assert result.exit_code == 0
    assert "|" in result.stdout
    assert "passed" in result.stdout


def test_jobs_format_template(monkeypatch):
    _jobs_mock(monkeypatch, [{"name": "deploy", "color": "blue"}])
    result = _invoke(
        "--no-update-check",
        "--format",
        "template",
        "--template",
        "{name}={status}",
        "jobs",
        "--no-weather",
    )
    assert result.exit_code == 0
    assert "deploy=passed" in result.stdout


def test_jobs_format_template_requires_template(monkeypatch):
    _jobs_mock(monkeypatch, [{"name": "deploy", "color": "blue"}])
    result = _invoke("--no-update-check", "--format", "template", "jobs")
    assert result.exit_code == 1
    assert "template" in result.output


def test_jobs_format_tree_expand(monkeypatch):
    def _mock(self, folder=None, depth=0):
        if folder is None:
            return [
                {
                    "name": "platform",
                    "_class": "com.cloudbees.hudson.plugins.folder.Folder",
                }
            ]
        if folder == "platform":
            return [{"name": "api", "color": "blue"}]
        return []

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "jobs", _mock)
    result = _invoke(
        "--no-colour", "--no-update-check", "--format", "tree", "jobs", "--expand"
    )
    assert result.exit_code == 0
    assert "jenkins" in result.stdout
    assert "platform" in result.stdout
    assert "api" in result.stdout
    # tree branch glyphs present
    assert "└──" in result.stdout or "├──" in result.stdout


def test_jobs_format_json_empty_is_array(monkeypatch):
    _jobs_mock(monkeypatch, [])
    result = _invoke("--no-update-check", "--format", "json", "jobs")
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"


def test_nodes_format_json_labels_as_list(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [
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
    result = _invoke("--no-update-check", "--format", "json", "nodes")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["labels"] == ["linux", "docker"]
    assert data[0]["status"] == "online"


def test_queue_format_json_stuck_bool(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "queue",
        lambda self: [{"why": "blocked", "stuck": True, "task": {"name": "deploy"}}],
    )
    result = _invoke("--no-update-check", "--format", "json", "queue")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["name"] == "deploy"
    assert data[0]["stuck"] is True


# ── decoration routing (stdout vs stderr) ─────────────────────────────────────


def test_jobs_header_on_stderr_data_on_stdout(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [{"name": "deploy-prod", "color": "blue"}],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    # decorative butler header goes to stderr only
    assert "roster" in result.stderr
    assert "roster" not in result.stdout
    # data lands on stdout
    assert "deploy-prod" in result.stdout


def test_jobs_empty_state_on_stderr(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "jobs", lambda self, folder=None, depth=0: []
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "bare" in result.stderr
    assert result.stdout.strip() == ""


def test_queue_header_on_stderr_data_on_stdout(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "queue",
        lambda self: [{"why": "waiting", "stuck": False, "task": {"name": "deploy"}}],
    )
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "pending requests" in result.stderr
    assert "pending requests" not in result.stdout
    assert "deploy" in result.stdout


def test_nodes_header_on_stderr_data_on_stdout(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [{"displayName": "agent1", "offline": False, "numExecutors": 2}],
    )
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "household staff" in result.stderr
    assert "household staff" not in result.stdout
    assert "agent1" in result.stdout


def test_status_header_on_stderr_table_on_stdout(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "status",
        lambda self: {
            "mode": "NORMAL",
            "nodeDescription": "master",
            "numExecutors": 2,
            "jobs": [],
        },
    )
    result = _invoke("--no-colour", "--no-update-check", "status")
    assert result.exit_code == 0
    assert "fine form" in result.stderr
    assert "fine form" not in result.stdout
    # the data table stays on stdout
    assert "Mode" in result.stdout


def test_greeting_on_stderr(monkeypatch):
    result = _invoke("--no-colour", "--no-update-check")
    assert result.exit_code == 0
    assert "Good morning" in result.stderr
    assert result.stdout.strip() == ""


def test_jobs_shows_status_labels(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {"name": "a", "color": "blue"},
            {"name": "b", "color": "red"},
            {"name": "c", "color": "yellow"},
            {"name": "d", "color": "grey"},
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "passed" in result.output
    assert "failed" in result.output
    assert "unstable" in result.output
    assert "disabled" in result.output


def test_jobs_shows_folder_icon(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "my-folder",
                "_class": "com.cloudbees.hudson.plugins.folder.Folder",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "my-folder" in result.output
    assert "folder" in result.output


def test_jobs_shows_type_icons(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
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
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "🔧" in result.output
    assert "🔨" in result.output


def test_jobs_type_workflow_job(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "pipe",
                "color": "blue",
                "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "pipeline" in result.output


def test_jobs_type_freestyle_project(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "free",
                "color": "blue",
                "_class": "hudson.model.FreeStyleProject",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "🔧" in result.output
    assert "freestyle" in result.output


def test_jobs_type_matrix_project(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "matrix",
                "color": "blue",
                "_class": "hudson.matrix.MatrixProject",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "🔢" in result.output
    assert "matrix" in result.output


def test_jobs_type_unknown_fallback(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "mystery",
                "color": "blue",
                "_class": "com.example.SomeUnknownJobType",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "🔨" in result.output
    assert "job" in result.output


def test_jobs_type_folder_icon(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
            {
                "name": "my-folder",
                "_class": "com.cloudbees.hudson.plugins.folder.Folder",
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "📁" in result.output
    assert "folder" in result.output


def test_jobs_type_key_flag(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--type-key")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "🔧" in result.output
    assert "🔢" in result.output
    assert "🔨" in result.output
    assert "📁" in result.output
    assert "pipeline" in result.output


def test_swatch_shows_iconography(monkeypatch):
    result = _invoke("--no-colour", "--no-update-check", "swatch")
    assert result.exit_code == 0
    assert "🔁" in result.output
    assert "🔧" in result.output
    assert "☀️" in result.output
    assert "⛈️" in result.output


def test_jobs_expand_recurses_into_folders(monkeypatch):
    def _mock_jobs(self, folder=None, depth=0):
        if folder is None:
            return [
                {
                    "name": "my-folder",
                    "_class": "com.cloudbees.hudson.plugins.folder.Folder",
                }
            ]
        if folder == "my-folder":
            return [
                {
                    "name": "child-job",
                    "color": "blue",
                    "_class": "org.jenkinsci.plugins.workflow.job.WorkflowJob",
                }
            ]
        return []

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "jobs", _mock_jobs)
    result = _invoke(
        "--no-colour", "--no-update-check", "jobs", "--expand", "--no-weather"
    )
    assert result.exit_code == 0
    assert "my-folder" in result.output
    assert "my-folder/child-job" in result.output


def test_jobs_shows_weather_column(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [
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
    result = _invoke("--no-colour", "--no-update-check", "jobs")
    assert result.exit_code == 0
    assert "Weather" in result.output
    assert "sunny" in result.output
    assert "stormy" in result.output
    assert "—" in result.output


def test_jobs_no_weather_skips_column(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [{"name": "x", "color": "blue"}],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "Weather" not in result.output


def test_jobs_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "jobs", lambda self, folder=None, depth=0: []
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs")
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


def test_jobs_hyperlinks_job_url(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [{"name": "deploy-prod", "color": "blue"}],
    )
    result = _invoke(
        "--no-update-check",
        "jobs",
        "--url",
        "http://jenkins.example.com",
        "--no-weather",
        color=True,
    )
    assert result.exit_code == 0
    assert "http://jenkins.example.com" in result.output
    assert "deploy-prod" in result.output


def test_jobs_no_colour_no_hyperlinks(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "jobs",
        lambda self, folder=None, depth=0: [{"name": "deploy-prod", "color": "blue"}],
    )
    result = _invoke("--no-colour", "--no-update-check", "jobs", "--no-weather")
    assert result.exit_code == 0
    assert "\x1b]8;;" not in result.output


def test_queue_hyperlinks_task_url(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "queue",
        lambda self: [
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


def test_nodes_hyperlinks_node_url(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [{"displayName": "agent1", "offline": False, "numExecutors": 2}],
    )
    result = _invoke(
        "--no-update-check",
        "nodes",
        "--url",
        "http://jenkins.example.com",
        color=True,
    )
    assert result.exit_code == 0
    assert "http://jenkins.example.com/computer/agent1/" in result.output


# ── build ─────────────────────────────────────────────────────────────────────


def test_build_success_shows_dispatch_message(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "build", lambda self, job, params=None: None
    )
    result = _invoke("--no-colour", "--no-update-check", "build", "my-pipeline")
    assert result.exit_code == 0
    assert (
        "dispatch" in result.output
        or "forthwith" in result.output
        or "at once" in result.output
    )


def test_build_bad_param_format(monkeypatch):
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "build",
        "my-pipeline",
        "--param",
        "no-equals-sign",
    )
    assert result.exit_code == 1


# ── builds ────────────────────────────────────────────────────────────────────


def _build_info_mock(monkeypatch, mapping):
    def _info(self, job, build="lastBuild"):
        return mapping.get(build)

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "build_info", _info)


def _builds_list_mock(monkeypatch, builds):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "builds", lambda self, job, limit=20: builds[:limit]
    )


def test_builds_summary_table(monkeypatch):
    _build_info_mock(
        monkeypatch,
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
    result = _invoke("--no-colour", "--no-update-check", "builds", "summary", "deploy")
    assert result.exit_code == 0
    assert "#142" in result.stdout
    assert "Success" in result.stdout
    # the absent lastFailedBuild renders a dash
    assert "—" in result.stdout
    # header is decoration -> stderr
    assert "build record" in result.stderr


def test_builds_summary_json(monkeypatch):
    _build_info_mock(
        monkeypatch,
        {
            "lastBuild": {"number": 9, "result": "FAILURE", "building": False},
            "lastSuccessfulBuild": None,
            "lastFailedBuild": {"number": 9, "result": "FAILURE", "building": False},
        },
    )
    result = _invoke(
        "--no-update-check", "--format", "json", "builds", "summary", "deploy"
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    by_permalink = {r["permalink"]: r for r in data}
    assert by_permalink["last"]["number"] == 9
    assert by_permalink["last"]["result"] == "FAILURE"
    assert by_permalink["successful"]["number"] is None


def test_builds_summary_none_shows_empty_state(monkeypatch):
    _build_info_mock(
        monkeypatch,
        {"lastBuild": None, "lastSuccessfulBuild": None, "lastFailedBuild": None},
    )
    result = _invoke("--no-colour", "--no-update-check", "builds", "summary", "deploy")
    assert result.exit_code == 0
    assert "no builds on record" in result.stderr
    assert result.stdout.strip() == ""


def test_builds_list_table(monkeypatch):
    _builds_list_mock(
        monkeypatch,
        [
            {"number": 142, "result": "SUCCESS", "building": False},
            {"number": 141, "result": "FAILURE", "building": False},
            {"number": 140, "result": "SUCCESS", "building": False},
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "builds", "list", "deploy")
    assert result.exit_code == 0
    assert "#142" in result.stdout
    assert "#141" in result.stdout
    assert "#140" in result.stdout
    # no Permalink column in list view
    assert "Permalink" not in result.stdout


def test_builds_list_result_filter(monkeypatch):
    _builds_list_mock(
        monkeypatch,
        [
            {"number": 142, "result": "SUCCESS", "building": False},
            {"number": 141, "result": "FAILURE", "building": False},
        ],
    )
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "builds",
        "list",
        "deploy",
        "--result",
        "failure",
    )
    assert result.exit_code == 0
    assert "#141" in result.stdout
    assert "#142" not in result.stdout


def test_builds_list_passes_limit(monkeypatch):
    captured = {}

    def _builds(self, job, limit=20):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "builds", _builds)
    result = _invoke("--no-update-check", "builds", "list", "deploy", "--limit", "5")
    assert result.exit_code == 0
    assert captured["limit"] == 5


def test_builds_show_single(monkeypatch):
    _build_info_mock(
        monkeypatch,
        {"7": {"number": 7, "result": "SUCCESS", "building": False}},
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "builds", "show", "deploy", "7"
    )
    assert result.exit_code == 0
    assert "#7" in result.stdout


def test_builds_show_missing(monkeypatch):
    _build_info_mock(monkeypatch, {})
    result = _invoke(
        "--no-colour", "--no-update-check", "builds", "show", "deploy", "999"
    )
    assert result.exit_code == 0
    assert "could find no build" in result.stderr


def test_builds_show_exposes_params_and_causes_table(monkeypatch):
    _build_info_mock(
        monkeypatch,
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
    result = _invoke(
        "--no-colour", "--no-update-check", "builds", "show", "deploy", "7"
    )
    assert result.exit_code == 0
    assert "CHANGE_ID=12345" in result.stdout
    assert "WAVE=2" in result.stdout
    assert "Started by user bob" in result.stdout


def test_builds_show_exposes_params_and_causes_json(monkeypatch):
    _build_info_mock(
        monkeypatch,
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
        "--no-update-check", "--format", "json", "builds", "show", "deploy", "7"
    )
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["params"] == {"CHANGE_ID": "12345"}
    assert data[0]["causes"][0]["upstreamProject"] == "foo"
    assert data[0]["causes"][0]["upstreamBuild"] == 3


def test_builds_list_param_filter(monkeypatch):
    _builds_list_mock(
        monkeypatch,
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
        "builds",
        "list",
        "deploy",
        "--param",
        "CHANGE_ID=abc",
    )
    assert result.exit_code == 0
    assert "#142" in result.stdout
    assert "#141" not in result.stdout


def test_builds_list_param_filter_bad_format(monkeypatch):
    _builds_list_mock(monkeypatch, [])
    result = _invoke(
        "--no-colour",
        "--no-update-check",
        "builds",
        "list",
        "deploy",
        "--param",
        "not-a-kv",
    )
    assert result.exit_code == 1
    assert "KEY=VALUE" in result.stderr


# ── params ────────────────────────────────────────────────────────────────────


def _job_detail_mock(monkeypatch, job_json):
    monkeypatch.setattr(jenkins_mod.JenkinsClient, "job", lambda self, job: job_json)


def test_params_table(monkeypatch):
    _job_detail_mock(
        monkeypatch,
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
    result = _invoke("--no-colour", "--no-update-check", "params", "deploy")
    assert result.exit_code == 0
    assert "BRANCH" in result.stdout
    assert "string" in result.stdout
    assert "choice" in result.stdout
    assert "dev, prod" in result.stdout


def test_params_json_types(monkeypatch):
    _job_detail_mock(
        monkeypatch,
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
    result = _invoke("--no-update-check", "--format", "json", "params", "deploy")
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data[0]["name"] == "DEBUG"
    assert data[0]["type"] == "boolean"
    assert data[0]["default"] is False


def test_params_unparameterised_empty_state(monkeypatch):
    _job_detail_mock(monkeypatch, {"property": []})
    result = _invoke("--no-colour", "--no-update-check", "params", "deploy")
    assert result.exit_code == 0
    assert "no special instructions" in result.stderr
    assert result.stdout.strip() == ""


# ── rebuild ───────────────────────────────────────────────────────────────────


def _rebuild_mocks(monkeypatch, info):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "build_info",
        lambda self, job, build="lastBuild": info,
    )
    captured = {}
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "build",
        lambda self, job, params=None: captured.update(job=job, params=params),
    )
    return captured


def test_rebuild_carries_previous_params(monkeypatch):
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
    captured = _rebuild_mocks(monkeypatch, info)
    result = _invoke("--no-colour", "--no-update-check", "rebuild", "deploy")
    assert result.exit_code == 0
    assert captured["params"] == {"BRANCH": "main", "DEBUG": "false"}


def test_rebuild_override_wins(monkeypatch):
    info = {
        "actions": [
            {
                "_class": "hudson.model.ParametersAction",
                "parameters": [{"name": "BRANCH", "value": "main"}],
            }
        ]
    }
    captured = _rebuild_mocks(monkeypatch, info)
    result = _invoke(
        "--no-colour", "--no-update-check", "rebuild", "deploy", "--param", "BRANCH=dev"
    )
    assert result.exit_code == 0
    assert captured["params"] == {"BRANCH": "dev"}


def test_rebuild_no_params_plain(monkeypatch):
    captured = _rebuild_mocks(monkeypatch, {"actions": []})
    result = _invoke("--no-colour", "--no-update-check", "rebuild", "deploy")
    assert result.exit_code == 0
    assert captured["params"] is None


def test_rebuild_missing_build_errors(monkeypatch):
    _rebuild_mocks(monkeypatch, None)
    result = _invoke("--no-colour", "--no-update-check", "rebuild", "deploy")
    assert result.exit_code == 1
    assert "no build on record" in result.output


# ── queue ─────────────────────────────────────────────────────────────────────


def test_queue_shows_items(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "queue",
        lambda self: [{"why": "waiting", "stuck": False, "task": {"name": "deploy"}}],
    )
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "waiting" in result.output or "pending" in result.output


def test_queue_shows_stuck_label(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "queue",
        lambda self: [{"why": "blocked", "stuck": True, "task": {"name": "deploy"}}],
    )
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "yes" in result.output


def test_queue_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(jenkins_mod.JenkinsClient, "queue", lambda self: [])
    result = _invoke("--no-colour", "--no-update-check", "queue")
    assert result.exit_code == 0
    assert "empty" in result.output or "leisure" in result.output
    assert "😴 The queue" in result.output


# ── cancel ────────────────────────────────────────────────────────────────────


def test_cancel_shows_dismissed_message(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient, "cancel", lambda self, job, build: None
    )
    result = _invoke(
        "--no-colour", "--no-update-check", "cancel", "my-pipeline", "--build", "5"
    )
    assert result.exit_code == 0
    assert "dismissed" in result.output


# ── nodes ─────────────────────────────────────────────────────────────────────


def test_nodes_shows_household_staff(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [{"displayName": "agent1", "offline": False, "numExecutors": 2}],
    )
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "agent1" in result.output
    assert "household" in result.output


def test_nodes_shows_online_offline_labels(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [
            {"displayName": "up", "offline": False, "numExecutors": 2},
            {"displayName": "down", "offline": True, "numExecutors": 0},
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "online" in result.output
    assert "offline" in result.output


def test_nodes_empty_shows_butler_message(monkeypatch):
    monkeypatch.setattr(jenkins_mod.JenkinsClient, "nodes", lambda self: [])
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "absented" in result.output or "notice" in result.output
    assert "🚪 The household" in result.output


def test_nodes_shows_labels(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [
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
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "Labels" in result.output
    assert "linux" in result.output
    assert "docker" in result.output


def test_nodes_filters_own_name_from_labels(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [
            {
                "displayName": "build-node",
                "offline": False,
                "numExecutors": 2,
                "assignedLabels": [{"name": "build-node"}, {"name": "java"}],
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "java" in result.output
    # node name appears once (Node column) but not again in Labels column
    assert result.output.count("build-node") == 1


def test_nodes_empty_labels_renders_blank(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "nodes",
        lambda self: [
            {
                "displayName": "agent-1",
                "offline": False,
                "numExecutors": 2,
                "assignedLabels": [{"name": "agent-1"}],
            }
        ],
    )
    result = _invoke("--no-colour", "--no-update-check", "nodes")
    assert result.exit_code == 0
    assert "Labels" in result.output


# ── whoami ────────────────────────────────────────────────────────────────────


def test_whoami_authenticated(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "whoami",
        lambda self: {"id": "alice", "fullName": "Alice Smith"},
    )
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 0
    assert "alice" in result.output
    assert "Alice Smith" in result.output


def test_whoami_anonymous(monkeypatch):
    monkeypatch.setattr(
        jenkins_mod.JenkinsClient,
        "whoami",
        lambda self: {"id": "anonymous", "fullName": "anonymous"},
    )
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 0
    assert "anonymous" in result.output


def test_whoami_error_shows_butler_message(monkeypatch):
    def _raise(self):
        raise JenkinsError("Cannot reach Jenkins at http://jenkins.example.com")

    monkeypatch.setattr(jenkins_mod.JenkinsClient, "whoami", _raise)
    result = _invoke("--no-colour", "--no-update-check", "whoami")
    assert result.exit_code == 1
    assert "unreachable" in result.output
