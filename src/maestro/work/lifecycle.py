from __future__ import annotations

from typing import Any

from maestro.errors import MaestroError

from .contracts import (
    complete_work_span,
    validate_work_span,
    validate_work_spans,
)


def append_work_span(
    work_spans: list[dict[str, Any]] | None,
    span: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    existing = list(work_spans or [])
    if not validate_work_spans(existing) or not validate_work_span(span):
        raise MaestroError(
            "WORK_SPAN_INVALID",
            "Observed work state does not satisfy the bounded contract.",
        )
    by_id = {item["work_id"]: item for item in existing}
    recorded = by_id.get(span["work_id"])
    if recorded is not None:
        if recorded != span:
            raise MaestroError(
                "WORK_SPAN_CONFLICT",
                "This work ID already contains a different observation.",
            )
        return existing, False
    updated = [*existing, span]
    if not validate_work_spans(updated):
        raise MaestroError(
            "WORK_RELATION_INVALID",
            "Observed work relations must reference earlier work in this run.",
        )
    return updated, True


def finish_work_span(
    work_spans: list[dict[str, Any]] | None,
    *,
    work_id: str,
    status: str,
    result_summary: str,
    ended_at: str,
    duration_ms: float,
    evidence_refs: list[str],
    applied_model: str | None = None,
    model_evidence: str | None = None,
    expertise_evidence: str | None = None,
    source_binding: dict[str, Any] | None = None,
    model_observation: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    existing = list(work_spans or [])
    if not validate_work_spans(existing):
        raise MaestroError(
            "WORK_SPAN_INVALID",
            "Observed work state does not satisfy the bounded contract.",
        )
    index = next(
        (
            position
            for position, item in enumerate(existing)
            if item["work_id"] == work_id
        ),
        None,
    )
    if index is None:
        raise MaestroError(
            "WORK_SPAN_NOT_FOUND",
            "The work ID is not present in this run observation.",
        )
    recorded = existing[index]
    if expertise_evidence in {"host_loaded", "application_observed"}:
        has_expertise_binding = bool(
            recorded.get("expertise_pack_ids")
            or recorded.get("decision_guide_ids")
        )
        if not has_expertise_binding or not evidence_refs:
            raise MaestroError(
                "WORK_EXPERTISE_EVIDENCE_INVALID",
                "Loaded or applied Expertise requires a bound Pack or Guide "
                "and at least one result evidence reference.",
            )
    if recorded["status"] != "running":
        comparable = {
            "status": status,
            "result_summary": result_summary,
            "evidence_refs": list(evidence_refs),
            "applied_model": applied_model,
            "model_evidence": model_evidence or recorded["model_evidence"],
            "expertise_evidence": (
                expertise_evidence or recorded["expertise_evidence"]
            ),
        }
        if recorded.get("schema_version") == "maestro_work_span_v2":
            comparable.update(
                {
                    "source_binding": (
                        source_binding or recorded["source_binding"]
                    ),
                    "model_observation": (
                        model_observation or recorded["model_observation"]
                    ),
                    "usage": usage or recorded["usage"],
                    "outcome": outcome or recorded["outcome"],
                    "diagnostics": diagnostics or recorded["diagnostics"],
                }
            )
        if all(recorded[key] == value for key, value in comparable.items()):
            return existing, False
        raise MaestroError(
            "WORK_SPAN_CONFLICT",
            "This work ID already contains a different terminal result.",
        )
    completed = complete_work_span(
        recorded,
        status=status,
        result_summary=result_summary,
        ended_at=ended_at,
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
    )
    updated = list(existing)
    updated[index] = completed
    if not validate_work_spans(updated):
        raise MaestroError(
            "WORK_SPAN_INVALID",
            "The completed work state is invalid.",
        )
    return updated, True
