from __future__ import annotations

import copy
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .errors import MaestroError
from .model_policy import validate_model_route_shape
from .util import canonical_json, sha256_text


EXECUTION_UNIT_VERSION = "maestro_execution_unit_v1"
EXECUTION_UNIT_RECEIPT_VERSION = "maestro_execution_unit_receipt_v1"
EXECUTION_ATTEMPT_VERSION = "maestro_execution_attempt_v1"
MAX_EXECUTION_UNITS = 1_024
MAX_EXECUTION_ATTEMPTS = 2
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_LOCAL_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

EXECUTION_UNIT_FIELDS = {
    "schema_version",
    "unit_id",
    "unit_digest",
    "source_kind",
    "source_schema_version",
    "source_plan_id",
    "source_plan_digest",
    "source_unit_digest",
    "local_unit_id",
    "stage_kind",
    "executor_id",
    "read_only",
    "mutation_owner",
    "depends_on_unit_ids",
    "input_packet_types",
    "output_packet_type",
    "model_route",
    "host_executable",
    "execution_status",
}
RECEIPT_FIELDS = {
    "schema_version",
    "receipt_id",
    "unit_id",
    "unit_digest",
    "source_plan_digest",
    "local_unit_id",
    "model_route_id",
    "input_digest",
    "dependency_receipt_ids",
    "attempts",
    "output_packet_type",
    "output_packet_digest",
    "verification_assessment_id",
    "terminal_work_id",
    "terminal_status",
    "effect_state",
    "producer",
    "issued_at",
}
ATTEMPT_FIELDS = {
    "schema_version",
    "attempt_id",
    "attempt",
    "followup_of_attempt",
    "route_kind",
    "requested_class",
    "requested_model",
    "requested_reasoning_effort",
    "applied_model",
    "applied_reasoning_effort",
    "reasoning_effort_evidence",
    "status",
    "transition_trigger",
    "provider_reroutes",
    "thread_id",
    "turn_id",
    "duration_ms",
    "tokens",
    "writes_observed",
}


def observation_identity(
    *,
    project_id: str,
    checkout_id: str,
    run_id: str,
) -> str:
    """Return the deterministic observation identity shared by all receipts."""

    return sha256_text(
        canonical_json(
            {
                "project_id": project_id,
                "checkout_id": checkout_id,
                "run_id": run_id,
            }
        )
    )[:32]
PRODUCER_FIELDS = {
    "interface",
    "framework_version",
    "runtime_schema_digest",
    "run_id",
    "observation_id",
}
REROUTE_FIELDS = {"from_model", "to_model", "reason"}


def _digest(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload[field] = ""
    return sha256_text(canonical_json(payload))


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _line(
    value: Any,
    *,
    maximum: int = 240,
    optional: bool = False,
) -> bool:
    if value is None:
        return optional
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and not any(character in value for character in "\r\n\x00")
    )


def _unique_lines(
    value: Any,
    *,
    maximum: int = MAX_EXECUTION_UNITS,
) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= maximum
        and len(value) == len(set(value))
        and all(_line(item) for item in value)
    )


def _timestamp(value: Any) -> bool:
    if not _line(value, maximum=64):
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _source_plan_digest(
    source_schema_version: str,
    source_plan: dict[str, Any],
) -> tuple[str, str]:
    if source_schema_version == "maestro_execution_plan_v1":
        return source_plan["route_plan"]["plan_id"], source_plan["execution_plan_id"]
    if source_schema_version == "maestro_route_v2":
        return source_plan["plan_id"], source_plan["plan_id"]
    if source_schema_version == "maestro_decision_plan_v1":
        return source_plan["plan_id"], source_plan["plan_id"]
    if source_schema_version == "maestro_expertise_work_plan_v1":
        return source_plan["work_plan_id"], source_plan["work_plan_id"]
    raise MaestroError(
        "EXECUTION_UNIT_SOURCE_UNSUPPORTED",
        f"Unsupported execution-unit source {source_schema_version!r}.",
    )


def _common_unit_id(
    *,
    source_schema_version: str,
    source_plan_digest: str,
    local_unit_id: str,
    source_unit_digest: str,
) -> str:
    return sha256_text(
        canonical_json(
            {
                "source_schema_version": source_schema_version,
                "source_plan_digest": source_plan_digest,
                "local_unit_id": local_unit_id,
                "source_unit_digest": source_unit_digest,
            }
        )
    )


def _project(
    *,
    source_kind: str,
    source_schema_version: str,
    source_plan_id: str,
    source_plan_digest: str,
    raw_units: list[dict[str, Any]],
    executable: bool,
) -> list[dict[str, Any]]:
    if len(raw_units) > MAX_EXECUTION_UNITS:
        raise MaestroError(
            "EXECUTION_UNIT_LIMIT_EXCEEDED",
            f"At most {MAX_EXECUTION_UNITS} units may be projected.",
        )
    source_unit_digests: dict[str, str] = {}
    common_ids: dict[str, str] = {}
    for raw in raw_units:
        local_id = raw.get("local_unit_id")
        if (
            not isinstance(local_id, str)
            or _LOCAL_ID.fullmatch(local_id) is None
            or local_id in common_ids
        ):
            raise MaestroError(
                "EXECUTION_UNIT_SOURCE_INVALID",
                "Source units need unique lowercase kebab-case local IDs.",
            )
        source_digest = sha256_text(canonical_json(raw["source_unit"]))
        source_unit_digests[local_id] = source_digest
        common_ids[local_id] = _common_unit_id(
            source_schema_version=source_schema_version,
            source_plan_digest=source_plan_digest,
            local_unit_id=local_id,
            source_unit_digest=source_digest,
        )

    units: list[dict[str, Any]] = []
    for raw in raw_units:
        local_id = raw["local_unit_id"]
        dependencies = raw.get("depends_on", [])
        if (
            not isinstance(dependencies, list)
            or len(dependencies) != len(set(dependencies))
            or any(dependency not in common_ids for dependency in dependencies)
        ):
            raise MaestroError(
                "EXECUTION_UNIT_DEPENDENCY_INVALID",
                f"Execution unit {local_id} has an unknown or duplicate dependency.",
            )
        route = raw.get("model_route")
        route_error = validate_model_route_shape(route)
        if route_error is not None:
            raise MaestroError(
                "EXECUTION_UNIT_MODEL_ROUTE_INVALID",
                f"{local_id}: {route_error}",
            )
        model_bearing = route["execution_kind"] == "model"
        unit = {
            "schema_version": EXECUTION_UNIT_VERSION,
            "unit_id": common_ids[local_id],
            "unit_digest": "",
            "source_kind": source_kind,
            "source_schema_version": source_schema_version,
            "source_plan_id": source_plan_id,
            "source_plan_digest": source_plan_digest,
            "source_unit_digest": source_unit_digests[local_id],
            "local_unit_id": local_id,
            "stage_kind": route["stage_kind"],
            "executor_id": raw["executor_id"],
            "read_only": raw["read_only"],
            "mutation_owner": raw["mutation_owner"],
            "depends_on_unit_ids": [
                common_ids[dependency] for dependency in dependencies
            ],
            "input_packet_types": list(raw["input_packet_types"]),
            "output_packet_type": raw["output_packet_type"],
            "model_route": copy.deepcopy(route),
            "host_executable": bool(executable and model_bearing),
            "execution_status": (
                "READY"
                if executable and model_bearing
                else "NOT_APPLICABLE"
                if not model_bearing
                else "UPGRADE_REQUIRED"
            ),
        }
        unit["unit_digest"] = _digest(unit, "unit_digest")
        units.append(unit)
    return units


def project_route_execution_units(
    source_plan: Any,
    *,
    repo_path: str | Path | None = None,
    research_bundle: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Project a validated Route v2 or Decision enactment route."""

    from .decisions import EXECUTION_PLAN_VERSION, validate_execution_plan
    from .planning import ROUTE_V2, validate_route_v2

    if not isinstance(source_plan, dict):
        raise MaestroError(
            "EXECUTION_UNIT_SOURCE_INVALID",
            "Execution-unit source must be one object.",
        )
    schema = source_plan.get("schema_version")
    if schema == EXECUTION_PLAN_VERSION:
        validation = validate_execution_plan(
            source_plan,
            repo_path=repo_path,
            research_bundle=research_bundle,
        )
        route_plan = source_plan.get("route_plan")
    elif schema == ROUTE_V2:
        validation = validate_route_v2(
            source_plan,
            repo_path=repo_path,
            research_bundle=research_bundle,
        )
        route_plan = source_plan
    else:
        raise MaestroError(
            "EXECUTION_UNIT_SOURCE_UNSUPPORTED",
            "Route execution units require Route v2 or one validated enactment.",
        )
    if validation["status"] != "PASS" or not isinstance(route_plan, dict):
        first = next(
            iter(validation.get("issues", [])),
            {
                "code": "EXECUTION_UNIT_SOURCE_INVALID",
                "message": "The Route source is invalid.",
            },
        )
        raise MaestroError(first["code"], first["message"])
    source_plan_id, source_digest = _source_plan_digest(schema, source_plan)
    raw_units = [
        {
            "local_unit_id": assignment["assignment_id"],
            "source_unit": assignment,
            "executor_id": assignment["executor_id"],
            "read_only": assignment["read_only"],
            "mutation_owner": assignment["mutation_owner"],
            "depends_on": assignment["depends_on"],
            "input_packet_types": assignment["input_packets"],
            "output_packet_type": assignment["output_packet"],
            "model_route": assignment["model_route"],
        }
        for assignment in route_plan["assignments"]
    ]
    return _project(
        source_kind="route-assignment",
        source_schema_version=schema,
        source_plan_id=source_plan_id,
        source_plan_digest=source_digest,
        raw_units=raw_units,
        executable=True,
    )


def project_decision_execution_units(
    decision_plan: Any,
) -> list[dict[str, Any]]:
    """Project validated Decision assignments without granting Host authority."""

    from .decisions import DECISION_PLAN_VERSION, validate_decision_plan

    validation = validate_decision_plan(decision_plan)
    if validation["status"] != "PASS":
        first = next(
            iter(validation.get("issues", [])),
            {
                "code": "EXECUTION_UNIT_SOURCE_INVALID",
                "message": "The DecisionPlan is invalid.",
            },
        )
        raise MaestroError(first["code"], first["message"])
    assert isinstance(decision_plan, dict)
    raw_units = [
        {
            "local_unit_id": assignment["assignment_id"],
            "source_unit": assignment,
            "executor_id": assignment["executor_id"],
            "read_only": assignment["read_only"],
            "mutation_owner": False,
            "depends_on": assignment["depends_on"],
            "input_packet_types": assignment["input_packets"],
            "output_packet_type": assignment["output_packet"],
            "model_route": assignment["model_route"],
        }
        for assignment in decision_plan["assignments"]
    ]
    return _project(
        source_kind="decision-assignment",
        source_schema_version=DECISION_PLAN_VERSION,
        source_plan_id=decision_plan["plan_id"],
        source_plan_digest=decision_plan["plan_id"],
        raw_units=raw_units,
        executable=False,
    )


def project_expertise_execution_units(
    work_plan: Any,
    *,
    repo_path: str | Path,
    goal: str,
    coverage: Any,
    source_plan: Any,
    research_bundle: dict[str, Any] | None = None,
    expertise_research_bundles: Any = None,
) -> list[dict[str, Any]]:
    """Project fully revalidated Expertise batches without Host authority."""

    from .expertise_work import (
        EXPERTISE_WORK_PLAN_VERSION,
        validate_expertise_work_plan,
    )

    validation = validate_expertise_work_plan(
        work_plan,
        repo_path=repo_path,
        goal=goal,
        coverage=coverage,
        plan=source_plan,
        research_bundle=research_bundle,
        expertise_research_bundles=expertise_research_bundles,
    )
    if validation["status"] != "PASS":
        first = next(
            iter(validation.get("issues", [])),
            {
                "code": "EXECUTION_UNIT_SOURCE_INVALID",
                "message": "The ExpertiseWorkPlan is invalid.",
            },
        )
        raise MaestroError(first["code"], first["message"])
    if validation.get("execution_status") != "READY":
        raise MaestroError(
            "EXECUTION_UNIT_SOURCE_UPGRADE_REQUIRED",
            "Legacy Expertise batches need typed stage routes before projection.",
        )
    assert isinstance(work_plan, dict)
    raw_units = [
        {
            "local_unit_id": batch["batch_id"],
            "source_unit": batch,
            "executor_id": batch["model_route"]["executor"],
            "read_only": batch["read_only"],
            "mutation_owner": False,
            "depends_on": batch["depends_on"],
            "input_packet_types": ["ExpertiseWorkInput"],
            "output_packet_type": "ExpertiseWorkPacket",
            "model_route": batch["model_route"],
        }
        for batch in work_plan["batches"]
    ]
    return _project(
        source_kind="expertise-batch",
        source_schema_version=EXPERTISE_WORK_PLAN_VERSION,
        source_plan_id=work_plan["work_plan_id"],
        source_plan_digest=work_plan["work_plan_id"],
        raw_units=raw_units,
        executable=False,
    )


def validate_execution_unit(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != EXECUTION_UNIT_FIELDS
        or value.get("schema_version") != EXECUTION_UNIT_VERSION
        or not _is_digest(value.get("unit_id"))
        or not _is_digest(value.get("unit_digest"))
        or value["unit_digest"] != _digest(value, "unit_digest")
        or value.get("source_kind")
        not in {
            "route-assignment",
            "decision-assignment",
            "expertise-batch",
        }
        or not _line(value.get("source_schema_version"))
        or not _is_digest(value.get("source_plan_id"))
        or not _is_digest(value.get("source_plan_digest"))
        or not _is_digest(value.get("source_unit_digest"))
        or not isinstance(value.get("local_unit_id"), str)
        or _LOCAL_ID.fullmatch(value["local_unit_id"]) is None
        or not _line(value.get("stage_kind"))
        or not _line(value.get("executor_id"))
        or not isinstance(value.get("read_only"), bool)
        or not isinstance(value.get("mutation_owner"), bool)
        or value.get("mutation_owner") is (value.get("read_only") is True)
        or not _unique_lines(value.get("depends_on_unit_ids"))
        or not all(
            _is_digest(item) for item in value["depends_on_unit_ids"]
        )
        or not _unique_lines(value.get("input_packet_types"))
        or not _line(value.get("output_packet_type"))
        or not isinstance(value.get("host_executable"), bool)
        or value.get("execution_status")
        not in {"READY", "UPGRADE_REQUIRED", "NOT_APPLICABLE"}
        or (value["host_executable"] is True)
        != (value["execution_status"] == "READY")
        or validate_model_route_shape(value.get("model_route")) is not None
    ):
        return False
    expected_unit_id = _common_unit_id(
        source_schema_version=value["source_schema_version"],
        source_plan_digest=value["source_plan_digest"],
        local_unit_id=value["local_unit_id"],
        source_unit_digest=value["source_unit_digest"],
    )
    return (
        value["unit_id"] == expected_unit_id
        and value["model_route"]["execution_unit_id"]
        == value["local_unit_id"]
        and value["model_route"]["stage_kind"] == value["stage_kind"]
        and value["model_route"]["executor"] == value["executor_id"]
        and (
            value["model_route"]["execution_kind"] == "model"
            or value["execution_status"] == "NOT_APPLICABLE"
        )
    )


def validate_plan_execution_units(plan_summary: Any) -> bool:
    """Bind projected ExecutionUnits back to their compact source plan."""

    if not isinstance(plan_summary, dict) or not isinstance(
        plan_summary.get("assignments"),
        list,
    ):
        return False
    assignments = plan_summary["assignments"]
    assignment_by_id = {
        assignment.get("assignment_id"): assignment
        for assignment in assignments
        if isinstance(assignment, dict)
        and isinstance(assignment.get("assignment_id"), str)
    }
    if len(assignment_by_id) != len(assignments):
        return False
    receipts_required = (
        plan_summary.get("execution_receipts_required") is True
    )
    has_any_execution_unit = any(
        isinstance(assignment.get("execution_unit"), dict)
        for assignment in assignments
    )
    has_all_execution_units = bool(assignments) and all(
        isinstance(assignment.get("execution_unit"), dict)
        for assignment in assignments
    )
    if receipts_required and not has_all_execution_units:
        return False
    if not has_any_execution_unit:
        return True
    if not has_all_execution_units:
        return False

    execution_contract = plan_summary.get("execution_contract")
    decision_enactment = (
        isinstance(execution_contract, dict)
        and execution_contract.get("kind") == "decision-enactment"
    )
    expected_source_schema = (
        "maestro_execution_plan_v1"
        if decision_enactment
        else "maestro_route_v2"
    )
    expected_source_digest = (
        execution_contract.get("execution_plan_id")
        if decision_enactment
        else plan_summary.get("plan_id")
    )
    unit_by_assignment = {
        assignment_id: assignment["execution_unit"]
        for assignment_id, assignment in assignment_by_id.items()
    }
    for assignment_id, assignment in assignment_by_id.items():
        unit = unit_by_assignment[assignment_id]
        dependencies = assignment.get("depends_on")
        if (
            not validate_execution_unit(unit)
            or not isinstance(dependencies, list)
            or any(
                dependency not in unit_by_assignment
                for dependency in dependencies
            )
            or unit.get("source_kind") != "route-assignment"
            or unit.get("source_schema_version")
            != expected_source_schema
            or unit.get("source_plan_id") != plan_summary.get("plan_id")
            or unit.get("source_plan_digest") != expected_source_digest
            or unit.get("local_unit_id") != assignment_id
            or unit.get("depends_on_unit_ids")
            != [
                unit_by_assignment[dependency]["unit_id"]
                for dependency in dependencies
            ]
            or unit.get("executor_id") != assignment.get("executor_id")
            or unit.get("read_only") is not assignment.get("read_only")
            or unit.get("mutation_owner")
            is not assignment.get("mutation_owner")
        ):
            return False
        route = unit["model_route"]
        if (
            route.get("model_route_id")
            != assignment.get("model_route_id")
            or route.get("execution_unit_id")
            != assignment.get("execution_unit_id")
            or route.get("stage_kind") != assignment.get("stage_kind")
            or route.get("execution_kind")
            != assignment.get("execution_kind")
            or route.get("quality_profile")
            != assignment.get("quality_profile")
            or route.get("task_class") != assignment.get("task_class")
            or route.get("risk") != plan_summary.get("risk")
            or route.get("selected_class")
            != assignment.get("selected_class")
            or route.get("selected_model")
            != assignment.get("planned_model")
            or route.get("reasoning_effort")
            != assignment.get("reasoning_effort")
            or route.get("quality_floor")
            != assignment.get("quality_floor")
            or route.get("fallback_route")
            != assignment.get("fallback_route")
        ):
            return False
    return True


def _valid_tokens(value: Any) -> bool:
    return value is None or (
        isinstance(value, dict)
        and set(value) == {"input", "output", "cached", "reasoning", "total"}
        and all(
            isinstance(item, int)
            and not isinstance(item, bool)
            and item >= 0
            for item in value.values()
        )
    )


def _valid_reroutes(value: Any) -> bool:
    if not isinstance(value, list) or len(value) > 1:
        return False
    return all(
        isinstance(item, dict)
        and set(item) == REROUTE_FIELDS
        and _line(item.get("from_model"), maximum=128)
        and _line(item.get("to_model"), maximum=128)
        and _line(item.get("reason"), maximum=240)
        for item in value
    )


def _valid_attempt_shape(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != ATTEMPT_FIELDS
        or value.get("schema_version") != EXECUTION_ATTEMPT_VERSION
        or not _is_digest(value.get("attempt_id"))
        or value["attempt_id"] != _digest(value, "attempt_id")
        or value.get("attempt") not in {1, 2}
        or isinstance(value.get("attempt"), bool)
        or value.get("followup_of_attempt") not in {None, 1}
        or value.get("route_kind") not in {"primary", "fallback"}
        or value.get("requested_class")
        not in {"economy", "balanced", "frontier"}
        or not _line(value.get("requested_model"), maximum=128)
        or value.get("requested_reasoning_effort")
        not in {"low", "medium", "high", "xhigh"}
        or not _line(
            value.get("applied_model"),
            maximum=128,
            optional=True,
        )
        or value.get("applied_reasoning_effort")
        not in {None, "low", "medium", "high", "xhigh"}
        or value.get("reasoning_effort_evidence")
        not in {"host-attested", "requested-only", "unavailable"}
        or value.get("status")
        not in {
            "completed",
            "model-unavailable",
            "failed",
            "blocked",
            "interrupted",
        }
        or value.get("transition_trigger")
        not in {None, "selected-model-unavailable"}
        or not _valid_reroutes(value.get("provider_reroutes"))
        or not _line(value.get("thread_id"), maximum=160)
        or not _line(value.get("turn_id"), maximum=160)
        or not isinstance(value.get("duration_ms"), (int, float))
        or isinstance(value.get("duration_ms"), bool)
        or not math.isfinite(value["duration_ms"])
        or value["duration_ms"] < 0
        or not _valid_tokens(value.get("tokens"))
        or value.get("writes_observed") not in {None, False, True}
    ):
        return False
    if (
        value["reasoning_effort_evidence"] == "host-attested"
        and value["applied_reasoning_effort"] is None
    ):
        return False
    if (
        value["reasoning_effort_evidence"] != "host-attested"
        and value["applied_reasoning_effort"] is not None
    ):
        return False
    return True


def build_execution_attempt(
    *,
    attempt: int,
    followup_of_attempt: int | None,
    route_kind: str,
    requested_class: str,
    requested_model: str,
    requested_reasoning_effort: str,
    applied_model: str | None,
    applied_reasoning_effort: str | None,
    reasoning_effort_evidence: str,
    status: str,
    transition_trigger: str | None,
    provider_reroutes: Iterable[dict[str, Any]],
    thread_id: str,
    turn_id: str,
    duration_ms: float,
    tokens: dict[str, int] | None,
    writes_observed: bool | None,
) -> dict[str, Any]:
    value = {
        "schema_version": EXECUTION_ATTEMPT_VERSION,
        "attempt_id": "",
        "attempt": attempt,
        "followup_of_attempt": followup_of_attempt,
        "route_kind": route_kind,
        "requested_class": requested_class,
        "requested_model": requested_model,
        "requested_reasoning_effort": requested_reasoning_effort,
        "applied_model": applied_model,
        "applied_reasoning_effort": applied_reasoning_effort,
        "reasoning_effort_evidence": reasoning_effort_evidence,
        "status": status,
        "transition_trigger": transition_trigger,
        "provider_reroutes": [
            copy.deepcopy(item) for item in provider_reroutes
        ],
        "thread_id": thread_id,
        "turn_id": turn_id,
        "duration_ms": duration_ms,
        "tokens": copy.deepcopy(tokens),
        "writes_observed": writes_observed,
    }
    value["attempt_id"] = _digest(value, "attempt_id")
    if not _valid_attempt_shape(value):
        raise MaestroError(
            "EXECUTION_UNIT_ATTEMPT_INVALID",
            "The Host attempt does not satisfy the bounded execution contract.",
        )
    return value


def build_execution_unit_receipt(
    *,
    unit: dict[str, Any],
    input_digest: str,
    dependency_units: Iterable[dict[str, Any]] = (),
    dependency_receipts: Iterable[dict[str, Any]] = (),
    attempts: Iterable[dict[str, Any]],
    output_packet_digest: str | None,
    verification_assessment_id: str | None = None,
    terminal_work_id: str | None,
    terminal_status: str,
    effect_state: str,
    producer: dict[str, Any],
    issued_at: str | None = None,
) -> dict[str, Any]:
    dependency_units_list = list(dependency_units)
    dependency_receipts_list = list(dependency_receipts)
    receipt_by_unit = {
        receipt.get("unit_id"): receipt
        for receipt in dependency_receipts_list
        if isinstance(receipt, dict)
    }
    required_dependency_ids = [
        dependency_id
        for dependency_id in unit.get("depends_on_unit_ids", [])
        if any(
            dependency.get("unit_id") == dependency_id
            and dependency.get("host_executable") is True
            for dependency in dependency_units_list
            if isinstance(dependency, dict)
        )
    ]
    value = {
        "schema_version": EXECUTION_UNIT_RECEIPT_VERSION,
        "receipt_id": "",
        "unit_id": unit.get("unit_id"),
        "unit_digest": unit.get("unit_digest"),
        "source_plan_digest": unit.get("source_plan_digest"),
        "local_unit_id": unit.get("local_unit_id"),
        "model_route_id": unit.get("model_route", {}).get(
            "model_route_id"
        ),
        "input_digest": input_digest,
        "dependency_receipt_ids": [
            receipt_by_unit[dependency_id]["receipt_id"]
            for dependency_id in required_dependency_ids
            if dependency_id in receipt_by_unit
        ],
        "attempts": [copy.deepcopy(item) for item in attempts],
        "output_packet_type": unit.get("output_packet_type"),
        "output_packet_digest": output_packet_digest,
        "verification_assessment_id": verification_assessment_id,
        "terminal_work_id": terminal_work_id,
        "terminal_status": terminal_status,
        "effect_state": effect_state,
        "producer": copy.deepcopy(producer),
        "issued_at": (
            issued_at
            or datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
    }
    value["receipt_id"] = _digest(value, "receipt_id")
    validation = validate_execution_unit_receipt(
        value,
        unit=unit,
        dependency_units=dependency_units_list,
        dependency_receipts=dependency_receipts_list,
    )
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    return value


def validate_execution_unit_receipt(
    value: Any,
    *,
    unit: Any,
    dependency_units: Iterable[Any] = (),
    dependency_receipts: Iterable[Any] = (),
) -> dict[str, Any]:
    """Validate one content-addressed Host receipt against its exact unit."""

    issues: list[dict[str, str]] = []
    if not validate_execution_unit(unit):
        issues.append(
            {
                "code": "EXECUTION_UNIT_INVALID",
                "path": "unit",
                "message": "Receipt validation requires one valid ExecutionUnit.",
            }
        )
    elif (
        unit.get("host_executable") is not True
        or unit.get("execution_status") != "READY"
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_HOST_AUTHORITY_REQUIRED",
                "path": "unit.host_executable",
                "message": "Only a READY Route unit may receive a Host execution receipt.",
            }
        )
    if (
        not isinstance(value, dict)
        or set(value) != RECEIPT_FIELDS
        or value.get("schema_version") != EXECUTION_UNIT_RECEIPT_VERSION
        or not _is_digest(value.get("receipt_id"))
        or value.get("receipt_id") != _digest(value, "receipt_id")
        or not _is_digest(value.get("unit_id"))
        or not _is_digest(value.get("unit_digest"))
        or not _is_digest(value.get("source_plan_digest"))
        or not isinstance(value.get("local_unit_id"), str)
        or _LOCAL_ID.fullmatch(value["local_unit_id"]) is None
        or not _is_digest(value.get("model_route_id"))
        or not _is_digest(value.get("input_digest"))
        or not _unique_lines(value.get("dependency_receipt_ids"))
        or not all(
            _is_digest(item)
            for item in value.get("dependency_receipt_ids", [])
        )
        or not isinstance(value.get("attempts"), list)
        or not 1 <= len(value["attempts"]) <= MAX_EXECUTION_ATTEMPTS
        or not _line(value.get("output_packet_type"))
        or (
            value.get("output_packet_digest") is not None
            and not _is_digest(value["output_packet_digest"])
        )
        or (
            value.get("verification_assessment_id") is not None
            and not _is_digest(value["verification_assessment_id"])
        )
        or not _line(
            value.get("terminal_work_id"),
            maximum=160,
            optional=True,
        )
        or value.get("terminal_status")
        not in {"completed", "failed", "blocked", "interrupted"}
        or value.get("effect_state")
        not in {"no-writes", "verified-writes", "unknown"}
        or not _timestamp(value.get("issued_at"))
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_RECEIPT_INVALID",
                "path": "$",
                "message": "ExecutionUnitReceipt identity or fields are invalid.",
            }
        )
    producer = value.get("producer") if isinstance(value, dict) else None
    if (
        not isinstance(producer, dict)
        or set(producer) != PRODUCER_FIELDS
        or producer.get("interface") != "codex_app_server"
        or not _line(producer.get("framework_version"), maximum=80)
        or (
            producer.get("runtime_schema_digest") is not None
            and not _is_digest(producer["runtime_schema_digest"])
        )
        or not _line(producer.get("run_id"), maximum=160)
        or not _line(producer.get("observation_id"), maximum=160)
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_RECEIPT_PRODUCER_INVALID",
                "path": "producer",
                "message": "Receipt producer must be the owned bounded Codex Host.",
            }
        )
    if issues:
        return {
            "schema_version": "maestro_execution_unit_receipt_validation_v1",
            "status": "FAIL",
            "execution_status": "INVALID",
            "issues": issues,
            "writes_performed": False,
        }

    assert isinstance(unit, dict)
    assert isinstance(value, dict)
    route = unit["model_route"]
    for field in (
        "unit_id",
        "unit_digest",
        "source_plan_digest",
        "local_unit_id",
    ):
        if value[field] != unit[field]:
            issues.append(
                {
                    "code": "EXECUTION_UNIT_RECEIPT_BINDING_MISMATCH",
                    "path": field,
                    "message": f"Receipt {field} does not match the exact unit.",
                }
            )
    if (
        value["model_route_id"] != route["model_route_id"]
        or value["output_packet_type"] != unit["output_packet_type"]
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_RECEIPT_BINDING_MISMATCH",
                "path": "model_route_id",
                "message": "Receipt model route or output packet type changed.",
            }
        )

    dependency_unit_by_id: dict[str, dict[str, Any]] = {}
    for dependency_unit in dependency_units:
        if (
            not validate_execution_unit(dependency_unit)
            or dependency_unit["unit_id"] in dependency_unit_by_id
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_DEPENDENCY_UNIT_INVALID",
                    "path": "dependency_receipt_ids",
                    "message": "Dependency units must be unique valid units from the same projected plan.",
                }
            )
            continue
        dependency_unit_by_id[dependency_unit["unit_id"]] = (
            dependency_unit
        )
    if set(dependency_unit_by_id) != set(unit["depends_on_unit_ids"]):
        issues.append(
            {
                "code": "EXECUTION_UNIT_DEPENDENCY_UNIT_MISMATCH",
                "path": "dependency_receipt_ids",
                "message": "Receipt validation requires every exact dependency unit in plan order.",
            }
        )

    dependency_by_unit: dict[str, dict[str, Any]] = {}
    for receipt in dependency_receipts:
        if (
            not isinstance(receipt, dict)
            or not _is_digest(receipt.get("receipt_id"))
            or receipt["receipt_id"] != _digest(receipt, "receipt_id")
            or not _is_digest(receipt.get("unit_id"))
            or receipt["unit_id"] in dependency_by_unit
            or receipt["unit_id"] not in dependency_unit_by_id
            or receipt.get("unit_digest")
            != dependency_unit_by_id[receipt["unit_id"]].get(
                "unit_digest"
            )
            or receipt.get("source_plan_digest")
            != dependency_unit_by_id[receipt["unit_id"]].get(
                "source_plan_digest"
            )
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_DEPENDENCY_RECEIPT_INVALID",
                    "path": "dependency_receipt_ids",
                    "message": "Dependency receipts must be unique content-addressed receipts.",
                }
            )
            continue
        dependency_by_unit[receipt["unit_id"]] = receipt
    required_dependency_units = [
        dependency_unit_by_id[unit_id]
        for unit_id in unit["depends_on_unit_ids"]
        if unit_id in dependency_unit_by_id
        and dependency_unit_by_id[unit_id]["host_executable"] is True
    ]
    expected_dependency_ids = [
        dependency_by_unit[unit_id]["receipt_id"]
        for unit_id in [
            dependency["unit_id"]
            for dependency in required_dependency_units
        ]
        if unit_id in dependency_by_unit
    ]
    if (
        set(dependency_by_unit)
        != {
            dependency["unit_id"]
            for dependency in required_dependency_units
        }
        or value["dependency_receipt_ids"] != expected_dependency_ids
        or any(
            receipt.get("terminal_status") != "completed"
            for receipt in dependency_by_unit.values()
        )
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_DEPENDENCY_RECEIPT_MISMATCH",
                "path": "dependency_receipt_ids",
                "message": "Receipt must bind every exact completed dependency in plan order.",
            }
        )

    attempts = value["attempts"]
    if any(not _valid_attempt_shape(item) for item in attempts):
        issues.append(
            {
                "code": "EXECUTION_UNIT_ATTEMPT_INVALID",
                "path": "attempts",
                "message": "Execution attempts do not satisfy the bounded Host contract.",
            }
        )
    else:
        primary = attempts[0]
        if (
            primary["attempt"] != 1
            or primary["followup_of_attempt"] is not None
            or primary["route_kind"] != "primary"
            or primary["requested_class"] != route["selected_class"]
            or primary["requested_model"] != route["selected_model"]
            or primary["requested_reasoning_effort"]
            != route["reasoning_effort"]
            or primary["transition_trigger"] is not None
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_PRIMARY_ATTEMPT_MISMATCH",
                    "path": "attempts[0]",
                    "message": "The first attempt must use the exact typed primary route.",
                }
            )
        provider_reroutes = primary["provider_reroutes"]
        if provider_reroutes:
            fallback = route.get("fallback_route")
            reroute = provider_reroutes[0]
            if (
                len(attempts) != 1
                or not isinstance(fallback, dict)
                or fallback.get("trigger") != "selected-model-unavailable"
                or reroute["from_model"] != route["selected_model"]
                or reroute["to_model"] != fallback["selected_model"]
                or primary["applied_model"] != fallback["selected_model"]
                or "quality" in reroute["reason"].casefold()
            ):
                issues.append(
                    {
                        "code": "EXECUTION_UNIT_PROVIDER_REROUTE_INVALID",
                        "path": "attempts[0].provider_reroutes",
                        "message": "Provider reroute must be the single typed availability fallback.",
                    }
                )
        elif len(attempts) == 1 and primary["applied_model"] not in {
            None,
            primary["requested_model"],
        }:
            issues.append(
                {
                    "code": "EXECUTION_UNIT_APPLIED_MODEL_UNATTESTED",
                    "path": "attempts[0].applied_model",
                    "message": "An applied model change requires the exact provider reroute evidence.",
                }
            )
        if len(attempts) == 2:
            fallback = route.get("fallback_route")
            second = attempts[1]
            if (
                primary["status"] != "model-unavailable"
                or primary["writes_observed"] is not False
                or primary["provider_reroutes"]
                or not isinstance(fallback, dict)
                or second["attempt"] != 2
                or second["followup_of_attempt"] != 1
                or second["route_kind"] != "fallback"
                or second["requested_class"] != fallback["selected_class"]
                or second["requested_model"] != fallback["selected_model"]
                or second["requested_reasoning_effort"]
                != fallback["reasoning_effort"]
                or second["transition_trigger"]
                != "selected-model-unavailable"
                or second["thread_id"] == primary["thread_id"]
                and second["turn_id"] == primary["turn_id"]
            ):
                issues.append(
                    {
                        "code": "EXECUTION_UNIT_FALLBACK_ATTEMPT_INVALID",
                        "path": "attempts[1]",
                        "message": "A second Host attempt is allowed only after an exact no-write model-unavailable failure.",
                    }
                )
        last = attempts[-1]
        expected_terminal = {
            "completed": "completed",
            "failed": "failed",
            "model-unavailable": "failed",
            "blocked": "blocked",
            "interrupted": "interrupted",
        }[last["status"]]
        if value["terminal_status"] != expected_terminal:
            issues.append(
                {
                    "code": "EXECUTION_UNIT_TERMINAL_STATUS_MISMATCH",
                    "path": "terminal_status",
                    "message": "Receipt terminal status must match its last Host attempt.",
                }
            )

    if value["terminal_status"] == "completed":
        if (
            not _is_digest(value.get("output_packet_digest"))
            or not _line(value.get("terminal_work_id"), maximum=160)
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_OUTPUT_REQUIRED",
                    "path": "output_packet_digest",
                    "message": "Completed units require an output Packet and terminal WorkSpan.",
                }
            )
        verifier_receipt = (
            unit.get("executor_id") == "verifier"
            and unit.get("output_packet_type")
            == "VerificationVerdict"
        )
        if verifier_receipt != _is_digest(
            value.get("verification_assessment_id")
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_VERIFICATION_ASSESSMENT_MISMATCH",
                    "path": "verification_assessment_id",
                    "message": "A completed verifier receipt must content-bind exactly one VerificationAssessment; other units must not.",
                }
            )
    elif (
        value.get("output_packet_digest") is not None
        or value.get("terminal_work_id") is not None
        or value.get("verification_assessment_id") is not None
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_NONTERMINAL_OUTPUT_INVALID",
                "path": "output_packet_digest",
                "message": "Unsuccessful units cannot claim completed output evidence.",
            }
        )
    if unit["read_only"] and value["effect_state"] != "no-writes":
        issues.append(
            {
                "code": "EXECUTION_UNIT_READ_ONLY_EFFECT_INVALID",
                "path": "effect_state",
                "message": "Read-only execution units must attest no writes.",
            }
        )
    attempts_write_states = [
        attempt.get("writes_observed")
        for attempt in value["attempts"]
        if isinstance(attempt, dict)
    ]
    if (
        value["effect_state"] == "no-writes"
        and any(state is not False for state in attempts_write_states)
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_EFFECT_STATE_MISMATCH",
                "path": "effect_state",
                "message": "no-writes requires every bounded attempt to observe no writes.",
            }
        )
    if (
        value["effect_state"] == "verified-writes"
        and True not in attempts_write_states
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_EFFECT_STATE_MISMATCH",
                "path": "effect_state",
                "message": "verified-writes requires an attempt with observed writes.",
            }
        )
    if (
        value["terminal_status"] == "completed"
        and unit["mutation_owner"]
        and value["effect_state"] == "unknown"
    ):
        issues.append(
            {
                "code": "EXECUTION_UNIT_COMPLETED_EFFECT_UNKNOWN",
                "path": "effect_state",
                "message": "A completed mutation owner must close its observed effect state.",
            }
        )
    return {
        "schema_version": "maestro_execution_unit_receipt_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "execution_status": (
            value["terminal_status"].upper() if not issues else "INVALID"
        ),
        "issues": issues,
        "writes_performed": False,
    }


def validate_execution_receipt_bundle(
    units: Iterable[Any],
    receipts: Iterable[Any],
    *,
    require_all_host_units: bool = True,
) -> dict[str, Any]:
    """Validate a plan-ordered set of Host receipts and dependency lineage."""

    unit_list = list(units)
    receipt_list = list(receipts)
    issues: list[dict[str, str]] = []
    unit_by_id: dict[str, dict[str, Any]] = {}
    for unit in unit_list:
        if (
            not validate_execution_unit(unit)
            or unit["unit_id"] in unit_by_id
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_BUNDLE_INVALID",
                    "path": "units",
                    "message": "ExecutionUnit bundle members must be valid and unique.",
                }
            )
            continue
        unit_by_id[unit["unit_id"]] = unit
    receipt_by_unit: dict[str, dict[str, Any]] = {}
    receipt_ids: set[str] = set()
    for receipt in receipt_list:
        if (
            not isinstance(receipt, dict)
            or not _is_digest(receipt.get("receipt_id"))
            or receipt["receipt_id"] in receipt_ids
            or not _is_digest(receipt.get("unit_id"))
            or receipt["unit_id"] in receipt_by_unit
            or receipt["unit_id"] not in unit_by_id
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_RECEIPT_BUNDLE_INVALID",
                    "path": "receipts",
                    "message": "Receipt bundle members must be unique and belong to the projected plan.",
                }
            )
            continue
        receipt_ids.add(receipt["receipt_id"])
        receipt_by_unit[receipt["unit_id"]] = receipt
    expected_host_units = {
        unit_id
        for unit_id, unit in unit_by_id.items()
        if unit["host_executable"] is True
    }
    if (
        require_all_host_units
        and set(receipt_by_unit) != expected_host_units
    ) or not set(receipt_by_unit).issubset(expected_host_units):
        issues.append(
            {
                "code": "EXECUTION_UNIT_RECEIPT_COVERAGE_MISMATCH",
                "path": "receipts",
                "message": "Receipt coverage must match the intended Host-executable units exactly.",
            }
        )
    if issues:
        return {
            "schema_version": "maestro_execution_receipt_bundle_validation_v1",
            "status": "FAIL",
            "issues": issues,
            "writes_performed": False,
        }

    validated_receipts: set[str] = set()
    for unit in unit_list:
        unit_id = unit["unit_id"]
        receipt = receipt_by_unit.get(unit_id)
        if receipt is None:
            continue
        missing_dependencies = [
            dependency_id
            for dependency_id in unit["depends_on_unit_ids"]
            if dependency_id not in unit_by_id
        ]
        if missing_dependencies:
            issues.append(
                {
                    "code": "EXECUTION_UNIT_DEPENDENCY_UNIT_MISMATCH",
                    "path": f"receipts.{unit_id}",
                    "message": "Receipt validation is missing one or more exact dependency units.",
                }
            )
            continue
        dependency_units = [
            unit_by_id[dependency_id]
            for dependency_id in unit["depends_on_unit_ids"]
        ]
        dependency_receipts = [
            receipt_by_unit[dependency_id]
            for dependency_id in unit["depends_on_unit_ids"]
            if dependency_id in receipt_by_unit
        ]
        if any(
            dependency["host_executable"] is True
            and dependency["unit_id"] not in validated_receipts
            for dependency in dependency_units
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_RECEIPT_ORDER_INVALID",
                    "path": f"receipts.{unit_id}",
                    "message": "Host receipt dependencies must appear and validate before their consumer.",
                }
            )
            continue
        validation = validate_execution_unit_receipt(
            receipt,
            unit=unit,
            dependency_units=dependency_units,
            dependency_receipts=dependency_receipts,
        )
        if validation["status"] != "PASS":
            issues.extend(validation["issues"])
            continue
        validated_receipts.add(unit_id)
    return {
        "schema_version": "maestro_execution_receipt_bundle_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "writes_performed": False,
    }


def validate_stage_execution_receipts(
    *,
    plan_summary: Any,
    stage_results: Any,
    run_id: str | None = None,
    observation_id: str | None = None,
    work_spans: Any = None,
    expected_framework_version: str | None = None,
) -> dict[str, Any]:
    """Validate receipt coverage and runtime bindings for observed stages.

    This is the shared semantic boundary used by both the mutable observation
    ledger and immutable governance receipts.  JSON Schema intentionally
    covers only shape; content-addressed lineage and cross-object bindings are
    checked here.
    """

    issues: list[dict[str, str]] = []
    if not isinstance(plan_summary, dict) or not isinstance(
        plan_summary.get("assignments"),
        list,
    ):
        return {
            "schema_version": "maestro_stage_execution_receipt_validation_v1",
            "status": "FAIL",
            "issues": [
                {
                    "code": "EXECUTION_UNIT_PLAN_SUMMARY_INVALID",
                    "path": "plan_summary",
                    "message": "Stage receipt validation requires one bounded plan summary.",
                }
            ],
            "writes_performed": False,
        }
    if not validate_plan_execution_units(plan_summary):
        return {
            "schema_version": "maestro_stage_execution_receipt_validation_v1",
            "status": "FAIL",
            "issues": [
                {
                    "code": "EXECUTION_UNIT_PLAN_SUMMARY_INVALID",
                    "path": "plan_summary",
                    "message": "Stage receipt validation requires one exact projected ExecutionUnit plan.",
                }
            ],
            "writes_performed": False,
        }
    if expected_framework_version is not None and (
        not isinstance(expected_framework_version, str)
        or not expected_framework_version.strip()
        or len(expected_framework_version) > 80
        or any(
            character in expected_framework_version
            for character in "\r\n\x00"
        )
    ):
        return {
            "schema_version": "maestro_stage_execution_receipt_validation_v1",
            "status": "FAIL",
            "issues": [
                {
                    "code": "EXECUTION_UNIT_FRAMEWORK_VERSION_INVALID",
                    "path": "expected_framework_version",
                    "message": "Receipt validation requires one bounded framework version when supplied.",
                }
            ],
            "writes_performed": False,
        }
    if stage_results is None:
        stage_results = []
    if not isinstance(stage_results, list):
        return {
            "schema_version": "maestro_stage_execution_receipt_validation_v1",
            "status": "FAIL",
            "issues": [
                {
                    "code": "EXECUTION_UNIT_STAGE_RESULTS_INVALID",
                    "path": "stage_results",
                    "message": "Stage receipt validation requires a result list.",
                }
            ],
            "writes_performed": False,
        }

    assignments = {
        assignment.get("assignment_id"): assignment
        for assignment in plan_summary["assignments"]
        if isinstance(assignment, dict)
        and isinstance(assignment.get("assignment_id"), str)
    }
    units = [
        assignment["execution_unit"]
        for assignment in plan_summary["assignments"]
        if isinstance(assignment, dict)
        and isinstance(assignment.get("execution_unit"), dict)
    ]
    unit_by_assignment = {
        assignment_id: assignment["execution_unit"]
        for assignment_id, assignment in assignments.items()
        if isinstance(assignment.get("execution_unit"), dict)
    }
    results = {
        result.get("assignment_id"): result
        for result in stage_results
        if isinstance(result, dict)
        and isinstance(result.get("assignment_id"), str)
    }
    if len(results) != len(stage_results):
        issues.append(
            {
                "code": "EXECUTION_UNIT_STAGE_RESULTS_INVALID",
                "path": "stage_results",
                "message": "Stage receipt results must have unique Assignment IDs.",
            }
        )

    receipts: list[dict[str, Any]] = []
    receipts_required = plan_summary.get("execution_receipts_required") is True
    if work_spans is None:
        work_span_list: list[Any] = []
    elif isinstance(work_spans, list):
        work_span_list = work_spans
    else:
        issues.append(
            {
                "code": "EXECUTION_UNIT_WORK_SPANS_INVALID",
                "path": "work_spans",
                "message": "Stage receipt validation requires a WorkSpan list.",
            }
        )
        work_span_list = []
    work_by_id = {
        span.get("work_id"): span
        for span in work_span_list
        if isinstance(span, dict)
        and isinstance(span.get("work_id"), str)
    }
    if len(work_by_id) != len(work_span_list):
        issues.append(
            {
                "code": "EXECUTION_UNIT_WORK_SPANS_INVALID",
                "path": "work_spans",
                "message": "Receipt WorkSpans must have unique bounded work IDs.",
            }
        )
    if not set(results).issubset(assignments):
        issues.append(
            {
                "code": "EXECUTION_UNIT_STAGE_RESULTS_INVALID",
                "path": "stage_results",
                "message": "Stage receipt results must belong to the exact projected plan.",
            }
        )
    for assignment_id, result in results.items():
        unit = unit_by_assignment.get(assignment_id)
        receipt = result.get("execution_unit_receipt")
        assessment = result.get("verification_assessment")
        host_executable = (
            isinstance(unit, dict)
            and unit.get("host_executable") is True
        )
        if receipts_required and isinstance(unit, dict):
            expected_source = (
                "codex_app_server"
                if host_executable
                else "deterministic_command"
            )
            if result.get("evidence_source") != expected_source:
                issues.append(
                    {
                        "code": "EXECUTION_UNIT_EVIDENCE_SOURCE_MISMATCH",
                        "path": f"stage_results.{assignment_id}.evidence_source",
                        "message": "Owned execution evidence source must follow the projected ExecutionUnit execution kind.",
                    }
                )
        required = (
            receipts_required
            and host_executable
            and result.get("status") == "completed"
        )
        if required and not isinstance(receipt, dict):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_RECEIPT_REQUIRED",
                    "path": f"stage_results.{assignment_id}.execution_unit_receipt",
                    "message": "A completed owned Codex stage requires its exact ExecutionUnitReceipt.",
                }
            )
            continue
        if assessment is not None and (
            not receipts_required
            or not host_executable
            or not isinstance(receipt, dict)
        ):
            issues.append(
                {
                    "code": "VERIFICATION_ASSESSMENT_RECEIPT_REQUIRED",
                    "path": f"stage_results.{assignment_id}.verification_assessment",
                    "message": "A Host-derived verification assessment requires the exact owned verifier ExecutionUnitReceipt.",
                }
            )
        if receipt is None:
            continue
        if (
            not isinstance(receipt, dict)
            or not receipts_required
            or not isinstance(unit, dict)
            or unit.get("host_executable") is not True
            or result.get("evidence_source") != "codex_app_server"
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_RECEIPT_CONTEXT_INVALID",
                    "path": f"stage_results.{assignment_id}.execution_unit_receipt",
                    "message": "Only an owned Codex result for a Host-executable unit may carry a receipt.",
                }
            )
            continue
        receipts.append(receipt)
        producer = receipt.get("producer")
        producer_fields = producer if isinstance(producer, dict) else {}
        attempts = receipt.get("attempts")
        first_candidate = (
            attempts[0]
            if isinstance(attempts, list) and attempts
            else {}
        )
        last_candidate = (
            attempts[-1]
            if isinstance(attempts, list) and attempts
            else {}
        )
        first = (
            first_candidate
            if isinstance(first_candidate, dict)
            else {}
        )
        last = (
            last_candidate
            if isinstance(last_candidate, dict)
            else {}
        )
        raw_evidence_refs = result.get("evidence_refs", [])
        if not _unique_lines(raw_evidence_refs, maximum=64):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_STAGE_EVIDENCE_INVALID",
                    "path": f"stage_results.{assignment_id}.evidence_refs",
                    "message": "Receipt evidence references must be one bounded unique list.",
                }
            )
            evidence_refs: list[Any] = []
        else:
            evidence_refs = raw_evidence_refs
        input_ref = f"assignment-input:{receipt.get('input_digest', '')}"
        host_ref = (
            "codex-app-server:"
            f"{first.get('thread_id', '')}:{first.get('turn_id', '')}"
        )
        output_ref = (
            f"assignment-packet:{receipt.get('output_packet_digest', '')}"
            if receipt.get("output_packet_digest") is not None
            else None
        )
        if (
            not isinstance(producer, dict)
            or (
                run_id is not None
                and producer_fields.get("run_id") != run_id
            )
            or (
                observation_id is not None
                and producer_fields.get("observation_id")
                != observation_id
            )
            or (
                expected_framework_version is not None
                and producer_fields.get("framework_version")
                != expected_framework_version
            )
            or receipt.get("terminal_status") != result.get("status")
            or first.get("requested_model") != result.get("requested_model")
            or first.get("requested_reasoning_effort")
            != result.get("requested_reasoning_effort")
            or last.get("applied_model") != result.get("actual_model")
            or first.get("provider_reroutes") != result.get("reroutes")
            or last.get("duration_ms") != result.get("duration_ms")
            or last.get("tokens") != result.get("tokens")
            or (
                receipt.get("verification_assessment_id")
                is not None
            )
            != isinstance(assessment, dict)
            or input_ref not in evidence_refs
            or host_ref not in evidence_refs
            or (
                output_ref is not None
                and output_ref not in evidence_refs
            )
            or (
                isinstance(assessment, dict)
                and (
                    assessment.get("packet_digest")
                    != receipt.get("output_packet_digest")
                    or assessment.get("assessment_id")
                    != receipt.get("verification_assessment_id")
                    or (
                        "assignment-packet:"
                        + str(assessment.get("packet_digest", ""))
                    )
                    not in evidence_refs
                )
            )
        ):
            issues.append(
                {
                    "code": "EXECUTION_UNIT_RECEIPT_OBSERVATION_MISMATCH",
                    "path": f"stage_results.{assignment_id}.execution_unit_receipt",
                    "message": "Receipt attempts, evidence, producer, or terminal status do not match the observed stage.",
                }
            )
        terminal_work_id = receipt.get("terminal_work_id")
        if receipt.get("terminal_status") == "completed":
            terminal_work = work_by_id.get(terminal_work_id)
            source_binding = (
                terminal_work.get("source_binding")
                if isinstance(terminal_work, dict)
                else None
            )

            if (
                not isinstance(terminal_work, dict)
                or terminal_work.get("assignment_id") != assignment_id
                or terminal_work.get("source") != "codex_app_server"
                or terminal_work.get("status") != "completed"
                or terminal_work.get("kind") != "orchestration"
                or not isinstance(source_binding, dict)
                or producer_fields.get("runtime_schema_digest")
                != source_binding.get("schema_digest")
            ):
                issues.append(
                    {
                        "code": "EXECUTION_UNIT_TERMINAL_WORK_MISMATCH",
                        "path": f"stage_results.{assignment_id}.execution_unit_receipt.terminal_work_id",
                        "message": "A completed receipt must bind the exact completed root Codex WorkSpan.",
                    }
                )

    bundle = validate_execution_receipt_bundle(
        units,
        receipts,
        require_all_host_units=False,
    )
    if bundle["status"] != "PASS":
        issues.extend(bundle["issues"])
    return {
        "schema_version": "maestro_stage_execution_receipt_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "writes_performed": False,
    }
