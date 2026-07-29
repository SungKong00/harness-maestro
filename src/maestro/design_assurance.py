from __future__ import annotations

import copy
import json
import re
import zlib
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import MaestroError
from .expertise import load_expertise_catalog
from .research import require_completed_research_bundle
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    safe_target,
    sha256_text,
)


ASSURANCE_REQUIREMENT_VERSION = (
    "maestro_product_design_assurance_requirement_v1"
)
DESIGN_DECISION_PACKET_VERSION = (
    "maestro_product_design_decision_packet_v2"
)
DESIGN_ASSURANCE_PROFILE_ID = "product-design-evidence-v1"

ASSURANCE_MODES = {"compact", "standard", "system"}
CHANGE_KINDS = {"element", "component", "page", "flow", "system"}
SYSTEM_MODES = {"reuse", "extend", "establish"}
SYSTEM_STATUSES = {"existing", "partial", "absent"}
SYSTEM_ARTIFACT_ROLES = {
    "tokens",
    "components",
    "typography",
    "layout",
    "theme",
    "documentation",
}
SURFACE_IDS = (
    "outcome-content",
    "information-architecture-navigation",
    "typography-localization",
    "layout-spacing-responsive",
    "color-surface-theme",
    "shape-border-radius-elevation",
    "action-control-semantics",
    "forms-validation",
    "state-feedback-recovery",
    "data-display",
    "imagery-iconography",
    "motion",
    "token-component-governance",
    "rendered-verification",
)
PROPERTY_GROUPS = {
    "content",
    "hierarchy",
    "typography",
    "spacing",
    "color",
    "shape",
    "action",
    "input",
    "navigation",
    "data",
    "media",
    "state",
    "motion",
    "responsive",
    "localization",
}
AUTHORITY_CLASSES = {
    "standard",
    "project-system",
    "research",
    "owner-preference",
    "derived-local",
}
LINEAGE_KINDS = {
    "existing-token",
    "component-contract",
    "new-semantic-token",
    "new-component-contract",
    "derived-local-value",
    "owner-preference",
    "asset",
    "content-rule",
}
LINEAGE_PREFIXES = {
    "existing-token": "token:",
    "component-contract": "component:",
    "new-semantic-token": "token:",
    "new-component-contract": "component:",
    "derived-local-value": "measurement:",
    "owner-preference": "owner:",
    "asset": "asset:",
    "content-rule": "content-rule:",
}
BASIS_PREFIXES = {
    "project:",
    "convention:",
    "guide:",
    "research-claim:",
    "owner:",
    "measurement:",
}
COMPACT_ELIGIBILITY_FIELDS = {
    "semantic_role_unchanged",
    "interaction_contract_unchanged",
    "approved_tokens_only",
    "no_new_variant",
    "no_unresolved_accessibility_or_locale_risk",
    "affected_contexts_known",
}
SYSTEM_POLICY = {
    "token_model": "foundation-semantic-component-when-needed",
    "reuse_priority": "existing-token-component-before-extension",
    "raw_value_policy": "token-or-explicit-derived-exception",
    "component_lifecycle": "local-experimental-stable-deprecated",
}
SCENARIO_CHECKS = {
    "visual-hierarchy",
    "token-lineage",
    "content-fit",
    "responsive",
    "interaction",
    "keyboard-focus",
    "contrast",
    "localization",
    "overflow",
    "state-feedback",
    "visual-regression",
}
INPUT_METHODS = {"pointer", "keyboard", "touch", "screen-reader"}
_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_MAX_PACKET_ITEMS = 64
_MAX_LINE = 1_000
_MAX_RENDER_BYTES = 20 * 1024 * 1024
_MAX_RENDER_DECODED_BYTES = 128 * 1024 * 1024
_MAX_SYSTEM_SYMBOL_SOURCE_BYTES = 2 * 1024 * 1024


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _line(value: Any, maximum: int = _MAX_LINE) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and not any(character in value for character in "\r\n\x00")
        and "```" not in value
    )


def _id(value: Any) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _exact(
    value: Any,
    fields: set[str],
    path: str,
    issues: list[dict[str, str]],
) -> bool:
    if not isinstance(value, dict):
        issues.append(_issue("DESIGN_OBJECT_REQUIRED", path, "Expected an object."))
        return False
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing:
        issues.append(
            _issue(
                "DESIGN_FIELDS_MISSING",
                path,
                f"Missing fields: {', '.join(missing)}.",
            )
        )
    if unknown:
        issues.append(
            _issue(
                "DESIGN_FIELDS_UNKNOWN",
                path,
                f"Unsupported fields: {', '.join(unknown)}.",
            )
        )
    return not missing and not unknown


def _unique_lines(
    value: Any,
    *,
    maximum: int,
    nonempty: bool = False,
) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= maximum
        and (bool(value) or not nonempty)
        and all(_line(item) for item in value)
        and len(value) == len(set(value))
    )


def _relative_path(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
        or len(value) > 500
    ):
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and path.as_posix() not in {"", "."}
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _regular_file(repo: Path, relative_path: str) -> Path | None:
    if not _relative_path(relative_path):
        return None
    try:
        target = safe_target(repo, relative_path)
        if target.is_symlink() or not target.is_file():
            return None
    except (MaestroError, OSError):
        return None
    return target


def _route_hints(plan: Any) -> dict[str, Any] | None:
    expertise = plan.get("expertise") if isinstance(plan, dict) else None
    hints = (
        expertise.get("route_hints")
        if isinstance(expertise, dict)
        else None
    )
    return hints if isinstance(hints, dict) else None


def assurance_mode(plan: Any) -> str | None:
    hints = _route_hints(plan)
    mode = hints.get("design_assurance_mode") if hints is not None else None
    return (
        mode
        if isinstance(mode, str) and mode in ASSURANCE_MODES
        else None
    )


def product_design_assurance_active(plan: Any) -> bool:
    if not isinstance(plan, dict) or plan.get("intent") != "implementation":
        return False
    expertise = plan.get("expertise")
    hints = _route_hints(plan)
    selected_pack_ids = (
        expertise.get("selected_pack_ids")
        if isinstance(expertise, dict)
        else None
    )
    work_kinds = hints.get("work_kinds") if isinstance(hints, dict) else None
    mode = (
        hints.get("design_assurance_mode")
        if isinstance(hints, dict)
        else None
    )
    return (
        isinstance(selected_pack_ids, list)
        and all(isinstance(item, str) for item in selected_pack_ids)
        and "product-design" in selected_pack_ids
        and isinstance(work_kinds, list)
        and all(isinstance(item, str) for item in work_kinds)
        and "user-interface" in work_kinds
        and isinstance(mode, str)
        and mode in ASSURANCE_MODES
    )


def build_assurance_requirement(mode: str) -> dict[str, Any]:
    if not isinstance(mode, str) or mode not in ASSURANCE_MODES:
        raise MaestroError(
            "DESIGN_ASSURANCE_MODE_INVALID",
            "Design assurance mode must be compact, standard, or system.",
        )
    return {
        "schema_version": ASSURANCE_REQUIREMENT_VERSION,
        "profile_id": DESIGN_ASSURANCE_PROFILE_ID,
        "mode": mode,
        "activation": {
            "work_kind": "user-interface",
            "expertise_pack_id": "product-design",
        },
        "mutation_gate": "design-decision-packet",
        "verification_gate": "rendered-verification-pass",
    }


def validate_assurance_requirement(
    value: Any,
    *,
    plan: Any,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    active = product_design_assurance_active(plan)
    if not active:
        if value is not None:
            issues.append(
                _issue(
                    "DESIGN_ASSURANCE_UNEXPECTED",
                    "design_assurance",
                    "Design assurance is allowed only on explicitly classified Product Design implementation routes.",
                )
            )
        return issues
    mode = assurance_mode(plan)
    expected = build_assurance_requirement(str(mode))
    if value != expected:
        issues.append(
            _issue(
                "DESIGN_ASSURANCE_REQUIREMENT_MISMATCH",
                "design_assurance",
                "The Product Design assurance requirement must match the active structured UI route and mode exactly.",
            )
        )
    expertise = plan.get("expertise", {})
    requirement = (
        expertise.get("research_requirement")
        if isinstance(expertise, dict)
        else None
    )
    research_mode = (
        requirement.get("mode")
        if isinstance(requirement, dict)
        else None
    )
    if mode == "compact" and research_mode != "reuse":
        issues.append(
            _issue(
                "DESIGN_ASSURANCE_COMPACT_UNDERSCOPED",
                "design_assurance.mode",
                "Compact assurance is invalid when the selected design work already requires contextual or refreshed research.",
            )
        )
    if mode in {"standard", "system"} and research_mode not in {
        "contextualize",
        "refresh",
    }:
        issues.append(
            _issue(
                "DESIGN_ASSURANCE_RESEARCH_GATE_MISSING",
                "expertise.research_requirement.mode",
                "Standard and system Product Design work must open contextual or refreshed reference research.",
            )
        )
    return issues


def _packet_identity(packet: dict[str, Any]) -> str:
    payload = copy.deepcopy(packet)
    payload["packet_id"] = ""
    return sha256_text(canonical_json(payload))


def _product_design_guides(repo: Path) -> set[str]:
    guides: set[str] = set()
    try:
        catalog = load_expertise_catalog(repo, include_candidates=False)
    except (MaestroError, OSError, TypeError, ValueError):
        return guides
    for pack in catalog:
        if pack.get("expertise_pack_id") != "product-design":
            continue
        for guide in pack.get("guides", []):
            guide_id = guide.get("guide_id")
            if isinstance(guide_id, str):
                guides.add(guide_id)
    return guides


def _research_claim_ids(bundle: Any) -> set[str]:
    if not isinstance(bundle, dict):
        return set()
    return {
        claim["claim_id"]
        for packet in bundle.get("packets", [])
        if isinstance(packet, dict)
        for claim in packet.get("claims", [])
        if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)
    }


def _basis_ref_valid(
    value: Any,
    *,
    repo: Path,
    guide_ids: set[str],
    research_claim_ids: set[str],
) -> bool:
    if not _line(value):
        return False
    assert isinstance(value, str)
    prefix = next(
        (candidate for candidate in BASIS_PREFIXES if value.startswith(candidate)),
        None,
    )
    if prefix is None:
        return False
    suffix = value[len(prefix) :]
    if not suffix:
        return False
    if prefix in {
        "project:",
        "convention:",
        "owner:",
        "measurement:",
    }:
        marker = "#sha256="
        if marker not in suffix:
            return False
        relative_path, digest = suffix.rsplit(marker, 1)
        target = _regular_file(repo, relative_path)
        if (
            target is None
            or not _digest(digest)
            or file_sha256(target) != digest
        ):
            return False
        if prefix == "convention:" and not relative_path.startswith(
            "docs/conventions/"
        ):
            return False
        if prefix == "owner:" and not relative_path.startswith(
            "docs/decisions/"
        ):
            return False
        return True
    if prefix == "guide:":
        return suffix in guide_ids
    if prefix == "research-claim:":
        return suffix in research_claim_ids
    return True


def _compact_evidence_ref_valid(
    value: Any,
    *,
    repo: Path,
    guide_ids: set[str],
) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(
            (
                "project:",
                "convention:",
                "measurement:",
            )
        )
        and _basis_ref_valid(
            value,
            repo=repo,
            guide_ids=guide_ids,
            research_claim_ids=set(),
        )
    )


def _artifact_defines_inventory_ref(
    target: Path,
    ref: Any,
) -> bool:
    if not isinstance(ref, str) or ":" not in ref:
        return False
    symbol = ref.split(":", 1)[1]
    if (
        not _line(symbol, maximum=240)
        or any(character.isspace() for character in symbol)
    ):
        return False
    try:
        if target.stat().st_size > _MAX_SYSTEM_SYMBOL_SOURCE_BYTES:
            return False
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    if target.suffix.casefold() == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return False
        pending = [value]
        while pending:
            current = pending.pop()
            if isinstance(current, dict):
                if ref in current or current.get("ref") == ref:
                    return True
                pending.extend(current.values())
            elif isinstance(current, list):
                pending.extend(current)
        return False

    boundary = r"A-Za-z0-9_.-"
    return (
        re.search(
            rf"(?<![{boundary}]){re.escape(ref)}(?![{boundary}])",
            text,
        )
        is not None
    )


def _validate_system_context(
    value: Any,
    *,
    repo: Path,
    mode: str | None,
    issues: list[dict[str, str]],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, set[str]],
]:
    fields = {
        "status",
        "artifacts",
        "inventory",
        "token_model",
        "reuse_priority",
        "raw_value_policy",
        "component_lifecycle",
    }
    if not _exact(value, fields, "system_context", issues):
        return {}, {}
    if (
        not isinstance(value["status"], str)
        or value["status"] not in SYSTEM_STATUSES
    ):
        issues.append(
            _issue(
                "DESIGN_SYSTEM_STATUS_INVALID",
                "system_context.status",
                "Design-system status must be existing, partial, or absent.",
            )
        )
    for field, expected in SYSTEM_POLICY.items():
        if value.get(field) != expected:
            issues.append(
                _issue(
                    "DESIGN_SYSTEM_POLICY_MISMATCH",
                    f"system_context.{field}",
                    f"Expected the evidence-backed policy {expected}.",
                )
            )
    artifacts = value["artifacts"]
    if (
        not isinstance(artifacts, list)
        or len(artifacts) > 16
        or (
            isinstance(value["status"], str)
            and value["status"] in {"existing", "partial"}
            and not artifacts
        )
    ):
        issues.append(
            _issue(
                "DESIGN_SYSTEM_ARTIFACTS_INVALID",
                "system_context.artifacts",
                "Existing or partial systems require a bounded source artifact set.",
            )
        )
        artifacts = []
    seen: set[tuple[str, str]] = set()
    artifact_roles: dict[str, set[str]] = {}
    artifact_digests: dict[str, str] = {}
    artifact_refs_by_role: dict[str, set[str]] = {}
    for index, artifact in enumerate(artifacts):
        path = f"system_context.artifacts[{index}]"
        if (
            not isinstance(artifact, dict)
            or set(artifact) != {"path", "sha256", "role"}
            or not _relative_path(artifact.get("path"))
            or not _digest(artifact.get("sha256"))
            or not isinstance(artifact.get("role"), str)
            or artifact.get("role") not in SYSTEM_ARTIFACT_ROLES
            or (artifact.get("path"), artifact.get("role")) in seen
        ):
            issues.append(
                _issue(
                    "DESIGN_SYSTEM_ARTIFACT_INVALID",
                    path,
                    "System artifacts require a unique repository path, current digest, and closed role.",
                )
            )
            continue
        seen.add((artifact["path"], artifact["role"]))
        target = _regular_file(repo, artifact["path"])
        if target is None or file_sha256(target) != artifact["sha256"]:
            issues.append(
                _issue(
                    "DESIGN_SYSTEM_ARTIFACT_STALE",
                    path,
                    "System artifact path and digest must match the pre-mutation repository.",
                )
            )
            continue
        artifact_roles.setdefault(artifact["path"], set()).add(
            artifact["role"]
        )
        artifact_digests[artifact["path"]] = artifact["sha256"]
        artifact_refs_by_role.setdefault(artifact["role"], set()).add(
            "project:"
            f"{artifact['path']}#sha256={artifact['sha256']}"
        )
    inventory = value["inventory"]
    if (
        not isinstance(inventory, list)
        or len(inventory) > _MAX_PACKET_ITEMS
    ):
        issues.append(
            _issue(
                "DESIGN_SYSTEM_INVENTORY_INVALID",
                "system_context.inventory",
                "The referenced token/component inventory must be a bounded list.",
            )
        )
        inventory = []
    symbols: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(inventory):
        path = f"system_context.inventory[{index}]"
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "kind",
                "ref",
                "artifact_path",
                "artifact_sha256",
            }
        ):
            issues.append(
                _issue(
                    "DESIGN_SYSTEM_SYMBOL_INVALID",
                    path,
                    "Inventory entries require kind, symbol ref, and exact source artifact binding.",
                )
            )
            continue
        kind = item["kind"]
        ref = item["ref"]
        artifact_path = item["artifact_path"]
        expected_role = (
            "tokens"
            if kind == "token"
            else "components"
            if kind == "component"
            else None
        )
        expected_prefix = (
            "token:"
            if kind == "token"
            else "component:"
            if kind == "component"
            else None
        )
        if (
            expected_role is None
            or not _line(ref)
            or expected_prefix is None
            or not ref.startswith(expected_prefix)
            or ref in symbols
            or not _relative_path(artifact_path)
            or not _digest(item["artifact_sha256"])
            or item["artifact_sha256"]
            != artifact_digests.get(artifact_path)
            or expected_role not in artifact_roles.get(artifact_path, set())
        ):
            issues.append(
                _issue(
                    "DESIGN_SYSTEM_SYMBOL_INVALID",
                    path,
                    "Inventory symbols must resolve uniquely to a digest-bound token or component artifact.",
                )
            )
            continue
        target = _regular_file(repo, artifact_path)
        if (
            target is None
            or not _artifact_defines_inventory_ref(target, ref)
        ):
            issues.append(
                _issue(
                    "DESIGN_SYSTEM_SYMBOL_UNRESOLVED",
                    path,
                    "The canonical token or component ref must be explicitly declared in its exact digest-bound source artifact.",
                )
            )
            continue
        symbols[ref] = item
    if mode == "compact" and value["status"] != "existing":
        issues.append(
            _issue(
                "DESIGN_COMPACT_SYSTEM_REQUIRED",
                "system_context.status",
                "Compact assurance requires an existing design system to inherit.",
            )
        )
    if mode == "compact" and not {"tokens", "components"}.issubset(
        {
            role
            for roles in artifact_roles.values()
            for role in roles
        }
    ):
        issues.append(
            _issue(
                "DESIGN_COMPACT_SYSTEM_EVIDENCE_REQUIRED",
                "system_context.artifacts",
                "Compact reuse requires current digest-bound token and component artifacts.",
            )
        )
    if mode == "compact" and not {
        item.get("kind")
        for item in symbols.values()
    }.issuperset({"token", "component"}):
        issues.append(
            _issue(
                "DESIGN_COMPACT_INVENTORY_REQUIRED",
                "system_context.inventory",
                "Compact reuse requires referenced token and component symbols in the bound inventory.",
            )
        )
    return symbols, artifact_refs_by_role


def _validate_compact_eligibility(
    value: Any,
    *,
    mode: str | None,
    repo: Path,
    guide_ids: set[str],
    system_artifact_refs: dict[str, set[str]],
    issues: list[dict[str, str]],
) -> None:
    if not _exact(
        value,
        COMPACT_ELIGIBILITY_FIELDS,
        "compact_eligibility",
        issues,
    ):
        return
    for field in COMPACT_ELIGIBILITY_FIELDS:
        item = value[field]
        path = f"compact_eligibility.{field}"
        if not _exact(item, {"satisfied", "evidence_refs"}, path, issues):
            continue
        refs = item["evidence_refs"]
        if (
            not isinstance(item["satisfied"], bool)
            or not _unique_lines(refs, maximum=8, nonempty=True)
            or any(
                not _compact_evidence_ref_valid(
                    ref,
                    repo=repo,
                    guide_ids=guide_ids,
                )
                for ref in refs
            )
        ):
            issues.append(
                _issue(
                    "DESIGN_COMPACT_ELIGIBILITY_INVALID",
                    path,
                    "Every eligibility judgment requires a boolean and current content-addressed project, Convention, or measurement evidence.",
                )
            )
        if mode == "compact" and item["satisfied"] is not True:
            issues.append(
                _issue(
                    "DESIGN_COMPACT_ELIGIBILITY_FAILED",
                    path,
                    "Compact mode is allowed only when every reuse safety condition is evidenced true.",
                )
            )
        required_roles = {
            "semantic_role_unchanged": {"components"},
            "interaction_contract_unchanged": {"components"},
            "approved_tokens_only": {"tokens"},
            "no_new_variant": {"components"},
            "affected_contexts_known": set(
                SYSTEM_ARTIFACT_ROLES
            ),
        }.get(field)
        if mode == "compact" and required_roles is not None:
            required_refs = {
                ref
                for role in required_roles
                for ref in system_artifact_refs.get(role, set())
            }
            safe_refs = (
                set(refs)
                if isinstance(refs, list)
                and all(isinstance(ref, str) for ref in refs)
                else set()
            )
            if not safe_refs & required_refs:
                issues.append(
                    _issue(
                        "DESIGN_COMPACT_ELIGIBILITY_SYSTEM_EVIDENCE_REQUIRED",
                        path,
                        "This compact judgment must cite the exact current design-system artifact that owns it.",
                    )
                )


def _validate_scope(
    value: Any,
    *,
    mode: str | None,
    issues: list[dict[str, str]],
) -> None:
    if not _exact(
        value,
        {"change_kind", "target_refs", "system_mode"},
        "scope",
        issues,
    ):
        return
    change_kind = value["change_kind"]
    system_mode = value["system_mode"]
    if (
        not isinstance(change_kind, str)
        or change_kind not in CHANGE_KINDS
    ):
        issues.append(
            _issue(
                "DESIGN_CHANGE_KIND_INVALID",
                "scope.change_kind",
                "Unsupported Product Design change kind.",
            )
        )
    if not _unique_lines(value["target_refs"], maximum=32, nonempty=True):
        issues.append(
            _issue(
                "DESIGN_TARGET_REFS_INVALID",
                "scope.target_refs",
                "Design scope requires unique bounded target references.",
            )
        )
    if (
        not isinstance(system_mode, str)
        or system_mode not in SYSTEM_MODES
    ):
        issues.append(
            _issue(
                "DESIGN_SYSTEM_MODE_INVALID",
                "scope.system_mode",
                "System mode must be reuse, extend, or establish.",
            )
        )
    if mode == "compact" and (
        not isinstance(change_kind, str)
        or change_kind not in {"element", "component"}
        or system_mode != "reuse"
    ):
        issues.append(
            _issue(
                "DESIGN_COMPACT_SCOPE_INVALID",
                "scope",
                "Compact mode is limited to element or component work that reuses the existing system.",
            )
        )
    if mode == "standard" and system_mode == "establish":
        issues.append(
            _issue(
                "DESIGN_STANDARD_SCOPE_INVALID",
                "scope.system_mode",
                "Establishing a design system requires system assurance mode.",
            )
        )
    if mode == "system" and system_mode == "reuse":
        issues.append(
            _issue(
                "DESIGN_SYSTEM_SCOPE_INVALID",
                "scope.system_mode",
                "System assurance must extend or establish the design system.",
            )
        )


def _validate_research(
    value: Any,
    *,
    mode: str | None,
    plan: dict[str, Any],
    research_bundle: Any,
    repo: Path,
    issues: list[dict[str, str]],
) -> set[str]:
    fields = {"required", "reason_codes", "evidence_digest"}
    if not _exact(value, fields, "research", issues):
        return set()
    required = mode in {"standard", "system"}
    if value["required"] is not required:
        issues.append(
            _issue(
                "DESIGN_RESEARCH_REQUIREMENT_MISMATCH",
                "research.required",
                "Research is mandatory for standard and system modes and omitted only for eligible compact reuse.",
            )
        )
    if not _unique_lines(value["reason_codes"], maximum=16, nonempty=required):
        issues.append(
            _issue(
                "DESIGN_RESEARCH_REASONS_INVALID",
                "research.reason_codes",
                "Research reasons must be a bounded unique list and non-empty when research is required.",
            )
        )
    expertise = plan.get("expertise", {})
    route_requirement = (
        expertise.get("research_requirement")
        if isinstance(expertise, dict)
        else {}
    )
    expected_digest = (
        route_requirement.get("evidence_digest")
        if isinstance(route_requirement, dict)
        else None
    )
    if value["evidence_digest"] != expected_digest:
        issues.append(
            _issue(
                "DESIGN_RESEARCH_DIGEST_MISMATCH",
                "research.evidence_digest",
                "The decision Packet must bind the route's exact ResearchBundle digest.",
            )
        )
    if required:
        if (
            not isinstance(route_requirement, dict)
            or route_requirement.get("gate") != "satisfied"
            or research_bundle is None
        ):
            issues.append(
                _issue(
                    "DESIGN_RESEARCH_NOT_READY",
                    "research",
                    "Complete and bind the route's reference research before building a standard or system decision Packet.",
                )
            )
            return set()
        try:
            validation = require_completed_research_bundle(
                research_bundle,
                goal=plan.get("goal", ""),
                expertise=expertise,
                repo_path=repo,
            )
        except (MaestroError, OSError, TypeError, ValueError) as exc:
            issues.append(
                _issue(
                    "DESIGN_RESEARCH_INVALID",
                    "research",
                    str(exc),
                )
            )
            return set()
        if validation["artifact_digest"] != expected_digest:
            issues.append(
                _issue(
                    "DESIGN_RESEARCH_DIGEST_MISMATCH",
                    "research.evidence_digest",
                    "The supplied ResearchBundle does not match the satisfied route gate.",
                )
            )
            return set()
        return _research_claim_ids(research_bundle)
    if research_bundle is not None or value["evidence_digest"] is not None:
        issues.append(
            _issue(
                "DESIGN_RESEARCH_UNEXPECTED",
                "research",
                "Eligible compact reuse must not smuggle an unbound external research artifact into the Packet.",
            )
        )
    return set()


def _validate_render_path(value: Any, plan_id: str) -> bool:
    if not _relative_path(value):
        return False
    assert isinstance(value, str)
    return (
        value.startswith(f".maestro/state/design-assurance/{plan_id}/")
        and value.casefold().endswith(".png")
    )


def _validate_packet_body(
    packet: dict[str, Any],
    *,
    plan: dict[str, Any],
    repo: Path,
    research_bundle: Any,
    issues: list[dict[str, str]],
) -> None:
    mode = assurance_mode(plan)
    guide_ids = _product_design_guides(repo)
    _validate_scope(packet["scope"], mode=mode, issues=issues)
    system_symbols, system_artifact_refs = _validate_system_context(
        packet["system_context"],
        repo=repo,
        mode=mode,
        issues=issues,
    )
    _validate_compact_eligibility(
        packet["compact_eligibility"],
        mode=mode,
        repo=repo,
        guide_ids=guide_ids,
        system_artifact_refs=system_artifact_refs,
        issues=issues,
    )
    research_claim_ids = _validate_research(
        packet["research"],
        mode=mode,
        plan=plan,
        research_bundle=research_bundle,
        repo=repo,
        issues=issues,
    )
    decisions = packet["decisions"]
    if (
        not isinstance(decisions, list)
        or not decisions
        or len(decisions) > _MAX_PACKET_ITEMS
    ):
        issues.append(
            _issue(
                "DESIGN_DECISIONS_INVALID",
                "decisions",
                "A decision Packet requires 1-64 material decisions.",
            )
        )
        decisions = []
    if mode == "compact" and len(decisions) != 1:
        issues.append(
            _issue(
                "DESIGN_COMPACT_DECISION_COUNT_INVALID",
                "decisions",
                "Compact assurance is limited to exactly one bounded material decision.",
            )
        )
    decision_ids: set[str] = set()
    decision_scenarios: dict[str, set[str]] = {}
    research_decisions = 0
    decision_fields = {
        "decision_id",
        "target_ref",
        "property_group",
        "semantic_role",
        "authority_class",
        "basis_refs",
        "chosen_rule",
        "value_lineage",
        "affected_states",
        "verification_scenario_ids",
        "rationale",
    }
    for index, decision in enumerate(decisions):
        path = f"decisions[{index}]"
        if not _exact(decision, decision_fields, path, issues):
            continue
        decision_id = decision["decision_id"]
        if not _id(decision_id) or decision_id in decision_ids:
            issues.append(
                _issue(
                    "DESIGN_DECISION_ID_INVALID",
                    f"{path}.decision_id",
                    "Decision IDs must be unique kebab-case identifiers.",
                )
            )
        else:
            decision_ids.add(decision_id)
        if not _line(decision["target_ref"]):
            issues.append(
                _issue(
                    "DESIGN_DECISION_TARGET_INVALID",
                    f"{path}.target_ref",
                    "Each material decision requires a bounded target reference.",
                )
            )
        if (
            not isinstance(decision["property_group"], str)
            or decision["property_group"] not in PROPERTY_GROUPS
        ):
            issues.append(
                _issue(
                    "DESIGN_PROPERTY_GROUP_INVALID",
                    f"{path}.property_group",
                    "Decision property group is outside the closed design taxonomy.",
                )
            )
        if not _line(decision["semantic_role"]):
            issues.append(
                _issue(
                    "DESIGN_SEMANTIC_ROLE_REQUIRED",
                    f"{path}.semantic_role",
                    "Classify semantic role before choosing visual values.",
                )
            )
        authority = decision["authority_class"]
        if (
            not isinstance(authority, str)
            or authority not in AUTHORITY_CLASSES
        ):
            issues.append(
                _issue(
                    "DESIGN_AUTHORITY_INVALID",
                    f"{path}.authority_class",
                    "Decision authority is outside the closed evidence taxonomy.",
                )
            )
        basis_refs = decision["basis_refs"]
        if not _unique_lines(basis_refs, maximum=16, nonempty=True):
            issues.append(
                _issue(
                    "DESIGN_BASIS_REFS_INVALID",
                    f"{path}.basis_refs",
                    "Every material decision requires unique bounded basis references.",
                )
            )
            basis_refs = []
        invalid_basis = [
            ref
            for ref in basis_refs
            if not _basis_ref_valid(
                ref,
                repo=repo,
                guide_ids=guide_ids,
                research_claim_ids=research_claim_ids,
            )
        ]
        if invalid_basis:
            issues.append(
                _issue(
                    "DESIGN_BASIS_REF_UNRESOLVED",
                    f"{path}.basis_refs",
                    "Decision basis references must resolve to current project, Guide, research, owner, or measurement evidence.",
                )
            )
        authority_prefixes = {
            "standard": ("guide:", "research-claim:"),
            "project-system": ("project:", "convention:"),
            "research": ("research-claim:",),
            "owner-preference": ("owner:",),
            "derived-local": ("measurement:",),
        }
        required_prefixes = (
            authority_prefixes.get(authority)
            if isinstance(authority, str)
            else None
        )
        if required_prefixes is not None and not any(
            ref.startswith(required_prefixes) for ref in basis_refs
        ):
            issues.append(
                _issue(
                    "DESIGN_AUTHORITY_BASIS_MISMATCH",
                    f"{path}.basis_refs",
                    "The declared authority class requires a matching evidence lineage.",
                )
            )
        research_decisions += any(
            ref.startswith("research-claim:") for ref in basis_refs
        )
        if mode == "compact" and (
            authority != "project-system"
            or not any(
                ref.startswith(("project:", "convention:"))
                for ref in basis_refs
            )
        ):
            issues.append(
                _issue(
                    "DESIGN_COMPACT_AUTHORITY_INVALID",
                    path,
                    "Compact decisions must inherit a digest-bound project system authority.",
                )
            )
        if not _line(decision["chosen_rule"], 2_000) or not _line(
            decision["rationale"],
            2_000,
        ):
            issues.append(
                _issue(
                    "DESIGN_DECISION_REASON_INVALID",
                    path,
                    "Each material decision requires one bounded chosen rule and rationale.",
                )
            )
        lineage = decision["value_lineage"]
        if _exact(
            lineage,
            {"kind", "ref", "exception_reason"},
            f"{path}.value_lineage",
            issues,
        ):
            kind = lineage["kind"]
            expected_prefix = (
                LINEAGE_PREFIXES.get(kind)
                if isinstance(kind, str)
                else None
            )
            if (
                not isinstance(kind, str)
                or kind not in LINEAGE_KINDS
                or not _line(lineage["ref"])
                or expected_prefix is None
                or not lineage["ref"].startswith(expected_prefix)
            ):
                issues.append(
                    _issue(
                        "DESIGN_VALUE_LINEAGE_INVALID",
                        f"{path}.value_lineage",
                        "Visual values must inherit a token, component, measurement, owner, asset, or content-rule lineage.",
                    )
                )
            exception_required = isinstance(kind, str) and kind in {
                "new-semantic-token",
                "new-component-contract",
                "derived-local-value",
                "owner-preference",
            }
            exception_reason = lineage["exception_reason"]
            if exception_required and not _line(exception_reason, 2_000):
                issues.append(
                    _issue(
                        "DESIGN_VALUE_EXCEPTION_REQUIRED",
                        f"{path}.value_lineage.exception_reason",
                        "New, locally derived, or preference values require an explicit exception reason.",
                    )
                )
            if (
                isinstance(kind, str)
                and kind in {"existing-token", "component-contract"}
                and isinstance(lineage.get("ref"), str)
                and lineage.get("ref") not in system_symbols
            ):
                issues.append(
                    _issue(
                        "DESIGN_VALUE_SYMBOL_UNRESOLVED",
                        f"{path}.value_lineage.ref",
                        "Existing token and component lineages must resolve in the digest-bound system inventory.",
                    )
                )
            if (
                isinstance(kind, str)
                and kind in {"owner-preference", "derived-local-value"}
                and lineage.get("ref") not in basis_refs
            ):
                issues.append(
                    _issue(
                        "DESIGN_VALUE_AUTHORITY_UNRESOLVED",
                        f"{path}.value_lineage.ref",
                        "Owner and measured value lineages must equal a content-addressed decision basis.",
                    )
                )
            if mode == "compact" and (
                not isinstance(kind, str)
                or kind
                not in {
                    "existing-token",
                    "component-contract",
                }
            ):
                issues.append(
                    _issue(
                        "DESIGN_COMPACT_VALUE_LINEAGE_INVALID",
                        f"{path}.value_lineage.kind",
                        "Compact reuse may use only an existing token or existing component contract.",
                    )
                )
            if not exception_required and exception_reason is not None:
                issues.append(
                    _issue(
                        "DESIGN_VALUE_EXCEPTION_UNEXPECTED",
                        f"{path}.value_lineage.exception_reason",
                        "Inherited stable lineage does not carry an exception reason.",
                    )
                )
        if not _unique_lines(
            decision["affected_states"],
            maximum=16,
            nonempty=True,
        ):
            issues.append(
                _issue(
                    "DESIGN_AFFECTED_STATES_INVALID",
                    f"{path}.affected_states",
                    "Each decision must name its reachable affected states.",
                )
            )
        scenario_ids = decision["verification_scenario_ids"]
        if (
            not isinstance(scenario_ids, list)
            or not scenario_ids
            or len(scenario_ids) > 16
            or not all(_id(item) for item in scenario_ids)
            or len(scenario_ids) != len(set(scenario_ids))
        ):
            issues.append(
                _issue(
                    "DESIGN_DECISION_SCENARIOS_INVALID",
                    f"{path}.verification_scenario_ids",
                    "Every material decision must map to one or more unique render scenarios.",
                )
            )
            scenario_ids = []
        if _id(decision_id):
            decision_scenarios[decision_id] = set(scenario_ids)

    if mode in {"standard", "system"} and research_decisions < 1:
        issues.append(
            _issue(
                "DESIGN_RESEARCH_DECISION_REQUIRED",
                "decisions",
                "Standard and system work must apply at least one validated research claim to a material decision.",
            )
        )
    if mode == "compact" and (
        not isinstance(packet["verification_scenarios"], list)
        or len(packet["verification_scenarios"]) != 1
    ):
        issues.append(
            _issue(
                "DESIGN_COMPACT_SCENARIO_COUNT_INVALID",
                "verification_scenarios",
                "Compact assurance requires exactly one real consuming-context render scenario.",
            )
        )

    checks = packet["surface_checks"]
    if not isinstance(checks, list) or len(checks) != len(SURFACE_IDS):
        issues.append(
            _issue(
                "DESIGN_SURFACE_SCAN_INVALID",
                "surface_checks",
                "The complete 14-surface Product Design scan is required exactly once.",
            )
        )
        checks = []
    seen_surfaces: set[str] = set()
    covered_decisions: set[str] = set()
    for index, check in enumerate(checks):
        path = f"surface_checks[{index}]"
        if not _exact(
            check,
            {"surface_id", "status", "decision_ids", "reason", "evidence_refs"},
            path,
            issues,
        ):
            continue
        surface_id = check["surface_id"]
        if (
            not isinstance(surface_id, str)
            or surface_id not in SURFACE_IDS
            or surface_id in seen_surfaces
        ):
            issues.append(
                _issue(
                    "DESIGN_SURFACE_ID_INVALID",
                    f"{path}.surface_id",
                    "Surface IDs must cover the fixed Product Design scan exactly once.",
                )
            )
        else:
            seen_surfaces.add(surface_id)
        status = check["status"]
        ids = check["decision_ids"]
        if (
            not isinstance(status, str)
            or status not in {"covered", "not_applicable"}
            or not isinstance(ids, list)
            or len(ids) > _MAX_PACKET_ITEMS
            or not all(_id(item) for item in ids)
            or len(ids) != len(set(ids))
            or any(item not in decision_ids for item in ids)
            or (status == "covered" and not ids)
            or (status == "not_applicable" and ids)
        ):
            issues.append(
                _issue(
                    "DESIGN_SURFACE_DISPOSITION_INVALID",
                    path,
                    "Covered surfaces require material decision IDs; not-applicable surfaces require none.",
                )
            )
        else:
            covered_decisions.update(ids)
        if not _line(check["reason"], 2_000) or not _unique_lines(
            check["evidence_refs"],
            maximum=16,
            nonempty=True,
        ):
            issues.append(
                _issue(
                    "DESIGN_SURFACE_EVIDENCE_INVALID",
                    path,
                    "Every surface disposition requires a bounded reason and evidence reference.",
                )
            )
    if seen_surfaces != set(SURFACE_IDS):
        issues.append(
            _issue(
                "DESIGN_SURFACE_SET_MISMATCH",
                "surface_checks",
                "The surface scan must cover every required Product Design surface exactly once.",
            )
        )
    if covered_decisions != decision_ids:
        issues.append(
            _issue(
                "DESIGN_DECISION_SURFACE_MISMATCH",
                "surface_checks",
                "Every material decision must be allocated to at least one applicable design surface.",
            )
        )

    scenarios = packet["verification_scenarios"]
    minimum_scenarios = {"compact": 1, "standard": 2, "system": 3}.get(mode, 1)
    if (
        not isinstance(scenarios, list)
        or len(scenarios) < minimum_scenarios
        or len(scenarios) > 32
    ):
        issues.append(
            _issue(
                "DESIGN_VERIFICATION_SCENARIOS_INVALID",
                "verification_scenarios",
                f"{mode or 'active'} mode requires {minimum_scenarios}-32 rendered scenarios.",
            )
        )
        scenarios = []
    scenario_ids: set[str] = set()
    scenario_fields = {
        "scenario_id",
        "target_ref",
        "states",
        "contexts",
        "viewport",
        "locale",
        "input_methods",
        "checks",
        "artifact_path",
    }
    for index, scenario in enumerate(scenarios):
        path = f"verification_scenarios[{index}]"
        if not _exact(scenario, scenario_fields, path, issues):
            continue
        scenario_id = scenario["scenario_id"]
        if not _id(scenario_id) or scenario_id in scenario_ids:
            issues.append(
                _issue(
                    "DESIGN_SCENARIO_ID_INVALID",
                    f"{path}.scenario_id",
                    "Scenario IDs must be unique kebab-case identifiers.",
                )
            )
        else:
            scenario_ids.add(scenario_id)
        if (
            not _line(scenario["target_ref"])
            or not _unique_lines(scenario["states"], maximum=16, nonempty=True)
            or not _unique_lines(scenario["contexts"], maximum=16, nonempty=True)
            or not _line(scenario["locale"], 80)
        ):
            issues.append(
                _issue(
                    "DESIGN_SCENARIO_CONTEXT_INVALID",
                    path,
                    "Rendered scenarios require target, reachable states, real contexts, and locale.",
                )
            )
        viewport = scenario["viewport"]
        if (
            not isinstance(viewport, dict)
            or set(viewport) != {"name", "width", "height"}
            or not isinstance(viewport.get("name"), str)
            or viewport.get("name") not in {"compact", "regular", "wide"}
            or not isinstance(viewport.get("width"), int)
            or isinstance(viewport.get("width"), bool)
            or not 240 <= viewport["width"] <= 7680
            or not isinstance(viewport.get("height"), int)
            or isinstance(viewport.get("height"), bool)
            or not 240 <= viewport["height"] <= 7680
        ):
            issues.append(
                _issue(
                    "DESIGN_SCENARIO_VIEWPORT_INVALID",
                    f"{path}.viewport",
                    "Viewport requires a named compact, regular, or wide bounded CSS-pixel size.",
                )
            )
        methods = scenario["input_methods"]
        if (
            not isinstance(methods, list)
            or not methods
            or not all(
                isinstance(item, str) and item in INPUT_METHODS
                for item in methods
            )
            or len(methods) != len(set(methods))
        ):
            issues.append(
                _issue(
                    "DESIGN_SCENARIO_INPUT_INVALID",
                    f"{path}.input_methods",
                    "Input methods must be a non-empty relevance-filtered set.",
                )
            )
        checks_applied = scenario["checks"]
        if (
            not isinstance(checks_applied, list)
            or not checks_applied
            or not all(
                isinstance(item, str) and item in SCENARIO_CHECKS
                for item in checks_applied
            )
            or len(checks_applied) != len(set(checks_applied))
        ):
            issues.append(
                _issue(
                    "DESIGN_SCENARIO_CHECKS_INVALID",
                    f"{path}.checks",
                    "Scenario checks must be a non-empty subset of the rendered design contract.",
                )
            )
        if not _validate_render_path(scenario["artifact_path"], plan["plan_id"]):
            issues.append(
                _issue(
                    "DESIGN_SCENARIO_ARTIFACT_PATH_INVALID",
                    f"{path}.artifact_path",
                    "Rendered evidence must be a PNG inside this plan's design-assurance state directory.",
                )
            )
    referenced_scenarios = {
        scenario_id
        for values in decision_scenarios.values()
        for scenario_id in values
    }
    if referenced_scenarios != scenario_ids:
        issues.append(
            _issue(
                "DESIGN_SCENARIO_SET_MISMATCH",
                "verification_scenarios",
                "Every declared scenario must verify a decision and every decision reference must resolve.",
            )
        )
    if packet["unresolved"] != []:
        issues.append(
            _issue(
                "DESIGN_DECISION_UNRESOLVED",
                "unresolved",
                "The mutation gate remains closed while any design question is unresolved.",
            )
        )


def validate_design_decision_packet(
    packet: Any,
    plan: dict[str, Any],
    *,
    repo_path: str | Path,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    issues = validate_assurance_requirement(
        plan.get("design_assurance") if isinstance(plan, dict) else None,
        plan=plan,
    )
    try:
        from .planning import validate_route_v2

        route_validation = validate_route_v2(
            plan,
            repo_path=repo,
            research_bundle=research_bundle,
        )
    except (MaestroError, OSError, TypeError, ValueError):
        route_validation = {
            "status": "FAIL",
            "execution_status": "INVALID",
        }
    if (
        route_validation.get("status") != "PASS"
        or route_validation.get("execution_status") != "READY"
    ):
        issues.append(
            _issue(
                "DESIGN_BOUND_PLAN_NOT_READY",
                "plan_id",
                "A Design Decision Packet requires the exact validated READY route and its bound research evidence.",
            )
        )
    fields = {
        "schema_version",
        "packet_id",
        "plan_id",
        "goal_digest",
        "expertise_pack_id",
        "pack_definition_digest",
        "assurance",
        "scope",
        "system_context",
        "compact_eligibility",
        "research",
        "surface_checks",
        "decisions",
        "verification_scenarios",
        "unresolved",
        "writes_performed",
    }
    if not _exact(packet, fields, "$", issues):
        return {
            "schema_version": "maestro_design_assurance_validation_v1",
            "status": "FAIL",
            "execution_status": "INVALID",
            "packet_id": packet.get("packet_id") if isinstance(packet, dict) else None,
            "issues": sorted(
                issues,
                key=lambda item: (item["code"], item["path"], item["message"]),
            ),
            "writes_performed": False,
        }
    assert isinstance(packet, dict)
    if packet["schema_version"] != DESIGN_DECISION_PACKET_VERSION:
        issues.append(
            _issue(
                "DESIGN_PACKET_VERSION_INVALID",
                "schema_version",
                f"Expected {DESIGN_DECISION_PACKET_VERSION}.",
            )
        )
    if packet["plan_id"] != plan.get("plan_id"):
        issues.append(
            _issue(
                "DESIGN_PACKET_PLAN_MISMATCH",
                "plan_id",
                "The decision Packet must bind the exact route plan.",
            )
        )
    if packet["goal_digest"] != sha256_text(plan.get("goal", "")):
        issues.append(
            _issue(
                "DESIGN_PACKET_GOAL_MISMATCH",
                "goal_digest",
                "The decision Packet goal digest changed.",
            )
        )
    expertise = plan.get("expertise", {})
    expected_pack_digest = (
        expertise.get("pack_definition_digests", {}).get("product-design")
        if isinstance(expertise, dict)
        else None
    )
    if (
        packet["expertise_pack_id"] != "product-design"
        or packet["pack_definition_digest"] != expected_pack_digest
    ):
        issues.append(
            _issue(
                "DESIGN_PACKET_PACK_MISMATCH",
                "pack_definition_digest",
                "The decision Packet must bind the selected Product Design Pack definition.",
            )
        )
    if packet["assurance"] != plan.get("design_assurance"):
        issues.append(
            _issue(
                "DESIGN_PACKET_REQUIREMENT_MISMATCH",
                "assurance",
                "The decision Packet must preserve the exact route assurance requirement.",
            )
        )
    if not _digest(packet["packet_id"]) or packet["packet_id"] != _packet_identity(
        packet
    ):
        issues.append(
            _issue(
                "DESIGN_PACKET_ID_MISMATCH",
                "packet_id",
                "packet_id must be the canonical digest of the complete decision Packet.",
            )
        )
    if packet["writes_performed"] is not False:
        issues.append(
            _issue(
                "DESIGN_PACKET_WRITE_FORBIDDEN",
                "writes_performed",
                "Design analysis is read-only and must finish before mutation.",
            )
        )
    _validate_packet_body(
        packet,
        plan=plan,
        repo=repo,
        research_bundle=research_bundle,
        issues=issues,
    )
    issues.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return {
        "schema_version": "maestro_design_assurance_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "execution_status": "READY" if not issues else "INVALID",
        "packet_id": packet.get("packet_id"),
        "issues": issues,
        "writes_performed": False,
    }


def build_design_decision_packet(
    repo_path: str | Path,
    plan: dict[str, Any],
    draft: dict[str, Any],
    *,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(draft, dict):
        raise MaestroError(
            "DESIGN_DECISION_DRAFT_INVALID",
            "Design decision draft must be one object.",
        )
    expected_draft_fields = {
        "scope",
        "system_context",
        "compact_eligibility",
        "surface_checks",
        "decisions",
        "verification_scenarios",
        "unresolved",
    }
    if set(draft) != expected_draft_fields:
        raise MaestroError(
            "DESIGN_DECISION_DRAFT_INVALID",
            "Design decision draft fields are incomplete or unsupported.",
        )
    from .planning import validate_route_v2

    route_validation = validate_route_v2(
        plan,
        repo_path=repo_path,
        research_bundle=research_bundle,
    )
    if (
        route_validation["status"] != "PASS"
        or route_validation["execution_status"] != "READY"
    ):
        raise MaestroError(
            "DESIGN_BOUND_PLAN_NOT_READY",
            "Build the Design Decision Packet only from the exact validated READY route and its bound research evidence.",
        )
    requirement_issues = validate_assurance_requirement(
        plan.get("design_assurance"),
        plan=plan,
    )
    if requirement_issues:
        first = requirement_issues[0]
        raise MaestroError(first["code"], first["message"])
    expertise = plan["expertise"]
    research_requirement = expertise["research_requirement"]
    mode = assurance_mode(plan)
    packet = {
        "schema_version": DESIGN_DECISION_PACKET_VERSION,
        "packet_id": "",
        "plan_id": plan["plan_id"],
        "goal_digest": sha256_text(plan["goal"]),
        "expertise_pack_id": "product-design",
        "pack_definition_digest": expertise["pack_definition_digests"][
            "product-design"
        ],
        "assurance": copy.deepcopy(plan["design_assurance"]),
        "scope": copy.deepcopy(draft["scope"]),
        "system_context": copy.deepcopy(draft["system_context"]),
        "compact_eligibility": copy.deepcopy(
            draft["compact_eligibility"]
        ),
        "research": {
            "required": mode in {"standard", "system"},
            "reason_codes": list(research_requirement["reasons"]),
            "evidence_digest": research_requirement["evidence_digest"],
        },
        "surface_checks": copy.deepcopy(draft["surface_checks"]),
        "decisions": copy.deepcopy(draft["decisions"]),
        "verification_scenarios": copy.deepcopy(
            draft["verification_scenarios"]
        ),
        "unresolved": copy.deepcopy(draft["unresolved"]),
        "writes_performed": False,
    }
    packet["packet_id"] = _packet_identity(packet)
    validation = validate_design_decision_packet(
        packet,
        plan,
        repo_path=repo_path,
        research_bundle=research_bundle,
    )
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    return packet


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    """Decode the bounded PNG wire contract used for rendered evidence.

    Browser captures are restricted to non-interlaced 8-bit grayscale, RGB,
    grayscale-alpha, or RGBA PNGs. Valid chunk CRCs, a complete zlib stream,
    exact scanline length, and legal filter bytes are all required.
    """

    if len(data) < 45 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    width = height = color_type = None
    idat_parts: list[bytes] = []
    seen_ihdr = False
    seen_idat = False
    idat_closed = False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if (
            end > len(data)
            or len(chunk_type) != 4
            or not all(
                65 <= item <= 90 or 97 <= item <= 122
                for item in chunk_type
            )
        ):
            return None
        payload = data[offset + 8 : offset + 8 + length]
        recorded_crc = int.from_bytes(
            data[offset + 8 + length : end],
            "big",
        )
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != recorded_crc:
            return None
        if not seen_ihdr:
            if chunk_type != b"IHDR" or length != 13:
                return None
            width = int.from_bytes(payload[0:4], "big")
            height = int.from_bytes(payload[4:8], "big")
            color_type = payload[9]
            if (
                not 1 <= width <= 7680
                or not 1 <= height <= 7680
                or payload[8] != 8
                or color_type not in {0, 2, 4, 6}
                or payload[10:13] != b"\x00\x00\x00"
            ):
                return None
            seen_ihdr = True
        elif chunk_type == b"IHDR":
            return None
        elif chunk_type == b"IDAT":
            if idat_closed or not payload:
                return None
            seen_idat = True
            idat_parts.append(payload)
        elif chunk_type == b"PLTE":
            if seen_idat or length < 3 or length > 768 or length % 3:
                return None
        elif chunk_type == b"IEND":
            if length != 0 or end != len(data) or not seen_idat:
                return None
            assert isinstance(width, int)
            assert isinstance(height, int)
            assert isinstance(color_type, int)
            channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
            row_bytes = width * channels
            expected_size = height * (row_bytes + 1)
            if expected_size > _MAX_RENDER_DECODED_BYTES:
                return None
            try:
                compressed = b"".join(idat_parts)
                decoder = zlib.decompressobj()
                decoded = decoder.decompress(
                    compressed,
                    expected_size + 1,
                )
            except zlib.error:
                return None
            if (
                len(decoded) != expected_size
                or not decoder.eof
                or decoder.unused_data
                or decoder.unconsumed_tail
                or any(
                    decoded[row_offset] > 4
                    for row_offset in range(
                        0,
                        expected_size,
                        row_bytes + 1,
                    )
                )
            ):
                return None
            return width, height
        elif chunk_type[:1].isupper():
            return None
        elif seen_idat:
            idat_closed = True
        offset = end
    return None


def _render_file(
    repo: Path,
    relative_path: Any,
    expected_digest: Any,
    *,
    expected_width: Any,
    expected_height: Any,
) -> bool:
    if (
        not _relative_path(relative_path)
        or not isinstance(relative_path, str)
        or not relative_path.casefold().endswith(".png")
        or not _digest(expected_digest)
        or not isinstance(expected_width, int)
        or isinstance(expected_width, bool)
        or not isinstance(expected_height, int)
        or isinstance(expected_height, bool)
    ):
        return False
    target = _regular_file(repo, relative_path)
    if target is None:
        return False
    try:
        size = target.stat().st_size
        if size <= 0 or size > _MAX_RENDER_BYTES:
            return False
        data = target.read_bytes()
    except OSError:
        return False
    return (
        _png_dimensions(data) == (expected_width, expected_height)
        and file_sha256(target) == expected_digest
    )


def validate_design_assurance_result(
    value: Any,
    *,
    decision_packet: dict[str, Any],
    repo_path: str | Path,
    completed: bool,
) -> list[dict[str, str]]:
    repo = ensure_repo(repo_path)
    issues: list[dict[str, str]] = []
    fields = {
        "decision_packet_id",
        "decision_dispositions",
        "rendered_artifacts",
        "unresolved",
    }
    if not _exact(value, fields, "design_assurance_result", issues):
        return issues
    assert isinstance(value, dict)
    if value["decision_packet_id"] != decision_packet.get("packet_id"):
        issues.append(
            _issue(
                "DESIGN_RESULT_PACKET_MISMATCH",
                "design_assurance_result.decision_packet_id",
                "Implementation results must bind the projected decision Packet.",
            )
        )
    expected_decisions = {
        item["decision_id"]
        for item in decision_packet.get("decisions", [])
        if isinstance(item, dict) and isinstance(item.get("decision_id"), str)
    }
    dispositions = value["decision_dispositions"]
    seen_decisions: set[str] = set()
    conflicts = False
    if not isinstance(dispositions, list) or len(dispositions) != len(
        expected_decisions
    ):
        issues.append(
            _issue(
                "DESIGN_RESULT_DECISIONS_INVALID",
                "design_assurance_result.decision_dispositions",
                "Implementation must report the exact material decision set.",
            )
        )
        dispositions = []
    for index, disposition in enumerate(dispositions):
        path = f"design_assurance_result.decision_dispositions[{index}]"
        if not _exact(
            disposition,
            {
                "decision_id",
                "disposition",
                "implementation_refs",
                "evidence_refs",
                "reason",
            },
            path,
            issues,
        ):
            continue
        decision_id = disposition["decision_id"]
        if (
            not isinstance(decision_id, str)
            or decision_id not in expected_decisions
            or decision_id in seen_decisions
        ):
            issues.append(
                _issue(
                    "DESIGN_RESULT_DECISION_MISMATCH",
                    f"{path}.decision_id",
                    "Decision disposition is duplicated or outside the projected set.",
                )
            )
        if isinstance(decision_id, str):
            seen_decisions.add(decision_id)
        if (
            not isinstance(disposition["disposition"], str)
            or disposition["disposition"] not in {"applied", "conflict"}
        ):
            issues.append(
                _issue(
                    "DESIGN_RESULT_DISPOSITION_INVALID",
                    f"{path}.disposition",
                    "Decision disposition must be applied or conflict.",
                )
            )
        conflicts = conflicts or disposition["disposition"] == "conflict"
        refs = disposition["implementation_refs"]
        if not _unique_lines(refs, maximum=16, nonempty=True) or any(
            _regular_file(repo, ref.split("#", 1)[0]) is None
            for ref in refs
        ):
            issues.append(
                _issue(
                    "DESIGN_RESULT_IMPLEMENTATION_REF_INVALID",
                    f"{path}.implementation_refs",
                    "Applied decisions require existing repository implementation references.",
                )
            )
        if not _unique_lines(
            disposition["evidence_refs"],
            maximum=16,
            nonempty=True,
        ) or not _line(disposition["reason"], 2_000):
            issues.append(
                _issue(
                    "DESIGN_RESULT_EVIDENCE_INVALID",
                    path,
                    "Each disposition requires bounded evidence and a reason.",
                )
            )
    if seen_decisions != expected_decisions:
        issues.append(
            _issue(
                "DESIGN_RESULT_DECISION_SET_MISMATCH",
                "design_assurance_result.decision_dispositions",
                "Implementation dispositions do not cover the exact decision set.",
            )
        )
    expected_scenarios = {
        item["scenario_id"]: item
        for item in decision_packet.get("verification_scenarios", [])
        if isinstance(item, dict) and isinstance(item.get("scenario_id"), str)
    }
    artifacts = value["rendered_artifacts"]
    seen_scenarios: set[str] = set()
    if not isinstance(artifacts, list) or len(artifacts) != len(
        expected_scenarios
    ):
        issues.append(
            _issue(
                "DESIGN_RESULT_RENDER_SET_INVALID",
                "design_assurance_result.rendered_artifacts",
                "Implementation must render the exact declared scenario set.",
            )
        )
        artifacts = []
    for index, artifact in enumerate(artifacts):
        path = f"design_assurance_result.rendered_artifacts[{index}]"
        if not _exact(
            artifact,
            {"scenario_id", "artifact_path", "sha256"},
            path,
            issues,
        ):
            continue
        artifact_scenario_id = artifact["scenario_id"]
        scenario = (
            expected_scenarios.get(artifact_scenario_id)
            if isinstance(artifact_scenario_id, str)
            else None
        )
        viewport = (
            scenario.get("viewport")
            if isinstance(scenario, dict)
            else None
        )
        if (
            scenario is None
            or not isinstance(viewport, dict)
            or artifact_scenario_id in seen_scenarios
            or artifact["artifact_path"] != scenario.get("artifact_path")
            or not _render_file(
                repo,
                artifact["artifact_path"],
                artifact["sha256"],
                expected_width=viewport.get("width"),
                expected_height=viewport.get("height"),
            )
        ):
            issues.append(
                _issue(
                    "DESIGN_RESULT_RENDER_INVALID",
                    path,
                    "Rendered evidence must match the declared scenario path, image type, current file, and digest.",
                )
            )
        if isinstance(artifact_scenario_id, str):
            seen_scenarios.add(artifact_scenario_id)
    if seen_scenarios != set(expected_scenarios):
        issues.append(
            _issue(
                "DESIGN_RESULT_RENDER_SET_MISMATCH",
                "design_assurance_result.rendered_artifacts",
                "Rendered artifacts do not cover the exact scenario set.",
            )
        )
    if (
        not isinstance(value["unresolved"], list)
        or len(value["unresolved"]) > 16
        or not all(_line(item) for item in value["unresolved"])
        or len(value["unresolved"]) != len(set(value["unresolved"]))
        or (completed and value["unresolved"])
    ):
        issues.append(
            _issue(
                "DESIGN_RESULT_UNRESOLVED",
                "design_assurance_result.unresolved",
                "A completed design implementation cannot retain unresolved decisions.",
            )
        )
    if completed and conflicts:
        issues.append(
            _issue(
                "DESIGN_RESULT_CONFLICT",
                "design_assurance_result.decision_dispositions",
                "A writer cannot complete with a design decision conflict.",
            )
        )
    return issues


def design_result_digest(value: Any) -> str:
    return sha256_text(canonical_json(value))


def validate_design_verification(
    value: Any,
    *,
    decision_packet: dict[str, Any],
    implementation_result: dict[str, Any],
    repo_path: str | Path,
    overall_verdict: Any,
) -> list[dict[str, str]]:
    repo = ensure_repo(repo_path)
    issues: list[dict[str, str]] = []
    if not _exact(
        value,
        {
            "decision_packet_id",
            "implementation_result_digest",
            "scenario_results",
        },
        "design_verification",
        issues,
    ):
        return issues
    assert isinstance(value, dict)
    if value["decision_packet_id"] != decision_packet.get("packet_id"):
        issues.append(
            _issue(
                "DESIGN_VERIFICATION_PACKET_MISMATCH",
                "design_verification.decision_packet_id",
                "Verification must bind the exact decision Packet.",
            )
        )
    expected_result_digest = design_result_digest(implementation_result)
    if value["implementation_result_digest"] != expected_result_digest:
        issues.append(
            _issue(
                "DESIGN_VERIFICATION_RESULT_MISMATCH",
                "design_verification.implementation_result_digest",
                "Verification must bind the exact implementation design result.",
            )
        )
    scenario_contracts = {
        item["scenario_id"]: item
        for item in decision_packet.get("verification_scenarios", [])
        if isinstance(item, dict) and isinstance(item.get("scenario_id"), str)
    }
    rendered = {
        item["scenario_id"]: item
        for item in implementation_result.get("rendered_artifacts", [])
        if isinstance(item, dict) and isinstance(item.get("scenario_id"), str)
    }
    results = value["scenario_results"]
    seen: set[str] = set()
    all_passed = True
    if not isinstance(results, list) or len(results) != len(scenario_contracts):
        issues.append(
            _issue(
                "DESIGN_VERIFICATION_SET_INVALID",
                "design_verification.scenario_results",
                "Verifier results must cover the exact rendered scenario set.",
            )
        )
        results = []
    for index, result in enumerate(results):
        path = f"design_verification.scenario_results[{index}]"
        if not _exact(
            result,
            {
                "scenario_id",
                "verdict",
                "artifact_path",
                "artifact_sha256",
                "checks_applied",
                "summary",
            },
            path,
            issues,
        ):
            continue
        scenario_id = result["scenario_id"]
        scenario = (
            scenario_contracts.get(scenario_id)
            if isinstance(scenario_id, str)
            else None
        )
        artifact = (
            rendered.get(scenario_id)
            if isinstance(scenario_id, str)
            else None
        )
        if (
            scenario is None
            or artifact is None
            or scenario_id in seen
        ):
            issues.append(
                _issue(
                    "DESIGN_VERIFICATION_SCENARIO_MISMATCH",
                    f"{path}.scenario_id",
                    "Scenario result is duplicated or outside the implemented set.",
                )
            )
            continue
        seen.add(scenario_id)
        verdict = result["verdict"]
        if (
            not isinstance(verdict, str)
            or verdict not in {"passed", "failed", "inconclusive"}
        ):
            issues.append(
                _issue(
                    "DESIGN_VERIFICATION_VERDICT_INVALID",
                    f"{path}.verdict",
                    "Scenario verdict must be passed, failed, or inconclusive.",
                )
            )
        all_passed = all_passed and verdict == "passed"
        viewport = scenario.get("viewport")
        if (
            not isinstance(viewport, dict)
            or result["artifact_path"] != artifact.get("artifact_path")
            or result["artifact_sha256"] != artifact.get("sha256")
            or not _render_file(
                repo,
                result["artifact_path"],
                result["artifact_sha256"],
                expected_width=(
                    viewport.get("width")
                    if isinstance(viewport, dict)
                    else None
                ),
                expected_height=(
                    viewport.get("height")
                    if isinstance(viewport, dict)
                    else None
                ),
            )
        ):
            issues.append(
                _issue(
                    "DESIGN_VERIFICATION_ARTIFACT_INVALID",
                    path,
                    "Verifier evidence must match the writer's unchanged rendered artifact.",
                )
            )
        if result["checks_applied"] != scenario.get("checks"):
            issues.append(
                _issue(
                    "DESIGN_VERIFICATION_CHECKS_MISMATCH",
                    f"{path}.checks_applied",
                    "Verifier checks must exactly replay the declared scenario contract.",
                )
            )
        if not _line(result["summary"], 2_000):
            issues.append(
                _issue(
                    "DESIGN_VERIFICATION_SUMMARY_INVALID",
                    f"{path}.summary",
                    "Each scenario requires a bounded observed verification summary.",
                )
            )
    if seen != set(scenario_contracts):
        issues.append(
            _issue(
                "DESIGN_VERIFICATION_SET_MISMATCH",
                "design_verification.scenario_results",
                "Verification did not cover the exact scenario set.",
            )
        )
    if (overall_verdict == "passed") != all_passed:
        issues.append(
            _issue(
                "DESIGN_VERIFICATION_OVERALL_MISMATCH",
                "verdict",
                "The overall verifier verdict may pass only when every design scenario passes.",
            )
        )
    return issues
