"""jeeves — a Jenkins CI/CD butler.

Good morning. I shall attend to your Jenkins affairs with the
utmost discretion and efficiency.
"""

from __future__ import annotations

import functools
import random
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from xml.etree import ElementTree

import click
from tabulate import tabulate

from . import render as _render
from .config import get_jenkins_config, load_config, show_config, write_default_config
from .jenkins import JenkinsClient, JenkinsError, _normalize_jenkins_path
from .logger import configure as configure_logging
from .render import Column
from .ui import THEME_NAMES, apply_seasonal_colour, colour_grade_number, get_theme
from .updater import check_for_update

_ENVVAR_PREFIX = "JEEVES"
_BUTLER_ITEMS = ["🎩", "🥂", "🤵", "📋", "🫗"]


@dataclass
class _Ctx:
    cfg: dict = field(default_factory=dict)
    colour: bool = True
    theme: object = None
    no_update_check: bool = False
    seasonal_colours: bool = True
    seasonal_calendar: str = "western"
    fmt: str = "table"
    template: str | None = None
    url: str | None = None
    user: str | None = None
    token: str | None = None


# Hands each subcommand the group's resolved _Ctx (see ctx.obj in main()).
pass_ctx = click.make_pass_decorator(_Ctx)


def _isatty() -> bool:
    """Whether stdout is an interactive terminal (seam for testing)."""
    return sys.stdout.isatty()


def _butler_error(msg: str, colour: bool) -> None:
    if "requires browser login at" in msg:
        url = msg.split("requires browser login at ", 1)[-1].strip()
        text = (
            "It appears the Jenkins estate requires you to sign in through your "
            "browser first, sir — your API token alone will not open the door. "
        )
        opened = False
        if _isatty():
            try:
                opened = webbrowser.open(url)
            except webbrowser.Error:
                opened = False
        if opened:
            text += f"I've opened {url} for you; do log in and try again."
        else:
            text += f"Kindly visit {url}, log in, and try again."
    elif "Cannot reach Jenkins at" in msg:
        url = msg.split("Cannot reach Jenkins at ", 1)[-1].strip()
        text = (
            f"I'm afraid the Jenkins estate at {url} appears to be quite unreachable, "
            "sir. The line seems entirely dead."
        )
    elif "Jenkins returned 403" in msg:
        text = (
            "Jenkins has turned us away at the door, sir. A 403 — most irregular. "
            "One suspects our credentials may not be in order."
        )
    elif "Jenkins returned 404" in msg:
        text = (
            "I searched the premises most thoroughly, sir, but the requested resource "
            "could not be found. A 404. It has vanished like Bertie's good intentions."
        )
    elif "Jenkins returned" in msg:
        code = msg.split("Jenkins returned ", 1)[-1].strip()
        text = (
            f"Jenkins appears to be in a considerable state of disarray, sir. "
            f"A {code}. Perhaps a restorative cup of tea is called for."
        )
    else:
        text = f"I'm afraid there's been a spot of bother, sir: {msg}"
    click.echo(
        click.style(f"🎩 {text}", fg="red"),
        err=True,
        color=colour,
    )


def _make_client(ctx: _Ctx) -> JenkinsClient:
    cfg_url, cfg_user, cfg_token = get_jenkins_config(ctx.cfg)
    return JenkinsClient(
        ctx.url or cfg_url, ctx.user or cfg_user, ctx.token or cfg_token
    )


# ── Group ────────────────────────────────────────────────────────────────────


@click.group(
    epilog=(
        "Made with ❤️ in the UK using the five-clis framework "
        "— https://github.com/mrsixw/five-clis"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.version_option(package_name="jeeves", prog_name="jeeves")
# ── Connection ─────────────────────────────────────────────────────────────
@click.option(
    "--url",
    default=None,
    metavar="URL",
    envvar="JEEVES_URL",
    help="Jenkins server URL (overrides config).",
)
@click.option(
    "--user",
    default=None,
    metavar="USER",
    envvar="JEEVES_USER",
    help="Jenkins username (overrides config).",
)
@click.option(
    "--token",
    default=None,
    metavar="TOKEN",
    envvar="JEEVES_TOKEN",
    help="Jenkins API token (overrides config).",
)
# ── Shell completions ──────────────────────────────────────────────────────
@click.option(
    "--completion",
    "completion_shell",
    type=click.Choice(["bash", "zsh", "fish"]),
    default=None,
    is_eager=True,
    expose_value=True,
    help="Print shell completion script for SHELL and exit. Eval in your shell config.",
)
# ── Config ─────────────────────────────────────────────────────────────────
@click.option(
    "--config",
    "config_path",
    default=None,
    metavar="PATH",
    help="Path to a TOML config file.",
)
@click.option(
    "--show-config",
    "do_show_config",
    is_flag=True,
    default=False,
    help="Print resolved config and exit.",
)
@click.option(
    "--init-config",
    "do_init_config",
    is_flag=True,
    default=False,
    help="Write a default config file and exit.",
)
# ── Display ─────────────────────────────────────────────────────────────────
@click.option(
    "--theme",
    type=click.Choice(THEME_NAMES, case_sensitive=False),
    default=None,
    help=f"Colour theme. Choices: {', '.join(THEME_NAMES)}.",
)
@click.option(
    "--seasonal-colours/--no-seasonal-colours",
    default=None,
    help="Apply seasonal ANSI colours based on the current date.",
)
@click.option(
    "--seasonal-calendar",
    type=click.Choice(
        ["western", "jewish", "islamic", "hindu", "sikh", "east-asian"],
        case_sensitive=False,
    ),
    default=None,
    help="Which cultural calendar drives seasonal colours (default: western).",
)
@click.option(
    "--no-colour",
    "no_colour",
    is_flag=True,
    default=False,
    envvar=f"{_ENVVAR_PREFIX}_NO_COLOUR",
    help="Disable all ANSI colour output.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(_render.FORMATS, case_sensitive=False),
    default=None,
    help="Output format for table commands (default: table).",
)
@click.option(
    "--template",
    "output_template",
    default=None,
    metavar="STR",
    help='Row template for --format template, e.g. "{name}: {status}".',
)
# ── Caching ─────────────────────────────────────────────────────────────────
@click.option(
    "--cache/--no-cache",
    default=None,
    help="Enable disk caching of results (off by default).",
)
@click.option(
    "--cache-ttl",
    default=None,
    metavar="TTL",
    help="Cache TTL: seconds (300), or suffixed (5m, 2h). Default: 300.",
)
# ── Updates ─────────────────────────────────────────────────────────────────
@click.option(
    "--no-update-check",
    is_flag=True,
    default=False,
    envvar=f"{_ENVVAR_PREFIX}_NO_UPDATE_CHECK",
    help="Disable the automatic update check.",
)
@click.pass_context
def main(
    ctx,
    url,
    user,
    token,
    completion_shell,
    config_path,
    do_show_config,
    do_init_config,
    theme,
    seasonal_colours,
    seasonal_calendar,
    no_colour,
    output_format,
    output_template,
    cache,
    cache_ttl,
    no_update_check,
):
    """🎩 jeeves — your Jenkins CI/CD butler.

    Good morning. How may Jeeves be of assistance?
    """
    configure_logging()
    colour = not no_colour

    # ── Shell completion ────────────────────────────────────────────────────
    if completion_shell:
        from click.shell_completion import get_completion_class

        comp_cls = get_completion_class(completion_shell)
        comp = comp_cls(
            cli=main,
            ctx_args={},
            prog_name="jeeves",
            complete_var="_JEEVES_COMPLETE",
        )
        click.echo(comp.source(), nl=False)
        sys.exit(0)

    # ── Config resolution ──────────────────────────────────────────────────
    try:
        cfg = load_config(config_path)
    except ValueError as exc:
        click.echo(click.style(str(exc), fg="red"), err=True, color=colour)
        sys.exit(1)

    if do_init_config:
        path = write_default_config()
        click.echo(f"Very good. Default config written to: {path}")
        sys.exit(0)

    if do_show_config:
        click.echo(show_config(cfg, config_path))
        sys.exit(0)

    # ── Resolve display options ────────────────────────────────────────────
    theme_name = theme if theme is not None else cfg.get("theme", "default")
    seasonal_colours = (
        seasonal_colours
        if seasonal_colours is not None
        else cfg.get("seasonal-colours", True)
    )
    seasonal_calendar = (
        seasonal_calendar
        if seasonal_calendar is not None
        else cfg.get("seasonal-calendar", "western")
    )
    no_update_check = no_update_check or cfg.get("no-update-check", False)
    output_format = (
        output_format if output_format is not None else cfg.get("format", "table")
    ).lower()

    active_theme = get_theme(theme_name)

    ctx.obj = _Ctx(
        cfg=cfg,
        colour=colour,
        theme=active_theme,
        no_update_check=no_update_check,
        seasonal_colours=seasonal_colours if seasonal_colours is not None else True,
        seasonal_calendar=seasonal_calendar or "western",
        fmt=output_format,
        template=output_template,
        url=url,
        user=user,
        token=token,
    )
    ctx.ensure_object(_Ctx)

    # ── Bare invocation: greet the user ───────────────────────────────────
    if ctx.invoked_subcommand is None:
        spinner = random.choice(_BUTLER_ITEMS)
        greeting = (
            f"{spinner} Good morning. " "How may Jeeves be of assistance? Try --help."
        )
        if seasonal_colours and not no_colour:
            greeting = apply_seasonal_colour(greeting, 0, calendar=seasonal_calendar)
        elif not no_colour:
            greeting = active_theme.apply(greeting, role="primary")
        click.echo(greeting, err=True, color=colour)
        return

    # ── Update check (runs after the subcommand via close callback) ────────
    if not no_update_check:

        def _check() -> None:
            msg = check_for_update()
            if msg:
                click.echo(
                    click.style(msg, fg="cyan", bold=True), err=True, color=colour
                )

        ctx.call_on_close(_check)


# ── status ──────────────────────────────────────────────────────────────────


@main.command()
@pass_ctx
def status(ctx: _Ctx) -> None:
    """Check Jenkins server health."""
    client = _make_client(ctx)
    try:
        data = client.status()
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    desc = data.get("nodeDescription", "Jenkins")
    mode = data.get("mode", "unknown")
    executors = data.get("numExecutors", "?")
    jobs_count = len(data.get("jobs", []))

    click.echo(
        click.style(f"✅ Certainly. {desc} is in fine form.", fg="green"),
        err=True,
        color=ctx.colour,
    )
    mode_str = (
        click.style(mode, fg="green", bold=True)
        if ctx.colour and mode.upper() == "NORMAL"
        else click.style(mode, fg="yellow", bold=True) if ctx.colour else mode
    )
    exec_cell = (
        colour_grade_number(executors)
        if ctx.colour and isinstance(executors, int)
        else executors
    )
    rows = [
        ["Mode", mode_str],
        ["Executors", exec_cell],
        ["Jobs", colour_grade_number(jobs_count) if ctx.colour else jobs_count],
    ]
    click.echo(tabulate(rows, tablefmt="simple"), color=ctx.colour)


# ── noun groups (job / build / node) ─────────────────────────────────────────


class _BuildGroup(click.Group):
    """`build` is a noun group, but the legacy verb `jeeves build JOB
    [--param K=V]` still works: an unknown first token falls back to the
    hidden deprecated trigger command; real subcommands take priority."""

    def resolve_command(self, ctx, args):
        if (
            args
            and not args[0].startswith("-")
            and self.get_command(ctx, args[0]) is None
        ):
            # Return full `args` (not args[1:]) so the token becomes JOB.
            return _LEGACY_BUILD_VERB.name, _LEGACY_BUILD_VERB, args
        return super().resolve_command(ctx, args)


@main.group()
def job() -> None:
    """Work with Jenkins jobs: list, parameters, trigger."""


@main.group(cls=_BuildGroup)
def build() -> None:
    """Inspect and manage a job's builds."""


@main.group("node")
def node_group() -> None:
    """Work with Jenkins build nodes (agents)."""


# ── job list ─────────────────────────────────────────────────────────────────

# (colour, label, emoji)
_JOB_COLOUR_MAP: dict[str, tuple[str, str, str]] = {
    "blue": ("green", "passed", "✅"),
    "blue_anime": ("green", "running", "▶️"),
    "red": ("red", "failed", "❌"),
    "red_anime": ("red", "running", "▶️"),
    "yellow": ("yellow", "unstable", "⚠️"),
    "yellow_anime": ("yellow", "running", "▶️"),
    "grey": ("white", "disabled", "⏸️"),
    "notbuilt": ("white", "not built", "🔘"),
    "aborted": ("white", "aborted", "🚫"),
    "aborted_anime": ("white", "running", "▶️"),
}

_FOLDER_CLASS_FRAGMENTS = ("Folder", "MultiBranch", "OrganizationFolder")

# (class fragment, icon, label) — first match wins
_JOB_TYPE_MAP: list[tuple[str, str, str]] = [
    ("WorkflowJob", "🔁", "pipeline"),
    ("FreeStyleProject", "🔧", "freestyle"),
    ("MatrixProject", "🔢", "matrix"),
]
_JOB_TYPE_FALLBACK = ("🔨", "job")

_OSC8_OPEN = "\x1b]8;;{url}\x1b\\"
_OSC8_CLOSE = "\x1b]8;;\x1b\\"


def _hyperlink(text: str, url: str, colour: bool) -> str:
    """Wrap text in an OSC 8 terminal hyperlink when colour output is active."""
    if not colour:
        return text
    return f"{_OSC8_OPEN.format(url=url)}{text}{_OSC8_CLOSE}"


_WEATHER_MAP: list[tuple[int, str, str, str]] = [
    (80, "green", "☀️", "sunny"),
    (60, "yellow", "🌤️", "fair"),
    (40, "yellow", "☁️", "cloudy"),
    (20, 208, "🌧️", "rainy"),
    (0, "red", "⛈️", "stormy"),
]


def _is_folder(job: dict) -> bool:
    cls = job.get("_class", "")
    return any(f in cls for f in _FOLDER_CLASS_FRAGMENTS)


_ICON_BY_LABEL = {label: icon for _, icon, label in _JOB_TYPE_MAP}
_ICON_BY_LABEL[_JOB_TYPE_FALLBACK[1]] = _JOB_TYPE_FALLBACK[0]


def _job_type_label(job: dict) -> str:
    """Semantic job-type label (e.g. 'pipeline') derived from the `_class`."""
    cls = job.get("_class", "")
    for fragment, _icon, label in _JOB_TYPE_MAP:
        if fragment in cls:
            return label
    return _JOB_TYPE_FALLBACK[1]


def _type_table_cell(label: str, colour: bool) -> str:
    """Decorated Type cell (icon + label) for table output."""
    if label == "folder":
        return click.style("📁 folder", fg="cyan") if colour else "📁 folder"
    icon = _ICON_BY_LABEL.get(label, _JOB_TYPE_FALLBACK[0])
    return f"{icon} {label}"


def _render_type_key() -> str:
    lines = [click.style("🗝️ Job type reference", fg="cyan", bold=True), ""]
    entries = (
        [
            ("📁 folder", "Jenkins folder or multi-branch project"),
        ]
        + [
            (f"{icon} {label}", f"Jenkins {label} job")
            for _, icon, label in _JOB_TYPE_MAP
        ]
        + [
            (
                f"{_JOB_TYPE_FALLBACK[0]} {_JOB_TYPE_FALLBACK[1]}",
                "Other / unrecognised",
            ),
        ]
    )
    width = max(len(e) for e, _ in entries)
    for entry, desc in entries:
        lines.append(f"  {entry:<{width}}  {desc}")
    return "\n".join(lines)


def _format_job_status(raw: str, colour: bool) -> str:
    fg, label, emoji = _JOB_COLOUR_MAP.get(raw, ("white", raw, "❓"))
    text = f"{emoji} {label}"
    return click.style(text, fg=fg, bold=True) if colour else text


def _format_weather(score: int | None, colour: bool) -> str:
    if score is None:
        return "—"
    for threshold, fg, emoji, label in _WEATHER_MAP:
        if score >= threshold:
            text = f"{emoji} {label}"
            return click.style(text, fg=fg, bold=True) if colour else text
    return "—"


def _weather_word(score: int | None) -> str | None:
    """Semantic weather label (e.g. 'sunny') for a health score, or None."""
    if score is None:
        return None
    for threshold, _fg, _emoji, label in _WEATHER_MAP:
        if score >= threshold:
            return label
    return None


# ── build result / time helpers ──────────────────────────────────────────────

# Jenkins build results (distinct vocabulary from job colours): (colour, emoji).
_BUILD_RESULT_MAP: dict[str, tuple[str, str]] = {
    "SUCCESS": ("green", "✅"),
    "FAILURE": ("red", "❌"),
    "UNSTABLE": ("yellow", "⚠️"),
    "ABORTED": ("white", "🚫"),
    "NOT_BUILT": ("white", "🔘"),
}


def _format_build_result(result: str | None, building: bool, colour: bool) -> str:
    """Decorated build-result cell (emoji + word) for table output."""
    if building:
        text = "▶️ building"
        return click.style(text, fg="cyan", bold=True) if colour else text
    if result is None:
        return "—"
    fg, emoji = _BUILD_RESULT_MAP.get(result, ("white", "❓"))
    text = f"{emoji} {result.title()}"
    return click.style(text, fg=fg, bold=True) if colour else text


def _build_result_word(result: str | None, building: bool) -> str:
    """Semantic build-result string for structured output."""
    if building:
        return "BUILDING"
    return result or ""


def _relative_time(ts_ms: int | None) -> str:
    """Human 'time ago' for an epoch-millis timestamp (e.g. '2h ago')."""
    if not ts_ms:
        return "—"
    delta = int(time.time()) - int(ts_ms) // 1000
    if delta < 0:
        delta = 0
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _format_duration(ms: int | None) -> str:
    """Human duration for a millisecond span (e.g. '3m12s', '45s')."""
    if not ms:
        return "—"
    seconds = int(ms) // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h{mins:02d}m"


def _format_bytes(num: int | None) -> str:
    """Human byte size (e.g. '12.3 GB'), or '—' when unknown."""
    if num is None:
        return "—"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _node_monitor(monitor_data: dict, name: str) -> dict | str | None:
    """Read one monitor's value from a node's monitorData (None if absent/null)."""
    return monitor_data.get(f"hudson.node_monitors.{name}")


def _node_stat_fields(monitor_data: dict) -> dict:
    """Parse a node's monitorData into flat semantic stat fields."""

    def _size(name: str, key: str) -> int | None:
        value = _node_monitor(monitor_data, name)
        return value.get(key) if isinstance(value, dict) else None

    arch = _node_monitor(monitor_data, "ArchitectureMonitor")
    return {
        "disk": _size("DiskSpaceMonitor", "size"),
        "temp": _size("TemporarySpaceMonitor", "size"),
        "swap": _size("SwapSpaceMonitor", "availableSwapSpace"),
        "response_ms": _size("ResponseTimeMonitor", "average"),
        "clock_ms": _size("ClockMonitor", "diff"),
        "architecture": arch if isinstance(arch, str) else None,
    }


def _node_host_from_config(config_xml: str) -> str | None:
    """Extract the launcher host (IP or hostname) from a node's config.xml.

    Only launchers that dial out to the agent (e.g. SSH) configure a host;
    inbound (JNLP) agents connect to Jenkins themselves, so there is nothing
    to report and None is returned.
    """
    try:
        root = ElementTree.fromstring(config_xml)
    except ElementTree.ParseError:
        return None
    launcher = root.find("launcher")
    if launcher is None:
        return None
    host = (launcher.findtext(".//host") or "").strip()
    return host or None


def _node_address(client: JenkinsClient, name: str, is_built_in: bool) -> str | None:
    """Resolve a node's address via its config.xml (None when unavailable).

    The built-in node runs inside the controller and has no config.xml.
    Permission errors (config.xml needs Extended Read) degrade to None
    rather than failing the whole listing.
    """
    if is_built_in:
        return "(local)"
    try:
        return _node_host_from_config(client.node_config(name))
    except JenkinsError:
        return None


def _parse_params(raw: tuple[str, ...]) -> dict[str, str]:
    """Parse repeated KEY=VALUE strings into a dict (raises ValueError on a bad one)."""
    parsed: dict[str, str] = {}
    for p in raw:
        if "=" not in p:
            raise ValueError(p)
        key, _, value = p.partition("=")
        parsed[key] = value
    return parsed


def _collect_job_records(
    client: "JenkinsClient",
    job_list: list[dict],
    no_weather: bool,
    expand: bool,
    path_prefix: str,
    base_url: str,
) -> list[dict]:
    """Recursively build semantic job records, expanding folders when asked.

    Each record is the JSON contract for a job:
    ``{name, type, color, status, health, url}``.
    """
    records: list[dict] = []
    for j in job_list:
        name = j.get("name", "?")
        full_path = f"{path_prefix}/{name}" if path_prefix else name
        url = f"{base_url}/{_normalize_jenkins_path(full_path)}"

        if _is_folder(j):
            records.append(
                {
                    "name": full_path,
                    "type": "folder",
                    "color": None,
                    "status": None,
                    "health": None,
                    "url": url,
                }
            )
        else:
            color = j.get("color", "grey")
            status = _JOB_COLOUR_MAP.get(color, ("white", color, "❓"))[1]
            reports = j.get("healthReport") or []
            health = reports[0].get("score") if reports else None
            records.append(
                {
                    "name": full_path,
                    "type": _job_type_label(j),
                    "color": color,
                    "status": status,
                    "health": health,
                    "url": url,
                }
            )

        if expand and _is_folder(j):
            try:
                depth = 0 if no_weather else 1
                child_jobs = client.jobs(folder=full_path, depth=depth)
            except JenkinsError:
                child_jobs = []
            records.extend(
                _collect_job_records(
                    client, child_jobs, no_weather, expand, full_path, base_url
                )
            )

    return records


def _job_columns(ctx: _Ctx, no_weather: bool) -> list[Column]:
    """Column specs for the jobs roster (table cells + plain projections)."""

    def name_table(r: dict, i: int) -> str:
        s = _hyperlink(r["name"], r["url"], ctx.colour)
        if ctx.colour and ctx.seasonal_colours:
            s = apply_seasonal_colour(s, i, calendar=ctx.seasonal_calendar)
        return s

    def status_table(r: dict, _i: int) -> str:
        if r["type"] == "folder":
            return "N/A"
        return _format_job_status(r["color"], ctx.colour)

    def status_plain(r: dict) -> str:
        return "n/a" if r["type"] == "folder" else (r["status"] or "")

    def weather_table(r: dict, _i: int) -> str:
        if r["type"] == "folder":
            return "N/A"
        return _format_weather(r["health"], ctx.colour)

    def weather_plain(r: dict) -> str:
        if r["type"] == "folder":
            return "n/a"
        return _weather_word(r["health"]) or ""

    def type_table(r: dict, _i: int) -> str:
        return _type_table_cell(r["type"], ctx.colour)

    cols = [
        Column("name", "Job", table=name_table, plain=lambda r: r["name"]),
        Column("type", "Type", table=type_table),
        Column("status", "Status", table=status_table, plain=status_plain),
    ]
    if not no_weather:
        cols.append(
            Column("health", "Weather", table=weather_table, plain=weather_plain)
        )
    return cols


def _job_tree(ctx: _Ctx, records: list[dict], root_label: str) -> str:
    """Render the job roster as a hierarchy reconstructed from name paths."""
    by_path = {r["name"]: r for r in records}
    tree: dict = {}
    for r in records:
        node = tree
        for part in r["name"].split("/"):
            node = node.setdefault(part, {})

    def leaf_label(rec: dict) -> str:
        leaf = rec["name"].split("/")[-1]
        if ctx.colour and ctx.seasonal_colours:
            leaf = apply_seasonal_colour(leaf, 0, calendar=ctx.seasonal_calendar)
        if rec["type"] == "folder":
            deco = "📁 folder"
        else:
            emoji = _JOB_COLOUR_MAP.get(rec["color"], ("white", "?", "❓"))[2]
            deco = f"{emoji} {rec['status']}"
        return f"{leaf}  {deco}"

    lines = [click.style(root_label, bold=True) if ctx.colour else root_label]

    def walk(node: dict, prefix: str, path_prefix: str) -> None:
        items = list(node.items())
        for idx, (part, children) in enumerate(items):
            last = idx == len(items) - 1
            branch = "└── " if last else "├── "
            full = f"{path_prefix}/{part}" if path_prefix else part
            rec = by_path.get(full)
            label = leaf_label(rec) if rec else f"{part}"
            lines.append(f"{prefix}{branch}{label}")
            walk(children, prefix + ("    " if last else "│   "), full)

    walk(tree, "", "")
    return "\n".join(lines)


def _emit(
    ctx: _Ctx,
    records: list[dict],
    columns: list[Column],
    *,
    header: str,
    empty: str,
    tree_fn=None,
    compress_col: int | None = None,
) -> None:
    """Render records in the active format; route decoration to stderr."""
    decorative = ctx.fmt in ("table", "tree")

    if not records:
        if decorative:
            click.echo(empty, err=True)
        else:
            click.echo(
                _render.render(ctx.fmt, [], columns, template=ctx.template),
                color=ctx.colour,
            )
        return

    if decorative:
        click.echo(click.style(header, fg="cyan"), err=True, color=ctx.colour)

    cc = (
        compress_col
        if (ctx.fmt == "table" and ctx.colour and sys.stdout.isatty())
        else None
    )
    try:
        out = _render.render(
            ctx.fmt,
            records,
            columns,
            template=ctx.template,
            tree_fn=tree_fn,
            compress_col=cc,
        )
    except ValueError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)
    click.echo(out, color=ctx.colour)


@job.command("list")
@click.option(
    "--folder", default=None, metavar="NAME", help="Limit to a Jenkins folder."
)
@click.option(
    "--no-weather",
    "no_weather",
    is_flag=True,
    default=False,
    help="Skip build health (weather) column; faster on large instances.",
)
@click.option(
    "--expand",
    "expand",
    is_flag=True,
    default=False,
    help="Recursively expand folders to show all descendant jobs.",
)
@click.option(
    "--type-key",
    "type_key",
    is_flag=True,
    default=False,
    is_eager=True,
    help="Print the job-type icon reference and exit.",
)
@pass_ctx
def job_list(
    ctx: _Ctx,
    folder: str | None,
    no_weather: bool,
    expand: bool,
    type_key: bool,
) -> None:
    """List all Jenkins jobs."""
    if type_key:
        click.echo(_render_type_key(), color=ctx.colour)
        return

    client = _make_client(ctx)
    depth = 0 if no_weather else 1
    try:
        job_list = client.jobs(folder=folder, depth=depth)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    records = _collect_job_records(
        client, job_list, no_weather, expand, folder or "", client._base
    )
    columns = _job_columns(ctx, no_weather)
    root_label = f"jenkins/{folder}" if folder else "jenkins"
    _emit(
        ctx,
        records,
        columns,
        header="📋 Allow me to present the staff roster.",
        empty=(
            "🗒️ The staff roster appears entirely bare. "
            "Jenkins would seem to have no positions filled at present."
        ),
        tree_fn=lambda recs: _job_tree(ctx, recs, root_label),
        compress_col=1,
    )


# ── job trigger ──────────────────────────────────────────────────────────────


@job.command("trigger")
@click.argument("job_name", metavar="JOB")
@click.option(
    "--param",
    "params",
    multiple=True,
    metavar="KEY=VALUE",
    help="Build parameter in KEY=VALUE format. Repeatable.",
)
@pass_ctx
def job_trigger(
    ctx: _Ctx,
    job_name: str,
    params: tuple[str, ...],
) -> None:
    """Trigger a Jenkins build.

    JOB is the job name (or folder/job path for nested jobs).
    """
    try:
        param_dict = _parse_params(params)
    except ValueError as exc:
        click.echo(
            click.style(f"I'm afraid '{exc}' is not in KEY=VALUE format.", fg="red"),
            err=True,
            color=ctx.colour,
        )
        sys.exit(1)

    client = _make_client(ctx)
    try:
        client.build(job_name, params=param_dict or None)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(
        click.style(
            f"🚀 I shall dispatch '{job_name}' at once. Very good.", fg="green"
        ),
        color=ctx.colour,
    )


# ── builds ───────────────────────────────────────────────────────────────────

# (permalink, display label) shown by `jeeves builds`.
_BUILD_PERMALINKS = [
    ("lastBuild", "last"),
    ("lastSuccessfulBuild", "successful"),
    ("lastFailedBuild", "failed"),
]


def _build_record(permalink: str, label: str, info: dict | None) -> dict:
    """Semantic record for one build permalink (or an empty one when absent)."""
    if info is None:
        return {
            "permalink": label,
            "number": None,
            "result": None,
            "building": False,
            "timestamp": None,
            "duration": None,
            "url": None,
        }
    return {
        "permalink": label,
        "number": info.get("number"),
        "result": info.get("result"),
        "building": bool(info.get("building", False)),
        "timestamp": info.get("timestamp"),
        "duration": info.get("duration"),
        "url": info.get("url"),
    }


def _causes_from_build(info: dict) -> list[dict]:
    """Extract the causes (why a build ran) from a build's actions."""
    causes = []
    for action in info.get("actions", []):
        if "CauseAction" not in action.get("_class", ""):
            continue
        for c in action.get("causes", []):
            causes.append(
                {
                    "description": c.get("shortDescription", ""),
                    "userId": c.get("userId"),
                    "upstreamProject": c.get("upstreamProject"),
                    "upstreamBuild": c.get("upstreamBuild"),
                }
            )
    return causes


def _raw_build_record(info: dict) -> dict:
    """Semantic record for a build dict from the builds list."""
    return {
        "number": info.get("number"),
        "result": info.get("result"),
        "building": bool(info.get("building", False)),
        "timestamp": info.get("timestamp"),
        "duration": info.get("duration"),
        "url": info.get("url"),
        "params": _params_from_build(info),
        "causes": _causes_from_build(info),
    }


def _build_columns(
    ctx: _Ctx, include_permalink: bool = False, include_details: bool = False
) -> list[Column]:
    def build_table(r: dict, i: int) -> str:
        if r["number"] is None:
            return "—"
        text = f"#{r['number']}"
        if r["url"]:
            text = _hyperlink(text, r["url"], ctx.colour)
        if ctx.colour and ctx.seasonal_colours:
            text = apply_seasonal_colour(text, i, calendar=ctx.seasonal_calendar)
        return text

    def build_plain(r: dict) -> str:
        return "" if r["number"] is None else f"#{r['number']}"

    cols = []
    if include_permalink:
        cols.append(Column("permalink", "Permalink"))
    cols += [
        Column("number", "Build", table=build_table, plain=build_plain),
        Column(
            "result",
            "Result",
            table=lambda r, _i: _format_build_result(
                r["result"], r["building"], ctx.colour
            ),
            plain=lambda r: _build_result_word(r["result"], r["building"]),
        ),
        Column(
            "timestamp",
            "When",
            table=lambda r, _i: _relative_time(r["timestamp"]),
            plain=lambda r: _relative_time(r["timestamp"]),
        ),
        Column(
            "duration",
            "Duration",
            table=lambda r, _i: _format_duration(r["duration"]),
            plain=lambda r: _format_duration(r["duration"]),
        ),
    ]
    if include_details:
        cols.append(
            Column(
                "params",
                "Parameters",
                plain=lambda r: ", ".join(f"{k}={v}" for k, v in r["params"].items()),
            )
        )
        cols.append(
            Column(
                "causes",
                "Causes",
                plain=lambda r: "; ".join(
                    c["description"] for c in r["causes"] if c["description"]
                ),
            )
        )
    return cols


@build.command("summary")
@click.argument("job")
@pass_ctx
def build_summary(
    ctx: _Ctx,
    job: str,
) -> None:
    """Show a job's last, last-successful, and last-failed builds."""
    client = _make_client(ctx)
    try:
        records = [
            _build_record(permalink, label, client.build_info(job, permalink))
            for permalink, label in _BUILD_PERMALINKS
        ]
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    if all(r["number"] is None for r in records):
        records = []

    _emit(
        ctx,
        records,
        _build_columns(ctx, include_permalink=True),
        header=f"🛠️ The build record for '{job}'.",
        empty=f"🆕 '{job}' has no builds on record yet. A clean slate.",
    )


@build.command("list")
@click.argument("job")
@click.option(
    "--limit", default=20, metavar="N", type=int, help="Maximum builds to show."
)
@click.option(
    "--result",
    "result_filter",
    default=None,
    metavar="RESULT",
    help="Only builds with this result (e.g. SUCCESS, FAILURE, UNSTABLE).",
)
@click.option(
    "--param",
    "param_filters",
    multiple=True,
    metavar="KEY=VALUE",
    help="Only builds with this parameter value. Repeatable (all must match).",
)
@pass_ctx
def build_list(
    ctx: _Ctx,
    job: str,
    limit: int,
    result_filter: str | None,
    param_filters: tuple[str, ...],
) -> None:
    """Show a job's recent build history (newest first)."""
    try:
        filter_dict = _parse_params(param_filters)
    except ValueError as exc:
        click.echo(
            click.style(f"I'm afraid '{exc}' is not in KEY=VALUE format.", fg="red"),
            err=True,
            color=ctx.colour,
        )
        sys.exit(1)

    client = _make_client(ctx)
    try:
        raw = client.builds(job, limit=limit)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    records = [_raw_build_record(b) for b in raw]
    if result_filter:
        wanted = result_filter.upper()
        records = [r for r in records if (r["result"] or "") == wanted]
    if filter_dict:
        records = [
            r
            for r in records
            if all(r["params"].get(k) == v for k, v in filter_dict.items())
        ]

    _emit(
        ctx,
        records,
        _build_columns(ctx, include_details=bool(filter_dict)),
        header=f"🛠️ The recent builds of '{job}'.",
        empty=f"🔍 '{job}' has no builds matching that description.",
    )


@build.command("show")
@click.argument("job")
@click.argument("build_id", metavar="[BUILD]", default="lastBuild")
@pass_ctx
def build_show(
    ctx: _Ctx,
    job: str,
    build_id: str,
) -> None:
    """Show a single build (by number, or a permalink like lastBuild)."""
    client = _make_client(ctx)
    try:
        info = client.build_info(job, build_id)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    records = [_raw_build_record(info)] if info is not None else []
    _emit(
        ctx,
        records,
        _build_columns(ctx, include_details=True),
        header=f"🛠️ Build {build_id} of '{job}'.",
        empty=f"🤷 I could find no build '{build_id}' for '{job}'.",
    )


# ── params ───────────────────────────────────────────────────────────────────


def _param_records(job_json: dict) -> list[dict]:
    """Extract parameter definitions from a job's detail JSON."""
    records = []
    for prop in job_json.get("property", []):
        if "ParametersDefinitionProperty" not in prop.get("_class", ""):
            continue
        for definition in prop.get("parameterDefinitions", []):
            cls = definition.get("_class", "").rsplit(".", 1)[-1]
            ptype = cls.replace("ParameterDefinition", "").lower() or "parameter"
            default = definition.get("defaultParameterValue") or {}
            records.append(
                {
                    "name": definition.get("name", "?"),
                    "type": ptype,
                    "default": default.get("value"),
                    "choices": definition.get("choices", []) or [],
                    "description": definition.get("description") or "",
                }
            )
    return records


@job.command("params")
@click.argument("job", metavar="JOB")
@pass_ctx
def job_params(
    ctx: _Ctx,
    job: str,
) -> None:
    """Show a job's build parameters (name, type, default, choices)."""
    client = _make_client(ctx)
    try:
        job_json = client.job(job)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    records = _param_records(job_json)
    columns = [
        Column("name", "Name"),
        Column("type", "Type"),
        Column(
            "default",
            "Default",
            plain=lambda r: "" if r["default"] is None else str(r["default"]),
        ),
        Column("choices", "Choices", plain=lambda r: ", ".join(map(str, r["choices"]))),
        Column("description", "Description"),
    ]
    _emit(
        ctx,
        records,
        columns,
        header=f"📝 The instructions for '{job}'.",
        empty=f"🗒️ '{job}' requires no special instructions. Simply say the word.",
    )


# ── build rebuild ────────────────────────────────────────────────────────────


def _params_from_build(info: dict) -> dict[str, str]:
    """Extract the parameter values a build was run with."""
    for action in info.get("actions", []):
        if "ParametersAction" not in action.get("_class", ""):
            continue
        return {
            p.get("name"): p.get("value")
            for p in action.get("parameters", [])
            if p.get("name") is not None
        }
    return {}


@build.command("rebuild")
@click.argument("job")
@click.option(
    "--build",
    "build_id",
    default="lastBuild",
    metavar="N",
    help="Build to copy parameters from (default: lastBuild).",
)
@click.option(
    "--param",
    "overrides",
    multiple=True,
    metavar="KEY=VALUE",
    help="Override a parameter for the rebuild. Repeatable.",
)
@pass_ctx
def build_rebuild(
    ctx: _Ctx,
    job: str,
    build_id: str,
    overrides: tuple[str, ...],
) -> None:
    """Re-trigger a build with the parameters it last ran with."""
    try:
        override_dict = _parse_params(overrides)
    except ValueError as exc:
        click.echo(
            click.style(f"I'm afraid '{exc}' is not in KEY=VALUE format.", fg="red"),
            err=True,
            color=ctx.colour,
        )
        sys.exit(1)

    client = _make_client(ctx)
    try:
        info = client.build_info(job, build_id)
        if info is None:
            _butler_error(
                f"There is no build on record to repeat for '{job}'.",
                ctx.colour,
            )
            sys.exit(1)
        merged = {**_params_from_build(info), **override_dict}
        client.build(job, params=merged or None)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    message = f"🔁 Once more, with feeling — re-running '{job}'."
    click.echo(click.style(message, fg="green"), color=ctx.colour)
    if merged:
        summary = ", ".join(f"{k}={v}" for k, v in merged.items())
        click.echo(f"   with: {summary}", color=ctx.colour)


# ── build log ────────────────────────────────────────────────────────────────


def _log_impl(ctx: _Ctx, job: str, build_id: str) -> None:
    client = _make_client(ctx)
    try:
        text = client.log(job, build=build_id)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(text, nl=False)


@build.command("log")
@click.argument("job")
@click.argument("build_id", metavar="[BUILD]", default="lastBuild")
@pass_ctx
def build_log(
    ctx: _Ctx,
    job: str,
    build_id: str,
) -> None:
    """Show the console log for a build.

    JOB is the job name; BUILD is a build number or permalink
    (default: lastBuild).
    """
    _log_impl(ctx, job, build_id)


# ── queue ───────────────────────────────────────────────────────────────────


@main.command()
@pass_ctx
def queue(ctx: _Ctx) -> None:
    """Show the Jenkins build queue."""
    client = _make_client(ctx)
    try:
        items = client.queue()
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    records = []
    for item in items:
        task_name = item.get("task", {}).get("name", "?")
        task_url = item.get("task", {}).get("url") or (
            f"{client._base}/{_normalize_jenkins_path(task_name)}"
        )
        records.append(
            {
                "name": task_name,
                "reason": item.get("why", ""),
                "stuck": bool(item.get("stuck", False)),
                "url": task_url,
            }
        )

    def name_table(r: dict, i: int) -> str:
        s = _hyperlink(r["name"], r["url"], ctx.colour)
        if ctx.colour and ctx.seasonal_colours:
            s = apply_seasonal_colour(s, i, calendar=ctx.seasonal_calendar)
        return s

    def stuck_table(r: dict, _i: int) -> str:
        if not ctx.colour:
            return "yes" if r["stuck"] else "no"
        return (
            click.style("⚠️ yes", fg="red", bold=True)
            if r["stuck"]
            else click.style("no", fg="green")
        )

    columns = [
        Column("name", "Job", table=name_table, plain=lambda r: r["name"]),
        Column("reason", "Reason"),
        Column(
            "stuck",
            "Stuck",
            table=stuck_table,
            plain=lambda r: "yes" if r["stuck"] else "no",
        ),
    ]
    _emit(
        ctx,
        records,
        columns,
        header="⏳ The pending requests.",
        empty=(
            "😴 The queue stands quite empty. Jenkins is evidently at leisure "
            "— a rare and precious state of affairs."
        ),
    )


# ── build cancel ─────────────────────────────────────────────────────────────


def _cancel_impl(ctx: _Ctx, job: str, build_id: int) -> None:
    client = _make_client(ctx)
    try:
        client.cancel(job, build_id)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(
        click.style(f"🛑 Consider build #{build_id} of '{job}' dismissed.", fg="green"),
        color=ctx.colour,
    )


@build.command("cancel")
@click.argument("job")
@click.argument("build_id", metavar="BUILD", type=int)
@pass_ctx
def build_cancel(
    ctx: _Ctx,
    job: str,
    build_id: int,
) -> None:
    """Cancel a running Jenkins build.

    JOB is the job name; BUILD is the build number to cancel.
    """
    _cancel_impl(ctx, job, build_id)


# ── node list ────────────────────────────────────────────────────────────────


def _disk_table_cell(num: int | None, colour: bool) -> str:
    """Free-disk cell with threshold colouring (low = red)."""
    text = _format_bytes(num)
    if not colour or num is None:
        return text
    gb = num / (1024**3)
    fg = "red" if gb < 5 else "yellow" if gb < 20 else "green"
    return click.style(text, fg=fg)


@node_group.command("list")
@click.option(
    "--stats",
    is_flag=True,
    default=False,
    help="Show node health metrics (disk, temp, swap, response time, arch).",
)
@click.option(
    "--address",
    is_flag=True,
    default=False,
    help="Show each node's launcher host/IP (one extra request per node).",
)
@pass_ctx
def node_list(ctx: _Ctx, stats: bool, address: bool) -> None:
    """List Jenkins build nodes (agents)."""
    client = _make_client(ctx)
    try:
        node_list = client.nodes(depth=1 if stats else 0)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    built_in = {"master", "Built-In Node"}
    records = []
    for n in node_list:
        display_name = n.get("displayName", "?")
        url_name = "(built-in)" if display_name in built_in else display_name
        raw_labels = [
            lbl["name"] for lbl in n.get("assignedLabels", []) if "name" in lbl
        ]
        record = {
            "name": display_name,
            "status": "offline" if n.get("offline", False) else "online",
            "executors": n.get("numExecutors", "?"),
            "labels": [lbl for lbl in raw_labels if lbl != display_name],
            "url": f"{client._base}/computer/{url_name}/",
        }
        if stats:
            record.update(_node_stat_fields(n.get("monitorData") or {}))
        if address:
            record["address"] = _node_address(
                client, display_name, display_name in built_in
            )
        records.append(record)

    def name_table(r: dict, i: int) -> str:
        s = _hyperlink(r["name"], r["url"], ctx.colour)
        if ctx.colour and ctx.seasonal_colours:
            s = apply_seasonal_colour(s, i, calendar=ctx.seasonal_calendar)
        return s

    def status_table(r: dict, _i: int) -> str:
        if not ctx.colour:
            return r["status"]
        if r["status"] == "offline":
            return click.style("🔴 offline", fg="red", bold=True)
        return click.style("✅ online", fg="green", bold=True)

    def executors_table(r: dict, _i: int) -> str:
        ex = r["executors"]
        if ctx.colour and isinstance(ex, int):
            return colour_grade_number(ex)
        return str(ex)

    def labels_table(r: dict, i: int) -> str:
        parts = []
        for lbl in r["labels"]:
            linked = _hyperlink(lbl, f"{client._base}/label/{lbl}/", ctx.colour)
            if ctx.colour and ctx.seasonal_colours:
                linked = apply_seasonal_colour(
                    linked, i, calendar=ctx.seasonal_calendar
                )
            parts.append(linked)
        return ", ".join(parts)

    name_col = Column("name", "Node", table=name_table, plain=lambda r: r["name"])
    status_col = Column("status", "Status", table=status_table)

    if stats:
        columns = [
            name_col,
            status_col,
            Column(
                "disk",
                "Disk",
                table=lambda r, _i: _disk_table_cell(r["disk"], ctx.colour),
                plain=lambda r: _format_bytes(r["disk"]),
            ),
            Column(
                "temp",
                "Temp",
                table=lambda r, _i: _format_bytes(r["temp"]),
                plain=lambda r: _format_bytes(r["temp"]),
            ),
            Column(
                "swap",
                "Swap",
                table=lambda r, _i: _format_bytes(r["swap"]),
                plain=lambda r: _format_bytes(r["swap"]),
            ),
            Column(
                "response_ms",
                "Response",
                table=lambda r, _i: (
                    "—" if r["response_ms"] is None else f"{int(r['response_ms'])}ms"
                ),
                plain=lambda r: (
                    "" if r["response_ms"] is None else f"{int(r['response_ms'])}ms"
                ),
            ),
            Column(
                "architecture",
                "Arch",
                plain=lambda r: r["architecture"] or "",
                table=lambda r, _i: r["architecture"] or "—",
            ),
        ]
    else:
        columns = [
            name_col,
            status_col,
            Column("executors", "Executors", table=executors_table),
            Column(
                "labels",
                "Labels",
                table=labels_table,
                plain=lambda r: ", ".join(r["labels"]),
            ),
        ]
    if address:
        columns.append(
            Column(
                "address",
                "Address",
                table=lambda r, _i: r["address"] or "—",
                plain=lambda r: r["address"] or "",
            )
        )
    _emit(
        ctx,
        records,
        columns,
        header="🏠 The household staff.",
        empty=(
            "🚪 The household staff appears to have entirely absented themselves. "
            "One trusts they haven't all handed in their notice."
        ),
    )


# ── whoami ───────────────────────────────────────────────────────────────────


@main.command()
@pass_ctx
def whoami(ctx: _Ctx) -> None:
    """Show the currently authenticated Jenkins user."""
    client = _make_client(ctx)
    try:
        data = client.whoami()
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    user_id = data.get("id", "anonymous")
    full_name = data.get("fullName", "")

    if user_id == "anonymous":
        click.echo(
            click.style(
                "👤 Connected as anonymous. No credentials were presented.",
                fg="yellow",
            ),
            color=ctx.colour,
        )
        return

    if full_name and full_name != user_id:
        identity = f"{user_id} ({full_name})"
    else:
        identity = user_id

    click.echo(
        click.style(f"👤 Authenticated as: {identity}", fg="green"),
        color=ctx.colour,
    )


# ── swatch ───────────────────────────────────────────────────────────────────


@main.command()
@pass_ctx
def swatch(ctx: _Ctx) -> None:
    """Show colour swatches and iconography reference for the current terminal."""
    from .ui import HOLI_RAINBOW, PRIDE_RAINBOW, SEASONAL_PALETTES

    colour = ctx.colour
    lines = [
        click.style("🎨 jeeves — colour & iconography reference", fg="cyan", bold=True),
        "",
    ]

    # ── Job type icons ────────────────────────────────────────────────────────
    lines.append(click.style("Job types", bold=True))
    type_entries = (
        [
            ("📁 folder", "Jenkins folder or multi-branch project"),
        ]
        + [
            (f"{icon} {label}", f"Jenkins {label} job")
            for _, icon, label in _JOB_TYPE_MAP
        ]
        + [
            (
                f"{_JOB_TYPE_FALLBACK[0]} {_JOB_TYPE_FALLBACK[1]}",
                "Other / unrecognised",
            ),
        ]
    )
    col_w = max(len(e) for e, _ in type_entries)
    for entry, desc in type_entries:
        lines.append(f"  {entry:<{col_w}}  {desc}")
    lines.append("")

    # ── Build status ─────────────────────────────────────────────────────────
    lines.append(click.style("Build status", bold=True))
    for raw, (fg, label, emoji) in _JOB_COLOUR_MAP.items():
        text = f"{emoji} {label}"
        cell = click.style(text, fg=fg, bold=True) if colour else text
        lines.append(f"  {cell}  ({raw})")
    lines.append("")

    # ── Weather / health ─────────────────────────────────────────────────────
    lines.append(click.style("Build health (weather)", bold=True))
    weather_entries = [
        (80, "100", "green", "☀️", "sunny"),
        (60, "79", "yellow", "🌤️", "fair"),
        (40, "59", "yellow", "☁️", "cloudy"),
        (20, "39", 208, "🌧️", "rainy"),
        (0, "19", "red", "⛈️", "stormy"),
    ]
    for lo, hi, fg, emoji, label in weather_entries:
        text = f"{emoji} {label}"
        cell = click.style(text, fg=fg, bold=True) if colour else text
        lines.append(f"  {cell}  score {lo}–{hi}")
    lines.append("")

    # ── Node status ───────────────────────────────────────────────────────────
    lines.append(click.style("Node status", bold=True))
    online = click.style("✅ online", fg="green", bold=True) if colour else "✅ online"
    offline = click.style("🔴 offline", fg="red", bold=True) if colour else "🔴 offline"
    lines.append(f"  {online}    {offline}")
    lines.append("")

    # ── Seasonal colours ─────────────────────────────────────────────────────
    def _ansi_block(code: str) -> str:
        return f"{code}████\033[0m"

    lines.append(click.style("Seasonal colours", bold=True))
    palette_rows = [
        ("January 🗓️", "purple"),
        ("Valentine's / Hanami 🌸", "pink"),
        ("Lunar New Year 🧧", "lny"),
        ("Rosh Hashanah / Diwali 🪔", "gold"),
        ("Easter / Mid-Autumn 🎑", "yellow"),
        ("October / Sukkot 🌿", "orange"),
        ("December 🎄", "red"),
        ("Eid / Summer 🌙", "green"),
        ("Hanukkah / Songkran 💦", "blue"),
        ("Passover / Vaisakhi 🌾", "spring_green"),
    ]
    col_w2 = max(len(label) for label, _ in palette_rows) + 2
    for label, key in palette_rows:
        swatch_block = _ansi_block(SEASONAL_PALETTES[key]) if colour else "████"
        lines.append(f"  {label:<{col_w2}}  {swatch_block}")
    pride = (
        "  ".join(_ansi_block(c) for c in PRIDE_RAINBOW) if colour else "pride rainbow"
    )
    lines.append(f"  {'Pride Month 🌈 (June)':<{col_w2}}  {pride}")
    holi = "  ".join(_ansi_block(c) for c in HOLI_RAINBOW) if colour else "holi rainbow"
    lines.append(f"  {'Holi 🎨 (spring)':<{col_w2}}  {holi}")

    click.echo("\n".join(lines), color=colour)


# ── deprecated aliases ────────────────────────────────────────────────────────
# The pre-noun-group flat commands keep working for one release, hidden from
# --help, each printing a gentle notice pointing at the new spelling.


def _deprecation_notice(old: str, new: str) -> None:
    ctx = click.get_current_context(silent=True)
    obj = ctx.find_object(_Ctx) if ctx else None
    colour = obj.colour if obj else True
    click.echo(
        click.style(
            f"🎩 A gentle word: 'jeeves {old}' has moved to 'jeeves {new}'. "
            "The old form retires in a future release.",
            fg="yellow",
        ),
        err=True,
        color=colour,
    )


def _deprecated_alias(
    old: str, new: str, target: click.Command, *, name: str
) -> click.Command:
    """A hidden Command that prints a deprecation notice then runs ``target``.

    The alias shares ``target``'s Param objects — safe, since parse state lives
    on the Context, not the Param; do not mutate params in place on either.
    """

    def _callback(*args, **kwargs):
        _deprecation_notice(old, new)
        return target.callback(*args, **kwargs)

    functools.update_wrapper(_callback, target.callback)
    return click.Command(
        name=name,
        params=list(target.params),
        callback=_callback,
        help=target.help,
        hidden=True,
    )


main.add_command(_deprecated_alias("jobs", "job list", job_list, name="jobs"))
main.add_command(
    _deprecated_alias("params JOB", "job params JOB", job_params, name="params")
)
main.add_command(
    _deprecated_alias("rebuild JOB", "build rebuild JOB", build_rebuild, name="rebuild")
)
main.add_command(_deprecated_alias("nodes", "node list", node_list, name="nodes"))

# Reachable only via _BuildGroup's fallback (never registered on main): keeps
# the legacy `jeeves build JOB [--param K=V]` trigger form working.
_LEGACY_BUILD_VERB = _deprecated_alias(
    "build JOB", "job trigger JOB", job_trigger, name="build"
)

_builds_alias = click.Group("builds", hidden=True, help="Deprecated: use 'build'.")
_builds_alias.add_command(
    _deprecated_alias(
        "builds summary JOB", "build summary JOB", build_summary, name="summary"
    )
)
_builds_alias.add_command(
    _deprecated_alias("builds list JOB", "build list JOB", build_list, name="list")
)
_builds_alias.add_command(
    _deprecated_alias(
        "builds show JOB [BUILD]", "build show JOB [BUILD]", build_show, name="show"
    )
)
main.add_command(_builds_alias)


# `log` and `cancel` changed shape (--build option → positional BUILD), so
# their aliases are hand-written with the old signatures frozen.
@main.command("log", hidden=True)
@click.argument("job")
@click.option(
    "--build",
    "build_id",
    default="lastBuild",
    metavar="N",
    help="Build number (default: lastBuild).",
)
@pass_ctx
def legacy_log(ctx: _Ctx, job: str, build_id: str) -> None:
    """Deprecated: use 'jeeves build log'."""
    _deprecation_notice("log JOB --build N", "build log JOB [BUILD]")
    _log_impl(ctx, job, build_id)


@main.command("cancel", hidden=True)
@click.argument("job")
@click.option(
    "--build",
    "build_id",
    required=True,
    type=int,
    metavar="N",
    help="Build number to cancel.",
)
@pass_ctx
def legacy_cancel(ctx: _Ctx, job: str, build_id: int) -> None:
    """Deprecated: use 'jeeves build cancel'."""
    _deprecation_notice("cancel JOB --build N", "build cancel JOB BUILD")
    _cancel_impl(ctx, job, build_id)
