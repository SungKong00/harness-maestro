from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import MaestroError
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

VERIFICATION_APPROVAL_PLAN_VERSION = "maestro_verification_approval_plan_v1"
PROJECT_PATH = ".maestro/project.json"


def _candidate_id(candidate: dict[str, str]) -> str:
    return sha256_text(
        canonical_json(
            {
                "name": candidate["name"],
                "command": candidate["command"],
            }
        )
    )[:20]


def _project(repo: Path) -> tuple[Path, dict[str, Any]]:
    path = safe_target(repo, PROJECT_PATH)
    project = read_json(path)
    commands = project.get("commands")
    approved = project.get("verification_commands")
    if not isinstance(commands, list) or not isinstance(approved, list):
        raise MaestroError(
            "PROJECT_STATE_INVALID",
            "commands and verification_commands must be lists.",
        )
    return path, project


def _valid_candidate(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"name", "command", "status"}
        and isinstance(value.get("name"), str)
        and bool(value["name"].strip())
        and isinstance(value.get("command"), str)
        and bool(value["command"].strip())
        and value.get("status") == "candidate"
    )


def verification_inventory(repo_path: str | Path) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _path, project = _project(repo)
    approved_by_name = {
        item["name"]: item["command"]
        for item in project["verification_commands"]
        if isinstance(item, dict)
        and set(item) == {"name", "command"}
        and isinstance(item.get("name"), str)
        and isinstance(item.get("command"), str)
    }
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in project["commands"]:
        if not _valid_candidate(item):
            continue
        candidate = {
            "name": item["name"].strip(),
            "command": item["command"].strip(),
        }
        identifier = _candidate_id(candidate)
        if identifier in seen:
            continue
        seen.add(identifier)
        approved_command = approved_by_name.get(candidate["name"])
        status = (
            "approved"
            if approved_command == candidate["command"]
            else "conflict"
            if approved_command is not None
            else "candidate"
        )
        candidates.append(
            {
                "candidate_id": identifier,
                **candidate,
                "status": status,
                "approvable": status == "candidate",
            }
        )
    return {
        "schema_version": "maestro_verification_inventory_v1",
        "repo_root": str(repo),
        "candidates": candidates,
        "writes_performed": False,
    }


def build_verification_approval_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    project_path, project = _project(repo)
    inventory = verification_inventory(repo)
    matches = [
        item
        for item in inventory["candidates"]
        if item["candidate_id"] == candidate_id
    ]
    if len(matches) != 1:
        raise MaestroError(
            "VERIFICATION_CANDIDATE_NOT_FOUND",
            "The candidate ID does not identify one current detected command.",
        )
    candidate = matches[0]
    if candidate["status"] == "approved":
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "verification-approve",
            "status": "already_approved",
            "repo_root": str(repo),
            "candidate": candidate,
            "writes_performed": False,
        }
    if not candidate["approvable"]:
        raise MaestroError(
            "VERIFICATION_NAME_CONFLICT",
            "An approved verification command already uses this name with "
            "different content.",
        )

    updated = dict(project)
    updated["verification_commands"] = [
        *project["verification_commands"],
        {
            "name": candidate["name"],
            "command": candidate["command"],
        },
    ]
    operation = {
        "op": "write",
        "path": PROJECT_PATH,
        "before_sha256": file_sha256(project_path),
        "after_sha256": sha256_text(pretty_json(updated)),
        "content": pretty_json(updated),
    }
    base = {
        "schema_version": VERIFICATION_APPROVAL_PLAN_VERSION,
        "command": "verification-approve",
        "repo_root": str(repo),
        "candidate": {
            "candidate_id": candidate["candidate_id"],
            "name": candidate["name"],
            "command": candidate["command"],
        },
        "operations": [operation],
        "executes_command": False,
        "writes_performed": False,
    }
    digest = sha256_text(canonical_json(base))
    return {
        **base,
        "plan_id": digest[:20],
        "plan_digest": digest,
    }


def _load_plan(value: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return read_json(Path(value).expanduser().resolve())


def apply_verification_approval_plan(
    plan_or_path: dict[str, Any] | str | Path,
    repo_path: str | Path,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    plan = _load_plan(plan_or_path)
    required = {
        "schema_version",
        "command",
        "repo_root",
        "candidate",
        "operations",
        "executes_command",
        "writes_performed",
        "plan_id",
        "plan_digest",
    }
    if (
        set(plan) != required
        or plan.get("schema_version") != VERIFICATION_APPROVAL_PLAN_VERSION
        or plan.get("command") != "verification-approve"
        or plan.get("repo_root") != str(repo)
        or plan.get("executes_command") is not False
        or plan.get("writes_performed") is not False
    ):
        raise MaestroError(
            "VERIFICATION_APPROVAL_PLAN_INVALID",
            "The verification approval plan contract is invalid.",
        )
    base = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(base))
    if plan.get("plan_id") != digest[:20] or plan.get("plan_digest") != digest:
        raise MaestroError(
            "VERIFICATION_APPROVAL_PLAN_TAMPERED",
            "The verification approval plan digest does not match its content.",
        )
    candidate = plan.get("candidate")
    operations = plan.get("operations")
    if (
        not isinstance(candidate, dict)
        or set(candidate) != {"candidate_id", "name", "command"}
        or not all(
            isinstance(candidate.get(field), str) and candidate[field]
            for field in ("candidate_id", "name", "command")
        )
        or not isinstance(operations, list)
        or len(operations) != 1
    ):
        raise MaestroError(
            "VERIFICATION_APPROVAL_PLAN_INVALID",
            "The plan must contain one exact candidate and one project-state write.",
        )
    current_plan = build_verification_approval_plan(
        repo,
        candidate_id=candidate["candidate_id"],
    )
    if current_plan.get("status") == "already_approved":
        return current_plan
    if current_plan != plan:
        raise MaestroError(
            "VERIFICATION_APPROVAL_PLAN_STALE",
            "Project state or the detected command changed after preview.",
        )
    operation = operations[0]
    if (
        not isinstance(operation, dict)
        or set(operation)
        != {
            "op",
            "path",
            "before_sha256",
            "after_sha256",
            "content",
        }
        or operation.get("op") != "write"
        or operation.get("path") != PROJECT_PATH
        or not isinstance(operation.get("content"), str)
        or sha256_text(operation["content"]) != operation.get("after_sha256")
    ):
        raise MaestroError(
            "VERIFICATION_APPROVAL_PLAN_INVALID",
            "The project-state operation is invalid.",
        )
    project_path = safe_target(repo, PROJECT_PATH)
    if file_sha256(project_path) != operation.get("before_sha256"):
        raise MaestroError(
            "VERIFICATION_APPROVAL_PLAN_STALE",
            "Project state changed after preview.",
        )
    atomic_write(project_path, operation["content"].encode("utf-8"))
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "verification-approve",
        "status": "approved",
        "repo_root": str(repo),
        "candidate": candidate,
        "changed_paths": [PROJECT_PATH],
        "executes_command": False,
        "writes_performed": True,
    }
