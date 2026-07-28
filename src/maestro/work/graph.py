from __future__ import annotations

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
                }
            )
            if span["status"] != "running":
                edges.append(
                    {
                        "from": work_id,
                        "to": parent,
                        "type": "reports_to",
                        "provenance": "observed_work",
                    }
                )
        if span["followup_of_work_id"] is not None:
            edges.append(
                {
                    "from": span["followup_of_work_id"],
                    "to": work_id,
                    "type": "followup_of",
                    "provenance": "observed_work",
                }
            )
        edges.extend(
            {
                "from": dependency,
                "to": work_id,
                "type": "depends_on",
                "provenance": "observed_work",
            }
            for dependency in span["depends_on_work_ids"]
        )
        edges.extend(
            {
                "from": joined,
                "to": work_id,
                "type": "joins_into",
                "provenance": "observed_work",
            }
            for joined in span["joins_work_ids"]
        )
    unique = {
        (edge["from"], edge["to"], edge["type"], edge["provenance"]): edge
        for edge in edges
    }
    return list(unique.values())


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
        "actual_concurrency": "unavailable",
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
