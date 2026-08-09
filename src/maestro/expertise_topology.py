from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .expertise import (
    expertise_manifest_digest,
    load_expertise_catalog,
)
from .util import (
    canonical_json,
    ensure_repo,
    read_json,
    safe_target,
    sha256_bytes,
    sha256_text,
)

CHANGE_SET_MANIFEST_VERSION = "maestro_expertise_change_set_manifest_v1"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
COMPLEX_KINDS = {
    "pack-merge",
    "pack-extraction",
    "pack-split",
    "guide-move",
    "guide-copy",
}
ROLES_BY_KIND = {
    "pack-merge": {"result"},
    "pack-extraction": {"result"},
    "pack-split": {"source", "target"},
    "guide-move": {"source", "target"},
    "guide-copy": {"target"},
}
RETIREMENT_BY_KIND = {
    "pack-merge": "deferred-owner-action",
    "pack-extraction": "not-applicable",
    "pack-split": "represented-by-members",
    "guide-move": "represented-by-members",
    "guide-copy": "not-applicable",
}
MANIFEST_FIELDS = {
    "schema_version",
    "change_set_id",
    "operation",
    "coverage_id",
    "adaptation_plan_id",
    "members",
    "sources",
    "guide_mappings",
    "default_guides",
    "source_retirement",
    "rollback_summary",
}
MEMBER_FIELDS = {
    "candidate_id",
    "operation_id",
    "role",
    "candidate_digest",
}
SOURCE_FIELDS = {
    "pack_id",
    "definition_digest",
}
MAPPING_FIELDS = {
    "guide_id",
    "source_pack_id",
    "target_pack_ids",
    "mode",
}
DEFAULT_GUIDES_FIELDS = {
    "pack_id",
    "guide_ids",
}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _unique_ids(
    value: Any,
    *,
    minimum: int = 0,
    maximum: int,
) -> bool:
    return (
        isinstance(value, list)
        and minimum <= len(value) <= maximum
        and all(
            isinstance(item, str)
            and ID_PATTERN.fullmatch(item) is not None
            for item in value
        )
        and len(value) == len(set(value))
    )


def _raw_candidate(
    repo: Path,
    candidate_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    root = safe_target(
        repo,
        f".maestro/state/candidates/expertise/{candidate_id}",
    )
    candidate_path = safe_target(root, "candidate.json")
    pack_path = safe_target(root, "draft/maestro-pack.json")
    if (
        root.is_symlink()
        or not root.is_dir()
        or candidate_path.is_symlink()
        or not candidate_path.is_file()
        or pack_path.is_symlink()
        or not pack_path.is_file()
    ):
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_MEMBER_MISSING",
            f"ChangeSet member is missing or unsafe: {candidate_id}",
        )
    return root, read_json(candidate_path), read_json(pack_path)


def expertise_candidate_content_digest(root: Path) -> str:
    """Digest one candidate tree without mutable lifecycle markers."""

    files: list[dict[str, str]] = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise MaestroError(
                "EXPERTISE_CANDIDATE_SYMLINK_UNSAFE",
                f"Candidate contains a symlink: {path.relative_to(root)}",
            )
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {"disposition.json", "promotion-decision.json"}:
            continue
        size = path.stat().st_size
        total_bytes += size
        if size > 2_000_000 or total_bytes > 2_000_000 or len(files) >= 200:
            raise MaestroError(
                "EXPERTISE_CANDIDATE_TOO_LARGE",
                "Candidate files exceed the bounded ChangeSet digest limit.",
            )
        files.append(
            {
                "path": relative,
                "sha256": sha256_bytes(path.read_bytes()),
            }
        )
    if not files:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_EMPTY",
            "Candidate has no regular files.",
        )
    return sha256_text(canonical_json(files))


def _active_packs(repo: Path) -> dict[str, dict[str, Any]]:
    return {
        pack["expertise_pack_id"]: pack
        for pack in load_expertise_catalog(
            repo,
            include_candidates=False,
        )
    }


def _guide_map(pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        guide["guide_id"]: {
            key: copy.deepcopy(value)
            for key, value in guide.items()
        }
        for guide in pack.get("guides", [])
        if isinstance(guide, dict)
        and isinstance(guide.get("guide_id"), str)
    }


def _default_guides(pack: dict[str, Any] | None) -> list[str]:
    if not isinstance(pack, dict):
        return []
    value = pack.get("default_guides", [])
    return list(value) if isinstance(value, list) else []


def _stable_pack_fields(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(pack.get(key))
        for key in (
            "summary",
            "triggers",
            "dominance_triggers",
            "skill_id",
            "research_policy",
            "extends",
        )
    }


def _active_guide_digest(
    repo: Path,
    pack: dict[str, Any],
    guide_id: str,
) -> str | None:
    metadata = pack.get("_maestro", {})
    origin = metadata.get("guide_origins", {}).get(guide_id, {})
    skill_id = origin.get("skill_id") or pack.get("skill_id")
    if not isinstance(skill_id, str):
        return None
    candidates = [
        safe_target(
            repo,
            f".agents/skills/{skill_id}/references/{guide_id}.md",
        ),
        (
            Path(__file__).resolve().parents[2]
            / "skills"
            / skill_id
            / "references"
            / f"{guide_id}.md"
        ),
    ]
    for path in candidates:
        if path.is_file() and not path.is_symlink():
            return sha256_bytes(path.read_bytes())
    return None


def _candidate_guide_digest(
    root: Path,
    guide_id: str,
) -> str | None:
    path = safe_target(root, f"draft/references/{guide_id}.md")
    if path.is_file() and not path.is_symlink():
        return sha256_bytes(path.read_bytes())
    return None


def _unchanged_guide_body_issues(
    repo: Path,
    *,
    candidate_root: Path,
    predecessor: dict[str, Any],
    guide_ids: set[str],
    path: str,
) -> list[dict[str, str]]:
    drifted = sorted(
        guide_id
        for guide_id in guide_ids
        if _active_guide_digest(repo, predecessor, guide_id)
        != _candidate_guide_digest(candidate_root, guide_id)
    )
    if not drifted:
        return []
    return [
        _issue(
            "EXPERTISE_GUIDE_BODY_UNDECLARED_DRIFT",
            path,
            "Unrelated Guide reference bodies changed: "
            + ", ".join(drifted),
        )
    ]


def validate_candidate_change_semantics(
    repo_path: str | Path,
    candidate: dict[str, Any],
    pack: dict[str, Any],
) -> list[dict[str, str]]:
    """Check single-Pack Guide revisions against the current predecessor."""

    generation = candidate.get("generation")
    if (
        not isinstance(generation, dict)
        or generation.get("mode") != "task-gap"
    ):
        return []
    change = candidate.get("component_change")
    kind = change.get("kind") if isinstance(change, dict) else None
    if kind not in {
        "guide-addition",
        "guide-revision",
        "guide-deprecation",
    }:
        return []
    repo = ensure_repo(repo_path)
    base = _active_packs(repo).get(candidate.get("expertise_pack_id"))
    target_guide_id = change.get("target_guide_id")
    if base is None:
        return [
            _issue(
                "EXPERTISE_GUIDE_CHANGE_BASE_MISSING",
                "candidate.json.component_change",
                "Guide revision or deprecation requires one current Pack predecessor.",
            )
        ]
    base_guides = _guide_map(base)
    candidate_guides = _guide_map(pack)
    issues: list[dict[str, str]] = []
    if (
        kind != "guide-addition"
        and target_guide_id not in base_guides
    ):
        issues.append(
            _issue(
                "EXPERTISE_GUIDE_CHANGE_TARGET_MISSING",
                "candidate.json.component_change.target_guide_id",
                "The target Guide does not exist in the current Pack.",
            )
        )
        return issues
    if _stable_pack_fields(pack) != _stable_pack_fields(base):
        issues.append(
            _issue(
                "EXPERTISE_GUIDE_CHANGE_PACK_DRIFT",
                "draft/maestro-pack.json",
                "A Guide-only change cannot silently alter Pack routing fields.",
            )
        )
    if kind == "guide-addition":
        expected = set(base_guides) | {target_guide_id}
        if (
            target_guide_id in base_guides
            or target_guide_id not in candidate_guides
            or set(candidate_guides) != expected
        ):
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_ADDITION_SCOPE_INVALID",
                    "draft/maestro-pack.json.guides",
                    "Guide addition must add exactly the declared new Guide.",
                )
            )
        if pack.get("default_guides") != base.get("default_guides"):
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_ADDITION_DEFAULT_DRIFT",
                    "draft/maestro-pack.json.default_guides",
                    "Guide addition cannot silently change default Guide routing.",
                )
            )
        unchanged = set(base_guides)
    elif kind == "guide-revision":
        if set(candidate_guides) != set(base_guides):
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_REVISION_SCOPE_INVALID",
                    "draft/maestro-pack.json.guides",
                    "Guide revision must preserve the complete Guide ID set.",
                )
            )
        if pack.get("default_guides") != base.get("default_guides"):
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_REVISION_DEFAULT_DRIFT",
                    "draft/maestro-pack.json.default_guides",
                    "Guide revision cannot silently change default Guide routing.",
                )
            )
        if candidate_guides.get(target_guide_id) == base_guides[target_guide_id]:
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_REVISION_NO_CHANGE",
                    "draft/maestro-pack.json.guides",
                    "Guide revision must change the declared Guide.",
                )
            )
        unchanged = set(base_guides) - {target_guide_id}
    else:
        expected = set(base_guides) - {target_guide_id}
        if set(candidate_guides) != expected:
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_DEPRECATION_SCOPE_INVALID",
                    "draft/maestro-pack.json.guides",
                    "Guide deprecation must remove exactly the declared Guide.",
                )
            )
        expected_defaults = [
            guide_id
            for guide_id in base.get("default_guides", [])
            if guide_id != target_guide_id
        ]
        if pack.get("default_guides") != expected_defaults:
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_DEPRECATION_DEFAULT_INVALID",
                    "draft/maestro-pack.json.default_guides",
                    "Deprecated Guide must be removed from defaults without other drift.",
                )
            )
        unchanged = set(base_guides) - {target_guide_id}
    drifted = sorted(
        guide_id
        for guide_id in unchanged
        if candidate_guides.get(guide_id) != base_guides.get(guide_id)
    )
    if drifted:
        issues.append(
            _issue(
                "EXPERTISE_GUIDE_CHANGE_UNDECLARED_DRIFT",
                "draft/maestro-pack.json.guides",
                "Unrelated Guides changed: " + ", ".join(drifted),
            )
        )
    candidate_id = candidate.get("candidate_id")
    if (
        isinstance(candidate_id, str)
        and ID_PATTERN.fullmatch(candidate_id) is not None
    ):
        candidate_root = safe_target(
            repo,
            f".maestro/state/candidates/expertise/{candidate_id}",
        )
        if candidate_root.is_dir() and not candidate_root.is_symlink():
            issues.extend(
                _unchanged_guide_body_issues(
                    repo,
                    candidate_root=candidate_root,
                    predecessor=base,
                    guide_ids=unchanged,
                    path="draft/references",
                )
            )
    return issues


def _manifest_path(repo: Path, change_set_id: str) -> Path:
    return safe_target(
        repo,
        (
            ".maestro/state/candidates/expertise-change-sets/"
            f"{change_set_id}.json"
        ),
    )


def expertise_change_set_manifest_digest(
    repo_path: str | Path,
    change_set_id: str,
) -> str:
    repo = ensure_repo(repo_path)
    path = _manifest_path(repo, change_set_id)
    if path.is_symlink() or not path.is_file():
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_MANIFEST_MISSING",
            f"ChangeSet manifest is missing: {change_set_id}",
        )
    return sha256_bytes(path.read_bytes())


def _raw_group_members(repo: Path, change_set_id: str) -> list[str]:
    from .expertise_changes import candidate_change_set_groups

    return candidate_change_set_groups(repo).get(change_set_id, [])


def _candidate_lineage_ids(
    root: Path,
    candidate: dict[str, Any],
) -> tuple[str | None, str | None]:
    adaptation = candidate.get("adaptation")
    if not isinstance(adaptation, dict):
        return None, None
    try:
        coverage = read_json(
            safe_target(root, adaptation["coverage_ref"]["path"])
        )
        plan = read_json(
            safe_target(root, adaptation["plan_ref"]["path"])
        )
    except (KeyError, TypeError, MaestroError):
        return None, None
    return coverage.get("coverage_id"), plan.get("plan_id")


def _validate_manifest_shape(
    value: Any,
    change_set_id: str,
    issues: list[dict[str, str]],
) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != MANIFEST_FIELDS
        or value.get("schema_version") != CHANGE_SET_MANIFEST_VERSION
        or value.get("change_set_id") != change_set_id
        or value.get("operation") not in COMPLEX_KINDS
        or not isinstance(value.get("coverage_id"), str)
        or DIGEST_PATTERN.fullmatch(value["coverage_id"]) is None
        or not isinstance(value.get("adaptation_plan_id"), str)
        or DIGEST_PATTERN.fullmatch(value["adaptation_plan_id"]) is None
        or value.get("source_retirement")
        != RETIREMENT_BY_KIND.get(value.get("operation"))
        or not isinstance(value.get("rollback_summary"), str)
        or not value["rollback_summary"].strip()
        or len(value["rollback_summary"]) > 1000
    ):
        issues.append(
            _issue(
                "EXPERTISE_CHANGE_SET_MANIFEST_INVALID",
                "change-set-manifest",
                "Complex Expertise ChangeSet manifest fields are invalid.",
            )
        )
        return False
    return True


def validate_expertise_change_set_manifest(
    repo_path: str | Path,
    change_set_id: str,
    *,
    validate_members: bool = False,
) -> dict[str, Any]:
    """Validate explicit membership and before/after topology fail-closed."""

    repo = ensure_repo(repo_path)
    issues: list[dict[str, str]] = []
    if (
        not isinstance(change_set_id, str)
        or ID_PATTERN.fullmatch(change_set_id) is None
    ):
        issues.append(
            _issue(
                "EXPERTISE_CHANGE_SET_ID_INVALID",
                "change_set_id",
                "change_set_id must be a lowercase ID.",
            )
        )
        value: Any = None
    else:
        path = _manifest_path(repo, change_set_id)
        try:
            if path.is_symlink() or not path.is_file():
                raise MaestroError(
                    "EXPERTISE_CHANGE_SET_MANIFEST_MISSING",
                    f"ChangeSet manifest is missing: {change_set_id}",
                )
            value = read_json(path)
        except MaestroError as exc:
            issues.append(_issue(exc.code, "change-set-manifest", exc.message))
            value = None
    if not _validate_manifest_shape(value, change_set_id, issues):
        return {
            "schema_version": "maestro_expertise_change_set_manifest_validation_v1",
            "status": "FAIL",
            "change_set_id": change_set_id,
            "issues": issues,
            "writes_performed": False,
        }
    operation = value["operation"]
    members = value.get("members")
    sources = value.get("sources")
    mappings = value.get("guide_mappings")
    defaults = value.get("default_guides")
    if (
        not isinstance(members, list)
        or not 1 <= len(members) <= 16
        or not isinstance(sources, list)
        or not 1 <= len(sources) <= 4
        or not isinstance(mappings, list)
        or len(mappings) > 64
        or not isinstance(defaults, list)
        or not 1 <= len(defaults) <= 16
    ):
        issues.append(
            _issue(
                "EXPERTISE_CHANGE_SET_MANIFEST_CARDINALITY_INVALID",
                "change-set-manifest",
                "Manifest members, sources, or Guide mappings exceed bounds.",
            )
        )
        members = []
        sources = []
        mappings = []
        defaults = []

    active = _active_packs(repo)
    source_by_id: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        if (
            not isinstance(source, dict)
            or set(source) != SOURCE_FIELDS
            or not isinstance(source.get("pack_id"), str)
            or source["pack_id"] in source_by_id
            or source["pack_id"] not in active
            or source.get("definition_digest")
            != expertise_manifest_digest(active[source["pack_id"]])
        ):
            issues.append(
                _issue(
                    "EXPERTISE_CHANGE_SET_SOURCE_INVALID",
                    f"sources[{index}]",
                    "Every source Pack must exist and bind its current definition digest.",
                )
            )
            continue
        source_by_id[source["pack_id"]] = active[source["pack_id"]]

    member_by_id: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
    member_roots: dict[str, Path] = {}
    operation_ids: set[str] = set()
    roles: list[str] = []
    for index, member in enumerate(members):
        path = f"members[{index}]"
        if (
            not isinstance(member, dict)
            or set(member) != MEMBER_FIELDS
            or not isinstance(member.get("candidate_id"), str)
            or ID_PATTERN.fullmatch(member["candidate_id"]) is None
            or not isinstance(member.get("operation_id"), str)
            or ID_PATTERN.fullmatch(member["operation_id"]) is None
            or member["operation_id"] in operation_ids
            or member.get("role") not in ROLES_BY_KIND[operation]
            or not isinstance(member.get("candidate_digest"), str)
            or DIGEST_PATTERN.fullmatch(member["candidate_digest"]) is None
        ):
            issues.append(
                _issue(
                    "EXPERTISE_CHANGE_SET_MEMBER_INVALID",
                    path,
                    "Manifest member identity, role, operation, or digest is invalid.",
                )
            )
            continue
        try:
            root, candidate, pack = _raw_candidate(
                repo,
                member["candidate_id"],
            )
        except MaestroError as exc:
            issues.append(_issue(exc.code, path, exc.message))
            continue
        change = candidate.get("component_change")
        coverage_id, adaptation_plan_id = _candidate_lineage_ids(
            root,
            candidate,
        )
        if (
            not isinstance(change, dict)
            or change.get("kind") != operation
            or change.get("change_set_id") != change_set_id
            or change.get("operation_id") != member["operation_id"]
            or change.get("operation_role") != member["role"]
            or expertise_candidate_content_digest(root)
            != member["candidate_digest"]
            or coverage_id != value["coverage_id"]
            or adaptation_plan_id != value["adaptation_plan_id"]
        ):
            issues.append(
                _issue(
                    "EXPERTISE_CHANGE_SET_MEMBER_MISMATCH",
                    path,
                    "Manifest member does not match its candidate, lineage, role, or digest.",
                )
            )
            continue
        operation_ids.add(member["operation_id"])
        roles.append(member["role"])
        member_by_id[member["candidate_id"]] = (candidate, pack, member)
        member_roots[member["candidate_id"]] = root

    declared_ids = sorted(member_by_id)
    discovered_ids = sorted(_raw_group_members(repo, change_set_id))
    if declared_ids != discovered_ids:
        issues.append(
            _issue(
                "EXPERTISE_CHANGE_SET_MEMBERSHIP_INCOMPLETE",
                "members",
                "Manifest membership must exactly match every candidate in the ChangeSet.",
            )
        )

    member_pack_by_id = {
        pack.get("expertise_pack_id"): pack
        for _candidate, pack, _member in member_by_id.values()
        if isinstance(pack.get("expertise_pack_id"), str)
    }
    default_by_pack: dict[str, list[str]] = {}
    for index, entry in enumerate(defaults):
        pack_id = entry.get("pack_id") if isinstance(entry, dict) else None
        guide_ids = entry.get("guide_ids") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or set(entry) != DEFAULT_GUIDES_FIELDS
            or not isinstance(pack_id, str)
            or pack_id in default_by_pack
            or pack_id not in member_pack_by_id
            or not _unique_ids(
                guide_ids,
                minimum=1,
                maximum=24,
            )
            or not set(guide_ids).issubset(
                _guide_map(member_pack_by_id[pack_id])
            )
            or _default_guides(member_pack_by_id[pack_id]) != guide_ids
        ):
            issues.append(
                _issue(
                    "EXPERTISE_CHANGE_SET_DEFAULT_GUIDES_INVALID",
                    f"default_guides[{index}]",
                    (
                        "Every resulting Pack must explicitly bind one "
                        "non-empty default Guide list drawn from its Guides."
                    ),
                )
            )
            continue
        default_by_pack[pack_id] = list(guide_ids)
    if set(default_by_pack) != set(member_pack_by_id):
        issues.append(
            _issue(
                "EXPERTISE_CHANGE_SET_DEFAULT_GUIDES_INCOMPLETE",
                "default_guides",
                "Default Guide declarations must cover every ChangeSet member Pack.",
            )
        )

    mapping_values: list[dict[str, Any]] = []
    for index, mapping in enumerate(mappings):
        if (
            not isinstance(mapping, dict)
            or set(mapping) != MAPPING_FIELDS
            or not isinstance(mapping.get("guide_id"), str)
            or ID_PATTERN.fullmatch(mapping["guide_id"]) is None
            or not isinstance(mapping.get("source_pack_id"), str)
            or mapping["source_pack_id"] not in source_by_id
            or not _unique_ids(
                mapping.get("target_pack_ids"),
                minimum=1,
                maximum=4,
            )
            or mapping.get("mode")
            not in {"move", "copy", "consolidate"}
        ):
            issues.append(
                _issue(
                    "EXPERTISE_CHANGE_SET_MAPPING_INVALID",
                    f"guide_mappings[{index}]",
                    "Guide mapping source, targets, or mode is invalid.",
                )
            )
            continue
        mapping_values.append(mapping)

    packs_by_role: dict[str, list[dict[str, Any]]] = {
        role: [
            pack
            for _candidate, pack, member in member_by_id.values()
            if member["role"] == role
        ]
        for role in ROLES_BY_KIND[operation]
    }
    semantic_source_ids = sorted(
        {
            mapping["source_pack_id"]
            for mapping in mapping_values
        }
    )
    target_role_ids = sorted(
        pack.get("expertise_pack_id")
        for pack in packs_by_role.get("target", [])
        if isinstance(pack.get("expertise_pack_id"), str)
    )
    result_role_ids = sorted(
        pack.get("expertise_pack_id")
        for pack in packs_by_role.get("result", [])
        if isinstance(pack.get("expertise_pack_id"), str)
    )
    mapped_guide_ids = {
        mapping.get("guide_id")
        for mapping in mapping_values
        if isinstance(mapping.get("guide_id"), str)
    }
    for candidate_id, (candidate, pack, member) in member_by_id.items():
        change = candidate["component_change"]
        pack_id = pack.get("expertise_pack_id")
        expected_targets = (
            target_role_ids
            if operation in {"pack-split", "guide-move", "guide-copy"}
            else []
        )
        identity_valid = (
            sorted(change.get("source_pack_ids", []))
            == semantic_source_ids
            and sorted(change.get("target_pack_ids", []))
            == expected_targets
        )
        if operation in {"guide-move", "guide-copy"}:
            identity_valid = (
                identity_valid
                and change.get("target_guide_id") in mapped_guide_ids
                and len(mapped_guide_ids) == 1
                and (
                    member["role"] != "source"
                    or pack_id in semantic_source_ids
                )
                and (
                    member["role"] != "target"
                    or pack_id in target_role_ids
                )
            )
        elif operation == "pack-split":
            identity_valid = (
                identity_valid
                and change.get("target_guide_id") is None
                and (
                    member["role"] != "source"
                    or pack_id in semantic_source_ids
                )
                and (
                    member["role"] != "target"
                    or pack_id in target_role_ids
                )
            )
        else:
            identity_valid = (
                identity_valid
                and change.get("target_guide_id") is None
                and member["role"] == "result"
                and pack_id in result_role_ids
            )
        if not identity_valid:
            issues.append(
                _issue(
                    "EXPERTISE_CHANGE_SET_CANDIDATE_TOPOLOGY_MISMATCH",
                    f"members.{candidate_id}",
                    (
                        "Candidate source, target, Guide, and role declarations "
                        "must exactly match the semantic manifest topology."
                    ),
                )
            )
    source_guides = {
        pack_id: _guide_map(pack)
        for pack_id, pack in source_by_id.items()
    }
    for candidate_id, (_candidate, pack, _member) in member_by_id.items():
        pack_id = pack.get("expertise_pack_id")
        predecessor = (
            active.get(pack_id)
            if isinstance(pack_id, str)
            else None
        )
        if predecessor is None:
            continue
        unchanged_ids = (
            set(_guide_map(predecessor))
            & set(_guide_map(pack))
        )
        issues.extend(
            _unchanged_guide_body_issues(
                repo,
                candidate_root=member_roots[candidate_id],
                predecessor=predecessor,
                guide_ids=unchanged_ids,
                path=f"members.{candidate_id}.draft/references",
            )
        )
    for index, mapping in enumerate(mapping_values):
        source_pack = source_by_id[mapping["source_pack_id"]]
        source_body_digest = _active_guide_digest(
            repo,
            source_pack,
            mapping["guide_id"],
        )
        target_candidate_ids = [
            candidate_id
            for candidate_id, (_candidate, pack, member) in member_by_id.items()
            if member["role"] in {"target", "result"}
            and pack.get("expertise_pack_id")
            in mapping["target_pack_ids"]
        ]
        target_body_digests = [
            _candidate_guide_digest(
                member_roots[candidate_id],
                mapping["guide_id"],
            )
            for candidate_id in target_candidate_ids
        ]
        if (
            source_body_digest is None
            or len(target_candidate_ids)
            != len(mapping["target_pack_ids"])
            or any(
                digest != source_body_digest
                for digest in target_body_digests
            )
        ):
            issues.append(
                _issue(
                    "EXPERTISE_CHANGE_SET_GUIDE_CONTENT_MISMATCH",
                    f"guide_mappings[{index}]",
                    (
                        "Guide mappings must preserve the exact source "
                        "reference body in every declared target Pack."
                    ),
                )
            )
    if operation == "guide-copy":
        if len(packs_by_role["target"]) != 1 or len(mapping_values) != 1:
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_COPY_TOPOLOGY_INVALID",
                    "members",
                    "Guide copy requires one target member and one mapping.",
                )
            )
        else:
            mapping = mapping_values[0]
            source_guide = source_guides.get(
                mapping["source_pack_id"],
                {},
            ).get(mapping["guide_id"])
            target_pack = packs_by_role["target"][0]
            target_id = target_pack.get("expertise_pack_id")
            target_base = (
                active.get(target_id)
                if isinstance(target_id, str)
                else None
            )
            target_base_guides = _guide_map(target_base or {})
            expected_target_guides = {
                **target_base_guides,
                mapping["guide_id"]: source_guide,
            }
            if (
                mapping["mode"] != "copy"
                or source_guide is None
                or target_id == mapping["source_pack_id"]
                or mapping["guide_id"] in target_base_guides
                or mapping["target_pack_ids"] != [target_id]
                or (
                    target_base is not None
                    and target_id not in source_by_id
                )
                or _guide_map(target_pack) != expected_target_guides
                or (
                    target_base is not None
                    and _default_guides(target_pack)
                    != _default_guides(target_base)
                )
                or (
                    target_base is not None
                    and _stable_pack_fields(target_pack)
                    != _stable_pack_fields(target_base)
                )
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_GUIDE_COPY_TOPOLOGY_INVALID",
                        "guide_mappings",
                        "Copy target must contain the exact source Guide metadata.",
                    )
                )
    elif operation == "guide-move":
        if (
            len(packs_by_role["source"]) != 1
            or len(packs_by_role["target"]) != 1
            or len(mapping_values) != 1
        ):
            issues.append(
                _issue(
                    "EXPERTISE_GUIDE_MOVE_TOPOLOGY_INVALID",
                    "members",
                    "Guide move requires one source member, one target member, and one mapping.",
                )
            )
        else:
            mapping = mapping_values[0]
            source_pack = source_by_id.get(mapping["source_pack_id"])
            source_after = packs_by_role["source"][0]
            target_after = packs_by_role["target"][0]
            source_guide = _guide_map(source_pack or {}).get(
                mapping["guide_id"]
            )
            source_before_guides = _guide_map(source_pack or {})
            expected_source_guides = {
                guide_id: guide
                for guide_id, guide in source_before_guides.items()
                if guide_id != mapping["guide_id"]
            }
            target_id = target_after.get("expertise_pack_id")
            target_base = (
                active.get(target_id)
                if isinstance(target_id, str)
                else None
            )
            target_base_guides = _guide_map(target_base or {})
            expected_target_guides = {
                **target_base_guides,
                mapping["guide_id"]: source_guide,
            }
            if (
                mapping["mode"] != "move"
                or source_guide is None
                or target_id == mapping["source_pack_id"]
                or source_after.get("expertise_pack_id")
                != mapping["source_pack_id"]
                or _guide_map(source_after) != expected_source_guides
                or _stable_pack_fields(source_after)
                != _stable_pack_fields(source_pack or {})
                or mapping["guide_id"] in target_base_guides
                or mapping["target_pack_ids"] != [target_id]
                or (
                    target_base is not None
                    and target_id not in source_by_id
                )
                or _guide_map(target_after) != expected_target_guides
                or (
                    target_base is not None
                    and _default_guides(target_after)
                    != _default_guides(target_base)
                )
                or (
                    target_base is not None
                    and _stable_pack_fields(target_after)
                    != _stable_pack_fields(target_base)
                )
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_GUIDE_MOVE_TOPOLOGY_INVALID",
                        "guide_mappings",
                        "Move must remove exactly one source Guide and add the same Guide to one target.",
                    )
                )
    elif operation == "pack-extraction":
        result_members = packs_by_role["result"]
        if (
            not 2 <= len(source_by_id) <= 4
            or len(result_members) != 1
        ):
            issues.append(
                _issue(
                    "EXPERTISE_PACK_EXTRACTION_TOPOLOGY_INVALID",
                    "members",
                    (
                        "Pack extraction requires two to four source "
                        "Packs and exactly one result member."
                    ),
                )
            )
        else:
            result_pack = result_members[0]
            result_id = result_pack.get("expertise_pack_id")
            selected_guides: dict[str, dict[str, Any]] = {}
            selected_pairs: set[tuple[str, str]] = set()
            participating_sources: set[str] = set()
            valid_mappings = True
            for mapping in mapping_values:
                source_id = mapping["source_pack_id"]
                guide_id = mapping["guide_id"]
                pair = (source_id, guide_id)
                source_guide = source_guides.get(
                    source_id,
                    {},
                ).get(guide_id)
                if (
                    mapping["mode"] != "copy"
                    or mapping["target_pack_ids"] != [result_id]
                    or source_guide is None
                    or pair in selected_pairs
                    or guide_id in selected_guides
                ):
                    valid_mappings = False
                    continue
                selected_pairs.add(pair)
                participating_sources.add(source_id)
                selected_guides[guide_id] = source_guide
            if (
                not valid_mappings
                or len(mapping_values) < 2
                or participating_sources != set(source_by_id)
                or not isinstance(result_id, str)
                or result_id in source_by_id
                or result_id in active
                or _guide_map(result_pack) != selected_guides
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_PACK_EXTRACTION_TOPOLOGY_INVALID",
                        "guide_mappings",
                        (
                            "Extraction must copy an exact, collision-free "
                            "Guide subset from every source into one new Pack."
                        ),
                    )
                )
    elif operation == "pack-split":
        source_members = packs_by_role["source"]
        target_members = packs_by_role["target"]
        if (
            len(source_by_id) != 1
            or len(source_members) != 1
            or not 2 <= len(target_members) <= 4
        ):
            issues.append(
                _issue(
                    "EXPERTISE_PACK_SPLIT_TOPOLOGY_INVALID",
                    "members",
                    "Pack split requires one source revision and two to four target members.",
                )
            )
        else:
            source_id, source_pack = next(iter(source_by_id.items()))
            original_guides = _guide_map(source_pack)
            source_after = source_members[0]
            moved: dict[str, str] = {}
            valid_mapping_modes = True
            for mapping in mapping_values:
                if (
                    mapping["source_pack_id"] != source_id
                    or mapping["mode"] != "move"
                    or len(mapping["target_pack_ids"]) != 1
                    or mapping["guide_id"] in moved
                ):
                    valid_mapping_modes = False
                    continue
                moved[mapping["guide_id"]] = mapping["target_pack_ids"][0]
            target_by_id = {
                pack["expertise_pack_id"]: pack
                for pack in target_members
                if isinstance(pack.get("expertise_pack_id"), str)
            }
            targets_match = all(
                target_id in target_by_id
                and _guide_map(target_by_id[target_id]).get(guide_id)
                == original_guides.get(guide_id)
                for guide_id, target_id in moved.items()
            )
            expected_source_ids = set(original_guides) - set(moved)
            expected_source_guides = {
                guide_id: original_guides[guide_id]
                for guide_id in expected_source_ids
            }
            target_guide_occurrences = [
                guide_id
                for pack in target_members
                for guide_id in _guide_map(pack)
            ]
            target_guide_ids = set(target_guide_occurrences)
            if (
                not valid_mapping_modes
                or not moved
                or not targets_match
                or source_after.get("expertise_pack_id") != source_id
                or _guide_map(source_after) != expected_source_guides
                or _stable_pack_fields(source_after)
                != _stable_pack_fields(source_pack)
                or len(target_by_id) != len(target_members)
                or source_id in target_by_id
                or set(target_by_id) & set(active)
                or any(
                    not _guide_map(target)
                    for target in target_members
                )
                or target_guide_ids != set(moved)
                or len(target_guide_occurrences) != len(target_guide_ids)
                or set(moved.values()) != set(target_by_id)
                or set(moved) - set(original_guides)
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_PACK_SPLIT_TOPOLOGY_INVALID",
                        "guide_mappings",
                        "Split must preserve every source Guide exactly once across source remainder and targets.",
                    )
                )
    elif operation == "pack-merge":
        result_members = packs_by_role["result"]
        if len(source_by_id) < 2 or len(result_members) != 1:
            issues.append(
                _issue(
                    "EXPERTISE_PACK_MERGE_TOPOLOGY_INVALID",
                    "members",
                    "Pack merge requires two to four sources and one result member.",
                )
            )
        else:
            union: dict[str, dict[str, Any]] = {}
            collisions: set[str] = set()
            expected_mappings: set[tuple[str, str, str]] = set()
            for source_id, guides in source_guides.items():
                for guide_id, guide in guides.items():
                    if guide_id in union:
                        collisions.add(guide_id)
                    union[guide_id] = guide
                    expected_mappings.add(
                        (source_id, guide_id, "consolidate")
                    )
            result_pack = result_members[0]
            result_id = result_pack.get("expertise_pack_id")
            result_guides = _guide_map(result_pack)
            mapped = [
                (
                    mapping["source_pack_id"],
                    mapping["guide_id"],
                    mapping["mode"],
                )
                for mapping in mapping_values
                if mapping["target_pack_ids"] == [result_id]
            ]
            if (
                collisions
                or not isinstance(result_id, str)
                or result_id in source_by_id
                or result_id in active
                or result_guides != union
                or len(mapped) != len(mapping_values)
                or len(mapped) != len(set(mapped))
                or set(mapped) != expected_mappings
            ):
                issues.append(
                    _issue(
                        "EXPERTISE_PACK_MERGE_TOPOLOGY_INVALID",
                        "guide_mappings",
                        "Merge result must preserve the collision-free union of every source Guide.",
                    )
                )

    if validate_members:
        from .expertise_lifecycle import validate_expertise_candidate

        for candidate_id in sorted(member_by_id):
            member_validation = validate_expertise_candidate(
                repo,
                candidate_id,
                validate_change_set=False,
            )
            if member_validation["status"] != "PASS":
                issues.append(
                    _issue(
                        "EXPERTISE_CHANGE_SET_MEMBER_VALIDATION_FAILED",
                        f"members.{candidate_id}",
                        (
                            "Every ChangeSet member must pass its complete "
                            "candidate contract before approval."
                        ),
                    )
                )

    return {
        "schema_version": "maestro_expertise_change_set_manifest_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "change_set_id": change_set_id,
        "operation": operation,
        "member_count": len(member_by_id),
        "issues": issues,
        "writes_performed": False,
    }


def validate_task_gap_complex_candidate(
    repo_path: str | Path,
    candidate: dict[str, Any],
) -> list[dict[str, str]]:
    change = candidate.get("component_change")
    if (
        not isinstance(change, dict)
        or change.get("kind") not in COMPLEX_KINDS
    ):
        return []
    if (
        not isinstance(change.get("change_set_id"), str)
        or not isinstance(change.get("operation_id"), str)
        or change.get("operation_role") not in ROLES_BY_KIND[change["kind"]]
    ):
        return [
            _issue(
                "EXPERTISE_COMPLEX_CHANGE_IDENTITY_INVALID",
                "candidate.json.component_change",
                "Complex changes require ChangeSet, operation, and role identities.",
            )
        ]
    validation = validate_expertise_change_set_manifest(
        repo_path,
        change["change_set_id"],
    )
    return validation["issues"] if validation["status"] != "PASS" else []
