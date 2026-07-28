from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from maestro.errors import MaestroError

LEGACY_WORK_SPAN_VERSION = "maestro_work_span_v1"
WORK_SPAN_VERSION = "maestro_work_span_v2"
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
    "hook_point",
    "complete",
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
EVENT_COVERAGE = {
    "complete_stream",
    "recovered_full",
    "hook_lifecycle",
    "partial_stream",
    "unavailable",
}
MODEL_COVERAGE = {
    "complete_stream",
    "hook_point",
    "request_only",
    "unavailable",
}
TIMING_COVERAGE = {
    "host_event",
    "collector_clock",
    "partial",
    "unavailable",
}
NEXT_ACTIONS = {
    "continue",
    "revise",
    "redelegate",
    "verify",
    "finish",
    "blocked",
    "user_decision",
}
FOLLOWUP_REASONS = {
    "new_scope",
    "retry_after_failure",
    "continue_incomplete",
    "verification_followup",
    "unknown",
}
_DIGEST = re.compile(r"^[a-f0-9]{64}$")

_BASE_WORK_SPAN_FIELDS = {
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
_WORK_SPAN_V1_FIELDS = set(_BASE_WORK_SPAN_FIELDS)
_WORK_SPAN_V2_FIELDS = {
    *_BASE_WORK_SPAN_FIELDS,
    "source_binding",
    "model_observation",
    "usage",
    "outcome",
    "diagnostics",
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


def _valid_tokens(value: Any, *, optional: bool = True) -> bool:
    if value is None:
        return optional
    return (
        isinstance(value, dict)
        and set(value) == {
            "input",
            "output",
            "cached",
            "reasoning",
            "total",
        }
        and all(
            isinstance(item, int)
            and not isinstance(item, bool)
            and item >= 0
            for item in value.values()
        )
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
    if evidence == "hook_point":
        return requested is None and applied is None
    if evidence == "complete":
        return requested is not None and applied is not None
    return False


def _valid_source_binding(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "interface",
            "version",
            "schema_digest",
            "capability",
            "correlation_id",
            "event_coverage",
        }
        or value["interface"] not in WORK_SOURCES
        or not _valid_line(value["version"], maximum=80, optional=True)
        or not _valid_line(
            value["schema_digest"],
            maximum=64,
            optional=True,
        )
        or (
            value["schema_digest"] is not None
            and _DIGEST.fullmatch(value["schema_digest"]) is None
        )
        or value["capability"]
        not in {
            "full_stream",
            "lifecycle_only",
            "current_host",
            "unavailable",
        }
        or not _valid_line(
            value["correlation_id"],
            maximum=160,
            optional=True,
        )
        or value["event_coverage"] not in EVENT_COVERAGE
    ):
        return False
    if value["event_coverage"] in {"complete_stream", "recovered_full"}:
        return (
            value["version"] is not None
            and value["schema_digest"] is not None
            and value["correlation_id"] is not None
            and value["capability"] == "full_stream"
        )
    return True


def _valid_model_observation(value: Any, span: dict[str, Any]) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != {"observed_model", "coverage", "reroutes"}
        or not _valid_line(
            value["observed_model"],
            maximum=128,
            optional=True,
        )
        or value["coverage"] not in MODEL_COVERAGE
        or not isinstance(value["reroutes"], list)
        or len(value["reroutes"]) > 4
    ):
        return False
    for reroute in value["reroutes"]:
        if (
            not isinstance(reroute, dict)
            or set(reroute) != {"from_model", "to_model", "reason"}
            or not _valid_line(reroute["from_model"], maximum=128)
            or not _valid_line(reroute["to_model"], maximum=128)
            or not _valid_line(reroute["reason"], maximum=240)
        ):
            return False
    requested = span["requested_model"]
    applied = span["applied_model"]
    coverage = value["coverage"]
    if coverage == "unavailable":
        return (
            requested is None
            and value["observed_model"] is None
            and applied is None
            and not value["reroutes"]
        )
    if coverage == "request_only":
        return requested is not None and applied is None and not value["reroutes"]
    if coverage == "hook_point":
        return value["observed_model"] is not None and applied is None
    if requested is None or applied is None:
        return False
    expected_applied = (
        value["reroutes"][-1]["to_model"]
        if value["reroutes"]
        else requested
    )
    return applied == expected_applied


def _valid_usage(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "last",
            "total",
            "scope",
            "attribution",
            "timing_coverage",
            "cost",
        }
        or not _valid_tokens(value["last"])
        or not _valid_tokens(value["total"])
        or value["scope"]
        not in {
            "work_turn",
            "thread",
            "parent_turn",
            "unavailable",
        }
        or value["attribution"]
        not in {"direct", "shared", "unavailable"}
        or value["timing_coverage"] not in TIMING_COVERAGE
    ):
        return False
    if value["scope"] == "unavailable":
        if (
            value["last"] is not None
            or value["total"] is not None
            or value["attribution"] != "unavailable"
        ):
            return False
    cost = value["cost"]
    if cost is None:
        return True
    return (
        isinstance(cost, dict)
        and set(cost) == {"provider", "amount", "currency", "receipt_ref"}
        and _valid_line(cost["provider"], maximum=80)
        and isinstance(cost["amount"], (int, float))
        and not isinstance(cost["amount"], bool)
        and math.isfinite(cost["amount"])
        and cost["amount"] >= 0
        and _valid_line(cost["currency"], maximum=16)
        and _valid_line(cost["receipt_ref"], maximum=240)
    )


def _valid_outcome(value: Any, span: dict[str, Any]) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "finding_summary",
            "conclusion",
            "decision",
            "next_action",
            "consumed_work_ids",
            "handoff",
            "artifacts",
            "verification",
        }
        or not _valid_line(
            value["finding_summary"],
            maximum=240,
            optional=True,
        )
        or not _valid_line(
            value["conclusion"],
            maximum=240,
            optional=True,
        )
        or not _valid_line(
            value["decision"],
            maximum=240,
            optional=True,
        )
        or (
            value["next_action"] is not None
            and value["next_action"] not in NEXT_ACTIONS
        )
        or not _valid_ids(value["consumed_work_ids"])
        or not isinstance(value["artifacts"], list)
        or len(value["artifacts"]) > 8
    ):
        return False
    if not set(value["consumed_work_ids"]).issubset(
        set(span["joins_work_ids"])
    ):
        return False
    handoff = value["handoff"]
    if handoff is not None and (
        not isinstance(handoff, dict)
        or set(handoff) != {"purpose", "completion_criteria"}
        or not _valid_line(handoff["purpose"], maximum=240)
        or not _valid_line(handoff["completion_criteria"], maximum=240)
    ):
        return False
    for artifact in value["artifacts"]:
        if (
            not isinstance(artifact, dict)
            or set(artifact)
            != {
                "artifact_id",
                "format",
                "digest",
                "producer_work_id",
                "verification",
            }
            or not _valid_id(artifact["artifact_id"])
            or not _valid_line(artifact["format"], maximum=80)
            or not isinstance(artifact["digest"], str)
            or _DIGEST.fullmatch(artifact["digest"]) is None
            or not _valid_id(artifact["producer_work_id"])
            or artifact["verification"]
            not in {"unverified", "passed", "failed"}
        ):
            return False
    verification = value["verification"]
    if verification is not None and (
        not isinstance(verification, dict)
        or set(verification)
        != {
            "target",
            "basis",
            "assertion",
            "command_result",
            "evidence_refs",
        }
        or not _valid_line(verification["target"], maximum=240)
        or not _valid_line(verification["basis"], maximum=240)
        or not _valid_line(verification["assertion"], maximum=240)
        or verification["command_result"] not in {"passed", "failed", "not_run"}
        or not _valid_evidence_refs(verification["evidence_refs"])
    ):
        return False
    return True


def _valid_diagnostics(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "interrupt_requested",
            "error_count",
            "last_error",
            "followup_reason",
        }
        or not isinstance(value["interrupt_requested"], bool)
        or not isinstance(value["error_count"], int)
        or isinstance(value["error_count"], bool)
        or not 0 <= value["error_count"] <= 20
        or not _valid_line(
            value["last_error"],
            maximum=240,
            optional=True,
        )
        or (
            value["followup_reason"] is not None
            and value["followup_reason"] not in FOLLOWUP_REASONS
        )
    ):
        return False
    return (value["error_count"] == 0) == (value["last_error"] is None)


def _valid_evidence_binding(value: dict[str, Any]) -> bool:
    """Keep complete claims bound to one compatible producer surface."""

    binding = value["source_binding"]
    model = value["model_observation"]
    usage = value["usage"]
    complete_stream = (
        binding["capability"] == "full_stream"
        and binding["event_coverage"]
        in {"complete_stream", "recovered_full"}
    )
    if (
        value["model_evidence"] == "complete"
        or model["coverage"] == "complete_stream"
    ) and not complete_stream:
        return False
    if usage["attribution"] == "direct":
        if not complete_stream:
            return False
    if usage["timing_coverage"] == "host_event" and not complete_stream:
        return False
    if value["timing_evidence"] == "host_event":
        if (
            binding["interface"] == "current_host"
            or binding["capability"] in {"current_host", "unavailable"}
            or binding["event_coverage"] == "unavailable"
        ):
            return False
    if model["coverage"] == "hook_point":
        return (
            binding["interface"] == "host_adapter"
            and binding["event_coverage"] == "hook_lifecycle"
            and binding["capability"] in {"lifecycle_only", "full_stream"}
        )
    return True


def _validate_work_span_base(value: Any, fields: set[str]) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != fields
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


def validate_work_span(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    version = value.get("schema_version")
    if version == LEGACY_WORK_SPAN_VERSION:
        return _validate_work_span_base(value, _WORK_SPAN_V1_FIELDS)
    if (
        version != WORK_SPAN_VERSION
        or not _validate_work_span_base(value, _WORK_SPAN_V2_FIELDS)
    ):
        return False
    return (
        _valid_source_binding(value["source_binding"])
        and value["source_binding"]["interface"] == value["source"]
        and _valid_model_observation(value["model_observation"], value)
        and _valid_usage(value["usage"])
        and _valid_outcome(value["outcome"], value)
        and _valid_diagnostics(value["diagnostics"])
        and _valid_evidence_binding(value)
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
    predecessors = {
        item["work_id"]: {
            relation
            for relation in (
                item["parent_work_id"],
                item["followup_of_work_id"],
                *item["depends_on_work_ids"],
                *item["joins_work_ids"],
            )
            if relation is not None
        }
        for item in value
    }
    resolved: set[str] = set()
    pending = set(known)
    while pending:
        ready = {
            work_id
            for work_id in pending
            if predecessors[work_id].issubset(resolved)
        }
        if not ready:
            return False
        resolved.update(ready)
        pending.difference_update(ready)
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
    source_binding: dict[str, Any] | None = None,
    model_observation: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
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
        "source_binding": source_binding or {
            "interface": source,
            "version": None,
            "schema_digest": None,
            "capability": (
                "current_host"
                if source == "current_host"
                else "lifecycle_only"
            ),
            "correlation_id": None,
            "event_coverage": (
                "partial_stream"
                if (
                    source in {"codex_app_server", "host_adapter"}
                    and timing_evidence == "host_event"
                )
                else "unavailable"
            ),
        },
        "model_observation": model_observation or {
            "observed_model": None,
            "coverage": (
                "request_only"
                if requested_model is not None
                else "unavailable"
            ),
            "reroutes": [],
        },
        "usage": usage or {
            "last": None,
            "total": None,
            "scope": "unavailable",
            "attribution": "unavailable",
            "timing_coverage": (
                "collector_clock"
                if timing_evidence == "current_host_clock"
                else "partial"
            ),
            "cost": None,
        },
        "outcome": outcome or {
            "finding_summary": None,
            "conclusion": None,
            "decision": None,
            "next_action": None,
            "consumed_work_ids": [],
            "handoff": None,
            "artifacts": [],
            "verification": None,
        },
        "diagnostics": diagnostics or {
            "interrupt_requested": False,
            "error_count": 0,
            "last_error": None,
            "followup_reason": None,
        },
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
    source_binding: dict[str, Any] | None = None,
    model_observation: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
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
        **(
            {
                "source_binding": source_binding or span["source_binding"],
                "model_observation": (
                    model_observation or span["model_observation"]
                ),
                "usage": usage or span["usage"],
                "outcome": outcome or span["outcome"],
                "diagnostics": diagnostics or span["diagnostics"],
            }
            if span["schema_version"] == WORK_SPAN_VERSION
            else {}
        ),
    }
    if not validate_work_span(completed):
        raise MaestroError(
            "WORK_SPAN_INVALID",
            "The observed work result does not satisfy the bounded contract.",
        )
    return completed
