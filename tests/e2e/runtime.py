"""Which container runtime are we on, and how do we drive it.

CI runs Docker on `ubuntu-latest`. A macOS developer may instead have Apple's
`container`, which ships with recent macOS and runs Linux containers in
lightweight VMs. The two are close enough at the CLI — `build -f`, `run -d
--name -p`, `stop`, `rm`, `logs` — that the suite can support both from one
thin seam, which is what this module is.

Deliberately not a general abstraction. It covers exactly the five verbs the
fixture needs, and nothing else, so there is no pretence that an arbitrary
Docker command will work here.
"""

import shutil
import subprocess

__all__ = ["ContainerRuntime", "RuntimeUnavailable", "detect_runtime"]

# Docker first: it is what CI uses, so when both exist the local run matches
# CI rather than diverging from it.
_CANDIDATES = ("docker", "container")


class RuntimeUnavailable(Exception):
    """No usable container runtime was found, or the one found is not healthy."""


class ContainerRuntime:
    """A container CLI the fixture can drive.

    ``name`` is the executable. ``kind`` is ``"docker"`` or ``"apple"``, for
    the handful of places the two genuinely differ.
    """

    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self._path = path
        self.kind = "docker" if name == "docker" else "apple"

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<ContainerRuntime {self.name}>"

    def run(self, *args: str, timeout: int = 120, check: bool = True):
        """Run the CLI with ``args`` and return the completed process."""
        completed = subprocess.run(
            [self._path, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if check and completed.returncode != 0:
            raise RuntimeUnavailable(
                f"`{self.name} {' '.join(args)}` failed with "
                f"{completed.returncode}\n"
                f"--- stdout ---\n{completed.stdout}\n"
                f"--- stderr ---\n{completed.stderr}"
            )
        return completed

    def healthy(self) -> tuple[bool, str]:
        """Can we actually talk to the runtime's daemon?

        A present binary is not a working runtime: Docker Desktop may be
        installed but stopped, and Apple's ``container`` needs
        ``container system start`` before anything works. Listing containers is
        the cheapest call that proves the daemon answers.
        """
        try:
            verb = "ps" if self.kind == "docker" else "ls"
            completed = self.run(verb, timeout=20, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"{self.name} could not be invoked: {exc}"
        if completed.returncode != 0:
            hint = (
                "is Docker running?"
                if self.kind == "docker"
                else "run `container system start`"
            )
            return False, f"{self.name} is installed but not answering — {hint}"
        return True, ""

    # ── the five verbs the fixture needs ────────────────────────────────────

    def build(self, *, context: str, dockerfile: str, tag: str, timeout: int) -> None:
        self.run("build", "-t", tag, "-f", dockerfile, context, timeout=timeout)

    def start_detached(
        self, *, image: str, name: str, host_port: int, container_port: int
    ) -> None:
        """Start a detached container publishing one port on loopback.

        Both runtimes honour ``-p``, and publishing is preferred over reaching
        the container's own IP: Apple's runtime gives each container a routable
        address, but it is not reachable from the host in every macOS
        configuration, whereas a published port is the same contract on both.
        """
        self.run(
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{host_port}:{container_port}",
            image,
            timeout=180,
        )

    def stop(self, name: str) -> None:
        """Stop and remove a container, tolerating one that is already gone."""
        self.run("stop", name, check=False, timeout=90)
        self.run("rm", name, check=False, timeout=60)

    def running(self, name: str) -> bool:
        """Is the named container still up?

        Used to tell a Jenkins that failed to boot from a Jenkins that booted
        fine but cannot be reached from the host.
        """
        verb = "ps" if self.kind == "docker" else "ls"
        completed = self.run(verb, check=False, timeout=30)
        return name in (completed.stdout or "")

    def serves_internally(self, name: str, port: int, path: str, auth: str) -> bool:
        """Does the container answer HTTP on ``port`` from inside itself?

        This is the discriminator that matters. If a service answers inside
        the container but not through its published port, the fault is the
        host's routing, not the service — and the suite should skip with that
        explanation rather than report a dozen failures or sit through a boot
        timeout blaming the application.

        It must probe **the same thing the readiness poll requires**, and with
        the same credentials. Probing something weaker — an unauthenticated
        login page, say — would classify a broken security realm as a host
        networking problem and skip locally, hiding exactly the kind of
        configuration bug this fixture is most likely to have.

        ``curl`` is present in the official Debian-based jenkins/jenkins
        image. If that ever stops being true this returns False, which
        degrades to the honest "not ready" failure with the container logs
        attached — not to a wrong answer.
        """
        completed = self.run(
            "exec",
            name,
            "curl",
            "-s",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            "10",
            "-u",
            auth,
            f"http://127.0.0.1:{port}{path}",
            check=False,
            timeout=60,
        )
        return (completed.stdout or "").strip().endswith("200")

    def logs(self, name: str) -> str:
        """Best-effort logs, for putting in a failure message."""
        completed = self.run("logs", name, check=False, timeout=30)
        return (completed.stdout or "") + (completed.stderr or "")


def detect_runtime() -> ContainerRuntime:
    """Return the first healthy runtime, or raise ``RuntimeUnavailable``.

    The error message gathers every reason, because "no container runtime" is
    far less useful than "docker is installed but its daemon is not running".
    """
    reasons = []
    for candidate in _CANDIDATES:
        path = shutil.which(candidate)
        if path is None:
            reasons.append(f"{candidate}: not installed")
            continue
        runtime = ContainerRuntime(candidate, path)
        ok, why = runtime.healthy()
        if ok:
            return runtime
        reasons.append(why)
    raise RuntimeUnavailable("no usable container runtime: " + "; ".join(reasons))
