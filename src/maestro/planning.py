from __future__ import annotations

import copy
import re
from collections import Counter, deque
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .design_assurance import (
    build_assurance_requirement,
    product_design_assurance_active,
    validate_assurance_requirement,
)
from .expertise import select_expertise
from .expertise_routing import (
    enforce_conflict_policy,
    require_reroute_lineage,
)
from .research import require_completed_research_bundle
from .model_policy import (
    LEGACY_MODEL_ROUTE_FIELDS,
    MODEL_ROUTE_FIELDS as STAGE_MODEL_ROUTE_FIELDS,
    MODEL_ROUTE_VERSION,
    default_stage_kind,
    is_deterministic_command,
    validate_model_route_shape,
)
from .model_feedback import (
    current_model_policy_authority,
    validate_model_policy_overlay,
    validate_model_policy_overlay_authority,
)
from .registry import (
    _model_route,
    load_host_profile,
    load_registry,
    registry_digest,
    resolve_request_contract,
    route_goal,
    validate_registry,
)
from .util import canonical_json, sha256_text

ROUTE_V1 = "maestro_route_v1"
ROUTE_V2 = "maestro_route_v2"
MAX_ASSIGNMENTS = 5
MAX_LENSES = 3
MAX_REBUTTAL_ROUNDS = 1
MAX_MODEL_ESCALATIONS = 1
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")

ROUTE_V2_FIELDS = {
    "schema_version",
    "plan_id",
    "source_route_version",
    "source_route_digest",
    "registry_digest",
    "goal",
    "intent",
    "intent_source",
    "department",
    "risk",
    "warnings",
    "depth",
    "selected_lenses",
    "selected_domains",
    "lens_cards",
    "selection_reasons",
    "selection_trace",
    "binding",
    "handoff_contract",
    "model_route",
    "deliberation",
    "task_contract",
    "assignments",
    "entry_assignments",
    "terminal_assignments",
    "mutation_owner_assignment_id",
    "expertise",
    "coverage_binding",
    "design_assurance",
    "model_policy_overlays",
}
ROUTE_V2_OPTIONAL_FIELDS = {
    "expertise",
    "coverage_binding",
    "design_assurance",
    "model_policy_overlays",
}

ASSIGNMENT_FIELDS = {
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
    "model_route",
    "may_spawn",
    "max_children",
    "max_rounds",
}
ASSIGNMENT_OPTIONAL_FIELDS = {
    "expertise_pack_ids",
    "decision_guide_ids",
}
V2_EXTENSION_FIELDS = {
    "plan_id",
    "source_route_version",
    "source_route_digest",
    "registry_digest",
    "task_contract",
    "assignments",
    "entry_assignments",
    "terminal_assignments",
    "mutation_owner_assignment_id",
    "expertise",
    "coverage_binding",
    "design_assurance",
}
SOURCE_ROUTE_FIELDS = ROUTE_V2_FIELDS - V2_EXTENSION_FIELDS
MODEL_ROUTE_FIELDS = set(STAGE_MODEL_ROUTE_FIELDS)
TASK_CONTRACT_FIELDS = {
    "objective",
    "allowed_side_effects",
    "forbidden_side_effects",
    "terminal_condition",
    "stop_conditions",
    "limits",
}
LIMIT_FIELDS = {
    "max_assignments",
    "max_lenses",
    "max_rebuttal_rounds",
    "max_model_escalations_per_assignment",
}
KIND_EXECUTOR = {
    "implementation": "implementation-engineer",
    "research": "researcher",
    "review": "lens-reviewer",
    "verification": "verifier",
}


def _diagnostic(
    code: str,
    path: str,
    message: str,
    related_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "path": path,
        "related_ids": sorted(set(related_ids or [])),
        "message": message,
    }


def _plan_id(plan: dict[str, Any]) -> str:
    payload = copy.deepcopy(plan)
    payload.pop("plan_id", None)
    return sha256_text(canonical_json(payload))


def build_coverage_binding(
    coverage: Any,
    *,
    goal: str,
    repo_path: str | Path | None,
) -> dict[str, Any]:
    """Project complete Task Coverage identity without importing its body."""

    from .task_coverage import validate_task_coverage

    validation = validate_task_coverage(
        coverage,
        goal=goal,
        repo_path=repo_path,
        require_current_revision=repo_path is not None,
    )
    if (
        validation["status"] != "PASS"
        or validation["coverage_status"] != "COMPLETE"
    ):
        first = next(
            iter(validation["issues"]),
            {
                "code": "TASK_COVERAGE_INCOMPLETE",
                "message": "Task Coverage must be complete before route binding.",
            },
        )
        raise MaestroError(first["code"], first["message"])
    return {
        "schema_version": "maestro_task_coverage_binding_v1",
        "coverage_id": coverage["coverage_id"],
        "goal_digest": sha256_text(goal),
        "required_for_mutation": True,
    }


def _source_route_projection(plan: dict[str, Any]) -> dict[str, Any]:
    source = {
        key: copy.deepcopy(plan[key])
        for key in sorted(SOURCE_ROUTE_FIELDS)
        if key in plan
    }
    source["schema_version"] = ROUTE_V1
    return source


def _source_route_digest(plan: dict[str, Any]) -> str:
    return sha256_text(canonical_json(_source_route_projection(plan)))


def _reconstruct_source_route(
    plan: dict[str, Any],
    *,
    repo_path: str | Path | None,
) -> dict[str, Any] | None:
    selected = plan.get("selected_lenses")
    reasons = plan.get("selection_reasons")
    top_model_route = plan.get("model_route")
    if (
        not isinstance(plan.get("goal"), str)
        or not isinstance(plan.get("risk"), str)
        or plan["risk"] not in ("low", "medium", "high", "critical")
        or not isinstance(plan.get("intent"), str)
        or plan["intent"] not in ("implementation", "review", "research")
        or not isinstance(plan.get("intent_source"), str)
        or plan["intent_source"] not in ("explicit", "inferred")
        or not isinstance(plan.get("department"), str)
        or not isinstance(selected, list)
        or not all(isinstance(item, str) for item in selected)
        or not isinstance(reasons, dict)
        or not isinstance(top_model_route, dict)
        or not isinstance(top_model_route.get("host"), str)
    ):
        return None
    explicit_lenses = (
        selected
        if selected
        and set(reasons) == set(selected)
        and all(reasons.get(lens_id) == ["explicit"] for lens_id in selected)
        else None
    )
    route_intent = plan["intent"] if plan["intent_source"] == "explicit" else "auto"
    arguments = (
        plan["goal"],
        plan["risk"],
        explicit_lenses,
        plan["department"],
        None,
        top_model_route["host"],
        route_intent,
    )
    overlays = plan.get("model_policy_overlays")
    if overlays is not None and (
        repo_path is None
        or
        not isinstance(overlays, list)
        or any(
            not validate_model_policy_overlay_authority(
                item,
                repo_path=repo_path,
            )
            for item in overlays
        )
    ):
        return None
    authority = (
        current_model_policy_authority(repo_path)
        if overlays
        else None
    )
    try:
        return route_goal(
            *arguments,
            decision_authorized=True,
            model_policy_overlays=overlays,
            model_policy_authority=authority,
            repo_path=repo_path,
        )
    except MaestroError as exc:
        if exc.code != "CONFLICT_EVIDENCE_REQUIRED":
            return None
    try:
        return route_goal(
            *arguments[:4],
            "validator-reconstruction",
            *arguments[5:],
            decision_authorized=True,
            model_policy_overlays=overlays,
            model_policy_authority=authority,
            repo_path=repo_path,
        )
    except MaestroError:
        return None


def _model_route_shape_issues(
    value: Any,
    path: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return [
            _diagnostic(
                "ADAG_MODEL_ROUTE_INVALID",
                path,
                "model_route must be an object.",
            )
        ]
    issues: list[dict[str, Any]] = []
    value_fields = set(value)
    accepted_fields = (
        LEGACY_MODEL_ROUTE_FIELDS
        if value_fields == LEGACY_MODEL_ROUTE_FIELDS
        else MODEL_ROUTE_FIELDS
    )
    for field in sorted(accepted_fields - value_fields):
        issues.append(
            _diagnostic(
                "ADAG_REQUIRED_FIELD_MISSING",
                f"{path}.{field}",
                f"Required model_route field is missing: {field}.",
            )
        )
    for field in sorted(
        value_fields
        - (MODEL_ROUTE_FIELDS | LEGACY_MODEL_ROUTE_FIELDS)
    ):
        issues.append(
            _diagnostic(
                "ADAG_UNKNOWN_FIELD",
                f"{path}.{field}",
                f"Unsupported model_route field: {field}.",
            )
        )
    if value_fields == MODEL_ROUTE_FIELDS:
        shape_error = validate_model_route_shape(value)
        if shape_error is not None:
            issues.append(
                _diagnostic(
                    "ADAG_MODEL_ROUTE_INVALID",
                    path,
                    shape_error,
                )
            )
    if (
        value_fields != LEGACY_MODEL_ROUTE_FIELDS
        and value.get("schema_version") != MODEL_ROUTE_VERSION
    ):
        issues.append(
            _diagnostic(
                "ADAG_MODEL_ROUTE_INVALID",
                f"{path}.schema_version",
                f"model_route schema_version must be {MODEL_ROUTE_VERSION}.",
            )
        )
    id_fields = ("executor", "task_class", "host")
    nullable_strings = ("selected_class", "selected_model", "reasoning_effort")
    for field in id_fields:
        item = value.get(field)
        if not isinstance(item, str) or ID_PATTERN.fullmatch(item) is None:
            issues.append(
                _diagnostic(
                    "ADAG_MODEL_ROUTE_INVALID",
                    f"{path}.{field}",
                    f"{field} must be a lowercase kebab-case identifier.",
                )
            )
    for field in nullable_strings:
        if value.get(field) is not None and not isinstance(value.get(field), str):
            issues.append(
                _diagnostic(
                    "ADAG_MODEL_ROUTE_INVALID",
                    f"{path}.{field}",
                    f"{field} must be a string or null.",
                )
            )
    if (
        not isinstance(value.get("risk"), str)
        or value["risk"] not in ("low", "medium", "high", "critical")
    ):
        issues.append(
            _diagnostic(
                "ADAG_MODEL_ROUTE_INVALID",
                f"{path}.risk",
                "risk is unsupported.",
            )
        )
    for field in ("selection_reason", "fallback"):
        if not isinstance(value.get(field), str) or not value.get(field):
            issues.append(
                _diagnostic(
                    "ADAG_MODEL_ROUTE_INVALID",
                    f"{path}.{field}",
                    f"{field} must be a non-empty string.",
                )
            )
    if not isinstance(value.get("escalation_allowed"), bool):
        issues.append(
            _diagnostic(
                "ADAG_MODEL_ROUTE_INVALID",
                f"{path}.escalation_allowed",
                "escalation_allowed must be a boolean.",
            )
        )
    return issues


def _legacy_model_route(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == LEGACY_MODEL_ROUTE_FIELDS


def _canonical_flow_issues(
    plan: dict[str, Any],
    assignments: dict[str, dict[str, Any]],
    dependencies: dict[str, list[str]],
) -> list[dict[str, Any]]:
    task_class = (
        plan.get("model_route", {}).get("task_class")
        if isinstance(plan.get("model_route"), dict)
        else None
    )
    intent = plan.get("intent")
    kinds = {
        assignment_id: assignment.get("kind")
        for assignment_id, assignment in assignments.items()
    }
    expected_dependencies: dict[str, list[str]] = {}
    valid = True
    if task_class == "deterministic-verification":
        valid = kinds == {"verification": "verification"}
        expected_dependencies = {"verification": []}
    elif intent == "implementation":
        review_ids = sorted(
            assignment_id
            for assignment_id, kind in kinds.items()
            if kind == "review"
        )
        expected_kinds = {
            **{assignment_id: "review" for assignment_id in review_ids},
            "implementation": "implementation",
            "verification": "verification",
        }
        valid = kinds == expected_kinds
        expected_dependencies = {
            **{assignment_id: [] for assignment_id in review_ids},
            "implementation": review_ids,
            "verification": ["implementation"],
        }
    elif intent == "review":
        valid = bool(kinds) and all(
            kind == "review" for kind in kinds.values()
        )
        expected_dependencies = {
            assignment_id: [] for assignment_id in kinds
        }
    elif intent == "research":
        valid = kinds == {"research": "research"}
        expected_dependencies = {"research": []}
    else:
        valid = False

    review_assignments = [
        item for item in assignments.values() if item.get("kind") == "review"
    ]
    if len(review_assignments) == 1:
        valid = valid and review_assignments[0].get("assignment_id") == "review"
    elif review_assignments:
        valid = valid and all(
            item.get("lens_ids")
            and len(item["lens_ids"]) == 1
            and item.get("assignment_id") == f"review-{item['lens_ids'][0]}"
            for item in review_assignments
        )
    if any(
        sorted(dependencies.get(assignment_id, [])) != sorted(expected)
        for assignment_id, expected in expected_dependencies.items()
    ):
        valid = False
    selected_lenses = (
        plan.get("selected_lenses")
        if isinstance(plan.get("selected_lenses"), list)
        and all(isinstance(item, str) for item in plan["selected_lenses"])
        else []
    )
    binding = plan.get("binding") if isinstance(plan.get("binding"), dict) else {}
    expected_lens_owners = {
        assignment_id: [] for assignment_id in assignments
    }
    if task_class != "deterministic-verification":
        if intent == "research" and "research" in expected_lens_owners:
            expected_lens_owners["research"] = selected_lenses
        elif intent in ("implementation", "review"):
            if (
                binding.get("executor") == "lens-reviewer"
                and binding.get("fresh_context_per_lens") is True
                and len(selected_lenses) > 1
            ):
                for lens_id in selected_lenses:
                    expected_lens_owners[f"review-{lens_id}"] = [lens_id]
            elif binding.get("executor") == "lens-reviewer" and selected_lenses:
                expected_lens_owners["review"] = selected_lenses
            elif intent == "implementation" and "implementation" in expected_lens_owners:
                expected_lens_owners["implementation"] = selected_lenses
    if set(expected_lens_owners) != set(assignments) or any(
        assignments[assignment_id].get("lens_ids") != lens_ids
        for assignment_id, lens_ids in expected_lens_owners.items()
        if assignment_id in assignments
    ):
        valid = False
    if valid:
        return []
    return [
        _diagnostic(
            "ADAG_CANONICAL_FLOW_MISMATCH",
            "assignments",
            "Assignments must follow the bounded canonical flow for the routed intent.",
            sorted(assignments),
        )
    ]


def _executor_map() -> dict[str, dict[str, Any]]:
    registry = load_registry()
    errors = validate_registry(registry)
    if errors:
        raise MaestroError("REGISTRY_INVALID", "; ".join(errors))
    return {
        item["executor_id"]: item
        for item in registry["executors"]
    }


def _assignment_model_route(
    route: dict[str, Any],
    executor: dict[str, Any],
    lens_ids: list[str],
    *,
    assignment_id: str,
    kind: str,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    host_id = route["model_route"]["host"]
    if not isinstance(kind, str):
        raise MaestroError(
            "MODEL_STAGE_UNKNOWN",
            "Assignment kind must be a string with an explicit model stage policy.",
        )
    stage_kind = {
        "implementation": "implementation",
        "review": "semantic-review",
        "research": "research",
        "verification": (
            "deterministic-verification"
            if route["model_route"]["task_class"]
            == "deterministic-verification"
            else "semantic-verification"
        ),
    }.get(kind)
    if stage_kind is None:
        raise MaestroError(
            "MODEL_STAGE_UNKNOWN",
            f"Assignment kind {kind!r} has no model stage policy.",
        )
    overlays = route.get("model_policy_overlays")
    authority = (
        overlays[0].get("authority")
        if isinstance(overlays, list)
        and overlays
        and all(
            isinstance(item, dict)
            and item.get("authority") == overlays[0].get("authority")
            for item in overlays
        )
        else None
    )
    return _model_route(
        route["goal"],
        route["risk"],
        lens_ids,
        executor,
        host_id,
        execution_unit_id=assignment_id,
        stage_kind=stage_kind,
        model_policy_overlays=overlays,
        model_policy_authority=authority,
        repo_path=repo_path,
    )


def _assignment(
    route: dict[str, Any],
    executors: dict[str, dict[str, Any]],
    *,
    assignment_id: str,
    kind: str,
    executor_id: str,
    lens_ids: list[str],
    depends_on: list[str],
    read_only: bool,
    mutation_owner: bool,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    executor = executors[executor_id]
    model_route = _assignment_model_route(
        route,
        executor,
        lens_ids,
        assignment_id=assignment_id,
        kind=kind,
        repo_path=repo_path,
    )
    assignment = {
        "assignment_id": assignment_id,
        "kind": kind,
        "executor_id": executor_id,
        "lens_ids": lens_ids,
        "depends_on": depends_on,
        "input_packets": list(executor["accepts"]),
        "output_packet": (
            "TerminalPacket"
            if (
                kind == "verification"
                and model_route["execution_kind"] == "deterministic"
            )
            else executor["returns"][0]
        ),
        "read_only": read_only,
        "mutation_owner": mutation_owner,
        "allowed_side_effects": [] if read_only else ["repository_write"],
        "model_route": model_route,
        "may_spawn": False,
        "max_children": 0,
        "max_rounds": 1,
    }
    expertise = route.get("expertise")
    if kind != "verification" and isinstance(expertise, dict):
        assignment["expertise_pack_ids"] = list(
            expertise.get("selected_pack_ids", [])
        )
        assignment["decision_guide_ids"] = list(
            expertise.get("selected_guide_ids", [])
        )
    return assignment


def _review_assignments(
    route: dict[str, Any],
    executors: dict[str, dict[str, Any]],
    *,
    repo_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    lens_ids = list(route["selected_lenses"])
    if route["binding"]["fresh_context_per_lens"] and len(lens_ids) > 1:
        return [
            _assignment(
                route,
                executors,
                assignment_id=f"review-{lens_id}",
                kind="review",
                executor_id="lens-reviewer",
                lens_ids=[lens_id],
                depends_on=[],
                read_only=True,
                mutation_owner=False,
                repo_path=repo_path,
            )
            for lens_id in lens_ids
        ]
    return [
        _assignment(
            route,
            executors,
            assignment_id="review",
            kind="review",
            executor_id="lens-reviewer",
            lens_ids=lens_ids,
            depends_on=[],
            read_only=True,
            mutation_owner=False,
            repo_path=repo_path,
        )
    ]


def compile_route_v2(
    route_v1: dict[str, Any],
    *,
    route_hints: dict[str, Any] | None = None,
    prior_route_plan: dict[str, Any] | None = None,
    research_evidence: dict[str, Any] | None = None,
    repo_path: str | Path | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a v1 route into a bounded, host-executed Assignment DAG."""

    if route_v1.get("schema_version") != ROUTE_V1:
        raise MaestroError(
            "ROUTE_VERSION_UNSUPPORTED",
            f"Expected {ROUTE_V1} as the normalization input.",
        )

    expertise, _ = select_expertise(
        route_v1["goal"],
        intent=route_v1["intent"],
        route_hints=route_hints,
        repo_path=repo_path,
    )
    enforce_conflict_policy(expertise, risk=route_v1["risk"])
    if research_evidence is not None:
        validation = require_completed_research_bundle(
            research_evidence,
            goal=route_v1["goal"],
            expertise=expertise,
            repo_path=repo_path,
        )
        expertise, _ = select_expertise(
            route_v1["goal"],
            intent=route_v1["intent"],
            route_hints=route_hints,
            research_evidence_digest=validation["artifact_digest"],
            repo_path=repo_path,
        )
        enforce_conflict_policy(expertise, risk=route_v1["risk"])
    route_context = copy.deepcopy(route_v1)
    if (
        route_hints is not None
        or expertise["selected_pack_ids"]
        or expertise["research_requirement"]["mode"] != "reuse"
    ):
        route_context["expertise"] = expertise

    executors = _executor_map()
    assignments: list[dict[str, Any]] = []
    intent = route_context["intent"]
    bound_executor = route_context["binding"]["executor"]
    deterministic_only = (
        route_context["model_route"]["task_class"] == "deterministic-verification"
    )

    if deterministic_only:
        assignments.append(
            _assignment(
                route_context,
                executors,
                assignment_id="verification",
                kind="verification",
                executor_id="verifier",
                lens_ids=[],
                depends_on=[],
                read_only=True,
                mutation_owner=False,
                repo_path=repo_path,
            )
        )
    elif intent == "implementation":
        review_ids: list[str] = []
        if bound_executor == "lens-reviewer":
            reviews = _review_assignments(
                route_context,
                executors,
                repo_path=repo_path,
            )
            assignments.extend(reviews)
            review_ids = [item["assignment_id"] for item in reviews]

        writer_lenses = (
            list(route_context["selected_lenses"])
            if bound_executor == "implementation-engineer"
            else []
        )
        assignments.append(
            _assignment(
                route_context,
                executors,
                assignment_id="implementation",
                kind="implementation",
                executor_id="implementation-engineer",
                lens_ids=writer_lenses,
                depends_on=review_ids,
                read_only=False,
                mutation_owner=True,
                repo_path=repo_path,
            )
        )
        assignments.append(
            _assignment(
                route_context,
                executors,
                assignment_id="verification",
                kind="verification",
                executor_id="verifier",
                lens_ids=[],
                depends_on=["implementation"],
                read_only=True,
                mutation_owner=False,
                repo_path=repo_path,
            )
        )
    elif intent == "research":
        assignments.append(
            _assignment(
                route_context,
                executors,
                assignment_id="research",
                kind="research",
                executor_id="researcher",
                lens_ids=list(route_context["selected_lenses"]),
                depends_on=[],
                read_only=True,
                mutation_owner=False,
                repo_path=repo_path,
            )
        )
    elif bound_executor == "lens-reviewer":
        assignments.extend(
            _review_assignments(
                route_context,
                executors,
                repo_path=repo_path,
            )
        )
    else:
        assignments.append(
            _assignment(
                route_context,
                executors,
                assignment_id="research",
                kind="research",
                executor_id="researcher",
                lens_ids=[],
                depends_on=[],
                read_only=True,
                mutation_owner=False,
                repo_path=repo_path,
            )
        )

    dependency_targets = {
        dependency
        for item in assignments
        for dependency in item["depends_on"]
    }
    entry_assignments = [
        item["assignment_id"]
        for item in assignments
        if not item["depends_on"]
    ]
    terminal_assignments = [
        item["assignment_id"]
        for item in assignments
        if item["assignment_id"] not in dependency_targets
    ]
    mutation_owner = next(
        (
            item["assignment_id"]
            for item in assignments
            if item["mutation_owner"]
        ),
        None,
    )

    plan = copy.deepcopy(route_context)
    plan["schema_version"] = ROUTE_V2
    plan["source_route_version"] = ROUTE_V1
    plan["source_route_digest"] = _source_route_digest(plan)
    plan["registry_digest"] = registry_digest()
    plan["task_contract"] = {
        "objective": route_v1["goal"],
        "allowed_side_effects": (
            ["repository_write"]
            if mutation_owner is not None
            else []
        ),
        "forbidden_side_effects": resolve_request_contract(
            route_v1["goal"],
            route_v1["intent"],
        )["forbidden_side_effects"],
        "terminal_condition": "all_terminal_assignments_complete",
        "stop_conditions": [
            "required_gate_failed",
            "user_decision_required",
            "budget_exhausted",
        ],
        "limits": {
            "max_assignments": MAX_ASSIGNMENTS,
            "max_lenses": {
                "fast": 1,
                "standard": 2,
                "deep": 3,
            }[route_v1["depth"]],
            "max_rebuttal_rounds": route_v1["deliberation"][
                "max_rebuttal_rounds"
            ],
            "max_model_escalations_per_assignment": MAX_MODEL_ESCALATIONS,
        },
    }
    plan["assignments"] = assignments
    plan["entry_assignments"] = entry_assignments
    plan["terminal_assignments"] = terminal_assignments
    plan["mutation_owner_assignment_id"] = mutation_owner
    if product_design_assurance_active(route_context):
        plan["design_assurance"] = build_assurance_requirement(
            route_context["expertise"]["route_hints"][
                "design_assurance_mode"
            ]
        )
    if coverage is not None:
        plan["coverage_binding"] = build_coverage_binding(
            coverage,
            goal=route_v1["goal"],
            repo_path=repo_path,
        )
    plan["plan_id"] = _plan_id(plan)

    require_reroute_lineage(
        route_hints,
        prior_plan=prior_route_plan,
        current_plan=plan,
    )
    require_valid_route_v2(plan, repo_path=repo_path)
    return plan


def route_goal_v2(
    goal: str,
    risk: str,
    explicit_lenses: list[str] | None = None,
    department_id: str = "software-development",
    conflict_evidence: str | None = None,
    host_id: str = "codex",
    intent: str = "auto",
    research_evidence: dict[str, Any] | None = None,
    decision_authorized: bool = False,
    repo_path: str | Path | None = None,
    route_hints: dict[str, Any] | None = None,
    prior_route_plan: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
    model_policy_overlays: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    authority = None
    if model_policy_overlays:
        if repo_path is None or any(
            not validate_model_policy_overlay_authority(
                overlay,
                repo_path=repo_path,
            )
            for overlay in model_policy_overlays
        ):
            raise MaestroError(
                "MODEL_POLICY_OVERLAY_AUTHORITY_INVALID",
                "Route overlays must match the exact current project, checkout, Registry, and policy.",
            )
        authority = current_model_policy_authority(repo_path)
    route = route_goal(
        goal,
        risk,
        explicit_lenses,
        department_id,
        conflict_evidence,
        host_id,
        intent,
        decision_authorized,
        model_policy_overlays,
        authority,
        repo_path,
    )
    return compile_route_v2(
        route,
        route_hints=route_hints,
        prior_route_plan=prior_route_plan,
        research_evidence=research_evidence,
        repo_path=repo_path,
        coverage=coverage,
    )


def validate_route_v2(
    plan: Any,
    *,
    repo_path: str | Path | None = None,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic structural and cross-contract diagnostics."""

    if not isinstance(plan, dict):
        return {
            "schema_version": "maestro_route_validation_v1",
            "status": "FAIL",
            "execution_status": "INVALID",
            "plan_id": None,
            "source_route_version": None,
            "issues": [
                _diagnostic(
                    "ADAG_PLAN_INVALID",
                    "$",
                    "Route v2 plan must be a JSON object.",
                )
            ],
            "writes_performed": False,
        }
    diagnostics: list[dict[str, Any]] = []
    if plan.get("schema_version") != ROUTE_V2:
        diagnostics.append(
            _diagnostic(
                "ADAG_UNSUPPORTED_SCHEMA_VERSION",
                "schema_version",
                f"Expected {ROUTE_V2}.",
            )
        )

    if plan.get("source_route_version") != ROUTE_V1:
        diagnostics.append(
            _diagnostic(
                "ADAG_SOURCE_ROUTE_VERSION_INVALID",
                "source_route_version",
                f"Route v2 must normalize {ROUTE_V1}.",
            )
        )
    if (
        not isinstance(plan.get("source_route_digest"), str)
        or DIGEST_PATTERN.fullmatch(plan["source_route_digest"]) is None
    ):
        diagnostics.append(
            _diagnostic(
                "ADAG_SOURCE_ROUTE_DIGEST_INVALID",
                "source_route_digest",
                "source_route_digest must be a canonical SHA-256 digest.",
            )
        )
    elif plan["source_route_digest"] != _source_route_digest(plan):
        diagnostics.append(
            _diagnostic(
                "ADAG_SOURCE_ROUTE_DIGEST_MISMATCH",
                "source_route_digest",
                "source_route_digest must bind the preserved route v1 projection.",
            )
        )
    if not isinstance(plan.get("goal"), str) or not plan["goal"].strip():
        diagnostics.append(
            _diagnostic(
                "ADAG_GOAL_INVALID",
                "goal",
                "goal must be a non-empty string.",
            )
        )
    coverage_binding = plan.get("coverage_binding")
    if coverage_binding is not None:
        if (
            not isinstance(coverage_binding, dict)
            or set(coverage_binding)
            != {
                "schema_version",
                "coverage_id",
                "goal_digest",
                "required_for_mutation",
            }
            or coverage_binding.get("schema_version")
            != "maestro_task_coverage_binding_v1"
            or not isinstance(coverage_binding.get("coverage_id"), str)
            or DIGEST_PATTERN.fullmatch(
                coverage_binding["coverage_id"]
            )
            is None
            or coverage_binding.get("goal_digest")
            != sha256_text(plan.get("goal", ""))
            or coverage_binding.get("required_for_mutation") is not True
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_COVERAGE_BINDING_INVALID",
                    "coverage_binding",
                    "Coverage binding must carry the complete Coverage and goal digests.",
                )
            )

    diagnostics.extend(
        _diagnostic(
            item["code"],
            item["path"],
            item["message"],
        )
        for item in validate_assurance_requirement(
            plan.get("design_assurance"),
            plan=plan,
        )
    )

    scalar_checks = {
        "intent": {"implementation", "review", "research"},
        "intent_source": {"explicit", "inferred"},
        "risk": {"low", "medium", "high", "critical"},
        "depth": {"fast", "standard", "deep"},
    }
    for field, allowed in scalar_checks.items():
        if not isinstance(plan.get(field), str) or plan[field] not in allowed:
            diagnostics.append(
                _diagnostic(
                    "ADAG_ROUTE_FIELD_INVALID",
                    field,
                    f"{field} is unsupported.",
                )
            )
    department = plan.get("department")
    if not isinstance(department, str) or ID_PATTERN.fullmatch(department) is None:
        diagnostics.append(
            _diagnostic(
                "ADAG_ROUTE_FIELD_INVALID",
                "department",
                "department must be a lowercase kebab-case identifier.",
            )
        )
    warnings = plan.get("warnings")
    if not isinstance(warnings, list) or not all(
        isinstance(item, dict) for item in warnings
    ):
        diagnostics.append(
            _diagnostic(
                "ADAG_ROUTE_FIELD_INVALID",
                "warnings",
                "warnings must be a list of objects.",
            )
        )
    for field in (
        "selection_reasons",
        "selection_trace",
        "binding",
        "deliberation",
    ):
        if not isinstance(plan.get(field), dict):
            diagnostics.append(
                _diagnostic(
                    "ADAG_ROUTE_FIELD_INVALID",
                    field,
                    f"{field} must be an object.",
                )
            )
    if plan.get("handoff_contract") is not None and not isinstance(
        plan.get("handoff_contract"),
        dict,
    ):
        diagnostics.append(
            _diagnostic(
                "ADAG_ROUTE_FIELD_INVALID",
                "handoff_contract",
                "handoff_contract must be an object or null.",
            )
        )

    missing_fields = sorted(
        ROUTE_V2_FIELDS - ROUTE_V2_OPTIONAL_FIELDS - set(plan)
    )
    unknown_fields = sorted(set(plan) - ROUTE_V2_FIELDS)
    for field in missing_fields:
        diagnostics.append(
            _diagnostic(
                "ADAG_REQUIRED_FIELD_MISSING",
                field,
                f"Required route v2 field is missing: {field}.",
            )
        )
    for field in unknown_fields:
        diagnostics.append(
            _diagnostic(
                "ADAG_UNKNOWN_FIELD",
                field,
                f"Unsupported route v2 field: {field}.",
            )
        )

    if not isinstance(plan.get("plan_id"), str) or plan.get("plan_id") != _plan_id(plan):
        diagnostics.append(
            _diagnostic(
                "ADAG_PLAN_ID_MISMATCH",
                "plan_id",
                "plan_id must match the canonical digest of the complete plan.",
            )
        )

    assignments = plan.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        diagnostics.append(
            _diagnostic(
                "ADAG_ASSIGNMENTS_INVALID",
                "assignments",
                "assignments must be a non-empty list.",
            )
        )
        assignments = []
    if len(assignments) > MAX_ASSIGNMENTS:
        diagnostics.append(
            _diagnostic(
                "ADAG_BOUND_EXCEEDED",
                "assignments",
                f"At most {MAX_ASSIGNMENTS} assignments are allowed.",
            )
        )

    registry = load_registry()
    registry_errors = validate_registry(registry)
    if registry_errors:
        diagnostics.append(
            _diagnostic(
                "ADAG_REGISTRY_INVALID",
                "registry_digest",
                "The active Registry is invalid.",
            )
        )
    expertise = plan.get("expertise")
    expertise_gate: str | None = "not-required"
    research_evidence_ready = False
    if "expertise" in plan and not isinstance(expertise, dict):
        diagnostics.append(
            _diagnostic(
                "ADAG_EXPERTISE_INVALID",
                "expertise",
                "expertise must be a Registry-backed selection object.",
            )
        )
    elif isinstance(expertise, dict):
        requirement = expertise.get("research_requirement")
        evidence_digest = (
            requirement.get("evidence_digest")
            if isinstance(requirement, dict)
            else None
        )
        expertise_gate = (
            requirement.get("gate")
            if isinstance(requirement, dict)
            and isinstance(requirement.get("gate"), str)
            else None
        )
        try:
            route_hints = expertise.get("route_hints")
            expected_expertise, _ = select_expertise(
                plan.get("goal", ""),
                intent=plan.get("intent", ""),
                route_hints=route_hints,
                research_evidence_digest=evidence_digest,
                repo_path=repo_path,
            )
            enforce_conflict_policy(
                expected_expertise,
                risk=plan.get("risk", ""),
            )
        except MaestroError:
            expected_expertise = None
        if expected_expertise is None or expertise != expected_expertise:
            diagnostics.append(
                _diagnostic(
                    "ADAG_EXPERTISE_SELECTION_MISMATCH",
                    "expertise",
                    (
                        "Expertise Pack, Decision Guide, and research gate "
                        "selection must match the active Registry."
                    ),
                )
            )
        if expertise_gate == "satisfied":
            if research_bundle is not None:
                try:
                    research_validation = require_completed_research_bundle(
                        research_bundle,
                        goal=plan.get("goal", ""),
                        expertise=expertise,
                        repo_path=repo_path,
                    )
                except (MaestroError, OSError, TypeError, ValueError) as exc:
                    diagnostics.append(
                        _diagnostic(
                            "ADAG_RESEARCH_EVIDENCE_INVALID",
                            "expertise.research_requirement",
                            str(exc),
                        )
                    )
                else:
                    if evidence_digest != research_validation["artifact_digest"]:
                        diagnostics.append(
                            _diagnostic(
                                "ADAG_RESEARCH_EVIDENCE_DIGEST_MISMATCH",
                                "expertise.research_requirement.evidence_digest",
                                (
                                    "The satisfied research gate must bind the "
                                    "exact validated ResearchBundle digest."
                                ),
                            )
                        )
                    else:
                        research_evidence_ready = True
        elif research_bundle is not None:
            diagnostics.append(
                _diagnostic(
                    "ADAG_RESEARCH_EVIDENCE_UNEXPECTED",
                    "research_bundle",
                    (
                        "ResearchBundle input is accepted only for a plan "
                        "whose research gate is already satisfied."
                    ),
                )
            )
    elif research_bundle is not None:
        diagnostics.append(
            _diagnostic(
                "ADAG_RESEARCH_EVIDENCE_UNEXPECTED",
                "research_bundle",
                "ResearchBundle input requires a selected Expertise research gate.",
            )
        )
    expected_source = _reconstruct_source_route(
        plan,
        repo_path=repo_path,
    )
    preserved_source = _source_route_projection(plan)
    if expected_source is None:
        diagnostics.append(
            _diagnostic(
                "ADAG_SOURCE_ROUTE_CONTRACT_MISMATCH",
                "$",
                "The preserved route v1 contract cannot be reconstructed from the active Registry.",
            )
        )
    else:
        legacy_source_route = _legacy_model_route(
            preserved_source.get("model_route")
        )
        for field in sorted(set(expected_source) | set(preserved_source)):
            if field == "model_route" and legacy_source_route:
                continue
            if expected_source.get(field) != preserved_source.get(field):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_SOURCE_ROUTE_CONTRACT_MISMATCH",
                        field,
                        f"Preserved route v1 field does not match the active Registry: {field}.",
                    )
                )
    executors = {
        item["executor_id"]: item
        for item in registry["executors"]
    }
    binding = plan.get("binding")
    binding_executor_id = (
        binding.get("executor")
        if isinstance(binding, dict)
        else None
    )
    if (
        not isinstance(binding_executor_id, str)
        or binding_executor_id not in executors
    ):
        diagnostics.append(
            _diagnostic(
                "ADAG_EXECUTOR_UNKNOWN",
                "binding.executor",
                f"Unknown bound Executor: {binding_executor_id}.",
                [str(binding_executor_id)],
            )
        )
    lens_ids = {
        item["lens_id"]
        for item in registry["lenses"]
    }
    top_model_route = plan.get("model_route")
    diagnostics.extend(_model_route_shape_issues(top_model_route, "model_route"))
    plan_host = (
        top_model_route.get("host")
        if isinstance(top_model_route, dict)
        else None
    )
    if not isinstance(top_model_route, dict) or not isinstance(plan_host, str):
        diagnostics.append(
            _diagnostic(
                "ADAG_MODEL_ROUTE_MISMATCH",
                "model_route",
                "The plan must preserve a v1 model route with a Host.",
            )
        )
    elif (
        isinstance(plan.get("binding"), dict)
        and isinstance(plan["binding"].get("executor"), str)
        and isinstance(plan.get("goal"), str)
        and isinstance(plan.get("risk"), str)
        and plan["risk"] in ("low", "medium", "high", "critical")
    ):
        top_executor = executors.get(plan["binding"]["executor"])
        if top_executor is not None:
            try:
                expected_top_route = _model_route(
                    plan["goal"],
                    plan["risk"],
                    (
                        plan.get("selected_lenses")
                        if isinstance(plan.get("selected_lenses"), list)
                        and all(
                            isinstance(item, str)
                            for item in plan["selected_lenses"]
                        )
                        else []
                    ),
                    top_executor,
                    plan_host,
                    execution_unit_id="route",
                    stage_kind=(
                        "deterministic-verification"
                        if is_deterministic_command(plan["goal"])
                        else default_stage_kind(
                            executor_id=top_executor["executor_id"],
                            goal=plan["goal"],
                        )
                    ),
                    model_policy_overlays=plan.get(
                        "model_policy_overlays",
                    ),
                    model_policy_authority=(
                        plan["model_policy_overlays"][0].get(
                            "authority"
                        )
                        if isinstance(
                            plan.get("model_policy_overlays"),
                            list,
                        )
                        and plan["model_policy_overlays"]
                        else None
                    ),
                    repo_path=repo_path,
                )
            except MaestroError:
                expected_top_route = None
            if (
                expected_top_route is None
                or (
                    not _legacy_model_route(top_model_route)
                    and top_model_route != expected_top_route
                )
            ):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_MODEL_ROUTE_MISMATCH",
                        "model_route",
                        "The preserved v1 model route does not match the active Registry.",
                        [top_executor["executor_id"]],
                    )
                )

    assignment_by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    selected_domains = plan.get("selected_domains")
    if (
        not isinstance(selected_domains, list)
        or not all(
            isinstance(item, str) and ID_PATTERN.fullmatch(item)
            for item in selected_domains
        )
        or len(selected_domains) != len(set(selected_domains))
    ):
        diagnostics.append(
            _diagnostic(
                "ADAG_ROUTE_FIELD_INVALID",
                "selected_domains",
                "selected_domains must be a unique list of identifiers.",
            )
        )
    selected_lenses = plan.get("selected_lenses")
    selected_lenses_valid = (
        isinstance(selected_lenses, list)
        and all(isinstance(item, str) for item in selected_lenses)
        and len(selected_lenses) == len(set(selected_lenses))
    )
    if not selected_lenses_valid:
        diagnostics.append(
            _diagnostic(
                "ADAG_LENSES_INVALID",
                "selected_lenses",
                "selected_lenses must be a unique list of Lens IDs.",
            )
        )
    selected_lens_set = set(selected_lenses) if selected_lenses_valid else set()
    unknown_selected_lenses = sorted(selected_lens_set - lens_ids)
    if unknown_selected_lenses:
        diagnostics.append(
            _diagnostic(
                "ADAG_LENS_UNKNOWN",
                "selected_lenses",
                f"Unknown selected Lens IDs: {', '.join(unknown_selected_lenses)}.",
                unknown_selected_lenses,
            )
        )

    lens_cards = plan.get("lens_cards")
    card_lens_ids = (
        [
            item.get("lens_id")
            for item in lens_cards
            if isinstance(item, dict)
            and isinstance(item.get("lens_id"), str)
        ]
        if isinstance(lens_cards, list)
        else []
    )
    if (
        not isinstance(lens_cards, list)
        or len(card_lens_ids) != len(lens_cards)
        or len(card_lens_ids) != len(set(card_lens_ids))
        or set(card_lens_ids) != selected_lens_set
    ):
        diagnostics.append(
            _diagnostic(
                "ADAG_LENS_CARD_MISMATCH",
                "lens_cards",
                "lens_cards must cover every and only selected Lens exactly once.",
                card_lens_ids,
            )
        )

    covered_lenses: list[str] = []

    for index, assignment in enumerate(assignments):
        path = f"assignments[{index}]"
        if not isinstance(assignment, dict):
            diagnostics.append(
                _diagnostic(
                    "ADAG_ASSIGNMENT_INVALID",
                    path,
                    "Each assignment must be an object.",
                )
            )
            continue
        for field in sorted(ASSIGNMENT_FIELDS - set(assignment)):
            diagnostics.append(
                _diagnostic(
                    "ADAG_REQUIRED_FIELD_MISSING",
                    f"{path}.{field}",
                    f"Required assignment field is missing: {field}.",
                )
            )
        for field in sorted(
            set(assignment) - ASSIGNMENT_FIELDS - ASSIGNMENT_OPTIONAL_FIELDS
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_UNKNOWN_FIELD",
                    f"{path}.{field}",
                    f"Unsupported assignment field: {field}.",
                )
            )

        selected_pack_ids = expertise.get("selected_pack_ids", []) if isinstance(
            expertise, dict
        ) else []
        selected_guide_ids = expertise.get("selected_guide_ids", []) if isinstance(
            expertise, dict
        ) else []
        assignment_pack_ids = assignment.get("expertise_pack_ids")
        assignment_guide_ids = assignment.get("decision_guide_ids")
        if not isinstance(expertise, dict):
            if (
                assignment_pack_ids is not None
                or assignment_guide_ids is not None
            ):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_EXPERTISE_BINDING_MISMATCH",
                        path,
                        "Assignment expertise IDs require a top-level expertise selection.",
                    )
                )
        elif assignment.get("kind") == "verification":
            if (
                assignment_pack_ids is not None
                or assignment_guide_ids is not None
            ):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_EXPERTISE_BINDING_MISMATCH",
                        path,
                        "Verification must not load Expertise Pack guidance.",
                    )
                )
        elif (
            assignment_pack_ids != selected_pack_ids
            or assignment_guide_ids != selected_guide_ids
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_EXPERTISE_BINDING_MISMATCH",
                    path,
                    (
                        "Non-verification assignments must bind the selected "
                        "Expertise Pack and Decision Guide IDs."
                    ),
                )
            )

        assignment_id = assignment.get("assignment_id")
        if not isinstance(assignment_id, str) or ID_PATTERN.fullmatch(assignment_id) is None:
            diagnostics.append(
                _diagnostic(
                    "ADAG_ASSIGNMENT_ID_INVALID",
                    f"{path}.assignment_id",
                    "assignment_id must be a lowercase kebab-case identifier.",
                )
            )
            continue
        if assignment_id in assignment_by_id:
            duplicate_ids.add(assignment_id)
        assignment_by_id[assignment_id] = assignment

        executor_id = assignment.get("executor_id")
        executor = executors.get(executor_id) if isinstance(executor_id, str) else None
        if executor is None:
            diagnostics.append(
                _diagnostic(
                    "ADAG_EXECUTOR_UNKNOWN",
                    f"{path}.executor_id",
                    f"Unknown Executor: {executor_id}.",
                    [str(executor_id)],
                )
            )

        assignment_lenses = assignment.get("lens_ids")
        if (
            not isinstance(assignment_lenses, list)
            or not all(isinstance(item, str) for item in assignment_lenses)
            or len(assignment_lenses) != len(set(assignment_lenses))
            or len(assignment_lenses) > MAX_LENSES
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_LENSES_INVALID",
                    f"{path}.lens_ids",
                    "lens_ids must be a list of Lens IDs.",
                )
            )
            assignment_lenses = []
        unknown_lenses = sorted(set(assignment_lenses) - lens_ids)
        if unknown_lenses:
            diagnostics.append(
                _diagnostic(
                    "ADAG_LENS_UNKNOWN",
                    f"{path}.lens_ids",
                    f"Unknown Lens IDs: {', '.join(unknown_lenses)}.",
                    unknown_lenses,
                )
            )
        covered_lenses.extend(assignment_lenses)

        kind = assignment.get("kind")
        if not isinstance(kind, str) or kind not in KIND_EXECUTOR:
            diagnostics.append(
                _diagnostic(
                    "ADAG_ASSIGNMENT_KIND_INVALID",
                    f"{path}.kind",
                    "Assignment kind is unsupported.",
                )
            )
        elif executor_id != KIND_EXECUTOR[kind]:
            diagnostics.append(
                _diagnostic(
                    "ADAG_KIND_EXECUTOR_MISMATCH",
                    path,
                    f"Assignment kind {kind} requires Executor {KIND_EXECUTOR[kind]}.",
                    [assignment_id, str(executor_id)],
                )
            )

        input_packets = assignment.get("input_packets")
        output_packet = assignment.get("output_packet")
        input_packets_valid = (
            isinstance(input_packets, list)
            and bool(input_packets)
            and all(
                isinstance(packet, str) and bool(packet)
                for packet in input_packets
            )
            and len(input_packets) == len(set(input_packets))
        )
        if not input_packets_valid:
            diagnostics.append(
                _diagnostic(
                    "ADAG_PACKET_CONTRACT_INVALID",
                    f"{path}.input_packets",
                    "input_packets must be a unique non-empty list of Packet IDs.",
                )
            )
        if not isinstance(output_packet, str) or not output_packet:
            diagnostics.append(
                _diagnostic(
                    "ADAG_PACKET_CONTRACT_INVALID",
                    f"{path}.output_packet",
                    "output_packet must be a non-empty Packet ID.",
                )
            )
        if executor is not None:
            if (
                not input_packets_valid
                or set(input_packets) != set(executor["accepts"])
            ):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_EXECUTOR_CONTRACT_MISMATCH",
                        f"{path}.input_packets",
                        f"Input packets do not match Executor {executor_id}.",
                        [executor_id],
                    )
                )
            if output_packet not in executor["returns"]:
                diagnostics.append(
                    _diagnostic(
                        "ADAG_EXECUTOR_CONTRACT_MISMATCH",
                        f"{path}.output_packet",
                        f"Output packet is not returned by Executor {executor_id}.",
                        [executor_id],
                    )
                )

            mutating_capabilities = [
                capability
                for capability in executor["capabilities"]
                if capability.startswith("mutate.")
            ]
            if assignment.get("read_only") is True and mutating_capabilities:
                diagnostics.append(
                    _diagnostic(
                        "ADAG_READ_ONLY_EXECUTOR_CONFLICT",
                        f"{path}.executor_id",
                        f"Read-only assignment uses mutating Executor {executor_id}.",
                        [executor_id],
                    )
                )

        model_route = assignment.get("model_route")
        diagnostics.extend(
            _model_route_shape_issues(model_route, f"{path}.model_route")
        )
        if (
            not isinstance(model_route, dict)
            or model_route.get("executor") != executor_id
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_MODEL_ROUTE_MISMATCH",
                    f"{path}.model_route",
                    "Assignment model_route must name the same Executor.",
                    [str(executor_id)],
                )
            )
        elif executor is not None:
            selected_class = model_route.get("selected_class")
            if (
                selected_class is not None
                and selected_class not in executor["model_policy"]["allowed_classes"]
            ):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_MODEL_ROUTE_MISMATCH",
                        f"{path}.model_route.selected_class",
                        f"Executor {executor_id} does not allow model class {selected_class}.",
                        [executor_id],
                    )
                )
            if model_route.get("host") != plan_host:
                diagnostics.append(
                    _diagnostic(
                        "ADAG_MODEL_ROUTE_MISMATCH",
                        f"{path}.model_route.host",
                        "Every Assignment model route must use the plan Host.",
                        [executor_id],
                    )
                )
            if _legacy_model_route(model_route):
                selected_class = model_route.get("selected_class")
                try:
                    host_profile = load_host_profile(plan_host)
                except MaestroError:
                    host_profile = None
                expected_model = (
                    None
                    if selected_class is None or host_profile is None
                    else host_profile["classes"][selected_class]["model"]
                )
                if (
                    host_profile is None
                    or model_route.get("selected_model")
                    != expected_model
                    or (
                        selected_class is None
                        and model_route.get("reasoning_effort") is not None
                    )
                ):
                    diagnostics.append(
                        _diagnostic(
                            "ADAG_MODEL_ROUTE_MISMATCH",
                            f"{path}.model_route",
                            "Legacy model_route must preserve the Host model mapping.",
                            [executor_id],
                        )
                    )
            if (
                isinstance(plan.get("goal"), str)
                and isinstance(plan.get("risk"), str)
                and plan["risk"] in ("low", "medium", "high", "critical")
                and isinstance(plan_host, str)
                and all(isinstance(item, str) for item in assignment_lenses)
            ):
                try:
                    expected_model_route = _assignment_model_route(
                        plan,
                        executor,
                        assignment_lenses,
                        assignment_id=assignment_id,
                        kind=assignment.get("kind", ""),
                        repo_path=repo_path,
                    )
                except MaestroError:
                    expected_model_route = None
                if (
                    expected_model_route is None
                    or (
                        not _legacy_model_route(model_route)
                        and model_route != expected_model_route
                    )
                ):
                    diagnostics.append(
                        _diagnostic(
                            "ADAG_MODEL_ROUTE_MISMATCH",
                            f"{path}.model_route",
                            "Assignment model_route does not match the active Registry and Host.",
                            [executor_id],
                        )
                    )

        if (
            assignment.get("may_spawn") is not False
            or isinstance(assignment.get("max_children"), bool)
            or assignment.get("max_children") != 0
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_SPAWN_FORBIDDEN",
                    path,
                    "Assignments may not spawn children in the v2 control-plane plan.",
                    [assignment_id],
                )
            )
        if (
            isinstance(assignment.get("max_rounds"), bool)
            or assignment.get("max_rounds") != 1
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_BOUND_EXCEEDED",
                    f"{path}.max_rounds",
                    "Each assignment is limited to one initial round.",
                    [assignment_id],
                )
            )

        read_only = assignment.get("read_only")
        mutation_owner = assignment.get("mutation_owner")
        allowed_side_effects = assignment.get("allowed_side_effects")
        if not isinstance(read_only, bool) or not isinstance(mutation_owner, bool):
            diagnostics.append(
                _diagnostic(
                    "ADAG_ASSIGNMENT_ACCESS_INVALID",
                    path,
                    "read_only and mutation_owner must be booleans.",
                    [assignment_id],
                )
            )
        if not isinstance(allowed_side_effects, list):
            diagnostics.append(
                _diagnostic(
                    "ADAG_ASSIGNMENT_ACCESS_INVALID",
                    f"{path}.allowed_side_effects",
                    "allowed_side_effects must be a list.",
                    [assignment_id],
                )
            )
            allowed_side_effects = []
        elif allowed_side_effects not in ([], ["repository_write"]):
            diagnostics.append(
                _diagnostic(
                    "ADAG_ASSIGNMENT_ACCESS_INVALID",
                    f"{path}.allowed_side_effects",
                    "Only repository_write is supported as an Assignment side effect.",
                    [assignment_id],
                )
            )
        if kind in ("research", "review", "verification") and (
            read_only is not True
            or mutation_owner is not False
            or allowed_side_effects
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_REVIEWER_WRITE_FORBIDDEN",
                    path,
                    "Research, review, and verification assignments must be read-only.",
                    [assignment_id],
                )
            )
        if read_only is False and (
            mutation_owner is not True
            or allowed_side_effects != ["repository_write"]
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_MUTATION_OWNER_MISMATCH",
                    path,
                    "The only writable assignment must be the repository mutation owner.",
                    [assignment_id],
                )
            )

    for duplicate_id in sorted(duplicate_ids):
        diagnostics.append(
            _diagnostic(
                "ADAG_DUPLICATE_ASSIGNMENT_ID",
                "assignments",
                f"Assignment ID is duplicated: {duplicate_id}.",
                [duplicate_id],
            )
        )

    ids = set(assignment_by_id)
    dependencies: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {assignment_id: [] for assignment_id in ids}
    for assignment_id, assignment in assignment_by_id.items():
        raw_dependencies = assignment.get("depends_on")
        if not isinstance(raw_dependencies, list) or not all(
            isinstance(item, str) for item in raw_dependencies
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_DEPENDENCIES_INVALID",
                    f"assignments.{assignment_id}.depends_on",
                    "depends_on must be a list of Assignment IDs.",
                    [assignment_id],
                )
            )
            raw_dependencies = []
        if len(raw_dependencies) != len(set(raw_dependencies)):
            diagnostics.append(
                _diagnostic(
                    "ADAG_DUPLICATE_EDGE",
                    f"assignments.{assignment_id}.depends_on",
                    "An Assignment dependency may appear only once.",
                    [assignment_id],
                )
            )
        unknown_dependencies = sorted(set(raw_dependencies) - ids)
        for dependency in unknown_dependencies:
            diagnostics.append(
                _diagnostic(
                    "ADAG_UNKNOWN_REFERENCE",
                    f"assignments.{assignment_id}.depends_on",
                    f"Unknown dependency: {dependency}.",
                    [assignment_id, dependency],
                )
            )
        dependencies[assignment_id] = [
            dependency
            for dependency in dict.fromkeys(raw_dependencies)
            if dependency in ids
        ]
        for dependency in dependencies[assignment_id]:
            outgoing[dependency].append(assignment_id)
            source_output = assignment_by_id[dependency].get("output_packet")
            target_inputs = assignment.get("input_packets")
            if not isinstance(target_inputs, list) or source_output not in target_inputs:
                diagnostics.append(
                    _diagnostic(
                        "ADAG_CONTRACT_MISMATCH",
                        f"assignments.{assignment_id}.depends_on",
                        f"{dependency} output is not accepted by {assignment_id}.",
                        [dependency, assignment_id],
                    )
                )

    diagnostics.extend(
        _canonical_flow_issues(plan, assignment_by_id, dependencies)
    )

    indegree = {
        assignment_id: len(dependencies.get(assignment_id, []))
        for assignment_id in ids
    }
    roots = sorted(
        assignment_id
        for assignment_id, count in indegree.items()
        if count == 0
    )
    queue = deque(roots)
    visited: list[str] = []
    while queue:
        current = queue.popleft()
        visited.append(current)
        for target in sorted(outgoing.get(current, [])):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(visited) != len(ids):
        cycle_ids = sorted(ids - set(visited))
        diagnostics.append(
            _diagnostic(
                "ADAG_CYCLE",
                "assignments",
                "The Assignment graph must be acyclic.",
                cycle_ids,
            )
        )

    leaves = sorted(
        assignment_id
        for assignment_id in ids
        if not outgoing.get(assignment_id)
    )
    declared_roots = plan.get("entry_assignments")
    declared_leaves = plan.get("terminal_assignments")
    declared_roots_valid = (
        isinstance(declared_roots, list)
        and all(isinstance(item, str) for item in declared_roots)
        and len(declared_roots) == len(set(declared_roots))
    )
    declared_leaves_valid = (
        isinstance(declared_leaves, list)
        and all(isinstance(item, str) for item in declared_leaves)
        and len(declared_leaves) == len(set(declared_leaves))
    )
    if not declared_roots_valid or sorted(declared_roots) != roots:
        diagnostics.append(
            _diagnostic(
                "ADAG_UNDECLARED_ROOT",
                "entry_assignments",
                "entry_assignments must declare every and only zero-dependency Assignment.",
                roots,
            )
        )
    if not declared_leaves_valid or sorted(declared_leaves) != leaves:
        diagnostics.append(
            _diagnostic(
                "ADAG_UNDECLARED_LEAF",
                "terminal_assignments",
                "terminal_assignments must declare every and only leaf Assignment.",
                leaves,
            )
        )
    if not leaves:
        diagnostics.append(
            _diagnostic(
                "ADAG_TERMINAL_MISSING",
                "terminal_assignments",
                "At least one terminal Assignment is required.",
            )
        )

    reachable: set[str] = set()
    pending = list(roots)
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(outgoing.get(current, []))
    unreachable = sorted(ids - reachable)
    if unreachable:
        diagnostics.append(
            _diagnostic(
                "ADAG_UNREACHABLE_ASSIGNMENT",
                "assignments",
                "Every Assignment must be reachable from an entry Assignment.",
                unreachable,
            )
        )

    owners = sorted(
        assignment_id
        for assignment_id, assignment in assignment_by_id.items()
        if assignment.get("mutation_owner") is True
    )
    declared_owner = plan.get("mutation_owner_assignment_id")
    if len(owners) > 1:
        diagnostics.append(
            _diagnostic(
                "ADAG_MULTIPLE_MUTATION_OWNERS",
                "mutation_owner_assignment_id",
                "At most one Assignment may own repository mutation.",
                owners,
            )
        )
    expected_owner = owners[0] if len(owners) == 1 else None
    if declared_owner != expected_owner:
        diagnostics.append(
            _diagnostic(
                "ADAG_MUTATION_OWNER_MISMATCH",
                "mutation_owner_assignment_id",
                "The declared mutation owner does not match the Assignment graph.",
                owners,
            )
        )

    task_contract = plan.get("task_contract")
    if not isinstance(task_contract, dict):
        diagnostics.append(
            _diagnostic(
                "ADAG_TASK_CONTRACT_INVALID",
                "task_contract",
                "task_contract must be an object.",
            )
        )
    else:
        for field in sorted(TASK_CONTRACT_FIELDS - set(task_contract)):
            diagnostics.append(
                _diagnostic(
                    "ADAG_REQUIRED_FIELD_MISSING",
                    f"task_contract.{field}",
                    f"Required task_contract field is missing: {field}.",
                )
            )
        for field in sorted(set(task_contract) - TASK_CONTRACT_FIELDS):
            diagnostics.append(
                _diagnostic(
                    "ADAG_UNKNOWN_FIELD",
                    f"task_contract.{field}",
                    f"Unsupported task_contract field: {field}.",
                )
            )
        limits = task_contract.get("limits")
        allowed = task_contract.get("allowed_side_effects")
        forbidden = task_contract.get("forbidden_side_effects")
        expected_allowed = ["repository_write"] if expected_owner else []
        expected_forbidden = (
            resolve_request_contract(
                plan["goal"],
                plan["intent"],
            )["forbidden_side_effects"]
            if (
                isinstance(plan.get("goal"), str)
                and isinstance(plan.get("intent"), str)
                and plan["intent"] in {"implementation", "review", "research"}
            )
            else None
        )
        if task_contract.get("objective") != plan.get("goal"):
            diagnostics.append(
                _diagnostic(
                    "ADAG_TASK_CONTRACT_INVALID",
                    "task_contract.objective",
                    "Task objective must match the routed goal.",
                )
            )
        if task_contract.get("terminal_condition") != "all_terminal_assignments_complete":
            diagnostics.append(
                _diagnostic(
                    "ADAG_TASK_CONTRACT_INVALID",
                    "task_contract.terminal_condition",
                    "The v2 terminal condition is unsupported.",
                )
            )
        if task_contract.get("stop_conditions") != [
            "required_gate_failed",
            "user_decision_required",
            "budget_exhausted",
        ]:
            diagnostics.append(
                _diagnostic(
                    "ADAG_TASK_CONTRACT_INVALID",
                    "task_contract.stop_conditions",
                    "The bounded v2 stop conditions must remain explicit and ordered.",
                )
            )
        if allowed != expected_allowed:
            diagnostics.append(
                _diagnostic(
                    "ADAG_MUTATION_OWNER_MISMATCH",
                    "task_contract.allowed_side_effects",
                    "Task side effects must match the unique mutation owner.",
                    owners,
                )
            )
        if (
            expected_forbidden is not None
            and forbidden != expected_forbidden
        ):
            diagnostics.append(
                _diagnostic(
                    "ADAG_TASK_CONTRACT_INVALID",
                    "task_contract.forbidden_side_effects",
                    "External-effect prohibitions must match the routed request.",
                )
            )
        if not isinstance(limits, dict):
            diagnostics.append(
                _diagnostic(
                    "ADAG_LIMITS_INVALID",
                    "task_contract.limits",
                    "Task limits must be an object.",
                )
            )
        else:
            for field in sorted(LIMIT_FIELDS - set(limits)):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_REQUIRED_FIELD_MISSING",
                        f"task_contract.limits.{field}",
                        f"Required limits field is missing: {field}.",
                    )
                )
            for field in sorted(set(limits) - LIMIT_FIELDS):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_UNKNOWN_FIELD",
                        f"task_contract.limits.{field}",
                        f"Unsupported limits field: {field}.",
                    )
                )
            max_lenses = limits.get("max_lenses")
            max_rebuttal_rounds = limits.get("max_rebuttal_rounds")
            max_assignments = limits.get("max_assignments")
            max_escalations = limits.get(
                "max_model_escalations_per_assignment"
            )
            depth_value = plan.get("depth")
            expected_max_lenses = (
                {"fast": 1, "standard": 2, "deep": 3}.get(depth_value)
                if isinstance(depth_value, str)
                else None
            )
            expected_rebuttal_rounds = (
                plan.get("deliberation", {}).get("max_rebuttal_rounds")
                if isinstance(plan.get("deliberation"), dict)
                else None
            )
            if (
                isinstance(max_assignments, bool)
                or max_assignments != MAX_ASSIGNMENTS
                or len(assignments) > (
                    max_assignments
                    if isinstance(max_assignments, int)
                    else -1
                )
                or isinstance(max_lenses, bool)
                or not isinstance(max_lenses, int)
                or len(selected_lens_set) > max_lenses
                or max_lenses < 1
                or max_lenses > MAX_LENSES
                or max_lenses != expected_max_lenses
                or isinstance(max_rebuttal_rounds, bool)
                or not isinstance(max_rebuttal_rounds, int)
                or max_rebuttal_rounds not in (0, 1)
                or max_rebuttal_rounds != expected_rebuttal_rounds
                or isinstance(max_escalations, bool)
                or max_escalations != MAX_MODEL_ESCALATIONS
            ):
                diagnostics.append(
                    _diagnostic(
                        "ADAG_BOUND_EXCEEDED",
                        "task_contract.limits",
                        "Task limits exceed or contradict the bounded v2 contract.",
                    )
                )

    selected_lens_counts = Counter(selected_lenses) if selected_lenses_valid else Counter()
    covered_lens_counts = Counter(covered_lenses)
    if covered_lens_counts != selected_lens_counts:
        diagnostics.append(
            _diagnostic(
                "ADAG_LENS_SELECTION_MISMATCH",
                "selected_lenses",
                "Every selected Lens must be assigned exactly once.",
                sorted(set(covered_lens_counts).symmetric_difference(selected_lens_set)),
            )
        )

    overlays = plan.get("model_policy_overlays")
    if overlays is not None:
        overlay_valid = (
            isinstance(overlays, list)
            and 1 <= len(overlays) <= 16
            and len(
                {
                    item.get("overlay_id")
                    for item in overlays
                    if isinstance(item, dict)
                }
            )
            == len(overlays)
            and all(
                validate_model_policy_overlay(item)
                for item in overlays
            )
            and repo_path is not None
            and all(
                validate_model_policy_overlay_authority(
                    item,
                    repo_path=repo_path,
                )
                for item in overlays
            )
        )
        if not overlay_valid:
            diagnostics.append(
                _diagnostic(
                    "ADAG_MODEL_POLICY_OVERLAY_INVALID",
                    "model_policy_overlays",
                    "Model-policy overlays must be unique accepted one-tier artifacts.",
                )
            )
        else:
            routed_values = [
                plan.get("model_route"),
                *[
                    item.get("model_route")
                    for item in plan.get("assignments", [])
                    if isinstance(item, dict)
                ],
            ]
            unused = [
                item["overlay_id"]
                for item in overlays
                if not any(
                    isinstance(route, dict)
                    and item["overlay_id"]
                    in str(route.get("selection_reason", ""))
                    for route in routed_values
                )
            ]
            if unused:
                diagnostics.append(
                    _diagnostic(
                        "ADAG_MODEL_POLICY_OVERLAY_UNUSED",
                        "model_policy_overlays",
                        "Every supplied overlay must match at least one newly typed route.",
                        sorted(unused),
                    )
                )

    if plan.get("registry_digest") != registry_digest():
        diagnostics.append(
            _diagnostic(
                "ADAG_REGISTRY_DIGEST_MISMATCH",
                "registry_digest",
                "The plan Registry digest does not match the installed Registry.",
            )
        )

    diagnostics.sort(
        key=lambda item: (
            item["code"],
            item["path"],
            item["related_ids"],
            item["message"],
        )
    )
    legacy_routes_present = (
        _legacy_model_route(plan.get("model_route"))
        or any(
            _legacy_model_route(assignment.get("model_route"))
            for assignment in (
                plan.get("assignments")
                if isinstance(plan.get("assignments"), list)
                else []
            )
            if isinstance(assignment, dict)
        )
    )
    return {
        "schema_version": "maestro_route_validation_v1",
        "status": "PASS" if not diagnostics else "FAIL",
        "execution_status": (
            "UPGRADE_REQUIRED"
            if not diagnostics and legacy_routes_present
            else "RESEARCH_REQUIRED"
            if (
                not diagnostics
                and (
                    expertise_gate == "open"
                    or (
                        expertise_gate == "satisfied"
                        and not research_evidence_ready
                    )
                )
            )
            else "READY"
            if not diagnostics
            else "INVALID"
        ),
        "plan_id": plan.get("plan_id"),
        "source_route_version": plan.get("source_route_version"),
        "issues": diagnostics,
        "writes_performed": False,
    }


def require_valid_route_v2(
    plan: dict[str, Any],
    *,
    repo_path: str | Path | None = None,
) -> None:
    result = validate_route_v2(plan, repo_path=repo_path)
    if result["status"] == "PASS":
        return
    codes = sorted({item["code"] for item in result["issues"]})
    raise MaestroError(
        "ROUTE_SEMANTIC_INVALID",
        f"Route v2 failed pre-execution validation: {', '.join(codes)}.",
    )
