from __future__ import annotations

from datetime import datetime
from typing import Any

from .contracts import validate_work_spans


_ORDERING_EDGE_TYPES = {
    "delegates_to",
    "depends_on",
    "followup_of",
    "joins_into",
}


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


def build_display_edge_groups(
    node_ids: list[str],
    ranks: dict[str, int],
    edges: list[dict[str, Any]],
    *,
    default_type: str | None = None,
) -> dict[str, Any]:
    """Derive bounded display geometry without changing raw edge semantics."""

    known = set(node_ids)
    node_position = {
        node_id: index
        for index, node_id in enumerate(node_ids)
    }
    links_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    detail_only_indexes: set[int] = set()
    report_edges: list[tuple[int, dict[str, Any]]] = []

    for index, edge in enumerate(edges):
        source = edge.get("from")
        target = edge.get("to")
        relation_type = edge.get("type", default_type)
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in known
            or target not in known
            or not isinstance(relation_type, str)
        ):
            detail_only_indexes.add(index)
            continue
        if relation_type == "reports_to":
            report_edges.append((index, edge))
            continue
        if (
            relation_type not in _ORDERING_EDGE_TYPES
            or ranks.get(target) != ranks.get(source, -2) + 1
        ):
            detail_only_indexes.add(index)
            continue
        link = links_by_pair.setdefault(
            (source, target),
            {
                "from": source,
                "to": target,
                "relation_types": [],
                "raw_edge_indexes": [],
            },
        )
        if relation_type not in link["relation_types"]:
            link["relation_types"].append(relation_type)
        link["raw_edge_indexes"].append(index)

    for index, edge in report_edges:
        pair = (edge["to"], edge["from"])
        link = links_by_pair.get(pair)
        if link is None:
            detail_only_indexes.add(index)
            continue
        if "reports_to" not in link["relation_types"]:
            link["relation_types"].append("reports_to")
        link["raw_edge_indexes"].append(index)

    links_by_boundary: dict[
        tuple[int, int],
        list[dict[str, Any]],
    ] = {}
    for link in links_by_pair.values():
        boundary = (ranks[link["from"]], ranks[link["to"]])
        link["relation_types"].sort()
        link["raw_edge_indexes"].sort()
        links_by_boundary.setdefault(boundary, []).append(link)

    groups: list[dict[str, Any]] = []
    for boundary in sorted(links_by_boundary):
        remaining = sorted(
            links_by_boundary[boundary],
            key=lambda link: (
                node_position[link["from"]],
                node_position[link["to"]],
            ),
        )
        boundary_groups: list[list[dict[str, Any]]] = []
        while remaining:
            component = [remaining.pop(0)]
            component_nodes = {
                component[0]["from"],
                component[0]["to"],
            }
            changed = True
            while changed:
                changed = False
                unmatched: list[dict[str, Any]] = []
                for link in remaining:
                    if (
                        link["from"] in component_nodes
                        or link["to"] in component_nodes
                    ):
                        component.append(link)
                        component_nodes.update(
                            (link["from"], link["to"])
                        )
                        changed = True
                    else:
                        unmatched.append(link)
                remaining = unmatched
            boundary_groups.append(component)

        for component_index, component in enumerate(boundary_groups, 1):
            source_node_ids = sorted(
                {link["from"] for link in component},
                key=node_position.__getitem__,
            )
            target_node_ids = sorted(
                {link["to"] for link in component},
                key=node_position.__getitem__,
            )
            complete_bipartite = (
                len(component)
                == len(source_node_ids) * len(target_node_ids)
            )
            shared_trunk = (
                len(source_node_ids) == 1
                or len(target_node_ids) == 1
                or complete_bipartite
            )
            groups.append(
                {
                    "group_id": (
                        f"wave-{boundary[0]}-{boundary[1]}"
                        f"-{component_index}"
                    ),
                    "from_rank": boundary[0],
                    "to_rank": boundary[1],
                    "source_node_ids": source_node_ids,
                    "target_node_ids": target_node_ids,
                    "links": component,
                    "routing": (
                        "shared_trunk"
                        if shared_trunk
                        else "individual"
                    ),
                }
            )

    return {
        "display_edge_groups": groups,
        "detail_only_edge_indexes": sorted(detail_only_indexes),
    }


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
    display = build_display_edge_groups(node_ids, ranks, edges)
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
        **display,
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
        if edge["type"] in _ORDERING_EDGE_TYPES
    ]
    ranks = _ranks(node_ids, ordering_edges)
    actual_concurrency, concurrent_pairs = _actual_concurrency(spans)
    display = build_display_edge_groups(
        node_ids,
        ranks,
        execution_edges,
    )
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
        **display,
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
