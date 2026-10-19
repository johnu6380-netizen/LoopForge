"""One-time patch for the existing Loopforge files. Run from the project root:

    python apply_patch.py

It makes small, exact edits (UTF-8 file reading/writing, an optional `keep_tours` switch in the
evaluator, and registration of the `loopforge exp ...` commands). It refuses to guess: if a file
does not look the way it expected, it stops and changes nothing in that file. Safe to run twice.
"""

from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
PKG = ROOT / "src" / "loopforge"

# (relative path, [(old text, new text, marker that means "already patched")])
PATCHES = {
    "evaluator.py": [
        (
            "    seconds: float\n    error: str | None = None\n\n\n@dataclass\nclass EvalResult:",
            "    seconds: float\n    error: str | None = None\n"
            "    tour: list[int] | None = None  # only filled when evaluate(..., keep_tours=True)\n\n\n"
            "@dataclass\nclass EvalResult:",
            "tour: list[int] | None = None",
        ),
        (
            "    references: list[float],\n    time_limit: float | None,\n) -> EvalResult:",
            "    references: list[float],\n    time_limit: float | None,\n    keep_tours: bool = False,\n) -> EvalResult:",
            "    time_limit: float | None,\n    keep_tours: bool = False,",
        ),
        (
            "        results.append(\n"
            "            InstanceResult(n, True, length, length / references[run.index], run.seconds)\n"
            "        )",
            "        results.append(\n"
            "            InstanceResult(\n"
            "                n, True, length, length / references[run.index], run.seconds,\n"
            "                tour=list(tour) if keep_tours else None,\n"
            "            )\n"
            "        )",
            "tour=list(tour) if keep_tours else None",
        ),
        (
            "    limits: SandboxLimits = DEFAULT_LIMITS,\n) -> EvalResult:",
            "    limits: SandboxLimits = DEFAULT_LIMITS,\n    keep_tours: bool = False,\n) -> EvalResult:",
            "    limits: SandboxLimits = DEFAULT_LIMITS,\n    keep_tours: bool = False,",
        ),
        (
            "    return _score(outcome, instance_set, references, time_limit)",
            "    return _score(outcome, instance_set, references, time_limit, keep_tours)",
            "time_limit, keep_tours)",
        ),
    ],
    "cli.py": [
        (
            "    source = Path(args.file).read_text()\n",
            '    source = Path(args.file).read_text(encoding="utf-8")\n',
            'Path(args.file).read_text(encoding="utf-8")',
        ),
        (
            "from .llmclient import PRESETS, LLMError, resolve_model\n",
            "from . import manual\nfrom .llmclient import PRESETS, LLMError, resolve_model\n",
            "from . import manual",
        ),
        (
            "    p.set_defaults(func=cmd_report)\n\n    args = parser.parse_args(argv)",
            "    p.set_defaults(func=cmd_report)\n\n    manual.register(sub)\n\n    args = parser.parse_args(argv)",
            "manual.register(sub)",
        ),
    ],
    "runlog.py": [
        (
            '(self.directory / "best.py").write_text(source.rstrip() + "\\n")',
            '(self.directory / "best.py").write_text(source.rstrip() + "\\n", encoding="utf-8")',
            'source.rstrip() + "\\n", encoding="utf-8")',
        ),
    ],
    "seeds/__init__.py": [
        (
            "    return path.read_text()",
            '    return path.read_text(encoding="utf-8")',
            'path.read_text(encoding="utf-8")',
        ),
    ],
    "llmclient.py": [
        (
            "    for line in p.read_text().splitlines():",
            '    for line in p.read_text(encoding="utf-8").splitlines():',
            'p.read_text(encoding="utf-8").splitlines()',
        ),
        (
            "        data = json.loads(path.read_text())",
            '        data = json.loads(path.read_text(encoding="utf-8"))',
            'json.loads(path.read_text(encoding="utf-8"))',
        ),
    ],
}


def patch_file(path: Path, edits) -> list[str]:
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    log = []
    for old, new, marker in edits:
        if marker in text:
            log.append("already done")
            continue
        if text.count(old) != 1:
            raise SystemExit(
                f"STOPPED: {path} does not contain the expected text exactly once:\n---\n{old}\n---\n"
                "Nothing was changed in this file. Send this message back to Claude."
            )
        text = text.replace(old, new)
        log.append("patched")
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    return log


def main() -> None:
    if not PKG.is_dir():
        raise SystemExit(f"Run this from the project root (the folder containing src/). Not found: {PKG}")
    for rel, edits in PATCHES.items():
        path = PKG / rel
        if not path.exists():
            raise SystemExit(f"STOPPED: {path} not found.")
        log = patch_file(path, edits)
        py_compile.compile(str(path), doraise=True)
        print(f"{rel:<22} {', '.join(log)}")
    for rel in ("manual.py", "safety.py"):
        if not (PKG / rel).exists():
            raise SystemExit(f"Missing {PKG / rel}. Did you unzip the new files into the project root?")
    print("\nDone. Next: pytest")


if __name__ == "__main__":
    main()
