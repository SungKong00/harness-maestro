from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import MaestroError
from .util import read_json

REQUEST_VERSION = "maestro_surface_signal_v1"
RESULT_VERSION = "maestro_surface_classification_v1"

SURFACES = (
    "none",
    "checker-schema-test",
    "convention",
    "decision-guide",
    "expertise-pack",
    "lens",
    "standalone-skill",
    "executor-agent",
    "department",
    "adapter",
    "research-lane",
    "specialist-contract",
    "packet-contract",
)

SIGNAL_FIELDS = {
    "durable",
    "machine_checkable",
    "project_specific_rule",
    "existing_pack_id",
    "existing_guide_id",
    "same_decision_family",
    "related_guide_count",
    "domain_workflow",
    "cross_task_failure_boundary",
    "verdict_impact",
    "procedural_only",
    "expertise_routed",
    "execution_boundaries",
    "department_routing_change",
    "integration_boundary",
    "research_lane_boundary",
    "specialist_contract_boundary",
    "typed_handoff_gap",
    "existing_packet_sufficient",
}
OPTIONAL_SIGNAL_FIELDS = {
    "overlapping_pack_ids",
    "pack_merge_boundary",
}

EXECUTION_BOUNDARIES = {
    "tools",
    "permissions",
    "model",
    "sandbox",
    "context",
    "approval",
}

BUILDERS = {
    "none": None,
    "checker-schema-test": "existing-engineering-surface",
    "convention": "maestro-convention-lifecycle",
    "decision-guide": "maestro-expertise-builder",
    "expertise-pack": "maestro-expertise-builder",
    "lens": "maestro-registry-builder",
    "standalone-skill": "skill-creator",
    "executor-agent": "maestro-registry-builder",
    "department": "maestro-registry-builder",
    "adapter": "maestro-registry-builder",
    "research-lane": "maestro-registry-builder",
    "specialist-contract": "maestro-registry-builder",
    "packet-contract": "maestro-registry-builder",
}

EVIDENCE_REQUIREMENTS = {
    "none": ["why no durable component changes a future outcome"],
    "checker-schema-test": [
        "a deterministic invariant",
        "positive and negative fixtures",
    ],
    "convention": [
        "project authority or held-out evaluation",
        "repository-local verification artifact",
    ],
    "decision-guide": [
        "named recurring decision failure",
        "existing Pack and Guide overlap check",
        "frozen positive, non-trigger, and regression cases",
    ],
    "expertise-pack": [
        "independent decision family",
        "at least two selectable Guide candidates",
        "source and held-out evaluation plan",
    ],
    "lens": [
        "distinct evidence or failure boundary",
        "proof that the finding can change a verdict",
        "cross-task non-trigger cases",
    ],
    "standalone-skill": [
        "repeated procedure or tool-use need",
        "proof that Expertise routing is not the owner",
    ],
    "executor-agent": [
        "an irreducible tool, permission, model, sandbox, context, or approval boundary",
        "fallback and additional-cost evidence",
    ],
    "department": [
        "frozen routes whose Lens set or selection cap must change",
        "regression cases for existing departments",
    ],
    "adapter": [
        "a new project, document, or tool integration boundary",
        "authority and rollback behavior",
    ],
    "research-lane": [
        "a distinct source or evidence boundary",
        "proof that an existing research packet cannot express the lane",
    ],
    "specialist-contract": [
        "a repeated decision-stage ownership boundary",
        "out-of-scope and escalation cases",
    ],
    "packet-contract": [
        "repeated typed handoff failures",
        "proof that existing Packet contracts are insufficient",
        "producer and consumer compatibility cases",
    ],
}

PROMOTION_BOUNDARIES = {
    "none": "Keep the result in the current run; do not create a durable component.",
    "checker-schema-test": "Merge through the owning code and test review path.",
    "convention": "Use the typed Convention preview/apply lifecycle with owner or held-out evidence.",
    "decision-guide": "Publish only through the reviewed Expertise candidate lifecycle.",
    "expertise-pack": "Publish only through the reviewed Expertise candidate lifecycle.",
    "lens": "Keep project-local until frozen route and verdict-impact evaluation plus owner approval.",
    "standalone-skill": "Validate and review as a versioned Skill; never install globally in the producing run.",
    "executor-agent": "Require owner approval and an evaluated execution-boundary pilot before Registry change.",
    "department": "Require frozen route comparisons and owner approval before Registry change.",
    "adapter": "Require explicit adapter authority approval and rollback verification.",
    "research-lane": "Require packet compatibility and bounded-cost evaluation before workflow change.",
    "specialist-contract": "Require repeated ownership evidence before adding a durable role contract.",
    "packet-contract": "Require producer/consumer compatibility evaluation and a schema-version decision.",
}


def _invalid(message: str) -> MaestroError:
    return MaestroError("SURFACE_SIGNAL_INVALID", message)


def _optional_slug(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"{field} must be null or a non-empty component ID.")
    return value


def _validate_request(value: Any) -> tuple[str, dict[str, Any], list[str]]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "request_id",
        "signals",
        "evidence_refs",
    }:
        raise _invalid("Surface input has unsupported or missing fields.")
    if value.get("schema_version") != REQUEST_VERSION:
        raise _invalid(f"schema_version must be {REQUEST_VERSION}.")
    request_id = value.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise _invalid("request_id must be a non-empty string.")
    signals = value.get("signals")
    if (
        not isinstance(signals, dict)
        or not SIGNAL_FIELDS.issubset(signals)
        or set(signals) - SIGNAL_FIELDS - OPTIONAL_SIGNAL_FIELDS
    ):
        raise _invalid(
            "signals must contain the exact surface signal fields plus only "
            "supported optional fields."
        )
    signals = {
        **signals,
        "overlapping_pack_ids": signals.get("overlapping_pack_ids", []),
        "pack_merge_boundary": signals.get("pack_merge_boundary", False),
    }
    boolean_fields = SIGNAL_FIELDS - {
        "existing_pack_id",
        "existing_guide_id",
        "related_guide_count",
        "execution_boundaries",
    }
    if any(not isinstance(signals[field], bool) for field in boolean_fields):
        raise _invalid("Every boolean surface signal must be true or false.")
    _optional_slug(signals["existing_pack_id"], "existing_pack_id")
    _optional_slug(signals["existing_guide_id"], "existing_guide_id")
    overlapping_pack_ids = signals["overlapping_pack_ids"]
    if (
        not isinstance(overlapping_pack_ids, list)
        or len(overlapping_pack_ids) > 4
        or len(overlapping_pack_ids) != len(set(overlapping_pack_ids))
    ):
        raise _invalid(
            "overlapping_pack_ids must be at most four unique component IDs."
        )
    for pack_id in overlapping_pack_ids:
        _optional_slug(pack_id, "overlapping_pack_ids item")
    if not isinstance(signals["pack_merge_boundary"], bool):
        raise _invalid("pack_merge_boundary must be true or false.")
    guide_count = signals["related_guide_count"]
    if (
        not isinstance(guide_count, int)
        or isinstance(guide_count, bool)
        or not 0 <= guide_count <= 12
    ):
        raise _invalid("related_guide_count must be an integer from 0 to 12.")
    boundaries = signals["execution_boundaries"]
    if (
        not isinstance(boundaries, list)
        or len(boundaries) != len(set(boundaries))
        or not all(item in EXECUTION_BOUNDARIES for item in boundaries)
    ):
        raise _invalid(
            "execution_boundaries must be unique supported boundary names."
        )
    evidence_refs = value.get("evidence_refs")
    if (
        not isinstance(evidence_refs, list)
        or len(evidence_refs) > 12
        or len(evidence_refs) != len(set(evidence_refs))
        or not all(isinstance(item, str) and item.strip() for item in evidence_refs)
    ):
        raise _invalid("evidence_refs must be at most 12 unique non-empty strings.")
    return request_id, signals, evidence_refs


def _select_surface(signals: dict[str, Any]) -> tuple[str, str, list[str]]:
    if not signals["durable"]:
        return "none", "one-off", []
    if signals["machine_checkable"]:
        return "checker-schema-test", "deterministic-invariant", []
    if signals["project_specific_rule"]:
        return "convention", "project-rule", []
    if signals["existing_guide_id"] is not None:
        return "decision-guide", "existing-guide-revision", []
    if (
        signals["pack_merge_boundary"]
        and signals["domain_workflow"]
        and len(signals["overlapping_pack_ids"]) >= 2
    ):
        return (
            "expertise-pack",
            "pack-consolidation",
            list(signals["overlapping_pack_ids"]),
        )
    if (
        signals["existing_pack_id"] is not None
        and signals["same_decision_family"]
    ):
        return "decision-guide", "existing-pack-decision-family", []
    if signals["integration_boundary"]:
        return "adapter", "integration", []
    if signals["execution_boundaries"]:
        return (
            "executor-agent",
            "execution",
            list(signals["execution_boundaries"]),
        )
    if signals["department_routing_change"]:
        return "department", "route-selection", []
    if signals["typed_handoff_gap"] and not signals["existing_packet_sufficient"]:
        return "packet-contract", "typed-handoff", []
    if signals["research_lane_boundary"]:
        return "research-lane", "research-source", []
    if (
        signals["cross_task_failure_boundary"]
        and signals["verdict_impact"]
    ):
        return "lens", "failure-or-evidence", []
    if signals["specialist_contract_boundary"]:
        return "specialist-contract", "decision-ownership", []
    if signals["procedural_only"] and not signals["expertise_routed"]:
        return "standalone-skill", "procedure", []
    if signals["domain_workflow"] and signals["related_guide_count"] >= 2:
        return "expertise-pack", "decision-family", []
    if signals["existing_pack_id"] is not None and signals["domain_workflow"]:
        return "decision-guide", "existing-pack-decision-family", []
    return "none", "insufficient-distinct-boundary", []


def _rejection_reason(
    surface: str,
    proposed: str,
    signals: dict[str, Any],
) -> str:
    if surface == "none":
        return "The evidence supports a durable surface."
    reasons = {
        "checker-schema-test": (
            "The requirement is not a mechanically decidable invariant."
        ),
        "convention": (
            "No project-specific authority or durable project rule was established."
        ),
        "decision-guide": (
            "No existing Pack or Guide owns the same decision family."
        ),
        "expertise-pack": (
            "No independent domain with at least two selectable Guides was established."
        ),
        "lens": (
            "No cross-task evidence or failure boundary with verdict impact was established."
        ),
        "standalone-skill": (
            "No repeated procedure outside Expertise routing was established."
        ),
        "executor-agent": (
            "No irreducible tool, permission, model, sandbox, context, or approval boundary was established."
        ),
        "department": (
            "No task-class Lens set or selection-limit change was established."
        ),
        "adapter": (
            "No new project, document, tool, or authority integration boundary was established."
        ),
        "research-lane": (
            "No distinct source/evidence lane beyond the current research contract was established."
        ),
        "specialist-contract": (
            "No repeated decision-stage ownership and escalation boundary was established."
        ),
        "packet-contract": (
            "No typed handoff gap beyond existing Packet capability was established."
            if not signals["existing_packet_sufficient"]
            else "The existing Packet contract is sufficient."
        ),
    }
    reason = reasons[surface]
    if proposed != "none":
        return f"{reason} The supplied signals are better owned by {proposed}."
    return reason


def classify_surface(value: dict[str, Any]) -> dict[str, Any]:
    request_id, signals, evidence_refs = _validate_request(value)
    proposed, boundary_kind, boundary_details = _select_surface(signals)
    blocker: str | None = None
    independent_boundaries = [
        name
        for name, present in (
            ("adapter", signals["integration_boundary"]),
            ("executor-agent", bool(signals["execution_boundaries"])),
            ("department", signals["department_routing_change"]),
            (
                "packet-contract",
                signals["typed_handoff_gap"]
                and not signals["existing_packet_sufficient"],
            ),
            ("research-lane", signals["research_lane_boundary"]),
            (
                "lens",
                signals["cross_task_failure_boundary"]
                and signals["verdict_impact"],
            ),
            (
                "specialist-contract",
                signals["specialist_contract_boundary"],
            ),
        )
        if present
    ]
    if len(independent_boundaries) > 1:
        blocker = (
            "Multiple independent boundaries were supplied; split them into "
            f"separate classifications: {', '.join(independent_boundaries)}."
        )
    elif proposed == "none" and signals["durable"]:
        blocker = "No distinct reusable boundary was established."
    elif signals["pack_merge_boundary"] and (
        len(signals["overlapping_pack_ids"]) < 2
        or not signals["domain_workflow"]
    ):
        blocker = (
            "Pack integration requires at least two existing Pack IDs and one "
            "shared domain workflow boundary."
        )
    elif proposed != "none" and not evidence_refs:
        blocker = "At least one evidence reference is required before candidate handoff."

    merge_recommended = (
        proposed == "expertise-pack"
        and boundary_kind == "pack-consolidation"
        and blocker is None
    )
    overlapping_pack_ids = list(signals["overlapping_pack_ids"])
    integration_considered = bool(
        overlapping_pack_ids or signals["pack_merge_boundary"]
    )
    if merge_recommended:
        integration_reason = (
            "Two or more existing Packs share one domain workflow, trigger, "
            "result, source, and evaluation boundary; evaluate a consolidated "
            "new Pack against the source Packs."
        )
    elif len(overlapping_pack_ids) >= 2:
        integration_reason = (
            "Multiple Packs overlap, but no shared lifecycle boundary was "
            "established; keep them separate or add/revise the owning Guide."
        )
    else:
        integration_reason = (
            "Pack integration was not indicated because fewer than two "
            "existing Packs share the proposed boundary."
        )
    existing_component = (
        None
        if merge_recommended
        else signals["existing_guide_id"] or signals["existing_pack_id"]
    )
    rejected = [
        {
            "surface": surface,
            "reason": _rejection_reason(surface, proposed, signals),
        }
        for surface in SURFACES
        if surface != proposed
    ]
    return {
        "schema_version": RESULT_VERSION,
        "status": "blocked" if blocker else "classified",
        "request_id": request_id,
        "proposed_surface": proposed,
        "rejected_surfaces": rejected,
        "existing_component_to_extend": existing_component,
        "pack_integration_assessment": {
            "considered": integration_considered,
            "recommended": merge_recommended,
            "source_pack_ids": overlapping_pack_ids,
            "reason": integration_reason,
        },
        "distinct_failure_or_decision_boundary": {
            "kind": boundary_kind,
            "details": boundary_details,
            "verdict_impact": bool(signals["verdict_impact"]),
        },
        "evidence_requirement": [
            *EVIDENCE_REQUIREMENTS[proposed],
            *(
                [
                    "source Pack inventory and overlap map",
                    "frozen comparison against every source Pack",
                    "migration, rollback, and coexistence plan",
                ]
                if merge_recommended
                else []
            ),
        ],
        "candidate_builder": BUILDERS[proposed],
        "promotion_boundary": PROMOTION_BOUNDARIES[proposed],
        "classification_confidence": (
            "blocked"
            if blocker
            else "high"
            if evidence_refs
            else "medium"
        ),
        "blocker": blocker,
        "writes_performed": False,
    }


def classify_surface_file(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise MaestroError(
            "SURFACE_SIGNAL_NOT_FOUND",
            f"Surface signal file is missing: {target}",
        )
    return classify_surface(read_json(target))
