from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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
