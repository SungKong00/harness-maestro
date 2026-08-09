from __future__ import annotations

from collections import Counter
from typing import Any

from .expertise_usage import expertise_usage_evidence

REVIEW_USE_INTERVAL = 5
NEGATIVE_SIGNAL_THRESHOLD = 3


def _guide_runtime(
    events: list[dict[str, Any]],
    *,
    pack_id: str,
    guide_id: str,
) -> dict[str, Any]:
    usage = expertise_usage_evidence(
        events,
        pack_id=pack_id,
        guide_id=guide_id,
    )
    applied = usage["applied_events"]
    observations = [
        observation
        for event in applied
        for observation in event.get("expertise_observations", [])
        if isinstance(observation, dict)
        and observation.get("pack_id") == pack_id
        and observation.get("guide_id") == guide_id
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
        for event in applied
    )
    corrected_count = sum(
        isinstance(event.get("correction_count"), int)
        and not isinstance(event.get("correction_count"), bool)
        and event.get("correction_count", 0) > 0
        for event in applied
    )
    negative_count = sum(observation_counts.values())
    use_count = usage["application_count"]
    reasons: list[str] = []
    if critical_count:
        reasons.append("critical expertise observation")
    if negative_count >= NEGATIVE_SIGNAL_THRESHOLD:
        reasons.append(
            f"{negative_count} component observations"
        )
    if failed_count >= NEGATIVE_SIGNAL_THRESHOLD:
        reasons.append(
            f"{failed_count} verification failures followed observed application"
        )
    if corrected_count >= NEGATIVE_SIGNAL_THRESHOLD:
        reasons.append(
            f"{corrected_count} corrected runs followed observed application"
        )
    if reasons:
        verdict = "review_required"
    elif use_count >= REVIEW_USE_INTERVAL:
        verdict = "review_due"
        reasons.append(
            f"{use_count} observed applications reached the review interval"
        )
    elif use_count:
        verdict = "evidence_gathering"
    else:
        verdict = "awaiting_usage"
    return {
        "usage_count": use_count,
        "selection_count": usage["selection_count"],
        "assigned_count": usage["assigned_count"],
        "loaded_count": usage["loaded_count"],
        "application_count": usage["application_count"],
        "verified_count": usage["verified_count"],
        "last_used_timestamp": usage["last_applied_timestamp"],
        "last_applied_timestamp": usage["last_applied_timestamp"],
        "last_selected_timestamp": usage["last_selected_timestamp"],
        "failed_verification_run_count": failed_count,
        "corrected_run_count": corrected_count,
        "observation_counts": dict(sorted(observation_counts.items())),
        "load_evidence": (
            "application_observed"
            if usage["application_count"]
            else (
                "host_loaded"
                if usage["loaded_count"]
                else "host_attestation_unavailable"
            )
        ),
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
        pack_usage = expertise_usage_evidence(
            events,
            pack_id=pack_id,
        )
        pack_selected = pack_usage["applied_events"]
        pack_observations = [
            observation
            for event in pack_selected
            for observation in event.get("expertise_observations", [])
            if isinstance(observation, dict)
            and observation.get("pack_id") == pack_id
            and observation.get("guide_id") is None
        ]
        pack_observation_counts = Counter(
            observation.get("kind")
            for observation in pack_observations
            if isinstance(observation.get("kind"), str)
        )
        pack_critical_count = sum(
            observation.get("severity") == "critical"
            for observation in pack_observations
        )
        pack_failed_count = sum(
            event.get("verifier_result") == "failed"
            for event in pack_selected
        )
        pack_corrected_count = sum(
            isinstance(event.get("correction_count"), int)
            and not isinstance(event.get("correction_count"), bool)
            and event.get("correction_count", 0) > 0
            for event in pack_selected
        )
        pack_review_reasons: list[str] = []
        if pack_critical_count:
            pack_review_reasons.append("critical expertise observation")
        if sum(pack_observation_counts.values()) >= NEGATIVE_SIGNAL_THRESHOLD:
            pack_review_reasons.append(
                f"{sum(pack_observation_counts.values())} component observations"
            )
        if pack_failed_count >= NEGATIVE_SIGNAL_THRESHOLD:
            pack_review_reasons.append(
                f"{pack_failed_count} verification failures followed observed application"
            )
        if pack_corrected_count >= NEGATIVE_SIGNAL_THRESHOLD:
            pack_review_reasons.append(
                f"{pack_corrected_count} corrected runs followed observed application"
            )
        if pack_review_reasons:
            pack_verdict = "review_required"
        elif any(
            guide["utility_verdict"] == "review_required"
            for guide in guide_health
        ):
            pack_verdict = "review_required"
        elif any(
            guide["utility_verdict"] == "review_due"
            for guide in guide_health
        ):
            pack_verdict = "review_due"
        elif pack_usage["application_count"]:
            pack_verdict = "evidence_gathering"
        else:
            pack_verdict = "awaiting_usage"
        if pack_review_reasons:
            review_items.append(
                {
                    "pack_id": pack_id,
                    "guide_id": None,
                    "utility_verdict": pack_verdict,
                    "usage_count": pack_usage["application_count"],
                    "reasons": pack_review_reasons,
                }
            )
        packs.append(
            {
                "pack_id": pack_id,
                "origin": pack.get("origin"),
                "version": pack.get("version"),
                "definition_digest": pack.get("definition_digest"),
                "usage_count": pack_usage["application_count"],
                "selection_count": pack_usage["selection_count"],
                "assigned_count": pack_usage["assigned_count"],
                "loaded_count": pack_usage["loaded_count"],
                "application_count": pack_usage["application_count"],
                "verified_count": pack_usage["verified_count"],
                "trigger_count": len(pack.get("triggers", [])),
                "source_status": pack.get(
                    "source_manifest",
                    {},
                ).get("status", "unavailable"),
                "failed_verification_run_count": pack_failed_count,
                "corrected_run_count": pack_corrected_count,
                "observation_counts": dict(
                    sorted(pack_observation_counts.items())
                ),
                "review_reasons": pack_review_reasons,
                "review_due": pack_verdict in {
                    "review_due",
                    "review_required",
                },
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
        component_change = candidate.get("component_change")
        target_guide_id = (
            component_change.get("target_guide_id")
            if isinstance(component_change, dict)
            else None
        )
        component_selected = [
            event
            for event in selected
            if target_guide_id is None
            or target_guide_id
            in event.get("selected_decision_guides", [])
        ]
        pack_usage = expertise_usage_evidence(
            selected,
            pack_id=pack_id,
        )
        component_usage = expertise_usage_evidence(
            component_selected,
            pack_id=pack_id,
            guide_id=target_guide_id,
        )
        usage_count = pack_usage["application_count"]
        component_usage_count = component_usage["application_count"]
        component_applied = component_usage["applied_events"]
        observations = [
            observation
            for event in component_applied
            for observation in event.get(
                "expertise_observations",
                [],
            )
            if isinstance(observation, dict)
            and observation.get("pack_id") == pack_id
            and (
                target_guide_id is None
                or observation.get("guide_id")
                in {None, target_guide_id}
            )
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
            for event in component_applied
        )
        corrected_count = sum(
            isinstance(event.get("correction_count"), int)
            and not isinstance(event.get("correction_count"), bool)
            and event.get("correction_count", 0) > 0
            for event in component_applied
        )
        review_reasons: list[str] = []
        if critical_count:
            review_reasons.append("critical expertise observation")
        if sum(observation_counts.values()) >= NEGATIVE_SIGNAL_THRESHOLD:
            review_reasons.append(
                f"{sum(observation_counts.values())} component observations"
            )
        if failed_count >= NEGATIVE_SIGNAL_THRESHOLD:
            review_reasons.append(
                f"{failed_count} verification failures followed observed application"
            )
        if corrected_count >= NEGATIVE_SIGNAL_THRESHOLD:
            review_reasons.append(
                f"{corrected_count} corrected runs followed observed application"
            )
        disposition = candidate.get("disposition")
        disposed = isinstance(disposition, dict)
        disposition_status = (
            disposition.get("status") if disposed else None
        )
        if disposed:
            utility_verdict = disposition_status
        elif review_reasons:
            utility_verdict = "review_required"
        elif component_usage_count >= REVIEW_USE_INTERVAL:
            utility_verdict = "review_due"
            review_reasons.append(
                f"{component_usage_count} observed applications reached the review interval"
            )
        elif component_usage_count:
            utility_verdict = "evidence_gathering"
        else:
            utility_verdict = "awaiting_usage"
        review_due = utility_verdict in {
            "review_due",
            "review_required",
        }
        global_portability = candidate.get("portability") in {
            "profile",
            "global",
        }
        promotion_decision = candidate.get(
            "promotion_decision",
            {"status": "pending"},
        )
        promotion_declined = (
            isinstance(promotion_decision, dict)
            and promotion_decision.get("status") == "declined"
        )
        runtime_available = candidate.get("runtime_status") in {
            "available",
            "published",
        }
        if not global_portability:
            global_promotion_status = "project_only"
        elif disposed:
            global_promotion_status = disposition_status
        elif not runtime_available:
            global_promotion_status = "candidate_unavailable"
        elif promotion_declined:
            global_promotion_status = "declined"
        elif component_usage_count >= REVIEW_USE_INTERVAL:
            global_promotion_status = "ask_owner"
        else:
            global_promotion_status = "request_available"
        global_request_available = global_promotion_status in {
            "request_available",
            "ask_owner",
        }
        recent_runs = component_usage["recent_applied_runs"]
        candidates.append(
            {
                "candidate_id": candidate_id,
                "pack_id": pack_id,
                "runtime_status": candidate.get("runtime_status"),
                "generation": candidate.get("generation"),
                "component_change": component_change,
                "disposition": candidate.get("disposition"),
                "immediate_use_allowed": candidate.get(
                    "immediate_use_allowed",
                    False,
                ),
                "usage_count": usage_count,
                "component_usage_count": component_usage_count,
                "selection_count": pack_usage["selection_count"],
                "assigned_count": pack_usage["assigned_count"],
                "loaded_count": pack_usage["loaded_count"],
                "application_count": pack_usage["application_count"],
                "verified_count": pack_usage["verified_count"],
                "component_selection_count": component_usage[
                    "selection_count"
                ],
                "component_assigned_count": component_usage[
                    "assigned_count"
                ],
                "component_loaded_count": component_usage["loaded_count"],
                "component_application_count": component_usage[
                    "application_count"
                ],
                "component_verified_count": component_usage[
                    "verified_count"
                ],
                "recent_runs": recent_runs,
                "last_used_timestamp": pack_usage[
                    "last_applied_timestamp"
                ],
                "last_selected_timestamp": pack_usage[
                    "last_selected_timestamp"
                ],
                "failed_verification_run_count": failed_count,
                "corrected_run_count": corrected_count,
                "observation_counts": dict(
                    sorted(observation_counts.items())
                ),
                "utility_verdict": utility_verdict,
                "review_due": review_due,
                "review_reasons": review_reasons,
                "global_promotion": {
                    "status": global_promotion_status,
                    "owner_decision": promotion_decision,
                    "eligibility_basis": (
                        "validated_portable_candidate"
                    ),
                    "recommendation_basis": (
                        "distinct_run_observed_application_count"
                    ),
                    "required_usage_count": REVIEW_USE_INTERVAL,
                    "observed_usage_count": component_usage_count,
                    "remaining_usage_count": max(
                        0,
                        REVIEW_USE_INTERVAL - component_usage_count,
                    ),
                    "request_available": global_request_available,
                    "eligible": global_request_available,
                    "owner_prompt_due": (
                        global_request_available
                        and component_usage_count >= REVIEW_USE_INTERVAL
                    ),
                    "problem_review_required": (
                        utility_verdict == "review_required"
                    ),
                    "automatic_promotion_allowed": False,
                },
                "next_usage_review_at": (
                    REVIEW_USE_INTERVAL
                    if component_usage_count < REVIEW_USE_INTERVAL
                    else (
                        (component_usage_count // REVIEW_USE_INTERVAL)
                        + 1
                    )
                    * REVIEW_USE_INTERVAL
                ),
            }
        )
        if review_due:
            review_items.append(
                {
                    "candidate_id": candidate_id,
                    "pack_id": pack_id,
                    "guide_id": target_guide_id,
                    "utility_verdict": utility_verdict,
                    "usage_count": component_usage_count,
                    "reasons": review_reasons,
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
            "Selection, assignment, loading, observed application, and "
            "verification are separate evidence levels. The five-use "
            "review interval counts only distinct runs with "
            "application_observed work-span evidence. Historical "
            "selection-only runs remain visible but are not upgraded by "
            "inference. These observations are not causal proof that a "
            "Guide improved or harmed the result. Pack lifecycle and "
            "Guide freshness remain "
            "independent from this project-local observation."
        ),
        "automatic_mutation_allowed": False,
    }
