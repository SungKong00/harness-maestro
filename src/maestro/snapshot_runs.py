from __future__ import annotations

from typing import Any

from .work import build_display_edge_groups, project_observed_work


_STAGE_PRESENTATION = {
    "research": {
        "lane_id": "research",
        "lane_label": "근거 조사",
        "lane_description": "외부·프로젝트 근거를 확인하는 담당 영역",
        "title": "근거 조사",
        "purpose": "결정에 필요한 근거와 적용 한계를 확인합니다.",
    },
    "review": {
        "lane_id": "review",
        "lane_label": "독립 검토",
        "lane_description": "구현과 분리된 관점에서 위험을 확인하는 담당 영역",
        "title": "독립 검토",
        "purpose": "선택된 검토 관점으로 위험과 누락을 확인합니다.",
    },
    "implementation": {
        "lane_id": "delivery",
        "lane_label": "구현",
        "lane_description": "승인된 범위의 변경을 만드는 담당 영역",
        "title": "구현",
        "purpose": "승인된 계획을 프로젝트 변경으로 구현합니다.",
    },
    "verification": {
        "lane_id": "verification",
        "lane_label": "결과 검증",
        "lane_description": "완료 조건과 실행 근거를 확인하는 담당 영역",
        "title": "결과 검증",
        "purpose": "결과와 완료 근거가 계약을 충족하는지 확인합니다.",
    },
    "summary": {
        "lane_id": "result",
        "lane_label": "결과 정리",
        "lane_description": "최종 작업 기록만 남은 이전 형식의 담당 영역",
        "title": "최종 결과 요약",
        "purpose": "보관된 최종 결과와 실행 요약을 보여 줍니다.",
    },
}
_STAGE_LANE_ORDER = {
    "research": 0,
    "review": 1,
    "delivery": 2,
    "verification": 3,
    "result": 4,
    "other": 5,
}


def _unique_strings(values: list[Any]) -> list[str]:
    return list(
        dict.fromkeys(
            value
            for value in values
            if isinstance(value, str) and value
        )
    )


def _stage_presentation(kind: Any) -> dict[str, str]:
    if isinstance(kind, str) and kind in _STAGE_PRESENTATION:
        return _STAGE_PRESENTATION[kind]
    label = kind if isinstance(kind, str) and kind else "기타 단계"
    return {
        "lane_id": "other",
        "lane_label": "기타 담당 영역",
        "lane_description": "현재 분류표에 없는 계획 단계",
        "title": label,
        "purpose": "이 단계의 구체적인 목적은 현재 실행 기록에서 확인할 수 없습니다.",
    }


def _graph_ranks(flow: list[dict[str, Any]]) -> dict[str, int]:
    assignment_ids = {
        stage["assignment_id"]
        for stage in flow
        if isinstance(stage.get("assignment_id"), str)
        and stage["assignment_id"]
    }
    pending = [
        stage
        for stage in flow
        if stage.get("assignment_id") in assignment_ids
    ]
    ranks: dict[str, int] = {}
    while pending:
        remaining: list[dict[str, Any]] = []
        progressed = False
        for stage in pending:
            dependencies = [
                dependency
                for dependency in stage.get("depends_on", [])
                if dependency in assignment_ids
            ]
            if all(dependency in ranks for dependency in dependencies):
                ranks[stage["assignment_id"]] = (
                    max((ranks[dependency] for dependency in dependencies), default=-1)
                    + 1
                )
                progressed = True
            else:
                remaining.append(stage)
        if not progressed:
            for stage in remaining:
                ranks[stage["assignment_id"]] = 0
            break
        pending = remaining
    return ranks


def _work_detail_projection(run: dict[str, Any]) -> dict[str, Any]:
    flow = run.get("flow", [])
    graph = run.get("flow_graph", {})
    ranks = _graph_ranks(flow)
    lanes_by_id: dict[str, dict[str, Any]] = {}
    stages: list[dict[str, Any]] = []
    for index, stage in enumerate(flow):
        presentation = _stage_presentation(stage.get("kind"))
        lane_id = presentation["lane_id"]
        lane = lanes_by_id.setdefault(
            lane_id,
            {
                "lane_id": lane_id,
                "label": presentation["lane_label"],
                "description": presentation["lane_description"],
                "basis": "assignment_kind",
                "stage_ids": [],
            },
        )
        stage_id = stage.get("assignment_id")
        lane["stage_ids"].append(stage_id)
        deterministic_stage = (
            stage.get("execution_kind") == "deterministic"
            or stage.get("evidence_source") == "deterministic_command"
        )
        applied_model_measured = (
            stage.get("applied_model") is not None
            and stage.get("model_evidence") == "complete"
        )
        if deterministic_stage:
            model_kind = "not_applicable"
            model_value = None
            model_coverage = "not_applicable"
            reasoning_kind = "not_applicable"
            reasoning_value = None
        elif applied_model_measured:
            model_kind = "actual"
            model_value = stage.get("applied_model")
            model_coverage = "complete"
            reasoning_kind = (
                "requested"
                if stage.get("requested_reasoning_effort") is not None
                else (
                    "recommended"
                    if stage.get("reasoning_effort") is not None
                    else "unavailable"
                )
            )
            reasoning_value = (
                stage.get("requested_reasoning_effort")
                or stage.get("reasoning_effort")
            )
        elif stage.get("requested_model") is not None:
            model_kind = "requested"
            model_value = stage.get("requested_model")
            model_coverage = "host_request"
            reasoning_kind = (
                "requested"
                if stage.get("requested_reasoning_effort") is not None
                else (
                    "recommended"
                    if stage.get("reasoning_effort") is not None
                    else "unavailable"
                )
            )
            reasoning_value = (
                stage.get("requested_reasoning_effort")
                or stage.get("reasoning_effort")
            )
        elif stage.get("route_recommended_model") is not None:
            model_kind = "recommended"
            model_value = stage.get("route_recommended_model")
            model_coverage = "route_plan"
            reasoning_kind = (
                "recommended"
                if stage.get("reasoning_effort") is not None
                else "unavailable"
            )
            reasoning_value = stage.get("reasoning_effort")
        else:
            model_kind = "unavailable"
            model_value = None
            model_coverage = "unavailable"
            reasoning_kind = "unavailable"
            reasoning_value = None
        stages.append(
            {
                "stage_id": stage_id,
                "kind": stage.get("kind"),
                "title": presentation["title"],
                "purpose": presentation["purpose"],
                "purpose_source": "assignment_kind_projection",
                "summary": {
                    "topic": presentation["purpose"],
                    "decision": None,
                    "result": None,
                    "decision_evidence": "unavailable",
                },
                "lane_id": lane_id,
                "rank": ranks.get(stage_id, 0),
                "position": index,
                "depends_on": list(stage.get("depends_on", [])),
                "status": {
                    "value": stage.get("status"),
                    "source": stage.get("status_evidence"),
                    "evidence_source": stage.get("evidence_source"),
                    "observed_at": stage.get("observed_at"),
                },
                "responsibility": {
                    "executor_id": stage.get("executor_id"),
                    "executor_source": (
                        "plan_summary"
                        if run.get("flow_evidence") == "assignment_observation"
                        else "run_receipt"
                    ),
                    "lens_ids": list(stage.get("lens_ids", [])),
                    "mutation_owner": stage.get("mutation_owner"),
                    "read_only": stage.get("read_only"),
                },
                "models": {
                    "requested": stage.get("requested_model"),
                    "requested_reasoning_effort": stage.get(
                        "requested_reasoning_effort"
                    ),
                    "route_recommended": stage.get(
                        "route_recommended_model"
                    ),
                    "route_recommended_reasoning_effort": stage.get(
                        "reasoning_effort"
                    ),
                    "applied": stage.get("applied_model"),
                    "applied_evidence": stage.get("model_evidence"),
                    "model_route_id": stage.get("model_route_id"),
                    "execution_unit_id": stage.get("execution_unit_id"),
                    "stage_kind": stage.get("stage_kind"),
                    "execution_kind": stage.get("execution_kind"),
                    "selected_class": stage.get("selected_class"),
                    "quality_profile": stage.get("quality_profile"),
                    "quality_floor": stage.get("quality_floor"),
                    "fallback_route": stage.get("fallback_route"),
                },
                "measurements": {
                    "duration_ms": stage.get("duration_ms"),
                    "tokens": stage.get("tokens"),
                },
                "execution_facts": {
                    "model": {
                        "kind": model_kind,
                        "value": model_value,
                        "coverage": model_coverage,
                    },
                    "reasoning": {
                        "kind": reasoning_kind,
                        "value": reasoning_value,
                    },
                    "tokens": {
                        "value": (
                            None
                            if deterministic_stage
                            else stage.get("tokens")
                        ),
                        "last": None,
                        "scope": (
                            "not_applicable"
                            if deterministic_stage
                            else (
                                "assignment"
                                if stage.get("tokens") is not None
                                else "unavailable"
                            )
                        ),
                        "attribution": (
                            "not_applicable"
                            if deterministic_stage
                            else (
                                "direct"
                                if stage.get("tokens") is not None
                                else "unavailable"
                            )
                        ),
                    },
                    "duration": {
                        "value_ms": stage.get("duration_ms"),
                        "state": (
                            "planned"
                            if stage.get("status") == "planned_only"
                            else "terminal"
                        ),
                        "coverage": (
                            "host_event"
                            if stage.get("duration_ms") is not None
                            and stage.get("evidence_source")
                            == "codex_app_server"
                            else (
                                "collector_clock"
                                if stage.get("duration_ms") is not None
                                else "unavailable"
                            )
                        ),
                    },
                },
                "evidence": {
                    "count": len(stage.get("evidence_refs", [])),
                    "refs": list(stage.get("evidence_refs", [])),
                },
                "expertise": {
                    "pack_ids": list(stage.get("expertise_pack_ids", [])),
                    "guide_ids": list(stage.get("decision_guide_ids", [])),
                    "evidence": (
                        "selection_only"
                        if stage.get("expertise_pack_ids")
                        else "unavailable"
                    ),
                    "host_load": "unavailable",
                    "application": "unavailable",
                },
                "detail_availability": {
                    "inputs": "unavailable",
                    "completion_criteria": "unavailable",
                    "findings": "unavailable",
                    "conclusion": "unavailable",
                    "typed_artifacts": "unavailable",
                    "handoff_history": "unavailable",
                },
            }
        )
        if isinstance(stage.get("model_feedback_ref"), dict):
            stages[-1]["model_feedback_ref"] = dict(
                stage["model_feedback_ref"]
            )

    lanes = sorted(
        lanes_by_id.values(),
        key=lambda lane: (
            _STAGE_LANE_ORDER.get(lane["lane_id"], 99),
            lane["label"],
        ),
    )
    models = run.get("models", {})
    plan = run.get("plan", {})
    receipt = run.get("receipt", {})
    observed_work = project_observed_work(
        run.get("work_spans"),
        flow,
    )
    feedback_by_assignment = {
        stage.get("assignment_id"): stage["model_feedback_ref"]
        for stage in flow
        if isinstance(stage.get("model_feedback_ref"), dict)
    }
    for card in observed_work.get("cards", []):
        assignment_id = card.get("assignment", {}).get("assignment_id")
        if assignment_id in feedback_by_assignment:
            card["model_feedback_ref"] = dict(
                feedback_by_assignment[assignment_id]
            )
    plan_edges = list(graph.get("edges", []))
    plan_display = build_display_edge_groups(
        [
            stage["stage_id"]
            for stage in stages
            if isinstance(stage.get("stage_id"), str)
        ],
        ranks,
        plan_edges,
        default_type="depends_on",
    )
    return {
        "schema_version": "maestro_work_detail_v2",
        "header": {
            "result": {
                "value": run.get("outcome"),
                "source": "run_receipt",
            },
            "verification": {
                "value": run.get("verifier_result"),
                "source": "run_receipt",
            },
            "duration": {
                "value_ms": run.get("duration_ms"),
                "source": run.get("measurement_provenance", {}).get(
                    "duration",
                    "unavailable",
                ),
            },
            "planning_duration": {
                "value_ms": run.get("planning_duration_ms"),
                "source": run.get("measurement_provenance", {}).get(
                    "planning_duration",
                    "unavailable",
                ),
            },
            "tokens": {
                "value": run.get("tokens"),
                "scope": run.get("token_scope", "unavailable"),
                "source": run.get("measurement_provenance", {}).get(
                    "tokens",
                    "unavailable",
                ),
            },
            "corrections": {
                "count": run.get("correction_count", 0),
                "summary": list(run.get("correction_summary", [])),
                "source": "run_receipt",
                "attempt_lineage": (
                    "observed_work"
                    if observed_work["summary"]["followup_count"]
                    else "unavailable"
                ),
                "observed_followups": observed_work["summary"][
                    "followup_count"
                ],
            },
            "models": {
                "requested": list(models.get("requested", [])),
                "requested_reasoning_effort": list(
                    models.get("requested_reasoning_effort", [])
                ),
                "route_recommended": list(
                    models.get("route_recommended", [])
                ),
                "route_recommended_reasoning_effort": list(
                    models.get(
                        "route_recommended_reasoning_effort",
                        [],
                    )
                ),
                "applied": list(models.get("applied", [])),
                "applied_evidence": models.get(
                    "model_event_evidence",
                    "unavailable",
                ),
            },
        },
        "responsibility": {
            "department": {
                "value": plan.get("department"),
                "source": plan.get("source", "unavailable"),
                "interpretation": "planned_classification",
            },
            "primary_executor": {
                "value": receipt.get("primary_executor_id"),
                "source": "run_receipt",
                "interpretation": "recorded_executor",
            },
        },
        "lanes": lanes,
        "stages": stages,
        "execution": observed_work,
        "graph": {
            "edges": plan_edges,
            "display_edge_groups": plan_display[
                "display_edge_groups"
            ],
            "detail_only_edge_indexes": plan_display[
                "detail_only_edge_indexes"
            ],
            "entry_stage_ids": list(
                graph.get("entry_assignment_ids", [])
            ),
            "terminal_stage_ids": list(
                graph.get("terminal_assignment_ids", [])
            ),
            "ordering_semantics": graph.get(
                "ordering_semantics",
                "unavailable",
            ),
            "actual_order": graph.get("actual_order", "unavailable"),
            "actual_concurrency": graph.get(
                "actual_concurrency",
                "unavailable",
            ),
            "max_rank": max(ranks.values(), default=0),
        },
        "limitations": {
            "actual_order": (
                "observed_relations"
                if observed_work["mode"] == "observed"
                else graph.get("actual_order", "unavailable")
            ),
            "actual_concurrency": graph.get(
                "actual_concurrency",
                "unavailable",
            ),
            "stage_retry_history": (
                "observed_work"
                if observed_work["summary"]["followup_count"]
                else "unavailable"
            ),
            "delegation_reports": (
                "observed_work"
                if observed_work["summary"]["report_count"]
                else "unavailable"
            ),
            "work_result_summaries": (
                "observed_work"
                if observed_work["mode"] == "observed"
                else "unavailable"
            ),
            "stage_findings": "unavailable",
            "stage_conclusions": "unavailable",
            "typed_artifacts": "unavailable",
            "guide_host_load": "unavailable",
            "guide_application": "unavailable",
            "verification_criteria": run.get("verification", {}).get(
                "criteria",
                "unavailable",
            ),
            "artifact_integrity": run.get("verification", {}).get(
                "artifact_integrity",
                "unavailable",
            ),
        },
    }


def _has_numeric_token_measurement(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and any(
            isinstance(item, int) and not isinstance(item, bool)
            for item in value.values()
        )
    )


def _aggregate_stage_tokens(
    flow: list[dict[str, Any]],
) -> dict[str, int] | None:
    measured = [
        stage["tokens"]
        for stage in flow
        if _has_numeric_token_measurement(stage.get("tokens"))
    ]
    if not measured:
        return None
    fields = {
        key
        for tokens in measured
        for key, value in tokens.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
    if not fields:
        return None
    return {
        field: sum(
            tokens.get(field, 0)
            for tokens in measured
            if isinstance(tokens.get(field, 0), int)
            and not isinstance(tokens.get(field, 0), bool)
        )
        for field in sorted(fields)
    }


def _host_model_provenance(
    host_observation: Any,
) -> dict[str, Any]:
    result = {
        "requested": None,
        "requested_reasoning_effort": None,
        "reasoning_effort_evidence": "unavailable",
        "applied": None,
        "evidence": "unavailable",
        "reroutes": [],
        "legacy_reported": None,
    }
    if not isinstance(host_observation, dict):
        return result
    if host_observation.get("schema_version") == "maestro_host_observation_v2":
        result["requested"] = host_observation.get("requested_model")
        result["requested_reasoning_effort"] = host_observation.get(
            "requested_reasoning_effort",
        )
        result["reasoning_effort_evidence"] = host_observation.get(
            "reasoning_effort_evidence",
            "unavailable",
        )
        result["evidence"] = host_observation.get(
            "model_event_evidence",
            "unavailable",
        )
        result["reroutes"] = list(host_observation.get("reroutes", []))
        if result["evidence"] == "complete":
            result["applied"] = host_observation.get("applied_model")
        return result
    if host_observation.get("schema_version") == "maestro_host_observation_v1":
        result["legacy_reported"] = host_observation.get("actual_model")
    return result


def _run_flow(event: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    plan = event.get("plan_summary")
    host_observation = event.get("host_observation")
    host_models = _host_model_provenance(host_observation)
    stage_results = {
        item["assignment_id"]: item
        for item in event.get("stage_results", [])
        if isinstance(item, dict) and isinstance(item.get("assignment_id"), str)
    }
    if not isinstance(plan, dict):
        return (
            [
                {
                    "assignment_id": "execution-summary",
                    "kind": "summary",
                    "executor_id": event.get("primary_executor_id"),
                    "depends_on": [],
                    "lens_ids": list(event.get("selected_lenses", [])),
                    "mutation_owner": None,
                    "read_only": None,
                    "planned_model": None,
                    "route_recommended_model": None,
                    "reasoning_effort": None,
                    "model_route_id": None,
                    "execution_unit_id": None,
                    "stage_kind": None,
                    "task_class": None,
                    "execution_kind": None,
                    "selected_class": None,
                    "quality_profile": None,
                    "quality_floor": None,
                    "fallback_route": None,
                    "requested_model": None,
                    "requested_reasoning_effort": None,
                    "actual_model": host_models["applied"],
                    "applied_model": host_models["applied"],
                    "legacy_reported_model": host_models["legacy_reported"],
                    "model_evidence": host_models["evidence"],
                    "reported_model_evidence": host_models["evidence"],
                    "status": event.get("outcome"),
                    "status_evidence": "run_receipt",
                    "evidence_source": None,
                    "observed_at": event.get("timestamp"),
                    "reroutes": list(host_models["reroutes"]),
                    "duration_ms": event.get("duration_ms"),
                    "tokens": event.get("tokens"),
                    "evidence_refs": list(event.get("evidence_refs", []))[:3],
                    "expertise_pack_ids": list(
                        event.get("selected_expertise_packs", [])
                    ),
                    "decision_guide_ids": list(
                        event.get("selected_decision_guides", [])
                    ),
                }
            ],
            "summary_only",
        )

    stages: list[dict[str, Any]] = []
    for assignment in plan.get("assignments", []):
        result = stage_results.get(assignment.get("assignment_id"), {})
        stage_observed = bool(result)
        reported_model_evidence = result.get(
            "model_evidence",
            "unavailable",
        )
        model_evidence = (
            "complete"
            if (
                reported_model_evidence == "complete"
                and result.get("evidence_source") == "codex_app_server"
            )
            else "unavailable"
        )
        applied_model = (
            result.get("actual_model")
            if model_evidence == "complete"
            else None
        )
        stages.append(
            {
                "assignment_id": assignment.get("assignment_id"),
                "kind": assignment.get("kind"),
                "executor_id": assignment.get("executor_id"),
                "depends_on": list(assignment.get("depends_on", [])),
                "lens_ids": list(assignment.get("lens_ids", [])),
                "mutation_owner": assignment.get("mutation_owner"),
                "read_only": assignment.get("read_only"),
                "planned_model": assignment.get("planned_model"),
                "route_recommended_model": assignment.get("planned_model"),
                "reasoning_effort": assignment.get("reasoning_effort"),
                "model_route_id": result.get(
                    "model_route_id",
                    assignment.get("model_route_id"),
                ),
                "execution_unit_id": result.get(
                    "execution_unit_id",
                    assignment.get("execution_unit_id"),
                ),
                "stage_kind": assignment.get("stage_kind"),
                "task_class": assignment.get("task_class"),
                "execution_kind": assignment.get("execution_kind"),
                "selected_class": assignment.get("selected_class"),
                "quality_profile": assignment.get("quality_profile"),
                "quality_floor": assignment.get("quality_floor"),
                "fallback_route": assignment.get("fallback_route"),
                "requested_model": result.get("requested_model"),
                "requested_reasoning_effort": result.get(
                    "requested_reasoning_effort",
                ),
                "actual_model": applied_model,
                "applied_model": applied_model,
                "legacy_reported_model": (
                    result.get("actual_model")
                    if result.get("actual_model") is not None
                    and model_evidence != "complete"
                    else None
                ),
                "model_evidence": model_evidence,
                "reported_model_evidence": reported_model_evidence,
                "status": result.get("status", "planned_only"),
                "status_evidence": (
                    (
                        {
                            "codex_app_server": "codex_app_server_event",
                            "current_host": "current_host_report",
                            "deterministic_command": "deterministic_command",
                        }.get(
                            result.get("evidence_source"),
                            "legacy_receipt",
                        )
                    )
                    if stage_observed
                    else "plan_only"
                ),
                "evidence_source": result.get("evidence_source"),
                "observed_at": result.get("observed_at"),
                "reroutes": list(result.get("reroutes", [])),
                "duration_ms": result.get("duration_ms"),
                "tokens": result.get("tokens"),
                "evidence_refs": list(result.get("evidence_refs", []))[:3],
                "expertise_pack_ids": list(
                    assignment.get("expertise_pack_ids", [])
                ),
                "decision_guide_ids": list(
                    assignment.get("decision_guide_ids", [])
                ),
            }
        )
    return stages, "assignment_observation"


def _plan_projection(event: dict[str, Any]) -> dict[str, Any]:
    plan = event.get("plan_summary")
    if not isinstance(plan, dict):
        return {
            "plan_id": None,
            "intent": None,
            "department": None,
            "risk": None,
            "depth": None,
            "source": "unavailable",
        }
    return {
        "plan_id": plan.get("plan_id"),
        "intent": plan.get("intent"),
        "department": plan.get("department"),
        "risk": plan.get("risk"),
        "depth": plan.get("depth"),
        "source": "plan_summary",
    }


def _flow_graph(
    flow: list[dict[str, Any]],
    flow_evidence: str,
) -> dict[str, Any]:
    if flow_evidence != "assignment_observation":
        return {
            "edges": [],
            "entry_assignment_ids": [],
            "terminal_assignment_ids": [],
            "ordering_semantics": "summary_only",
            "actual_order": "unavailable",
            "actual_concurrency": "unavailable",
        }
    assignment_ids = {
        stage["assignment_id"]
        for stage in flow
        if isinstance(stage.get("assignment_id"), str)
        and stage["assignment_id"]
    }
    edges = sorted(
        (
            {
                "from": dependency,
                "to": stage["assignment_id"],
                "source": "plan_summary",
            }
            for stage in flow
            for dependency in stage.get("depends_on", [])
            if dependency in assignment_ids
        ),
        key=lambda edge: (edge["from"], edge["to"]),
    )
    dependency_targets = {edge["from"] for edge in edges}
    return {
        "edges": edges,
        "entry_assignment_ids": sorted(
            stage["assignment_id"]
            for stage in flow
            if not stage.get("depends_on")
            and stage.get("assignment_id") in assignment_ids
        ),
        "terminal_assignment_ids": sorted(
            assignment_ids - dependency_targets
        ),
        "ordering_semantics": "planned_dependency",
        "actual_order": "unavailable",
        "actual_concurrency": "unavailable",
    }


def _receipt_projection(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": event.get("kind", "run_summary"),
        "fingerprint": event.get("fingerprint"),
        "finding_severity": event.get("finding_severity"),
        "human_fix_required": event.get("human_fix_required"),
        "decision_changed": event.get("decision_changed", False),
        "command_artifact_ref": event.get("command_artifact_ref"),
        "primary_executor_id": event.get("primary_executor_id"),
        "executor_ids": list(event.get("executor_ids", [])),
        "executor_runs": event.get("executor_runs"),
        "experiment_id": event.get("experiment_id"),
        "experiment_arm": event.get("experiment_arm"),
        "project_convention_action": event.get(
            "project_convention_action",
            "none",
        ),
        "project_convention_basis": event.get(
            "project_convention_basis",
            "none",
        ),
        "project_convention_path": event.get("project_convention_path"),
        "project_convention_evidence": event.get(
            "project_convention_evidence"
        ),
        "source": "run_receipt",
    }


def _verification_projection(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "result": event.get("verifier_result"),
        "command_artifact_ref": event.get("command_artifact_ref"),
        "evidence_refs": list(event.get("evidence_refs", []))[:8],
        "source": "run_receipt",
        "criteria": "unavailable",
        "artifact_integrity": "unavailable",
        "interpretation": (
            "The RunReceipt reports the verifier result and references. "
            "It does not define the verifier criteria or prove artifact "
            "integrity."
        ),
    }


def _measurement_provenance(
    event: dict[str, Any],
    *,
    token_scope: str,
) -> dict[str, str]:
    return {
        "duration": (
            "run_receipt"
            if event.get("duration_ms") is not None
            else "unavailable"
        ),
        "planning_duration": (
            "run_receipt"
            if event.get("planning_duration_ms") is not None
            else "unavailable"
        ),
        "tokens": token_scope,
        "agent_calls": (
            "run_receipt"
            if event.get("agent_calls") is not None
            else "unavailable"
        ),
        "corrections": "run_receipt",
    }


def _expertise_routing_projection(event: dict[str, Any]) -> dict[str, Any]:
    plan_summary = event.get("plan_summary")
    routing = (
        plan_summary.get("expertise_routing")
        if isinstance(plan_summary, dict)
        else None
    )
    if isinstance(routing, dict):
        return {
            **routing,
            "evidence": "plan_summary",
        }
    return {
        "schema_version": None,
        "selection_state": "unavailable",
        "selection_source": "unavailable",
        "route_attempt": None,
        "conflict_warning_codes": [],
        "evidence": "unavailable",
    }


def _attach_model_feedback_ref(
    flow: list[dict[str, Any]],
    *,
    event: dict[str, Any],
    history_evidence: dict[str, Any] | None,
    model_feedback_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Attach one observational aggregate only to its exact current subject."""

    if (
        not isinstance(history_evidence, dict)
        or history_evidence.get("governance_eligible") is not True
        or history_evidence.get("definition_status") != "current"
        or not isinstance(model_feedback_report, dict)
        or model_feedback_report.get("schema_version")
        != "maestro_model_feedback_report_v1"
    ):
        return None
    writers = [
        stage
        for stage in flow
        if stage.get("mutation_owner") is True
        and stage.get("execution_kind") == "model"
    ]
    if len(writers) != 1:
        return None
    writer = writers[0]
    subject = {
        "quality_profile": writer.get("quality_profile"),
        "stage_kind": writer.get("stage_kind"),
        "task_class": writer.get("task_class"),
        "selected_class": writer.get("selected_class"),
        "selected_model": writer.get("route_recommended_model"),
        "reasoning_effort": writer.get("reasoning_effort"),
        "risk": event.get("risk"),
    }
    matches = [
        group
        for group in model_feedback_report.get("groups", [])
        if isinstance(group, dict) and group.get("subject") == subject
    ]
    if len(matches) != 1:
        return None
    reference = {
        "report_id": model_feedback_report["report_id"],
        "group_id": matches[0]["group_id"],
        "subject": subject,
        "relation": "exact_current_subject",
        "interpretation": "observational-only",
    }
    writer["model_feedback_ref"] = dict(reference)
    return reference


def _run_card(
    event: dict[str, Any],
    display_labels: dict[str, str] | None = None,
    *,
    history_evidence: dict[str, Any] | None = None,
    model_feedback_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    flow, flow_evidence = _run_flow(event)
    model_feedback_ref = _attach_model_feedback_ref(
        flow,
        event=event,
        history_evidence=history_evidence,
        model_feedback_report=model_feedback_report,
    )
    host_observation = event.get("host_observation")
    host_models = _host_model_provenance(host_observation)
    execution_measurements = event.get("execution_measurements")
    has_canonical_measurements = isinstance(
        execution_measurements,
        dict,
    )
    event_id = event["event_id"]
    original_task_label = event.get("task_label") or event["run_id"]
    task_label = (display_labels or {}).get(
        event_id,
        original_task_label,
    )
    route_recommended = _unique_strings(
        [stage.get("route_recommended_model") for stage in flow]
    )
    route_recommended_effort = _unique_strings(
        [stage.get("reasoning_effort") for stage in flow]
    )
    observed_applied = _unique_strings(
        [
            host_models["applied"],
            *[stage.get("applied_model") for stage in flow],
        ]
    )
    requested = _unique_strings(
        [
            host_models["requested"],
            *[stage.get("requested_model") for stage in flow],
        ]
    )
    requested_effort = _unique_strings(
        [
            host_models["requested_reasoning_effort"],
            *[
                stage.get("requested_reasoning_effort")
                for stage in flow
            ],
        ]
    )
    if has_canonical_measurements:
        requested = list(
            execution_measurements.get("model", {}).get(
                "requested",
                [],
            )
        )
        requested_effort = list(
            execution_measurements.get("reasoning_effort", {}).get(
                "requested",
                [],
            )
        )
        observed_applied = list(
            execution_measurements.get("model", {}).get(
                "applied",
                [],
            )
        )
    event_tokens = event.get("tokens")
    stage_tokens = _aggregate_stage_tokens(flow)
    canonical_tokens = (
        execution_measurements.get("tokens", {}).get("value")
        if has_canonical_measurements
        else None
    )
    canonical_duration = (
        execution_measurements.get("duration", {}).get("value_ms")
        if has_canonical_measurements
        else None
    )
    displayed_duration = (
        canonical_duration
        if isinstance(canonical_duration, (int, float))
        and not isinstance(canonical_duration, bool)
        else event.get("duration_ms")
    )
    displayed_tokens = canonical_tokens or event_tokens or stage_tokens
    token_scope = (
        "execution_ledger"
        if canonical_tokens is not None
        else (
            "run_receipt"
            if isinstance(event_tokens, dict)
            else (
                "observed_stages_aggregate"
                if isinstance(stage_tokens, dict)
                else "unavailable"
            )
        )
    )
    stage_tracking_available = flow_evidence == "assignment_observation"
    recorded_stage_count = (
        sum(
            stage.get("status_evidence") != "plan_only"
            for stage in flow
        )
        if stage_tracking_available
        else 0
    )
    model_stage_count = sum(
        bool(stage.get("route_recommended_model"))
        and stage.get("evidence_source") != "deterministic_command"
        for stage in flow
    )
    measured_model_stage_count = sum(
        bool(stage.get("applied_model"))
        and stage.get("model_evidence") == "complete"
        for stage in flow
    )
    stage_model_evidence = (
        "complete"
        if (
            model_stage_count > 0
            and measured_model_stage_count == model_stage_count
        )
        else (
            "partial"
            if measured_model_stage_count > 0
            else "unavailable"
        )
    )
    model_event_evidence = (
        execution_measurements.get("model", {}).get("coverage")
        if has_canonical_measurements
        else (
            "complete"
            if (
                host_models["evidence"] == "complete"
                or stage_model_evidence == "complete"
            )
            else stage_model_evidence
        )
    )
    applied = (
        observed_applied
        if model_event_evidence == "complete"
        else []
    )
    measured_duration_stage_count = sum(
        stage.get("duration_ms") is not None
        for stage in flow
    )
    measured_token_stage_count = sum(
        _has_numeric_token_measurement(stage.get("tokens"))
        for stage in flow
    )
    selected_packs = list(event.get("selected_expertise_packs", []))
    selected_guides = list(event.get("selected_decision_guides", []))
    expertise_assignment_ids = _unique_strings(
        [
            stage.get("assignment_id")
            for stage in flow
            if stage.get("expertise_pack_ids")
            or stage.get("decision_guide_ids")
        ]
    )
    measurement_provenance = _measurement_provenance(
        event,
        token_scope=token_scope,
    )
    if canonical_duration is not None:
        duration_coverage = execution_measurements.get(
            "duration",
            {},
        ).get("coverage", "unavailable")
        measurement_provenance["duration"] = (
            f"execution_ledger_{duration_coverage}"
        )
    run = {
        "event_id": event_id,
        "run_id": event["run_id"],
        "task_label": task_label,
        "original_task_label": original_task_label,
        "history_evidence": (
            dict(history_evidence)
            if isinstance(history_evidence, dict)
            else {
                "classification": "unavailable",
                "history_visibility": "visible",
                "governance_eligible": None,
                "definition_status": "unavailable",
                "reason": "projection_unavailable",
            }
        ),
        "timestamp": event["timestamp"],
        "risk": event["risk"],
        "route_depth": event["route_depth"],
        "outcome": event["outcome"],
        "verifier_result": event["verifier_result"],
        "duration_ms": displayed_duration,
        "planning_duration_ms": event.get("planning_duration_ms"),
        "tokens": displayed_tokens,
        "token_scope": (
            "execution_ledger"
            if token_scope == "execution_ledger"
            else (
                "run"
                if token_scope == "run_receipt"
                else (
                    "observed_stages"
                    if token_scope == "observed_stages_aggregate"
                    else "unavailable"
                )
            )
        ),
        "measurement_provenance": measurement_provenance,
        "stage_coverage": {
            "available": stage_tracking_available,
            "recorded": recorded_stage_count,
            "planned": len(flow) if stage_tracking_available else 0,
            "complete": (
                stage_tracking_available
                and bool(flow)
                and recorded_stage_count == len(flow)
            ),
        },
        "stage_telemetry": {
            "model_expected": model_stage_count,
            "model_measured": measured_model_stage_count,
            "duration_measured": measured_duration_stage_count,
            "tokens_measured": measured_token_stage_count,
            "complete": (
                model_stage_count > 0
                and measured_model_stage_count == model_stage_count
            ),
        },
        "execution_binding": event.get("execution_binding"),
        "execution_measurements": execution_measurements,
        "agent_calls": event.get("agent_calls"),
        "correction_count": event.get("correction_count", 0),
        "correction_summary": list(event.get("correction_summary", [])),
        "models": {
            "requested": requested,
            "requested_reasoning_effort": requested_effort,
            "applied": applied,
            "route_recommended": route_recommended,
            "route_recommended_reasoning_effort": (
                route_recommended_effort
            ),
            "reasoning_effort_evidence": host_models[
                "reasoning_effort_evidence"
            ],
            "model_event_evidence": model_event_evidence,
            "host_model_event_evidence": host_models["evidence"],
            "applied_model_provenance": {
                "host_observation": host_models["evidence"],
                "observed_stages": stage_model_evidence,
                "observed_stage_count": measured_model_stage_count,
            },
            "reroutes": host_models["reroutes"],
            "legacy_reported": _unique_strings(
                [host_models["legacy_reported"]]
            ),
            "planned": route_recommended,
            "actual": applied,
            "estimated": False,
            "measurement_state": (
                "host_event_stream_complete"
                if (
                    has_canonical_measurements
                    and model_event_evidence == "complete"
                    and host_models["evidence"] == "complete"
                )
                else (
                    "execution_ledger_complete"
                    if (
                        has_canonical_measurements
                        and model_event_evidence == "complete"
                    )
                    else (
                        "execution_ledger_request_only"
                        if (
                            has_canonical_measurements
                            and model_event_evidence == "request_only"
                            and host_observation is None
                        )
                        else (
                            "host_request_observed"
                            if (
                                has_canonical_measurements
                                and model_event_evidence == "request_only"
                            )
                            else (
                                "execution_ledger_unavailable"
                                if has_canonical_measurements
                                else (
                                    "host_event_stream_complete"
                                    if model_event_evidence == "complete"
                                    else (
                                        "host_not_connected"
                                        if host_observation is None
                                        else "host_request_observed"
                                    )
                                )
                            )
                        )
                    )
                )
            ),
        },
        "host_observation": host_observation,
        "plan": _plan_projection(event),
        "flow_evidence": flow_evidence,
        "flow": flow,
        "flow_graph": _flow_graph(flow, flow_evidence),
        "receipt": _receipt_projection(event),
        "verification": _verification_projection(event),
        "lenses": list(event.get("selected_lenses", [])),
        "expertise": {
            "packs": selected_packs,
            "guides": selected_guides,
            "research_mode": event.get("expertise_research_mode", "reuse"),
            "research_gate": event.get(
                "expertise_research_gate",
                "not-required",
            ),
            "observations": list(event.get("expertise_observations", [])),
            "routing": _expertise_routing_projection(event),
            "evidence": {
                "selection": (
                    "run_receipt"
                    if selected_packs or selected_guides
                    else "not_selected"
                ),
                "assignment_attachment": (
                    "plan_projection"
                    if expertise_assignment_ids
                    else "unavailable"
                ),
                "assignment_ids": expertise_assignment_ids,
                "host_load": "unavailable",
                "application": "unavailable",
                "interpretation": (
                    "Selection and Assignment projection do not prove that "
                    "the Host loaded or applied the Guide body."
                ),
            },
        },
        "conventions": event.get("convention_usage"),
        "evidence_refs": list(event.get("evidence_refs", []))[:8],
        "work_spans": list(event.get("work_spans", [])),
    }
    if model_feedback_ref is not None:
        run["model_feedback_ref"] = model_feedback_ref
    run["work_detail"] = _work_detail_projection(run)
    return run


def _measurement_coverage(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(records)

    def measured(predicate: Any) -> dict[str, Any]:
        count = sum(bool(predicate(record)) for record in records)
        return {
            "scope": "request_records",
            "measured_requests": count,
            "total_requests": total,
            "measured_runs": count,
            "total_runs": total,
            "ratio": round(count / total, 3) if total else None,
        }

    return {
        "task_label": measured(
            lambda run: run["task_label"] != run["run_id"]
        ),
        "duration": measured(lambda run: run.get("duration_ms") is not None),
        "tokens": measured(
            lambda run: (
                _has_numeric_token_measurement(run.get("tokens"))
                or (
                    isinstance(
                        run.get("request_measurement", {}).get(
                            "token_measured_attempts"
                        ),
                        int,
                    )
                    and run["request_measurement"][
                        "token_measured_attempts"
                    ]
                    > 0
                )
            )
        ),
        "token_aggregate": measured(
            lambda run: _has_numeric_token_measurement(run.get("tokens"))
        ),
        "plan": measured(
            lambda run: run.get("flow_evidence") == "assignment_observation"
        ),
        "observed_work": measured(
            lambda run: bool(run.get("work_spans"))
        ),
        "actual_model": measured(
            lambda run: bool(run.get("models", {}).get("applied"))
        ),
        "requested_model": measured(
            lambda run: bool(run.get("models", {}).get("requested"))
        ),
        "requested_reasoning_effort": measured(
            lambda run: bool(
                run.get("models", {}).get(
                    "requested_reasoning_effort",
                )
            )
        ),
        "interpretation": (
            "측정되지 않은 값은 추정하지 않는다. 공개 Host 요청 메타데이터는 "
            "요청값만, 완료 이벤트 구간은 적용 모델과 토큰까지 표시한다."
        ),
    }
