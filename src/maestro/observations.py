from __future__ import annotations

import copy
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .errors import MaestroError
from .execution_contracts import normalize_execution_contract
from .execution_units import (
    observation_identity,
    validate_plan_execution_units,
    validate_stage_execution_receipts,
    validate_execution_unit,
    validate_execution_unit_receipt,
)
from .expertise_routing import (
    expertise_routing_summary,
    valid_expertise_routing_summary,
    valid_route_correction_summary,
)
from .model_feedback import validate_verification_assessment
from .project import checkout_id
from .request_lineage import (
    assert_request_lineage_available,
    desktop_root_lineage,
    generated_root_lineage,
    inherited_request_lineage,
    request_lineage_write_lock,
    validate_request_lineage,
)
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    pretty_json,
    read_json,
    safe_target,
    sha256_text,
)
from .work import (
    append_execution_event,
    append_work_span,
    completion_evaluation_for_observation,
    commit_execution_transition,
    ensure_execution_ledger,
    execution_measurements,
    finish_work_span,
    measurement_from_host,
    measurement_from_stage,
    measurement_from_work,
    managed_completion_policy,
    new_work_span,
    new_execution_ledger,
    observation_write_lock,
    producer_binding,
    seal_readiness_error,
    validate_completion_closure,
    validate_completion_policy,
    validate_execution_ledger,
    validate_execution_measurements,
    validate_work_spans,
)

OBSERVATION_VERSION = "maestro_run_observation_v1"
LEGACY_HOST_OBSERVATION_VERSION = "maestro_host_observation_v1"
HOST_OBSERVATION_VERSION = "maestro_host_observation_v2"
EXECUTION_BINDING_VERSION = "maestro_execution_binding_v1"
EXECUTION_FALLBACK_REASONS = {
    "interactive_required",
    "network_required",
    "app_connector_required",
    "capability_unavailable",
}
MAX_TASK_LABEL_LENGTH = 160
MAX_PLAN_ASSIGNMENTS = 5
MAX_INFLIGHT_OBSERVATIONS = 100
MAX_OBSERVATION_FILE_BYTES = 1_000_000
MAX_MODEL_REROUTES = 4
MAX_APP_SERVER_TRACE_BYTES = 4_000_000
MAX_APP_SERVER_TRACE_MESSAGES = 20_000
CORRECTED_ROUTE_RECEIPT_VERSION = (
    "maestro_corrected_route_consumption_v2"
)
STAGE_STATUSES = {
    "completed",
    "failed",
    "blocked",
    "skipped",
    "interrupted",
}
STAGE_EVIDENCE_SOURCES = {
    "codex_app_server",
    "current_host",
    "deterministic_command",
}


def _valid_completion_state(value: dict[str, Any]) -> bool:
    policy = value.get("completion_policy")
    closure = value.get("completion_closure")
    ledger = value.get("execution_ledger")
    if policy is None:
        return closure is None
    if not validate_completion_policy(policy):
        return False
    if "completed_at" not in value:
        return closure is None
    if (
        isinstance(ledger, dict)
        and ledger.get("origin") == "legacy_import"
    ):
        return closure is None
    if (
        not isinstance(closure, dict)
        or not isinstance(ledger, dict)
        or not validate_execution_ledger(ledger)
        or ledger.get("origin") != "native"
        or not ledger.get("events")
        or ledger["events"][-1].get("event_type") != "execution_sealed"
        or ledger["events"][-1].get("payload", {}).get(
            "completion_closure"
        )
        != closure
        or closure.get("pre_seal_ledger", {}).get("revision")
        != ledger["revision"] - 1
    ):
        return False
    pre_seal = copy.deepcopy(ledger)
    pre_seal["events"] = pre_seal["events"][:-1]
    pre_seal["revision"] -= 1
    if (
        sha256_text(canonical_json(pre_seal))
        != closure.get("pre_seal_ledger", {}).get("digest")
    ):
        return False
    return validate_completion_closure(
        closure,
        policy=policy,
        plan_summary=value.get("plan_summary"),
        stage_results=value.get("stage_results"),
        work_spans=value.get("work_spans"),
        receipt_intent=closure.get("receipt_intent_digest"),
    )


def _execution_producer(
    source: str,
    *,
    correlation_id: str | None = None,
    complete: bool = False,
) -> dict[str, Any]:
    if source == "codex_app_server":
        return producer_binding(
            source,
            capability="full_stream",
            event_coverage="complete_stream" if complete else "partial_stream",
            correlation_id=correlation_id,
        )
    if source == "host_adapter":
        return producer_binding(
            source,
            capability="lifecycle_only",
            event_coverage="hook_lifecycle",
            correlation_id=correlation_id,
        )
    if source == "deterministic_command":
        return producer_binding(
            source,
            capability="deterministic",
            event_coverage="unavailable",
            correlation_id=correlation_id,
        )
    if source == "desktop_request":
        return producer_binding(
            source,
            capability="request_metadata",
            event_coverage="request_only",
            correlation_id=correlation_id,
        )
    return producer_binding(
        "current_host",
        capability="current_host",
        event_coverage="unavailable",
        correlation_id=correlation_id,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _observation_id(
    *,
    project_id: str,
    current_checkout: str,
    run_id: str,
) -> str:
    return observation_identity(
        project_id=project_id,
        checkout_id=current_checkout,
        run_id=run_id,
    )


def observation_id_for_run(
    repo_path: str | Path,
    *,
    run_id: str,
) -> str:
    """Return the deterministic observation ID for one project checkout run."""

    repo = ensure_repo(repo_path)
    project = read_json(safe_target(repo, ".maestro/project.json"))
    project_id = project.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise MaestroError(
            "PROJECT_STATE_INVALID",
            "project_id must be a non-empty string.",
        )
    if not isinstance(run_id, str) or not run_id.strip():
        raise MaestroError(
            "RUN_OBSERVATION_ID_INVALID",
            "run-id must be a non-empty string.",
        )
    return _observation_id(
        project_id=project_id,
        current_checkout=checkout_id(repo),
        run_id=run_id,
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _task_label(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_TASK_LABEL_LENGTH
        or any(character in value for character in "\r\n\x00")
    ):
        raise MaestroError(
            "RUN_OBSERVATION_LABEL_INVALID",
            "task-label must be a single non-empty line of at most "
            f"{MAX_TASK_LABEL_LENGTH} characters.",
        )
    return value.strip()


def _bounded_line(value: Any, *, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(character in value for character in "\r\n\x00")
    ):
        raise MaestroError(
            "HOST_OBSERVATION_INVALID",
            f"{field} must be one non-empty line of at most {maximum} characters.",
        )
    return value.strip()


def _valid_token_summary(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or "total" not in value:
        return False
    if set(value) - {
        "input",
        "output",
        "cached",
        "reasoning",
        "total",
        "parent_context_total",
        "total_system",
    }:
        return False
    return all(
        item is None
        or (
            isinstance(item, int)
            and not isinstance(item, bool)
            and item >= 0
        )
        for item in value.values()
    )


def _valid_model(value: Any) -> bool:
    return (
        value is None
        or (
            isinstance(value, str)
            and bool(value.strip())
            and len(value) <= 128
            and not any(character in value for character in "\r\n\x00")
        )
    )


def _valid_reasoning_effort(value: Any) -> bool:
    return (
        value is None
        or (
            isinstance(value, str)
            and bool(value.strip())
            and len(value) <= 40
            and not any(character in value for character in "\r\n\x00")
        )
    )


def _valid_execution_binding(value: Any) -> bool:
    """Validate the durable execution-path assertion for a managed run."""

    if value is None:
        return True
    if not isinstance(value, dict) or value.get("schema_version") != EXECUTION_BINDING_VERSION:
        return False
    mode = value.get("mode")
    if mode == "maestro_owned_codex_app_server":
        return set(value) == {"schema_version", "mode"}
    if mode == "desktop_request":
        return set(value) == {"schema_version", "mode"}
    if mode != "explicit_fallback" or set(value) != {
        "schema_version",
        "mode",
        "reason",
        "evidence",
    }:
        return False
    return (
        value.get("reason") in EXECUTION_FALLBACK_REASONS
        and isinstance(value.get("evidence"), str)
        and bool(value["evidence"].strip())
        and len(value["evidence"]) <= 240
        and not any(character in value["evidence"] for character in "\r\n\x00")
    )


def record_execution_fallback(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    reason: str,
    evidence: str,
) -> dict[str, Any]:
    """Explicitly move a Desktop-orchestrated run onto the current Host."""

    repo = ensure_repo(repo_path)
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    if value.get("run_id") != run_id or "completed_at" in value:
        raise MaestroError(
            "RUN_EXECUTION_FALLBACK_INVALID",
            "Fallback requires the matching unfinished run observation.",
        )
    binding = {
        "schema_version": EXECUTION_BINDING_VERSION,
        "mode": "explicit_fallback",
        "reason": reason,
        "evidence": evidence,
    }
    if not _valid_execution_binding(binding):
        raise MaestroError(
            "RUN_EXECUTION_FALLBACK_INVALID",
            "Fallback requires a supported reason and one bounded evidence line.",
        )
    existing = value.get("execution_binding")
    if existing == binding:
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "observe-fallback",
            "status": "already_attached",
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation_id,
            "execution_binding": binding,
            "writes_performed": False,
        }
    if not (
        existing is None
        or (
            isinstance(existing, dict)
            and existing.get("mode") == "desktop_request"
        )
    ):
        raise MaestroError(
            "RUN_EXECUTION_FALLBACK_CONFLICT",
            "Only an unfinished Desktop request may change to explicit fallback.",
        )
    if any(
        isinstance(item, dict)
        and item.get("evidence_source") == "current_host"
        for item in value.get("stage_results", [])
    ):
        raise MaestroError(
            "RUN_EXECUTION_FALLBACK_INVALID",
            "Fallback must be recorded before the first current-Host stage.",
        )
    before = copy.deepcopy(value)
    recorded_at = _timestamp(_utc_now())
    value["execution_binding"] = binding
    value["fallback_recorded_at"] = recorded_at
    commit_execution_transition(
        target,
        before=before,
        after=value,
        event_type="execution_binding_changed",
        idempotency_key="execution:binding:explicit_fallback",
        producer=producer_binding(
            "maestro_core",
            capability="lifecycle_only",
            event_coverage="partial_stream",
        ),
        payload={"execution_binding": binding},
        measurement=None,
        recorded_at=recorded_at,
    )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-fallback",
        "status": "attached",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "execution_binding": binding,
        "writes_performed": True,
    }


def claim_maestro_owned_codex_execution(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Claim a fact-free Desktop intake for Maestro-owned App Server execution."""

    repo = ensure_repo(repo_path)
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    if value.get("run_id") != run_id or "completed_at" in value:
        raise MaestroError(
            "RUN_EXECUTION_BINDING_INVALID",
            "Owned execution requires the matching unfinished observation.",
        )
    existing = value.get("execution_binding")
    existing_mode = (
        existing.get("mode") if isinstance(existing, dict) else None
    )
    plan_summary = value.get("plan_summary")
    if existing_mode == "maestro_owned_codex_app_server":
        if (
            not isinstance(plan_summary, dict)
            or plan_summary.get("execution_receipts_required") is not True
            or not validate_plan_execution_units(plan_summary)
        ):
            raise MaestroError(
                "RUN_EXECUTION_BINDING_INVALID",
                "Owned execution must retain its exact receipt-required ExecutionUnit plan.",
            )
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "observe-claim-owned-codex",
            "status": "already_owned",
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation_id,
            "execution_binding": existing,
            "writes_performed": False,
        }
    if existing_mode == "explicit_fallback":
        raise MaestroError(
            "RUN_EXECUTION_BINDING_CONFLICT",
            "An explicit current-Host fallback cannot later launch an owned Codex App Server Assignment.",
        )
    if existing_mode not in {None, "desktop_request"}:
        raise MaestroError(
            "RUN_EXECUTION_BINDING_CONFLICT",
            "Only a fact-free Desktop request may become Maestro-owned execution.",
        )
    if (
        not isinstance(plan_summary, dict)
        or not validate_plan_execution_units(plan_summary)
        or value.get("stage_results")
        or value.get("work_spans")
        or value.get("completion_closure") is not None
    ):
        raise MaestroError(
            "RUN_EXECUTION_BINDING_CONFLICT",
            "Owned execution must be claimed before the first execution fact on an exact ExecutionUnit plan.",
        )
    binding = {
        "schema_version": EXECUTION_BINDING_VERSION,
        "mode": "maestro_owned_codex_app_server",
    }
    before = copy.deepcopy(value)
    updated_plan = copy.deepcopy(plan_summary)
    updated_plan["execution_receipts_required"] = True
    value["plan_summary"] = updated_plan
    value["execution_binding"] = binding
    recorded_at = _timestamp(_utc_now())
    committed = commit_execution_transition(
        target,
        before=before,
        after=value,
        event_type="execution_binding_changed",
        idempotency_key=(
            "execution:binding:maestro_owned_codex_app_server"
        ),
        producer=producer_binding(
            "maestro_core",
            capability="lifecycle_only",
            event_coverage="partial_stream",
        ),
        payload={
            "execution_binding": binding,
            "execution_receipts_required": True,
        },
        measurement=None,
        recorded_at=recorded_at,
    )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-claim-owned-codex",
        "status": "owned",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "execution_binding": binding,
        "writes_performed": committed != before,
    }


def _valid_legacy_host_observation(value: dict[str, Any]) -> bool:
    if set(value) != {
        "schema_version",
        "source",
        "quality",
        "correlation_id",
        "actual_model",
        "tokens",
        "observed_at",
    }:
        return False
    actual_model = value.get("actual_model")
    tokens = value.get("tokens")
    return (
        value.get("schema_version") == LEGACY_HOST_OBSERVATION_VERSION
        and _valid_host_observation_identity(value)
        and _valid_model(actual_model)
        and _valid_token_summary(tokens)
        and (actual_model is not None or tokens is not None)
        and _parse_timestamp(value.get("observed_at")) is not None
    )


def _valid_host_observation_identity(value: dict[str, Any]) -> bool:
    return (
        isinstance(value.get("source"), str)
        and bool(value["source"].strip())
        and len(value["source"]) <= 80
        and not any(character in value["source"] for character in "\r\n\x00")
        and value.get("quality") in {"host_reported", "host_delta"}
        and isinstance(value.get("correlation_id"), str)
        and bool(value["correlation_id"].strip())
        and len(value["correlation_id"]) <= 160
        and not any(
            character in value["correlation_id"]
            for character in "\r\n\x00"
        )
    )


def _valid_model_reroutes(
    value: Any,
    *,
    requested_model: str | None,
    applied_model: str | None,
) -> bool:
    if (
        not isinstance(value, list)
        or len(value) > MAX_MODEL_REROUTES
    ):
        return False
    previous = requested_model
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"from_model", "to_model", "reason"}
            or not _valid_model(item.get("from_model"))
            or not _valid_model(item.get("to_model"))
            or item.get("from_model") is None
            or item.get("to_model") is None
            or not isinstance(item.get("reason"), str)
            or not item["reason"].strip()
            or len(item["reason"]) > 240
            or any(character in item["reason"] for character in "\r\n\x00")
            or item["from_model"] != previous
        ):
            return False
        previous = item["to_model"]
    return previous == applied_model


def _valid_host_observation(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") == LEGACY_HOST_OBSERVATION_VERSION:
        return _valid_legacy_host_observation(value)
    required_fields = {
        "schema_version",
        "source",
        "quality",
        "correlation_id",
        "requested_model",
        "applied_model",
        "model_event_evidence",
        "reroutes",
        "tokens",
        "observed_at",
    }
    optional_fields = {
        "requested_reasoning_effort",
        "reasoning_effort_evidence",
        "duration_ms",
    }
    if (
        not required_fields.issubset(value)
        or set(value) - required_fields - optional_fields
    ):
        return False
    requested_model = value.get("requested_model")
    applied_model = value.get("applied_model")
    requested_reasoning_effort = value.get(
        "requested_reasoning_effort",
    )
    reasoning_effort_evidence = value.get(
        "reasoning_effort_evidence",
        "unavailable",
    )
    model_event_evidence = value.get("model_event_evidence")
    reroutes = value.get("reroutes")
    tokens = value.get("tokens")
    duration_ms = value.get("duration_ms")
    if not (
        value.get("schema_version") == HOST_OBSERVATION_VERSION
        and _valid_host_observation_identity(value)
        and _valid_model(requested_model)
        and _valid_model(applied_model)
        and _valid_reasoning_effort(requested_reasoning_effort)
        and reasoning_effort_evidence in {
            "unavailable",
            "host_request",
        }
        and model_event_evidence
        in {"unavailable", "request_only", "complete"}
        and _valid_token_summary(tokens)
        and (
            duration_ms is None
            or (
                isinstance(duration_ms, (int, float))
                and not isinstance(duration_ms, bool)
                and math.isfinite(duration_ms)
                and duration_ms >= 0
            )
        )
        and (
            requested_model is not None
            or applied_model is not None
            or tokens is not None
            or duration_ms is not None
        )
        and _parse_timestamp(value.get("observed_at")) is not None
    ):
        return False
    if (
        requested_reasoning_effort is None
        and reasoning_effort_evidence != "unavailable"
    ) or (
        requested_reasoning_effort is not None
        and reasoning_effort_evidence != "host_request"
    ):
        return False
    if model_event_evidence == "unavailable":
        return applied_model is None and reroutes == []
    if model_event_evidence == "request_only":
        return (
            requested_model is not None
            and applied_model is None
            and reroutes == []
        )
    return (
        requested_model is not None
        and applied_model is not None
        and _valid_model_reroutes(
            reroutes,
            requested_model=requested_model,
            applied_model=applied_model,
        )
    )


def _read_observation_file(path: Path) -> dict[str, Any]:
    try:
        valid = (
            not path.is_symlink()
            and path.is_file()
            and path.stat().st_size <= MAX_OBSERVATION_FILE_BYTES
        )
    except OSError:
        valid = False
    if not valid:
        raise MaestroError(
            "RUN_OBSERVATION_INVALID",
            "The observation file is missing, unsafe, or exceeds its size limit.",
        )
    value = read_json(path)
    if not isinstance(value, dict):
        raise MaestroError(
            "RUN_OBSERVATION_INVALID",
            "The observation file must contain one object.",
        )
    return value


def _assignment_plan_summary(
    assignment: dict[str, Any],
    *,
    execution_unit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route = assignment["model_route"]
    summary = {
        "assignment_id": assignment["assignment_id"],
        "kind": assignment["kind"],
        "executor_id": assignment["executor_id"],
        "mutation_owner": assignment["mutation_owner"],
        "read_only": assignment["read_only"],
        "may_spawn": assignment["may_spawn"],
        "max_children": assignment["max_children"],
        "depends_on": list(assignment["depends_on"]),
        "lens_ids": list(assignment.get("lens_ids", [])),
        "planned_model": route["selected_model"],
        "reasoning_effort": route["reasoning_effort"],
        "expertise_pack_ids": list(
            assignment.get("expertise_pack_ids", [])
        ),
        "decision_guide_ids": list(
            assignment.get("decision_guide_ids", [])
        ),
    }
    if route.get("schema_version") == "maestro_stage_model_route_v1":
        summary.update(
            {
                "model_route_id": route["model_route_id"],
                "execution_unit_id": route["execution_unit_id"],
                "stage_kind": route["stage_kind"],
                "task_class": route["task_class"],
                "execution_kind": route["execution_kind"],
                "quality_profile": route["quality_profile"],
                "selected_class": route["selected_class"],
                "quality_floor": copy.deepcopy(route["quality_floor"]),
                "fallback_route": copy.deepcopy(route["fallback_route"]),
            }
        )
    if execution_unit is not None:
        summary["execution_unit"] = copy.deepcopy(execution_unit)
    return summary


def _plan_summary(repo: Path, plan_path: str | Path | None) -> dict[str, Any] | None:
    if plan_path is None:
        return None
    path = Path(plan_path).expanduser().resolve()
    plan = read_json(path)
    validation = normalize_execution_contract(plan, repo_path=repo)
    plan = validation.get("route_plan")
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(
            "RUN_OBSERVATION_PLAN_INVALID",
            f"{first['code']}: {first['message']}",
        )
    if not isinstance(plan, dict):
        raise MaestroError(
            "RUN_OBSERVATION_PLAN_INVALID",
            "The execution contract has no route plan.",
        )
    assignments = plan.get("assignments", [])
    if not isinstance(assignments, list) or len(assignments) > MAX_PLAN_ASSIGNMENTS:
        raise MaestroError(
            "RUN_OBSERVATION_PLAN_INVALID",
            "A monitored plan may contain at most five Assignments.",
        )
    expertise = plan.get("expertise")
    research = (
        expertise.get("research_requirement")
        if isinstance(expertise, dict)
        else None
    )
    common_units = {
        unit["local_unit_id"]: unit
        for unit in validation.get("execution_units", [])
        if isinstance(unit, dict)
        and isinstance(unit.get("local_unit_id"), str)
    }
    summary = {
        "schema_version": "maestro_plan_summary_v1",
        "plan_id": plan["plan_id"],
        "execution_contract": {
            "kind": (
                "decision-enactment"
                if validation.get("execution_plan_id") is not None
                else "direct-route"
            ),
            "execution_plan_id": validation.get("execution_plan_id"),
            "decision_plan_id": validation.get("decision_plan_id"),
            "decision_bundle_digest": validation.get(
                "decision_bundle_digest"
            ),
        },
        "intent": plan["intent"],
        "department": plan["department"],
        "risk": plan["risk"],
        "depth": plan["depth"],
        "selected_lenses": list(plan["selected_lenses"]),
        "assignments": [
            _assignment_plan_summary(
                assignment,
                execution_unit=common_units.get(
                    assignment["assignment_id"]
                ),
            )
            for assignment in assignments
        ],
        "research": (
            {
                "mode": research["mode"],
                "gate": research["gate"],
            }
            if isinstance(research, dict)
            else {"mode": "reuse", "gate": "not-required"}
        ),
    }
    summary["expertise_routing"] = expertise_routing_summary(
        expertise
        if isinstance(expertise, dict)
        else {
            "selected_pack_ids": [],
            "selection_trace": {},
            "warnings": [],
        }
    )
    design_assurance = plan.get("design_assurance")
    if isinstance(design_assurance, dict):
        summary["design_assurance"] = {
            "profile_id": design_assurance.get("profile_id"),
            "mode": design_assurance.get("mode"),
            "mutation_gate": design_assurance.get("mutation_gate"),
            "verification_gate": design_assurance.get(
                "verification_gate"
            ),
        }
    route_hints = (
        expertise.get("route_hints")
        if isinstance(expertise, dict)
        else None
    )
    summary["route_correction"] = (
        {
            "prior_plan_id": route_hints["prior_plan_id"],
            "prior_source_route_digest": route_hints[
                "prior_source_route_digest"
            ],
        }
        if isinstance(route_hints, dict)
        and route_hints.get("route_attempt") == 2
        else None
    )
    return summary


def _claim_corrected_route(
    repo: Path,
    plan_summary: dict[str, Any] | None,
    *,
    observation_id: str,
) -> tuple[Path, dict[str, Any]] | None:
    if not isinstance(plan_summary, dict):
        return None
    correction = plan_summary.get("route_correction")
    if not isinstance(correction, dict):
        return None
    prior_plan_id = correction.get("prior_plan_id")
    prior_digest = correction.get("prior_source_route_digest")
    corrected_plan_id = plan_summary.get("plan_id")
    if not all(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
        for value in (prior_plan_id, prior_digest, corrected_plan_id)
    ):
        raise MaestroError(
            "EXPERTISE_CORRECTED_ROUTE_RECEIPT_INVALID",
            "Corrected route lineage cannot be consumed.",
        )
    receipt = {
        "schema_version": CORRECTED_ROUTE_RECEIPT_VERSION,
        "prior_plan_id": prior_plan_id,
        "prior_source_route_digest": prior_digest,
        "corrected_plan_id": corrected_plan_id,
        "consumer_observation_id": observation_id,
    }
    target = safe_target(
        repo,
        f".maestro/state/route-corrections/{prior_plan_id}.json",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    content = pretty_json(receipt).encode("utf-8")
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        existing = read_json(target)
        legacy_same_plan = (
            existing.get("schema_version")
            == "maestro_corrected_route_consumption_v1"
            and existing.get("prior_plan_id") == prior_plan_id
            and existing.get("prior_source_route_digest") == prior_digest
            and existing.get("corrected_plan_id") == corrected_plan_id
        )
        if legacy_same_plan:
            observation_target = safe_target(
                repo,
                f".maestro/state/inflight/{observation_id}.json",
            )
            observation = (
                _read_observation_file(observation_target)
                if observation_target.is_file()
                and not observation_target.is_symlink()
                else {}
            )
            observed_plan = observation.get("plan_summary")
            if (
                not isinstance(observed_plan, dict)
                or observed_plan.get("plan_id") != corrected_plan_id
            ):
                raise MaestroError(
                    "EXPERTISE_CORRECTED_ROUTE_ALREADY_CONSUMED",
                    (
                        "The first route has a legacy corrected-route "
                        "receipt without proof that this observation owns it."
                    ),
                )
            atomic_write(target, pretty_json(receipt).encode("utf-8"))
            return None
        if existing != receipt:
            raise MaestroError(
                "EXPERTISE_CORRECTED_ROUTE_ALREADY_CONSUMED",
                (
                    "The first route already has a different corrected "
                    "execution plan."
                ),
            )
        return None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target, receipt


def _rollback_corrected_route_claim(
    claim: tuple[Path, dict[str, Any]] | None,
    *,
    observation_target: Path,
) -> None:
    if claim is None:
        return
    target, receipt = claim
    if observation_target.is_file() and not observation_target.is_symlink():
        try:
            observation = read_json(observation_target)
        except MaestroError:
            observation = {}
        summary = observation.get("plan_summary")
        if (
            isinstance(summary, dict)
            and summary.get("plan_id") == receipt["corrected_plan_id"]
        ):
            return
    try:
        if read_json(target) == receipt:
            target.unlink(missing_ok=True)
    except MaestroError:
        return


def start_run_observation(
    repo_path: str | Path,
    *,
    run_id: str,
    task_label: str,
    plan_path: str | Path | None = None,
    execution_binding: dict[str, Any] | None = None,
    request_key: str | None = None,
    request_lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    project = read_json(safe_target(repo, ".maestro/project.json"))
    project_id = project.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise MaestroError(
            "PROJECT_STATE_INVALID",
            "project_id must be a non-empty string.",
        )
    if not isinstance(run_id, str) or not run_id.strip():
        raise MaestroError(
            "RUN_OBSERVATION_ID_INVALID",
            "run-id must be a non-empty string.",
        )
    label = _task_label(task_label)
    current_checkout = checkout_id(repo)
    if request_key is not None and request_lineage is not None:
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "Provide either request-key or inherited request lineage, not both.",
        )
    if request_key is None and request_lineage is None:
        raise MaestroError(
            "REQUEST_LINEAGE_UNAVAILABLE",
            (
                "A root observation requires an explicit request-key; "
                "a detached child or retry requires inherited request lineage."
            ),
        )
    lineage = (
        request_lineage
        if request_lineage is not None
        else generated_root_lineage(
            project_id=project_id,
            current_checkout=current_checkout,
            run_id=run_id,
            request_key=request_key,
        )
    )
    if not validate_request_lineage(lineage, current_run_id=run_id):
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "The request lineage does not match the run being started.",
        )
    observation_id = _observation_id(
        project_id=project_id,
        current_checkout=current_checkout,
        run_id=run_id,
    )
    relative_path = f".maestro/state/inflight/{observation_id}.json"
    target = safe_target(repo, relative_path)
    now = _timestamp(_utc_now())
    plan_summary = _plan_summary(repo, plan_path)
    if (
        isinstance(plan_summary, dict)
        and isinstance(execution_binding, dict)
        and execution_binding.get("mode")
        == "maestro_owned_codex_app_server"
    ):
        plan_summary["execution_receipts_required"] = True
    value = {
        "schema_version": OBSERVATION_VERSION,
        "observation_id": observation_id,
        "project_id": project_id,
        "checkout_id": current_checkout,
        "run_id": run_id,
        "task_label": label,
        "started_at": now,
        "plan_summary": plan_summary,
        "request_lineage": lineage,
    }
    if plan_summary is not None:
        value["plan_attached_at"] = now
        value["completion_policy"] = managed_completion_policy()
    if execution_binding is not None:
        if not _valid_execution_binding(execution_binding):
            raise MaestroError(
                "RUN_EXECUTION_BINDING_INVALID",
                "execution binding does not satisfy the managed execution contract.",
            )
        value["execution_binding"] = execution_binding
    ledger = new_execution_ledger(
        observation_id=observation_id,
        run_id=run_id,
        recorded_at=now,
        payload={
            "task_label": label,
            "started_at": now,
            "request_lineage": lineage,
        },
    )
    if plan_summary is not None:
        ledger, _ = append_execution_event(
            ledger,
            event_type="plan_attached",
            idempotency_key="plan:attached",
            producer=producer_binding(
                "maestro_core",
                capability="lifecycle_only",
                event_coverage="partial_stream",
            ),
            payload={
                "plan_summary": plan_summary,
                "completion_policy": value["completion_policy"],
            },
            measurement=None,
            recorded_at=now,
        )
    if execution_binding is not None:
        ledger, _ = append_execution_event(
            ledger,
            event_type="execution_binding_changed",
            idempotency_key=(
                f"execution:binding:{execution_binding['mode']}"
            ),
            producer=producer_binding(
                "maestro_core",
                capability="lifecycle_only",
                event_coverage="partial_stream",
            ),
            payload={"execution_binding": execution_binding},
            measurement=None,
            recorded_at=now,
        )
    value["execution_ledger"] = ledger
    if target.exists() or target.is_symlink():
        with request_lineage_write_lock(repo):
            assert_request_lineage_available(
                repo,
                observation_id=observation_id,
                run_id=run_id,
                lineage=lineage,
            )
        existing = _read_observation_file(target)
        if existing.get("request_lineage") != lineage:
            raise MaestroError(
                "RUN_REQUEST_LINEAGE_CONFLICT",
                "The run ID already has a different immutable request lineage.",
            )
        runtime_fields = {
            "started_at",
            "plan_attached_at",
            "host_observation",
            "stage_results",
            "work_spans",
            "completed_at",
            "duration_ms",
            "fallback_recorded_at",
            "execution_ledger",
            "completion_closure",
        }
        comparable = {
            key: item
            for key, item in existing.items()
            if key not in runtime_fields
        }
        expected = {
            key: item
            for key, item in value.items()
            if key not in runtime_fields
        }
        if (
            execution_binding is not None
            and existing.get("execution_binding") is None
        ):
            comparable_without_binding = {
                key: item
                for key, item in comparable.items()
                if key != "execution_binding"
            }
            expected_without_binding = {
                key: item
                for key, item in expected.items()
                if key != "execution_binding"
            }
            if comparable_without_binding == expected_without_binding:
                before = copy.deepcopy(existing)
                existing["execution_binding"] = execution_binding
                claim = _claim_corrected_route(
                    repo,
                    plan_summary,
                    observation_id=observation_id,
                )
                try:
                    commit_execution_transition(
                        target,
                        before=before,
                        after=existing,
                        event_type="execution_binding_changed",
                        idempotency_key=(
                            f"execution:binding:{execution_binding['mode']}"
                        ),
                        producer=producer_binding(
                            "maestro_core",
                            capability="lifecycle_only",
                            event_coverage="partial_stream",
                        ),
                        payload={"execution_binding": execution_binding},
                        measurement=None,
                        recorded_at=now,
                    )
                except Exception:
                    _rollback_corrected_route_claim(
                        claim,
                        observation_target=target,
                    )
                    raise
                return {
                    "schema_version": "maestro_command_result_v1",
                    "command": "observe-start",
                    "status": "fallback_attached",
                    "repo_root": str(repo),
                    "run_id": run_id,
                    "observation_id": observation_id,
                    "observation_path": relative_path,
                    "request_lineage": lineage,
                    "writes_performed": True,
                }
        if (
            isinstance(execution_binding, dict)
            and execution_binding.get("mode") == "desktop_request"
            and isinstance(existing.get("execution_binding"), dict)
            and existing["execution_binding"].get("mode") == "explicit_fallback"
        ):
            comparable_without_binding = {
                key: item
                for key, item in comparable.items()
                if key != "execution_binding"
            }
            expected_without_binding = {
                key: item
                for key, item in expected.items()
                if key != "execution_binding"
            }
            if comparable_without_binding == expected_without_binding:
                claim = _claim_corrected_route(
                    repo,
                    plan_summary,
                    observation_id=observation_id,
                )
                return {
                    "schema_version": "maestro_command_result_v1",
                    "command": "observe-start",
                    "status": "already_started",
                    "repo_root": str(repo),
                    "run_id": run_id,
                    "observation_id": observation_id,
                    "observation_path": relative_path,
                    "request_lineage": lineage,
                    "writes_performed": claim is not None,
                }
        if comparable != expected:
            raise MaestroError(
                "RUN_OBSERVATION_CONFLICT",
                "The run ID already has a different in-flight observation.",
            )
        claim = _claim_corrected_route(
            repo,
            plan_summary,
            observation_id=observation_id,
        )
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "observe-start",
            "status": "already_started",
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation_id,
            "observation_path": relative_path,
            "request_lineage": lineage,
            "writes_performed": claim is not None,
        }
    claim = _claim_corrected_route(
        repo,
        plan_summary,
        observation_id=observation_id,
    )
    try:
        with request_lineage_write_lock(repo):
            assert_request_lineage_available(
                repo,
                observation_id=observation_id,
                run_id=run_id,
                lineage=lineage,
            )
            with observation_write_lock(target):
                if target.exists() or target.is_symlink():
                    raise MaestroError(
                        "RUN_OBSERVATION_CONFLICT",
                        "The run observation appeared concurrently.",
                    )
                atomic_write(target, pretty_json(value).encode("utf-8"))
    except Exception:
        _rollback_corrected_route_claim(
            claim,
            observation_target=target,
        )
        raise
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-start",
        "status": "started",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "observation_path": relative_path,
        "request_lineage": lineage,
        "writes_performed": True,
    }


def start_child_run_observation(
    repo_path: str | Path,
    *,
    run_id: str,
    task_label: str,
    parent_observation_id: str,
    parent_run_id: str,
    relation: str,
    plan_path: str | Path | None = None,
    execution_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a distinct run that remains inside one existing request."""

    repo = ensure_repo(repo_path)
    if (
        not isinstance(parent_observation_id, str)
        or len(parent_observation_id) != 32
        or any(
            character not in "0123456789abcdef"
            for character in parent_observation_id
        )
    ):
        raise MaestroError(
            "REQUEST_LINEAGE_PARENT_NOT_FOUND",
            "parent-observation must be an exact 32-character observation ID.",
        )
    parent_target = safe_target(
        repo,
        f".maestro/state/inflight/{parent_observation_id}.json",
    )
    if not parent_target.is_file() or parent_target.is_symlink():
        raise MaestroError(
            "REQUEST_LINEAGE_PARENT_NOT_FOUND",
            "The exact parent observation could not be found.",
        )
    parent = _read_observation_file(parent_target)
    project = read_json(safe_target(repo, ".maestro/project.json"))
    if (
        parent.get("schema_version") != OBSERVATION_VERSION
        or parent.get("observation_id") != parent_observation_id
        or parent.get("project_id") != project.get("project_id")
        or parent.get("checkout_id") != checkout_id(repo)
        or parent.get("run_id") != parent_run_id
    ):
        raise MaestroError(
            "REQUEST_LINEAGE_PARENT_NOT_FOUND",
            "The parent observation does not match this project and run.",
        )
    lineage = inherited_request_lineage(
        parent.get("request_lineage"),
        parent_run_id=parent_run_id,
        parent_observation_id=parent_observation_id,
        child_run_id=run_id,
        relation=relation,
    )
    result = start_run_observation(
        repo,
        run_id=run_id,
        task_label=task_label,
        plan_path=plan_path,
        execution_binding=execution_binding,
        request_lineage=lineage,
    )
    return {
        **result,
        "command": "observe-child",
        "parent_observation_id": parent_observation_id,
        "parent_run_id": parent_run_id,
        "relation": relation,
    }


def attach_run_plan(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    plan_path: str | Path,
) -> dict[str, Any]:
    """Attach one validated route plan after request observation has started."""

    repo = ensure_repo(repo_path)
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    if value.get("run_id") != run_id or "completed_at" in value:
        raise MaestroError(
            "RUN_OBSERVATION_CONFLICT",
            "A plan can be attached only to the matching unfinished run.",
        )
    plan_summary = _plan_summary(repo, plan_path)
    assert plan_summary is not None
    if (
        isinstance(value.get("execution_binding"), dict)
        and value["execution_binding"].get("mode")
        == "maestro_owned_codex_app_server"
    ):
        plan_summary["execution_receipts_required"] = True
    existing = value.get("plan_summary")
    if existing is not None:
        if existing != plan_summary:
            raise MaestroError(
                "RUN_OBSERVATION_PLAN_CONFLICT",
                "The run already contains a different validated plan.",
            )
        claim = _claim_corrected_route(
            repo,
            plan_summary,
            observation_id=observation_id,
        )
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "observe-plan",
            "status": "already_attached",
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation_id,
            "plan_id": plan_summary["plan_id"],
            "writes_performed": claim is not None,
        }
    if value.get("stage_results"):
        raise MaestroError(
            "RUN_OBSERVATION_PLAN_CONFLICT",
            "A plan cannot be attached after stage evidence exists.",
        )
    before = copy.deepcopy(value)
    recorded_at = _timestamp(_utc_now())
    value["plan_summary"] = plan_summary
    value["plan_attached_at"] = recorded_at
    value["completion_policy"] = managed_completion_policy()
    claim = _claim_corrected_route(
        repo,
        plan_summary,
        observation_id=observation_id,
    )
    try:
        commit_execution_transition(
            target,
            before=before,
            after=value,
            event_type="plan_attached",
            idempotency_key="plan:attached",
            producer=producer_binding(
                "maestro_core",
                capability="lifecycle_only",
                event_coverage="partial_stream",
            ),
            payload={
                "plan_summary": plan_summary,
                "completion_policy": value["completion_policy"],
            },
            measurement=None,
            recorded_at=recorded_at,
        )
    except Exception:
        _rollback_corrected_route_claim(
            claim,
            observation_target=target,
        )
        raise
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-plan",
        "status": "attached",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "plan_id": plan_summary["plan_id"],
        "writes_performed": True,
    }


def _valid_stage_result(
    value: Any,
    *,
    plan_summary: dict[str, Any],
    prior_results: dict[str, dict[str, Any]] | None = None,
) -> bool:
    required = {
        "assignment_id",
        "status",
        "requested_model",
        "requested_reasoning_effort",
        "actual_model",
        "model_evidence",
        "reroutes",
        "duration_ms",
        "tokens",
        "evidence_refs",
        "evidence_source",
        "observed_at",
    }
    route_identity_fields = {"model_route_id", "execution_unit_id"}
    optional_fields = {
        "verification_assessment",
        "execution_unit_receipt",
    }
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or set(value) - required - route_identity_fields - optional_fields
        or bool(set(value) & route_identity_fields)
        != route_identity_fields.issubset(value)
    ):
        return False
    assignments = {
        assignment["assignment_id"]: assignment
        for assignment in plan_summary["assignments"]
    }
    actual_model = value.get("actual_model")
    requested_model = value.get("requested_model")
    requested_effort = value.get("requested_reasoning_effort")
    duration = value.get("duration_ms")
    evidence_refs = value.get("evidence_refs")
    source = value.get("evidence_source")
    assignment = assignments.get(value.get("assignment_id"))
    if (
        assignment is None
        or value.get("status") not in STAGE_STATUSES
        or source not in STAGE_EVIDENCE_SOURCES
        or value.get("model_evidence")
        not in {"unavailable", "request_only", "complete"}
        or not _valid_model(requested_model)
        or not _valid_reasoning_effort(requested_effort)
        or not _valid_model(actual_model)
        or not isinstance(value.get("reroutes"), list)
        or (
            value.get("model_evidence") == "unavailable"
            and actual_model is not None
        )
        or (
            value.get("model_evidence") == "complete"
            and actual_model is None
        )
        or (
            duration is not None
            and (
                not isinstance(duration, (int, float))
                or isinstance(duration, bool)
                or not math.isfinite(duration)
                or duration < 0
            )
        )
        or not _valid_token_summary(value.get("tokens"))
        or not isinstance(evidence_refs, list)
        or not evidence_refs
        or len(evidence_refs) > 3
        or not all(
            isinstance(item, str)
            and bool(item.strip())
            and len(item) <= 240
            and not any(character in item for character in "\r\n\x00")
            for item in evidence_refs
        )
        or _parse_timestamp(value.get("observed_at")) is None
    ):
        return False
    planned_route_id = assignment.get("model_route_id")
    planned_unit_id = assignment.get("execution_unit_id")
    if planned_route_id is None and planned_unit_id is None:
        if route_identity_fields & set(value):
            return False
    elif (
        value.get("model_route_id") != planned_route_id
        or value.get("execution_unit_id") != planned_unit_id
    ):
        return False
    assessment = value.get("verification_assessment")
    if assessment is not None and not _valid_verification_assessment(
        assessment,
        verifier_assignment=assignment,
        assignments=assignments,
        evidence_source=source,
        stage_status=value.get("status"),
        verifier_stage=value,
    ):
        return False
    execution_unit = assignment.get("execution_unit")
    execution_unit_receipt = value.get("execution_unit_receipt")
    receipt_required = (
        plan_summary.get("execution_receipts_required") is True
        and isinstance(execution_unit, dict)
        and execution_unit.get("host_executable") is True
        and source == "codex_app_server"
        and value.get("status") == "completed"
    )
    if receipt_required and execution_unit_receipt is None:
        return False
    if execution_unit_receipt is not None:
        if not isinstance(execution_unit_receipt, dict):
            return False
        assignment_by_id = {
            item["assignment_id"]: item
            for item in plan_summary["assignments"]
        }
        dependency_ids = assignment.get("depends_on", [])
        if any(
            dependency_id not in assignment_by_id
            for dependency_id in dependency_ids
        ):
            return False
        dependency_assignments = [
            assignment_by_id[dependency_id]
            for dependency_id in dependency_ids
        ]
        dependency_receipts = [
            result["execution_unit_receipt"]
            for dependency_id in assignment.get("depends_on", [])
            for result in [
                (prior_results or {}).get(dependency_id, {})
            ]
            if isinstance(result.get("execution_unit_receipt"), dict)
        ]
        validation = validate_execution_unit_receipt(
            execution_unit_receipt,
            unit=execution_unit,
            dependency_units=[
                item["execution_unit"]
                for item in dependency_assignments
                if isinstance(item.get("execution_unit"), dict)
            ],
            dependency_receipts=dependency_receipts,
        )
        attempts = execution_unit_receipt.get("attempts", [])
        last_attempt = attempts[-1] if attempts else {}
        if (
            validation["status"] != "PASS"
            or execution_unit_receipt.get("producer", {}).get("run_id")
            is None
            or attempts[0].get("requested_model")
            != value.get("requested_model")
            or attempts[0].get("requested_reasoning_effort")
            != value.get("requested_reasoning_effort")
            or last_attempt.get("applied_model")
            != value.get("actual_model")
            or attempts[0].get("provider_reroutes")
            != value.get("reroutes")
            or last_attempt.get("duration_ms") != value.get("duration_ms")
            or last_attempt.get("tokens") != value.get("tokens")
            or (
                "assignment-packet:"
                + str(
                    execution_unit_receipt.get(
                        "output_packet_digest",
                        "",
                    )
                )
            )
            not in evidence_refs
        ):
            return False
    if source == "codex_app_server":
        if value["model_evidence"] == "complete":
            return (
                requested_model is not None
                and actual_model is not None
                and duration is not None
                and _valid_model_reroutes(
                    value["reroutes"],
                    requested_model=requested_model,
                    applied_model=actual_model,
                )
            )
        if value["model_evidence"] == "request_only":
            return (
                requested_model is not None
                and actual_model is None
                and duration is not None
                and value["reroutes"] == []
            )
        return (
            value["status"] != "completed"
            and requested_model is None
            and requested_effort is None
            and actual_model is None
            and value["reroutes"] == []
            and value.get("tokens") is None
        )
    return (
        value["model_evidence"] == "unavailable"
        and requested_model is None
        and requested_effort is None
        and actual_model is None
        and value["reroutes"] == []
        and value.get("tokens") is None
    )


def _valid_verification_assessment(
    value: Any,
    *,
    verifier_assignment: dict[str, Any],
    assignments: dict[str, dict[str, Any]],
    evidence_source: Any,
    stage_status: Any,
    verifier_stage: dict[str, Any],
) -> bool:
    return (
        evidence_source == "codex_app_server"
        and stage_status == "completed"
        and verifier_assignment.get("executor_id") == "verifier"
        and isinstance(value, dict)
        and value.get("verifier_assignment_id")
        == verifier_assignment.get("assignment_id")
        and validate_verification_assessment(
            value,
            plan_summary={
                "assignments": list(assignments.values()),
            },
            verifier_stage=verifier_stage,
        )
    )


def _valid_stage_results_for_observation(
    value: Any,
    *,
    plan_summary: dict[str, Any] | None,
    run_id: str | None = None,
    observation_id: str | None = None,
    work_spans: Any = None,
) -> bool:
    if value is None:
        return True
    if (
        not isinstance(plan_summary, dict)
        or not isinstance(value, list)
        or len(value) > MAX_PLAN_ASSIGNMENTS
    ):
        return False
    ids: set[str] = set()
    prior_results: dict[str, dict[str, Any]] = {}
    for item in value:
        if (
            not _valid_stage_result(
                item,
                plan_summary=plan_summary,
                prior_results=prior_results,
            )
            or item["assignment_id"] in ids
        ):
            return False
        ids.add(item["assignment_id"])
        prior_results[item["assignment_id"]] = item
    return (
        validate_stage_execution_receipts(
            plan_summary=plan_summary,
            stage_results=value,
            run_id=run_id,
            observation_id=observation_id,
            work_spans=work_spans,
            expected_framework_version=__version__,
        )["status"]
        == "PASS"
    )


def record_stage_observation(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    assignment_id: str,
    status: str,
    evidence_source: str,
    evidence_refs: list[str],
    requested_model: str | None = None,
    requested_reasoning_effort: str | None = None,
    actual_model: str | None = None,
    model_route_id: str | None = None,
    execution_unit_id: str | None = None,
    model_evidence: str = "unavailable",
    reroutes: list[dict[str, str]] | None = None,
    duration_ms: float | None = None,
    tokens: dict[str, int | None] | None = None,
    verification_assessment: dict[str, Any] | None = None,
    execution_unit_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one immutable terminal Assignment result to a run observation."""

    repo = ensure_repo(repo_path)
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    plan_summary = value.get("plan_summary")
    if (
        value.get("run_id") != run_id
        or "completed_at" in value
        or not isinstance(plan_summary, dict)
    ):
        raise MaestroError(
            "RUN_STAGE_OBSERVATION_INVALID",
            "Stage evidence requires the matching unfinished run and attached plan.",
        )
    execution_binding = value.get("execution_binding")
    if (
        evidence_source == "current_host"
        and (
            not isinstance(execution_binding, dict)
            or execution_binding.get("mode") != "explicit_fallback"
        )
    ):
        raise MaestroError(
            "RUN_EXECUTION_FALLBACK_REQUIRED",
            "A current-Host stage requires an explicit fallback recorded "
            "after Desktop request intake. Use the Maestro-owned Codex App "
            "Server path when no fallback is required.",
        )
    assignments = {
        item["assignment_id"]: item
        for item in plan_summary["assignments"]
    }
    assignment = assignments.get(assignment_id)
    if assignment is None:
        raise MaestroError(
            "RUN_STAGE_OBSERVATION_INVALID",
            "The Assignment is not present in the attached plan.",
        )
    existing_results = list(value.get("stage_results", []))
    by_id = {
        item["assignment_id"]: item
        for item in existing_results
        if isinstance(item, dict)
    }
    missing_dependencies = [
        dependency
        for dependency in assignment.get("depends_on", [])
        if dependency not in by_id
    ]
    if missing_dependencies:
        raise MaestroError(
            "RUN_STAGE_ORDER_INVALID",
            "Stage evidence cannot precede its dependencies: "
            + ", ".join(missing_dependencies),
        )
    if status == "completed":
        unsuccessful_dependencies = [
            dependency
            for dependency in assignment.get("depends_on", [])
            if by_id[dependency]["status"] != "completed"
        ]
        if unsuccessful_dependencies:
            raise MaestroError(
                "RUN_STAGE_ORDER_INVALID",
                "A completed stage requires completed dependencies: "
                + ", ".join(unsuccessful_dependencies),
            )
    result = {
        "assignment_id": assignment_id,
        "status": status,
        "requested_model": requested_model,
        "requested_reasoning_effort": requested_reasoning_effort,
        "actual_model": actual_model,
        "model_evidence": model_evidence,
        "reroutes": list(reroutes or []),
        "duration_ms": duration_ms,
        "tokens": tokens,
        "evidence_refs": list(evidence_refs),
        "evidence_source": evidence_source,
        "observed_at": _timestamp(_utc_now()),
    }
    if verification_assessment is not None:
        result["verification_assessment"] = copy.deepcopy(
            verification_assessment
        )
    if execution_unit_receipt is not None:
        result["execution_unit_receipt"] = copy.deepcopy(
            execution_unit_receipt
        )
    planned_route_id = assignment.get("model_route_id")
    planned_unit_id = assignment.get("execution_unit_id")
    if planned_route_id is not None or planned_unit_id is not None:
        if (
            model_route_id not in {None, planned_route_id}
            or execution_unit_id not in {None, planned_unit_id}
        ):
            raise MaestroError(
                "RUN_STAGE_MODEL_ROUTE_CONFLICT",
                "Stage evidence must preserve the exact planned model route identity.",
            )
        result["model_route_id"] = planned_route_id
        result["execution_unit_id"] = planned_unit_id
    elif model_route_id is not None or execution_unit_id is not None:
        raise MaestroError(
            "RUN_STAGE_MODEL_ROUTE_CONFLICT",
            "Legacy Assignment evidence cannot claim an unplanned model route identity.",
        )
    if not _valid_stage_result(
        result,
        plan_summary=plan_summary,
        prior_results=by_id,
    ):
        raise MaestroError(
            "RUN_STAGE_OBSERVATION_INVALID",
            "Stage evidence does not satisfy its source and measurement contract.",
        )
    existing = by_id.get(assignment_id)
    if existing is not None:
        comparable = {key: item for key, item in existing.items() if key != "observed_at"}
        expected = {key: item for key, item in result.items() if key != "observed_at"}
        if comparable != expected:
            raise MaestroError(
                "RUN_STAGE_OBSERVATION_CONFLICT",
                "The Assignment already has a different terminal result.",
            )
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "observe-stage",
            "status": "already_recorded",
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation_id,
            "assignment_id": assignment_id,
            "writes_performed": False,
        }
    if (
        validate_stage_execution_receipts(
            plan_summary=plan_summary,
            stage_results=[*existing_results, result],
            run_id=run_id,
            observation_id=observation_id,
            work_spans=value.get("work_spans"),
            expected_framework_version=__version__,
        )["status"]
        != "PASS"
    ):
        raise MaestroError(
            "RUN_STAGE_EXECUTION_RECEIPT_INVALID",
            "Stage execution receipts do not bind the exact plan, evidence, and WorkSpan lineage.",
        )
    before = copy.deepcopy(value)
    existing_results.append(result)
    plan_order = {
        item["assignment_id"]: index
        for index, item in enumerate(plan_summary["assignments"])
    }
    value["stage_results"] = sorted(
        existing_results,
        key=lambda item: plan_order[item["assignment_id"]],
    )
    all_terminal = len(value["stage_results"]) == len(plan_summary["assignments"])
    commit_execution_transition(
        target,
        before=before,
        after=value,
        event_type="assignment_terminal",
        idempotency_key=f"assignment:{assignment_id}:terminal",
        producer=_execution_producer(
            evidence_source,
            correlation_id=assignment_id,
            complete=(
                evidence_source == "codex_app_server"
                and model_evidence in {"request_only", "complete"}
            ),
        ),
        payload={"stage_result": result},
        measurement=measurement_from_stage(result),
        recorded_at=result["observed_at"],
    )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-stage",
        "status": "recorded",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "assignment_id": assignment_id,
        "run_terminal": False,
        "assignments_terminal": all_terminal,
        "writes_performed": True,
    }


def _work_bindings_match_plan(
    work_spans: Any,
    plan_summary: Any,
) -> bool:
    if not validate_work_spans(work_spans):
        return False
    assignments = (
        {
            assignment["assignment_id"]: assignment
            for assignment in plan_summary.get("assignments", [])
            if isinstance(assignment, dict)
            and isinstance(assignment.get("assignment_id"), str)
        }
        if isinstance(plan_summary, dict)
        else {}
    )
    child_counts: dict[str, int] = {}
    for span in work_spans or []:
        assignment_id = span["assignment_id"]
        if assignment_id is None:
            continue
        assignment = assignments.get(assignment_id)
        if (
            assignment is None
            or span.get("read_only") is not assignment.get("read_only")
        ):
            return False
        if span.get("kind") == "delegation":
            child_counts[assignment_id] = child_counts.get(
                assignment_id,
                0,
            ) + 1
            if (
                assignment.get("may_spawn") is not True
                or child_counts[assignment_id]
                > assignment.get("max_children", 0)
            ):
                return False
    return True


def record_work_start(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    work_id: str,
    kind: str,
    role: str,
    executor_id: str,
    task_summary: str,
    read_only: bool,
    source: str = "current_host",
    parent_work_id: str | None = None,
    assignment_id: str | None = None,
    attempt: int = 1,
    followup_of_work_id: str | None = None,
    depends_on_work_ids: list[str] | None = None,
    joins_work_ids: list[str] | None = None,
    requested_model: str | None = None,
    requested_reasoning_effort: str | None = None,
    applied_model: str | None = None,
    model_evidence: str = "unavailable",
    lens_ids: list[str] | None = None,
    expertise_pack_ids: list[str] | None = None,
    decision_guide_ids: list[str] | None = None,
    expertise_evidence: str = "unavailable",
    source_binding: dict[str, Any] | None = None,
    model_observation: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
    allocation: dict[str, Any] | None = None,
    expertise_observation: dict[str, Any] | None = None,
    event_started_at: str | None = None,
) -> dict[str, Any]:
    """Append one bounded actual-work attempt to a run observation."""

    repo = ensure_repo(repo_path)
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    if value.get("run_id") != run_id or "completed_at" in value:
        raise MaestroError(
            "WORK_OBSERVATION_INVALID",
            "Observed work requires the matching unfinished run.",
        )
    assignment: dict[str, Any] | None = None
    if assignment_id is not None:
        plan_summary = value.get("plan_summary")
        assignment = next(
            (
                item
                for item in (
                    plan_summary.get("assignments", [])
                    if isinstance(plan_summary, dict)
                    else []
                )
                if isinstance(item, dict)
                and item.get("assignment_id") == assignment_id
            ),
            None,
        )
        if assignment is None:
            raise MaestroError(
                "WORK_ASSIGNMENT_BINDING_INVALID",
                "Observed work references an Assignment outside the attached plan.",
            )
        if read_only is not assignment.get("read_only"):
            raise MaestroError(
                "WORK_ASSIGNMENT_ACCESS_MISMATCH",
                "Assignment-bound work must preserve the planned read-only "
                "or writer access policy.",
            )
        execution_binding = value.get("execution_binding")
        if source == "current_host" and (
            not isinstance(execution_binding, dict)
            or execution_binding.get("mode") != "explicit_fallback"
        ):
            raise MaestroError(
                "RUN_EXECUTION_FALLBACK_REQUIRED",
                "Assignment-bound current-Host work requires an explicit "
                "fallback before it starts.",
            )
        if kind == "delegation":
            current_children = sum(
                1
                for span in value.get("work_spans", [])
                if isinstance(span, dict)
                and span.get("assignment_id") == assignment_id
                and span.get("kind") == "delegation"
            )
            if (
                assignment.get("may_spawn") is not True
                or current_children >= assignment.get("max_children", 0)
            ):
                raise MaestroError(
                    "WORK_DELEGATION_FORBIDDEN",
                    "Assignment-bound work attempted delegation outside its "
                    "planned may_spawn/max_children policy.",
                )
    event_start = (
        _parse_timestamp(event_started_at)
        if event_started_at is not None
        else None
    )
    if event_started_at is not None and (
        event_start is None
        or source not in {"codex_app_server", "host_adapter"}
    ):
        raise MaestroError(
            "WORK_EVENT_TIME_INVALID",
            "Only a Host event source may supply a valid event start time.",
        )
    now = _timestamp(
        event_start.astimezone(timezone.utc)
        if event_start is not None
        else _utc_now()
    )
    span = new_work_span(
        work_id=work_id,
        parent_work_id=parent_work_id,
        assignment_id=assignment_id,
        kind=kind,
        role=role,
        executor_id=executor_id,
        task_summary=task_summary,
        read_only=read_only,
        source=source,
        started_at=now,
        timing_evidence=(
            "host_event"
            if event_start is not None
            else "current_host_clock"
        ),
        attempt=attempt,
        followup_of_work_id=followup_of_work_id,
        depends_on_work_ids=depends_on_work_ids,
        joins_work_ids=joins_work_ids,
        requested_model=requested_model,
        requested_reasoning_effort=requested_reasoning_effort,
        applied_model=applied_model,
        model_evidence=model_evidence,
        lens_ids=lens_ids,
        expertise_pack_ids=expertise_pack_ids,
        decision_guide_ids=decision_guide_ids,
        expertise_evidence=expertise_evidence,
        source_binding=source_binding,
        model_observation=model_observation,
        usage=usage,
        outcome=outcome,
        diagnostics=diagnostics,
        allocation=allocation,
        expertise_observation=expertise_observation,
    )
    before = copy.deepcopy(value)
    work_spans, changed = append_work_span(
        value.get("work_spans"),
        span,
    )
    if not _work_bindings_match_plan(
        work_spans,
        value.get("plan_summary"),
    ):
        raise MaestroError(
            "WORK_ASSIGNMENT_BINDING_INVALID",
            "A work Assignment binding must reference the attached plan.",
        )
    if changed:
        value["work_spans"] = work_spans
        commit_execution_transition(
            target,
            before=before,
            after=value,
            event_type="work_started",
            idempotency_key=f"work:{work_id}:start",
            producer=_execution_producer(
                source,
                correlation_id=span.get("source_binding", {}).get(
                    "correlation_id"
                ),
            ),
            payload={"work_span": span},
            measurement=measurement_from_work(span),
            recorded_at=now,
        )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-work-start",
        "status": "recorded" if changed else "already_recorded",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "work_id": work_id,
        "writes_performed": changed,
    }


def record_work_finish(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    work_id: str,
    status: str,
    result_summary: str,
    evidence_refs: list[str],
    applied_model: str | None = None,
    model_evidence: str | None = None,
    expertise_evidence: str | None = None,
    source_binding: dict[str, Any] | None = None,
    model_observation: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
    allocation: dict[str, Any] | None = None,
    expertise_observation: dict[str, Any] | None = None,
    event_ended_at: str | None = None,
    event_duration_ms: float | None = None,
) -> dict[str, Any]:
    """Complete one actual-work attempt without exposing its raw exchange."""

    repo = ensure_repo(repo_path)
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    if value.get("run_id") != run_id or "completed_at" in value:
        raise MaestroError(
            "WORK_OBSERVATION_INVALID",
            "Observed work requires the matching unfinished run.",
        )
    recorded = next(
        (
            span
            for span in value.get("work_spans", [])
            if span.get("work_id") == work_id
        ),
        None,
    )
    if not isinstance(recorded, dict):
        raise MaestroError(
            "WORK_SPAN_NOT_FOUND",
            "The work ID is not present in this run observation.",
        )
    event_end = (
        _parse_timestamp(event_ended_at)
        if event_ended_at is not None
        else None
    )
    if (
        (
            event_ended_at is not None
            and event_end is None
        )
        or (
            (event_ended_at is not None or event_duration_ms is not None)
            and recorded.get("source")
            not in {"codex_app_server", "host_adapter"}
        )
        or (
            event_duration_ms is not None
            and (
                not isinstance(event_duration_ms, (int, float))
                or isinstance(event_duration_ms, bool)
                or not math.isfinite(event_duration_ms)
                or event_duration_ms < 0
            )
        )
    ):
        raise MaestroError(
            "WORK_EVENT_TIME_INVALID",
            "Only a Host event source may supply valid terminal event timing.",
        )
    recorded_end = _parse_timestamp(recorded.get("ended_at"))
    terminal_replay = recorded.get("status") != "running"
    now = (
        event_end.astimezone(timezone.utc)
        if event_end is not None
        else (
            recorded_end
            if terminal_replay and recorded_end is not None
            else _utc_now()
        )
    )
    started_at = _parse_timestamp(recorded.get("started_at"))
    if started_at is None:
        raise MaestroError(
            "WORK_SPAN_INVALID",
            "The observed work start time is invalid.",
        )
    duration_ms = (
        round(float(event_duration_ms), 3)
        if event_duration_ms is not None
        else (
            recorded["duration_ms"]
            if terminal_replay
            and isinstance(recorded.get("duration_ms"), (int, float))
            else round(
                max(0.0, (now - started_at).total_seconds() * 1000),
                3,
            )
        )
    )
    before = copy.deepcopy(value)
    work_spans, changed = finish_work_span(
        value.get("work_spans"),
        work_id=work_id,
        status=status,
        result_summary=result_summary,
        ended_at=_timestamp(now),
        duration_ms=duration_ms,
        evidence_refs=evidence_refs,
        applied_model=applied_model,
        model_evidence=model_evidence,
        expertise_evidence=expertise_evidence,
        source_binding=source_binding,
        model_observation=model_observation,
        usage=usage,
        outcome=outcome,
        diagnostics=diagnostics,
        allocation=allocation,
        expertise_observation=expertise_observation,
    )
    if changed:
        value["work_spans"] = work_spans
        completed_span = next(
            span for span in work_spans if span["work_id"] == work_id
        )
        binding = completed_span.get("source_binding")
        complete_stream = (
            isinstance(binding, dict)
            and binding.get("event_coverage")
            in {"complete_stream", "recovered_full"}
        )
        commit_execution_transition(
            target,
            before=before,
            after=value,
            event_type="work_terminal",
            idempotency_key=f"work:{work_id}:terminal",
            producer=_execution_producer(
                completed_span["source"],
                correlation_id=(
                    binding.get("correlation_id")
                    if isinstance(binding, dict)
                    else None
                ),
                complete=complete_stream,
            ),
            payload={"work_span": completed_span},
            measurement=measurement_from_work(completed_span),
            recorded_at=completed_span["ended_at"],
        )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-work-finish",
        "status": "recorded" if changed else "already_recorded",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "work_id": work_id,
        "writes_performed": changed,
    }


def start_desktop_request_observation(
    repo_path: str | Path,
    *,
    run_id: str,
    task_label: str,
    thread_id: str,
    turn_id: str,
    requested_model: str,
    requested_reasoning_effort: str | None = None,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """Start a run and attach allowlisted Codex Desktop request data."""

    thread = _bounded_line(
        thread_id,
        field="thread-id",
        maximum=72,
    )
    turn = _bounded_line(
        turn_id,
        field="turn-id",
        maximum=72,
    )
    model = _bounded_line(
        requested_model,
        field="requested-model",
        maximum=128,
    )
    effort = (
        _bounded_line(
            requested_reasoning_effort,
            field="requested-reasoning-effort",
            maximum=40,
        )
        if requested_reasoning_effort is not None
        else None
    )
    binding = {
        "schema_version": EXECUTION_BINDING_VERSION,
        "mode": "desktop_request",
    }
    lineage = desktop_root_lineage(
        run_id=run_id,
        thread_id=thread,
        turn_id=turn,
    )
    started = start_run_observation(
        repo_path,
        run_id=run_id,
        task_label=task_label,
        plan_path=plan_path,
        execution_binding=binding,
        request_lineage=lineage,
    )
    attached = record_host_observation(
        repo_path,
        observation_id=started["observation_id"],
        run_id=run_id,
        source="codex-desktop-request-meta",
        quality="host_reported",
        correlation_id=f"{thread}:{turn}",
        requested_model=model,
        requested_reasoning_effort=effort,
        model_event_evidence="unavailable",
    )
    observed_fields = observation_receipt_fields(
        repo_path,
        observation_id=started["observation_id"],
        run_id=run_id,
    )
    telemetry = attached.get("telemetry") or observed_fields["host_observation"]
    effective_binding = observed_fields.get("execution_binding", binding)
    writes_performed = bool(
        started["writes_performed"] or attached["writes_performed"]
    )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-desktop",
        "status": (
            "started"
            if started["status"] == "started"
            else "already_started"
        ),
        "repo_root": started["repo_root"],
        "run_id": run_id,
        "observation_id": started["observation_id"],
        "observation_path": started["observation_path"],
        "telemetry_scope": "desktop_request_only",
        "telemetry": telemetry,
        "execution_binding": effective_binding,
        "request_lineage": observed_fields["request_lineage"],
        "writes_performed": writes_performed,
    }


def observation_receipt_fields(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    if (
        not isinstance(observation_id, str)
        or len(observation_id) != 32
        or any(character not in "0123456789abcdef" for character in observation_id)
    ):
        raise MaestroError(
            "RUN_OBSERVATION_ID_INVALID",
            "observation-id must be the 32-character ID returned by observe start.",
        )
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    base_fields = {
        "schema_version",
        "observation_id",
        "project_id",
        "checkout_id",
        "run_id",
        "task_label",
        "started_at",
        "plan_summary",
    }
    optional_fields = {
        "request_lineage",
        "host_observation",
        "plan_attached_at",
        "stage_results",
        "work_spans",
        "completed_at",
        "duration_ms",
        "execution_binding",
        "fallback_recorded_at",
        "execution_ledger",
        "completion_policy",
        "completion_closure",
    }
    started_at = _parse_timestamp(value.get("started_at"))
    completed_at = _parse_timestamp(value.get("completed_at"))
    project = read_json(safe_target(repo, ".maestro/project.json"))
    if (
        not base_fields.issubset(value)
        or set(value) - (base_fields | optional_fields)
        or (("completed_at" in value) != ("duration_ms" in value))
        or value.get("schema_version") != OBSERVATION_VERSION
        or value.get("observation_id") != observation_id
        or value.get("project_id") != project.get("project_id")
        or value.get("checkout_id") != checkout_id(repo)
        or value.get("run_id") != run_id
        or started_at is None
        or (
            value.get("plan_attached_at") is not None
            and _parse_timestamp(value.get("plan_attached_at")) is None
        )
        or (
            value.get("fallback_recorded_at") is not None
            and _parse_timestamp(value.get("fallback_recorded_at")) is None
        )
        or not _valid_plan_summary_for_observation(
            value.get("plan_summary")
        )
        or (
            value.get("request_lineage") is not None
            and not validate_request_lineage(
                value.get("request_lineage"),
                current_run_id=run_id,
            )
        )
        or (
            isinstance(value.get("execution_binding"), dict)
            and value["execution_binding"].get("mode")
            == "maestro_owned_codex_app_server"
            and isinstance(value.get("plan_summary"), dict)
            and value["plan_summary"].get(
                "execution_receipts_required"
            )
            is not True
        )
        or not _valid_stage_results_for_observation(
            value.get("stage_results"),
            plan_summary=value.get("plan_summary"),
            run_id=run_id,
            observation_id=observation_id,
            work_spans=value.get("work_spans"),
        )
        or not _work_bindings_match_plan(
            value.get("work_spans"),
            value.get("plan_summary"),
        )
        or not _valid_host_observation(value.get("host_observation"))
        or not _valid_execution_binding(value.get("execution_binding"))
        or (
            value.get("execution_ledger") is not None
            and not validate_execution_ledger(value.get("execution_ledger"))
        )
        or not _valid_completion_state(value)
        or (
            "completed_at" in value
            and (
                completed_at is None
                or not isinstance(value.get("duration_ms"), (int, float))
                or isinstance(value.get("duration_ms"), bool)
                or value["duration_ms"] < 0
            )
        )
    ):
        raise MaestroError(
            "RUN_OBSERVATION_INVALID",
            "The in-flight observation does not match this project and run.",
        )
    label = _task_label(value.get("task_label"))
    elapsed = (
        value["duration_ms"]
        if "duration_ms" in value
        else (_utc_now() - started_at).total_seconds() * 1000
    )
    if elapsed < 0:
        raise MaestroError(
            "RUN_OBSERVATION_CLOCK_INVALID",
            "The observation start time is in the future.",
        )
    result = {
        "observation_id": observation_id,
        "task_label": label,
        "duration_ms": round(elapsed, 3),
        "plan_summary": value.get("plan_summary"),
        "stage_results": list(value.get("stage_results", [])),
        "work_spans": list(value.get("work_spans", [])),
    }
    if value.get("request_lineage") is not None:
        result["request_lineage"] = value["request_lineage"]
    ledger = ensure_execution_ledger(value)
    result["execution_measurements"] = execution_measurements(
        ledger,
        duration_ms=round(elapsed, 3),
    )
    result["duration_ms"] = result["execution_measurements"]["duration"][
        "value_ms"
    ]
    plan_attached_at = _parse_timestamp(value.get("plan_attached_at"))
    result["planning_duration_ms"] = (
        round(
            max(
                0.0,
                (plan_attached_at - started_at).total_seconds() * 1000,
            ),
            3,
        )
        if plan_attached_at is not None
        else None
    )
    if value.get("host_observation") is not None:
        result["host_observation"] = value["host_observation"]
    if value.get("execution_binding") is not None:
        result["execution_binding"] = value["execution_binding"]
    if value.get("completion_policy") is not None:
        result["completion_policy"] = value["completion_policy"]
    if value.get("completion_closure") is not None:
        result["completion_closure"] = value["completion_closure"]
    return result


def record_host_observation(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    source: str,
    quality: str,
    correlation_id: str,
    requested_model: str | None = None,
    requested_reasoning_effort: str | None = None,
    applied_model: str | None = None,
    model_event_evidence: str = "unavailable",
    reroutes: list[dict[str, str]] | None = None,
    actual_model: str | None = None,
    tokens: dict[str, int | None] | None = None,
    duration_ms: float | None = None,
    trusted_event_stream: bool = False,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    if (
        not trusted_event_stream
        and (
            applied_model is not None
            or actual_model is not None
            or model_event_evidence == "complete"
            or bool(reroutes)
            or tokens is not None
            or duration_ms is not None
        )
    ):
        raise MaestroError(
            "HOST_OBSERVATION_TRUST_REQUIRED",
            "Applied model, reroute, and token claims may be attached only "
            "by the owned App Server or the validated trace importer.",
        )
    if (
        not isinstance(observation_id, str)
        or len(observation_id) != 32
        or any(
            character not in "0123456789abcdef"
            for character in observation_id
        )
    ):
        raise MaestroError(
            "RUN_OBSERVATION_ID_INVALID",
            "observation-id must be the 32-character ID returned by observe start.",
        )
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    observation_receipt_fields(
        repo,
        observation_id=observation_id,
        run_id=run_id,
    )
    value = _read_observation_file(target)
    if value.get("run_id") != run_id or "completed_at" in value:
        raise MaestroError(
            "HOST_OBSERVATION_CONFLICT",
            "Host telemetry must match an unfinished in-flight observation.",
        )
    if actual_model is not None:
        if applied_model is not None and applied_model != actual_model:
            raise MaestroError(
                "HOST_OBSERVATION_INVALID",
                "actual-model and applied-model cannot disagree.",
            )
        applied_model = actual_model
    host_observation = {
        "schema_version": HOST_OBSERVATION_VERSION,
        "source": _bounded_line(source, field="source", maximum=80),
        "quality": quality,
        "correlation_id": _bounded_line(
            correlation_id,
            field="correlation-id",
            maximum=160,
        ),
        "requested_model": (
            _bounded_line(
                requested_model,
                field="requested-model",
                maximum=128,
            )
            if requested_model is not None
            else None
        ),
        "requested_reasoning_effort": (
            _bounded_line(
                requested_reasoning_effort,
                field="requested-reasoning-effort",
                maximum=40,
            )
            if requested_reasoning_effort is not None
            else None
        ),
        "reasoning_effort_evidence": (
            "host_request"
            if requested_reasoning_effort is not None
            else "unavailable"
        ),
        "applied_model": (
            _bounded_line(
                applied_model,
                field="applied-model",
                maximum=128,
            )
            if applied_model is not None
            else None
        ),
        "model_event_evidence": model_event_evidence,
        "reroutes": list(reroutes or []),
        "tokens": tokens,
        "duration_ms": duration_ms,
        "observed_at": _timestamp(_utc_now()),
    }
    if not _valid_host_observation(host_observation):
        raise MaestroError(
            "HOST_OBSERVATION_INVALID",
            "Applied model telemetry requires a complete Host model event "
            "stream. Requested-only telemetry must keep the applied model "
            "unknown.",
        )
    host_identity = {
        key: item
        for key, item in host_observation.items()
        if key != "observed_at"
    }
    host_key = (
        "measurement:"
        f"{host_observation['source']}:"
        f"{host_observation['correlation_id']}:"
        f"{sha256_text(canonical_json(host_identity))[:16]}"
    )
    ledger_source = (
        "desktop_request"
        if source == "codex-desktop-request-meta"
        else (
            "codex_app_server"
            if source in {"codex-app-server", "codex_app_server"}
            else "host_adapter"
        )
    )
    producer = _execution_producer(
        ledger_source,
        correlation_id=host_observation["correlation_id"],
        complete=(
            trusted_event_stream
            and model_event_evidence == "complete"
        ),
    )
    existing = value.get("host_observation")
    if existing is not None:
        comparable = {
            key: item
            for key, item in existing.items()
            if key != "observed_at"
        }
        expected = {
            key: item
            for key, item in host_observation.items()
            if key != "observed_at"
        }
        if comparable != expected:
            same_identity = (
                existing.get("schema_version") == HOST_OBSERVATION_VERSION
                and existing.get("source") == host_observation["source"]
                and existing.get("quality") == host_observation["quality"]
                and existing.get("correlation_id")
                == host_observation["correlation_id"]
            )
            monotonic_enrichment = (
                same_identity
                and existing.get("requested_model")
                in {None, host_observation["requested_model"]}
                and existing.get("requested_reasoning_effort")
                in {
                    None,
                    host_observation["requested_reasoning_effort"],
                }
                and existing.get(
                    "reasoning_effort_evidence",
                    "unavailable",
                )
                in {
                    "unavailable",
                    host_observation["reasoning_effort_evidence"],
                }
                and existing.get("applied_model")
                in {None, host_observation["applied_model"]}
                and existing.get("model_event_evidence")
                in {"unavailable", host_observation["model_event_evidence"]}
                and (
                    existing.get("reroutes") == []
                    or existing.get("reroutes")
                    == host_observation["reroutes"]
                )
                and (
                    existing.get("tokens") is None
                    or existing.get("tokens") == host_observation["tokens"]
                )
                and (
                    existing.get("duration_ms") is None
                    or existing.get("duration_ms")
                    == host_observation["duration_ms"]
                )
            )
            if not monotonic_enrichment:
                if (
                    existing.get("correlation_id")
                    != host_observation["correlation_id"]
                    or not trusted_event_stream
                ):
                    raise MaestroError(
                        "HOST_OBSERVATION_CONFLICT",
                        "This run already has different Host telemetry.",
                    )
                commit_execution_transition(
                    target,
                    before=copy.deepcopy(value),
                    after=value,
                    event_type="measurement_observed",
                    idempotency_key=host_key,
                    producer=producer,
                    payload={"host_observation": host_observation},
                    measurement=measurement_from_host(host_observation),
                    recorded_at=host_observation["observed_at"],
                )
                return {
                    "schema_version": "maestro_command_result_v1",
                    "command": "observe-host",
                    "status": "co_recorded",
                    "repo_root": str(repo),
                    "run_id": run_id,
                    "observation_id": observation_id,
                    "telemetry": host_observation,
                    "writes_performed": True,
                }
            before = copy.deepcopy(value)
            value["host_observation"] = host_observation
            commit_execution_transition(
                target,
                before=before,
                after=value,
                event_type="measurement_observed",
                idempotency_key=host_key,
                producer=producer,
                payload={"host_observation": host_observation},
                measurement=measurement_from_host(host_observation),
                recorded_at=host_observation["observed_at"],
            )
            return {
                "schema_version": "maestro_command_result_v1",
                "command": "observe-host",
                "status": "enriched",
                "repo_root": str(repo),
                "run_id": run_id,
                "observation_id": observation_id,
                "telemetry": host_observation,
                "writes_performed": True,
            }
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "observe-host",
            "status": "already_recorded",
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation_id,
            "writes_performed": False,
        }
    before = copy.deepcopy(value)
    value["host_observation"] = host_observation
    commit_execution_transition(
        target,
        before=before,
        after=value,
        event_type="measurement_observed",
        idempotency_key=host_key,
        producer=producer,
        payload={"host_observation": host_observation},
        measurement=measurement_from_host(host_observation),
        recorded_at=host_observation["observed_at"],
    )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-host",
        "status": "recorded",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "telemetry": host_observation,
        "writes_performed": True,
    }


def _rpc_id(value: Any) -> tuple[str, str] | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return type(value).__name__, str(value)


def _app_server_trace_messages(trace_path: str | Path) -> list[dict[str, Any]]:
    path = Path(trace_path).expanduser().resolve()
    try:
        valid = (
            not path.is_symlink()
            and path.is_file()
            and path.stat().st_size <= MAX_APP_SERVER_TRACE_BYTES
        )
    except OSError:
        valid = False
    if not valid:
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INVALID",
            "App Server trace is missing, unsafe, or exceeds the 4 MB limit.",
        )
    messages: list[dict[str, Any]] = []
    try:
        lines = path.open(encoding="utf-8", errors="strict")
    except OSError as exc:
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INVALID",
            f"Cannot read App Server trace: {exc}",
        ) from exc
    with lines:
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            if len(messages) >= MAX_APP_SERVER_TRACE_MESSAGES:
                raise MaestroError(
                    "CODEX_APP_SERVER_TRACE_INVALID",
                    "App Server trace exceeds the 20,000-message limit.",
                )
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MaestroError(
                    "CODEX_APP_SERVER_TRACE_INVALID",
                    f"Invalid JSON-RPC message at line {line_number}.",
                ) from exc
            if not isinstance(message, dict):
                raise MaestroError(
                    "CODEX_APP_SERVER_TRACE_INVALID",
                    f"Trace line {line_number} must be one JSON-RPC object.",
                )
            messages.append(message)
    if not messages:
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INVALID",
            "App Server trace contains no JSON-RPC messages.",
        )
    return messages


def _token_summary_from_app_server(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    fields = {
        "inputTokens": "input",
        "outputTokens": "output",
        "cachedInputTokens": "cached",
        "reasoningOutputTokens": "reasoning",
        "totalTokens": "total",
    }
    if any(
        not isinstance(value.get(source), int)
        or isinstance(value.get(source), bool)
        or value[source] < 0
        for source in fields
    ):
        return None
    return {
        target: value[source]
        for source, target in fields.items()
    }


def import_codex_app_server_trace(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    trace_path: str | Path,
    turn_id: str | None = None,
) -> dict[str, Any]:
    """Import one fully captured public Codex App Server turn event stream."""

    messages = _app_server_trace_messages(trace_path)
    requests: dict[tuple[str, str], dict[str, Any]] = {}
    responses: dict[tuple[str, str], dict[str, Any]] = {}
    notifications: list[dict[str, Any]] = []
    for message in messages:
        identifier = _rpc_id(message.get("id"))
        method = message.get("method")
        if identifier is not None and isinstance(method, str):
            requests[identifier] = message
        elif identifier is not None and (
            "result" in message or "error" in message
        ):
            responses[identifier] = message
        elif isinstance(method, str) and isinstance(message.get("params"), dict):
            notifications.append(message)

    thread_models: dict[str, str] = {}
    thread_reasoning_efforts: dict[str, str] = {}
    turn_requests: list[dict[str, Any]] = []
    for identifier, request in requests.items():
        response = responses.get(identifier)
        if not isinstance(response, dict) or not isinstance(
            response.get("result"),
            dict,
        ):
            continue
        params = request.get("params")
        result = response["result"]
        if not isinstance(params, dict):
            continue
        if request.get("method") == "thread/start":
            thread = result.get("thread")
            model = (
                params.get("model")
                if isinstance(params.get("model"), str)
                and params["model"].strip()
                else result.get("model")
            )
            if (
                isinstance(thread, dict)
                and isinstance(thread.get("id"), str)
                and isinstance(model, str)
                and model.strip()
            ):
                thread_models[thread["id"]] = model.strip()
            reasoning_effort = result.get("reasoningEffort")
            if (
                isinstance(thread, dict)
                and isinstance(thread.get("id"), str)
                and isinstance(reasoning_effort, str)
                and reasoning_effort.strip()
            ):
                thread_reasoning_efforts[thread["id"]] = (
                    reasoning_effort.strip()
                )
        elif request.get("method") == "turn/start":
            turn = result.get("turn")
            thread = params.get("threadId")
            if (
                isinstance(turn, dict)
                and isinstance(turn.get("id"), str)
                and isinstance(thread, str)
            ):
                turn_requests.append(
                    {
                        "turn_id": turn["id"],
                        "thread_id": thread,
                        "requested_model": (
                            params["model"].strip()
                            if isinstance(params.get("model"), str)
                            and params["model"].strip()
                            else thread_models.get(thread)
                        ),
                        "requested_reasoning_effort": (
                            params["effort"].strip()
                            if isinstance(params.get("effort"), str)
                            and params["effort"].strip()
                            else thread_reasoning_efforts.get(thread)
                        ),
                    }
                )
    if turn_id is not None:
        turn_requests = [
            item for item in turn_requests
            if item["turn_id"] == turn_id
        ]
    if len(turn_requests) != 1:
        raise MaestroError(
            "CODEX_APP_SERVER_TURN_AMBIGUOUS",
            "Trace must contain exactly one matching turn/start response; pass --turn-id when needed.",
        )
    selected = turn_requests[0]
    selected_turn = selected["turn_id"]
    selected_thread = selected["thread_id"]
    completion: dict[str, Any] | None = None
    reroutes: list[dict[str, str]] = []
    tokens: dict[str, int] | None = None
    for message in notifications:
        params = message["params"]
        if params.get("threadId") != selected_thread:
            continue
        method = message["method"]
        if method == "turn/completed":
            turn = params.get("turn")
            if isinstance(turn, dict) and turn.get("id") == selected_turn:
                completion = turn
            continue
        if params.get("turnId") != selected_turn:
            continue
        if method == "model/rerouted":
            reroutes.append(
                {
                    "from_model": params.get("fromModel"),
                    "to_model": params.get("toModel"),
                    "reason": params.get("reason"),
                }
            )
        elif method == "thread/tokenUsage/updated":
            usage = params.get("tokenUsage")
            if isinstance(usage, dict):
                observed = _token_summary_from_app_server(usage.get("total"))
                if observed is not None:
                    tokens = observed
    if completion is None or completion.get("status") not in {
        "completed",
        "interrupted",
        "failed",
    }:
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INCOMPLETE",
            "A complete turn/completed notification is required before telemetry is trusted.",
        )
    requested_model = selected["requested_model"]
    applied_model = (
        reroutes[-1]["to_model"]
        if reroutes
        else requested_model
    )
    evidence = (
        "complete"
        if requested_model is not None and applied_model is not None
        else "unavailable"
    )
    turn_duration = completion.get("durationMs")
    if turn_duration is not None and (
        not isinstance(turn_duration, (int, float))
        or isinstance(turn_duration, bool)
        or not math.isfinite(turn_duration)
        or turn_duration < 0
    ):
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INVALID",
            "turn/completed durationMs must be null or a finite non-negative number.",
        )
    recorded = record_host_observation(
        repo_path,
        observation_id=observation_id,
        run_id=run_id,
        source="codex-app-server",
        quality="host_reported",
        correlation_id=f"{selected_thread}:{selected_turn}",
        requested_model=requested_model,
        requested_reasoning_effort=selected[
            "requested_reasoning_effort"
        ],
        applied_model=applied_model if evidence == "complete" else None,
        model_event_evidence=evidence,
        reroutes=reroutes if evidence == "complete" else [],
        tokens=tokens,
        duration_ms=turn_duration,
        trusted_event_stream=True,
    )
    return {
        **recorded,
        "command": "observe-import-codex",
        "turn_status": completion["status"],
        "turn_duration_ms": turn_duration,
        "trace_sha256": sha256_text(canonical_json(messages)),
    }


def complete_run_observation(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    duration_ms: float,
    receipt_intent_digest: str | None = None,
) -> None:
    repo = ensure_repo(repo_path)
    if (
        not isinstance(duration_ms, (int, float))
        or isinstance(duration_ms, bool)
        or not math.isfinite(duration_ms)
        or duration_ms < 0
    ):
        raise MaestroError(
            "RUN_OBSERVATION_DURATION_INVALID",
            "duration-ms must be a finite non-negative number.",
        )
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    with observation_write_lock(target):
        value = _read_observation_file(target)
        if value.get("run_id") != run_id:
            raise MaestroError(
                "RUN_OBSERVATION_INVALID",
                "The in-flight observation does not match this run.",
            )
        if "completed_at" in value:
            if value.get("duration_ms") != duration_ms:
                raise MaestroError(
                    "RUN_OBSERVATION_CONFLICT",
                    "The observation already has a different frozen duration.",
                )
            closure = value.get("completion_closure")
            if (
                isinstance(closure, dict)
                and closure.get("receipt_intent_digest")
                != receipt_intent_digest
            ):
                raise MaestroError(
                    "RUN_RECEIPT_INTENT_CONFLICT",
                    "The sealed execution is bound to a different receipt intent.",
                )
            if not _valid_completion_state(value):
                raise MaestroError(
                    "RUN_OBSERVATION_INVALID",
                    "The sealed completion closure is invalid.",
                )
            return
        if (
            not _valid_plan_summary_for_observation(
                value.get("plan_summary")
            )
            or not _valid_stage_results_for_observation(
                value.get("stage_results"),
                plan_summary=value.get("plan_summary"),
                run_id=run_id,
                observation_id=observation_id,
                work_spans=value.get("work_spans"),
            )
            or not _work_bindings_match_plan(
                value.get("work_spans"),
                value.get("plan_summary"),
            )
            or (
                isinstance(value.get("execution_binding"), dict)
                and value["execution_binding"].get("mode")
                == "maestro_owned_codex_app_server"
                and isinstance(value.get("plan_summary"), dict)
                and value["plan_summary"].get(
                    "execution_receipts_required"
                )
                is not True
            )
        ):
            raise MaestroError(
                "RUN_OBSERVATION_NOT_SEALABLE",
                "The execution-unit plan, receipts, or WorkSpan bindings are invalid.",
            )
        readiness_error = seal_readiness_error(
            value,
            receipt_intent_digest=receipt_intent_digest,
        )
        if readiness_error is not None:
            raise MaestroError(
                "RUN_OBSERVATION_NOT_SEALABLE",
                "The execution cannot be sealed while facts are incomplete: "
                + readiness_error,
            )
        completion = completion_evaluation_for_observation(
            value,
            receipt_intent_digest=receipt_intent_digest,
        )
        completed_at = _timestamp(_utc_now())
        value["completed_at"] = completed_at
        value["duration_ms"] = duration_ms
        payload: dict[str, Any] = {
            "completed_at": completed_at,
            "duration_ms": duration_ms,
        }
        if completion["status"] == "ready":
            closure = completion["closure"]
            assert isinstance(closure, dict)
            value["completion_closure"] = closure
            payload["completion_closure"] = closure
        ledger = ensure_execution_ledger(value)
        ledger, changed = append_execution_event(
            ledger,
            event_type="execution_sealed",
            idempotency_key="execution:seal",
            producer=producer_binding(
                "maestro_core",
                capability="lifecycle_only",
                event_coverage="partial_stream",
            ),
            payload=payload,
            measurement=None,
            recorded_at=completed_at,
        )
        if not changed:
            raise MaestroError(
                "RUN_OBSERVATION_CONFLICT",
                "The execution seal did not advance the observation revision.",
            )
        value["execution_ledger"] = ledger
        if not _valid_completion_state(value):
            raise MaestroError(
                "RUN_OBSERVATION_INVALID",
                "The managed completion closure could not be sealed.",
            )
        atomic_write(target, pretty_json(value).encode("utf-8"))


def inflight_observations(
    repo_path: str | Path,
    *,
    completed_run_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    repo = ensure_repo(repo_path)
    root = safe_target(repo, ".maestro/state/inflight")
    if not root.exists():
        return []
    if not root.is_dir() or root.is_symlink():
        raise MaestroError(
            "RUN_OBSERVATION_STATE_INVALID",
            "The in-flight observation path must be a safe directory.",
        )
    completed = completed_run_ids or set()
    current_project = read_json(
        safe_target(repo, ".maestro/project.json")
    ).get("project_id")
    current_checkout = checkout_id(repo)
    now = _utc_now()
    results: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), reverse=True)[:MAX_INFLIGHT_OBSERVATIONS]:
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            continue
        try:
            value = _read_observation_file(path)
        except MaestroError:
            continue
        started_at = _parse_timestamp(value.get("started_at"))
        run_id = value.get("run_id")
        if (
            value.get("schema_version") != OBSERVATION_VERSION
            or not isinstance(value.get("observation_id"), str)
            or not value["observation_id"]
            or value.get("project_id") != current_project
            or value.get("checkout_id") != current_checkout
            or not isinstance(run_id, str)
            or run_id in completed
            or started_at is None
            or not isinstance(value.get("task_label"), str)
            or not value["task_label"].strip()
            or len(value["task_label"]) > MAX_TASK_LABEL_LENGTH
            or any(
                character in value["task_label"]
                for character in "\r\n\x00"
            )
            or (
                value.get("request_lineage") is not None
                and not validate_request_lineage(
                    value.get("request_lineage"),
                    current_run_id=run_id,
                )
            )
            or not _valid_plan_summary_for_observation(value.get("plan_summary"))
            or (
                isinstance(value.get("execution_binding"), dict)
                and value["execution_binding"].get("mode")
                == "maestro_owned_codex_app_server"
                and isinstance(value.get("plan_summary"), dict)
                and value["plan_summary"].get(
                    "execution_receipts_required"
                )
                is not True
            )
            or not _valid_stage_results_for_observation(
                value.get("stage_results"),
                plan_summary=value.get("plan_summary"),
                run_id=run_id,
                observation_id=value.get("observation_id"),
                work_spans=value.get("work_spans"),
            )
            or not _work_bindings_match_plan(
                value.get("work_spans"),
                value.get("plan_summary"),
            )
            or not _valid_completion_state(value)
        ):
            continue
        try:
            ledger = ensure_execution_ledger(value)
        except MaestroError:
            continue
        completed_at = _parse_timestamp(value.get("completed_at"))
        elapsed = max(0.0, (now - started_at).total_seconds() * 1000)
        measurement_summary = execution_measurements(
            ledger,
            duration_ms=(
                value.get("duration_ms")
                if completed_at is not None
                else round(elapsed, 3)
            ),
        )
        if not validate_execution_measurements(measurement_summary):
            continue
        status_elapsed = max(
            0.0,
            (
                now - (completed_at if completed_at is not None else started_at)
            ).total_seconds()
            * 1000,
        )
        host_observation = value.get("host_observation")
        stage_results = list(value.get("stage_results", []))
        work_spans = list(value.get("work_spans", []))
        plan_summary = value.get("plan_summary")
        assignment_count = (
            len(plan_summary.get("assignments", []))
            if isinstance(plan_summary, dict)
            else 0
        )
        plan_attached_at = _parse_timestamp(value.get("plan_attached_at"))
        host_state = "host_not_connected"
        requested_model = None
        requested_reasoning_effort = None
        if isinstance(host_observation, dict):
            host_state = (
                "host_event_stream_complete"
                if host_observation.get("model_event_evidence")
                == "complete"
                else "host_request_observed"
            )
            requested_model = host_observation.get("requested_model")
            requested_reasoning_effort = host_observation.get(
                "requested_reasoning_effort",
            )
        requested_models = measurement_summary["model"]["requested"]
        requested_efforts = measurement_summary["reasoning_effort"]["requested"]
        if requested_models:
            requested_model = requested_models[-1]
        if requested_efforts:
            requested_reasoning_effort = requested_efforts[-1]
        results.append(
            {
                "observation_id": value.get("observation_id"),
                "run_id": run_id,
                "task_label": value.get("task_label"),
                "started_at": value["started_at"],
                "elapsed_ms": round(elapsed, 3),
                "status": (
                    (
                        "receipt_stale"
                        if status_elapsed > 24 * 60 * 60 * 1000
                        else "receipt_pending"
                    )
                    if completed_at is not None
                    else (
                        "stale"
                        if status_elapsed > 24 * 60 * 60 * 1000
                        else "in_progress"
                    )
                ),
                "completed_at": (
                    value.get("completed_at")
                    if completed_at is not None
                    else None
                ),
                "status_elapsed_ms": round(status_elapsed, 3),
                "plan_summary": value.get("plan_summary"),
                "planning_status": (
                    "attached"
                    if isinstance(plan_summary, dict)
                    else "awaiting_plan"
                ),
                "planning_duration_ms": (
                    round(
                        max(
                            0.0,
                            (
                                plan_attached_at - started_at
                            ).total_seconds()
                            * 1000,
                        ),
                        3,
                    )
                    if plan_attached_at is not None
                    else None
                ),
                "stage_results": stage_results,
                "recorded_stage_count": len(stage_results),
                "planned_stage_count": assignment_count,
                "work_spans": work_spans,
                "recorded_work_count": len(work_spans),
                "host_state": host_state,
                "requested_model": requested_model,
                "requested_reasoning_effort": (
                    requested_reasoning_effort
                ),
                "execution_measurements": measurement_summary,
            }
        )
    return sorted(
        results,
        key=lambda item: item["started_at"],
        reverse=True,
    )


def _valid_execution_contract_summary(value: Any) -> bool:
    if value is None:
        return True
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "kind",
            "execution_plan_id",
            "decision_plan_id",
            "decision_bundle_digest",
        }
        or value.get("kind")
        not in {"direct-route", "decision-enactment"}
    ):
        return False
    bindings = (
        value.get("execution_plan_id"),
        value.get("decision_plan_id"),
        value.get("decision_bundle_digest"),
    )
    if value["kind"] == "direct-route":
        return all(binding is None for binding in bindings)
    return all(
        isinstance(binding, str)
        and len(binding) == 64
        and all(
            character in "0123456789abcdef"
            for character in binding
        )
        for binding in bindings
    )


def _valid_plan_summary_for_observation(value: Any) -> bool:
    if value is None:
        return True
    if not (
        isinstance(value, dict)
        and value.get("schema_version") == "maestro_plan_summary_v1"
        and isinstance(value.get("plan_id"), str)
        and isinstance(value.get("assignments"), list)
        and len(value["assignments"]) <= MAX_PLAN_ASSIGNMENTS
    ):
        return False
    if value.get("risk") is not None and value.get("risk") not in {
        "low",
        "medium",
        "high",
        "critical",
    }:
        return False
    if value.get("depth") is not None and value.get("depth") not in {
        "fast",
        "standard",
        "deep",
    }:
        return False
    if not _valid_execution_contract_summary(
        value.get("execution_contract")
    ):
        return False
    if value.get("execution_receipts_required") not in {None, True}:
        return False
    design_assurance = value.get("design_assurance")
    if design_assurance is not None and (
        not isinstance(design_assurance, dict)
        or set(design_assurance)
        != {
            "profile_id",
            "mode",
            "mutation_gate",
            "verification_gate",
        }
        or design_assurance.get("profile_id")
        != "product-design-evidence-v1"
        or design_assurance.get("mode")
        not in {"compact", "standard", "system"}
        or design_assurance.get("mutation_gate")
        != "design-decision-packet"
        or design_assurance.get("verification_gate")
        != "rendered-verification-pass"
    ):
        return False
    if not validate_plan_execution_units(value):
        return False
    selected_lenses = value.get("selected_lenses")
    if selected_lenses is not None and (
        not isinstance(selected_lenses, list)
        or len(selected_lenses) > 3
        or not all(isinstance(item, str) and item for item in selected_lenses)
    ):
        return False
    for assignment in value["assignments"]:
        if not isinstance(assignment, dict):
            return False
        typed_route_fields = {
            "model_route_id",
            "execution_unit_id",
            "stage_kind",
            "execution_kind",
            "quality_profile",
            "selected_class",
            "quality_floor",
            "fallback_route",
        }
        present_typed_fields = typed_route_fields & set(assignment)
        execution_unit = assignment.get("execution_unit")
        if (
            not isinstance(assignment.get("assignment_id"), str)
            or not isinstance(assignment.get("read_only"), bool)
            or (
                execution_unit is not None
                and (
                    not validate_execution_unit(execution_unit)
                    or execution_unit.get("local_unit_id")
                    != assignment.get("assignment_id")
                    or execution_unit.get("model_route", {}).get(
                        "model_route_id"
                    )
                    != assignment.get("model_route_id")
                )
            )
            or (
                present_typed_fields
                and present_typed_fields != typed_route_fields
            )
            or (
                present_typed_fields
                and (
                    not isinstance(assignment.get("model_route_id"), str)
                    or len(assignment["model_route_id"]) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in assignment["model_route_id"]
                    )
                    or not isinstance(
                        assignment.get("execution_unit_id"),
                        str,
                    )
                    or not assignment["execution_unit_id"]
                    or not isinstance(assignment.get("stage_kind"), str)
                    or not assignment["stage_kind"]
                    or (
                        assignment.get("task_class") is not None
                        and (
                            not isinstance(
                                assignment.get("task_class"),
                                str,
                            )
                            or not assignment["task_class"]
                        )
                    )
                    or assignment.get("execution_kind")
                    not in {"model", "deterministic"}
                    or assignment.get("quality_profile") != "pro-quality"
                    or not isinstance(
                        assignment.get("quality_floor"),
                        dict,
                    )
                    or assignment["quality_floor"].get("failure_action")
                    != "reject-or-reroute"
                    or not isinstance(
                        assignment["quality_floor"].get(
                            "acceptable_routes"
                        ),
                        list,
                    )
                    or (
                        assignment["execution_kind"] == "model"
                        and (
                            not isinstance(
                                assignment.get("selected_class"),
                                str,
                            )
                            or not isinstance(
                                assignment.get("planned_model"),
                                str,
                            )
                            or not isinstance(
                                assignment.get("reasoning_effort"),
                                str,
                            )
                        )
                    )
                    or (
                        assignment["execution_kind"] == "deterministic"
                        and (
                            assignment.get("selected_class") is not None
                            or assignment.get("planned_model") is not None
                            or assignment.get("reasoning_effort") is not None
                            or assignment.get("fallback_route") is not None
                        )
                    )
                )
            )
            or (
                ("may_spawn" in assignment)
                != ("max_children" in assignment)
            )
            or (
                "may_spawn" in assignment
                and (
                    not isinstance(assignment.get("may_spawn"), bool)
                    or not isinstance(assignment.get("max_children"), int)
                    or isinstance(assignment.get("max_children"), bool)
                    or assignment["max_children"] < 0
                    or assignment["max_children"] > 63
                    or (
                        assignment["may_spawn"] is False
                        and assignment["max_children"] != 0
                    )
                    or (
                        assignment["may_spawn"] is True
                        and assignment["max_children"] < 1
                    )
                )
            )
        ):
            return False
    selected_pack_ids = list(
        dict.fromkeys(
            pack_id
            for assignment in value["assignments"]
            if isinstance(assignment, dict)
            for pack_id in assignment.get("expertise_pack_ids", [])
            if isinstance(pack_id, str)
        )
    )
    routing = value.get("expertise_routing")
    if not valid_expertise_routing_summary(
        routing,
        selected_pack_ids=selected_pack_ids,
    ):
        return False
    return valid_route_correction_summary(
        value.get("route_correction"),
        route_attempt=(
            routing.get("route_attempt")
            if isinstance(routing, dict)
            else 1
        ),
    )
