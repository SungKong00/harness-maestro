from __future__ import annotations

from datetime import datetime
from typing import Any

from .contracts import validate_work_spans


def _ranks(
    node_ids: list[str],
    edges: list[dict[str, str]],
) -> dict[str, int]:
    known = set(node_ids)
    predecessors = {
        node_id: [
            edge["from"]
            for edge in edges
            if edge["to"] == node_id and edge["from"] in known
        ]
        for node_id in node_ids
    }
    ranks: dict[str, int] = {}
    pending = list(node_ids)
    while pending:
        remaining = []
        progressed = False
        for node_id in pending:
            dependencies = predecessors[node_id]
            if all(dependency in ranks for dependency in dependencies):
                ranks[node_id] = (
                    max(
                        (ranks[dependency] for dependency in dependencies),
                        default=-1,
                    )
                    + 1
                )
                progressed = True
            else:
                remaining.append(node_id)
        if not progressed:
            for node_id in remaining:
                ranks[node_id] = 0
            break
        pending = remaining
    return ranks


def _plan_graph(stages: list[dict[str, Any]]) -> dict[str, Any]:
    node_ids = [
        stage["assignment_id"]
        for stage in stages
        if isinstance(stage.get("assignment_id"), str)
    ]
    known = set(node_ids)
    edges = [
        {
            "from": dependency,
            "to": stage["assignment_id"],
            "type": "depends_on",
            "provenance": "plan",
            "source": "route_plan",
            "coverage": "declared",
        }
        for stage in stages
        for dependency in stage.get("depends_on", [])
        if dependency in known
    ]
    ranks = _ranks(node_ids, edges)
    return {
        "nodes": [
            {
                "node_id": stage["assignment_id"],
                "node_type": "plan_stage",
                "rank": ranks.get(stage["assignment_id"], 0),
                "data": stage,
            }
            for stage in stages
            if stage.get("assignment_id") in known
        ],
        "edges": edges,
        "entry_node_ids": [
            node_id
            for node_id in node_ids
            if not any(edge["to"] == node_id for edge in edges)
        ],
        "terminal_node_ids": [
            node_id
            for node_id in node_ids
            if not any(edge["from"] == node_id for edge in edges)
        ],
        "max_rank": max(ranks.values(), default=0),
    }


def _edge_coverage(span: dict[str, Any]) -> str:
    binding = span.get("source_binding")
    return (
        binding.get("event_coverage", "unavailable")
        if isinstance(binding, dict)
        else "legacy_observation"
    )


def _execution_edges(spans: list[dict[str, Any]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for span in spans:
        work_id = span["work_id"]
        parent = span["parent_work_id"]
        if parent is not None:
            edges.append(
                {
                    "from": parent,
                    "to": work_id,
                    "type": "delegates_to",
                    "provenance": "observed_work",
                    "source": span["source"],
                    "coverage": _edge_coverage(span),
                }
            )
            if span["status"] != "running":
                edges.append(
                    {
                        "from": work_id,
                        "to": parent,
                        "type": "reports_to",
                        "provenance": "observed_work",
                        "source": span["source"],
                        "coverage": _edge_coverage(span),
                    }
                )
        if span["followup_of_work_id"] is not None:
            edges.append(
                {
                    "from": span["followup_of_work_id"],
                    "to": work_id,
                    "type": "followup_of",
                    "provenance": "observed_work",
                    "source": span["source"],
                    "coverage": _edge_coverage(span),
                }
            )
        edges.extend(
            {
                "from": dependency,
                "to": work_id,
                "type": "depends_on",
                "provenance": "observed_work",
                "source": span["source"],
                "coverage": _edge_coverage(span),
            }
            for dependency in span["depends_on_work_ids"]
        )
        edges.extend(
            {
                "from": joined,
                "to": work_id,
                "type": "joins_into",
                "provenance": "observed_work",
                "source": span["source"],
                "coverage": _edge_coverage(span),
            }
            for joined in span["joins_work_ids"]
        )
    unique = {
        (
            edge["from"],
            edge["to"],
            edge["type"],
            edge["provenance"],
        ): edge
        for edge in edges
    }
    return list(unique.values())


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _actual_concurrency(
    spans: list[dict[str, Any]],
) -> tuple[str, list[list[str]]]:
    eligible: list[
        tuple[str, tuple[str, str, str], datetime, datetime]
    ] = []
    for span in spans:
        binding = span.get("source_binding")
        usage = span.get("usage")
        started = _timestamp(span.get("started_at"))
        ended = _timestamp(span.get("ended_at"))
        if (
            not isinstance(binding, dict)
            or binding.get("event_coverage")
            not in {"complete_stream", "recovered_full"}
            or not isinstance(usage, dict)
            or usage.get("timing_coverage") != "host_event"
            or span.get("timing_evidence") != "host_event"
            or started is None
            or ended is None
            or not all(
                isinstance(binding.get(field), str)
                and binding[field]
                for field in ("interface", "version", "schema_digest")
            )
        ):
            continue
        eligible.append(
            (
                span["work_id"],
                (
                    binding["interface"],
                    binding["version"],
                    binding["schema_digest"],
                ),
                started,
                ended,
            )
        )
    comparable_domains = {
        domain
        for _, domain, _, _ in eligible
        if sum(1 for item in eligible if item[1] == domain) >= 2
    }
    if not comparable_domains:
        return "unavailable", []
    pairs = [
        [left[0], right[0]]
        for index, left in enumerate(eligible)
        for right in eligible[index + 1 :]
        if left[1] in comparable_domains
        and left[1] == right[1]
        and left[2] < right[3]
        and right[2] < left[3]
    ]
    return ("observed" if pairs else "none_observed"), pairs


def build_work_graph(
    stages: list[dict[str, Any]],
    work_spans: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    spans = list(work_spans or [])
    if not validate_work_spans(spans):
        spans = []
        completeness = "invalid"
    else:
        completeness = (
            "unavailable"
            if not spans
            else (
                "partial"
                if any(span["status"] == "running" for span in spans)
                else "complete"
            )
        )
    plan = _plan_graph(stages)
    execution_edges = _execution_edges(spans)
    node_ids = [span["work_id"] for span in spans]
    ordering_edges = [
        edge
        for edge in execution_edges
        if edge["type"] != "reports_to"
    ]
    ranks = _ranks(node_ids, ordering_edges)
    actual_concurrency, concurrent_pairs = _actual_concurrency(spans)
    execution = {
        "nodes": [
            {
                "node_id": span["work_id"],
                "node_type": "work_attempt",
                "rank": ranks.get(span["work_id"], 0),
                "data": span,
            }
            for span in spans
        ],
        "edges": execution_edges,
        "entry_node_ids": [
            node_id
            for node_id in node_ids
            if not any(
                edge["to"] == node_id
                and edge["type"] != "reports_to"
                for edge in execution_edges
            )
        ],
        "terminal_node_ids": [
            node_id
            for node_id in node_ids
            if not any(
                edge["from"] == node_id
                and edge["type"] not in {"reports_to"}
                for edge in execution_edges
            )
        ],
        "max_rank": max(ranks.values(), default=0),
        "completeness": completeness,
        "actual_concurrency": actual_concurrency,
        "concurrent_work_pairs": concurrent_pairs,
    }
    bindings = [
        {
            "assignment_id": span["assignment_id"],
            "work_id": span["work_id"],
            "provenance": "explicit_assignment_binding",
        }
        for span in spans
        if span["assignment_id"] is not None
    ]
    return {
        "schema_version": "maestro_work_graph_v1",
        "plan": plan,
        "execution": execution,
        "bindings": bindings,
    }
