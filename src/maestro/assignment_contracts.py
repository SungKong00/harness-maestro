from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Iterable

from .documents import select_documents
from .errors import MaestroError
from .planning import validate_route_v2
from .registry import load_registry
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    safe_target,
    sha256_text,
)

ENGINEERING_BASELINE_VERSION = "maestro_engineering_baseline_v1"
ASSIGNMENT_INPUT_VERSION = "maestro_assignment_input_v1"
FINDING_PACKET_VERSION = "maestro_finding_packet_v2"
TERMINAL_PACKET_VERSION = "maestro_terminal_packet_v1"
VALIDATION_VERSION = "maestro_assignment_contract_validation_v1"
CONVENTION_SELECTION_VERSION = "maestro_convention_selection_v1"

_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_ARTIFACT_KINDS = {
    "source",
    "test",
    "schema",
    "config",
    "documentation",
    "interface",
    "data",
    "external",
}
_LIFECYCLE_KINDS = {
    "success",
    "validation-failure",
    "timeout",
    "retry",
    "cancellation",
    "rollback",
    "recovery",
    "other",
}
_CHECK_IDS = {
    "behavior-contract",
    "affected-surface",
    "failure-recovery",
    "compatibility",
    "completion-evidence",
    "risk-ownership",
}
_VERDICTS = {"PASS", "FINDINGS", "BLOCK", "INSUFFICIENT_EVIDENCE"}
_SEVERITIES = {"medium", "high", "critical"}
_TERMINAL_STATUSES = {
    "completed",
    "failed_transient",
    "failed_semantic",
    "blocked",
    "cancelled",
    "skipped",
}
_ASSIGNMENT_FIELDS = {
    "assignment_id",
    "kind",
    "executor_id",
    "lens_ids",
    "depends_on",
    "input_packets",
    "output_packet",
    "read_only",
    "mutation_owner",
    "allowed_side_effects",
    "may_spawn",
    "max_children",
    "max_rounds",
}
_FORBIDDEN_CONTEXT = [
    "parent_conversation",
    "other_initial_conclusions",
    "raw_transcripts",
    "hidden_reasoning",
    "file_bodies",
]


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _digest(value: Any) -> str | None:
    try:
        return sha256_text(canonical_json(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _validation(
    value: Any,
    issues: list[dict[str, str]],
    *,
    execution_status: str = "READY",
) -> dict[str, Any]:
    issues.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return {
        "schema_version": VALIDATION_VERSION,
        "status": "PASS" if not issues else "FAIL",
        "execution_status": "INVALID" if issues else execution_status,
        "issues": issues,
        "packet_digest": _digest(value),
        "writes_performed": False,
    }


def _project_document_selection(
    repo: Path,
    plan: dict[str, Any],
    assignment: dict[str, Any],
    target_paths: list[str],
) -> tuple[dict[str, Any], list[str]]:
    selection = select_documents(
        repo,
        plan["goal"],
        assignment["lens_ids"],
        target_paths,
    )
    selected_documents = selection.get("required_documents")
    if not isinstance(selected_documents, list):
        selected_documents = selection.get("documents", [])
    compact_documents: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}
    for item in selected_documents:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
            or _DIGEST.fullmatch(item["sha256"]) is None
        ):
            continue
        compact = {
            "path": item["path"],
            "sha256": item["sha256"],
            "reason": (
                item.get("reason")
                if _line(item.get("reason"), 500)
                else "selected by maestro docs"
            ),
            "document_type": (
                item.get("document_type")
                if isinstance(item.get("document_type"), str)
                else "map"
            ),
        }
        compact_documents.append(compact)
        by_path[item["path"]] = compact
    convention_paths = selection.get("selected_conventions", [])
    compact_conventions = [
        {
            "path": path,
            "sha256": by_path[path]["sha256"],
            "reason": by_path[path]["reason"],
        }
        for path in convention_paths
        if isinstance(path, str) and path in by_path
    ]
    payload = {
        "schema_version": CONVENTION_SELECTION_VERSION,
        "selector_version": selection.get("schema_version"),
        "goal_digest": sha256_text(plan["goal"]),
        "target_paths": target_paths,
        "evidence_status": selection.get("evidence_status"),
        "documents": compact_documents,
        "selected_conventions": compact_conventions,
        "missing_evidence": [
            item
            for item in selection.get("missing_evidence", [])
            if _line(item, 500)
        ][:8],
    }
    projected = {
        **payload,
        "selection_digest": sha256_text(canonical_json(payload)),
    }
    return projected, [item["path"] for item in compact_documents]


def _valid_convention_selection(
    value: Any,
    *,
    goal: Any,
) -> bool:
    fields = {
        "schema_version",
        "selection_digest",
        "selector_version",
        "goal_digest",
        "target_paths",
        "evidence_status",
        "documents",
        "selected_conventions",
        "missing_evidence",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema_version") != CONVENTION_SELECTION_VERSION
        or value.get("selector_version") != "maestro_docs_selection_v1"
        or not isinstance(goal, str)
        or value.get("goal_digest") != sha256_text(goal)
        or value.get("evidence_status")
        not in {"sufficient", "insufficient"}
    ):
        return False
    payload = copy.deepcopy(value)
    selection_digest = payload.pop("selection_digest")
    if (
        not isinstance(selection_digest, str)
        or _DIGEST.fullmatch(selection_digest) is None
        or selection_digest != sha256_text(canonical_json(payload))
    ):
        return False
    target_paths = value.get("target_paths")
    if (
        not isinstance(target_paths, list)
        or len(target_paths) > 10
        or len(set(target_paths)) != len(target_paths)
        or not all(_relative_path(path) for path in target_paths)
    ):
        return False
    documents = value.get("documents")
    if not isinstance(documents, list) or len(documents) > 8:
        return False
    document_refs: set[tuple[str, str]] = set()
    for item in documents:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"path", "sha256", "reason", "document_type"}
            or not _relative_path(item.get("path"))
            or not isinstance(item.get("sha256"), str)
            or _DIGEST.fullmatch(item["sha256"]) is None
            or not _line(item.get("reason"), 500)
            or not _line(item.get("document_type"), 100)
        ):
            return False
        reference = (item["path"], item["sha256"])
        if reference in document_refs:
            return False
        document_refs.add(reference)
    conventions = value.get("selected_conventions")
    if not isinstance(conventions, list) or len(conventions) > 8:
        return False
    convention_refs: set[tuple[str, str]] = set()
    for item in conventions:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256", "reason"}
            or not isinstance(item.get("path"), str)
            or not item["path"].startswith("docs/conventions/")
            or not item["path"].endswith(".md")
            or not _relative_path(item["path"])
            or not isinstance(item.get("sha256"), str)
            or _DIGEST.fullmatch(item["sha256"]) is None
            or not _line(item.get("reason"), 500)
            or (item["path"], item["sha256"]) not in document_refs
        ):
            return False
        reference = (item["path"], item["sha256"])
        if reference in convention_refs:
            return False
        convention_refs.add(reference)
    missing = value.get("missing_evidence")
    if (
        not isinstance(missing, list)
        or len(missing) > 8
        or len(set(missing)) != len(missing)
        or not all(_line(item, 500) for item in missing)
        or (value["evidence_status"] == "sufficient" and missing)
    ):
        return False
    return True


def _exact(
    value: Any,
    fields: set[str],
    path: str,
    issues: list[dict[str, str]],
) -> bool:
    if not isinstance(value, dict):
        issues.append(_issue("CONTRACT_OBJECT_REQUIRED", path, "Expected an object."))
        return False
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing:
        issues.append(
            _issue(
                "CONTRACT_FIELDS_MISSING",
                path,
                f"Missing fields: {', '.join(missing)}.",
            )
        )
    if unknown:
        issues.append(
            _issue(
                "CONTRACT_FIELDS_UNKNOWN",
                path,
                f"Unsupported fields: {', '.join(unknown)}.",
            )
        )
    return not missing and not unknown


def _line(value: Any, maximum: int, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    return (
        isinstance(value, str)
        and 0 < len(value.strip()) <= maximum
        and not any(character in value for character in "\r\n\x00")
        and "```" not in value
    )


def _id(value: Any) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _lines(
    value: Any,
    maximum_items: int,
    *,
    allow_empty: bool = True,
    identifiers: bool = False,
) -> bool:
    if (
        not isinstance(value, list)
        or len(value) > maximum_items
        or (not allow_empty and not value)
    ):
        return False
    if not all(
        _id(item) if identifiers else _line(item, 240)
        for item in value
    ):
        return False
    return len(value) == len(set(value))


def _relative_path(value: Any) -> bool:
    if not _line(value, 300) or "\\" in value:
        return False
    path = Path(value)
    return (
        bool(path.parts)
        and path != Path(".")
        and not path.is_absolute()
        and ".." not in path.parts
    )


def _assignments(plan: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(plan, dict) or not isinstance(plan.get("assignments"), list):
        return {}
    return {
        item["assignment_id"]: item
        for item in plan["assignments"]
        if isinstance(item, dict) and isinstance(item.get("assignment_id"), str)
    }


def _plan_issues(
    plan: Any,
    repo_path: str | Path | None = None,
) -> list[dict[str, str]]:
    try:
        result = validate_route_v2(plan, repo_path=repo_path)
    except (MaestroError, OSError, TypeError, ValueError) as exc:
        return [_issue("ASSIGNMENT_PLAN_INVALID", "plan", str(exc))]
    if result["status"] == "PASS":
        return []
    return [
        _issue(
            "ASSIGNMENT_PLAN_INVALID",
            f"plan.{item['path']}",
            item["message"],
        )
        for item in result["issues"]
    ]


def _regular_file(repo: Path, relative_path: str) -> Path | None:
    try:
        target = safe_target(repo, relative_path)
    except MaestroError:
        return None
    return (
        target
        if target.is_file() and not target.is_symlink()
        else None
    )


def validate_engineering_baseline(
    baseline: Any,
    *,
    repo_path: str | Path | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a small project-evidence surface and six coverage checks."""

    issues: list[dict[str, str]] = []
    repo: Path | None = None
    if repo_path is not None:
        try:
            repo = ensure_repo(repo_path)
        except MaestroError as exc:
            issues.append(_issue("BASELINE_REPO_INVALID", "repo", exc.message))
    fields = {"schema_version", "goal_digest", "surface_map", "checks"}
    if not _exact(baseline, fields, "$", issues):
        return _validation(baseline, issues)
    if baseline["schema_version"] != ENGINEERING_BASELINE_VERSION:
        issues.append(
            _issue(
                "BASELINE_VERSION_INVALID",
                "schema_version",
                f"Expected {ENGINEERING_BASELINE_VERSION}.",
            )
        )
    if not isinstance(baseline["goal_digest"], str) or _DIGEST.fullmatch(
        baseline["goal_digest"]
    ) is None:
        issues.append(
            _issue(
                "BASELINE_GOAL_DIGEST_INVALID",
                "goal_digest",
                "goal_digest must be a SHA-256 digest.",
            )
        )
    if (
        isinstance(plan, dict)
        and isinstance(plan.get("goal"), str)
        and baseline["goal_digest"] != sha256_text(plan["goal"])
    ):
        issues.append(
            _issue(
                "BASELINE_GOAL_MISMATCH",
                "goal_digest",
                "Baseline goal does not match the route plan.",
            )
        )

    surface_fields = {
        "artifacts",
        "affected_boundaries",
        "stakeholders",
        "lifecycle_states",
    }
    surface = baseline["surface_map"]
    if not _exact(surface, surface_fields, "surface_map", issues):
        return _validation(baseline, issues)

    artifacts = surface["artifacts"]
    artifact_ids: set[str] = set()
    if (
        not isinstance(artifacts, list)
        or not artifacts
        or len(artifacts) > 10
    ):
        issues.append(
            _issue(
                "BASELINE_ARTIFACTS_INVALID",
                "surface_map.artifacts",
                "artifacts must contain 1 to 10 items.",
            )
        )
        artifacts = []
    for index, artifact in enumerate(artifacts):
        path = f"surface_map.artifacts[{index}]"
        if not _exact(
            artifact,
            {"artifact_id", "kind", "path", "state"},
            path,
            issues,
        ):
            continue
        artifact_id = artifact["artifact_id"]
        if not _id(artifact_id) or artifact_id in artifact_ids:
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_ID_INVALID",
                    f"{path}.artifact_id",
                    "artifact_id must be unique lowercase kebab-case.",
                )
            )
        else:
            artifact_ids.add(artifact_id)
        if (
            not isinstance(artifact["kind"], str)
            or artifact["kind"] not in _ARTIFACT_KINDS
        ):
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_KIND_INVALID",
                    f"{path}.kind",
                    "Unsupported artifact kind.",
                )
            )
        if not _relative_path(artifact["path"]):
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_PATH_INVALID",
                    f"{path}.path",
                    "Artifact path must be repository-relative.",
                )
            )
        if (
            not isinstance(artifact["state"], str)
            or artifact["state"] not in {"existing", "planned"}
        ):
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_STATE_INVALID",
                    f"{path}.state",
                    "Artifact state must be existing or planned.",
                )
            )
        if (
            repo is not None
            and artifact["state"] == "existing"
            and _relative_path(artifact["path"])
            and _regular_file(repo, artifact["path"]) is None
        ):
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_MISSING",
                    f"{path}.path",
                    "Existing artifact must be a regular non-symlink file.",
                )
            )

    boundaries = surface["affected_boundaries"]
    if not isinstance(boundaries, list) or len(boundaries) > 8:
        issues.append(
            _issue(
                "BASELINE_BOUNDARIES_INVALID",
                "surface_map.affected_boundaries",
                "affected_boundaries must contain at most 8 items.",
            )
        )
        boundaries = []
    boundary_ids: set[str] = set()
    for index, boundary in enumerate(boundaries):
        path = f"surface_map.affected_boundaries[{index}]"
        if not _exact(boundary, {"boundary_id", "artifact_ids"}, path, issues):
            continue
        if not _id(boundary["boundary_id"]) or boundary["boundary_id"] in boundary_ids:
            issues.append(
                _issue(
                    "BASELINE_BOUNDARY_ID_INVALID",
                    f"{path}.boundary_id",
                    "boundary_id must be unique lowercase kebab-case.",
                )
            )
        else:
            boundary_ids.add(boundary["boundary_id"])
        if (
            not _lines(
                boundary["artifact_ids"],
                10,
                allow_empty=False,
                identifiers=True,
            )
            or not set(boundary["artifact_ids"]).issubset(artifact_ids)
        ):
            issues.append(
                _issue(
                    "BASELINE_BOUNDARY_ARTIFACTS_INVALID",
                    f"{path}.artifact_ids",
                    "Boundary artifact_ids must name known artifacts.",
                )
            )

    stakeholders = surface["stakeholders"]
    if not isinstance(stakeholders, list) or len(stakeholders) > 6:
        issues.append(
            _issue(
                "BASELINE_STAKEHOLDERS_INVALID",
                "surface_map.stakeholders",
                "stakeholders must contain at most 6 items.",
            )
        )
        stakeholders = []
    stakeholder_ids: set[str] = set()
    for index, stakeholder in enumerate(stakeholders):
        path = f"surface_map.stakeholders[{index}]"
        if not _exact(
            stakeholder,
            {"stakeholder_id", "concern"},
            path,
            issues,
        ):
            continue
        if (
            not _id(stakeholder["stakeholder_id"])
            or stakeholder["stakeholder_id"] in stakeholder_ids
        ):
            issues.append(
                _issue(
                    "BASELINE_STAKEHOLDER_ID_INVALID",
                    f"{path}.stakeholder_id",
                    "stakeholder_id must be unique lowercase kebab-case.",
                )
            )
        else:
            stakeholder_ids.add(stakeholder["stakeholder_id"])
        if not _line(stakeholder["concern"], 240):
            issues.append(
                _issue(
                    "BASELINE_STAKEHOLDER_CONCERN_INVALID",
                    f"{path}.concern",
                    "Concern must be one bounded line.",
                )
            )

    lifecycle_states = surface["lifecycle_states"]
    if not isinstance(lifecycle_states, list) or len(lifecycle_states) > 8:
        issues.append(
            _issue(
                "BASELINE_LIFECYCLE_INVALID",
                "surface_map.lifecycle_states",
                "lifecycle_states must contain at most 8 items.",
            )
        )
        lifecycle_states = []
    state_ids: set[str] = set()
    for index, state in enumerate(lifecycle_states):
        path = f"surface_map.lifecycle_states[{index}]"
        if not _exact(state, {"state_id", "kind", "artifact_ids"}, path, issues):
            continue
        if not _id(state["state_id"]) or state["state_id"] in state_ids:
            issues.append(
                _issue(
                    "BASELINE_LIFECYCLE_ID_INVALID",
                    f"{path}.state_id",
                    "state_id must be unique lowercase kebab-case.",
                )
            )
        else:
            state_ids.add(state["state_id"])
        if (
            not isinstance(state["kind"], str)
            or state["kind"] not in _LIFECYCLE_KINDS
        ):
            issues.append(
                _issue(
                    "BASELINE_LIFECYCLE_KIND_INVALID",
                    f"{path}.kind",
                    "Unsupported lifecycle kind.",
                )
            )
        if (
            not _lines(
                state["artifact_ids"],
                10,
                allow_empty=False,
                identifiers=True,
            )
            or not set(state["artifact_ids"]).issubset(artifact_ids)
        ):
            issues.append(
                _issue(
                    "BASELINE_LIFECYCLE_ARTIFACTS_INVALID",
                    f"{path}.artifact_ids",
                    "Lifecycle artifact_ids must name known artifacts.",
                )
            )

    checks = baseline["checks"]
    if not isinstance(checks, list) or len(checks) != len(_CHECK_IDS):
        issues.append(
            _issue(
                "BASELINE_CHECKS_INVALID",
                "checks",
                "Exactly six Engineering Baseline checks are required.",
            )
        )
        checks = []
    check_ids: set[str] = set()
    known_assignments = set(_assignments(plan))
    selected_lenses = (
        {
            item
            for item in plan.get("selected_lenses", [])
            if isinstance(item, str)
        }
        if isinstance(plan, dict) and isinstance(plan.get("selected_lenses"), list)
        else set()
    )
    for index, check in enumerate(checks):
        path = f"checks[{index}]"
        if not _exact(
            check,
            {"check_id", "status", "owner", "evidence_refs", "note"},
            path,
            issues,
        ):
            continue
        check_id = check["check_id"]
        if (
            not isinstance(check_id, str)
            or check_id not in _CHECK_IDS
            or check_id in check_ids
        ):
            issues.append(
                _issue(
                    "BASELINE_CHECK_ID_INVALID",
                    f"{path}.check_id",
                    "check_id must be one unique baseline criterion.",
                )
            )
        else:
            check_ids.add(check_id)
        status = check["status"]
        owner = check["owner"]
        refs = check["evidence_refs"]
        if (
            not isinstance(status, str)
            or status not in {"covered", "gap", "not_applicable"}
        ):
            issues.append(
                _issue(
                    "BASELINE_CHECK_STATUS_INVALID",
                    f"{path}.status",
                    "Unsupported check status.",
                )
            )
        if not _lines(refs, 5):
            issues.append(
                _issue(
                    "BASELINE_CHECK_EVIDENCE_INVALID",
                    f"{path}.evidence_refs",
                    "evidence_refs must be a bounded unique list.",
                )
            )
        elif not set(refs).issubset(artifact_ids | {"task-contract"}):
            issues.append(
                _issue(
                    "BASELINE_CHECK_EVIDENCE_UNBOUND",
                    f"{path}.evidence_refs",
                    "Baseline evidence must name a mapped artifact or task-contract.",
                )
            )
        owner_valid = owner == "task-contract"
        if isinstance(owner, str) and owner.startswith("lens:"):
            owner_valid = _id(owner[5:]) and (
                plan is None or owner[5:] in selected_lenses
            )
        if isinstance(owner, str) and owner.startswith("assignment:"):
            owner_valid = _id(owner[11:]) and (
                plan is None or owner[11:] in known_assignments
            )
        if owner is not None and not owner_valid:
            issues.append(
                _issue(
                    "BASELINE_CHECK_OWNER_INVALID",
                    f"{path}.owner",
                    "Owner must bind the task contract, a selected Lens, or an Assignment.",
                )
            )
        if status == "covered" and (not owner_valid or not refs):
            issues.append(
                _issue(
                    "BASELINE_COVERED_UNPROVED",
                    path,
                    "Covered checks require a bound owner and evidence.",
                )
            )
        if status == "gap" and (owner is not None or not refs):
            issues.append(
                _issue(
                    "BASELINE_GAP_INVALID",
                    path,
                    "Gap checks require evidence and no owner.",
                )
            )
        if status == "not_applicable" and owner is not None:
            issues.append(
                _issue(
                    "BASELINE_NOT_APPLICABLE_OWNED",
                    path,
                    "Not-applicable checks cannot have an owner.",
                )
            )
        if not _line(check["note"], 300):
            issues.append(
                _issue(
                    "BASELINE_CHECK_NOTE_INVALID",
                    f"{path}.note",
                    "Note must be one bounded line.",
                )
            )
    if check_ids != _CHECK_IDS:
        issues.append(
            _issue(
                "BASELINE_CHECK_SET_INVALID",
                "checks",
                "The six required check IDs must appear exactly once.",
            )
        )

    execution_status = (
        "GAPS_PRESENT"
        if any(
            isinstance(item, dict) and item.get("status") == "gap"
            for item in checks
        )
        else "READY"
    )
    return _validation(
        baseline,
        issues,
        execution_status=execution_status,
    )


def _projection_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("input"), dict):
        return value["input"]
    return value if isinstance(value, dict) else None


def _projection_bound(
    projection: Any,
    plan_id: Any,
    assignment_id: Any,
) -> bool:
    value = _projection_value(projection)
    if (
        value is None
        or value.get("schema_version") != ASSIGNMENT_INPUT_VERSION
        or value.get("plan_id") != plan_id
        or value.get("assignment_id") != assignment_id
        or not isinstance(value.get("projection_digest"), str)
    ):
        return False
    payload = copy.deepcopy(value)
    digest = payload.pop("projection_digest")
    try:
        return digest == sha256_text(canonical_json(payload))
    except (TypeError, ValueError, OverflowError):
        return False


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _projection_refs(
    projection: Any,
) -> tuple[set[str], set[str]]:
    value = _projection_value(projection)
    if value is None:
        return set(), set()
    identifiers: set[str] = set()
    locations: set[str] = set()
    for item in _dict_items(value.get("artifact_refs")):
        if (
            isinstance(item.get("artifact_id"), str)
            and isinstance(item.get("sha256"), str)
            and _DIGEST.fullmatch(item["sha256"]) is not None
        ):
            identifiers.add(item["artifact_id"])
        if isinstance(item.get("path"), str):
            locations.add(item["path"])
    for item in _dict_items(value.get("document_refs")):
        if isinstance(item.get("ref_id"), str):
            identifiers.add(item["ref_id"])
        if isinstance(item.get("path"), str):
            locations.add(item["path"])
    for item in _dict_items(value.get("dependency_packets")):
        if isinstance(item.get("ref_id"), str):
            identifiers.add(item["ref_id"])
    return identifiers, locations


def _projection_artifacts(projection: Any) -> tuple[set[str], set[str]]:
    value = _projection_value(projection)
    if value is None:
        return set(), set()
    identifiers: set[str] = set()
    locations: set[str] = set()
    for item in _dict_items(value.get("artifact_refs")):
        if isinstance(item.get("artifact_id"), str):
            identifiers.add(item["artifact_id"])
        if isinstance(item.get("path"), str):
            locations.add(item["path"])
    return identifiers, locations


def _evidence(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
    *,
    projection: Any = None,
    allow_empty: bool = False,
) -> list[str]:
    if not _lines(value, 5, allow_empty=allow_empty):
        issues.append(
            _issue(
                "PACKET_EVIDENCE_INVALID",
                path,
                "Evidence must be a bounded unique reference list.",
            )
        )
        return []
    refs = value
    if projection is not None:
        allowed, _ = _projection_refs(projection)
        if not set(refs).issubset(allowed):
            issues.append(
                _issue(
                    "PACKET_EVIDENCE_OUT_OF_PROJECTION",
                    path,
                    "Evidence contains a reference outside the Assignment projection.",
                )
            )
    return refs


def validate_finding_packet(
    packet: Any,
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any] | None = None,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate FindingPacket structure and bindings, not claim truth."""

    issues = _plan_issues(plan, repo_path)
    plan_value = plan if isinstance(plan, dict) else {}
    assignment = _assignments(plan).get(assignment_id)
    if assignment is None:
        issues.append(
            _issue(
                "PACKET_ASSIGNMENT_UNKNOWN",
                "assignment_id",
                f"Unknown Assignment: {assignment_id}.",
            )
        )
    elif assignment.get("output_packet") != "FindingPacket":
        issues.append(
            _issue(
                "PACKET_TYPE_MISMATCH",
                "schema_version",
                "Assignment does not return FindingPacket.",
            )
        )
    packet_fields = {
        "schema_version",
        "plan_id",
        "assignment_id",
        "lens_ids",
        "verdict",
        "findings",
        "coverage_gaps",
        "uncertainties",
        "inspected",
        "skipped",
    }
    if not _exact(packet, packet_fields, "$", issues):
        return _validation(packet, issues)
    if packet["schema_version"] != FINDING_PACKET_VERSION:
        issues.append(
            _issue(
                "PACKET_VERSION_INVALID",
                "schema_version",
                f"Expected {FINDING_PACKET_VERSION}.",
            )
        )
    if packet["plan_id"] != plan_value.get("plan_id"):
        issues.append(
            _issue("PACKET_PLAN_MISMATCH", "plan_id", "Packet plan does not match.")
        )
    if packet["assignment_id"] != assignment_id:
        issues.append(
            _issue(
                "PACKET_ASSIGNMENT_MISMATCH",
                "assignment_id",
                "Packet Assignment does not match.",
            )
        )
    expected_lenses = assignment.get("lens_ids", []) if assignment else []
    if (
        not _lines(packet["lens_ids"], 3, allow_empty=False, identifiers=True)
        or packet["lens_ids"] != expected_lenses
    ):
        issues.append(
            _issue(
                "PACKET_LENS_BINDING_INVALID",
                "lens_ids",
                "lens_ids must exactly match the Assignment.",
            )
        )
    if projection is not None:
        if not _projection_bound(
            projection,
            packet["plan_id"],
            assignment_id,
        ):
            issues.append(
                _issue(
                    "PACKET_PROJECTION_INVALID",
                    "projection",
                    "Projection is not bound to this plan and Assignment.",
                )
            )
    if (
        not isinstance(packet["verdict"], str)
        or packet["verdict"] not in _VERDICTS
    ):
        issues.append(
            _issue("PACKET_VERDICT_INVALID", "verdict", "Unsupported verdict.")
        )

    findings = packet["findings"]
    if not isinstance(findings, list) or len(findings) > 5:
        issues.append(
            _issue(
                "PACKET_FINDINGS_INVALID",
                "findings",
                "findings must contain at most 5 items.",
            )
        )
        findings = []
    finding_fields = {
        "owner_lens_id",
        "location",
        "severity",
        "claim",
        "evidence_refs",
        "counterexample",
        "suggested_action",
        "fingerprint",
    }
    _, allowed_locations = _projection_artifacts(projection)
    fingerprints: set[str] = set()
    for index, finding in enumerate(findings):
        path = f"findings[{index}]"
        if not _exact(finding, finding_fields, path, issues):
            continue
        if (
            not isinstance(finding["owner_lens_id"], str)
            or finding["owner_lens_id"] not in expected_lenses
        ):
            issues.append(
                _issue(
                    "PACKET_FINDING_SCOPE_INVALID",
                    f"{path}.owner_lens_id",
                    "Finding owner is outside the Assignment Lens set.",
                )
            )
        if (
            not isinstance(finding["severity"], str)
            or finding["severity"] not in _SEVERITIES
        ):
            issues.append(
                _issue(
                    "PACKET_FINDING_SEVERITY_INVALID",
                    f"{path}.severity",
                    "Finding severity must be medium or higher.",
                )
            )
        for field, maximum in (
            ("location", 300),
            ("claim", 500),
            ("suggested_action", 400),
            ("fingerprint", 160),
        ):
            if not _line(finding[field], maximum):
                issues.append(
                    _issue(
                        "PACKET_TEXT_INVALID",
                        f"{path}.{field}",
                        "Packet text must be one bounded line without code blocks.",
                    )
                )
        if not _line(finding["counterexample"], 400, nullable=True):
            issues.append(
                _issue(
                    "PACKET_TEXT_INVALID",
                    f"{path}.counterexample",
                    "counterexample must be null or one bounded line.",
                )
            )
        _evidence(
            finding["evidence_refs"],
            f"{path}.evidence_refs",
            issues,
            projection=projection,
        )
        if projection is not None and (
            not isinstance(finding["location"], str)
            or not any(
                finding["location"] == location
                or finding["location"].startswith(f"{location}:")
                for location in allowed_locations
            )
        ):
            issues.append(
                _issue(
                    "PACKET_LOCATION_OUT_OF_PROJECTION",
                    f"{path}.location",
                    "Finding location is outside projected artifacts.",
                )
            )
        if (
            isinstance(finding["fingerprint"], str)
            and finding["fingerprint"] in fingerprints
        ):
            issues.append(
                _issue(
                    "PACKET_FINDING_DUPLICATE",
                    f"{path}.fingerprint",
                    "Finding fingerprint is duplicated.",
                )
            )
        if isinstance(finding["fingerprint"], str):
            fingerprints.add(finding["fingerprint"])

    gaps = packet["coverage_gaps"]
    if not isinstance(gaps, list) or len(gaps) > 2:
        issues.append(
            _issue(
                "PACKET_COVERAGE_GAPS_INVALID",
                "coverage_gaps",
                "coverage_gaps must contain at most 2 items.",
            )
        )
        gaps = []
    gap_fields = {
        "affected_artifact",
        "possible_failure",
        "evidence_refs",
        "severity",
        "why_uncovered",
        "suggested_lens",
    }
    registry_lenses = {
        item["lens_id"] for item in load_registry()["lenses"]
    }
    selected_lenses = {
        item
        for item in plan_value.get("selected_lenses", [])
        if isinstance(item, str)
    }
    projected_artifacts, _ = _projection_artifacts(projection)
    gap_keys: set[tuple[str, str]] = set()
    for index, gap in enumerate(gaps):
        path = f"coverage_gaps[{index}]"
        if not _exact(gap, gap_fields, path, issues):
            continue
        if not _id(gap["affected_artifact"]):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_ARTIFACT_INVALID",
                    f"{path}.affected_artifact",
                    "affected_artifact must be a typed artifact ID.",
                )
            )
        if projection is not None and (
            not isinstance(gap["affected_artifact"], str)
            or gap["affected_artifact"] not in projected_artifacts
        ):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_ARTIFACT_UNPROJECTED",
                    f"{path}.affected_artifact",
                    "Coverage gap artifact is outside the projection.",
                )
            )
        if (
            not isinstance(gap["severity"], str)
            or gap["severity"] not in _SEVERITIES
        ):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_SEVERITY_INVALID",
                    f"{path}.severity",
                    "Coverage gap severity must be medium or higher.",
                )
            )
        for field in ("possible_failure", "why_uncovered"):
            if not _line(gap[field], 400):
                issues.append(
                    _issue(
                        "PACKET_TEXT_INVALID",
                        f"{path}.{field}",
                        "Coverage text must be one bounded line.",
                    )
                )
        _evidence(
            gap["evidence_refs"],
            f"{path}.evidence_refs",
            issues,
            projection=projection,
        )
        suggested = gap["suggested_lens"]
        if suggested is not None and (
            not _id(suggested)
            or suggested not in registry_lenses
            or suggested in selected_lenses
        ):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_LENS_INVALID",
                    f"{path}.suggested_lens",
                    "suggested_lens must be an unselected registered Lens or null.",
                )
            )
        if isinstance(gap["affected_artifact"], str) and isinstance(
            gap["possible_failure"], str
        ):
            key = (gap["affected_artifact"], gap["possible_failure"])
            if key in gap_keys:
                issues.append(
                    _issue(
                        "PACKET_COVERAGE_DUPLICATE",
                        path,
                        "Coverage gap duplicates an earlier gap.",
                    )
                )
            gap_keys.add(key)

    for field in ("uncertainties", "skipped"):
        if not _lines(packet[field], 5):
            issues.append(
                _issue(
                    "PACKET_LIST_INVALID",
                    field,
                    f"{field} must be a bounded unique one-line list.",
                )
            )
    if not _lines(packet["inspected"], 10):
        issues.append(
            _issue(
                "PACKET_LIST_INVALID",
                "inspected",
                "inspected must be a bounded unique reference list.",
            )
        )
    inspected_valid = _lines(packet["inspected"], 10)
    if projection is not None and inspected_valid:
        projected_refs, _ = _projection_refs(projection)
        if not set(packet["inspected"]).issubset(projected_refs):
            issues.append(
                _issue(
                    "PACKET_INSPECTED_OUT_OF_PROJECTION",
                    "inspected",
                    "inspected contains a reference outside the projection.",
                )
            )
    verdict = packet["verdict"] if isinstance(packet["verdict"], str) else None
    if verdict == "PASS" and (findings or gaps):
        issues.append(
            _issue(
                "PACKET_PASS_HAS_FINDINGS",
                "verdict",
                "PASS cannot contain findings or coverage gaps.",
            )
        )
    if verdict in {"FINDINGS", "BLOCK"} and not (findings or gaps):
        issues.append(
            _issue(
                "PACKET_FINDING_REQUIRED",
                "verdict",
                "FINDINGS or BLOCK requires a finding or coverage gap.",
            )
        )
    if (
        verdict == "INSUFFICIENT_EVIDENCE"
        and not gaps
        and not packet["uncertainties"]
    ):
        issues.append(
            _issue(
                "PACKET_UNCERTAINTY_REQUIRED",
                "uncertainties",
                "INSUFFICIENT_EVIDENCE requires a gap or uncertainty.",
            )
        )
    return _validation(packet, issues)


def validate_terminal_packet(
    packet: Any,
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any] | None = None,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate one terminal observation; this does not execute retries."""

    issues = _plan_issues(plan, repo_path)
    plan_value = plan if isinstance(plan, dict) else {}
    assignment = _assignments(plan).get(assignment_id)
    if assignment is None:
        issues.append(
            _issue(
                "PACKET_ASSIGNMENT_UNKNOWN",
                "assignment_id",
                f"Unknown Assignment: {assignment_id}.",
            )
        )
    fields = {
        "schema_version",
        "plan_id",
        "assignment_id",
        "packet_type",
        "status",
        "summary",
        "evidence_refs",
        "retryable",
    }
    if isinstance(packet, dict) and "convention_dispositions" in packet:
        fields.add("convention_dispositions")
    if not _exact(packet, fields, "$", issues):
        return _validation(packet, issues)
    if packet["schema_version"] != TERMINAL_PACKET_VERSION:
        issues.append(
            _issue(
                "PACKET_VERSION_INVALID",
                "schema_version",
                f"Expected {TERMINAL_PACKET_VERSION}.",
            )
        )
    if packet["plan_id"] != plan_value.get("plan_id"):
        issues.append(
            _issue("PACKET_PLAN_MISMATCH", "plan_id", "Packet plan does not match.")
        )
    if packet["assignment_id"] != assignment_id:
        issues.append(
            _issue(
                "PACKET_ASSIGNMENT_MISMATCH",
                "assignment_id",
                "Packet Assignment does not match.",
            )
        )
    if assignment is not None and packet["packet_type"] != assignment["output_packet"]:
        issues.append(
            _issue(
                "PACKET_TYPE_MISMATCH",
                "packet_type",
                "Packet type does not match the Assignment output.",
            )
        )
    if (
        packet.get("status") == "completed"
        and assignment is not None
        and assignment["mutation_owner"]
        and projection is None
    ):
        issues.append(
            _issue(
                "PACKET_PROJECTION_REQUIRED",
                "projection",
                "A completed mutation Packet requires its bound Assignment projection.",
            )
        )
    if projection is not None:
        if not _projection_bound(
            projection,
            packet["plan_id"],
            assignment_id,
        ):
            issues.append(
                _issue(
                    "PACKET_PROJECTION_INVALID",
                    "projection",
                    "Projection is not bound to this plan and Assignment.",
                )
            )
    if (
        not isinstance(packet["status"], str)
        or packet["status"] not in _TERMINAL_STATUSES
    ):
        issues.append(
            _issue("PACKET_STATUS_INVALID", "status", "Unsupported terminal status.")
        )
    if not _line(packet["summary"], 400):
        issues.append(
            _issue(
                "PACKET_TEXT_INVALID",
                "summary",
                "Summary must be one bounded line.",
            )
        )
    refs = _evidence(
        packet["evidence_refs"],
        "evidence_refs",
        issues,
        projection=projection,
        allow_empty=packet["status"] != "completed",
    )
    if not isinstance(packet["retryable"], bool):
        issues.append(
            _issue(
                "PACKET_RETRYABLE_INVALID",
                "retryable",
                "retryable must be boolean.",
            )
        )
    elif packet["retryable"] != (packet["status"] == "failed_transient"):
        issues.append(
            _issue(
                "PACKET_RETRYABLE_MISMATCH",
                "retryable",
                "Only failed_transient may be retryable.",
            )
        )
    if (
        packet["status"] == "completed"
        and assignment is not None
        and assignment["output_packet"] == "FindingPacket"
    ):
        issues.append(
            _issue(
                "PACKET_FINDING_PAYLOAD_REQUIRED",
                "status",
                "A completed reviewer must return FindingPacket v2.",
            )
        )
    if packet["status"] == "completed" and not refs:
        issues.append(
            _issue(
                "PACKET_EVIDENCE_REQUIRED",
                "evidence_refs",
                "Completed Assignments require evidence.",
            )
        )
    projected_value = _projection_value(projection)
    selection = (
        projected_value.get("convention_selection")
        if isinstance(projected_value, dict)
        else None
    )
    selection_valid = _valid_convention_selection(
        selection,
        goal=plan_value.get("goal"),
    )
    if (
        projection is not None
        and assignment is not None
        and assignment["mutation_owner"]
        and not selection_valid
    ):
        issues.append(
            _issue(
                "PACKET_CONVENTION_SELECTION_INVALID",
                "projection.convention_selection",
                "A mutation result requires the intact document and Convention selection produced for this goal.",
            )
        )
    selected_conventions = (
        selection.get("selected_conventions", [])
        if selection_valid
        else []
    )
    dispositions = packet.get("convention_dispositions")
    if (
        packet["status"] == "completed"
        and assignment is not None
        and assignment["mutation_owner"]
        and selected_conventions
        and dispositions is None
    ):
        issues.append(
            _issue(
                "PACKET_CONVENTION_DISPOSITIONS_REQUIRED",
                "convention_dispositions",
                "A completed writer must report one disposition for every selected Convention.",
            )
        )
    if dispositions is not None:
        if (
            not isinstance(dispositions, list)
            or len(dispositions) > 8
            or len(dispositions) != len(selected_conventions)
        ):
            issues.append(
                _issue(
                    "PACKET_CONVENTION_DISPOSITIONS_INVALID",
                    "convention_dispositions",
                    "Convention dispositions must match the bounded selected Convention set.",
                )
            )
        else:
            expected = {
                (item.get("path"), item.get("sha256"))
                for item in selected_conventions
                if isinstance(item, dict)
            }
            seen: set[tuple[Any, Any]] = set()
            has_conflict = False
            for index, item in enumerate(dispositions):
                path = f"convention_dispositions[{index}]"
                if (
                    not isinstance(item, dict)
                    or set(item)
                    != {
                        "path",
                        "sha256",
                        "disposition",
                        "reason",
                        "approval_ref",
                    }
                    or not _line(item.get("reason"), 500)
                    or item.get("disposition")
                    not in {
                        "applied",
                        "not_applicable",
                        "waived",
                        "conflict",
                    }
                ):
                    issues.append(
                        _issue(
                            "PACKET_CONVENTION_DISPOSITION_INVALID",
                            path,
                            "Convention disposition does not satisfy the closed execution-report contract.",
                        )
                    )
                    continue
                key = (item.get("path"), item.get("sha256"))
                approval_ref = item.get("approval_ref")
                if key not in expected or key in seen:
                    issues.append(
                        _issue(
                            "PACKET_CONVENTION_DISPOSITION_MISMATCH",
                            path,
                            "Convention disposition is duplicated or outside the selected digest set.",
                        )
                    )
                seen.add(key)
                if item["disposition"] == "waived":
                    if (
                        not isinstance(approval_ref, str)
                        or not approval_ref.startswith("owner_decision:")
                        or not _line(approval_ref, 500)
                    ):
                        issues.append(
                            _issue(
                                "PACKET_CONVENTION_WAIVER_INVALID",
                                f"{path}.approval_ref",
                                "A waiver requires one bounded owner_decision reference.",
                            )
                        )
                elif approval_ref is not None:
                    issues.append(
                        _issue(
                            "PACKET_CONVENTION_APPROVAL_UNEXPECTED",
                            f"{path}.approval_ref",
                            "Only waived Conventions may carry an approval reference.",
                        )
                    )
                has_conflict = has_conflict or item["disposition"] == "conflict"
            if seen != expected:
                issues.append(
                    _issue(
                        "PACKET_CONVENTION_DISPOSITION_SET_MISMATCH",
                        "convention_dispositions",
                        "Convention dispositions do not cover the exact selected path and digest set.",
                    )
                )
            if packet["status"] == "completed" and has_conflict:
                issues.append(
                    _issue(
                        "PACKET_CONVENTION_CONFLICT_UNRESOLVED",
                        "convention_dispositions",
                        "A writer cannot complete while a selected Convention conflict remains open.",
                    )
                )
    return _validation(packet, issues)


def validate_assignment_packet(
    packet: Any,
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any] | None = None,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    version = packet.get("schema_version") if isinstance(packet, dict) else None
    if version == FINDING_PACKET_VERSION:
        return validate_finding_packet(
            packet,
            plan,
            assignment_id,
            projection,
            repo_path=repo_path,
        )
    if version == TERMINAL_PACKET_VERSION:
        return validate_terminal_packet(
            packet,
            plan,
            assignment_id,
            projection,
            repo_path=repo_path,
        )
    return _validation(
        packet,
        [
            _issue(
                "PACKET_VERSION_UNSUPPORTED",
                "schema_version",
                "Supported versions are FindingPacket v2 and terminal Packet v1.",
            )
        ],
    )


def project_assignment_input(
    repo_path: str | Path,
    plan: dict[str, Any],
    assignment_id: str,
    baseline: dict[str, Any],
    *,
    document_paths: Iterable[str] = (),
    dependency_packets: Iterable[dict[str, Any]] = (),
    dependency_projections: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Project the explicit allowlist for one Host-executed Assignment."""

    repo = ensure_repo(repo_path)
    issues = _plan_issues(plan, repo)
    plan_value = plan if isinstance(plan, dict) else {}
    assignment = _assignments(plan).get(assignment_id)
    if assignment is None:
        issues.append(
            _issue(
                "PROJECTION_ASSIGNMENT_UNKNOWN",
                "assignment_id",
                f"Unknown Assignment: {assignment_id}.",
            )
        )
    baseline_result = validate_engineering_baseline(
        baseline,
        repo_path=repo,
        plan=plan,
    )
    issues.extend(baseline_result["issues"])

    surface_artifacts = (
        baseline.get("surface_map", {}).get("artifacts", [])
        if isinstance(baseline, dict)
        and isinstance(baseline.get("surface_map"), dict)
        else []
    )
    target_paths = list(
        dict.fromkeys(
            item["path"]
            for item in surface_artifacts
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
        )
    )
    convention_selection: dict[str, Any] | None = None
    selected_document_paths: list[str] = []
    document_selection_blocked = False
    if assignment is not None and isinstance(plan_value.get("goal"), str):
        convention_selection, selected_document_paths = (
            _project_document_selection(
                repo,
                plan_value,
                assignment,
                target_paths,
            )
        )
        if (
            assignment["mutation_owner"]
            and convention_selection["evidence_status"] != "sufficient"
        ):
            document_selection_blocked = True

    documents: list[dict[str, str]] = []
    seen_document_paths: set[str] = set()
    all_document_paths = [
        *selected_document_paths,
        *list(document_paths),
    ]
    for index, relative_path in enumerate(all_document_paths):
        if len(documents) >= 8:
            issues.append(
                _issue(
                    "PROJECTION_DOCUMENT_LIMIT",
                    "document_paths",
                    "At most 8 document references are allowed.",
                )
            )
            break
        if relative_path in seen_document_paths:
            continue
        if not _relative_path(relative_path):
            issues.append(
                _issue(
                    "PROJECTION_DOCUMENT_INVALID",
                    f"document_paths[{index}]",
                    "Document path must be unique and repository-relative.",
                )
            )
            continue
        target = _regular_file(repo, relative_path)
        digest = file_sha256(target) if target is not None else None
        if digest is None:
            issues.append(
                _issue(
                    "PROJECTION_DOCUMENT_MISSING",
                    f"document_paths[{index}]",
                    "Document must be a regular non-symlink file.",
                )
            )
            continue
        seen_document_paths.add(relative_path)
        documents.append(
            {
                "ref_id": f"doc-{sha256_text(relative_path)[:12]}",
                "path": relative_path,
                "sha256": digest,
            }
        )

    baseline_artifact_refs = [
        {
            "artifact_id": artifact.get("artifact_id"),
            "path": artifact.get("path"),
            "sha256": (
                file_sha256(target)
                if (
                    artifact.get("state") == "existing"
                    and isinstance(artifact.get("path"), str)
                    and (target := _regular_file(repo, artifact["path"]))
                    is not None
                )
                else None
            ),
        }
        for artifact in (
            baseline.get("surface_map", {}).get("artifacts", [])
            if isinstance(baseline, dict)
            and isinstance(baseline.get("surface_map"), dict)
            else []
        )
        if isinstance(artifact, dict)
    ]
    dependency_projection_by_id: dict[str, dict[str, Any]] = {}
    for index, projection in enumerate(dependency_projections):
        projected_value = _projection_value(projection)
        projected_assignment_id = (
            projected_value.get("assignment_id")
            if isinstance(projected_value, dict)
            else None
        )
        if (
            not isinstance(projected_assignment_id, str)
            or projected_assignment_id in dependency_projection_by_id
            or not _projection_bound(
                projection,
                plan_value.get("plan_id"),
                projected_assignment_id,
            )
        ):
            issues.append(
                _issue(
                    "PROJECTION_DEPENDENCY_PROJECTION_INVALID",
                    f"dependency_projections[{index}]",
                    "Each dependency needs one unique, intact source projection bound to this plan.",
                )
            )
            continue
        dependency_projection_by_id[projected_assignment_id] = copy.deepcopy(
            projection
        )

    dependency_by_id: dict[str, dict[str, Any]] = {}
    for index, packet in enumerate(dependency_packets):
        packet_assignment_id = (
            packet.get("assignment_id") if isinstance(packet, dict) else None
        )
        if (
            not isinstance(packet_assignment_id, str)
            or packet_assignment_id in dependency_by_id
        ):
            issues.append(
                _issue(
                    "PROJECTION_DEPENDENCY_DUPLICATE",
                    f"dependency_packets[{index}]",
                    "Dependency Packet needs one unique Assignment ID.",
                )
            )
            continue
        dependency_projection = dependency_projection_by_id.get(
            packet_assignment_id
        )
        if dependency_projection is None:
            issues.append(
                _issue(
                    "PROJECTION_DEPENDENCY_PROJECTION_REQUIRED",
                    f"dependency_packets[{index}]",
                    "Provide the exact source projection used to validate this dependency Packet.",
                )
            )
            continue
        validation = validate_assignment_packet(
            packet,
            plan,
            packet_assignment_id,
            dependency_projection,
            repo_path=repo,
        )
        if validation["status"] != "PASS":
            issues.append(
                _issue(
                    "PROJECTION_DEPENDENCY_INVALID",
                    f"dependency_packets[{index}]",
                    validation["issues"][0]["message"],
                )
            )
            continue
        dependency_by_id[packet_assignment_id] = copy.deepcopy(packet)

    expected_dependencies = (
        set(assignment["depends_on"]) if assignment is not None else set()
    )
    if set(dependency_projection_by_id) != expected_dependencies:
        issues.append(
            _issue(
                "PROJECTION_DEPENDENCY_PROJECTION_SET_INVALID",
                "dependency_projections",
                "Provide exactly one intact source projection for every direct dependency.",
            )
        )
    if set(dependency_by_id) != expected_dependencies:
        issues.append(
            _issue(
                "PROJECTION_DEPENDENCY_SET_INVALID",
                "dependency_packets",
                "Provide exactly one valid Packet for every direct dependency.",
            )
        )

    gap_ids = (
        [
            item["check_id"]
            for item in baseline.get("checks", [])
            if isinstance(item, dict)
            and isinstance(item.get("check_id"), str)
            and item.get("status") == "gap"
        ]
        if isinstance(baseline, dict)
        else []
    )
    if issues:
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "FAIL",
            "execution_status": "INVALID",
            "issues": sorted(
                issues,
                key=lambda item: (item["code"], item["path"], item["message"]),
            ),
            "input": None,
            "writes_performed": False,
        }
    if assignment["mutation_owner"] and gap_ids:
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "BLOCKED",
            "execution_status": "GAPS_PRESENT",
            "issues": [
                _issue(
                    "PROJECTION_COVERAGE_GAP",
                    "engineering_baseline",
                    f"Mutation is blocked by baseline gaps: {', '.join(gap_ids)}.",
                )
            ],
            "input": None,
            "writes_performed": False,
        }
    if assignment["mutation_owner"] and document_selection_blocked:
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "BLOCKED",
            "execution_status": "DOCUMENT_EVIDENCE_INSUFFICIENT",
            "issues": [
                _issue(
                    "PROJECTION_DOCUMENT_SELECTION_INSUFFICIENT",
                    "convention_selection.evidence_status",
                    "Mutation requires a sufficient maestro docs selection; narrow the task or target paths and resolve its missing evidence.",
                )
            ],
            "input": None,
            "writes_performed": False,
        }

    lens_ids = set(assignment["lens_ids"])
    lens_cards = [
        copy.deepcopy(item)
        for item in plan.get("lens_cards", [])
        if item.get("lens_id") in lens_ids
    ]
    artifacts: list[dict[str, Any]] = []
    for artifact in baseline["surface_map"]["artifacts"]:
        target = (
            _regular_file(repo, artifact["path"])
            if artifact["state"] == "existing"
            else None
        )
        artifacts.append(
            {
                "artifact_id": artifact["artifact_id"],
                "path": artifact["path"],
                "state": artifact["state"],
                "sha256": file_sha256(target) if target is not None else None,
            }
        )
    executors = {
        item["executor_id"]: item for item in load_registry()["executors"]
    }
    context = executors[assignment["executor_id"]]["context_policy"]
    assignment_guide_ids = copy.deepcopy(
        assignment.get("decision_guide_ids", [])
    )
    expertise = plan.get("expertise")
    expertise_load_packs: list[dict[str, Any]] = []
    if isinstance(expertise, dict) and assignment_guide_ids:
        selected_guides = set(assignment_guide_ids)
        for pack in expertise.get("pack_cards", []):
            guides = [
                {
                    "guide_id": guide["guide_id"],
                    "skill_id": guide["skill_id"],
                    "resource_path": guide["resource_path"],
                    "skill_definition_digest": guide[
                        "skill_definition_digest"
                    ],
                }
                for guide in pack.get("guides", [])
                if guide.get("guide_id") in selected_guides
            ]
            if guides:
                expertise_load_packs.append(
                    {
                        "expertise_pack_id": pack["expertise_pack_id"],
                        "skill_id": pack["skill_id"],
                        "skill_path": pack["skill_path"],
                        "definition_digest": pack["definition_digest"],
                        "skill_definition_digest": pack[
                            "skill_definition_digest"
                        ],
                        "guides": guides,
                    }
                )
    if assignment["mutation_owner"]:
        expertise_application_mode = "authorized-executor-may-apply"
    elif expertise_load_packs:
        expertise_application_mode = "advisory-only"
    else:
        expertise_application_mode = "not-applicable"

    projected = {
        "schema_version": ASSIGNMENT_INPUT_VERSION,
        "projection_digest": "",
        "plan_id": plan["plan_id"],
        "assignment_id": assignment_id,
        "goal_digest": sha256_text(plan["goal"]),
        "task_contract": copy.deepcopy(plan["task_contract"]),
        "assignment_contract": {
            field: copy.deepcopy(assignment[field])
            for field in sorted(_ASSIGNMENT_FIELDS)
        },
        "surface_map": copy.deepcopy(baseline["surface_map"]),
        "engineering_baseline": copy.deepcopy(baseline["checks"]),
        "selected_lens_cards": lens_cards,
        "decision_guide_ids": assignment_guide_ids,
        "expertise_load": {
            "application_mode": expertise_application_mode,
            "packs": expertise_load_packs,
            "host_attestation": {
                "status": "unavailable",
                "loaded_skill_digests": [],
                "loaded_guide_refs": [],
            },
        },
        "convention_selection": convention_selection,
        "document_refs": documents,
        "artifact_refs": artifacts,
        "dependency_packets": [
            {
                "ref_id": f"dependency-{dependency_id}",
                "assignment_id": dependency_id,
                "projection_digest": _projection_value(
                    dependency_projection_by_id[dependency_id]
                )["projection_digest"],
                "packet": dependency_by_id[dependency_id],
            }
            for dependency_id in assignment["depends_on"]
        ],
        "context_policy": {
            "requests": {
                "fresh_context": (
                    context["fresh_context_supported"] and assignment["read_only"]
                ),
                "read_only": assignment["read_only"],
                "packet_only": context["return_packet_only"],
                "hide_other_lens_conclusions": context[
                    "hide_other_lens_conclusions"
                ],
            },
            "host_attestation": {
                "fresh_context": "unavailable",
                "read_only": "unavailable",
                "packet_only": "unavailable",
            },
            "forbidden": list(_FORBIDDEN_CONTEXT),
        },
    }
    payload = copy.deepcopy(projected)
    payload.pop("projection_digest")
    projected["projection_digest"] = sha256_text(canonical_json(payload))
    return {
        "schema_version": "maestro_assignment_projection_result_v1",
        "status": "PASS",
        "execution_status": (
            "GAPS_PRESENT" if gap_ids else "READY"
        ),
        "issues": [],
        "input": projected,
        "writes_performed": False,
    }
