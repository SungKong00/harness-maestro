from __future__ import annotations

import json
import re
from datetime import date, datetime
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
    pretty_json,
    read_json,
    safe_target,
    sha256_text,
)

CONVENTION_DRAFT_PLAN_VERSION = "maestro_convention_draft_plan_v1"
CONVENTION_LIFECYCLE_PLAN_VERSION = "maestro_convention_lifecycle_plan_v1"
CONVENTION_HELD_OUT_EVALUATION_VERSION = (
    "maestro_convention_held_out_evaluation_v1"
)
CONVENTION_EVALUATION_REQUEST_VERSION = (
    "maestro_convention_evaluation_request_v1"
)
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
HELD_OUT_CATEGORIES = {"positive", "negative_scope", "regression"}


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
    candidate_sha256: str,
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
    normalized_artifact_path = Path(artifact_path.replace("\\", "/"))
    if (
        normalized_artifact_path.is_absolute()
        or ".." in normalized_artifact_path.parts
        or artifact_path.startswith("./")
        or artifact_path.startswith(".git/")
        or artifact_path.startswith(".maestro/state/")
    ):
        raise MaestroError(
            "CONVENTION_VERIFICATION_ARTIFACT_INVALID",
            "verification-artifact must be a durable repository-local file outside .git and .maestro/state.",
        )
    artifact = safe_target(repo, artifact_path)
    digest = file_sha256(artifact)
    if artifact.is_symlink() or digest is None:
        raise MaestroError(
            "CONVENTION_VERIFICATION_ARTIFACT_INVALID",
            "verification-artifact must be a regular repository-local file.",
        )
    approval_strength = (
        "owner_attested"
        if basis == "owner_decision"
        else "held_out_verified"
    )
    if basis == "held_out_evaluation":
        validate_held_out_evaluation(
            repo,
            artifact,
            candidate_sha256=candidate_sha256,
        )
    return {
        "basis": basis,
        "approval_strength": approval_strength,
        "approval_ref": approval_ref,
        "decision_summary": summary,
        "verification_artifact": {
            "path": artifact_path,
            "sha256": digest,
        },
    }


def _bounded_line(value: Any, *, limit: int = 500) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= limit
        and not any(character in value for character in "\r\n\x00")
    )


def _valid_evaluation_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_held_out_evaluation(
    repo: Path,
    artifact: Path,
    *,
    candidate_sha256: str,
) -> dict[str, Any]:
    """Validate semantic evidence before it can activate a Convention."""

    value = read_json(artifact)
    expected_fields = {
        "schema_version",
        "candidate_sha256",
        "suite_sha256",
        "source_revision",
        "held_out",
        "cases",
        "critical_regressions",
        "verifier",
        "conditions",
    }
    if set(value) != expected_fields:
        raise MaestroError(
            "CONVENTION_HELD_OUT_EVALUATION_INVALID",
            "Held-out evaluation fields do not match the v1 contract.",
        )
    if (
        value.get("schema_version")
        != CONVENTION_HELD_OUT_EVALUATION_VERSION
        or value.get("candidate_sha256") != candidate_sha256
        or value.get("held_out") is not True
    ):
        raise MaestroError(
            "CONVENTION_HELD_OUT_EVALUATION_INVALID",
            "Held-out evaluation must bind the exact candidate and declare held_out=true.",
        )
    revision = repository_revision(repo)
    expected_source_revision = (
        revision.get("head")
        if revision.get("kind") == "git"
        else "unavailable"
    )
    if value.get("source_revision") != expected_source_revision:
        raise MaestroError(
            "CONVENTION_HELD_OUT_EVALUATION_INVALID",
            "Held-out evaluation source_revision does not match the current checkout HEAD.",
        )
    cases = value.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) < 3
        or len(cases) > 60
        or value.get("suite_sha256")
        != sha256_text(canonical_json(cases))
    ):
        raise MaestroError(
            "CONVENTION_HELD_OUT_EVALUATION_INVALID",
            "Held-out evaluation needs a content-addressed bounded case suite.",
        )
    categories: set[str] = set()
    case_ids: set[str] = set()
    failed_cases: list[str] = []
    critical_failures = 0
    case_fields = {
        "case_id",
        "category",
        "assertion",
        "result",
        "critical",
        "evidence_ref",
    }
    for item in cases:
        if not isinstance(item, dict) or set(item) != case_fields:
            raise MaestroError(
                "CONVENTION_HELD_OUT_EVALUATION_INVALID",
                "Every held-out case must use the closed v1 case contract.",
            )
        case_id = item.get("case_id")
        category = item.get("category")
        if (
            not isinstance(case_id, str)
            or TOPIC_PATTERN.fullmatch(case_id) is None
            or case_id in case_ids
            or category not in HELD_OUT_CATEGORIES
            or not _bounded_line(item.get("assertion"))
            or item.get("result") not in {"passed", "failed"}
            or not isinstance(item.get("critical"), bool)
            or not _bounded_line(item.get("evidence_ref"))
        ):
            raise MaestroError(
                "CONVENTION_HELD_OUT_EVALUATION_INVALID",
                "Held-out cases need unique IDs, valid categories, assertions, results, and evidence.",
            )
        case_ids.add(case_id)
        categories.add(category)
        if item["result"] == "failed":
            failed_cases.append(case_id)
            if item["critical"]:
                critical_failures += 1
    if categories != HELD_OUT_CATEGORIES:
        raise MaestroError(
            "CONVENTION_HELD_OUT_EVALUATION_INVALID",
            "Held-out evaluation requires positive, negative_scope, and regression cases.",
        )
    if (
        not isinstance(value.get("critical_regressions"), int)
        or isinstance(value.get("critical_regressions"), bool)
        or value["critical_regressions"] != critical_failures
        or failed_cases
    ):
        raise MaestroError(
            "CONVENTION_HELD_OUT_EVALUATION_FAILED",
            f"Held-out evaluation did not pass every case: {failed_cases}.",
        )
    verifier = value.get("verifier")
    if (
        not isinstance(verifier, dict)
        or set(verifier) != {
            "command",
            "exit_code",
            "executed_at",
        }
        or not _bounded_line(verifier.get("command"))
        or verifier.get("exit_code") != 0
        or not _valid_evaluation_timestamp(verifier.get("executed_at"))
    ):
        raise MaestroError(
            "CONVENTION_HELD_OUT_EVALUATION_INVALID",
            "Held-out verifier must record a successful command and timezone-aware execution time.",
        )
    conditions = value.get("conditions")
    if (
        not isinstance(conditions, dict)
        or set(conditions) != {"tool", "model", "budget"}
        or not _bounded_line(conditions.get("tool"))
        or any(
            item is not None and not _bounded_line(item)
            for item in (
                conditions.get("model"),
                conditions.get("budget"),
            )
        )
    ):
        raise MaestroError(
            "CONVENTION_HELD_OUT_EVALUATION_INVALID",
            "Held-out conditions must state the tool and explicitly record model and budget or null.",
        )
    return {
        "case_count": len(cases),
        "categories": sorted(categories),
        "source_revision": expected_source_revision,
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


def _managed_baseline_operations(
    repo: Path,
    *,
    entrypoint_path: str,
    entrypoint_content: str,
) -> list[dict[str, Any]]:
    managed_path = safe_target(repo, ".maestro/managed.json")
    lock_path = safe_target(repo, ".maestro/lock.json")
    if (
        managed_path.is_symlink()
        or lock_path.is_symlink()
        or not managed_path.is_file()
        or not lock_path.is_file()
    ):
        raise MaestroError(
            "CONVENTION_MANAGED_STATE_INVALID",
            "Convention lifecycle requires intact managed and lock state.",
        )
    managed = read_json(managed_path)
    lock = read_json(lock_path)
    if (
        managed.get("schema_version") != "maestro_managed_v1"
        or managed.get("kind") != "managed"
        or not isinstance(managed.get("entries"), list)
        or lock.get("schema_version") != "maestro_lock_v1"
        or lock.get("kind") != "lock"
        or lock.get("managed", {}).get("sha256") != file_sha256(managed_path)
    ):
        raise MaestroError(
            "CONVENTION_MANAGED_STATE_INVALID",
            "Managed state is invalid or no longer matches lock.json.",
        )
    entries: list[dict[str, Any]] = []
    replaced = False
    for item in managed["entries"]:
        if not isinstance(item, dict):
            raise MaestroError(
                "CONVENTION_MANAGED_STATE_INVALID",
                "managed.json entries must be objects.",
            )
        entry = dict(item)
        if entry.get("path") == entrypoint_path:
            entry = {
                "path": entrypoint_path,
                "ownership": "user_owned",
                "sha256": sha256_text(entrypoint_content),
                "preserve_on_drift": True,
            }
            replaced = True
        entries.append(entry)
    if not replaced:
        entries.append(
            {
                "path": entrypoint_path,
                "ownership": "user_owned",
                "sha256": sha256_text(entrypoint_content),
                "preserve_on_drift": True,
            }
        )
    entries.sort(key=lambda item: item.get("path", ""))
    managed_content = pretty_json(
        {
            "schema_version": "maestro_managed_v1",
            "kind": "managed",
            "entries": entries,
        }
    )
    updated_lock = dict(lock)
    updated_lock["managed"] = {"sha256": sha256_text(managed_content)}
    lock_content = pretty_json(updated_lock)
    return [
        _text_operation(repo, ".maestro/managed.json", managed_content),
        _text_operation(repo, ".maestro/lock.json", lock_content),
    ]


def _finalize_lifecycle_plan(base: dict[str, Any]) -> dict[str, Any]:
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def _held_out_evaluation_request(
    repo: Path,
    *,
    command: str,
    topic: str,
    candidate_sha256: str,
) -> dict[str, Any]:
    revision = repository_revision(repo)
    return {
        "schema_version": CONVENTION_EVALUATION_REQUEST_VERSION,
        "command": command,
        "status": "evaluation_required",
        "repo_root": str(repo),
        "topic": topic,
        "candidate_sha256": candidate_sha256,
        "source_revision": (
            revision["head"]
            if revision["kind"] == "git"
            else "unavailable"
        ),
        "artifact_schema": (
            "schemas/convention-held-out-evaluation.schema.json"
        ),
        "required_categories": sorted(HELD_OUT_CATEGORIES),
        "suite_digest_rule": "sha256(canonical_json(cases))",
        "writes_performed": False,
    }


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
    if basis == "held_out_evaluation" and verification_artifact is None:
        return _held_out_evaluation_request(
            repo,
            command="convention-activate",
            topic=normalized_topic,
            candidate_sha256=sha256_text(active),
        )
    entrypoint_path, entrypoint = _markdown_entrypoint(repo)
    active_paths = [*_all_active_paths(repo), target_path]
    indexed = _convention_index_content(entrypoint, active_paths)
    evidence = _approval_evidence(
        repo,
        basis=basis,
        approval_ref=approval_ref,
        verification_artifact=verification_artifact,
        decision_summary=decision_summary,
        candidate_sha256=sha256_text(active),
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
                *_managed_baseline_operations(
                    repo,
                    entrypoint_path=entrypoint_path,
                    entrypoint_content=indexed,
                ),
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
    if basis == "held_out_evaluation" and verification_artifact is None:
        return _held_out_evaluation_request(
            repo,
            command="convention-update",
            topic=normalized_topic,
            candidate_sha256=sha256_text(updated),
        )
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
        candidate_sha256=sha256_text(updated),
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
                *_managed_baseline_operations(
                    repo,
                    entrypoint_path=entrypoint_path,
                    entrypoint_content=indexed,
                ),
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
        "approval_strength",
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
    approval_strength = plan.get("approval_strength")
    approval_ref = plan.get("approval_ref")
    decision_summary = plan.get("decision_summary")
    if (
        basis not in {"owner_decision", "held_out_evaluation"}
        or approval_strength
        != (
            "owner_attested"
            if basis == "owner_decision"
            else "held_out_verified"
        )
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
    expected_operation_paths = {
        target_path,
        entrypoint_path,
        ".maestro/managed.json",
        ".maestro/lock.json",
    }
    if (
        not isinstance(operations, list)
        or len(operations) != 4
        or {item.get("path") for item in operations if isinstance(item, dict)}
        != expected_operation_paths
    ):
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Convention lifecycle operations are not the bounded target, index, and managed baseline set.",
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
        elif operation["path"] == entrypoint_path and (
            CONVENTION_INDEX_BEGIN not in operation["content"]
            or CONVENTION_INDEX_END not in operation["content"]
        ):
            raise MaestroError(
                "CONVENTION_LIFECYCLE_PLAN_INVALID",
                "Convention document index marker is missing.",
                exit_code=3,
            )
    operation_by_path = {
        operation["path"]: operation
        for operation in operations
    }
    try:
        planned_managed = json.loads(
            operation_by_path[".maestro/managed.json"]["content"]
        )
        planned_lock = json.loads(
            operation_by_path[".maestro/lock.json"]["content"]
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Managed baseline operations are not valid JSON.",
            exit_code=3,
        ) from exc
    entrypoint_digest = operation_by_path[entrypoint_path]["after_sha256"]
    matching_entries = [
        item
        for item in planned_managed.get("entries", [])
        if isinstance(item, dict) and item.get("path") == entrypoint_path
    ]
    if (
        planned_managed.get("schema_version") != "maestro_managed_v1"
        or planned_managed.get("kind") != "managed"
        or len(matching_entries) != 1
        or matching_entries[0].get("ownership") != "user_owned"
        or matching_entries[0].get("sha256") != entrypoint_digest
        or planned_lock.get("schema_version") != "maestro_lock_v1"
        or planned_lock.get("kind") != "lock"
        or planned_lock.get("managed", {}).get("sha256")
        != sha256_text(operation_by_path[".maestro/managed.json"]["content"])
    ):
        raise MaestroError(
            "CONVENTION_LIFECYCLE_PLAN_INVALID",
            "Managed baseline does not bind the updated Convention index.",
            exit_code=3,
        )
    if basis == "held_out_evaluation":
        target_operation = next(
            operation
            for operation in operations
            if operation["path"] == target_path
        )
        validate_held_out_evaluation(
            repo,
            safe_target(repo, artifact["path"]),
            candidate_sha256=target_operation["after_sha256"],
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
            elif target.exists() and not target.is_symlink():
                target.unlink()
        raise
    return {
        "schema_version": "maestro_command_result_v1",
        "command": plan["command"],
        "status": "applied",
        "repo_root": str(repo),
        "plan_id": plan["plan_id"],
        "topic": topic,
        "basis": plan["basis"],
        "approval_strength": plan["approval_strength"],
        "verification_artifact": plan["verification_artifact"],
        "changed_paths": changed,
        "writes_performed": True,
    }
