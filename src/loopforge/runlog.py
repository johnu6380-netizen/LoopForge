"""Run logging: everything a search does is written to disk so it can be replayed.

A run directory contains:

    config.json      the settings the run started with
    programs.jsonl   one JSON line per program, appended as it is produced
    summary.json     written at the end: best program, counts, best-so-far curve
    best.py          source of the best program found

``programs.jsonl`` is flushed line by line, so a crashed run still leaves a
usable log. The web UI (Stage 5) reads these same files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .archive import Program


def _dumps(obj: object, **kwargs) -> str:
    # allow_nan=False makes any stray inf/NaN fail loudly instead of writing invalid JSON.
    return json.dumps(obj, allow_nan=False, **kwargs)


def unique_run_dir(base: Path, name: str) -> Path:
    """``base/name``, or ``base/name-2``, ``-3``... if that already exists."""
    candidate = base / name
    n = 2
    while candidate.exists():
        candidate = base / f"{name}-{n}"
        n += 1
    return candidate


class RunLogger:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.programs_path = self.directory / "programs.jsonl"
        self.programs_path.write_text("")

    def write_config(self, config: dict) -> None:
        (self.directory / "config.json").write_text(_dumps(config, indent=2) + "\n")

    def log_program(self, program: Program) -> None:
        with self.programs_path.open("a") as f:
            f.write(_dumps(program.to_dict()) + "\n")
            f.flush()

    def write_summary(self, summary: dict) -> None:
        (self.directory / "summary.json").write_text(_dumps(summary, indent=2) + "\n")

    def write_best_source(self, source: str) -> None:
        (self.directory / "best.py").write_text(source.rstrip() + "\n", encoding="utf-8")


@dataclass
class LoadedRun:
    directory: Path
    config: dict
    programs: list[Program]
    summary: dict | None  # None if the run never finished


def load_run(directory: Path) -> LoadedRun:
    directory = Path(directory)
    config = json.loads((directory / "config.json").read_text())
    programs = [
        Program.from_dict(json.loads(line))
        for line in (directory / "programs.jsonl").read_text().splitlines()
        if line.strip()
    ]
    summary_path = directory / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    return LoadedRun(directory, config, programs, summary)
