from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from maestro.errors import MaestroError

WORK_SPAN_VERSION = "maestro_work_span_v1"
MAX_WORK_SPANS = 64
MAX_RELATIONS_PER_SPAN = 16
MAX_EVIDENCE_REFS = 5
WORK_KINDS = {
    "orchestration",
    "delegation",
    "research",
    "review",
    "implementation",
    "synthesis",
    "verification",
}
WORK_STATUSES = {
    "running",
    "completed",
    "failed",
    "blocked",
    "interrupted",
}
TERMINAL_WORK_STATUSES = WORK_STATUSES - {"running"}
WORK_SOURCES = {
    "current_host",
    "codex_app_server",
    "host_adapter",
}
MODEL_EVIDENCE = {
    "unavailable",
    "host_request",
}
EXPERTISE_EVIDENCE = {
    "unavailable",
    "selection_only",
    "host_loaded",
    "application_observed",
}
TIMING_EVIDENCE = {
    "current_host_clock",
    "host_event",
}

_WORK_SPAN_FIELDS = {
    "schema_version",
    "work_id",
    "parent_work_id",
    "assignment_id",
    "kind",
    "role",
    "executor_id",
    "task_summary",
    "result_summary",
    "status",
    "attempt",
    "followup_of_work_id",
    "depends_on_work_ids",
    "joins_work_ids",
    "read_only",
    "source",
    "started_at",
    "ended_at",
    "duration_ms",
    "timing_evidence",
    "requested_model",
    "requested_reasoning_effort",
    "applied_model",
    "model_evidence",
    "lens_ids",
    "expertise_pack_ids",
    "decision_guide_ids",
    "expertise_evidence",
    "evidence_refs",
}


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _valid_line(
    value: Any,
    *,
    maximum: int,
    optional: bool = False,
) -> bool:
    if value is None:
        return optional
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and not any(character in value for character in "\r\n\x00")
    )


def _valid_id(value: Any, *, optional: bool = False) -> bool:
    return _valid_line(value, maximum=96, optional=optional)


def _valid_ids(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= MAX_RELATIONS_PER_SPAN
        and len(value) == len(set(value))
        and all(_valid_id(item) for item in value)
    )


def _valid_evidence_refs(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= MAX_EVIDENCE_REFS
        and all(_valid_line(item, maximum=240) for item in value)
    )


def _valid_model_fields(value: dict[str, Any]) -> bool:
    requested = value["requested_model"]
    effort = value["requested_reasoning_effort"]
    applied = value["applied_model"]
    evidence = value["model_evidence"]
    if (
        evidence not in MODEL_EVIDENCE
        or not _valid_line(requested, maximum=128, optional=True)
        or not _valid_line(effort, maximum=40, optional=True)
        or not _valid_line(applied, maximum=128, optional=True)
    ):
        return False
    if evidence == "unavailable":
        return requested is None and effort is None and applied is None
    if evidence == "host_request":
        return requested is not None and applied is None
    return False


def validate_work_span(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != _WORK_SPAN_FIELDS
        or value.get("schema_version") != WORK_SPAN_VERSION
        or not _valid_id(value.get("work_id"))
        or not _valid_id(value.get("parent_work_id"), optional=True)
        or not _valid_id(value.get("assignment_id"), optional=True)
        or value.get("kind") not in WORK_KINDS
        or not _valid_line(value.get("role"), maximum=80)
        or not _valid_id(value.get("executor_id"))
        or not _valid_line(value.get("task_summary"), maximum=240)
        or not _valid_line(
            value.get("result_summary"),
            maximum=240,
            optional=True,
        )
        or value.get("status") not in WORK_STATUSES
        or not isinstance(value.get("attempt"), int)
        or isinstance(value.get("attempt"), bool)
        or not 1 <= value["attempt"] <= 20
        or not _valid_id(value.get("followup_of_work_id"), optional=True)
        or not _valid_ids(value.get("depends_on_work_ids"))
        or not _valid_ids(value.get("joins_work_ids"))
        or not isinstance(value.get("read_only"), bool)
        or value.get("source") not in WORK_SOURCES
        or _timestamp(value.get("started_at")) is None
        or value.get("timing_evidence") not in TIMING_EVIDENCE
        or not _valid_model_fields(value)
        or not _valid_ids(value.get("lens_ids"))
        or not _valid_ids(value.get("expertise_pack_ids"))
        or not _valid_ids(value.get("decision_guide_ids"))
        or value.get("expertise_evidence") not in EXPERTISE_EVIDENCE
        or not _valid_evidence_refs(value.get("evidence_refs"))
    ):
        return False

    work_id = value["work_id"]
    related_ids = [
        value["parent_work_id"],
        value["followup_of_work_id"],
        *value["depends_on_work_ids"],
        *value["joins_work_ids"],
    ]
    if work_id in related_ids:
        return False

    ended_at = _timestamp(value.get("ended_at"))
    duration = value.get("duration_ms")
    if value["status"] == "running":
        return (
            value["ended_at"] is None
            and duration is None
            and value["result_summary"] is None
        )
    return (
        ended_at is not None
        and ended_at >= _timestamp(value["started_at"])
        and isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and math.isfinite(duration)
        and duration >= 0
        and value["result_summary"] is not None
    )


def validate_work_spans(value: Any) -> bool:
    if (
        value is None
        or not isinstance(value, list)
        or len(value) > MAX_WORK_SPANS
        or not all(validate_work_span(item) for item in value)
    ):
        return value is None
    work_ids = [item["work_id"] for item in value]
    if len(work_ids) != len(set(work_ids)):
        return False
    known = set(work_ids)
    for item in value:
        relations = [
            item["parent_work_id"],
            item["followup_of_work_id"],
            *item["depends_on_work_ids"],
            *item["joins_work_ids"],
        ]
        if any(relation is not None and relation not in known for relation in relations):
            return False
    return True


def new_work_span(
    *,
    work_id: str,
    kind: str,
    role: str,
    executor_id: str,
    task_summary: str,
    read_only: bool,
    source: str,
    started_at: str,
    timing_evidence: str,
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
) -> dict[str, Any]:
    span = {
        "schema_version": WORK_SPAN_VERSION,
        "work_id": work_id,
        "parent_work_id": parent_work_id,
        "assignment_id": assignment_id,
        "kind": kind,
        "role": role,
        "executor_id": executor_id,
        "task_summary": task_summary,
        "result_summary": None,
        "status": "running",
        "attempt": attempt,
        "followup_of_work_id": followup_of_work_id,
        "depends_on_work_ids": list(depends_on_work_ids or []),
        "joins_work_ids": list(joins_work_ids or []),
        "read_only": read_only,
        "source": source,
        "started_at": started_at,
        "ended_at": None,
        "duration_ms": None,
        "timing_evidence": timing_evidence,
        "requested_model": requested_model,
        "requested_reasoning_effort": requested_reasoning_effort,
        "applied_model": applied_model,
        "model_evidence": model_evidence,
        "lens_ids": list(lens_ids or []),
        "expertise_pack_ids": list(expertise_pack_ids or []),
        "decision_guide_ids": list(decision_guide_ids or []),
        "expertise_evidence": expertise_evidence,
        "evidence_refs": [],
    }
    if not validate_work_span(span):
        raise MaestroError(
            "WORK_SPAN_INVALID",
            "The observed work start does not satisfy the bounded contract.",
        )
    return span


def complete_work_span(
    span: dict[str, Any],
    *,
    status: str,
    result_summary: str,
    ended_at: str,
    duration_ms: float,
    evidence_refs: list[str],
    applied_model: str | None = None,
    model_evidence: str | None = None,
    expertise_evidence: str | None = None,
) -> dict[str, Any]:
    if not validate_work_span(span) or span["status"] != "running":
        raise MaestroError(
            "WORK_SPAN_CONFLICT",
            "Only one valid running work span can be completed.",
        )
    completed = {
        **span,
        "status": status,
        "result_summary": result_summary,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "evidence_refs": list(evidence_refs),
        "applied_model": applied_model,
        "model_evidence": model_evidence or span["model_evidence"],
        "expertise_evidence": (
            expertise_evidence or span["expertise_evidence"]
        ),
    }
    if not validate_work_span(completed):
        raise MaestroError(
            "WORK_SPAN_INVALID",
            "The observed work result does not satisfy the bounded contract.",
        )
    return completed
