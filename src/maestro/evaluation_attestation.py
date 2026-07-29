from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import MaestroError
from .model_policy import (
    LEGACY_MODEL_ROUTE_FIELDS,
    validate_model_route_shape,
)
from .observations import (
    observation_id_for_run,
    observation_receipt_fields,
)
from .registry import load_host_profile


_STAGE_MINIMUM_PAIRS = {
    "implementation": {
        ("economy", "high"),
        ("balanced", "high"),
        ("frontier", "high"),
    },
    "semantic-review": {
        ("balanced", "high"),
        ("frontier", "high"),
    },
    "research": {
        ("balanced", "high"),
        ("frontier", "high"),
    },
    "semantic-verification": {
        ("balanced", "high"),
        ("frontier", "high"),
    },
    "specialist-review": {
        ("balanced", "high"),
        ("frontier", "high"),
    },
    "expertise-review": {
        ("balanced", "high"),
        ("frontier", "high"),
    },
    "intermediate-synthesis": {("frontier", "high")},
    "technical-feasibility": {("frontier", "high")},
    "final-synthesis": {("frontier", "high")},
}
_FRONTIER_TASK_CLASSES = {
    "architecture-judgment",
    "complex-implementation",
    "complex-semantic-judgment",
    "final-synthesis",
    "high-impact-judgment",
    "material-conflict-resolution",
}


def _active_stage_floor_valid(
    *,
    stage_kind: Any,
    selected_class: Any,
    selected_model: Any,
    reasoning_effort: Any,
    host_id: str = "codex",
    task_class: Any = None,
    risk: Any = None,
) -> bool:
    allowed_pairs = _STAGE_MINIMUM_PAIRS.get(stage_kind)
    if (
        allowed_pairs is None
        or (selected_class, reasoning_effort) not in allowed_pairs
        or not isinstance(selected_model, str)
    ):
        return False
    if (
        risk in {"high", "critical"}
        or task_class in _FRONTIER_TASK_CLASSES
    ) and (selected_class, reasoning_effort) != ("frontier", "high"):
        return False
    try:
        host_profile = load_host_profile(host_id)
    except MaestroError:
        return False
    return (
        selected_class in host_profile["classes"]
        and host_profile["classes"][selected_class]["model"]
        == selected_model
    )


def _assignment_stage_valid(
    assignment: dict[str, Any],
    *,
    allowed_stage_kinds: set[str],
) -> bool:
    route = assignment.get("model_route")
    if isinstance(route, dict):
        if set(route) == LEGACY_MODEL_ROUTE_FIELDS:
            return False
        return (
            validate_model_route_shape(route) is None
            and route.get("stage_kind") in allowed_stage_kinds
            and _active_stage_floor_valid(
                stage_kind=route.get("stage_kind"),
                selected_class=route.get("selected_class"),
                selected_model=route.get("selected_model"),
                reasoning_effort=route.get("reasoning_effort"),
                host_id=route.get("host", "codex"),
                task_class=route.get("task_class"),
                risk=route.get("risk"),
            )
        )
    stage_kind = assignment.get("stage_kind")
    if stage_kind is None:
        return False
    return (
        stage_kind in allowed_stage_kinds
        and assignment.get("quality_profile") == "pro-quality"
        and isinstance(assignment.get("model_route_id"), str)
        and len(assignment["model_route_id"]) == 64
        and _active_stage_floor_valid(
            stage_kind=stage_kind,
            selected_class=assignment.get("selected_class"),
            selected_model=assignment.get("planned_model"),
            reasoning_effort=assignment.get("reasoning_effort"),
        )
    )


def read_only_evaluation_receipts_valid(
    *,
    evaluated: Any,
    authored: Any,
    evaluation_observation_id: Any,
    authoring_observation_id: Any,
    subject_evidence_refs: set[str],
    result_evidence_ref: Any,
    evaluator_kind: Any,
) -> bool:
    """Validate detached authoring and evaluation receipt payloads."""

    if (
        not isinstance(evaluated, dict)
        or not isinstance(authored, dict)
        or not isinstance(evaluation_observation_id, str)
        or not isinstance(authoring_observation_id, str)
        or evaluation_observation_id == authoring_observation_id
        or not subject_evidence_refs
        or not isinstance(result_evidence_ref, str)
        or not result_evidence_ref.strip()
        or evaluator_kind not in {"fresh-context", "human"}
    ):
        return False
    evaluation_plan = evaluated.get("plan_summary", {}).get(
        "assignments",
        [],
    )
    evaluation_results = evaluated.get("stage_results", [])
    evaluation_by_id = {
        item.get("assignment_id"): item
        for item in evaluation_plan
        if isinstance(item, dict)
        and isinstance(item.get("assignment_id"), str)
    }
    evaluation_result_by_id = {
        item.get("assignment_id"): item
        for item in evaluation_results
        if isinstance(item, dict)
        and isinstance(item.get("assignment_id"), str)
    }
    required_evaluation_refs = {
        *subject_evidence_refs,
        result_evidence_ref,
    }
    expected_source = (
        "codex_app_server"
        if evaluator_kind == "fresh-context"
        else "current_host"
    )
    evaluation_valid = (
        bool(evaluation_by_id)
        and set(evaluation_result_by_id) == set(evaluation_by_id)
        and all(
            assignment.get("read_only") is True
            and assignment.get("mutation_owner") is False
            and _assignment_stage_valid(
                assignment,
                allowed_stage_kinds={
                    "semantic-review",
                    "semantic-verification",
                    "specialist-review",
                    "technical-feasibility",
                    "final-synthesis",
                },
            )
            for assignment in evaluation_by_id.values()
        )
        and all(
            result.get("status") == "completed"
            and result.get("evidence_source") == expected_source
            for result in evaluation_result_by_id.values()
        )
        and any(
            required_evaluation_refs.issubset(
                set(result.get("evidence_refs", []))
            )
            for result in evaluation_result_by_id.values()
        )
    )

    authoring_plan = authored.get("plan_summary", {}).get(
        "assignments",
        [],
    )
    authoring_results = authored.get("stage_results", [])
    authoring_by_id = {
        item.get("assignment_id"): item
        for item in authoring_plan
        if isinstance(item, dict)
        and isinstance(item.get("assignment_id"), str)
    }
    authoring_result_by_id = {
        item.get("assignment_id"): item
        for item in authoring_results
        if isinstance(item, dict)
        and isinstance(item.get("assignment_id"), str)
    }
    authoring_valid = (
        bool(authoring_by_id)
        and set(authoring_result_by_id) == set(authoring_by_id)
        and all(
            result.get("status") == "completed"
            for result in authoring_result_by_id.values()
        )
        and any(
            assignment.get("mutation_owner") is True
            and assignment.get("read_only") is False
            and _assignment_stage_valid(
                assignment,
                allowed_stage_kinds={"implementation"},
            )
            and subject_evidence_refs.issubset(
                set(
                    authoring_result_by_id.get(
                        assignment_id,
                        {},
                    ).get("evidence_refs", [])
                )
            )
            for assignment_id, assignment in authoring_by_id.items()
        )
    )
    return evaluation_valid and authoring_valid


def observed_read_only_evaluation(
    repo_path: str | Path,
    *,
    observation_id: Any,
    evaluation_run_id: Any,
    authoring_run_id: Any,
    subject_evidence_refs: set[str],
    result_evidence_ref: Any,
    evaluator_kind: Any,
) -> bool:
    """Confirm detached authoring and output-bound read-only evaluation."""

    if (
        not isinstance(observation_id, str)
        or not isinstance(evaluation_run_id, str)
        or not evaluation_run_id.strip()
        or not isinstance(authoring_run_id, str)
        or not authoring_run_id.strip()
        or authoring_run_id == evaluation_run_id
        or not subject_evidence_refs
        or not isinstance(result_evidence_ref, str)
        or not result_evidence_ref.strip()
        or evaluator_kind not in {"fresh-context", "human"}
    ):
        return False
    try:
        evaluated = observation_receipt_fields(
            repo_path,
            observation_id=observation_id,
            run_id=evaluation_run_id,
        )
        authoring_observation_id = observation_id_for_run(
            repo_path,
            run_id=authoring_run_id,
        )
        authored = observation_receipt_fields(
            repo_path,
            observation_id=authoring_observation_id,
            run_id=authoring_run_id,
        )
    except (MaestroError, TypeError, ValueError):
        return False

    if authoring_observation_id == observation_id:
        return False
    return read_only_evaluation_receipts_valid(
        evaluated=evaluated,
        authored=authored,
        evaluation_observation_id=observation_id,
        authoring_observation_id=authoring_observation_id,
        subject_evidence_refs=subject_evidence_refs,
        result_evidence_ref=result_evidence_ref,
        evaluator_kind=evaluator_kind,
    )
