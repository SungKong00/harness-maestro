from __future__ import annotations

import re
from typing import Any

from .errors import MaestroError
from .matching import searchable_terms, term_matches
from .registry import load_registry, validate_registry


DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MAX_SELECTED_PACKS = 1
MAX_SELECTED_GUIDES = 4
DISCOVERY_TRIGGERS = (
    "expert criteria",
    "best practice",
    "technology stack",
    "architecture choice",
    "전문가 기준",
    "모범 사례",
    "기술 스택",
    "아키텍처 선택",
    "큰 방향",
)


def _matches(goal_terms: frozenset[str], trigger: str) -> bool:
    return term_matches(goal_terms, trigger)


def _minimal_pack_card(
    pack: dict[str, Any],
    selected_guides: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "expertise_pack_id": pack["expertise_pack_id"],
        "summary": pack["summary"],
        "status": pack["status"],
        "portability": pack["portability"],
        "version": pack["version"],
        "skill_id": pack["skill_id"],
        "guides": [
            {
                "guide_id": guide["guide_id"],
                "summary": guide["summary"],
                "freshness": guide["freshness"],
            }
            for guide in selected_guides
        ],
        "source_manifest": pack["source_manifest"],
        "evaluation_suite": pack["evaluation_suite"],
    }


def select_expertise(
    goal: str,
    *,
    intent: str,
    research_evidence_digest: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select one compact reusable expertise pack and an explicit research gate."""

    if research_evidence_digest is not None and (
        not isinstance(research_evidence_digest, str)
        or DIGEST_PATTERN.fullmatch(research_evidence_digest) is None
    ):
        raise MaestroError(
            "RESEARCH_EVIDENCE_DIGEST_INVALID",
            "Research evidence digest must be a canonical SHA-256 digest.",
        )

    registry = load_registry()
    errors = validate_registry(registry)
    if errors:
        raise MaestroError("REGISTRY_INVALID", "; ".join(errors))

    goal_terms = searchable_terms(goal)
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    eligible_packs = [
        pack
        for pack in registry["expertise_packs"]
        if pack["status"] in {"pilot", "active"}
    ]
    for pack in eligible_packs:
        score = sum(
            1 for trigger in pack["triggers"] if _matches(goal_terms, trigger)
        )
        if score:
            ranked.append((score, pack["expertise_pack_id"], pack))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected_packs = [item[2] for item in ranked[:MAX_SELECTED_PACKS]]

    selected_guide_ids: list[str] = []
    pack_cards: list[dict[str, Any]] = []
    research_mode = "reuse"
    research_reasons: list[str] = []
    warnings: list[dict[str, Any]] = []

    for pack in selected_packs:
        guide_by_id = {guide["guide_id"]: guide for guide in pack["guides"]}
        matched_guides = [
            guide
            for guide in pack["guides"]
            if any(_matches(goal_terms, trigger) for trigger in guide["triggers"])
        ]
        matched_guides.sort(
            key=lambda guide: (
                guide["freshness"] != "volatile",
                guide["guide_id"] == "design-brief",
                guide["guide_id"],
            )
        )
        ordered_ids = list(
            dict.fromkeys(
                [
                    *(guide["guide_id"] for guide in matched_guides),
                    *pack["default_guides"],
                ]
            )
        )[:MAX_SELECTED_GUIDES]
        selected_guides = [guide_by_id[guide_id] for guide_id in ordered_ids]
        selected_guide_ids.extend(ordered_ids)
        pack_cards.append(_minimal_pack_card(pack, selected_guides))

        policy = pack["research_policy"]
        refresh_matches = [
            trigger
            for trigger in policy["refresh_triggers"]
            if _matches(goal_terms, trigger)
        ]
        contextual_matches = [
            trigger
            for trigger in policy["contextualize_triggers"]
            if _matches(goal_terms, trigger)
        ]
        if refresh_matches:
            research_mode = "refresh"
            research_reasons.extend(refresh_matches)
        elif contextual_matches and research_mode == "reuse":
            research_mode = "contextualize"
            research_reasons.extend(contextual_matches)

        if pack["status"] == "pilot":
            warnings.append(
                {
                    "code": "EXPERTISE_PACK_PILOT",
                    "expertise_pack_id": pack["expertise_pack_id"],
                    "message": (
                        "The selected Expertise Pack is in pilot status; "
                        "verify its rubric against the task result."
                    ),
                }
            )

    if not selected_packs:
        discovery_matches = [
            trigger
            for trigger in DISCOVERY_TRIGGERS
            if _matches(goal_terms, trigger)
        ]
        if discovery_matches:
            research_mode = "discover"
            research_reasons = discovery_matches

    if research_evidence_digest is not None and (
        research_mode == "reuse" or intent == "research"
    ):
        raise MaestroError(
            "RESEARCH_EVIDENCE_NOT_APPLICABLE",
            "The routed task has no external research gate to satisfy.",
        )

    if research_mode == "reuse":
        gate = "not-required"
        evidence_digest = None
    elif intent == "research":
        gate = "in-plan"
        evidence_digest = None
    elif research_evidence_digest is not None:
        gate = "satisfied"
        evidence_digest = research_evidence_digest
    else:
        gate = "open"
        evidence_digest = None
        warnings.append(
            {
                "code": "EXPERTISE_RESEARCH_REQUIRED",
                "mode": research_mode,
                "message": (
                    "Run bounded reference research and re-route with its "
                    "artifact digest before executing assignments."
                ),
            }
        )

    selection = {
        "schema_version": "maestro_expertise_selection_v1",
        "selected_pack_ids": [
            pack["expertise_pack_id"] for pack in selected_packs
        ],
        "selected_guide_ids": selected_guide_ids,
        "pack_cards": pack_cards,
        "research_requirement": {
            "mode": research_mode,
            "gate": gate,
            "reasons": list(dict.fromkeys(research_reasons)),
            "evidence_digest": evidence_digest,
        },
        "warnings": warnings,
        "selection_trace": {
            "catalog_packs": len(registry["expertise_packs"]),
            "eligible_packs": len(eligible_packs),
            "returned_pack_bodies": len(pack_cards),
            "returned_guide_bodies": len(selected_guide_ids),
            "max_selected_packs": MAX_SELECTED_PACKS,
            "max_selected_guides": MAX_SELECTED_GUIDES,
        },
    }
    return selection, warnings
