from __future__ import annotations

import json
import os
import queue
import signal
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Sequence, TextIO

from . import __version__
from .errors import MaestroError
from .observations import (
    MAX_APP_SERVER_TRACE_BYTES,
    MAX_APP_SERVER_TRACE_MESSAGES,
    MAX_MODEL_REROUTES,
    complete_run_observation,
    record_host_observation,
    start_run_observation,
)
from .planning import validate_route_v2
from .util import ensure_repo, read_json

HOST_RUN_VERSION = "maestro_codex_host_run_v1"
MAX_PROMPT_BYTES = 256_000
MAX_PROTOCOL_LINE_BYTES = 1_000_000
MAX_FINAL_MESSAGE_CHARS = 12_000
MAX_TIMEOUT_SECONDS = 7_200.0
DEFAULT_TIMEOUT_SECONDS = 1_800.0
POST_COMPLETION_DRAIN_SECONDS = 0.35
PROCESS_EXIT_GRACE_SECONDS = 1.0
_SANDBOXES = {"read-only", "workspace-write"}
_TERMINAL_STATUSES = {"completed", "interrupted", "failed"}
_RELEVANT_NOTIFICATIONS = {
    "item/completed",
    "model/rerouted",
    "thread/tokenUsage/updated",
    "turn/completed",
}


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

    assignment: dict[str, Any] | None = None
    if plan_path is not None:
        plan = read_json(Path(plan_path).expanduser().resolve())
        validation = validate_route_v2(plan, repo_path=repo)
        if validation["status"] != "PASS":
            first = validation["issues"][0]
            raise MaestroError(
                "CODEX_HOST_PLAN_INVALID",
                f"{first['code']}: {first['message']}",
            )
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
        if requested_sandbox is None:
            raise MaestroError(
                "CODEX_HOST_SANDBOX_REQUIRED",
                "Use --sandbox explicitly when no Assignment contract is supplied.",
            )
        effective_sandbox = requested_sandbox
        effective_model = requested_model
        effective_effort = requested_effort
    else:
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
        "sandbox": effective_sandbox,
        "sandbox_policy": sandbox_policy,
        "model": effective_model,
        "reasoning_effort": effective_effort,
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
        self.pending: dict[tuple[str, str], dict[str, Any]] = {}
        self.notifications: list[dict[str, Any]] = []
        self.output: queue.Queue[tuple[str, Any]] = queue.Queue()
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
            or self.messages > MAX_APP_SERVER_TRACE_MESSAGES
            or self.bytes > MAX_APP_SERVER_TRACE_BYTES
        ):
            raise MaestroError(
                "CODEX_HOST_PROTOCOL_LIMIT",
                "codex app-server event stream exceeded its bounded limit.",
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
            if isinstance(value.get("method"), str):
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
    if params.get("threadId") != state["thread_id"]:
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
        observed = (
            _token_summary(usage.get("last"))
            if isinstance(usage, dict)
            else None
        )
        if observed is not None:
            state["tokens"] = observed
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


def run_codex_host(
    repo_path: str | Path,
    *,
    run_id: str,
    task_label: str,
    prompt_file: str | Path,
    plan_path: str | Path | None = None,
    assignment_id: str | None = None,
    sandbox: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    command: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run one Codex App Server turn and persist only bounded Host telemetry."""

    repo = ensure_repo(repo_path)
    prompt = _bounded_text_file(prompt_file)
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
        sandbox=sandbox,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    deadline = time.monotonic() + float(timeout_seconds)
    server = _AppServer(_command(command), cwd=repo, deadline=deadline)
    observation: dict[str, Any] | None = None
    state = {
        "thread_id": None,
        "turn_id": None,
        "completion": None,
        "reroutes": [],
        "tokens": None,
        "final_message": None,
        "final_message_is_final": False,
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
                    }
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

        observation = start_run_observation(
            repo,
            run_id=run_id,
            task_label=task_label,
            plan_path=plan_path,
        )
        if observation["status"] != "started":
            raise MaestroError(
                "CODEX_HOST_RUN_CONFLICT",
                "run-id already belongs to an existing observation; use a new run-id.",
            )

        turn_params: dict[str, Any] = {
            "threadId": state["thread_id"],
            "input": [{"type": "text", "text": prompt}],
            "cwd": str(repo),
            "approvalPolicy": "never",
            "sandboxPolicy": contract["sandbox_policy"],
        }
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
            time.monotonic() + POST_COMPLETION_DRAIN_SECONDS,
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

        applied_model = (
            state["reroutes"][-1]["to_model"]
            if state["reroutes"]
            else requested_model
        )
        completion = state["completion"]
        assert isinstance(completion, dict)
        _capture_terminal_message(completion, state)
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
            "status": completion["status"],
            "repo_root": str(repo),
            "run_id": run_id,
            "observation_id": observation["observation_id"],
            "assignment_id": contract["assignment_id"],
            "sandbox": contract["sandbox"],
            "thread_id": state["thread_id"],
            "turn_id": state["turn_id"],
            "duration_ms": duration,
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
            "host_observation": recorded["telemetry"],
            "writes_performed": True,
        }
    finally:
        server.close()
