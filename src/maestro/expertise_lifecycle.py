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
from .registry import load_registry, validate_registry
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


def expertise_inventory(repo_path: str | Path) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    catalog = load_expertise_catalog(repo)
    entries = [
        {
            "expertise_pack_id": pack["expertise_pack_id"],
            "skill_id": pack["skill_id"],
            "status": pack["status"],
            "portability": pack["portability"],
            "origin": pack["_maestro"]["origin"],
            "pack_path": pack["_maestro"]["pack_path"],
            "definition_digest": pack["_maestro"]["definition_digest"],
            "extends": pack["_maestro"]["base"],
        }
        for pack in catalog
    ]
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
    if not isinstance(approval_ref, str) or APPROVAL_PATTERN.fullmatch(approval_ref) is None:
        raise MaestroError(
            "EXPERTISE_ACTIVATION_APPROVAL_INVALID",
            "approval-ref must be owner_decision:<ref> or held_out_evaluation:<ref>.",
        )
    candidate_root, candidate = _read_candidate(repo, candidate_id)
    if date.fromisoformat(candidate["review_after"]) < date.today():
        raise MaestroError(
            "EXPERTISE_CANDIDATE_EXPIRED",
            "Expired candidates must be revalidated before activation.",
        )
    pack = read_json(
        safe_target(candidate_root, f"draft/{PROJECT_PACK_FILENAME}")
    )
    _validate_activation_pack(candidate, pack)

    skill_id = pack["skill_id"]
    destination_root = f".agents/skills/{skill_id}"
    if safe_target(repo, destination_root).exists():
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_EXISTS",
            f"Project Skill already exists: {destination_root}",
        )
    project_path = safe_target(repo, ".maestro/project.json")
    project = read_json(project_path)
    expertise = project.get("expertise", {"active_pack_paths": []})
    if (
        not isinstance(expertise, dict)
        or set(expertise) != {"active_pack_paths"}
        or not isinstance(expertise["active_pack_paths"], list)
    ):
        raise MaestroError(
            "PROJECT_EXPERTISE_CONFIG_INVALID",
            "Repair project.json expertise configuration before activation.",
        )
    pack_path = f"{destination_root}/{PROJECT_PACK_FILENAME}"
    if git_ignored(repo, pack_path) is True:
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_IGNORED",
            "Active project Expertise must not be Git-ignored. "
            "Repair the project ignore policy before activation.",
        )
    if pack_path in expertise["active_pack_paths"]:
        raise MaestroError(
            "EXPERTISE_ALREADY_ACTIVE",
            f"Project Expertise is already enabled: {pack_path}",
        )

    source_to_destination = {
        f"draft/{PROJECT_PACK_FILENAME}": pack_path,
        "draft/SKILL.md": f"{destination_root}/SKILL.md",
        "draft/agents/openai.yaml": f"{destination_root}/agents/openai.yaml",
        "evidence/sources.json": f"{destination_root}/evidence/sources.json",
        "evals/cases.json": f"{destination_root}/evals/cases.json",
    }
    for guide in pack["guides"]:
        guide_id = guide["guide_id"]
        source_to_destination[
            f"draft/references/{guide_id}.md"
        ] = f"{destination_root}/references/{guide_id}.md"

    operations: list[dict[str, Any]] = []
    candidate_file_digests: dict[str, str] = {}
    for source, destination in sorted(source_to_destination.items()):
        content = _read_text_file(candidate_root, source)
        candidate_file_digests[source] = sha256_text(content)
        operations.append(
            {
                "op": "create",
                "path": destination,
                "before_sha256": None,
                "after_sha256": sha256_text(content),
                "content": content,
            }
        )

    activation = {
        "schema_version": "maestro_expertise_activation_v1",
        "candidate_id": candidate_id,
        "candidate_digest": sha256_text(
            canonical_json(candidate_file_digests)
        ),
        "approval_ref": approval_ref,
        "source_candidate_path": (
            f".maestro/state/candidates/expertise/{candidate_id}"
        ),
    }
    activation_content = pretty_json(activation)
    operations.append(
        {
            "op": "create",
            "path": f"{destination_root}/activation.json",
            "before_sha256": None,
            "after_sha256": sha256_text(activation_content),
            "content": activation_content,
        }
    )

    updated_project = copy.deepcopy(project)
    updated_project["expertise"] = {
        "active_pack_paths": [
            *expertise["active_pack_paths"],
            pack_path,
        ]
    }
    project_content = pretty_json(updated_project)
    operations.append(
        {
            "op": "replace",
            "path": ".maestro/project.json",
            "before_sha256": file_sha256(project_path),
            "after_sha256": sha256_text(project_content),
            "content": project_content,
        }
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
            "The ignored candidate is retained for rollback and audit.",
        ],
        "writes_performed": False,
    }
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def apply_expertise_activation_plan(
    plan_path: str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = read_json(Path(plan_path).expanduser().resolve())
    allowed_fields = {
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
    if (
        set(plan) != allowed_fields
        or plan.get("schema_version") != ACTIVATION_PLAN_VERSION
        or plan.get("command") != "expertise-activate"
        or plan.get("writes_performed") is not False
    ):
        raise MaestroError(
            "EXPERTISE_ACTIVATION_PLAN_INVALID",
            "Unsupported Expertise activation plan.",
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
            "EXPERTISE_ACTIVATION_PLAN_TAMPERED",
            "Activation plan digest does not match its contents.",
            exit_code=3,
        )
    repo = ensure_repo(repo_override or plan["repo_realpath"])
    if str(repo) != plan["repo_realpath"]:
        raise MaestroError(
            "EXPERTISE_ACTIVATION_REPO_MISMATCH",
            "Activation plan belongs to a different repository.",
            exit_code=3,
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

    originals: dict[Path, bytes | None] = {}
    for operation in plan["operations"]:
        if (
            not isinstance(operation, dict)
            or set(operation)
            != {"op", "path", "before_sha256", "after_sha256", "content"}
            or operation.get("op") not in {"create", "replace"}
            or not isinstance(operation.get("path"), str)
            or not isinstance(operation.get("content"), str)
        ):
            raise MaestroError(
                "EXPERTISE_ACTIVATION_PLAN_INVALID",
                "Activation operation is invalid.",
                exit_code=3,
            )
        path = operation["path"]
        if path != ".maestro/project.json" and not path.startswith(
            ".agents/skills/"
        ):
            raise MaestroError(
                "EXPERTISE_ACTIVATION_PATH_INVALID",
                f"Activation may not write this path: {path}",
                exit_code=3,
            )
        target = safe_target(repo, path)
        if file_sha256(target) != operation["before_sha256"]:
            raise MaestroError(
                "EXPERTISE_ACTIVATION_PLAN_STALE",
                f"File changed after preview: {path}",
                exit_code=3,
            )
        content = operation["content"].encode("utf-8")
        if sha256_bytes(content) != operation["after_sha256"]:
            raise MaestroError(
                "EXPERTISE_ACTIVATION_PLAN_TAMPERED",
                f"Content hash mismatch: {path}",
                exit_code=3,
            )
        originals[target] = target.read_bytes() if target.exists() else None

    try:
        for operation in plan["operations"]:
            target = safe_target(repo, operation["path"])
            atomic_write(target, operation["content"].encode("utf-8"))
        load_expertise_catalog(repo)
    except Exception:
        for target, content in reversed(list(originals.items())):
            if content is None:
                if target.exists() and target.is_file():
                    target.unlink()
            else:
                atomic_write(target, content)
        raise

    return {
        "schema_version": "maestro_expertise_activation_result_v1",
        "status": "applied",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "changed_paths": [
            operation["path"] for operation in plan["operations"]
        ],
        "candidate_retained": True,
        "writes_performed": True,
    }
