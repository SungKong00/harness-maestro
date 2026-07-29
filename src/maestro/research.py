from __future__ import annotations

import copy
import re
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from .errors import MaestroError
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    safe_target,
    sha256_text,
)


PACKET_VERSION = "maestro_research_packet_v2"
BUNDLE_VERSION = "maestro_research_bundle_v2"
LEGACY_PACKET_VERSION = "maestro_research_packet_v1"
LEGACY_BUNDLE_VERSION = "maestro_research_bundle_v1"
RESEARCH_CONTEXT_VERSION = "maestro_assignment_research_context_v1"
LANE_IDS = {"official", "repository", "field", "skeptic"}
CLAIM_KINDS = {
    "fact",
    "policy",
    "preference",
    "prediction",
    "practice",
    "opinion",
    "risk",
}
CLAIM_AUTHORITIES = {"authoritative", "derived", "advisory"}
VERIFICATION_STATUSES = {
    "verified",
    "supported",
    "inferred",
    "contested",
    "unknown",
    "rejected",
}
ADOPTIONS = {
    "rule",
    "checklist",
    "warning",
    "optional-pattern",
    "reject",
    "open-question",
}
SOURCE_ROLES = {
    "direct-evidence",
    "adjacent-comparator",
    "counterexample",
    "foundation-constraint",
    "skeptic",
}
RESEARCH_MODES = {"discover", "contextualize", "refresh"}
PACKET_STATUSES = {"completed", "partial", "blocked"}
ARTIFACT_KINDS = {
    "file",
    "url",
    "user-input",
    "command-output",
    "owner-decision",
}
MAX_PACKET_SOURCES = 12
MAX_PACKET_CLAIMS = 20
MAX_PACKET_ARTIFACTS = 12
MAX_BUNDLE_SOURCES = 24
MAX_BUNDLE_CLAIMS = 32
MAX_BUNDLE_ARTIFACTS = 24
MAX_SYNTHESIS_ITEMS = 32
MAX_BUNDLE_BYTES = 160_000

PACKET_FIELDS = {
    "schema_version",
    "packet_id",
    "status",
    "workflow_owner",
    "decision_scope",
    "question",
    "decision_needed",
    "target_context",
    "date_checked",
    "depth",
    "lane_id",
    "wave",
    "lane_rationale",
    "artifacts_checked",
    "queries_used",
    "sources",
    "claims",
    "conflicts",
    "open_questions",
    "recommended_checklist_items",
    "rejected_claim_ids",
    "limitations",
}
ARTIFACT_FIELDS = {"artifact_id", "kind", "locator", "sha256"}
SOURCE_FIELDS = {
    "source_id",
    "tier",
    "title",
    "url",
    "artifact_ref",
    "source_role",
    "version_sensitive",
    "version",
    "checked_at",
    "inspected_evidence",
    "limitations",
}
CLAIM_FIELDS = {
    "claim_id",
    "kind",
    "statement",
    "authority",
    "verification_status",
    "source_refs",
    "artifact_refs",
    "supporting_evidence",
    "conflicting_evidence",
    "applicability",
    "project_fit",
    "confidence",
    "adoption",
}
CONFIDENCE_FIELDS = {"level", "reason"}
BUNDLE_FIELDS = {
    "schema_version",
    "workflow_owner",
    "request_binding",
    "question",
    "decision_needed",
    "target_context",
    "date_checked",
    "depth",
    "source_plan",
    "packets",
    "synthesis",
    "follow_up_waves",
    "status",
}
REQUEST_BINDING_FIELDS = {
    "goal_digest",
    "research_mode",
    "selected_pack_ids",
    "selected_guide_ids",
    "pack_definition_digests",
}
SOURCE_PLAN_FIELDS = {"lanes", "stop_conditions"}
SOURCE_PLAN_LANE_FIELDS = {
    "lane_id",
    "wave",
    "rationale",
    "decision_impact",
    "queries",
}
SYNTHESIS_FIELDS = {
    "adopted_claim_ids",
    "rejected_claim_ids",
    "recommended_checklist_items",
    "conflicts",
    "open_questions",
    "limitations",
    "confidence",
    "freshness_notes",
}
CONFLICT_FIELDS = {
    "claim_ids",
    "conflict_type",
    "material",
    "resolution",
    "evidence_refs",
    "reason",
    "remaining_uncertainty",
    "what_would_resolve_it",
}

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{2,127}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")


def _issue(
    issues: list[dict[str, str]],
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append({"code": code, "path": path, "message": message})


def _text(value: Any, maximum: int = 4_000) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and "\x00" not in value
    )


def _line(value: Any, maximum: int = 1_000) -> bool:
    return (
        _text(value, maximum)
        and not any(character in value for character in "\r\n")
    )


def _nullable_line(value: Any, maximum: int = 1_000) -> bool:
    return value is None or _line(value, maximum)


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _string_list(
    value: Any,
    *,
    maximum: int = MAX_SYNTHESIS_ITEMS,
    nonempty: bool = False,
    identifiers: bool = False,
) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= maximum
        and (bool(value) or not nonempty)
        and all(
            _identifier(item) if identifiers else _line(item)
            for item in value
        )
        and len(value) == len(set(value))
    )


def _iso_date(value: Any, *, allow_future: bool = False) -> bool:
    if not _line(value, 10):
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed.isoformat() == value and (allow_future or parsed <= date.today())


def _http_url(value: Any) -> bool:
    if not _line(value, 2_000):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _relative_file(value: Any) -> bool:
    if not _line(value, 1_000):
        return False
    parsed = PurePosixPath(value.replace("\\", "/"))
    return (
        not parsed.is_absolute()
        and ".." not in parsed.parts
        and value != "."
        and not value.startswith("./")
    )


def _exact_fields(
    value: Any,
    expected: set[str],
    path: str,
    code: str,
    issues: list[dict[str, str]],
) -> bool:
    if not isinstance(value, dict):
        _issue(issues, code, path, "Expected an object.")
        return False
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    if missing or unexpected:
        _issue(
            issues,
            code,
            path,
            f"Missing={missing} unsupported={unexpected}",
        )
        return False
    return True


def _artifact_issues(
    artifact: Any,
    *,
    path: str,
    repo: Path | None,
) -> tuple[list[dict[str, str]], str | None]:
    issues: list[dict[str, str]] = []
    if not _exact_fields(
        artifact,
        ARTIFACT_FIELDS,
        path,
        "RESEARCH_ARTIFACT_FIELDS",
        issues,
    ):
        return issues, None
    artifact_id = artifact["artifact_id"]
    if not _identifier(artifact_id):
        _issue(
            issues,
            "RESEARCH_ARTIFACT_ID_INVALID",
            f"{path}.artifact_id",
            "artifact_id must be a stable identifier.",
        )
        artifact_id = None
    kind = artifact["kind"]
    locator = artifact["locator"]
    digest = artifact["sha256"]
    if digest is not None and (
        not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None
    ):
        _issue(
            issues,
            "RESEARCH_ARTIFACT_DIGEST_INVALID",
            f"{path}.sha256",
            "sha256 must be null or a canonical SHA-256 digest.",
        )
    if kind not in ARTIFACT_KINDS:
        _issue(
            issues,
            "RESEARCH_ARTIFACT_KIND_INVALID",
            f"{path}.kind",
            f"kind must be one of {sorted(ARTIFACT_KINDS)}.",
        )
    elif kind == "url":
        if not _http_url(locator):
            _issue(
                issues,
                "RESEARCH_ARTIFACT_URL_INVALID",
                f"{path}.locator",
                "URL artifacts require an exact http(s) URL.",
            )
    elif kind == "file":
        if not _relative_file(locator):
            _issue(
                issues,
                "RESEARCH_ARTIFACT_PATH_INVALID",
                f"{path}.locator",
                "File artifacts must use a safe repository-relative path.",
            )
        elif repo is not None:
            try:
                target = safe_target(repo, locator)
            except MaestroError:
                target = None
            if (
                target is None
                or target.is_symlink()
                or not target.is_file()
            ):
                _issue(
                    issues,
                    "RESEARCH_ARTIFACT_FILE_MISSING",
                    f"{path}.locator",
                    "File artifacts must exist as regular files in the bound repository.",
                )
            elif digest != file_sha256(target):
                _issue(
                    issues,
                    "RESEARCH_ARTIFACT_DIGEST_MISMATCH",
                    f"{path}.sha256",
                    "File artifact digest must match the inspected repository file.",
                )
        else:
            _issue(
                issues,
                "RESEARCH_ARTIFACT_REPO_REQUIRED",
                f"{path}.locator",
                "File artifacts must be validated against their bound repository.",
            )
        if digest is None:
            _issue(
                issues,
                "RESEARCH_ARTIFACT_DIGEST_REQUIRED",
                f"{path}.sha256",
                "File artifacts require a content digest.",
            )
    elif kind == "owner-decision":
        decision_path = (
            locator.removeprefix("owner_decision:")
            if isinstance(locator, str)
            else ""
        )
        if (
            not _line(locator, 2_000)
            or not locator.startswith("owner_decision:")
            or not _relative_file(decision_path)
        ):
            _issue(
                issues,
                "RESEARCH_OWNER_DECISION_INVALID",
                f"{path}.locator",
                "Owner-decision artifacts require owner_decision:<repository-relative-file>.",
            )
        elif repo is None:
            _issue(
                issues,
                "RESEARCH_OWNER_DECISION_REPO_REQUIRED",
                f"{path}.locator",
                "Owner-decision authority must be validated against its bound repository.",
            )
        else:
            try:
                target = safe_target(repo, decision_path)
            except MaestroError:
                target = None
            if (
                target is None
                or target.is_symlink()
                or not target.is_file()
            ):
                _issue(
                    issues,
                    "RESEARCH_OWNER_DECISION_FILE_MISSING",
                    f"{path}.locator",
                    "Owner-decision authority requires an existing regular repository file.",
                )
            elif digest != file_sha256(target):
                _issue(
                    issues,
                    "RESEARCH_OWNER_DECISION_DIGEST_MISMATCH",
                    f"{path}.sha256",
                    "Owner-decision digest must match the durable repository decision file.",
                )
        if digest is None:
            _issue(
                issues,
                "RESEARCH_ARTIFACT_DIGEST_REQUIRED",
                f"{path}.sha256",
                "Owner-decision artifacts require a content digest.",
            )
    elif not _line(locator, 2_000):
        _issue(
            issues,
            "RESEARCH_ARTIFACT_LOCATOR_INVALID",
            f"{path}.locator",
            "Artifact locator must be one bounded line.",
        )
    return issues, artifact_id


def _source_issues(
    source: Any,
    *,
    path: str,
    artifacts_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, str]], str | None]:
    issues: list[dict[str, str]] = []
    if not _exact_fields(
        source,
        SOURCE_FIELDS,
        path,
        "RESEARCH_SOURCE_FIELDS",
        issues,
    ):
        return issues, None
    source_id = source["source_id"]
    if not _identifier(source_id):
        _issue(
            issues,
            "RESEARCH_SOURCE_ID_INVALID",
            f"{path}.source_id",
            "source_id must be a stable identifier.",
        )
        source_id = None
    tier = source["tier"]
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
    if not _line(source["title"], 1_000):
        _issue(
            issues,
            "RESEARCH_SOURCE_TITLE_INVALID",
            f"{path}.title",
            "Source title must be one bounded line.",
        )
    url = source["url"]
    artifact_ref = source["artifact_ref"]
    if url is None and artifact_ref is None:
        _issue(
            issues,
            "RESEARCH_SOURCE_LOCATOR_REQUIRED",
            path,
            "A source requires a URL or a checked artifact reference.",
        )
    if url is not None and not _http_url(url):
        _issue(
            issues,
            "RESEARCH_SOURCE_URL_INVALID",
            f"{path}.url",
            "Source URL must be an exact http(s) URL.",
        )
    if artifact_ref is not None and (
        not _identifier(artifact_ref) or artifact_ref not in artifacts_by_id
    ):
        _issue(
            issues,
            "RESEARCH_SOURCE_ARTIFACT_UNKNOWN",
            f"{path}.artifact_ref",
            "artifact_ref must name a checked artifact in this packet.",
        )
    if tier == 0:
        tier0_artifact = artifacts_by_id.get(artifact_ref)
        if tier0_artifact is None:
            _issue(
                issues,
                "RESEARCH_TIER0_ARTIFACT_REQUIRED",
                f"{path}.artifact_ref",
                "Tier 0 project evidence requires a checked project artifact reference.",
            )
        elif tier0_artifact.get("kind") not in {"file", "owner-decision"}:
            _issue(
                issues,
                "RESEARCH_TIER0_AUTHORITY_INVALID",
                f"{path}.artifact_ref",
                "Tier 0 authority requires a digest-checked repository file or durable owner-decision file.",
            )
    if source["source_role"] not in SOURCE_ROLES:
        _issue(
            issues,
            "RESEARCH_SOURCE_ROLE_INVALID",
            f"{path}.source_role",
            f"source_role must be one of {sorted(SOURCE_ROLES)}.",
        )
    if not isinstance(source["version_sensitive"], bool):
        _issue(
            issues,
            "RESEARCH_SOURCE_VERSION_SENSITIVITY_INVALID",
            f"{path}.version_sensitive",
            "version_sensitive must be boolean.",
        )
    if not _nullable_line(source["version"], 500):
        _issue(
            issues,
            "RESEARCH_SOURCE_VERSION_INVALID",
            f"{path}.version",
            "version must be null or one bounded non-empty line.",
        )
    if source["version_sensitive"] is True and source["version"] is None:
        _issue(
            issues,
            "RESEARCH_SOURCE_VERSION_REQUIRED",
            f"{path}.version",
            "Version-sensitive material requires the inspected version or date.",
        )
    if not _iso_date(source["checked_at"]):
        _issue(
            issues,
            "RESEARCH_SOURCE_DATE_INVALID",
            f"{path}.checked_at",
            "checked_at must be a non-future ISO-8601 calendar date.",
        )
    if not _text(source["inspected_evidence"]):
        _issue(
            issues,
            "RESEARCH_SOURCE_EVIDENCE_INVALID",
            f"{path}.inspected_evidence",
            "Record the evidence actually inspected, not a search snippet.",
        )
    if not _string_list(source["limitations"], maximum=12):
        _issue(
            issues,
            "RESEARCH_SOURCE_LIMITATIONS_INVALID",
            f"{path}.limitations",
            "Source limitations must be a bounded unique string list.",
        )
    return issues, source_id


def _source_identity(
    source: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> tuple[str, str] | None:
    if isinstance(source.get("url"), str):
        return ("url", source["url"])
    artifact = artifacts.get(source.get("artifact_ref"))
    if not isinstance(artifact, dict):
        return None
    identity = {
        "kind": artifact.get("kind"),
        "locator": artifact.get("locator"),
        "sha256": artifact.get("sha256"),
    }
    return ("artifact", canonical_json(identity))


def _claim_issues(
    claim: Any,
    *,
    path: str,
    sources_by_id: dict[str, dict[str, Any]],
    artifact_ids: set[str],
) -> tuple[list[dict[str, str]], str | None]:
    issues: list[dict[str, str]] = []
    if not _exact_fields(
        claim,
        CLAIM_FIELDS,
        path,
        "RESEARCH_CLAIM_FIELDS",
        issues,
    ):
        return issues, None
    claim_id = claim["claim_id"]
    if not _identifier(claim_id):
        _issue(
            issues,
            "RESEARCH_CLAIM_ID_INVALID",
            f"{path}.claim_id",
            "claim_id must be a stable identifier.",
        )
        claim_id = None
    if claim["kind"] not in CLAIM_KINDS:
        _issue(
            issues,
            "RESEARCH_CLAIM_KIND_INVALID",
            f"{path}.kind",
            f"kind must be one of {sorted(CLAIM_KINDS)}.",
        )
    if not _text(claim["statement"]):
        _issue(
            issues,
            "RESEARCH_CLAIM_STATEMENT_INVALID",
            f"{path}.statement",
            "Claim statement must be non-empty and bounded.",
        )
    if claim["authority"] not in CLAIM_AUTHORITIES:
        _issue(
            issues,
            "RESEARCH_CLAIM_AUTHORITY_INVALID",
            f"{path}.authority",
            f"authority must be one of {sorted(CLAIM_AUTHORITIES)}.",
        )
    status = claim["verification_status"]
    if status not in VERIFICATION_STATUSES:
        _issue(
            issues,
            "RESEARCH_CLAIM_STATUS_INVALID",
            f"{path}.verification_status",
            f"verification_status must be one of {sorted(VERIFICATION_STATUSES)}.",
        )
    source_refs = claim["source_refs"]
    artifact_refs = claim["artifact_refs"]
    if not _string_list(
        source_refs,
        maximum=12,
        identifiers=True,
    ):
        _issue(
            issues,
            "RESEARCH_CLAIM_SOURCE_REFS_INVALID",
            f"{path}.source_refs",
            "source_refs must be a bounded unique identifier list.",
        )
        source_refs = []
    if not _string_list(
        artifact_refs,
        maximum=12,
        identifiers=True,
    ):
        _issue(
            issues,
            "RESEARCH_CLAIM_ARTIFACT_REFS_INVALID",
            f"{path}.artifact_refs",
            "artifact_refs must be a bounded unique identifier list.",
        )
        artifact_refs = []
    unknown_sources = sorted(set(source_refs) - set(sources_by_id))
    if unknown_sources:
        _issue(
            issues,
            "RESEARCH_CLAIM_SOURCE_UNKNOWN",
            f"{path}.source_refs",
            f"Unknown source references: {unknown_sources}",
        )
    unknown_artifacts = sorted(set(artifact_refs) - artifact_ids)
    if unknown_artifacts:
        _issue(
            issues,
            "RESEARCH_CLAIM_ARTIFACT_UNKNOWN",
            f"{path}.artifact_refs",
            f"Unknown artifact references: {unknown_artifacts}",
        )
    evidence_required = status in {
        "verified",
        "supported",
        "contested",
        "rejected",
    }
    if evidence_required and not source_refs:
        _issue(
            issues,
            "RESEARCH_CLAIM_EVIDENCE_REQUIRED",
            path,
            f"{status} claims require inspected source evidence.",
        )
    for field in (
        "supporting_evidence",
        "applicability",
        "project_fit",
    ):
        if not _text(claim[field]):
            _issue(
                issues,
                "RESEARCH_CLAIM_TEXT_INVALID",
                f"{path}.{field}",
                f"{field} must be non-empty and bounded.",
            )
    if not _string_list(claim["conflicting_evidence"], maximum=12):
        _issue(
            issues,
            "RESEARCH_CLAIM_CONFLICTS_INVALID",
            f"{path}.conflicting_evidence",
            "conflicting_evidence must be a bounded unique string list.",
        )
    confidence = claim["confidence"]
    if not _exact_fields(
        confidence,
        CONFIDENCE_FIELDS,
        f"{path}.confidence",
        "RESEARCH_CLAIM_CONFIDENCE_FIELDS",
        issues,
    ):
        confidence = {}
    if confidence.get("level") not in {"high", "medium", "low"}:
        _issue(
            issues,
            "RESEARCH_CLAIM_CONFIDENCE_INVALID",
            f"{path}.confidence.level",
            "Confidence must be high, medium, or low.",
        )
    if not _text(confidence.get("reason")):
        _issue(
            issues,
            "RESEARCH_CLAIM_CONFIDENCE_INVALID",
            f"{path}.confidence.reason",
            "Confidence requires a bounded evidence-based reason.",
        )
    adoption = claim["adoption"]
    if adoption not in ADOPTIONS:
        _issue(
            issues,
            "RESEARCH_CLAIM_ADOPTION_INVALID",
            f"{path}.adoption",
            f"adoption must be one of {sorted(ADOPTIONS)}.",
        )
        adoption = None

    tiers = {
        sources_by_id[source_id]["tier"]
        for source_id in source_refs
        if source_id in sources_by_id
        and isinstance(sources_by_id[source_id].get("tier"), int)
        and not isinstance(sources_by_id[source_id].get("tier"), bool)
    }
    has_primary_authority = bool(tiers & {0, 1})
    if status == "verified" and not has_primary_authority:
        _issue(
            issues,
            "RESEARCH_VERIFIED_AUTHORITY_INSUFFICIENT",
            f"{path}.verification_status",
            "Verified claims require Tier 0/1 or checked direct artifact evidence.",
        )
    if claim.get("authority") == "authoritative" and not has_primary_authority:
        _issue(
            issues,
            "RESEARCH_CLAIM_AUTHORITY_INSUFFICIENT",
            f"{path}.authority",
            "Authoritative claims require Tier 0/1 or checked direct artifact evidence.",
        )
    if (
        claim.get("kind") == "policy"
        and claim.get("authority") == "authoritative"
        and 0 not in tiers
    ):
        _issue(
            issues,
            "RESEARCH_POLICY_AUTHORITY_INSUFFICIENT",
            f"{path}.authority",
            "Authoritative project policy requires Tier 0 or direct project evidence.",
        )
    if confidence.get("level") == "high" and not has_primary_authority:
        _issue(
            issues,
            "RESEARCH_HIGH_CONFIDENCE_UNSUPPORTED",
            f"{path}.confidence.level",
            "High confidence requires Tier 0/1 or checked direct artifact evidence.",
        )
    if adoption == "rule" and not has_primary_authority:
        _issue(
            issues,
            "RESEARCH_RULE_AUTHORITY_INSUFFICIENT",
            f"{path}.adoption",
            "A reusable rule requires Tier 0/1 or checked direct artifact evidence.",
        )
    if (
        claim.get("kind") == "policy"
        and adoption == "rule"
        and 0 not in tiers
    ):
        _issue(
            issues,
            "RESEARCH_POLICY_RULE_AUTHORITY_INSUFFICIENT",
            f"{path}.adoption",
            "A project policy rule requires Tier 0 or checked project evidence.",
        )
    if tiers and min(tiers) >= 5 and adoption not in {
        "reject",
        "open-question",
    }:
        _issue(
            issues,
            "RESEARCH_TIER5_CANNOT_SUPPORT",
            f"{path}.adoption",
            "Tier 5 material is a discovery lead, not final support.",
        )
    if tiers and min(tiers) >= 4 and adoption in {
        "rule",
        "checklist",
        "optional-pattern",
    }:
        _issue(
            issues,
            "RESEARCH_FIELD_AUTHORITY_EXCEEDED",
            f"{path}.adoption",
            "Tier 4 material supports warnings or questions, not reusable rules.",
        )
    if status == "unknown" and adoption not in {"open-question", "reject"}:
        _issue(
            issues,
            "RESEARCH_UNKNOWN_CLAIM_ADOPTED",
            f"{path}.adoption",
            "Unknown claims must remain open questions or be rejected.",
        )
    if status == "rejected" and adoption != "reject":
        _issue(
            issues,
            "RESEARCH_REJECTED_CLAIM_ADOPTION_INVALID",
            f"{path}.adoption",
            "Rejected claims must use adoption=reject.",
        )
    return issues, claim_id


def _packet_issues(
    packet: Any,
    *,
    prefix: str = "packet",
    repo: Path | None = None,
) -> tuple[
    list[dict[str, str]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    issues: list[dict[str, str]] = []
    artifacts_by_id: dict[str, dict[str, Any]] = {}
    sources_by_id: dict[str, dict[str, Any]] = {}
    claims_by_id: dict[str, dict[str, Any]] = {}
    if not _exact_fields(
        packet,
        PACKET_FIELDS,
        prefix,
        "RESEARCH_PACKET_FIELDS",
        issues,
    ):
        return issues, artifacts_by_id, sources_by_id, claims_by_id
    if packet["schema_version"] != PACKET_VERSION:
        _issue(
            issues,
            "RESEARCH_PACKET_VERSION",
            f"{prefix}.schema_version",
            f"Expected {PACKET_VERSION}.",
        )
    if not _identifier(packet["packet_id"]):
        _issue(
            issues,
            "RESEARCH_PACKET_ID_INVALID",
            f"{prefix}.packet_id",
            "packet_id must be a stable identifier.",
        )
    if packet["status"] not in PACKET_STATUSES:
        _issue(
            issues,
            "RESEARCH_PACKET_STATUS_INVALID",
            f"{prefix}.status",
            f"status must be one of {sorted(PACKET_STATUSES)}.",
        )
    fixed_values = {
        "workflow_owner": "maestro",
        "decision_scope": "research_only",
    }
    for field, expected in fixed_values.items():
        if packet[field] != expected:
            _issue(
                issues,
                "RESEARCH_PACKET_OWNERSHIP_INVALID",
                f"{prefix}.{field}",
                f"{field} must equal {expected!r}.",
            )
    for field in (
        "question",
        "decision_needed",
        "target_context",
        "lane_rationale",
    ):
        if not _text(packet[field]):
            _issue(
                issues,
                "RESEARCH_PACKET_TEXT_INVALID",
                f"{prefix}.{field}",
                f"{field} must be non-empty and bounded.",
            )
    if not _iso_date(packet["date_checked"]):
        _issue(
            issues,
            "RESEARCH_PACKET_DATE_INVALID",
            f"{prefix}.date_checked",
            "date_checked must be a non-future ISO-8601 date.",
        )
    if packet["depth"] not in {"quick", "normal", "deep"}:
        _issue(
            issues,
            "RESEARCH_DEPTH_INVALID",
            f"{prefix}.depth",
            "depth must be quick, normal, or deep.",
        )
    if packet["lane_id"] not in LANE_IDS:
        _issue(
            issues,
            "RESEARCH_LANE_UNKNOWN",
            f"{prefix}.lane_id",
            f"lane_id must be one of {sorted(LANE_IDS)}.",
        )
    if (
        not isinstance(packet["wave"], int)
        or isinstance(packet["wave"], bool)
        or packet["wave"] not in {0, 1}
    ):
        _issue(
            issues,
            "RESEARCH_WAVE_INVALID",
            f"{prefix}.wave",
            "wave must be 0 or 1.",
        )

    artifacts = packet["artifacts_checked"]
    if (
        not isinstance(artifacts, list)
        or not artifacts
        or len(artifacts) > MAX_PACKET_ARTIFACTS
    ):
        _issue(
            issues,
            "RESEARCH_ARTIFACTS_REQUIRED",
            f"{prefix}.artifacts_checked",
            f"artifacts_checked must contain 1..{MAX_PACKET_ARTIFACTS} items.",
        )
        artifacts = artifacts if isinstance(artifacts, list) else []
    for index, artifact in enumerate(artifacts):
        artifact_issues, artifact_id = _artifact_issues(
            artifact,
            path=f"{prefix}.artifacts_checked[{index}]",
            repo=repo,
        )
        issues.extend(artifact_issues)
        if artifact_id is not None:
            if artifact_id in artifacts_by_id:
                _issue(
                    issues,
                    "RESEARCH_ARTIFACT_ID_DUPLICATE",
                    f"{prefix}.artifacts_checked[{index}].artifact_id",
                    f"Duplicate artifact_id: {artifact_id}",
                )
            else:
                artifacts_by_id[artifact_id] = artifact

    if not _string_list(
        packet["queries_used"],
        maximum=8,
        nonempty=True,
    ):
        _issue(
            issues,
            "RESEARCH_QUERIES_INVALID",
            f"{prefix}.queries_used",
            "queries_used must contain 1..8 exact bounded queries or repository paths.",
        )

    sources = packet["sources"]
    if (
        not isinstance(sources, list)
        or not sources
        or len(sources) > MAX_PACKET_SOURCES
    ):
        _issue(
            issues,
            "RESEARCH_SOURCES_REQUIRED",
            f"{prefix}.sources",
            f"sources must contain 1..{MAX_PACKET_SOURCES} inspected sources.",
        )
        sources = sources if isinstance(sources, list) else []
    for index, source in enumerate(sources):
        source_issues, source_id = _source_issues(
            source,
            path=f"{prefix}.sources[{index}]",
            artifacts_by_id=artifacts_by_id,
        )
        issues.extend(source_issues)
        if source_id is not None:
            if source_id in sources_by_id:
                _issue(
                    issues,
                    "RESEARCH_SOURCE_ID_DUPLICATE",
                    f"{prefix}.sources[{index}].source_id",
                    f"Duplicate source_id: {source_id}",
                )
            else:
                sources_by_id[source_id] = source

    claims = packet["claims"]
    if (
        not isinstance(claims, list)
        or not claims
        or len(claims) > MAX_PACKET_CLAIMS
    ):
        _issue(
            issues,
            "RESEARCH_CLAIMS_REQUIRED",
            f"{prefix}.claims",
            f"claims must contain 1..{MAX_PACKET_CLAIMS} evidence claims.",
        )
        claims = claims if isinstance(claims, list) else []
    for index, claim in enumerate(claims):
        claim_issues, claim_id = _claim_issues(
            claim,
            path=f"{prefix}.claims[{index}]",
            sources_by_id=sources_by_id,
            artifact_ids=set(artifacts_by_id),
        )
        issues.extend(claim_issues)
        if claim_id is not None:
            if claim_id in claims_by_id:
                _issue(
                    issues,
                    "RESEARCH_CLAIM_ID_DUPLICATE",
                    f"{prefix}.claims[{index}].claim_id",
                    f"Duplicate claim_id: {claim_id}",
                )
            else:
                claims_by_id[claim_id] = claim

    for field in (
        "conflicts",
        "open_questions",
        "recommended_checklist_items",
        "limitations",
    ):
        if not _string_list(packet[field], maximum=MAX_SYNTHESIS_ITEMS):
            _issue(
                issues,
                "RESEARCH_PACKET_LIST_INVALID",
                f"{prefix}.{field}",
                f"{field} must be a bounded unique string list.",
            )
    rejected_claim_ids = packet["rejected_claim_ids"]
    if not _string_list(
        rejected_claim_ids,
        maximum=MAX_PACKET_CLAIMS,
        identifiers=True,
    ):
        _issue(
            issues,
            "RESEARCH_REJECTED_CLAIMS_INVALID",
            f"{prefix}.rejected_claim_ids",
            "rejected_claim_ids must be a bounded unique identifier list.",
        )
        rejected_claim_ids = []
    expected_rejected = {
        claim_id
        for claim_id, claim in claims_by_id.items()
        if claim.get("adoption") == "reject"
        or claim.get("verification_status") == "rejected"
    }
    if set(rejected_claim_ids) != expected_rejected:
        _issue(
            issues,
            "RESEARCH_REJECTED_CLAIM_SET_MISMATCH",
            f"{prefix}.rejected_claim_ids",
            "rejected_claim_ids must exactly name every rejected claim.",
        )
    if packet["status"] != "completed" and not (
        packet["open_questions"] or packet["limitations"]
    ):
        _issue(
            issues,
            "RESEARCH_INCOMPLETE_PACKET_REASON_REQUIRED",
            f"{prefix}.status",
            "Partial or blocked packets require an open question or limitation.",
        )
    return issues, artifacts_by_id, sources_by_id, claims_by_id


def validate_research_packet(
    packet: Any,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path) if repo_path is not None else None
    issues, artifacts, sources, claims = _packet_issues(
        packet,
        repo=repo,
    )
    return {
        "schema_version": "maestro_research_packet_validation_v2",
        "status": "PASS" if not issues else "FAIL",
        "issues": sorted(
            issues,
            key=lambda item: (item["code"], item["path"], item["message"]),
        ),
        "lane_id": packet.get("lane_id") if isinstance(packet, dict) else None,
        "artifact_count": len(artifacts),
        "source_count": len(sources),
        "claim_count": len(claims),
        "artifact_digest": (
            sha256_text(canonical_json(packet)) if not issues else None
        ),
        "writes_performed": False,
    }


def _request_binding_issues(
    value: Any,
    issues: list[dict[str, str]],
) -> None:
    path = "bundle.request_binding"
    if not _exact_fields(
        value,
        REQUEST_BINDING_FIELDS,
        path,
        "RESEARCH_REQUEST_BINDING_FIELDS",
        issues,
    ):
        return
    if (
        not isinstance(value["goal_digest"], str)
        or _DIGEST.fullmatch(value["goal_digest"]) is None
    ):
        _issue(
            issues,
            "RESEARCH_REQUEST_GOAL_DIGEST_INVALID",
            f"{path}.goal_digest",
            "goal_digest must be a canonical SHA-256 digest.",
        )
    mode = value["research_mode"]
    if mode not in RESEARCH_MODES:
        _issue(
            issues,
            "RESEARCH_REQUEST_MODE_INVALID",
            f"{path}.research_mode",
            f"research_mode must be one of {sorted(RESEARCH_MODES)}.",
        )
    pack_ids = value["selected_pack_ids"]
    guide_ids = value["selected_guide_ids"]
    if not _string_list(pack_ids, maximum=1, identifiers=True):
        _issue(
            issues,
            "RESEARCH_REQUEST_PACKS_INVALID",
            f"{path}.selected_pack_ids",
            "selected_pack_ids must be a unique list with at most one Pack.",
        )
        pack_ids = []
    if not _string_list(guide_ids, maximum=4, identifiers=True):
        _issue(
            issues,
            "RESEARCH_REQUEST_GUIDES_INVALID",
            f"{path}.selected_guide_ids",
            "selected_guide_ids must be a unique list with at most four Guides.",
        )
    digests = value["pack_definition_digests"]
    if (
        not isinstance(digests, dict)
        or set(digests) != set(pack_ids)
        or any(
            not _identifier(pack_id)
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
            for pack_id, digest in digests.items()
        )
    ):
        _issue(
            issues,
            "RESEARCH_REQUEST_PACK_DIGESTS_INVALID",
            f"{path}.pack_definition_digests",
            "Pack definition digests must exactly bind the selected Pack set.",
        )
    if mode == "discover" and (pack_ids or guide_ids or digests):
        _issue(
            issues,
            "RESEARCH_DISCOVERY_BINDING_INVALID",
            path,
            "Discovery research must not claim an already selected Pack or Guide.",
        )
    if mode in {"contextualize", "refresh"} and not pack_ids:
        _issue(
            issues,
            "RESEARCH_PACK_BINDING_REQUIRED",
            path,
            "Contextualize and refresh research require the selected Pack binding.",
        )


def _source_plan_issues(
    value: Any,
    issues: list[dict[str, str]],
) -> dict[tuple[str, int], dict[str, Any]]:
    plan_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    path = "bundle.source_plan"
    if not _exact_fields(
        value,
        SOURCE_PLAN_FIELDS,
        path,
        "RESEARCH_SOURCE_PLAN_FIELDS",
        issues,
    ):
        return plan_by_key
    lanes = value["lanes"]
    if not isinstance(lanes, list) or not lanes or len(lanes) > 4:
        _issue(
            issues,
            "RESEARCH_SOURCE_PLAN_LANES_INVALID",
            f"{path}.lanes",
            "source_plan requires one to four bounded lane entries.",
        )
        lanes = lanes if isinstance(lanes, list) else []
    for index, lane in enumerate(lanes):
        lane_path = f"{path}.lanes[{index}]"
        if not _exact_fields(
            lane,
            SOURCE_PLAN_LANE_FIELDS,
            lane_path,
            "RESEARCH_SOURCE_PLAN_LANE_FIELDS",
            issues,
        ):
            continue
        lane_id = lane["lane_id"]
        wave = lane["wave"]
        if lane_id not in LANE_IDS:
            _issue(
                issues,
                "RESEARCH_LANE_UNKNOWN",
                f"{lane_path}.lane_id",
                f"lane_id must be one of {sorted(LANE_IDS)}.",
            )
        if (
            not isinstance(wave, int)
            or isinstance(wave, bool)
            or wave not in {0, 1}
        ):
            _issue(
                issues,
                "RESEARCH_WAVE_INVALID",
                f"{lane_path}.wave",
                "wave must be 0 or 1.",
            )
        for field in ("rationale", "decision_impact"):
            if not _text(lane[field]):
                _issue(
                    issues,
                    "RESEARCH_SOURCE_PLAN_TEXT_INVALID",
                    f"{lane_path}.{field}",
                    f"{field} must explain why this lane can change the decision.",
                )
        if not _string_list(
            lane["queries"],
            maximum=8,
            nonempty=True,
        ):
            _issue(
                issues,
                "RESEARCH_SOURCE_PLAN_QUERIES_INVALID",
                f"{lane_path}.queries",
                "Each lane requires 1..8 exact queries or repository paths.",
            )
        if lane_id in LANE_IDS and wave in {0, 1}:
            key = (lane_id, wave)
            if key in plan_by_key:
                _issue(
                    issues,
                    "RESEARCH_SOURCE_PLAN_LANE_DUPLICATE",
                    lane_path,
                    "Each lane and wave pair must be unique.",
                )
            else:
                plan_by_key[key] = lane
    initial_lanes = [
        lane_id for lane_id, wave in plan_by_key if wave == 0
    ]
    follow_up_lanes = [
        lane_id for lane_id, wave in plan_by_key if wave == 1
    ]
    if not initial_lanes or len(initial_lanes) > 3:
        _issue(
            issues,
            "RESEARCH_INITIAL_LANE_LIMIT",
            f"{path}.lanes",
            "Use one to three independent initial lanes.",
        )
    if len(follow_up_lanes) > 1:
        _issue(
            issues,
            "RESEARCH_FOLLOW_UP_LIMIT",
            f"{path}.lanes",
            "At most one conflict-only follow-up lane is allowed.",
        )
    if not _string_list(
        value["stop_conditions"],
        maximum=8,
        nonempty=True,
    ):
        _issue(
            issues,
            "RESEARCH_STOP_CONDITIONS_INVALID",
            f"{path}.stop_conditions",
            "source_plan requires bounded stop conditions.",
        )
    return plan_by_key


def _synthesis_issues(
    synthesis: Any,
    *,
    claims_by_id: dict[str, dict[str, Any]],
    evidence_refs: set[str],
    checklist_candidates: set[str],
    issues: list[dict[str, str]],
) -> tuple[list[str], list[str], bool]:
    path = "bundle.synthesis"
    material_conflict = False
    if not _exact_fields(
        synthesis,
        SYNTHESIS_FIELDS,
        path,
        "RESEARCH_SYNTHESIS_FIELDS",
        issues,
    ):
        return [], [], material_conflict
    adopted = synthesis["adopted_claim_ids"]
    rejected = synthesis["rejected_claim_ids"]
    if not _string_list(
        adopted,
        maximum=MAX_SYNTHESIS_ITEMS,
        identifiers=True,
    ):
        _issue(
            issues,
            "RESEARCH_ADOPTED_CLAIMS_INVALID",
            f"{path}.adopted_claim_ids",
            "adopted_claim_ids must be a bounded unique identifier list.",
        )
        adopted = []
    if not _string_list(
        rejected,
        maximum=MAX_SYNTHESIS_ITEMS,
        identifiers=True,
    ):
        _issue(
            issues,
            "RESEARCH_REJECTED_CLAIMS_INVALID",
            f"{path}.rejected_claim_ids",
            "rejected_claim_ids must be a bounded unique identifier list.",
        )
        rejected = []
    for claim_id in adopted:
        claim = claims_by_id.get(claim_id)
        if claim is None:
            _issue(
                issues,
                "RESEARCH_ADOPTED_CLAIM_UNKNOWN",
                f"{path}.adopted_claim_ids",
                f"Unknown adopted claim: {claim_id}",
            )
        elif claim.get("adoption") in {"reject", "open-question"}:
            _issue(
                issues,
                "RESEARCH_ADOPTED_CLAIM_NOT_ADOPTABLE",
                f"{path}.adopted_claim_ids",
                f"Claim {claim_id} is classified as {claim.get('adoption')}.",
            )
        elif claim.get("verification_status") not in {
            "verified",
            "supported",
            "contested",
        }:
            _issue(
                issues,
                "RESEARCH_ADOPTED_CLAIM_UNSUPPORTED",
                f"{path}.adopted_claim_ids",
                f"Claim {claim_id} is not verified, supported, or explicitly contested.",
            )
    expected_rejected = {
        claim_id
        for claim_id, claim in claims_by_id.items()
        if claim.get("adoption") == "reject"
        or claim.get("verification_status") == "rejected"
    }
    if set(rejected) != expected_rejected:
        _issue(
            issues,
            "RESEARCH_REJECTED_CLAIM_SET_MISMATCH",
            f"{path}.rejected_claim_ids",
            "Synthesis must preserve every rejected claim ID.",
        )
    if set(adopted) & set(rejected):
        _issue(
            issues,
            "RESEARCH_CLAIM_DISPOSITION_CONFLICT",
            path,
            "A claim cannot be both adopted and rejected.",
        )
    checklist = synthesis["recommended_checklist_items"]
    if not _string_list(checklist, maximum=MAX_SYNTHESIS_ITEMS):
        _issue(
            issues,
            "RESEARCH_CHECKLIST_INVALID",
            f"{path}.recommended_checklist_items",
            "recommended_checklist_items must be a bounded unique list.",
        )
        checklist = []
    if not set(checklist).issubset(checklist_candidates):
        _issue(
            issues,
            "RESEARCH_CHECKLIST_UNSOURCED",
            f"{path}.recommended_checklist_items",
            "Synthesized checklist items must come from inspected lane packets.",
        )
    if any(
        claims_by_id.get(claim_id, {}).get("adoption") == "checklist"
        for claim_id in adopted
    ) and not checklist:
        _issue(
            issues,
            "RESEARCH_CHECKLIST_REQUIRED",
            f"{path}.recommended_checklist_items",
            "Adopted checklist claims require at least one concrete checklist item.",
        )

    conflicts = synthesis["conflicts"]
    if not isinstance(conflicts, list) or len(conflicts) > 12:
        _issue(
            issues,
            "RESEARCH_CONFLICTS_INVALID",
            f"{path}.conflicts",
            "conflicts must contain at most 12 bounded items.",
        )
        conflicts = []
    for index, conflict in enumerate(conflicts):
        conflict_path = f"{path}.conflicts[{index}]"
        if not _exact_fields(
            conflict,
            CONFLICT_FIELDS,
            conflict_path,
            "RESEARCH_CONFLICT_FIELDS",
            issues,
        ):
            continue
        claim_ids = conflict["claim_ids"]
        if (
            not _string_list(
                claim_ids,
                maximum=8,
                nonempty=True,
                identifiers=True,
            )
            or len(claim_ids) < 2
        ):
            _issue(
                issues,
                "RESEARCH_CONFLICT_CLAIMS_INVALID",
                f"{conflict_path}.claim_ids",
                "A conflict requires at least two unique claim IDs.",
            )
            claim_ids = []
        missing_claims = sorted(set(claim_ids) - set(claims_by_id))
        if missing_claims:
            _issue(
                issues,
                "RESEARCH_CONFLICT_CLAIM_UNKNOWN",
                f"{conflict_path}.claim_ids",
                f"Unknown conflicting claims: {missing_claims}",
            )
        if conflict["conflict_type"] not in {
            "factual",
            "version-or-freshness",
            "scope",
            "authority",
            "practice",
            "preference",
            "transfer",
        }:
            _issue(
                issues,
                "RESEARCH_CONFLICT_TYPE_INVALID",
                f"{conflict_path}.conflict_type",
                "Conflict type must preserve the disagreement boundary.",
            )
        if not isinstance(conflict["material"], bool):
            _issue(
                issues,
                "RESEARCH_CONFLICT_MATERIAL_INVALID",
                f"{conflict_path}.material",
                "material must be boolean.",
            )
        elif conflict["material"]:
            material_conflict = True
        if conflict["resolution"] not in {
            "upheld",
            "qualified",
            "unresolved",
            "rejected",
        }:
            _issue(
                issues,
                "RESEARCH_CONFLICT_RESOLUTION_INVALID",
                f"{conflict_path}.resolution",
                "Conflict resolution is invalid.",
            )
        refs = conflict["evidence_refs"]
        if not _string_list(refs, maximum=12, nonempty=True):
            _issue(
                issues,
                "RESEARCH_CONFLICT_EVIDENCE_INVALID",
                f"{conflict_path}.evidence_refs",
                "Conflict resolution requires bounded evidence references.",
            )
        elif not set(refs).issubset(evidence_refs):
            _issue(
                issues,
                "RESEARCH_CONFLICT_EVIDENCE_UNKNOWN",
                f"{conflict_path}.evidence_refs",
                "Conflict evidence must name an inspected source or artifact.",
            )
        for field in (
            "reason",
            "remaining_uncertainty",
            "what_would_resolve_it",
        ):
            if not _text(conflict[field]):
                _issue(
                    issues,
                    "RESEARCH_CONFLICT_TEXT_INVALID",
                    f"{conflict_path}.{field}",
                    f"{field} must be non-empty and bounded.",
                )
    for field in (
        "open_questions",
        "limitations",
        "freshness_notes",
    ):
        if not _string_list(synthesis[field], maximum=MAX_SYNTHESIS_ITEMS):
            _issue(
                issues,
                "RESEARCH_SYNTHESIS_LIST_INVALID",
                f"{path}.{field}",
                f"{field} must be a bounded unique string list.",
            )
    confidence = synthesis["confidence"]
    if not _exact_fields(
        confidence,
        CONFIDENCE_FIELDS,
        f"{path}.confidence",
        "RESEARCH_SYNTHESIS_CONFIDENCE_FIELDS",
        issues,
    ):
        confidence = {}
    if confidence.get("level") not in {"high", "medium", "low"}:
        _issue(
            issues,
            "RESEARCH_SYNTHESIS_CONFIDENCE_INVALID",
            f"{path}.confidence.level",
            "Confidence must be high, medium, or low.",
        )
    if not _text(confidence.get("reason")):
        _issue(
            issues,
            "RESEARCH_SYNTHESIS_CONFIDENCE_INVALID",
            f"{path}.confidence.reason",
            "Synthesis confidence requires a bounded reason.",
        )
    return adopted, rejected, material_conflict


def validate_research_bundle(
    bundle: Any,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path) if repo_path is not None else None
    issues: list[dict[str, str]] = []
    artifacts_by_id: dict[str, dict[str, Any]] = {}
    sources_by_id: dict[str, dict[str, Any]] = {}
    claims_by_id: dict[str, dict[str, Any]] = {}
    if not _exact_fields(
        bundle,
        BUNDLE_FIELDS,
        "bundle",
        "RESEARCH_BUNDLE_FIELDS",
        issues,
    ):
        return {
            "schema_version": "maestro_research_bundle_validation_v2",
            "status": "FAIL",
            "evidence_status": "invalid",
            "issues": issues,
            "artifact_digest": None,
            "writes_performed": False,
        }
    try:
        bundle_bytes = len(canonical_json(bundle).encode("utf-8"))
    except (TypeError, ValueError, OverflowError):
        bundle_bytes = 0
    if bundle_bytes > MAX_BUNDLE_BYTES:
        _issue(
            issues,
            "RESEARCH_BUNDLE_BYTE_LIMIT",
            "bundle",
            (
                "ResearchBundle exceeds the lossless managed-context limit; "
                "narrow the question or split a later decision instead of truncating evidence."
            ),
        )
    if bundle["schema_version"] != BUNDLE_VERSION:
        _issue(
            issues,
            "RESEARCH_BUNDLE_VERSION",
            "bundle.schema_version",
            f"Expected {BUNDLE_VERSION}.",
        )
    fixed_values = {"workflow_owner": "maestro"}
    for field, expected in fixed_values.items():
        if bundle[field] != expected:
            _issue(
                issues,
                "RESEARCH_BUNDLE_OWNERSHIP_INVALID",
                f"bundle.{field}",
                f"{field} must equal {expected!r}.",
            )
    _request_binding_issues(bundle["request_binding"], issues)
    for field in ("question", "decision_needed", "target_context"):
        if not _text(bundle[field]):
            _issue(
                issues,
                "RESEARCH_BUNDLE_TEXT_INVALID",
                f"bundle.{field}",
                f"{field} must be non-empty and bounded.",
            )
    if not _iso_date(bundle["date_checked"]):
        _issue(
            issues,
            "RESEARCH_BUNDLE_DATE_INVALID",
            "bundle.date_checked",
            "date_checked must be a non-future ISO-8601 date.",
        )
    if bundle["depth"] not in {"quick", "normal", "deep"}:
        _issue(
            issues,
            "RESEARCH_DEPTH_INVALID",
            "bundle.depth",
            "depth must be quick, normal, or deep.",
        )
    source_plan_by_key = _source_plan_issues(bundle["source_plan"], issues)

    follow_up_waves = bundle["follow_up_waves"]
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
    packets = bundle["packets"]
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
    packet_keys: set[tuple[str, int]] = set()
    checklist_candidates: set[str] = set()
    packet_statuses: list[str] = []
    packet_ids: set[str] = set()
    source_locations_by_wave: dict[int, set[tuple[str, str]]] = {
        0: set(),
        1: set(),
    }
    initial_source_locations_by_lane: dict[
        str,
        set[tuple[str, str]],
    ] = {}
    for index, packet in enumerate(packets):
        prefix = f"bundle.packets[{index}]"
        packet_issues, artifacts, sources, claims = _packet_issues(
            packet,
            prefix=prefix,
            repo=repo,
        )
        issues.extend(packet_issues)
        if not isinstance(packet, dict):
            continue
        packet_id = packet.get("packet_id")
        if isinstance(packet_id, str):
            if packet_id in packet_ids:
                _issue(
                    issues,
                    "RESEARCH_PACKET_ID_DUPLICATE",
                    f"{prefix}.packet_id",
                    f"Duplicate packet_id: {packet_id}",
                )
            packet_ids.add(packet_id)
        packet_statuses.append(packet.get("status"))
        expected_equal = {
            "question": bundle["question"],
            "decision_needed": bundle["decision_needed"],
            "target_context": bundle["target_context"],
            "date_checked": bundle["date_checked"],
            "depth": bundle["depth"],
        }
        for field, expected in expected_equal.items():
            if packet.get(field) != expected:
                _issue(
                    issues,
                    "RESEARCH_PACKET_BUNDLE_MISMATCH",
                    f"{prefix}.{field}",
                    f"Packet {field} must match the bundle.",
                )
        lane_id = packet.get("lane_id")
        wave = packet.get("wave")
        if lane_id in LANE_IDS and wave in {0, 1}:
            key = (lane_id, wave)
            if key in packet_keys:
                _issue(
                    issues,
                    "RESEARCH_BUNDLE_LANE_DUPLICATE",
                    prefix,
                    "Each lane and wave pair may appear once.",
                )
            packet_keys.add(key)
            planned = source_plan_by_key.get(key)
            if planned is None:
                _issue(
                    issues,
                    "RESEARCH_PACKET_UNPLANNED",
                    prefix,
                    "Every packet requires a matching source-plan lane.",
                )
            else:
                if packet.get("lane_rationale") != planned["rationale"]:
                    _issue(
                        issues,
                        "RESEARCH_LANE_RATIONALE_MISMATCH",
                        f"{prefix}.lane_rationale",
                        "Packet lane_rationale must match the admitted source plan.",
                    )
                if packet.get("queries_used") != planned["queries"]:
                    _issue(
                        issues,
                        "RESEARCH_QUERY_PLAN_MISMATCH",
                        f"{prefix}.queries_used",
                        "queries_used must exactly preserve the admitted source plan.",
                    )
        for artifact_id, artifact in artifacts.items():
            if artifact_id in artifacts_by_id:
                _issue(
                    issues,
                    "RESEARCH_BUNDLE_ARTIFACT_DUPLICATE",
                    prefix,
                    f"Artifact IDs must be unique across lanes: {artifact_id}",
                )
            else:
                artifacts_by_id[artifact_id] = artifact
        for source_id, source in sources.items():
            if source_id in sources_by_id:
                _issue(
                    issues,
                    "RESEARCH_BUNDLE_SOURCE_DUPLICATE",
                    prefix,
                    f"Source IDs must be unique across lanes: {source_id}",
                )
            else:
                sources_by_id[source_id] = source
            packet_wave = packet.get("wave")
            if packet_wave in {0, 1}:
                locator = _source_identity(source, artifacts)
                if locator is not None:
                    source_locations_by_wave[packet_wave].add(locator)
                    if (
                        packet_wave == 0
                        and isinstance(lane_id, str)
                    ):
                        initial_source_locations_by_lane.setdefault(
                            lane_id,
                            set(),
                        ).add(locator)
        for claim_id, claim in claims.items():
            if claim_id in claims_by_id:
                _issue(
                    issues,
                    "RESEARCH_BUNDLE_CLAIM_DUPLICATE",
                    prefix,
                    f"Claim IDs must be unique across lanes: {claim_id}",
                )
            else:
                claims_by_id[claim_id] = claim
        checklist_candidates.update(
            item
            for item in packet.get("recommended_checklist_items", [])
            if isinstance(item, str)
        )
    if set(source_plan_by_key) != packet_keys:
        _issue(
            issues,
            "RESEARCH_SOURCE_PLAN_PACKET_SET_MISMATCH",
            "bundle.source_plan.lanes",
            "Source-plan lanes must exactly match the returned packet lane and wave set.",
        )
    repeated_follow_up_sources = sorted(
        source_locations_by_wave[0].intersection(
            source_locations_by_wave[1]
        )
    )
    if repeated_follow_up_sources:
        _issue(
            issues,
            "RESEARCH_FOLLOW_UP_NEW_EVIDENCE_REQUIRED",
            "bundle.packets",
            "A conflict follow-up must inspect new source material, not repeat an initial source.",
        )
    if len(initial_source_locations_by_lane) > 1:
        for lane_id, locations in sorted(
            initial_source_locations_by_lane.items(),
        ):
            other_locations = set().union(
                *(
                    other
                    for other_lane, other in (
                        initial_source_locations_by_lane.items()
                    )
                    if other_lane != lane_id
                )
            )
            if not (locations - other_locations):
                _issue(
                    issues,
                    "RESEARCH_INITIAL_LANE_SOURCE_INDEPENDENCE_REQUIRED",
                    "bundle.packets",
                    (
                        f"Initial lane {lane_id} must inspect at least one "
                        "source not already covered by another initial lane."
                    ),
                )
    if len(artifacts_by_id) > MAX_BUNDLE_ARTIFACTS:
        _issue(
            issues,
            "RESEARCH_BUNDLE_ARTIFACT_LIMIT",
            "bundle.packets",
            f"Bundle contains more than {MAX_BUNDLE_ARTIFACTS} checked artifacts.",
        )
    if len(sources_by_id) > MAX_BUNDLE_SOURCES:
        _issue(
            issues,
            "RESEARCH_BUNDLE_SOURCE_LIMIT",
            "bundle.packets",
            f"Bundle contains more than {MAX_BUNDLE_SOURCES} sources.",
        )
    if len(claims_by_id) > MAX_BUNDLE_CLAIMS:
        _issue(
            issues,
            "RESEARCH_BUNDLE_CLAIM_LIMIT",
            "bundle.packets",
            f"Bundle contains more than {MAX_BUNDLE_CLAIMS} claims; narrow the question instead of truncating evidence.",
        )

    evidence_refs = set(artifacts_by_id) | set(sources_by_id)
    adopted, rejected, material_conflict = _synthesis_issues(
        bundle["synthesis"],
        claims_by_id=claims_by_id,
        evidence_refs=evidence_refs,
        checklist_candidates=checklist_candidates,
        issues=issues,
    )
    planned_follow_ups = sum(
        wave == 1 for _, wave in source_plan_by_key
    )
    if planned_follow_ups != follow_up_waves:
        _issue(
            issues,
            "RESEARCH_FOLLOW_UP_COUNT_MISMATCH",
            "bundle.follow_up_waves",
            "follow_up_waves must match the source plan and returned packets.",
        )
    if follow_up_waves == 1 and not material_conflict:
        _issue(
            issues,
            "RESEARCH_FOLLOW_UP_UNJUSTIFIED",
            "bundle.follow_up_waves",
            "A follow-up wave requires a material conflict with new evidence.",
        )
    if bundle["status"] not in {"completed", "insufficient"}:
        _issue(
            issues,
            "RESEARCH_BUNDLE_STATUS_INVALID",
            "bundle.status",
            "status must be completed or insufficient.",
        )
    synthesis = bundle["synthesis"] if isinstance(bundle["synthesis"], dict) else {}
    unresolved_material = any(
        isinstance(conflict, dict)
        and conflict.get("material") is True
        and conflict.get("resolution") == "unresolved"
        for conflict in synthesis.get("conflicts", [])
    )
    if bundle["status"] == "completed":
        if not adopted:
            _issue(
                issues,
                "RESEARCH_COMPLETED_WITHOUT_ADOPTION",
                "bundle.status",
                "A completed bundle requires at least one supported adopted claim.",
            )
        if any(status != "completed" for status in packet_statuses):
            _issue(
                issues,
                "RESEARCH_COMPLETED_WITH_INCOMPLETE_PACKET",
                "bundle.status",
                "A completed bundle may contain only completed lane packets.",
            )
        if unresolved_material:
            _issue(
                issues,
                "RESEARCH_COMPLETED_WITH_UNRESOLVED_CONFLICT",
                "bundle.status",
                "A material unresolved conflict keeps the bundle insufficient.",
            )
    elif bundle["status"] == "insufficient" and not (
        synthesis.get("open_questions")
        or synthesis.get("limitations")
        or unresolved_material
        or any(status != "completed" for status in packet_statuses)
    ):
        _issue(
            issues,
            "RESEARCH_INSUFFICIENT_REASON_REQUIRED",
            "bundle.status",
            "An insufficient bundle requires an open question, limitation, incomplete packet, or unresolved conflict.",
        )

    issues.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return {
        "schema_version": "maestro_research_bundle_validation_v2",
        "status": "PASS" if not issues else "FAIL",
        "evidence_status": bundle["status"] if not issues else "invalid",
        "issues": issues,
        "artifact_digest": (
            sha256_text(canonical_json(bundle)) if not issues else None
        ),
        "packet_count": len(packets),
        "artifact_count": len(artifacts_by_id),
        "source_count": len(sources_by_id),
        "claim_count": len(claims_by_id),
        "bundle_bytes": bundle_bytes,
        "adopted_claim_count": len(adopted),
        "rejected_claim_count": len(rejected),
        "writes_performed": False,
    }


def validate_research_artifact(
    value: Any,
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    version = value.get("schema_version") if isinstance(value, dict) else None
    if version == PACKET_VERSION:
        return validate_research_packet(value, repo_path=repo_path)
    if version == BUNDLE_VERSION:
        return validate_research_bundle(value, repo_path=repo_path)
    if version in {LEGACY_PACKET_VERSION, LEGACY_BUNDLE_VERSION}:
        return _validate_legacy_research_artifact(value)
    return {
        "schema_version": "maestro_research_artifact_validation_v2",
        "status": "FAIL",
        "evidence_status": "invalid",
        "issues": [
            {
                "code": "RESEARCH_SCHEMA_UPGRADE_REQUIRED",
                "path": "schema_version",
                "message": (
                    f"Expected {PACKET_VERSION} or {BUNDLE_VERSION}; "
                    "legacy compact artifacts cannot satisfy the semantic gate."
                ),
            }
        ],
        "artifact_digest": None,
        "writes_performed": False,
    }


def _validate_legacy_research_artifact(value: Any) -> dict[str, Any]:
    """Inspect v1 artifacts without allowing them to satisfy a v2 gate."""

    issues: list[dict[str, str]] = []
    version = value.get("schema_version") if isinstance(value, dict) else None
    packet_fields = {
        "schema_version",
        "question",
        "lane_id",
        "sources",
        "claims",
        "conflicts",
        "limitations",
    }
    source_fields = {
        "source_id",
        "tier",
        "title",
        "url",
        "artifact_ref",
        "version",
        "checked_at",
        "limitations",
    }
    claim_fields = {
        "claim_id",
        "kind",
        "text",
        "source_refs",
        "artifact_refs",
        "adoption",
    }

    def inspect_packet(
        packet: Any,
        path: str,
    ) -> tuple[set[str], set[str]]:
        source_ids: set[str] = set()
        claim_ids: set[str] = set()
        if not _exact_fields(
            packet,
            packet_fields,
            path,
            "RESEARCH_LEGACY_PACKET_FIELDS",
            issues,
        ):
            return source_ids, claim_ids
        if packet["schema_version"] != LEGACY_PACKET_VERSION:
            _issue(
                issues,
                "RESEARCH_LEGACY_PACKET_VERSION",
                f"{path}.schema_version",
                f"Expected {LEGACY_PACKET_VERSION}.",
            )
        if not _text(packet["question"]):
            _issue(
                issues,
                "RESEARCH_LEGACY_QUESTION_INVALID",
                f"{path}.question",
                "Legacy question must be non-empty.",
            )
        if packet["lane_id"] not in LANE_IDS:
            _issue(
                issues,
                "RESEARCH_LEGACY_LANE_INVALID",
                f"{path}.lane_id",
                "Legacy lane is not recognized.",
            )
        sources = packet["sources"]
        if not isinstance(sources, list) or not sources:
            _issue(
                issues,
                "RESEARCH_LEGACY_SOURCES_REQUIRED",
                f"{path}.sources",
                "Legacy packets require inspected sources.",
            )
            sources = []
        source_tiers: dict[str, int] = {}
        for index, source in enumerate(sources):
            source_path = f"{path}.sources[{index}]"
            if not _exact_fields(
                source,
                source_fields,
                source_path,
                "RESEARCH_LEGACY_SOURCE_FIELDS",
                issues,
            ):
                continue
            source_id = source["source_id"]
            if not _identifier(source_id) or source_id in source_ids:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_SOURCE_ID_INVALID",
                    f"{source_path}.source_id",
                    "Legacy source IDs must be unique stable identifiers.",
                )
            else:
                source_ids.add(source_id)
            tier = source["tier"]
            if (
                not isinstance(tier, int)
                or isinstance(tier, bool)
                or tier not in range(0, 6)
            ):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_SOURCE_TIER_INVALID",
                    f"{source_path}.tier",
                    "Legacy source tier must be 0 through 5.",
                )
            elif source_id in source_ids:
                source_tiers[source_id] = tier
            if not _line(source["title"]):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_SOURCE_TITLE_INVALID",
                    f"{source_path}.title",
                    "Legacy source title must be non-empty.",
                )
            if source["url"] is None and source["artifact_ref"] is None:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_SOURCE_LOCATOR_REQUIRED",
                    source_path,
                    "Legacy sources require a URL or artifact reference.",
                )
            if source["url"] is not None and not _http_url(source["url"]):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_SOURCE_URL_INVALID",
                    f"{source_path}.url",
                    "Legacy source URL must be http(s).",
                )
            if (
                source["artifact_ref"] is not None
                and not _line(source["artifact_ref"])
            ):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_SOURCE_ARTIFACT_INVALID",
                    f"{source_path}.artifact_ref",
                    "Legacy artifact reference must be bounded.",
                )
            if not _iso_date(source["checked_at"]):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_SOURCE_DATE_INVALID",
                    f"{source_path}.checked_at",
                    "Legacy checked_at must be a non-future ISO date.",
                )
            if not _string_list(source["limitations"], maximum=12):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_SOURCE_LIMITATIONS_INVALID",
                    f"{source_path}.limitations",
                    "Legacy source limitations are invalid.",
                )
        claims = packet["claims"]
        if not isinstance(claims, list) or not claims:
            _issue(
                issues,
                "RESEARCH_LEGACY_CLAIMS_REQUIRED",
                f"{path}.claims",
                "Legacy packets require claims.",
            )
            claims = []
        for index, claim in enumerate(claims):
            claim_path = f"{path}.claims[{index}]"
            if not _exact_fields(
                claim,
                claim_fields,
                claim_path,
                "RESEARCH_LEGACY_CLAIM_FIELDS",
                issues,
            ):
                continue
            claim_id = claim["claim_id"]
            if not _identifier(claim_id) or claim_id in claim_ids:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_CLAIM_ID_INVALID",
                    f"{claim_path}.claim_id",
                    "Legacy claim IDs must be unique stable identifiers.",
                )
            else:
                claim_ids.add(claim_id)
            if claim["kind"] not in {
                "fact",
                "policy",
                "preference",
                "prediction",
            }:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_CLAIM_KIND_INVALID",
                    f"{claim_path}.kind",
                    "Legacy claim kind is invalid.",
                )
            if not _text(claim["text"]):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_CLAIM_TEXT_INVALID",
                    f"{claim_path}.text",
                    "Legacy claim text must be non-empty.",
                )
            refs = claim["source_refs"]
            if not _string_list(refs, maximum=12, identifiers=True):
                refs = []
                _issue(
                    issues,
                    "RESEARCH_LEGACY_CLAIM_REFS_INVALID",
                    f"{claim_path}.source_refs",
                    "Legacy claim source references are invalid.",
                )
            if not set(refs).issubset(source_ids):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_CLAIM_SOURCE_UNKNOWN",
                    f"{claim_path}.source_refs",
                    "Legacy claim references an unknown source.",
                )
            if claim["adoption"] not in ADOPTIONS:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_CLAIM_ADOPTION_INVALID",
                    f"{claim_path}.adoption",
                    "Legacy claim adoption is invalid.",
                )
            tiers = {
                source_tiers[ref]
                for ref in refs
                if ref in source_tiers
            }
            if claim["adoption"] == "rule" and not tiers.intersection({0, 1}):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_RULE_AUTHORITY_INSUFFICIENT",
                    f"{claim_path}.adoption",
                    "Legacy reusable rules require Tier 0 or 1 evidence.",
                )
        for field in ("conflicts", "limitations"):
            if not _string_list(packet[field]):
                _issue(
                    issues,
                    "RESEARCH_LEGACY_LIST_INVALID",
                    f"{path}.{field}",
                    f"Legacy {field} must be a bounded list.",
                )
        return source_ids, claim_ids

    if version == LEGACY_PACKET_VERSION:
        inspect_packet(value, "packet")
    elif version == LEGACY_BUNDLE_VERSION:
        bundle_fields = {
            "schema_version",
            "workflow_owner",
            "question",
            "depth",
            "packets",
            "synthesis",
            "follow_up_waves",
            "status",
        }
        if _exact_fields(
            value,
            bundle_fields,
            "bundle",
            "RESEARCH_LEGACY_BUNDLE_FIELDS",
            issues,
        ):
            if value["workflow_owner"] != "maestro":
                _issue(
                    issues,
                    "RESEARCH_LEGACY_OWNER_INVALID",
                    "bundle.workflow_owner",
                    "Legacy Maestro bundles require workflow_owner=maestro.",
                )
            packets = value["packets"]
            if not isinstance(packets, list) or not 1 <= len(packets) <= 4:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_PACKET_LIMIT",
                    "bundle.packets",
                    "Legacy bundles require one to four packets.",
                )
                packets = []
            all_claim_ids: set[str] = set()
            for index, packet in enumerate(packets):
                _, claim_ids = inspect_packet(
                    packet,
                    f"bundle.packets[{index}]",
                )
                duplicate = all_claim_ids.intersection(claim_ids)
                if duplicate:
                    _issue(
                        issues,
                        "RESEARCH_LEGACY_CLAIM_ID_DUPLICATE",
                        f"bundle.packets[{index}]",
                        "Legacy claim IDs must be unique across packets.",
                    )
                all_claim_ids.update(claim_ids)
                if (
                    isinstance(packet, dict)
                    and packet.get("question") != value["question"]
                ):
                    _issue(
                        issues,
                        "RESEARCH_LEGACY_QUESTION_MISMATCH",
                        f"bundle.packets[{index}].question",
                        "Legacy packet question must match its bundle.",
                    )
            synthesis_fields = {
                "adopted_claim_ids",
                "conflicts",
                "open_questions",
                "limitations",
            }
            synthesis = value["synthesis"]
            if _exact_fields(
                synthesis,
                synthesis_fields,
                "bundle.synthesis",
                "RESEARCH_LEGACY_SYNTHESIS_FIELDS",
                issues,
            ):
                adopted = synthesis["adopted_claim_ids"]
                if (
                    not _string_list(
                        adopted,
                        maximum=32,
                        identifiers=True,
                    )
                    or not set(adopted).issubset(all_claim_ids)
                ):
                    _issue(
                        issues,
                        "RESEARCH_LEGACY_ADOPTION_INVALID",
                        "bundle.synthesis.adopted_claim_ids",
                        "Legacy adopted claims must resolve inside the bundle.",
                    )
                for field in ("open_questions", "limitations"):
                    if not _string_list(synthesis[field]):
                        _issue(
                            issues,
                            "RESEARCH_LEGACY_SYNTHESIS_LIST_INVALID",
                            f"bundle.synthesis.{field}",
                            "Legacy synthesis list is invalid.",
                        )
                if not isinstance(synthesis["conflicts"], list):
                    _issue(
                        issues,
                        "RESEARCH_LEGACY_CONFLICTS_INVALID",
                        "bundle.synthesis.conflicts",
                        "Legacy conflicts must be a list.",
                    )
            if value["depth"] not in {"quick", "normal", "deep"}:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_DEPTH_INVALID",
                    "bundle.depth",
                    "Legacy depth is invalid.",
                )
            if value["follow_up_waves"] not in {0, 1}:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_FOLLOW_UP_INVALID",
                    "bundle.follow_up_waves",
                    "Legacy follow_up_waves must be zero or one.",
                )
            if value["status"] not in {"completed", "insufficient"}:
                _issue(
                    issues,
                    "RESEARCH_LEGACY_STATUS_INVALID",
                    "bundle.status",
                    "Legacy bundle status is invalid.",
                )
    issues.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return {
        "schema_version": "maestro_research_legacy_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "evidence_status": "historical" if not issues else "invalid",
        "gate_eligible": False,
        "issues": issues,
        "artifact_digest": (
            sha256_text(canonical_json(value)) if not issues else None
        ),
        "writes_performed": False,
    }


def expected_research_binding(
    goal: str,
    expertise: dict[str, Any],
) -> dict[str, Any]:
    """Return the exact route binding that a ResearchBundle must preserve."""

    requirement = expertise.get("research_requirement", {})
    return {
        "goal_digest": sha256_text(goal),
        "research_mode": requirement.get("mode"),
        "selected_pack_ids": copy.deepcopy(
            expertise.get("selected_pack_ids", [])
        ),
        "selected_guide_ids": copy.deepcopy(
            expertise.get("selected_guide_ids", [])
        ),
        "pack_definition_digests": copy.deepcopy(
            expertise.get("pack_definition_digests", {})
        ),
    }


def require_completed_research_bundle(
    bundle: Any,
    *,
    goal: str,
    expertise: dict[str, Any],
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate one execution-gate bundle and bind it to the exact request."""

    if (
        not isinstance(bundle, dict)
        or bundle.get("schema_version") != BUNDLE_VERSION
    ):
        raise MaestroError(
            "RESEARCH_BUNDLE_REQUIRED",
            "A research gate requires one synthesized v2 ResearchBundle.",
        )
    validation = validate_research_bundle(bundle, repo_path=repo_path)
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    if validation["evidence_status"] != "completed":
        raise MaestroError(
            "RESEARCH_EVIDENCE_INSUFFICIENT",
            "Only a completed ResearchBundle can satisfy an execution gate.",
        )
    if bundle["request_binding"] != expected_research_binding(goal, expertise):
        raise MaestroError(
            "RESEARCH_EVIDENCE_BINDING_MISMATCH",
            "The ResearchBundle does not match this goal, research mode, "
            "selected Pack, Guides, and Pack definition digests.",
        )
    return validation


def project_research_context(
    bundle: dict[str, Any],
    *,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Project full bounded decision-ready evidence without packet boilerplate."""

    validation = validate_research_bundle(bundle, repo_path=repo_path)
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    if validation["evidence_status"] != "completed":
        raise MaestroError(
            "RESEARCH_EVIDENCE_INSUFFICIENT",
            "An insufficient ResearchBundle cannot be projected for execution.",
        )
    lanes: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    for packet in bundle["packets"]:
        lanes.append(
            {
                "packet_id": packet["packet_id"],
                "lane_id": packet["lane_id"],
                "wave": packet["wave"],
                "status": packet["status"],
                "lane_rationale": packet["lane_rationale"],
                "queries_used": copy.deepcopy(packet["queries_used"]),
                "conflicts": copy.deepcopy(packet["conflicts"]),
                "open_questions": copy.deepcopy(packet["open_questions"]),
                "recommended_checklist_items": copy.deepcopy(
                    packet["recommended_checklist_items"]
                ),
                "rejected_claim_ids": copy.deepcopy(
                    packet["rejected_claim_ids"]
                ),
                "limitations": copy.deepcopy(packet["limitations"]),
            }
        )
        artifacts.extend(copy.deepcopy(packet["artifacts_checked"]))
        sources.extend(copy.deepcopy(packet["sources"]))
        claims.extend(copy.deepcopy(packet["claims"]))
    return {
        "schema_version": RESEARCH_CONTEXT_VERSION,
        "evidence_digest": validation["artifact_digest"],
        "request_binding": copy.deepcopy(bundle["request_binding"]),
        "question": bundle["question"],
        "decision_needed": bundle["decision_needed"],
        "target_context": bundle["target_context"],
        "date_checked": bundle["date_checked"],
        "depth": bundle["depth"],
        "source_plan": copy.deepcopy(bundle["source_plan"]),
        "lanes": lanes,
        "artifacts_checked": artifacts,
        "sources": sources,
        "claims": claims,
        "synthesis": copy.deepcopy(bundle["synthesis"]),
    }
