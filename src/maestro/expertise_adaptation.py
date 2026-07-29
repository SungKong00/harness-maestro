from __future__ import annotations

import copy
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .coverage_admission import validate_task_coverage_admission
from .planning import validate_route_v2
from .surface_classification import BUILDERS, SURFACES
from .task_coverage import validate_task_coverage
from .research import require_completed_research_bundle
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    read_json,
    safe_target,
    sha256_text,
)

ADAPTATION_PLAN_VERSION = "maestro_expertise_adaptation_plan_v1"
ADAPTATION_PLAN_DRAFT_FIELDS = {
    "units",
}
ADAPTATION_PLAN_FIELDS = {
    "schema_version",
    "plan_id",
    "coverage_id",
    "goal_digest",
    "source_route_plan_id",
    "source_route_digest",
    "source_admission_id",
    "signal_fingerprint",
    "units",
    "parallel_groups",
    "max_corrected_routes",
    "execution_authority",
    "writes_performed",
}
UNIT_DRAFT_FIELDS = {
    "unit_id",
    "coverage_item_ids",
    "surface",
    "change_kind",
    "target_ref",
    "depends_on",
    "change_set_id",
    "evidence_refs",
}
UNIT_FIELDS = UNIT_DRAFT_FIELDS | {
    "candidate_builder",
    "research_required",
    "same_task_eligible",
}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FINGERPRINT_PATTERN = re.compile(r"^[a-f0-9]{24}$")
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MAX_UNITS = 64
MAX_REFS = 16
MAX_REF_CHARS = 512
CANDIDATE_ADAPTATION_VERSION = "maestro_task_gap_adaptation_v1"
CANDIDATE_ADAPTATION_FIELDS = {
    "schema_version",
    "coverage_ref",
    "plan_ref",
    "source_route_ref",
    "source_admission_ref",
    "unit_id",
    "authoring_research_ref",
}

SURFACE_CHANGE_KINDS = {
    "none": {"no-change"},
    "checker-schema-test": {"checker-change"},
    "convention": {"convention-change"},
    "decision-guide": {
        "guide-addition",
        "guide-revision",
        "guide-deprecation",
        "guide-move",
        "guide-copy",
    },
    "expertise-pack": {
        "new-pack",
        "pack-revision",
        "pack-merge",
        "pack-extraction",
        "pack-split",
    },
    "lens": {"lens-candidate"},
    "standalone-skill": {"standalone-skill-candidate"},
    "executor-agent": {"registry-candidate"},
    "department": {"registry-candidate"},
    "adapter": {"registry-candidate"},
    "research-lane": {"registry-candidate"},
    "specialist-contract": {"registry-candidate"},
    "packet-contract": {"registry-candidate"},
}
COMPLEX_CHANGE_KINDS = {
    "pack-merge",
    "pack-extraction",
    "pack-split",
    "guide-move",
    "guide-copy",
}
SAME_TASK_SURFACES = {"decision-guide", "expertise-pack"}
TARGET_PREFIXES = {
    "decision-guide": "guide:",
    "expertise-pack": "pack:",
    "lens": "lens:",
}


def _signal_fingerprint(
    *,
    coverage_id: str,
    source_route_plan_id: str,
    source_admission_id: str,
    units: list[dict[str, Any]],
) -> str:
    return sha256_text(
        canonical_json(
            {
                "coverage_id": coverage_id,
                "source_route_plan_id": source_route_plan_id,
                "source_admission_id": source_admission_id,
                "units": units,
            }
        )
    )[:24]


def _unit_evidence_refs(
    item_ids: list[str],
    items_by_id: dict[str, dict[str, Any]],
) -> set[str]:
    return {
        ref
        for item_id in item_ids
        for item in [items_by_id.get(item_id, {})]
        for ref in [
            *(
                item.get("source_refs", [])
                if isinstance(item.get("source_refs"), list)
                else []
            ),
            *[
                allocation.get("target_ref")
                for allocation in (
                    item.get("allocations", [])
                    if isinstance(item.get("allocations"), list)
                    else []
                )
                if isinstance(allocation, dict)
            ],
        ]
        if isinstance(ref, str) and ref
    }


def _classification_evidence_valid(
    refs: Any,
    *,
    item_ids: list[str],
    items_by_id: dict[str, dict[str, Any]],
) -> bool:
    if not _valid_strings(refs, minimum=1, maximum=MAX_REFS):
        return False
    allowed = _unit_evidence_refs(item_ids, items_by_id)
    return all(ref in allowed for ref in refs)


def _candidate_gap_item_ids(
    admission: dict[str, Any],
) -> set[str]:
    gaps = admission.get("gaps", [])
    if not isinstance(gaps, list):
        return set()
    return {
        gap["item_id"]
        for gap in gaps
        if isinstance(gap, dict)
        and isinstance(gap.get("item_id"), str)
        and gap.get("materiality") in {"blocking", "important"}
        and gap.get("adaptation_eligible") is True
    }


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _digest_payload(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload.pop("plan_id", None)
    return sha256_text(canonical_json(payload))


def _valid_strings(
    value: Any,
    *,
    minimum: int = 0,
    maximum: int,
    identifiers: bool = False,
) -> bool:
    if (
        not isinstance(value, list)
        or not minimum <= len(value) <= maximum
        or not all(
            isinstance(item, str)
            and bool(item.strip())
            and len(item) <= MAX_REF_CHARS
            and (
                not identifiers
                or ID_PATTERN.fullmatch(item) is not None
            )
            for item in value
        )
    ):
        return False
    return len(value) == len(set(value))


def _candidate_builder(surface: str) -> str | None:
    return BUILDERS.get(surface)


def _research_required(
    item_ids: list[str],
    items_by_id: dict[str, dict[str, Any]],
) -> bool:
    return any(
        allocation.get("kind") == "research"
        for item_id in item_ids
        for allocation in (
            items_by_id[item_id].get("allocations", [])
            if isinstance(
                items_by_id[item_id].get("allocations", []),
                list,
            )
            else []
        )
        if isinstance(allocation, dict)
    )


def _topological_groups(
    units: list[dict[str, Any]],
) -> list[list[str]] | None:
    if any(
        not isinstance(unit.get("unit_id"), str)
        or not isinstance(unit.get("depends_on"), list)
        or not all(
            isinstance(dependency, str)
            for dependency in unit["depends_on"]
        )
        for unit in units
    ):
        return None
    dependencies = {
        unit["unit_id"]: set(unit["depends_on"])
        for unit in units
    }
    reverse: dict[str, set[str]] = defaultdict(set)
    for unit_id, values in dependencies.items():
        for dependency in values:
            reverse[dependency].add(unit_id)
    groups: list[list[str]] = []
    ready = sorted(
        unit_id for unit_id, values in dependencies.items() if not values
    )
    visited: set[str] = set()
    while ready:
        group = [unit_id for unit_id in ready if unit_id not in visited]
        if not group:
            break
        groups.append(group)
        next_ready: set[str] = set()
        for unit_id in group:
            visited.add(unit_id)
            for dependent in reverse.get(unit_id, set()):
                dependencies[dependent].discard(unit_id)
                if not dependencies[dependent]:
                    next_ready.add(dependent)
        ready = sorted(next_ready)
    return groups if len(visited) == len(units) else None


def _validate_units(
    units: Any,
    *,
    coverage: dict[str, Any],
    source_admission: dict[str, Any],
    draft: bool,
    issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if (
        not isinstance(units, list)
        or not 1 <= len(units) <= MAX_UNITS
    ):
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_UNIT_LIMIT_INVALID",
                "units",
                (
                    "Adaptation must contain one to 64 discovered units; "
                    "units are never truncated to a preferred count."
                ),
            )
        )
        return []

    expected_fields = UNIT_DRAFT_FIELDS if draft else UNIT_FIELDS
    coverage_items = coverage.get("items", [])
    if not isinstance(coverage_items, list):
        coverage_items = []
    items_by_id = {
        item["item_id"]: item
        for item in coverage_items
        if isinstance(item, dict)
        and isinstance(item.get("item_id"), str)
    }
    gap_item_ids = _candidate_gap_item_ids(source_admission)
    unit_ids: set[str] = set()
    claimed_items: dict[str, str] = {}
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(units):
        path = f"units[{index}]"
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_UNIT_INVALID",
                    path,
                    "Adaptation unit fields are incomplete or unknown.",
                )
            )
            continue
        unit_id = raw.get("unit_id")
        surface = raw.get("surface")
        change_kind = raw.get("change_kind")
        item_ids = raw.get("coverage_item_ids")
        if (
            not isinstance(unit_id, str)
            or ID_PATTERN.fullmatch(unit_id) is None
            or unit_id in unit_ids
        ):
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_UNIT_ID_INVALID",
                    f"{path}.unit_id",
                    "unit_id must be a unique lowercase kebab-case ID.",
                )
            )
            continue
        unit_ids.add(unit_id)
        if (
            not _valid_strings(
                item_ids,
                minimum=1,
                maximum=MAX_UNITS,
                identifiers=True,
            )
            or not set(item_ids).issubset(items_by_id)
        ):
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_COVERAGE_ITEMS_INVALID",
                    f"{path}.coverage_item_ids",
                    "Every unit must own one or more existing coverage items.",
                )
            )
            item_ids = []
        for item_id in item_ids:
            if item_id in claimed_items:
                issues.append(
                    _issue(
                        "EXPERTISE_ADAPTATION_COVERAGE_DUPLICATE",
                        f"{path}.coverage_item_ids",
                        (
                            f"Coverage item {item_id} is already owned by "
                            f"{claimed_items[item_id]}."
                        ),
                    )
                )
            else:
                claimed_items[item_id] = unit_id
        surface_valid = (
            isinstance(surface, str)
            and surface in SURFACES
            and isinstance(change_kind, str)
            and change_kind in SURFACE_CHANGE_KINDS.get(surface, set())
        )
        if not surface_valid:
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_SURFACE_INVALID",
                    f"{path}.surface",
                    "Surface and change kind do not share one owning lifecycle.",
                )
            )
        target_ref = raw.get("target_ref")
        expected_prefix = (
            TARGET_PREFIXES.get(surface)
            if isinstance(surface, str)
            else None
        )
        if expected_prefix is None:
            if target_ref is not None and (
                not isinstance(target_ref, str)
                or not target_ref.strip()
                or len(target_ref) > MAX_REF_CHARS
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_ADAPTATION_TARGET_INVALID",
                        f"{path}.target_ref",
                        "target_ref must be null or bounded text.",
                    )
                )
        elif (
            not isinstance(target_ref, str)
            or not target_ref.startswith(expected_prefix)
            or len(target_ref) <= len(expected_prefix)
            or len(target_ref) > MAX_REF_CHARS
        ):
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_TARGET_INVALID",
                    f"{path}.target_ref",
                    f"{surface} units require a {expected_prefix} target.",
                )
            )
        if not _valid_strings(
            raw.get("depends_on"),
            maximum=MAX_UNITS,
            identifiers=True,
        ):
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_DEPENDENCY_INVALID",
                    f"{path}.depends_on",
                    "depends_on must contain unique unit IDs.",
                )
            )
        change_set_id = raw.get("change_set_id")
        if (
            isinstance(change_kind, str)
            and change_kind in COMPLEX_CHANGE_KINDS
        ):
            if (
                not isinstance(change_set_id, str)
                or ID_PATTERN.fullmatch(change_set_id) is None
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_ADAPTATION_CHANGE_SET_REQUIRED",
                        f"{path}.change_set_id",
                        (
                            "Merge, extraction, split, move, and copy "
                            "require an atomic ChangeSet ID."
                        ),
                    )
                )
        elif change_set_id is not None:
            if (
                not isinstance(change_set_id, str)
                or ID_PATTERN.fullmatch(change_set_id) is None
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_ADAPTATION_CHANGE_SET_INVALID",
                        f"{path}.change_set_id",
                        "change_set_id must be null or a lowercase ID.",
                    )
                )
        if not _classification_evidence_valid(
            raw.get("evidence_refs"),
            item_ids=item_ids,
            items_by_id=items_by_id,
        ):
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_EVIDENCE_REQUIRED",
                    f"{path}.evidence_refs",
                    (
                        "Every unit needs classification evidence copied from "
                        "its bound Coverage sources or allocations. A "
                        "self-declared classification digest is not authority."
                    ),
                )
            )
        builder = (
            _candidate_builder(surface)
            if isinstance(surface, str)
            else None
        )
        if (
            builder is not None
            and not set(item_ids).intersection(gap_item_ids)
        ):
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_SOURCE_GAP_REQUIRED",
                    f"{path}.coverage_item_ids",
                    (
                        "Durable candidate work requires an unresolved "
                        "blocking or important allocation in the bound "
                        "initial admission."
                    ),
                )
            )
        if draft:
            normalized.append(
                {
                    **copy.deepcopy(raw),
                    "candidate_builder": builder,
                    "research_required": _research_required(
                        item_ids,
                        items_by_id,
                    ),
                    "same_task_eligible": (
                        isinstance(surface, str)
                        and surface in SAME_TASK_SURFACES
                        and change_kind not in COMPLEX_CHANGE_KINDS
                    ),
                }
            )
        else:
            expected_builder = (
                _candidate_builder(surface)
                if isinstance(surface, str)
                else None
            )
            expected_research = _research_required(item_ids, items_by_id)
            if raw.get("candidate_builder") != expected_builder:
                issues.append(
                    _issue(
                        "EXPERTISE_ADAPTATION_BUILDER_MISMATCH",
                        f"{path}.candidate_builder",
                        "candidate_builder does not match the classified surface.",
                    )
                )
            if raw.get("research_required") is not expected_research:
                issues.append(
                    _issue(
                        "EXPERTISE_ADAPTATION_RESEARCH_MISMATCH",
                        f"{path}.research_required",
                        "research_required must reflect the unit's coverage allocations.",
                    )
                )
            if raw.get("same_task_eligible") is not (
                isinstance(surface, str)
                and surface in SAME_TASK_SURFACES
                and change_kind not in COMPLEX_CHANGE_KINDS
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_ADAPTATION_ELIGIBILITY_MISMATCH",
                        f"{path}.same_task_eligible",
                        "Only Expertise Pack and Guide candidates may be same-task eligible.",
                    )
                )
            normalized.append(copy.deepcopy(raw))

    expected_item_ids = set(items_by_id)
    missing = sorted(expected_item_ids - set(claimed_items))
    if missing:
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_COVERAGE_MISSING",
                "units",
                (
                    "Every discovered coverage item must be allocated before "
                    "work distribution: " + ", ".join(missing)
                ),
            )
        )

    normalized_by_id = {
        unit["unit_id"]: unit
        for unit in normalized
        if isinstance(unit.get("unit_id"), str)
    }
    for index, unit in enumerate(normalized):
        unit_id = unit["unit_id"]
        dependencies = unit.get("depends_on", [])
        unknown = (
            sorted(set(dependencies) - set(normalized_by_id))
            if isinstance(dependencies, list)
            and all(isinstance(item, str) for item in dependencies)
            else []
        )
        if unit_id in dependencies or unknown:
            issues.append(
                _issue(
                    "EXPERTISE_ADAPTATION_DEPENDENCY_INVALID",
                    f"units[{index}].depends_on",
                    (
                        "Dependencies must name other declared units"
                        + (
                            f": {', '.join(unknown)}"
                            if unknown
                            else "."
                        )
                    ),
                )
            )
    for item_id, item in items_by_id.items():
        owner = claimed_items.get(item_id)
        if owner is None:
            continue
        dependency_item_ids = item.get("depends_on", [])
        if not isinstance(dependency_item_ids, list):
            continue
        for dependency_item_id in dependency_item_ids:
            dependency_owner = claimed_items.get(dependency_item_id)
            owner_dependencies = normalized_by_id.get(owner, {}).get(
                "depends_on",
                [],
            )
            if (
                dependency_owner is not None
                and dependency_owner != owner
                and (
                    not isinstance(owner_dependencies, list)
                    or dependency_owner not in owner_dependencies
                )
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_ADAPTATION_DEPENDENCY_MISSING",
                        f"units.{owner}.depends_on",
                        (
                            f"{owner} must depend on {dependency_owner} because "
                            f"coverage item {item_id} depends on "
                            f"{dependency_item_id}."
                        ),
                    )
                )
    return normalized


def validate_expertise_adaptation_plan(
    plan: Any,
    *,
    coverage: Any,
    source_route: Any,
    source_admission: Any,
    goal: str,
    repo_path: str | Path,
    require_current_revision: bool = True,
) -> dict[str, Any]:
    """Validate complete discovery-to-work allocation without executing it."""

    ensure_repo(repo_path)
    issues: list[dict[str, str]] = []
    coverage_validation = validate_task_coverage(
        coverage,
        goal=goal,
        repo_path=repo_path,
        require_current_revision=require_current_revision,
    )
    if coverage_validation["status"] != "PASS":
        issues.extend(coverage_validation["issues"])
    route_validation = validate_route_v2(
        source_route,
        repo_path=repo_path,
    )
    if route_validation["status"] != "PASS":
        issues.extend(route_validation["issues"])
    admission_validation = validate_task_coverage_admission(
        source_admission,
        repo_path=repo_path,
        goal=goal,
        coverage=coverage,
        plan=source_route,
        require_current_revision=require_current_revision,
    )
    if admission_validation["status"] != "PASS":
        issues.extend(admission_validation["issues"])
    if not isinstance(plan, dict) or set(plan) != ADAPTATION_PLAN_FIELDS:
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_PLAN_INVALID",
                "$",
                "Adaptation plan fields are incomplete or unknown.",
            )
        )
        return {
            "schema_version": "maestro_expertise_adaptation_validation_v1",
            "status": "FAIL",
            "coverage_status": "INVALID",
            "issues": issues,
            "execution_authority": "NONE",
            "writes_performed": False,
        }
    if plan.get("schema_version") != ADAPTATION_PLAN_VERSION:
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_VERSION_INVALID",
                "schema_version",
                f"Expected {ADAPTATION_PLAN_VERSION}.",
            )
        )
    if (
        not isinstance(plan.get("plan_id"), str)
        or DIGEST_PATTERN.fullmatch(plan["plan_id"]) is None
        or plan["plan_id"] != _digest_payload(plan)
    ):
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_DIGEST_INVALID",
                "plan_id",
                "plan_id does not bind the complete adaptation plan.",
            )
        )
    if (
        not isinstance(coverage, dict)
        or plan.get("coverage_id") != coverage.get("coverage_id")
        or plan.get("goal_digest") != coverage.get("goal_digest")
    ):
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_COVERAGE_MISMATCH",
                "coverage_id",
                "Adaptation plan is bound to a different Task Coverage artifact.",
            )
        )
    if (
        not isinstance(source_route, dict)
        or plan.get("source_route_plan_id") != source_route.get("plan_id")
        or plan.get("source_route_digest")
        != source_route.get("source_route_digest")
        or source_route.get("goal") != goal
    ):
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_ROUTE_MISMATCH",
                "source_route_plan_id",
                "Adaptation plan is bound to a different original route.",
            )
        )
    if (
        not isinstance(source_admission, dict)
        or plan.get("source_admission_id")
        != source_admission.get("admission_id")
        or source_admission.get("coverage_id")
        != plan.get("coverage_id")
        or source_admission.get("plan_id")
        != plan.get("source_route_plan_id")
    ):
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_ADMISSION_MISMATCH",
                "source_admission_id",
                "Adaptation must bind the exact initial Coverage admission.",
            )
        )
    if (
        not isinstance(plan.get("signal_fingerprint"), str)
        or FINGERPRINT_PATTERN.fullmatch(plan["signal_fingerprint"]) is None
    ):
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_SIGNAL_INVALID",
                "signal_fingerprint",
                "signal_fingerprint must be a stable 24-character digest prefix.",
            )
        )
    units = _validate_units(
        plan.get("units"),
        coverage=coverage if isinstance(coverage, dict) else {},
        source_admission=(
            source_admission
            if isinstance(source_admission, dict)
            else {}
        ),
        draft=False,
        issues=issues,
    )
    if (
        isinstance(coverage, dict)
        and isinstance(source_route, dict)
        and isinstance(source_admission, dict)
        and isinstance(plan.get("signal_fingerprint"), str)
        and plan["signal_fingerprint"]
        != _signal_fingerprint(
            coverage_id=coverage.get("coverage_id", ""),
            source_route_plan_id=source_route.get("plan_id", ""),
            source_admission_id=source_admission.get(
                "admission_id",
                "",
            ),
            units=units,
        )
    ):
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_SIGNAL_MISMATCH",
                "signal_fingerprint",
                (
                    "signal_fingerprint must be derived from the exact "
                    "Coverage, initial admission, route, and unit allocation."
                ),
            )
        )
    groups = _topological_groups(units) if units else None
    if groups is None:
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_DEPENDENCY_CYCLE",
                "units",
                "Adaptation unit dependencies must be acyclic.",
            )
        )
    elif plan.get("parallel_groups") != groups:
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_PARALLEL_GROUPS_INVALID",
                "parallel_groups",
                (
                    "parallel_groups must contain every independent unit in "
                    "deterministic topological layers."
                ),
            )
        )
    if plan.get("max_corrected_routes") != 1:
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_REROUTE_LIMIT_INVALID",
                "max_corrected_routes",
                "Same-task adaptation permits exactly one corrected route.",
            )
        )
    if (
        plan.get("execution_authority") != "NONE"
        or plan.get("writes_performed") is not False
    ):
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_AUTHORITY_INVALID",
                "execution_authority",
                "Adaptation planning is read-only and grants no execution authority.",
            )
        )
    return {
        "schema_version": "maestro_expertise_adaptation_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "coverage_status": (
            "ALLOCATED" if not issues else "INVALID"
        ),
        "unit_count": len(units),
        "parallel_group_count": len(groups or []),
        "issues": issues,
        "execution_authority": "NONE",
        "writes_performed": False,
    }


def build_expertise_adaptation_plan(
    repo_path: str | Path,
    *,
    goal: str,
    coverage: Any,
    source_route: Any,
    source_admission: Any,
    draft: Any,
) -> dict[str, Any]:
    """Bind all discovered coverage items before distributing candidate work."""

    ensure_repo(repo_path)
    coverage_validation = validate_task_coverage(
        coverage,
        goal=goal,
        repo_path=repo_path,
    )
    if (
        coverage_validation["status"] != "PASS"
        or coverage_validation["coverage_status"] != "COMPLETE"
    ):
        raise MaestroError(
            "EXPERTISE_ADAPTATION_COVERAGE_REQUIRED",
            "A complete current Task Coverage artifact is required.",
        )
    route_validation = validate_route_v2(
        source_route,
        repo_path=repo_path,
    )
    if route_validation["status"] != "PASS":
        first = route_validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    admission_validation = validate_task_coverage_admission(
        source_admission,
        repo_path=repo_path,
        goal=goal,
        coverage=coverage,
        plan=source_route,
    )
    if admission_validation["status"] != "PASS":
        first = admission_validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    if (
        not isinstance(draft, dict)
        or set(draft) != ADAPTATION_PLAN_DRAFT_FIELDS
    ):
        raise MaestroError(
            "EXPERTISE_ADAPTATION_DRAFT_INVALID",
            "Draft must contain only the complete discovered unit list.",
        )
    issues: list[dict[str, str]] = []
    units = _validate_units(
        draft.get("units"),
        coverage=coverage,
        source_admission=source_admission,
        draft=True,
        issues=issues,
    )
    groups = _topological_groups(units) if units else None
    if groups is None:
        issues.append(
            _issue(
                "EXPERTISE_ADAPTATION_DEPENDENCY_CYCLE",
                "units",
                "Adaptation unit dependencies must be acyclic.",
            )
        )
    if issues:
        raise MaestroError(
            "EXPERTISE_ADAPTATION_DRAFT_INVALID",
            "; ".join(issue["message"] for issue in issues),
        )
    plan = {
        "schema_version": ADAPTATION_PLAN_VERSION,
        "plan_id": "",
        "coverage_id": coverage["coverage_id"],
        "goal_digest": coverage["goal_digest"],
        "source_route_plan_id": source_route["plan_id"],
        "source_route_digest": source_route["source_route_digest"],
        "source_admission_id": source_admission["admission_id"],
        "signal_fingerprint": _signal_fingerprint(
            coverage_id=coverage["coverage_id"],
            source_route_plan_id=source_route["plan_id"],
            source_admission_id=source_admission["admission_id"],
            units=units,
        ),
        "units": units,
        "parallel_groups": groups,
        "max_corrected_routes": 1,
        "execution_authority": "NONE",
        "writes_performed": False,
    }
    plan["plan_id"] = _digest_payload(plan)
    validation = validate_expertise_adaptation_plan(
        plan,
        coverage=coverage,
        source_route=source_route,
        source_admission=source_admission,
        goal=goal,
        repo_path=repo_path,
    )
    if validation["status"] != "PASS":
        raise MaestroError(
            "EXPERTISE_ADAPTATION_PLAN_INVALID",
            "; ".join(issue["message"] for issue in validation["issues"]),
        )
    return plan


def _artifact_reference_valid(
    value: Any,
    *,
    expected_path: str,
) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"path", "sha256"}
        and value.get("path") == expected_path
        and isinstance(value.get("sha256"), str)
        and DIGEST_PATTERN.fullmatch(value["sha256"]) is not None
    )


def _read_candidate_artifact(
    root: Path,
    reference: dict[str, str],
) -> Any:
    target = safe_target(root, reference["path"])
    if (
        target.is_symlink()
        or not target.is_file()
        or file_sha256(target) != reference["sha256"]
    ):
        raise MaestroError(
            "EXPERTISE_ADAPTATION_ARTIFACT_INVALID",
            (
                "Task-gap adaptation artifact is missing, unsafe, or has "
                f"a different digest: {reference['path']}"
            ),
        )
    return read_json(target)


def validate_task_gap_candidate_lineage(
    repo_path: str | Path,
    candidate_root: Path,
    candidate: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    """Resolve the strict lineage used only by new task-gap candidates."""

    generation = candidate.get("generation")
    if (
        not isinstance(generation, dict)
        or generation.get("mode") != "task-gap"
    ):
        return [], None
    issues: list[dict[str, str]] = []
    adaptation = candidate.get("adaptation")
    if (
        not isinstance(adaptation, dict)
        or set(adaptation) != CANDIDATE_ADAPTATION_FIELDS
        or adaptation.get("schema_version")
        != CANDIDATE_ADAPTATION_VERSION
        or not _artifact_reference_valid(
            adaptation.get("coverage_ref"),
            expected_path="evidence/task-coverage.json",
        )
        or not _artifact_reference_valid(
            adaptation.get("plan_ref"),
            expected_path="evidence/adaptation-plan.json",
        )
        or not _artifact_reference_valid(
            adaptation.get("source_route_ref"),
            expected_path="evidence/source-route.json",
        )
        or not _artifact_reference_valid(
            adaptation.get("source_admission_ref"),
            expected_path="evidence/source-admission.json",
        )
        or not isinstance(adaptation.get("unit_id"), str)
        or ID_PATTERN.fullmatch(adaptation["unit_id"]) is None
        or (
            adaptation.get("authoring_research_ref") is not None
            and not _artifact_reference_valid(
                adaptation["authoring_research_ref"],
                expected_path="evidence/research-bundle.json",
            )
        )
    ):
        return [
            _issue(
                "EXPERTISE_TASK_GAP_ADAPTATION_INVALID",
                "candidate.json.adaptation",
                (
                    "task-gap generation requires exact Coverage, adaptation "
                    "plan, source route, unit, and optional research references."
                ),
            )
        ], None
    try:
        coverage = _read_candidate_artifact(
            candidate_root,
            adaptation["coverage_ref"],
        )
        plan = _read_candidate_artifact(
            candidate_root,
            adaptation["plan_ref"],
        )
        source_route = _read_candidate_artifact(
            candidate_root,
            adaptation["source_route_ref"],
        )
        source_admission = _read_candidate_artifact(
            candidate_root,
            adaptation["source_admission_ref"],
        )
    except MaestroError as exc:
        return [
            _issue(exc.code, "candidate.json.adaptation", exc.message)
        ], None
    goal = coverage.get("goal") if isinstance(coverage, dict) else None
    if not isinstance(goal, str):
        issues.append(
            _issue(
                "EXPERTISE_TASK_GAP_COVERAGE_INVALID",
                adaptation["coverage_ref"]["path"],
                "Copied Task Coverage has no exact goal.",
            )
        )
    else:
        validation = validate_expertise_adaptation_plan(
            plan,
            coverage=coverage,
            source_route=source_route,
            source_admission=source_admission,
            goal=goal,
            repo_path=repo_path,
            require_current_revision=False,
        )
        if validation["status"] != "PASS":
            issues.extend(validation["issues"])
    unit = next(
        (
            item
            for item in plan.get("units", [])
            if isinstance(item, dict)
            and item.get("unit_id") == adaptation["unit_id"]
        ),
        None,
    ) if isinstance(plan, dict) else None
    component_change = candidate.get("component_change")
    component_kind = (
        component_change.get("kind")
        if isinstance(component_change, dict)
        else (
            "guide-addition"
            if candidate.get("expertise_pack_id")
            and candidate.get("coverage")
            else "new-pack"
        )
    )
    expected_same_task_eligibility = (
        component_kind not in COMPLEX_CHANGE_KINDS
    )
    if (
        not isinstance(unit, dict)
        or unit.get("surface") not in SAME_TASK_SURFACES
        or (
            unit.get("same_task_eligible")
            is not expected_same_task_eligibility
        )
        or unit.get("change_kind") != component_kind
        or plan.get("signal_fingerprint")
        != generation.get("signal_fingerprint")
    ):
        issues.append(
            _issue(
                "EXPERTISE_TASK_GAP_UNIT_MISMATCH",
                "candidate.json.adaptation.unit_id",
                (
                    "Candidate must match one Expertise adaptation unit, its "
                    "routing eligibility, and its stable signal fingerprint."
                ),
            )
        )
    else:
        declared_change_set = (
            component_change.get("change_set_id")
            if isinstance(component_change, dict)
            else None
        )
        if unit.get("change_set_id") != declared_change_set:
            issues.append(
                _issue(
                    "EXPERTISE_TASK_GAP_CHANGE_SET_MISMATCH",
                    "candidate.json.component_change.change_set_id",
                    (
                        "Candidate and adaptation unit must name the exact "
                        "same ChangeSet."
                    ),
                )
            )
        target_ref = unit.get("target_ref")
        pack_id = candidate.get("expertise_pack_id")
        if unit["surface"] == "expertise-pack":
            target_matches = target_ref == f"pack:{pack_id}"
        else:
            target_guide_id = (
                component_change.get("target_guide_id")
                if isinstance(component_change, dict)
                else None
            )
            target_matches = target_ref in {
                f"guide:{target_guide_id}",
                f"guide:{pack_id}/{target_guide_id}",
            }
        if not target_matches:
            issues.append(
                _issue(
                    "EXPERTISE_TASK_GAP_TARGET_MISMATCH",
                    "candidate.json.adaptation.unit_id",
                    "Adaptation unit target does not match the candidate Pack or Guide.",
                )
            )

    research_digest: str | None = None
    research_ref = adaptation.get("authoring_research_ref")
    research_required = (
        unit.get("research_required") is True
        if isinstance(unit, dict)
        else False
    )
    if research_required and research_ref is None:
        issues.append(
            _issue(
                "EXPERTISE_TASK_GAP_RESEARCH_REQUIRED",
                "candidate.json.adaptation.authoring_research_ref",
                "This unit needs one completed authoring ResearchBundle.",
            )
        )
    elif not research_required and research_ref is not None:
        issues.append(
            _issue(
                "EXPERTISE_TASK_GAP_RESEARCH_NOT_APPLICABLE",
                "candidate.json.adaptation.authoring_research_ref",
                "A unit without a research allocation cannot claim a research bundle.",
            )
        )
    elif research_ref is not None and isinstance(goal, str):
        try:
            research = _read_candidate_artifact(
                candidate_root,
                research_ref,
            )
            research_validation = require_completed_research_bundle(
                research,
                goal=goal,
                expertise={
                    "selected_pack_ids": [],
                    "selected_guide_ids": [],
                    "pack_definition_digests": {},
                    "research_requirement": {"mode": "discover"},
                },
                repo_path=repo_path,
            )
            if research.get("depth") != "deep":
                issues.append(
                    _issue(
                        "EXPERTISE_TASK_GAP_RESEARCH_DEPTH_INVALID",
                        research_ref["path"],
                        "Task-gap Expertise authoring requires deep research.",
                    )
                )
            else:
                research_digest = research_validation["artifact_digest"]
        except MaestroError as exc:
            issues.append(
                _issue(
                    exc.code,
                    research_ref["path"],
                    exc.message,
                )
            )
    if issues:
        return issues, None
    assert isinstance(unit, dict)
    return [], {
        "coverage_id": coverage["coverage_id"],
        "goal": goal,
        "goal_digest": coverage["goal_digest"],
        "plan_id": plan["plan_id"],
        "source_route_plan_id": plan["source_route_plan_id"],
        "source_route_digest": plan["source_route_digest"],
        "source_admission_id": plan["source_admission_id"],
        "unit_id": unit["unit_id"],
        "coverage_item_ids": list(unit["coverage_item_ids"]),
        "surface": unit["surface"],
        "change_kind": unit["change_kind"],
        "same_task_eligible": unit["same_task_eligible"],
        "research_required": research_required,
        "authoring_research_digest": research_digest,
        "max_corrected_routes": plan["max_corrected_routes"],
        "change_set_id": unit.get("change_set_id"),
    }


def task_gap_candidate_binding(
    repo_path: str | Path,
    candidate_id: str,
) -> dict[str, Any] | None:
    """Return resolved task-gap lineage without evaluating candidate quality."""

    repo = ensure_repo(repo_path)
    if (
        not isinstance(candidate_id, str)
        or ID_PATTERN.fullmatch(candidate_id) is None
    ):
        return None
    root = safe_target(
        repo,
        f".maestro/state/candidates/expertise/{candidate_id}",
    )
    candidate_path = safe_target(root, "candidate.json")
    if (
        root.is_symlink()
        or not root.is_dir()
        or candidate_path.is_symlink()
        or not candidate_path.is_file()
    ):
        return None
    try:
        candidate = read_json(candidate_path)
        issues, binding = validate_task_gap_candidate_lineage(
            repo,
            root,
            candidate,
        )
    except MaestroError:
        return None
    if issues or binding is None:
        return None
    return {
        **binding,
        "candidate_id": candidate_id,
        "expertise_pack_id": candidate.get("expertise_pack_id"),
        "target_guide_id": (
            candidate.get("component_change", {}).get("target_guide_id")
            if isinstance(candidate.get("component_change"), dict)
            else None
        ),
    }
