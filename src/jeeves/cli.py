"""jeeves — a Jenkins CI/CD butler.

Good morning, sir. I shall attend to your Jenkins affairs with the
utmost discretion and efficiency.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field

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


def _butler_error(msg: str, colour: bool) -> None:
    if "Cannot reach Jenkins at" in msg:
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


def _make_client(
    ctx: _Ctx, url: str | None, user: str | None, token: str | None
) -> JenkinsClient:
    cfg_url, cfg_user, cfg_token = get_jenkins_config(ctx.cfg)
    return JenkinsClient(url or cfg_url, user or cfg_user, token or cfg_token)


# ── Shared connection options ────────────────────────────────────────────────
_url_opt = click.option(
    "--url",
    default=None,
    metavar="URL",
    envvar="JEEVES_URL",
    help="Jenkins server URL (overrides config).",
)
_user_opt = click.option(
    "--user",
    default=None,
    metavar="USER",
    envvar="JEEVES_USER",
    help="Jenkins username (overrides config).",
)
_token_opt = click.option(
    "--token",
    default=None,
    metavar="TOKEN",
    envvar="JEEVES_TOKEN",
    help="Jenkins API token (overrides config).",
)


# ── Group ────────────────────────────────────────────────────────────────────


@click.group(
    epilog=(
        "Made with ❤️  in the UK using the five-clis framework "
        "— https://github.com/mrsixw/five-clis"
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.version_option(package_name="jeeves")
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

    Good morning, sir. How may Jeeves be of assistance?
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
    )
    ctx.ensure_object(_Ctx)

    # ── Bare invocation: greet the user ───────────────────────────────────
    if ctx.invoked_subcommand is None:
        spinner = random.choice(_BUTLER_ITEMS)
        greeting = (
            f"{spinner}  Good morning. " "How may Jeeves be of assistance? Try --help."
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
@_url_opt
@_user_opt
@_token_opt
@click.pass_obj
def status(ctx: _Ctx, url: str | None, user: str | None, token: str | None) -> None:
    """Check Jenkins server health."""
    client = _make_client(ctx, url, user, token)
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


# ── jobs ────────────────────────────────────────────────────────────────────

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
    lines = [click.style("🗝️  Job type reference", fg="cyan", bold=True), ""]
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


@main.command()
@_url_opt
@_user_opt
@_token_opt
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
@click.pass_obj
def jobs(
    ctx: _Ctx,
    url: str | None,
    user: str | None,
    token: str | None,
    folder: str | None,
    no_weather: bool,
    expand: bool,
    type_key: bool,
) -> None:
    """List all Jenkins jobs."""
    if type_key:
        click.echo(_render_type_key(), color=ctx.colour)
        return

    client = _make_client(ctx, url, user, token)
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
            "The staff roster appears entirely bare. "
            "Jenkins would seem to have no positions filled at present."
        ),
        tree_fn=lambda recs: _job_tree(ctx, recs, root_label),
        compress_col=1,
    )


# ── build ───────────────────────────────────────────────────────────────────


@main.command()
@click.argument("job")
@_url_opt
@_user_opt
@_token_opt
@click.option(
    "--param",
    "params",
    multiple=True,
    metavar="KEY=VALUE",
    help="Build parameter in KEY=VALUE format. Repeatable.",
)
@click.pass_obj
def build(
    ctx: _Ctx,
    job: str,
    url: str | None,
    user: str | None,
    token: str | None,
    params: tuple[str, ...],
) -> None:
    """Trigger a Jenkins build.

    JOB is the job name (or folder/job path for nested jobs).
    """
    param_dict: dict[str, str] = {}
    for p in params:
        if "=" not in p:
            click.echo(
                click.style(f"I'm afraid '{p}' is not in KEY=VALUE format.", fg="red"),
                err=True,
                color=ctx.colour,
            )
            sys.exit(1)
        k, _, v = p.partition("=")
        param_dict[k] = v

    client = _make_client(ctx, url, user, token)
    try:
        client.build(job, params=param_dict or None)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(
        click.style(f"🚀 I shall dispatch '{job}' at once. Very good.", fg="green"),
        color=ctx.colour,
    )


# ── log ─────────────────────────────────────────────────────────────────────


@main.command()
@click.argument("job")
@_url_opt
@_user_opt
@_token_opt
@click.option(
    "--build",
    "build_id",
    default="lastBuild",
    metavar="N",
    help="Build number (default: lastBuild).",
)
@click.pass_obj
def log(
    ctx: _Ctx,
    job: str,
    url: str | None,
    user: str | None,
    token: str | None,
    build_id: str,
) -> None:
    """Show the console log for a build.

    JOB is the job name. Use --build to specify a build number.
    """
    client = _make_client(ctx, url, user, token)
    try:
        text = client.log(job, build=build_id)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(text, nl=False)


# ── queue ───────────────────────────────────────────────────────────────────


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.pass_obj
def queue(ctx: _Ctx, url: str | None, user: str | None, token: str | None) -> None:
    """Show the Jenkins build queue."""
    client = _make_client(ctx, url, user, token)
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
            "The queue stands quite empty. Jenkins is evidently at leisure "
            "— a rare and precious state of affairs."
        ),
    )


# ── cancel ──────────────────────────────────────────────────────────────────


@main.command()
@click.argument("job")
@_url_opt
@_user_opt
@_token_opt
@click.option(
    "--build",
    "build_id",
    required=True,
    type=int,
    metavar="N",
    help="Build number to cancel.",
)
@click.pass_obj
def cancel(
    ctx: _Ctx,
    job: str,
    url: str | None,
    user: str | None,
    token: str | None,
    build_id: int,
) -> None:
    """Cancel a running Jenkins build.

    JOB is the job name. --build N is required.
    """
    client = _make_client(ctx, url, user, token)
    try:
        client.cancel(job, build_id)
    except JenkinsError as exc:
        _butler_error(str(exc), ctx.colour)
        sys.exit(1)

    click.echo(
        click.style(
            f"🛑 Consider build #{build_id} of '{job}' dismissed, sir.", fg="green"
        ),
        color=ctx.colour,
    )


# ── nodes ───────────────────────────────────────────────────────────────────


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.pass_obj
def nodes(ctx: _Ctx, url: str | None, user: str | None, token: str | None) -> None:
    """List Jenkins build nodes (agents)."""
    client = _make_client(ctx, url, user, token)
    try:
        node_list = client.nodes()
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
        records.append(
            {
                "name": display_name,
                "status": "offline" if n.get("offline", False) else "online",
                "executors": n.get("numExecutors", "?"),
                "labels": [lbl for lbl in raw_labels if lbl != display_name],
                "url": f"{client._base}/computer/{url_name}/",
            }
        )

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

    columns = [
        Column("name", "Node", table=name_table, plain=lambda r: r["name"]),
        Column("status", "Status", table=status_table),
        Column("executors", "Executors", table=executors_table),
        Column(
            "labels",
            "Labels",
            table=labels_table,
            plain=lambda r: ", ".join(r["labels"]),
        ),
    ]
    _emit(
        ctx,
        records,
        columns,
        header="🏠 The household staff.",
        empty=(
            "The household staff appears to have entirely absented themselves. "
            "One trusts they haven't all handed in their notice."
        ),
    )


# ── whoami ───────────────────────────────────────────────────────────────────


@main.command()
@_url_opt
@_user_opt
@_token_opt
@click.pass_obj
def whoami(ctx: _Ctx, url: str | None, user: str | None, token: str | None) -> None:
    """Show the currently authenticated Jenkins user."""
    client = _make_client(ctx, url, user, token)
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
@click.pass_obj
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
