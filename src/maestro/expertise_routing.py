from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Iterable

from .errors import MaestroError
from .util import canonical_json, sha256_text


ROUTE_HINT_SCHEMA_VERSION = "maestro_expertise_route_hints_v1"
ROUTING_SUMMARY_SCHEMA_VERSION = "maestro_expertise_routing_summary_v1"
MAX_WORK_KINDS = 2
MAX_AFFECTED_PATHS = 32
MAX_AFFECTED_PATH_LENGTH = 240
MAX_ROUTE_ATTEMPT = 2
DESIGN_ASSURANCE_MODES = {"compact", "standard", "system"}
HIGH_RISK_LEVELS = {"high", "critical"}
PLAN_DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
CONFLICT_WARNING_CODES = {
    "EXPERTISE_HINTS_AMBIGUOUS",
    "EXPERTISE_OVERRIDE_CONFLICT",
    "EXPERTISE_SELECTION_AMBIGUOUS",
}
ROUTING_SELECTION_SOURCES = {
    "natural_language",
    "work_kind",
    "explicit_pack",
    "none",
}
CANDIDATE_ROUTING_ROLES = {
    "ordinary-route",
    "corrected-task-gap",
    "management-only",
}
COMPLEX_CANDIDATE_CHANGE_KINDS = {
    "pack-merge",
    "pack-extraction",
    "pack-split",
    "guide-move",
    "guide-copy",
}

WORK_KIND_TO_PACK_ID = {
    "user-interface": "product-design",
    "content-claim": "marketing",
    "software-structure": "software-engineering",
    "security-sensitive": "security-engineering",
    "data-change": "data-engineering",
    "delivery-operation": "devops-sre",
    "quality-verification": "software-qa",
}

POLICY_ID = "expertise-route-hints-v1"
POLICY_DIGEST = sha256_text(
    canonical_json(
        {
            "policy_id": POLICY_ID,
            "schema_version": ROUTE_HINT_SCHEMA_VERSION,
            "work_kind_to_pack_id": WORK_KIND_TO_PACK_ID,
            "max_work_kinds": MAX_WORK_KINDS,
            "max_affected_paths": MAX_AFFECTED_PATHS,
            "max_affected_path_length": MAX_AFFECTED_PATH_LENGTH,
            "max_route_attempt": MAX_ROUTE_ATTEMPT,
            "path_policy": "audit-only",
            "user_interface_assurance_default": "standard",
            "normal_conflict_policy": "warn-and-use-first-structured-signal",
            "high_risk_conflict_policy": "stop-before-assignments",
            "reroute_lineage": "one-correction-bound-to-prior-plan",
        }
    )
)


def candidate_routing_policy(
    *,
    generation_mode: str | None,
    change_kind: str | None,
    grouped: bool = False,
) -> dict[str, Any]:
    """Classify candidate use without conflating validation and authority."""

    if grouped or change_kind in COMPLEX_CANDIDATE_CHANGE_KINDS:
        role = "management-only"
        reason = (
            "atomic-change-set"
            if grouped
            else "complex-topology-change"
        )
    elif generation_mode == "task-gap":
        role = "corrected-task-gap"
        reason = "exact-producing-route-only"
    else:
        role = "ordinary-route"
        reason = "validated-project-candidate"
    return {
        "routing_role": role,
        "routing_reason": reason,
        "ordinary_route_allowed": role == "ordinary-route",
        "corrected_task_gap_allowed": role == "corrected-task-gap",
    }


def expertise_routing_summary(selection: Any) -> dict[str, Any]:
    """Project one validated selection into bounded Pilot telemetry."""

    if not isinstance(selection, dict):
        raise MaestroError(
            "EXPERTISE_ROUTING_SUMMARY_INVALID",
            "Expertise selection must be an object.",
        )
    selected_pack_ids = selection.get("selected_pack_ids")
    if not isinstance(selected_pack_ids, list):
        raise MaestroError(
            "EXPERTISE_ROUTING_SUMMARY_INVALID",
            "Expertise selection must contain selected_pack_ids.",
        )
    selected = bool(selected_pack_ids)
    hints = selection.get("route_hints")
    normalized_hints = require_route_hints(hints) if hints is not None else None
    structured_routing = (
        selection.get("selection_trace", {}).get("structured_routing")
        if isinstance(selection.get("selection_trace"), dict)
        else None
    )

    if not selected:
        source = "none"
    elif (
        normalized_hints is not None
        and normalized_hints["explicit_pack_id"] is not None
    ):
        source = "explicit_pack"
    elif (
        isinstance(structured_routing, dict)
        and structured_routing.get("structured_pack_id") is not None
    ):
        source = "work_kind"
    else:
        source = "natural_language"

    warning_codes = list(
        dict.fromkeys(
            warning["code"]
            for warning in selection.get("warnings", [])
            if isinstance(warning, dict)
            and warning.get("code") in CONFLICT_WARNING_CODES
        )
    )
    return {
        "schema_version": ROUTING_SUMMARY_SCHEMA_VERSION,
        "selection_state": "selected" if selected else "not_selected",
        "selection_source": source,
        "route_attempt": (
            normalized_hints["route_attempt"]
            if normalized_hints is not None
            else 1
        ),
        "conflict_warning_codes": warning_codes,
    }


def valid_expertise_routing_summary(
    value: Any,
    *,
    selected_pack_ids: list[str] | None = None,
) -> bool:
    """Validate compact telemetry without re-running Pack selection."""

    if value is None:
        return True
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "selection_state",
            "selection_source",
            "route_attempt",
            "conflict_warning_codes",
        }
        or value.get("schema_version") != ROUTING_SUMMARY_SCHEMA_VERSION
        or value.get("selection_state") not in {"selected", "not_selected"}
        or value.get("selection_source") not in ROUTING_SELECTION_SOURCES
        or value.get("route_attempt") not in {1, 2}
        or isinstance(value.get("route_attempt"), bool)
    ):
        return False
    warning_codes = value.get("conflict_warning_codes")
    if (
        not isinstance(warning_codes, list)
        or len(warning_codes) > len(CONFLICT_WARNING_CODES)
        or len(set(warning_codes)) != len(warning_codes)
        or any(code not in CONFLICT_WARNING_CODES for code in warning_codes)
    ):
        return False

    selected = value["selection_state"] == "selected"
    if selected != (value["selection_source"] != "none"):
        return False
    if not selected and warning_codes:
        return False
    if selected_pack_ids is not None and selected != bool(selected_pack_ids):
        return False
    return True


def valid_route_correction_summary(
    value: Any,
    *,
    route_attempt: int,
) -> bool:
    """Validate the first-route lineage retained in observed plan summaries."""

    if route_attempt == 1:
        return value is None
    return (
        route_attempt == 2
        and isinstance(value, dict)
        and set(value)
        == {"prior_plan_id", "prior_source_route_digest"}
        and all(
            isinstance(value.get(field), str)
            and PLAN_DIGEST_PATTERN.fullmatch(value[field]) is not None
            for field in (
                "prior_plan_id",
                "prior_source_route_digest",
            )
        )
    )


def _unique_strings(
    values: Iterable[str] | None,
    *,
    code: str,
    field: str,
) -> list[str]:
    normalized: list[str] = []
    for value in values or ():
        if not isinstance(value, str) or not value.strip():
            raise MaestroError(code, f"{field} entries must be non-empty strings.")
        item = value.strip()
        if item not in normalized:
            normalized.append(item)
    return normalized


def _normalize_affected_path(value: str) -> str:
    if (
        "\x00" in value
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value) is not None
        or len(value) > MAX_AFFECTED_PATH_LENGTH
    ):
        raise MaestroError(
            "EXPERTISE_AFFECTED_PATH_INVALID",
            (
                "Affected paths must be short POSIX-style repository-relative "
                "paths."
            ),
        )
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise MaestroError(
            "EXPERTISE_AFFECTED_PATH_INVALID",
            "Affected paths must stay inside the repository and cannot contain '.' or '..'.",
        )
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise MaestroError(
            "EXPERTISE_AFFECTED_PATH_INVALID",
            "Affected paths must identify a repository-relative path.",
        )
    return normalized


def normalize_route_hints(
    *,
    work_kinds: Iterable[str] | None = None,
    affected_paths: Iterable[str] | None = None,
    explicit_pack_id: str | None = None,
    route_attempt: int = 1,
    prior_plan_id: str | None = None,
    prior_source_route_digest: str | None = None,
    design_assurance_mode: str | None = None,
) -> dict[str, Any]:
    """Validate and canonicalize Host-confirmed expertise routing signals."""

    kinds = _unique_strings(
        work_kinds,
        code="EXPERTISE_WORK_KIND_INVALID",
        field="work_kinds",
    )
    unknown = sorted(set(kinds) - set(WORK_KIND_TO_PACK_ID))
    if unknown:
        raise MaestroError(
            "EXPERTISE_WORK_KIND_INVALID",
            f"Unsupported work kinds: {', '.join(unknown)}.",
        )
    if len(kinds) > MAX_WORK_KINDS:
        raise MaestroError(
            "EXPERTISE_WORK_KIND_LIMIT_EXCEEDED",
            f"At most {MAX_WORK_KINDS} work kinds may be routed in one stage.",
        )

    raw_paths = _unique_strings(
        affected_paths,
        code="EXPERTISE_AFFECTED_PATH_INVALID",
        field="affected_paths",
    )
    if len(raw_paths) > MAX_AFFECTED_PATHS:
        raise MaestroError(
            "EXPERTISE_AFFECTED_PATH_LIMIT_EXCEEDED",
            f"At most {MAX_AFFECTED_PATHS} affected paths may be recorded.",
        )
    paths: list[str] = []
    for raw_path in raw_paths:
        normalized_path = _normalize_affected_path(raw_path)
        if normalized_path not in paths:
            paths.append(normalized_path)
    paths.sort()

    if explicit_pack_id is not None:
        if (
            not isinstance(explicit_pack_id, str)
            or not explicit_pack_id.strip()
        ):
            raise MaestroError(
                "EXPERTISE_PACK_EXPLICIT_INVALID",
                "explicit_pack_id must be a non-empty Pack ID.",
            )
        explicit_pack_id = explicit_pack_id.strip()

    if (
        not isinstance(route_attempt, int)
        or isinstance(route_attempt, bool)
        or route_attempt not in {1, MAX_ROUTE_ATTEMPT}
    ):
        raise MaestroError(
            "EXPERTISE_ROUTE_ATTEMPT_INVALID",
            (
                "expertise route attempt must be 1 for the initial stage route "
                f"or {MAX_ROUTE_ATTEMPT} for its single correction."
            ),
        )

    prior_digests = (prior_plan_id, prior_source_route_digest)
    if route_attempt == 1 and any(item is not None for item in prior_digests):
        raise MaestroError(
            "EXPERTISE_ROUTE_LINEAGE_INVALID",
            "An initial stage route cannot reference a prior route plan.",
        )
    if route_attempt == MAX_ROUTE_ATTEMPT and any(
        not isinstance(item, str)
        or PLAN_DIGEST_PATTERN.fullmatch(item) is None
        for item in prior_digests
    ):
        raise MaestroError(
            "EXPERTISE_ROUTE_LINEAGE_REQUIRED",
            "The single corrected route must bind the prior plan and source-route digests.",
        )

    if design_assurance_mode is None and "user-interface" in kinds:
        design_assurance_mode = "standard"
    if (
        design_assurance_mode is not None
        and (
            design_assurance_mode not in DESIGN_ASSURANCE_MODES
            or "user-interface" not in kinds
        )
    ):
        raise MaestroError(
            "DESIGN_ASSURANCE_MODE_INVALID",
            (
                "design_assurance_mode must be compact, standard, or system "
                "and is valid only with work_kind=user-interface."
            ),
        )

    normalized = {
        "schema_version": ROUTE_HINT_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "policy_digest": POLICY_DIGEST,
        "work_kinds": kinds,
        "affected_paths": paths,
        "path_policy": "audit-only",
        "explicit_pack_id": explicit_pack_id,
        "route_attempt": route_attempt,
        "prior_plan_id": prior_plan_id,
        "prior_source_route_digest": prior_source_route_digest,
    }
    if design_assurance_mode is not None:
        normalized["design_assurance_mode"] = design_assurance_mode
    return normalized


def require_route_hints(value: Any) -> dict[str, Any]:
    """Reconstruct a canonical hint object crossing a plan boundary."""

    if not isinstance(value, dict):
        raise MaestroError(
            "EXPERTISE_ROUTE_HINTS_INVALID",
            "Expertise route hints must be an object.",
        )
    expected_fields = {
        "schema_version",
        "policy_id",
        "policy_digest",
        "work_kinds",
        "affected_paths",
        "path_policy",
        "explicit_pack_id",
        "route_attempt",
        "prior_plan_id",
        "prior_source_route_digest",
    }
    optional_fields = {"design_assurance_mode"}
    if (
        not expected_fields.issubset(value)
        or set(value) - expected_fields - optional_fields
    ):
        raise MaestroError(
            "EXPERTISE_ROUTE_HINTS_INVALID",
            "Expertise route hints contain missing or unsupported fields.",
        )
    canonical = normalize_route_hints(
        work_kinds=value.get("work_kinds"),
        affected_paths=value.get("affected_paths"),
        explicit_pack_id=value.get("explicit_pack_id"),
        route_attempt=value.get("route_attempt"),
        prior_plan_id=value.get("prior_plan_id"),
        prior_source_route_digest=value.get("prior_source_route_digest"),
        design_assurance_mode=value.get("design_assurance_mode"),
    )
    if value != canonical:
        raise MaestroError(
            "EXPERTISE_ROUTE_HINTS_MISMATCH",
            "Expertise route hints do not match the active routing policy.",
        )
    return canonical


def resolve_structured_pack(
    route_hints: dict[str, Any],
    *,
    eligible_pack_ids: set[str],
    catalog_pack_ids: set[str],
) -> tuple[str | None, list[dict[str, Any]], dict[str, Any]]:
    """Resolve structured signals without owning catalog loading or lexical scoring."""

    hints = require_route_hints(route_hints)
    explicit_pack_id = hints["explicit_pack_id"]
    if explicit_pack_id is not None and explicit_pack_id not in eligible_pack_ids:
        code = (
            "EXPERTISE_PACK_EXPLICIT_INELIGIBLE"
            if explicit_pack_id in catalog_pack_ids
            else "EXPERTISE_PACK_EXPLICIT_UNKNOWN"
        )
        raise MaestroError(
            code,
            (
                f"Explicit Pack {explicit_pack_id} is "
                + (
                    "not eligible for this project route."
                    if code.endswith("INELIGIBLE")
                    else "not present in the eligible catalog."
                )
            ),
        )

    work_kind_targets = list(
        dict.fromkeys(
            WORK_KIND_TO_PACK_ID[work_kind]
            for work_kind in hints["work_kinds"]
        )
    )
    unavailable_targets = [
        pack_id
        for pack_id in work_kind_targets
        if pack_id not in eligible_pack_ids
    ]
    if unavailable_targets:
        raise MaestroError(
            "EXPERTISE_WORK_KIND_PACK_INELIGIBLE",
            (
                "Work-kind mapping targets an unavailable Pack: "
                f"{', '.join(unavailable_targets)}."
            ),
        )

    warnings: list[dict[str, Any]] = []
    conflict: dict[str, Any] | None = None
    if (
        explicit_pack_id is not None
        and work_kind_targets
        and any(pack_id != explicit_pack_id for pack_id in work_kind_targets)
    ):
        conflict = {
            "code": "EXPERTISE_OVERRIDE_CONFLICT",
            "candidate_pack_ids": list(
                dict.fromkeys([explicit_pack_id, *work_kind_targets])
            ),
            "selected_pack_id": explicit_pack_id,
            "message": (
                "The explicit Pack conflicts with the confirmed work kind; "
                "the explicit Pack wins only for a non-high-risk route."
            ),
        }
    elif len(work_kind_targets) > 1:
        conflict = {
            "code": "EXPERTISE_HINTS_AMBIGUOUS",
            "candidate_pack_ids": work_kind_targets,
            "selected_pack_id": work_kind_targets[0],
            "message": (
                "Confirmed work kinds point to different Packs; the first "
                "work kind wins only for a non-high-risk route."
            ),
        }

    if conflict is not None:
        warnings.append(conflict)

    selected_pack_id = (
        explicit_pack_id
        if explicit_pack_id is not None
        else work_kind_targets[0]
        if work_kind_targets
        else None
    )
    if (
        "user-interface" in hints["work_kinds"]
        and selected_pack_id != "product-design"
    ):
        raise MaestroError(
            "DESIGN_ASSURANCE_ROUTE_CONFLICT",
            (
                "A structured user-interface mutation cannot route around "
                "Product Design assurance. Split the work or make "
                "user-interface the owning structured work kind."
            ),
        )
    return (
        selected_pack_id,
        warnings,
        {
            "rule_id": POLICY_ID,
            "policy_digest": POLICY_DIGEST,
            "structured_pack_id": selected_pack_id,
            "work_kind_pack_ids": work_kind_targets,
            "path_policy": hints["path_policy"],
            "route_attempt": hints["route_attempt"],
            "prior_plan_id": hints["prior_plan_id"],
            "prior_source_route_digest": hints[
                "prior_source_route_digest"
            ],
            "design_assurance_mode": hints.get(
                "design_assurance_mode"
            ),
        },
    )


def require_reroute_lineage(
    route_hints: dict[str, Any] | None,
    *,
    prior_plan: dict[str, Any] | None,
    current_plan: dict[str, Any],
) -> None:
    """Enforce one correction with unchanged stage identity before observation."""

    if route_hints is None:
        if prior_plan is not None:
            raise MaestroError(
                "EXPERTISE_ROUTE_LINEAGE_UNEXPECTED",
                "A prior route plan requires corrected route hints.",
            )
        return
    hints = require_route_hints(route_hints)
    if hints["route_attempt"] == 1:
        if prior_plan is not None:
            raise MaestroError(
                "EXPERTISE_ROUTE_LINEAGE_UNEXPECTED",
                "An initial route cannot receive a prior route plan.",
            )
        return
    if not isinstance(prior_plan, dict):
        raise MaestroError(
            "EXPERTISE_ROUTE_LINEAGE_REQUIRED",
            "The single corrected route requires the exact prior route v2 plan.",
        )
    prior_hints = (
        prior_plan.get("expertise", {}).get("route_hints")
        if isinstance(prior_plan.get("expertise"), dict)
        else None
    )
    if (
        isinstance(prior_hints, dict)
        and prior_hints.get("route_attempt") == MAX_ROUTE_ATTEMPT
    ):
        raise MaestroError(
            "EXPERTISE_REROUTE_LIMIT_EXCEEDED",
            "A stage may have only one corrected expertise route.",
        )
    if (
        hints["prior_plan_id"] != prior_plan.get("plan_id")
        or hints["prior_source_route_digest"]
        != prior_plan.get("source_route_digest")
    ):
        raise MaestroError(
            "EXPERTISE_ROUTE_LINEAGE_MISMATCH",
            "Corrected route hints do not bind the supplied prior plan.",
        )
    if current_plan.get("source_route_digest") != prior_plan.get(
        "source_route_digest"
    ):
        raise MaestroError(
            "EXPERTISE_REROUTE_STAGE_CHANGED",
            (
                "A corrected expertise route must preserve the exact Lens, "
                "Department, model, and source-route decision."
            ),
        )
    stable_fields = ("goal", "risk", "intent", "department")
    changed_fields = [
        field
        for field in stable_fields
        if current_plan.get(field) != prior_plan.get(field)
    ]
    current_host = (
        current_plan.get("model_route", {}).get("host")
        if isinstance(current_plan.get("model_route"), dict)
        else None
    )
    prior_host = (
        prior_plan.get("model_route", {}).get("host")
        if isinstance(prior_plan.get("model_route"), dict)
        else None
    )
    if current_host != prior_host:
        changed_fields.append("host")
    if changed_fields:
        raise MaestroError(
            "EXPERTISE_REROUTE_STAGE_CHANGED",
            (
                "A corrected route must preserve the stage goal, risk, intent, "
                f"department, and Host. Changed: {', '.join(changed_fields)}."
            ),
        )


def enforce_conflict_policy(
    selection: dict[str, Any],
    *,
    risk: str,
) -> None:
    """Stop high-risk execution plans when selection still contains a conflict."""

    if risk not in HIGH_RISK_LEVELS:
        return
    conflicts = [
        warning
        for warning in selection.get("warnings", [])
        if isinstance(warning, dict)
        and warning.get("code") in CONFLICT_WARNING_CODES
    ]
    if not conflicts:
        return
    candidate_pack_ids = list(
        dict.fromkeys(
            pack_id
            for warning in conflicts
            for pack_id in warning.get("candidate_pack_ids", [])
            if isinstance(pack_id, str)
        )
    )
    codes = ", ".join(
        str(warning["code"]) for warning in conflicts
    )
    candidates = ", ".join(candidate_pack_ids) or "unresolved"
    raise MaestroError(
        "EXPERTISE_ROUTING_CONFLICT_HIGH_RISK",
        (
            "High-risk expertise routing stopped before assignments. "
            f"Conflicts: {codes}. Candidate Packs: {candidates}."
        ),
    )
