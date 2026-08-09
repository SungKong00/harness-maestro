from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .errors import MaestroError
from .util import ensure_repo, safe_target


def resolve_authorized_write_roots(
    repo_path: str | Path,
    allowed_paths: Iterable[Any],
) -> list[Path]:
    """Resolve one Decision scope into existing, non-symlink directories."""

    repo = ensure_repo(repo_path)
    values = list(allowed_paths)
    if (
        not values
        or not all(
            isinstance(value, str)
            and value.strip()
            and "\x00" not in value
            and "\r" not in value
            and "\n" not in value
            for value in values
        )
        or len(values) != len(set(values))
    ):
        raise MaestroError(
            "EXECUTION_SCOPE_INVALID",
            "Decision allowed_paths must be a non-empty unique string list.",
        )

    roots: list[Path] = []
    for relative_path in values:
        try:
            target = safe_target(repo, relative_path)
        except MaestroError as exc:
            raise MaestroError(
                "EXECUTION_SCOPE_INVALID",
                "Decision allowed_paths must stay inside the repository.",
            ) from exc
        if target.is_symlink() or not target.is_dir():
            raise MaestroError(
                "EXECUTION_SCOPE_INVALID",
                (
                    "Decision allowed_paths must name existing regular "
                    f"repository directories: {relative_path}."
                ),
            )
        resolved = target.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return roots
