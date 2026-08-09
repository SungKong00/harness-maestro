from __future__ import annotations

from typing import Any

from .graph import build_work_graph

_WORK_PRESENTATION = {
    "orchestration": {
        "lane_id": "orchestration",
        "lane_label": "오케스트레이션",
        "lane_description": "작업을 나누고 담당자 결과를 다시 합치는 영역",
        "title": "메인 오케스트레이터",
    },
    "delegation": {
        "lane_id": "delegation",
        "lane_label": "위임 작업",
        "lane_description": "독립 실행 컨텍스트에 맡긴 실제 작업",
        "title": "위임 작업",
    },
    "research": {
        "lane_id": "specialist",
        "lane_label": "조사·전문 검토",
        "lane_description": "근거 조사와 독립 전문 검토를 수행한 영역",
        "title": "근거 조사",
    },
    "review": {
        "lane_id": "specialist",
        "lane_label": "조사·전문 검토",
        "lane_description": "근거 조사와 독립 전문 검토를 수행한 영역",
        "title": "전문 검토",
    },
    "implementation": {
        "lane_id": "delivery",
        "lane_label": "구현",
        "lane_description": "승인된 범위를 실제 변경으로 만든 영역",
        "title": "구현",
    },
    "synthesis": {
        "lane_id": "synthesis",
        "lane_label": "결과 합성",
        "lane_description": "여러 보고를 하나의 판단이나 결과로 합친 영역",
        "title": "결과 합성",
    },
    "verification": {
        "lane_id": "verification",
        "lane_label": "검증",
        "lane_description": "구현과 완료 근거를 독립적으로 확인한 영역",
        "title": "검증",
    },
}
_LANE_ORDER = {
    "orchestration": 0,
    "delegation": 1,
    "specialist": 2,
    "delivery": 3,
    "synthesis": 4,
    "verification": 5,
}


def _presentation(kind: str) -> dict[str, str]:
    return _WORK_PRESENTATION.get(
        kind,
        {
            "lane_id": "delegation",
            "lane_label": "위임 작업",
            "lane_description": "현재 분류표에 없는 실제 작업",
            "title": kind,
        },
    )


def _coverage(span: dict[str, Any]) -> dict[str, Any]:
    source = span.get("source_binding")
    model = span.get("model_observation")
    usage = span.get("usage")
    return {
        "source": source or {
            "interface": span["source"],
            "version": None,
            "schema_digest": None,
            "capability": "unavailable",
            "correlation_id": None,
            "event_coverage": "unavailable",
        },
        "model": (
            model.get("coverage")
            if isinstance(model, dict)
            else (
                "request_only"
                if span["requested_model"] is not None
                else "unavailable"
            )
        ),
        "timing": (
            usage.get("timing_coverage")
            if isinstance(usage, dict)
            else (
                "collector_clock"
                if span["timing_evidence"] == "current_host_clock"
                else "partial"
            )
        ),
        "event": (
            source.get("event_coverage")
            if isinstance(source, dict)
            else "unavailable"
        ),
    }


def _outcome(span: dict[str, Any]) -> dict[str, Any]:
    structured = span.get("outcome")
    if isinstance(structured, dict):
        return {
            **structured,
            "result_summary": span["result_summary"],
            "decision_evidence": (
                "structured_work_outcome"
                if structured["decision"] is not None
                else "unavailable"
            ),
        }
    return {
        "finding_summary": None,
        "conclusion": None,
        "decision": None,
        "next_action": None,
        "consumed_work_ids": [],
        "handoff": None,
        "artifacts": [],
        "verification": None,
        "result_summary": span["result_summary"],
        "decision_evidence": "unavailable",
    }


def _usage(span: dict[str, Any]) -> dict[str, Any]:
    value = span.get("usage")
    return value if isinstance(value, dict) else {
        "last": None,
        "total": None,
        "scope": "unavailable",
        "attribution": "unavailable",
        "timing_coverage": (
            "collector_clock"
            if span["timing_evidence"] == "current_host_clock"
            else "partial"
        ),
        "cost": None,
    }


def _allocation(span: dict[str, Any]) -> dict[str, Any]:
    value = span.get("allocation")
    if isinstance(value, dict):
        return {
            **value,
            "evidence": "structured_allocation_observation",
        }
    return {
        "status": "unavailable",
        "source": "unavailable",
        "reason": None,
        "basis_refs": [],
        "dependency_assignment_ids": [],
        "evidence": "legacy_work_span",
    }


def _expertise(span: dict[str, Any]) -> dict[str, Any]:
    observation = span.get("expertise_observation")
    selected = bool(
        span["expertise_pack_ids"]
        or span["decision_guide_ids"]
    )
    projected = {
        "lens_ids": list(span["lens_ids"]),
        "pack_ids": list(span["expertise_pack_ids"]),
        "guide_ids": list(span["decision_guide_ids"]),
        "evidence": (
            span["expertise_evidence"]
            if isinstance(observation, dict)
            else ("selection_only" if selected else "unavailable")
        ),
    }
    if not isinstance(observation, dict):
        return projected
    return {
        **projected,
        "packs": [dict(item) for item in observation["packs"]],
        "load": dict(observation["load"]),
        "application": dict(observation["application"]),
    }


def project_observed_work(
    work_spans: list[dict[str, Any]] | None,
    stages: list[dict[str, Any]],
) -> dict[str, Any]:
    graph = build_work_graph(stages, work_spans)
    execution = graph["execution"]
    stage_titles = {
        stage["assignment_id"]: stage.get("kind") or stage["assignment_id"]
        for stage in stages
        if isinstance(stage.get("assignment_id"), str)
    }
    stage_model_routes = {
        stage["assignment_id"]: {
            "route_recommended": stage.get("route_recommended_model"),
            "route_recommended_reasoning_effort": stage.get(
                "reasoning_effort"
            ),
            "model_route_id": stage.get("model_route_id"),
            "execution_unit_id": stage.get("execution_unit_id"),
            "stage_kind": stage.get("stage_kind"),
            "execution_kind": stage.get("execution_kind"),
            "selected_class": stage.get("selected_class"),
            "quality_profile": stage.get("quality_profile"),
            "quality_floor": stage.get("quality_floor"),
            "fallback_route": stage.get("fallback_route"),
        }
        for stage in stages
        if isinstance(stage.get("assignment_id"), str)
    }
    lanes_by_id: dict[str, dict[str, Any]] = {}
    cards = []
    for position, node in enumerate(execution["nodes"]):
        span = node["data"]
        presentation = _presentation(span["kind"])
        lane = lanes_by_id.setdefault(
            presentation["lane_id"],
            {
                "lane_id": presentation["lane_id"],
                "label": presentation["lane_label"],
                "description": presentation["lane_description"],
                "basis": "observed_work_kind",
                "work_ids": [],
            },
        )
        lane["work_ids"].append(span["work_id"])
        outcome = _outcome(span)
        coverage = _coverage(span)
        usage = _usage(span)
        model_observation = span.get("model_observation")
        diagnostics = span.get("diagnostics")
        cards.append(
            {
                "work_id": span["work_id"],
                "node_type": "work_attempt",
                "kind": span["kind"],
                "title": presentation["title"],
                "role": span["role"],
                "task_summary": span["task_summary"],
                "result_summary": span["result_summary"],
                "summary": {
                    "topic": span["task_summary"],
                    "decision": outcome["decision"],
                    "result": span["result_summary"],
                    "decision_evidence": outcome["decision_evidence"],
                },
                "assignment": {
                    "assignment_id": span["assignment_id"],
                    "label": stage_titles.get(span["assignment_id"]),
                    "model_route": stage_model_routes.get(
                        span["assignment_id"]
                    ),
                    "source": (
                        "explicit_assignment_binding"
                        if span["assignment_id"] is not None
                        else "unavailable"
                    ),
                },
                "lane_id": presentation["lane_id"],
                "rank": node["rank"],
                "position": position,
                "status": {
                    "value": span["status"],
                    "source": span["source"],
                },
                "responsibility": {
                    "executor_id": span["executor_id"],
                    "role": span["role"],
                    "read_only": span["read_only"],
                },
                "allocation": _allocation(span),
                "relationships": {
                    "parent_work_id": span["parent_work_id"],
                    "followup_of_work_id": span["followup_of_work_id"],
                    "depends_on_work_ids": list(
                        span["depends_on_work_ids"]
                    ),
                    "joins_work_ids": list(span["joins_work_ids"]),
                },
                "attempt": span["attempt"],
                "models": {
                    "requested": span["requested_model"],
                    "requested_reasoning_effort": span[
                        "requested_reasoning_effort"
                    ],
                    "applied": span["applied_model"],
                    "evidence": span["model_evidence"],
                    "observed": (
                        model_observation.get("observed_model")
                        if isinstance(model_observation, dict)
                        else None
                    ),
                    "coverage": coverage["model"],
                    "reroutes": (
                        list(model_observation.get("reroutes", []))
                        if isinstance(model_observation, dict)
                        else []
                    ),
                },
                "measurements": {
                    "started_at": span["started_at"],
                    "ended_at": span["ended_at"],
                    "duration_ms": span["duration_ms"],
                    "timing_evidence": span["timing_evidence"],
                    "timing_coverage": coverage["timing"],
                    "tokens": {
                        "last": usage["last"],
                        "total": usage["total"],
                        "scope": usage["scope"],
                        "attribution": usage["attribution"],
                    },
                    "cost": usage["cost"],
                },
                "execution_facts": {
                    "model": {
                        "kind": (
                            "actual"
                            if coverage["model"] == "complete_stream"
                            and span["applied_model"] is not None
                            else (
                                "hook_point"
                                if coverage["model"] == "hook_point"
                                and isinstance(model_observation, dict)
                                and model_observation.get("observed_model")
                                is not None
                                else (
                                    "requested"
                                    if span["requested_model"] is not None
                                    else "unavailable"
                                )
                            )
                        ),
                        "value": (
                            span["applied_model"]
                            if coverage["model"] == "complete_stream"
                            else (
                                model_observation.get("observed_model")
                                if coverage["model"] == "hook_point"
                                and isinstance(model_observation, dict)
                                else span["requested_model"]
                            )
                        ),
                        "coverage": coverage["model"],
                    },
                    "reasoning": {
                        "kind": (
                            "requested"
                            if span["requested_reasoning_effort"] is not None
                            else "unavailable"
                        ),
                        "value": span["requested_reasoning_effort"],
                    },
                    "tokens": {
                        "value": usage["total"],
                        "last": usage["last"],
                        "scope": usage["scope"],
                        "attribution": usage["attribution"],
                    },
                    "duration": {
                        "value_ms": span["duration_ms"],
                        "coverage": coverage["timing"],
                        "state": (
                            "running"
                            if span["status"] == "running"
                            else "terminal"
                        ),
                    },
                },
                "expertise": _expertise(span),
                "evidence": {
                    "count": len(span["evidence_refs"]),
                    "refs": list(span["evidence_refs"]),
                },
                "coverage": coverage,
                "outcome": outcome,
                "diagnostics": (
                    diagnostics
                    if isinstance(diagnostics, dict)
                    else {
                        "interrupt_requested": False,
                        "error_count": 0,
                        "last_error": None,
                        "followup_reason": None,
                    }
                ),
                "detail": {
                    "input": span["task_summary"],
                    "completion_criteria": (
                        outcome["handoff"]["completion_criteria"]
                        if isinstance(outcome["handoff"], dict)
                        else None
                    ),
                    "finding": outcome["finding_summary"],
                    "conclusion": outcome["conclusion"],
                    "decision": outcome["decision"],
                    "next_action": outcome["next_action"],
                    "handoff": outcome["handoff"],
                    "artifacts": list(outcome["artifacts"]),
                    "verification": outcome["verification"],
                },
            }
        )
    lanes = sorted(
        lanes_by_id.values(),
        key=lambda lane: (
            _LANE_ORDER.get(lane["lane_id"], 99),
            lane["label"],
        ),
    )
    edge_counts: dict[str, int] = {}
    for edge in execution["edges"]:
        edge_counts[edge["type"]] = edge_counts.get(edge["type"], 0) + 1
    return {
        "schema_version": "maestro_observed_work_projection_v2",
        "mode": "observed" if cards else "plan_only",
        "completeness": execution["completeness"],
        "cards": cards,
        "lanes": lanes,
        "graph": {
            "edges": list(execution["edges"]),
            "display_edge_groups": list(
                execution["display_edge_groups"]
            ),
            "detail_only_edge_indexes": list(
                execution["detail_only_edge_indexes"]
            ),
            "entry_work_ids": list(execution["entry_node_ids"]),
            "terminal_work_ids": list(execution["terminal_node_ids"]),
            "max_rank": execution["max_rank"],
            "actual_concurrency": execution["actual_concurrency"],
            "concurrent_work_pairs": list(
                execution["concurrent_work_pairs"]
            ),
        },
        "bindings": list(graph["bindings"]),
        "summary": {
            "work_count": len(cards),
            "delegation_count": edge_counts.get("delegates_to", 0),
            "report_count": edge_counts.get("reports_to", 0),
            "join_count": edge_counts.get("joins_into", 0),
            "followup_count": edge_counts.get("followup_of", 0),
        },
    }
