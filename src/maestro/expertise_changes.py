from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .util import read_json, safe_target

CHANGE_KIND_TO_OPERATION = {
    "new-pack": "add-pack",
    "pack-merge": "merge-packs",
    "pack-split": "split-pack",
    "guide-addition": "add-guide",
    "guide-revision": "revise-guide",
    "guide-deprecation": "deprecate-guide",
    "guide-move": "move-guide",
    "guide-copy": "copy-guide",
    "trigger-adjustment": "adjust-triggers",
    "source-refresh": "refresh-sources",
    "evaluation-extension": "extend-evaluation",
}
OPERATION_LABELS = {
    "add-pack": ("+", "Pack 추가"),
    "merge-packs": ("+", "Pack 통합"),
    "split-pack": ("+", "Pack 분할"),
    "add-guide": ("+", "Guide 추가"),
    "revise-guide": ("~", "Guide 수정"),
    "deprecate-guide": ("−", "Guide 사용 중지"),
    "move-guide": ("→", "Guide 이동"),
    "copy-guide": ("⧉", "Guide 복사"),
    "adjust-triggers": ("~", "선택 조건 수정"),
    "refresh-sources": ("~", "출처 갱신"),
    "extend-evaluation": ("+", "검증 범위 확장"),
}
COMPLEX_OPERATIONS = {
    "merge-packs",
    "split-pack",
    "move-guide",
    "copy-guide",
}
MAX_CHANGE_SET_CANDIDATES = 100


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _raw_candidate_change(
    repo: Path,
    candidate_id: str,
) -> dict[str, Any] | None:
    candidate_path = safe_target(
        repo,
        (
            ".maestro/state/candidates/expertise/"
            f"{candidate_id}/candidate.json"
        ),
    )
    if candidate_path.is_symlink() or not candidate_path.is_file():
        return None
    candidate = read_json(candidate_path)
    change = candidate.get("component_change")
    return change if isinstance(change, dict) else None


def candidate_change_set_groups(
    repo: Path,
) -> dict[str, list[str]]:
    """Read candidate grouping without requiring every candidate to validate."""

    root = safe_target(repo, ".maestro/state/candidates/expertise")
    if root.is_symlink() or not root.is_dir():
        return {}
    groups: dict[str, list[str]] = defaultdict(list)
    for candidate_path in sorted(root.glob("*/candidate.json"))[
        :MAX_CHANGE_SET_CANDIDATES
    ]:
        if candidate_path.is_symlink() or not candidate_path.is_file():
            continue
        try:
            candidate = read_json(candidate_path)
        except MaestroError:
            continue
        change = candidate.get("component_change")
        change_set_id = (
            change.get("change_set_id")
            if isinstance(change, dict)
            else None
        )
        if isinstance(change_set_id, str) and change_set_id:
            groups[change_set_id].append(candidate_path.parent.name)
    return {
        change_set_id: sorted(candidate_ids)
        for change_set_id, candidate_ids in sorted(groups.items())
    }


def candidate_change_set_context(
    repo: Path,
    *,
    candidate_id: str,
) -> dict[str, Any]:
    """Return the lifecycle boundary for one candidate."""

    change = _raw_candidate_change(repo, candidate_id)
    change_set_id = (
        change.get("change_set_id")
        if isinstance(change, dict)
        else None
    )
    operation = (
        CHANGE_KIND_TO_OPERATION.get(change.get("kind"), "revise-guide")
        if isinstance(change, dict)
        else None
    )
    candidate_ids = (
        candidate_change_set_groups(repo).get(change_set_id, [])
        if isinstance(change_set_id, str)
        else []
    )
    if not candidate_ids:
        candidate_ids = [candidate_id]
    grouped = len(candidate_ids) > 1
    return {
        "change_set_id": change_set_id,
        "candidate_ids": candidate_ids,
        "grouped": grouped,
        "atomic_required": (
            grouped
            or operation in COMPLEX_OPERATIONS
        ),
        "operation": operation,
    }


def require_change_set(
    repo: Path,
    *,
    change_set_id: str,
) -> dict[str, Any]:
    """Resolve one explicit ChangeSet or fail without guessing its members."""

    if not isinstance(change_set_id, str) or not change_set_id:
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_ID_INVALID",
            "change_set_id must be a non-empty string.",
        )
    candidate_ids = candidate_change_set_groups(repo).get(change_set_id)
    if not candidate_ids:
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_NOT_FOUND",
            f"Expertise ChangeSet is missing: {change_set_id}",
        )
    operations = []
    for candidate_id in candidate_ids:
        change = _raw_candidate_change(repo, candidate_id)
        operation = (
            CHANGE_KIND_TO_OPERATION.get(
                change.get("kind"),
                "revise-guide",
            )
            if isinstance(change, dict)
            else None
        )
        operations.append(operation)
    grouped = len(candidate_ids) > 1
    atomic_required = grouped or any(
        operation in COMPLEX_OPERATIONS
        for operation in operations
    )
    if not atomic_required:
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_ATOMIC_NOT_REQUIRED",
            (
                "This candidate may be managed individually because its "
                "ChangeSet does not contain an atomic operation."
            ),
        )
    return {
        "change_set_id": change_set_id,
        "candidate_ids": candidate_ids,
        "grouped": grouped,
        "atomic_required": atomic_required,
        "operations": operations,
    }


def _candidate_state(candidate: dict[str, Any]) -> str:
    disposition = candidate.get("disposition")
    if isinstance(disposition, dict):
        return (
            "archived"
            if disposition.get("status") == "archived"
            else "rejected"
        )
    runtime_status = candidate.get("runtime_status")
    return (
        runtime_status
        if isinstance(runtime_status, str)
        else "invalid"
    )


def _operation(candidate: dict[str, Any]) -> dict[str, Any]:
    change = candidate.get("component_change")
    if not isinstance(change, dict):
        change = {"kind": "new-pack", "target_guide_id": None}
    operation_kind = CHANGE_KIND_TO_OPERATION.get(
        change.get("kind"),
        "revise-guide",
    )
    symbol, label = OPERATION_LABELS[operation_kind]
    pack_id = candidate.get("expertise_pack_id")
    source_pack_ids = list(change.get("source_pack_ids", []))
    target_pack_ids = list(change.get("target_pack_ids", []))
    if isinstance(pack_id, str) and not target_pack_ids:
        target_pack_ids = [pack_id]
    target_guide_id = change.get("target_guide_id")
    operation_id = change.get("operation_id")
    if not isinstance(operation_id, str):
        operation_id = f"{candidate.get('candidate_id')}:{operation_kind}"
    summary = change.get("summary")
    if not isinstance(summary, str):
        subject = target_guide_id or pack_id or candidate.get("candidate_id")
        summary = f"{label}: {subject}"
    return {
        "operation_id": operation_id,
        "kind": operation_kind,
        "symbol": symbol,
        "label": label,
        "summary": summary,
        "candidate_id": candidate.get("candidate_id"),
        "source_pack_ids": source_pack_ids,
        "target_pack_ids": target_pack_ids,
        "target_guide_id": target_guide_id,
    }


def _candidate_reason(candidate: dict[str, Any]) -> str:
    preview = candidate.get("pack_preview")
    if isinstance(preview, dict) and isinstance(preview.get("problem"), str):
        return preview["problem"]
    value = candidate.get("problem")
    return value if isinstance(value, str) else ""


def _globally_applied(candidate: dict[str, Any]) -> bool:
    adoption = candidate.get("global_adoption")
    return (
        isinstance(adoption, dict)
        and adoption.get("status") == "harness_source_applied"
    )


def expertise_change_sets(
    inventory: dict[str, Any],
    component_health: dict[str, Any],
) -> dict[str, Any]:
    """Project candidate state into lifecycle-aware ChangeSet views."""

    health_by_candidate = {
        item.get("candidate_id"): item
        for item in component_health.get("candidates", [])
        if isinstance(item, dict)
        and isinstance(item.get("candidate_id"), str)
    }
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in inventory.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        change = candidate.get("component_change")
        change_set_id = (
            change.get("change_set_id")
            if isinstance(change, dict)
            else None
        )
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str):
            continue
        groups[
            change_set_id
            if isinstance(change_set_id, str)
            else candidate_id
        ].append(candidate)

    change_sets: list[dict[str, Any]] = []
    pack_links: dict[str, list[str]] = defaultdict(list)
    for change_set_id, candidates in sorted(groups.items()):
        operations = [_operation(candidate) for candidate in candidates]
        candidate_ids = [
            candidate["candidate_id"] for candidate in candidates
        ]
        states = [_candidate_state(candidate) for candidate in candidates]
        affected_pack_ids = _unique(
            [
                pack_id
                for operation in operations
                for pack_id in [
                    *operation["source_pack_ids"],
                    *operation["target_pack_ids"],
                ]
            ]
        )
        health_items = [
            health_by_candidate.get(candidate_id, {})
            for candidate_id in candidate_ids
        ]
        archived = all(state == "archived" for state in states)
        unavailable_states = {
            "change_set_paused",
            "conflict",
            "expired",
            "invalid",
            "superseded",
        }
        paused = any(state in unavailable_states for state in states)
        grouped = len(candidates) > 1
        atomic_required = grouped or any(
            operation["kind"] in COMPLEX_OPERATIONS
            for operation in operations
        )
        if archived:
            state = "archived"
        elif any(item == "rejected" for item in states):
            state = "rejected"
        elif paused:
            state = "paused"
        elif all(item in {"published", "globally_promoted"} for item in states):
            state = "project_approved"
        else:
            state = "candidate"
        if state in {"candidate", "paused", "project_approved"}:
            for pack_id in affected_pack_ids:
                pack_links[pack_id].append(change_set_id)
        change_sets.append(
            {
                "schema_version": "maestro_expertise_change_set_v1",
                "change_set_id": change_set_id,
                "candidate_ids": candidate_ids,
                "state": state,
                "grouped": grouped,
                "atomic_required": atomic_required,
                "partial_approval_allowed": not atomic_required,
                "affected_pack_ids": affected_pack_ids,
                "operations": operations,
                "reason": " / ".join(
                    _candidate_reason(candidate)
                    for candidate in candidates
                    if _candidate_reason(candidate)
                ),
                "base_pins": [
                    {
                        "candidate_id": candidate["candidate_id"],
                        "definition_digest": candidate.get(
                            "definition_digest"
                        ),
                    }
                    for candidate in candidates
                ],
                "usage_evidence": {
                    "selected": sum(
                        item.get("component_selection_count", 0)
                        for item in health_items
                    ),
                    "assigned": sum(
                        item.get("component_assigned_count", 0)
                        for item in health_items
                    ),
                    "loaded": sum(
                        item.get("component_loaded_count", 0)
                        for item in health_items
                    ),
                    "applied": sum(
                        item.get("component_application_count", 0)
                        for item in health_items
                    ),
                    "verified": sum(
                        item.get("component_verified_count", 0)
                        for item in health_items
                    ),
                },
                "review_due": any(
                    item.get("review_due") is True for item in health_items
                ),
                "issues": _unique(
                    [
                        reason
                        for item in health_items
                        for reason in item.get("review_reasons", [])
                    ]
                    + (
                        [
                            "묶음 변경안은 일부 후보만 따로 승인할 수 없습니다."
                        ]
                        if atomic_required
                        else []
                    )
                    + (
                        [
                            "기준 Pack이 바뀌었거나 후보가 유효하지 않아 승인을 멈췄습니다."
                        ]
                        if paused
                        else []
                    )
                ),
                "project_approval": {
                    "status": (
                        "approved"
                        if state == "project_approved"
                        else "available"
                        if state == "candidate" and not atomic_required
                        else "group_review_required"
                        if state == "candidate"
                        else "unavailable"
                    ),
                },
                "global_approval": {
                    "status": (
                        "approved"
                        if all(
                            _globally_applied(candidate)
                            for candidate in candidates
                        )
                        else "available"
                        if state in {"candidate", "project_approved"}
                        and not atomic_required
                        else "repository_review_required"
                        if state in {"candidate", "project_approved"}
                        else "unavailable"
                    ),
                },
            }
        )
    return {
        "schema_version": "maestro_expertise_change_set_projection_v1",
        "change_sets": change_sets,
        "pack_change_set_ids": {
            pack_id: _unique(change_set_ids)
            for pack_id, change_set_ids in sorted(pack_links.items())
        },
        "automatic_mutation_allowed": False,
    }
