from __future__ import annotations

from datetime import date
from typing import Any

from .util import canonical_json, sha256_text


PACKET_VERSION = "maestro_research_packet_v1"
BUNDLE_VERSION = "maestro_research_bundle_v1"
LANE_IDS = {"official", "repository", "field", "skeptic"}
CLAIM_KINDS = {"fact", "policy", "preference", "prediction"}
ADOPTIONS = {
    "rule",
    "checklist",
    "warning",
    "optional-pattern",
    "reject",
    "open-question",
}
PACKET_FIELDS = {
    "schema_version",
    "question",
    "lane_id",
    "sources",
    "claims",
    "conflicts",
    "limitations",
}
SOURCE_FIELDS = {
    "source_id",
    "tier",
    "title",
    "url",
    "artifact_ref",
    "version",
    "checked_at",
    "limitations",
}
CLAIM_FIELDS = {
    "claim_id",
    "kind",
    "text",
    "source_refs",
    "artifact_refs",
    "adoption",
}
BUNDLE_FIELDS = {
    "schema_version",
    "workflow_owner",
    "question",
    "depth",
    "packets",
    "synthesis",
    "follow_up_waves",
    "status",
}
SYNTHESIS_FIELDS = {
    "adopted_claim_ids",
    "conflicts",
    "open_questions",
    "limitations",
}
CONFLICT_FIELDS = {
    "claim_ids",
    "material",
    "resolution",
    "evidence_refs",
}


def _issue(
    issues: list[dict[str, str]],
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append({"code": code, "path": path, "message": message})


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(
    value: Any,
    *,
    nonempty: bool = False,
    unique: bool = False,
) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and all(_nonempty_string(item) for item in value)
        and (not unique or len(value) == len(set(value)))
    )


def _iso_date(value: Any) -> bool:
    if not _nonempty_string(value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _packet_issues(
    packet: Any,
    *,
    prefix: str = "packet",
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    issues: list[dict[str, str]] = []
    sources_by_id: dict[str, dict[str, Any]] = {}
    claims_by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(packet, dict):
        _issue(issues, "RESEARCH_PACKET_TYPE", prefix, "ResearchPacket must be an object.")
        return issues, sources_by_id, claims_by_id
    missing = sorted(PACKET_FIELDS - set(packet))
    unexpected = sorted(set(packet) - PACKET_FIELDS)
    if missing:
        _issue(
            issues,
            "RESEARCH_PACKET_FIELDS",
            prefix,
            f"Missing fields: {missing}",
        )
    if unexpected:
        _issue(
            issues,
            "RESEARCH_PACKET_FIELDS",
            prefix,
            f"Unsupported fields: {unexpected}",
        )
    if packet.get("schema_version") != PACKET_VERSION:
        _issue(
            issues,
            "RESEARCH_PACKET_VERSION",
            f"{prefix}.schema_version",
            f"Expected {PACKET_VERSION}.",
        )
    if not _nonempty_string(packet.get("question")):
        _issue(
            issues,
            "RESEARCH_QUESTION_INVALID",
            f"{prefix}.question",
            "Question must be a non-empty string.",
        )
    if packet.get("lane_id") not in LANE_IDS:
        _issue(
            issues,
            "RESEARCH_LANE_UNKNOWN",
            f"{prefix}.lane_id",
            f"Lane must be one of {sorted(LANE_IDS)}.",
        )

    sources = packet.get("sources")
    if not isinstance(sources, list) or not sources:
        _issue(
            issues,
            "RESEARCH_SOURCES_REQUIRED",
            f"{prefix}.sources",
            "At least one inspected source is required.",
        )
        sources = []
    for index, source in enumerate(sources):
        path = f"{prefix}.sources[{index}]"
        if not isinstance(source, dict):
            _issue(issues, "RESEARCH_SOURCE_TYPE", path, "Source must be an object.")
            continue
        unexpected_source = sorted(set(source) - SOURCE_FIELDS)
        if unexpected_source:
            _issue(
                issues,
                "RESEARCH_SOURCE_FIELDS",
                path,
                f"Unsupported fields: {unexpected_source}",
            )
        source_id = source.get("source_id")
        if not _nonempty_string(source_id):
            _issue(
                issues,
                "RESEARCH_SOURCE_ID_INVALID",
                f"{path}.source_id",
                "source_id must be a non-empty string.",
            )
        elif source_id in sources_by_id:
            _issue(
                issues,
                "RESEARCH_SOURCE_ID_DUPLICATE",
                f"{path}.source_id",
                f"Duplicate source_id: {source_id}",
            )
        else:
            sources_by_id[source_id] = source
        tier = source.get("tier")
        if (
            not isinstance(tier, int)
            or isinstance(tier, bool)
            or tier not in range(0, 6)
        ):
            _issue(
                issues,
                "RESEARCH_SOURCE_TIER_INVALID",
                f"{path}.tier",
                "Source tier must be an integer from 0 through 5.",
            )
        if not _nonempty_string(source.get("title")):
            _issue(
                issues,
                "RESEARCH_SOURCE_TITLE_INVALID",
                f"{path}.title",
                "Source title must be a non-empty string.",
            )
        if not (
            _nonempty_string(source.get("url"))
            or _nonempty_string(source.get("artifact_ref"))
        ):
            _issue(
                issues,
                "RESEARCH_SOURCE_LOCATOR_REQUIRED",
                path,
                "A source needs a URL or repository-local artifact reference.",
            )
        if not _iso_date(source.get("checked_at")):
            _issue(
                issues,
                "RESEARCH_SOURCE_DATE_INVALID",
                f"{path}.checked_at",
                "checked_at must be an ISO-8601 calendar date.",
            )
        if "limitations" in source and not _string_list(source["limitations"]):
            _issue(
                issues,
                "RESEARCH_SOURCE_LIMITATIONS_INVALID",
                f"{path}.limitations",
                "Source limitations must be a string list.",
            )

    claims = packet.get("claims")
    if not isinstance(claims, list) or not claims:
        _issue(
            issues,
            "RESEARCH_CLAIMS_REQUIRED",
            f"{prefix}.claims",
            "At least one evidence-bearing claim is required.",
        )
        claims = []
    for index, claim in enumerate(claims):
        path = f"{prefix}.claims[{index}]"
        if not isinstance(claim, dict):
            _issue(issues, "RESEARCH_CLAIM_TYPE", path, "Claim must be an object.")
            continue
        missing_claim = sorted(CLAIM_FIELDS - set(claim))
        unexpected_claim = sorted(set(claim) - CLAIM_FIELDS)
        if missing_claim or unexpected_claim:
            _issue(
                issues,
                "RESEARCH_CLAIM_FIELDS",
                path,
                f"Missing={missing_claim} unsupported={unexpected_claim}",
            )
        claim_id = claim.get("claim_id")
        if not _nonempty_string(claim_id):
            _issue(
                issues,
                "RESEARCH_CLAIM_ID_INVALID",
                f"{path}.claim_id",
                "claim_id must be a non-empty string.",
            )
        elif claim_id in claims_by_id:
            _issue(
                issues,
                "RESEARCH_CLAIM_ID_DUPLICATE",
                f"{path}.claim_id",
                f"Duplicate claim_id: {claim_id}",
            )
        else:
            claims_by_id[claim_id] = claim
        if claim.get("kind") not in CLAIM_KINDS:
            _issue(
                issues,
                "RESEARCH_CLAIM_KIND_INVALID",
                f"{path}.kind",
                f"Claim kind must be one of {sorted(CLAIM_KINDS)}.",
            )
        if not _nonempty_string(claim.get("text")):
            _issue(
                issues,
                "RESEARCH_CLAIM_TEXT_INVALID",
                f"{path}.text",
                "Claim text must be a non-empty string.",
            )
        source_refs = claim.get("source_refs")
        artifact_refs = claim.get("artifact_refs")
        if not _string_list(source_refs, unique=True):
            _issue(
                issues,
                "RESEARCH_CLAIM_SOURCE_REFS_INVALID",
                f"{path}.source_refs",
                "source_refs must be a unique string list.",
            )
            source_refs = []
        if not _string_list(artifact_refs, unique=True):
            _issue(
                issues,
                "RESEARCH_CLAIM_ARTIFACT_REFS_INVALID",
                f"{path}.artifact_refs",
                "artifact_refs must be a unique string list.",
            )
            artifact_refs = []
        if not source_refs and not artifact_refs:
            _issue(
                issues,
                "RESEARCH_CLAIM_EVIDENCE_REQUIRED",
                path,
                "A claim needs a source reference or direct artifact reference.",
            )
        unresolved_refs = sorted(
            source_id
            for source_id in source_refs
            if source_id not in sources_by_id
        )
        if unresolved_refs:
            _issue(
                issues,
                "RESEARCH_CLAIM_SOURCE_UNKNOWN",
                f"{path}.source_refs",
                f"Unknown source references: {unresolved_refs}",
            )
        adoption = claim.get("adoption")
        if adoption not in ADOPTIONS:
            _issue(
                issues,
                "RESEARCH_CLAIM_ADOPTION_INVALID",
                f"{path}.adoption",
                f"Adoption must be one of {sorted(ADOPTIONS)}.",
            )
            continue
        tiers = [
            sources_by_id[source_id].get("tier")
            for source_id in source_refs
            if source_id in sources_by_id
            and isinstance(sources_by_id[source_id].get("tier"), int)
            and not isinstance(sources_by_id[source_id].get("tier"), bool)
        ]
        has_direct_artifact = bool(artifact_refs)
        if adoption == "rule" and not has_direct_artifact and not any(
            tier in {0, 1} for tier in tiers
        ):
            _issue(
                issues,
                "RESEARCH_RULE_AUTHORITY_INSUFFICIENT",
                f"{path}.adoption",
                "A rule requires Tier 0/1 or direct repository evidence.",
            )
        if (
            claim.get("kind") == "policy"
            and adoption == "rule"
            and not has_direct_artifact
            and 0 not in tiers
        ):
            _issue(
                issues,
                "RESEARCH_POLICY_AUTHORITY_INSUFFICIENT",
                f"{path}.adoption",
                "Project policy requires Tier 0 or direct repository evidence.",
            )
        if (
            tiers
            and min(tiers) >= 5
            and not has_direct_artifact
            and adoption not in {"reject", "open-question"}
        ):
            _issue(
                issues,
                "RESEARCH_TIER5_CANNOT_SUPPORT",
                f"{path}.adoption",
                "Tier 5 material is a discovery lead, not final support.",
            )
        if (
            tiers
            and min(tiers) >= 4
            and not has_direct_artifact
            and adoption in {"rule", "checklist", "optional-pattern"}
        ):
            _issue(
                issues,
                "RESEARCH_FIELD_AUTHORITY_EXCEEDED",
                f"{path}.adoption",
                "Tier 4 material may support warnings or questions, not reusable rules.",
            )

    for field in ("conflicts", "limitations"):
        if not _string_list(packet.get(field)):
            _issue(
                issues,
                "RESEARCH_PACKET_LIST_INVALID",
                f"{prefix}.{field}",
                f"{field} must be a string list.",
            )
    return issues, sources_by_id, claims_by_id


def validate_research_packet(packet: Any) -> dict[str, Any]:
    issues, sources, claims = _packet_issues(packet)
    return {
        "schema_version": "maestro_research_packet_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "lane_id": packet.get("lane_id") if isinstance(packet, dict) else None,
        "source_count": len(sources),
        "claim_count": len(claims),
        "artifact_digest": (
            sha256_text(canonical_json(packet)) if not issues else None
        ),
        "writes_performed": False,
    }


def validate_research_bundle(bundle: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    packet_claims: dict[str, dict[str, Any]] = {}
    if not isinstance(bundle, dict):
        _issue(
            issues,
            "RESEARCH_BUNDLE_TYPE",
            "bundle",
            "ResearchBundle must be an object.",
        )
        return {
            "schema_version": "maestro_research_bundle_validation_v1",
            "status": "FAIL",
            "issues": issues,
            "artifact_digest": None,
            "writes_performed": False,
        }
    missing = sorted(BUNDLE_FIELDS - set(bundle))
    unexpected = sorted(set(bundle) - BUNDLE_FIELDS)
    if missing or unexpected:
        _issue(
            issues,
            "RESEARCH_BUNDLE_FIELDS",
            "bundle",
            f"Missing={missing} unsupported={unexpected}",
        )
    if bundle.get("schema_version") != BUNDLE_VERSION:
        _issue(
            issues,
            "RESEARCH_BUNDLE_VERSION",
            "bundle.schema_version",
            f"Expected {BUNDLE_VERSION}.",
        )
    if bundle.get("workflow_owner") != "maestro":
        _issue(
            issues,
            "RESEARCH_WORKFLOW_OWNER_INVALID",
            "bundle.workflow_owner",
            "The bounded research workflow owner must remain maestro.",
        )
    if not _nonempty_string(bundle.get("question")):
        _issue(
            issues,
            "RESEARCH_QUESTION_INVALID",
            "bundle.question",
            "Question must be a non-empty string.",
        )
    if bundle.get("depth") not in {"quick", "normal", "deep"}:
        _issue(
            issues,
            "RESEARCH_DEPTH_INVALID",
            "bundle.depth",
            "Depth must be quick, normal, or deep.",
        )
    follow_up_waves = bundle.get("follow_up_waves")
    if (
        not isinstance(follow_up_waves, int)
        or isinstance(follow_up_waves, bool)
        or follow_up_waves not in {0, 1}
    ):
        _issue(
            issues,
            "RESEARCH_FOLLOW_UP_LIMIT",
            "bundle.follow_up_waves",
            "At most one follow-up wave is allowed.",
        )
        follow_up_waves = 0
    packets = bundle.get("packets")
    maximum_packets = 4 if follow_up_waves == 1 else 3
    if (
        not isinstance(packets, list)
        or not packets
        or len(packets) > maximum_packets
    ):
        _issue(
            issues,
            "RESEARCH_PACKET_LIMIT",
            "bundle.packets",
            f"Bundle must contain 1..{maximum_packets} bounded lane packets.",
        )
        packets = packets if isinstance(packets, list) else []
    lane_ids: list[str] = []
    for index, packet in enumerate(packets):
        packet_issues, _sources, claims = _packet_issues(
            packet,
            prefix=f"bundle.packets[{index}]",
        )
        issues.extend(packet_issues)
        if isinstance(packet, dict) and isinstance(packet.get("lane_id"), str):
            lane_ids.append(packet["lane_id"])
            if packet.get("question") != bundle.get("question"):
                _issue(
                    issues,
                    "RESEARCH_PACKET_QUESTION_MISMATCH",
                    f"bundle.packets[{index}].question",
                    "Every lane packet must answer the bundle question.",
                )
        for claim_id, claim in claims.items():
            if claim_id in packet_claims:
                _issue(
                    issues,
                    "RESEARCH_BUNDLE_CLAIM_DUPLICATE",
                    f"bundle.packets[{index}]",
                    f"Claim IDs must be unique across lanes: {claim_id}",
                )
            else:
                packet_claims[claim_id] = claim
    initial_lane_ids = (
        lane_ids[:-1] if follow_up_waves == 1 else lane_ids
    )
    if len(initial_lane_ids) != len(set(initial_lane_ids)):
        _issue(
            issues,
            "RESEARCH_BUNDLE_LANE_DUPLICATE",
            "bundle.packets",
            "Initial source lanes must be independent and unique.",
        )

    synthesis = bundle.get("synthesis")
    material_conflict = False
    if not isinstance(synthesis, dict):
        _issue(
            issues,
            "RESEARCH_SYNTHESIS_TYPE",
            "bundle.synthesis",
            "Synthesis must be an object.",
        )
        synthesis = {}
    elif set(synthesis) != SYNTHESIS_FIELDS:
        _issue(
            issues,
            "RESEARCH_SYNTHESIS_FIELDS",
            "bundle.synthesis",
            f"Expected fields: {sorted(SYNTHESIS_FIELDS)}",
        )
    adopted_claim_ids = synthesis.get("adopted_claim_ids")
    if not _string_list(adopted_claim_ids, unique=True):
        _issue(
            issues,
            "RESEARCH_ADOPTED_CLAIMS_INVALID",
            "bundle.synthesis.adopted_claim_ids",
            "adopted_claim_ids must be a unique string list.",
        )
        adopted_claim_ids = []
    for claim_id in adopted_claim_ids:
        claim = packet_claims.get(claim_id)
        if claim is None:
            _issue(
                issues,
                "RESEARCH_ADOPTED_CLAIM_UNKNOWN",
                "bundle.synthesis.adopted_claim_ids",
                f"Unknown adopted claim: {claim_id}",
            )
        elif claim.get("adoption") in {"reject", "open-question"}:
            _issue(
                issues,
                "RESEARCH_ADOPTED_CLAIM_NOT_ADOPTABLE",
                "bundle.synthesis.adopted_claim_ids",
                f"Claim {claim_id} is classified as {claim.get('adoption')}.",
            )
    conflicts = synthesis.get("conflicts")
    if not isinstance(conflicts, list):
        _issue(
            issues,
            "RESEARCH_CONFLICTS_INVALID",
            "bundle.synthesis.conflicts",
            "Conflicts must be a list.",
        )
        conflicts = []
    for index, conflict in enumerate(conflicts):
        path = f"bundle.synthesis.conflicts[{index}]"
        if not isinstance(conflict, dict) or set(conflict) != CONFLICT_FIELDS:
            _issue(
                issues,
                "RESEARCH_CONFLICT_FIELDS",
                path,
                f"Expected fields: {sorted(CONFLICT_FIELDS)}",
            )
            continue
        claim_ids = conflict.get("claim_ids")
        if not _string_list(claim_ids, nonempty=True, unique=True) or len(
            claim_ids
        ) < 2:
            _issue(
                issues,
                "RESEARCH_CONFLICT_CLAIMS_INVALID",
                f"{path}.claim_ids",
                "A conflict needs at least two unique claim IDs.",
            )
            claim_ids = []
        for claim_id in claim_ids:
            if claim_id not in packet_claims:
                _issue(
                    issues,
                    "RESEARCH_CONFLICT_CLAIM_UNKNOWN",
                    f"{path}.claim_ids",
                    f"Unknown conflicting claim: {claim_id}",
                )
        if not isinstance(conflict.get("material"), bool):
            _issue(
                issues,
                "RESEARCH_CONFLICT_MATERIAL_INVALID",
                f"{path}.material",
                "material must be a boolean.",
            )
        elif conflict["material"]:
            material_conflict = True
        if conflict.get("resolution") not in {
            "upheld",
            "qualified",
            "unresolved",
            "rejected",
        }:
            _issue(
                issues,
                "RESEARCH_CONFLICT_RESOLUTION_INVALID",
                f"{path}.resolution",
                "Conflict resolution is invalid.",
            )
        if not _string_list(conflict.get("evidence_refs"), nonempty=True, unique=True):
            _issue(
                issues,
                "RESEARCH_CONFLICT_EVIDENCE_REQUIRED",
                f"{path}.evidence_refs",
                "Conflict resolution needs bounded evidence references.",
            )
    for field in ("open_questions", "limitations"):
        if not _string_list(synthesis.get(field)):
            _issue(
                issues,
                "RESEARCH_SYNTHESIS_LIST_INVALID",
                f"bundle.synthesis.{field}",
                f"{field} must be a string list.",
            )
    if follow_up_waves == 1 and not material_conflict:
        _issue(
            issues,
            "RESEARCH_FOLLOW_UP_UNJUSTIFIED",
            "bundle.follow_up_waves",
            "A follow-up wave requires a material conflict.",
        )
    if bundle.get("status") not in {"completed", "insufficient"}:
        _issue(
            issues,
            "RESEARCH_BUNDLE_STATUS_INVALID",
            "bundle.status",
            "Status must be completed or insufficient.",
        )
    if bundle.get("status") == "completed" and not adopted_claim_ids:
        _issue(
            issues,
            "RESEARCH_COMPLETED_WITHOUT_ADOPTION",
            "bundle.status",
            "A completed bundle needs at least one adopted claim.",
        )
    return {
        "schema_version": "maestro_research_bundle_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "artifact_digest": (
            sha256_text(canonical_json(bundle)) if not issues else None
        ),
        "packet_count": len(packets),
        "claim_count": len(packet_claims),
        "adopted_claim_count": len(adopted_claim_ids),
        "writes_performed": False,
    }


def validate_research_artifact(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("schema_version") == PACKET_VERSION:
        return validate_research_packet(value)
    return validate_research_bundle(value)
