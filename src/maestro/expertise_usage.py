from __future__ import annotations

from typing import Any

TERMINAL_WORK_STATUSES = {
    "completed",
    "failed",
    "blocked",
    "interrupted",
}
LOADED_EXPERTISE_EVIDENCE = {
    "host_loaded",
    "application_observed",
}
APPLIED_EXPERTISE_EVIDENCE = {"application_observed"}


def _run_id(event: dict[str, Any]) -> str | None:
    value = event.get("run_id")
    return value if isinstance(value, str) and value else None


def _selected(
    event: dict[str, Any],
    *,
    pack_id: str,
    guide_id: str | None,
) -> bool:
    if pack_id not in event.get("selected_expertise_packs", []):
        return False
    return (
        guide_id is None
        or guide_id in event.get("selected_decision_guides", [])
    )


def _assigned(
    event: dict[str, Any],
    *,
    pack_id: str,
    guide_id: str | None,
) -> bool:
    plan = event.get("plan_summary")
    if not isinstance(plan, dict):
        return False
    for assignment in plan.get("assignments", []):
        if (
            isinstance(assignment, dict)
            and pack_id in assignment.get("expertise_pack_ids", [])
            and (
                guide_id is None
                or guide_id in assignment.get("decision_guide_ids", [])
            )
        ):
            return True
    return False


def _span_matches(
    span: dict[str, Any],
    *,
    pack_id: str,
    guide_id: str | None,
) -> bool:
    return (
        span.get("status") in TERMINAL_WORK_STATUSES
        and pack_id in span.get("expertise_pack_ids", [])
        and (
            guide_id is None
            or guide_id in span.get("decision_guide_ids", [])
        )
    )


def _observed(
    event: dict[str, Any],
    *,
    pack_id: str,
    guide_id: str | None,
    accepted_evidence: set[str],
) -> bool:
    return any(
        isinstance(span, dict)
        and _span_matches(
            span,
            pack_id=pack_id,
            guide_id=guide_id,
        )
        and span.get("expertise_evidence") in accepted_evidence
        for span in event.get("work_spans", [])
    )


def expertise_usage_evidence(
    events: list[dict[str, Any]],
    *,
    pack_id: str,
    guide_id: str | None = None,
) -> dict[str, Any]:
    """Project distinct-run Expertise evidence without deciding lifecycle policy."""

    selected_events = [
        event
        for event in events
        if _run_id(event) is not None
        and _selected(event, pack_id=pack_id, guide_id=guide_id)
    ]
    assigned_events = [
        event
        for event in selected_events
        if _assigned(event, pack_id=pack_id, guide_id=guide_id)
    ]
    loaded_events = [
        event
        for event in selected_events
        if _observed(
            event,
            pack_id=pack_id,
            guide_id=guide_id,
            accepted_evidence=LOADED_EXPERTISE_EVIDENCE,
        )
    ]
    applied_events = [
        event
        for event in selected_events
        if _observed(
            event,
            pack_id=pack_id,
            guide_id=guide_id,
            accepted_evidence=APPLIED_EXPERTISE_EVIDENCE,
        )
    ]
    verified_events = [
        event
        for event in applied_events
        if event.get("verifier_result") == "passed"
    ]

    def distinct_count(items: list[dict[str, Any]]) -> int:
        return len({_run_id(item) for item in items})

    recent_runs = [
        {
            "run_id": event["run_id"],
            "task_label": event.get("task_label") or event["run_id"],
            "timestamp": event.get("timestamp"),
            "outcome": event.get("outcome"),
            "verifier_result": event.get("verifier_result"),
        }
        for event in sorted(
            applied_events,
            key=lambda item: item.get("timestamp", ""),
            reverse=True,
        )[:3]
    ]
    latest_applied_timestamp = max(
        (
            event.get("timestamp")
            for event in applied_events
            if isinstance(event.get("timestamp"), str)
        ),
        default=None,
    )
    latest_selected_timestamp = max(
        (
            event.get("timestamp")
            for event in selected_events
            if isinstance(event.get("timestamp"), str)
        ),
        default=None,
    )
    return {
        "selection_count": distinct_count(selected_events),
        "assigned_count": distinct_count(assigned_events),
        "loaded_count": distinct_count(loaded_events),
        "application_count": distinct_count(applied_events),
        "verified_count": distinct_count(verified_events),
        "last_selected_timestamp": latest_selected_timestamp,
        "last_applied_timestamp": latest_applied_timestamp,
        "recent_applied_runs": recent_runs,
        "selected_events": selected_events,
        "applied_events": applied_events,
    }
