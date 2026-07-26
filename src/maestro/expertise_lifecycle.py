from __future__ import annotations

import copy
import re
from datetime import date
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .expertise import (
    PROJECT_PACK_FILENAME,
    expertise_manifest_digest,
    load_expertise_catalog,
)
from .project import git_ignored
from .registry import load_registry, resource_root, validate_registry
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    file_sha256,
    pretty_json,
    read_json,
    safe_target,
    sha256_bytes,
    sha256_text,
)

ACTIVATION_PLAN_VERSION = "maestro_expertise_activation_plan_v1"
UPDATE_PLAN_VERSION = "maestro_expertise_update_plan_v1"
DEACTIVATION_PLAN_VERSION = "maestro_expertise_deactivation_plan_v1"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
APPROVAL_PATTERN = re.compile(
    r"^(?:owner_decision|held_out_evaluation):\S.+$"
)
MAX_CANDIDATES = 100
MAX_ACTIVATION_FILE_BYTES = 2_000_000
CANDIDATE_REQUIRED_FIELDS = {
    "schema_version",
    "candidate_id",
    "expertise_pack_id",
    "status",
    "portability",
    "owner",
    "review_after",
    "problem",
    "reusable_when",
    "not_for",
    "existing_coverage",
    "evidence_refs",
    "proposed_guides",
    "evaluation",
}
PROPOSED_GUIDE_FIELDS = {
    "guide_id",
    "failure_prevented",
    "decision_checks",
    "freshness",
}
EVALUATION_FIELDS = {
    "baseline",
    "cases_path",
    "pass_criteria",
    "regression_criteria",
}
PUBLICATION_PLAN_FIELDS = {
    "schema_version",
    "command",
    "repo_realpath",
    "candidate_id",
    "approval_ref",
    "operations",
    "warnings",
    "writes_performed",
    "plan_id",
    "plan_digest",
}


def _nonempty_unique_strings(
    value: Any,
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= minimum
        and (maximum is None or len(value) <= maximum)
        and len(value) == len(set(value))
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _candidate_contract_valid(
    candidate: dict[str, Any],
    candidate_id: str,
) -> bool:
    if (
        set(candidate) != CANDIDATE_REQUIRED_FIELDS
        or candidate.get("schema_version") != "maestro_expertise_candidate_v1"
        or candidate.get("candidate_id") != candidate_id
        or candidate.get("status") != "candidate"
        or candidate.get("portability") not in {"project", "profile", "global"}
        or not isinstance(candidate.get("expertise_pack_id"), str)
        or ID_PATTERN.fullmatch(candidate["expertise_pack_id"]) is None
        or not isinstance(candidate.get("owner"), str)
        or not candidate["owner"].strip()
        or not isinstance(candidate.get("problem"), str)
        or not candidate["problem"].strip()
        or not isinstance(candidate.get("existing_coverage"), str)
        or not candidate["existing_coverage"].strip()
        or not _nonempty_unique_strings(candidate.get("reusable_when"))
        or not _nonempty_unique_strings(candidate.get("not_for"))
        or not _nonempty_unique_strings(candidate.get("evidence_refs"))
    ):
        return False
    try:
        date.fromisoformat(candidate.get("review_after", ""))
    except (TypeError, ValueError):
        return False
    guides = candidate.get("proposed_guides")
    if not isinstance(guides, list) or not 1 <= len(guides) <= 8:
        return False
    guide_ids: list[str] = []
    for guide in guides:
        if (
            not isinstance(guide, dict)
            or set(guide) != PROPOSED_GUIDE_FIELDS
            or not isinstance(guide.get("guide_id"), str)
            or ID_PATTERN.fullmatch(guide["guide_id"]) is None
            or not isinstance(guide.get("failure_prevented"), str)
            or not guide["failure_prevented"].strip()
            or not _nonempty_unique_strings(
                guide.get("decision_checks"),
                minimum=2,
                maximum=12,
            )
            or guide.get("freshness") not in {"stable", "versioned", "volatile"}
        ):
            return False
        guide_ids.append(guide["guide_id"])
    if len(guide_ids) != len(set(guide_ids)):
        return False
    evaluation = candidate.get("evaluation")
    return (
        isinstance(evaluation, dict)
        and set(evaluation) == EVALUATION_FIELDS
        and evaluation.get("baseline")
        in {"no-pack", "persona-only", "existing-pack"}
        and evaluation.get("cases_path") == "evals/cases.json"
        and _nonempty_unique_strings(evaluation.get("pass_criteria"))
        and _nonempty_unique_strings(evaluation.get("regression_criteria"))
    )


def _candidate_root(repo: Path, candidate_id: str) -> Path:
    if not isinstance(candidate_id, str) or ID_PATTERN.fullmatch(candidate_id) is None:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_ID_INVALID",
            "candidate must be a lowercase ASCII slug.",
        )
    return safe_target(
        repo,
        f".maestro/state/candidates/expertise/{candidate_id}",
    )


def _read_candidate(repo: Path, candidate_id: str) -> tuple[Path, dict[str, Any]]:
    root = _candidate_root(repo, candidate_id)
    if root.is_symlink() or not root.is_dir():
        raise MaestroError(
            "EXPERTISE_CANDIDATE_MISSING",
            f"Expertise candidate is missing: {candidate_id}",
        )
    candidate = read_json(safe_target(root, "candidate.json"))
    if not _candidate_contract_valid(candidate, candidate_id):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_INVALID",
            f"Candidate {candidate_id} does not satisfy the activation contract.",
        )
    return root, candidate


def _read_text_file(root: Path, relative_path: str) -> str:
    target = safe_target(root, relative_path)
    if target.is_symlink() or not target.is_file():
        raise MaestroError(
            "EXPERTISE_CANDIDATE_FILE_MISSING",
            f"Candidate requires a regular file: {relative_path}",
        )
    if target.stat().st_size > MAX_ACTIVATION_FILE_BYTES:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_FILE_TOO_LARGE",
            f"Candidate file exceeds {MAX_ACTIVATION_FILE_BYTES} bytes: {relative_path}",
        )
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_FILE_INVALID",
            f"Candidate file is not UTF-8 text: {relative_path}",
        ) from exc


def _validate_activation_pack(
    candidate: dict[str, Any],
    pack: dict[str, Any],
) -> None:
    registry = load_registry()
    combined = copy.deepcopy(registry)
    combined["expertise_packs"].append(pack)
    errors = validate_registry(combined)
    if errors:
        raise MaestroError("EXPERTISE_ACTIVATION_PACK_INVALID", "; ".join(errors))
    if (
        pack["expertise_pack_id"] != candidate["expertise_pack_id"]
        or pack["portability"] != "project"
        or pack["status"] != "pilot"
        or pack["source_manifest"] != "evidence/sources.json"
        or pack["evaluation_suite"] != "evals/cases.json"
    ):
        raise MaestroError(
            "EXPERTISE_ACTIVATION_PACK_INVALID",
            "Activated packs must match the candidate, use project portability, "
            "enter as pilot, and use the canonical evidence/eval paths.",
        )
    proposed_ids = {
        item.get("guide_id")
        for item in candidate["proposed_guides"]
        if isinstance(item, dict)
    }
    pack_guide_ids = {guide["guide_id"] for guide in pack["guides"]}
    if proposed_ids != pack_guide_ids:
        raise MaestroError(
            "EXPERTISE_ACTIVATION_GUIDES_MISMATCH",
            "Candidate proposed guides and the pilot pack guides differ.",
        )
    extends = pack.get("extends")
    if extends is None:
        return
    base = next(
        (
            item
            for item in registry["expertise_packs"]
            if item["expertise_pack_id"] == extends["expertise_pack_id"]
        ),
        None,
    )
    if (
        base is None
        or base["version"] != extends["version"]
        or expertise_manifest_digest(base) != extends["digest"]
    ):
        raise MaestroError(
            "EXPERTISE_ACTIVATION_BASE_STALE",
            "extends must pin one current bundled pack by ID, version, and digest.",
        )
    collisions = sorted(
        pack_guide_ids
        & {guide["guide_id"] for guide in base["guides"]}
    )
    if collisions:
        raise MaestroError(
            "EXPERTISE_ACTIVATION_GUIDE_COLLISION",
            f"Local guides may not redefine inherited guides: {collisions}",
        )


def _validate_approval_ref(approval_ref: str) -> None:
    if (
        not isinstance(approval_ref, str)
        or APPROVAL_PATTERN.fullmatch(approval_ref) is None
    ):
        raise MaestroError(
            "EXPERTISE_PUBLICATION_APPROVAL_INVALID",
            "approval-ref must be owner_decision:<ref> or "
            "held_out_evaluation:<ref>.",
        )


def _fresh_candidate_pack(
    repo: Path,
    candidate_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    candidate_root, candidate = _read_candidate(repo, candidate_id)
    if date.fromisoformat(candidate["review_after"]) < date.today():
        raise MaestroError(
            "EXPERTISE_CANDIDATE_EXPIRED",
            "Expired candidates must be revalidated before publication.",
        )
    pack = read_json(
        safe_target(candidate_root, f"draft/{PROJECT_PACK_FILENAME}")
    )
    _validate_activation_pack(candidate, pack)
    return candidate_root, candidate, pack


def _project_expertise_configuration(
    repo: Path,
) -> tuple[Path, dict[str, Any], list[str]]:
    project_path = safe_target(repo, ".maestro/project.json")
    project = read_json(project_path)
    expertise = project.get("expertise", {"active_pack_paths": []})
    if (
        not isinstance(expertise, dict)
        or set(expertise) != {"active_pack_paths"}
        or not isinstance(expertise["active_pack_paths"], list)
        or len(expertise["active_pack_paths"])
        != len(set(expertise["active_pack_paths"]))
        or any(
            not isinstance(path, str) or not path.strip()
            for path in expertise["active_pack_paths"]
        )
    ):
        raise MaestroError(
            "PROJECT_EXPERTISE_CONFIG_INVALID",
            "Repair project.json expertise configuration before publication.",
        )
    return project_path, project, expertise["active_pack_paths"]


def _candidate_publication_contents(
    candidate_root: Path,
    pack: dict[str, Any],
    destination_root: str,
) -> tuple[dict[str, str], str]:
    source_to_destination = {
        f"draft/{PROJECT_PACK_FILENAME}": (
            f"{destination_root}/{PROJECT_PACK_FILENAME}"
        ),
        "draft/SKILL.md": f"{destination_root}/SKILL.md",
        "draft/agents/openai.yaml": (
            f"{destination_root}/agents/openai.yaml"
        ),
        "candidate.json": f"{destination_root}/evidence/candidate.json",
        "evidence/sources.json": (
            f"{destination_root}/evidence/sources.json"
        ),
        "evals/cases.json": f"{destination_root}/evals/cases.json",
    }
    for guide in pack["guides"]:
        guide_id = guide["guide_id"]
        source_to_destination[
            f"draft/references/{guide_id}.md"
        ] = f"{destination_root}/references/{guide_id}.md"

    contents: dict[str, str] = {}
    source_digests: dict[str, str] = {}
    for source, destination in sorted(source_to_destination.items()):
        content = _read_text_file(candidate_root, source)
        source_digests[source] = sha256_text(content)
        contents[destination] = content
    return contents, sha256_text(canonical_json(source_digests))


def _publication_record(
    *,
    action: str,
    candidate_id: str,
    candidate_digest: str,
    approval_ref: str,
    pack_version: int,
    previous_definition_digest: str | None,
) -> str:
    return pretty_json(
        {
            "schema_version": "maestro_expertise_publication_v1",
            "action": action,
            "candidate_id": candidate_id,
            "candidate_digest": candidate_digest,
            "approval_ref": approval_ref,
            "source_candidate_path": (
                f".maestro/state/candidates/expertise/{candidate_id}"
            ),
            "pack_version": pack_version,
            "previous_definition_digest": previous_definition_digest,
        }
    )


def _text_operation(
    repo: Path,
    path: str,
    content: str,
    *,
    require_missing: bool = False,
) -> dict[str, Any]:
    before = file_sha256(safe_target(repo, path))
    if require_missing and before is not None:
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_EXISTS",
            f"Project Expertise target already exists: {path}",
        )
    return {
        "op": "create" if before is None else "replace",
        "path": path,
        "before_sha256": before,
        "after_sha256": sha256_text(content),
        "content": content,
    }


def _delete_operation(repo: Path, path: str) -> dict[str, Any]:
    before = file_sha256(safe_target(repo, path))
    if before is None:
        raise MaestroError(
            "EXPERTISE_UPDATE_TARGET_MISSING",
            f"Cannot remove a missing project Expertise file: {path}",
        )
    return {
        "op": "delete",
        "path": path,
        "before_sha256": before,
        "after_sha256": None,
        "content": None,
    }


def _finalize_plan(base: dict[str, Any]) -> dict[str, Any]:
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def expertise_inventory(repo_path: str | Path) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    catalog = load_expertise_catalog(repo)
    entries: list[dict[str, Any]] = []
    for pack in catalog:
        metadata = pack["_maestro"]
        if metadata["origin"] == "project":
            skill_path = metadata["skill_path"]
            source_path = safe_target(
                repo,
                (
                    Path(skill_path).parent
                    / pack["source_manifest"]
                ).as_posix(),
            )
            publication_path = safe_target(
                repo,
                (
                    Path(skill_path).parent
                    / "activation.json"
                ).as_posix(),
            )
        else:
            source_path = Path(
                str(
                    resource_root().joinpath(
                        f"expertise-sources/{pack['expertise_pack_id']}.json"
                    )
                )
            )
            publication_path = None
        source_manifest: dict[str, Any] | None = None
        if source_path.is_file() and not source_path.is_symlink():
            try:
                candidate = read_json(source_path)
                if (
                    candidate.get("schema_version")
                    == "maestro_expertise_sources_v1"
                    and candidate.get("expertise_pack_id")
                    == pack["expertise_pack_id"]
                    and isinstance(candidate.get("sources"), list)
                    and len(candidate["sources"]) <= 20
                ):
                    source_manifest = candidate
            except MaestroError:
                source_manifest = None
        publication: dict[str, Any] | None = None
        if (
            publication_path is not None
            and publication_path.is_file()
            and not publication_path.is_symlink()
        ):
            try:
                value = read_json(publication_path)
                publication = {
                    key: value.get(key)
                    for key in (
                        "action",
                        "candidate_id",
                        "pack_version",
                        "previous_definition_digest",
                    )
                }
            except MaestroError:
                publication = None
        entries.append(
            {
                "expertise_pack_id": pack["expertise_pack_id"],
                "summary": pack["summary"],
                "skill_id": pack["skill_id"],
                "status": pack["status"],
                "portability": pack["portability"],
                "version": pack["version"],
                "origin": metadata["origin"],
                "pack_path": metadata["pack_path"],
                "definition_digest": metadata["definition_digest"],
                "extends": metadata["base"],
                "guides": [
                    {
                        "guide_id": guide["guide_id"],
                        "summary": guide["summary"],
                        "freshness": guide["freshness"],
                    }
                    for guide in pack["guides"]
                ],
                "source_manifest": (
                    {
                        "status": "available",
                        "verified_on": source_manifest.get("verified_on"),
                        "sources": [
                            {
                                key: source.get(key)
                                for key in (
                                    "source_id",
                                    "tier",
                                    "authority",
                                    "url",
                                    "used_by",
                                    "freshness",
                                )
                            }
                            for source in source_manifest["sources"]
                            if isinstance(source, dict)
                        ],
                    }
                    if source_manifest is not None
                    else {
                        "status": "unavailable",
                        "verified_on": None,
                        "sources": [],
                    }
                ),
                "publication": publication,
            }
        )
    candidates: list[dict[str, Any]] = []
    candidate_root = safe_target(
        repo,
        ".maestro/state/candidates/expertise",
    )
    if candidate_root.is_dir() and not candidate_root.is_symlink():
        for path in sorted(candidate_root.iterdir())[:MAX_CANDIDATES]:
            if path.is_symlink() or not path.is_dir():
                continue
            try:
                _, candidate = _read_candidate(repo, path.name)
                candidates.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "expertise_pack_id": candidate["expertise_pack_id"],
                        "owner": candidate["owner"],
                        "review_after": candidate["review_after"],
                        "ready_for_activation_review": (
                            path / "draft" / PROJECT_PACK_FILENAME
                        ).is_file()
                        and date.fromisoformat(candidate["review_after"])
                        >= date.today(),
                    }
                )
            except MaestroError as exc:
                candidates.append(
                    {
                        "candidate_id": path.name,
                        "error": f"{exc.code}: {exc.message}",
                        "ready_for_activation_review": False,
                    }
                )
    return {
        "schema_version": "maestro_expertise_inventory_v1",
        "status": "ok",
        "repo_root": str(repo),
        "packs": entries,
        "candidates": candidates,
        "writes_performed": False,
    }


def build_expertise_activation_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    approval_ref: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _validate_approval_ref(approval_ref)
    candidate_root, _, pack = _fresh_candidate_pack(repo, candidate_id)

    skill_id = pack["skill_id"]
    destination_root = f".agents/skills/{skill_id}"
    if safe_target(repo, destination_root).exists():
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_EXISTS",
            f"Project Skill already exists: {destination_root}",
        )
    _, project, active_pack_paths = (
        _project_expertise_configuration(repo)
    )
    pack_path = f"{destination_root}/{PROJECT_PACK_FILENAME}"
    if git_ignored(repo, pack_path) is True:
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_IGNORED",
            "Active project Expertise must not be Git-ignored. "
            "Repair the project ignore policy before activation.",
        )
    if pack_path in active_pack_paths:
        raise MaestroError(
            "EXPERTISE_ALREADY_ACTIVE",
            f"Project Expertise is already enabled: {pack_path}",
        )

    contents, candidate_digest = _candidate_publication_contents(
        candidate_root,
        pack,
        destination_root,
    )
    operations = [
        _text_operation(
            repo,
            path,
            content,
            require_missing=True,
        )
        for path, content in sorted(contents.items())
    ]

    activation_content = _publication_record(
        action="activate",
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        approval_ref=approval_ref,
        pack_version=pack["version"],
        previous_definition_digest=None,
    )
    operations.append(
        _text_operation(
            repo,
            f"{destination_root}/activation.json",
            activation_content,
            require_missing=True,
        )
    )

    updated_project = copy.deepcopy(project)
    updated_project["expertise"] = {
        "active_pack_paths": [
            *active_pack_paths,
            pack_path,
        ]
    }
    project_content = pretty_json(updated_project)
    operations.append(
        _text_operation(
            repo,
            ".maestro/project.json",
            project_content,
        )
    )
    operations.sort(key=lambda item: item["path"])
    base = {
        "schema_version": ACTIVATION_PLAN_VERSION,
        "command": "expertise-activate",
        "repo_realpath": str(repo),
        "candidate_id": candidate_id,
        "approval_ref": approval_ref,
        "operations": operations,
        "warnings": [
            "Activation publishes a tracked project pilot; it does not promote a global Harness Pack.",
            "A compact candidate snapshot is copied into the active Pack; the ignored working candidate is retained.",
            "Stage and commit the changed project files after Doctor passes.",
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def build_expertise_update_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    approval_ref: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _validate_approval_ref(approval_ref)
    candidate_root, _, pack = _fresh_candidate_pack(repo, candidate_id)
    _, _, active_pack_paths = _project_expertise_configuration(repo)

    destination_root = f".agents/skills/{pack['skill_id']}"
    pack_path = f"{destination_root}/{PROJECT_PACK_FILENAME}"
    if pack_path not in active_pack_paths:
        raise MaestroError(
            "EXPERTISE_UPDATE_TARGET_NOT_ACTIVE",
            "Update requires an active project Expertise with the same Skill "
            "identity. Use activate for a new Pack.",
        )
    if git_ignored(repo, pack_path) is True:
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_IGNORED",
            "Active project Expertise must not be Git-ignored. "
            "Repair the project ignore policy before updating it.",
        )

    catalog = load_expertise_catalog(repo)
    current = next(
        (
            item
            for item in catalog
            if item["_maestro"]["origin"] == "project"
            and item["_maestro"]["pack_path"] == pack_path
        ),
        None,
    )
    if current is None:
        raise MaestroError(
            "EXPERTISE_UPDATE_TARGET_INVALID",
            f"Active project Expertise cannot be loaded: {pack_path}",
        )
    if (
        pack["expertise_pack_id"] != current["expertise_pack_id"]
        or pack["skill_id"] != current["skill_id"]
    ):
        raise MaestroError(
            "EXPERTISE_UPDATE_IDENTITY_CHANGED",
            "An update must preserve expertise_pack_id and skill_id.",
        )
    if current["status"] != "pilot" or pack["status"] != current["status"]:
        raise MaestroError(
            "EXPERTISE_UPDATE_STATUS_UNSUPPORTED",
            "The v0.3 update path supports project pilot revisions only; "
            "active promotion remains a separate owner decision.",
        )
    if pack["version"] != current["version"] + 1:
        raise MaestroError(
            "EXPERTISE_UPDATE_VERSION_INVALID",
            "A project Expertise update must increment version by exactly one.",
        )

    contents, candidate_digest = _candidate_publication_contents(
        candidate_root,
        pack,
        destination_root,
    )
    publication_path = f"{destination_root}/activation.json"
    contents[publication_path] = _publication_record(
        action="update",
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        approval_ref=approval_ref,
        pack_version=pack["version"],
        previous_definition_digest=current["_maestro"]["definition_digest"],
    )
    operations = [
        _text_operation(repo, path, content)
        for path, content in sorted(contents.items())
    ]

    desired_guide_paths = {
        f"{destination_root}/references/{guide['guide_id']}.md"
        for guide in pack["guides"]
    }
    current_guide_paths = {
        f"{destination_root}/references/{guide['guide_id']}.md"
        for guide in current["guides"]
        if current["_maestro"]["guide_origins"][guide["guide_id"]]["origin"]
        == "project"
    }
    for obsolete_path in sorted(
        current_guide_paths - desired_guide_paths
    ):
        operations.append(_delete_operation(repo, obsolete_path))
    operations.sort(key=lambda item: item["path"])

    base = {
        "schema_version": UPDATE_PLAN_VERSION,
        "command": "expertise-update",
        "repo_realpath": str(repo),
        "candidate_id": candidate_id,
        "approval_ref": approval_ref,
        "operations": operations,
        "warnings": [
            "Update keeps the same project Pack identity and publishes one reviewed version increment.",
            "A changed bundled base pin is accepted only when the candidate pins the currently installed base.",
            "The ignored working candidate is retained; stage and commit the changed project files after Doctor passes.",
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def build_expertise_deactivation_plan(
    repo_path: str | Path,
    *,
    expertise_pack_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    if (
        not isinstance(expertise_pack_id, str)
        or ID_PATTERN.fullmatch(expertise_pack_id) is None
    ):
        raise MaestroError(
            "EXPERTISE_DEACTIVATION_ID_INVALID",
            "pack must be a lowercase ASCII Expertise Pack ID.",
        )
    _, project, active_pack_paths = _project_expertise_configuration(repo)
    catalog = load_expertise_catalog(repo)
    current = next(
        (
            item
            for item in catalog
            if item["_maestro"]["origin"] == "project"
            and item["expertise_pack_id"] == expertise_pack_id
        ),
        None,
    )
    if current is None:
        raise MaestroError(
            "EXPERTISE_DEACTIVATION_TARGET_NOT_ACTIVE",
            f"Active project Expertise is missing: {expertise_pack_id}",
        )
    pack_path = current["_maestro"]["pack_path"]
    if pack_path not in active_pack_paths:
        raise MaestroError(
            "EXPERTISE_DEACTIVATION_TARGET_NOT_ACTIVE",
            f"Project Expertise is not allowlisted: {expertise_pack_id}",
        )

    updated_project = copy.deepcopy(project)
    updated_project["expertise"] = {
        "active_pack_paths": [
            path for path in active_pack_paths if path != pack_path
        ]
    }
    operations = [
        _text_operation(
            repo,
            ".maestro/project.json",
            pretty_json(updated_project),
        )
    ]
    base = {
        "schema_version": DEACTIVATION_PLAN_VERSION,
        "command": "expertise-deactivate",
        "repo_realpath": str(repo),
        "expertise_pack_id": expertise_pack_id,
        "pack_path": pack_path,
        "definition_digest": current["_maestro"]["definition_digest"],
        "operations": operations,
        "warnings": [
            "Deactivation removes only the Maestro allowlist entry; project Skill files are preserved for review and rollback.",
            "The preserved project Skill may remain explicitly visible to the Host; deactivation stops Maestro routing, not Host discovery.",
            "Commit the project manifest change after review.",
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def _read_publication_plan(
    plan_path: str | Path,
    *,
    schema_version: str,
    command: str,
    allowed_fields: set[str],
    label: str,
) -> dict[str, Any]:
    plan = read_json(Path(plan_path).expanduser().resolve())
    if (
        set(plan) != allowed_fields
        or plan.get("schema_version") != schema_version
        or plan.get("command") != command
        or plan.get("writes_performed") is not False
    ):
        raise MaestroError(
            f"EXPERTISE_{label}_PLAN_INVALID",
            f"Unsupported Expertise {label.casefold()} plan.",
            exit_code=3,
        )
    unsigned = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(unsigned))
    if plan.get("plan_id") != digest[:20] or plan.get("plan_digest") != digest:
        raise MaestroError(
            f"EXPERTISE_{label}_PLAN_TAMPERED",
            f"{label.title()} plan digest does not match its contents.",
            exit_code=3,
        )
    return plan


def _publication_repo(
    plan: dict[str, Any],
    *,
    repo_override: str | Path | None,
    label: str,
) -> Path:
    repo = ensure_repo(repo_override or plan["repo_realpath"])
    if str(repo) != plan["repo_realpath"]:
        raise MaestroError(
            f"EXPERTISE_{label}_REPO_MISMATCH",
            f"{label.title()} plan belongs to a different repository.",
            exit_code=3,
        )
    return repo


def _operation_originals(
    repo: Path,
    operations: Any,
    *,
    allow_delete: bool,
    project_only: bool,
    label: str,
) -> dict[Path, bytes | None]:
    if not isinstance(operations, list) or not operations:
        raise MaestroError(
            f"EXPERTISE_{label}_PLAN_INVALID",
            f"{label.title()} operations must be a non-empty list.",
            exit_code=3,
        )

    originals: dict[Path, bytes | None] = {}
    seen_paths: set[str] = set()
    allowed_operations = (
        {"create", "replace", "delete"}
        if allow_delete
        else {"create", "replace"}
    )
    for operation in operations:
        if (
            not isinstance(operation, dict)
            or set(operation)
            != {"op", "path", "before_sha256", "after_sha256", "content"}
            or operation.get("op") not in allowed_operations
            or not isinstance(operation.get("path"), str)
        ):
            raise MaestroError(
                f"EXPERTISE_{label}_PLAN_INVALID",
                f"{label.title()} operation is invalid.",
                exit_code=3,
            )
        path = operation["path"]
        if path in seen_paths:
            raise MaestroError(
                f"EXPERTISE_{label}_PLAN_INVALID",
                f"{label.title()} plan contains a duplicate path: {path}",
                exit_code=3,
            )
        seen_paths.add(path)
        if project_only:
            path_allowed = path == ".maestro/project.json"
        else:
            path_allowed = (
                path == ".maestro/project.json"
                or path.startswith(".agents/skills/")
            )
        if not path_allowed:
            raise MaestroError(
                f"EXPERTISE_{label}_PATH_INVALID",
                f"{label.title()} may not change this path: {path}",
                exit_code=3,
            )
        target = safe_target(repo, path)
        if file_sha256(target) != operation["before_sha256"]:
            raise MaestroError(
                f"EXPERTISE_{label}_PLAN_STALE",
                f"File changed after preview: {path}",
                exit_code=3,
            )

        if operation["op"] == "delete":
            if (
                operation.get("content") is not None
                or operation.get("after_sha256") is not None
                or operation.get("before_sha256") is None
            ):
                raise MaestroError(
                    f"EXPERTISE_{label}_PLAN_INVALID",
                    f"Delete operation is invalid: {path}",
                    exit_code=3,
                )
        else:
            if not isinstance(operation.get("content"), str):
                raise MaestroError(
                    f"EXPERTISE_{label}_PLAN_INVALID",
                    f"Text operation is invalid: {path}",
                    exit_code=3,
                )
            content = operation["content"].encode("utf-8")
            if sha256_bytes(content) != operation["after_sha256"]:
                raise MaestroError(
                    f"EXPERTISE_{label}_PLAN_TAMPERED",
                    f"Content hash mismatch: {path}",
                    exit_code=3,
                )
        originals[target] = target.read_bytes() if target.exists() else None
    return originals


def _apply_publication_operations(
    repo: Path,
    operations: list[dict[str, Any]],
    originals: dict[Path, bytes | None],
) -> None:
    try:
        for operation in operations:
            target = safe_target(repo, operation["path"])
            if operation["op"] == "delete":
                target.unlink()
            else:
                atomic_write(target, operation["content"].encode("utf-8"))
        load_expertise_catalog(repo)
    except BaseException:
        for target, content in reversed(list(originals.items())):
            if content is None:
                if target.exists() and target.is_file():
                    target.unlink()
            else:
                atomic_write(target, content)
        raise


def _published_skill_root(plan: dict[str, Any]) -> str:
    pack_paths = [
        operation["path"]
        for operation in plan["operations"]
        if operation["op"] != "delete"
        and Path(operation["path"]).name == PROJECT_PACK_FILENAME
    ]
    if len(pack_paths) != 1:
        raise MaestroError(
            "EXPERTISE_PUBLICATION_PLAN_INVALID",
            "Publication plan must contain exactly one Expertise Pack file.",
            exit_code=3,
        )
    return Path(pack_paths[0]).parent.as_posix()


def apply_expertise_activation_plan(
    plan_path: str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=ACTIVATION_PLAN_VERSION,
        command="expertise-activate",
        allowed_fields=PUBLICATION_PLAN_FIELDS,
        label="ACTIVATION",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="ACTIVATION",
    )
    fresh = build_expertise_activation_plan(
        repo,
        candidate_id=plan["candidate_id"],
        approval_ref=plan["approval_ref"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_ACTIVATION_PLAN_STALE",
            "Candidate, project configuration, or destination changed after preview.",
            exit_code=3,
        )

    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=False,
        project_only=False,
        label="ACTIVATION",
    )
    skill_root = _published_skill_root(plan)
    _apply_publication_operations(repo, plan["operations"], originals)

    return {
        "schema_version": "maestro_expertise_activation_result_v1",
        "status": "applied",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "changed_paths": [
            operation["path"] for operation in plan["operations"]
        ],
        "git_stage_paths": [
            ".maestro/project.json",
            skill_root,
        ],
        "candidate_retained": True,
        "writes_performed": True,
    }


def apply_expertise_update_plan(
    plan_path: str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=UPDATE_PLAN_VERSION,
        command="expertise-update",
        allowed_fields=PUBLICATION_PLAN_FIELDS,
        label="UPDATE",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="UPDATE",
    )
    fresh = build_expertise_update_plan(
        repo,
        candidate_id=plan["candidate_id"],
        approval_ref=plan["approval_ref"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_UPDATE_PLAN_STALE",
            "Candidate or active project Expertise changed after preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=True,
        project_only=False,
        label="UPDATE",
    )
    skill_root = _published_skill_root(plan)
    _apply_publication_operations(repo, plan["operations"], originals)
    pack_path = f"{skill_root}/{PROJECT_PACK_FILENAME}"
    catalog = load_expertise_catalog(repo)
    updated = next(
        pack
        for pack in catalog
        if pack["_maestro"]["origin"] == "project"
        and pack["_maestro"]["pack_path"] == pack_path
    )
    return {
        "schema_version": "maestro_expertise_update_result_v1",
        "status": "applied",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "expertise_pack_id": updated["expertise_pack_id"],
        "version": updated["version"],
        "changed_paths": [
            operation["path"] for operation in plan["operations"]
        ],
        "git_stage_paths": [
            skill_root,
        ],
        "candidate_retained": True,
        "writes_performed": True,
    }


def apply_expertise_deactivation_plan(
    plan_path: str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    allowed_fields = {
        "schema_version",
        "command",
        "repo_realpath",
        "expertise_pack_id",
        "pack_path",
        "definition_digest",
        "operations",
        "warnings",
        "writes_performed",
        "plan_id",
        "plan_digest",
    }
    plan = _read_publication_plan(
        plan_path,
        schema_version=DEACTIVATION_PLAN_VERSION,
        command="expertise-deactivate",
        allowed_fields=allowed_fields,
        label="DEACTIVATION",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="DEACTIVATION",
    )
    fresh = build_expertise_deactivation_plan(
        repo,
        expertise_pack_id=plan["expertise_pack_id"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_DEACTIVATION_PLAN_STALE",
            "Active project Expertise or project configuration changed after preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=False,
        project_only=True,
        label="DEACTIVATION",
    )
    _apply_publication_operations(repo, plan["operations"], originals)
    return {
        "schema_version": "maestro_expertise_deactivation_result_v1",
        "status": "applied",
        "repo_root": str(repo),
        "expertise_pack_id": plan["expertise_pack_id"],
        "preserved_pack_path": plan["pack_path"],
        "changed_paths": [".maestro/project.json"],
        "git_stage_paths": [".maestro/project.json"],
        "writes_performed": True,
    }
