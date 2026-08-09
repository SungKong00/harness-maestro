from __future__ import annotations

import copy
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .errors import MaestroError
from .util import canonical_json, sha256_text


MODEL_FEEDBACK_REPORT_VERSION = "maestro_model_feedback_report_v1"
MODEL_POLICY_OVERLAY_VERSION = "maestro_model_policy_overlay_v1"
VERIFICATION_ASSESSMENT_VERSION = "maestro_verification_assessment_v1"
DEFAULT_CONFIDENCE_LEVEL = 0.95
DEFAULT_MIN_ELIGIBLE_SAMPLES = 20
DEFAULT_MIN_FAILURES = 3
DEFAULT_MAX_ACCEPTABLE_FAILURE_RATE = 0.10
DEFAULT_EVIDENCE_WINDOW = 200
_Z_95 = 1.959963984540054
_DIGEST = re.compile(r"^[a-f0-9]{64}$")


def _policy_authority_digest(
    *,
    minimum_eligible_samples: int,
    minimum_failures: int,
    max_acceptable_failure_rate: float,
    evidence_window: int,
    source_complete: bool,
) -> str:
    return sha256_text(
        canonical_json(
            {
                "schema_version": "maestro_model_policy_authority_v1",
                "quality_profile": "pro-quality",
                "feedback_policy": {
                    "confidence_level": DEFAULT_CONFIDENCE_LEVEL,
                    "minimum_eligible_samples": minimum_eligible_samples,
                    "minimum_failures": minimum_failures,
                    "max_acceptable_failure_rate": (
                        max_acceptable_failure_rate
                    ),
                    "evidence_window": evidence_window,
                    "source_complete": source_complete,
                    "max_escalation_steps": 1,
                    "automatic_downgrade_allowed": False,
                },
                "class_steps": [
                    ["economy", "balanced"],
                    ["balanced", "frontier"],
                ],
            }
        )
    )


MODEL_POLICY_AUTHORITY_DIGEST = _policy_authority_digest(
    minimum_eligible_samples=DEFAULT_MIN_ELIGIBLE_SAMPLES,
    minimum_failures=DEFAULT_MIN_FAILURES,
    max_acceptable_failure_rate=DEFAULT_MAX_ACCEPTABLE_FAILURE_RATE,
    evidence_window=DEFAULT_EVIDENCE_WINDOW,
    source_complete=True,
)


def _digest(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload[field] = ""
    return sha256_text(canonical_json(payload))


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _is_checkout_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[a-f0-9]{12}", value) is not None
    )


def _line(value: Any, maximum: int = 240) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and not any(character in value for character in "\r\n\x00")
    )


def wilson_interval(
    failures: int,
    samples: int,
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> tuple[float | None, float | None]:
    """Return a deterministic two-sided Wilson score interval."""

    if (
        not isinstance(failures, int)
        or isinstance(failures, bool)
        or not isinstance(samples, int)
        or isinstance(samples, bool)
        or failures < 0
        or samples < 0
        or failures > samples
        or confidence_level != DEFAULT_CONFIDENCE_LEVEL
    ):
        raise MaestroError(
            "MODEL_FEEDBACK_SAMPLE_INVALID",
            "Wilson inputs need 0 <= failures <= samples and confidence_level=0.95.",
        )
    if samples == 0:
        return None, None
    proportion = failures / samples
    z_squared = _Z_95 * _Z_95
    denominator = 1.0 + z_squared / samples
    center = (proportion + z_squared / (2.0 * samples)) / denominator
    margin = (
        _Z_95
        * math.sqrt(
            proportion * (1.0 - proportion) / samples
            + z_squared / (4.0 * samples * samples)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def validate_verification_assessment(
    value: Any,
    *,
    plan_summary: dict[str, Any] | None = None,
    verifier_stage: dict[str, Any] | None = None,
) -> bool:
    fields = {
        "schema_version",
        "assessment_id",
        "packet_digest",
        "verifier_assignment_id",
        "target_assignment_id",
        "target_execution_unit_id",
        "target_model_route_id",
        "verdict",
        "failure_cause",
        "failure_categories",
        "evidence_refs",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema_version") != VERIFICATION_ASSESSMENT_VERSION
        or not _is_digest(value.get("assessment_id"))
        or value["assessment_id"] != _digest(value, "assessment_id")
        or not _is_digest(value.get("packet_digest"))
        or not _line(value.get("verifier_assignment_id"), 96)
        or not _line(value.get("target_assignment_id"), 96)
        or not _line(value.get("target_execution_unit_id"), 96)
        or not _is_digest(value.get("target_model_route_id"))
        or value.get("verdict")
        not in {"passed", "failed", "inconclusive"}
        or value.get("failure_cause")
        not in {
            "none",
            "implementation",
            "specification",
            "environment",
            "tooling",
            "unknown",
        }
        or not isinstance(value.get("failure_categories"), list)
        or len(value["failure_categories"]) > 8
        or len(value["failure_categories"])
        != len(set(value["failure_categories"]))
        or any(
            category
            not in {
                "correctness",
                "integration",
                "security",
                "regression",
                "performance",
                "contract",
                "test-infrastructure",
                "specification",
                "unknown",
            }
            for category in value["failure_categories"]
        )
        or not isinstance(value.get("evidence_refs"), list)
        or not value["evidence_refs"]
        or len(value["evidence_refs"]) > 10
        or len(value["evidence_refs"]) != len(set(value["evidence_refs"]))
        or any(not _line(ref) for ref in value["evidence_refs"])
    ):
        return False
    if value["verdict"] == "passed" and (
        value["failure_cause"] != "none"
        or value["failure_categories"]
    ):
        return False
    if value["verdict"] == "failed" and (
        value["failure_cause"] in {"none", "unknown"}
        or not value["failure_categories"]
    ):
        return False
    if value["verdict"] == "inconclusive" and value[
        "failure_cause"
    ] not in {"specification", "environment", "tooling", "unknown"}:
        return False
    if plan_summary is None:
        target_valid = True
    else:
        from .assignment_contracts import expected_verification_target

        expected = expected_verification_target(
            plan_summary,
            value["verifier_assignment_id"],
        )
        target_valid = (
            isinstance(expected, dict)
            and expected.get("assignment_id")
            == value["target_assignment_id"]
            and expected.get("execution_unit_id")
            == value["target_execution_unit_id"]
            and expected.get("model_route_id")
            == value["target_model_route_id"]
        )
    if not target_valid:
        return False
    if verifier_stage is None:
        return True
    receipt = verifier_stage.get("execution_unit_receipt")
    return (
        isinstance(receipt, dict)
        and receipt.get("output_packet_digest") == value["packet_digest"]
        and receipt.get("verification_assessment_id")
        == value["assessment_id"]
        and (
            "assignment-packet:"
            + value["packet_digest"]
        )
        in verifier_stage.get("evidence_refs", [])
    )


def _metric(samples: int, failures: int) -> dict[str, Any]:
    lower, upper = wilson_interval(failures, samples)
    return {
        "sample_count": samples,
        "failure_count": failures,
        "failure_rate": failures / samples if samples else None,
        "interval": {
            "method": "wilson",
            "confidence_level": DEFAULT_CONFIDENCE_LEVEL,
            "lower": lower,
            "upper": upper,
        },
    }


def _group_key(
    event: dict[str, Any],
    assignment: dict[str, Any],
) -> tuple[Any, ...]:
    return (
        assignment.get("quality_profile"),
        assignment.get("stage_kind"),
        assignment.get("task_class"),
        assignment.get("selected_class"),
        assignment.get("planned_model"),
        assignment.get("reasoning_effort"),
        event.get("risk"),
    )


def _subject(
    event: dict[str, Any],
    assignment: dict[str, Any],
) -> dict[str, Any]:
    return {
        "quality_profile": assignment.get("quality_profile"),
        "stage_kind": assignment.get("stage_kind"),
        "task_class": assignment.get("task_class"),
        "selected_class": assignment.get("selected_class"),
        "selected_model": assignment.get("planned_model"),
        "reasoning_effort": assignment.get("reasoning_effort"),
        "risk": event.get("risk"),
    }


def _safe_escalation_target(
    assignment: dict[str, Any],
) -> dict[str, Any] | None:
    selected_class = assignment.get("selected_class")
    fallback = assignment.get("fallback_route")
    if selected_class == "economy" and isinstance(fallback, dict):
        return {
            "selected_class": "balanced",
            "selected_model": fallback.get("selected_model"),
            "reasoning_effort": "high",
        }
    if selected_class == "balanced" and isinstance(fallback, dict):
        return {
            "selected_class": "frontier",
            "selected_model": fallback.get("selected_model"),
            "reasoning_effort": "high",
        }
    return None


def _advice(
    *,
    attributed: dict[str, Any],
    assignment: dict[str, Any],
    min_eligible_samples: int,
    min_failures: int,
    max_acceptable_failure_rate: float,
) -> dict[str, Any]:
    sample_count = attributed["sample_count"]
    failure_count = attributed["failure_count"]
    lower = attributed["interval"]["lower"]
    if sample_count < min_eligible_samples:
        return {
            "action": "collect_more_evidence",
            "target": None,
            "requires_new_typed_route": False,
            "reason_code": "minimum_sample_not_met",
        }
    if failure_count < min_failures or not isinstance(lower, float):
        return {
            "action": "keep_route",
            "target": None,
            "requires_new_typed_route": False,
            "reason_code": "minimum_failure_signal_not_met",
        }
    if lower <= max_acceptable_failure_rate:
        return {
            "action": "keep_route",
            "target": None,
            "requires_new_typed_route": False,
            "reason_code": "wilson_lower_bound_within_threshold",
        }
    target = _safe_escalation_target(assignment)
    if target is None:
        return {
            "action": "needs_decision",
            "target": None,
            "requires_new_typed_route": True,
            "reason_code": "frontier_route_has_no_automatic_upward_step",
        }
    return {
        "action": "quality_escalation",
        "target": target,
        "requires_new_typed_route": True,
        "reason_code": "attributed_failure_wilson_lower_bound_exceeded",
    }


def build_model_feedback_report(
    events: Iterable[Any],
    *,
    min_eligible_samples: int = DEFAULT_MIN_ELIGIBLE_SAMPLES,
    min_failures: int = DEFAULT_MIN_FAILURES,
    max_acceptable_failure_rate: float = (
        DEFAULT_MAX_ACCEPTABLE_FAILURE_RATE
    ),
    evidence_window: int = DEFAULT_EVIDENCE_WINDOW,
    source_complete: bool = True,
    expected_authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate immutable run facts without reading state or changing policy."""

    if (
        not isinstance(min_eligible_samples, int)
        or isinstance(min_eligible_samples, bool)
        or min_eligible_samples < 5
        or not isinstance(min_failures, int)
        or isinstance(min_failures, bool)
        or min_failures < 1
        or min_failures > min_eligible_samples
        or not isinstance(max_acceptable_failure_rate, (int, float))
        or isinstance(max_acceptable_failure_rate, bool)
        or not math.isfinite(max_acceptable_failure_rate)
        or not 0.0 < max_acceptable_failure_rate < 1.0
        or not isinstance(evidence_window, int)
        or isinstance(evidence_window, bool)
        or evidence_window < 1
        or evidence_window > 1_000
        or not isinstance(source_complete, bool)
        or (
            expected_authority is not None
            and (
                not isinstance(expected_authority, dict)
                or not _line(
                    expected_authority.get("project_id"),
                    160,
                )
                or not _is_checkout_id(
                    expected_authority.get("checkout_id")
                )
                or not _is_digest(
                    expected_authority.get("registry_digest")
                )
                or not _line(
                    expected_authority.get("framework_version"),
                    64,
                )
            )
        )
    ):
        raise MaestroError(
            "MODEL_FEEDBACK_POLICY_INVALID",
            "Feedback gates require bounded sample, failure, and rate thresholds.",
        )

    event_list = list(events)
    if len(event_list) > evidence_window:
        raise MaestroError(
            "MODEL_FEEDBACK_WINDOW_EXCEEDED",
            "Feedback input exceeds its declared bounded evidence window.",
        )
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    seen_samples: set[str] = set()
    excluded = Counter()
    run_ids: set[str] = set()
    project_ids: set[str] = set()
    checkout_ids: set[str] = set()
    registry_digests: set[str] = set()
    framework_versions: set[str] = set()
    inferred_authority: tuple[str, str, str, str] | None = None
    for raw in event_list:
        if not isinstance(raw, dict):
            excluded["invalid-event"] += 1
            continue
        run_id = raw.get("run_id")
        plan = raw.get("plan_summary")
        if not _line(run_id, 160) or not isinstance(plan, dict):
            excluded["missing-plan-or-run"] += 1
            continue
        event_authority = (
            raw.get("project_id"),
            raw.get("checkout_id"),
            raw.get("registry_digest"),
            raw.get("framework_version"),
        )
        if (
            not _line(event_authority[0], 160)
            or not _is_checkout_id(event_authority[1])
            or not _is_digest(event_authority[2])
            or not _line(event_authority[3], 64)
        ):
            excluded["current-definition-authority-invalid"] += 1
            continue
        expected_event_authority = (
            (
                expected_authority["project_id"],
                expected_authority["checkout_id"],
                expected_authority["registry_digest"],
                expected_authority["framework_version"],
            )
            if expected_authority is not None
            else inferred_authority
        )
        if (
            expected_event_authority is not None
            and event_authority != expected_event_authority
        ):
            excluded["current-definition-authority-mismatch"] += 1
            continue
        if inferred_authority is None:
            inferred_authority = event_authority
        execution_binding = raw.get("execution_binding")
        if (
            not isinstance(execution_binding, dict)
            or execution_binding.get("mode")
            != "maestro_owned_codex_app_server"
            or plan.get("execution_receipts_required") is not True
        ):
            excluded["execution-binding-not-owned"] += 1
            continue
        assignments = [
            item
            for item in plan.get("assignments", [])
            if isinstance(item, dict)
        ]
        writers = [
            item
            for item in assignments
            if item.get("mutation_owner") is True
            and item.get("execution_kind") == "model"
        ]
        if len(writers) != 1:
            excluded["no-unique-model-writer"] += 1
            continue
        writer = writers[0]
        unit_id = writer.get("execution_unit_id")
        route_id = writer.get("model_route_id")
        if not _line(unit_id, 96) or not _is_digest(route_id):
            excluded["writer-route-unbound"] += 1
            continue
        if run_id in seen_samples:
            excluded["duplicate-run-unit"] += 1
            continue
        stage_results = {
            item.get("assignment_id"): item
            for item in raw.get("stage_results", [])
            if isinstance(item, dict)
        }
        writer_stage = stage_results.get(writer.get("assignment_id"))
        verifier_stages = [
            item
            for item in stage_results.values()
            if isinstance(item, dict)
            and isinstance(
                next(
                    (
                        assignment
                        for assignment in assignments
                        if assignment.get("assignment_id")
                        == item.get("assignment_id")
                    ),
                    None,
                ),
                dict,
            )
            and next(
                assignment
                for assignment in assignments
                if assignment.get("assignment_id")
                == item.get("assignment_id")
            ).get("executor_id")
            == "verifier"
        ]
        verifier_result = raw.get("verifier_result")
        if (
            not isinstance(writer_stage, dict)
            or writer_stage.get("status") != "completed"
            or writer_stage.get("model_route_id") != route_id
            or writer_stage.get("execution_unit_id") != unit_id
            or verifier_result not in {"passed", "failed"}
        ):
            excluded["incomplete-writer-or-verification"] += 1
            continue
        seen_samples.add(run_id)
        run_ids.add(run_id)
        project_ids.add(event_authority[0])
        checkout_ids.add(event_authority[1])
        registry_digests.add(event_authority[2])
        framework_versions.add(event_authority[3])
        key = _group_key(raw, writer)
        group = grouped.setdefault(
            key,
            {
                "subject": _subject(raw, writer),
                "assignment": writer,
                "recommendation_samples": 0,
                "recommendation_failures": 0,
                "applied_samples": 0,
                "applied_failures": 0,
                "applied_models": Counter(),
                "attributed_samples": 0,
                "attributed_failures": 0,
                "attribution_exclusions": Counter(),
                "run_ids": set(),
            },
        )
        group["run_ids"].add(run_id)
        group["recommendation_samples"] += 1
        group["recommendation_failures"] += verifier_result == "failed"
        applied_complete = (
            writer_stage.get("model_evidence") == "complete"
            and _line(writer_stage.get("actual_model"), 128)
        )
        if applied_complete:
            group["applied_samples"] += 1
            group["applied_failures"] += verifier_result == "failed"
            group["applied_models"][writer_stage["actual_model"]] += 1
        else:
            group["attribution_exclusions"][
                "applied-model-not-complete"
            ] += 1

        verifier_stage = next(
            (
                stage
                for stage in verifier_stages
                if isinstance(stage.get("verification_assessment"), dict)
                and stage["verification_assessment"].get(
                    "target_execution_unit_id"
                )
                == unit_id
            ),
            None,
        )
        assessment = (
            verifier_stage.get("verification_assessment")
            if isinstance(verifier_stage, dict)
            else None
        )
        if not applied_complete:
            continue
        if (
            writer_stage.get("actual_model")
            != writer.get("planned_model")
            or writer_stage.get("reroutes") != []
        ):
            group["attribution_exclusions"][
                "applied-route-differs-from-recommendation"
            ] += 1
            continue
        from .execution_units import (
            observation_identity,
            validate_stage_execution_receipts,
        )

        expected_observation_id = observation_identity(
            project_id=str(raw.get("project_id", "")),
            checkout_id=str(raw.get("checkout_id", "")),
            run_id=run_id,
        )

        if (
            not isinstance(
                writer_stage.get("execution_unit_receipt"),
                dict,
            )
            or validate_stage_execution_receipts(
                plan_summary=plan,
                stage_results=raw.get("stage_results"),
                run_id=raw.get("run_id"),
                observation_id=expected_observation_id,
                work_spans=raw.get("work_spans"),
                expected_framework_version=event_authority[3],
            )["status"]
            != "PASS"
        ):
            group["attribution_exclusions"][
                "execution-unit-receipt-missing-or-invalid"
            ] += 1
            continue
        completion_policy = raw.get("completion_policy")
        completion_closure = raw.get("completion_closure")
        execution_measurements = raw.get("execution_measurements")
        from .work import (
            receipt_intent_digest,
            validate_completion_closure,
            validate_completion_policy,
            validate_execution_measurements,
        )

        if (
            not validate_completion_policy(completion_policy)
            or not validate_execution_measurements(
                execution_measurements
            )
            or not validate_completion_closure(
                completion_closure,
                policy=completion_policy,
                plan_summary=plan,
                stage_results=raw.get("stage_results"),
                work_spans=raw.get("work_spans"),
                receipt_intent=receipt_intent_digest(raw),
            )
        ):
            group["attribution_exclusions"][
                "managed-completion-proof-missing"
            ] += 1
            continue
        if not validate_verification_assessment(
            assessment,
            plan_summary=plan,
            verifier_stage=verifier_stage,
        ):
            group["attribution_exclusions"][
                "assessment-missing-or-invalid"
            ] += 1
            continue
        assert isinstance(assessment, dict)
        verdict = assessment["verdict"]
        cause = assessment["failure_cause"]
        if (
            (verdict == "passed" and verifier_result != "passed")
            or (verdict == "failed" and verifier_result != "failed")
            or verdict == "inconclusive"
        ):
            group["attribution_exclusions"][
                "assessment-result-mismatch-or-inconclusive"
            ] += 1
            continue
        if verdict == "passed":
            group["attributed_samples"] += 1
        elif verdict == "failed" and cause == "implementation":
            group["attributed_samples"] += 1
            group["attributed_failures"] += 1
        else:
            group["attribution_exclusions"][
                f"cause:{cause}"
            ] += 1

    groups: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda item: tuple(str(x) for x in item)):
        source = grouped[key]
        recommendation = _metric(
            source["recommendation_samples"],
            source["recommendation_failures"],
        )
        applied = _metric(
            source["applied_samples"],
            source["applied_failures"],
        )
        applied["actual_models"] = dict(
            sorted(source["applied_models"].items())
        )
        attributed = _metric(
            source["attributed_samples"],
            source["attributed_failures"],
        )
        attributed["excluded_count"] = sum(
            source["attribution_exclusions"].values()
        )
        attributed["exclusion_reasons"] = dict(
            sorted(source["attribution_exclusions"].items())
        )
        group = {
            "group_id": "",
            "subject": source["subject"],
            "route_recommendation_failure": recommendation,
            "applied_model_failure": applied,
            "model_attributed_failure": attributed,
            "evaluation_gate": {
                "minimum_eligible_samples": min_eligible_samples,
                "minimum_failures": min_failures,
                "max_acceptable_failure_rate": float(
                    max_acceptable_failure_rate
                ),
                "state": (
                    "eligible"
                    if attributed["sample_count"]
                    >= min_eligible_samples
                    else "ineligible"
                ),
            },
            "advice": _advice(
                attributed=attributed,
                assignment=source["assignment"],
                min_eligible_samples=min_eligible_samples,
                min_failures=min_failures,
                max_acceptable_failure_rate=float(
                    max_acceptable_failure_rate
                ),
            ),
            "evidence": {
                "run_count": len(source["run_ids"]),
                "run_ids_digest": sha256_text(
                    canonical_json(sorted(source["run_ids"]))
                ),
                "interpretation": "observational-only",
            },
        }
        group["group_id"] = _digest(group, "group_id")
        groups.append(group)

    report = {
        "schema_version": MODEL_FEEDBACK_REPORT_VERSION,
        "report_id": "",
        "source": {
            "scope": "mutation-owner-only",
            "coverage": "latest-current-definition-runs",
            "evidence_window": evidence_window,
            "scan_complete": source_complete,
            "events_received": len(event_list),
            "run_count": len(run_ids),
            "run_ids_digest": sha256_text(canonical_json(sorted(run_ids))),
            "excluded_event_count": sum(excluded.values()),
            "exclusion_reasons": dict(sorted(excluded.items())),
        },
        "authority": {
            "project_id": (
                next(iter(project_ids)) if len(project_ids) == 1 else None
            ),
            "checkout_id": (
                next(iter(checkout_ids)) if len(checkout_ids) == 1 else None
            ),
            "registry_digest": (
                next(iter(registry_digests))
                if len(registry_digests) == 1
                else None
            ),
            "framework_version": (
                next(iter(framework_versions))
                if len(framework_versions) == 1
                else None
            ),
            "policy_digest": _policy_authority_digest(
                minimum_eligible_samples=min_eligible_samples,
                minimum_failures=min_failures,
                max_acceptable_failure_rate=float(
                    max_acceptable_failure_rate
                ),
                evidence_window=evidence_window,
                source_complete=source_complete,
            ),
        },
        "policy": {
            "confidence_level": DEFAULT_CONFIDENCE_LEVEL,
            "minimum_eligible_samples": min_eligible_samples,
            "minimum_failures": min_failures,
            "max_acceptable_failure_rate": float(
                max_acceptable_failure_rate
            ),
            "max_escalation_steps": 1,
            "automatic_downgrade_allowed": False,
        },
        "groups": groups,
        "causal_interpretation": "observational-only",
        "automatic_policy_mutation_allowed": False,
        "writes_performed": False,
    }
    report["report_id"] = _digest(report, "report_id")
    return report


def validate_model_feedback_report(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "report_id",
            "source",
            "authority",
            "policy",
            "groups",
            "causal_interpretation",
            "automatic_policy_mutation_allowed",
            "writes_performed",
        }
        or value.get("schema_version") != MODEL_FEEDBACK_REPORT_VERSION
        or not _is_digest(value.get("report_id"))
        or value["report_id"] != _digest(value, "report_id")
        or value.get("causal_interpretation") != "observational-only"
        or value.get("automatic_policy_mutation_allowed") is not False
        or value.get("writes_performed") is not False
        or not isinstance(value.get("groups"), list)
        or len(value["groups"]) > 1_024
    ):
        return False
    source = value.get("source")
    authority = value.get("authority")
    policy = value.get("policy")
    if (
        not isinstance(source, dict)
        or set(source)
        != {
            "scope",
            "coverage",
            "evidence_window",
            "scan_complete",
            "events_received",
            "run_count",
            "run_ids_digest",
            "excluded_event_count",
            "exclusion_reasons",
        }
        or source.get("scope") != "mutation-owner-only"
        or source.get("coverage") != "latest-current-definition-runs"
        or not isinstance(source.get("evidence_window"), int)
        or isinstance(source.get("evidence_window"), bool)
        or not 1 <= source["evidence_window"] <= 1_000
        or not isinstance(source.get("scan_complete"), bool)
        or not isinstance(source.get("events_received"), int)
        or isinstance(source.get("events_received"), bool)
        or not 0 <= source["events_received"] <= source["evidence_window"]
        or not isinstance(source.get("run_count"), int)
        or isinstance(source.get("run_count"), bool)
        or source["run_count"] < 0
        or not _is_digest(source.get("run_ids_digest"))
        or not isinstance(source.get("excluded_event_count"), int)
        or isinstance(source.get("excluded_event_count"), bool)
        or source["excluded_event_count"] < 0
        or not isinstance(source.get("exclusion_reasons"), dict)
        or not isinstance(policy, dict)
        or set(policy)
        != {
            "confidence_level",
            "minimum_eligible_samples",
            "minimum_failures",
            "max_acceptable_failure_rate",
            "max_escalation_steps",
            "automatic_downgrade_allowed",
        }
        or policy.get("confidence_level") != DEFAULT_CONFIDENCE_LEVEL
        or policy.get("max_escalation_steps") != 1
        or policy.get("automatic_downgrade_allowed") is not False
        or not isinstance(policy.get("minimum_eligible_samples"), int)
        or isinstance(policy.get("minimum_eligible_samples"), bool)
        or policy["minimum_eligible_samples"] < 5
        or not isinstance(policy.get("minimum_failures"), int)
        or isinstance(policy.get("minimum_failures"), bool)
        or policy["minimum_failures"] < 1
        or policy["minimum_failures"]
        > policy["minimum_eligible_samples"]
        or not isinstance(
            policy.get("max_acceptable_failure_rate"),
            (int, float),
        )
        or isinstance(
            policy.get("max_acceptable_failure_rate"),
            bool,
        )
        or not math.isfinite(policy["max_acceptable_failure_rate"])
        or not 0.0 < policy["max_acceptable_failure_rate"] < 1.0
        or any(
            not _line(key)
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            for key, count in source["exclusion_reasons"].items()
        )
        or sum(source["exclusion_reasons"].values())
        != source["excluded_event_count"]
        or source["run_count"] + source["excluded_event_count"]
        != source["events_received"]
        or not isinstance(authority, dict)
        or set(authority)
        != {
            "project_id",
            "checkout_id",
            "registry_digest",
            "framework_version",
            "policy_digest",
        }
        or (
            authority.get("project_id") is not None
            and not _line(authority["project_id"], 160)
        )
        or (
            authority.get("checkout_id") is not None
            and not _is_checkout_id(authority["checkout_id"])
        )
        or (
            authority.get("registry_digest") is not None
            and not _is_digest(authority["registry_digest"])
        )
        or (
            authority.get("framework_version") is not None
            and not _line(authority["framework_version"], 64)
        )
        or authority.get("policy_digest")
        != _policy_authority_digest(
            minimum_eligible_samples=policy.get(
                "minimum_eligible_samples",
                -1,
            ),
            minimum_failures=policy.get("minimum_failures", -1),
            max_acceptable_failure_rate=policy.get(
                "max_acceptable_failure_rate",
                -1.0,
            ),
            evidence_window=source.get("evidence_window", -1),
            source_complete=source.get("scan_complete", False),
        )
    ):
        return False
    group_ids: set[str] = set()
    for group in value["groups"]:
        if (
            not isinstance(group, dict)
            or set(group)
            != {
                "group_id",
                "subject",
                "route_recommendation_failure",
                "applied_model_failure",
                "model_attributed_failure",
                "evaluation_gate",
                "advice",
                "evidence",
            }
            or not _is_digest(group.get("group_id"))
            or group["group_id"] != _digest(group, "group_id")
            or group["group_id"] in group_ids
            or not _valid_feedback_subject(group.get("subject"))
            or not _valid_feedback_metric(
                group.get("route_recommendation_failure"),
            )
            or not _valid_feedback_metric(
                group.get("applied_model_failure"),
                applied=True,
            )
            or not _valid_feedback_metric(
                group.get("model_attributed_failure"),
                attributed=True,
            )
            or not _valid_evaluation_gate(
                group.get("evaluation_gate"),
                attributed=group.get("model_attributed_failure"),
                policy=policy,
            )
            or not _valid_feedback_advice(
                group.get("advice"),
                subject=group.get("subject"),
                attributed=group.get("model_attributed_failure"),
                policy=policy,
            )
            or not _valid_feedback_evidence(group.get("evidence"))
            or group["evidence"]["run_count"]
            != group["route_recommendation_failure"]["sample_count"]
            or group["applied_model_failure"]["sample_count"]
            > group["route_recommendation_failure"]["sample_count"]
            or group["model_attributed_failure"]["sample_count"]
            > group["applied_model_failure"]["sample_count"]
            or (
                group["model_attributed_failure"]["sample_count"]
                + group["model_attributed_failure"]["excluded_count"]
                != group["route_recommendation_failure"]["sample_count"]
            )
            or group["applied_model_failure"]["failure_count"]
            > group["route_recommendation_failure"]["failure_count"]
            or group["model_attributed_failure"]["failure_count"]
            > group["applied_model_failure"]["failure_count"]
        ):
            return False
        group_ids.add(group["group_id"])
    return sum(
        group["evidence"]["run_count"]
        for group in value["groups"]
    ) == source["run_count"]


def _valid_feedback_subject(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {
            "quality_profile",
            "stage_kind",
            "task_class",
            "selected_class",
            "selected_model",
            "reasoning_effort",
            "risk",
        }
        and value.get("quality_profile") == "pro-quality"
        and _line(value.get("stage_kind"), 96)
        and _line(value.get("task_class"), 96)
        and value.get("selected_class")
        in {"economy", "balanced", "frontier"}
        and _line(value.get("selected_model"), 128)
        and value.get("reasoning_effort")
        in {"low", "medium", "high", "xhigh"}
        and value.get("risk") in {"low", "medium", "high", "critical"}
    )


def _valid_feedback_metric(
    value: Any,
    *,
    applied: bool = False,
    attributed: bool = False,
) -> bool:
    fields = {
        "sample_count",
        "failure_count",
        "failure_rate",
        "interval",
    }
    if applied:
        fields.add("actual_models")
    if attributed:
        fields.update({"excluded_count", "exclusion_reasons"})
    if not isinstance(value, dict) or set(value) != fields:
        return False
    samples = value.get("sample_count")
    failures = value.get("failure_count")
    rate = value.get("failure_rate")
    interval = value.get("interval")
    if (
        not isinstance(samples, int)
        or isinstance(samples, bool)
        or samples < 0
        or not isinstance(failures, int)
        or isinstance(failures, bool)
        or failures < 0
        or failures > samples
        or not isinstance(interval, dict)
        or set(interval)
        != {"method", "confidence_level", "lower", "upper"}
        or interval.get("method") != "wilson"
        or interval.get("confidence_level") != DEFAULT_CONFIDENCE_LEVEL
    ):
        return False
    expected_rate = failures / samples if samples else None
    lower, upper = wilson_interval(failures, samples)
    for actual, expected in (
        (rate, expected_rate),
        (interval.get("lower"), lower),
        (interval.get("upper"), upper),
    ):
        if expected is None:
            if actual is not None:
                return False
        elif (
            not isinstance(actual, (int, float))
            or isinstance(actual, bool)
            or not math.isfinite(actual)
            or not math.isclose(float(actual), expected, abs_tol=1e-12)
        ):
            return False
    if applied:
        actual_models = value.get("actual_models")
        if (
            not isinstance(actual_models, dict)
            or sum(actual_models.values()) != samples
            or any(
                not _line(model, 128)
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 1
                for model, count in actual_models.items()
            )
        ):
            return False
    if attributed:
        excluded = value.get("excluded_count")
        reasons = value.get("exclusion_reasons")
        if (
            not isinstance(excluded, int)
            or isinstance(excluded, bool)
            or excluded < 0
            or not isinstance(reasons, dict)
            or sum(reasons.values()) != excluded
            or any(
                not _line(reason)
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 1
                for reason, count in reasons.items()
            )
        ):
            return False
    return True


def _valid_evaluation_gate(
    value: Any,
    *,
    attributed: Any,
    policy: dict[str, Any],
) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {
            "minimum_eligible_samples",
            "minimum_failures",
            "max_acceptable_failure_rate",
            "state",
        }
        and value["minimum_eligible_samples"]
        == policy["minimum_eligible_samples"]
        and value["minimum_failures"] == policy["minimum_failures"]
        and value["max_acceptable_failure_rate"]
        == policy["max_acceptable_failure_rate"]
        and isinstance(attributed, dict)
        and value.get("state")
        == (
            "eligible"
            if attributed.get("sample_count", 0)
            >= policy["minimum_eligible_samples"]
            else "ineligible"
        )
    )


def _valid_feedback_advice(
    value: Any,
    *,
    subject: Any,
    attributed: Any,
    policy: dict[str, Any],
) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "action",
            "target",
            "requires_new_typed_route",
            "reason_code",
        }
        or value.get("action")
        not in {
            "collect_more_evidence",
            "keep_route",
            "quality_escalation",
            "needs_decision",
        }
        or not _line(value.get("reason_code"))
        or not isinstance(subject, dict)
        or not isinstance(attributed, dict)
    ):
        return False
    samples = attributed.get("sample_count")
    failures = attributed.get("failure_count")
    lower = attributed.get("interval", {}).get("lower")
    expected_action = (
        "collect_more_evidence"
        if samples < policy["minimum_eligible_samples"]
        else (
            "keep_route"
            if (
                failures < policy["minimum_failures"]
                or not isinstance(lower, float)
                or lower <= policy["max_acceptable_failure_rate"]
            )
            else (
                "needs_decision"
                if subject.get("selected_class") == "frontier"
                else "quality_escalation"
            )
        )
    )
    if value["action"] != expected_action:
        return False
    if expected_action not in {"quality_escalation", "needs_decision"}:
        return (
            value.get("target") is None
            and value.get("requires_new_typed_route") is False
        )
    if value.get("requires_new_typed_route") is not True:
        return False
    if expected_action == "needs_decision":
        return value.get("target") is None
    target = value.get("target")
    expected_pair = {
        "economy": "balanced",
        "balanced": "frontier",
    }.get(subject.get("selected_class"))
    return (
        isinstance(target, dict)
        and set(target)
        == {
            "selected_class",
            "selected_model",
            "reasoning_effort",
        }
        and target.get("selected_class") == expected_pair
        and _line(target.get("selected_model"), 128)
        and target.get("reasoning_effort") == "high"
    )


def _valid_feedback_evidence(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {"run_count", "run_ids_digest", "interpretation"}
        and isinstance(value.get("run_count"), int)
        and not isinstance(value.get("run_count"), bool)
        and value["run_count"] >= 1
        and _is_digest(value.get("run_ids_digest"))
        and value.get("interpretation") == "observational-only"
    )


def build_model_policy_overlay(
    report: Any,
    *,
    group_id: str,
    basis: str,
    approval_ref: str,
    repo_path: str | Path,
) -> dict[str, Any]:
    """Accept one escalation candidate without mutating router state."""

    if not validate_model_feedback_report(report):
        raise MaestroError(
            "MODEL_FEEDBACK_REPORT_INVALID",
            "A validated feedback report is required.",
        )
    if basis not in {"owner_decision", "held_out_evaluation"}:
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_BASIS_INVALID",
            "Overlay acceptance requires owner_decision or held_out_evaluation.",
        )
    if (
        report["authority"]["policy_digest"]
        != MODEL_POLICY_AUTHORITY_DIGEST
        or report["source"]["evidence_window"]
        != DEFAULT_EVIDENCE_WINDOW
        or report["source"]["scan_complete"] is not True
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_POLICY_INVALID",
            "Only one complete 200-run production feedback window may create an active overlay.",
        )
    if report["authority"] != current_model_policy_authority(repo_path):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_AUTHORITY_INVALID",
            "An overlay report must match the current project, checkout, Registry, framework, and policy authority.",
        )
    if (
        not _line(approval_ref, 500)
        or not approval_ref.startswith(basis + ":")
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_APPROVAL_INVALID",
            "Overlay acceptance requires a basis-prefixed repository artifact reference.",
        )
    group = next(
        (item for item in report["groups"] if item["group_id"] == group_id),
        None,
    )
    if (
        group is None
        or group["advice"]["action"] != "quality_escalation"
        or group["advice"]["requires_new_typed_route"] is not True
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_NOT_ELIGIBLE",
            "Only a quality-escalation candidate can become an overlay.",
        )
    approval_digest = _model_policy_approval_digest(
        repo_path,
        basis=basis,
        approval_ref=approval_ref,
        report_id=report["report_id"],
        group_id=group_id,
        authority=report["authority"],
        scope=group["subject"],
        target=group["advice"]["target"],
    )
    overlay = {
        "schema_version": MODEL_POLICY_OVERLAY_VERSION,
        "overlay_id": "",
        "report_id": report["report_id"],
        "group_id": group_id,
        "authority": copy.deepcopy(report["authority"]),
        "scope": copy.deepcopy(group["subject"]),
        "target": copy.deepcopy(group["advice"]["target"]),
        "acceptance": {
            "basis": basis,
            "approval_ref": approval_ref,
            "approval_digest": approval_digest,
        },
        "max_escalation_steps": 1,
        "automatic_downgrade_allowed": False,
        "status": "accepted",
        "writes_performed": False,
    }
    overlay["overlay_id"] = _digest(overlay, "overlay_id")
    if any(
        overlay["authority"].get(field) is None
        for field in (
            "project_id",
            "checkout_id",
            "registry_digest",
            "framework_version",
        )
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_AUTHORITY_INVALID",
            "An accepted overlay requires one current project, checkout, and Registry authority.",
        )
    return overlay


def validate_model_policy_overlay(
    value: Any,
    *,
    report: Any | None = None,
) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "overlay_id",
            "report_id",
            "group_id",
            "authority",
            "scope",
            "target",
            "acceptance",
            "max_escalation_steps",
            "automatic_downgrade_allowed",
            "status",
            "writes_performed",
        }
        or value.get("schema_version") != MODEL_POLICY_OVERLAY_VERSION
        or not _is_digest(value.get("overlay_id"))
        or value["overlay_id"] != _digest(value, "overlay_id")
        or not _is_digest(value.get("report_id"))
        or not _is_digest(value.get("group_id"))
        or not isinstance(value.get("authority"), dict)
        or set(value["authority"])
        != {
            "project_id",
            "checkout_id",
            "registry_digest",
            "framework_version",
            "policy_digest",
        }
        or not _line(value["authority"].get("project_id"), 160)
        or not _is_checkout_id(value["authority"].get("checkout_id"))
        or not _is_digest(value["authority"].get("registry_digest"))
        or not _line(value["authority"].get("framework_version"), 64)
        or value["authority"].get("policy_digest")
        != MODEL_POLICY_AUTHORITY_DIGEST
        or value.get("max_escalation_steps") != 1
        or value.get("automatic_downgrade_allowed") is not False
        or value.get("status") != "accepted"
        or value.get("writes_performed") is not False
        or not isinstance(value.get("scope"), dict)
        or not _valid_feedback_subject(value.get("scope"))
        or not isinstance(value.get("target"), dict)
        or set(value["target"])
        != {
            "selected_class",
            "selected_model",
            "reasoning_effort",
        }
        or value["target"].get("selected_class")
        not in {"balanced", "frontier"}
        or not _line(value["target"].get("selected_model"), 128)
        or value["target"].get("reasoning_effort") != "high"
        or not isinstance(value.get("acceptance"), dict)
        or set(value["acceptance"])
        != {"basis", "approval_ref", "approval_digest"}
        or value["acceptance"].get("basis")
        not in {"owner_decision", "held_out_evaluation"}
        or not _line(value["acceptance"].get("approval_ref"), 500)
        or not value["acceptance"]["approval_ref"].startswith(
            value["acceptance"]["basis"] + ":"
        )
        or not _is_digest(
            value["acceptance"].get("approval_digest")
        )
    ):
        return False
    selected = value["scope"].get("selected_class")
    target = value["target"]["selected_class"]
    if (selected, target) not in {
        ("economy", "balanced"),
        ("balanced", "frontier"),
    }:
        return False
    if report is None:
        return True
    if not validate_model_feedback_report(report):
        return False
    group = next(
        (
            item
            for item in report["groups"]
            if item["group_id"] == value["group_id"]
        ),
        None,
    )
    return (
        report["report_id"] == value["report_id"]
        and report["authority"] == value["authority"]
        and isinstance(group, dict)
        and group["subject"] == value["scope"]
        and group["advice"]["action"] == "quality_escalation"
        and group["advice"]["target"] == value["target"]
    )


def current_model_policy_authority(
    repo_path: str | Path,
) -> dict[str, str]:
    """Bind an overlay to the exact current project and policy context."""

    from .project import checkout_id
    from .registry import registry_digest
    from .util import ensure_repo, read_json, safe_target
    from . import __version__

    repo = ensure_repo(repo_path)
    project = read_json(safe_target(repo, ".maestro/project.json"))
    project_id = project.get("project_id")
    if not _line(project_id, 160):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_AUTHORITY_INVALID",
            "The current project has no bounded project_id.",
        )
    return {
        "project_id": project_id,
        "checkout_id": checkout_id(repo),
        "registry_digest": registry_digest(),
        "framework_version": __version__,
        "policy_digest": MODEL_POLICY_AUTHORITY_DIGEST,
    }


def _model_policy_approval_digest(
    repo_path: str | Path,
    *,
    basis: str,
    approval_ref: str,
    report_id: str,
    group_id: str,
    authority: dict[str, Any],
    scope: dict[str, Any],
    target: dict[str, Any],
) -> str:
    from .util import ensure_repo, file_sha256, read_json, safe_target

    if (
        basis not in {"owner_decision", "held_out_evaluation"}
        or not _line(approval_ref, 500)
        or not approval_ref.startswith(basis + ":")
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_APPROVAL_INVALID",
            "Approval must use owner_decision:<path> or held_out_evaluation:<path>.",
        )
    relative = approval_ref.removeprefix(basis + ":")
    if (
        not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or "\\" in relative
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_APPROVAL_INVALID",
            "Approval authority must be a safe repository-relative file.",
        )
    repo = ensure_repo(repo_path)
    approval_path = safe_target(repo, relative)
    try:
        valid_file = (
            not approval_path.is_symlink()
            and approval_path.is_file()
            and 0 < approval_path.stat().st_size <= 1_000_000
        )
    except OSError:
        valid_file = False
    if not valid_file:
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_APPROVAL_INVALID",
            "Approval authority requires one existing bounded regular file.",
        )
    if basis == "owner_decision":
        artifact = read_json(approval_path)
        if (
            not isinstance(artifact, dict)
            or set(artifact)
            != {
                "schema_version",
                "report_ref",
                "report_digest",
                "report_id",
                "group_id",
                "authority",
                "scope",
                "target",
                "decision",
                "rationale",
                "evidence_refs",
            }
            or artifact.get("schema_version")
            != "maestro_model_policy_owner_decision_v1"
            or not _line(artifact.get("report_ref"), 500)
            or not _is_digest(artifact.get("report_digest"))
            or artifact.get("report_id") != report_id
            or artifact.get("group_id") != group_id
            or artifact.get("authority") != authority
            or artifact.get("scope") != scope
            or artifact.get("target") != target
            or artifact.get("decision") != "accept"
            or not _line(artifact.get("rationale"), 1_000)
            or not isinstance(artifact.get("evidence_refs"), list)
            or not 1 <= len(artifact["evidence_refs"]) <= 60
            or len(artifact["evidence_refs"])
            != len(set(artifact["evidence_refs"]))
            or any(
                not _line(ref, 500)
                for ref in artifact["evidence_refs"]
            )
        ):
            raise MaestroError(
                "MODEL_POLICY_OVERLAY_OWNER_DECISION_INVALID",
                "Owner authority must explicitly accept the exact report, group, and policy authority.",
            )
    else:
        artifact = read_json(approval_path)
        if (
            not isinstance(artifact, dict)
            or set(artifact)
            != {
                "schema_version",
                "report_ref",
                "report_digest",
                "report_id",
                "group_id",
                "authority",
                "scope",
                "target",
                "held_out",
                "verdict",
                "evidence_refs",
            }
            or artifact.get("schema_version")
            != "maestro_model_policy_held_out_evaluation_v1"
            or not _line(artifact.get("report_ref"), 500)
            or not _is_digest(artifact.get("report_digest"))
            or artifact.get("report_id") != report_id
            or artifact.get("group_id") != group_id
            or artifact.get("authority") != authority
            or artifact.get("scope") != scope
            or artifact.get("target") != target
            or artifact.get("held_out") is not True
            or artifact.get("verdict") != "accept"
            or not isinstance(artifact.get("evidence_refs"), list)
            or len(artifact["evidence_refs"]) < 3
            or len(artifact["evidence_refs"]) > 60
            or len(artifact["evidence_refs"])
            != len(set(artifact["evidence_refs"]))
            or any(not _line(ref, 500) for ref in artifact["evidence_refs"])
        ):
            raise MaestroError(
                "MODEL_POLICY_OVERLAY_HELD_OUT_INVALID",
                "Held-out authority must bind the exact feedback candidate and at least three evidence references.",
            )
    report_ref = artifact["report_ref"]
    if not report_ref.startswith("model_feedback_report:"):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_REPORT_INVALID",
            "Approval authority must name one model_feedback_report:<path> artifact.",
        )
    report_relative = report_ref.removeprefix(
        "model_feedback_report:"
    )
    if (
        not report_relative
        or Path(report_relative).is_absolute()
        or ".." in Path(report_relative).parts
        or "\\" in report_relative
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_REPORT_INVALID",
            "The feedback report artifact must be a safe repository-relative file.",
        )
    report_path = safe_target(repo, report_relative)
    try:
        valid_report_file = (
            not report_path.is_symlink()
            and report_path.is_file()
            and 0 < report_path.stat().st_size <= 5_000_000
        )
    except OSError:
        valid_report_file = False
    if (
        not valid_report_file
        or file_sha256(report_path) != artifact["report_digest"]
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_REPORT_INVALID",
            "The feedback report artifact is missing, unsafe, or digest-mismatched.",
        )
    report = read_json(report_path)
    group = (
        next(
            (
                item
                for item in report.get("groups", [])
                if isinstance(item, dict)
                and item.get("group_id") == group_id
            ),
            None,
        )
        if isinstance(report, dict)
        else None
    )
    if (
        not validate_model_feedback_report(report)
        or report.get("report_id") != report_id
        or report.get("authority") != authority
        or not isinstance(group, dict)
        or group.get("subject") != scope
        or group.get("advice", {}).get("action")
        != "quality_escalation"
        or group.get("advice", {}).get("target") != target
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_REPORT_INVALID",
            "Approval scope and target must come from the exact validated feedback report group.",
        )
    return file_sha256(approval_path)


def validate_model_policy_overlay_authority(
    value: Any,
    *,
    repo_path: str | Path,
) -> bool:
    if (
        not validate_model_policy_overlay(value)
        or value["authority"] != current_model_policy_authority(repo_path)
    ):
        return False
    try:
        digest = _model_policy_approval_digest(
            repo_path,
            basis=value["acceptance"]["basis"],
            approval_ref=value["acceptance"]["approval_ref"],
            report_id=value["report_id"],
            group_id=value["group_id"],
            authority=value["authority"],
            scope=value["scope"],
            target=value["target"],
        )
    except (MaestroError, OSError, TypeError, ValueError):
        return False
    return digest == value["acceptance"]["approval_digest"]
