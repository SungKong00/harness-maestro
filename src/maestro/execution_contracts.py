from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .decisions import EXECUTION_PLAN_VERSION, validate_execution_plan
from .errors import MaestroError
from .execution_units import project_route_execution_units
from .planning import ROUTE_V2, validate_route_v2

EXECUTION_CONTEXT_VERSION = "maestro_execution_context_v1"
MODEL_EXECUTION_CONTRACT_VERSION = "maestro_model_execution_contract_v1"


def _invalid_context(
    *,
    code: str,
    message: str,
    path: str = "plan",
    execution_status: str = "INVALID",
) -> dict[str, Any]:
    return {
        "schema_version": EXECUTION_CONTEXT_VERSION,
        "status": "FAIL",
        "execution_status": execution_status,
        "route_plan": None,
        "execution_authorization": None,
        "execution_plan_id": None,
        "decision_plan_id": None,
        "decision_bundle_digest": None,
        "model_execution_units": [],
        "execution_units": [],
        "issues": [
            {
                "code": code,
                "path": path,
                "message": message,
            }
        ],
        "writes_performed": False,
    }


def _model_execution_units(
    route_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Project only Assignment units with an enforceable model contract.

    A Route v2 Assignment already has the bounded read-only or single-writer
    boundary the owned Host can enforce. Other model-bearing workflow
    artifacts are deliberately not normalized here until they have an
    equivalent execution boundary.
    """

    units: list[dict[str, Any]] = []
    for assignment in route_plan.get("assignments", []):
        if (
            not isinstance(assignment, dict)
            or not isinstance(assignment.get("assignment_id"), str)
            or not isinstance(assignment.get("read_only"), bool)
            or not isinstance(assignment.get("mutation_owner"), bool)
        ):
            raise MaestroError(
                "EXECUTION_MODEL_UNIT_UNSAFE",
                "Only a validated bounded Assignment may expose a Host model contract.",
            )
        route = assignment.get("model_route")
        if not isinstance(route, dict):
            raise MaestroError(
                "EXECUTION_MODEL_ROUTE_INVALID",
                "Every model-bearing Assignment requires a validated model route.",
            )
        typed = route.get("schema_version") == "maestro_stage_model_route_v1"
        if not typed:
            raise MaestroError(
                "EXECUTION_MODEL_ROUTE_UPGRADE_REQUIRED",
                (
                    "Legacy model routes remain readable as historical "
                    "artifacts but cannot start a new Host execution without "
                    "a stage-bound quality floor. Re-route the request."
                ),
            )

        execution_kind = route.get("execution_kind")
        if execution_kind == "deterministic":
            continue
        if execution_kind != "model":
            raise MaestroError(
                "EXECUTION_MODEL_ROUTE_INVALID",
                "A typed Assignment route must declare model or deterministic execution.",
            )
        selected_class = route.get("selected_class")
        selected_model = route.get("selected_model")
        reasoning_effort = route.get("reasoning_effort")
        quality_floor = route.get("quality_floor")
        acceptable_routes = (
            quality_floor.get("acceptable_routes")
            if isinstance(quality_floor, dict)
            else None
        )
        selected_pair = {
            "selected_class": selected_class,
            "reasoning_effort": reasoning_effort,
        }
        fallback_route = route.get("fallback_route")
        if (
            not isinstance(route.get("model_route_id"), str)
            or len(route["model_route_id"]) != 64
            or not isinstance(route.get("execution_unit_id"), str)
            or not route["execution_unit_id"]
            or not isinstance(route.get("stage_kind"), str)
            or not route["stage_kind"]
            or route.get("quality_profile") != "pro-quality"
            or not isinstance(selected_class, str)
            or not selected_class
            or not isinstance(selected_model, str)
            or not selected_model
            or not isinstance(reasoning_effort, str)
            or not reasoning_effort
            or not isinstance(acceptable_routes, list)
            or selected_pair not in acceptable_routes
            or quality_floor.get("failure_action") != "reject-or-reroute"
        ):
            raise MaestroError(
                "EXECUTION_MODEL_ROUTE_INVALID",
                "The typed Assignment model route has no enforceable selected route or quality floor.",
            )
        if fallback_route is not None:
            if not isinstance(fallback_route, dict):
                raise MaestroError(
                    "EXECUTION_MODEL_ROUTE_INVALID",
                    "A typed fallback must be an explicitly acceptable model route.",
                )
            fallback_pair = {
                "selected_class": fallback_route.get("selected_class"),
                "reasoning_effort": fallback_route.get(
                    "reasoning_effort"
                ),
            }
            if (
                set(fallback_route)
                != {
                    "selected_class",
                    "selected_model",
                    "reasoning_effort",
                    "trigger",
                }
                or not isinstance(
                    fallback_route.get("selected_class"),
                    str,
                )
                or not isinstance(
                    fallback_route.get("selected_model"),
                    str,
                )
                or not isinstance(
                    fallback_route.get("reasoning_effort"),
                    str,
                )
                or fallback_route.get("trigger")
                != "selected-model-unavailable"
                or fallback_pair not in acceptable_routes
            ):
                raise MaestroError(
                    "EXECUTION_MODEL_ROUTE_INVALID",
                    "A typed fallback must be an explicitly acceptable model route.",
                )
        units.append(
            {
                "schema_version": MODEL_EXECUTION_CONTRACT_VERSION,
                "assignment_id": assignment["assignment_id"],
                "model_route_id": route["model_route_id"],
                "execution_unit_id": route["execution_unit_id"],
                "stage_kind": route["stage_kind"],
                "quality_profile": route["quality_profile"],
                "enforcement": "typed-quality-floor",
                "selected_class": selected_class,
                "selected_model": selected_model,
                "reasoning_effort": reasoning_effort,
                "quality_floor": copy.deepcopy(quality_floor),
                "fallback_route": copy.deepcopy(fallback_route),
            }
        )
    return units


def normalize_execution_contract(
    plan: Any,
    *,
    repo_path: str | Path | None = None,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a direct route or decision enactment at one shared boundary."""

    if not isinstance(plan, dict):
        return _invalid_context(
            code="EXECUTION_CONTRACT_INVALID",
            message="The execution contract must be one object.",
        )
    is_enactment = (
        plan.get("schema_version") == EXECUTION_PLAN_VERSION
    )
    if not is_enactment and plan.get("schema_version") != ROUTE_V2:
        return _invalid_context(
            code="EXECUTION_CONTRACT_UNSUPPORTED",
            message=(
                "Only Route v2 Assignments and validated Decision enactments "
                "have an owned Host execution boundary."
            ),
            path="plan.schema_version",
        )
    try:
        validation = (
            validate_execution_plan(
                plan,
                repo_path=repo_path,
                research_bundle=research_bundle,
            )
            if is_enactment
            else validate_route_v2(
                plan,
                repo_path=repo_path,
                research_bundle=research_bundle,
            )
        )
    except (MaestroError, OSError, TypeError, ValueError) as exc:
        return _invalid_context(
            code="EXECUTION_CONTRACT_INVALID",
            message=str(exc),
        )

    if validation["status"] != "PASS":
        return {
            "schema_version": EXECUTION_CONTEXT_VERSION,
            "status": "FAIL",
            "execution_status": validation.get(
                "execution_status",
                "INVALID",
            ),
            "route_plan": None,
            "execution_authorization": None,
            "execution_plan_id": None,
            "decision_plan_id": None,
            "decision_bundle_digest": None,
            "model_execution_units": [],
            "execution_units": [],
            "issues": copy.deepcopy(validation.get("issues", [])),
            "writes_performed": False,
        }

    route_plan = plan["route_plan"] if is_enactment else plan
    try:
        model_execution_units = _model_execution_units(route_plan)
        common_units = project_route_execution_units(
            plan,
            repo_path=repo_path,
            research_bundle=research_bundle,
        )
    except MaestroError as exc:
        return _invalid_context(
            code=exc.code,
            message=exc.message,
            path="plan.route_plan.assignments" if is_enactment else "plan.assignments",
        )
    common_by_local_id = {
        unit["local_unit_id"]: unit for unit in common_units
    }
    for contract in model_execution_units:
        common = common_by_local_id.get(contract["assignment_id"])
        if common is None or common.get("execution_status") != "READY":
            return _invalid_context(
                code="EXECUTION_MODEL_UNIT_UNSAFE",
                message=(
                    "The validated Assignment did not produce one exact "
                    "Host-executable common ExecutionUnit."
                ),
                path=(
                    "plan.route_plan.assignments"
                    if is_enactment
                    else "plan.assignments"
                ),
            )
        contract["common_execution_unit_id"] = common["unit_id"]
        contract["common_execution_unit_digest"] = common["unit_digest"]
        contract["execution_unit"] = copy.deepcopy(common)
    authorization = None
    if is_enactment:
        source = plan["execution_authorization"]
        authorization = {
            "schema_version": "maestro_execution_authorization_v1",
            "execution_plan_id": plan["execution_plan_id"],
            "decision_plan_id": plan["decision_plan_id"],
            "decision_bundle_digest": plan["decision_bundle_digest"],
            "authorization_source": source["authorization_source"],
            "allowed_side_effects": copy.deepcopy(
                source["allowed_side_effects"]
            ),
            "allowed_paths": copy.deepcopy(source["allowed_paths"]),
            "prohibited_changes": copy.deepcopy(
                source["prohibited_changes"]
            ),
            "status": source["status"],
        }
    return {
        "schema_version": EXECUTION_CONTEXT_VERSION,
        "status": "PASS",
        "execution_status": validation.get("execution_status", "READY"),
        "route_plan": copy.deepcopy(route_plan),
        "execution_authorization": authorization,
        "execution_plan_id": (
            plan["execution_plan_id"] if is_enactment else None
        ),
        "decision_plan_id": (
            plan["decision_plan_id"] if is_enactment else None
        ),
        "decision_bundle_digest": (
            plan["decision_bundle_digest"] if is_enactment else None
        ),
        "model_execution_units": model_execution_units,
        "execution_units": common_units,
        "issues": [],
        "writes_performed": False,
    }
