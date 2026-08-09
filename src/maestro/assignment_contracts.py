from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Iterable

from .coverage_admission import validate_task_coverage_admission
from .documents import select_documents
from .design_assurance import (
    design_result_digest,
    product_design_assurance_active,
    validate_design_assurance_result,
    validate_design_decision_packet,
    validate_design_verification,
)
from .errors import MaestroError
from .execution_contracts import normalize_execution_contract
from .planning import validate_route_v2
from .registry import load_registry
from .research import (
    expected_research_binding,
    project_research_context,
    require_completed_research_bundle,
    validate_research_bundle,
)
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    safe_target,
    sha256_text,
)

ENGINEERING_BASELINE_VERSION = "maestro_engineering_baseline_v1"
ASSIGNMENT_INPUT_VERSION = "maestro_assignment_input_v1"
FINDING_PACKET_VERSION = "maestro_finding_packet_v2"
TERMINAL_PACKET_VERSION = "maestro_terminal_packet_v1"
VERIFICATION_VERDICT_VERSION = "maestro_verification_verdict_v1"
VALIDATION_VERSION = "maestro_assignment_contract_validation_v1"
CONVENTION_SELECTION_VERSION = "maestro_convention_selection_v1"
_ASSIGNMENT_SCHEMA_RESOURCE = "schemas/assignment-contracts.schema.json"
_OUTPUT_SCHEMA_UNSUPPORTED_KEYWORDS = {
    "$schema",
    "format",
    "maxItems",
    "maxLength",
    "minItems",
    "minLength",
    "pattern",
    "uniqueItems",
}

_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_ARTIFACT_KINDS = {
    "source",
    "test",
    "schema",
    "config",
    "documentation",
    "interface",
    "data",
    "external",
}
_LIFECYCLE_KINDS = {
    "success",
    "validation-failure",
    "timeout",
    "retry",
    "cancellation",
    "rollback",
    "recovery",
    "other",
}
_CHECK_IDS = {
    "behavior-contract",
    "affected-surface",
    "failure-recovery",
    "compatibility",
    "completion-evidence",
    "risk-ownership",
}
_VERDICTS = {"PASS", "FINDINGS", "BLOCK", "INSUFFICIENT_EVIDENCE"}
_SEVERITIES = {"medium", "high", "critical"}
_VERIFICATION_VERDICTS = {"passed", "failed", "inconclusive"}
_VERIFICATION_FAILURE_CAUSES = {
    "none",
    "implementation",
    "specification",
    "environment",
    "tooling",
    "unknown",
}
_VERIFICATION_FAILURE_CATEGORIES = {
    "correctness",
    "integration",
    "security",
    "regression",
    "performance",
    "contract",
    "test-infrastructure",
    "specification",
    "unknown",
}
_TERMINAL_STATUSES = {
    "completed",
    "failed_transient",
    "failed_semantic",
    "blocked",
    "cancelled",
    "skipped",
}
_ASSIGNMENT_FIELDS = {
    "assignment_id",
    "kind",
    "executor_id",
    "lens_ids",
    "depends_on",
    "input_packets",
    "output_packet",
    "read_only",
    "mutation_owner",
    "allowed_side_effects",
    "may_spawn",
    "max_children",
    "max_rounds",
}
_FORBIDDEN_CONTEXT = [
    "parent_conversation",
    "other_initial_conclusions",
    "raw_transcripts",
    "hidden_reasoning",
    "file_bodies",
]


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _digest(value: Any) -> str | None:
    try:
        return sha256_text(canonical_json(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _validation(
    value: Any,
    issues: list[dict[str, str]],
    *,
    execution_status: str = "READY",
) -> dict[str, Any]:
    issues.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return {
        "schema_version": VALIDATION_VERSION,
        "status": "PASS" if not issues else "FAIL",
        "execution_status": "INVALID" if issues else execution_status,
        "issues": issues,
        "packet_digest": _digest(value),
        "writes_performed": False,
    }


@lru_cache(maxsize=1)
def _assignment_schema_document() -> dict[str, Any]:
    """Load the packaged wire schema that the runtime validators implement."""

    try:
        item = resources.files("maestro.resources").joinpath(
            _ASSIGNMENT_SCHEMA_RESOURCE
        )
        value = json.loads(item.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MaestroError(
            "PACKET_OUTPUT_SCHEMA_UNAVAILABLE",
            "The packaged Assignment Packet schema cannot be loaded.",
        ) from exc
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("$defs"), dict)
    ):
        raise MaestroError(
            "PACKET_OUTPUT_SCHEMA_INVALID",
            "The packaged Assignment Packet schema has no usable definitions.",
        )
    return value


def _schema_definition_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            refs.add(ref.removeprefix("#/$defs/"))
        for item in value.values():
            refs.update(_schema_definition_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_schema_definition_refs(item))
    return refs


def _closed_packet_output_schema(definition_id: str) -> dict[str, Any]:
    document = _assignment_schema_document()
    available = document["$defs"]
    pending = [definition_id]
    selected: dict[str, Any] = {}
    while pending:
        current = pending.pop()
        if current in selected:
            continue
        definition = available.get(current)
        if not isinstance(definition, dict):
            raise MaestroError(
                "PACKET_OUTPUT_SCHEMA_INVALID",
                f"Missing packaged Assignment Packet definition: {current}.",
            )
        selected[current] = copy.deepcopy(definition)
        pending.extend(
            sorted(
                _schema_definition_refs(definition) - set(selected),
                reverse=True,
            )
        )
    root = selected.pop(definition_id)
    return _provider_output_schema(
        {
            "$schema": document.get(
                "$schema",
                "https://json-schema.org/draft/2020-12/schema",
            ),
            "title": "Harness Maestro Assignment final-answer Packet",
            "description": (
                "Return exactly one JSON object. Markdown fences, commentary, "
                "and fields outside this closed schema are not allowed."
            ),
            **root,
            "$defs": selected,
        }
    )


def _provider_output_schema(value: Any) -> Any:
    """Compile the wire schema to the App Server structured-output subset."""

    if isinstance(value, list):
        return [_provider_output_schema(item) for item in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    compiled: dict[str, Any] = {}
    for key, item in value.items():
        if key in _OUTPUT_SCHEMA_UNSUPPORTED_KEYWORDS:
            continue
        if key == "const":
            compiled["enum"] = [copy.deepcopy(item)]
            continue
        if key == "oneOf":
            compiled["anyOf"] = _provider_output_schema(item)
            continue
        compiled[key] = _provider_output_schema(item)
    return compiled


def assignment_output_schema(
    projection: Any,
    *,
    require_expertise_dispositions: bool = False,
) -> dict[str, Any]:
    """Derive the exact final-answer JSON Schema for one AssignmentInput."""

    projected = _projection_value(projection)
    if (
        not isinstance(projected, dict)
        or projected.get("schema_version") != ASSIGNMENT_INPUT_VERSION
        or not isinstance(projected.get("plan_id"), str)
        or not isinstance(projected.get("assignment_id"), str)
        or not isinstance(projected.get("assignment_contract"), dict)
    ):
        raise MaestroError(
            "PACKET_OUTPUT_SCHEMA_INVALID",
            "A valid AssignmentInput is required to derive its output schema.",
        )
    assignment = projected["assignment_contract"]
    output_packet = assignment.get("output_packet")
    if output_packet == "FindingPacket":
        definition_id = "findingPacket"
    elif output_packet == "VerificationVerdict":
        definition_id = "verificationVerdict"
    elif isinstance(output_packet, str) and output_packet.strip():
        definition_id = "terminalPacket"
    else:
        raise MaestroError(
            "PACKET_OUTPUT_SCHEMA_INVALID",
            "The Assignment output Packet ID is missing.",
        )

    schema = _closed_packet_output_schema(definition_id)
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise MaestroError(
            "PACKET_OUTPUT_SCHEMA_INVALID",
            "The packaged Assignment Packet definition has no properties.",
        )
    properties["plan_id"] = {"enum": [projected["plan_id"]]}
    properties["assignment_id"] = {
        "enum": [projected["assignment_id"]],
    }
    expertise_load = projected.get("expertise_load")
    expected_expertise = [
        {
            "expertise_pack_id": pack["expertise_pack_id"],
            "definition_digest": pack["definition_digest"],
            "guide_id": guide["guide_id"],
            "skill_definition_digest": guide[
                "skill_definition_digest"
            ],
        }
        for pack in (
            expertise_load.get("packs", [])
            if isinstance(expertise_load, dict)
            else []
        )
        if isinstance(pack, dict)
        for guide in pack.get("guides", [])
        if isinstance(guide, dict)
    ]
    if expected_expertise and require_expertise_dispositions:
        properties["expertise_dispositions"] = {
            "type": "array",
            "items": {
                "anyOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "expertise_pack_id",
                            "definition_digest",
                            "guide_id",
                            "skill_definition_digest",
                            "disposition",
                            "reason",
                            "evidence_refs",
                        ],
                        "properties": {
                            "expertise_pack_id": {
                                "enum": [
                                    item["expertise_pack_id"]
                                ]
                            },
                            "definition_digest": {
                                "enum": [item["definition_digest"]]
                            },
                            "guide_id": {
                                "enum": [item["guide_id"]]
                            },
                            "skill_definition_digest": {
                                "enum": [
                                    item["skill_definition_digest"]
                                ]
                            },
                            "disposition": {
                                "enum": [
                                    "consulted",
                                    "applied",
                                    "not_applicable",
                                    "conflict",
                                ]
                            },
                            "reason": {"type": "string"},
                            "evidence_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    }
                    for item in expected_expertise
                ]
            },
        }
        required = schema.get("required")
        if not isinstance(required, list):
            raise MaestroError(
                "PACKET_OUTPUT_SCHEMA_INVALID",
                "The packaged Assignment Packet has no required field set.",
            )
        required.append("expertise_dispositions")
    elif require_expertise_dispositions:
        raise MaestroError(
            "PACKET_OUTPUT_SCHEMA_INVALID",
            "Expertise dispositions cannot be required without selected Guides.",
        )
    else:
        properties.pop("expertise_dispositions", None)
    if definition_id == "findingPacket":
        lens_ids = assignment.get("lens_ids")
        if (
            not isinstance(lens_ids, list)
            or not lens_ids
            or not all(isinstance(item, str) for item in lens_ids)
        ):
            raise MaestroError(
                "PACKET_OUTPUT_SCHEMA_INVALID",
                "A FindingPacket output schema requires the exact Assignment Lens set.",
            )
        properties["lens_ids"] = {
            "type": "array",
            "items": {"enum": copy.deepcopy(lens_ids)},
        }
        projected_refs, _ = _projection_refs(projected)
        projected_artifacts, _ = _projection_artifacts(projected)
        finding = schema["$defs"].get("finding")
        if isinstance(finding, dict) and isinstance(
            finding.get("properties"),
            dict,
        ):
            finding["properties"]["owner_lens_id"] = {
                "enum": copy.deepcopy(lens_ids),
            }
            if projected_refs:
                finding["properties"]["evidence_refs"] = {
                    "type": "array",
                    "items": {"enum": sorted(projected_refs)},
                }
        coverage_gap = schema["$defs"].get("coverageGap")
        if isinstance(coverage_gap, dict) and isinstance(
            coverage_gap.get("properties"),
            dict,
        ):
            coverage_properties = coverage_gap["properties"]
            if projected_artifacts:
                coverage_properties["affected_artifact"] = {
                    "enum": sorted(projected_artifacts),
                }
            if projected_refs:
                coverage_properties["evidence_refs"] = {
                    "type": "array",
                    "items": {"enum": sorted(projected_refs)},
                }
            registered_lenses = {
                item["lens_id"] for item in load_registry()["lenses"]
            }
            unselected_lenses = sorted(registered_lenses - set(lens_ids))
            suggested_options: list[dict[str, Any]] = [{"type": "null"}]
            if unselected_lenses:
                suggested_options.insert(
                    0,
                    {"enum": unselected_lenses},
                )
            coverage_properties["suggested_lens"] = {
                "anyOf": suggested_options,
            }
        if projected_refs:
            properties["inspected"] = {
                "type": "array",
                "items": {"enum": sorted(projected_refs)},
            }
    elif definition_id == "verificationVerdict":
        target = projected.get("verification_target")
        if not isinstance(target, dict):
            raise MaestroError(
                "PACKET_OUTPUT_SCHEMA_INVALID",
                "VerificationVerdict requires one exact mutation-owner target.",
            )
        properties["target_assignment_id"] = {
            "enum": [target["assignment_id"]]
        }
        properties["target_execution_unit_id"] = {
            "enum": [target["execution_unit_id"]]
        }
        properties["target_model_route_id"] = {
            "enum": [target["model_route_id"]]
        }
        projected_refs, _ = _projection_refs(projected)
        if projected_refs:
            properties["evidence_refs"] = {
                "type": "array",
                "items": {"enum": sorted(projected_refs)},
            }
        design_context = projected.get("design_assurance_context")
        if (
            isinstance(design_context, dict)
            and design_context.get("role") == "verification"
        ):
            required = schema.get("required")
            if not isinstance(required, list):
                raise MaestroError(
                    "PACKET_OUTPUT_SCHEMA_INVALID",
                    "The verification Packet output schema has no required field set.",
                )
            required.append("design_verification")
            decision_packet = design_context["decision_packet"]
            implementation_result = design_context[
                "implementation_result"
            ]
            design_verification_schema = schema["$defs"][
                "designVerification"
            ]
            design_verification_schema["properties"][
                "decision_packet_id"
            ] = {"enum": [decision_packet["packet_id"]]}
            design_verification_schema["properties"][
                "implementation_result_digest"
            ] = {"enum": [design_result_digest(implementation_result)]}
            scenario_ids = [
                item["scenario_id"]
                for item in decision_packet["verification_scenarios"]
            ]
            scenario_result = schema["$defs"].get(
                "designVerificationScenarioResult"
            )
            if isinstance(scenario_result, dict):
                scenario_result["properties"]["scenario_id"] = {
                    "enum": scenario_ids
                }
                scenario_result["properties"]["artifact_path"] = {
                    "enum": [
                        item["artifact_path"]
                        for item in implementation_result[
                            "rendered_artifacts"
                        ]
                    ]
                }
                scenario_result["properties"]["artifact_sha256"] = {
                    "enum": [
                        item["sha256"]
                        for item in implementation_result[
                            "rendered_artifacts"
                        ]
                    ]
                }
        else:
            properties.pop("design_verification", None)
    else:
        properties["packet_type"] = {"enum": [output_packet]}
        mutation_owner = assignment.get("mutation_owner") is True
        selection = projected.get("convention_selection")
        selected_conventions = (
            selection.get("selected_conventions")
            if isinstance(selection, dict)
            and isinstance(selection.get("selected_conventions"), list)
            else []
        )
        research_context = projected.get("research_context")
        coverage_context = projected.get("coverage_context")
        required = schema.get("required")
        if not isinstance(required, list):
            raise MaestroError(
                "PACKET_OUTPUT_SCHEMA_INVALID",
                "The terminal Packet output schema has no required field set.",
            )
        if mutation_owner and selected_conventions:
            required.append("convention_dispositions")
        else:
            properties.pop("convention_dispositions", None)
        if mutation_owner and isinstance(research_context, dict):
            required.append("research_dispositions")
        else:
            properties.pop("research_dispositions", None)
        if mutation_owner and isinstance(coverage_context, dict):
            required.append("coverage_dispositions")
        else:
            properties.pop("coverage_dispositions", None)
        design_context = projected.get("design_assurance_context")
        if (
            mutation_owner
            and isinstance(design_context, dict)
            and design_context.get("role") == "implementation"
        ):
            required.append("design_assurance_result")
            decision_packet = design_context["decision_packet"]
            decision_ids = [
                item["decision_id"]
                for item in decision_packet["decisions"]
            ]
            scenario_ids = [
                item["scenario_id"]
                for item in decision_packet["verification_scenarios"]
            ]
            disposition = schema["$defs"].get(
                "designDecisionDisposition"
            )
            if isinstance(disposition, dict):
                disposition["properties"]["decision_id"] = {
                    "enum": decision_ids
                }
                implementation_paths = sorted(
                    {
                        item["path"]
                        for item in projected["surface_map"]["artifacts"]
                        if item["state"] == "existing"
                    }
                )
                disposition["properties"]["implementation_refs"][
                    "items"
                ] = {"enum": implementation_paths}
            artifact = schema["$defs"].get("designRenderedArtifact")
            if isinstance(artifact, dict):
                artifact["properties"]["scenario_id"] = {
                    "enum": scenario_ids
                }
                artifact["properties"]["artifact_path"] = {
                    "enum": [
                        item["artifact_path"]
                        for item in decision_packet[
                            "verification_scenarios"
                        ]
                    ]
                }
            schema["$defs"]["designAssuranceResult"]["properties"][
                "decision_packet_id"
            ] = {"enum": [decision_packet["packet_id"]]}
        else:
            properties.pop("design_assurance_result", None)
    return schema


def _project_document_selection(
    repo: Path,
    plan: dict[str, Any],
    assignment: dict[str, Any],
    target_paths: list[str],
    *,
    decision_authorized: bool,
) -> tuple[dict[str, Any], list[str]]:
    selection = select_documents(
        repo,
        plan["goal"],
        assignment["lens_ids"],
        target_paths,
        decision_authorized=decision_authorized,
    )
    selected_documents = selection.get("required_documents")
    if not isinstance(selected_documents, list):
        selected_documents = selection.get("documents", [])
    compact_documents: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}
    for item in selected_documents:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
            or _DIGEST.fullmatch(item["sha256"]) is None
        ):
            continue
        compact = {
            "path": item["path"],
            "sha256": item["sha256"],
            "reason": (
                item.get("reason")
                if _line(item.get("reason"), 500)
                else "selected by maestro docs"
            ),
            "document_type": (
                item.get("document_type")
                if isinstance(item.get("document_type"), str)
                else "map"
            ),
        }
        compact_documents.append(compact)
        by_path[item["path"]] = compact
    convention_paths = selection.get("selected_conventions", [])
    compact_conventions = [
        {
            "path": path,
            "sha256": by_path[path]["sha256"],
            "reason": by_path[path]["reason"],
        }
        for path in convention_paths
        if isinstance(path, str) and path in by_path
    ]
    payload = {
        "schema_version": CONVENTION_SELECTION_VERSION,
        "selector_version": selection.get("schema_version"),
        "goal_digest": sha256_text(plan["goal"]),
        "target_paths": target_paths,
        "evidence_status": selection.get("evidence_status"),
        "documents": compact_documents,
        "selected_conventions": compact_conventions,
        "missing_evidence": [
            item
            for item in selection.get("missing_evidence", [])
            if _line(item, 500)
        ][:8],
    }
    projected = {
        **payload,
        "selection_digest": sha256_text(canonical_json(payload)),
    }
    return projected, [item["path"] for item in compact_documents]


def _valid_convention_selection(
    value: Any,
    *,
    goal: Any,
) -> bool:
    fields = {
        "schema_version",
        "selection_digest",
        "selector_version",
        "goal_digest",
        "target_paths",
        "evidence_status",
        "documents",
        "selected_conventions",
        "missing_evidence",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema_version") != CONVENTION_SELECTION_VERSION
        or value.get("selector_version") != "maestro_docs_selection_v1"
        or not isinstance(goal, str)
        or value.get("goal_digest") != sha256_text(goal)
        or value.get("evidence_status")
        not in {"sufficient", "insufficient"}
    ):
        return False
    payload = copy.deepcopy(value)
    selection_digest = payload.pop("selection_digest")
    if (
        not isinstance(selection_digest, str)
        or _DIGEST.fullmatch(selection_digest) is None
        or selection_digest != sha256_text(canonical_json(payload))
    ):
        return False
    target_paths = value.get("target_paths")
    if (
        not isinstance(target_paths, list)
        or len(target_paths) > 10
        or len(set(target_paths)) != len(target_paths)
        or not all(_relative_path(path) for path in target_paths)
    ):
        return False
    documents = value.get("documents")
    if not isinstance(documents, list) or len(documents) > 8:
        return False
    document_refs: set[tuple[str, str]] = set()
    for item in documents:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"path", "sha256", "reason", "document_type"}
            or not _relative_path(item.get("path"))
            or not isinstance(item.get("sha256"), str)
            or _DIGEST.fullmatch(item["sha256"]) is None
            or not _line(item.get("reason"), 500)
            or not _line(item.get("document_type"), 100)
        ):
            return False
        reference = (item["path"], item["sha256"])
        if reference in document_refs:
            return False
        document_refs.add(reference)
    conventions = value.get("selected_conventions")
    if not isinstance(conventions, list) or len(conventions) > 8:
        return False
    convention_refs: set[tuple[str, str]] = set()
    for item in conventions:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256", "reason"}
            or not isinstance(item.get("path"), str)
            or not item["path"].startswith("docs/conventions/")
            or not item["path"].endswith(".md")
            or not _relative_path(item["path"])
            or not isinstance(item.get("sha256"), str)
            or _DIGEST.fullmatch(item["sha256"]) is None
            or not _line(item.get("reason"), 500)
            or (item["path"], item["sha256"]) not in document_refs
        ):
            return False
        reference = (item["path"], item["sha256"])
        if reference in convention_refs:
            return False
        convention_refs.add(reference)
    missing = value.get("missing_evidence")
    if (
        not isinstance(missing, list)
        or len(missing) > 8
        or len(set(missing)) != len(missing)
        or not all(_line(item, 500) for item in missing)
        or (value["evidence_status"] == "sufficient" and missing)
    ):
        return False
    return True


def _exact(
    value: Any,
    fields: set[str],
    path: str,
    issues: list[dict[str, str]],
) -> bool:
    if not isinstance(value, dict):
        issues.append(_issue("CONTRACT_OBJECT_REQUIRED", path, "Expected an object."))
        return False
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing:
        issues.append(
            _issue(
                "CONTRACT_FIELDS_MISSING",
                path,
                f"Missing fields: {', '.join(missing)}.",
            )
        )
    if unknown:
        issues.append(
            _issue(
                "CONTRACT_FIELDS_UNKNOWN",
                path,
                f"Unsupported fields: {', '.join(unknown)}.",
            )
        )
    return not missing and not unknown


def _line(value: Any, maximum: int, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    return (
        isinstance(value, str)
        and 0 < len(value.strip()) <= maximum
        and not any(character in value for character in "\r\n\x00")
        and "```" not in value
    )


def _id(value: Any) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _lines(
    value: Any,
    maximum_items: int,
    *,
    allow_empty: bool = True,
    identifiers: bool = False,
) -> bool:
    if (
        not isinstance(value, list)
        or len(value) > maximum_items
        or (not allow_empty and not value)
    ):
        return False
    if not all(
        _id(item) if identifiers else _line(item, 240)
        for item in value
    ):
        return False
    return len(value) == len(set(value))


def _relative_path(value: Any) -> bool:
    if not _line(value, 300) or "\\" in value:
        return False
    path = Path(value)
    return (
        bool(path.parts)
        and path != Path(".")
        and not path.is_absolute()
        and ".." not in path.parts
    )


def _assignments(plan: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(plan, dict) or not isinstance(plan.get("assignments"), list):
        return {}
    return {
        item["assignment_id"]: item
        for item in plan["assignments"]
        if isinstance(item, dict) and isinstance(item.get("assignment_id"), str)
    }


def _assignment_ancestors(
    plan: Any,
    assignment_id: str,
) -> set[str]:
    assignments = _assignments(plan)
    pending = list(assignments.get(assignment_id, {}).get("depends_on", []))
    ancestors: set[str] = set()
    while pending:
        current = pending.pop()
        if current in ancestors or current not in assignments:
            continue
        ancestors.add(current)
        pending.extend(assignments[current].get("depends_on", []))
    return ancestors


def expected_verification_target(
    plan: Any,
    verifier_assignment_id: str,
) -> dict[str, str] | None:
    assignments = _assignments(plan)
    verifier = assignments.get(verifier_assignment_id)
    mutation_owners = [
        item
        for item in assignments.values()
        if item.get("mutation_owner") is True
    ]
    if (
        not isinstance(verifier, dict)
        or verifier.get("executor_id") != "verifier"
        or (
            verifier.get("output_packet") is not None
            and verifier.get("output_packet") != "VerificationVerdict"
        )
        or (
            verifier.get("output_packet") is None
            and verifier.get("kind") != "verification"
        )
        or len(mutation_owners) != 1
    ):
        return None
    target = mutation_owners[0]
    route = (
        target.get("model_route")
        if isinstance(target.get("model_route"), dict)
        else target
    )
    if (
        target.get("assignment_id")
        not in _assignment_ancestors(plan, verifier_assignment_id)
        or not isinstance(route, dict)
        or not isinstance(route.get("execution_unit_id"), str)
        or not isinstance(route.get("model_route_id"), str)
    ):
        return None
    return {
        "assignment_id": target["assignment_id"],
        "execution_unit_id": route["execution_unit_id"],
        "model_route_id": route["model_route_id"],
    }


_expected_verification_target = expected_verification_target


def _plan_issues(
    plan: Any,
    repo_path: str | Path | None = None,
    research_bundle: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    try:
        result = validate_route_v2(
            plan,
            repo_path=repo_path,
            research_bundle=research_bundle,
        )
    except (MaestroError, OSError, TypeError, ValueError) as exc:
        return [_issue("ASSIGNMENT_PLAN_INVALID", "plan", str(exc))]
    if result["status"] == "PASS":
        return []
    return [
        _issue(
            "ASSIGNMENT_PLAN_INVALID",
            f"plan.{item['path']}",
            item["message"],
        )
        for item in result["issues"]
    ]


def _execution_context(
    plan: Any,
    *,
    repo_path: str | Path | None = None,
    research_bundle: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, str]]]:
    """Normalize a direct route or a validated decision enactment wrapper."""

    context = normalize_execution_contract(
        plan,
        repo_path=repo_path,
        research_bundle=research_bundle,
    )
    if context["status"] != "PASS":
        return (
            {},
            None,
            [
                _issue(
                    "ASSIGNMENT_EXECUTION_PLAN_INVALID",
                    f"plan.{item['path']}",
                    item["message"],
                )
                for item in context["issues"]
            ],
        )
    return (
        context["route_plan"],
        context["execution_authorization"],
        [],
    )


def _coverage_context(
    plan: dict[str, Any],
    *,
    goal: str,
    repo: Path,
    coverage: dict[str, Any] | None,
    coverage_admission: dict[str, Any] | None,
    coverage_projection: dict[str, Any] | None,
    expertise_work_plan: dict[str, Any] | None,
    expertise_closure: dict[str, Any] | None,
    research_bundle: dict[str, Any] | None,
    expertise_research_bundles: Any,
    require_ready: bool,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    binding = plan.get("coverage_binding")
    supplied = any(
        item is not None
        for item in (
            coverage,
            coverage_admission,
            coverage_projection,
            expertise_work_plan,
            expertise_closure,
        )
    ) or bool(expertise_research_bundles)
    if binding is None:
        if supplied:
            return (
                None,
                [
                    _issue(
                        "PROJECTION_COVERAGE_UNEXPECTED",
                        "coverage",
                        "Coverage artifacts require a route bound to that Coverage.",
                    )
                ],
            )
        return None, []
    if not isinstance(coverage, dict) or not isinstance(
        coverage_admission,
        dict,
    ):
        return (
            None,
            [
                _issue(
                    "PROJECTION_COVERAGE_REQUIRED",
                    "coverage",
                    "A Coverage-bound route requires its exact Coverage and final admission.",
                )
            ],
        )
    if (
        coverage.get("coverage_id") != binding.get("coverage_id")
        or coverage.get("goal_digest") != binding.get("goal_digest")
    ):
        return (
            None,
            [
                _issue(
                    "PROJECTION_COVERAGE_BINDING_MISMATCH",
                    "coverage",
                    "Coverage does not match the route binding.",
                )
            ],
        )
    candidate_ids = coverage_admission.get("compiled_candidate_ids")
    if not isinstance(candidate_ids, list):
        candidate_ids = []
    validation = validate_task_coverage_admission(
        coverage_admission,
        repo_path=repo,
        goal=goal,
        coverage=coverage,
        plan=plan,
        coverage_projection=coverage_projection,
        expertise_work_plan=expertise_work_plan,
        expertise_closure=expertise_closure,
        candidate_ids=candidate_ids,
        research_bundle=research_bundle,
        expertise_research_bundles=expertise_research_bundles,
        allow_candidates=True,
    )
    if validation["status"] != "PASS":
        return (
            None,
            [
                _issue(
                    "PROJECTION_COVERAGE_ADMISSION_INVALID",
                    f"coverage_admission.{item['path']}",
                    item["message"],
                )
                for item in validation["issues"]
            ],
        )
    if require_ready and coverage_admission.get("status") != "READY":
        return (
            None,
            [
                _issue(
                    "PROJECTION_COVERAGE_NOT_READY",
                    "coverage_admission.status",
                    "Mutation is blocked until every blocking and important Coverage allocation is ready.",
                )
            ],
        )
    return (
        {
            "schema_version": "maestro_assignment_coverage_context_v1",
            "coverage_id": coverage["coverage_id"],
            "admission_id": coverage_admission["admission_id"],
            "coverage_projection_id": coverage_admission.get(
                "coverage_projection_id"
            ),
            "expertise_work_plan_id": coverage_admission.get(
                "expertise_work_plan_id"
            ),
            "expertise_closure_id": coverage_admission.get(
                "expertise_closure_id"
            ),
            "items": [
                {
                    "item_id": item["item_id"],
                    "kind": item["kind"],
                    "summary": item["summary"],
                    "failure_if_omitted": item["failure_if_omitted"],
                    "materiality": item["materiality"],
                    "depends_on": copy.deepcopy(item["depends_on"]),
                    "allocations": [
                        {
                            "kind": allocation["kind"],
                            "target_ref": allocation["target_ref"],
                        }
                        for allocation in item["allocations"]
                    ],
                }
                for item in coverage["items"]
            ],
            "evidence_entries": copy.deepcopy(
                coverage_projection.get("entries", [])
                if isinstance(coverage_projection, dict)
                else []
            ),
            "expertise_handoff": copy.deepcopy(
                expertise_closure
                if isinstance(expertise_closure, dict)
                else None
            ),
        },
        [],
    )


def _research_context(
    plan: dict[str, Any],
    research_bundle: dict[str, Any] | None,
    repo: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Validate and bind optional preflight research to one route plan."""

    issues: list[dict[str, str]] = []
    expertise = plan.get("expertise")
    requirement = (
        expertise.get("research_requirement")
        if isinstance(expertise, dict)
        else None
    )
    gate = requirement.get("gate") if isinstance(requirement, dict) else None
    if gate != "satisfied":
        if research_bundle is not None:
            issues.append(
                _issue(
                    "PROJECTION_RESEARCH_NOT_APPLICABLE",
                    "research_bundle",
                    "Research evidence is accepted only for a satisfied route research gate.",
                )
            )
        return None, issues
    if research_bundle is None:
        issues.append(
            _issue(
                "PROJECTION_RESEARCH_REQUIRED",
                "research_bundle",
                "The satisfied route gate requires its completed bound ResearchBundle.",
            )
        )
        return None, issues

    validation = validate_research_bundle(
        research_bundle,
        repo_path=repo,
    )
    if validation["status"] != "PASS":
        issues.extend(
            _issue(
                "PROJECTION_RESEARCH_INVALID",
                f"research_bundle.{item['path']}",
                item["message"],
            )
            for item in validation["issues"]
        )
        return None, issues
    if validation["evidence_status"] != "completed":
        issues.append(
            _issue(
                "PROJECTION_RESEARCH_INSUFFICIENT",
                "research_bundle.status",
                "Only completed research evidence may enter an executable Assignment.",
            )
        )
    expected_digest = requirement.get("evidence_digest")
    if validation["artifact_digest"] != expected_digest:
        issues.append(
            _issue(
                "PROJECTION_RESEARCH_DIGEST_MISMATCH",
                "research_bundle",
                "ResearchBundle digest does not match the satisfied route gate.",
            )
        )
    goal = plan.get("goal")
    if not isinstance(goal, str):
        issues.append(
            _issue(
                "PROJECTION_RESEARCH_BINDING_UNAVAILABLE",
                "goal",
                "A valid route goal is required before research evidence can be bound.",
            )
        )
    elif research_bundle.get("request_binding") != expected_research_binding(
        goal,
        expertise,
    ):
        issues.append(
            _issue(
                "PROJECTION_RESEARCH_BINDING_MISMATCH",
                "research_bundle.request_binding",
                "ResearchBundle binding does not match this goal and selected expertise.",
            )
        )
    if issues:
        return None, issues
    try:
        return project_research_context(
            research_bundle,
            repo_path=repo,
        ), []
    except MaestroError as exc:
        return None, [
            _issue(
                "PROJECTION_RESEARCH_INVALID",
                "research_bundle",
                exc.message,
            )
        ]


def _projection_research_issues(
    plan: Any,
    projection: Any,
    research_bundle: dict[str, Any] | None,
    *,
    repo_path: str | Path | None,
) -> list[dict[str, str]]:
    """Bind packet validation to the exact ResearchBundle, not a self-digest."""

    issues: list[dict[str, str]] = []
    plan_value = plan if isinstance(plan, dict) else {}
    expertise = plan_value.get("expertise")
    requirement = (
        expertise.get("research_requirement")
        if isinstance(expertise, dict)
        else None
    )
    gate = requirement.get("gate") if isinstance(requirement, dict) else None
    projected = _projection_value(projection)
    context = (
        projected.get("research_context")
        if isinstance(projected, dict)
        else None
    )
    if gate != "satisfied":
        if research_bundle is not None:
            issues.append(
                _issue(
                    "PACKET_RESEARCH_BUNDLE_UNEXPECTED",
                    "research_bundle",
                    "ResearchBundle is accepted only for a satisfied plan gate.",
                )
            )
        if context is not None:
            issues.append(
                _issue(
                    "PACKET_RESEARCH_CONTEXT_UNEXPECTED",
                    "projection.research_context",
                    "Projection research context is not allowed without a satisfied gate.",
                )
            )
        return issues
    if research_bundle is None:
        issues.append(
            _issue(
                "PACKET_RESEARCH_BUNDLE_REQUIRED",
                "research_bundle",
                "Packet validation requires the exact ResearchBundle for a satisfied gate.",
            )
        )
        return issues
    goal = plan_value.get("goal")
    if not isinstance(goal, str) or not isinstance(expertise, dict):
        issues.append(
            _issue(
                "PACKET_RESEARCH_BINDING_UNAVAILABLE",
                "plan",
                "A valid plan goal and expertise selection are required.",
            )
        )
        return issues
    try:
        validation = require_completed_research_bundle(
            research_bundle,
            goal=goal,
            expertise=expertise,
            repo_path=repo_path,
        )
        expected_context = project_research_context(
            research_bundle,
            repo_path=repo_path,
        )
    except MaestroError as exc:
        issues.append(
            _issue(
                "PACKET_RESEARCH_BUNDLE_INVALID",
                "research_bundle",
                exc.message,
            )
        )
        return issues
    if validation["artifact_digest"] != requirement.get("evidence_digest"):
        issues.append(
            _issue(
                "PACKET_RESEARCH_DIGEST_MISMATCH",
                "research_bundle",
                "ResearchBundle digest does not match the satisfied plan gate.",
            )
        )
    if context != expected_context:
        issues.append(
            _issue(
                "PACKET_RESEARCH_CONTEXT_MISMATCH",
                "projection.research_context",
                "Projection must preserve the exact validated ResearchBundle context.",
            )
        )
    return issues


def _regular_file(repo: Path, relative_path: str) -> Path | None:
    try:
        target = safe_target(repo, relative_path)
    except MaestroError:
        return None
    return (
        target
        if target.is_file() and not target.is_symlink()
        else None
    )


def validate_engineering_baseline(
    baseline: Any,
    *,
    repo_path: str | Path | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a small project-evidence surface and six coverage checks."""

    issues: list[dict[str, str]] = []
    repo: Path | None = None
    if repo_path is not None:
        try:
            repo = ensure_repo(repo_path)
        except MaestroError as exc:
            issues.append(_issue("BASELINE_REPO_INVALID", "repo", exc.message))
    fields = {"schema_version", "goal_digest", "surface_map", "checks"}
    if not _exact(baseline, fields, "$", issues):
        return _validation(baseline, issues)
    if baseline["schema_version"] != ENGINEERING_BASELINE_VERSION:
        issues.append(
            _issue(
                "BASELINE_VERSION_INVALID",
                "schema_version",
                f"Expected {ENGINEERING_BASELINE_VERSION}.",
            )
        )
    if not isinstance(baseline["goal_digest"], str) or _DIGEST.fullmatch(
        baseline["goal_digest"]
    ) is None:
        issues.append(
            _issue(
                "BASELINE_GOAL_DIGEST_INVALID",
                "goal_digest",
                "goal_digest must be a SHA-256 digest.",
            )
        )
    if (
        isinstance(plan, dict)
        and isinstance(plan.get("goal"), str)
        and baseline["goal_digest"] != sha256_text(plan["goal"])
    ):
        issues.append(
            _issue(
                "BASELINE_GOAL_MISMATCH",
                "goal_digest",
                "Baseline goal does not match the route plan.",
            )
        )

    surface_fields = {
        "artifacts",
        "affected_boundaries",
        "stakeholders",
        "lifecycle_states",
    }
    surface = baseline["surface_map"]
    if not _exact(surface, surface_fields, "surface_map", issues):
        return _validation(baseline, issues)

    artifacts = surface["artifacts"]
    artifact_ids: set[str] = set()
    if (
        not isinstance(artifacts, list)
        or not artifacts
        or len(artifacts) > 10
    ):
        issues.append(
            _issue(
                "BASELINE_ARTIFACTS_INVALID",
                "surface_map.artifacts",
                "artifacts must contain 1 to 10 items.",
            )
        )
        artifacts = []
    for index, artifact in enumerate(artifacts):
        path = f"surface_map.artifacts[{index}]"
        if not _exact(
            artifact,
            {"artifact_id", "kind", "path", "state"},
            path,
            issues,
        ):
            continue
        artifact_id = artifact["artifact_id"]
        if not _id(artifact_id) or artifact_id in artifact_ids:
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_ID_INVALID",
                    f"{path}.artifact_id",
                    "artifact_id must be unique lowercase kebab-case.",
                )
            )
        else:
            artifact_ids.add(artifact_id)
        if (
            not isinstance(artifact["kind"], str)
            or artifact["kind"] not in _ARTIFACT_KINDS
        ):
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_KIND_INVALID",
                    f"{path}.kind",
                    "Unsupported artifact kind.",
                )
            )
        if not _relative_path(artifact["path"]):
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_PATH_INVALID",
                    f"{path}.path",
                    "Artifact path must be repository-relative.",
                )
            )
        if (
            not isinstance(artifact["state"], str)
            or artifact["state"] not in {"existing", "planned"}
        ):
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_STATE_INVALID",
                    f"{path}.state",
                    "Artifact state must be existing or planned.",
                )
            )
        if (
            repo is not None
            and artifact["state"] == "existing"
            and _relative_path(artifact["path"])
            and _regular_file(repo, artifact["path"]) is None
        ):
            issues.append(
                _issue(
                    "BASELINE_ARTIFACT_MISSING",
                    f"{path}.path",
                    "Existing artifact must be a regular non-symlink file.",
                )
            )

    boundaries = surface["affected_boundaries"]
    if not isinstance(boundaries, list) or len(boundaries) > 8:
        issues.append(
            _issue(
                "BASELINE_BOUNDARIES_INVALID",
                "surface_map.affected_boundaries",
                "affected_boundaries must contain at most 8 items.",
            )
        )
        boundaries = []
    boundary_ids: set[str] = set()
    for index, boundary in enumerate(boundaries):
        path = f"surface_map.affected_boundaries[{index}]"
        if not _exact(boundary, {"boundary_id", "artifact_ids"}, path, issues):
            continue
        if not _id(boundary["boundary_id"]) or boundary["boundary_id"] in boundary_ids:
            issues.append(
                _issue(
                    "BASELINE_BOUNDARY_ID_INVALID",
                    f"{path}.boundary_id",
                    "boundary_id must be unique lowercase kebab-case.",
                )
            )
        else:
            boundary_ids.add(boundary["boundary_id"])
        if (
            not _lines(
                boundary["artifact_ids"],
                10,
                allow_empty=False,
                identifiers=True,
            )
            or not set(boundary["artifact_ids"]).issubset(artifact_ids)
        ):
            issues.append(
                _issue(
                    "BASELINE_BOUNDARY_ARTIFACTS_INVALID",
                    f"{path}.artifact_ids",
                    "Boundary artifact_ids must name known artifacts.",
                )
            )

    stakeholders = surface["stakeholders"]
    if not isinstance(stakeholders, list) or len(stakeholders) > 6:
        issues.append(
            _issue(
                "BASELINE_STAKEHOLDERS_INVALID",
                "surface_map.stakeholders",
                "stakeholders must contain at most 6 items.",
            )
        )
        stakeholders = []
    stakeholder_ids: set[str] = set()
    for index, stakeholder in enumerate(stakeholders):
        path = f"surface_map.stakeholders[{index}]"
        if not _exact(
            stakeholder,
            {"stakeholder_id", "concern"},
            path,
            issues,
        ):
            continue
        if (
            not _id(stakeholder["stakeholder_id"])
            or stakeholder["stakeholder_id"] in stakeholder_ids
        ):
            issues.append(
                _issue(
                    "BASELINE_STAKEHOLDER_ID_INVALID",
                    f"{path}.stakeholder_id",
                    "stakeholder_id must be unique lowercase kebab-case.",
                )
            )
        else:
            stakeholder_ids.add(stakeholder["stakeholder_id"])
        if not _line(stakeholder["concern"], 240):
            issues.append(
                _issue(
                    "BASELINE_STAKEHOLDER_CONCERN_INVALID",
                    f"{path}.concern",
                    "Concern must be one bounded line.",
                )
            )

    lifecycle_states = surface["lifecycle_states"]
    if not isinstance(lifecycle_states, list) or len(lifecycle_states) > 8:
        issues.append(
            _issue(
                "BASELINE_LIFECYCLE_INVALID",
                "surface_map.lifecycle_states",
                "lifecycle_states must contain at most 8 items.",
            )
        )
        lifecycle_states = []
    state_ids: set[str] = set()
    for index, state in enumerate(lifecycle_states):
        path = f"surface_map.lifecycle_states[{index}]"
        if not _exact(state, {"state_id", "kind", "artifact_ids"}, path, issues):
            continue
        if not _id(state["state_id"]) or state["state_id"] in state_ids:
            issues.append(
                _issue(
                    "BASELINE_LIFECYCLE_ID_INVALID",
                    f"{path}.state_id",
                    "state_id must be unique lowercase kebab-case.",
                )
            )
        else:
            state_ids.add(state["state_id"])
        if (
            not isinstance(state["kind"], str)
            or state["kind"] not in _LIFECYCLE_KINDS
        ):
            issues.append(
                _issue(
                    "BASELINE_LIFECYCLE_KIND_INVALID",
                    f"{path}.kind",
                    "Unsupported lifecycle kind.",
                )
            )
        if (
            not _lines(
                state["artifact_ids"],
                10,
                allow_empty=False,
                identifiers=True,
            )
            or not set(state["artifact_ids"]).issubset(artifact_ids)
        ):
            issues.append(
                _issue(
                    "BASELINE_LIFECYCLE_ARTIFACTS_INVALID",
                    f"{path}.artifact_ids",
                    "Lifecycle artifact_ids must name known artifacts.",
                )
            )

    checks = baseline["checks"]
    if not isinstance(checks, list) or len(checks) != len(_CHECK_IDS):
        issues.append(
            _issue(
                "BASELINE_CHECKS_INVALID",
                "checks",
                "Exactly six Engineering Baseline checks are required.",
            )
        )
        checks = []
    check_ids: set[str] = set()
    known_assignments = set(_assignments(plan))
    selected_lenses = (
        {
            item
            for item in plan.get("selected_lenses", [])
            if isinstance(item, str)
        }
        if isinstance(plan, dict) and isinstance(plan.get("selected_lenses"), list)
        else set()
    )
    for index, check in enumerate(checks):
        path = f"checks[{index}]"
        if not _exact(
            check,
            {"check_id", "status", "owner", "evidence_refs", "note"},
            path,
            issues,
        ):
            continue
        check_id = check["check_id"]
        if (
            not isinstance(check_id, str)
            or check_id not in _CHECK_IDS
            or check_id in check_ids
        ):
            issues.append(
                _issue(
                    "BASELINE_CHECK_ID_INVALID",
                    f"{path}.check_id",
                    "check_id must be one unique baseline criterion.",
                )
            )
        else:
            check_ids.add(check_id)
        status = check["status"]
        owner = check["owner"]
        refs = check["evidence_refs"]
        if (
            not isinstance(status, str)
            or status not in {"covered", "gap", "not_applicable"}
        ):
            issues.append(
                _issue(
                    "BASELINE_CHECK_STATUS_INVALID",
                    f"{path}.status",
                    "Unsupported check status.",
                )
            )
        if not _lines(refs, 5):
            issues.append(
                _issue(
                    "BASELINE_CHECK_EVIDENCE_INVALID",
                    f"{path}.evidence_refs",
                    "evidence_refs must be a bounded unique list.",
                )
            )
        elif not set(refs).issubset(artifact_ids | {"task-contract"}):
            issues.append(
                _issue(
                    "BASELINE_CHECK_EVIDENCE_UNBOUND",
                    f"{path}.evidence_refs",
                    "Baseline evidence must name a mapped artifact or task-contract.",
                )
            )
        owner_valid = owner == "task-contract"
        if isinstance(owner, str) and owner.startswith("lens:"):
            owner_valid = _id(owner[5:]) and (
                plan is None or owner[5:] in selected_lenses
            )
        if isinstance(owner, str) and owner.startswith("assignment:"):
            owner_valid = _id(owner[11:]) and (
                plan is None or owner[11:] in known_assignments
            )
        if owner is not None and not owner_valid:
            issues.append(
                _issue(
                    "BASELINE_CHECK_OWNER_INVALID",
                    f"{path}.owner",
                    "Owner must bind the task contract, a selected Lens, or an Assignment.",
                )
            )
        if status == "covered" and (not owner_valid or not refs):
            issues.append(
                _issue(
                    "BASELINE_COVERED_UNPROVED",
                    path,
                    "Covered checks require a bound owner and evidence.",
                )
            )
        if status == "gap" and (owner is not None or not refs):
            issues.append(
                _issue(
                    "BASELINE_GAP_INVALID",
                    path,
                    "Gap checks require evidence and no owner.",
                )
            )
        if status == "not_applicable" and owner is not None:
            issues.append(
                _issue(
                    "BASELINE_NOT_APPLICABLE_OWNED",
                    path,
                    "Not-applicable checks cannot have an owner.",
                )
            )
        if not _line(check["note"], 300):
            issues.append(
                _issue(
                    "BASELINE_CHECK_NOTE_INVALID",
                    f"{path}.note",
                    "Note must be one bounded line.",
                )
            )
    if check_ids != _CHECK_IDS:
        issues.append(
            _issue(
                "BASELINE_CHECK_SET_INVALID",
                "checks",
                "The six required check IDs must appear exactly once.",
            )
        )

    execution_status = (
        "GAPS_PRESENT"
        if any(
            isinstance(item, dict) and item.get("status") == "gap"
            for item in checks
        )
        else "READY"
    )
    return _validation(
        baseline,
        issues,
        execution_status=execution_status,
    )


def _projection_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("input"), dict):
        return value["input"]
    return value if isinstance(value, dict) else None


def _projection_bound(
    projection: Any,
    plan_id: Any,
    assignment_id: Any,
) -> bool:
    value = _projection_value(projection)
    if (
        value is None
        or value.get("schema_version") != ASSIGNMENT_INPUT_VERSION
        or value.get("plan_id") != plan_id
        or value.get("assignment_id") != assignment_id
        or not isinstance(value.get("projection_digest"), str)
    ):
        return False
    payload = copy.deepcopy(value)
    digest = payload.pop("projection_digest")
    try:
        return digest == sha256_text(canonical_json(payload))
    except (TypeError, ValueError, OverflowError):
        return False


def _dict_items(value: Any) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _projection_refs(
    projection: Any,
) -> tuple[set[str], set[str]]:
    value = _projection_value(projection)
    if value is None:
        return set(), set()
    identifiers: set[str] = set()
    locations: set[str] = set()
    for item in _dict_items(value.get("artifact_refs")):
        if (
            isinstance(item.get("artifact_id"), str)
            and isinstance(item.get("sha256"), str)
            and _DIGEST.fullmatch(item["sha256"]) is not None
        ):
            identifiers.add(item["artifact_id"])
        if isinstance(item.get("path"), str):
            locations.add(item["path"])
    for item in _dict_items(value.get("document_refs")):
        if isinstance(item.get("ref_id"), str):
            identifiers.add(item["ref_id"])
        if isinstance(item.get("path"), str):
            locations.add(item["path"])
    for item in _dict_items(value.get("dependency_packets")):
        if isinstance(item.get("ref_id"), str):
            identifiers.add(item["ref_id"])
    research = value.get("research_context")
    if isinstance(research, dict):
        digest = research.get("evidence_digest")
        if isinstance(digest, str) and _DIGEST.fullmatch(digest) is not None:
            identifiers.add(f"research-bundle:{digest}")
        for item in _dict_items(research.get("artifacts_checked")):
            if isinstance(item.get("artifact_id"), str):
                identifiers.add(f"research-artifact:{item['artifact_id']}")
        for item in _dict_items(research.get("sources")):
            if isinstance(item.get("source_id"), str):
                identifiers.add(f"research-source:{item['source_id']}")
        for item in _dict_items(research.get("claims")):
            if isinstance(item.get("claim_id"), str):
                identifiers.add(f"research-claim:{item['claim_id']}")
    coverage = value.get("coverage_context")
    if isinstance(coverage, dict):
        admission_id = coverage.get("admission_id")
        if (
            isinstance(admission_id, str)
            and _DIGEST.fullmatch(admission_id) is not None
        ):
            identifiers.add(f"coverage-admission:{admission_id}")
        for item in _dict_items(coverage.get("evidence_entries")):
            digest = item.get("evidence_digest")
            if (
                isinstance(digest, str)
                and _DIGEST.fullmatch(digest) is not None
            ):
                identifiers.add(f"coverage-evidence:{digest}")
            if (
                item.get("evidence_kind") == "repository-file"
                and isinstance(item.get("evidence_ref"), str)
            ):
                locations.add(item["evidence_ref"])
        handoff = coverage.get("expertise_handoff")
        if isinstance(handoff, dict):
            closure_id = handoff.get("closure_id")
            if (
                isinstance(closure_id, str)
                and _DIGEST.fullmatch(closure_id) is not None
            ):
                identifiers.add(f"expertise-closure:{closure_id}")
            for result in _dict_items(handoff.get("batch_results")):
                packet_digest = result.get("packet_digest")
                if (
                    isinstance(packet_digest, str)
                    and _DIGEST.fullmatch(packet_digest) is not None
                ):
                    identifiers.add(
                        f"expertise-packet:{packet_digest}"
                    )
    design = value.get("design_assurance_context")
    if isinstance(design, dict):
        packet = design.get("decision_packet")
        if isinstance(packet, dict):
            packet_id = packet.get("packet_id")
            if isinstance(packet_id, str) and _DIGEST.fullmatch(packet_id):
                identifiers.add(f"design-decision:{packet_id}")
            for decision in _dict_items(packet.get("decisions")):
                decision_id = decision.get("decision_id")
                if isinstance(decision_id, str):
                    identifiers.add(f"design-material:{decision_id}")
            for scenario in _dict_items(
                packet.get("verification_scenarios")
            ):
                scenario_id = scenario.get("scenario_id")
                if isinstance(scenario_id, str):
                    identifiers.add(f"design-scenario:{scenario_id}")
        result = design.get("implementation_result")
        if isinstance(result, dict):
            for artifact in _dict_items(result.get("rendered_artifacts")):
                scenario_id = artifact.get("scenario_id")
                digest = artifact.get("sha256")
                if (
                    isinstance(scenario_id, str)
                    and isinstance(digest, str)
                    and _DIGEST.fullmatch(digest)
                ):
                    identifiers.add(
                        f"design-render:{scenario_id}:{digest}"
                    )
                if isinstance(artifact.get("artifact_path"), str):
                    locations.add(artifact["artifact_path"])
    return identifiers, locations


def _projection_artifacts(projection: Any) -> tuple[set[str], set[str]]:
    value = _projection_value(projection)
    if value is None:
        return set(), set()
    identifiers: set[str] = set()
    locations: set[str] = set()
    for item in _dict_items(value.get("artifact_refs")):
        if isinstance(item.get("artifact_id"), str):
            identifiers.add(item["artifact_id"])
        if isinstance(item.get("path"), str):
            locations.add(item["path"])
    return identifiers, locations


def _evidence(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
    *,
    projection: Any = None,
    allow_empty: bool = False,
) -> list[str]:
    if not _lines(value, 5, allow_empty=allow_empty):
        issues.append(
            _issue(
                "PACKET_EVIDENCE_INVALID",
                path,
                "Evidence must be a bounded unique reference list.",
            )
        )
        return []
    refs = value
    if projection is not None:
        allowed, _ = _projection_refs(projection)
        if not set(refs).issubset(allowed):
            issues.append(
                _issue(
                    "PACKET_EVIDENCE_OUT_OF_PROJECTION",
                    path,
                    "Evidence contains a reference outside the Assignment projection.",
                )
            )
    return refs


def _research_disposition_issues(
    dispositions: Any,
    *,
    projection: Any,
    completed: bool,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    projected = _projection_value(projection)
    context = (
        projected.get("research_context")
        if isinstance(projected, dict)
        else None
    )
    synthesis = (
        context.get("synthesis")
        if isinstance(context, dict)
        else None
    )
    adopted = (
        synthesis.get("adopted_claim_ids")
        if isinstance(synthesis, dict)
        and isinstance(synthesis.get("adopted_claim_ids"), list)
        else []
    )
    if not isinstance(context, dict):
        if dispositions is not None:
            issues.append(
                _issue(
                    "PACKET_RESEARCH_DISPOSITIONS_UNEXPECTED",
                    "research_dispositions",
                    "Research dispositions require a bound research projection.",
                )
            )
        return issues
    if completed and dispositions is None:
        issues.append(
            _issue(
                "PACKET_RESEARCH_DISPOSITIONS_REQUIRED",
                "research_dispositions",
                "A completed writer must disposition every adopted research claim.",
            )
        )
        return issues
    if dispositions is None:
        return issues
    if (
        not isinstance(dispositions, list)
        or len(dispositions) != len(adopted)
        or len(dispositions) > 32
    ):
        issues.append(
            _issue(
                "PACKET_RESEARCH_DISPOSITIONS_INVALID",
                "research_dispositions",
                "Research dispositions must exactly match the bounded adopted claim set.",
            )
        )
        return issues

    allowed_refs, _ = _projection_refs(projection)
    project_refs = {
        ref for ref in allowed_refs if not ref.startswith("research-")
    }
    seen: set[str] = set()
    has_conflict = False
    expected = {
        claim_id for claim_id in adopted if isinstance(claim_id, str)
    }
    for index, item in enumerate(dispositions):
        path = f"research_dispositions[{index}]"
        if (
            not isinstance(item, dict)
            or set(item)
            != {"claim_id", "disposition", "reason", "evidence_refs"}
            or not _line(item.get("claim_id"), 128)
            or not _line(item.get("reason"), 1_000)
            or item.get("disposition")
            not in {"applied", "not_applicable", "conflict"}
            or not _lines(
                item.get("evidence_refs"),
                5,
                allow_empty=True,
            )
        ):
            issues.append(
                _issue(
                    "PACKET_RESEARCH_DISPOSITION_INVALID",
                    path,
                    "Research disposition does not satisfy the closed implementation-use contract.",
                )
            )
            continue
        claim_id = item["claim_id"]
        item_refs = set(item["evidence_refs"])
        if claim_id not in expected or claim_id in seen:
            issues.append(
                _issue(
                    "PACKET_RESEARCH_DISPOSITION_MISMATCH",
                    f"{path}.claim_id",
                    "Research claim is duplicated or outside the adopted claim set.",
                )
            )
        seen.add(claim_id)
        if not item_refs.issubset(allowed_refs):
            issues.append(
                _issue(
                    "PACKET_RESEARCH_EVIDENCE_OUT_OF_PROJECTION",
                    f"{path}.evidence_refs",
                    "Research-use evidence contains a reference outside the projection.",
                )
            )
        if (
            item["disposition"] == "applied"
            and not item_refs.intersection(project_refs)
        ):
            issues.append(
                _issue(
                    "PACKET_RESEARCH_APPLICATION_EVIDENCE_REQUIRED",
                    f"{path}.evidence_refs",
                    "Applied research needs at least one projected project or verification evidence reference.",
                )
            )
        has_conflict = has_conflict or item["disposition"] == "conflict"
    if seen != expected:
        issues.append(
            _issue(
                "PACKET_RESEARCH_DISPOSITION_SET_MISMATCH",
                "research_dispositions",
                "Research dispositions must cover the exact adopted claim set.",
            )
        )
    if completed and has_conflict:
        issues.append(
            _issue(
                "PACKET_RESEARCH_CONFLICT_UNRESOLVED",
                "research_dispositions",
                "A writer cannot complete with an unresolved research conflict.",
            )
        )
    return issues


def _expertise_disposition_issues(
    dispositions: Any,
    *,
    projection: Any,
    required: bool,
    completed: bool,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    projected = _projection_value(projection)
    expertise_load = (
        projected.get("expertise_load")
        if isinstance(projected, dict)
        else None
    )
    expected = {
        (
            pack.get("expertise_pack_id"),
            guide.get("guide_id"),
        ): {
            "definition_digest": pack.get("definition_digest"),
            "skill_definition_digest": guide.get(
                "skill_definition_digest"
            ),
        }
        for pack in (
            expertise_load.get("packs", [])
            if isinstance(expertise_load, dict)
            else []
        )
        if isinstance(pack, dict)
        for guide in pack.get("guides", [])
        if isinstance(guide, dict)
    }
    if not expected:
        if dispositions is not None and dispositions != []:
            issues.append(
                _issue(
                    "PACKET_EXPERTISE_DISPOSITIONS_UNEXPECTED",
                    "expertise_dispositions",
                    "Guide dispositions require projected Expertise Guides.",
                )
            )
        return issues
    if dispositions is None:
        if required:
            issues.append(
                _issue(
                    "PACKET_EXPERTISE_DISPOSITIONS_REQUIRED",
                    "expertise_dispositions",
                    "The owned Host requires one disposition for every loaded Guide.",
                )
            )
        return issues
    if (
        not isinstance(dispositions, list)
        or len(dispositions) != len(expected)
        or len(dispositions) > 32
    ):
        issues.append(
            _issue(
                "PACKET_EXPERTISE_DISPOSITIONS_INVALID",
                "expertise_dispositions",
                "Expertise dispositions must exactly cover the projected Guide set.",
            )
        )
        return issues

    allowed_refs, _ = _projection_refs(projection)
    application_mode = (
        expertise_load.get("application_mode")
        if isinstance(expertise_load, dict)
        else None
    )
    seen: set[tuple[Any, Any]] = set()
    has_conflict = False
    for index, item in enumerate(dispositions):
        path = f"expertise_dispositions[{index}]"
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "expertise_pack_id",
                "definition_digest",
                "guide_id",
                "skill_definition_digest",
                "disposition",
                "reason",
                "evidence_refs",
            }
            or item.get("disposition")
            not in {
                "consulted",
                "applied",
                "not_applicable",
                "conflict",
            }
            or not _line(item.get("reason"), 400)
            or not _lines(
                item.get("evidence_refs"),
                5,
                allow_empty=True,
            )
        ):
            issues.append(
                _issue(
                    "PACKET_EXPERTISE_DISPOSITION_INVALID",
                    path,
                    "Guide disposition does not satisfy the closed result contract.",
                )
            )
            continue
        key = (
            item["expertise_pack_id"],
            item["guide_id"],
        )
        binding = expected.get(key)
        if (
            binding is None
            or key in seen
            or item["definition_digest"]
            != binding["definition_digest"]
            or item["skill_definition_digest"]
            != binding["skill_definition_digest"]
        ):
            issues.append(
                _issue(
                    "PACKET_EXPERTISE_DISPOSITION_MISMATCH",
                    path,
                    "Guide disposition identity or digest is outside the projection.",
                )
            )
        seen.add(key)
        refs = set(item["evidence_refs"])
        if not refs.issubset(allowed_refs):
            issues.append(
                _issue(
                    "PACKET_EXPERTISE_EVIDENCE_OUT_OF_PROJECTION",
                    f"{path}.evidence_refs",
                    "Guide-use evidence contains a reference outside the projection.",
                )
            )
        if (
            item["disposition"] in {"consulted", "applied"}
            and not refs
        ):
            issues.append(
                _issue(
                    "PACKET_EXPERTISE_APPLICATION_EVIDENCE_REQUIRED",
                    f"{path}.evidence_refs",
                    "Consulted or applied Guides require projected result evidence.",
                )
            )
        if (
            item["disposition"] == "applied"
            and application_mode == "advisory-only"
        ):
            issues.append(
                _issue(
                    "PACKET_EXPERTISE_APPLICATION_FORBIDDEN",
                    f"{path}.disposition",
                    "An advisory-only Assignment cannot claim Guide application.",
                )
            )
        has_conflict = has_conflict or item["disposition"] == "conflict"
    if seen != set(expected):
        issues.append(
            _issue(
                "PACKET_EXPERTISE_DISPOSITION_SET_MISMATCH",
                "expertise_dispositions",
                "Guide dispositions must cover the exact projected Pack and Guide pairs.",
            )
        )
    if completed and has_conflict:
        issues.append(
            _issue(
                "PACKET_EXPERTISE_CONFLICT_UNRESOLVED",
                "expertise_dispositions",
                "A writer cannot complete with an unresolved Expertise conflict.",
            )
        )
    return issues


def _coverage_disposition_issues(
    dispositions: Any,
    *,
    projection: Any,
    completed: bool,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    projected = _projection_value(projection)
    context = (
        projected.get("coverage_context")
        if isinstance(projected, dict)
        else None
    )
    if not isinstance(context, dict):
        if dispositions is not None:
            issues.append(
                _issue(
                    "PACKET_COVERAGE_DISPOSITIONS_UNEXPECTED",
                    "coverage_dispositions",
                    "Coverage dispositions require a bound Coverage context.",
                )
            )
        return issues
    expected: dict[tuple[str, str], str] = {}
    for item in _dict_items(context.get("items")):
        item_id = item.get("item_id")
        if not isinstance(item_id, str):
            continue
        for allocation in _dict_items(item.get("allocations")):
            target_ref = allocation.get("target_ref")
            kind = allocation.get("kind")
            if isinstance(target_ref, str) and isinstance(kind, str):
                expected[(item_id, target_ref)] = kind
    if completed and dispositions is None:
        issues.append(
            _issue(
                "PACKET_COVERAGE_DISPOSITIONS_REQUIRED",
                "coverage_dispositions",
                "A completed writer must disposition every Coverage allocation.",
            )
        )
        return issues
    if dispositions is None:
        return issues
    if (
        not isinstance(dispositions, list)
        or len(dispositions) != len(expected)
        or len(dispositions) > 1_024
    ):
        issues.append(
            _issue(
                "PACKET_COVERAGE_DISPOSITIONS_INVALID",
                "coverage_dispositions",
                "Coverage dispositions must match the exact bounded allocation set.",
            )
        )
        return issues

    seen: set[tuple[str, str]] = set()
    has_conflict = False
    for index, item in enumerate(dispositions):
        path = f"coverage_dispositions[{index}]"
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "item_id",
                "target_ref",
                "disposition",
                "reason",
                "evidence_refs",
            }
            or not _line(item.get("item_id"), 128)
            or not _line(item.get("target_ref"), 512)
            or not _line(item.get("reason"), 1_000)
            or item.get("disposition")
            not in {
                "applied",
                "not_applicable",
                "conflict",
                "deferred",
            }
        ):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_DISPOSITION_INVALID",
                    path,
                    "Coverage disposition fields are invalid.",
                )
            )
            continue
        key = (item["item_id"], item["target_ref"])
        allocation_kind = expected.get(key)
        if allocation_kind is None or key in seen:
            issues.append(
                _issue(
                    "PACKET_COVERAGE_DISPOSITION_MISMATCH",
                    path,
                    "Coverage disposition is duplicated or outside the projected set.",
                )
            )
        seen.add(key)
        _evidence(
            item.get("evidence_refs"),
            f"{path}.evidence_refs",
            issues,
            projection=projection,
            allow_empty=False,
        )
        if (
            item["disposition"] == "deferred"
            and allocation_kind
            not in {"deferred-explicit", "out-of-scope-explicit"}
        ):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_DEFERRED_UNAUTHORIZED",
                    f"{path}.disposition",
                    "Only an explicitly deferred or out-of-scope allocation may be reported as deferred.",
                )
            )
        has_conflict = has_conflict or item["disposition"] == "conflict"
    if seen != set(expected):
        issues.append(
            _issue(
                "PACKET_COVERAGE_DISPOSITION_SET_MISMATCH",
                "coverage_dispositions",
                "Coverage dispositions do not cover the exact projected allocation set.",
            )
        )
    if completed and has_conflict:
        issues.append(
            _issue(
                "PACKET_COVERAGE_CONFLICT_UNRESOLVED",
                "coverage_dispositions",
                "A writer cannot complete with an unresolved Coverage conflict.",
            )
        )
    return issues


def validate_finding_packet(
    packet: Any,
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any] | None = None,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate FindingPacket structure and bindings, not claim truth."""

    issues = _plan_issues(plan, repo_path)
    plan_value = plan if isinstance(plan, dict) else {}
    assignment = _assignments(plan).get(assignment_id)
    if assignment is None:
        issues.append(
            _issue(
                "PACKET_ASSIGNMENT_UNKNOWN",
                "assignment_id",
                f"Unknown Assignment: {assignment_id}.",
            )
        )
    elif assignment.get("output_packet") != "FindingPacket":
        issues.append(
            _issue(
                "PACKET_TYPE_MISMATCH",
                "schema_version",
                "Assignment does not return FindingPacket.",
            )
        )
    packet_fields = {
        "schema_version",
        "plan_id",
        "assignment_id",
        "lens_ids",
        "verdict",
        "findings",
        "coverage_gaps",
        "uncertainties",
        "inspected",
        "skipped",
    }
    if isinstance(packet, dict) and "expertise_dispositions" in packet:
        packet_fields.add("expertise_dispositions")
    if not _exact(packet, packet_fields, "$", issues):
        return _validation(packet, issues)
    if packet["schema_version"] != FINDING_PACKET_VERSION:
        issues.append(
            _issue(
                "PACKET_VERSION_INVALID",
                "schema_version",
                f"Expected {FINDING_PACKET_VERSION}.",
            )
        )
    if packet["plan_id"] != plan_value.get("plan_id"):
        issues.append(
            _issue("PACKET_PLAN_MISMATCH", "plan_id", "Packet plan does not match.")
        )
    if packet["assignment_id"] != assignment_id:
        issues.append(
            _issue(
                "PACKET_ASSIGNMENT_MISMATCH",
                "assignment_id",
                "Packet Assignment does not match.",
            )
        )
    expected_lenses = assignment.get("lens_ids", []) if assignment else []
    if (
        not _lines(packet["lens_ids"], 3, allow_empty=False, identifiers=True)
        or packet["lens_ids"] != expected_lenses
    ):
        issues.append(
            _issue(
                "PACKET_LENS_BINDING_INVALID",
                "lens_ids",
                "lens_ids must exactly match the Assignment.",
            )
        )
    if projection is not None:
        if not _projection_bound(
            projection,
            packet["plan_id"],
            assignment_id,
        ):
            issues.append(
                _issue(
                    "PACKET_PROJECTION_INVALID",
                    "projection",
                    "Projection is not bound to this plan and Assignment.",
                )
            )
    if (
        not isinstance(packet["verdict"], str)
        or packet["verdict"] not in _VERDICTS
    ):
        issues.append(
            _issue("PACKET_VERDICT_INVALID", "verdict", "Unsupported verdict.")
        )

    findings = packet["findings"]
    if not isinstance(findings, list) or len(findings) > 5:
        issues.append(
            _issue(
                "PACKET_FINDINGS_INVALID",
                "findings",
                "findings must contain at most 5 items.",
            )
        )
        findings = []
    finding_fields = {
        "owner_lens_id",
        "location",
        "severity",
        "claim",
        "evidence_refs",
        "counterexample",
        "suggested_action",
        "fingerprint",
    }
    _, allowed_locations = _projection_artifacts(projection)
    fingerprints: set[str] = set()
    for index, finding in enumerate(findings):
        path = f"findings[{index}]"
        if not _exact(finding, finding_fields, path, issues):
            continue
        if (
            not isinstance(finding["owner_lens_id"], str)
            or finding["owner_lens_id"] not in expected_lenses
        ):
            issues.append(
                _issue(
                    "PACKET_FINDING_SCOPE_INVALID",
                    f"{path}.owner_lens_id",
                    "Finding owner is outside the Assignment Lens set.",
                )
            )
        if (
            not isinstance(finding["severity"], str)
            or finding["severity"] not in _SEVERITIES
        ):
            issues.append(
                _issue(
                    "PACKET_FINDING_SEVERITY_INVALID",
                    f"{path}.severity",
                    "Finding severity must be medium or higher.",
                )
            )
        for field, maximum in (
            ("location", 300),
            ("claim", 500),
            ("suggested_action", 400),
            ("fingerprint", 160),
        ):
            if not _line(finding[field], maximum):
                issues.append(
                    _issue(
                        "PACKET_TEXT_INVALID",
                        f"{path}.{field}",
                        "Packet text must be one bounded line without code blocks.",
                    )
                )
        if not _line(finding["counterexample"], 400, nullable=True):
            issues.append(
                _issue(
                    "PACKET_TEXT_INVALID",
                    f"{path}.counterexample",
                    "counterexample must be null or one bounded line.",
                )
            )
        _evidence(
            finding["evidence_refs"],
            f"{path}.evidence_refs",
            issues,
            projection=projection,
        )
        if projection is not None and (
            not isinstance(finding["location"], str)
            or not any(
                finding["location"] == location
                or finding["location"].startswith(f"{location}:")
                for location in allowed_locations
            )
        ):
            issues.append(
                _issue(
                    "PACKET_LOCATION_OUT_OF_PROJECTION",
                    f"{path}.location",
                    "Finding location is outside projected artifacts.",
                )
            )
        if (
            isinstance(finding["fingerprint"], str)
            and finding["fingerprint"] in fingerprints
        ):
            issues.append(
                _issue(
                    "PACKET_FINDING_DUPLICATE",
                    f"{path}.fingerprint",
                    "Finding fingerprint is duplicated.",
                )
            )
        if isinstance(finding["fingerprint"], str):
            fingerprints.add(finding["fingerprint"])

    gaps = packet["coverage_gaps"]
    if not isinstance(gaps, list) or len(gaps) > 2:
        issues.append(
            _issue(
                "PACKET_COVERAGE_GAPS_INVALID",
                "coverage_gaps",
                "coverage_gaps must contain at most 2 items.",
            )
        )
        gaps = []
    gap_fields = {
        "affected_artifact",
        "possible_failure",
        "evidence_refs",
        "severity",
        "why_uncovered",
        "suggested_lens",
    }
    registry_lenses = {
        item["lens_id"] for item in load_registry()["lenses"]
    }
    selected_lenses = {
        item
        for item in plan_value.get("selected_lenses", [])
        if isinstance(item, str)
    }
    projected_artifacts, _ = _projection_artifacts(projection)
    gap_keys: set[tuple[str, str]] = set()
    for index, gap in enumerate(gaps):
        path = f"coverage_gaps[{index}]"
        if not _exact(gap, gap_fields, path, issues):
            continue
        if not _id(gap["affected_artifact"]):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_ARTIFACT_INVALID",
                    f"{path}.affected_artifact",
                    "affected_artifact must be a typed artifact ID.",
                )
            )
        if projection is not None and (
            not isinstance(gap["affected_artifact"], str)
            or gap["affected_artifact"] not in projected_artifacts
        ):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_ARTIFACT_UNPROJECTED",
                    f"{path}.affected_artifact",
                    "Coverage gap artifact is outside the projection.",
                )
            )
        if (
            not isinstance(gap["severity"], str)
            or gap["severity"] not in _SEVERITIES
        ):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_SEVERITY_INVALID",
                    f"{path}.severity",
                    "Coverage gap severity must be medium or higher.",
                )
            )
        for field in ("possible_failure", "why_uncovered"):
            if not _line(gap[field], 400):
                issues.append(
                    _issue(
                        "PACKET_TEXT_INVALID",
                        f"{path}.{field}",
                        "Coverage text must be one bounded line.",
                    )
                )
        _evidence(
            gap["evidence_refs"],
            f"{path}.evidence_refs",
            issues,
            projection=projection,
        )
        suggested = gap["suggested_lens"]
        if suggested is not None and (
            not _id(suggested)
            or suggested not in registry_lenses
            or suggested in selected_lenses
        ):
            issues.append(
                _issue(
                    "PACKET_COVERAGE_LENS_INVALID",
                    f"{path}.suggested_lens",
                    "suggested_lens must be an unselected registered Lens or null.",
                )
            )
        if isinstance(gap["affected_artifact"], str) and isinstance(
            gap["possible_failure"], str
        ):
            key = (gap["affected_artifact"], gap["possible_failure"])
            if key in gap_keys:
                issues.append(
                    _issue(
                        "PACKET_COVERAGE_DUPLICATE",
                        path,
                        "Coverage gap duplicates an earlier gap.",
                    )
                )
            gap_keys.add(key)

    for field in ("uncertainties", "skipped"):
        if not _lines(packet[field], 5):
            issues.append(
                _issue(
                    "PACKET_LIST_INVALID",
                    field,
                    f"{field} must be a bounded unique one-line list.",
                )
            )
    if not _lines(packet["inspected"], 10):
        issues.append(
            _issue(
                "PACKET_LIST_INVALID",
                "inspected",
                "inspected must be a bounded unique reference list.",
            )
        )
    inspected_valid = _lines(packet["inspected"], 10)
    if projection is not None and inspected_valid:
        projected_refs, _ = _projection_refs(projection)
        if not set(packet["inspected"]).issubset(projected_refs):
            issues.append(
                _issue(
                    "PACKET_INSPECTED_OUT_OF_PROJECTION",
                    "inspected",
                    "inspected contains a reference outside the projection.",
                )
            )
    verdict = packet["verdict"] if isinstance(packet["verdict"], str) else None
    if verdict == "PASS" and (findings or gaps):
        issues.append(
            _issue(
                "PACKET_PASS_HAS_FINDINGS",
                "verdict",
                "PASS cannot contain findings or coverage gaps.",
            )
        )
    if verdict in {"FINDINGS", "BLOCK"} and not (findings or gaps):
        issues.append(
            _issue(
                "PACKET_FINDING_REQUIRED",
                "verdict",
                "FINDINGS or BLOCK requires a finding or coverage gap.",
            )
        )
    if (
        verdict == "INSUFFICIENT_EVIDENCE"
        and not gaps
        and not packet["uncertainties"]
    ):
        issues.append(
            _issue(
                "PACKET_UNCERTAINTY_REQUIRED",
                "uncertainties",
                "INSUFFICIENT_EVIDENCE requires a gap or uncertainty.",
            )
        )
    return _validation(packet, issues)


def validate_terminal_packet(
    packet: Any,
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any] | None = None,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate one terminal observation; this does not execute retries."""

    issues = _plan_issues(plan, repo_path)
    plan_value = plan if isinstance(plan, dict) else {}
    assignment = _assignments(plan).get(assignment_id)
    if assignment is None:
        issues.append(
            _issue(
                "PACKET_ASSIGNMENT_UNKNOWN",
                "assignment_id",
                f"Unknown Assignment: {assignment_id}.",
            )
        )
    fields = {
        "schema_version",
        "plan_id",
        "assignment_id",
        "packet_type",
        "status",
        "summary",
        "evidence_refs",
        "retryable",
    }
    if isinstance(packet, dict) and "convention_dispositions" in packet:
        fields.add("convention_dispositions")
    if isinstance(packet, dict) and "research_dispositions" in packet:
        fields.add("research_dispositions")
    if isinstance(packet, dict) and "coverage_dispositions" in packet:
        fields.add("coverage_dispositions")
    if isinstance(packet, dict) and "design_assurance_result" in packet:
        fields.add("design_assurance_result")
    if isinstance(packet, dict) and "expertise_dispositions" in packet:
        fields.add("expertise_dispositions")
    if not _exact(packet, fields, "$", issues):
        return _validation(packet, issues)
    if packet["schema_version"] != TERMINAL_PACKET_VERSION:
        issues.append(
            _issue(
                "PACKET_VERSION_INVALID",
                "schema_version",
                f"Expected {TERMINAL_PACKET_VERSION}.",
            )
        )
    if packet["plan_id"] != plan_value.get("plan_id"):
        issues.append(
            _issue("PACKET_PLAN_MISMATCH", "plan_id", "Packet plan does not match.")
        )
    if packet["assignment_id"] != assignment_id:
        issues.append(
            _issue(
                "PACKET_ASSIGNMENT_MISMATCH",
                "assignment_id",
                "Packet Assignment does not match.",
            )
        )
    if assignment is not None and packet["packet_type"] != assignment["output_packet"]:
        issues.append(
            _issue(
                "PACKET_TYPE_MISMATCH",
                "packet_type",
                "Packet type does not match the Assignment output.",
            )
        )
    if (
        packet.get("status") == "completed"
        and assignment is not None
        and assignment["mutation_owner"]
        and projection is None
    ):
        issues.append(
            _issue(
                "PACKET_PROJECTION_REQUIRED",
                "projection",
                "A completed mutation Packet requires its bound Assignment projection.",
            )
        )
    if projection is not None:
        if not _projection_bound(
            projection,
            packet["plan_id"],
            assignment_id,
        ):
            issues.append(
                _issue(
                    "PACKET_PROJECTION_INVALID",
                    "projection",
                    "Projection is not bound to this plan and Assignment.",
                )
            )
    if (
        not isinstance(packet["status"], str)
        or packet["status"] not in _TERMINAL_STATUSES
    ):
        issues.append(
            _issue("PACKET_STATUS_INVALID", "status", "Unsupported terminal status.")
        )
    if not _line(packet["summary"], 400):
        issues.append(
            _issue(
                "PACKET_TEXT_INVALID",
                "summary",
                "Summary must be one bounded line.",
            )
        )
    refs = _evidence(
        packet["evidence_refs"],
        "evidence_refs",
        issues,
        projection=projection,
        allow_empty=packet["status"] != "completed",
    )
    if not isinstance(packet["retryable"], bool):
        issues.append(
            _issue(
                "PACKET_RETRYABLE_INVALID",
                "retryable",
                "retryable must be boolean.",
            )
        )
    elif packet["retryable"] != (packet["status"] == "failed_transient"):
        issues.append(
            _issue(
                "PACKET_RETRYABLE_MISMATCH",
                "retryable",
                "Only failed_transient may be retryable.",
            )
        )
    if (
        packet["status"] == "completed"
        and assignment is not None
        and assignment["output_packet"] == "FindingPacket"
    ):
        issues.append(
            _issue(
                "PACKET_FINDING_PAYLOAD_REQUIRED",
                "status",
                "A completed reviewer must return FindingPacket v2.",
            )
        )
    if (
        packet["status"] == "completed"
        and assignment is not None
        and assignment["output_packet"] == "VerificationVerdict"
    ):
        issues.append(
            _issue(
                "PACKET_VERIFICATION_PAYLOAD_REQUIRED",
                "status",
                "A completed verifier must return VerificationVerdict v1.",
            )
        )
    if packet["status"] == "completed" and not refs:
        issues.append(
            _issue(
                "PACKET_EVIDENCE_REQUIRED",
                "evidence_refs",
                "Completed Assignments require evidence.",
            )
        )
    projected_value = _projection_value(projection)
    design_context = (
        projected_value.get("design_assurance_context")
        if isinstance(projected_value, dict)
        else None
    )
    design_required = (
        assignment is not None
        and assignment["mutation_owner"]
        and isinstance(design_context, dict)
        and design_context.get("role") == "implementation"
    )
    design_result = packet.get("design_assurance_result")
    if design_required and design_result is None:
        issues.append(
            _issue(
                "PACKET_DESIGN_ASSURANCE_RESULT_REQUIRED",
                "design_assurance_result",
                "An assured Product Design writer must report the exact material decisions and rendered scenarios.",
            )
        )
    elif design_result is not None and not design_required:
        issues.append(
            _issue(
                "PACKET_DESIGN_ASSURANCE_RESULT_UNEXPECTED",
                "design_assurance_result",
                "Design assurance results are allowed only for the projected Product Design mutation gate.",
            )
        )
    elif design_required:
        if repo_path is None:
            issues.append(
                _issue(
                    "PACKET_DESIGN_ASSURANCE_REPO_REQUIRED",
                    "design_assurance_result",
                    "Rendered Product Design evidence requires repository-bound validation.",
                )
            )
        else:
            issues.extend(
                validate_design_assurance_result(
                    design_result,
                    decision_packet=design_context["decision_packet"],
                    repo_path=repo_path,
                    completed=packet["status"] == "completed",
                )
            )
            for index, disposition in enumerate(
                (
                    design_result.get("decision_dispositions", [])
                    if isinstance(design_result, dict)
                    else []
                )
            ):
                if isinstance(disposition, dict):
                    _evidence(
                        disposition.get("evidence_refs"),
                        (
                            "design_assurance_result."
                            f"decision_dispositions[{index}].evidence_refs"
                        ),
                        issues,
                        projection=projection,
                        allow_empty=False,
                    )
        required_design_ref = (
            f"design-decision:{design_context['decision_packet']['packet_id']}"
        )
        if packet["status"] == "completed" and required_design_ref not in refs:
            issues.append(
                _issue(
                    "PACKET_DESIGN_ASSURANCE_EVIDENCE_REQUIRED",
                    "evidence_refs",
                    "A completed Product Design writer must cite the bound decision Packet.",
                )
            )
    research_context = (
        projected_value.get("research_context")
        if isinstance(projected_value, dict)
        else None
    )
    if (
        packet["status"] == "completed"
        and assignment is not None
        and assignment["mutation_owner"]
        and isinstance(research_context, dict)
    ):
        required_research_ref = (
            f"research-bundle:{research_context.get('evidence_digest')}"
        )
        if required_research_ref not in refs:
            issues.append(
                _issue(
                    "PACKET_RESEARCH_EVIDENCE_REQUIRED",
                    "evidence_refs",
                    "A completed writer must cite the bound ResearchBundle.",
                )
            )
    selection = (
        projected_value.get("convention_selection")
        if isinstance(projected_value, dict)
        else None
    )
    selection_valid = _valid_convention_selection(
        selection,
        goal=plan_value.get("goal"),
    )
    if (
        projection is not None
        and assignment is not None
        and assignment["mutation_owner"]
        and not selection_valid
    ):
        issues.append(
            _issue(
                "PACKET_CONVENTION_SELECTION_INVALID",
                "projection.convention_selection",
                "A mutation result requires the intact document and Convention selection produced for this goal.",
            )
        )
    selected_conventions = (
        selection.get("selected_conventions", [])
        if selection_valid
        else []
    )
    dispositions = packet.get("convention_dispositions")
    if (
        packet["status"] == "completed"
        and assignment is not None
        and assignment["mutation_owner"]
        and selected_conventions
        and dispositions is None
    ):
        issues.append(
            _issue(
                "PACKET_CONVENTION_DISPOSITIONS_REQUIRED",
                "convention_dispositions",
                "A completed writer must report one disposition for every selected Convention.",
            )
        )
    if dispositions is not None:
        if (
            not isinstance(dispositions, list)
            or len(dispositions) > 8
            or len(dispositions) != len(selected_conventions)
        ):
            issues.append(
                _issue(
                    "PACKET_CONVENTION_DISPOSITIONS_INVALID",
                    "convention_dispositions",
                    "Convention dispositions must match the bounded selected Convention set.",
                )
            )
        else:
            expected = {
                (item.get("path"), item.get("sha256"))
                for item in selected_conventions
                if isinstance(item, dict)
            }
            seen: set[tuple[Any, Any]] = set()
            has_conflict = False
            for index, item in enumerate(dispositions):
                path = f"convention_dispositions[{index}]"
                if (
                    not isinstance(item, dict)
                    or set(item)
                    != {
                        "path",
                        "sha256",
                        "disposition",
                        "reason",
                        "approval_ref",
                    }
                    or not _line(item.get("reason"), 500)
                    or item.get("disposition")
                    not in {
                        "applied",
                        "not_applicable",
                        "waived",
                        "conflict",
                    }
                ):
                    issues.append(
                        _issue(
                            "PACKET_CONVENTION_DISPOSITION_INVALID",
                            path,
                            "Convention disposition does not satisfy the closed execution-report contract.",
                        )
                    )
                    continue
                key = (item.get("path"), item.get("sha256"))
                approval_ref = item.get("approval_ref")
                if key not in expected or key in seen:
                    issues.append(
                        _issue(
                            "PACKET_CONVENTION_DISPOSITION_MISMATCH",
                            path,
                            "Convention disposition is duplicated or outside the selected digest set.",
                        )
                    )
                seen.add(key)
                if item["disposition"] == "waived":
                    if (
                        not isinstance(approval_ref, str)
                        or not approval_ref.startswith("owner_decision:")
                        or not _line(approval_ref, 500)
                    ):
                        issues.append(
                            _issue(
                                "PACKET_CONVENTION_WAIVER_INVALID",
                                f"{path}.approval_ref",
                                "A waiver requires one bounded owner_decision reference.",
                            )
                        )
                elif approval_ref is not None:
                    issues.append(
                        _issue(
                            "PACKET_CONVENTION_APPROVAL_UNEXPECTED",
                            f"{path}.approval_ref",
                            "Only waived Conventions may carry an approval reference.",
                        )
                    )
                has_conflict = has_conflict or item["disposition"] == "conflict"
            if seen != expected:
                issues.append(
                    _issue(
                        "PACKET_CONVENTION_DISPOSITION_SET_MISMATCH",
                        "convention_dispositions",
                        "Convention dispositions do not cover the exact selected path and digest set.",
                    )
                )
            if packet["status"] == "completed" and has_conflict:
                issues.append(
                    _issue(
                        "PACKET_CONVENTION_CONFLICT_UNRESOLVED",
                        "convention_dispositions",
                        "A writer cannot complete while a selected Convention conflict remains open.",
                    )
                )
    if assignment is not None and assignment["mutation_owner"]:
        issues.extend(
            _research_disposition_issues(
                packet.get("research_dispositions"),
                projection=projection,
                completed=packet["status"] == "completed",
            )
        )
        issues.extend(
            _coverage_disposition_issues(
                packet.get("coverage_dispositions"),
                projection=projection,
                completed=packet["status"] == "completed",
            )
        )
    return _validation(packet, issues)


def validate_verification_verdict(
    packet: Any,
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any] | None = None,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a verifier result and its exact upstream model target."""

    issues = _plan_issues(plan, repo_path)
    plan_value = plan if isinstance(plan, dict) else {}
    assignment = _assignments(plan).get(assignment_id)
    if (
        assignment is None
        or assignment.get("output_packet") != "VerificationVerdict"
        or assignment.get("executor_id") != "verifier"
    ):
        issues.append(
            _issue(
                "VERIFICATION_ASSIGNMENT_INVALID",
                "assignment_id",
                "VerificationVerdict requires the exact verifier Assignment.",
            )
        )
    fields = {
        "schema_version",
        "plan_id",
        "assignment_id",
        "packet_type",
        "target_assignment_id",
        "target_execution_unit_id",
        "target_model_route_id",
        "verdict",
        "failure_cause",
        "failure_categories",
        "evidence_refs",
        "summary",
        "writes_performed",
    }
    if isinstance(packet, dict) and "design_verification" in packet:
        fields.add("design_verification")
    if isinstance(packet, dict) and "expertise_dispositions" in packet:
        fields.add("expertise_dispositions")
    if not _exact(packet, fields, "$", issues):
        return _validation(packet, issues)
    if packet["schema_version"] != VERIFICATION_VERDICT_VERSION:
        issues.append(
            _issue(
                "PACKET_VERSION_INVALID",
                "schema_version",
                f"Expected {VERIFICATION_VERDICT_VERSION}.",
            )
        )
    if (
        packet["plan_id"] != plan_value.get("plan_id")
        or packet["assignment_id"] != assignment_id
        or packet["packet_type"] != "VerificationVerdict"
    ):
        issues.append(
            _issue(
                "VERIFICATION_PACKET_BINDING_MISMATCH",
                "plan_id",
                "VerificationVerdict plan, Assignment, or Packet type changed.",
            )
        )
    projected = _projection_value(projection)
    target = (
        projected.get("verification_target")
        if isinstance(projected, dict)
        else None
    )
    expected_target = _expected_verification_target(plan, assignment_id)
    if (
        projection is None
        or not _projection_bound(
            projection,
            packet["plan_id"],
            assignment_id,
        )
        or expected_target is None
        or not isinstance(target, dict)
        or target != expected_target
        or packet["target_assignment_id"] != target.get("assignment_id")
        or packet["target_execution_unit_id"]
        != target.get("execution_unit_id")
        or packet["target_model_route_id"] != target.get("model_route_id")
    ):
        issues.append(
            _issue(
                "VERIFICATION_TARGET_MISMATCH",
                "target_assignment_id",
                "VerificationVerdict must bind the projected mutation-owner target.",
            )
        )
    verdict = packet["verdict"]
    cause = packet["failure_cause"]
    categories = packet["failure_categories"]
    if verdict not in _VERIFICATION_VERDICTS:
        issues.append(
            _issue(
                "VERIFICATION_VERDICT_INVALID",
                "verdict",
                "Verification verdict must be passed, failed, or inconclusive.",
            )
        )
    if cause not in _VERIFICATION_FAILURE_CAUSES:
        issues.append(
            _issue(
                "VERIFICATION_FAILURE_CAUSE_INVALID",
                "failure_cause",
                "Verification failure cause is outside the closed taxonomy.",
            )
        )
    if (
        not isinstance(categories, list)
        or len(categories) > 8
        or len(categories) != len(set(categories))
        or any(
            category not in _VERIFICATION_FAILURE_CATEGORIES
            for category in categories
        )
    ):
        issues.append(
            _issue(
                "VERIFICATION_FAILURE_CATEGORY_INVALID",
                "failure_categories",
                "Verification failure categories are invalid or duplicated.",
            )
        )
    if verdict == "passed" and (cause != "none" or categories):
        issues.append(
            _issue(
                "VERIFICATION_PASS_CAUSE_CONFLICT",
                "failure_cause",
                "A passed verdict must use failure_cause=none and no categories.",
            )
        )
    if verdict == "failed" and (
        cause in {"none", "unknown"} or not categories
    ):
        issues.append(
            _issue(
                "VERIFICATION_FAILURE_ATTRIBUTION_REQUIRED",
                "failure_cause",
                "A failed verdict needs a bounded non-unknown cause and category.",
            )
        )
    if verdict == "inconclusive" and cause not in {
        "specification",
        "environment",
        "tooling",
        "unknown",
    }:
        issues.append(
            _issue(
                "VERIFICATION_INCONCLUSIVE_CAUSE_INVALID",
                "failure_cause",
                "Inconclusive verification requires a non-target uncertainty cause.",
            )
        )
    refs = _evidence(
        packet["evidence_refs"],
        "evidence_refs",
        issues,
        projection=projection,
        allow_empty=False,
    )
    if not refs:
        issues.append(
            _issue(
                "VERIFICATION_EVIDENCE_REQUIRED",
                "evidence_refs",
                "VerificationVerdict requires bounded projected evidence.",
            )
        )
    if not _line(packet["summary"], 500):
        issues.append(
            _issue(
                "PACKET_TEXT_INVALID",
                "summary",
                "Verification summary must be one bounded line.",
            )
        )
    if packet["writes_performed"] is not False:
        issues.append(
            _issue(
                "VERIFICATION_WRITE_FORBIDDEN",
                "writes_performed",
                "The verifier is read-only.",
            )
        )
    design_context = (
        projected.get("design_assurance_context")
        if isinstance(projected, dict)
        else None
    )
    design_required = (
        isinstance(design_context, dict)
        and design_context.get("role") == "verification"
    )
    design_verification = packet.get("design_verification")
    if design_required and design_verification is None:
        issues.append(
            _issue(
                "DESIGN_VERIFICATION_REQUIRED",
                "design_verification",
                "An assured Product Design verifier must report every rendered scenario.",
            )
        )
    elif design_verification is not None and not design_required:
        issues.append(
            _issue(
                "DESIGN_VERIFICATION_UNEXPECTED",
                "design_verification",
                "Rendered design verification is allowed only for an assured Product Design projection.",
            )
        )
    elif design_required:
        if repo_path is None:
            issues.append(
                _issue(
                    "DESIGN_VERIFICATION_REPO_REQUIRED",
                    "design_verification",
                    "Rendered Product Design verification requires repository-bound validation.",
                )
            )
        else:
            issues.extend(
                validate_design_verification(
                    design_verification,
                    decision_packet=design_context["decision_packet"],
                    implementation_result=design_context[
                        "implementation_result"
                    ],
                    repo_path=repo_path,
                    overall_verdict=verdict,
                )
            )
        required_design_ref = (
            f"design-decision:{design_context['decision_packet']['packet_id']}"
        )
        render_refs = {
            (
                "design-render:"
                f"{item['scenario_id']}:{item['sha256']}"
            )
            for item in design_context[
                "implementation_result"
            ].get("rendered_artifacts", [])
            if isinstance(item, dict)
            and isinstance(item.get("scenario_id"), str)
            and isinstance(item.get("sha256"), str)
        }
        if required_design_ref not in refs or not (set(refs) & render_refs):
            issues.append(
                _issue(
                    "DESIGN_VERIFICATION_EVIDENCE_REQUIRED",
                    "evidence_refs",
                    "Design verification must cite the decision Packet and at least one unchanged rendered artifact.",
                )
            )
    result = _validation(packet, issues)
    if result["status"] == "PASS":
        assessment = {
            "schema_version": "maestro_verification_assessment_v1",
            "assessment_id": "",
            "packet_digest": result["packet_digest"],
            "verifier_assignment_id": assignment_id,
            "target_assignment_id": packet["target_assignment_id"],
            "target_execution_unit_id": packet[
                "target_execution_unit_id"
            ],
            "target_model_route_id": packet["target_model_route_id"],
            "verdict": verdict,
            "failure_cause": cause,
            "failure_categories": list(categories),
            "evidence_refs": list(packet["evidence_refs"]),
        }
        assessment["assessment_id"] = sha256_text(
            canonical_json(
                {
                    **assessment,
                    "assessment_id": "",
                }
            )
        )
        result["verification_assessment"] = assessment
    return result


def validate_assignment_packet(
    packet: Any,
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any] | None = None,
    *,
    repo_path: str | Path | None = None,
    research_bundle: dict[str, Any] | None = None,
    require_expertise_dispositions: bool = False,
) -> dict[str, Any]:
    route_plan, _, execution_issues = _execution_context(
        plan,
        repo_path=repo_path,
        research_bundle=research_bundle,
    )
    if execution_issues:
        return _validation(packet, execution_issues)
    plan = route_plan
    version = packet.get("schema_version") if isinstance(packet, dict) else None
    if version == FINDING_PACKET_VERSION:
        result = validate_finding_packet(
            packet,
            plan,
            assignment_id,
            projection,
            repo_path=repo_path,
        )
    elif version == TERMINAL_PACKET_VERSION:
        result = validate_terminal_packet(
            packet,
            plan,
            assignment_id,
            projection,
            repo_path=repo_path,
        )
    elif version == VERIFICATION_VERDICT_VERSION:
        result = validate_verification_verdict(
            packet,
            plan,
            assignment_id,
            projection,
            repo_path=repo_path,
        )
    else:
        result = _validation(
            packet,
            [
                _issue(
                    "PACKET_VERSION_UNSUPPORTED",
                    "schema_version",
                    (
                        "Supported versions are FindingPacket v2, terminal "
                        "Packet v1, and VerificationVerdict v1."
                    ),
                )
            ],
        )
    expertise_issues = _expertise_disposition_issues(
        (
            packet.get("expertise_dispositions")
            if isinstance(packet, dict)
            else None
        ),
        projection=projection,
        required=require_expertise_dispositions,
        completed=(
            version == TERMINAL_PACKET_VERSION
            and isinstance(packet, dict)
            and packet.get("status") == "completed"
            and _assignments(plan).get(
                assignment_id,
                {},
            ).get("mutation_owner")
            is True
        ),
    )
    research_issues = _projection_research_issues(
        plan,
        projection,
        research_bundle,
        repo_path=repo_path,
    )
    if not expertise_issues and not research_issues:
        return result
    return _validation(
        packet,
        [
            *result["issues"],
            *expertise_issues,
            *research_issues,
        ],
    )


def project_assignment_input(
    repo_path: str | Path,
    plan: dict[str, Any],
    assignment_id: str,
    baseline: dict[str, Any],
    *,
    document_paths: Iterable[str] = (),
    dependency_packets: Iterable[dict[str, Any]] = (),
    dependency_projections: Iterable[dict[str, Any]] = (),
    research_bundle: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
    coverage_admission: dict[str, Any] | None = None,
    coverage_projection: dict[str, Any] | None = None,
    expertise_work_plan: dict[str, Any] | None = None,
    expertise_closure: dict[str, Any] | None = None,
    design_decision_packet: dict[str, Any] | None = None,
    expertise_research_bundles: Any = None,
) -> dict[str, Any]:
    """Project the explicit allowlist for one Host-executed Assignment."""

    repo = ensure_repo(repo_path)
    route_plan, execution_authorization, execution_issues = (
        _execution_context(
            plan,
            repo_path=repo,
            research_bundle=research_bundle,
        )
    )
    if execution_issues:
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "FAIL",
            "execution_status": "INVALID",
            "issues": sorted(
                execution_issues,
                key=lambda item: (
                    item["code"],
                    item["path"],
                    item["message"],
                ),
            ),
            "input": None,
            "writes_performed": False,
        }
    plan = route_plan
    try:
        route_validation = validate_route_v2(
            plan,
            repo_path=repo,
            research_bundle=research_bundle,
        )
    except (MaestroError, OSError, TypeError, ValueError):
        route_validation = None
    if (
        isinstance(route_validation, dict)
        and route_validation.get("status") == "PASS"
        and route_validation.get("execution_status") != "READY"
    ):
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "BLOCKED",
            "execution_status": "RESEARCH_REQUIRED",
            "issues": [
                _issue(
                    "PROJECTION_RESEARCH_REQUIRED",
                    "plan.expertise.research_requirement",
                    "Complete and bind the required research before projecting an executable Assignment.",
                )
            ],
            "input": None,
            "writes_performed": False,
        }
    issues = _plan_issues(
        plan,
        repo,
        research_bundle=research_bundle,
    )
    plan_value = plan if isinstance(plan, dict) else {}
    assignment = _assignments(plan).get(assignment_id)
    if assignment is None:
        issues.append(
            _issue(
                "PROJECTION_ASSIGNMENT_UNKNOWN",
                "assignment_id",
                f"Unknown Assignment: {assignment_id}.",
            )
        )
    projected_coverage, coverage_issues = _coverage_context(
        plan_value,
        goal=(
            plan_value.get("goal", "")
            if isinstance(plan_value, dict)
            else ""
        ),
        repo=repo,
        coverage=coverage,
        coverage_admission=coverage_admission,
        coverage_projection=coverage_projection,
        expertise_work_plan=expertise_work_plan,
        expertise_closure=expertise_closure,
        research_bundle=research_bundle,
        expertise_research_bundles=expertise_research_bundles,
        require_ready=(
            assignment is not None
            and assignment.get("mutation_owner") is True
        ),
    )
    issues.extend(coverage_issues)
    baseline_result = validate_engineering_baseline(
        baseline,
        repo_path=repo,
        plan=plan,
    )
    issues.extend(baseline_result["issues"])
    research_context, research_issues = _research_context(
        plan_value,
        research_bundle,
        repo,
    )
    issues.extend(research_issues)
    design_active = product_design_assurance_active(plan_value)
    design_context: dict[str, Any] | None = None
    design_decision_pending = False
    if assignment is not None and design_active:
        if assignment.get("mutation_owner") is True:
            if design_decision_packet is None:
                design_decision_pending = True
            else:
                design_validation = validate_design_decision_packet(
                    design_decision_packet,
                    plan_value,
                    repo_path=repo,
                    research_bundle=research_bundle,
                )
                issues.extend(design_validation["issues"])
                if design_validation["status"] == "PASS":
                    design_context = {
                        "role": "implementation",
                        "requirement": copy.deepcopy(
                            plan_value["design_assurance"]
                        ),
                        "decision_packet": copy.deepcopy(
                            design_decision_packet
                        ),
                    }
        elif assignment.get("output_packet") == "FindingPacket":
            if design_decision_packet is not None:
                issues.append(
                    _issue(
                        "PROJECTION_DESIGN_DECISION_UNEXPECTED",
                        "design_decision_packet",
                        "Review assignments receive the assurance requirement, not a mutation decision sidecar.",
                    )
                )
            design_context = {
                "role": "analysis",
                "requirement": copy.deepcopy(
                    plan_value["design_assurance"]
                ),
            }
        elif design_decision_packet is not None:
            issues.append(
                _issue(
                    "PROJECTION_DESIGN_DECISION_UNEXPECTED",
                    "design_decision_packet",
                    "Only the assured mutation owner accepts a direct design decision Packet.",
                )
            )
    elif design_decision_packet is not None:
        issues.append(
            _issue(
                "PROJECTION_DESIGN_DECISION_UNEXPECTED",
                "design_decision_packet",
                "A design decision Packet requires an explicitly classified Product Design route.",
            )
        )

    surface_artifacts = (
        baseline.get("surface_map", {}).get("artifacts", [])
        if isinstance(baseline, dict)
        and isinstance(baseline.get("surface_map"), dict)
        else []
    )
    target_paths = list(
        dict.fromkeys(
            item["path"]
            for item in surface_artifacts
            if isinstance(item, dict)
            and isinstance(item.get("path"), str)
        )
    )
    convention_selection: dict[str, Any] | None = None
    selected_document_paths: list[str] = []
    document_selection_blocked = False
    if assignment is not None and isinstance(plan_value.get("goal"), str):
        convention_selection, selected_document_paths = (
            _project_document_selection(
                repo,
                plan_value,
                assignment,
                target_paths,
                decision_authorized=execution_authorization is not None,
            )
        )
        if (
            assignment["mutation_owner"]
            and convention_selection["evidence_status"] != "sufficient"
        ):
            document_selection_blocked = True

    documents: list[dict[str, str]] = []
    seen_document_paths: set[str] = set()
    all_document_paths = [
        *selected_document_paths,
        *list(document_paths),
    ]
    for index, relative_path in enumerate(all_document_paths):
        if len(documents) >= 8:
            issues.append(
                _issue(
                    "PROJECTION_DOCUMENT_LIMIT",
                    "document_paths",
                    "At most 8 document references are allowed.",
                )
            )
            break
        if relative_path in seen_document_paths:
            continue
        if not _relative_path(relative_path):
            issues.append(
                _issue(
                    "PROJECTION_DOCUMENT_INVALID",
                    f"document_paths[{index}]",
                    "Document path must be unique and repository-relative.",
                )
            )
            continue
        target = _regular_file(repo, relative_path)
        digest = file_sha256(target) if target is not None else None
        if digest is None:
            issues.append(
                _issue(
                    "PROJECTION_DOCUMENT_MISSING",
                    f"document_paths[{index}]",
                    "Document must be a regular non-symlink file.",
                )
            )
            continue
        seen_document_paths.add(relative_path)
        documents.append(
            {
                "ref_id": f"doc-{sha256_text(relative_path)[:12]}",
                "path": relative_path,
                "sha256": digest,
            }
        )

    baseline_artifact_refs = [
        {
            "artifact_id": artifact.get("artifact_id"),
            "path": artifact.get("path"),
            "sha256": (
                file_sha256(target)
                if (
                    artifact.get("state") == "existing"
                    and isinstance(artifact.get("path"), str)
                    and (target := _regular_file(repo, artifact["path"]))
                    is not None
                )
                else None
            ),
        }
        for artifact in (
            baseline.get("surface_map", {}).get("artifacts", [])
            if isinstance(baseline, dict)
            and isinstance(baseline.get("surface_map"), dict)
            else []
        )
        if isinstance(artifact, dict)
    ]
    dependency_projection_by_id: dict[str, dict[str, Any]] = {}
    for index, projection in enumerate(dependency_projections):
        projected_value = _projection_value(projection)
        projected_assignment_id = (
            projected_value.get("assignment_id")
            if isinstance(projected_value, dict)
            else None
        )
        if (
            not isinstance(projected_assignment_id, str)
            or projected_assignment_id in dependency_projection_by_id
            or not _projection_bound(
                projection,
                plan_value.get("plan_id"),
                projected_assignment_id,
            )
        ):
            issues.append(
                _issue(
                    "PROJECTION_DEPENDENCY_PROJECTION_INVALID",
                    f"dependency_projections[{index}]",
                    "Each dependency needs one unique, intact source projection bound to this plan.",
                )
            )
            continue
        dependency_projection_by_id[projected_assignment_id] = copy.deepcopy(
            projection
        )

    dependency_by_id: dict[str, dict[str, Any]] = {}
    for index, packet in enumerate(dependency_packets):
        packet_assignment_id = (
            packet.get("assignment_id") if isinstance(packet, dict) else None
        )
        if (
            not isinstance(packet_assignment_id, str)
            or packet_assignment_id in dependency_by_id
        ):
            issues.append(
                _issue(
                    "PROJECTION_DEPENDENCY_DUPLICATE",
                    f"dependency_packets[{index}]",
                    "Dependency Packet needs one unique Assignment ID.",
                )
            )
            continue
        dependency_projection = dependency_projection_by_id.get(
            packet_assignment_id
        )
        if dependency_projection is None:
            issues.append(
                _issue(
                    "PROJECTION_DEPENDENCY_PROJECTION_REQUIRED",
                    f"dependency_packets[{index}]",
                    "Provide the exact source projection used to validate this dependency Packet.",
                )
            )
            continue
        validation = validate_assignment_packet(
            packet,
            plan,
            packet_assignment_id,
            dependency_projection,
            repo_path=repo,
            research_bundle=research_bundle,
        )
        if validation["status"] != "PASS":
            issues.append(
                _issue(
                    "PROJECTION_DEPENDENCY_INVALID",
                    f"dependency_packets[{index}]",
                    validation["issues"][0]["message"],
                )
            )
            continue
        dependency_by_id[packet_assignment_id] = copy.deepcopy(packet)

    expected_dependencies = (
        set(assignment["depends_on"]) if assignment is not None else set()
    )
    if set(dependency_projection_by_id) != expected_dependencies:
        issues.append(
            _issue(
                "PROJECTION_DEPENDENCY_PROJECTION_SET_INVALID",
                "dependency_projections",
                "Provide exactly one intact source projection for every direct dependency.",
            )
        )
    if set(dependency_by_id) != expected_dependencies:
        issues.append(
            _issue(
                "PROJECTION_DEPENDENCY_SET_INVALID",
                "dependency_packets",
                "Provide exactly one valid Packet for every direct dependency.",
            )
        )
    if (
        assignment is not None
        and design_active
        and assignment.get("output_packet") == "VerificationVerdict"
    ):
        mutation_owner_id = plan_value.get(
            "mutation_owner_assignment_id"
        )
        source_projection = dependency_projection_by_id.get(
            mutation_owner_id
        )
        source_input = _projection_value(source_projection)
        source_context = (
            source_input.get("design_assurance_context")
            if isinstance(source_input, dict)
            else None
        )
        source_packet = dependency_by_id.get(mutation_owner_id)
        implementation_result = (
            source_packet.get("design_assurance_result")
            if isinstance(source_packet, dict)
            else None
        )
        if (
            not isinstance(source_context, dict)
            or source_context.get("role") != "implementation"
            or source_context.get("requirement")
            != plan_value.get("design_assurance")
            or not isinstance(
                source_context.get("decision_packet"),
                dict,
            )
            or not isinstance(implementation_result, dict)
        ):
            issues.append(
                _issue(
                    "PROJECTION_DESIGN_DEPENDENCY_INVALID",
                    "dependency_packets",
                    "Design verification requires the exact assured writer projection and implementation result.",
                )
            )
        else:
            design_context = {
                "role": "verification",
                "requirement": copy.deepcopy(
                    plan_value["design_assurance"]
                ),
                "decision_packet": copy.deepcopy(
                    source_context["decision_packet"]
                ),
                "implementation_result": copy.deepcopy(
                    implementation_result
                ),
            }

    gap_ids = (
        [
            item["check_id"]
            for item in baseline.get("checks", [])
            if isinstance(item, dict)
            and isinstance(item.get("check_id"), str)
            and item.get("status") == "gap"
        ]
        if isinstance(baseline, dict)
        else []
    )
    if issues:
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "FAIL",
            "execution_status": "INVALID",
            "issues": sorted(
                issues,
                key=lambda item: (item["code"], item["path"], item["message"]),
            ),
            "input": None,
            "writes_performed": False,
        }
    if (
        assignment["mutation_owner"]
        and design_decision_pending
    ):
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "BLOCKED",
            "execution_status": "DESIGN_DECISION_REQUIRED",
            "issues": [
                _issue(
                    "PROJECTION_DESIGN_DECISION_REQUIRED",
                    "design_decision_packet",
                    "Build and validate the complete Product Design decision Packet before opening repository mutation.",
                )
            ],
            "input": None,
            "writes_performed": False,
        }
    if assignment["mutation_owner"] and gap_ids:
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "BLOCKED",
            "execution_status": "GAPS_PRESENT",
            "issues": [
                _issue(
                    "PROJECTION_COVERAGE_GAP",
                    "engineering_baseline",
                    f"Mutation is blocked by baseline gaps: {', '.join(gap_ids)}.",
                )
            ],
            "input": None,
            "writes_performed": False,
        }
    if assignment["mutation_owner"] and document_selection_blocked:
        return {
            "schema_version": "maestro_assignment_projection_result_v1",
            "status": "BLOCKED",
            "execution_status": "DOCUMENT_EVIDENCE_INSUFFICIENT",
            "issues": [
                _issue(
                    "PROJECTION_DOCUMENT_SELECTION_INSUFFICIENT",
                    "convention_selection.evidence_status",
                    "Mutation requires a sufficient maestro docs selection; narrow the task or target paths and resolve its missing evidence.",
                )
            ],
            "input": None,
            "writes_performed": False,
        }

    lens_ids = set(assignment["lens_ids"])
    lens_cards = [
        copy.deepcopy(item)
        for item in plan.get("lens_cards", [])
        if item.get("lens_id") in lens_ids
    ]
    artifacts: list[dict[str, Any]] = []
    for artifact in baseline["surface_map"]["artifacts"]:
        target = (
            _regular_file(repo, artifact["path"])
            if artifact["state"] == "existing"
            else None
        )
        artifacts.append(
            {
                "artifact_id": artifact["artifact_id"],
                "path": artifact["path"],
                "state": artifact["state"],
                "sha256": file_sha256(target) if target is not None else None,
            }
        )
    executors = {
        item["executor_id"]: item for item in load_registry()["executors"]
    }
    context = executors[assignment["executor_id"]]["context_policy"]
    assignment_guide_ids = copy.deepcopy(
        assignment.get("decision_guide_ids", [])
    )
    expertise = plan.get("expertise")
    expertise_load_packs: list[dict[str, Any]] = []
    if isinstance(expertise, dict) and assignment_guide_ids:
        selected_guides = set(assignment_guide_ids)
        for pack in expertise.get("pack_cards", []):
            guides = [
                {
                    "guide_id": guide["guide_id"],
                    "skill_id": guide["skill_id"],
                    "resource_path": guide["resource_path"],
                    "skill_definition_digest": guide[
                        "skill_definition_digest"
                    ],
                }
                for guide in pack.get("guides", [])
                if guide.get("guide_id") in selected_guides
            ]
            if guides:
                expertise_load_packs.append(
                    {
                        "expertise_pack_id": pack["expertise_pack_id"],
                        "skill_id": pack["skill_id"],
                        "skill_path": pack["skill_path"],
                        "definition_digest": pack["definition_digest"],
                        "skill_definition_digest": pack[
                            "skill_definition_digest"
                        ],
                        "guides": guides,
                    }
                )
    if assignment["mutation_owner"]:
        expertise_application_mode = "authorized-executor-may-apply"
    elif expertise_load_packs:
        expertise_application_mode = "advisory-only"
    else:
        expertise_application_mode = "not-applicable"

    verification_target = None
    if assignment.get("output_packet") == "VerificationVerdict":
        verification_target = _expected_verification_target(
            plan,
            assignment_id,
        )
        if verification_target is None:
            raise MaestroError(
                "ASSIGNMENT_VERIFICATION_TARGET_INVALID",
                "The mutation owner must be a typed ancestor of the verifier.",
            )

    projected = {
        "schema_version": ASSIGNMENT_INPUT_VERSION,
        "projection_digest": "",
        "plan_id": plan["plan_id"],
        "assignment_id": assignment_id,
        "goal_digest": sha256_text(plan["goal"]),
        "task_contract": copy.deepcopy(plan["task_contract"]),
        "execution_authorization": execution_authorization,
        "coverage_context": projected_coverage,
        "assignment_contract": {
            field: copy.deepcopy(assignment[field])
            for field in sorted(_ASSIGNMENT_FIELDS)
        },
        "verification_target": verification_target,
        "surface_map": copy.deepcopy(baseline["surface_map"]),
        "engineering_baseline": copy.deepcopy(baseline["checks"]),
        "selected_lens_cards": lens_cards,
        "decision_guide_ids": assignment_guide_ids,
        "expertise_load": {
            "application_mode": expertise_application_mode,
            "packs": expertise_load_packs,
            "host_attestation": {
                "status": "unavailable",
                "loaded_skill_digests": [],
                "loaded_guide_refs": [],
            },
        },
        "convention_selection": convention_selection,
        "research_context": research_context,
        "document_refs": documents,
        "artifact_refs": artifacts,
        "dependency_packets": [
            {
                "ref_id": f"dependency-{dependency_id}",
                "assignment_id": dependency_id,
                "projection_digest": _projection_value(
                    dependency_projection_by_id[dependency_id]
                )["projection_digest"],
                "packet": dependency_by_id[dependency_id],
            }
            for dependency_id in assignment["depends_on"]
        ],
        "context_policy": {
            "requests": {
                "fresh_context": (
                    context["fresh_context_supported"] and assignment["read_only"]
                ),
                "read_only": assignment["read_only"],
                "packet_only": context["return_packet_only"],
                "hide_other_lens_conclusions": context[
                    "hide_other_lens_conclusions"
                ],
            },
            "host_attestation": {
                "fresh_context": "unavailable",
                "read_only": "unavailable",
                "packet_only": "unavailable",
            },
            "forbidden": list(_FORBIDDEN_CONTEXT),
        },
    }
    if design_context is not None:
        projected["design_assurance_context"] = design_context
    payload = copy.deepcopy(projected)
    payload.pop("projection_digest")
    projected["projection_digest"] = sha256_text(canonical_json(payload))
    return {
        "schema_version": "maestro_assignment_projection_result_v1",
        "status": "PASS",
        "execution_status": (
            "GAPS_PRESENT" if gap_ids else "READY"
        ),
        "issues": [],
        "input": projected,
        "writes_performed": False,
    }
