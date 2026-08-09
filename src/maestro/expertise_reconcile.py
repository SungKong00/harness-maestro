from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .release import (
    canonical_skill_execution_record,
    load_source_release_manifest,
    load_source_registry,
    skill_record,
)
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    file_sha256,
    pretty_json,
    read_json,
    safe_target,
    sha256_text,
)

RECONCILE_PLAN_VERSION = "maestro_expertise_reconcile_plan_v1"
_PLAN_FIELDS = {
    "schema_version",
    "command",
    "repo_realpath",
    "source_root",
    "source_release_id",
    "project_sha256",
    "updated_active_pack_paths",
    "moves",
    "conflicts",
    "warnings",
    "writes_performed",
    "plan_id",
    "plan_digest",
}


def _finalize_plan(value: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(payload))
    return {**payload, "plan_id": digest[:16], "plan_digest": digest}


def _active_paths(project: dict[str, Any]) -> list[str]:
    expertise = project.get("expertise")
    paths = expertise.get("active_pack_paths") if isinstance(expertise, dict) else None
    if (
        not isinstance(paths, list)
        or len(paths) != len(set(paths))
        or any(not isinstance(path, str) or not path for path in paths)
    ):
        raise MaestroError(
            "EXPERTISE_RECONCILE_PROJECT_INVALID",
            "project.json expertise active_pack_paths is invalid.",
        )
    return paths


def build_expertise_reconcile_plan(
    repo_path: str | Path,
    *,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    """Plan safe removal of inactive or globally superseded Host-visible Packs."""

    repo = ensure_repo(repo_path)
    source = ensure_repo(source_root or repo)
    source_manifest = load_source_release_manifest(source)
    project_path = safe_target(repo, ".maestro/project.json")
    project = read_json(project_path)
    active_paths = _active_paths(project)
    active_set = set(active_paths)
    registry = load_source_registry(source)
    bundled_by_id = {
        pack["expertise_pack_id"]: pack
        for pack in registry["expertise_packs"]
    }
    skills_root = safe_target(repo, ".agents/skills")
    moves: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    if skills_root.is_dir() and not skills_root.is_symlink():
        for local_root in sorted(skills_root.iterdir()):
            pack_path = local_root / "maestro-pack.json"
            activation_path = local_root / "activation.json"
            if (
                local_root.is_symlink()
                or not local_root.is_dir()
                or not pack_path.is_file()
                or pack_path.is_symlink()
                or not activation_path.is_file()
                or activation_path.is_symlink()
            ):
                continue
            relative_pack = pack_path.relative_to(repo).as_posix()
            pack = read_json(pack_path)
            pack_id = pack.get("expertise_pack_id")
            version = pack.get("version")
            if not isinstance(pack_id, str) or not isinstance(version, int):
                conflicts.append(
                    {
                        "skill_root": local_root.relative_to(repo).as_posix(),
                        "reason": "invalid-publication-identity",
                    }
                )
                continue
            is_active = relative_pack in active_set
            bundled = bundled_by_id.get(pack_id)
            reason: str | None = None
            global_skill_root: Path | None = None
            execution_matches = False
            if bundled is not None:
                global_skill_root = safe_target(
                    source,
                    f"skills/{bundled['skill_id']}",
                )
                if global_skill_root.is_dir():
                    execution_matches = (
                        canonical_skill_execution_record(
                            local_root,
                            source_skill_id=pack["skill_id"],
                            canonical_skill_id=bundled["skill_id"],
                        )
                        == canonical_skill_execution_record(
                            global_skill_root,
                            source_skill_id=bundled["skill_id"],
                            canonical_skill_id=bundled["skill_id"],
                        )
                    )
            if is_active and bundled is not None and execution_matches:
                reason = "globally-superseded"
            elif not is_active:
                reason = "inactive-publication"
            elif bundled is not None and not execution_matches:
                conflicts.append(
                    {
                        "expertise_pack_id": pack_id,
                        "skill_root": local_root.relative_to(repo).as_posix(),
                        "global_skill_root": (
                            str(global_skill_root)
                            if global_skill_root is not None
                            else None
                        ),
                        "reason": "active-content-differs-from-global",
                    }
                )
            if reason is None:
                continue
            tree = skill_record(local_root)
            destination = (
                f".agents/archive/expertise/{local_root.name}-"
                f"v{version}-{tree['sha256'][:12]}"
            )
            destination_path = safe_target(repo, destination)
            if destination_path.exists():
                conflicts.append(
                    {
                        "expertise_pack_id": pack_id,
                        "skill_root": local_root.relative_to(repo).as_posix(),
                        "archive_path": destination,
                        "reason": "archive-target-exists",
                    }
                )
                continue
            moves.append(
                {
                    "expertise_pack_id": pack_id,
                    "pack_path": relative_pack,
                    "source": local_root.relative_to(repo).as_posix(),
                    "destination": destination,
                    "reason": reason,
                    "was_active": is_active,
                    "tree": tree,
                }
            )

    removed_paths = {
        move["pack_path"] for move in moves if move["was_active"]
    }
    base = {
        "schema_version": RECONCILE_PLAN_VERSION,
        "command": "expertise-reconcile",
        "repo_realpath": str(repo),
        "source_root": str(source),
        "source_release_id": source_manifest["release_id"],
        "project_sha256": file_sha256(project_path),
        "moves": moves,
        "conflicts": conflicts,
        "warnings": [
            (
                "Only inactive publications and active publications whose "
                "Host-executable content exactly matches bundled global "
                "Expertise are moved out of Host discovery."
            ),
            (
                "Content conflicts remain untouched and require an explicit "
                "owner decision."
            ),
        ],
        "writes_performed": False,
    }
    return _finalize_plan(
        {
            **base,
            "updated_active_pack_paths": [
                path for path in active_paths if path not in removed_paths
            ],
        }
    )


def apply_expertise_reconcile_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    if isinstance(plan_path, dict):
        supplied = copy.deepcopy(plan_path)
    else:
        supplied = read_json(Path(plan_path).expanduser().resolve())
    if set(supplied) != _PLAN_FIELDS:
        raise MaestroError(
            "EXPERTISE_RECONCILE_PLAN_INVALID",
            "Expertise reconcile plan fields are invalid.",
            exit_code=3,
        )
    repo = ensure_repo(repo_override or supplied["repo_realpath"])
    if str(repo) != supplied["repo_realpath"]:
        raise MaestroError(
            "EXPERTISE_RECONCILE_REPO_MISMATCH",
            "Reconcile plan belongs to another repository.",
            exit_code=3,
        )
    fresh = build_expertise_reconcile_plan(
        repo,
        source_root=supplied["source_root"],
    )
    if supplied != fresh:
        raise MaestroError(
            "EXPERTISE_RECONCILE_PLAN_STALE",
            "Expertise storage changed after preview.",
            exit_code=3,
        )
    if supplied["conflicts"] and not supplied["moves"]:
        raise MaestroError(
            "EXPERTISE_RECONCILE_DECISION_REQUIRED",
            (
                "An owner decision is required for the remaining content "
                "conflicts; no safe move is available."
            ),
            exit_code=3,
        )

    project_path = safe_target(repo, ".maestro/project.json")
    project_before = project_path.read_bytes()
    moved: list[tuple[Path, Path]] = []
    try:
        for operation in supplied["moves"]:
            source = safe_target(repo, operation["source"])
            destination = safe_target(repo, operation["destination"])
            if skill_record(source) != operation["tree"] or destination.exists():
                raise MaestroError(
                    "EXPERTISE_RECONCILE_PLAN_STALE",
                    "Expertise archive source or destination changed after preview.",
                    exit_code=3,
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
            moved.append((source, destination))

        project = read_json(project_path)
        project["expertise"]["active_pack_paths"] = supplied[
            "updated_active_pack_paths"
        ]
        atomic_write(project_path, pretty_json(project).encode("utf-8"))
    except BaseException:
        atomic_write(project_path, project_before)
        for source, destination in reversed(moved):
            if destination.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                destination.rename(source)
        raise

    return {
        "schema_version": "maestro_expertise_reconcile_result_v1",
        "status": (
            "needs_decision" if supplied["conflicts"] else "applied"
        ),
        "repo_root": str(repo),
        "archived": [
            {
                "expertise_pack_id": item["expertise_pack_id"],
                "archive_path": item["destination"],
                "reason": item["reason"],
            }
            for item in supplied["moves"]
        ],
        "conflicts": supplied["conflicts"],
        "changed_paths": [
            ".maestro/project.json",
            *[
                item["source"] for item in supplied["moves"]
            ],
            *[
                item["destination"] for item in supplied["moves"]
            ],
        ],
        "writes_performed": True,
    }
