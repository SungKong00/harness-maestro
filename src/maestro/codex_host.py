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
from .errors import MaestroError
from .observations import (
    MAX_MODEL_REROUTES,
    complete_run_observation,
    observation_receipt_fields,
    record_host_observation,
    record_stage_observation,
    record_work_finish,
    record_work_start,
    start_run_observation,
)
from .planning import validate_route_v2
from .util import (
    canonical_json,
    ensure_repo,
    read_json,
    safe_target,
    sha256_text,
)
from .work.codex import (
    CodexCollaborationTracker,
    codex_event_timestamp,
    codex_work_id,
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
_SANDBOXES = {"read-only", "workspace-write"}
_TERMINAL_STATUSES = {"completed", "interrupted", "failed"}
_RELEVANT_NOTIFICATIONS = {
    "error",
    "item/started",
    "item/completed",
    "model/rerouted",
    "thread/tokenUsage/updated",
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
) -> str:
    prompt = (
        "Execute only the following validated Maestro AssignmentInput. "
        "Treat its task, side-effect, context, evidence, and Packet contracts "
        "as closed. Inspect only referenced repository artifacts. Your final "
        "answer is machine-validated: return exactly one JSON object matching "
        "the final-answer JSON Schema below, with no Markdown fence, preface, "
        "or trailing commentary.\n"
        "Final-answer JSON Schema:\n"
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
    sandbox: str | None,
    model: str | None,
    reasoning_effort: str | None,
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
    projection: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    research_bundle: dict[str, Any] | None = None
    dependency_packet_digests: dict[str, str] = {}
    plan_id: str | None = None
    if research_evidence_path is not None:
        research_bundle = read_json(
            Path(research_evidence_path).expanduser().resolve()
        )
    if plan_path is not None:
        plan = read_json(Path(plan_path).expanduser().resolve())
        validation = validate_route_v2(
            plan,
            repo_path=repo,
            research_bundle=research_bundle,
        )
        if validation["status"] != "PASS":
            first = validation["issues"][0]
            raise MaestroError(
                "CODEX_HOST_PLAN_INVALID",
                f"{first['code']}: {first['message']}",
            )
        if validation["execution_status"] != "READY":
            raise MaestroError(
                "CODEX_HOST_PLAN_NOT_READY",
                "The validated plan still requires bound research evidence "
                "and cannot start Host execution.",
            )
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
    else:
        if projection_path is None or baseline_path is None:
            raise MaestroError(
                "CODEX_HOST_ASSIGNMENT_INPUT_REQUIRED",
                "An Assignment requires its exact --projection and authoritative --baseline.",
            )
        assert plan is not None
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
            plan,
            assignment_id,
            baseline,
            document_paths=document_paths,
            dependency_packets=dependency_packets,
            dependency_projections=dependency_projections,
            research_bundle=research_bundle,
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
        output_schema = assignment_output_schema(projection)
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
        route = assignment["model_route"]
        planned_model = route.get("selected_model")
        planned_effort = route.get("reasoning_effort")
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
    if effective_sandbox == "read-only":
        sandbox_policy = {
            "type": "readOnly",
            "networkAccess": False,
        }
    else:
        sandbox_policy = {
            "type": "workspaceWrite",
            "writableRoots": [str(repo)],
            "networkAccess": False,
            "excludeSlashTmp": True,
            "excludeTmpdirEnvVar": True,
        }
    return {
        "assignment_id": assignment_id,
        "plan_id": plan_id,
        "sandbox": effective_sandbox,
        "sandbox_policy": sandbox_policy,
        "model": effective_model,
        "reasoning_effort": effective_effort,
        "assignment": assignment,
        "plan": plan,
        "projection": projection,
        "output_schema": output_schema,
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

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=PROCESS_EXIT_GRACE_SECONDS)
        except (subprocess.TimeoutExpired, OSError):
            pass
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        elif process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        if process.poll() is None:
            try:
                process.wait(timeout=PROCESS_EXIT_GRACE_SECONDS)
            except (subprocess.TimeoutExpired, OSError):
                pass
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        elif process.poll() is None:
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
    if params.get("threadId") != state["thread_id"]:
        return
    if method == "error":
        if params.get("turnId") not in {None, state["turn_id"]}:
            return
        error = params.get("error")
        code = (
            error.get("code")
            if isinstance(error, dict)
            and isinstance(error.get("code"), (str, int))
            else "unclassified"
        )
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
            source_binding=action.get("source_binding"),
            model_observation=action.get("model_observation"),
            usage=action.get("usage"),
            outcome=action.get("outcome"),
            diagnostics=action.get("diagnostics"),
            event_ended_at=action["ended_at"],
            event_duration_ms=action.get("duration_ms"),
        )
        return
    raise MaestroError(
        "CODEX_WORK_EVENT_INVALID",
        "Codex collaboration adapter returned an unsupported work action.",
    )


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


@lru_cache(maxsize=4)
def _codex_runtime_binding(executable: str) -> dict[str, Any]:
    """Bind the installed Codex version and generated stable schema surface."""

    if Path(executable).name != "codex":
        return {
            "version": None,
            "schema_digest": None,
            "capability": "lifecycle_only",
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
            schema_manifest = [
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_text(path.read_text(encoding="utf-8")),
                }
                for path in files
            ]
        return {
            "version": version,
            "schema_digest": sha256_text(canonical_json(schema_manifest)),
            "capability": "full_stream",
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
        }


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
        )
    else:
        if prompt_file is None:
            raise MaestroError(
                "CODEX_HOST_PROMPT_REQUIRED",
                "Standalone Host execution requires --prompt-file.",
            )
        prompt = _bounded_text_file(prompt_file)
    observation: dict[str, Any] | None
    if observation_id is not None:
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
        dependency_results = {
            item.get("assignment_id"): item
            for item in observed.get("stage_results", [])
            if isinstance(item, dict)
        }
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
    deadline = time.monotonic() + float(timeout_seconds)
    host_command = _command(command)
    runtime_binding = _codex_runtime_binding(host_command[0])
    server = _AppServer(host_command, cwd=repo, deadline=deadline)
    state = {
        "thread_id": None,
        "turn_id": None,
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
        "work_tracker": None,
        "work_action_sink": None,
    }
    try:
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
                    "capabilities": {
                        "optOutNotificationMethods": (
                            _HIGH_VOLUME_NOTIFICATION_OPT_OUTS
                        )
                    },
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
        requested_model = contract["model"] or thread_result.get("model")
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
        if contract["output_schema"] is not None:
            turn_params["outputSchema"] = contract["output_schema"]
        if contract["model"] is not None:
            turn_params["model"] = contract["model"]
        if contract["reasoning_effort"] is not None:
            turn_params["effort"] = contract["reasoning_effort"]
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
            requested_model=requested_model,
            requested_reasoning_effort=requested_effort,
            model_evidence="host_request",
            source_binding={
                "interface": "codex_app_server",
                "version": runtime_binding["version"],
                "schema_digest": runtime_binding["schema_digest"],
                "capability": runtime_binding["capability"],
                "correlation_id": codex_work_id(
                    "source",
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
            source_version=runtime_binding["version"],
            schema_digest=runtime_binding["schema_digest"],
            source_capability=runtime_binding["capability"],
        )
        def record_action(action: dict[str, Any]) -> None:
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

        token_updates_at_completion = state["token_updates"]
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
                if state["token_updates"] > token_updates_at_completion:
                    break

        applied_model = (
            state["reroutes"][-1]["to_model"]
            if state["reroutes"]
            else requested_model
        )
        completion = state["completion"]
        assert isinstance(completion, dict)
        _capture_terminal_message(completion, state)
        _capture_terminal_collaboration(completion, state)
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
            "model_event_evidence": "complete",
            "reroutes": state["reroutes"],
            "tokens": state["tokens"],
        }
        stage_record = None
        packet_validation = None
        packet_digest = None
        packet_error: MaestroError | None = None
        result_status = completion["status"]
        if contract["assignment_id"] is not None:
            evidence_refs = [
                (
                    "codex-app-server:"
                    f"{state['thread_id']}:{state['turn_id']}"
                )
            ]
            if completion["status"] == "completed":
                assert isinstance(contract["plan"], dict)
                assert isinstance(contract["projection"], dict)
                try:
                    _, packet_validation, result_status = (
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
                        )
                    )
                except MaestroError as exc:
                    packet_error = exc
                    result_status = "failed"
                else:
                    packet_digest = packet_validation["packet_digest"]
                    assert isinstance(packet_digest, str)
                    evidence_refs.append(f"assignment-packet:{packet_digest}")
            stage_record = record_stage_observation(
                repo,
                observation_id=observation["observation_id"],
                run_id=run_id,
                assignment_id=contract["assignment_id"],
                status=result_status,
                evidence_source="codex_app_server",
                evidence_refs=evidence_refs,
                requested_model=requested_model,
                requested_reasoning_effort=requested_effort,
                actual_model=applied_model,
                model_evidence="complete",
                reroutes=state["reroutes"],
                duration_ms=duration,
                tokens=state["tokens"],
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
                model_event_evidence="complete",
                reroutes=state["reroutes"],
                tokens=state["tokens"],
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
    except MaestroError as exc:
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
                    evidence_refs=[f"codex-host-error:{exc.code}"],
                )
                state["root_work_terminal"] = True
            except MaestroError:
                pass
        raise
    finally:
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
            observation_id=observation_id,
            sandbox=sandbox,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            command=command,
        )
