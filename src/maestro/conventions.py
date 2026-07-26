from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from .decisions import repository_revision
from .documents import frontmatter_fields, frontmatter_list
from .errors import MaestroError
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    file_sha256,
    read_json,
    safe_target,
    sha256_text,
)

CONVENTION_DRAFT_PLAN_VERSION = "maestro_convention_draft_plan_v1"
CONVENTION_LIFECYCLE_PLAN_VERSION = "maestro_convention_lifecycle_plan_v1"
CONVENTION_INDEX_BEGIN = "<!-- MAESTRO:CONVENTIONS:BEGIN -->"
CONVENTION_INDEX_END = "<!-- MAESTRO:CONVENTIONS:END -->"
APPROVAL_REF_PATTERN = re.compile(
    r"^(owner_decision|held_out_evaluation):\S.+$"
)
TOPIC_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_BODY_SECTIONS = (
    "Rule",
    "Applies when",
    "Does not apply",
    "Evidence",
    "Verification",
    "Exceptions",
)


def _required_text(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaestroError(
            "CONVENTION_DRAFT_INVALID",
            f"{field} must be a non-empty string.",
        )
    result = value.strip()
    if "\x00" in result:
        raise MaestroError(
            "CONVENTION_DRAFT_INVALID",
            f"{field} contains an unsupported null byte.",
        )
    return result


def _required_list(values: list[str] | None, field: str) -> list[str]:
    result = list(
        dict.fromkeys(
            _required_text(value, field)
            for value in (values or [])
        )
    )
    if not result:
        raise MaestroError(
            "CONVENTION_DRAFT_INVALID",
            f"{field} requires at least one value.",
        )
    return result


def _validate_scope(scope: str) -> None:
    normalized = scope.replace("\\", "/")
    if (
        normalized.startswith("/")
        or normalized.startswith("./")
        or ".." in Path(normalized).parts
    ):
        raise MaestroError(
            "CONVENTION_SCOPE_INVALID",
            f"Convention scope must be a repository-relative path or topic: {scope!r}",
        )


def _bullets(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def _render_draft(
    *,
    topic: str,
    summary: str,
    scopes: list[str],
    owner: str,
    rule: str,
    applies_when: list[str],
    does_not_apply: list[str],
    evidence: list[str],
    verification: list[str],
    exceptions: list[str],
) -> str:
    return (
        "---\n"
        "maestro_doc: 1\n"
        f"id: convention-{topic}\n"
        "type: convention\n"
        "status: draft\n"
        "authority: repository\n"
        f"owner: {json.dumps(owner, ensure_ascii=False)}\n"
        f"summary: {json.dumps(summary, ensure_ascii=False)}\n"
        f"topic: {topic}\n"
        f"scope: {json.dumps(scopes, ensure_ascii=False)}\n"
        "last_verified: null\n"
        "supersedes: []\n"
        "sensitivity: internal\n"
        "---\n\n"
        f"# Convention: {topic}\n\n"
        "## Rule\n\n"
        f"{rule}\n\n"
        "## Applies when\n\n"
        f"{_bullets(applies_when)}\n\n"
        "## Does not apply\n\n"
        f"{_bullets(does_not_apply)}\n\n"
        "## Evidence\n\n"
        f"{_bullets(evidence)}\n\n"
        "## Verification\n\n"
        f"{_bullets(verification)}\n\n"
        "## Exceptions\n\n"
        f"{_bullets(exceptions or ['None currently approved.'])}\n"
    )


def build_convention_draft_plan(
    repo_path: str | Path,
    *,
    topic: str | None,
    summary: str | None,
    scopes: list[str] | None,
    owner: str | None,
    rule: str | None,
    applies_when: list[str] | None,
    does_not_apply: list[str] | None,
    evidence: list[str] | None,
    verification: list[str] | None,
    exceptions: list[str] | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    project = safe_target(repo, ".maestro/project.json")
    if project.is_symlink() or not project.is_file():
        raise MaestroError(
            "PROJECT_NOT_INITIALIZED",
            "Run and review maestro init before drafting a project Convention.",
        )

    normalized_topic = _required_text(topic, "topic")
    if not TOPIC_PATTERN.fullmatch(normalized_topic):
        raise MaestroError(
            "CONVENTION_TOPIC_INVALID",
            "topic must be a lowercase ASCII slug such as api-error-contract.",
        )
    normalized_summary = _required_text(summary, "summary")
    normalized_owner = _required_text(owner, "owner")
    normalized_rule = _required_text(rule, "rule")
    normalized_scopes = _required_list(scopes, "scope")
    for scope in normalized_scopes:
        _validate_scope(scope)
    normalized_applies = _required_list(applies_when, "applies-when")
    normalized_excludes = _required_list(does_not_apply, "does-not-apply")
    normalized_evidence = _required_list(evidence, "evidence")
    normalized_verification = _required_list(verification, "verification")
    normalized_exceptions = list(
        dict.fromkeys(
            _required_text(value, "exception")
            for value in (exceptions or [])
        )
    )

    relative_path = f"docs/conventions/{normalized_topic}.md"
    target = safe_target(repo, relative_path)
    before = file_sha256(target)
    if before is not None:
        raise MaestroError(
            "CONVENTION_ALREADY_EXISTS",
            f"Review the existing topic authority instead of creating a duplicate: {relative_path}",
        )
    content = _render_draft(
        topic=normalized_topic,
        summary=normalized_summary,
        scopes=normalized_scopes,
        owner=normalized_owner,
        rule=normalized_rule,
        applies_when=normalized_applies,
        does_not_apply=normalized_excludes,
        evidence=normalized_evidence,
        verification=normalized_verification,
        exceptions=normalized_exceptions,
    )
    base = {
        "schema_version": CONVENTION_DRAFT_PLAN_VERSION,
        "command": "convention-draft",
        "repo_realpath": str(repo),
        "operation": {
            "op": "create",
            "path": relative_path,
            "before_sha256": None,
            "after_sha256": sha256_text(content),
            "content": content,
        },
        "warnings": [
            "The result remains draft and is excluded from active document selection.",
            "Activation requires a separate owner decision or accepted held-out evaluation.",
        ],
        "writes_performed": False,
    }
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def _validate_draft_content(path: str, content: str) -> None:
    metadata = frontmatter_fields(content)
    topic = metadata.get("topic", "")
    expected_path = f"docs/conventions/{topic}.md"
    required_metadata = {
        "maestro_doc": "1",
        "id": f"convention-{topic}",
        "type": "convention",
        "status": "draft",
        "authority": "repository",
        "last_verified": "null",
        "supersedes": "[]",
        "sensitivity": "internal",
    }
    if (
        not TOPIC_PATTERN.fullmatch(topic)
        or path != expected_path
        or any(metadata.get(key) != value for key, value in required_metadata.items())
        or not metadata.get("owner", "").strip()
        or not metadata.get("summary", "").strip()
        or not frontmatter_list(metadata.get("scope"))
    ):
        raise MaestroError(
            "CONVENTION_DRAFT_PLAN_INVALID",
            "Convention draft content does not satisfy the managed draft contract.",
            exit_code=3,
        )
    for section in REQUIRED_BODY_SECTIONS:
        if f"## {section}\n" not in content:
            raise MaestroError(
                "CONVENTION_DRAFT_PLAN_INVALID",
                f"Convention draft is missing the {section!r} section.",
                exit_code=3,
            )


def apply_convention_draft_plan(
    plan_path: str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = read_json(Path(plan_path).expanduser().resolve())
    allowed_plan_fields = {
        "schema_version",
        "command",
        "repo_realpath",
        "operation",
        "warnings",
        "plan_id",
        "plan_digest",
        "writes_performed",
    }
    if set(plan) != allowed_plan_fields:
        raise MaestroError(
            "CONVENTION_DRAFT_PLAN_INVALID",
            "Convention draft plan has unsupported fields.",
            exit_code=3,
        )
    if (
        plan.get("schema_version") != CONVENTION_DRAFT_PLAN_VERSION
        or plan.get("command") != "convention-draft"
        or plan.get("writes_performed") is not False
    ):
        raise MaestroError(
            "CONVENTION_DRAFT_PLAN_INVALID",
            "Unsupported Convention draft plan.",
            exit_code=3,
        )
    unsigned = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(unsigned))
    if plan.get("plan_digest") != digest or plan.get("plan_id") != digest[:20]:
        raise MaestroError(
            "PLAN_TAMPERED",
            "Convention draft plan digest does not match its contents.",
            exit_code=3,
        )

    repo = ensure_repo(repo_override or plan.get("repo_realpath", ""))
    if str(repo) != plan.get("repo_realpath"):
        raise MaestroError(
            "PLAN_REPO_MISMATCH",
            "Convention draft plan belongs to a different repository.",
            exit_code=3,
        )
    operation = plan.get("operation")
    expected_operation_fields = {
        "op",
        "path",
        "before_sha256",
        "after_sha256",
        "content",
    }
    if (
        not isinstance(operation, dict)
        or set(operation) != expected_operation_fields
        or operation.get("op") != "create"
        or operation.get("before_sha256") is not None
        or not isinstance(operation.get("path"), str)
        or not isinstance(operation.get("content"), str)
    ):
        raise MaestroError(
            "CONVENTION_DRAFT_PLAN_INVALID",
            "Convention draft plan operation is invalid.",
            exit_code=3,
        )
    _validate_draft_content(operation["path"], operation["content"])
    if sha256_text(operation["content"]) != operation.get("after_sha256"):
        raise MaestroError(
            "PLAN_TAMPERED",
            "Convention draft content digest does not match.",
            exit_code=3,
        )
    target = safe_target(repo, operation["path"])
    if file_sha256(target) is not None:
        raise MaestroError(
            "PLAN_STALE",
            f"Convention path changed after preview: {operation['path']}",
            exit_code=3,
        )
    atomic_write(target, operation["content"].encode("utf-8"))
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "convention-draft",
        "status": "applied",
        "repo_root": str(repo),
        "plan_id": plan["plan_id"],
        "changed_paths": [operation["path"]],
        "writes_performed": True,
    }


def _markdown_entrypoint(repo: Path) -> tuple[str, str]:
    project = read_json(safe_target(repo, ".maestro/project.json"))
    documentation = project.get("documentation")
    if (
        not isinstance(documentation, dict)
        or documentation.get("provider") != "markdown"
        or not isinstance(documentation.get("entrypoint"), str)
    ):
        raise MaestroError(
            "CONVENTION_PROVIDER_UNSUPPORTED",
            "Typed Convention lifecycle commands currently require the Markdown provider.",
        )
    path = documentation["entrypoint"]
    target = safe_target(repo, path)
    if target.is_symlink() or not target.is_file():
        raise MaestroError(
            "CONVENTION_ENTRYPOINT_INVALID",
            f"Documentation entrypoint must be a regular repository file: {path}",
        )
    return path, target.read_text(encoding="utf-8")


def _active_topic_paths(repo: Path, topic: str) -> list[str]:
    root = safe_target(repo, "docs/conventions")
    if not root.exists():
        return []
    result: list[str] = []
    for path in sorted(root.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        metadata = frontmatter_fields(path.read_text(encoding="utf-8"))
        if metadata.get("status") == "active" and metadata.get("topic") == topic:
            result.append(path.relative_to(repo).as_posix())
    return result


def _all_active_paths(repo: Path) -> list[str]:
    root = safe_target(repo, "docs/conventions")
    if not root.exists():
        return []
    result: list[str] = []
    for path in sorted(root.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        metadata = frontmatter_fields(path.read_text(encoding="utf-8"))
        if metadata.get("status") == "active":
            result.append(path.relative_to(repo).as_posix())
    return result


def _render_active_from_draft(content: str) -> str:
    if content.count("status: draft") != 1 or content.count(
        "last_verified: null"
    ) != 1:
        raise MaestroError(
            "CONVENTION_ACTIVATION_CONTENT_INVALID",
            "Convention draft status or verification marker is ambiguous.",
        )
    return content.replace("status: draft", "status: active", 1).replace(
        "last_verified: null",
        f"last_verified: {date.today().isoformat()}",
        1,
    )


def _validate_active_content(path: str, content: str) -> None:
    metadata = frontmatter_fields(content)
    topic = metadata.get("topic", "")
    expected_path = f"docs/conventions/{topic}.md"
    try:
        date.fromisoformat(metadata.get("last_verified", ""))
    except ValueError as exc:
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Active Convention last_verified must be an ISO date.",
            exit_code=3,
        ) from exc
    required_metadata = {
        "maestro_doc": "1",
        "id": f"convention-{topic}",
        "type": "convention",
        "status": "active",
        "authority": "repository",
        "supersedes": "[]",
        "sensitivity": "internal",
    }
    if (
        not TOPIC_PATTERN.fullmatch(topic)
        or path != expected_path
        or any(
            metadata.get(key) != value
            for key, value in required_metadata.items()
        )
        or not metadata.get("owner", "").strip()
        or not metadata.get("summary", "").strip()
        or not frontmatter_list(metadata.get("scope"))
    ):
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Active Convention content does not satisfy the managed contract.",
            exit_code=3,
        )
    for section in REQUIRED_BODY_SECTIONS:
        if f"## {section}\n" not in content:
            raise MaestroError(
                "CONVENTION_LIFECYCLE_PLAN_INVALID",
                f"Active Convention is missing the {section!r} section.",
                exit_code=3,
            )


def _convention_index_content(
    entrypoint: str,
    topic_paths: list[str],
) -> str:
    relative_links = [
        Path(path).relative_to("docs").as_posix()
        if path.startswith("docs/")
        else path
        for path in sorted(set(topic_paths))
    ]
    block = (
        f"{CONVENTION_INDEX_BEGIN}\n"
        "## Project Conventions\n\n"
        + "\n".join(
            f"- [{Path(path).stem}]({path})" for path in relative_links
        )
        + f"\n{CONVENTION_INDEX_END}"
    )
    pattern = re.compile(
        re.escape(CONVENTION_INDEX_BEGIN)
        + r".*?"
        + re.escape(CONVENTION_INDEX_END),
        re.DOTALL,
    )
    if pattern.search(entrypoint):
        return pattern.sub(block, entrypoint)
    return entrypoint.rstrip() + "\n\n" + block + "\n"


def _approval_evidence(
    repo: Path,
    *,
    basis: str | None,
    approval_ref: str | None,
    verification_artifact: str | None,
    decision_summary: str | None,
) -> dict[str, Any]:
    if basis not in {"owner_decision", "held_out_evaluation"}:
        raise MaestroError(
            "CONVENTION_APPROVAL_INVALID",
            "basis must be owner_decision or held_out_evaluation.",
        )
    if (
        not isinstance(approval_ref, str)
        or APPROVAL_REF_PATTERN.fullmatch(approval_ref) is None
        or not approval_ref.startswith(f"{basis}:")
    ):
        raise MaestroError(
            "CONVENTION_APPROVAL_INVALID",
            "approval-ref must match the selected basis and contain a non-empty reference.",
        )
    summary = decision_summary.strip() if isinstance(
        decision_summary, str
    ) else None
    if basis == "owner_decision" and not summary:
        raise MaestroError(
            "CONVENTION_APPROVAL_INVALID",
            "owner_decision requires a bounded decision summary.",
        )
    if summary is not None and (len(summary) > 500 or "\x00" in summary):
        raise MaestroError(
            "CONVENTION_APPROVAL_INVALID",
            "decision-summary must be at most 500 characters.",
        )
    artifact_path = _required_text(
        verification_artifact,
        "verification-artifact",
    )
    artifact = safe_target(repo, artifact_path)
    digest = file_sha256(artifact)
    if artifact.is_symlink() or digest is None:
        raise MaestroError(
            "CONVENTION_VERIFICATION_ARTIFACT_INVALID",
            "verification-artifact must be a regular repository-local file.",
        )
    return {
        "basis": basis,
        "approval_ref": approval_ref,
        "decision_summary": summary,
        "verification_artifact": {
            "path": artifact_path,
            "sha256": digest,
        },
    }


def _text_operation(
    repo: Path,
    path: str,
    content: str,
) -> dict[str, Any]:
    return {
        "op": "replace" if file_sha256(safe_target(repo, path)) else "create",
        "path": path,
        "before_sha256": file_sha256(safe_target(repo, path)),
        "after_sha256": sha256_text(content),
        "content": content,
    }


def _finalize_lifecycle_plan(base: dict[str, Any]) -> dict[str, Any]:
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def build_convention_activation_plan(
    repo_path: str | Path,
    *,
    topic: str | None,
    basis: str | None,
    approval_ref: str | None,
    verification_artifact: str | None,
    decision_summary: str | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    normalized_topic = _required_text(topic, "topic")
    if TOPIC_PATTERN.fullmatch(normalized_topic) is None:
        raise MaestroError(
            "CONVENTION_TOPIC_INVALID",
            "topic must be a lowercase ASCII slug.",
        )
    target_path = f"docs/conventions/{normalized_topic}.md"
    target = safe_target(repo, target_path)
    if target.is_symlink() or not target.is_file():
        raise MaestroError(
            "CONVENTION_DRAFT_MISSING",
            f"Convention draft is missing: {target_path}",
        )
    draft = target.read_text(encoding="utf-8")
    _validate_draft_content(target_path, draft)
    duplicates = [
        path for path in _active_topic_paths(repo, normalized_topic)
        if path != target_path
    ]
    if duplicates:
        raise MaestroError(
            "CONVENTION_TOPIC_DUPLICATE",
            f"Another active authority already exists: {', '.join(duplicates)}",
        )
    active = _render_active_from_draft(draft)
    _validate_active_content(target_path, active)
    entrypoint_path, entrypoint = _markdown_entrypoint(repo)
    active_paths = [*_all_active_paths(repo), target_path]
    indexed = _convention_index_content(entrypoint, active_paths)
    evidence = _approval_evidence(
        repo,
        basis=basis,
        approval_ref=approval_ref,
        verification_artifact=verification_artifact,
        decision_summary=decision_summary,
    )
    return _finalize_lifecycle_plan(
        {
            "schema_version": CONVENTION_LIFECYCLE_PLAN_VERSION,
            "command": "convention-activate",
            "repo_realpath": str(repo),
            "base_revision": repository_revision(repo),
            "topic": normalized_topic,
            **evidence,
            "operations": [
                _text_operation(repo, target_path, active),
                _text_operation(repo, entrypoint_path, indexed),
            ],
            "warnings": [
                "Activation changes repository documentation authority.",
                "The verification artifact is bound by path and digest but is not executed by this command.",
            ],
            "writes_performed": False,
        }
    )


def build_convention_update_plan(
    repo_path: str | Path,
    *,
    topic: str | None,
    summary: str | None,
    scopes: list[str] | None,
    owner: str | None,
    rule: str | None,
    applies_when: list[str] | None,
    does_not_apply: list[str] | None,
    evidence: list[str] | None,
    verification: list[str] | None,
    exceptions: list[str] | None,
    basis: str | None,
    approval_ref: str | None,
    verification_artifact: str | None,
    decision_summary: str | None = None,
    allow_scope_expansion: bool = False,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    normalized_topic = _required_text(topic, "topic")
    if TOPIC_PATTERN.fullmatch(normalized_topic) is None:
        raise MaestroError(
            "CONVENTION_TOPIC_INVALID",
            "topic must be a lowercase ASCII slug.",
        )
    target_path = f"docs/conventions/{normalized_topic}.md"
    target = safe_target(repo, target_path)
    if target.is_symlink() or not target.is_file():
        raise MaestroError(
            "CONVENTION_ACTIVE_MISSING",
            f"Active Convention is missing: {target_path}",
        )
    current = target.read_text(encoding="utf-8")
    _validate_active_content(target_path, current)
    duplicates = [
        path for path in _active_topic_paths(repo, normalized_topic)
        if path != target_path
    ]
    if duplicates:
        raise MaestroError(
            "CONVENTION_TOPIC_DUPLICATE",
            f"Another active authority already exists: {', '.join(duplicates)}",
        )
    normalized_scopes = _required_list(scopes, "scope")
    for scope in normalized_scopes:
        _validate_scope(scope)
    current_scopes = set(
        frontmatter_list(frontmatter_fields(current).get("scope"))
    )
    added_scopes = sorted(set(normalized_scopes) - current_scopes)
    if added_scopes and not allow_scope_expansion:
        raise MaestroError(
            "CONVENTION_SCOPE_EXPANSION_REQUIRES_APPROVAL",
            f"Scope expansion requires --allow-scope-expansion: {', '.join(added_scopes)}",
        )
    updated = _render_active_from_draft(
        _render_draft(
            topic=normalized_topic,
            summary=_required_text(summary, "summary"),
            scopes=normalized_scopes,
            owner=_required_text(owner, "owner"),
            rule=_required_text(rule, "rule"),
            applies_when=_required_list(applies_when, "applies-when"),
            does_not_apply=_required_list(
                does_not_apply,
                "does-not-apply",
            ),
            evidence=_required_list(evidence, "evidence"),
            verification=_required_list(verification, "verification"),
            exceptions=list(
                dict.fromkeys(
                    _required_text(value, "exception")
                    for value in (exceptions or [])
                )
            ),
        )
    )
    _validate_active_content(target_path, updated)
    entrypoint_path, entrypoint = _markdown_entrypoint(repo)
    indexed = _convention_index_content(
        entrypoint,
        _all_active_paths(repo),
    )
    approval = _approval_evidence(
        repo,
        basis=basis,
        approval_ref=approval_ref,
        verification_artifact=verification_artifact,
        decision_summary=decision_summary,
    )
    return _finalize_lifecycle_plan(
        {
            "schema_version": CONVENTION_LIFECYCLE_PLAN_VERSION,
            "command": "convention-update",
            "repo_realpath": str(repo),
            "base_revision": repository_revision(repo),
            "topic": normalized_topic,
            **approval,
            "operations": [
                _text_operation(repo, target_path, updated),
                _text_operation(repo, entrypoint_path, indexed),
            ],
            "warnings": [
                "This plan updates exactly one active Convention topic.",
                "Supersession is intentionally not inferred by this command.",
            ],
            "writes_performed": False,
        }
    )


def apply_convention_lifecycle_plan(
    plan_path: str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = read_json(Path(plan_path).expanduser().resolve())
    allowed = {
        "schema_version",
        "command",
        "repo_realpath",
        "base_revision",
        "topic",
        "basis",
        "approval_ref",
        "decision_summary",
        "verification_artifact",
        "operations",
        "warnings",
        "writes_performed",
        "plan_id",
        "plan_digest",
    }
    if (
        set(plan) != allowed
        or plan.get("schema_version") != CONVENTION_LIFECYCLE_PLAN_VERSION
        or plan.get("command")
        not in {"convention-activate", "convention-update"}
        or plan.get("writes_performed") is not False
    ):
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Unsupported Convention lifecycle plan.",
            exit_code=3,
        )
    unsigned = {
        key: value for key, value in plan.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(unsigned))
    if plan.get("plan_digest") != digest or plan.get("plan_id") != digest[:20]:
        raise MaestroError(
            "PLAN_TAMPERED",
            "Convention lifecycle plan digest does not match.",
            exit_code=3,
        )
    repo = ensure_repo(repo_override or plan.get("repo_realpath", ""))
    if str(repo) != plan.get("repo_realpath"):
        raise MaestroError(
            "PLAN_REPO_MISMATCH",
            "Convention lifecycle plan belongs to a different repository.",
            exit_code=3,
        )
    base_revision = plan.get("base_revision")
    if (
        not isinstance(base_revision, dict)
        or set(base_revision)
        != {"kind", "head", "state_digest", "dirty_path_count"}
        or base_revision.get("kind") not in {"git", "unavailable"}
    ):
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Convention lifecycle base revision is invalid.",
            exit_code=3,
        )
    if (
        base_revision["kind"] == "git"
        and (
            not isinstance(base_revision.get("head"), str)
            or not base_revision["head"]
            or not isinstance(base_revision.get("state_digest"), str)
            or re.fullmatch(
                r"[a-f0-9]{64}",
                base_revision["state_digest"],
            )
            is None
            or not isinstance(base_revision.get("dirty_path_count"), int)
            or isinstance(base_revision["dirty_path_count"], bool)
            or base_revision["dirty_path_count"] < 0
        )
    ) or (
        base_revision["kind"] == "unavailable"
        and any(
            base_revision.get(field) is not None
            for field in ("head", "state_digest", "dirty_path_count")
        )
    ):
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Convention lifecycle base revision values are invalid.",
            exit_code=3,
        )
    basis = plan.get("basis")
    approval_ref = plan.get("approval_ref")
    decision_summary = plan.get("decision_summary")
    if (
        basis not in {"owner_decision", "held_out_evaluation"}
        or not isinstance(approval_ref, str)
        or APPROVAL_REF_PATTERN.fullmatch(approval_ref) is None
        or not approval_ref.startswith(f"{basis}:")
        or (
            basis == "owner_decision"
            and (
                not isinstance(decision_summary, str)
                or not decision_summary.strip()
            )
        )
        or (
            decision_summary is not None
            and (
                not isinstance(decision_summary, str)
                or len(decision_summary) > 500
                or "\x00" in decision_summary
            )
        )
    ):
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Convention lifecycle approval evidence is invalid.",
            exit_code=3,
        )
    current_revision = repository_revision(repo)
    if (
        base_revision["kind"] == "git"
        and current_revision != base_revision
    ):
        raise MaestroError(
            "PLAN_STALE",
            "Repository checkout changed after Convention preview.",
            exit_code=3,
        )
    artifact = plan.get("verification_artifact")
    if (
        not isinstance(artifact, dict)
        or set(artifact) != {"path", "sha256"}
        or file_sha256(safe_target(repo, artifact.get("path", "")))
        != artifact.get("sha256")
    ):
        raise MaestroError(
            "PLAN_STALE",
            "Convention verification artifact changed after preview.",
            exit_code=3,
        )
    topic = plan.get("topic")
    if not isinstance(topic, str) or TOPIC_PATTERN.fullmatch(topic) is None:
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Convention lifecycle topic is invalid.",
            exit_code=3,
        )
    target_path = f"docs/conventions/{topic}.md"
    duplicates = [
        path for path in _active_topic_paths(repo, topic)
        if path != target_path
    ]
    if duplicates:
        raise MaestroError(
            "CONVENTION_TOPIC_DUPLICATE",
            f"Another active authority already exists: {', '.join(duplicates)}",
            exit_code=3,
        )
    entrypoint_path, _ = _markdown_entrypoint(repo)
    operations = plan.get("operations")
    if (
        not isinstance(operations, list)
        or len(operations) != 2
        or {item.get("path") for item in operations if isinstance(item, dict)}
        != {target_path, entrypoint_path}
    ):
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Convention lifecycle operations are not the bounded target and index pair.",
            exit_code=3,
        )
    originals: dict[Path, bytes | None] = {}
    for operation in operations:
        if (
            not isinstance(operation, dict)
            or set(operation)
            != {
                "op",
                "path",
                "before_sha256",
                "after_sha256",
                "content",
            }
            or operation.get("op") not in {"create", "replace"}
            or not isinstance(operation.get("content"), str)
            or sha256_text(operation["content"])
            != operation.get("after_sha256")
        ):
            raise MaestroError(
                "CONVENTION_LIFECYCLE_PLAN_INVALID",
                "Convention lifecycle operation is invalid.",
                exit_code=3,
            )
        path = safe_target(repo, operation["path"])
        if file_sha256(path) != operation.get("before_sha256"):
            raise MaestroError(
                "PLAN_STALE",
                f"Convention target changed after preview: {operation['path']}",
                exit_code=3,
            )
        originals[path] = path.read_bytes() if path.is_file() else None
        if operation["path"] == target_path:
            _validate_active_content(operation["path"], operation["content"])
        elif (
            CONVENTION_INDEX_BEGIN not in operation["content"]
            or CONVENTION_INDEX_END not in operation["content"]
        ):
            raise MaestroError(
                "CONVENTION_LIFECYCLE_PLAN_INVALID",
                "Convention document index marker is missing.",
                exit_code=3,
            )
    changed: list[str] = []
    try:
        for operation in operations:
            target = safe_target(repo, operation["path"])
            atomic_write(target, operation["content"].encode("utf-8"))
            changed.append(operation["path"])
    except BaseException:
        for target, original in originals.items():
            if original is not None:
                atomic_write(target, original)
        raise
    return {
        "schema_version": "maestro_command_result_v1",
        "command": plan["command"],
        "status": "applied",
        "repo_root": str(repo),
        "plan_id": plan["plan_id"],
        "topic": topic,
        "basis": plan["basis"],
        "verification_artifact": plan["verification_artifact"],
        "changed_paths": changed,
        "writes_performed": True,
    }
