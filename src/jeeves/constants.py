"""Shared lookup tables and static data used by the CLI."""

from __future__ import annotations

ENVVAR_PREFIX = "JEEVES"
BUTLER_ITEMS = ["🎩", "🥂", "🤵", "📋", "🫗"]

# OSC 8 terminal hyperlink escape sequences.
OSC8_OPEN = "\x1b]8;;{url}\x1b\\"
OSC8_CLOSE = "\x1b]8;;\x1b\\"

# (colour, label, emoji) keyed by Jenkins job "colour" status field.
JOB_COLOUR_MAP: dict[str, tuple[str, str, str]] = {
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

FOLDER_CLASS_FRAGMENTS = ("Folder", "MultiBranch", "OrganizationFolder")

# (class fragment, icon, label) — first match wins
JOB_TYPE_MAP: list[tuple[str, str, str]] = [
    ("WorkflowJob", "🔁", "pipeline"),
    ("FreeStyleProject", "🔧", "freestyle"),
    ("MatrixProject", "🔢", "matrix"),
]
JOB_TYPE_FALLBACK = ("🔨", "job")

ICON_BY_LABEL = {label: icon for _, icon, label in JOB_TYPE_MAP}
ICON_BY_LABEL[JOB_TYPE_FALLBACK[1]] = JOB_TYPE_FALLBACK[0]

WEATHER_MAP: list[tuple[int, str, str, str]] = [
    (80, "green", "☀️", "sunny"),
    (60, "yellow", "🌤️", "fair"),
    (40, "yellow", "☁️", "cloudy"),
    (20, 208, "🌧️", "rainy"),
    (0, "red", "⛈️", "stormy"),
]

# Jenkins build results (distinct vocabulary from job colours): (colour, emoji).
BUILD_RESULT_MAP: dict[str, tuple[str, str]] = {
    "SUCCESS": ("green", "✅"),
    "FAILURE": ("red", "❌"),
    "UNSTABLE": ("yellow", "⚠️"),
    "ABORTED": ("white", "🚫"),
    "NOT_BUILT": ("white", "🔘"),
}

SNIPPET_LEN = 80

TEST_STATUS_MAP: dict[str, tuple[str, str]] = {
    "PASSED": ("green", "✅"),
    "FIXED": ("green", "✅"),
    "FAILED": ("red", "❌"),
    "REGRESSION": ("red", "❌"),
    "SKIPPED": ("yellow", "⏭️"),
}

# Exit codes for --wait, mirroring the build's verdict (unknown verdicts → 1).
WAIT_EXIT_CODES = {"SUCCESS": 0, "FAILURE": 1, "UNSTABLE": 2, "ABORTED": 3}
WAIT_TIMEOUT_EXIT = 124

WAIT_VERDICTS = {
    "SUCCESS": (
        "green",
        "✅ Build #{n} of '{job}' concluded: SUCCESS. Most satisfactory.",
    ),
    "UNSTABLE": (
        "yellow",
        "⚠️ Build #{n} of '{job}' concluded: UNSTABLE. A somewhat mixed report.",
    ),
    "FAILURE": (
        "red",
        "❌ Build #{n} of '{job}' concluded: FAILURE. I regret the outcome.",
    ),
    "ABORTED": ("red", "🛑 Build #{n} of '{job}' was aborted before completion."),
}

# (permalink, display label) shown by `jeeves builds`.
BUILD_PERMALINKS = [
    ("lastBuild", "last"),
    ("lastSuccessfulBuild", "successful"),
    ("lastFailedBuild", "failed"),
]

FOLLOW_POLL_INTERVAL = 1.0
