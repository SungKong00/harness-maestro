from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .planning import validate_route_v2
from .project import checkout_id
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    pretty_json,
    read_json,
    safe_target,
    sha256_text,
)

OBSERVATION_VERSION = "maestro_run_observation_v1"
LEGACY_HOST_OBSERVATION_VERSION = "maestro_host_observation_v1"
HOST_OBSERVATION_VERSION = "maestro_host_observation_v2"
MAX_TASK_LABEL_LENGTH = 160
MAX_PLAN_ASSIGNMENTS = 5
MAX_INFLIGHT_OBSERVATIONS = 100
MAX_OBSERVATION_FILE_BYTES = 128_000
MAX_MODEL_REROUTES = 4
MAX_APP_SERVER_TRACE_BYTES = 4_000_000
MAX_APP_SERVER_TRACE_MESSAGES = 20_000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _task_label(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_TASK_LABEL_LENGTH
        or any(character in value for character in "\r\n\x00")
    ):
        raise MaestroError(
            "RUN_OBSERVATION_LABEL_INVALID",
            "task-label must be a single non-empty line of at most "
            f"{MAX_TASK_LABEL_LENGTH} characters.",
        )
    return value.strip()


def _bounded_line(value: Any, *, field: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(character in value for character in "\r\n\x00")
    ):
        raise MaestroError(
            "HOST_OBSERVATION_INVALID",
            f"{field} must be one non-empty line of at most {maximum} characters.",
        )
    return value.strip()


def _valid_token_summary(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or "total" not in value:
        return False
    if set(value) - {
        "input",
        "output",
        "cached",
        "reasoning",
        "total",
        "parent_context_total",
        "total_system",
    }:
        return False
    return all(
        item is None
        or (
            isinstance(item, int)
            and not isinstance(item, bool)
            and item >= 0
        )
        for item in value.values()
    )


def _valid_model(value: Any) -> bool:
    return (
        value is None
        or (
            isinstance(value, str)
            and bool(value.strip())
            and len(value) <= 128
            and not any(character in value for character in "\r\n\x00")
        )
    )


def _valid_reasoning_effort(value: Any) -> bool:
    return (
        value is None
        or (
            isinstance(value, str)
            and bool(value.strip())
            and len(value) <= 40
            and not any(character in value for character in "\r\n\x00")
        )
    )


def _valid_legacy_host_observation(value: dict[str, Any]) -> bool:
    if set(value) != {
        "schema_version",
        "source",
        "quality",
        "correlation_id",
        "actual_model",
        "tokens",
        "observed_at",
    }:
        return False
    actual_model = value.get("actual_model")
    tokens = value.get("tokens")
    return (
        value.get("schema_version") == LEGACY_HOST_OBSERVATION_VERSION
        and _valid_host_observation_identity(value)
        and _valid_model(actual_model)
        and _valid_token_summary(tokens)
        and (actual_model is not None or tokens is not None)
        and _parse_timestamp(value.get("observed_at")) is not None
    )


def _valid_host_observation_identity(value: dict[str, Any]) -> bool:
    return (
        isinstance(value.get("source"), str)
        and bool(value["source"].strip())
        and len(value["source"]) <= 80
        and not any(character in value["source"] for character in "\r\n\x00")
        and value.get("quality") in {"host_reported", "host_delta"}
        and isinstance(value.get("correlation_id"), str)
        and bool(value["correlation_id"].strip())
        and len(value["correlation_id"]) <= 160
        and not any(
            character in value["correlation_id"]
            for character in "\r\n\x00"
        )
    )


def _valid_model_reroutes(
    value: Any,
    *,
    requested_model: str | None,
    applied_model: str | None,
) -> bool:
    if (
        not isinstance(value, list)
        or len(value) > MAX_MODEL_REROUTES
    ):
        return False
    previous = requested_model
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"from_model", "to_model", "reason"}
            or not _valid_model(item.get("from_model"))
            or not _valid_model(item.get("to_model"))
            or item.get("from_model") is None
            or item.get("to_model") is None
            or not isinstance(item.get("reason"), str)
            or not item["reason"].strip()
            or len(item["reason"]) > 240
            or any(character in item["reason"] for character in "\r\n\x00")
            or item["from_model"] != previous
        ):
            return False
        previous = item["to_model"]
    return previous == applied_model


def _valid_host_observation(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") == LEGACY_HOST_OBSERVATION_VERSION:
        return _valid_legacy_host_observation(value)
    required_fields = {
        "schema_version",
        "source",
        "quality",
        "correlation_id",
        "requested_model",
        "applied_model",
        "model_event_evidence",
        "reroutes",
        "tokens",
        "observed_at",
    }
    optional_fields = {
        "requested_reasoning_effort",
        "reasoning_effort_evidence",
    }
    if (
        not required_fields.issubset(value)
        or set(value) - required_fields - optional_fields
    ):
        return False
    requested_model = value.get("requested_model")
    applied_model = value.get("applied_model")
    requested_reasoning_effort = value.get(
        "requested_reasoning_effort",
    )
    reasoning_effort_evidence = value.get(
        "reasoning_effort_evidence",
        "unavailable",
    )
    model_event_evidence = value.get("model_event_evidence")
    reroutes = value.get("reroutes")
    tokens = value.get("tokens")
    if not (
        value.get("schema_version") == HOST_OBSERVATION_VERSION
        and _valid_host_observation_identity(value)
        and _valid_model(requested_model)
        and _valid_model(applied_model)
        and _valid_reasoning_effort(requested_reasoning_effort)
        and reasoning_effort_evidence in {
            "unavailable",
            "host_request",
        }
        and model_event_evidence in {"unavailable", "complete"}
        and _valid_token_summary(tokens)
        and (
            requested_model is not None
            or applied_model is not None
            or tokens is not None
        )
        and _parse_timestamp(value.get("observed_at")) is not None
    ):
        return False
    if (
        requested_reasoning_effort is None
        and reasoning_effort_evidence != "unavailable"
    ) or (
        requested_reasoning_effort is not None
        and reasoning_effort_evidence != "host_request"
    ):
        return False
    if model_event_evidence == "unavailable":
        return applied_model is None and reroutes == []
    return (
        requested_model is not None
        and applied_model is not None
        and _valid_model_reroutes(
            reroutes,
            requested_model=requested_model,
            applied_model=applied_model,
        )
    )


def _read_observation_file(path: Path) -> dict[str, Any]:
    try:
        valid = (
            not path.is_symlink()
            and path.is_file()
            and path.stat().st_size <= MAX_OBSERVATION_FILE_BYTES
        )
    except OSError:
        valid = False
    if not valid:
        raise MaestroError(
            "RUN_OBSERVATION_INVALID",
            "The observation file is missing, unsafe, or exceeds its size limit.",
        )
    value = read_json(path)
    if not isinstance(value, dict):
        raise MaestroError(
            "RUN_OBSERVATION_INVALID",
            "The observation file must contain one object.",
        )
    return value


def _plan_summary(repo: Path, plan_path: str | Path | None) -> dict[str, Any] | None:
    if plan_path is None:
        return None
    path = Path(plan_path).expanduser().resolve()
    plan = read_json(path)
    validation = validate_route_v2(plan, repo_path=repo)
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(
            "RUN_OBSERVATION_PLAN_INVALID",
            f"{first['code']}: {first['message']}",
        )
    assignments = plan.get("assignments", [])
    if not isinstance(assignments, list) or len(assignments) > MAX_PLAN_ASSIGNMENTS:
        raise MaestroError(
            "RUN_OBSERVATION_PLAN_INVALID",
            "A monitored plan may contain at most five Assignments.",
        )
    expertise = plan.get("expertise")
    research = (
        expertise.get("research_requirement")
        if isinstance(expertise, dict)
        else None
    )
    return {
        "schema_version": "maestro_plan_summary_v1",
        "plan_id": plan["plan_id"],
        "intent": plan["intent"],
        "department": plan["department"],
        "assignments": [
            {
                "assignment_id": assignment["assignment_id"],
                "kind": assignment["kind"],
                "executor_id": assignment["executor_id"],
                "depends_on": list(assignment["depends_on"]),
                "planned_model": assignment["model_route"]["selected_model"],
                "reasoning_effort": assignment["model_route"][
                    "reasoning_effort"
                ],
                "expertise_pack_ids": list(
                    assignment.get("expertise_pack_ids", [])
                ),
                "decision_guide_ids": list(
                    assignment.get("decision_guide_ids", [])
                ),
            }
            for assignment in assignments
        ],
        "research": (
            {
                "mode": research["mode"],
                "gate": research["gate"],
            }
            if isinstance(research, dict)
            else {"mode": "reuse", "gate": "not-required"}
        ),
    }


def start_run_observation(
    repo_path: str | Path,
    *,
    run_id: str,
    task_label: str,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    project = read_json(safe_target(repo, ".maestro/project.json"))
    project_id = project.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise MaestroError(
            "PROJECT_STATE_INVALID",
            "project_id must be a non-empty string.",
        )
    if not isinstance(run_id, str) or not run_id.strip():
        raise MaestroError(
            "RUN_OBSERVATION_ID_INVALID",
            "run-id must be a non-empty string.",
        )
    label = _task_label(task_label)
    current_checkout = checkout_id(repo)
    observation_id = sha256_text(
        canonical_json(
            {
                "project_id": project_id,
                "checkout_id": current_checkout,
                "run_id": run_id,
            }
        )
    )[:32]
    relative_path = f".maestro/state/inflight/{observation_id}.json"
    target = safe_target(repo, relative_path)
    value = {
        "schema_version": OBSERVATION_VERSION,
        "observation_id": observation_id,
        "project_id": project_id,
        "checkout_id": current_checkout,
        "run_id": run_id,
        "task_label": label,
        "started_at": _timestamp(_utc_now()),
        "plan_summary": _plan_summary(repo, plan_path),
    }
    if target.exists() or target.is_symlink():
        existing = _read_observation_file(target)
        runtime_fields = {
            "started_at",
            "host_observation",
            "completed_at",
            "duration_ms",
        }
        comparable = {
            key: item
            for key, item in existing.items()
            if key not in runtime_fields
        }
        expected = {
            key: item
            for key, item in value.items()
            if key not in runtime_fields
        }
        if comparable != expected:
            raise MaestroError(
                "RUN_OBSERVATION_CONFLICT",
                "The run ID already has a different in-flight observation.",
            )
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "observe-start",
            "status": "already_started",
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation_id,
            "observation_path": relative_path,
            "writes_performed": False,
        }
    atomic_write(target, pretty_json(value).encode("utf-8"))
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-start",
        "status": "started",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "observation_path": relative_path,
        "writes_performed": True,
    }


def start_desktop_request_observation(
    repo_path: str | Path,
    *,
    run_id: str,
    task_label: str,
    thread_id: str,
    turn_id: str,
    requested_model: str,
    requested_reasoning_effort: str | None = None,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """Start a run and attach allowlisted Codex Desktop request data."""

    thread = _bounded_line(
        thread_id,
        field="thread-id",
        maximum=72,
    )
    turn = _bounded_line(
        turn_id,
        field="turn-id",
        maximum=72,
    )
    model = _bounded_line(
        requested_model,
        field="requested-model",
        maximum=128,
    )
    effort = (
        _bounded_line(
            requested_reasoning_effort,
            field="requested-reasoning-effort",
            maximum=40,
        )
        if requested_reasoning_effort is not None
        else None
    )
    started = start_run_observation(
        repo_path,
        run_id=run_id,
        task_label=task_label,
        plan_path=plan_path,
    )
    attached = record_host_observation(
        repo_path,
        observation_id=started["observation_id"],
        run_id=run_id,
        source="codex-desktop-request-meta",
        quality="host_reported",
        correlation_id=f"{thread}:{turn}",
        requested_model=model,
        requested_reasoning_effort=effort,
        model_event_evidence="unavailable",
    )
    telemetry = attached.get("telemetry")
    if telemetry is None:
        telemetry = observation_receipt_fields(
            repo_path,
            observation_id=started["observation_id"],
            run_id=run_id,
        )["host_observation"]
    writes_performed = bool(
        started["writes_performed"] or attached["writes_performed"]
    )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-desktop",
        "status": (
            "started"
            if started["status"] == "started"
            else "already_started"
        ),
        "repo_root": started["repo_root"],
        "run_id": run_id,
        "observation_id": started["observation_id"],
        "observation_path": started["observation_path"],
        "telemetry_scope": "desktop_request_only",
        "telemetry": telemetry,
        "writes_performed": writes_performed,
    }


def observation_receipt_fields(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    if (
        not isinstance(observation_id, str)
        or len(observation_id) != 32
        or any(character not in "0123456789abcdef" for character in observation_id)
    ):
        raise MaestroError(
            "RUN_OBSERVATION_ID_INVALID",
            "observation-id must be the 32-character ID returned by observe start.",
        )
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    base_fields = {
        "schema_version",
        "observation_id",
        "project_id",
        "checkout_id",
        "run_id",
        "task_label",
        "started_at",
        "plan_summary",
    }
    optional_fields = {"host_observation", "completed_at", "duration_ms"}
    started_at = _parse_timestamp(value.get("started_at"))
    completed_at = _parse_timestamp(value.get("completed_at"))
    project = read_json(safe_target(repo, ".maestro/project.json"))
    if (
        not base_fields.issubset(value)
        or set(value) - (base_fields | optional_fields)
        or (("completed_at" in value) != ("duration_ms" in value))
        or value.get("schema_version") != OBSERVATION_VERSION
        or value.get("observation_id") != observation_id
        or value.get("project_id") != project.get("project_id")
        or value.get("checkout_id") != checkout_id(repo)
        or value.get("run_id") != run_id
        or started_at is None
        or not _valid_host_observation(value.get("host_observation"))
        or (
            "completed_at" in value
            and (
                completed_at is None
                or not isinstance(value.get("duration_ms"), (int, float))
                or isinstance(value.get("duration_ms"), bool)
                or value["duration_ms"] < 0
            )
        )
    ):
        raise MaestroError(
            "RUN_OBSERVATION_INVALID",
            "The in-flight observation does not match this project and run.",
        )
    label = _task_label(value.get("task_label"))
    elapsed = (
        value["duration_ms"]
        if "duration_ms" in value
        else (_utc_now() - started_at).total_seconds() * 1000
    )
    if elapsed < 0:
        raise MaestroError(
            "RUN_OBSERVATION_CLOCK_INVALID",
            "The observation start time is in the future.",
        )
    result = {
        "observation_id": observation_id,
        "task_label": label,
        "duration_ms": round(elapsed, 3),
        "plan_summary": value.get("plan_summary"),
    }
    if value.get("host_observation") is not None:
        result["host_observation"] = value["host_observation"]
    return result


def record_host_observation(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    source: str,
    quality: str,
    correlation_id: str,
    requested_model: str | None = None,
    requested_reasoning_effort: str | None = None,
    applied_model: str | None = None,
    model_event_evidence: str = "unavailable",
    reroutes: list[dict[str, str]] | None = None,
    actual_model: str | None = None,
    tokens: dict[str, int | None] | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    if (
        not isinstance(observation_id, str)
        or len(observation_id) != 32
        or any(
            character not in "0123456789abcdef"
            for character in observation_id
        )
    ):
        raise MaestroError(
            "RUN_OBSERVATION_ID_INVALID",
            "observation-id must be the 32-character ID returned by observe start.",
        )
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    observation_receipt_fields(
        repo,
        observation_id=observation_id,
        run_id=run_id,
    )
    value = _read_observation_file(target)
    if value.get("run_id") != run_id or "completed_at" in value:
        raise MaestroError(
            "HOST_OBSERVATION_CONFLICT",
            "Host telemetry must match an unfinished in-flight observation.",
        )
    if actual_model is not None:
        if applied_model is not None and applied_model != actual_model:
            raise MaestroError(
                "HOST_OBSERVATION_INVALID",
                "actual-model and applied-model cannot disagree.",
            )
        applied_model = actual_model
    host_observation = {
        "schema_version": HOST_OBSERVATION_VERSION,
        "source": _bounded_line(source, field="source", maximum=80),
        "quality": quality,
        "correlation_id": _bounded_line(
            correlation_id,
            field="correlation-id",
            maximum=160,
        ),
        "requested_model": (
            _bounded_line(
                requested_model,
                field="requested-model",
                maximum=128,
            )
            if requested_model is not None
            else None
        ),
        "requested_reasoning_effort": (
            _bounded_line(
                requested_reasoning_effort,
                field="requested-reasoning-effort",
                maximum=40,
            )
            if requested_reasoning_effort is not None
            else None
        ),
        "reasoning_effort_evidence": (
            "host_request"
            if requested_reasoning_effort is not None
            else "unavailable"
        ),
        "applied_model": (
            _bounded_line(
                applied_model,
                field="applied-model",
                maximum=128,
            )
            if applied_model is not None
            else None
        ),
        "model_event_evidence": model_event_evidence,
        "reroutes": list(reroutes or []),
        "tokens": tokens,
        "observed_at": _timestamp(_utc_now()),
    }
    if not _valid_host_observation(host_observation):
        raise MaestroError(
            "HOST_OBSERVATION_INVALID",
            "Applied model telemetry requires a complete Host model event "
            "stream. Requested-only or token-only telemetry remains unmeasured.",
        )
    existing = value.get("host_observation")
    if existing is not None:
        comparable = {
            key: item
            for key, item in existing.items()
            if key != "observed_at"
        }
        expected = {
            key: item
            for key, item in host_observation.items()
            if key != "observed_at"
        }
        if comparable != expected:
            same_identity = (
                existing.get("schema_version") == HOST_OBSERVATION_VERSION
                and existing.get("source") == host_observation["source"]
                and existing.get("quality") == host_observation["quality"]
                and existing.get("correlation_id")
                == host_observation["correlation_id"]
            )
            monotonic_enrichment = (
                same_identity
                and existing.get("requested_model")
                in {None, host_observation["requested_model"]}
                and existing.get("requested_reasoning_effort")
                in {
                    None,
                    host_observation["requested_reasoning_effort"],
                }
                and existing.get(
                    "reasoning_effort_evidence",
                    "unavailable",
                )
                in {
                    "unavailable",
                    host_observation["reasoning_effort_evidence"],
                }
                and existing.get("applied_model")
                in {None, host_observation["applied_model"]}
                and existing.get("model_event_evidence")
                in {"unavailable", host_observation["model_event_evidence"]}
                and (
                    existing.get("reroutes") == []
                    or existing.get("reroutes")
                    == host_observation["reroutes"]
                )
                and (
                    existing.get("tokens") is None
                    or existing.get("tokens") == host_observation["tokens"]
                )
            )
            if not monotonic_enrichment:
                raise MaestroError(
                    "HOST_OBSERVATION_CONFLICT",
                    "This run already has different Host telemetry.",
                )
            value["host_observation"] = host_observation
            atomic_write(target, pretty_json(value).encode("utf-8"))
            return {
                "schema_version": "maestro_command_result_v1",
                "command": "observe-host",
                "status": "enriched",
                "repo_root": str(repo),
                "run_id": run_id,
                "observation_id": observation_id,
                "telemetry": host_observation,
                "writes_performed": True,
            }
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "observe-host",
            "status": "already_recorded",
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation_id,
            "writes_performed": False,
        }
    value["host_observation"] = host_observation
    atomic_write(target, pretty_json(value).encode("utf-8"))
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "observe-host",
        "status": "recorded",
        "repo_root": str(repo),
        "run_id": run_id,
        "observation_id": observation_id,
        "telemetry": host_observation,
        "writes_performed": True,
    }


def _rpc_id(value: Any) -> tuple[str, str] | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return type(value).__name__, str(value)


def _app_server_trace_messages(trace_path: str | Path) -> list[dict[str, Any]]:
    path = Path(trace_path).expanduser().resolve()
    try:
        valid = (
            not path.is_symlink()
            and path.is_file()
            and path.stat().st_size <= MAX_APP_SERVER_TRACE_BYTES
        )
    except OSError:
        valid = False
    if not valid:
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INVALID",
            "App Server trace is missing, unsafe, or exceeds the 4 MB limit.",
        )
    messages: list[dict[str, Any]] = []
    try:
        lines = path.open(encoding="utf-8", errors="strict")
    except OSError as exc:
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INVALID",
            f"Cannot read App Server trace: {exc}",
        ) from exc
    with lines:
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            if len(messages) >= MAX_APP_SERVER_TRACE_MESSAGES:
                raise MaestroError(
                    "CODEX_APP_SERVER_TRACE_INVALID",
                    "App Server trace exceeds the 20,000-message limit.",
                )
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MaestroError(
                    "CODEX_APP_SERVER_TRACE_INVALID",
                    f"Invalid JSON-RPC message at line {line_number}.",
                ) from exc
            if not isinstance(message, dict):
                raise MaestroError(
                    "CODEX_APP_SERVER_TRACE_INVALID",
                    f"Trace line {line_number} must be one JSON-RPC object.",
                )
            messages.append(message)
    if not messages:
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INVALID",
            "App Server trace contains no JSON-RPC messages.",
        )
    return messages


def _token_summary_from_app_server(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    fields = {
        "inputTokens": "input",
        "outputTokens": "output",
        "cachedInputTokens": "cached",
        "reasoningOutputTokens": "reasoning",
        "totalTokens": "total",
    }
    if any(
        not isinstance(value.get(source), int)
        or isinstance(value.get(source), bool)
        or value[source] < 0
        for source in fields
    ):
        return None
    return {
        target: value[source]
        for source, target in fields.items()
    }


def import_codex_app_server_trace(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    trace_path: str | Path,
    turn_id: str | None = None,
) -> dict[str, Any]:
    """Import one fully captured public Codex App Server turn event stream."""

    messages = _app_server_trace_messages(trace_path)
    requests: dict[tuple[str, str], dict[str, Any]] = {}
    responses: dict[tuple[str, str], dict[str, Any]] = {}
    notifications: list[dict[str, Any]] = []
    for message in messages:
        identifier = _rpc_id(message.get("id"))
        method = message.get("method")
        if identifier is not None and isinstance(method, str):
            requests[identifier] = message
        elif identifier is not None and (
            "result" in message or "error" in message
        ):
            responses[identifier] = message
        elif isinstance(method, str) and isinstance(message.get("params"), dict):
            notifications.append(message)

    thread_models: dict[str, str] = {}
    thread_reasoning_efforts: dict[str, str] = {}
    turn_requests: list[dict[str, Any]] = []
    for identifier, request in requests.items():
        response = responses.get(identifier)
        if not isinstance(response, dict) or not isinstance(
            response.get("result"),
            dict,
        ):
            continue
        params = request.get("params")
        result = response["result"]
        if not isinstance(params, dict):
            continue
        if request.get("method") == "thread/start":
            thread = result.get("thread")
            model = (
                params.get("model")
                if isinstance(params.get("model"), str)
                and params["model"].strip()
                else result.get("model")
            )
            if (
                isinstance(thread, dict)
                and isinstance(thread.get("id"), str)
                and isinstance(model, str)
                and model.strip()
            ):
                thread_models[thread["id"]] = model.strip()
            reasoning_effort = result.get("reasoningEffort")
            if (
                isinstance(thread, dict)
                and isinstance(thread.get("id"), str)
                and isinstance(reasoning_effort, str)
                and reasoning_effort.strip()
            ):
                thread_reasoning_efforts[thread["id"]] = (
                    reasoning_effort.strip()
                )
        elif request.get("method") == "turn/start":
            turn = result.get("turn")
            thread = params.get("threadId")
            if (
                isinstance(turn, dict)
                and isinstance(turn.get("id"), str)
                and isinstance(thread, str)
            ):
                turn_requests.append(
                    {
                        "turn_id": turn["id"],
                        "thread_id": thread,
                        "requested_model": (
                            params["model"].strip()
                            if isinstance(params.get("model"), str)
                            and params["model"].strip()
                            else thread_models.get(thread)
                        ),
                        "requested_reasoning_effort": (
                            params["effort"].strip()
                            if isinstance(params.get("effort"), str)
                            and params["effort"].strip()
                            else thread_reasoning_efforts.get(thread)
                        ),
                    }
                )
    if turn_id is not None:
        turn_requests = [
            item for item in turn_requests
            if item["turn_id"] == turn_id
        ]
    if len(turn_requests) != 1:
        raise MaestroError(
            "CODEX_APP_SERVER_TURN_AMBIGUOUS",
            "Trace must contain exactly one matching turn/start response; pass --turn-id when needed.",
        )
    selected = turn_requests[0]
    selected_turn = selected["turn_id"]
    selected_thread = selected["thread_id"]
    completion: dict[str, Any] | None = None
    reroutes: list[dict[str, str]] = []
    tokens: dict[str, int] | None = None
    for message in notifications:
        params = message["params"]
        if params.get("threadId") != selected_thread:
            continue
        method = message["method"]
        if method == "turn/completed":
            turn = params.get("turn")
            if isinstance(turn, dict) and turn.get("id") == selected_turn:
                completion = turn
            continue
        if params.get("turnId") != selected_turn:
            continue
        if method == "model/rerouted":
            reroutes.append(
                {
                    "from_model": params.get("fromModel"),
                    "to_model": params.get("toModel"),
                    "reason": params.get("reason"),
                }
            )
        elif method == "thread/tokenUsage/updated":
            usage = params.get("tokenUsage")
            if isinstance(usage, dict):
                observed = _token_summary_from_app_server(usage.get("last"))
                if observed is not None:
                    tokens = observed
    if completion is None or completion.get("status") not in {
        "completed",
        "interrupted",
        "failed",
    }:
        raise MaestroError(
            "CODEX_APP_SERVER_TRACE_INCOMPLETE",
            "A complete turn/completed notification is required before telemetry is trusted.",
        )
    requested_model = selected["requested_model"]
    applied_model = (
        reroutes[-1]["to_model"]
        if reroutes
        else requested_model
    )
    evidence = (
        "complete"
        if requested_model is not None and applied_model is not None
        else "unavailable"
    )
    recorded = record_host_observation(
        repo_path,
        observation_id=observation_id,
        run_id=run_id,
        source="codex-app-server",
        quality="host_reported",
        correlation_id=f"{selected_thread}:{selected_turn}",
        requested_model=requested_model,
        requested_reasoning_effort=selected[
            "requested_reasoning_effort"
        ],
        applied_model=applied_model if evidence == "complete" else None,
        model_event_evidence=evidence,
        reroutes=reroutes if evidence == "complete" else [],
        tokens=tokens,
    )
    return {
        **recorded,
        "command": "observe-import-codex",
        "turn_status": completion["status"],
        "turn_duration_ms": completion.get("durationMs"),
        "trace_sha256": sha256_text(canonical_json(messages)),
    }


def complete_run_observation(
    repo_path: str | Path,
    *,
    observation_id: str,
    run_id: str,
    duration_ms: float,
) -> None:
    repo = ensure_repo(repo_path)
    target = safe_target(
        repo,
        f".maestro/state/inflight/{observation_id}.json",
    )
    value = _read_observation_file(target)
    if value.get("run_id") != run_id:
        raise MaestroError(
            "RUN_OBSERVATION_INVALID",
            "The in-flight observation does not match this run.",
        )
    if "completed_at" in value:
        if value.get("duration_ms") != duration_ms:
            raise MaestroError(
                "RUN_OBSERVATION_CONFLICT",
                "The observation already has a different frozen duration.",
            )
        return
    value["completed_at"] = _timestamp(_utc_now())
    value["duration_ms"] = duration_ms
    atomic_write(target, pretty_json(value).encode("utf-8"))


def inflight_observations(
    repo_path: str | Path,
    *,
    completed_run_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    repo = ensure_repo(repo_path)
    root = safe_target(repo, ".maestro/state/inflight")
    if not root.exists():
        return []
    if not root.is_dir() or root.is_symlink():
        raise MaestroError(
            "RUN_OBSERVATION_STATE_INVALID",
            "The in-flight observation path must be a safe directory.",
        )
    completed = completed_run_ids or set()
    current_project = read_json(
        safe_target(repo, ".maestro/project.json")
    ).get("project_id")
    current_checkout = checkout_id(repo)
    now = _utc_now()
    results: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), reverse=True)[:MAX_INFLIGHT_OBSERVATIONS]:
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            continue
        try:
            value = _read_observation_file(path)
        except MaestroError:
            continue
        started_at = _parse_timestamp(value.get("started_at"))
        run_id = value.get("run_id")
        if (
            value.get("schema_version") != OBSERVATION_VERSION
            or value.get("project_id") != current_project
            or value.get("checkout_id") != current_checkout
            or not isinstance(run_id, str)
            or run_id in completed
            or started_at is None
            or not isinstance(value.get("task_label"), str)
            or not value["task_label"].strip()
            or len(value["task_label"]) > MAX_TASK_LABEL_LENGTH
            or any(
                character in value["task_label"]
                for character in "\r\n\x00"
            )
            or not _valid_plan_summary_for_observation(value.get("plan_summary"))
        ):
            continue
        elapsed = max(0.0, (now - started_at).total_seconds() * 1000)
        completed_at = _parse_timestamp(value.get("completed_at"))
        host_observation = value.get("host_observation")
        host_state = "host_not_connected"
        requested_model = None
        requested_reasoning_effort = None
        if isinstance(host_observation, dict):
            host_state = (
                "host_event_stream_complete"
                if host_observation.get("model_event_evidence")
                == "complete"
                else "host_request_observed"
            )
            requested_model = host_observation.get("requested_model")
            requested_reasoning_effort = host_observation.get(
                "requested_reasoning_effort",
            )
        results.append(
            {
                "observation_id": value.get("observation_id"),
                "run_id": run_id,
                "task_label": value.get("task_label"),
                "started_at": value["started_at"],
                "elapsed_ms": round(elapsed, 3),
                "status": (
                    "record_pending"
                    if completed_at is not None
                    else (
                        "stale"
                        if elapsed > 24 * 60 * 60 * 1000
                        else "in_progress"
                    )
                ),
                "plan_summary": value.get("plan_summary"),
                "host_state": host_state,
                "requested_model": requested_model,
                "requested_reasoning_effort": (
                    requested_reasoning_effort
                ),
            }
        )
    return sorted(
        results,
        key=lambda item: item["started_at"],
        reverse=True,
    )


def _valid_plan_summary_for_observation(value: Any) -> bool:
    if value is None:
        return True
    return (
        isinstance(value, dict)
        and value.get("schema_version") == "maestro_plan_summary_v1"
        and isinstance(value.get("plan_id"), str)
        and isinstance(value.get("assignments"), list)
        and len(value["assignments"]) <= MAX_PLAN_ASSIGNMENTS
    )
