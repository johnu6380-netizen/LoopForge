"""Seed candidates. These are plain source files so they can be treated exactly
like any candidate the search loop later generates."""

from pathlib import Path

TSP_SEED_DIR = Path(__file__).parent / "tsp"


def tsp_seed_names() -> list[str]:
    return sorted(p.stem for p in TSP_SEED_DIR.glob("*.py") if not p.name.startswith("_"))


def load_tsp_seed_source(name: str) -> str:
    path = TSP_SEED_DIR / f"{name}.py"
    if not path.exists():
        raise KeyError(f"no TSP seed named {name!r}; have {tsp_seed_names()}")
    return path.read_text(encoding="utf-8")
