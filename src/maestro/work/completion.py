from __future__ import annotations

import copy
import re
from collections import deque
from typing import Any

from maestro.util import canonical_json, sha256_text

from .contracts import (
    MAX_WORK_SPANS,
    TERMINAL_WORK_STATUSES,
    WORK_SPAN_VERSION,
    validate_work_spans,
)

COMPLETION_POLICY_VERSION = "maestro_completion_policy_v1"
COMPLETION_EVALUATION_VERSION = "maestro_completion_evaluation_v1"
COMPLETION_CLOSURE_VERSION = "maestro_completion_closure_v1"
MANAGED_COMPLETION_MODE = "managed_execution_graph"
MAX_COMPLETION_ISSUES = 64
MAX_PRE_SEAL_EXECUTION_EVENTS = 255
_DIGEST = re.compile(r"^[a-f0-9]{64}$")


def _digest_payload(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload[field] = ""
    return sha256_text(canonical_json(payload))


def managed_completion_policy() -> dict[str, Any]:
    """Return the immutable policy pinned to newly attached managed plans."""

    policy = {
        "schema_version": COMPLETION_POLICY_VERSION,
        "policy_id": "",
        "mode": MANAGED_COMPLETION_MODE,
        "required_work_schema_version": WORK_SPAN_VERSION,
        "require_assignment_terminal_work": True,
        "require_plan_dependency_paths": True,
        "require_single_final_synthesis": True,
    }
    policy["policy_id"] = _digest_payload(policy, "policy_id")
    return policy


def validate_completion_policy(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {
            "schema_version",
            "policy_id",
            "mode",
            "required_work_schema_version",
            "require_assignment_terminal_work",
            "require_plan_dependency_paths",
            "require_single_final_synthesis",
        }
        and value.get("schema_version") == COMPLETION_POLICY_VERSION
        and isinstance(value.get("policy_id"), str)
        and _DIGEST.fullmatch(value["policy_id"]) is not None
        and value["policy_id"] == _digest_payload(value, "policy_id")
        and value.get("mode") == MANAGED_COMPLETION_MODE
        and value.get("required_work_schema_version") == WORK_SPAN_VERSION
        and value.get("require_assignment_terminal_work") is True
        and value.get("require_plan_dependency_paths") is True
        and value.get("require_single_final_synthesis") is True
    )


def is_managed_completion_policy(value: Any) -> bool:
    return validate_completion_policy(value)


def receipt_intent_digest(value: dict[str, Any]) -> str:
    """Bind deterministic receipt content, excluding append-time projections."""

    return sha256_text(
        canonical_json(
            {
                key: item
                for key, item in value.items()
                if key
                not in {
                    "timestamp",
                    "execution_measurements",
                    "completion_policy",
                    "completion_closure",
                }
            }
        )
    )


def _issue(
    code: str,
    message: str,
    *related_ids: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "related_ids": list(dict.fromkeys(related_ids))[:MAX_WORK_SPANS],
    }


def _predecessors(span: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            item
            for item in (
                span.get("parent_work_id"),
                span.get("followup_of_work_id"),
                *span.get("depends_on_work_ids", []),
                *span.get("joins_work_ids", []),
            )
            if isinstance(item, str)
        )
    )


def _adjacency(
    work_spans: list[dict[str, Any]],
    *,
    excluded_work_ids: set[str] | None = None,
) -> dict[str, list[str]]:
    excluded = excluded_work_ids or set()
    work_ids = {
        span["work_id"]
        for span in work_spans
        if span["work_id"] not in excluded
    }
    adjacency = {work_id: [] for work_id in sorted(work_ids)}
    for span in work_spans:
        work_id = span["work_id"]
        if work_id not in work_ids:
            continue
        for predecessor in _predecessors(span):
            if predecessor in work_ids:
                adjacency[predecessor].append(work_id)
    for successors in adjacency.values():
        successors.sort()
    return adjacency


def terminal_assignment_work_heads(
    work_spans: Any,
    assignment_ids: list[str],
) -> dict[str, list[str]]:
    """Return terminal v2 leaves within each Assignment-bound subgraph."""

    if not isinstance(work_spans, list) or not validate_work_spans(work_spans):
        return {assignment_id: [] for assignment_id in assignment_ids}
    result: dict[str, list[str]] = {}
    for assignment_id in assignment_ids:
        candidates = {
            span["work_id"]
            for span in work_spans or []
            if span.get("schema_version") == WORK_SPAN_VERSION
            and span.get("assignment_id") == assignment_id
            and span.get("status") in TERMINAL_WORK_STATUSES
        }
        successors = {
            predecessor
            for span in work_spans or []
            if span.get("work_id") in candidates
            for predecessor in _predecessors(span)
            if predecessor in candidates
        }
        result[assignment_id] = sorted(candidates - successors)
    return result


def _shortest_path(
    adjacency: dict[str, list[str]],
    sources: list[str],
    targets: set[str],
) -> list[str] | None:
    queue: deque[list[str]] = deque(
        [[source] for source in sorted(sources) if source in adjacency]
    )
    visited = set(source for source in sources if source in adjacency)
    while queue:
        path = queue.popleft()
        current = path[-1]
        if current in targets:
            return path
        for successor in adjacency[current]:
            if successor in visited:
                continue
            visited.add(successor)
            queue.append([*path, successor])
    return None


def _evaluation(
    *,
    status: str,
    issues: list[dict[str, Any]],
    closure: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": COMPLETION_EVALUATION_VERSION,
        "status": status,
        "issues": issues[:MAX_COMPLETION_ISSUES],
        "closure": closure,
    }


def evaluate_completion(
    *,
    policy: Any,
    plan_summary: Any,
    stage_results: Any,
    work_spans: Any,
    pre_seal_ledger_revision: Any,
    pre_seal_ledger_digest: Any,
    receipt_intent: Any,
) -> dict[str, Any]:
    """Evaluate managed graph completion without persistence or Host I/O."""

    if policy is None:
        return _evaluation(status="not_managed", issues=[], closure=None)
    if not validate_completion_policy(policy):
        return _evaluation(
            status="blocked",
            issues=[
                _issue(
                    "COMPLETION_POLICY_INVALID",
                    "The managed completion policy is invalid.",
                )
            ],
            closure=None,
        )
    issues: list[dict[str, Any]] = []
    if (
        not isinstance(plan_summary, dict)
        or not isinstance(plan_summary.get("assignments"), list)
        or not plan_summary["assignments"]
    ):
        issues.append(
            _issue(
                "COMPLETION_PLAN_REQUIRED",
                "Managed completion requires one attached non-empty plan.",
            )
        )
    if not isinstance(stage_results, list):
        issues.append(
            _issue(
                "COMPLETION_STAGE_RESULTS_INVALID",
                "Managed completion requires bounded terminal stage results.",
            )
        )
    if not isinstance(work_spans, list) or not validate_work_spans(work_spans):
        issues.append(
            _issue(
                "COMPLETION_WORK_GRAPH_INVALID",
                "Observed work does not satisfy the bounded DAG contract.",
            )
        )
    elif any(
        span.get("schema_version") != policy["required_work_schema_version"]
        for span in work_spans or []
    ):
        issues.append(
            _issue(
                "COMPLETION_WORK_VERSION_REQUIRED",
                "Managed completion accepts only terminal v2 work spans.",
            )
        )
    elif any(
        span.get("status") not in TERMINAL_WORK_STATUSES
        for span in work_spans or []
    ):
        running = sorted(
            span["work_id"]
            for span in work_spans
            if span.get("status") not in TERMINAL_WORK_STATUSES
        )
        issues.append(
            _issue(
                "COMPLETION_WORK_RUNNING",
                "Managed completion cannot seal while work remains running.",
                *running,
            )
        )
    if (
        not isinstance(pre_seal_ledger_revision, int)
        or isinstance(pre_seal_ledger_revision, bool)
        or pre_seal_ledger_revision < 1
        or pre_seal_ledger_revision > MAX_PRE_SEAL_EXECUTION_EVENTS
        or not isinstance(pre_seal_ledger_digest, str)
        or _DIGEST.fullmatch(pre_seal_ledger_digest) is None
    ):
        issues.append(
            _issue(
                "COMPLETION_LEDGER_REVISION_INVALID",
                "Managed completion requires one content-addressed pre-seal ledger revision.",
            )
        )
    if (
        not isinstance(receipt_intent, str)
        or _DIGEST.fullmatch(receipt_intent) is None
    ):
        issues.append(
            _issue(
                "COMPLETION_RECEIPT_INTENT_REQUIRED",
                "Managed completion requires one deterministic receipt intent digest.",
            )
        )
    if issues:
        return _evaluation(status="blocked", issues=issues, closure=None)

    assert isinstance(plan_summary, dict)
    assert isinstance(stage_results, list)
    assert isinstance(work_spans, list)
    assignments = {
        assignment["assignment_id"]: assignment
        for assignment in plan_summary["assignments"]
        if isinstance(assignment, dict)
        and isinstance(assignment.get("assignment_id"), str)
    }
    statuses = {
        stage["assignment_id"]: stage["status"]
        for stage in stage_results
        if isinstance(stage, dict)
        and isinstance(stage.get("assignment_id"), str)
        and isinstance(stage.get("status"), str)
    }
    missing_stages = sorted(set(assignments) - set(statuses))
    if missing_stages:
        issues.append(
            _issue(
                "COMPLETION_ASSIGNMENT_STAGE_MISSING",
                "Every planned Assignment requires one terminal stage result.",
                *missing_stages,
            )
        )
    active_assignment_ids = [
        assignment_id
        for assignment_id in assignments
        if statuses.get(assignment_id) != "skipped"
    ]
    bindings: list[dict[str, Any]] = []
    bound_work: dict[str, list[str]] = {}
    for assignment_id in active_assignment_ids:
        terminal_ids = sorted(
            span["work_id"]
            for span in work_spans
            if span.get("assignment_id") == assignment_id
            and span.get("schema_version") == WORK_SPAN_VERSION
            and span.get("status") in TERMINAL_WORK_STATUSES
        )
        if not terminal_ids:
            issues.append(
                _issue(
                    "COMPLETION_ASSIGNMENT_WORK_MISSING",
                    "Every non-skipped Assignment requires terminal v2 bound work.",
                    assignment_id,
                )
            )
        bound_work[assignment_id] = terminal_ids
        bindings.append(
            {
                "assignment_id": assignment_id,
                "stage_status": statuses.get(assignment_id),
                "terminal_work_ids": terminal_ids,
            }
        )

    adjacency = _adjacency(work_spans)
    bound_heads = terminal_assignment_work_heads(
        work_spans,
        active_assignment_ids,
    )
    dependency_paths: list[dict[str, Any]] = []
    for downstream_id in active_assignment_ids:
        assignment = assignments[downstream_id]
        for upstream_id in assignment.get("depends_on", []):
            if upstream_id not in active_assignment_ids:
                issues.append(
                    _issue(
                        "COMPLETION_DEPENDENCY_INACTIVE",
                        "An active downstream Assignment cannot depend on a skipped stage.",
                        upstream_id,
                        downstream_id,
                    )
                )
                continue
            for upstream_head_id in bound_heads.get(upstream_id, []):
                path = _shortest_path(
                    adjacency,
                    [upstream_head_id],
                    set(bound_work.get(downstream_id, [])),
                )
                if path is None:
                    issues.append(
                        _issue(
                            "COMPLETION_DEPENDENCY_PATH_MISSING",
                            (
                                "A current upstream Assignment terminal head "
                                "lacks an observed path into downstream work."
                            ),
                            upstream_id,
                            upstream_head_id,
                            downstream_id,
                        )
                    )
                    continue
                dependency_paths.append(
                    {
                        "upstream_assignment_id": upstream_id,
                        "upstream_terminal_work_id": upstream_head_id,
                        "downstream_assignment_id": downstream_id,
                        "work_path": path,
                    }
                )

    leaves = sorted(
        work_id
        for work_id, successors in adjacency.items()
        if not successors
    )
    final_work: dict[str, Any] | None = None
    if len(leaves) != 1:
        issues.append(
            _issue(
                "COMPLETION_FINAL_LEAF_INVALID",
                "The execution graph must have exactly one terminal leaf.",
                *leaves,
            )
        )
    else:
        final_work = next(
            span for span in work_spans if span["work_id"] == leaves[0]
        )
        if not (
            final_work.get("schema_version") == WORK_SPAN_VERSION
            and final_work.get("kind") == "synthesis"
            and final_work.get("assignment_id") is None
            and final_work.get("status") == "completed"
        ):
            issues.append(
                _issue(
                    "COMPLETION_FINAL_SYNTHESIS_INVALID",
                    "The unique terminal leaf must be completed, unbound v2 synthesis work.",
                    final_work["work_id"],
                )
            )
        outcome = final_work.get("outcome")
        if not (
            isinstance(outcome, dict)
            and isinstance(outcome.get("conclusion"), str)
            and bool(outcome["conclusion"].strip())
            and isinstance(outcome.get("decision"), str)
            and bool(outcome["decision"].strip())
            and outcome.get("next_action") == "finish"
        ):
            issues.append(
                _issue(
                    "COMPLETION_FINAL_OUTCOME_INVALID",
                    "Final synthesis requires a conclusion, decision, and next_action=finish.",
                    final_work["work_id"],
                )
            )

    required_heads: list[str] = []
    consumption_paths: list[dict[str, Any]] = []
    if final_work is not None:
        without_final = _adjacency(
            work_spans,
            excluded_work_ids={final_work["work_id"]},
        )
        required_heads = sorted(
            work_id
            for work_id, successors in without_final.items()
            if not successors
        )
        joined = set(final_work.get("joins_work_ids", []))
        consumed = set(
            final_work.get("outcome", {}).get(
                "consumed_work_ids",
                [],
            )
        )
        required = set(required_heads)
        if joined != required:
            issues.append(
                _issue(
                    "COMPLETION_FINAL_SYNTHESIS_INCOMPLETE",
                    "Final synthesis joins must exactly cover every prior execution leaf.",
                    *sorted(required.symmetric_difference(joined)),
                )
            )
        if consumed != required or consumed != joined:
            issues.append(
                _issue(
                    "COMPLETION_FINAL_CONSUMPTION_INVALID",
                    "Final synthesis consumed work must exactly match its required joins.",
                    *sorted(
                        required.symmetric_difference(consumed)
                        | joined.symmetric_difference(consumed)
                    ),
                )
            )
        for head in required_heads:
            path = _shortest_path(
                adjacency,
                [head],
                {final_work["work_id"]},
            )
            if path is None:
                issues.append(
                    _issue(
                        "COMPLETION_FINAL_REACHABILITY_MISSING",
                        "A required terminal head does not reach final synthesis.",
                        head,
                        final_work["work_id"],
                    )
                )
                continue
            consumption_paths.append(
                {
                    "terminal_work_id": head,
                    "work_path": path,
                }
            )
    if issues:
        return _evaluation(status="blocked", issues=issues, closure=None)

    assert final_work is not None
    closure = {
        "schema_version": COMPLETION_CLOSURE_VERSION,
        "closure_digest": "",
        "policy": copy.deepcopy(policy),
        "assignment_bindings": bindings,
        "plan_dependency_paths": dependency_paths,
        "final_synthesis": {
            "work_id": final_work["work_id"],
            "joined_work_ids": list(final_work["joins_work_ids"]),
            "required_terminal_work_ids": required_heads,
            "consumption_paths": consumption_paths,
        },
        "pre_seal_ledger": {
            "revision": pre_seal_ledger_revision,
            "event_count": pre_seal_ledger_revision,
            "digest": pre_seal_ledger_digest,
        },
        "receipt_intent_digest": receipt_intent,
    }
    closure["closure_digest"] = _digest_payload(
        closure,
        "closure_digest",
    )
    return _evaluation(status="ready", issues=[], closure=closure)


def validate_completion_closure(
    value: Any,
    *,
    policy: Any,
    plan_summary: Any,
    stage_results: Any,
    work_spans: Any,
    receipt_intent: Any,
) -> bool:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "closure_digest",
            "policy",
            "assignment_bindings",
            "plan_dependency_paths",
            "final_synthesis",
            "pre_seal_ledger",
            "receipt_intent_digest",
        }
        or value.get("schema_version") != COMPLETION_CLOSURE_VERSION
        or not isinstance(value.get("closure_digest"), str)
        or _DIGEST.fullmatch(value["closure_digest"]) is None
        or value["closure_digest"] != _digest_payload(value, "closure_digest")
        or value.get("policy") != policy
        or value.get("receipt_intent_digest") != receipt_intent
    ):
        return False
    pre_seal = value.get("pre_seal_ledger")
    if (
        not isinstance(pre_seal, dict)
        or set(pre_seal) != {"revision", "event_count", "digest"}
        or pre_seal.get("revision") != pre_seal.get("event_count")
    ):
        return False
    evaluation = evaluate_completion(
        policy=policy,
        plan_summary=plan_summary,
        stage_results=stage_results,
        work_spans=work_spans,
        pre_seal_ledger_revision=pre_seal.get("revision"),
        pre_seal_ledger_digest=pre_seal.get("digest"),
        receipt_intent=receipt_intent,
    )
    return evaluation["status"] == "ready" and evaluation["closure"] == value
