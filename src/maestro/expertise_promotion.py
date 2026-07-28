from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .expertise import candidate_expertise_statuses
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    file_sha256,
    pretty_json,
    read_json,
    safe_target,
    sha256_bytes,
    sha256_text,
)

PROMOTION_DECISION_VERSION = "maestro_expertise_promotion_decision_v1"
PROMOTION_DECISION_PLAN_VERSION = (
    "maestro_expertise_promotion_decision_plan_v1"
)
PROMOTION_DECISION_FILENAME = "promotion-decision.json"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLAN_FIELDS = {
    "schema_version",
    "command",
    "repo_realpath",
    "candidate_id",
    "candidate_digest",
    "decision",
    "reason",
    "operation",
    "warnings",
    "writes_performed",
    "plan_id",
    "plan_digest",
}


def _decision_path(repo: Path, candidate_id: str) -> Path:
    if (
        not isinstance(candidate_id, str)
        or ID_PATTERN.fullmatch(candidate_id) is None
    ):
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_ID_INVALID",
            "candidate_id must be a lowercase ASCII ID.",
        )
    return safe_target(
        repo,
        (
            ".maestro/state/candidates/expertise/"
            f"{candidate_id}/{PROMOTION_DECISION_FILENAME}"
        ),
    )


def read_expertise_promotion_decision(
    repo_path: str | Path,
    *,
    candidate_id: str,
    candidate_digest: str | None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    path = _decision_path(repo, candidate_id)
    if path.is_symlink():
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_SYMLINK_UNSAFE",
            "Promotion decision markers may not be symlinks.",
        )
    if not path.is_file():
        return {
            "status": "pending",
            "reason": None,
            "matches_current_candidate": True,
        }
    value = read_json(path)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "candidate_id",
            "candidate_digest",
            "status",
            "reason",
        }
        or value.get("schema_version") != PROMOTION_DECISION_VERSION
        or value.get("candidate_id") != candidate_id
        or value.get("status") != "declined"
        or not isinstance(value.get("candidate_digest"), str)
        or re.fullmatch(r"[a-f0-9]{64}", value["candidate_digest"]) is None
        or not isinstance(value.get("reason"), str)
        or not value["reason"].strip()
        or len(value["reason"]) > 200
    ):
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_INVALID",
            "Promotion decision marker does not satisfy its bounded contract.",
        )
    matches = (
        isinstance(candidate_digest, str)
        and value["candidate_digest"] == candidate_digest
    )
    return {
        "status": "declined" if matches else "pending",
        "reason": value["reason"] if matches else None,
        "matches_current_candidate": matches,
        "previous_candidate_status": (
            None if matches else "declined"
        ),
    }


def _finalize_plan(base: dict[str, Any]) -> dict[str, Any]:
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def build_expertise_promotion_decision_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    decision: str,
    reason: str | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    if decision not in {"decline", "reconsider"}:
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_INVALID",
            "decision must be decline or reconsider.",
        )
    runtime = candidate_expertise_statuses(repo).get(candidate_id, {})
    candidate_digest = runtime.get("definition_digest")
    if not isinstance(candidate_digest, str):
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_CANDIDATE_UNAVAILABLE",
            "A current validated candidate digest is required.",
        )
    path = _decision_path(repo, candidate_id)
    relative_path = path.relative_to(repo).as_posix()
    before = file_sha256(path)
    normalized_reason: str | None = None
    if decision == "decline":
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or len(reason.strip()) > 200
            or any(character in reason for character in "\r\n\x00")
        ):
            raise MaestroError(
                "EXPERTISE_PROMOTION_DECISION_REASON_INVALID",
                "Decline requires one non-empty line of at most 200 characters.",
            )
        normalized_reason = reason.strip()
        content = pretty_json(
            {
                "schema_version": PROMOTION_DECISION_VERSION,
                "candidate_id": candidate_id,
                "candidate_digest": candidate_digest,
                "status": "declined",
                "reason": normalized_reason,
            }
        )
        encoded = content.encode("utf-8")
        operation = {
            "op": "create" if before is None else "replace",
            "path": relative_path,
            "before_sha256": before,
            "after_sha256": sha256_bytes(encoded),
            "content": content,
        }
    else:
        if before is None:
            raise MaestroError(
                "EXPERTISE_PROMOTION_DECISION_NOT_FOUND",
                "There is no declined promotion decision to reconsider.",
            )
        operation = {
            "op": "delete",
            "path": relative_path,
            "before_sha256": before,
            "after_sha256": None,
            "content": None,
        }
    return _finalize_plan(
        {
            "schema_version": PROMOTION_DECISION_PLAN_VERSION,
            "command": "expertise-promotion-decision",
            "repo_realpath": str(repo),
            "candidate_id": candidate_id,
            "candidate_digest": candidate_digest,
            "decision": decision,
            "reason": normalized_reason,
            "operation": operation,
            "warnings": [
                (
                    "Declining suppresses the five-use global-promotion prompt "
                    "only for this exact candidate digest."
                ),
                (
                    "A changed candidate becomes pending again; reconsidering "
                    "removes the decision marker explicitly."
                ),
            ],
            "writes_performed": False,
        }
    )


def apply_expertise_promotion_decision_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = (
        copy.deepcopy(plan_path)
        if isinstance(plan_path, dict)
        else read_json(Path(plan_path).expanduser().resolve())
    )
    if (
        not isinstance(plan, dict)
        or set(plan) != PLAN_FIELDS
        or plan.get("schema_version") != PROMOTION_DECISION_PLAN_VERSION
        or plan.get("command") != "expertise-promotion-decision"
        or plan.get("writes_performed") is not False
    ):
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_PLAN_INVALID",
            "Unsupported Expertise promotion decision plan.",
            exit_code=3,
        )
    unsigned = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(unsigned))
    if plan.get("plan_id") != digest[:20] or plan.get("plan_digest") != digest:
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_PLAN_TAMPERED",
            "Promotion decision plan digest does not match its contents.",
            exit_code=3,
        )
    repo = ensure_repo(repo_override or plan["repo_realpath"])
    if str(repo) != plan["repo_realpath"]:
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_REPO_MISMATCH",
            "Promotion decision plan belongs to a different repository.",
            exit_code=3,
        )
    fresh = build_expertise_promotion_decision_plan(
        repo,
        candidate_id=plan["candidate_id"],
        decision=plan["decision"],
        reason=plan["reason"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_PLAN_STALE",
            "Candidate or decision marker changed after preview.",
            exit_code=3,
        )
    operation = plan["operation"]
    target = _decision_path(repo, plan["candidate_id"])
    if (
        operation.get("path") != target.relative_to(repo).as_posix()
        or file_sha256(target) != operation.get("before_sha256")
    ):
        raise MaestroError(
            "EXPERTISE_PROMOTION_DECISION_PLAN_STALE",
            "Promotion decision marker changed after preview.",
            exit_code=3,
        )
    if operation["op"] == "delete":
        target.unlink()
        status = "pending"
    else:
        content = operation.get("content")
        if (
            not isinstance(content, str)
            or sha256_bytes(content.encode("utf-8"))
            != operation.get("after_sha256")
        ):
            raise MaestroError(
                "EXPERTISE_PROMOTION_DECISION_PLAN_TAMPERED",
                "Promotion decision content does not match its digest.",
                exit_code=3,
            )
        atomic_write(target, content.encode("utf-8"))
        status = "declined"
    return {
        "schema_version": "maestro_expertise_promotion_decision_result_v1",
        "status": status,
        "candidate_id": plan["candidate_id"],
        "candidate_digest": plan["candidate_digest"],
        "writes_performed": True,
    }
