from __future__ import annotations

from copy import deepcopy
from typing import Any

from .errors import MaestroError
from .request_lineage import resolve_request_identity
from .work import build_display_edge_groups


REQUEST_RECORD_VERSION = "maestro_request_record_v1"
_ORDERING_EDGE_TYPES = {
    "delegates_to",
    "depends_on",
    "followup_of",
    "joins_into",
}


def _unique_strings(values: list[Any]) -> list[str]:
    return list(
        dict.fromkeys(
            value
            for value in values
            if isinstance(value, str) and value
        )
    )


def _attempt_started_at(run: dict[str, Any]) -> str:
    host = run.get("host_observation")
    if (
        isinstance(host, dict)
        and isinstance(host.get("observed_at"), str)
        and host["observed_at"]
    ):
        return host["observed_at"]
    return run.get("timestamp", "")


def _sum_numeric_maps(values: list[Any]) -> dict[str, int] | None:
    measured = [
        value
        for value in values
        if isinstance(value, dict)
        and any(
            isinstance(item, int) and not isinstance(item, bool)
            for item in value.values()
        )
    ]
    if not measured:
        return None
    fields = {
        key
        for value in measured
        for key, item in value.items()
        if isinstance(item, int) and not isinstance(item, bool)
    }
    return {
        field: sum(
            value.get(field, 0)
            for value in measured
            if isinstance(value.get(field, 0), int)
            and not isinstance(value.get(field, 0), bool)
        )
        for field in sorted(fields)
    }


def _measured_work_models(run: dict[str, Any]) -> list[str]:
    measured = list(run.get("models", {}).get("applied", []))
    for card in (
        run.get("work_detail", {})
        .get("execution", {})
        .get("cards", [])
    ):
        fact = card.get("execution_facts", {}).get("model", {})
        if (
            fact.get("kind") == "actual"
            and fact.get("coverage") == "complete_stream"
        ):
            measured.append(fact.get("value"))
    return _unique_strings(measured)


def _measured_attempt_tokens(run: dict[str, Any]) -> dict[str, int] | None:
    direct = _sum_numeric_maps([run.get("tokens")])
    if direct is not None:
        return direct
    work_totals = []
    for card in (
        run.get("work_detail", {})
        .get("execution", {})
        .get("cards", [])
    ):
        fact = card.get("execution_facts", {}).get("tokens", {})
        if (
            fact.get("attribution") == "direct"
            and fact.get("scope") in {"assignment", "work_turn"}
        ):
            work_totals.append(fact.get("value"))
    return _sum_numeric_maps(work_totals)


def _attempt_token_measurement(run: dict[str, Any]) -> dict[str, Any]:
    value = _measured_attempt_tokens(run)
    if value is None:
        return {"value": None, "scope": "unavailable"}
    if isinstance(run.get("tokens"), dict):
        scope = run.get("token_scope", "unavailable")
    else:
        scope = "observed_work"
    return {
        "value": value,
        "scope": (
            scope
            if isinstance(scope, str) and scope
            else "unavailable"
        ),
    }


def _sum_numbers(values: list[Any]) -> float | int | None:
    measured = [
        value
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return sum(measured) if measured else None


def _attempt_coverage(measured: int, total: int) -> str:
    if measured <= 0:
        return "unavailable"
    if measured == total:
        return "complete"
    return "partial"


def _namespaced(identifier: Any, attempt: int) -> Any:
    if not isinstance(identifier, str) or not identifier:
        return identifier
    return f"attempt-{attempt}:{identifier}"


def _rewrite_ids(values: Any, attempt: int) -> list[str]:
    if not isinstance(values, list):
        return []
    return [
        _namespaced(value, attempt)
        for value in values
        if isinstance(value, str) and value
    ]


def _merge_observed_execution(
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    cards: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    lanes_by_id: dict[str, dict[str, Any]] = {}
    concurrent_pairs: list[list[str]] = []
    entries_by_run: dict[str, list[str]] = {}
    terminals_by_run: dict[str, list[str]] = {}
    next_rank = 0
    completeness: list[str] = []
    concurrency_coverage: list[str] = []

    for attempt, run in enumerate(attempts, 1):
        work_detail = run.get("work_detail", {})
        execution = work_detail.get("execution", {})
        source_cards = execution.get("cards", [])
        if not isinstance(source_cards, list) or not source_cards:
            continue
        source_stage_routes = {
            stage["stage_id"]: deepcopy(stage.get("models"))
            for stage in work_detail.get("stages", [])
            if isinstance(stage, dict)
            and isinstance(stage.get("stage_id"), str)
            and isinstance(stage.get("models"), dict)
        }
        source_graph = execution.get("graph", {})
        source_concurrency = source_graph.get(
            "actual_concurrency",
            "unavailable",
        )
        concurrency_coverage.append(
            source_concurrency
            if source_concurrency in {"observed", "none_observed"}
            else "unavailable"
        )
        source_ranks = [
            card.get("rank", 0)
            for card in source_cards
            if isinstance(card.get("rank", 0), int)
        ]
        minimum_rank = min(source_ranks, default=0)
        rank_shift = next_rank - minimum_rank
        attempt_ids = {
            card["work_id"]: _namespaced(card["work_id"], attempt)
            for card in source_cards
            if isinstance(card.get("work_id"), str)
        }

        for source_card in source_cards:
            card = deepcopy(source_card)
            assignment = card.get("assignment")
            if isinstance(assignment, dict) and not isinstance(
                assignment.get("model_route"),
                dict,
            ):
                source_route = source_stage_routes.get(
                    assignment.get("assignment_id")
                )
                if isinstance(source_route, dict):
                    assignment["model_route"] = source_route
            card["source_work_id"] = source_card["work_id"]
            card["source_run_id"] = run["run_id"]
            card["request_attempt"] = attempt
            card["work_id"] = attempt_ids[source_card["work_id"]]
            card["rank"] = source_card.get("rank", 0) + rank_shift
            card["position"] = len(cards)
            relationships = card.get("relationships", {})
            for field in ("parent_work_id", "followup_of_work_id"):
                relationships[field] = attempt_ids.get(
                    relationships.get(field),
                    relationships.get(field),
                )
            for field in ("depends_on_work_ids", "joins_work_ids"):
                relationships[field] = [
                    attempt_ids.get(item, item)
                    for item in relationships.get(field, [])
                ]
            cards.append(card)

        for source_edge in source_graph.get("edges", []):
            edge = deepcopy(source_edge)
            edge["from"] = attempt_ids.get(edge.get("from"), edge.get("from"))
            edge["to"] = attempt_ids.get(edge.get("to"), edge.get("to"))
            edge["request_attempt"] = attempt
            edges.append(edge)

        entries = [
            attempt_ids[item]
            for item in source_graph.get("entry_work_ids", [])
            if item in attempt_ids
        ]
        terminals = [
            attempt_ids[item]
            for item in source_graph.get("terminal_work_ids", [])
            if item in attempt_ids
        ]
        if not entries:
            entries = [
                card["work_id"]
                for card in cards
                if card.get("request_attempt") == attempt
                and card.get("rank") == next_rank
            ]
        entries_by_run[run["run_id"]] = entries
        terminals_by_run[run["run_id"]] = terminals or entries
        next_rank = max(
            (
                card["rank"]
                for card in cards
                if card.get("request_attempt") == attempt
            ),
            default=next_rank,
        ) + 1

        for lane in execution.get("lanes", []):
            lane_id = lane.get("lane_id")
            if not isinstance(lane_id, str):
                continue
            merged = lanes_by_id.setdefault(
                lane_id,
                {
                    **deepcopy(lane),
                    "work_ids": [],
                },
            )
            merged["work_ids"].extend(
                attempt_ids[item]
                for item in lane.get("work_ids", [])
                if item in attempt_ids
            )
        for binding in execution.get("bindings", []):
            rewritten = deepcopy(binding)
            rewritten["work_id"] = attempt_ids.get(
                rewritten.get("work_id"),
                rewritten.get("work_id"),
            )
            rewritten["request_attempt"] = attempt
            bindings.append(rewritten)
        for pair in source_graph.get("concurrent_work_pairs", []):
            rewritten = [
                attempt_ids[item]
                for item in pair
                if item in attempt_ids
            ]
            if len(rewritten) == 2:
                concurrent_pairs.append(rewritten)
        completeness.append(execution.get("completeness", "unavailable"))

    if not cards:
        return None
    for run in attempts:
        identity = resolve_request_identity(run)
        if identity["relation"] != "retry":
            continue
        parent_run_id = identity["parent_run_id"]
        for source in terminals_by_run.get(parent_run_id, []):
            for target in entries_by_run.get(run["run_id"], []):
                edges.append(
                    {
                        "from": source,
                        "to": target,
                        "type": "followup_of",
                        "provenance": "request_record_projection",
                        "source": "explicit_request_lineage",
                        "coverage": "explicit_retry_parent",
                    }
                )

    ranks = {card["work_id"]: card["rank"] for card in cards}
    node_ids = [card["work_id"] for card in cards]
    display = build_display_edge_groups(node_ids, ranks, edges)
    entry_work_ids = [
        node_id
        for node_id in node_ids
        if not any(
            edge.get("to") == node_id
            and edge.get("type") in _ORDERING_EDGE_TYPES
            for edge in edges
        )
    ]
    terminal_work_ids = [
        node_id
        for node_id in node_ids
        if not any(
            edge.get("from") == node_id
            and edge.get("type") in _ORDERING_EDGE_TYPES
            for edge in edges
        )
    ]
    edge_counts: dict[str, int] = {}
    for edge in edges:
        edge_type = edge.get("type")
        if isinstance(edge_type, str):
            edge_counts[edge_type] = edge_counts.get(edge_type, 0) + 1
    return {
        "schema_version": "maestro_observed_work_projection_v2",
        "mode": "observed",
        "completeness": (
            "complete"
            if completeness and all(item == "complete" for item in completeness)
            else "partial"
        ),
        "cards": cards,
        "lanes": list(lanes_by_id.values()),
        "graph": {
            "edges": edges,
            "display_edge_groups": display["display_edge_groups"],
            "detail_only_edge_indexes": display[
                "detail_only_edge_indexes"
            ],
            "entry_work_ids": entry_work_ids,
            "terminal_work_ids": terminal_work_ids,
            "max_rank": max(ranks.values(), default=0),
            "actual_concurrency": (
                "observed"
                if concurrent_pairs
                else (
                    "none_observed"
                    if concurrency_coverage
                    and all(
                        item == "none_observed"
                        for item in concurrency_coverage
                    )
                    else "unavailable"
                )
            ),
            "concurrent_work_pairs": concurrent_pairs,
        },
        "bindings": bindings,
        "summary": {
            "work_count": len(cards),
            "delegation_count": edge_counts.get("delegates_to", 0),
            "report_count": edge_counts.get("reports_to", 0),
            "join_count": edge_counts.get("joins_into", 0),
            "followup_count": edge_counts.get("followup_of", 0),
        },
    }


def _request_work_detail(
    record: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    work = deepcopy(record.get("work_detail", {}))
    execution = _merge_observed_execution(attempts)
    if execution is not None:
        work["execution"] = execution
        work.setdefault("limitations", {})["stage_retry_history"] = (
            "request_record_projection"
        )
        work["limitations"]["delegation_reports"] = (
            "observed_work"
            if execution["summary"]["report_count"]
            else "unavailable"
        )
        work["limitations"]["work_result_summaries"] = "observed_work"
    header = work.setdefault("header", {})
    header["result"] = {
        "value": record.get("outcome"),
        "source": "latest_request_attempt",
    }
    header["verification"] = {
        "value": record.get("verifier_result"),
        "source": "latest_request_attempt",
    }
    header["duration"] = {
        "value_ms": record.get("duration_ms"),
        "source": record.get("measurement_provenance", {}).get(
            "duration",
            "unavailable",
        ),
    }
    header["planning_duration"] = {
        "value_ms": record.get("planning_duration_ms"),
        "source": record.get("measurement_provenance", {}).get(
            "planning_duration",
            "unavailable",
        ),
    }
    header["tokens"] = {
        "value": record.get("tokens"),
        "scope": record.get("token_scope", "unavailable"),
        "source": record.get("measurement_provenance", {}).get(
            "tokens",
            "unavailable",
        ),
    }
    header["corrections"] = {
        "count": record.get("correction_count", 0),
        "summary": list(record.get("correction_summary", [])),
        "source": "request_attempt_lineage",
        "attempt_lineage": "request_record_projection",
        "observed_followups": sum(
            resolve_request_identity(run)["relation"] == "retry"
            for run in attempts
        ),
    }
    header["models"] = {
        "requested": list(record.get("models", {}).get("requested", [])),
        "requested_reasoning_effort": list(
            record.get("models", {}).get(
                "requested_reasoning_effort",
                [],
            )
        ),
        "route_recommended": list(
            record.get("models", {}).get("route_recommended", [])
        ),
        "route_recommended_reasoning_effort": list(
            record.get("models", {}).get(
                "route_recommended_reasoning_effort",
                [],
            )
        ),
        "applied": list(record.get("models", {}).get("applied", [])),
        "applied_evidence": record.get("models", {}).get(
            "model_event_evidence",
            "unavailable",
        ),
    }
    return work


def _unique_pairs(
    values: list[dict[str, Any]],
) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        pack_id = value.get("expertise_pack_id")
        guide_id = value.get("guide_id")
        if not isinstance(pack_id, str) or not isinstance(guide_id, str):
            continue
        key = (pack_id, guide_id)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(
            {
                "expertise_pack_id": pack_id,
                "guide_id": guide_id,
            }
        )
    return pairs


def _request_expertise_evidence(
    expertise: dict[str, Any],
    attempts: list[dict[str, Any]],
    cards: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_packs = list(expertise.get("packs", []))
    selected_guides = list(expertise.get("guides", []))
    evidence_cards = [
        card
        for card in cards
        if isinstance(card, dict)
        and isinstance(card.get("work_id"), str)
        and isinstance(card.get("expertise"), dict)
    ]
    expected = [
        card
        for card in evidence_cards
        if (
            set(card["expertise"].get("pack_ids", []))
            & set(selected_packs)
            or set(card["expertise"].get("guide_ids", []))
            & set(selected_guides)
        )
    ]
    loaded = [
        card
        for card in expected
        if card["expertise"].get("load", {}).get("status")
        == "host_loaded"
    ]
    applied = [
        card
        for card in loaded
        if card["expertise"].get("application", {}).get("status")
        == "observed"
    ]
    not_applicable = [
        card
        for card in loaded
        if card["expertise"].get("application", {}).get("status")
        == "not_applicable"
    ]
    loaded_pairs = _unique_pairs(
        [
            {
                "expertise_pack_id": pack.get(
                    "expertise_pack_id"
                ),
                "guide_id": guide_id,
            }
            for card in loaded
            for pack in card["expertise"].get("packs", [])
            if isinstance(pack, dict)
            for guide_id in pack.get("guide_ids", [])
        ]
    )
    applied_pairs = _unique_pairs(
        [
            {
                "expertise_pack_id": pack.get(
                    "expertise_pack_id"
                ),
                "guide_id": guide_id,
            }
            for card in applied
            for guide_id in (
                card["expertise"]
                .get("application", {})
                .get("guide_ids", [])
            )
            for pack in card["expertise"].get("packs", [])
            if isinstance(pack, dict)
            and guide_id in pack.get("guide_ids", [])
        ]
    )
    expected_ids = _unique_strings(
        [card["work_id"] for card in expected]
    )
    loaded_ids = _unique_strings(
        [card["work_id"] for card in loaded]
    )
    applied_ids = _unique_strings(
        [card["work_id"] for card in applied]
    )
    not_applicable_ids = _unique_strings(
        [card["work_id"] for card in not_applicable]
    )
    no_selection = not selected_packs and not selected_guides
    resolved_ids = set(applied_ids) | set(not_applicable_ids)
    host_load = (
        "not_selected"
        if no_selection
        else (
            "complete"
            if expected_ids and set(expected_ids) == set(loaded_ids)
            else ("partial" if loaded_ids else "unavailable")
        )
    )
    application = (
        "not_selected"
        if no_selection
        else (
            "observed"
            if (
                expected_ids
                and set(expected_ids) == resolved_ids
                and applied_ids
            )
            else (
                "not_applicable"
                if (
                    expected_ids
                    and set(expected_ids)
                    == set(not_applicable_ids)
                )
                else (
                    "partial"
                    if resolved_ids
                    else "unavailable"
                )
            )
        )
    )
    assignment_ids = _unique_strings(
        [
            assignment_id
            for run in attempts
            for assignment_id in (
                run.get("expertise", {})
                .get("evidence", {})
                .get("assignment_ids", [])
            )
        ]
    )
    return {
        "selection": (
            "not_selected"
            if no_selection
            else "run_receipt"
        ),
        "assignment_attachment": (
            "plan_projection"
            if assignment_ids
            else "unavailable"
        ),
        "assignment_ids": assignment_ids,
        "host_load": host_load,
        "application": application,
        "work_ids": {
            "expected": expected_ids,
            "loaded": loaded_ids,
            "applied": applied_ids,
            "not_applicable": not_applicable_ids,
        },
        "counts": {
            "expected": len(expected_ids),
            "loaded": len(loaded_ids),
            "applied": len(applied_ids),
            "not_applicable": len(not_applicable_ids),
        },
        "loaded_pairs": loaded_pairs,
        "applied_pairs": applied_pairs,
        "interpretation": (
            "Request-level Expertise evidence is recomputed from the "
            "exact namespaced work cards of every source run."
        ),
    }


def _project_group(
    grouped_runs: list[dict[str, Any]],
    request_record_id: str,
    identity_evidence: str,
    root_request_id: str | None,
    root_run_id: str | None,
) -> dict[str, Any]:
    attempts = sorted(
        grouped_runs,
        key=lambda run: (
            _attempt_started_at(run),
            run.get("timestamp", ""),
        ),
    )
    latest = attempts[-1]
    record = deepcopy(latest)
    attempt_token_measurements = [
        _attempt_token_measurement(run)
        for run in attempts
    ]
    attempt_tokens = [
        measurement["value"]
        for measurement in attempt_token_measurements
    ]
    attempt_models = [_measured_work_models(run) for run in attempts]
    measured_token_scopes = _unique_strings(
        [
            measurement["scope"]
            for measurement in attempt_token_measurements
            if measurement["value"] is not None
        ]
    )
    compatible_token_scopes = len(measured_token_scopes) <= 1
    tokens = (
        _sum_numeric_maps(attempt_tokens)
        if compatible_token_scopes
        else None
    )
    duration = _sum_numbers([run.get("duration_ms") for run in attempts])
    planning_duration = _sum_numbers(
        [run.get("planning_duration_ms") for run in attempts]
    )
    token_measured = sum(value is not None for value in attempt_tokens)
    model_measured = sum(bool(value) for value in attempt_models)
    duration_measured = sum(
        isinstance(run.get("duration_ms"), (int, float))
        and not isinstance(run.get("duration_ms"), bool)
        for run in attempts
    )
    planning_duration_measured = sum(
        isinstance(run.get("planning_duration_ms"), (int, float))
        and not isinstance(run.get("planning_duration_ms"), bool)
        for run in attempts
    )
    reasoning_requested = sum(
        bool(
            run.get("models", {}).get(
                "requested_reasoning_effort",
                [],
            )
        )
        for run in attempts
    )
    source_event_ids = [run["event_id"] for run in attempts]
    source_run_ids = [run["run_id"] for run in attempts]
    attempt_history_evidence = [
        deepcopy(run.get("history_evidence", {}))
        for run in attempts
    ]
    governance_eligible_attempts = sum(
        evidence.get("governance_eligible") is True
        for evidence in attempt_history_evidence
    )
    definition_states = {
        evidence.get("definition_status")
        for evidence in attempt_history_evidence
        if evidence.get("definition_status")
        in {"current", "historical"}
    }
    request_definition_status = (
        next(iter(definition_states))
        if len(definition_states) == 1
        else ("mixed" if definition_states else "unavailable")
    )
    prior_failures = sum(
        run.get("outcome") in {"failed", "blocked", "corrected"}
        for run in attempts[:-1]
    )
    identities = [resolve_request_identity(run) for run in attempts]
    explicit_retry_count = sum(
        identity["relation"] == "retry"
        for identity in identities
    )
    rework_count = (
        explicit_retry_count
        if identity_evidence
        in {
            "explicit_request_lineage",
            "content_addressed_legacy_alias",
            "mixed_structural_lineage",
        }
        else prior_failures
    )

    record.update(
        {
            "schema_version": REQUEST_RECORD_VERSION,
            "request_record_id": request_record_id,
            "request_identity_evidence": identity_evidence,
            "source_event_ids": source_event_ids,
            "source_run_ids": source_run_ids,
            "attempt_count": len(attempts),
            "rework_count": rework_count,
            "history_evidence": {
                "definition_status": request_definition_status,
                "governance_eligible": (
                    governance_eligible_attempts == len(attempts)
                ),
                "governance_eligible_attempts": (
                    governance_eligible_attempts
                ),
                "attempts_total": len(attempts),
                "latest_attempt": deepcopy(
                    latest.get("history_evidence", {})
                ),
            },
            "duration_ms": duration,
            "planning_duration_ms": planning_duration,
            "tokens": tokens,
            "token_scope": (
                (
                    "measured_"
                    f"{measured_token_scopes[0]}_attempts"
                )
                if tokens is not None
                and measured_token_scopes
                else (
                    "mixed_attempt_scopes"
                    if not compatible_token_scopes
                    else "unavailable"
                )
            ),
            "correction_count": sum(
                run.get("correction_count", 0)
                for run in attempts
            )
            + rework_count,
            "correction_summary": _unique_strings(
                [
                    *[
                        summary
                        for run in attempts
                        for summary in run.get("correction_summary", [])
                    ],
                    *(
                        [
                            f"{rework_count}개 명시적 재시도"
                        ]
                        if rework_count
                        else []
                    ),
                ]
            ),
        }
    )
    if root_request_id is not None:
        record["root_request_id"] = root_request_id
        record["root_run_id"] = root_run_id or attempts[0]["run_id"]
    record["models"] = {
        **deepcopy(latest.get("models", {})),
        "requested": _unique_strings(
            [
                value
                for run in attempts
                for value in run.get("models", {}).get("requested", [])
            ]
        ),
        "requested_reasoning_effort": _unique_strings(
            [
                value
                for run in attempts
                for value in run.get("models", {}).get(
                    "requested_reasoning_effort",
                    [],
                )
            ]
        ),
        "applied": _unique_strings(
            [
                value
                for models in attempt_models
                for value in models
            ]
        ),
        "route_recommended": _unique_strings(
            [
                value
                for run in attempts
                for value in run.get("models", {}).get(
                    "route_recommended",
                    [],
                )
            ]
        ),
        "route_recommended_reasoning_effort": _unique_strings(
            [
                value
                for run in attempts
                for value in run.get("models", {}).get(
                    "route_recommended_reasoning_effort",
                    [],
                )
            ]
        ),
        "model_event_evidence": (
            "complete"
            if model_measured == len(attempts)
            else ("partial" if model_measured else "unavailable")
        ),
        "measurement_state": (
            "request_attempts_measured"
            if (
                model_measured
                or token_measured
                or duration_measured
                or planning_duration_measured
                or reasoning_requested
            )
            else latest.get("models", {}).get(
                "measurement_state",
                "host_not_connected",
            )
        ),
    }
    record["measurement_provenance"] = {
        **deepcopy(latest.get("measurement_provenance", {})),
        "tokens": (
            "measured_request_attempts_aggregate"
            if tokens is not None
            else "unavailable"
        ),
        "duration": (
            "measured_request_attempts_aggregate"
            if duration is not None
            else "unavailable"
        ),
        "planning_duration": (
            "measured_request_attempts_aggregate"
            if planning_duration is not None
            else "unavailable"
        ),
        "requested_reasoning_effort": (
            "observed_request_attempts"
            if reasoning_requested
            else "unavailable"
        ),
        "estimated": False,
    }
    record["stage_coverage"] = {
        "available": any(
            run.get("stage_coverage", {}).get("available")
            for run in attempts
        ),
        "recorded": sum(
            run.get("stage_coverage", {}).get("recorded", 0)
            for run in attempts
        ),
        "planned": sum(
            run.get("stage_coverage", {}).get("planned", 0)
            for run in attempts
        ),
    }
    record["stage_coverage"]["complete"] = (
        record["stage_coverage"]["available"]
        and record["stage_coverage"]["planned"] > 0
        and record["stage_coverage"]["recorded"]
        == record["stage_coverage"]["planned"]
    )
    record["stage_telemetry"] = {
        field: sum(
            run.get("stage_telemetry", {}).get(field, 0)
            for run in attempts
        )
        for field in (
            "model_expected",
            "model_measured",
            "duration_measured",
            "tokens_measured",
        )
    }
    record["stage_telemetry"]["complete"] = (
        record["stage_telemetry"]["model_expected"] > 0
        and record["stage_telemetry"]["model_expected"]
        == record["stage_telemetry"]["model_measured"]
    )
    record["request_measurement"] = {
        "scope": "observed_request_attempts",
        "attempts_total": len(attempts),
        "model_measured_attempts": model_measured,
        "token_measured_attempts": token_measured,
        "duration_measured_attempts": duration_measured,
        "planning_duration_measured_attempts": (
            planning_duration_measured
        ),
        "reasoning_request_observed_attempts": reasoning_requested,
        "model_coverage": _attempt_coverage(
            model_measured,
            len(attempts),
        ),
        "token_coverage": (
            "incompatible_scopes"
            if not compatible_token_scopes
            else _attempt_coverage(
                token_measured,
                len(attempts),
            )
        ),
        "token_aggregation": (
            "summed_compatible_scopes"
            if tokens is not None
            else (
                "not_aggregated_mixed_scopes"
                if not compatible_token_scopes
                else "unavailable"
            )
        ),
        "token_scopes": measured_token_scopes,
        "duration_coverage": _attempt_coverage(
            duration_measured,
            len(attempts),
        ),
        "planning_duration_coverage": _attempt_coverage(
            planning_duration_measured,
            len(attempts),
        ),
        "reasoning_request_coverage": _attempt_coverage(
            reasoning_requested,
            len(attempts),
        ),
        "desktop_parent_actual_model": "unavailable",
        "desktop_parent_tokens": "unavailable",
        "estimated": False,
    }
    record["attempts"] = [
        {
            "attempt": index,
            "event_id": run["event_id"],
            "run_id": run["run_id"],
            "relation": identities[index - 1]["relation"],
            "parent_run_id": identities[index - 1]["parent_run_id"],
            "timestamp": run.get("timestamp"),
            "outcome": run.get("outcome"),
            "verifier_result": run.get("verifier_result"),
            "duration_ms": run.get("duration_ms"),
            "duration_source": run.get(
                "measurement_provenance",
                {},
            ).get("duration", "unavailable"),
            "tokens": attempt_tokens[index - 1],
            "token_scope": (
                attempt_token_measurements[index - 1]["scope"]
            ),
            "requested_models": list(
                run.get("models", {}).get("requested", [])
            ),
            "requested_reasoning_effort": list(
                run.get("models", {}).get(
                    "requested_reasoning_effort",
                    [],
                )
            ),
            "route_recommended_models": list(
                run.get("models", {}).get("route_recommended", [])
            ),
            "route_recommended_reasoning_effort": list(
                run.get("models", {}).get(
                    "route_recommended_reasoning_effort",
                    [],
                )
            ),
            "applied_models": list(attempt_models[index - 1]),
            "model_event_evidence": run.get("models", {}).get(
                "model_event_evidence",
                "unavailable",
            ),
            "history_evidence": deepcopy(
                run.get("history_evidence", {})
            ),
            "work_count": len(
                run.get("work_detail", {})
                .get("execution", {})
                .get("cards", [])
            ),
        }
        for index, run in enumerate(attempts, 1)
    ]
    record["work_detail"] = _request_work_detail(record, attempts)
    selected_packs = _unique_strings(
        [
            value
            for run in attempts
            for value in run.get("expertise", {}).get("packs", [])
        ]
    )
    selected_guides = _unique_strings(
        [
            value
            for run in attempts
            for value in run.get("expertise", {}).get("guides", [])
        ]
    )
    record["expertise"] = {
        **deepcopy(latest.get("expertise", {})),
        "packs": selected_packs,
        "guides": selected_guides,
    }
    record["expertise"]["evidence"] = _request_expertise_evidence(
        record["expertise"],
        attempts,
        (
            record["work_detail"]
            .get("execution", {})
            .get("cards", [])
        ),
    )
    return record


def project_request_records(
    runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project immutable runs into one UI record per trusted user request."""

    grouped: dict[str, dict[str, Any]] = {}
    for run in runs:
        resolved = resolve_request_identity(run)
        identity = resolved["identity"]
        group = grouped.setdefault(
            identity,
            {
                "request_record_id": resolved["request_record_id"],
                "root_request_id": resolved["root_request_id"],
                "root_run_ids": set(),
                "evidence": set(),
                "runs": [],
            },
        )
        if (
            resolved["root_run_id"] is not None
            and group["root_run_ids"]
            and resolved["root_run_id"] not in group["root_run_ids"]
        ):
            raise MaestroError(
                "RUN_REQUEST_LINEAGE_CONFLICT",
                "One request record resolves to multiple root runs.",
            )
        if resolved["root_run_id"] is not None:
            group["root_run_ids"].add(resolved["root_run_id"])
        group["evidence"].add(resolved["evidence"])
        group["runs"].append(run)
    records = [
        _project_group(
            group["runs"],
            group["request_record_id"],
            (
                next(iter(group["evidence"]))
                if len(group["evidence"]) == 1
                else "mixed_structural_lineage"
            ),
            group["root_request_id"],
            (
                next(iter(group["root_run_ids"]))
                if len(group["root_run_ids"]) == 1
                else None
            ),
        )
        for group in grouped.values()
    ]
    return sorted(
        records,
        key=lambda record: record.get("timestamp", ""),
        reverse=True,
    )
