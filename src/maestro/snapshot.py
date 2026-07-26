from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .expertise_health import expertise_component_health
from .expertise_lifecycle import expertise_inventory
from .governance import (
    expertise_management_signals,
    govern_report,
    recent_run_events,
)
from .history import history_inventory, run_display_labels
from .observations import inflight_observations
from .status import status_report
from .errors import MaestroError
from .util import ensure_repo, safe_target
from .verification import verification_inventory

SNAPSHOT_VERSION = "maestro_snapshot_v1"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _unique_strings(values: list[Any]) -> list[str]:
    return list(
        dict.fromkeys(
            value
            for value in values
            if isinstance(value, str) and value
        )
    )


def _host_model_provenance(
    host_observation: Any,
) -> dict[str, Any]:
    result = {
        "requested": None,
        "requested_reasoning_effort": None,
        "reasoning_effort_evidence": "unavailable",
        "applied": None,
        "evidence": "unavailable",
        "reroutes": [],
        "legacy_reported": None,
    }
    if not isinstance(host_observation, dict):
        return result
    if host_observation.get("schema_version") == "maestro_host_observation_v2":
        result["requested"] = host_observation.get("requested_model")
        result["requested_reasoning_effort"] = host_observation.get(
            "requested_reasoning_effort",
        )
        result["reasoning_effort_evidence"] = host_observation.get(
            "reasoning_effort_evidence",
            "unavailable",
        )
        result["evidence"] = host_observation.get(
            "model_event_evidence",
            "unavailable",
        )
        result["reroutes"] = list(host_observation.get("reroutes", []))
        if result["evidence"] == "complete":
            result["applied"] = host_observation.get("applied_model")
        return result
    if host_observation.get("schema_version") == "maestro_host_observation_v1":
        result["legacy_reported"] = host_observation.get("actual_model")
    return result


def _run_flow(event: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    plan = event.get("plan_summary")
    host_observation = event.get("host_observation")
    host_models = _host_model_provenance(host_observation)
    stage_results = {
        item["assignment_id"]: item
        for item in event.get("stage_results", [])
        if isinstance(item, dict) and isinstance(item.get("assignment_id"), str)
    }
    if not isinstance(plan, dict):
        return (
            [
                {
                    "assignment_id": "execution-summary",
                    "kind": "summary",
                    "executor_id": event.get("primary_executor_id"),
                    "depends_on": [],
                    "planned_model": None,
                    "route_recommended_model": None,
                    "reasoning_effort": None,
                    "actual_model": host_models["applied"],
                    "applied_model": host_models["applied"],
                    "model_evidence": host_models["evidence"],
                    "status": event.get("outcome"),
                    "status_evidence": "run_receipt",
                    "duration_ms": event.get("duration_ms"),
                    "tokens": event.get("tokens"),
                    "evidence_refs": list(event.get("evidence_refs", []))[:3],
                    "expertise_pack_ids": list(
                        event.get("selected_expertise_packs", [])
                    ),
                    "decision_guide_ids": list(
                        event.get("selected_decision_guides", [])
                    ),
                }
            ],
            "summary_only",
        )

    stages: list[dict[str, Any]] = []
    for assignment in plan.get("assignments", []):
        result = stage_results.get(assignment.get("assignment_id"), {})
        stage_observed = bool(result)
        model_evidence = result.get("model_evidence", "unavailable")
        applied_model = (
            result.get("actual_model")
            if model_evidence == "complete"
            else None
        )
        stages.append(
            {
                "assignment_id": assignment.get("assignment_id"),
                "kind": assignment.get("kind"),
                "executor_id": assignment.get("executor_id"),
                "depends_on": list(assignment.get("depends_on", [])),
                "planned_model": assignment.get("planned_model"),
                "route_recommended_model": assignment.get("planned_model"),
                "reasoning_effort": assignment.get("reasoning_effort"),
                "actual_model": applied_model,
                "applied_model": applied_model,
                "model_evidence": model_evidence,
                "status": result.get("status", "planned_only"),
                "status_evidence": (
                    "host_stage_result" if stage_observed else "plan_only"
                ),
                "duration_ms": result.get("duration_ms"),
                "tokens": result.get("tokens"),
                "evidence_refs": list(result.get("evidence_refs", []))[:3],
                "expertise_pack_ids": list(
                    assignment.get("expertise_pack_ids", [])
                ),
                "decision_guide_ids": list(
                    assignment.get("decision_guide_ids", [])
                ),
            }
        )
    return stages, "assignment_observation"


def _run_card(
    event: dict[str, Any],
    display_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    flow, flow_evidence = _run_flow(event)
    host_observation = event.get("host_observation")
    host_models = _host_model_provenance(host_observation)
    event_id = event["event_id"]
    original_task_label = event.get("task_label") or event["run_id"]
    task_label = (display_labels or {}).get(
        event_id,
        original_task_label,
    )
    route_recommended = _unique_strings(
        [stage.get("route_recommended_model") for stage in flow]
    )
    route_recommended_effort = _unique_strings(
        [stage.get("reasoning_effort") for stage in flow]
    )
    applied = _unique_strings(
        [
            host_models["applied"],
            *[stage.get("applied_model") for stage in flow],
        ]
    )
    return {
        "event_id": event_id,
        "run_id": event["run_id"],
        "task_label": task_label,
        "original_task_label": original_task_label,
        "timestamp": event["timestamp"],
        "risk": event["risk"],
        "route_depth": event["route_depth"],
        "outcome": event["outcome"],
        "verifier_result": event["verifier_result"],
        "duration_ms": event.get("duration_ms"),
        "tokens": event.get("tokens"),
        "agent_calls": event.get("agent_calls"),
        "correction_count": event.get("correction_count", 0),
        "correction_summary": list(event.get("correction_summary", [])),
        "models": {
            "requested": _unique_strings([host_models["requested"]]),
            "requested_reasoning_effort": _unique_strings(
                [host_models["requested_reasoning_effort"]]
            ),
            "applied": applied,
            "route_recommended": route_recommended,
            "route_recommended_reasoning_effort": (
                route_recommended_effort
            ),
            "reasoning_effort_evidence": host_models[
                "reasoning_effort_evidence"
            ],
            "model_event_evidence": host_models["evidence"],
            "reroutes": host_models["reroutes"],
            "legacy_reported": _unique_strings(
                [host_models["legacy_reported"]]
            ),
            "planned": route_recommended,
            "actual": applied,
            "estimated": False,
            "measurement_state": (
                "host_not_connected"
                if host_observation is None
                else (
                    "host_event_stream_complete"
                    if host_models["evidence"] == "complete"
                    else "host_request_observed"
                )
            ),
        },
        "host_observation": host_observation,
        "flow_evidence": flow_evidence,
        "flow": flow,
        "lenses": list(event.get("selected_lenses", [])),
        "expertise": {
            "packs": list(event.get("selected_expertise_packs", [])),
            "guides": list(event.get("selected_decision_guides", [])),
            "research_mode": event.get("expertise_research_mode", "reuse"),
            "research_gate": event.get(
                "expertise_research_gate",
                "not-required",
            ),
            "observations": list(event.get("expertise_observations", [])),
        },
        "conventions": event.get("convention_usage"),
        "evidence_refs": list(event.get("evidence_refs", []))[:8],
    }


def _measurement_coverage(runs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(runs)

    def measured(predicate: Any) -> dict[str, Any]:
        count = sum(bool(predicate(run)) for run in runs)
        return {
            "measured_runs": count,
            "total_runs": total,
            "ratio": round(count / total, 3) if total else None,
        }

    return {
        "task_label": measured(
            lambda run: run["task_label"] != run["run_id"]
        ),
        "duration": measured(lambda run: run.get("duration_ms") is not None),
        "tokens": measured(lambda run: isinstance(run.get("tokens"), dict)),
        "plan": measured(
            lambda run: run.get("flow_evidence") == "assignment_observation"
        ),
        "actual_model": measured(
            lambda run: bool(run.get("models", {}).get("applied"))
        ),
        "requested_model": measured(
            lambda run: bool(run.get("models", {}).get("requested"))
        ),
        "requested_reasoning_effort": measured(
            lambda run: bool(
                run.get("models", {}).get(
                    "requested_reasoning_effort",
                )
            )
        ),
        "interpretation": (
            "측정되지 않은 값은 추정하지 않는다. 공개 Host 요청 메타데이터는 "
            "요청값만, 완료 이벤트 구간은 적용 모델과 토큰까지 표시한다."
        ),
    }


def snapshot_report(
    repo_path: str | Path,
    *,
    window: int = 20,
) -> dict[str, Any]:
    if (
        not isinstance(window, int)
        or isinstance(window, bool)
        or window < 1
        or window > 100
    ):
        raise MaestroError(
            "WINDOW_INVALID",
            "Viewer run window must be an integer from 1 to 100.",
        )
    repo = ensure_repo(repo_path)
    initialized = all(
        safe_target(repo, path).is_file()
        for path in (
            ".maestro/project.json",
            ".maestro/managed.json",
            ".maestro/lock.json",
        )
    )
    governance_window = max(window, 3)
    governance = (
        govern_report(repo, window=governance_window)
        if initialized
        else None
    )
    status = status_report(
        repo,
        precomputed_governance=governance,
    )
    if not status["initialized"]:
        return {
            "schema_version": SNAPSHOT_VERSION,
            "generated_at": _utc_timestamp(),
            "repo_root": str(repo),
            "project_id": None,
            "window": window,
            "overview": {
                "readiness": status["readiness"]["state"],
                "doctor": status["doctor"]["status"],
                "runs": 0,
                "inflight": 0,
                "attention": len(status["next_actions"]),
                "history_bundles": 0,
            },
            "attention": status["next_actions"],
            "measurement_coverage": _measurement_coverage([]),
            "runs": [],
            "history_bundles": [],
            "inflight": [],
            "expertise": {
                "packs": [],
                "candidates": [],
                "component_health": {
                    "schema_version": "maestro_expertise_component_health_v1",
                    "review_use_interval": 5,
                    "negative_signal_threshold": 3,
                    "packs": [],
                    "review_items": [],
                    "automatic_mutation_allowed": False,
                },
            },
            "governance": status["governance"],
            "doctor": status["doctor"],
            "status": status,
            "automation": {
                "mode": "review_recommendation_only",
                "expertise_signals": [],
                "automatic_mutation_allowed": False,
            },
            "verification": {
                "candidates": [],
                "approval_mode": "preview_then_apply",
                "executes_commands": False,
            },
            "writes_performed": False,
        }

    history = recent_run_events(repo, window=window)
    labels = run_display_labels(repo)
    history_state = history_inventory(repo)
    bundled_event_ids = set(history_state["bundled_event_ids"])
    history_bundles = []
    for bundle in history_state["bundles"]:
        rendered = dict(bundle)
        rendered["runs"] = [
            {
                **run,
                "task_label": labels.get(
                    run["event_id"],
                    run["task_label"],
                ),
            }
            for run in bundle["runs"]
        ]
        history_bundles.append(rendered)
    runs = [
        _run_card(event, labels)
        for event in history["runs"]
        if event["event_id"] not in bundled_event_ids
    ]
    completed_run_ids = {
        event["run_id"] for event in history["runs"]
    }
    inflight = inflight_observations(
        repo,
        completed_run_ids=completed_run_ids,
    )
    doctor = status["doctor"]
    assert governance is not None
    expertise = expertise_inventory(repo)
    expertise["component_health"] = expertise_component_health(
        expertise,
        history["runs"],
    )
    verification = verification_inventory(repo)
    expertise_signals = expertise_management_signals(history["runs"])

    attention: list[dict[str, Any]] = [
        item
        for item in status["next_actions"]
        if item.get("id") != "review_governance_candidates"
    ]
    attention.extend(
        {
            "id": "review_governance_candidate",
            "fingerprint": item["fingerprint"],
            "severity": item["severity"],
            "occurrences": item["occurrences"],
            "reason": item["next_step"],
        }
        for item in governance["candidates_for_review"]
    )
    attention.extend(
        {
            "id": "review_expertise_signal",
            "fingerprint": item["fingerprint"],
            "severity": item["severity"],
            "occurrences": item["occurrences"],
            "reason": (
                f"{item['kind']} repeated in domain {item['domain']}; "
                "review whether a local candidate should be created or updated."
            ),
        }
        for item in expertise_signals
    )
    attention.extend(
        {
            "id": "review_expertise_component",
            "pack_id": item["pack_id"],
            "guide_id": item["guide_id"],
            "severity": (
                "high"
                if item["utility_verdict"] == "review_required"
                else "medium"
            ),
            "reason": (
                f"{item['pack_id']}/{item['guide_id']} reached a component "
                f"review condition after {item['usage_count']} uses: "
                + "; ".join(item["reasons"])
            ),
        }
        for item in expertise["component_health"]["review_items"]
    )
    attention.extend(
        {
            "id": "review_stale_run",
            "run_id": item["run_id"],
            "severity": "medium",
            "reason": "The run observation has remained open for more than 24 hours.",
        }
        for item in inflight
        if item["status"] == "stale"
    )

    outcomes = Counter(run["outcome"] for run in runs)
    return {
        "schema_version": SNAPSHOT_VERSION,
        "generated_at": _utc_timestamp(),
        "repo_root": str(repo),
        "project_id": status["project_id"],
        "window": window,
        "overview": {
            "readiness": status["readiness"]["state"],
            "doctor": doctor["status"],
            "runs": len(runs),
            "inflight": len(inflight),
            "attention": len(attention),
            "history_bundles": len(history_bundles),
            "outcomes": dict(sorted(outcomes.items())),
            "corrections": sum(run["correction_count"] for run in runs),
        },
        "attention": attention,
        "measurement_coverage": _measurement_coverage(runs),
        "runs": runs,
        "history_bundles": history_bundles,
        "inflight": inflight,
        "expertise": expertise,
        "governance": {
            "window": governance_window,
            "evidence_status": governance["evidence_status"],
            "runs_considered": governance["runs_considered"],
            "scan_truncated": governance["scan_truncated"],
            "candidates_for_review": governance["candidates_for_review"],
            "token_summary": governance["token_summary"],
            "duration_summary": governance["duration_summary"],
            "agent_call_summary": governance["agent_call_summary"],
            "correction_summary": governance["correction_summary"],
            "expertise_pack_usage": governance["expertise_pack_usage"],
            "decision_guide_usage": governance.get(
                "decision_guide_usage",
                {},
            ),
            "expertise_research_modes": governance[
                "expertise_research_modes"
            ],
            "retention": governance["retention"],
        },
        "doctor": doctor,
        "status": status,
        "automation": {
            "mode": "review_recommendation_only",
            "expertise_signals": expertise_signals,
            "automatic_mutation_allowed": False,
        },
        "verification": {
            "candidates": verification["candidates"],
            "approval_mode": "preview_then_apply",
            "executes_commands": False,
        },
        "history_evidence_status": history["evidence_status"],
        "writes_performed": False,
    }
