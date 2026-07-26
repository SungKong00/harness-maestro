from __future__ import annotations

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
HOST_OBSERVATION_VERSION = "maestro_host_observation_v1"
MAX_TASK_LABEL_LENGTH = 160
MAX_PLAN_ASSIGNMENTS = 5
MAX_INFLIGHT_OBSERVATIONS = 100
MAX_OBSERVATION_FILE_BYTES = 128_000


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


def _valid_host_observation(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {
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
        value.get("schema_version") == HOST_OBSERVATION_VERSION
        and isinstance(value.get("source"), str)
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
        and (
            actual_model is None
            or (
                isinstance(actual_model, str)
                and bool(actual_model.strip())
                and len(actual_model) <= 128
                and not any(
                    character in actual_model
                    for character in "\r\n\x00"
                )
            )
        )
        and _valid_token_summary(tokens)
        and (actual_model is not None or tokens is not None)
        and _parse_timestamp(value.get("observed_at")) is not None
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
        comparable = {
            key: item
            for key, item in existing.items()
            if key != "started_at"
        }
        expected = {
            key: item
            for key, item in value.items()
            if key != "started_at"
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
    host_observation = {
        "schema_version": HOST_OBSERVATION_VERSION,
        "source": _bounded_line(source, field="source", maximum=80),
        "quality": quality,
        "correlation_id": _bounded_line(
            correlation_id,
            field="correlation-id",
            maximum=160,
        ),
        "actual_model": (
            _bounded_line(
                actual_model,
                field="actual-model",
                maximum=128,
            )
            if actual_model is not None
            else None
        ),
        "tokens": tokens,
        "observed_at": _timestamp(_utc_now()),
    }
    if not _valid_host_observation(host_observation):
        raise MaestroError(
            "HOST_OBSERVATION_INVALID",
            "Host telemetry requires a supported quality and at least one "
            "host-reported model or token summary with total.",
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
            raise MaestroError(
                "HOST_OBSERVATION_CONFLICT",
                "This run already has different Host telemetry.",
            )
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
