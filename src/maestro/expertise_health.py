from __future__ import annotations

from collections import Counter
from typing import Any

REVIEW_USE_INTERVAL = 5
NEGATIVE_SIGNAL_THRESHOLD = 3


def _guide_runtime(
    events: list[dict[str, Any]],
    *,
    pack_id: str,
    guide_id: str,
) -> dict[str, Any]:
    selected = [
        event
        for event in events
        if pack_id in event.get("selected_expertise_packs", [])
        and guide_id in event.get("selected_decision_guides", [])
    ]
    observations = [
        observation
        for event in events
        for observation in event.get("expertise_observations", [])
        if isinstance(observation, dict)
        and observation.get("pack_id") == pack_id
        and observation.get("guide_id") in {None, guide_id}
    ]
    observation_counts = Counter(
        observation.get("kind")
        for observation in observations
        if isinstance(observation.get("kind"), str)
    )
    critical_count = sum(
        observation.get("severity") == "critical"
        for observation in observations
    )
    failed_count = sum(
        event.get("verifier_result") == "failed"
        for event in selected
    )
    corrected_count = sum(
        isinstance(event.get("correction_count"), int)
        and not isinstance(event.get("correction_count"), bool)
        and event.get("correction_count", 0) > 0
        for event in selected
    )
    negative_count = sum(observation_counts.values())
    use_count = len({event.get("run_id") for event in selected})
    reasons: list[str] = []
    if critical_count:
        reasons.append("critical expertise observation")
    if negative_count >= NEGATIVE_SIGNAL_THRESHOLD:
        reasons.append(
            f"{negative_count} component observations"
        )
    if failed_count >= NEGATIVE_SIGNAL_THRESHOLD:
        reasons.append(
            f"{failed_count} verification failures accompanied selection"
        )
    if corrected_count >= NEGATIVE_SIGNAL_THRESHOLD:
        reasons.append(
            f"{corrected_count} corrected runs accompanied selection"
        )
    if reasons:
        verdict = "review_required"
    elif use_count >= REVIEW_USE_INTERVAL:
        verdict = "review_due"
        reasons.append(
            f"{use_count} measured selections reached the review interval"
        )
    elif use_count:
        verdict = "evidence_gathering"
    else:
        verdict = "awaiting_usage"
    latest_timestamp = max(
        (
            event.get("timestamp")
            for event in selected
            if isinstance(event.get("timestamp"), str)
        ),
        default=None,
    )
    return {
        "usage_count": use_count,
        "selection_count": use_count,
        "last_used_timestamp": latest_timestamp,
        "last_selected_timestamp": latest_timestamp,
        "failed_verification_run_count": failed_count,
        "corrected_run_count": corrected_count,
        "observation_counts": dict(sorted(observation_counts.items())),
        "load_evidence": "host_attestation_unavailable",
        "utility_verdict": verdict,
        "review_due": verdict in {"review_due", "review_required"},
        "review_reasons": reasons,
        "next_usage_review_at": (
            REVIEW_USE_INTERVAL
            if use_count < REVIEW_USE_INTERVAL
            else (
                (use_count // REVIEW_USE_INTERVAL) + 1
            )
            * REVIEW_USE_INTERVAL
        ),
    }


def expertise_component_health(
    inventory: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    packs: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    for pack in inventory.get("packs", []):
        pack_id = pack["expertise_pack_id"]
        guide_health: list[dict[str, Any]] = []
        for guide in pack.get("guides", []):
            runtime = _guide_runtime(
                events,
                pack_id=pack_id,
                guide_id=guide["guide_id"],
            )
            source_refs = guide.get("sources", [])
            item = {
                "guide_id": guide["guide_id"],
                "freshness": guide.get("freshness"),
                "trigger_count": len(guide.get("triggers", [])),
                "source_count": len(source_refs),
                "source_tiers": sorted(
                    {
                        source["tier"]
                        for source in source_refs
                        if isinstance(source.get("tier"), int)
                    }
                ),
                **runtime,
            }
            guide_health.append(item)
            if item["review_due"]:
                review_items.append(
                    {
                        "pack_id": pack_id,
                        "guide_id": item["guide_id"],
                        "utility_verdict": item["utility_verdict"],
                        "usage_count": item["usage_count"],
                        "reasons": item["review_reasons"],
                    }
                )
        pack_usage = len(
            {
                event.get("run_id")
                for event in events
                if pack_id in event.get("selected_expertise_packs", [])
            }
        )
        if any(
            guide["utility_verdict"] == "review_required"
            for guide in guide_health
        ):
            pack_verdict = "review_required"
        elif any(
            guide["utility_verdict"] == "review_due"
            for guide in guide_health
        ):
            pack_verdict = "review_due"
        elif pack_usage:
            pack_verdict = "evidence_gathering"
        else:
            pack_verdict = "awaiting_usage"
        packs.append(
            {
                "pack_id": pack_id,
                "origin": pack.get("origin"),
                "version": pack.get("version"),
                "definition_digest": pack.get("definition_digest"),
                "usage_count": pack_usage,
                "selection_count": pack_usage,
                "trigger_count": len(pack.get("triggers", [])),
                "source_status": pack.get(
                    "source_manifest",
                    {},
                ).get("status", "unavailable"),
                "utility_verdict": pack_verdict,
                "guides": guide_health,
            }
        )
    candidates: list[dict[str, Any]] = []
    for candidate in inventory.get("candidates", []):
        pack_id = candidate.get("expertise_pack_id")
        digest = candidate.get("definition_digest")
        candidate_id = candidate.get("candidate_id")
        if (
            not isinstance(pack_id, str)
            or not isinstance(digest, str)
            or not isinstance(candidate_id, str)
        ):
            continue
        selected = [
            event
            for event in events
            if pack_id in event.get("selected_expertise_packs", [])
            and event.get(
                "expertise_pack_definition_digests",
                {},
            ).get(pack_id)
            == digest
        ]
        usage_count = len(
            {
                event.get("run_id")
                for event in selected
                if isinstance(event.get("run_id"), str)
            }
        )
        recent_runs = [
            {
                "run_id": event["run_id"],
                "task_label": event.get("task_label") or event["run_id"],
                "timestamp": event.get("timestamp"),
                "outcome": event.get("outcome"),
            }
            for event in sorted(
                selected,
                key=lambda item: item.get("timestamp", ""),
                reverse=True,
            )[:3]
            if isinstance(event.get("run_id"), str)
        ]
        candidates.append(
            {
                "candidate_id": candidate_id,
                "pack_id": pack_id,
                "runtime_status": candidate.get("runtime_status"),
                "immediate_use_allowed": candidate.get(
                    "immediate_use_allowed",
                    False,
                ),
                "usage_count": usage_count,
                "recent_runs": recent_runs,
                "last_used_timestamp": max(
                    (
                        event.get("timestamp")
                        for event in selected
                        if isinstance(event.get("timestamp"), str)
                    ),
                    default=None,
                ),
                "failed_verification_run_count": sum(
                    event.get("verifier_result") == "failed"
                    for event in selected
                ),
                "corrected_run_count": sum(
                    isinstance(event.get("correction_count"), int)
                    and not isinstance(
                        event.get("correction_count"),
                        bool,
                    )
                    and event.get("correction_count", 0) > 0
                    for event in selected
                ),
            }
        )
    return {
        "schema_version": "maestro_expertise_component_health_v1",
        "review_use_interval": REVIEW_USE_INTERVAL,
        "negative_signal_threshold": NEGATIVE_SIGNAL_THRESHOLD,
        "packs": packs,
        "candidates": candidates,
        "review_items": review_items,
        "interpretation": (
            "Selection, correction, and verifier co-occurrence are local "
            "review signals, not causal proof that a Guide was loaded, "
            "applied, improved, or harmed the result. Pack lifecycle and "
            "Guide freshness remain independent from this project-local "
            "observation."
        ),
        "automatic_mutation_allowed": False,
    }
