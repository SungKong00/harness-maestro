from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from maestro.errors import MaestroError
from maestro.util import canonical_json, sha256_text

COLLAB_ITEM_TYPE = "collabAgentToolCall"
COLLAB_TOOLS = {
    "spawnAgent",
    "sendInput",
    "resumeAgent",
    "wait",
    "closeAgent",
}
COLLAB_CALL_STATUSES = {
    "inProgress",
    "completed",
    "failed",
}
COLLAB_AGENT_STATUSES = {
    "pendingInit",
    "running",
    "interrupted",
    "completed",
    "errored",
    "shutdown",
    "notFound",
}
TERMINAL_AGENT_STATUSES = {
    "interrupted": "interrupted",
    "completed": "completed",
    "errored": "failed",
    "shutdown": "interrupted",
    "notFound": "failed",
}
MAX_COLLAB_TARGETS = 16
MAX_COLLAB_WORK = 63


def codex_work_id(*identity: str) -> str:
    """Return a bounded, privacy-preserving ID for one App Server work item."""

    if not identity or not all(
        isinstance(item, str)
        and item
        and len(item) <= 512
        and not any(character in item for character in "\r\n\x00")
        for item in identity
    ):
        raise MaestroError(
            "CODEX_WORK_ID_INVALID",
            "Codex work identity must contain bounded non-empty lines.",
        )
    digest = sha256_text(canonical_json(list(identity)))
    return f"codex-{digest[:32]}"


def codex_event_timestamp(value: Any) -> str:
    """Convert an App Server millisecond timestamp into the work contract."""

    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise MaestroError(
            "CODEX_WORK_EVENT_INVALID",
            "Codex work lifecycle events require a non-negative integer timestamp.",
        )
    try:
        observed = datetime.fromtimestamp(value / 1000, timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise MaestroError(
            "CODEX_WORK_EVENT_INVALID",
            "Codex work lifecycle timestamp is outside the supported range.",
        ) from exc
    return observed.isoformat().replace("+00:00", "Z")


def _bounded_line(
    value: Any,
    *,
    field: str,
    maximum: int,
    nullable: bool = False,
) -> str | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(character in value for character in "\r\n\x00")
    ):
        raise MaestroError(
            "CODEX_WORK_EVENT_INVALID",
            f"{field} must be one bounded non-empty line.",
        )
    return value.strip()


def _targets(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > MAX_COLLAB_TARGETS
    ):
        raise MaestroError(
            "CODEX_WORK_EVENT_INVALID",
            "receiverThreadIds must be a bounded unique list.",
        )
    targets = [
        _bounded_line(item, field="receiverThreadIds", maximum=160)
        for item in value
    ]
    if len(targets) != len(set(targets)):
        raise MaestroError(
            "CODEX_WORK_EVENT_INVALID",
            "receiverThreadIds must be a bounded unique list.",
        )
    return targets


def _agent_states(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > MAX_COLLAB_TARGETS:
        raise MaestroError(
            "CODEX_WORK_EVENT_INVALID",
            "agentsStates must be a bounded object.",
        )
    result: dict[str, str] = {}
    for thread_id, state in value.items():
        target = _bounded_line(
            thread_id,
            field="agentsStates thread ID",
            maximum=160,
        )
        if not isinstance(state, dict):
            raise MaestroError(
                "CODEX_WORK_EVENT_INVALID",
                "Each agentsStates entry must be an object.",
            )
        status = state.get("status")
        if status not in COLLAB_AGENT_STATUSES:
            raise MaestroError(
                "CODEX_WORK_EVENT_INVALID",
                "agentsStates contains an unsupported status.",
            )
        result[target] = status
    return result


class CodexCollaborationTracker:
    """Translate allowlisted Codex collaboration events into work actions."""

    def __init__(
        self,
        *,
        root_work_id: str,
        root_thread_id: str,
        assignment_id: str | None,
        read_only: bool,
    ) -> None:
        self.root_work_id = _bounded_line(
            root_work_id,
            field="root_work_id",
            maximum=96,
        )
        self.root_thread_id = _bounded_line(
            root_thread_id,
            field="root_thread_id",
            maximum=160,
        )
        self.assignment_id = assignment_id
        self.read_only = read_only
        self._work_by_item: dict[str, str] = {}
        self._work_by_thread: dict[str, str] = {}
        self._attempt_by_work: dict[str, int] = {}
        self._started_work: set[str] = set()
        self._finished_work: set[str] = set()

    @property
    def running_work_ids(self) -> list[str]:
        return sorted(self._started_work - self._finished_work)

    @property
    def observed_work_count(self) -> int:
        return len(self._started_work)

    @property
    def terminal_work_count(self) -> int:
        return len(self._finished_work)

    def consume(
        self,
        *,
        method: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if method not in {"item/started", "item/completed"}:
            return []
        item = params.get("item")
        if not isinstance(item, dict) or item.get("type") != COLLAB_ITEM_TYPE:
            return []
        if item.get("senderThreadId") != self.root_thread_id:
            return []

        observed_at = codex_event_timestamp(
            params.get(
                "startedAtMs"
                if method == "item/started"
                else "completedAtMs"
            )
        )
        item_id = _bounded_line(
            item.get("id"),
            field="collaboration item ID",
            maximum=512,
        )
        tool = item.get("tool")
        status = item.get("status")
        if tool not in COLLAB_TOOLS or status not in COLLAB_CALL_STATUSES:
            raise MaestroError(
                "CODEX_WORK_EVENT_INVALID",
                "Collaboration item contains an unsupported tool or call status.",
            )
        targets = _targets(item.get("receiverThreadIds"))
        states = _agent_states(item.get("agentsStates"))
        if any(target not in targets for target in states):
            raise MaestroError(
                "CODEX_WORK_EVENT_INVALID",
                "agentsStates may describe only receiverThreadIds.",
            )

        actions: list[dict[str, Any]] = []
        current_work_id: str | None = None
        if tool in {"spawnAgent", "resumeAgent"}:
            current_work_id = self._work_by_item.setdefault(
                item_id,
                codex_work_id(
                    self.root_thread_id,
                    str(item_id),
                    str(tool),
                ),
            )
            previous = next(
                (
                    self._work_by_thread[target]
                    for target in targets
                    if target in self._work_by_thread
                ),
                None,
            )
            if current_work_id not in self._started_work:
                if len(self._started_work) >= MAX_COLLAB_WORK:
                    raise MaestroError(
                        "CODEX_WORK_LIMIT",
                        "Codex collaboration work exceeds the bounded run limit.",
                    )
                requested_model = _bounded_line(
                    item.get("model"),
                    field="collaboration model",
                    maximum=128,
                    nullable=True,
                )
                requested_effort = _bounded_line(
                    item.get("reasoningEffort"),
                    field="collaboration reasoning effort",
                    maximum=40,
                    nullable=True,
                )
                if requested_model is None:
                    requested_effort = None
                attempt = (
                    self._attempt_by_work.get(previous, 0) + 1
                    if tool == "resumeAgent" and previous is not None
                    else 1
                )
                actions.append(
                    {
                        "action": "start",
                        "work_id": current_work_id,
                        "parent_work_id": self.root_work_id,
                        "assignment_id": self.assignment_id,
                        "kind": "delegation",
                        "role": "Codex 위임 실행 담당",
                        "executor_id": codex_work_id(
                            "agent",
                            targets[0] if targets else str(item_id),
                        ),
                        "task_summary": (
                            "중단된 위임 작업을 다시 실행합니다."
                            if tool == "resumeAgent"
                            else "오케스트레이터가 위임한 작업을 실행합니다."
                        ),
                        "read_only": self.read_only,
                        "source": "codex_app_server",
                        "started_at": observed_at,
                        "attempt": attempt,
                        "followup_of_work_id": (
                            previous if tool == "resumeAgent" else None
                        ),
                        "requested_model": requested_model,
                        "requested_reasoning_effort": requested_effort,
                        "model_evidence": (
                            "host_request"
                            if requested_model is not None
                            else "unavailable"
                        ),
                    }
                )
                self._started_work.add(current_work_id)
                self._attempt_by_work[current_work_id] = attempt
            for target in targets:
                self._work_by_thread[target] = current_work_id

        if (
            current_work_id is not None
            and status == "failed"
            and current_work_id not in self._finished_work
        ):
            actions.append(
                self._finish_action(
                    current_work_id,
                    status="failed",
                    observed_at=observed_at,
                    evidence_identity=(str(item_id), str(tool), "call-failed"),
                )
            )

        for target in targets:
            target_work_id = self._work_by_thread.get(target)
            target_status = states.get(target)
            if (
                target_work_id is None
                or target_status not in TERMINAL_AGENT_STATUSES
                or target_work_id in self._finished_work
            ):
                continue
            actions.append(
                self._finish_action(
                    target_work_id,
                    status=TERMINAL_AGENT_STATUSES[target_status],
                    observed_at=observed_at,
                    evidence_identity=(
                        str(item_id),
                        str(tool),
                        target,
                        target_status,
                    ),
                )
            )
        return actions

    def _finish_action(
        self,
        work_id: str,
        *,
        status: str,
        observed_at: str,
        evidence_identity: tuple[str, ...],
    ) -> dict[str, Any]:
        self._finished_work.add(work_id)
        summary = {
            "completed": "위임 작업이 완료되었습니다.",
            "failed": "위임 작업이 실패했습니다.",
            "interrupted": "위임 작업이 중단되었습니다.",
        }[status]
        return {
            "action": "finish",
            "work_id": work_id,
            "status": status,
            "result_summary": summary,
            "ended_at": observed_at,
            "evidence_refs": [
                "codex-collab:"
                + sha256_text(canonical_json(list(evidence_identity)))[:32]
            ],
        }
