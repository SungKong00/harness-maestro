from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .expertise_lifecycle import expertise_inventory
from .expertise_projection import project_expertise_operations
from .governance import (
    expertise_management_signals,
    govern_report,
    recent_run_events,
)
from .history import history_inventory, run_display_labels
from .observations import inflight_observations
from .snapshot_runs import (
    _measurement_coverage,
    _run_card,
)
from .status import status_report
from .errors import MaestroError
from .util import ensure_repo, safe_target
from .verification import verification_inventory

SNAPSHOT_VERSION = "maestro_snapshot_v1"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stale_registry_governance(error: MaestroError) -> dict[str, Any]:
    return {
        "schema_version": "maestro_govern_report_v1",
        "evidence_status": "stale_registry",
        "runs_considered": 0,
        "scan_truncated": False,
        "candidates_for_review": [],
        "token_summary": {
            "measured_events": 0,
            "total": None,
            "estimated": False,
        },
        "duration_summary": {
            "measured_events": 0,
            "total_ms": None,
            "estimated": False,
        },
        "agent_call_summary": {
            "measured_events": 0,
            "total": None,
            "estimated": False,
        },
        "correction_summary": {
            "total": 0,
            "events_with_corrections": 0,
        },
        "expertise_pack_usage": {},
        "decision_guide_usage": {},
        "expertise_research_modes": {},
        "retention": {
            "format": "daily-jsonl",
            "raw_messages_stored": False,
            "automatic_deletion_supported": False,
            "review_due": False,
        },
        "error": {
            "code": error.code,
            "message": error.message,
        },
        "writes_performed": False,
    }


def _expertise_review_attention(
    review_items: list[dict[str, Any]],
    *,
    excluded_candidate_ids: set[str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str | None, str], dict[str, Any]] = {}
    for item in review_items:
        candidate_id = item.get("candidate_id")
        if candidate_id in excluded_candidate_ids:
            continue
        key = (candidate_id, item["pack_id"])
        group = grouped.setdefault(
            key,
            {
                "id": "review_expertise_component",
                "candidate_id": candidate_id,
                "pack_id": item["pack_id"],
                "guide_ids": [],
                "pack_scope": False,
                "severity": "medium",
                "usage_count": 0,
                "reasons": [],
            },
        )
        guide_id = item.get("guide_id")
        if isinstance(guide_id, str) and guide_id:
            if guide_id not in group["guide_ids"]:
                group["guide_ids"].append(guide_id)
        else:
            group["pack_scope"] = True
        if item.get("utility_verdict") == "review_required":
            group["severity"] = "high"
        group["usage_count"] = max(
            group["usage_count"],
            item.get("usage_count", 0),
        )
        for reason in item.get("reasons", []):
            if reason not in group["reasons"]:
                group["reasons"].append(reason)
    result = []
    for group in grouped.values():
        subject = (
            f"candidate {group['candidate_id']}"
            if group.get("candidate_id")
            else group["pack_id"]
        )
        scope = (
            "Pack-wide criteria"
            if group["pack_scope"]
            else f"{len(group['guide_ids'])} Guide components"
        )
        group["reason"] = (
            f"{subject} reached a review condition for {scope} "
            f"after {group['usage_count']} uses: "
            + "; ".join(group["reasons"])
        )
        result.append(group)
    return sorted(
        result,
        key=lambda item: (
            item["severity"] != "high",
            item["pack_id"],
            item.get("candidate_id") or "",
        ),
    )


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
    governance: dict[str, Any] | None = None
    if initialized:
        try:
            governance = govern_report(repo, window=governance_window)
        except MaestroError as exc:
            if exc.code != "PROJECT_STATE_STALE":
                raise
            governance = _stale_registry_governance(exc)
    status = status_report(
        repo,
        precomputed_governance=(
            governance
            if governance is not None
            and governance.get("evidence_status") != "stale_registry"
            else None
        ),
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
                "execution_active": 0,
                "receipt_pending": 0,
                "stale_observations": 0,
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
                "mode": "isolated_candidate_authoring",
                "expertise_signals": [],
                "automatic_candidate_authoring_allowed": False,
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
    completed_run_ids = set(
        history.get(
            "recorded_run_ids",
            [event["run_id"] for event in history["runs"]],
        )
    )
    inflight = inflight_observations(
        repo,
        completed_run_ids=completed_run_ids,
    )
    doctor = status["doctor"]
    assert governance is not None
    expertise = project_expertise_operations(
        expertise_inventory(repo),
        history["runs"],
    )
    promotion_prompt_candidates = [
        item
        for item in expertise["component_health"]["candidates"]
        if item.get("global_promotion", {}).get("owner_prompt_due")
    ]
    promotion_prompt_candidate_ids = {
        item["candidate_id"]
        for item in promotion_prompt_candidates
    }
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
            "kind": item["kind"],
            "domain": item["domain"],
            "reason": (
                f"{item['kind']} repeated in domain {item['domain']}; "
                "review whether a local candidate should be created or updated."
            ),
        }
        for item in expertise_signals
    )
    attention.extend(
        {
            "id": "ask_global_expertise_promotion",
            "candidate_id": item["candidate_id"],
            "pack_id": item["pack_id"],
            "severity": (
                "high"
                if item["global_promotion"].get(
                    "problem_review_required"
                )
                else "medium"
            ),
            "observed_usage_count": item["global_promotion"][
                "observed_usage_count"
            ],
            "required_usage_count": item["global_promotion"][
                "required_usage_count"
            ],
            "problem_review_required": item["global_promotion"].get(
                "problem_review_required",
                False,
            ),
            "reason": (
                f"{item['pack_id']} candidate reached "
                f"{item['global_promotion']['observed_usage_count']} "
                "distinct runs with observed application; ask the owner whether to apply "
                "it to the Harness bundled Pack source."
            ),
        }
        for item in promotion_prompt_candidates
    )
    attention.extend(
        _expertise_review_attention(
            expertise["component_health"]["review_items"],
            excluded_candidate_ids=promotion_prompt_candidate_ids,
        )
    )
    attention.extend(
        {
            "id": "review_stale_run",
            "run_id": item["run_id"],
            "observation_status": item["status"],
            "severity": "medium",
            "reason": (
                "The completed execution still lacks a final receipt after 24 hours."
                if item["status"] == "receipt_stale"
                else "The run observation has remained open for more than 24 hours."
            ),
        }
        for item in inflight
        if item["status"] in {"stale", "receipt_stale"}
    )

    outcomes = Counter(run["outcome"] for run in runs)
    observation_counts = Counter(item["status"] for item in inflight)
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
            "execution_active": observation_counts["in_progress"],
            "execution_stale": observation_counts["stale"],
            "receipt_pending": observation_counts["receipt_pending"],
            "receipt_stale": observation_counts["receipt_stale"],
            "stale_observations": (
                observation_counts["stale"]
                + observation_counts["receipt_stale"]
            ),
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
            "error": governance.get("error"),
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
            "mode": "isolated_candidate_authoring",
            "expertise_signals": expertise_signals,
            "automatic_candidate_authoring_allowed": bool(
                expertise_signals
            ),
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
