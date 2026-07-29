from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import MaestroError
from .util import read_json, safe_target

DECISION_MAP_VERSION = "maestro_expertise_decision_map_v1"
DECISION_MAP_PATH = "evidence/decision-map.json"
MAX_DECISION_AREAS = 64
MATERIALITY_LEVELS = {"blocking", "important", "supporting"}
EVIDENCE_TYPES = {
    "project-fact",
    "external-current",
    "external-stable",
    "owner-preference",
    "runtime-verification",
}
DISPOSITION_KINDS = {
    "proposed-guide",
    "existing-guide",
    "checker",
    "convention",
    "out-of-scope-explicit",
}
_LOCAL_EVIDENCE_PREFIXES = (
    "project:",
    "owner:",
    "verification:",
    "research-bundle:",
)


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "path": path,
        "message": message,
    }


def _nonempty_unique_strings(
    value: Any,
    *,
    maximum: int | None = None,
) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and (maximum is None or len(value) <= maximum)
        and len(value) == len(set(value))
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _evidence_ref_resolves(
    value: str,
    *,
    source_ids: set[str],
    resolved_research_bundle_refs: set[str] | None = None,
) -> bool:
    if value.startswith("research-bundle:"):
        return (
            True
            if resolved_research_bundle_refs is None
            else value in resolved_research_bundle_refs
        )
    return value in source_ids or value.startswith(
        tuple(
            prefix
            for prefix in _LOCAL_EVIDENCE_PREFIXES
            if prefix != "research-bundle:"
        )
    )


def validate_candidate_decision_map(
    candidate_root: Path,
    candidate: dict[str, Any],
    *,
    proposed_guide_ids: set[str],
    source_ids: set[str],
    resolved_research_bundle_refs: set[str] | None = None,
) -> list[dict[str, str]]:
    """Validate v2 coverage discovery independently from Pack publication."""

    if candidate.get("schema_version") == "maestro_expertise_candidate_v1":
        return []
    coverage = candidate.get("coverage")
    if (
        not isinstance(coverage, dict)
        or set(coverage)
        != {
            "decision_map_path",
            "discovery_complete",
            "allocation_complete",
        }
        or coverage.get("decision_map_path") != DECISION_MAP_PATH
        or coverage.get("discovery_complete") is not True
        or coverage.get("allocation_complete") is not True
    ):
        return [
            _issue(
                "EXPERTISE_DECISION_MAP_CONTRACT_INVALID",
                "candidate.json.coverage",
                (
                    "Candidate v2 must bind a complete discovery and allocation "
                    f"map at {DECISION_MAP_PATH}."
                ),
            )
        ]

    try:
        target = safe_target(candidate_root, DECISION_MAP_PATH)
        if target.is_symlink() or not target.is_file():
            raise MaestroError(
                "EXPERTISE_DECISION_MAP_MISSING",
                "The candidate Decision Map is missing or unsafe.",
            )
        decision_map = read_json(target)
    except MaestroError as exc:
        return [_issue(exc.code, DECISION_MAP_PATH, exc.message)]

    areas = decision_map.get("decision_areas")
    if (
        set(decision_map)
        != {"schema_version", "candidate_id", "decision_areas"}
        or decision_map.get("schema_version") != DECISION_MAP_VERSION
        or decision_map.get("candidate_id") != candidate.get("candidate_id")
        or not isinstance(areas, list)
        or not 1 <= len(areas) <= MAX_DECISION_AREAS
    ):
        return [
            _issue(
                "EXPERTISE_DECISION_MAP_INVALID",
                DECISION_MAP_PATH,
                (
                    "Decision Map must bind this candidate and contain one to "
                    f"{MAX_DECISION_AREAS} explicitly allocated areas."
                ),
            )
        ]

    issues: list[dict[str, str]] = []
    area_ids: set[str] = set()
    allocated_guides: set[str] = set()
    for index, area in enumerate(areas):
        path = f"{DECISION_MAP_PATH}.decision_areas[{index}]"
        if not isinstance(area, dict) or set(area) != {
            "area_id",
            "decision",
            "failure_if_omitted",
            "materiality",
            "evidence_types",
            "evidence_refs",
            "disposition",
        }:
            issues.append(
                _issue(
                    "EXPERTISE_DECISION_AREA_INVALID",
                    path,
                    "Decision area fields are incomplete or unknown.",
                )
            )
            continue
        area_id = area.get("area_id")
        disposition = area.get("disposition")
        if (
            not isinstance(area_id, str)
            or not area_id
            or area_id in area_ids
            or not isinstance(area.get("decision"), str)
            or not area["decision"].strip()
            or not isinstance(area.get("failure_if_omitted"), str)
            or not area["failure_if_omitted"].strip()
            or area.get("materiality") not in MATERIALITY_LEVELS
            or not _nonempty_unique_strings(
                area.get("evidence_types"),
                maximum=len(EVIDENCE_TYPES),
            )
            or not set(area["evidence_types"]).issubset(EVIDENCE_TYPES)
            or not _nonempty_unique_strings(
                area.get("evidence_refs"),
                maximum=16,
            )
            or any(
                not _evidence_ref_resolves(
                    ref,
                    source_ids=source_ids,
                    resolved_research_bundle_refs=resolved_research_bundle_refs,
                )
                for ref in area["evidence_refs"]
            )
            or not isinstance(disposition, dict)
            or set(disposition) != {"kind", "target_id", "rationale"}
            or disposition.get("kind") not in DISPOSITION_KINDS
            or not isinstance(disposition.get("target_id"), str)
            or not disposition["target_id"].strip()
            or not isinstance(disposition.get("rationale"), str)
            or not disposition["rationale"].strip()
        ):
            issues.append(
                _issue(
                    "EXPERTISE_DECISION_AREA_INVALID",
                    path,
                    (
                        "Each area needs unique identity, materiality, typed "
                        "evidence, and one explicit allocation."
                    ),
                )
            )
            continue
        area_ids.add(area_id)
        if disposition["kind"] == "proposed-guide":
            target_id = disposition["target_id"]
            if target_id not in proposed_guide_ids:
                issues.append(
                    _issue(
                        "EXPERTISE_DECISION_AREA_GUIDE_MISSING",
                        f"{path}.disposition.target_id",
                        (
                            "A proposed-guide allocation must name one Guide "
                            "in candidate.json."
                        ),
                    )
                )
            else:
                allocated_guides.add(target_id)

    missing_guides = sorted(proposed_guide_ids - allocated_guides)
    if missing_guides:
        issues.append(
            _issue(
                "EXPERTISE_DECISION_MAP_GUIDE_UNALLOCATED",
                DECISION_MAP_PATH,
                (
                    "Every proposed Guide must own at least one discovered "
                    f"decision area: {', '.join(missing_guides)}."
                ),
            )
        )
    return issues
