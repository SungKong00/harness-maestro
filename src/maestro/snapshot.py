from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .expertise_lifecycle import expertise_inventory
from .governance import (
    expertise_management_signals,
    govern_report,
    recent_run_events,
)
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


def _run_flow(event: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    plan = event.get("plan_summary")
    host_observation = event.get("host_observation")
    host_model = (
        host_observation.get("actual_model")
        if isinstance(host_observation, dict)
        else None
    )
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
                    "reasoning_effort": None,
                    "actual_model": host_model,
                    "status": event.get("outcome"),
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
        stages.append(
            {
                "assignment_id": assignment.get("assignment_id"),
                "kind": assignment.get("kind"),
                "executor_id": assignment.get("executor_id"),
                "depends_on": list(assignment.get("depends_on", [])),
                "planned_model": assignment.get("planned_model"),
                "reasoning_effort": assignment.get("reasoning_effort"),
                "actual_model": result.get("actual_model"),
                "status": result.get("status", "not_observed"),
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


def _run_card(event: dict[str, Any]) -> dict[str, Any]:
    flow, flow_evidence = _run_flow(event)
    host_observation = event.get("host_observation")
    host_model = (
        host_observation.get("actual_model")
        if isinstance(host_observation, dict)
        else None
    )
    return {
        "run_id": event["run_id"],
        "task_label": event.get("task_label") or event["run_id"],
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
            "planned": _unique_strings(
                [stage.get("planned_model") for stage in flow]
            ),
            "actual": _unique_strings(
                [
                    host_model,
                    *[stage.get("actual_model") for stage in flow],
                ]
            ),
            "estimated": False,
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
            lambda run: bool(run.get("models", {}).get("actual"))
        ),
        "interpretation": (
            "Unmeasured values are kept null and are never estimated."
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
            },
            "attention": status["next_actions"],
            "measurement_coverage": _measurement_coverage([]),
            "runs": [],
            "inflight": [],
            "expertise": {"packs": [], "candidates": []},
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
    runs = [_run_card(event) for event in history["runs"]]
    completed_run_ids = {run["run_id"] for run in runs}
    inflight = inflight_observations(
        repo,
        completed_run_ids=completed_run_ids,
    )
    doctor = status["doctor"]
    assert governance is not None
    expertise = expertise_inventory(repo)
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
            "outcomes": dict(sorted(outcomes.items())),
            "corrections": sum(run["correction_count"] for run in runs),
        },
        "attention": attention,
        "measurement_coverage": _measurement_coverage(runs),
        "runs": runs,
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
