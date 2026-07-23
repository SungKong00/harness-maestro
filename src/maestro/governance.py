from __future__ import annotations

import heapq
import json
import math
import os
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .errors import MaestroError
from .project import checkout_id
from .registry import definition_digest_maps, registry_digest
from .util import (
    canonical_json,
    ensure_repo,
    read_json,
    safe_target,
    sha256_text,
)

MAX_GOVERN_WINDOW = 1_000
MAX_FINGERPRINTS_PER_RUN = 1_000
MAX_EVENT_FILES = 100
MAX_EVENT_DIRECTORY_ENTRIES = 10_000
MAX_EVENT_FILE_BYTES = 2_000_000
MAX_EVENT_TOTAL_BYTES = 64_000_000
MAX_EVENT_RECORDS = 200_000
MAX_EVENT_LINE_BYTES = 1_000_000
RUN_RECEIPT_ALLOWED_FIELDS = {
    "run_id",
    "risk",
    "route_depth",
    "selected_lenses",
    "executor_runs",
    "primary_executor_id",
    "executor_ids",
    "outcome",
    "evidence_refs",
    "duration_ms",
    "tokens",
    "experiment_id",
    "experiment_arm",
    "correction_count",
    "correction_summary",
    "agent_calls",
    "human_fix_required",
    "decision_changed",
    "verifier_result",
    "command_artifact_ref",
    "project_convention_action",
    "project_convention_path",
}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _existing_run_receipt(
    repo: Path,
    events_directory: Path,
    *,
    project_id: str,
    checkout: str,
    run_id: str,
) -> tuple[str, str] | None:
    if not events_directory.exists():
        return None
    paths, overflow, directory_truncated = _event_paths(events_directory)
    if overflow or directory_truncated:
        raise MaestroError(
            "EVENT_STATE_TRUNCATED",
            "Cannot prove RunReceipt idempotency because the event directory exceeds scan limits.",
        )
    total_bytes = 0
    for path, safe in paths:
        if not safe:
            raise MaestroError(
                "EVENT_STATE_INVALID",
                f"Unsafe event file blocks RunReceipt idempotency: {path.name}",
            )
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise MaestroError(
                "EVENT_STATE_UNREADABLE",
                f"Cannot inspect event file: {path.name}",
            ) from exc
        total_bytes += size
        if size > MAX_EVENT_FILE_BYTES or total_bytes > MAX_EVENT_TOTAL_BYTES:
            raise MaestroError(
                "EVENT_STATE_TRUNCATED",
                "Cannot prove RunReceipt idempotency because event files exceed scan limits.",
            )
        try:
            lines = path.open(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise MaestroError(
                "EVENT_STATE_UNREADABLE",
                f"Cannot read event file: {path.name}",
            ) from exc
        with lines:
            for line in lines:
                if not line.strip():
                    continue
                if len(line.encode("utf-8")) > MAX_EVENT_LINE_BYTES:
                    raise MaestroError(
                        "EVENT_STATE_TRUNCATED",
                        f"Event line exceeds the scan limit: {path.name}",
                    )
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(event, dict)
                    and event.get("kind") == "run_summary"
                    and event.get("project_id") == project_id
                    and event.get("checkout_id") == checkout
                    and event.get("run_id") == run_id
                    and isinstance(event.get("event_id"), str)
                ):
                    return (
                        event["event_id"],
                        path.relative_to(repo).as_posix(),
                    )
    return None


def record_run(
    repo_path: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    project_path = safe_target(repo, ".maestro/project.json")
    lock_path = safe_target(repo, ".maestro/lock.json")
    if not project_path.is_file() or not lock_path.is_file():
        raise MaestroError(
            "PROJECT_UNINITIALIZED",
            "RunReceipt recording requires initialized project and lock state.",
        )
    project = read_json(project_path)
    lock = read_json(lock_path)
    if lock.get("framework", {}).get("version") != __version__:
        raise MaestroError(
            "PROJECT_STATE_STALE",
            "Review and apply a fresh upgrade plan before recording.",
        )
    if lock.get("registry", {}).get("sha256") != registry_digest():
        raise MaestroError(
            "PROJECT_STATE_STALE",
            "Registry lock differs from the installed registry.",
        )
    receipt = read_json(Path(receipt_path))
    unexpected = sorted(set(receipt) - RUN_RECEIPT_ALLOWED_FIELDS)
    if unexpected:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            f"RunReceipt has unsupported fields: {unexpected}",
        )
    required = {
        "run_id",
        "risk",
        "route_depth",
        "selected_lenses",
        "executor_runs",
        "primary_executor_id",
        "executor_ids",
        "outcome",
        "evidence_refs",
        "duration_ms",
        "tokens",
        "correction_count",
        "agent_calls",
        "verifier_result",
        "command_artifact_ref",
    }
    missing = sorted(required - set(receipt))
    if missing:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            f"RunReceipt is missing fields: {missing}",
        )
    definitions = definition_digest_maps()
    selected_lenses = receipt.get("selected_lenses")
    executor_ids = receipt.get("executor_ids")
    if not isinstance(selected_lenses, list) or not isinstance(executor_ids, list):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "selected_lenses and executor_ids must be lists.",
        )
    unknown_lenses = sorted(set(selected_lenses) - set(definitions["lenses"]))
    unknown_executors = sorted(set(executor_ids) - set(definitions["executors"]))
    if unknown_lenses or unknown_executors:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            f"Unknown lenses={unknown_lenses} executors={unknown_executors}",
        )
    convention_action = receipt.get("project_convention_action", "none")
    convention_path = receipt.get("project_convention_path")
    if convention_action in {"created", "updated"} and isinstance(
        convention_path,
        str,
    ):
        convention_target = safe_target(repo, convention_path)
        if convention_target.is_symlink() or not convention_target.is_file():
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                f"Recorded project convention is missing or unsafe: {convention_path}",
            )
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    fingerprint = sha256_text(
        canonical_json(
            {
                "outcome": receipt.get("outcome"),
                "verifier_result": receipt.get("verifier_result"),
                "selected_lenses": selected_lenses,
            }
        )
    )[:24]
    current_checkout_id = checkout_id(repo)
    event_id = sha256_text(
        canonical_json(
            {
                "checkout_id": current_checkout_id,
                "run_id": receipt.get("run_id"),
                "kind": "run_summary",
            }
        )
    )[:32]
    event = {
        "schema_version": "maestro_event_v1",
        "event_id": event_id,
        "timestamp": timestamp,
        "project_id": project.get("project_id"),
        "checkout_id": current_checkout_id,
        "run_id": receipt.get("run_id"),
        "framework_version": __version__,
        "registry_digest": registry_digest(),
        "lens_definition_digests": {
            lens_id: definitions["lenses"][lens_id]
            for lens_id in selected_lenses
        },
        "executor_definition_digests": {
            executor_id: definitions["executors"][executor_id]
            for executor_id in executor_ids
        },
        "risk": receipt.get("risk"),
        "route_depth": receipt.get("route_depth"),
        "selected_lenses": selected_lenses,
        "executor_runs": receipt.get("executor_runs"),
        "primary_executor_id": receipt.get("primary_executor_id"),
        "executor_ids": executor_ids,
        "kind": "run_summary",
        "outcome": receipt.get("outcome"),
        "fingerprint": fingerprint,
        "evidence_refs": receipt.get("evidence_refs"),
        "duration_ms": receipt.get("duration_ms"),
        "tokens": receipt.get("tokens"),
        "correction_count": receipt.get("correction_count"),
        "correction_summary": receipt.get("correction_summary", []),
        "agent_calls": receipt.get("agent_calls"),
        "human_fix_required": receipt.get("human_fix_required"),
        "finding_severity": None,
        "decision_changed": receipt.get("decision_changed", False),
        "verifier_result": receipt.get("verifier_result"),
        "command_artifact_ref": receipt.get("command_artifact_ref"),
        "project_convention_action": receipt.get(
            "project_convention_action",
            "none",
        ),
        "project_convention_path": receipt.get("project_convention_path"),
    }
    if receipt.get("experiment_id") is not None:
        event["experiment_id"] = receipt["experiment_id"]
    if receipt.get("experiment_arm") is not None:
        event["experiment_arm"] = receipt["experiment_arm"]
    if not _valid_event(event):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "RunReceipt does not satisfy the compact event contract.",
        )

    state_root = project.get("state_root")
    if state_root != ".maestro/state":
        raise MaestroError(
            "PROJECT_STATE_INVALID",
            "state_root must equal '.maestro/state'.",
        )
    events_directory = safe_target(repo, f"{state_root}/events")
    existing = _existing_run_receipt(
        repo,
        events_directory,
        project_id=event["project_id"],
        checkout=current_checkout_id,
        run_id=event["run_id"],
    )
    if existing is not None:
        existing_event_id, existing_path = existing
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "record",
            "status": "already_recorded",
            "repo_root": str(repo),
            "run_id": event["run_id"],
            "event_id": existing_event_id,
            "event_path": existing_path,
            "writes_performed": False,
        }
    date = timestamp[:10]
    relative_path = f"{state_root}/events/{date}.jsonl"
    event_path = safe_target(repo, relative_path)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path = safe_target(repo, relative_path)
    payload = (canonical_json(event) + "\n").encode("utf-8")
    if len(payload) > MAX_EVENT_LINE_BYTES:
        raise MaestroError(
            "RUN_RECEIPT_TOO_LARGE",
            f"RunReceipt exceeds {MAX_EVENT_LINE_BYTES} bytes.",
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(event_path, flags, 0o600)
        with os.fdopen(descriptor, "ab", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise MaestroError(
            "EVENT_WRITE_FAILED",
            f"Could not append RunReceipt: {exc}",
        ) from exc
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "record",
        "status": "recorded",
        "repo_root": str(repo),
        "run_id": event["run_id"],
        "event_id": event_id,
        "event_path": relative_path,
        "writes_performed": True,
    }


def _valid_event(event: dict[str, Any]) -> bool:
    allowed_fields = {
        "schema_version",
        "event_id",
        "timestamp",
        "project_id",
        "checkout_id",
        "run_id",
        "framework_version",
        "registry_digest",
        "lens_definition_digests",
        "executor_definition_digests",
        "risk",
        "route_depth",
        "selected_lenses",
        "executor_runs",
        "primary_executor_id",
        "executor_ids",
        "kind",
        "outcome",
        "fingerprint",
        "evidence_refs",
        "duration_ms",
        "tokens",
        "experiment_id",
        "experiment_arm",
        "correction_count",
        "correction_summary",
        "agent_calls",
        "human_fix_required",
        "finding_severity",
        "decision_changed",
        "verifier_result",
        "command_artifact_ref",
        "project_convention_action",
        "project_convention_path",
    }
    if set(event) - allowed_fields:
        return False
    required_fields = {
        "schema_version",
        "event_id",
        "timestamp",
        "project_id",
        "checkout_id",
        "run_id",
        "framework_version",
        "registry_digest",
        "lens_definition_digests",
        "executor_definition_digests",
        "risk",
        "route_depth",
        "selected_lenses",
        "executor_runs",
        "primary_executor_id",
        "executor_ids",
        "kind",
        "outcome",
        "fingerprint",
        "evidence_refs",
        "duration_ms",
        "tokens",
        "correction_count",
        "agent_calls",
        "human_fix_required",
        "finding_severity",
        "decision_changed",
        "verifier_result",
        "command_artifact_ref",
    }
    if required_fields - set(event):
        return False
    required_strings = (
        "event_id",
        "timestamp",
        "project_id",
        "checkout_id",
        "run_id",
        "framework_version",
        "primary_executor_id",
        "kind",
        "outcome",
        "fingerprint",
    )
    if event.get("schema_version") != "maestro_event_v1":
        return False
    if any(not isinstance(event.get(field), str) or not event[field] for field in required_strings):
        return False
    if _parse_timestamp(event.get("timestamp")) is None:
        return False
    registry_digest = event.get("registry_digest")
    if (
        not isinstance(registry_digest, str)
        or len(registry_digest) != 64
        or any(character not in "0123456789abcdef" for character in registry_digest)
    ):
        return False
    for field in ("lens_definition_digests", "executor_definition_digests"):
        digests = event.get(field)
        if not isinstance(digests, dict) or not all(
            isinstance(key, str)
            and isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
            for key, value in digests.items()
        ):
            return False
    if event.get("risk") not in {"low", "medium", "high", "critical"}:
        return False
    if event.get("route_depth") not in {"fast", "standard", "deep"}:
        return False
    selected_lenses = event.get("selected_lenses")
    if (
        not isinstance(selected_lenses, list)
        or len(selected_lenses) > 3
        or not all(
            isinstance(item, str) and bool(item.strip())
            for item in selected_lenses
        )
        or len(set(selected_lenses)) != len(selected_lenses)
    ):
        return False
    executor_runs = event.get("executor_runs")
    if (
        not isinstance(executor_runs, int)
        or isinstance(executor_runs, bool)
        or executor_runs < 0
    ):
        return False
    executor_ids = event.get("executor_ids")
    if (
        not isinstance(executor_ids, list)
        or not executor_ids
        or len(executor_ids) > 4
        or not all(
            isinstance(item, str) and bool(item.strip())
            for item in executor_ids
        )
        or len(set(executor_ids)) != len(executor_ids)
        or event["primary_executor_id"] not in executor_ids
        or executor_runs < len(executor_ids)
    ):
        return False
    evidence_refs = event.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not all(
        isinstance(item, str) and bool(item.strip())
        for item in evidence_refs
    ):
        return False
    duration = event.get("duration_ms")
    if duration is not None and (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not math.isfinite(duration)
        or duration < 0
    ):
        return False
    tokens = event.get("tokens")
    if tokens is not None:
        if not isinstance(tokens, dict):
            return False
        if set(tokens) - {
            "input",
            "output",
            "cached",
            "reasoning",
            "total",
            "parent_context_total",
            "total_system",
        }:
            return False
        if "total" not in tokens:
            return False
        for token_value in tokens.values():
            if token_value is not None and (
                not isinstance(token_value, int)
                or isinstance(token_value, bool)
                or token_value < 0
            ):
                return False
    correction_count = event.get("correction_count", 0)
    if (
        not isinstance(correction_count, int)
        or isinstance(correction_count, bool)
        or correction_count < 0
    ):
        return False
    correction_summary = event.get("correction_summary", [])
    if not isinstance(correction_summary, list) or len(correction_summary) > 5 or not all(
        isinstance(item, str) and bool(item.strip())
        for item in correction_summary
    ):
        return False
    agent_calls = event.get("agent_calls")
    if agent_calls is not None and (
        not isinstance(agent_calls, int)
        or isinstance(agent_calls, bool)
        or agent_calls < 0
    ):
        return False
    for field in ("experiment_id", "experiment_arm"):
        if event.get(field) is not None and not isinstance(event.get(field), str):
            return False
    if event.get("human_fix_required") is not None and not isinstance(
        event.get("human_fix_required"), bool
    ):
        return False
    if event.get("finding_severity") not in {
        None,
        "medium",
        "high",
        "critical",
    }:
        return False
    if not isinstance(event.get("decision_changed"), bool):
        return False
    if event.get("verifier_result") not in {
        "passed",
        "failed",
        "not_run",
    }:
        return False
    command_artifact_ref = event.get("command_artifact_ref")
    if command_artifact_ref is not None and (
        not isinstance(command_artifact_ref, str)
        or not command_artifact_ref.strip()
    ):
        return False
    convention_action = event.get("project_convention_action", "none")
    if convention_action not in {
        "none",
        "created",
        "updated",
        "candidate",
        "needs_decision",
    }:
        return False
    project_convention_path = event.get("project_convention_path")
    if project_convention_path is not None and (
        not isinstance(project_convention_path, str)
        or not project_convention_path.startswith("docs/conventions/")
        or not project_convention_path.endswith(".md")
        or ".." in Path(project_convention_path).parts
    ):
        return False
    if (
        convention_action in {"created", "updated"}
        and project_convention_path is None
    ):
        return False
    if (
        convention_action in {
            "none",
            "candidate",
            "needs_decision",
        }
        and project_convention_path is not None
    ):
        return False
    if event["kind"] not in {
        "review_finding",
        "verification_failure",
        "correction",
        "run_summary",
    }:
        return False
    if event["outcome"] not in {
        "completed",
        "failed",
        "corrected",
        "blocked",
        "no_change",
    }:
        return False
    if (
        event["verifier_result"] != "not_run"
        and "verifier" not in executor_ids
    ):
        return False
    if event["kind"] == "review_finding" and (
        not selected_lenses or event["finding_severity"] is None
    ):
        return False
    if event["kind"] == "verification_failure" and (
        event["verifier_result"] != "failed"
        or "verifier" not in executor_ids
        or not isinstance(command_artifact_ref, str)
    ):
        return False
    if event["kind"] == "correction" and correction_count < 1:
        return False
    return True


def _has_candidate_evidence(event: dict[str, Any]) -> bool:
    return (
        event["finding_severity"] in {"medium", "high", "critical"}
        and bool(event["evidence_refs"])
        and isinstance(event["command_artifact_ref"], str)
        and bool(event["command_artifact_ref"].strip())
        and event["kind"] in {
            "review_finding",
            "verification_failure",
            "correction",
        }
        and event["outcome"] in {"failed", "corrected", "blocked"}
        and (
            event["verifier_result"] == "failed"
            or event["decision_changed"]
            or event["human_fix_required"] is True
        )
    )


def _definition_digests_match(
    event: dict[str, Any],
    expected: dict[str, dict[str, str]],
) -> bool:
    selected_lenses = event["selected_lenses"]
    lens_definitions = event["lens_definition_digests"]
    if set(lens_definitions) != set(selected_lenses):
        return False
    if any(
        expected["lenses"].get(lens_id) != digest
        for lens_id, digest in lens_definitions.items()
    ):
        return False
    executor_definitions = event["executor_definition_digests"]
    if set(executor_definitions) != set(event["executor_ids"]):
        return False
    return all(
        expected["executors"].get(executor_id) == digest
        for executor_id, digest in executor_definitions.items()
    )


def _event_paths(
    events_directory: Path,
) -> tuple[list[tuple[Path, bool]], int, bool]:
    try:
        entries = os.scandir(events_directory)
    except OSError as exc:
        raise MaestroError(
            "EVENT_STATE_UNREADABLE",
            f"Cannot scan governance event directory: {exc}",
        ) from exc
    retained: list[tuple[str, Path, bool]] = []
    matched = 0
    scanned = 0
    directory_truncated = False
    with entries:
        for entry in entries:
            scanned += 1
            if scanned > MAX_EVENT_DIRECTORY_ENTRIES:
                directory_truncated = True
                break
            if not entry.name.endswith(".jsonl"):
                continue
            matched += 1
            try:
                safe = not entry.is_symlink() and entry.is_file(follow_symlinks=False)
            except OSError:
                safe = False
            item = (entry.name, Path(entry.path), safe)
            if len(retained) < MAX_EVENT_FILES:
                heapq.heappush(retained, item)
            elif entry.name > retained[0][0]:
                heapq.heapreplace(retained, item)
    selected = [
        (path, safe)
        for _, path, safe in sorted(retained, reverse=True)
    ]
    return (
        selected,
        max(0, matched - len(selected)),
        directory_truncated,
    )


def _classify_event(
    event: Any,
    *,
    project_id: str,
    checkout_id: str,
    framework_version: str,
    current_registry_digest: str,
    expected_definition_digests: dict[str, dict[str, str]],
) -> tuple[str, datetime | None]:
    if not isinstance(event, dict):
        return "invalid", None
    if event.get("project_id") != project_id:
        return "foreign", None
    if event.get("checkout_id") != checkout_id:
        return "foreign", None
    if not _valid_event(event):
        return "invalid", None
    if (
        event["framework_version"] != framework_version
        or event["registry_digest"] != current_registry_digest
    ):
        return "version", None
    if not _definition_digests_match(event, expected_definition_digests):
        return "definition", None
    return "eligible", _parse_timestamp(event["timestamp"])


def govern_report(
    repo_path: str | Path,
    *,
    window: int = 20,
    threshold: int = 3,
) -> dict[str, Any]:
    if (
        not isinstance(window, int)
        or isinstance(window, bool)
        or window < 1
        or window > MAX_GOVERN_WINDOW
    ):
        raise MaestroError(
            "WINDOW_INVALID",
            f"Governance window must be an integer from 1 to {MAX_GOVERN_WINDOW}",
        )
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 2:
        raise MaestroError(
            "THRESHOLD_INVALID",
            "Governance candidate threshold must be an integer of at least 2",
        )
    if threshold > window:
        raise MaestroError(
            "THRESHOLD_INVALID",
            "Governance candidate threshold cannot exceed the run window",
        )
    repo = ensure_repo(repo_path)
    try:
        project_path = safe_target(repo, ".maestro/project.json")
        lock_path = safe_target(repo, ".maestro/lock.json")
    except MaestroError as exc:
        raise MaestroError(
            "PROJECT_STATE_UNSAFE",
            f"Governance state must stay inside the repository: {exc.message}",
        ) from exc
    if not project_path.is_file():
        return {
            "schema_version": "maestro_govern_report_v1",
            "repo_root": str(repo),
            "evidence_status": "uninitialized",
            "observations": [],
            "candidates_for_review": [],
            "writes_performed": False,
        }

    project = read_json(project_path)
    if not lock_path.is_file():
        raise MaestroError("PROJECT_STATE_INVALID", "lock.json is required for governance scope")
    lock = read_json(lock_path)
    current_framework_version = lock.get("framework", {}).get("version")
    current_registry_digest = lock.get("registry", {}).get("sha256")
    if not isinstance(current_framework_version, str) or not isinstance(
        current_registry_digest, str
    ):
        raise MaestroError("PROJECT_STATE_INVALID", "lock.json is incomplete")
    if current_framework_version != __version__:
        raise MaestroError(
            "PROJECT_STATE_STALE",
            "The locked framework differs from the installed framework; review a fresh init plan",
        )
    if current_registry_digest != registry_digest():
        raise MaestroError(
            "PROJECT_STATE_STALE",
            "The locked registry differs from the installed registry; review a fresh init plan",
        )
    expected_checkout_id = checkout_id(repo)
    project_id = project.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise MaestroError("PROJECT_STATE_INVALID", "project_id must be a non-empty string")
    state_root_value = project.get("state_root", ".maestro/state")
    if state_root_value != ".maestro/state":
        raise MaestroError(
            "PROJECT_STATE_INVALID",
            "state_root must equal '.maestro/state' in project schema v1",
        )
    safe_target(repo, state_root_value)
    events_relative = (Path(state_root_value) / "events").as_posix()
    events_directory = safe_target(repo, events_relative)
    if events_directory.exists() and not events_directory.is_dir():
        raise MaestroError(
            "EVENT_STATE_INVALID",
            "The governance events path must be a directory",
        )
    expected_definitions = definition_digest_maps()
    invalid_records = 0
    excluded_version_records = 0
    excluded_definition_records = 0
    duplicate_event_records = 0
    truncated_records = 0
    skipped_event_files = 0
    scan_truncated = False
    directory_scan_truncated = False
    selected_run_records: list[dict[str, Any]] = []
    selected_event_paths: list[Path] = []
    if not events_directory.exists():
        event_files_available = False
    else:
        event_files_available = True
        (
            discovered_paths,
            overflow_files,
            directory_scan_truncated,
        ) = _event_paths(events_directory)
        if directory_scan_truncated:
            scan_truncated = True
        if overflow_files:
            scan_truncated = True
            skipped_event_files += overflow_files
        total_event_bytes = 0
        for path, safe in discovered_paths:
            if not safe:
                invalid_records += 1
                continue
            try:
                size = path.stat().st_size
            except OSError:
                invalid_records += 1
                continue
            if (
                size > MAX_EVENT_FILE_BYTES
                or total_event_bytes + size > MAX_EVENT_TOTAL_BYTES
            ):
                scan_truncated = True
                skipped_event_files += 1
                continue
            selected_event_paths.append(path)
            total_event_bytes += size
        with tempfile.TemporaryDirectory(prefix="maestro-govern-") as temporary:
            database_path = Path(temporary) / "runs.sqlite3"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    "CREATE TABLE runs ("
                    "run_id TEXT PRIMARY KEY, "
                    "timestamp REAL NOT NULL, "
                    "latest_event TEXT NOT NULL)"
                )
                records_scanned = 0
                first_pass_stopped = False
                for path in selected_event_paths:
                    try:
                        lines = path.open(encoding="utf-8", errors="replace")
                    except OSError:
                        invalid_records += 1
                        continue
                    with lines:
                        for line in lines:
                            if not line.strip():
                                continue
                            records_scanned += 1
                            if records_scanned > MAX_EVENT_RECORDS:
                                scan_truncated = True
                                truncated_records += 1
                                first_pass_stopped = True
                                break
                            if len(line.encode("utf-8")) > MAX_EVENT_LINE_BYTES:
                                invalid_records += 1
                                truncated_records += 1
                                scan_truncated = True
                                continue
                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                invalid_records += 1
                                continue
                            status, timestamp = _classify_event(
                                event,
                                project_id=project_id,
                                checkout_id=expected_checkout_id,
                                framework_version=current_framework_version,
                                current_registry_digest=current_registry_digest,
                                expected_definition_digests=expected_definitions,
                            )
                            if status == "foreign":
                                continue
                            if status == "invalid":
                                invalid_records += 1
                                continue
                            if status == "version":
                                excluded_version_records += 1
                                continue
                            if status == "definition":
                                excluded_definition_records += 1
                                continue
                            if timestamp is None:
                                invalid_records += 1
                                continue
                            connection.execute(
                                "INSERT INTO runs(run_id, timestamp, latest_event) "
                                "VALUES (?, ?, ?) "
                                "ON CONFLICT(run_id) DO UPDATE SET "
                                "timestamp=excluded.timestamp, "
                                "latest_event=excluded.latest_event "
                                "WHERE excluded.timestamp >= runs.timestamp",
                                (
                                    event["run_id"],
                                    timestamp.timestamp(),
                                    json.dumps(event, ensure_ascii=False, sort_keys=True),
                                ),
                            )
                    if first_pass_stopped:
                        break
                connection.commit()
                selected_rows = connection.execute(
                    "SELECT run_id, timestamp, latest_event FROM runs "
                    "ORDER BY timestamp DESC, run_id DESC LIMIT ?",
                    (window,),
                ).fetchall()
                selected_run_records = [
                    {
                        "run_id": run_id,
                        "timestamp": timestamp,
                        "latest": json.loads(latest_event),
                        "events": {},
                        "duplicate_fingerprints": 0,
                    }
                    for run_id, timestamp, latest_event in selected_rows
                ]
                records_by_run = {
                    record["run_id"]: record for record in selected_run_records
                }
                selected_run_ids = set(records_by_run)
                connection.execute(
                    "CREATE TABLE event_ids (event_id TEXT PRIMARY KEY)"
                )
                records_scanned = 0
                second_pass_stopped = False
                for path in selected_event_paths:
                    try:
                        lines = path.open(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    with lines:
                        for line in lines:
                            if not line.strip():
                                continue
                            records_scanned += 1
                            if records_scanned > MAX_EVENT_RECORDS:
                                second_pass_stopped = True
                                break
                            if len(line.encode("utf-8")) > MAX_EVENT_LINE_BYTES:
                                continue
                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if (
                                not isinstance(event, dict)
                                or event.get("run_id") not in selected_run_ids
                            ):
                                continue
                            status, timestamp = _classify_event(
                                event,
                                project_id=project_id,
                                checkout_id=expected_checkout_id,
                                framework_version=current_framework_version,
                                current_registry_digest=current_registry_digest,
                                expected_definition_digests=expected_definitions,
                            )
                            if status != "eligible" or timestamp is None:
                                continue
                            inserted = connection.execute(
                                "INSERT OR IGNORE INTO event_ids(event_id) VALUES (?)",
                                (event["event_id"],),
                            ).rowcount
                            if inserted == 0:
                                duplicate_event_records += 1
                                continue
                            record = records_by_run[event["run_id"]]
                            fingerprint = event["fingerprint"]
                            existing = record["events"].get(fingerprint)
                            if existing is not None:
                                record["duplicate_fingerprints"] += 1
                                existing_timestamp = _parse_timestamp(existing["timestamp"])
                                if (
                                    existing_timestamp is not None
                                    and timestamp >= existing_timestamp
                                ):
                                    record["events"][fingerprint] = event
                            elif len(record["events"]) < MAX_FINGERPRINTS_PER_RUN:
                                record["events"][fingerprint] = event
                            else:
                                truncated_records += 1
                                scan_truncated = True
                    if second_pass_stopped:
                        break
            finally:
                connection.close()

    considered = [
        event
        for record in selected_run_records
        for event in record["events"].values()
    ]

    fingerprint_runs: dict[str, set[str]] = {}
    duplicate_fingerprint_records = sum(
        record["duplicate_fingerprints"]
        for record in selected_run_records
    )
    for event in considered:
        fingerprint_runs.setdefault(event["fingerprint"], set()).add(event["run_id"])
    fingerprints = {
        fingerprint: len(run_ids)
        for fingerprint, run_ids in fingerprint_runs.items()
    }
    eligible_fingerprint_runs: dict[str, set[str]] = {}
    for event in considered:
        if _has_candidate_evidence(event):
            eligible_fingerprint_runs.setdefault(
                event["fingerprint"],
                set(),
            ).add(event["run_id"])
    candidates = [
        {
            "fingerprint": fingerprint,
            "occurrences": len(run_ids),
            "status": "candidate_for_review",
            "automatic_change_allowed": False,
        }
        for fingerprint, run_ids in sorted(eligible_fingerprint_runs.items())
        if len(run_ids) >= threshold
    ]
    unique_runs = [
        record["latest"]
        for record in selected_run_records
    ]
    actual_tokens = [
        event["tokens"]["total"]
        for event in unique_runs
        if isinstance(event.get("tokens"), dict)
        and isinstance(event["tokens"].get("total"), int)
        and not isinstance(event["tokens"].get("total"), bool)
    ]
    measured_durations = [
        event["duration_ms"]
        for event in unique_runs
        if isinstance(event.get("duration_ms"), (int, float))
        and not isinstance(event.get("duration_ms"), bool)
    ]
    experiment_arms = Counter(
        event["experiment_arm"]
        for event in unique_runs
        if isinstance(event.get("experiment_arm"), str)
    )
    project_convention_actions = Counter(
        event.get("project_convention_action", "none")
        for event in unique_runs
    )
    return {
        "schema_version": "maestro_govern_report_v1",
        "repo_root": str(repo),
        "project_id": project.get("project_id"),
        "checkout_id": expected_checkout_id,
        "window": window,
        "events_considered": len(considered),
        "runs_considered": len(unique_runs),
        "duplicate_fingerprint_records": duplicate_fingerprint_records,
        "duplicate_event_records": duplicate_event_records,
        "invalid_records": invalid_records,
        "excluded_version_records": excluded_version_records,
        "excluded_definition_records": excluded_definition_records,
        "truncated_records": truncated_records,
        "skipped_event_files": skipped_event_files,
        "scan_truncated": scan_truncated,
        "directory_scan_truncated": directory_scan_truncated,
        "event_files_available": event_files_available,
        "evidence_status": (
            "truncated"
            if scan_truncated
            else ("sufficient" if len(unique_runs) >= threshold else "insufficient")
        ),
        "observations": [
            {"fingerprint": key, "occurrences": value}
            for key, value in sorted(fingerprints.items())
        ],
        "candidates_for_review": candidates,
        "candidate_evidence_rule": {
            "minimum_distinct_runs": threshold,
            "requires_finding_severity": True,
            "requires_evidence_ref": True,
            "requires_command_artifact": True,
            "requires_decision_change_or_failed_verifier_or_human_fix": True,
        },
        "token_summary": {
            "measured_events": len(actual_tokens),
            "total": sum(actual_tokens) if actual_tokens else None,
            "estimated": False,
        },
        "duration_summary": {
            "measured_events": len(measured_durations),
            "total_ms": sum(measured_durations) if measured_durations else None,
            "estimated": False,
        },
        "correction_summary": {
            "total": sum(event.get("correction_count", 0) for event in unique_runs),
            "events_with_corrections": sum(
                event.get("correction_count", 0) > 0 for event in unique_runs
            ),
        },
        "experiment_arms": dict(sorted(experiment_arms.items())),
        "project_convention_actions": dict(
            sorted(project_convention_actions.items())
        ),
        "writes_performed": False,
        "promotion_supported": False,
        "scan_limits": {
            "max_window": MAX_GOVERN_WINDOW,
            "max_fingerprints_per_run": MAX_FINGERPRINTS_PER_RUN,
            "max_event_files": MAX_EVENT_FILES,
            "max_event_directory_entries": MAX_EVENT_DIRECTORY_ENTRIES,
            "max_event_file_bytes": MAX_EVENT_FILE_BYTES,
            "max_event_total_bytes": MAX_EVENT_TOTAL_BYTES,
            "max_event_records": MAX_EVENT_RECORDS,
            "max_event_line_bytes": MAX_EVENT_LINE_BYTES,
        },
    }
