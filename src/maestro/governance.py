from __future__ import annotations

import heapq
import json
import math
import os
import re
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .errors import MaestroError
from .expertise import expertise_definition_map, load_expertise_catalog
from .observations import (
    _valid_host_observation,
    complete_run_observation,
    observation_receipt_fields,
)
from .project import checkout_id
from .registry import definition_digest_maps, registry_digest
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
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
    "kind",
    "fingerprint",
    "finding_severity",
    "risk",
    "route_depth",
    "selected_lenses",
    "selected_expertise_packs",
    "selected_decision_guides",
    "expertise_research_mode",
    "expertise_research_gate",
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
    "project_convention_basis",
    "project_convention_path",
    "project_convention_evidence",
    "task_label",
    "plan_summary",
    "stage_results",
    "expertise_observations",
    "host_observation",
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


def _active_convention_evidence_required(framework_version: Any) -> bool:
    if not isinstance(framework_version, str):
        return False
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", framework_version)
    if match is None:
        return False
    return tuple(int(part) for part in match.groups()) >= (0, 2, 2)


def _existing_run_receipt(
    repo: Path,
    events_directory: Path,
    *,
    project_id: str,
    checkout: str,
    run_id: str,
) -> tuple[dict[str, Any], str] | None:
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
                    and event.get("project_id") == project_id
                    and event.get("checkout_id") == checkout
                    and event.get("run_id") == run_id
                    and isinstance(event.get("event_id"), str)
                ):
                    return (
                        event,
                        path.relative_to(repo).as_posix(),
                    )
    return None


def _idempotency_digest(event: dict[str, Any]) -> str:
    return sha256_text(
        canonical_json(
            {
                key: value
                for key, value in event.items()
                if key != "timestamp"
            }
        )
    )


def _run_semantic_error(value: dict[str, Any]) -> str | None:
    risk = value.get("risk")
    route_depth = value.get("route_depth")
    expected_depth = {
        "low": "fast",
        "medium": "standard",
        "high": "deep",
        "critical": "deep",
    }.get(risk)
    if expected_depth is not None and route_depth != expected_depth:
        return (
            f"risk={risk!r} requires route_depth={expected_depth!r}; "
            f"received {route_depth!r}."
        )

    selected_lenses = value.get("selected_lenses")
    maximum_lenses = {
        "fast": 1,
        "standard": 2,
        "deep": 3,
    }.get(route_depth)
    if (
        isinstance(selected_lenses, list)
        and maximum_lenses is not None
        and len(selected_lenses) > maximum_lenses
    ):
        return (
            f"route_depth={route_depth!r} permits at most "
            f"{maximum_lenses} selected_lenses."
        )

    executor_ids = value.get("executor_ids")
    executor_runs = value.get("executor_runs")
    primary_executor_id = value.get("primary_executor_id")
    if (
        not isinstance(executor_runs, int)
        or isinstance(executor_runs, bool)
        or executor_runs < 1
    ):
        return "executor_runs must be an integer of at least 1."
    if isinstance(executor_ids, list):
        if primary_executor_id not in executor_ids:
            return "primary_executor_id must be present in executor_ids."
        if executor_runs < len(executor_ids):
            return "executor_runs cannot be smaller than the number of executor_ids."

    verifier_result = value.get("verifier_result")
    if (
        verifier_result in {"passed", "failed"}
        and isinstance(executor_ids, list)
        and "verifier" not in executor_ids
    ):
        return (
            f"verifier_result={verifier_result!r} requires 'verifier' "
            "in executor_ids."
        )

    high_risk_implementation_completion = (
        risk in {"high", "critical"}
        and primary_executor_id == "implementation-engineer"
        and value.get("outcome") in {"completed", "corrected"}
    )
    if high_risk_implementation_completion:
        if verifier_result != "passed":
            return (
                "High/critical implementation completion requires "
                "verifier_result='passed'."
            )
        command_artifact_ref = value.get("command_artifact_ref")
        if (
            not isinstance(command_artifact_ref, str)
            or not command_artifact_ref.strip()
        ):
            return (
                "High/critical implementation completion requires a non-empty "
                "command_artifact_ref."
            )
    return None


def _valid_task_label(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= 160
        and not any(character in value for character in "\r\n\x00")
    )


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


def _valid_plan_summary(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "plan_id",
        "intent",
        "department",
        "assignments",
        "research",
    }:
        return False
    if (
        value.get("schema_version") != "maestro_plan_summary_v1"
        or not isinstance(value.get("plan_id"), str)
        or len(value["plan_id"]) != 64
        or any(character not in "0123456789abcdef" for character in value["plan_id"])
        or not isinstance(value.get("intent"), str)
        or not value["intent"]
        or not isinstance(value.get("department"), str)
        or not value["department"]
    ):
        return False
    assignments = value.get("assignments")
    if not isinstance(assignments, list) or len(assignments) > 5:
        return False
    assignment_ids: set[str] = set()
    for assignment in assignments:
        if not isinstance(assignment, dict) or set(assignment) != {
            "assignment_id",
            "kind",
            "executor_id",
            "depends_on",
            "planned_model",
            "reasoning_effort",
            "expertise_pack_ids",
            "decision_guide_ids",
        }:
            return False
        assignment_id = assignment.get("assignment_id")
        if (
            not isinstance(assignment_id, str)
            or not assignment_id
            or assignment_id in assignment_ids
            or not isinstance(assignment.get("kind"), str)
            or not assignment["kind"]
            or not isinstance(assignment.get("executor_id"), str)
            or not assignment["executor_id"]
            or not isinstance(assignment.get("planned_model"), str)
            or not assignment["planned_model"]
            or len(assignment["planned_model"]) > 128
            or assignment.get("reasoning_effort")
            not in {"low", "medium", "high", "xhigh", "max", "ultra"}
        ):
            return False
        assignment_ids.add(assignment_id)
        for field, maximum in (
            ("depends_on", 5),
            ("expertise_pack_ids", 1),
            ("decision_guide_ids", 4),
        ):
            items = assignment.get(field)
            if (
                not isinstance(items, list)
                or len(items) > maximum
                or len(set(items)) != len(items)
                or not all(isinstance(item, str) and item for item in items)
            ):
                return False
    if any(
        dependency not in assignment_ids
        for assignment in assignments
        for dependency in assignment["depends_on"]
    ):
        return False
    research = value.get("research")
    return (
        isinstance(research, dict)
        and set(research) == {"mode", "gate"}
        and research.get("mode")
        in {"reuse", "contextualize", "refresh", "discover"}
        and research.get("gate")
        in {"not-required", "satisfied", "in-plan", "open"}
    )


def _valid_stage_results(value: Any, plan_summary: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, list) or len(value) > 5:
        return False
    plan_ids = (
        {
            assignment["assignment_id"]
            for assignment in plan_summary["assignments"]
        }
        if isinstance(plan_summary, dict)
        and _valid_plan_summary(plan_summary)
        else set()
    )
    seen: set[str] = set()
    for result in value:
        if not isinstance(result, dict) or set(result) != {
            "assignment_id",
            "status",
            "actual_model",
            "duration_ms",
            "tokens",
            "evidence_refs",
        }:
            return False
        assignment_id = result.get("assignment_id")
        actual_model = result.get("actual_model")
        duration = result.get("duration_ms")
        evidence_refs = result.get("evidence_refs")
        if (
            not isinstance(assignment_id, str)
            or not assignment_id
            or assignment_id in seen
            or (plan_ids and assignment_id not in plan_ids)
            or result.get("status")
            not in {"completed", "failed", "blocked", "skipped"}
            or (
                actual_model is not None
                and (
                    not isinstance(actual_model, str)
                    or not actual_model
                    or len(actual_model) > 128
                    or any(character in actual_model for character in "\r\n\x00")
                )
            )
            or (
                duration is not None
                and (
                    not isinstance(duration, (int, float))
                    or isinstance(duration, bool)
                    or not math.isfinite(duration)
                    or duration < 0
                )
            )
            or not _valid_token_summary(result.get("tokens"))
            or not isinstance(evidence_refs, list)
            or len(evidence_refs) > 3
            or not all(
                isinstance(item, str) and bool(item.strip())
                for item in evidence_refs
            )
        ):
            return False
        seen.add(assignment_id)
    return True


def _valid_expertise_observations(
    value: Any,
    *,
    evidence_refs: list[str],
    catalog: list[dict[str, Any]] | None,
) -> bool:
    if value is None:
        return True
    if not isinstance(value, list) or len(value) > 3:
        return False
    guides = (
        {
            (pack["expertise_pack_id"], guide["guide_id"])
            for pack in catalog
            for guide in pack["guides"]
        }
        if catalog is not None
        else set()
    )
    pack_ids = (
        {pack["expertise_pack_id"] for pack in catalog}
        if catalog is not None
        else set()
    )
    for observation in value:
        if not isinstance(observation, dict) or set(observation) != {
            "kind",
            "domain",
            "pack_id",
            "guide_id",
            "severity",
            "reusable",
            "resolution",
            "evidence_ref",
        }:
            return False
        pack_id = observation.get("pack_id")
        guide_id = observation.get("guide_id")
        evidence_ref = observation.get("evidence_ref")
        if (
            observation.get("kind")
            not in {
                "missing_pack",
                "missing_guide",
                "stale_guide",
                "trigger_miss",
                "unnecessary_research",
            }
            or not isinstance(observation.get("domain"), str)
            or not observation["domain"].strip()
            or len(observation["domain"]) > 80
            or any(
                character in observation["domain"]
                for character in "\r\n\x00"
            )
            or (
                catalog is not None
                and pack_id is not None
                and pack_id not in pack_ids
            )
            or (
                guide_id is not None
                and (
                    not isinstance(pack_id, str)
                    or (
                        catalog is not None
                        and (pack_id, guide_id) not in guides
                    )
                )
            )
            or observation.get("severity")
            not in {"medium", "high", "critical"}
            or not isinstance(observation.get("reusable"), bool)
            or observation.get("resolution")
            not in {
                "reuse",
                "research",
                "manual_correction",
                "unresolved",
            }
            or not isinstance(evidence_ref, str)
            or evidence_ref not in evidence_refs
        ):
            return False
    return True


def record_run(
    repo_path: str | Path,
    receipt_path: str | Path,
    *,
    observation_id: str | None = None,
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
    observed: dict[str, Any] | None = None
    if observation_id is not None:
        observed = observation_receipt_fields(
            repo,
            observation_id=observation_id,
            run_id=receipt.get("run_id"),
        )
        for field in ("task_label", "plan_summary"):
            if field in receipt and receipt[field] != observed[field]:
                raise MaestroError(
                    "RUN_OBSERVATION_CONFLICT",
                    f"RunReceipt {field} differs from the in-flight observation.",
                )
            receipt[field] = observed[field]
        if receipt.get("duration_ms") is None:
            receipt["duration_ms"] = observed["duration_ms"]
        host_observation = observed.get("host_observation")
        if host_observation is not None:
            if (
                receipt.get("host_observation") is not None
                and receipt["host_observation"] != host_observation
            ):
                raise MaestroError(
                    "RUN_OBSERVATION_CONFLICT",
                    "RunReceipt Host telemetry differs from the in-flight observation.",
                )
            receipt["host_observation"] = host_observation
            observed_tokens = host_observation.get("tokens")
            if receipt.get("tokens") is None:
                receipt["tokens"] = observed_tokens
            elif (
                observed_tokens is not None
                and receipt["tokens"] != observed_tokens
            ):
                raise MaestroError(
                    "RUN_OBSERVATION_CONFLICT",
                    "RunReceipt tokens differ from Host-reported telemetry.",
                )
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
    definitions["expertise_packs"] = expertise_definition_map(repo)
    selected_lenses = receipt.get("selected_lenses")
    executor_ids = receipt.get("executor_ids")
    if not isinstance(selected_lenses, list) or not isinstance(executor_ids, list):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "selected_lenses and executor_ids must be lists.",
        )
    semantic_error = _run_semantic_error(receipt)
    if semantic_error is not None:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            f"RunReceipt semantic contract failed: {semantic_error}",
        )
    unknown_lenses = sorted(set(selected_lenses) - set(definitions["lenses"]))
    unknown_executors = sorted(set(executor_ids) - set(definitions["executors"]))
    if unknown_lenses or unknown_executors:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            f"Unknown lenses={unknown_lenses} executors={unknown_executors}",
        )
    selected_expertise_packs = receipt.get("selected_expertise_packs", [])
    selected_decision_guides = receipt.get("selected_decision_guides", [])
    expertise_research_mode = receipt.get("expertise_research_mode", "reuse")
    expertise_research_gate = receipt.get(
        "expertise_research_gate",
        "not-required",
    )
    if (
        not isinstance(selected_expertise_packs, list)
        or len(selected_expertise_packs) > 1
        or len(set(selected_expertise_packs)) != len(selected_expertise_packs)
        or not all(
            isinstance(item, str) and item.strip()
            for item in selected_expertise_packs
        )
        or not isinstance(selected_decision_guides, list)
        or len(selected_decision_guides) > 4
        or len(set(selected_decision_guides)) != len(selected_decision_guides)
        or not all(
            isinstance(item, str) and item.strip()
            for item in selected_decision_guides
        )
    ):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "Expertise Pack and Decision Guide selections exceed their bounds.",
        )
    unknown_packs = sorted(
        set(selected_expertise_packs) - set(definitions["expertise_packs"])
    )
    catalog = load_expertise_catalog(repo)
    guide_ids = {
        guide["guide_id"]
        for pack in catalog
        if pack["expertise_pack_id"] in selected_expertise_packs
        for guide in pack["guides"]
    }
    unknown_guides = sorted(set(selected_decision_guides) - guide_ids)
    if unknown_packs or unknown_guides:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            f"Unknown expertise packs={unknown_packs} guides={unknown_guides}",
        )
    if receipt.get("task_label") is not None and not _valid_task_label(
        receipt.get("task_label")
    ):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "task_label must be a single non-empty line of at most 160 characters.",
        )
    plan_summary = receipt.get("plan_summary")
    if not _valid_plan_summary(plan_summary):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "plan_summary does not satisfy the compact monitored-plan contract.",
        )
    if isinstance(plan_summary, dict):
        planned_executors = {
            assignment["executor_id"]
            for assignment in plan_summary["assignments"]
        }
        if not planned_executors.issubset(set(executor_ids)):
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "plan_summary Executors must be present in executor_ids.",
            )
    if not _valid_stage_results(receipt.get("stage_results"), plan_summary):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "stage_results do not satisfy the bounded Host observation contract.",
        )
    if not _valid_host_observation(receipt.get("host_observation")):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "host_observation does not satisfy the bounded Host telemetry contract.",
        )
    if not _valid_expertise_observations(
        receipt.get("expertise_observations"),
        evidence_refs=receipt.get("evidence_refs", []),
        catalog=catalog,
    ):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "expertise_observations are invalid or lack matching evidence.",
        )
    if expertise_research_mode not in {
        "reuse",
        "contextualize",
        "refresh",
        "discover",
    } or expertise_research_gate not in {
        "not-required",
        "satisfied",
        "in-plan",
        "open",
    }:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "Expertise research mode or gate is invalid.",
        )
    if (
        (expertise_research_mode == "reuse")
        != (expertise_research_gate == "not-required")
        or (
            expertise_research_gate == "open"
            and receipt.get("outcome") not in {"blocked", "no_change"}
        )
    ):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "Expertise research mode, gate, and outcome are inconsistent.",
        )
    event_kind = receipt.get("kind", "run_summary")
    finding_severity = receipt.get("finding_severity")
    explicit_fingerprint = receipt.get("fingerprint")
    if event_kind == "run_summary" and finding_severity is not None:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "run_summary must not declare finding_severity.",
        )
    if event_kind != "run_summary" and (
        not isinstance(explicit_fingerprint, str)
        or not explicit_fingerprint.strip()
        or finding_severity not in {"medium", "high", "critical"}
    ):
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "Finding, failure, and correction receipts require a stable fingerprint and finding_severity.",
        )
    convention_action = receipt.get("project_convention_action", "none")
    convention_basis = receipt.get("project_convention_basis", "none")
    convention_path = receipt.get("project_convention_path")
    convention_evidence = receipt.get("project_convention_evidence")
    if convention_action in {"created", "updated"} and convention_basis not in {
        "owner_decision",
        "held_out_evaluation",
    }:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "An active Convention change requires owner_decision or held_out_evaluation evidence.",
        )
    if convention_action in {"created", "updated"}:
        if not isinstance(convention_path, str):
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "An active Convention change requires a Convention path.",
            )
        convention_target = safe_target(repo, convention_path)
        if convention_target.is_symlink() or not convention_target.is_file():
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                f"Recorded project convention is missing or unsafe: {convention_path}",
            )
        if not isinstance(convention_evidence, dict):
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "An active Convention change requires structured project_convention_evidence.",
            )
        expected_keys = {
            "convention_sha256",
            "kind",
            "artifact",
        }
        if convention_basis == "owner_decision":
            expected_keys.add("decision_summary")
        if set(convention_evidence) != expected_keys:
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "Convention evidence fields do not match the declared basis.",
            )
        if convention_evidence.get("kind") != convention_basis:
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "Convention evidence kind must match project_convention_basis.",
            )
        convention_sha256 = convention_evidence.get("convention_sha256")
        if (
            not isinstance(convention_sha256, str)
            or file_sha256(convention_target) != convention_sha256
        ):
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "Convention evidence digest does not match the active Convention file.",
            )
        if convention_basis == "owner_decision":
            decision_summary = convention_evidence.get("decision_summary")
            if (
                not isinstance(decision_summary, str)
                or not decision_summary.strip()
                or len(decision_summary) > 500
            ):
                raise MaestroError(
                    "RUN_RECEIPT_INVALID",
                    "owner_decision requires a non-empty decision_summary of at most 500 characters.",
                )
        artifact = convention_evidence.get("artifact")
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "Convention evidence requires one content-addressed artifact.",
            )
        artifact_path = artifact.get("path")
        artifact_sha256 = artifact.get("sha256")
        if (
            not isinstance(artifact_path, str)
            or not artifact_path.strip()
            or Path(artifact_path).is_absolute()
            or ".." in Path(artifact_path).parts
            or artifact_path == convention_path
            or artifact_path.startswith(".git/")
            or artifact_path.startswith(".maestro/state/")
            or not isinstance(artifact_sha256, str)
        ):
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "Convention evidence artifact must be a durable repository-local file.",
            )
        artifact_target = safe_target(repo, artifact_path)
        if (
            artifact_target.is_symlink()
            or not artifact_target.is_file()
            or file_sha256(artifact_target) != artifact_sha256
        ):
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "Convention evidence artifact is missing, unsafe, or has a digest mismatch.",
            )
        if receipt.get("command_artifact_ref") != artifact_path:
            raise MaestroError(
                "RUN_RECEIPT_INVALID",
                "command_artifact_ref must name the content-addressed Convention evidence artifact.",
            )
    elif convention_evidence is not None:
        raise MaestroError(
            "RUN_RECEIPT_INVALID",
            "project_convention_evidence is allowed only for an active Convention change.",
        )
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    fingerprint = (
        explicit_fingerprint.strip()
        if isinstance(explicit_fingerprint, str) and explicit_fingerprint.strip()
        else sha256_text(
            canonical_json(
                {
                    "outcome": receipt.get("outcome"),
                    "verifier_result": receipt.get("verifier_result"),
                    "selected_lenses": selected_lenses,
                }
            )
        )[:24]
    )
    current_checkout_id = checkout_id(repo)
    event_id = sha256_text(
        canonical_json(
            {
                "checkout_id": current_checkout_id,
                "run_id": receipt.get("run_id"),
                "kind": event_kind,
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
        "expertise_pack_definition_digests": {
            pack_id: definitions["expertise_packs"][pack_id]
            for pack_id in selected_expertise_packs
        },
        "risk": receipt.get("risk"),
        "route_depth": receipt.get("route_depth"),
        "selected_lenses": selected_lenses,
        "selected_expertise_packs": selected_expertise_packs,
        "selected_decision_guides": selected_decision_guides,
        "expertise_research_mode": expertise_research_mode,
        "expertise_research_gate": expertise_research_gate,
        "executor_runs": receipt.get("executor_runs"),
        "primary_executor_id": receipt.get("primary_executor_id"),
        "executor_ids": executor_ids,
        "kind": event_kind,
        "outcome": receipt.get("outcome"),
        "fingerprint": fingerprint,
        "evidence_refs": receipt.get("evidence_refs"),
        "duration_ms": receipt.get("duration_ms"),
        "tokens": receipt.get("tokens"),
        "correction_count": receipt.get("correction_count"),
        "correction_summary": receipt.get("correction_summary", []),
        "agent_calls": receipt.get("agent_calls"),
        "human_fix_required": receipt.get("human_fix_required"),
        "finding_severity": finding_severity,
        "decision_changed": receipt.get("decision_changed", False),
        "verifier_result": receipt.get("verifier_result"),
        "command_artifact_ref": receipt.get("command_artifact_ref"),
        "project_convention_action": receipt.get(
            "project_convention_action",
            "none",
        ),
        "project_convention_basis": convention_basis,
        "project_convention_path": receipt.get("project_convention_path"),
    }
    for field in (
        "task_label",
        "plan_summary",
        "stage_results",
        "expertise_observations",
        "host_observation",
    ):
        if receipt.get(field) is not None:
            event[field] = receipt[field]
    if convention_evidence is not None:
        event["project_convention_evidence"] = convention_evidence
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
    if observed is not None:
        complete_run_observation(
            repo,
            observation_id=observed["observation_id"],
            run_id=event["run_id"],
            duration_ms=event["duration_ms"],
        )
    existing = _existing_run_receipt(
        repo,
        events_directory,
        project_id=event["project_id"],
        checkout=current_checkout_id,
        run_id=event["run_id"],
    )
    if existing is not None:
        existing_event, existing_path = existing
        if _idempotency_digest(existing_event) != _idempotency_digest(event):
            raise MaestroError(
                "RUN_ID_CONFLICT",
                f"Run ID {event['run_id']} is already recorded with different content.",
            )
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "record",
            "status": "already_recorded",
            "repo_root": str(repo),
            "run_id": event["run_id"],
            "event_id": existing_event["event_id"],
            "event_path": existing_path,
            "management_check": _post_record_management_check(repo),
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
        "management_check": _post_record_management_check(repo),
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
        "expertise_pack_definition_digests",
        "risk",
        "route_depth",
        "selected_lenses",
        "selected_expertise_packs",
        "selected_decision_guides",
        "expertise_research_mode",
        "expertise_research_gate",
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
        "project_convention_basis",
        "project_convention_path",
        "project_convention_evidence",
        "task_label",
        "plan_summary",
        "stage_results",
        "expertise_observations",
        "host_observation",
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
    for field in (
        "lens_definition_digests",
        "executor_definition_digests",
        "expertise_pack_definition_digests",
    ):
        digests = event.get(field)
        if digests is None and field == "expertise_pack_definition_digests":
            continue
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
    selected_expertise_packs = event.get("selected_expertise_packs", [])
    selected_decision_guides = event.get("selected_decision_guides", [])
    expertise_research_mode = event.get("expertise_research_mode", "reuse")
    expertise_research_gate = event.get(
        "expertise_research_gate",
        "not-required",
    )
    if (
        not isinstance(selected_expertise_packs, list)
        or len(selected_expertise_packs) > 1
        or len(set(selected_expertise_packs)) != len(selected_expertise_packs)
        or not all(
            isinstance(item, str) and bool(item.strip())
            for item in selected_expertise_packs
        )
        or not isinstance(selected_decision_guides, list)
        or len(selected_decision_guides) > 4
        or len(set(selected_decision_guides)) != len(selected_decision_guides)
        or not all(
            isinstance(item, str) and bool(item.strip())
            for item in selected_decision_guides
        )
        or expertise_research_mode
        not in {"reuse", "contextualize", "refresh", "discover"}
        or expertise_research_gate
        not in {"not-required", "satisfied", "in-plan", "open"}
        or (
            (expertise_research_mode == "reuse")
            != (expertise_research_gate == "not-required")
        )
        or (
            expertise_research_gate == "open"
            and event.get("outcome") not in {"blocked", "no_change"}
        )
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
    if _run_semantic_error(event) is not None:
        return False
    evidence_refs = event.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not all(
        isinstance(item, str) and bool(item.strip())
        for item in evidence_refs
    ):
        return False
    task_label = event.get("task_label")
    if task_label is not None and not _valid_task_label(task_label):
        return False
    plan_summary = event.get("plan_summary")
    if not _valid_plan_summary(plan_summary):
        return False
    if isinstance(plan_summary, dict):
        planned_executors = {
            assignment["executor_id"]
            for assignment in plan_summary["assignments"]
        }
        if not planned_executors.issubset(set(executor_ids)):
            return False
    if not _valid_stage_results(event.get("stage_results"), plan_summary):
        return False
    if not _valid_host_observation(event.get("host_observation")):
        return False
    if not _valid_expertise_observations(
        event.get("expertise_observations"),
        evidence_refs=evidence_refs,
        catalog=None,
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
    if not _valid_token_summary(tokens):
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
    convention_basis = event.get("project_convention_basis", "none")
    if convention_basis not in {
        "none",
        "same_run_candidate",
        "owner_decision",
        "held_out_evaluation",
    }:
        return False
    project_convention_path = event.get("project_convention_path")
    project_convention_evidence = event.get("project_convention_evidence")
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
        convention_action in {"created", "updated"}
        and (
            convention_basis not in {
                "owner_decision",
                "held_out_evaluation",
            }
            or event["verifier_result"] != "passed"
            or not event["evidence_refs"]
            or not isinstance(command_artifact_ref, str)
        )
    ):
        return False
    if (
        convention_action in {
            "none",
            "candidate",
            "needs_decision",
        }
        and (
            project_convention_path is not None
            or project_convention_evidence is not None
        )
    ):
        return False
    if project_convention_evidence is not None:
        if not isinstance(project_convention_evidence, dict):
            return False
        expected_keys = {"convention_sha256", "kind", "artifact"}
        if convention_basis == "owner_decision":
            expected_keys.add("decision_summary")
        if (
            set(project_convention_evidence) != expected_keys
            or project_convention_evidence.get("kind") != convention_basis
        ):
            return False
        digest = project_convention_evidence.get("convention_sha256")
        artifact = project_convention_evidence.get("artifact")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(artifact, dict)
            or set(artifact) != {"path", "sha256"}
            or not isinstance(artifact.get("path"), str)
            or not artifact["path"].strip()
            or Path(artifact["path"]).is_absolute()
            or ".." in Path(artifact["path"]).parts
            or artifact["path"].startswith(".git/")
            or artifact["path"].startswith(".maestro/state/")
            or not isinstance(artifact.get("sha256"), str)
            or len(artifact["sha256"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in artifact["sha256"]
            )
        ):
            return False
        if convention_basis == "owner_decision":
            summary = project_convention_evidence.get("decision_summary")
            if (
                not isinstance(summary, str)
                or not summary.strip()
                or len(summary) > 500
            ):
                return False
        if command_artifact_ref != artifact["path"]:
            return False
    if (
        convention_action in {"created", "updated"}
        and project_convention_evidence is None
        and _active_convention_evidence_required(event.get("framework_version"))
    ):
        return False
    if convention_action == "none" and convention_basis != "none":
        return False
    if (
        convention_action in {"candidate", "needs_decision"}
        and convention_basis != "same_run_candidate"
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
    if not all(
        expected["executors"].get(executor_id) == digest
        for executor_id, digest in executor_definitions.items()
    ):
        return False
    pack_ids = event.get("selected_expertise_packs", [])
    pack_definitions = event.get("expertise_pack_definition_digests", {})
    if set(pack_definitions) != set(pack_ids):
        return False
    return all(
        expected["expertise_packs"].get(pack_id) == digest
        for pack_id, digest in pack_definitions.items()
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
    if not _definition_digests_match(event, expected_definition_digests):
        return "definition", None
    timestamp = _parse_timestamp(event["timestamp"])
    if (
        event["framework_version"] != framework_version
        or event["registry_digest"] != current_registry_digest
    ):
        return "compatible", timestamp
    return "eligible", timestamp


def recent_run_events(
    repo_path: str | Path,
    *,
    window: int = 20,
) -> dict[str, Any]:
    if (
        not isinstance(window, int)
        or isinstance(window, bool)
        or window < 1
        or window > 100
    ):
        raise MaestroError(
            "WINDOW_INVALID",
            "Viewer run window must be an integer from 1 to 100.",
        )
    repo = ensure_repo(repo_path)
    project = read_json(safe_target(repo, ".maestro/project.json"))
    lock = read_json(safe_target(repo, ".maestro/lock.json"))
    project_id = project.get("project_id")
    framework_version = lock.get("framework", {}).get("version")
    current_registry_digest = lock.get("registry", {}).get("sha256")
    if (
        not isinstance(project_id, str)
        or not project_id
        or not isinstance(framework_version, str)
        or not isinstance(current_registry_digest, str)
    ):
        raise MaestroError(
            "PROJECT_STATE_INVALID",
            "Project and lock state are required for run history.",
        )
    events_directory = safe_target(repo, ".maestro/state/events")
    if not events_directory.exists():
        return {
            "schema_version": "maestro_run_history_v1",
            "runs": [],
            "evidence_status": "empty",
            "invalid_records": 0,
            "scan_truncated": False,
            "writes_performed": False,
        }
    if not events_directory.is_dir():
        raise MaestroError(
            "EVENT_STATE_INVALID",
            "The governance events path must be a directory.",
        )
    definitions = definition_digest_maps()
    definitions["expertise_packs"] = expertise_definition_map(repo)
    paths, overflow, directory_truncated = _event_paths(events_directory)
    latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    invalid_records = 0
    scan_truncated = bool(overflow or directory_truncated)
    total_bytes = 0
    records_scanned = 0
    current_checkout = checkout_id(repo)
    for path, safe in paths:
        if not safe:
            invalid_records += 1
            continue
        try:
            size = path.stat().st_size
        except OSError:
            invalid_records += 1
            continue
        if size > MAX_EVENT_FILE_BYTES or total_bytes + size > MAX_EVENT_TOTAL_BYTES:
            scan_truncated = True
            continue
        total_bytes += size
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
                    break
                if len(line.encode("utf-8")) > MAX_EVENT_LINE_BYTES:
                    invalid_records += 1
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
                    checkout_id=current_checkout,
                    framework_version=framework_version,
                    current_registry_digest=current_registry_digest,
                    expected_definition_digests=definitions,
                )
                if status == "foreign":
                    continue
                if status not in {"eligible", "compatible"} or timestamp is None:
                    invalid_records += 1
                    continue
                existing = latest.get(event["run_id"])
                if existing is None or timestamp >= existing[0]:
                    latest[event["run_id"]] = (timestamp, event)
        if records_scanned > MAX_EVENT_RECORDS:
            break
    ordered = [
        event
        for _, event in sorted(
            latest.values(),
            key=lambda item: (item[0], item[1]["run_id"]),
            reverse=True,
        )[:window]
    ]
    return {
        "schema_version": "maestro_run_history_v1",
        "runs": ordered,
        "evidence_status": "truncated" if scan_truncated else "sufficient",
        "invalid_records": invalid_records,
        "scan_truncated": scan_truncated,
        "writes_performed": False,
    }


def expertise_management_signals(
    events: list[dict[str, Any]],
    *,
    threshold: int = 3,
) -> list[dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for event in events:
        for item in event.get("expertise_observations", []):
            if not item.get("reusable"):
                continue
            fingerprint = sha256_text(
                canonical_json(
                    {
                        "kind": item["kind"],
                        "domain": item["domain"].casefold(),
                        "pack_id": item["pack_id"],
                        "guide_id": item["guide_id"],
                    }
                )
            )[:24]
            record = observations.setdefault(
                fingerprint,
                {
                    "fingerprint": fingerprint,
                    "kind": item["kind"],
                    "domain": item["domain"],
                    "pack_id": item["pack_id"],
                    "guide_id": item["guide_id"],
                    "severity": item["severity"],
                    "run_ids": set(),
                    "latest_timestamp": event["timestamp"],
                    "evidence_refs": [],
                },
            )
            record["run_ids"].add(event["run_id"])
            if event["timestamp"] >= record["latest_timestamp"]:
                record["latest_timestamp"] = event["timestamp"]
            severity_order = {"medium": 1, "high": 2, "critical": 3}
            if severity_order[item["severity"]] > severity_order[record["severity"]]:
                record["severity"] = item["severity"]
            if (
                item["evidence_ref"] not in record["evidence_refs"]
                and len(record["evidence_refs"]) < 3
            ):
                record["evidence_refs"].append(item["evidence_ref"])
    signals: list[dict[str, Any]] = []
    for record in observations.values():
        occurrences = len(record.pop("run_ids"))
        if occurrences < threshold and record["severity"] != "critical":
            continue
        signals.append(
            {
                **record,
                "occurrences": occurrences,
                "status": "review_recommended",
                "automatic_change_allowed": False,
            }
        )
    return sorted(
        signals,
        key=lambda item: (
            {"critical": 3, "high": 2, "medium": 1}[item["severity"]],
            item["occurrences"],
            item["latest_timestamp"],
        ),
        reverse=True,
    )


def _post_record_management_check(repo: Path) -> dict[str, Any]:
    try:
        history = recent_run_events(repo, window=20)
        expertise_signals = expertise_management_signals(history["runs"])
        governance = govern_report(repo, window=20, threshold=3)
    except MaestroError as exc:
        return {
            "schema_version": "maestro_management_check_v1",
            "status": "unavailable",
            "review_due": False,
            "expertise_signals": [],
            "governance_candidate_count": 0,
            "automatic_mutation_allowed": False,
            "error": {"code": exc.code, "message": exc.message},
        }
    return {
        "schema_version": "maestro_management_check_v1",
        "status": "available",
        "review_due": bool(
            expertise_signals or governance["candidates_for_review"]
        ),
        "expertise_signals": expertise_signals,
        "governance_candidate_count": len(
            governance["candidates_for_review"]
        ),
        "automatic_mutation_allowed": False,
    }


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
    expected_definitions["expertise_packs"] = expertise_definition_map(repo)
    invalid_records = 0
    excluded_version_records = 0
    excluded_definition_records = 0
    included_compatible_records = 0
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
                            if status == "compatible":
                                included_compatible_records += 1
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
                            if (
                                status not in {"eligible", "compatible"}
                                or timestamp is None
                            ):
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
    eligible_fingerprint_events: dict[str, list[dict[str, Any]]] = {}
    for event in considered:
        if _has_candidate_evidence(event):
            eligible_fingerprint_runs.setdefault(
                event["fingerprint"],
                set(),
            ).add(event["run_id"])
            eligible_fingerprint_events.setdefault(
                event["fingerprint"],
                [],
            ).append(event)

    severity_order = {"medium": 1, "high": 2, "critical": 3}
    candidates: list[dict[str, Any]] = []
    for fingerprint, run_ids in sorted(eligible_fingerprint_runs.items()):
        if len(run_ids) < threshold:
            continue
        events = sorted(
            eligible_fingerprint_events[fingerprint],
            key=lambda item: (
                _parse_timestamp(item["timestamp"])
                or datetime.min.replace(tzinfo=timezone.utc),
                item["run_id"],
            ),
            reverse=True,
        )
        evidence_refs: list[str] = []
        command_artifact_refs: list[str] = []
        for event in events:
            for evidence_ref in event["evidence_refs"]:
                if (
                    evidence_ref not in evidence_refs
                    and len(evidence_refs) < 3
                ):
                    evidence_refs.append(evidence_ref)
            artifact_ref = event.get("command_artifact_ref")
            if (
                isinstance(artifact_ref, str)
                and artifact_ref not in command_artifact_refs
                and len(command_artifact_refs) < 3
            ):
                command_artifact_refs.append(artifact_ref)
        severity = max(
            (
                event["finding_severity"]
                for event in events
                if event["finding_severity"] in severity_order
            ),
            key=lambda item: severity_order[item],
        )
        latest = events[0]
        candidates.append(
            {
                "fingerprint": fingerprint,
                "occurrences": len(run_ids),
                "severity": severity,
                "latest_run_id": latest["run_id"],
                "latest_timestamp": latest["timestamp"],
                "evidence_refs": evidence_refs,
                "command_artifact_refs": command_artifact_refs,
                "status": "candidate_for_review",
                "automatic_change_allowed": False,
                "next_step": (
                    "Classify the gap as a deterministic check, project "
                    "Convention, Expertise Pack, or global Harness candidate."
                ),
            }
        )
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
    measured_agent_calls = [
        event["agent_calls"]
        for event in unique_runs
        if isinstance(event.get("agent_calls"), int)
        and not isinstance(event.get("agent_calls"), bool)
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
    expertise_pack_usage = Counter(
        pack_id
        for event in unique_runs
        for pack_id in event.get("selected_expertise_packs", [])
    )
    expertise_research_modes = Counter(
        event.get("expertise_research_mode", "reuse")
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
        "included_compatible_records": included_compatible_records,
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
        "agent_call_summary": {
            "measured_events": len(measured_agent_calls),
            "total": sum(measured_agent_calls) if measured_agent_calls else None,
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
        "expertise_pack_usage": dict(sorted(expertise_pack_usage.items())),
        "expertise_research_modes": dict(
            sorted(expertise_research_modes.items())
        ),
        "writes_performed": False,
        "promotion_supported": False,
        "governance_review_due": bool(candidates),
        "retention": {
            "format": "daily-jsonl",
            "raw_messages_stored": False,
            "automatic_deletion_supported": False,
            "review_due": skipped_event_files > 0 or directory_scan_truncated,
        },
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
