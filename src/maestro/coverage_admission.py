from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .coverage_projection import validate_coverage_projection
from .execution_contracts import normalize_execution_contract
from .expertise import load_expertise_catalog
from .expertise_work import (
    validate_expertise_work_closure,
    validate_expertise_work_plan,
)
from .task_coverage import validate_task_coverage
from .util import canonical_json, ensure_repo, sha256_text

COVERAGE_ADMISSION_VERSION = "maestro_task_coverage_admission_v1"
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_CANDIDATES = 64
MAX_PROJECTIONS = 64
HOST_PROJECTION_KINDS = {
    "project-fact",
    "owner-decision",
    "runtime-verification",
    "checker",
    "convention",
    "deferred-explicit",
    "out-of-scope-explicit",
}
ADAPTATION_ELIGIBLE_GAP_REASONS = {
    "guide-unavailable",
    "research-not-completed",
}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _digest_payload(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload.pop("admission_id", None)
    return sha256_text(canonical_json(payload))


def _valid_ids(value: Any, *, maximum: int) -> bool:
    if (
        not isinstance(value, list)
        or len(value) > maximum
        or not all(
            isinstance(item, str)
            and ID_PATTERN.fullmatch(item) is not None
            for item in value
        )
    ):
        return False
    return len(value) == len(set(value))


def _guide_selected(target_ref: str, expertise: dict[str, Any]) -> bool:
    target = target_ref.removeprefix("guide:")
    selected_packs = expertise.get("selected_pack_ids", [])
    selected_guides = expertise.get("selected_guide_ids", [])
    if (
        not isinstance(selected_packs, list)
        or not isinstance(selected_guides, list)
    ):
        return False
    if "/" in target:
        pack_id, guide_id = target.split("/", 1)
        return (
            pack_id in selected_packs
            and guide_id in selected_guides
        )
    return target in selected_guides


def _eligible_guide_target_counts(repo: Path) -> dict[str, int]:
    """Index eligible current Guide targets once for admission diagnostics."""

    counts: dict[str, int] = {}
    for pack in load_expertise_catalog(repo, include_candidates=True):
        if pack.get("status") not in {"pilot", "active"}:
            continue
        pack_id = pack.get("expertise_pack_id")
        if not isinstance(pack_id, str):
            continue
        for guide in pack.get("guides", []):
            guide_id = (
                guide.get("guide_id")
                if isinstance(guide, dict)
                else None
            )
            if not isinstance(guide_id, str):
                continue
            for target in (guide_id, f"{pack_id}/{guide_id}"):
                counts[target] = counts.get(target, 0) + 1
    return counts


def _eligible_task_gap_bindings(
    repo: Path,
    plan: dict[str, Any],
    coverage: dict[str, Any],
    candidate_ids: list[str],
) -> list[dict[str, Any]]:
    if not candidate_ids:
        return []
    from .expertise_adaptation import task_gap_candidate_binding
    from .expertise import candidate_expertise_statuses
    from .expertise_lifecycle import validate_expertise_candidate

    statuses = candidate_expertise_statuses(repo)
    expertise = plan.get("expertise", {})
    route_hints = (
        expertise.get("route_hints")
        if isinstance(expertise, dict)
        else None
    )
    if (
        not isinstance(route_hints, dict)
        or route_hints.get("route_attempt") != 2
    ):
        return []
    selected_packs = expertise.get("selected_pack_ids", [])
    selected_guides = expertise.get("selected_guide_ids", [])
    if (
        not isinstance(selected_packs, list)
        or not isinstance(selected_guides, list)
    ):
        return []
    bindings: list[dict[str, Any]] = []
    for candidate_id in candidate_ids:
        validation = validate_expertise_candidate(repo, candidate_id)
        status = statuses.get(candidate_id, {})
        binding = task_gap_candidate_binding(repo, candidate_id)
        if (
            validation["status"] != "PASS"
            or status.get("runtime_status") != "available"
            or status.get("corrected_task_gap_allowed") is not True
            or not isinstance(binding, dict)
            or binding.get("same_task_eligible") is not True
            or binding.get("coverage_id") != coverage.get("coverage_id")
            or binding.get("goal_digest") != coverage.get("goal_digest")
            or binding.get("expertise_pack_id")
            not in selected_packs
            or route_hints.get("prior_plan_id")
            != binding.get("source_route_plan_id")
            or route_hints.get("prior_source_route_digest")
            != binding.get("source_route_digest")
            or binding.get("max_corrected_routes") != 1
        ):
            continue
        if binding.get("surface") == "decision-guide":
            guide_id = binding.get("target_guide_id")
            if (
                isinstance(guide_id, str)
                and guide_id
                not in selected_guides
            ):
                continue
        bindings.append(binding)
    return bindings


def build_task_coverage_admission(
    repo_path: str | Path,
    *,
    goal: str,
    coverage: Any,
    plan: Any,
    projected_item_ids: list[str] | None = None,
    candidate_ids: list[str] | None = None,
    coverage_projection: Any | None = None,
    expertise_work_plan: Any | None = None,
    expertise_closure: Any | None = None,
    research_bundle: dict[str, Any] | None = None,
    expertise_research_bundles: Any = None,
) -> dict[str, Any]:
    """Compare declared coverage with one concrete route without executing it."""

    repo = ensure_repo(repo_path)
    projected: Any = (
        [] if projected_item_ids is None else copy.deepcopy(projected_item_ids)
    )
    candidates: Any = (
        [] if candidate_ids is None else copy.deepcopy(candidate_ids)
    )
    issues: list[dict[str, str]] = []
    if not _valid_ids(projected, maximum=MAX_PROJECTIONS):
        issues.append(
            _issue(
                "TASK_COVERAGE_PROJECTION_IDS_INVALID",
                "projected_item_ids",
                "Projected item IDs must be unique lowercase coverage IDs.",
            )
        )
        projected = []
    if not _valid_ids(candidates, maximum=MAX_CANDIDATES):
        issues.append(
            _issue(
                "TASK_COVERAGE_CANDIDATE_IDS_INVALID",
                "candidate_ids",
                "Candidate IDs must be unique lowercase IDs.",
            )
        )
        candidates = []
    coverage_validation = validate_task_coverage(
        coverage,
        goal=goal,
        repo_path=repo,
        require_current_revision=True,
    )
    if coverage_validation["status"] != "PASS":
        issues.extend(coverage_validation["issues"])
    execution_context = normalize_execution_contract(
        plan,
        repo_path=repo,
        research_bundle=research_bundle,
    )
    if execution_context["status"] != "PASS":
        issues.extend(execution_context["issues"])
    route_plan = (
        execution_context["route_plan"]
        if execution_context["status"] == "PASS"
        else {}
    )
    if (
        not isinstance(coverage, dict)
        or not isinstance(route_plan, dict)
        or coverage.get("goal") != route_plan.get("goal")
        or coverage.get("goal_digest") != sha256_text(goal)
    ):
        issues.append(
            _issue(
                "TASK_COVERAGE_ADMISSION_GOAL_MISMATCH",
                "goal",
                "Coverage and route must bind the exact same goal.",
            )
        )
    item_ids = {
        item.get("item_id")
        for item in coverage.get("items", [])
        if isinstance(item, dict)
        and isinstance(item.get("item_id"), str)
    } if isinstance(coverage, dict) else set()
    unknown_projected = sorted(set(projected) - item_ids)
    if unknown_projected:
        issues.append(
            _issue(
                "TASK_COVERAGE_PROJECTION_UNKNOWN",
                "projected_item_ids",
                "Projected coverage items do not exist: "
                + ", ".join(unknown_projected),
            )
        )

    bindings = (
        _eligible_task_gap_bindings(
            repo,
            route_plan,
            coverage,
            candidates,
        )
        if (
            isinstance(coverage, dict)
            and isinstance(route_plan, dict)
        )
        else []
    )
    eligible_candidate_ids = {
        binding.get("candidate_id")
        for binding in bindings
        if isinstance(binding.get("candidate_id"), str)
    }
    ineligible_candidates = sorted(
        set(candidates) - eligible_candidate_ids
    )
    if ineligible_candidates:
        issues.append(
            _issue(
                "TASK_COVERAGE_CANDIDATE_INELIGIBLE",
                "candidate_ids",
                (
                    "Candidate IDs must be valid task-gap candidates bound "
                    "to this exact corrected route: "
                    + ", ".join(ineligible_candidates)
                ),
            )
        )
    compiled_item_ids = {
        item_id
        for binding in bindings
        for item_id in binding.get("coverage_item_ids", [])
    }
    projected_allocations: set[tuple[str, str]] = set()
    coverage_projection_id: str | None = None
    if coverage_projection is not None:
        projection_validation = validate_coverage_projection(
            coverage_projection,
            repo_path=repo,
            goal=goal,
            coverage=coverage,
            plan=plan,
            research_bundle=research_bundle,
        )
        if projection_validation["status"] != "PASS":
            issues.extend(projection_validation["issues"])
        else:
            coverage_projection_id = coverage_projection["projection_id"]
            projected_allocations = {
                (entry["item_id"], entry["target_ref"])
                for entry in coverage_projection["entries"]
            }

    closed_expertise_pairs: set[tuple[str, str]] = set()
    expertise_work_plan_id: str | None = None
    expertise_closure_id: str | None = None
    if (expertise_work_plan is None) != (expertise_closure is None):
        issues.append(
            _issue(
                "TASK_COVERAGE_EXPERTISE_CLOSURE_INCOMPLETE",
                "expertise_closure",
                "Expertise work plan and closure must be supplied together.",
            )
        )
    elif (
        expertise_work_plan is None
        and expertise_research_bundles
    ):
        issues.append(
            _issue(
                "TASK_COVERAGE_EXPERTISE_RESEARCH_UNEXPECTED",
                "expertise_research_bundles",
                (
                    "Pack-bound Expertise research evidence requires its exact "
                    "work plan and closure."
                ),
            )
        )
    elif expertise_work_plan is not None:
        decision_evidence = (
            plan.get("decision_evidence")
            if isinstance(plan, dict)
            and plan.get("schema_version")
            == "maestro_execution_plan_v1"
            and isinstance(plan.get("decision_evidence"), dict)
            else None
        )
        if decision_evidence is not None and (
            decision_evidence.get("task_coverage") != coverage
            or decision_evidence.get("expertise_work_plan")
            != expertise_work_plan
            or decision_evidence.get("expertise_work_closure")
            != expertise_closure
            or decision_evidence.get("expertise_research_bundles")
            != (expertise_research_bundles or [])
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_DECISION_EXPERTISE_MISMATCH",
                    "expertise_work_plan",
                    (
                        "Decision enactment must reuse the exact embedded "
                        "Coverage, Expertise work plan, READY closure, and "
                        "Pack research sidecars."
                    ),
                )
            )
        work_validation = validate_expertise_work_plan(
            expertise_work_plan,
            repo_path=repo,
            goal=goal,
            coverage=coverage,
            plan=plan,
            research_bundle=research_bundle,
            expertise_research_bundles=expertise_research_bundles,
        )
        if work_validation["status"] != "PASS":
            issues.extend(work_validation["issues"])
        elif work_validation.get("execution_status") != "READY":
            issues.append(
                _issue(
                    "TASK_COVERAGE_EXPERTISE_ROUTE_UPGRADE_REQUIRED",
                    "expertise_work_plan.batches",
                    (
                        "Legacy Expertise batches cannot satisfy new writer "
                        "Coverage; rebuild the work plan with typed stage routes."
                    ),
                )
            )
        else:
            closure_validation = validate_expertise_work_closure(
                expertise_closure,
                work_plan=expertise_work_plan,
            )
            if closure_validation["status"] != "PASS":
                issues.extend(closure_validation["issues"])
            elif closure_validation["execution_status"] != "READY":
                issues.append(
                    _issue(
                        "TASK_COVERAGE_EXPERTISE_CLOSURE_BLOCKED",
                        "expertise_closure.status",
                        "Blocked, failed, conflicted, or unresolved Expertise work cannot satisfy Coverage.",
                    )
                )
            else:
                expertise_work_plan_id = expertise_work_plan["work_plan_id"]
                expertise_closure_id = expertise_closure["closure_id"]
                closed_pair_ids = set(
                    expertise_closure["terminal_pair_ids"]
                )
                closed_expertise_pairs = {
                    (
                        pair["coverage_item_id"],
                        pair["target_ref"],
                    )
                    for pair in expertise_work_plan["pairs"]
                    if pair["pair_id"] in closed_pair_ids
                }
    expertise = (
        route_plan.get("expertise", {})
        if isinstance(route_plan, dict)
        and isinstance(route_plan.get("expertise"), dict)
        else {}
    )
    research_gate = expertise.get("research_requirement", {})
    research_satisfied = (
        isinstance(research_gate, dict)
        and research_gate.get("gate") == "satisfied"
        and research_bundle is not None
        and execution_context.get("execution_status") == "READY"
    )
    raw_selected_lenses = (
        route_plan.get("selected_lenses", [])
        if isinstance(route_plan, dict)
        else []
    )
    selected_lenses = (
        set(raw_selected_lenses)
        if isinstance(raw_selected_lenses, list)
        and all(isinstance(item, str) for item in raw_selected_lenses)
        else set()
    )
    guide_target_counts = _eligible_guide_target_counts(repo)

    resolutions: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    projection_required: list[str] = []
    for item in (
        coverage.get("items", [])
        if isinstance(coverage, dict)
        else []
    ):
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        if not isinstance(item_id, str):
            continue
        allocation_results: list[dict[str, Any]] = []
        allocations = item.get("allocations", [])
        if not isinstance(allocations, list):
            allocations = []
        for allocation in allocations:
            if not isinstance(allocation, dict):
                continue
            kind = allocation.get("kind")
            target_ref = allocation.get("target_ref")
            satisfied = False
            reason = ""
            if kind in HOST_PROJECTION_KINDS:
                satisfied = (
                    isinstance(target_ref, str)
                    and (item_id, target_ref) in projected_allocations
                )
                reason = (
                    "typed-evidence-projected"
                    if satisfied
                    else (
                        "legacy-id-unverified"
                        if item_id in projected
                        else "host-projection-required"
                    )
                )
                if not satisfied:
                    projection_required.append(item_id)
            elif kind == "expertise-guide":
                resolution_count = (
                    guide_target_counts.get(
                        target_ref.removeprefix("guide:"),
                        0,
                    )
                    if isinstance(target_ref, str)
                    else 0
                )
                satisfied = (
                    isinstance(target_ref, str)
                    and (
                        _guide_selected(target_ref, expertise)
                        or (item_id, target_ref)
                        in closed_expertise_pairs
                    )
                )
                reason = (
                    "selected-guide"
                    if (
                        isinstance(target_ref, str)
                        and _guide_selected(target_ref, expertise)
                    )
                    else "expertise-work-closed"
                    if satisfied
                    else (
                        "route-capacity"
                        if resolution_count == 1
                        else "guide-reference-ambiguous"
                        if resolution_count > 1
                        else "guide-unavailable"
                    )
                )
            elif kind == "lens":
                lens_id = (
                    target_ref.removeprefix("lens:")
                    if isinstance(target_ref, str)
                    else None
                )
                satisfied = lens_id in selected_lenses
                reason = (
                    "selected-lens"
                    if satisfied
                    else "lens-not-selected"
                )
            elif kind == "research":
                satisfied = research_satisfied or item_id in compiled_item_ids
                reason = (
                    "execution-research-satisfied"
                    if research_satisfied
                    else "candidate-compiled-authoring-research"
                    if item_id in compiled_item_ids
                    else "research-not-completed"
                )
            elif kind == "unresolved":
                reason = "unresolved-allocation"
            else:
                reason = "unsupported-allocation"
            result = {
                "kind": kind,
                "target_ref": target_ref,
                "status": "satisfied" if satisfied else "gap",
                "reason": reason,
                "adaptation_eligible": (
                    not satisfied
                    and reason in ADAPTATION_ELIGIBLE_GAP_REASONS
                ),
            }
            allocation_results.append(result)
            if not satisfied:
                gaps.append(
                    {
                        "item_id": item_id,
                        "materiality": item.get("materiality"),
                        **result,
                    }
                )
        resolutions.append(
            {
                "item_id": item_id,
                "status": (
                    "satisfied"
                    if allocation_results
                    and all(
                        result["status"] == "satisfied"
                        for result in allocation_results
                    )
                    else "gap"
                ),
                "allocations": allocation_results,
            }
        )

    blocking_gaps = [
        gap
        for gap in gaps
        if gap.get("materiality") in {"blocking", "important"}
    ]
    if issues:
        status = "INVALID"
    elif blocking_gaps:
        status = (
            "PROJECTION_REQUIRED"
            if all(
                gap["reason"] == "host-projection-required"
                for gap in blocking_gaps
            )
            else "GAPS"
        )
    else:
        status = "READY"
    result = {
        "schema_version": COVERAGE_ADMISSION_VERSION,
        "admission_id": "",
        "coverage_id": (
            coverage.get("coverage_id")
            if isinstance(coverage, dict)
            else None
        ),
        "plan_id": (
            route_plan.get("plan_id")
            if isinstance(route_plan, dict)
            else None
        ),
        "goal_digest": sha256_text(goal),
        "status": status,
        "resolutions": resolutions,
        "projected_item_ids": sorted(set(projected)),
        "coverage_projection_id": coverage_projection_id,
        "expertise_work_plan_id": expertise_work_plan_id,
        "expertise_closure_id": expertise_closure_id,
        "compiled_candidate_ids": sorted(
            binding["candidate_id"] for binding in bindings
        ),
        "compiled_item_ids": sorted(compiled_item_ids),
        "gaps": gaps,
        "issues": issues,
        "execution_authority": "NONE",
        "writes_performed": False,
    }
    result["admission_id"] = _digest_payload(result)
    return result


def validate_task_coverage_admission(
    value: Any,
    *,
    repo_path: str | Path,
    goal: str,
    coverage: Any,
    plan: Any,
    coverage_projection: Any | None = None,
    expertise_work_plan: Any | None = None,
    expertise_closure: Any | None = None,
    candidate_ids: list[str] | None = None,
    research_bundle: dict[str, Any] | None = None,
    expertise_research_bundles: Any = None,
    allow_candidates: bool = False,
    require_current_revision: bool = True,
) -> dict[str, Any]:
    """Recompute a persisted no-candidate admission and compare it exactly."""

    issues: list[dict[str, str]] = []
    if not isinstance(value, dict):
        issues.append(
            _issue(
                "TASK_COVERAGE_ADMISSION_INVALID",
                "$",
                "Task Coverage admission must be an object.",
            )
        )
    elif (
        value.get("schema_version") != COVERAGE_ADMISSION_VERSION
        or not isinstance(value.get("admission_id"), str)
        or DIGEST_PATTERN.fullmatch(value["admission_id"]) is None
        or value["admission_id"] != _digest_payload(value)
        or (
            not allow_candidates
            and (
                value.get("compiled_candidate_ids") != []
                or value.get("compiled_item_ids") != []
            )
        )
    ):
        issues.append(
            _issue(
                "TASK_COVERAGE_ADMISSION_INVALID",
                "$",
                (
                    "A source admission must be digest-bound and cannot "
                    "contain already compiled task-gap candidates."
                ),
            )
        )
    if not issues:
        projected = value.get("projected_item_ids")
        if not _valid_ids(projected, maximum=MAX_PROJECTIONS):
            issues.append(
                _issue(
                    "TASK_COVERAGE_ADMISSION_INVALID",
                    "projected_item_ids",
                    "Persisted projected item IDs are invalid.",
                )
            )
        else:
            expected = build_task_coverage_admission(
                repo_path,
                goal=goal,
                coverage=coverage,
                plan=plan,
                projected_item_ids=projected,
                candidate_ids=candidate_ids,
                coverage_projection=coverage_projection,
                expertise_work_plan=expertise_work_plan,
                expertise_closure=expertise_closure,
                research_bundle=research_bundle,
                expertise_research_bundles=expertise_research_bundles,
            )
            if not require_current_revision:
                expected_issues = [
                    issue
                    for issue in expected["issues"]
                    if issue.get("code")
                    != "TASK_COVERAGE_REVISION_STALE"
                ]
                expected = {
                    **expected,
                    "issues": expected_issues,
                    "status": (
                        value.get("status")
                        if not expected_issues
                        else "INVALID"
                    ),
                }
                expected["admission_id"] = _digest_payload(expected)
            if expected != value:
                issues.append(
                    _issue(
                        "TASK_COVERAGE_ADMISSION_MISMATCH",
                        "$",
                        (
                            "Admission must exactly match deterministic "
                            "recomputation for the copied Coverage and route."
                        ),
                    )
                )
    return {
        "schema_version": "maestro_task_coverage_admission_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "admission_id": (
            value.get("admission_id")
            if isinstance(value, dict)
            else None
        ),
        "issues": issues,
        "writes_performed": False,
    }
