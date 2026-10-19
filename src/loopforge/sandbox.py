"""Run untrusted candidate code in an isolated subprocess.

The parent process (this file) never executes candidate code. It launches
``sandbox_runner.py`` in a fresh Python process, hands it the source and the
instances over stdin, and reads raw tours back. The parent then validates and
scores those tours itself, so a candidate cannot lie about its own score.

What this protects against: buggy or overeager LLM-generated code (infinite
loops, memory blow-ups, crashes, noisy prints, accidental file or network use).
What it does NOT claim: to stop a determined attacker. See docs/SANDBOX.md.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

RUNNER = Path(__file__).with_name("sandbox_runner.py")
MAX_OUTPUT_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class SandboxLimits:
    per_instance_seconds: float = 2.0  # candidate must solve each instance this fast
    memory_mb: int = 512  # address-space cap (where the OS supports it)
    max_source_bytes: int = 100_000
    startup_grace_seconds: float = 5.0  # extra wall-clock time for interpreter startup


DEFAULT_LIMITS = SandboxLimits()


@dataclass(frozen=True)
class RawRun:
    """What the candidate returned for one instance, before any validation."""

    index: int
    seconds: float
    tour: object | None = None
    error: str | None = None


@dataclass
class SandboxOutcome:
    runs: list[RawRun] = field(default_factory=list)
    fatal: str | None = None  # whole-run failure: timeout, crash, bad source...
    limits_applied: list[str] = field(default_factory=list)
    alarm_available: bool = False


def _child_env() -> dict[str, str]:
    """A nearly empty environment so API keys and tokens never reach candidate code."""
    env: dict[str, str] = {}
    if os.name == "nt":  # Windows needs a few variables for Python to start
        for key in ("SYSTEMROOT", "SYSTEMDRIVE"):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _describe_exit(returncode: int) -> str:
    if returncode < 0:
        sig = -returncode
        try:
            name = signal.Signals(sig).name
        except ValueError:
            name = f"signal {sig}"
        hints = {
            "SIGXCPU": "CPU time limit exceeded",
            "SIGKILL": "killed, possibly for exceeding the memory limit",
            "SIGSEGV": "crashed (segmentation fault)",
        }
        return f"sandbox process terminated by {name}: {hints.get(name, 'abnormal exit')}"
    return f"sandbox process exited with code {returncode} before finishing"


def run_in_sandbox(
    source: str,
    instances: tuple | list,
    limits: SandboxLimits = DEFAULT_LIMITS,
) -> SandboxOutcome:
    """Run ``solve`` from ``source`` on each instance inside a subprocess."""
    if len(source.encode("utf-8", "replace")) > limits.max_source_bytes:
        return SandboxOutcome(fatal=f"source is larger than {limits.max_source_bytes} bytes")

    payload = json.dumps(
        {
            "source": source,
            "instances": [[list(p) for p in inst] for inst in instances],
            "per_instance_seconds": limits.per_instance_seconds,
            "memory_mb": limits.memory_mb,
        }
    ).encode()

    wall = limits.startup_grace_seconds + limits.per_instance_seconds * max(1, len(instances))
    timed_out = False

    with tempfile.TemporaryDirectory(prefix="loopforge-sbx-") as workdir:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-B", str(RUNNER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workdir,
            env=_child_env(),
            start_new_session=(os.name == "posix"),
        )
        try:
            stdout, stderr = proc.communicate(payload, timeout=wall)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(proc)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout, stderr = b"", b""

    outcome = SandboxOutcome()
    done = False

    if len(stdout) > MAX_OUTPUT_BYTES:
        outcome.fatal = "sandbox produced too much output"
        return outcome

    for line in stdout.decode("utf-8", "replace").splitlines():
        try:
            msg = json.loads(line)
            kind = msg["t"]
        except (ValueError, KeyError, TypeError):
            outcome.fatal = "malformed output from sandbox"
            return outcome
        if kind == "ready":
            outcome.limits_applied = list(msg.get("limits", []))
            outcome.alarm_available = bool(msg.get("alarm", False))
        elif kind == "fatal":
            outcome.fatal = str(msg.get("error", "unknown error"))
            return outcome
        elif kind == "run":
            outcome.runs.append(
                RawRun(
                    index=int(msg["i"]),
                    seconds=float(msg.get("seconds", 0.0)),
                    tour=msg.get("tour"),
                    error=msg.get("error"),
                )
            )
        elif kind == "done":
            done = True

    if timed_out:
        outcome.fatal = f"timed out: sandbox exceeded {wall:.1f}s of wall-clock time"
    elif not done:
        detail = _describe_exit(proc.returncode)
        tail = stderr.decode("utf-8", "replace").strip()[-200:]
        outcome.fatal = f"{detail}. {tail}".strip() if tail else detail
    return outcome


def probe_sandbox() -> SandboxOutcome:
    """Run a trivial candidate to find out which protections this machine enforces."""
    return run_in_sandbox(
        "def solve(points):\n    return list(range(len(points)))",
        [[(0.0, 0.0), (1.0, 1.0)]],
    )
