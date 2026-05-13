"""Environment loading helpers for the ML service."""

from __future__ import annotations

from pathlib import Path
from os import PathLike
from typing import Iterable, List


ML_SERVICE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ML_SERVICE_ROOT.parent


def load_ml_environment(
    *,
    override: bool = False,
    env_paths: Iterable[str | PathLike[str]] | None = None,
) -> List[Path]:
    """Load service-local and repo-level env files, returning paths that existed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return []

    loaded: List[Path] = []
    paths = env_paths or (ML_SERVICE_ROOT / ".env", REPO_ROOT / ".env")
    for raw_path in paths:
        env_path = Path(raw_path)
        if env_path.exists():
            load_dotenv(env_path, override=override)
            loaded.append(env_path)
    return loaded
