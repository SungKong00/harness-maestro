from __future__ import annotations

import copy
import math
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from maestro.errors import MaestroError
from maestro.util import (
    atomic_write,
    canonical_json,
    pretty_json,
    read_json,
    sha256_text,
)

from .completion import evaluate_completion

try:  # pragma: no cover - exercised on the supported POSIX hosts.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


EXECUTION_LEDGER_VERSION = "maestro_execution_ledger_v1"
EXECUTION_EVENT_VERSION = "maestro_execution_event_v1"
EXECUTION_MEASUREMENTS_VERSION = "maestro_execution_measurements_v1"
MAX_EXECUTION_EVENTS = 256
MAX_EXECUTION_LEDGER_BYTES = 900_000
EVENT_TYPES = {
    "execution_started",
    "plan_attached",
    "execution_binding_changed",
    "measurement_observed",
    "work_started",
    "work_terminal",
    "assignment_terminal",
    "execution_sealed",
}
PRODUCER_INTERFACES = {
    "maestro_core",
    "desktop_request",
    "current_host",
    "codex_app_server",
    "host_adapter",
    "deterministic_command",
    "legacy_import",
}
PRODUCER_CAPABILITIES = {
    "full_stream",
    "lifecycle_only",
    "request_metadata",
    "current_host",
    "deterministic",
    "unavailable",
}
EVENT_COVERAGE = {
    "complete_stream",
    "recovered_full",
    "hook_lifecycle",
    "partial_stream",
    "request_only",
    "unavailable",
}
MEASUREMENT_COVERAGE = {
    "complete",
    "partial",
    "request_only",
    "collector_clock",
    "unavailable",
}


def _sha256_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


MISSING_REASONS = {
    None,
    "producer_did_not_expose",
    "request_metadata_only",
    "partial_stream",
    "work_running",
    "not_applicable",
    "legacy_unmeasured",
}


def _line(value: Any, maximum: int, *, optional: bool = False) -> bool:
    if value is None:
        return optional
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and not any(character in value for character in "\r\n\x00")
    )


def _numeric_map(value: Any) -> bool:
    return (
        value is None
        or (
            isinstance(value, dict)
            and all(
                isinstance(item, int)
                and not isinstance(item, bool)
                and item >= 0
                for item in value.values()
            )
        )
    )


def _duration_map(value: Any) -> bool:
    return (
        value is None
        or (
            isinstance(value, dict)
            and set(value) == {"total"}
            and isinstance(value["total"], (int, float))
            and not isinstance(value["total"], bool)
            and math.isfinite(value["total"])
            and value["total"] >= 0
        )
    )


def producer_binding(
    interface: str,
    *,
    capability: str,
    event_coverage: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    value = {
        "interface": interface,
        "capability": capability,
        "event_coverage": event_coverage,
        "correlation_id": correlation_id,
    }
    if not _valid_producer(value):
        raise MaestroError(
            "EXECUTION_LEDGER_PRODUCER_INVALID",
            "Execution events require one bounded producer binding.",
        )
    return value


def _valid_producer(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {
            "interface",
            "capability",
            "event_coverage",
            "correlation_id",
        }
        and value.get("interface") in PRODUCER_INTERFACES
        and value.get("capability") in PRODUCER_CAPABILITIES
        and value.get("event_coverage") in EVENT_COVERAGE
        and _line(value.get("correlation_id"), 160, optional=True)
    )


def _measurement_slot(
    *,
    value: Any,
    coverage: str,
    missing_reason: str | None,
    scope: str,
    attribution: str,
) -> dict[str, Any]:
    return {
        "value": value,
        "coverage": coverage,
        "missing_reason": missing_reason,
        "scope": scope,
        "attribution": attribution,
    }


def _valid_measurement_slot(
    value: Any,
    *,
    numeric: bool = False,
    duration: bool = False,
) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "value",
            "coverage",
            "missing_reason",
            "scope",
            "attribution",
        }
        or value.get("coverage") not in MEASUREMENT_COVERAGE
        or value.get("missing_reason") not in MISSING_REASONS
        or not _line(value.get("scope"), 40)
        or not _line(value.get("attribution"), 40)
    ):
        return False
    measured = value.get("value")
    if duration:
        if not _duration_map(measured):
            return False
    elif numeric:
        if not _numeric_map(measured):
            return False
    elif measured is not None and not _line(measured, 128):
        return False
    if measured is None:
        return (
            value["coverage"] == "unavailable"
            and value["missing_reason"] is not None
            and value["attribution"] == "unavailable"
        )
    if (
        value["coverage"] == "unavailable"
        or value["missing_reason"] is not None
        or value["scope"] == "unavailable"
    ):
        return False
    if value["coverage"] == "request_only":
        return (
            not numeric
            and not duration
            and value["attribution"] == "requested"
        )
    if value["coverage"] in {"complete", "collector_clock"}:
        return value["attribution"] == "direct"
    return value["coverage"] == "partial" and value["attribution"] in {
        "direct",
        "shared",
    }


def empty_measurement(
    *,
    reason: str = "producer_did_not_expose",
) -> dict[str, Any]:
    return {
        "model": _measurement_slot(
            value=None,
            coverage="unavailable",
            missing_reason=reason,
            scope="execution_attempt",
            attribution="unavailable",
        ),
        "reasoning_effort": _measurement_slot(
            value=None,
            coverage="unavailable",
            missing_reason=reason,
            scope="execution_attempt",
            attribution="unavailable",
        ),
        "tokens": _measurement_slot(
            value=None,
            coverage="unavailable",
            missing_reason=reason,
            scope="execution_attempt",
            attribution="unavailable",
        ),
        "duration": _measurement_slot(
            value=None,
            coverage="unavailable",
            missing_reason=reason,
            scope="execution_attempt",
            attribution="unavailable",
        ),
    }


def _valid_measurement(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {"model", "reasoning_effort", "tokens", "duration"}
        and _valid_measurement_slot(value["model"])
        and _valid_measurement_slot(value["reasoning_effort"])
        and _valid_measurement_slot(value["tokens"], numeric=True)
        and _valid_measurement_slot(value["duration"], duration=True)
    )


def measurement_from_host(value: dict[str, Any]) -> dict[str, Any]:
    requested_model = value.get("requested_model")
    applied_model = value.get("applied_model")
    requested_effort = value.get("requested_reasoning_effort")
    tokens = value.get("tokens")
    duration_ms = value.get("duration_ms")
    model_complete = (
        value.get("model_event_evidence") == "complete"
        and applied_model is not None
    )
    reason = (
        "request_metadata_only"
        if value.get("source") == "codex-desktop-request-meta"
        else "producer_did_not_expose"
    )
    return {
        "model": _measurement_slot(
            value=applied_model if model_complete else requested_model,
            coverage=(
                "complete"
                if model_complete
                else ("request_only" if requested_model is not None else "unavailable")
            ),
            missing_reason=(None if requested_model is not None or model_complete else reason),
            scope="request_turn",
            attribution=(
                "direct"
                if model_complete
                else ("requested" if requested_model is not None else "unavailable")
            ),
        ),
        "reasoning_effort": _measurement_slot(
            value=requested_effort,
            coverage="request_only" if requested_effort is not None else "unavailable",
            missing_reason=None if requested_effort is not None else reason,
            scope="request_turn",
            attribution="requested" if requested_effort is not None else "unavailable",
        ),
        "tokens": _measurement_slot(
            value=tokens,
            coverage="complete" if tokens is not None else "unavailable",
            missing_reason=None if tokens is not None else reason,
            scope="request_turn" if tokens is not None else "unavailable",
            attribution="direct" if tokens is not None else "unavailable",
        ),
        "duration": _measurement_slot(
            value={"total": duration_ms} if duration_ms is not None else None,
            coverage="complete" if duration_ms is not None else "unavailable",
            missing_reason=None if duration_ms is not None else reason,
            scope="request_turn",
            attribution="direct" if duration_ms is not None else "unavailable",
        ),
    }


def measurement_from_stage(value: dict[str, Any]) -> dict[str, Any]:
    requested_model = value.get("requested_model")
    applied_model = value.get("actual_model")
    requested_effort = value.get("requested_reasoning_effort")
    tokens = value.get("tokens")
    duration = value.get("duration_ms")
    model_complete = (
        value.get("model_evidence") == "complete"
        and applied_model is not None
    )
    unavailable_reason = (
        "not_applicable"
        if value.get("evidence_source") == "deterministic_command"
        else "producer_did_not_expose"
    )
    return {
        "model": _measurement_slot(
            value=applied_model if model_complete else requested_model,
            coverage=(
                "complete"
                if model_complete
                else ("request_only" if requested_model is not None else "unavailable")
            ),
            missing_reason=(
                None
                if model_complete or requested_model is not None
                else unavailable_reason
            ),
            scope="assignment_attempt",
            attribution=(
                "direct"
                if model_complete
                else ("requested" if requested_model is not None else "unavailable")
            ),
        ),
        "reasoning_effort": _measurement_slot(
            value=requested_effort,
            coverage="request_only" if requested_effort is not None else "unavailable",
            missing_reason=(
                None if requested_effort is not None else unavailable_reason
            ),
            scope="assignment_attempt",
            attribution="requested" if requested_effort is not None else "unavailable",
        ),
        "tokens": _measurement_slot(
            value=tokens,
            coverage="complete" if tokens is not None else "unavailable",
            missing_reason=None if tokens is not None else unavailable_reason,
            scope="assignment_attempt" if tokens is not None else "unavailable",
            attribution="direct" if tokens is not None else "unavailable",
        ),
        "duration": _measurement_slot(
            value={"total": duration} if duration is not None else None,
            coverage=(
                "complete"
                if duration is not None
                and value.get("evidence_source") == "codex_app_server"
                else ("collector_clock" if duration is not None else "unavailable")
            ),
            missing_reason=None if duration is not None else unavailable_reason,
            scope="assignment_attempt",
            attribution="direct" if duration is not None else "unavailable",
        ),
    }


def measurement_from_work(value: dict[str, Any]) -> dict[str, Any]:
    model_observation = value.get("model_observation")
    usage = value.get("usage")
    requested_model = value.get("requested_model")
    applied_model = value.get("applied_model")
    requested_effort = value.get("requested_reasoning_effort")
    model_coverage = (
        model_observation.get("coverage")
        if isinstance(model_observation, dict)
        else "unavailable"
    )
    model_value = (
        applied_model
        if model_coverage == "complete_stream"
        else requested_model
    )
    token_value = (
        usage.get("total")
        if isinstance(usage, dict)
        and usage.get("attribution") == "direct"
        else None
    )
    duration = value.get("duration_ms")
    running = value.get("status") == "running"
    reason = "work_running" if running else "producer_did_not_expose"
    return {
        "model": _measurement_slot(
            value=model_value,
            coverage=(
                "complete"
                if model_coverage == "complete_stream" and applied_model is not None
                else ("request_only" if requested_model is not None else "unavailable")
            ),
            missing_reason=None if model_value is not None else reason,
            scope="work_turn",
            attribution=(
                "direct"
                if applied_model is not None and model_coverage == "complete_stream"
                else ("requested" if requested_model is not None else "unavailable")
            ),
        ),
        "reasoning_effort": _measurement_slot(
            value=requested_effort,
            coverage="request_only" if requested_effort is not None else "unavailable",
            missing_reason=None if requested_effort is not None else reason,
            scope="work_turn",
            attribution="requested" if requested_effort is not None else "unavailable",
        ),
        "tokens": _measurement_slot(
            value=token_value,
            coverage="complete" if token_value is not None else "unavailable",
            missing_reason=None if token_value is not None else reason,
            scope="work_turn" if token_value is not None else "unavailable",
            attribution="direct" if token_value is not None else "unavailable",
        ),
        "duration": _measurement_slot(
            value={"total": duration} if duration is not None else None,
            coverage=(
                "complete"
                if duration is not None
                and isinstance(usage, dict)
                and usage.get("timing_coverage") == "host_event"
                else ("collector_clock" if duration is not None else "unavailable")
            ),
            missing_reason=None if duration is not None else reason,
            scope="work_attempt",
            attribution="direct" if duration is not None else "unavailable",
        ),
    }


def _event_id(
    *,
    run_id: str,
    event_type: str,
    idempotency_key: str,
    producer: dict[str, Any],
    payload: dict[str, Any],
    measurement: dict[str, Any] | None,
) -> str:
    return sha256_text(
        canonical_json(
            {
                "run_id": run_id,
                "event_type": event_type,
                "idempotency_key": idempotency_key,
                "producer": producer,
                "payload": payload,
                "measurement": measurement,
            }
        )
    )


def new_execution_ledger(
    *,
    observation_id: str,
    run_id: str,
    recorded_at: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    ledger = {
        "schema_version": EXECUTION_LEDGER_VERSION,
        "observation_id": observation_id,
        "run_id": run_id,
        "origin": "native",
        "revision": 0,
        "events": [],
    }
    ledger, changed = append_execution_event(
        ledger,
        event_type="execution_started",
        idempotency_key="execution:start",
        producer=producer_binding(
            "maestro_core",
            capability="lifecycle_only",
            event_coverage="partial_stream",
        ),
        payload=payload,
        measurement=None,
        recorded_at=recorded_at,
    )
    assert changed
    return ledger


def append_execution_event(
    ledger: dict[str, Any],
    *,
    event_type: str,
    idempotency_key: str,
    producer: dict[str, Any],
    payload: dict[str, Any],
    measurement: dict[str, Any] | None,
    recorded_at: str,
) -> tuple[dict[str, Any], bool]:
    if not validate_execution_ledger(ledger, allow_empty=True):
        raise MaestroError(
            "EXECUTION_LEDGER_INVALID",
            "The semantic execution ledger is invalid.",
        )
    if (
        event_type not in EVENT_TYPES
        or not _line(idempotency_key, 200)
        or not _valid_producer(producer)
        or not isinstance(payload, dict)
        or (measurement is not None and not _valid_measurement(measurement))
        or not _line(recorded_at, 40)
    ):
        raise MaestroError(
            "EXECUTION_EVENT_INVALID",
            "Execution event fields do not satisfy the bounded semantic contract.",
        )
    events = ledger["events"]
    if any(event["event_type"] == "execution_sealed" for event in events):
        raise MaestroError(
            "EXECUTION_LEDGER_SEALED",
            "A sealed execution cannot accept new facts.",
        )
    event_id = _event_id(
        run_id=ledger["run_id"],
        event_type=event_type,
        idempotency_key=idempotency_key,
        producer=producer,
        payload=payload,
        measurement=measurement,
    )
    existing = next(
        (
            event
            for event in events
            if event["event_type"] == event_type
            and event["idempotency_key"] == idempotency_key
        ),
        None,
    )
    if existing is not None:
        if existing["event_id"] == event_id:
            return copy.deepcopy(ledger), False
        raise MaestroError(
            "EXECUTION_EVENT_CONFLICT",
            "The event identity already contains different semantic facts.",
        )
    if len(events) >= MAX_EXECUTION_EVENTS:
        raise MaestroError(
            "EXECUTION_LEDGER_LIMIT_EXCEEDED",
            "The execution ledger reached its bounded event limit.",
        )
    event = {
        "schema_version": EXECUTION_EVENT_VERSION,
        "sequence": len(events) + 1,
        "event_id": event_id,
        "event_type": event_type,
        "idempotency_key": idempotency_key,
        "recorded_at": recorded_at,
        "producer": copy.deepcopy(producer),
        "payload": copy.deepcopy(payload),
        "measurement": copy.deepcopy(measurement),
    }
    updated = copy.deepcopy(ledger)
    updated["events"].append(event)
    updated["revision"] = len(updated["events"])
    if len(canonical_json(updated).encode("utf-8")) > MAX_EXECUTION_LEDGER_BYTES:
        raise MaestroError(
            "EXECUTION_LEDGER_TOO_LARGE",
            "The bounded semantic execution ledger exceeds its byte limit.",
        )
    if not validate_execution_ledger(updated):
        raise MaestroError(
            "EXECUTION_LEDGER_INVALID",
            "The appended semantic execution ledger is invalid.",
        )
    return updated, True


def validate_execution_ledger(
    value: Any,
    *,
    allow_empty: bool = False,
) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "observation_id",
            "run_id",
            "origin",
            "revision",
            "events",
        }
        or value.get("schema_version") != EXECUTION_LEDGER_VERSION
        or not _line(value.get("observation_id"), 64)
        or not _line(value.get("run_id"), 160)
        or value.get("origin") not in {"native", "legacy_import"}
        or not isinstance(value.get("revision"), int)
        or isinstance(value.get("revision"), bool)
        or not isinstance(value.get("events"), list)
        or len(value["events"]) > MAX_EXECUTION_EVENTS
        or value["revision"] != len(value["events"])
        or (not allow_empty and not value["events"])
    ):
        return False
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    sealed = False
    for index, event in enumerate(value["events"], 1):
        if (
            not isinstance(event, dict)
            or set(event)
            != {
                "schema_version",
                "sequence",
                "event_id",
                "event_type",
                "idempotency_key",
                "recorded_at",
                "producer",
                "payload",
                "measurement",
            }
            or event.get("schema_version") != EXECUTION_EVENT_VERSION
            or event.get("sequence") != index
            or event.get("event_type") not in EVENT_TYPES
            or not _line(event.get("event_id"), 64)
            or not _line(event.get("idempotency_key"), 200)
            or not _line(event.get("recorded_at"), 40)
            or not _valid_producer(event.get("producer"))
            or not isinstance(event.get("payload"), dict)
            or (
                event.get("measurement") is not None
                and not _valid_measurement(event["measurement"])
            )
            or event["event_id"]
            != _event_id(
                run_id=value["run_id"],
                event_type=event["event_type"],
                idempotency_key=event["idempotency_key"],
                producer=event["producer"],
                payload=event["payload"],
                measurement=event["measurement"],
            )
            or event["event_id"] in seen_ids
            or (
                event["event_type"],
                event["idempotency_key"],
            )
            in seen_keys
            or sealed
        ):
            return False
        seen_ids.add(event["event_id"])
        seen_keys.add((event["event_type"], event["idempotency_key"]))
        sealed = event["event_type"] == "execution_sealed"
    return (
        not value["events"]
        or value["events"][0]["event_type"] == "execution_started"
    )


def _legacy_ledger(observation: dict[str, Any]) -> dict[str, Any]:
    observation_id = observation.get("observation_id")
    run_id = observation.get("run_id")
    started_at = observation.get("started_at")
    task_label = observation.get("task_label")
    if (
        not _line(observation_id, 64)
        or not _line(run_id, 160)
        or not _line(started_at, 40)
        or not _line(task_label, 160)
    ):
        raise MaestroError(
            "EXECUTION_LEDGER_LEGACY_INVALID",
            "The legacy observation lacks the identity needed for projection.",
        )
    ledger = {
        "schema_version": EXECUTION_LEDGER_VERSION,
        "observation_id": observation_id,
        "run_id": run_id,
        "origin": "legacy_import",
        "revision": 0,
        "events": [],
    }
    legacy_producer = producer_binding(
        "legacy_import",
        capability="unavailable",
        event_coverage="unavailable",
    )

    def append(
        event_type: str,
        key: str,
        payload: dict[str, Any],
        *,
        measurement: dict[str, Any] | None = None,
        recorded_at: str | None = None,
        producer: dict[str, Any] = legacy_producer,
    ) -> None:
        nonlocal ledger
        ledger, _ = append_execution_event(
            ledger,
            event_type=event_type,
            idempotency_key=key,
            producer=producer,
            payload=payload,
            measurement=measurement,
            recorded_at=recorded_at or started_at,
        )

    append(
        "execution_started",
        "execution:start",
        {
            "task_label": task_label,
            "started_at": started_at,
        },
    )
    if isinstance(observation.get("plan_summary"), dict):
        append(
            "plan_attached",
            "plan:attached",
            {"plan_summary": observation["plan_summary"]},
            recorded_at=observation.get("plan_attached_at") or started_at,
        )
    if isinstance(observation.get("execution_binding"), dict):
        append(
            "execution_binding_changed",
            (
                "execution:binding:"
                f"{observation['execution_binding'].get('mode', 'legacy')}"
            ),
            {"execution_binding": observation["execution_binding"]},
            recorded_at=observation.get("fallback_recorded_at") or started_at,
        )
    host = observation.get("host_observation")
    if isinstance(host, dict):
        append(
            "measurement_observed",
            "measurement:legacy-host",
            {"host_observation": host},
            measurement=measurement_from_host(host),
            recorded_at=host.get("observed_at") or started_at,
        )
    for span in observation.get("work_spans", []):
        if not isinstance(span, dict):
            continue
        append(
            "work_started" if span.get("status") == "running" else "work_terminal",
            (
                f"work:{span.get('work_id')}:start"
                if span.get("status") == "running"
                else f"work:{span.get('work_id')}:terminal"
            ),
            {"work_span": span},
            measurement=measurement_from_work(span),
            recorded_at=span.get("ended_at") or span.get("started_at") or started_at,
        )
    for stage in observation.get("stage_results", []):
        if not isinstance(stage, dict):
            continue
        append(
            "assignment_terminal",
            f"assignment:{stage.get('assignment_id')}:terminal",
            {"stage_result": stage},
            measurement=measurement_from_stage(stage),
            recorded_at=stage.get("observed_at") or started_at,
        )
    if observation.get("completed_at") is not None:
        append(
            "execution_sealed",
            "execution:seal",
            {
                "completed_at": observation["completed_at"],
                "duration_ms": observation.get("duration_ms"),
            },
            recorded_at=observation["completed_at"],
        )
    return ledger


def ensure_execution_ledger(
    observation: dict[str, Any],
) -> dict[str, Any]:
    ledger = observation.get("execution_ledger")
    if ledger is None:
        return _legacy_ledger(observation)
    if (
        not validate_execution_ledger(ledger)
        or ledger.get("observation_id") != observation.get("observation_id")
        or ledger.get("run_id") != observation.get("run_id")
    ):
        raise MaestroError(
            "EXECUTION_LEDGER_INVALID",
            "The execution ledger does not match this observation.",
        )
    return copy.deepcopy(ledger)


@contextmanager
def observation_write_lock(target: Path) -> Iterator[None]:
    if fcntl is None:  # pragma: no cover
        raise MaestroError(
            "OBSERVATION_LOCK_UNAVAILABLE",
            "This Host does not provide the required interprocess file lock.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f".{target.name}.lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise MaestroError(
            "OBSERVATION_LOCK_FAILED",
            f"Could not open the observation lock: {exc}",
        ) from exc
    try:
        with os.fdopen(descriptor, "a+b", closefd=True) as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise MaestroError(
            "OBSERVATION_LOCK_FAILED",
            f"Could not lock the observation: {exc}",
        ) from exc


def commit_execution_transition(
    target: Path,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    event_type: str,
    idempotency_key: str,
    producer: dict[str, Any],
    payload: dict[str, Any],
    measurement: dict[str, Any] | None,
    recorded_at: str,
) -> dict[str, Any]:
    """Atomically append one semantic event and update compatibility projections."""

    with observation_write_lock(target):
        current = read_json(target)
        if canonical_json(current) != canonical_json(before):
            raise MaestroError(
                "RUN_OBSERVATION_STALE_REVISION",
                "The observation changed concurrently; reload before retrying.",
            )
        ledger = ensure_execution_ledger(before)
        ledger, changed = append_execution_event(
            ledger,
            event_type=event_type,
            idempotency_key=idempotency_key,
            producer=producer,
            payload=payload,
            measurement=measurement,
            recorded_at=recorded_at,
        )
        if not changed:
            return current
        updated = copy.deepcopy(after)
        updated["execution_ledger"] = ledger
        atomic_write(target, pretty_json(updated).encode("utf-8"))
        return updated


def _sum_numeric_maps(values: list[Any]) -> dict[str, int] | None:
    measured = [
        value
        for value in values
        if isinstance(value, dict)
        and any(
            isinstance(item, int) and not isinstance(item, bool)
            for item in value.values()
        )
    ]
    if not measured:
        return None
    keys = {
        key
        for value in measured
        for key, item in value.items()
        if isinstance(item, int) and not isinstance(item, bool)
    }
    return {
        key: sum(
            value.get(key, 0)
            for value in measured
            if isinstance(value.get(key, 0), int)
            and not isinstance(value.get(key, 0), bool)
        )
        for key in sorted(keys)
    }


def execution_measurements(
    ledger: dict[str, Any],
    *,
    duration_ms: float | None,
) -> dict[str, Any]:
    if not validate_execution_ledger(ledger):
        raise MaestroError(
            "EXECUTION_LEDGER_INVALID",
            "Measurements require a valid semantic execution ledger.",
        )
    measured_events = [
        event
        for event in ledger["events"]
        if isinstance(event.get("measurement"), dict)
    ]
    work_terminal = [
        event for event in measured_events if event["event_type"] == "work_terminal"
    ]
    work_started = [
        event for event in measured_events if event["event_type"] == "work_started"
    ]
    assignment_terminal = [
        event
        for event in measured_events
        if event["event_type"] == "assignment_terminal"
    ]
    host_measurements = [
        event
        for event in measured_events
        if event["event_type"] == "measurement_observed"
    ]
    selected_for_models = [
        *work_started,
        *work_terminal,
        *assignment_terminal,
        *host_measurements,
    ]
    requested_models: list[str] = []
    applied_models: list[str] = []
    requested_efforts: list[str] = []
    for event in selected_for_models:
        measurement = event["measurement"]
        model = measurement["model"]
        if model["coverage"] == "complete":
            applied_models.append(model["value"])
        elif model["coverage"] == "request_only":
            requested_models.append(model["value"])
        reasoning = measurement["reasoning_effort"]
        if reasoning["coverage"] == "request_only":
            requested_efforts.append(reasoning["value"])
        payload = event["payload"]
        source_value = (
            payload.get("work_span")
            or payload.get("stage_result")
            or payload.get("host_observation")
            or {}
        )
        if isinstance(source_value, dict):
            requested = source_value.get("requested_model")
            if isinstance(requested, str) and requested:
                requested_models.append(requested)
    requested_models = list(dict.fromkeys(requested_models))
    applied_models = list(dict.fromkeys(applied_models))
    requested_efforts = list(dict.fromkeys(requested_efforts))

    work_tokens = [
        event["measurement"]["tokens"]["value"]
        for event in work_terminal
        if event["measurement"]["tokens"]["coverage"] == "complete"
        and event["measurement"]["tokens"]["attribution"] == "direct"
    ]
    assignment_ids_with_work = {
        event["payload"].get("work_span", {}).get("assignment_id")
        for event in work_terminal
        if isinstance(event["payload"].get("work_span"), dict)
    }
    stage_tokens = [
        event["measurement"]["tokens"]["value"]
        for event in assignment_terminal
        if event["measurement"]["tokens"]["coverage"] == "complete"
        and event["payload"].get("stage_result", {}).get("assignment_id")
        not in assignment_ids_with_work
    ]
    host_tokens = [
        event["measurement"]["tokens"]["value"]
        for event in host_measurements
        if event["measurement"]["tokens"]["coverage"] == "complete"
    ]
    if work_tokens:
        tokens = _sum_numeric_maps(work_tokens)
        token_source = "direct_work_attempts"
        token_scope = "work_turns"
    elif stage_tokens:
        tokens = _sum_numeric_maps(stage_tokens)
        token_source = "direct_assignment_attempts"
        token_scope = "assignments"
    else:
        tokens = _sum_numeric_maps(host_tokens)
        token_source = "host_request_turn" if tokens is not None else "unavailable"
        token_scope = "request_turn" if tokens is not None else "unavailable"

    host_durations = [
        event["measurement"]["duration"]["value"]["total"]
        for event in host_measurements
        if event["measurement"]["duration"]["coverage"] == "complete"
        and isinstance(event["measurement"]["duration"]["value"], dict)
    ]
    measured_duration_ms = (
        host_durations[-1] if host_durations else duration_ms
    )
    duration_coverage = (
        "complete"
        if host_durations
        else ("collector_clock" if duration_ms is not None else "unavailable")
    )
    model_coverage = (
        "complete"
        if applied_models
        else ("request_only" if requested_models else "unavailable")
    )
    token_coverage = "complete" if tokens is not None else "unavailable"
    missing_measurements = [
        slot.get("missing_reason")
        for event in selected_for_models
        for slot in event["measurement"].values()
        if isinstance(slot, dict) and slot.get("missing_reason") is not None
    ]
    summary_missing_reason = (
        "request_metadata_only"
        if "request_metadata_only" in missing_measurements
        else "producer_did_not_expose"
    )
    return {
        "schema_version": EXECUTION_MEASUREMENTS_VERSION,
        "ledger_revision": ledger["revision"],
        "ledger_event_count": len(ledger["events"]),
        "ledger_digest": sha256_text(canonical_json(ledger)),
        "model": {
            "requested": requested_models,
            "applied": applied_models,
            "coverage": model_coverage,
            "missing_reason": (
                None
                if applied_models
                else (
                    "request_metadata_only"
                    if requested_models
                    else summary_missing_reason
                )
            ),
        },
        "reasoning_effort": {
            "requested": requested_efforts,
            "applied": [],
            "coverage": "request_only" if requested_efforts else "unavailable",
            "missing_reason": (
                summary_missing_reason
            ),
        },
        "tokens": {
            "value": tokens,
            "coverage": token_coverage,
            "scope": token_scope,
            "attribution": "direct" if tokens is not None else "unavailable",
            "source": token_source,
            "missing_reason": (
                None if tokens is not None else summary_missing_reason
            ),
        },
        "duration": {
            "value_ms": measured_duration_ms,
            "coverage": duration_coverage,
            "scope": "managed_run",
            "attribution": (
                "direct" if measured_duration_ms is not None else "unavailable"
            ),
            "missing_reason": (
                None
                if measured_duration_ms is not None
                else "producer_did_not_expose"
            ),
        },
        "producer_coverage": [
            {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "interface": event["producer"]["interface"],
                "capability": event["producer"]["capability"],
                "event_coverage": event["producer"]["event_coverage"],
                "model": event["measurement"]["model"]["coverage"],
                "reasoning_effort": event["measurement"][
                    "reasoning_effort"
                ]["coverage"],
                "tokens": event["measurement"]["tokens"]["coverage"],
                "duration": event["measurement"]["duration"]["coverage"],
            }
            for event in measured_events
        ],
    }


def validate_execution_measurements(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "ledger_revision",
            "ledger_event_count",
            "ledger_digest",
            "model",
            "reasoning_effort",
            "tokens",
            "duration",
            "producer_coverage",
        }
        or value.get("schema_version") != EXECUTION_MEASUREMENTS_VERSION
        or not isinstance(value.get("ledger_revision"), int)
        or isinstance(value.get("ledger_revision"), bool)
        or not 1 <= value["ledger_revision"] <= MAX_EXECUTION_EVENTS
        or not isinstance(value.get("ledger_event_count"), int)
        or isinstance(value.get("ledger_event_count"), bool)
        or not 1 <= value["ledger_event_count"] <= MAX_EXECUTION_EVENTS
        or value["ledger_revision"] != value["ledger_event_count"]
        or not _sha256_digest(value.get("ledger_digest"))
    ):
        return False
    model = value.get("model")
    reasoning = value.get("reasoning_effort")
    tokens = value.get("tokens")
    duration = value.get("duration")
    if (
        not isinstance(model, dict)
        or set(model) != {"requested", "applied", "coverage", "missing_reason"}
        or not all(
            isinstance(items, list)
            and len(items) == len(set(items))
            and all(_line(item, 128) for item in items)
            for items in (model.get("requested"), model.get("applied"))
        )
        or model.get("coverage") not in {"complete", "request_only", "unavailable"}
        or model.get("missing_reason") not in MISSING_REASONS
        or not isinstance(reasoning, dict)
        or set(reasoning)
        != {"requested", "applied", "coverage", "missing_reason"}
        or not all(
            isinstance(items, list)
            and len(items) == len(set(items))
            and all(_line(item, 40) for item in items)
            for items in (
                reasoning.get("requested"),
                reasoning.get("applied"),
            )
        )
        or reasoning.get("coverage") not in {"request_only", "unavailable"}
        or reasoning.get("missing_reason") not in MISSING_REASONS
        or not isinstance(tokens, dict)
        or set(tokens)
        != {
            "value",
            "coverage",
            "scope",
            "attribution",
            "source",
            "missing_reason",
        }
        or not _numeric_map(tokens.get("value"))
        or tokens.get("coverage") not in {"complete", "unavailable"}
        or not _line(tokens.get("scope"), 40)
        or not _line(tokens.get("attribution"), 40)
        or not _line(tokens.get("source"), 80)
        or tokens.get("missing_reason") not in MISSING_REASONS
        or not isinstance(duration, dict)
        or set(duration)
        != {
            "value_ms",
            "coverage",
            "scope",
            "attribution",
            "missing_reason",
        }
        or (
            duration.get("value_ms") is not None
            and (
                not isinstance(duration["value_ms"], (int, float))
                or isinstance(duration["value_ms"], bool)
                or not math.isfinite(duration["value_ms"])
                or duration["value_ms"] < 0
            )
        )
        or duration.get("coverage")
        not in {"complete", "collector_clock", "unavailable"}
        or not _line(duration.get("scope"), 40)
        or not _line(duration.get("attribution"), 40)
        or duration.get("missing_reason") not in MISSING_REASONS
    ):
        return False
    requested_models = model["requested"]
    applied_models = model["applied"]
    if model["coverage"] == "complete":
        if not applied_models or model["missing_reason"] is not None:
            return False
    elif model["coverage"] == "request_only":
        if (
            not requested_models
            or applied_models
            or model["missing_reason"] is None
        ):
            return False
    elif (
        requested_models
        or applied_models
        or model["missing_reason"] is None
    ):
        return False
    requested_efforts = reasoning["requested"]
    if reasoning["coverage"] == "request_only":
        if (
            not requested_efforts
            or reasoning["applied"]
            or reasoning["missing_reason"] is None
        ):
            return False
    elif (
        requested_efforts
        or reasoning["applied"]
        or reasoning["missing_reason"] is None
    ):
        return False
    if tokens["value"] is None:
        if (
            tokens["coverage"] != "unavailable"
            or tokens["attribution"] != "unavailable"
            or tokens["source"] != "unavailable"
            or tokens["missing_reason"] is None
        ):
            return False
    elif (
        tokens["coverage"] != "complete"
        or tokens["scope"] == "unavailable"
        or tokens["attribution"] != "direct"
        or tokens["source"] == "unavailable"
        or tokens["missing_reason"] is not None
    ):
        return False
    if duration["value_ms"] is None:
        if (
            duration["coverage"] != "unavailable"
            or duration["attribution"] != "unavailable"
            or duration["missing_reason"] is None
        ):
            return False
    elif (
        duration["coverage"] not in {"complete", "collector_clock"}
        or duration["scope"] == "unavailable"
        or duration["attribution"] != "direct"
        or duration["missing_reason"] is not None
    ):
        return False
    producers = value.get("producer_coverage")
    valid_producers = (
        isinstance(producers, list)
        and len(producers) <= MAX_EXECUTION_EVENTS
        and all(
            isinstance(item, dict)
            and set(item)
            == {
                "event_id",
                "event_type",
                "interface",
                "capability",
                "event_coverage",
                "model",
                "reasoning_effort",
                "tokens",
                "duration",
            }
            and _sha256_digest(item.get("event_id"))
            and item.get("event_type") in EVENT_TYPES
            and item.get("interface") in PRODUCER_INTERFACES
            and item.get("capability") in PRODUCER_CAPABILITIES
            and item.get("event_coverage") in EVENT_COVERAGE
            and item.get("model") in MEASUREMENT_COVERAGE
            and item.get("reasoning_effort") in MEASUREMENT_COVERAGE
            and item.get("tokens") in MEASUREMENT_COVERAGE
            and item.get("duration") in MEASUREMENT_COVERAGE
            for item in producers
        )
    )
    return (
        valid_producers
        and len(producers) <= value["ledger_event_count"]
    )


def completion_evaluation_for_observation(
    observation: dict[str, Any],
    *,
    receipt_intent_digest: str | None,
) -> dict[str, Any]:
    ledger = ensure_execution_ledger(observation)
    if ledger.get("origin") == "legacy_import" or observation.get(
        "completion_policy"
    ) is None:
        return {
            "schema_version": "maestro_completion_evaluation_v1",
            "status": "not_managed",
            "issues": [],
            "closure": None,
        }
    return evaluate_completion(
        policy=observation.get("completion_policy"),
        plan_summary=observation.get("plan_summary"),
        stage_results=observation.get("stage_results"),
        work_spans=observation.get("work_spans"),
        pre_seal_ledger_revision=ledger["revision"],
        pre_seal_ledger_digest=sha256_text(canonical_json(ledger)),
        receipt_intent=receipt_intent_digest,
    )


def seal_readiness_error(
    observation: dict[str, Any],
    *,
    receipt_intent_digest: str | None = None,
) -> str | None:
    completion = completion_evaluation_for_observation(
        observation,
        receipt_intent_digest=receipt_intent_digest,
    )
    if completion["status"] == "blocked":
        issue = completion["issues"][0]
        related = issue.get("related_ids", [])
        suffix = (
            " related=" + ",".join(str(item) for item in related)
            if related
            else ""
        )
        return f"{issue['code']}: {issue['message']}{suffix}"
    if completion["status"] == "ready":
        return None

    work_spans = observation.get("work_spans", [])
    running = [
        span.get("work_id")
        for span in work_spans
        if isinstance(span, dict) and span.get("status") == "running"
    ]
    if running:
        return "running work remains: " + ",".join(
            str(item) for item in running
        )
    plan = observation.get("plan_summary")
    if isinstance(plan, dict):
        planned = {
            assignment.get("assignment_id")
            for assignment in plan.get("assignments", [])
            if isinstance(assignment, dict)
        }
        terminal = {
            stage.get("assignment_id")
            for stage in observation.get("stage_results", [])
            if isinstance(stage, dict)
        }
        missing = sorted(
            item for item in planned - terminal if isinstance(item, str)
        )
        if missing:
            return "terminal Assignment evidence is missing: " + ",".join(missing)
    return None
