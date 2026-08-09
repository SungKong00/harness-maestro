from __future__ import annotations

import json
import os
import queue
import signal
import shutil
import stat
import subprocess
import threading
import time
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence, TextIO

try:  # POSIX Host lease; other CLI commands remain cross-platform importable.
    import fcntl
except ImportError:  # pragma: no cover - exercised through the typed fallback
    fcntl = None  # type: ignore[assignment]

from . import __version__
from .assignment_contracts import (
    assignment_output_schema,
    project_assignment_input,
    validate_assignment_packet,
)
from .authorization import resolve_authorized_write_roots
from .errors import MaestroError
from .evaluation_attestation import projected_evaluation_evidence_refs
from .execution_contracts import normalize_execution_contract
from .execution_units import (
    build_execution_attempt,
    build_execution_unit_receipt,
)
from .expertise_runtime import load_assignment_expertise
from .observations import (
    MAX_MODEL_REROUTES,
    claim_maestro_owned_codex_execution,
    complete_run_observation,
    observation_receipt_fields,
    record_host_observation,
    record_stage_observation,
    record_work_finish,
    record_work_start,
    start_run_observation,
)
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    read_json,
    safe_target,
    sha256_text,
)
from .work.codex import (
    MAX_COLLAB_WORK,
    CodexCollaborationTracker,
    codex_event_timestamp,
    codex_work_id,
)
from .work.completion import terminal_assignment_work_heads
from .work.assignment import (
    allocation_from_assignment,
    application_from_packet,
    outcome_from_assignment_packet,
)

HOST_RUN_VERSION = "maestro_codex_host_run_v1"
MAX_PROMPT_BYTES = 256_000
MAX_PROTOCOL_LINE_BYTES = 1_000_000
MAX_PROTOCOL_STREAM_BYTES = 64_000_000
MAX_PROTOCOL_STREAM_MESSAGES = 100_000
MAX_PROTOCOL_QUEUE_MESSAGES = 256
HOST_LEASE_SHARDS = 64
MAX_FINAL_MESSAGE_CHARS = 12_000
MAX_TIMEOUT_SECONDS = 7_200.0
DEFAULT_TIMEOUT_SECONDS = 1_800.0
POST_COMPLETION_TOKEN_WAIT_SECONDS = 1.0
PROCESS_EXIT_GRACE_SECONDS = 1.0
TURN_INTERRUPT_GRACE_SECONDS = 5.0
SCOPED_SHUTDOWN_GRACE_SECONDS = 15.0
MAX_BACKGROUND_TERMINALS = 1_000
BACKGROUND_TERMINAL_PAGE_SIZE = 100
MAX_BACKGROUND_TERMINAL_CLEANUP_ROUNDS = 8
_SANDBOXES = {"read-only", "workspace-write"}
_TERMINAL_STATUSES = {"completed", "interrupted", "failed"}
_RELEVANT_NOTIFICATIONS = {
    "error",
    "item/started",
    "item/completed",
    "model/rerouted",
    "thread/tokenUsage/updated",
    "turn/started",
    "turn/completed",
}
_HIGH_VOLUME_NOTIFICATION_OPT_OUTS = [
    "item/agentMessage/delta",
    "item/plan/delta",
    "item/reasoning/summaryTextDelta",
    "item/reasoning/summaryPartAdded",
    "item/reasoning/textDelta",
    "item/commandExecution/outputDelta",
    "item/fileChange/outputDelta",
]


@contextmanager
def _host_assignment_lease(
    repo: Path,
    *,
    run_id: str,
    assignment_id: str | None,
):
    """Hold one crash-recoverable interprocess lease for a Host turn."""

    if fcntl is None:
        raise MaestroError(
            "CODEX_HOST_LEASE_UNAVAILABLE",
            "This platform has no supported crash-recoverable Host lease; use an explicit current-Host fallback.",
        )
    identity = sha256_text(
        canonical_json(
            {
                "run_id": run_id,
                "assignment_id": assignment_id,
            }
        )
    )
    shard = int(identity[:8], 16) % HOST_LEASE_SHARDS
    lease_root = safe_target(repo, ".maestro/state/host-leases")
    try:
        lease_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lease_path = safe_target(
            repo,
            f".maestro/state/host-leases/lease-{shard:02d}.lock",
        )
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lease_path, flags, 0o600)
        lease_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(lease_stat.st_mode)
            or lease_stat.st_nlink != 1
        ):
            os.close(descriptor)
            raise MaestroError(
                "CODEX_HOST_LEASE_INVALID",
                "The bounded Host lease must be one regular non-linked file.",
            )
    except OSError as exc:
        raise MaestroError(
            "CODEX_HOST_LEASE_INVALID",
            "Cannot open the bounded Host Assignment lease.",
        ) from exc
    try:
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise MaestroError(
                "CODEX_HOST_ASSIGNMENT_BUSY",
                "The same Host lease shard already has an in-flight turn; retry after it reaches a terminal result.",
            ) from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _bounded_text_file(path_value: str | Path) -> str:
    candidate = Path(path_value).expanduser()
    try:
        valid = (
            not candidate.is_symlink()
            and candidate.is_file()
            and candidate.stat().st_size <= MAX_PROMPT_BYTES
        )
    except OSError:
        valid = False
    if not valid:
        raise MaestroError(
            "CODEX_HOST_PROMPT_INVALID",
            "prompt-file must be a regular non-symlink UTF-8 file of at most "
            f"{MAX_PROMPT_BYTES} bytes.",
        )
    try:
        value = candidate.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise MaestroError(
            "CODEX_HOST_PROMPT_INVALID",
            "prompt-file must be readable strict UTF-8 text.",
        ) from exc
    if not value.strip():
        raise MaestroError(
            "CODEX_HOST_PROMPT_INVALID",
            "prompt-file must contain a non-empty request.",
        )
    return value


def _assignment_prompt(
    projection: dict[str, Any],
    output_schema: dict[str, Any],
    expertise_context: dict[str, Any] | None = None,
) -> str:
    prompt = (
        "Execute only the following validated Maestro AssignmentInput. "
        "Treat its task, side-effect, context, evidence, and Packet contracts "
        "as closed. Inspect only referenced repository artifacts. Your final "
        "answer is machine-validated: return exactly one JSON object matching "
        "the final-answer JSON Schema below, with no Markdown fence, preface, "
        "or trailing commentary.\n"
        + (
            "The owned Host loaded and digest-verified the exact Expertise "
            "content below. Use it only within the Assignment contract and "
            "report one closed disposition per Guide in the final Packet.\n"
            "Loaded Expertise context:\n"
            f"{canonical_json(expertise_context)}\n"
            if expertise_context is not None
            else ""
        )
        + "Final-answer JSON Schema:\n"
        f"{canonical_json(output_schema)}\n"
        "Validated AssignmentInput:\n"
        f"{canonical_json(projection)}"
    )
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise MaestroError(
            "CODEX_HOST_PROMPT_INVALID",
            "The exact AssignmentInput exceeds the Host prompt limit; narrow "
            "the bounded inputs instead of truncating them.",
        )
    return prompt


def _validated_assignment_result(
    final_message: Any,
    *,
    final_message_is_final: bool,
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any],
    repo: Path,
    research_bundle: dict[str, Any] | None,
    require_expertise_dispositions: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if (
        not final_message_is_final
        or not isinstance(final_message, str)
        or not final_message.strip()
    ):
        raise MaestroError(
            "CODEX_HOST_PACKET_INVALID",
            "A completed Assignment turn must return one final-answer JSON Packet.",
        )
    try:
        packet = json.loads(final_message)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MaestroError(
            "CODEX_HOST_PACKET_INVALID",
            "A completed Assignment turn must return only one valid JSON Packet.",
        ) from exc
    if not isinstance(packet, dict):
        raise MaestroError(
            "CODEX_HOST_PACKET_INVALID",
            "The Assignment result Packet must be a JSON object.",
        )
    validation = validate_assignment_packet(
        packet,
        plan,
        assignment_id,
        projection,
        repo_path=repo,
        research_bundle=research_bundle,
        require_expertise_dispositions=require_expertise_dispositions,
    )
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(
            "CODEX_HOST_PACKET_INVALID",
            f"{first['code']}: {first['message']}",
        )

    if packet["schema_version"] == "maestro_finding_packet_v2":
        stage_status = (
            "blocked"
            if packet["verdict"] in {"BLOCK", "INSUFFICIENT_EVIDENCE"}
            else "completed"
        )
    elif packet["schema_version"] == "maestro_verification_verdict_v1":
        # The verifier turn completed successfully even when it found a
        # target failure. The bounded verdict is preserved separately.
        stage_status = "completed"
    else:
        stage_status = {
            "completed": "completed",
            "failed_transient": "failed",
            "failed_semantic": "failed",
            "blocked": "blocked",
            "cancelled": "interrupted",
            "skipped": "skipped",
        }[packet["status"]]
    return packet, validation, stage_status


def _bounded_option(
    value: str | None,
    *,
    field: str,
    maximum: int,
) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(character in value for character in "\r\n\x00")
    ):
        raise MaestroError(
            "CODEX_HOST_ARGUMENT_INVALID",
            f"{field} must be one non-empty line of at most {maximum} characters.",
        )
    return value.strip()


def _validate_managed_model_reroutes(
    model_contract: dict[str, Any] | None,
    *,
    requested_model: str,
    provider_reported_model: str | None,
    reroutes: Sequence[dict[str, Any]],
) -> str | None:
    """Return the applied model after enforcing a managed route transition."""

    reported_model = _bounded_option(
        provider_reported_model,
        field="provider-reported-model",
        maximum=128,
    )
    if len(reroutes) > MAX_MODEL_REROUTES:
        raise MaestroError(
            "CODEX_HOST_PROTOCOL_LIMIT",
            "The turn emitted more model reroutes than the observation contract allows.",
        )
    expected_model = requested_model
    for reroute in reroutes:
        from_model = _bounded_option(
            reroute.get("from_model"),
            field="reroute-from-model",
            maximum=128,
        )
        to_model = _bounded_option(
            reroute.get("to_model"),
            field="reroute-to-model",
            maximum=128,
        )
        reason = _bounded_option(
            reroute.get("reason"),
            field="reroute-reason",
            maximum=240,
        )
        if (
            from_model is None
            or to_model is None
            or reason is None
            or from_model != expected_model
        ):
            raise MaestroError(
                "CODEX_HOST_MODEL_REROUTE_INVALID",
                "Model reroutes must form one bounded chain from the exact requested model.",
            )
        expected_model = to_model

    if not reroutes:
        if (
            model_contract is not None
            and model_contract.get("enforcement") == "typed-quality-floor"
            and reported_model is not None
            and reported_model != requested_model
        ):
            raise MaestroError(
                "CODEX_HOST_QUALITY_FLOOR_VIOLATION",
                "The provider reported an untyped model transition outside the validated route.",
            )
        return reported_model
    if (
        model_contract is None
        or model_contract.get("enforcement") != "typed-quality-floor"
    ):
        return expected_model
    normalized_reason = str(reroutes[0].get("reason", "")).casefold()
    if normalized_reason in {
        "quality-escalation",
        "quality_escalation",
        "quality-gate-miss",
        "quality_gate_miss",
    }:
        raise MaestroError(
            "CODEX_HOST_MODEL_TRANSITION_KIND_CONFLICT",
            (
                "A runtime availability fallback cannot carry a quality "
                "escalation reason; quality escalation requires a new typed route."
            ),
        )
    fallback = model_contract.get("fallback_route")
    allowed = (
        len(reroutes) == 1
        and isinstance(fallback, dict)
        and fallback.get("trigger") == "selected-model-unavailable"
        and reroutes[0].get("from_model")
        == model_contract.get("selected_model")
        and reroutes[0].get("to_model")
        == fallback.get("selected_model")
    )
    if not allowed:
        raise MaestroError(
            "CODEX_HOST_QUALITY_FLOOR_VIOLATION",
            (
                "The Host rerouted outside the typed fallback route. "
                "Unlisted downgrades and implicit escalation fail closed."
            ),
        )
    acceptable = model_contract["quality_floor"]["acceptable_routes"]
    fallback_pair = {
        "selected_class": fallback["selected_class"],
        "reasoning_effort": fallback["reasoning_effort"],
    }
    if fallback_pair not in acceptable:
        raise MaestroError(
            "CODEX_HOST_QUALITY_FLOOR_VIOLATION",
            "The typed fallback route is below the validated quality floor.",
        )
    return expected_model


def _host_contract(
    repo: Path,
    *,
    plan_path: str | Path | None,
    assignment_id: str | None,
    projection_path: str | Path | None,
    baseline_path: str | Path | None,
    document_paths: Sequence[str],
    dependency_packet_paths: Sequence[str | Path],
    dependency_projection_paths: Sequence[str | Path],
    research_evidence_path: str | Path | None,
    coverage_path: str | Path | None,
    coverage_admission_path: str | Path | None,
    coverage_projection_path: str | Path | None,
    expertise_work_plan_path: str | Path | None,
    expertise_closure_path: str | Path | None,
    expertise_research_evidence_paths: Sequence[str | Path] = (),
    sandbox: str | None,
    model: str | None,
    reasoning_effort: str | None,
    design_decision_path: str | Path | None = None,
) -> dict[str, Any]:
    requested_sandbox = _bounded_option(
        sandbox,
        field="sandbox",
        maximum=40,
    )
    requested_model = _bounded_option(
        model,
        field="model",
        maximum=128,
    )
    requested_effort = _bounded_option(
        reasoning_effort,
        field="reasoning-effort",
        maximum=40,
    )
    if requested_sandbox is not None and requested_sandbox not in _SANDBOXES:
        raise MaestroError(
            "CODEX_HOST_SANDBOX_INVALID",
            "sandbox must be read-only or workspace-write.",
        )
    if assignment_id is not None and plan_path is None:
        raise MaestroError(
            "CODEX_HOST_PLAN_REQUIRED",
            "--assignment requires a validated --plan.",
        )
    if plan_path is not None and assignment_id is None:
        raise MaestroError(
            "CODEX_HOST_ASSIGNMENT_REQUIRED",
            "--plan and --assignment are an inseparable managed-execution pair.",
        )

    assignment: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    projection_plan: dict[str, Any] | None = None
    projection: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    expertise_execution: dict[str, Any] | None = None
    research_bundle: dict[str, Any] | None = None
    dependency_packet_digests: dict[str, str] = {}
    plan_id: str | None = None
    execution_plan_id: str | None = None
    decision_bundle_digest: str | None = None
    model_execution_units: list[dict[str, Any]] = []
    execution_units: list[dict[str, Any]] = []
    if research_evidence_path is not None:
        research_bundle = read_json(
            Path(research_evidence_path).expanduser().resolve()
        )
    expertise_research_bundles = [
        read_json(Path(path).expanduser().resolve())
        for path in expertise_research_evidence_paths
    ]
    if plan_path is not None:
        loaded_plan = read_json(Path(plan_path).expanduser().resolve())
        validation = normalize_execution_contract(
            loaded_plan,
            repo_path=repo,
            research_bundle=research_bundle,
        )
        plan = validation.get("route_plan")
        projection_plan = loaded_plan
        if validation["status"] != "PASS":
            first = validation["issues"][0]
            raise MaestroError(
                "CODEX_HOST_PLAN_INVALID",
                f"{first['code']}: {first['message']}",
            )
        if validation["execution_status"] != "READY":
            raise MaestroError(
                "CODEX_HOST_PLAN_NOT_READY",
                (
                    "The validated plan is not executable yet "
                    f"({validation['execution_status']}); refresh legacy "
                    "routes or bind the required evidence first."
                ),
            )
        if not isinstance(plan, dict):
            raise MaestroError(
                "CODEX_HOST_PLAN_INVALID",
                "The validated execution contract has no route plan.",
            )
        execution_plan_id = validation.get("execution_plan_id")
        decision_bundle_digest = validation.get(
            "decision_bundle_digest"
        )
        model_execution_units = list(
            validation.get("model_execution_units", [])
        )
        execution_units = list(validation.get("execution_units", []))
        plan_id = plan["plan_id"]
        if assignment_id is not None:
            assignment = next(
                (
                    item
                    for item in plan["assignments"]
                    if item["assignment_id"] == assignment_id
                ),
                None,
            )
            if assignment is None:
                raise MaestroError(
                    "CODEX_HOST_ASSIGNMENT_INVALID",
                    "assignment does not exist in the validated plan.",
                )

    if assignment is None:
        if any(
            (
                projection_path is not None,
                baseline_path is not None,
                bool(document_paths),
                bool(dependency_packet_paths),
                bool(dependency_projection_paths),
                research_evidence_path is not None,
                coverage_path is not None,
                coverage_admission_path is not None,
                coverage_projection_path is not None,
                expertise_work_plan_path is not None,
                expertise_closure_path is not None,
                design_decision_path is not None,
                bool(expertise_research_evidence_paths),
            )
        ):
            raise MaestroError(
                "CODEX_HOST_ASSIGNMENT_INPUT_UNEXPECTED",
                "Projection, baseline, dependency, document, and research inputs require --assignment.",
            )
        if requested_sandbox is None:
            raise MaestroError(
                "CODEX_HOST_SANDBOX_REQUIRED",
                "Use --sandbox explicitly when no Assignment contract is supplied.",
            )
        effective_sandbox = requested_sandbox
        effective_model = requested_model
        effective_effort = requested_effort
        model_execution_contract = None
    else:
        if projection_path is None or baseline_path is None:
            raise MaestroError(
                "CODEX_HOST_ASSIGNMENT_INPUT_REQUIRED",
                "An Assignment requires its exact --projection and authoritative --baseline.",
            )
        assert plan is not None
        assert projection_plan is not None
        baseline = read_json(Path(baseline_path).expanduser().resolve())
        dependency_packets = [
            read_json(Path(path).expanduser().resolve())
            for path in dependency_packet_paths
        ]
        dependency_projections = [
            read_json(Path(path).expanduser().resolve())
            for path in dependency_projection_paths
        ]
        reconstructed = project_assignment_input(
            repo,
            projection_plan,
            assignment_id,
            baseline,
            document_paths=document_paths,
            dependency_packets=dependency_packets,
            dependency_projections=dependency_projections,
            research_bundle=research_bundle,
            coverage=(
                read_json(Path(coverage_path).expanduser().resolve())
                if coverage_path is not None
                else None
            ),
            coverage_admission=(
                read_json(
                    Path(coverage_admission_path)
                    .expanduser()
                    .resolve()
                )
                if coverage_admission_path is not None
                else None
            ),
            coverage_projection=(
                read_json(
                    Path(coverage_projection_path)
                    .expanduser()
                    .resolve()
                )
                if coverage_projection_path is not None
                else None
            ),
            expertise_work_plan=(
                read_json(
                    Path(expertise_work_plan_path)
                    .expanduser()
                    .resolve()
                )
                if expertise_work_plan_path is not None
                else None
            ),
            expertise_closure=(
                read_json(
                    Path(expertise_closure_path)
                    .expanduser()
                    .resolve()
                )
                if expertise_closure_path is not None
                else None
            ),
            design_decision_packet=(
                read_json(
                    Path(design_decision_path)
                    .expanduser()
                    .resolve()
                )
                if design_decision_path is not None
                else None
            ),
            expertise_research_bundles=expertise_research_bundles,
        )
        if (
            reconstructed.get("status") != "PASS"
            or reconstructed.get("execution_status") != "READY"
            or not isinstance(reconstructed.get("input"), dict)
        ):
            first = next(
                iter(reconstructed.get("issues", [])),
                {
                    "code": "PROJECTION_INVALID",
                    "message": "Assignment projection is not executable.",
                },
            )
            raise MaestroError(
                "CODEX_HOST_ASSIGNMENT_INPUT_INVALID",
                f"{first['code']}: {first['message']}",
            )
        supplied_projection = read_json(
            Path(projection_path).expanduser().resolve()
        )
        supplied_input = (
            supplied_projection.get("input")
            if isinstance(supplied_projection, dict)
            and isinstance(supplied_projection.get("input"), dict)
            else supplied_projection
        )
        if supplied_input != reconstructed["input"]:
            raise MaestroError(
                "CODEX_HOST_ASSIGNMENT_INPUT_MISMATCH",
                "Projection does not exactly match the AssignmentInput reconstructed from authoritative inputs.",
            )
        projection = reconstructed["input"]
        expertise_execution = load_assignment_expertise(repo, projection)
        output_schema = assignment_output_schema(
            projection,
            require_expertise_dispositions=(
                expertise_execution["attestation_digest"] is not None
            ),
        )
        dependency_packet_digests = {
            packet["assignment_id"]: sha256_text(canonical_json(packet))
            for packet in dependency_packets
        }
        assignment_sandbox = (
            "workspace-write"
            if assignment["mutation_owner"] and not assignment["read_only"]
            else "read-only"
        )
        if (
            requested_sandbox is not None
            and requested_sandbox != assignment_sandbox
        ):
            raise MaestroError(
                "CODEX_HOST_SANDBOX_CONFLICT",
                "sandbox conflicts with the validated Assignment side-effect contract.",
        )
        effective_sandbox = assignment_sandbox
        model_execution_contract = next(
            (
                item
                for item in model_execution_units
                if item.get("assignment_id") == assignment_id
            ),
            None,
        )
        if model_execution_contract is None:
            raise MaestroError(
                "CODEX_HOST_MODEL_ROUTE_UNSUPPORTED",
                (
                    "This Assignment is deterministic or lacks an enforceable "
                    "model execution contract; the owned model Host cannot run it."
                ),
            )
        planned_model = model_execution_contract["selected_model"]
        planned_effort = model_execution_contract["reasoning_effort"]
        if (
            requested_model is not None
            and planned_model is not None
            and requested_model != planned_model
        ):
            raise MaestroError(
                "CODEX_HOST_MODEL_CONFLICT",
                "model conflicts with the validated Assignment model route.",
            )
        if (
            requested_effort is not None
            and planned_effort is not None
            and requested_effort != planned_effort
        ):
            raise MaestroError(
                "CODEX_HOST_REASONING_CONFLICT",
                "reasoning-effort conflicts with the validated Assignment model route.",
            )
        effective_model = requested_model or planned_model
        effective_effort = requested_effort or planned_effort

    sandbox_policy: dict[str, Any]
    scoped_write_roots = False
    if effective_sandbox == "read-only":
        runtime_workspace_roots = [str(repo)]
        sandbox_policy = {
            "type": "readOnly",
            "networkAccess": False,
        }
    else:
        writable_roots = [str(repo)]
        authorization = (
            projection.get("execution_authorization")
            if isinstance(projection, dict)
            else None
        )
        if isinstance(authorization, dict):
            try:
                writable_roots = [
                    str(path)
                    for path in resolve_authorized_write_roots(
                        repo,
                        authorization["allowed_paths"],
                    )
                ]
            except MaestroError as exc:
                raise MaestroError(
                    "CODEX_HOST_AUTHORIZED_ROOT_INVALID",
                    exc.message,
                ) from exc
            scoped_write_roots = True
        runtime_workspace_roots = list(writable_roots)
        sandbox_policy = {
            "type": "workspaceWrite",
            "writableRoots": writable_roots,
            "networkAccess": False,
            "excludeSlashTmp": True,
            "excludeTmpdirEnvVar": True,
        }
    return {
        "assignment_id": assignment_id,
        "plan_id": plan_id,
        "execution_plan_id": execution_plan_id,
        "decision_bundle_digest": decision_bundle_digest,
        "sandbox": effective_sandbox,
        "sandbox_policy": sandbox_policy,
        "runtime_workspace_roots": runtime_workspace_roots,
        "scoped_write_roots": scoped_write_roots,
        "model": effective_model,
        "reasoning_effort": effective_effort,
        "model_execution_contract": model_execution_contract,
        "execution_units": execution_units,
        "execution_unit": (
            model_execution_contract.get("execution_unit")
            if isinstance(model_execution_contract, dict)
            else None
        ),
        "model_route_id": (
            model_execution_contract.get("model_route_id")
            if isinstance(model_execution_contract, dict)
            else None
        ),
        "execution_unit_id": (
            model_execution_contract.get("execution_unit_id")
            if isinstance(model_execution_contract, dict)
            else None
        ),
        "assignment": assignment,
        "plan": plan,
        "projection": projection,
        "output_schema": output_schema,
        "expertise_execution": expertise_execution,
        "research_bundle": research_bundle,
        "dependency_packet_digests": dependency_packet_digests,
    }


def _stdout_reader(
    stream: TextIO,
    output: queue.Queue[tuple[str, Any]],
) -> None:
    try:
        while True:
            line = stream.readline()
            if line == "":
                output.put(("eof", None))
                return
            output.put(("line", line))
    except Exception as exc:  # pragma: no cover - platform pipe failures
        output.put(("reader-error", type(exc).__name__))


def _stderr_reader(stream: TextIO, sink: list[str]) -> None:
    try:
        while stream.read(4_096):
            if len(sink) < 1:
                sink.append("stderr-observed")
    except Exception:  # pragma: no cover - diagnostic drain only
        return


def _process_group_exists(process_group_id: int) -> bool:
    if os.name != "posix":
        return False
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def _wait_for_process_group_exit(
    process_group_id: int,
    *,
    timeout: float,
) -> bool:
    deadline = time.monotonic() + timeout
    while _process_group_exists(process_group_id):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


def _scoped_process_quiescence_supported() -> bool:
    return (
        os.name == "posix"
        and hasattr(os, "killpg")
        and hasattr(os, "getpgid")
    )


class _AppServer:
    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        deadline: float,
    ) -> None:
        try:
            self.process = subprocess.Popen(
                list(command),
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                bufsize=1,
                start_new_session=os.name == "posix",
            )
        except OSError as exc:
            raise MaestroError(
                "CODEX_HOST_START_FAILED",
                "Unable to start codex app-server.",
            ) from exc
        self.process_group_id = (
            self.process.pid
            if os.name == "posix"
            else None
        )
        if (
            self.process.stdin is None
            or self.process.stdout is None
            or self.process.stderr is None
        ):
            self.close()
            raise MaestroError(
                "CODEX_HOST_START_FAILED",
                "codex app-server stdio pipes are unavailable.",
            )
        self.deadline = deadline
        self.messages = 0
        self.bytes = 0
        self.filtered_notifications = 0
        self.pending: dict[tuple[str, str], dict[str, Any]] = {}
        self.notifications: list[dict[str, Any]] = []
        self.output: queue.Queue[tuple[str, Any]] = queue.Queue(
            maxsize=MAX_PROTOCOL_QUEUE_MESSAGES
        )
        self.stderr_seen: list[str] = []
        self.stdout_thread = threading.Thread(
            target=_stdout_reader,
            args=(self.process.stdout, self.output),
            daemon=True,
        )
        self.stderr_thread = threading.Thread(
            target=_stderr_reader,
            args=(self.process.stderr, self.stderr_seen),
            daemon=True,
        )
        self.stdout_thread.start()
        self.stderr_thread.start()

    def send(self, value: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_CLOSED",
                "codex app-server stdin closed unexpectedly.",
            )
        try:
            self.process.stdin.write(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
            self.process.stdin.flush()
        except (BrokenPipeError, OSError, UnicodeError) as exc:
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_CLOSED",
                "codex app-server closed before the request was sent.",
            ) from exc

    def _remaining(self, limit: float | None = None) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise MaestroError(
                "CODEX_HOST_TIMEOUT",
                "codex app-server did not complete within the configured timeout.",
            )
        return min(remaining, limit) if limit is not None else remaining

    def next_message(
        self,
        *,
        idle_limit: float | None = None,
        idle_ok: bool = False,
    ) -> dict[str, Any] | None:
        try:
            kind, raw = self.output.get(timeout=self._remaining(idle_limit))
        except queue.Empty:
            if idle_ok:
                return None
            if self.process.poll() is not None:
                raise MaestroError(
                    "CODEX_HOST_EXITED",
                    "codex app-server exited before the turn completed.",
                )
            raise MaestroError(
                "CODEX_HOST_TIMEOUT",
                "codex app-server did not produce the required event in time.",
            )
        if kind == "eof":
            if idle_ok:
                return None
            raise MaestroError(
                "CODEX_HOST_EXITED",
                "codex app-server closed its event stream before completion.",
            )
        if kind == "reader-error":
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "codex app-server emitted non-UTF-8 protocol data.",
            )
        encoded_size = len(raw.encode("utf-8"))
        self.messages += 1
        self.bytes += encoded_size
        if (
            encoded_size > MAX_PROTOCOL_LINE_BYTES
            or self.messages > MAX_PROTOCOL_STREAM_MESSAGES
            or self.bytes > MAX_PROTOCOL_STREAM_BYTES
        ):
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_LIMIT",
                "codex app-server exceeded the raw transport safety limit "
                "after high-volume notifications were opted out.",
            )
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "codex app-server emitted invalid JSON-RPC data.",
            ) from exc
        if not isinstance(value, dict):
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "codex app-server messages must be JSON objects.",
            )
        method = value.get("method")
        if (
            isinstance(method, str)
            and "id" not in value
            and method not in _RELEVANT_NOTIFICATIONS
        ):
            self.filtered_notifications += 1
        if "id" in value and isinstance(value.get("method"), str):
            try:
                self.send(
                    {
                        "jsonrpc": "2.0",
                        "id": value["id"],
                        "error": {
                            "code": -32601,
                            "message": "Interactive server requests are not supported.",
                        },
                    }
                )
            except MaestroError as exc:
                if exc.code != "CODEX_HOST_PROTOCOL_CLOSED":
                    raise
            raise MaestroError(
                "CODEX_HOST_INTERACTION_UNSUPPORTED",
                "The turn requested interactive Host input; no approval or user-input request was accepted.",
            )
        return value

    def response(self, request_id: int) -> dict[str, Any]:
        key = ("int", str(request_id))
        if key in self.pending:
            pending = self.pending.pop(key)
            if "error" in pending:
                raise MaestroError(
                    "CODEX_HOST_RPC_FAILED",
                    "codex app-server rejected a Host request.",
                )
            result = pending.get("result")
            if not isinstance(result, dict):
                raise MaestroError(
                    "CODEX_HOST_PROTOCOL_INVALID",
                    "codex app-server response result must be an object.",
                )
            return result
        while True:
            value = self.next_message()
            assert value is not None
            if "id" in value and ("result" in value or "error" in value):
                identifier = value["id"]
                if (
                    isinstance(identifier, (str, int))
                    and not isinstance(identifier, bool)
                ):
                    observed_key = (type(identifier).__name__, str(identifier))
                    if observed_key == key:
                        if "error" in value:
                            raise MaestroError(
                                "CODEX_HOST_RPC_FAILED",
                                "codex app-server rejected a Host request.",
                            )
                        result = value.get("result")
                        if not isinstance(result, dict):
                            raise MaestroError(
                                "CODEX_HOST_PROTOCOL_INVALID",
                                "codex app-server response result must be an object.",
                            )
                        return result
                    self.pending[observed_key] = value
                continue
            if value.get("method") in _RELEVANT_NOTIFICATIONS:
                self.notifications.append(value)

    def close(self) -> bool:
        process = getattr(self, "process", None)
        if process is None:
            return True
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        process_group_id = getattr(self, "process_group_id", None)
        group_terminated = True
        if os.name == "posix" and isinstance(process_group_id, int):
            try:
                os.killpg(process_group_id, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            if _process_group_exists(process_group_id):
                try:
                    os.killpg(process_group_id, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
            try:
                process.wait(timeout=PROCESS_EXIT_GRACE_SECONDS)
            except (subprocess.TimeoutExpired, OSError):
                pass
            group_terminated = _wait_for_process_group_exit(
                process_group_id,
                timeout=PROCESS_EXIT_GRACE_SECONDS,
            )
        else:
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
            if process.poll() is None:
                try:
                    process.wait(timeout=PROCESS_EXIT_GRACE_SECONDS)
                except (subprocess.TimeoutExpired, OSError):
                    pass
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            if process.poll() is None:
                try:
                    process.wait(timeout=PROCESS_EXIT_GRACE_SECONDS)
                except (subprocess.TimeoutExpired, OSError):
                    pass
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        terminated = process.poll() is not None and group_terminated
        if terminated:
            self.process = None
            self.process_group_id = None
        return terminated


def _token_summary(value: Any) -> dict[str, int] | None:
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
    return {target: value[source] for source, target in fields.items()}


def _capture_child_runtime_event(
    *,
    method: str,
    params: dict[str, Any],
    state: dict[str, Any],
    tracker: CodexCollaborationTracker,
) -> bool:
    """Buffer verified child-turn telemetry until its WorkSpan can freeze."""

    if method not in {
        "model/rerouted",
        "thread/tokenUsage/updated",
        "turn/started",
        "turn/completed",
    }:
        return False
    thread_id = params.get("threadId")
    turn = params.get("turn")
    turn_id = (
        turn.get("id")
        if method in {"turn/started", "turn/completed"}
        and isinstance(turn, dict)
        else params.get("turnId")
    )
    work_id = tracker.runtime_work_id(
        thread_id=thread_id,
        turn_id=turn_id,
        bind=method == "turn/started",
    )
    if work_id is None:
        return False
    runtime = state["child_work_runtime"].setdefault(
        work_id,
        {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "started": False,
            "completion": None,
            "reroutes": [],
            "tokens_last": None,
            "tokens_total": None,
            "token_baseline": None,
            "token_baseline_stable": False,
        },
    )
    if (
        runtime["thread_id"] != thread_id
        or runtime["turn_id"] != turn_id
    ):
        raise MaestroError(
            "CODEX_HOST_PROTOCOL_INVALID",
            "A delegated work attempt received conflicting child turn identities.",
        )
    if method == "turn/started":
        if runtime["started"]:
            return True
        prior_turns = [
            item
            for item in state["child_work_runtime"].values()
            if item is not runtime and item["thread_id"] == thread_id
        ]
        start_action = state.get("child_work_starts", {}).get(work_id)
        first_observation_is_resume = (
            not isinstance(start_action, dict)
            or start_action.get("diagnostics", {}).get("followup_reason")
            == "continue_incomplete"
        )
        if not prior_turns and not first_observation_is_resume:
            runtime["token_baseline"] = {
                "input": 0,
                "output": 0,
                "cached": 0,
                "reasoning": 0,
                "total": 0,
            }
            runtime["token_baseline_stable"] = True
        elif isinstance(
            state["child_thread_totals"].get(thread_id),
            dict,
        ):
            runtime["token_baseline"] = dict(
                state["child_thread_totals"][thread_id]
            )
            runtime["token_baseline_stable"] = True
        runtime["started"] = True
        return True
    if method == "model/rerouted":
        reroute = {
            "from_model": _bounded_option(
                params.get("fromModel"),
                field="child-reroute-from-model",
                maximum=128,
            ),
            "to_model": _bounded_option(
                params.get("toModel"),
                field="child-reroute-to-model",
                maximum=128,
            ),
            "reason": _bounded_option(
                params.get("reason"),
                field="child-reroute-reason",
                maximum=160,
            ),
        }
        if any(value is None for value in reroute.values()):
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "A child model reroute requires bounded from, to, and reason fields.",
            )
        if runtime["reroutes"] and runtime["reroutes"][-1] == reroute:
            return True
        runtime["reroutes"].append(reroute)
        if len(runtime["reroutes"]) > MAX_MODEL_REROUTES:
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_LIMIT",
                "A child turn emitted more model reroutes than the observation contract allows.",
            )
        return True
    if method == "thread/tokenUsage/updated":
        usage = params.get("tokenUsage")
        observed_last = (
            _token_summary(usage.get("last"))
            if isinstance(usage, dict)
            else None
        )
        observed_total = (
            _token_summary(usage.get("total"))
            if isinstance(usage, dict)
            else None
        )
        if observed_total is not None:
            runtime["tokens_last"] = observed_last
            runtime["tokens_total"] = observed_total
            state["child_thread_totals"][thread_id] = observed_total
            current = tracker.current_work_id(thread_id)
            if current is not None and current != work_id:
                newer = state["child_work_runtime"].get(current)
                if isinstance(newer, dict):
                    newer["token_baseline_stable"] = False
        return True
    assert isinstance(turn, dict)
    if turn.get("status") not in _TERMINAL_STATUSES:
        return True
    recorded = runtime["completion"]
    if recorded is not None and recorded != turn:
        raise MaestroError(
            "CODEX_HOST_PROTOCOL_INVALID",
            "Conflicting terminal events were emitted for one child turn.",
        )
    runtime["completion"] = turn
    return True


def _token_delta(
    final: Any,
    baseline: Any,
) -> dict[str, int] | None:
    fields = {"input", "output", "cached", "reasoning", "total"}
    if (
        not isinstance(final, dict)
        or not isinstance(baseline, dict)
        or set(final) != fields
        or set(baseline) != fields
    ):
        return None
    delta = {
        field: final[field] - baseline[field]
        for field in fields
    }
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for value in delta.values()
    ):
        return None
    return delta


def _enrich_child_finish_action(
    action: dict[str, Any],
    *,
    start_action: dict[str, Any],
    runtime: dict[str, Any] | None,
) -> dict[str, Any]:
    """Promote child telemetry only from one complete version-bound stream."""

    if not isinstance(runtime, dict):
        return action
    completion = runtime.get("completion")
    binding = start_action.get("source_binding")
    complete_coverage = (
        isinstance(completion, dict)
        and completion.get("status") == action["status"]
        and runtime.get("started") is True
        and isinstance(binding, dict)
        and binding.get("capability") == "full_stream"
        and isinstance(binding.get("version"), str)
        and bool(binding["version"])
        and isinstance(binding.get("schema_digest"), str)
        and bool(binding["schema_digest"])
    )
    if not complete_coverage:
        return action
    requested_model = start_action.get("requested_model")
    reroutes = list(runtime.get("reroutes", []))
    complete_model = isinstance(requested_model, str)
    expected_model = requested_model
    for reroute in reroutes:
        if (
            not complete_model
            or reroute.get("from_model") != expected_model
            or not isinstance(reroute.get("to_model"), str)
        ):
            complete_model = False
            break
        expected_model = reroute["to_model"]
    applied_model = (
        expected_model if complete_model else None
    )
    direct_tokens = (
        _token_delta(
            runtime.get("tokens_total"),
            runtime.get("token_baseline"),
        )
        if runtime.get("token_baseline_stable") is True
        else None
    )
    tokens_last = runtime.get("tokens_last")
    observed_last = tokens_last if isinstance(tokens_last, dict) else None
    completed_at = completion.get("completedAt")
    event_ended_at = (
        codex_event_timestamp(completed_at * 1000)
        if (
            isinstance(completed_at, int)
            and not isinstance(completed_at, bool)
            and completed_at >= 0
        )
        else action["ended_at"]
    )
    duration = completion.get("durationMs")
    event_duration = (
        float(duration)
        if (
            isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and duration >= 0
        )
        else action.get("duration_ms")
    )
    return {
        **action,
        "ended_at": event_ended_at,
        "duration_ms": event_duration,
        "applied_model": applied_model,
        "model_evidence": (
            "complete"
            if complete_model
            else start_action.get("model_evidence", "unavailable")
        ),
        "source_binding": {
            **binding,
            "event_coverage": "complete_stream",
        },
        "model_observation": {
            "observed_model": None,
            "coverage": (
                "complete_stream"
                if complete_model
                else (
                    "request_only"
                    if isinstance(requested_model, str)
                    else "unavailable"
                )
            ),
            "reroutes": reroutes if complete_model else [],
        },
        "usage": {
            "last": observed_last if direct_tokens is not None else None,
            "total": direct_tokens,
            "scope": (
                "work_turn"
                if direct_tokens is not None
                else "unavailable"
            ),
            "attribution": (
                "direct"
                if direct_tokens is not None
                else "unavailable"
            ),
            "timing_coverage": "host_event",
            "cost": None,
        },
    }


def _codex_error_identifier(value: Any) -> str:
    """Return a bounded, non-message identifier for one Host error."""

    if isinstance(value, dict):
        for field in ("code", "codexErrorInfo", "type"):
            candidate = value.get(field)
            if (
                isinstance(candidate, (str, int))
                and not isinstance(candidate, bool)
                and str(candidate).strip()
            ):
                return str(candidate).strip()[:80]
        return "unclassified"
    if isinstance(value, str) and value.strip():
        return value.strip()[:80]
    return "unclassified"


def _process_notification(
    value: dict[str, Any],
    state: dict[str, Any],
) -> None:
    method = value.get("method")
    params = value.get("params")
    if method not in _RELEVANT_NOTIFICATIONS or not isinstance(params, dict):
        return
    tracker = state.get("work_tracker")
    action_sink = state.get("work_action_sink")
    if (
        method in {"item/started", "item/completed"}
        and isinstance(tracker, CodexCollaborationTracker)
        and callable(action_sink)
        and tracker.accepts(params)
    ):
        actions = tracker.consume(method=method, params=params)
        for action in actions:
            action_sink(action)
        return
    if (
        isinstance(tracker, CodexCollaborationTracker)
        and _capture_child_runtime_event(
            method=str(method),
            params=params,
            state=state,
            tracker=tracker,
        )
    ):
        return
    if params.get("threadId") != state["thread_id"]:
        return
    if method == "error":
        if params.get("turnId") not in {None, state["turn_id"]}:
            return
        code = _codex_error_identifier(params.get("error"))
        state["error_count"] += 1
        state["last_error"] = f"Codex App Server error ({str(code)[:80]})"
        return
    if method == "turn/completed":
        turn = params.get("turn")
        if (
            not isinstance(turn, dict)
            or turn.get("id") != state["turn_id"]
            or turn.get("status") not in _TERMINAL_STATUSES
        ):
            return
        if state["completion"] is not None and state["completion"] != turn:
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "Conflicting terminal events were emitted for the same turn.",
            )
        state["completion"] = turn
        return
    if params.get("turnId") != state["turn_id"]:
        return
    if method == "model/rerouted":
        reroute = {
            "from_model": params.get("fromModel"),
            "to_model": params.get("toModel"),
            "reason": params.get("reason"),
        }
        state["reroutes"].append(reroute)
        if len(state["reroutes"]) > MAX_MODEL_REROUTES:
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_LIMIT",
                "The turn emitted more model reroutes than the observation contract allows.",
            )
        return
    if method == "thread/tokenUsage/updated":
        usage = params.get("tokenUsage")
        observed_last = (
            _token_summary(usage.get("last"))
            if isinstance(usage, dict)
            else None
        )
        observed_total = (
            _token_summary(usage.get("total"))
            if isinstance(usage, dict)
            else None
        )
        if observed_total is not None:
            state["tokens"] = observed_total
            state["tokens_last"] = observed_last
            state["token_updates"] += 1
        return
    item = params.get("item")
    if (
        method == "item/completed"
        and isinstance(item, dict)
    ):
        _capture_agent_message(item, state)


def _capture_agent_message(
    item: dict[str, Any],
    state: dict[str, Any],
) -> None:
    if (
        item.get("type") != "agentMessage"
        or not isinstance(item.get("text"), str)
    ):
        return
    if item.get("phase") == "final_answer":
        state["final_message"] = item["text"]
        state["final_message_is_final"] = True
    elif not state["final_message_is_final"]:
        state["final_message"] = item["text"]


def _capture_terminal_message(
    completion: dict[str, Any],
    state: dict[str, Any],
) -> None:
    items = completion.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if isinstance(item, dict):
            _capture_agent_message(item, state)


def _capture_terminal_collaboration(
    completion: dict[str, Any],
    state: dict[str, Any],
) -> None:
    completed_at = completion.get("completedAt")
    items = completion.get("items")
    if (
        not isinstance(completed_at, int)
        or isinstance(completed_at, bool)
        or completed_at < 0
        or not isinstance(items, list)
    ):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        _process_notification(
            {
                "method": "item/completed",
                "params": {
                    "threadId": state["thread_id"],
                    "turnId": state["turn_id"],
                    "completedAtMs": completed_at * 1000,
                    "item": item,
                },
            },
            state,
        )


def _record_codex_work_action(
    repo: Path,
    *,
    observation_id: str,
    run_id: str,
    action: dict[str, Any],
) -> None:
    if action["action"] == "start":
        record_work_start(
            repo,
            observation_id=observation_id,
            run_id=run_id,
            work_id=action["work_id"],
            parent_work_id=action["parent_work_id"],
            assignment_id=action["assignment_id"],
            kind=action["kind"],
            role=action["role"],
            executor_id=action["executor_id"],
            task_summary=action["task_summary"],
            read_only=action["read_only"],
            source=action["source"],
            attempt=action["attempt"],
            followup_of_work_id=action["followup_of_work_id"],
            depends_on_work_ids=action["depends_on_work_ids"],
            joins_work_ids=action["joins_work_ids"],
            requested_model=action["requested_model"],
            requested_reasoning_effort=action[
                "requested_reasoning_effort"
            ],
            model_evidence=action["model_evidence"],
            source_binding=action.get("source_binding"),
            model_observation=action.get("model_observation"),
            usage=action.get("usage"),
            outcome=action.get("outcome"),
            diagnostics=action.get("diagnostics"),
            allocation=action.get("allocation"),
            expertise_observation=action.get(
                "expertise_observation"
            ),
            event_started_at=action["started_at"],
        )
        return
    if action["action"] == "finish":
        record_work_finish(
            repo,
            observation_id=observation_id,
            run_id=run_id,
            work_id=action["work_id"],
            status=action["status"],
            result_summary=action["result_summary"],
            evidence_refs=action["evidence_refs"],
            applied_model=action.get("applied_model"),
            model_evidence=action.get("model_evidence"),
            expertise_evidence=action.get("expertise_evidence"),
            source_binding=action.get("source_binding"),
            model_observation=action.get("model_observation"),
            usage=action.get("usage"),
            outcome=action.get("outcome"),
            diagnostics=action.get("diagnostics"),
            allocation=action.get("allocation"),
            expertise_observation=action.get(
                "expertise_observation"
            ),
            event_ended_at=action["ended_at"],
            event_duration_ms=action.get("duration_ms"),
        )
        return
    raise MaestroError(
        "CODEX_WORK_EVENT_INVALID",
        "Codex collaboration adapter returned an unsupported work action.",
    )


def _managed_root_finish_action(
    action: dict[str, Any],
    *,
    status: str,
    result_summary: str,
    evidence_refs: list[str],
    runtime_binding: dict[str, Any],
    requested_model: str,
    applied_model: str | None,
    reroutes: list[dict[str, Any]],
    tokens_last: dict[str, Any] | None,
    tokens_total: dict[str, Any] | None,
    outcome: dict[str, Any],
    diagnostics: dict[str, Any],
    expertise_evidence: str,
    expertise_observation: dict[str, Any],
    preserve_host_timing: bool,
    correlation_id: str,
) -> dict[str, Any]:
    complete_coverage = (
        runtime_binding["capability"] == "full_stream"
        and runtime_binding["version"] is not None
        and runtime_binding["schema_digest"] is not None
    )
    complete_model_coverage = (
        complete_coverage and applied_model is not None
    )
    work_status = {
        "completed": "completed",
        "failed": "failed",
        "blocked": "blocked",
        "interrupted": "interrupted",
        "skipped": "interrupted",
    }.get(status, "failed")
    return {
        **action,
        "status": work_status,
        "result_summary": result_summary[:240],
        "evidence_refs": evidence_refs[:5],
        "ended_at": (
            action.get("ended_at")
            if preserve_host_timing
            else None
        ),
        "duration_ms": (
            action.get("duration_ms")
            if preserve_host_timing
            else None
        ),
        "applied_model": (
            applied_model if complete_model_coverage else None
        ),
        "model_evidence": (
            "complete"
            if complete_model_coverage
            else "host_request"
        ),
        "expertise_evidence": expertise_evidence,
        "source_binding": {
            "interface": "codex_app_server",
            "version": runtime_binding["version"],
            "schema_digest": runtime_binding["schema_digest"],
            "capability": runtime_binding["capability"],
            "correlation_id": correlation_id,
            "event_coverage": (
                "complete_stream"
                if complete_coverage
                else "partial_stream"
            ),
        },
        "model_observation": {
            "observed_model": None,
            "coverage": (
                "complete_stream"
                if complete_model_coverage
                else "request_only"
            ),
            "reroutes": list(reroutes) if complete_model_coverage else [],
        },
        "usage": {
            "last": tokens_last if complete_coverage else None,
            "total": tokens_total if complete_coverage else None,
            "scope": (
                "work_turn"
                if complete_coverage and tokens_total is not None
                else "unavailable"
            ),
            "attribution": (
                "direct"
                if complete_coverage and tokens_total is not None
                else "unavailable"
            ),
            "timing_coverage": (
                "host_event" if complete_coverage else "partial"
            ),
            "cost": None,
        },
        "outcome": outcome,
        "diagnostics": diagnostics,
        "expertise_observation": expertise_observation,
    }


def _record_dependency_handoff(
    repo: Path,
    *,
    observation: dict[str, Any],
    run_id: str,
    downstream_assignment_id: str,
    dependency_assignment_ids: list[str],
    dependency_packet_digests: dict[str, str],
) -> str:
    """Record validated dependency consumption without claiming model work."""

    heads_by_assignment = terminal_assignment_work_heads(
        observation.get("work_spans"),
        dependency_assignment_ids,
    )
    missing = [
        assignment_id
        for assignment_id in dependency_assignment_ids
        if not heads_by_assignment.get(assignment_id)
    ]
    if missing:
        raise MaestroError(
            "CODEX_HOST_DEPENDENCY_WORK_MISSING",
            "A dependent Assignment requires terminal v2 work for every "
            "direct dependency: " + ", ".join(missing),
        )
    joined_work_ids = list(
        dict.fromkeys(
            work_id
            for assignment_id in dependency_assignment_ids
            for work_id in heads_by_assignment[assignment_id]
        )
    )
    if len(joined_work_ids) > 16:
        raise MaestroError(
            "CODEX_HOST_DEPENDENCY_WORK_LIMIT",
            "Direct dependency terminal work exceeds the bounded handoff relation limit.",
        )
    packet_digests = [
        dependency_packet_digests[assignment_id]
        for assignment_id in dependency_assignment_ids
    ]
    evidence_refs = [
        f"assignment-packet:{digest}" for digest in packet_digests
    ]
    handoff_work_id = codex_work_id(
        "assignment-handoff",
        run_id,
        downstream_assignment_id,
        *dependency_assignment_ids,
        *packet_digests,
        *joined_work_ids,
    )
    expected_outcome = {
        "finding_summary": None,
        "conclusion": (
            "Direct dependency terminal work와 Packet digest가 "
            "parent stage evidence에 일치합니다."
        ),
        "decision": (
            f"{downstream_assignment_id} Assignment launch 조건이 "
            "충족되었습니다."
        ),
        "next_action": "continue",
        "consumed_work_ids": joined_work_ids,
        "handoff": {
            "purpose": (
                f"검증된 dependency 결과를 {downstream_assignment_id} "
                "Assignment에 전달합니다."
            ),
            "completion_criteria": (
                "Downstream root work가 이 handoff에 명시적으로 의존합니다."
            ),
        },
        "artifacts": [],
        "verification": None,
    }
    recorded = next(
        (
            span
            for span in observation.get("work_spans", [])
            if isinstance(span, dict)
            and span.get("work_id") == handoff_work_id
        ),
        None,
    )
    if recorded is not None:
        if not (
            recorded.get("schema_version") == "maestro_work_span_v2"
            and recorded.get("assignment_id") is None
            and recorded.get("kind") == "synthesis"
            and recorded.get("joins_work_ids") == joined_work_ids
            and recorded.get("outcome") == expected_outcome
        ):
            raise MaestroError(
                "CODEX_HOST_DEPENDENCY_HANDOFF_CONFLICT",
                "The deterministic dependency handoff already contains different facts.",
            )
        if recorded.get("status") == "running":
            record_work_finish(
                repo,
                observation_id=observation["observation_id"],
                run_id=run_id,
                work_id=handoff_work_id,
                status="completed",
                result_summary=(
                    "Dependency Packet 검증과 downstream launch 결정을 기록했습니다."
                ),
                evidence_refs=evidence_refs,
            )
            return handoff_work_id
        if recorded.get("status") != "completed":
            raise MaestroError(
                "CODEX_HOST_DEPENDENCY_HANDOFF_CONFLICT",
                "The deterministic dependency handoff has a non-recoverable terminal state.",
            )
        return handoff_work_id

    record_work_start(
        repo,
        observation_id=observation["observation_id"],
        run_id=run_id,
        work_id=handoff_work_id,
        assignment_id=None,
        kind="synthesis",
        role="Maestro dependency handoff",
        executor_id="maestro-codex-host",
        task_summary=(
            f"Direct dependency Packet {len(packet_digests)}건을 검증하고 "
            f"{downstream_assignment_id} launch 결정을 기록합니다."
        ),
        read_only=True,
        source="current_host",
        joins_work_ids=joined_work_ids,
        outcome=expected_outcome,
    )
    record_work_finish(
        repo,
        observation_id=observation["observation_id"],
        run_id=run_id,
        work_id=handoff_work_id,
        status="completed",
        result_summary=(
            "Dependency Packet 검증과 downstream launch 결정을 기록했습니다."
        ),
        evidence_refs=evidence_refs,
    )
    return handoff_work_id


def _command(command: Sequence[str] | None) -> list[str]:
    if command is not None:
        if not command or not all(
            isinstance(item, str) and item
            for item in command
        ):
            raise MaestroError(
                "CODEX_HOST_COMMAND_INVALID",
                "Internal app-server command must be a non-empty argument list.",
            )
        return list(command)
    executable = shutil.which("codex")
    if executable is None:
        raise MaestroError(
            "CODEX_HOST_NOT_INSTALLED",
            "Codex CLI is not installed or is not available on PATH.",
        )
    return [executable, "app-server", "--stdio"]


def _repository_change_snapshot(repo: Path) -> dict[str, Any]:
    """Fingerprint HEAD plus Git-visible working changes for a scope audit."""

    repo = repo.resolve()
    head_result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    head = head_result.stdout.decode("ascii").strip()
    if (
        len(head) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in head)
    ):
        raise MaestroError(
            "CODEX_HOST_SCOPE_AUDIT_INVALID",
            "Unable to bind scoped execution to a valid repository HEAD.",
        )
    commands = (
        ["git", "-C", str(repo), "diff", "--name-only", "-z", "HEAD", "--"],
        [
            "git",
            "-C",
            str(repo),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
    )
    paths: set[str] = set()
    for command in commands:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=20,
        )
        paths.update(
            value.decode("utf-8", errors="surrogateescape")
            for value in completed.stdout.split(b"\0")
            if value
        )
    snapshot: dict[str, str] = {}
    for relative_path in sorted(paths):
        if (
            relative_path == ".maestro/state"
            or relative_path.startswith(".maestro/state/")
        ):
            continue
        target = repo / relative_path
        if target.is_symlink():
            snapshot[relative_path] = "symlink:" + os.readlink(target)
        elif target.is_file():
            snapshot[relative_path] = "file:" + file_sha256(target)
        elif target.exists():
            snapshot[relative_path] = "other"
        else:
            snapshot[relative_path] = "missing"
    return {
        "head": head,
        "paths": snapshot,
    }


def _repository_effect_snapshot(repo: Path) -> dict[str, Any]:
    """Fingerprint effects even in a newly initialized repository.

    Scoped Decision execution still uses the stricter HEAD-bound audit above.
    This fallback exists only so a receipt can attest writes in an unborn
    temporary or freshly initialized worktree.
    """

    try:
        return _repository_change_snapshot(repo)
    except subprocess.CalledProcessError:
        snapshot: dict[str, str] = {}
        for root, directory_names, file_names in os.walk(repo):
            root_path = Path(root)
            directory_names[:] = [
                name
                for name in directory_names
                if not (
                    root_path == repo and name == ".git"
                )
                and not (
                    root_path == repo / ".maestro"
                    and name == "state"
                )
            ]
            for name in file_names:
                target = root_path / name
                relative_path = target.relative_to(repo).as_posix()
                if target.is_symlink():
                    snapshot[relative_path] = (
                        "symlink:" + os.readlink(target)
                    )
                elif target.is_file():
                    snapshot[relative_path] = (
                        "file:" + file_sha256(target)
                    )
        return {
            "head": None,
            "paths": snapshot,
        }


def _repository_snapshot_changed(
    before: dict[str, Any],
    after: dict[str, Any],
) -> bool:
    """Return whether a bounded turn changed Git-visible repository state."""

    return (
        before.get("head") != after.get("head")
        or before.get("paths") != after.get("paths")
    )


def _assert_scoped_repository_changes(
    repo: Path,
    *,
    before: dict[str, Any],
    allowed_roots: Sequence[str],
) -> None:
    """Fail if a scoped turn leaves a material Git-visible sibling change."""

    repo = repo.resolve()
    after = _repository_change_snapshot(repo)
    if before.get("head") != after["head"]:
        raise MaestroError(
            "CODEX_HOST_SCOPE_VIOLATION",
            (
                "Scoped Decision execution changed repository HEAD; "
                "git commits and reference updates are outside repository_write."
            ),
        )
    before_paths = before.get("paths")
    if not isinstance(before_paths, dict):
        raise MaestroError(
            "CODEX_HOST_SCOPE_AUDIT_INVALID",
            "The pre-execution scope snapshot is invalid.",
        )
    after_paths = after["paths"]
    changed = sorted(
        path
        for path in set(before_paths) | set(after_paths)
        if before_paths.get(path) != after_paths.get(path)
    )
    allowed_relative = [
        Path(root).resolve().relative_to(repo)
        for root in allowed_roots
    ]
    unauthorized = [
        path
        for path in changed
        if not any(
            Path(path) == root or root in Path(path).parents
            for root in allowed_relative
        )
    ]
    if unauthorized:
        raise MaestroError(
            "CODEX_HOST_SCOPE_VIOLATION",
            (
                "Scoped Decision execution changed paths outside allowed_paths: "
                + ", ".join(unauthorized)
            ),
        )


def _terminate_and_audit_scoped_server(
    server: "_AppServer",
    repo: Path,
    *,
    before: dict[str, Any],
    allowed_roots: Sequence[str],
    thread_ids: Sequence[str] = (),
    active_turn: tuple[str, str] | None = None,
) -> None:
    """Quiesce scoped work, terminate its Host, then inspect repository state."""

    server.deadline = max(
        server.deadline,
        time.monotonic() + SCOPED_SHUTDOWN_GRACE_SECONDS,
    )
    quiescence_error: MaestroError | None = None
    if active_turn is not None:
        try:
            _interrupt_active_turn(
                server,
                thread_id=active_turn[0],
                turn_id=active_turn[1],
            )
        except MaestroError as exc:
            quiescence_error = exc
    if quiescence_error is None:
        seen_thread_ids: set[str] = set()
        for thread_id in thread_ids:
            if thread_id in seen_thread_ids:
                continue
            seen_thread_ids.add(thread_id)
            try:
                _quiesce_background_terminals(server, thread_id)
            except MaestroError as exc:
                if quiescence_error is None:
                    quiescence_error = exc
    server_terminated = server.close()
    if quiescence_error is not None:
        raise MaestroError(
            "CODEX_HOST_BACKGROUND_TERMINALS_UNQUIESCED",
            (
                "Codex background terminals could not be confirmed stopped, "
                "so post-run write scope cannot be verified."
            ),
        ) from quiescence_error
    if not server_terminated:
        raise MaestroError(
            "CODEX_HOST_TERMINATION_FAILED",
            (
                "The scoped Codex App Server did not terminate, so post-run "
                "write scope cannot be verified."
            ),
        )
    _assert_scoped_repository_changes(
        repo,
        before=before,
        allowed_roots=allowed_roots,
    )


def _interrupt_active_turn(
    server: "_AppServer",
    *,
    thread_id: str,
    turn_id: str,
) -> None:
    """Interrupt one active turn and wait for its matching terminal event."""

    if any(
        not isinstance(value, str) or not value.strip()
        for value in (thread_id, turn_id)
    ):
        raise MaestroError(
            "CODEX_HOST_PROTOCOL_INVALID",
            "Scoped turn interruption requires usable thread and turn IDs.",
        )

    def is_terminal(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        params = value.get("params")
        turn = params.get("turn") if isinstance(params, dict) else None
        return (
            value.get("method") == "turn/completed"
            and params.get("threadId") == thread_id
            and isinstance(turn, dict)
            and turn.get("id") == turn_id
            and turn.get("status") in _TERMINAL_STATUSES
        )

    server.send(
        {
            "jsonrpc": "2.0",
            "id": 9_000,
            "method": "turn/interrupt",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
            },
        }
    )
    server.response(9_000)
    if any(is_terminal(value) for value in server.notifications):
        return
    interrupt_deadline = min(
        server.deadline,
        time.monotonic() + TURN_INTERRUPT_GRACE_SECONDS,
    )
    while time.monotonic() < interrupt_deadline:
        value = server.next_message(
            idle_limit=max(
                0.001,
                interrupt_deadline - time.monotonic(),
            ),
            idle_ok=True,
        )
        if value is None:
            break
        if is_terminal(value):
            return
    raise MaestroError(
        "CODEX_HOST_TURN_UNQUIESCED",
        "Codex did not confirm a terminal turn after interruption.",
    )


def _quiesce_background_terminals(
    server: "_AppServer",
    thread_id: str,
) -> int:
    """Terminate every tracked terminal and prove the thread has none left."""

    if not isinstance(thread_id, str) or not thread_id.strip():
        raise MaestroError(
            "CODEX_HOST_PROTOCOL_INVALID",
            "Background-terminal cleanup requires a usable thread ID.",
        )
    request_id = 10_000

    def request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        nonlocal request_id
        current_id = request_id
        request_id += 1
        server.send(
            {
                "jsonrpc": "2.0",
                "id": current_id,
                "method": method,
                "params": params,
            }
        )
        return server.response(current_id)

    def list_terminals() -> list[dict[str, Any]]:
        cursor: str | None = None
        seen_cursors: set[str] = set()
        seen_processes: set[str] = set()
        terminals: list[dict[str, Any]] = []
        while True:
            params: dict[str, Any] = {
                "threadId": thread_id,
                "limit": BACKGROUND_TERMINAL_PAGE_SIZE,
            }
            if cursor is not None:
                params["cursor"] = cursor
            result = request(
                "thread/backgroundTerminals/list",
                params,
            )
            data = result.get("data")
            if not isinstance(data, list):
                raise MaestroError(
                    "CODEX_HOST_PROTOCOL_INVALID",
                    "backgroundTerminals/list did not return a data array.",
                )
            for terminal in data:
                process_id = (
                    terminal.get("processId")
                    if isinstance(terminal, dict)
                    else None
                )
                if (
                    not isinstance(process_id, str)
                    or not process_id.strip()
                    or process_id in seen_processes
                ):
                    raise MaestroError(
                        "CODEX_HOST_PROTOCOL_INVALID",
                        (
                            "backgroundTerminals/list returned an invalid or "
                            "duplicate processId."
                        ),
                    )
                seen_processes.add(process_id)
                terminals.append(terminal)
                if len(terminals) > MAX_BACKGROUND_TERMINALS:
                    raise MaestroError(
                        "CODEX_HOST_PROTOCOL_LIMIT",
                        (
                            "backgroundTerminals/list exceeded the scoped "
                            "cleanup safety limit."
                        ),
                    )
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                return terminals
            if (
                not isinstance(next_cursor, str)
                or not next_cursor
                or next_cursor in seen_cursors
            ):
                raise MaestroError(
                    "CODEX_HOST_PROTOCOL_INVALID",
                    (
                        "backgroundTerminals/list returned an invalid or "
                        "repeated pagination cursor."
                    ),
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    observed_processes: set[str] = set()
    for _ in range(MAX_BACKGROUND_TERMINAL_CLEANUP_ROUNDS):
        terminals = list_terminals()
        if not terminals:
            return len(observed_processes)
        for terminal in terminals:
            process_id = terminal["processId"]
            observed_processes.add(process_id)
            result = request(
                "thread/backgroundTerminals/terminate",
                {
                    "threadId": thread_id,
                    "processId": process_id,
                },
            )
            if not isinstance(result.get("terminated"), bool):
                raise MaestroError(
                    "CODEX_HOST_PROTOCOL_INVALID",
                    (
                        "backgroundTerminals/terminate did not return a "
                        "boolean terminated result."
                    ),
                )
    if list_terminals():
        raise MaestroError(
            "CODEX_HOST_BACKGROUND_TERMINAL_ACTIVE",
            (
                "Codex still reports a background terminal after bounded "
                "cleanup attempts."
            ),
        )
    return len(observed_processes)


def _scoped_thread_ids(state: dict[str, Any]) -> list[str]:
    """Return every root or delegated Codex thread observed by this turn."""

    candidates = [state.get("thread_id")]
    child_runtime = state.get("child_work_runtime")
    if isinstance(child_runtime, dict):
        candidates.extend(
            runtime.get("thread_id")
            for runtime in child_runtime.values()
            if isinstance(runtime, dict)
        )
    thread_ids: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        if (
            isinstance(value, str)
            and value.strip()
            and value not in seen
        ):
            seen.add(value)
            thread_ids.append(value)
    return thread_ids


def _active_scoped_turn(
    state: dict[str, Any],
) -> tuple[str, str] | None:
    """Return the owned turn only while no terminal event was observed."""

    if state.get("completion") is not None:
        return None
    thread_id = state.get("thread_id")
    turn_id = state.get("turn_id")
    if (
        isinstance(thread_id, str)
        and thread_id.strip()
        and isinstance(turn_id, str)
        and turn_id.strip()
    ):
        return thread_id, turn_id
    return None


def _shutdown_and_audit_scoped_host(
    server: "_AppServer",
    repo: Path,
    *,
    state: dict[str, Any],
    before: dict[str, Any],
    allowed_roots: Sequence[str],
) -> None:
    """Interpret owned turn state before delegating bounded shutdown."""

    if (
        state.get("turn_start_requested") is True
        and state.get("turn_id") is None
        and state.get("completion") is None
    ):
        server.deadline = max(
            server.deadline,
            time.monotonic() + SCOPED_SHUTDOWN_GRACE_SECONDS,
        )
        if not server.close():
            raise MaestroError(
                "CODEX_HOST_TERMINATION_FAILED",
                (
                    "The scoped Codex App Server did not terminate after an "
                    "unconfirmed turn/start."
                ),
            )
        raise MaestroError(
            "CODEX_HOST_BACKGROUND_TERMINALS_UNQUIESCED",
            (
                "turn/start was sent but no turn ID was confirmed, so active "
                "work cannot be interrupted and post-run scope cannot be "
                "verified."
            ),
        )
    _terminate_and_audit_scoped_server(
        server,
        repo,
        before=before,
        allowed_roots=allowed_roots,
        thread_ids=_scoped_thread_ids(state),
        active_turn=_active_scoped_turn(state),
    )


def _same_runtime_workspace_roots(
    reported: Any,
    expected: Sequence[str],
) -> bool:
    """Compare the App Server's effective roots with the authorized roots."""

    if (
        not isinstance(reported, list)
        or not all(
            isinstance(value, str)
            and value
            and Path(value).is_absolute()
            for value in reported
        )
        or len(reported) != len(set(reported))
    ):
        return False
    return {
        str(Path(value).resolve())
        for value in reported
    } == {
        str(Path(value).resolve())
        for value in expected
    }


@lru_cache(maxsize=4)
def _codex_runtime_binding(executable: str) -> dict[str, Any]:
    """Bind the installed Codex version and generated stable schema surface."""

    if Path(executable).name != "codex":
        return {
            "version": None,
            "schema_digest": None,
            "capability": "lifecycle_only",
            "experimental_api": False,
            "runtime_workspace_roots": False,
            "background_terminal_control": False,
            "turn_interrupt": False,
        }
    try:
        version_result = subprocess.run(
            [executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = version_result.stdout.strip()
        if not version or len(version) > 80 or "\n" in version:
            raise ValueError("invalid version")
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run(
                [
                    executable,
                    "app-server",
                    "generate-json-schema",
                    "--experimental",
                    "--out",
                    temporary,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            root = Path(temporary)
            files = sorted(
                path
                for path in root.rglob("*")
                if path.is_file() and not path.is_symlink()
            )
            if not files:
                raise ValueError("schema bundle is empty")
            schema_manifest: list[dict[str, str]] = []
            schema_texts: dict[str, str] = {}
            for path in files:
                schema_text = path.read_text(encoding="utf-8")
                relative_path = path.relative_to(root).as_posix()
                schema_texts[relative_path] = schema_text
                schema_manifest.append(
                    {
                        "path": relative_path,
                        "sha256": sha256_text(schema_text),
                    }
                )
            experimental_api = '"experimentalApi"' in schema_texts.get(
                "v1/InitializeParams.json",
                "",
            )
            runtime_workspace_roots = all(
                '"runtimeWorkspaceRoots"' in schema_texts.get(path, "")
                for path in (
                    "v2/ThreadStartParams.json",
                    "v2/ThreadStartResponse.json",
                    "v2/TurnStartParams.json",
                )
            )
            client_requests = schema_texts.get("ClientRequest.json", "")
            background_terminal_schema_files = {
                "v2/ThreadBackgroundTerminalsListParams.json",
                "v2/ThreadBackgroundTerminalsListResponse.json",
                "v2/ThreadBackgroundTerminalsTerminateParams.json",
                "v2/ThreadBackgroundTerminalsTerminateResponse.json",
            }
            background_terminal_control = (
                background_terminal_schema_files <= schema_texts.keys()
                and all(
                    f'"thread/backgroundTerminals/{method}"'
                    in client_requests
                    for method in ("list", "terminate")
                )
                and all(
                    field
                    in schema_texts.get(
                        "v2/ThreadBackgroundTerminalsListParams.json",
                        "",
                    )
                    for field in ('"threadId"', '"cursor"', '"limit"')
                )
                and all(
                    field
                    in schema_texts.get(
                        "v2/ThreadBackgroundTerminalsListResponse.json",
                        "",
                    )
                    for field in ('"data"', '"processId"', '"nextCursor"')
                )
                and all(
                    field
                    in schema_texts.get(
                        "v2/ThreadBackgroundTerminalsTerminateParams.json",
                        "",
                    )
                    for field in ('"threadId"', '"processId"')
                )
                and '"terminated"' in schema_texts.get(
                    "v2/ThreadBackgroundTerminalsTerminateResponse.json",
                    "",
                )
            )
            turn_interrupt = (
                '"turn/interrupt"' in client_requests
                and {
                    "v2/TurnInterruptParams.json",
                    "v2/TurnInterruptResponse.json",
                }
                <= schema_texts.keys()
                and all(
                    field
                    in schema_texts.get(
                        "v2/TurnInterruptParams.json",
                        "",
                    )
                    for field in ('"threadId"', '"turnId"')
                )
            )
        return {
            "version": version,
            "schema_digest": sha256_text(canonical_json(schema_manifest)),
            "capability": "full_stream",
            "experimental_api": experimental_api,
            "runtime_workspace_roots": runtime_workspace_roots,
            "background_terminal_control": background_terminal_control,
            "turn_interrupt": turn_interrupt,
        }
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeError,
        ValueError,
    ):
        return {
            "version": None,
            "schema_digest": None,
            "capability": "lifecycle_only",
            "experimental_api": False,
            "runtime_workspace_roots": False,
            "background_terminal_control": False,
            "turn_interrupt": False,
        }


def _supports_scoped_enactment(runtime_binding: dict[str, Any]) -> bool:
    return (
        _scoped_process_quiescence_supported()
        and runtime_binding.get("experimental_api") is True
        and runtime_binding.get("runtime_workspace_roots") is True
        and runtime_binding.get("background_terminal_control") is True
        and runtime_binding.get("turn_interrupt") is True
    )


def _run_codex_host_locked(
    repo_path: str | Path,
    *,
    run_id: str,
    task_label: str,
    prompt_file: str | Path | None = None,
    plan_path: str | Path | None = None,
    assignment_id: str | None = None,
    projection_path: str | Path | None = None,
    baseline_path: str | Path | None = None,
    document_paths: Sequence[str] = (),
    dependency_packet_paths: Sequence[str | Path] = (),
    dependency_projection_paths: Sequence[str | Path] = (),
    research_evidence_path: str | Path | None = None,
    coverage_path: str | Path | None = None,
    coverage_admission_path: str | Path | None = None,
    coverage_projection_path: str | Path | None = None,
    expertise_work_plan_path: str | Path | None = None,
    expertise_closure_path: str | Path | None = None,
    design_decision_path: str | Path | None = None,
    expertise_research_evidence_paths: Sequence[str | Path] = (),
    observation_id: str | None = None,
    sandbox: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    command: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run one Codex App Server turn and persist only bounded Host telemetry."""

    repo = ensure_repo(repo_path)
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
        or timeout_seconds > MAX_TIMEOUT_SECONDS
    ):
        raise MaestroError(
            "CODEX_HOST_TIMEOUT_INVALID",
            f"timeout must be greater than zero and at most {MAX_TIMEOUT_SECONDS:g} seconds.",
        )
    contract = _host_contract(
        repo,
        plan_path=plan_path,
        assignment_id=assignment_id,
        projection_path=projection_path,
        baseline_path=baseline_path,
        document_paths=document_paths,
        dependency_packet_paths=dependency_packet_paths,
        dependency_projection_paths=dependency_projection_paths,
        research_evidence_path=research_evidence_path,
        coverage_path=coverage_path,
        coverage_admission_path=coverage_admission_path,
        coverage_projection_path=coverage_projection_path,
        expertise_work_plan_path=expertise_work_plan_path,
        expertise_closure_path=expertise_closure_path,
        design_decision_path=design_decision_path,
        expertise_research_evidence_paths=expertise_research_evidence_paths,
        sandbox=sandbox,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    if contract["assignment"] is not None:
        if prompt_file is not None:
            raise MaestroError(
                "CODEX_HOST_PROMPT_CONFLICT",
                "Assignment execution derives its prompt only from the exact projection; do not supply --prompt-file.",
            )
        assert isinstance(contract["projection"], dict)
        assert isinstance(contract["output_schema"], dict)
        prompt = _assignment_prompt(
            contract["projection"],
            contract["output_schema"],
            (
                contract["expertise_execution"]["prompt_context"]
                if isinstance(
                    contract.get("expertise_execution"),
                    dict,
                )
                else None
            ),
        )
    else:
        if prompt_file is None:
            raise MaestroError(
                "CODEX_HOST_PROMPT_REQUIRED",
                "Standalone Host execution requires --prompt-file.",
            )
        prompt = _bounded_text_file(prompt_file)
    host_command = _command(command)
    runtime_binding = _codex_runtime_binding(host_command[0])
    if (
        contract["scoped_write_roots"]
        and not _supports_scoped_enactment(runtime_binding)
    ):
        raise MaestroError(
            "CODEX_HOST_SCOPED_SANDBOX_UNAVAILABLE",
            (
                "This Host cannot prove both exact Decision write roots and "
                "terminal background-work and App Server quiescence, so "
                "scoped enactment fails closed."
            ),
        )
    send_runtime_workspace_roots = (
        runtime_binding.get("runtime_workspace_roots") is True
        or Path(host_command[0]).name != "codex"
    )
    scope_snapshot = (
        _repository_change_snapshot(repo)
        if contract["scoped_write_roots"]
        else None
    )
    effect_snapshot = (
        scope_snapshot
        if scope_snapshot is not None
        else (
            _repository_effect_snapshot(repo)
            if contract["assignment_id"] is not None
            else None
        )
    )
    dependency_results: dict[str, dict[str, Any]] = {}
    execution_receipts_required = False
    observation: dict[str, Any] | None
    if observation_id is not None:
        claim_maestro_owned_codex_execution(
            repo,
            observation_id=observation_id,
            run_id=run_id,
        )
        observed = observation_receipt_fields(
            repo,
            observation_id=observation_id,
            run_id=run_id,
        )
        observed_plan = observed.get("plan_summary")
        if (
            contract["assignment_id"] is None
            or not isinstance(observed_plan, dict)
            or observed_plan.get("plan_id") != contract["plan_id"]
        ):
            raise MaestroError(
                "CODEX_HOST_RUN_CONFLICT",
                "The parent observation must contain the same plan and Assignment.",
            )
        observed_execution = observed_plan.get("execution_contract")
        if (
            contract["execution_plan_id"] is not None
            and (
                not isinstance(observed_execution, dict)
                or observed_execution.get("kind")
                != "decision-enactment"
                or observed_execution.get("execution_plan_id")
                != contract["execution_plan_id"]
                or observed_execution.get("decision_bundle_digest")
                != contract["decision_bundle_digest"]
            )
        ):
            raise MaestroError(
                "CODEX_HOST_RUN_EXECUTION_CONFLICT",
                (
                    "The parent observation must bind the exact enacted "
                    "Decision execution wrapper, not only its nested route."
                ),
            )
        dependency_results = {
            item.get("assignment_id"): item
            for item in observed.get("stage_results", [])
            if isinstance(item, dict)
        }
        execution_receipts_required = (
            observed_plan.get("execution_receipts_required") is True
        )
        if contract["assignment_id"] in dependency_results:
            raise MaestroError(
                "CODEX_HOST_ASSIGNMENT_ALREADY_TERMINAL",
                "The Assignment already has a terminal result in the parent observation.",
            )
        unsatisfied = [
            dependency
            for dependency in contract["assignment"]["depends_on"]
            if (
                dependency not in dependency_results
                or dependency_results[dependency].get("status")
                != "completed"
            )
        ]
        if unsatisfied:
            raise MaestroError(
                "CODEX_HOST_DEPENDENCIES_UNSATISFIED",
                "Assignment dependencies are not completed in the parent observation: "
                + ", ".join(unsatisfied),
            )
        mismatched_dependency_evidence = [
            dependency
            for dependency in contract["assignment"]["depends_on"]
            if (
                "assignment-packet:"
                + contract["dependency_packet_digests"].get(
                    dependency,
                    "",
                )
            )
            not in dependency_results[dependency].get("evidence_refs", [])
        ]
        if mismatched_dependency_evidence:
            raise MaestroError(
                "CODEX_HOST_DEPENDENCY_EVIDENCE_MISMATCH",
                "The supplied dependency Packet does not match the Packet "
                "digest recorded for the completed parent stage: "
                + ", ".join(mismatched_dependency_evidence),
            )
        observation = {
            "observation_id": observation_id,
            "status": "already_started",
        }
        dependency_handoff_work_id = (
            _record_dependency_handoff(
                repo,
                observation=observed,
                run_id=run_id,
                downstream_assignment_id=contract["assignment_id"],
                dependency_assignment_ids=list(
                    contract["assignment"]["depends_on"]
                ),
                dependency_packet_digests=contract[
                    "dependency_packet_digests"
                ],
            )
            if contract["assignment"]["depends_on"]
            else None
        )
    else:
        if (
            contract["assignment"] is not None
            and contract["assignment"]["depends_on"]
        ):
            raise MaestroError(
                "CODEX_HOST_DEPENDENCIES_UNSATISFIED",
                "A dependent Assignment requires a parent observation with completed dependencies.",
            )
        observation = start_run_observation(
            repo,
            run_id=run_id,
            task_label=task_label,
            plan_path=plan_path,
            request_key=run_id,
            execution_binding={
                "schema_version": "maestro_execution_binding_v1",
                "mode": "maestro_owned_codex_app_server",
            },
        )
        if observation["status"] != "started":
            raise MaestroError(
                "CODEX_HOST_RUN_CONFLICT",
                "run-id already belongs to an existing observation; pass its "
                "observation ID only when starting a different pending Assignment.",
            )
        execution_receipts_required = contract["assignment_id"] is not None
        dependency_handoff_work_id = None
    deadline = time.monotonic() + float(timeout_seconds)
    server: _AppServer | None = None
    state = {
        "thread_id": None,
        "turn_id": None,
        "turn_start_requested": False,
        "completion": None,
        "reroutes": [],
        "tokens": None,
        "tokens_last": None,
        "token_updates": 0,
        "error_count": 0,
        "last_error": None,
        "interrupt_requested": False,
        "final_message": None,
        "final_message_is_final": False,
        "root_work_id": None,
        "root_work_terminal": False,
        "pending_root_finish": None,
        "work_tracker": None,
        "work_action_sink": None,
        "delegated_work_ids": set(),
        "child_work_starts": {},
        "child_work_runtime": {},
        "child_thread_totals": {},
        "pending_child_finishes": {},
        "scope_shutdown_attempted": False,
        "scope_audit_complete": False,
    }
    try:
        server = _AppServer(host_command, cwd=repo, deadline=deadline)
        initialize_capabilities: dict[str, Any] = {
            "optOutNotificationMethods": (
                _HIGH_VOLUME_NOTIFICATION_OPT_OUTS
            )
        }
        if runtime_binding.get("experimental_api") is True:
            initialize_capabilities["experimentalApi"] = True
        server.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "harness-maestro",
                        "title": "Harness Maestro",
                        "version": __version__,
                    },
                    "capabilities": initialize_capabilities,
                },
            }
        )
        server.response(1)
        server.send({"jsonrpc": "2.0", "method": "initialized"})

        thread_params: dict[str, Any] = {
            "cwd": str(repo),
            "approvalPolicy": "never",
            "sandbox": contract["sandbox"],
            "ephemeral": True,
            "serviceName": "harness-maestro",
        }
        if send_runtime_workspace_roots:
            thread_params["runtimeWorkspaceRoots"] = contract[
                "runtime_workspace_roots"
            ]
        if contract["model"] is not None:
            thread_params["model"] = contract["model"]
        server.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "thread/start",
                "params": thread_params,
            }
        )
        thread_result = server.response(2)
        thread = thread_result.get("thread")
        if (
            not isinstance(thread, dict)
            or not isinstance(thread.get("id"), str)
            or not thread["id"].strip()
        ):
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "thread/start did not return a usable thread ID.",
            )
        state["thread_id"] = thread["id"]
        if (
            contract["scoped_write_roots"]
            and not _same_runtime_workspace_roots(
                thread_result.get("runtimeWorkspaceRoots"),
                contract["runtime_workspace_roots"],
            )
        ):
            raise MaestroError(
                "CODEX_HOST_SCOPED_SANDBOX_MISMATCH",
                (
                    "thread/start did not confirm the exact Decision "
                    "runtimeWorkspaceRoots."
                ),
            )
        provider_reported_model = _bounded_option(
            thread_result.get("model"),
            field="provider-reported-model",
            maximum=128,
        )
        requested_model = contract["model"] or provider_reported_model
        requested_effort = (
            contract["reasoning_effort"]
            or thread_result.get("reasoningEffort")
        )
        requested_model = _bounded_option(
            requested_model,
            field="requested-model",
            maximum=128,
        )
        requested_effort = _bounded_option(
            requested_effort,
            field="requested-reasoning-effort",
            maximum=40,
        )
        if requested_model is None:
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "thread/start did not identify the configured model.",
            )

        turn_params: dict[str, Any] = {
            "threadId": state["thread_id"],
            "input": [{"type": "text", "text": prompt}],
            "cwd": str(repo),
            "approvalPolicy": "never",
            "sandboxPolicy": contract["sandbox_policy"],
        }
        if send_runtime_workspace_roots:
            turn_params["runtimeWorkspaceRoots"] = contract[
                "runtime_workspace_roots"
            ]
        if contract["output_schema"] is not None:
            turn_params["outputSchema"] = contract["output_schema"]
        if contract["model"] is not None:
            turn_params["model"] = contract["model"]
        if contract["reasoning_effort"] is not None:
            turn_params["effort"] = contract["reasoning_effort"]
        state["turn_start_requested"] = True
        server.send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "turn/start",
                "params": turn_params,
            }
        )
        turn_result = server.response(3)
        turn = turn_result.get("turn")
        if (
            not isinstance(turn, dict)
            or not isinstance(turn.get("id"), str)
            or not turn["id"].strip()
        ):
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "turn/start did not return a usable turn ID.",
            )
        state["turn_id"] = turn["id"]
        root_work_id = codex_work_id(
            run_id,
            contract["assignment_id"] or "standalone",
            state["thread_id"],
            state["turn_id"],
            "orchestration",
        )
        turn_started_at = turn.get("startedAt")
        root_event_started_at = (
            codex_event_timestamp(turn_started_at * 1000)
            if (
                isinstance(turn_started_at, int)
                and not isinstance(turn_started_at, bool)
                and turn_started_at >= 0
            )
            else None
        )
        expertise_execution = contract.get("expertise_execution")
        expertise_observation = (
            expertise_execution["observation"]
            if isinstance(expertise_execution, dict)
            else None
        )
        loaded_packs = (
            expertise_observation.get("packs", [])
            if isinstance(expertise_observation, dict)
            else []
        )
        expertise_pack_ids = [
            item["expertise_pack_id"]
            for item in loaded_packs
        ]
        decision_guide_ids = [
            guide_id
            for item in loaded_packs
            for guide_id in item["guide_ids"]
        ]
        root_projection_digest = (
            contract["projection"].get("projection_digest")
            if isinstance(contract.get("projection"), dict)
            else None
        )
        root_allocation = (
            allocation_from_assignment(
                plan_id=contract["plan_id"],
                assignment=contract["assignment"],
                projection_digest=root_projection_digest,
            )
            if (
                isinstance(contract.get("assignment"), dict)
                and isinstance(contract.get("plan_id"), str)
                and isinstance(root_projection_digest, str)
            )
            else None
        )
        record_work_start(
            repo,
            observation_id=observation["observation_id"],
            run_id=run_id,
            work_id=root_work_id,
            assignment_id=contract["assignment_id"],
            kind="orchestration",
            role="Codex 메인 오케스트레이터",
            executor_id="codex-app-server",
            task_summary=task_label,
            read_only=contract["sandbox"] == "read-only",
            source="codex_app_server",
            depends_on_work_ids=(
                [dependency_handoff_work_id]
                if dependency_handoff_work_id is not None
                else []
            ),
            requested_model=requested_model,
            requested_reasoning_effort=requested_effort,
            model_evidence="host_request",
            lens_ids=(
                list(contract["assignment"]["lens_ids"])
                if isinstance(contract.get("assignment"), dict)
                else []
            ),
            expertise_pack_ids=expertise_pack_ids,
            decision_guide_ids=decision_guide_ids,
            expertise_evidence=(
                "host_loaded"
                if expertise_pack_ids
                else "unavailable"
            ),
            allocation=root_allocation,
            expertise_observation=expertise_observation,
            source_binding={
                "interface": "codex_app_server",
                "version": runtime_binding["version"],
                "schema_digest": runtime_binding["schema_digest"],
                "capability": runtime_binding["capability"],
                "correlation_id": codex_work_id(
                    "source",
                    root_work_id,
                    state["thread_id"],
                    state["turn_id"],
                ),
                "event_coverage": "partial_stream",
            },
            event_started_at=root_event_started_at,
        )
        state["root_work_id"] = root_work_id
        state["work_tracker"] = CodexCollaborationTracker(
            root_work_id=root_work_id,
            root_thread_id=state["thread_id"],
            root_turn_id=state["turn_id"],
            assignment_id=contract["assignment_id"],
            read_only=contract["sandbox"] == "read-only",
            may_spawn=(
                contract["assignment"]["may_spawn"]
                if contract["assignment"] is not None
                else True
            ),
            max_children=(
                contract["assignment"]["max_children"]
                if contract["assignment"] is not None
                else MAX_COLLAB_WORK
            ),
            source_version=runtime_binding["version"],
            schema_digest=runtime_binding["schema_digest"],
            source_capability=runtime_binding["capability"],
        )
        def record_action(action: dict[str, Any]) -> None:
            if (
                action["action"] == "start"
                and action["kind"] == "delegation"
            ):
                assignment = contract["assignment"]
                if (
                    assignment is not None
                    and (
                        not assignment["may_spawn"]
                        or len(state["delegated_work_ids"])
                        >= assignment["max_children"]
                    )
                ):
                    raise MaestroError(
                        "CODEX_HOST_DELEGATION_FORBIDDEN",
                        "The observed Assignment attempted delegation outside "
                        "its validated may_spawn/max_children contract.",
                    )
                state["delegated_work_ids"].add(action["work_id"])
                state["child_work_starts"][action["work_id"]] = action
            if (
                action["action"] == "finish"
                and action["work_id"] in state["delegated_work_ids"]
            ):
                pending = state["pending_child_finishes"].get(
                    action["work_id"]
                )
                if pending is not None and pending != action:
                    raise MaestroError(
                        "CODEX_HOST_PROTOCOL_INVALID",
                        "A delegated work attempt received conflicting terminal states.",
                    )
                state["pending_child_finishes"][action["work_id"]] = action
                return
            if (
                action["action"] == "finish"
                and action["work_id"] == root_work_id
                and contract["assignment_id"] is not None
            ):
                pending_root = state.get("pending_root_finish")
                if pending_root is not None and pending_root != action:
                    raise MaestroError(
                        "CODEX_HOST_PROTOCOL_INVALID",
                        "The Assignment root received conflicting terminal states.",
                    )
                state["pending_root_finish"] = action
                return
            recorded_action = action
            if (
                action["action"] == "finish"
                and action["work_id"] == root_work_id
                and root_event_started_at is None
            ):
                recorded_action = {
                    **action,
                    "ended_at": None,
                    "duration_ms": None,
                }
            if (
                action["action"] == "finish"
                and state["completion"] is not None
                and (
                    state["error_count"]
                    or state["interrupt_requested"]
                )
            ):
                recorded_action = {
                    **recorded_action,
                    "diagnostics": {
                        "interrupt_requested": state[
                            "interrupt_requested"
                        ],
                        "error_count": min(state["error_count"], 20),
                        "last_error": state["last_error"],
                        "followup_reason": None,
                    },
                }
            if (
                action["action"] == "finish"
                and action["work_id"] == root_work_id
                and state["completion"] is not None
            ):
                complete_coverage = (
                    runtime_binding["capability"] == "full_stream"
                    and runtime_binding["version"] is not None
                    and runtime_binding["schema_digest"] is not None
                )
                complete_model_coverage = (
                    complete_coverage and requested_model is not None
                )
                recorded_action = {
                    **recorded_action,
                    "applied_model": (
                        (
                            state["reroutes"][-1]["to_model"]
                            if state["reroutes"]
                            else requested_model
                        )
                        if complete_model_coverage
                        else None
                    ),
                    "model_evidence": (
                        "complete"
                        if complete_model_coverage
                        else (
                            "host_request"
                            if requested_model is not None
                            else "unavailable"
                        )
                    ),
                    "source_binding": {
                        "interface": "codex_app_server",
                        "version": runtime_binding["version"],
                        "schema_digest": runtime_binding["schema_digest"],
                        "capability": runtime_binding["capability"],
                        "correlation_id": codex_work_id(
                            "source",
                            root_work_id,
                            str(state["thread_id"]),
                            str(state["turn_id"]),
                        ),
                        "event_coverage": (
                            "complete_stream"
                            if complete_coverage
                            else "partial_stream"
                        ),
                    },
                    "model_observation": {
                        "observed_model": None,
                        "coverage": (
                            "complete_stream"
                            if complete_model_coverage
                            else (
                                "request_only"
                                if requested_model is not None
                                else "unavailable"
                            )
                        ),
                        "reroutes": (
                            list(state["reroutes"])
                            if complete_model_coverage
                            else []
                        ),
                    },
                    "usage": {
                        "last": (
                            state["tokens_last"]
                            if complete_coverage
                            else None
                        ),
                        "total": (
                            state["tokens"]
                            if complete_coverage
                            else None
                        ),
                        "scope": (
                            "work_turn"
                            if (
                                complete_coverage
                                and state["tokens"] is not None
                            )
                            else "unavailable"
                        ),
                        "attribution": (
                            "direct"
                            if (
                                complete_coverage
                                and state["tokens"] is not None
                            )
                            else "unavailable"
                        ),
                        "timing_coverage": (
                            "host_event"
                            if complete_coverage
                            else "partial"
                        ),
                        "cost": None,
                    },
                    "outcome": {
                        "finding_summary": None,
                        "conclusion": action["result_summary"],
                        "decision": (
                            "작업을 종료합니다."
                            if action["status"] == "completed"
                            else (
                                "실행 실패로 작업을 종료합니다."
                                if action["status"] == "failed"
                                else "중단된 상태로 작업을 종료합니다."
                            )
                        ),
                        "next_action": (
                            "finish"
                            if action["status"] in {
                                "completed",
                                "interrupted",
                            }
                            else "blocked"
                        ),
                        "consumed_work_ids": [],
                        "handoff": None,
                        "artifacts": [],
                        "verification": None,
                    },
                    "diagnostics": {
                        "interrupt_requested": state[
                            "interrupt_requested"
                        ],
                        "error_count": min(state["error_count"], 20),
                        "last_error": state["last_error"],
                        "followup_reason": None,
                    },
                }
            _record_codex_work_action(
                repo,
                observation_id=observation["observation_id"],
                run_id=run_id,
                action=recorded_action,
            )
            if (
                action["action"] == "finish"
                and action["work_id"] == root_work_id
            ):
                state["root_work_terminal"] = True

        def flush_child_finishes() -> None:
            pending = state["pending_child_finishes"]
            for work_id, action in list(pending.items()):
                recorded_action = _enrich_child_finish_action(
                    action,
                    start_action=state["child_work_starts"][work_id],
                    runtime=state["child_work_runtime"].get(work_id),
                )
                _record_codex_work_action(
                    repo,
                    observation_id=observation["observation_id"],
                    run_id=run_id,
                    action=recorded_action,
                )
                del pending[work_id]

        state["work_action_sink"] = record_action
        pending_notifications = server.notifications
        server.notifications = []
        for notification in pending_notifications:
            _process_notification(notification, state)

        while state["completion"] is None:
            value = server.next_message()
            assert value is not None
            if isinstance(value.get("method"), str):
                _process_notification(value, state)

        drain_deadline = min(
            deadline,
            time.monotonic() + POST_COMPLETION_TOKEN_WAIT_SECONDS,
        )
        while time.monotonic() < drain_deadline:
            value = server.next_message(
                idle_limit=max(
                    0.001,
                    drain_deadline - time.monotonic(),
                ),
                idle_ok=True,
            )
            if value is None:
                break
            if isinstance(value.get("method"), str):
                _process_notification(value, state)

        applied_model = _validate_managed_model_reroutes(
            contract["model_execution_contract"],
            requested_model=requested_model,
            provider_reported_model=provider_reported_model,
            reroutes=state["reroutes"],
        )
        model_evidence = (
            "complete"
            if applied_model is not None
            else "request_only"
        )
        completion = state["completion"]
        assert isinstance(completion, dict)
        _capture_terminal_message(completion, state)
        _capture_terminal_collaboration(completion, state)
        flush_child_finishes()
        duration = completion.get("durationMs")
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration < 0
        ):
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_INVALID",
                "turn/completed did not provide a valid durationMs.",
            )
        completed_at = completion.get("completedAt")
        root_event_ended_at = (
            codex_event_timestamp(completed_at * 1000)
            if (
                isinstance(completed_at, int)
                and not isinstance(completed_at, bool)
                and completed_at >= 0
            )
            else None
        )
        tracker = state["work_tracker"]
        assert isinstance(tracker, CodexCollaborationTracker)
        action_sink = state["work_action_sink"]
        assert callable(action_sink)
        terminal_actions = tracker.finish_turn(
            status=completion["status"],
            observed_at=(
                root_event_ended_at
                or codex_event_timestamp(int(time.time() * 1000))
            ),
            duration_ms=duration,
            evidence_identity=(
                str(state["thread_id"]),
                str(state["turn_id"]),
                "turn-terminal",
            ),
        )
        for action in terminal_actions:
            action_sink(action)
        if tracker.running_work_ids:
            raise MaestroError(
                "CODEX_HOST_WORK_INCOMPLETE",
                "The parent turn ended before every observed delegated agent reached an explicit terminal state.",
            )
        if scope_snapshot is not None:
            state["scope_shutdown_attempted"] = True
            _shutdown_and_audit_scoped_host(
                server,
                repo,
                state=state,
                before=scope_snapshot,
                allowed_roots=contract["runtime_workspace_roots"],
            )
            state["scope_audit_complete"] = True
        effect_changed = (
            _repository_snapshot_changed(
                effect_snapshot,
                _repository_effect_snapshot(repo),
            )
            if effect_snapshot is not None
            else False
        )
        telemetry = {
            "schema_version": "maestro_host_observation_v2",
            "source": "codex-app-server",
            "quality": "host_reported",
            "correlation_id": f"{state['thread_id']}:{state['turn_id']}",
            "requested_model": requested_model,
            "requested_reasoning_effort": requested_effort,
            "reasoning_effort_evidence": (
                "host_request" if requested_effort is not None else "unavailable"
            ),
            "applied_model": applied_model,
            "model_event_evidence": model_evidence,
            "reroutes": (
                state["reroutes"]
                if applied_model is not None
                else []
            ),
            "tokens": state["tokens"],
        }
        stage_record = None
        packet_validation = None
        packet_digest = None
        verification_assessment = None
        execution_unit_receipt = None
        packet_error: MaestroError | None = None
        packet: dict[str, Any] | None = None
        evaluation_refs: list[str] = []
        result_status = completion["status"]
        if contract["assignment_id"] is not None:
            projection_digest = contract["projection"].get(
                "projection_digest"
            )
            if not isinstance(projection_digest, str):
                raise MaestroError(
                    "CODEX_HOST_PROJECTION_DIGEST_INVALID",
                    "The reconstructed Assignment input has no content-addressed projection digest.",
                )
            evidence_refs = [
                (
                    "codex-app-server:"
                    f"{state['thread_id']}:{state['turn_id']}"
                ),
                f"assignment-input:{projection_digest}",
            ]
            load_evidence_ref = (
                contract["expertise_execution"].get("evidence_ref")
                if isinstance(
                    contract.get("expertise_execution"),
                    dict,
                )
                else None
            )
            if completion["status"] == "completed":
                assert isinstance(contract["plan"], dict)
                assert isinstance(contract["projection"], dict)
                try:
                    packet, packet_validation, result_status = (
                        _validated_assignment_result(
                            state["final_message"],
                            final_message_is_final=state[
                                "final_message_is_final"
                            ],
                            plan=contract["plan"],
                            assignment_id=contract["assignment_id"],
                            projection=contract["projection"],
                            repo=repo,
                            research_bundle=contract["research_bundle"],
                            require_expertise_dispositions=(
                                load_evidence_ref is not None
                            ),
                        )
                    )
                except MaestroError as exc:
                    packet_error = exc
                    result_status = "failed"
                else:
                    packet_digest = packet_validation["packet_digest"]
                    assert isinstance(packet_digest, str)
                    verification_assessment = packet_validation.get(
                        "verification_assessment"
                    )
                    evidence_refs.append(f"assignment-packet:{packet_digest}")
                    evaluation_refs = projected_evaluation_evidence_refs(
                        contract["projection"]
                    )
                    if len(evaluation_refs) > 3:
                        packet_error = MaestroError(
                            "CODEX_HOST_EVALUATION_EVIDENCE_INVALID",
                            "A Host-observed evaluation may bind at most three exact lifecycle evidence references.",
                        )
                        result_status = "failed"
            if result_status == "completed":
                execution_unit = contract["execution_unit"]
                if not isinstance(execution_unit, dict):
                    raise MaestroError(
                        "CODEX_HOST_EXECUTION_UNIT_INVALID",
                        "The validated Assignment did not retain its exact common ExecutionUnit.",
                    )
                unit_by_local_id = {
                    unit.get("local_unit_id"): unit
                    for unit in contract["execution_units"]
                    if isinstance(unit, dict)
                }
                dependency_units = [
                    unit_by_local_id[dependency_id]
                    for dependency_id in contract["assignment"].get(
                        "depends_on",
                        [],
                    )
                    if dependency_id in unit_by_local_id
                ]
                dependency_receipts = [
                    dependency_results[dependency_id][
                        "execution_unit_receipt"
                    ]
                    for dependency_id in contract["assignment"].get(
                        "depends_on",
                        [],
                    )
                    if isinstance(
                        dependency_results.get(dependency_id, {}).get(
                            "execution_unit_receipt"
                        ),
                        dict,
                    )
                ]
                required_dependency_receipts = sum(
                    1
                    for unit in dependency_units
                    if unit.get("host_executable") is True
                )
                can_issue_receipt = (
                    len(dependency_receipts)
                    == required_dependency_receipts
                )
                if execution_receipts_required and not can_issue_receipt:
                    raise MaestroError(
                        "CODEX_HOST_DEPENDENCY_RECEIPT_REQUIRED",
                        "The owned Codex stage cannot close without every exact Host dependency receipt.",
                    )
                if execution_receipts_required and can_issue_receipt:
                    attempt = build_execution_attempt(
                        attempt=1,
                        followup_of_attempt=None,
                        route_kind="primary",
                        requested_class=execution_unit[
                            "model_route"
                        ]["selected_class"],
                        requested_model=requested_model,
                        requested_reasoning_effort=requested_effort,
                        applied_model=applied_model,
                        applied_reasoning_effort=None,
                        reasoning_effort_evidence="requested-only",
                        status="completed",
                        transition_trigger=None,
                        provider_reroutes=state["reroutes"],
                        thread_id=state["thread_id"],
                        turn_id=state["turn_id"],
                        duration_ms=duration,
                        tokens=state["tokens"],
                        writes_observed=effect_changed,
                    )
                    execution_unit_receipt = (
                        build_execution_unit_receipt(
                            unit=execution_unit,
                            input_digest=projection_digest,
                            dependency_units=dependency_units,
                            dependency_receipts=dependency_receipts,
                            attempts=[attempt],
                            output_packet_digest=packet_digest,
                            verification_assessment_id=(
                                verification_assessment.get(
                                    "assessment_id"
                                )
                                if isinstance(
                                    verification_assessment,
                                    dict,
                                )
                                else None
                            ),
                            terminal_work_id=root_work_id,
                            terminal_status="completed",
                            effect_state=(
                                "verified-writes"
                                if effect_changed
                                else "no-writes"
                            ),
                            producer={
                                "interface": "codex_app_server",
                                "framework_version": __version__,
                                "runtime_schema_digest": runtime_binding[
                                    "schema_digest"
                                ],
                                "run_id": run_id,
                                "observation_id": observation[
                                    "observation_id"
                                ],
                            },
                        )
                    )
            pending_root_finish = state.get("pending_root_finish")
            if not isinstance(pending_root_finish, dict):
                raise MaestroError(
                    "CODEX_HOST_WORK_INCOMPLETE",
                    "The managed Assignment turn did not produce a root terminal action.",
                )
            if packet is not None and packet_digest is not None:
                root_outcome = outcome_from_assignment_packet(packet)
                root_expertise, root_expertise_evidence = (
                    application_from_packet(
                        contract["expertise_execution"]["observation"],
                        packet,
                        packet_evidence_ref=(
                            f"assignment-packet:{packet_digest}"
                        ),
                    )
                )
            else:
                root_outcome = {
                    "finding_summary": None,
                    "conclusion": (
                        "The managed Assignment result failed closed before "
                        "a valid terminal Packet was accepted."
                        if packet_error is not None
                        else pending_root_finish["result_summary"]
                    ),
                    "decision": (
                        "Reject the terminal result and preserve failure evidence."
                        if packet_error is not None
                        else "Preserve the Host terminal status."
                    ),
                    "next_action": (
                        "blocked"
                        if result_status in {"failed", "blocked"}
                        else "finish"
                    ),
                    "consumed_work_ids": [],
                    "handoff": None,
                    "artifacts": [],
                    "verification": None,
                }
                root_expertise = contract[
                    "expertise_execution"
                ]["observation"]
                root_expertise_evidence = (
                    "host_loaded"
                    if root_expertise["load"]["status"] == "host_loaded"
                    else "unavailable"
                )
            diagnostic_count = min(
                state["error_count"] + (1 if packet_error else 0),
                20,
            )
            diagnostic_error = (
                f"{packet_error.code}: Assignment Packet validation failed."
                if packet_error is not None
                else state["last_error"]
            )
            if diagnostic_count and diagnostic_error is None:
                diagnostic_error = "Codex Host reported an execution error."
            managed_root_action = _managed_root_finish_action(
                pending_root_finish,
                status=result_status,
                result_summary=root_outcome["conclusion"],
                evidence_refs=[
                    *evidence_refs,
                    *(
                        [load_evidence_ref]
                        if isinstance(load_evidence_ref, str)
                        else []
                    ),
                ],
                runtime_binding=runtime_binding,
                requested_model=requested_model,
                applied_model=applied_model,
                reroutes=list(state["reroutes"]),
                tokens_last=state["tokens_last"],
                tokens_total=state["tokens"],
                outcome=root_outcome,
                diagnostics={
                    "interrupt_requested": state[
                        "interrupt_requested"
                    ],
                    "error_count": diagnostic_count,
                    "last_error": diagnostic_error,
                    "followup_reason": None,
                },
                expertise_evidence=root_expertise_evidence,
                expertise_observation=root_expertise,
                preserve_host_timing=root_event_started_at is not None,
                correlation_id=codex_work_id(
                    "source",
                    root_work_id,
                    str(state["thread_id"]),
                    str(state["turn_id"]),
                ),
            )
            _record_codex_work_action(
                repo,
                observation_id=observation["observation_id"],
                run_id=run_id,
                action=managed_root_action,
            )
            state["root_work_terminal"] = True
            if (
                result_status != "completed"
                and contract["assignment"]["mutation_owner"]
            ):
                evidence_refs.append("effect-state:unknown")
            stage_record = record_stage_observation(
                repo,
                observation_id=observation["observation_id"],
                run_id=run_id,
                assignment_id=contract["assignment_id"],
                status=result_status,
                evidence_source="codex_app_server",
                evidence_refs=[*evidence_refs, *evaluation_refs],
                requested_model=requested_model,
                requested_reasoning_effort=requested_effort,
                actual_model=applied_model,
                model_route_id=contract["model_route_id"],
                execution_unit_id=contract["execution_unit_id"],
                model_evidence=model_evidence,
                reroutes=state["reroutes"],
                duration_ms=duration,
                tokens=state["tokens"],
                verification_assessment=(
                    verification_assessment
                    if isinstance(verification_assessment, dict)
                    else None
                ),
                execution_unit_receipt=execution_unit_receipt,
            )
            if packet_error is not None:
                raise packet_error
        else:
            recorded = record_host_observation(
                repo,
                observation_id=observation["observation_id"],
                run_id=run_id,
                source="codex-app-server",
                quality="host_reported",
                correlation_id=f"{state['thread_id']}:{state['turn_id']}",
                requested_model=requested_model,
                requested_reasoning_effort=requested_effort,
                applied_model=applied_model,
                model_event_evidence=model_evidence,
                reroutes=(
                    state["reroutes"]
                    if applied_model is not None
                    else []
                ),
                tokens=state["tokens"],
                trusted_event_stream=True,
            )
            telemetry = recorded["telemetry"]
            complete_run_observation(
                repo,
                observation_id=observation["observation_id"],
                run_id=run_id,
                duration_ms=duration,
            )
        final_message = state["final_message"]
        truncated = (
            isinstance(final_message, str)
            and len(final_message) > MAX_FINAL_MESSAGE_CHARS
        )
        if truncated:
            final_message = final_message[:MAX_FINAL_MESSAGE_CHARS]
        return {
            "schema_version": HOST_RUN_VERSION,
            "command": "host-codex",
            "status": result_status,
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation["observation_id"],
            "assignment_id": contract["assignment_id"],
            "sandbox": contract["sandbox"],
            "thread_id": state["thread_id"],
            "turn_id": state["turn_id"],
            "duration_ms": duration,
            "protocol_messages_seen": server.messages,
            "protocol_bytes_seen": server.bytes,
            "filtered_notifications": server.filtered_notifications,
            "requested_model": requested_model,
            "requested_reasoning_effort": requested_effort,
            "applied_model": applied_model,
            "model_route_id": contract["model_route_id"],
            "execution_unit_id": contract["execution_unit_id"],
            "reroutes": state["reroutes"],
            "tokens": state["tokens"],
            "token_measurement": (
                "host_event"
                if state["tokens"] is not None
                else "unavailable"
            ),
            "final_message": final_message,
            "final_message_truncated": truncated,
            "host_observation": telemetry,
            "stage_record": stage_record,
            "packet_digest": packet_digest,
            "packet_validation": packet_validation,
            "execution_unit_receipt": execution_unit_receipt,
            "output_schema_applied": (
                contract["output_schema"] is not None
            ),
            "work_capture": {
                "root_work_id": root_work_id,
                "delegation_count": tracker.observed_work_count,
                "terminal_delegation_count": tracker.terminal_work_count,
                "decision_count": tracker.decision_work_count,
                "incomplete_delegation_count": len(
                    tracker.running_work_ids
                ),
            },
            "writes_performed": True,
        }
    except Exception as exc:
        if (
            server is not None
            and scope_snapshot is not None
            and not state["scope_shutdown_attempted"]
        ):
            state["scope_shutdown_attempted"] = True
            try:
                _shutdown_and_audit_scoped_host(
                    server,
                    repo,
                    state=state,
                    before=scope_snapshot,
                    allowed_roots=contract["runtime_workspace_roots"],
                )
            except MaestroError as scope_exc:
                exc = scope_exc
            else:
                state["scope_audit_complete"] = True
        elif server is not None:
            server.close()
        error_code = (
            exc.code
            if isinstance(exc, MaestroError)
            else type(exc).__name__
        )
        root_work_id = state.get("root_work_id")
        if (
            isinstance(root_work_id, str)
            and not state.get("root_work_terminal")
        ):
            try:
                record_work_finish(
                    repo,
                    observation_id=observation["observation_id"],
                    run_id=run_id,
                    work_id=root_work_id,
                    status="failed",
                    result_summary="Codex Host 실행이 완료 전에 실패했습니다.",
                    evidence_refs=[f"codex-host-error:{error_code}"],
                )
                state["root_work_terminal"] = True
            except MaestroError:
                pass
        if contract["assignment_id"] is not None:
            try:
                observed = observation_receipt_fields(
                    repo,
                    observation_id=observation["observation_id"],
                    run_id=run_id,
                )
                terminal_ids = {
                    item.get("assignment_id")
                    for item in observed.get("stage_results", [])
                    if isinstance(item, dict)
                }
                if contract["assignment_id"] not in terminal_ids:
                    failure_evidence = [
                        f"codex-host-error:{error_code}"[:240]
                    ]
                    if contract["assignment"]["mutation_owner"]:
                        failure_evidence.append("effect-state:unknown")
                    record_stage_observation(
                        repo,
                        observation_id=observation["observation_id"],
                        run_id=run_id,
                        assignment_id=contract["assignment_id"],
                        status="failed",
                        evidence_source="codex_app_server",
                        evidence_refs=failure_evidence,
                        model_route_id=contract["model_route_id"],
                        execution_unit_id=contract["execution_unit_id"],
                    )
            except MaestroError as terminal_exc:
                raise MaestroError(
                    "CODEX_HOST_TERMINAL_EVIDENCE_FAILED",
                    "Codex Host failed and could not freeze a terminal "
                    f"Assignment result: {terminal_exc.code}.",
                ) from exc
        raise exc
    finally:
        if server is not None:
            server.close()


def run_codex_host(
    repo_path: str | Path,
    *,
    run_id: str,
    task_label: str,
    prompt_file: str | Path | None = None,
    plan_path: str | Path | None = None,
    assignment_id: str | None = None,
    projection_path: str | Path | None = None,
    baseline_path: str | Path | None = None,
    document_paths: Sequence[str] = (),
    dependency_packet_paths: Sequence[str | Path] = (),
    dependency_projection_paths: Sequence[str | Path] = (),
    research_evidence_path: str | Path | None = None,
    coverage_path: str | Path | None = None,
    coverage_admission_path: str | Path | None = None,
    coverage_projection_path: str | Path | None = None,
    expertise_work_plan_path: str | Path | None = None,
    expertise_closure_path: str | Path | None = None,
    design_decision_path: str | Path | None = None,
    expertise_research_evidence_paths: Sequence[str | Path] = (),
    observation_id: str | None = None,
    sandbox: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    command: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Serialize each Host turn before validating and launching it."""

    repo = ensure_repo(repo_path)
    with _host_assignment_lease(
        repo,
        run_id=run_id,
        assignment_id=assignment_id,
    ):
        return _run_codex_host_locked(
            repo,
            run_id=run_id,
            task_label=task_label,
            prompt_file=prompt_file,
            plan_path=plan_path,
            assignment_id=assignment_id,
            projection_path=projection_path,
            baseline_path=baseline_path,
            document_paths=document_paths,
            dependency_packet_paths=dependency_packet_paths,
            dependency_projection_paths=dependency_projection_paths,
            research_evidence_path=research_evidence_path,
            coverage_path=coverage_path,
            coverage_admission_path=coverage_admission_path,
            coverage_projection_path=coverage_projection_path,
            expertise_work_plan_path=expertise_work_plan_path,
            expertise_closure_path=expertise_closure_path,
            design_decision_path=design_decision_path,
            expertise_research_evidence_paths=expertise_research_evidence_paths,
            observation_id=observation_id,
            sandbox=sandbox,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            command=command,
        )
