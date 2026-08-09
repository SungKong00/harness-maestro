from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .execution_contracts import normalize_execution_contract
from .task_coverage import validate_task_coverage
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    safe_target,
    sha256_text,
)

COVERAGE_PROJECTION_VERSION = "maestro_coverage_projection_v1"
PROJECTABLE_KINDS = {
    "project-fact",
    "owner-decision",
    "runtime-verification",
    "checker",
    "convention",
    "deferred-explicit",
    "out-of-scope-explicit",
}
PROJECTION_FIELDS = {
    "schema_version",
    "projection_id",
    "coverage_id",
    "plan_id",
    "goal_digest",
    "entries",
    "writes_performed",
}
ENTRY_FIELDS = {
    "item_id",
    "allocation_kind",
    "target_ref",
    "evidence_kind",
    "evidence_ref",
    "evidence_digest",
    "authority_ref",
    "reason",
}
DRAFT_FIELDS = {"items"}
DRAFT_ENTRY_FIELDS = {
    "item_id",
    "target_ref",
    "evidence_ref",
    "authority_ref",
    "reason",
}


def _digest(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload[field] = ""
    return sha256_text(canonical_json(payload))


def _line(value: Any, maximum: int = 1_000) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and "\x00" not in value
        and "\r" not in value
        and "\n" not in value
    )


def _route_plan(
    plan: Any,
    *,
    repo: Path,
    research_bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    context = normalize_execution_contract(
        plan,
        repo_path=repo,
        research_bundle=research_bundle,
    )
    if context["status"] != "PASS":
        first = context["issues"][0]
        raise MaestroError(first["code"], first["message"])
    return context["route_plan"]


def _expected_allocations(
    coverage: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for item in coverage["items"]:
        for allocation in item["allocations"]:
            if allocation["kind"] not in PROJECTABLE_KINDS:
                continue
            key = (item["item_id"], allocation["target_ref"])
            if key in expected:
                raise MaestroError(
                    "COVERAGE_PROJECTION_ALLOCATION_DUPLICATE",
                    "Projectable Coverage allocations must be unique per item and target.",
                )
            expected[key] = allocation
    return expected


def _file_entry(
    repo: Path,
    *,
    item_id: str,
    allocation: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    relative_path = allocation["target_ref"].split(":", 1)[1].split("#", 1)[0]
    if draft["evidence_ref"] != relative_path:
        raise MaestroError(
            "COVERAGE_PROJECTION_FILE_REF_MISMATCH",
            "Repository evidence must name the exact path in the Coverage allocation.",
        )
    target = safe_target(repo, relative_path)
    if not target.is_file() or target.is_symlink():
        raise MaestroError(
            "COVERAGE_PROJECTION_FILE_INVALID",
            f"Projected repository evidence is unavailable: {relative_path}.",
        )
    expected_authority = (
        f"convention:{relative_path}"
        if allocation["kind"] == "convention"
        else "repository-state"
    )
    if draft["authority_ref"] != expected_authority:
        raise MaestroError(
            "COVERAGE_PROJECTION_AUTHORITY_INVALID",
            f"{allocation['kind']} requires authority_ref {expected_authority}.",
        )
    return {
        "item_id": item_id,
        "allocation_kind": allocation["kind"],
        "target_ref": allocation["target_ref"],
        "evidence_kind": "repository-file",
        "evidence_ref": relative_path,
        "evidence_digest": file_sha256(target),
        "authority_ref": expected_authority,
        "reason": draft["reason"].strip(),
    }


def _attestation_entry(
    repo: Path,
    *,
    item_id: str,
    allocation: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    authority_ref = draft["authority_ref"]
    decision_path = (
        authority_ref.removeprefix("owner_decision:")
        if isinstance(authority_ref, str)
        else ""
    )
    if (
        not _line(authority_ref, 500)
        or not authority_ref.startswith("owner_decision:")
        or not decision_path
        or draft["evidence_ref"] != authority_ref
    ):
        raise MaestroError(
            "COVERAGE_PROJECTION_OWNER_AUTHORITY_REQUIRED",
            (
                "Owner decisions, deferrals, and exclusions require one exact "
                "owner_decision:<repository-relative-file> reference."
            ),
        )
    try:
        target = safe_target(repo, decision_path)
    except MaestroError as exc:
        raise MaestroError(
            "COVERAGE_PROJECTION_OWNER_AUTHORITY_INVALID",
            (
                "Owner-decision authority must be a safe repository-relative "
                "decision file."
            ),
        ) from exc
    if target.is_symlink() or not target.is_file():
        raise MaestroError(
            "COVERAGE_PROJECTION_OWNER_AUTHORITY_INVALID",
            (
                "Owner-decision authority requires an existing regular "
                "repository file."
            ),
        )
    return {
        "item_id": item_id,
        "allocation_kind": allocation["kind"],
        "target_ref": allocation["target_ref"],
        "evidence_kind": "owner-attestation",
        "evidence_ref": authority_ref,
        "evidence_digest": file_sha256(target),
        "authority_ref": authority_ref,
        "reason": draft["reason"].strip(),
    }


def _verification_entry(
    plan: dict[str, Any],
    *,
    item_id: str,
    allocation: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    expected_authority = f"plan:{plan['plan_id']}"
    if (
        draft["evidence_ref"] != allocation["target_ref"]
        or draft["authority_ref"] != expected_authority
        or not any(
            assignment.get("kind") == "verification"
            and assignment.get("executor_id") == "verifier"
            for assignment in plan["assignments"]
        )
    ):
        raise MaestroError(
            "COVERAGE_PROJECTION_CHECK_BINDING_INVALID",
            "A projected check must bind its exact target to this plan's verifier.",
        )
    entry = {
        "item_id": item_id,
        "allocation_kind": allocation["kind"],
        "target_ref": allocation["target_ref"],
        "evidence_kind": "planned-check",
        "evidence_ref": allocation["target_ref"],
        "evidence_digest": "",
        "authority_ref": expected_authority,
        "reason": draft["reason"].strip(),
    }
    entry["evidence_digest"] = _digest(entry, "evidence_digest")
    return entry


def build_coverage_projection(
    repo_path: str | Path,
    *,
    goal: str,
    coverage: Any,
    plan: Any,
    draft: Any,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build typed evidence for the Coverage allocations a route cannot infer."""

    repo = ensure_repo(repo_path)
    coverage_validation = validate_task_coverage(
        coverage,
        goal=goal,
        repo_path=repo,
        require_current_revision=True,
    )
    if coverage_validation["status"] != "PASS":
        first = coverage_validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    route = _route_plan(
        plan,
        repo=repo,
        research_bundle=research_bundle,
    )
    if coverage["goal"] != route["goal"]:
        raise MaestroError(
            "COVERAGE_PROJECTION_GOAL_MISMATCH",
            "Coverage and execution plan must bind the same goal.",
        )
    if not isinstance(draft, dict) or set(draft) != DRAFT_FIELDS:
        raise MaestroError(
            "COVERAGE_PROJECTION_DRAFT_INVALID",
            "Projection draft must contain only items.",
        )
    draft_items = draft["items"]
    if not isinstance(draft_items, list):
        raise MaestroError(
            "COVERAGE_PROJECTION_DRAFT_INVALID",
            "Projection draft items must be a list.",
        )

    expected = _expected_allocations(coverage)
    declared: dict[tuple[str, str], dict[str, Any]] = {}
    for item in draft_items:
        if (
            not isinstance(item, dict)
            or set(item) != DRAFT_ENTRY_FIELDS
            or not _line(item.get("item_id"), 128)
            or not _line(item.get("target_ref"), 512)
            or not _line(item.get("evidence_ref"), 1_000)
            or not _line(item.get("authority_ref"), 500)
            or not _line(item.get("reason"), 1_000)
        ):
            raise MaestroError(
                "COVERAGE_PROJECTION_DRAFT_INVALID",
                "Every projection item must use the closed bounded draft fields.",
            )
        key = (item["item_id"], item["target_ref"])
        if key in declared:
            raise MaestroError(
                "COVERAGE_PROJECTION_DRAFT_DUPLICATE",
                "Projection draft entries must be unique.",
            )
        declared[key] = item
    if set(declared) != set(expected):
        missing = sorted(set(expected) - set(declared))
        extra = sorted(set(declared) - set(expected))
        raise MaestroError(
            "COVERAGE_PROJECTION_SET_MISMATCH",
            f"Projection must cover every and only projectable allocation; missing={missing}, extra={extra}.",
        )

    entries: list[dict[str, Any]] = []
    for key in sorted(expected):
        item_id, _ = key
        allocation = expected[key]
        item = declared[key]
        if allocation["kind"] in {"project-fact", "convention"}:
            entry = _file_entry(
                repo,
                item_id=item_id,
                allocation=allocation,
                draft=item,
            )
        elif allocation["kind"] in {
            "owner-decision",
            "deferred-explicit",
            "out-of-scope-explicit",
        }:
            entry = _attestation_entry(
                repo,
                item_id=item_id,
                allocation=allocation,
                draft=item,
            )
        else:
            entry = _verification_entry(
                route,
                item_id=item_id,
                allocation=allocation,
                draft=item,
            )
        entries.append(entry)

    result = {
        "schema_version": COVERAGE_PROJECTION_VERSION,
        "projection_id": "",
        "coverage_id": coverage["coverage_id"],
        "plan_id": route["plan_id"],
        "goal_digest": coverage["goal_digest"],
        "entries": entries,
        "writes_performed": False,
    }
    result["projection_id"] = _digest(result, "projection_id")
    return result


def validate_coverage_projection(
    value: Any,
    *,
    repo_path: str | Path,
    goal: str,
    coverage: Any,
    plan: Any,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild typed projection evidence against current repository state."""

    issues: list[dict[str, str]] = []
    if (
        not isinstance(value, dict)
        or set(value) != PROJECTION_FIELDS
        or value.get("schema_version") != COVERAGE_PROJECTION_VERSION
        or value.get("writes_performed") is not False
        or not isinstance(value.get("entries"), list)
    ):
        issues.append(
            {
                "code": "COVERAGE_PROJECTION_INVALID",
                "path": "$",
                "message": "Coverage projection fields are invalid.",
            }
        )
    if not issues:
        draft = {
            "items": [
                {
                    "item_id": entry.get("item_id"),
                    "target_ref": entry.get("target_ref"),
                    "evidence_ref": entry.get("evidence_ref"),
                    "authority_ref": entry.get("authority_ref"),
                    "reason": entry.get("reason"),
                }
                for entry in value["entries"]
                if isinstance(entry, dict)
            ]
        }
        if (
            len(draft["items"]) != len(value["entries"])
            or any(
                not isinstance(entry, dict)
                or set(entry) != ENTRY_FIELDS
                for entry in value["entries"]
            )
        ):
            issues.append(
                {
                    "code": "COVERAGE_PROJECTION_ENTRY_INVALID",
                    "path": "entries",
                    "message": "Coverage projection entries are invalid.",
                }
            )
        else:
            try:
                expected = build_coverage_projection(
                    repo_path,
                    goal=goal,
                    coverage=coverage,
                    plan=plan,
                    draft=draft,
                    research_bundle=research_bundle,
                )
            except MaestroError as exc:
                issues.append(
                    {
                        "code": exc.code,
                        "path": "entries",
                        "message": exc.message,
                    }
                )
            else:
                if expected != value:
                    issues.append(
                        {
                            "code": "COVERAGE_PROJECTION_MISMATCH",
                            "path": "$",
                            "message": "Coverage projection no longer matches its bound evidence.",
                        }
                    )
    return {
        "schema_version": "maestro_coverage_projection_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "projection_id": (
            value.get("projection_id")
            if isinstance(value, dict)
            else None
        ),
        "issues": issues,
        "writes_performed": False,
    }
