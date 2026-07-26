from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__
from .documents import (
    REQUIRED_DOCUMENT_FIELDS,
    active_documents,
    broken_links,
    frontmatter_list,
    frontmatter_fields,
    scan_document_paths,
)
from .errors import MaestroError
from .expertise import load_expertise_catalog
from .host import host_installation_checks
from .project import (
    AGENTS_BEGIN,
    AGENTS_END,
    CORE_APPROVAL_GATES,
    GITIGNORE_BEGIN,
    GITIGNORE_END,
    MAX_MANAGED_TEXT_BYTES,
    git_ignored,
    inspect_adapter,
)
from .registry import (
    REGISTRY_FORMAT_VERSION,
    load_registry,
    registry_digest,
    validate_registry,
)
from .util import (
    ensure_repo,
    extract_managed_block,
    file_sha256,
    read_json,
    safe_target,
    sha256_text,
)


def _check(
    check_id: str,
    status: str,
    evidence: str,
    remediation: str = "",
) -> dict[str, str]:
    return {
        "id": check_id,
        "status": status,
        "evidence": evidence,
        "remediation": remediation,
    }


def _state_errors(value: dict[str, Any], expected_kind: str) -> list[str]:
    errors: list[str] = []
    expected_versions = {
        "project": "maestro_project_v1",
        "managed": "maestro_managed_v1",
        "lock": "maestro_lock_v1",
    }
    if value.get("kind") != expected_kind:
        errors.append(f"kind must be {expected_kind!r}")
    if value.get("schema_version") != expected_versions[expected_kind]:
        errors.append(f"schema_version must be {expected_versions[expected_kind]!r}")

    if expected_kind == "project":
        allowed = {
            "schema_version",
            "kind",
            "project_id",
            "state_root",
            "documentation",
            "adapters",
            "profiles",
            "commands",
            "verification_commands",
            "approval_required_for",
            "self_improvement",
            "expertise",
        }
        unexpected = sorted(set(value) - allowed)
        if unexpected:
            errors.append(f"unsupported fields: {unexpected}")
        for field in ("project_id", "state_root"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                errors.append(f"{field} must be a non-empty string")
        state_root = value.get("state_root")
        if state_root != ".maestro/state":
            errors.append("state_root must equal '.maestro/state' in project schema v1")
        documentation = value.get("documentation")
        if not isinstance(documentation, dict):
            errors.append("documentation must be an object")
        else:
            provider = documentation.get("provider")
            allowed_documentation = {
                "provider",
                "entrypoint",
                "core_documents",
                "external_topics",
                "custom_adapter",
            }
            if set(documentation) - allowed_documentation:
                errors.append("documentation has unsupported fields")
            if provider not in {"markdown", "custom"}:
                errors.append("documentation.provider is invalid")
            if not isinstance(documentation.get("entrypoint"), str) or not documentation[
                "entrypoint"
            ].strip():
                errors.append("documentation.entrypoint must be a non-empty string")
            core_documents = documentation.get("core_documents")
            if (
                not isinstance(core_documents, dict)
                or set(core_documents) != {"project", "architecture"}
                or any(
                    not isinstance(core_documents.get(key), str)
                    or not core_documents[key].strip()
                    for key in ("project", "architecture")
                )
            ):
                errors.append("documentation.core_documents is invalid")
            if not isinstance(documentation.get("external_topics"), dict):
                errors.append("documentation.external_topics must be an object")
            custom_adapter = documentation.get("custom_adapter")
            if provider == "markdown" and custom_adapter is not None:
                errors.append("markdown provider may not declare custom_adapter")
            if provider == "custom" and (
                not isinstance(custom_adapter, dict)
                or set(custom_adapter) != {"id", "instructions_path"}
                or any(
                    not isinstance(custom_adapter.get(key), str)
                    or not custom_adapter[key].strip()
                    for key in ("id", "instructions_path")
                )
            ):
                errors.append("custom provider requires a valid custom_adapter")
        self_improvement = value.get("self_improvement")
        if (
            not isinstance(self_improvement, dict)
            or set(self_improvement) != {"mode", "max_updates_per_run"}
            or self_improvement.get("mode")
            not in {"off", "verified-project-conventions"}
            or self_improvement.get("max_updates_per_run") not in {0, 1}
            or (
                self_improvement.get("mode") == "verified-project-conventions"
                and self_improvement.get("max_updates_per_run") != 1
            )
            or (
                self_improvement.get("mode") == "off"
                and self_improvement.get("max_updates_per_run") != 0
            )
        ):
            errors.append("self_improvement policy is invalid")
        for field in ("adapters", "profiles", "commands", "approval_required_for"):
            if not isinstance(value.get(field), list):
                errors.append(f"{field} must be a list")
        if not isinstance(value.get("verification_commands", []), list):
            errors.append("verification_commands must be a list")
        expertise = value.get(
            "expertise",
            {"active_pack_paths": []},
        )
        if (
            not isinstance(expertise, dict)
            or set(expertise) != {"active_pack_paths"}
            or not isinstance(expertise.get("active_pack_paths"), list)
            or any(
                not isinstance(path, str) or not path.strip()
                for path in expertise.get("active_pack_paths", [])
            )
            or len(expertise.get("active_pack_paths", []))
            != len(set(expertise.get("active_pack_paths", [])))
        ):
            errors.append("expertise active_pack_paths is invalid")
        for field in ("adapters", "profiles", "approval_required_for"):
            items = value.get(field)
            if isinstance(items, list) and not all(
                isinstance(item, str) and item for item in items
            ):
                errors.append(f"{field} must contain only non-empty strings")
        if value.get("adapters") != ["generic-repo"]:
            errors.append("adapters must equal ['generic-repo'] in project schema v1")
        approval_gates = value.get("approval_required_for")
        if isinstance(approval_gates, list):
            if len(set(approval_gates)) != len(approval_gates):
                errors.append("approval_required_for must be unique")
            missing_approval_gates = sorted(
                set(CORE_APPROVAL_GATES) - set(approval_gates)
            )
            if missing_approval_gates:
                errors.append(
                    f"approval_required_for is missing safety gates: {missing_approval_gates}"
                )
        commands = value.get("commands")
        if isinstance(commands, list):
            for index, command in enumerate(commands):
                if (
                    not isinstance(command, dict)
                    or set(command) != {"name", "command", "status"}
                    or not isinstance(command.get("name"), str)
                    or not command["name"]
                    or not isinstance(command.get("command"), str)
                    or not command["command"]
                    or command.get("status") != "candidate"
                ):
                    errors.append(f"commands[{index}] is invalid")
        verification_commands = value.get("verification_commands", [])
        if isinstance(verification_commands, list):
            seen_verification_names: set[str] = set()
            for index, command in enumerate(verification_commands):
                if (
                    not isinstance(command, dict)
                    or set(command) != {"name", "command"}
                    or not isinstance(command.get("name"), str)
                    or not command["name"].strip()
                    or not isinstance(command.get("command"), str)
                    or not command["command"].strip()
                ):
                    errors.append(f"verification_commands[{index}] is invalid")
                    continue
                if command["name"] in seen_verification_names:
                    errors.append(
                        f"verification_commands[{index}].name must be unique"
                    )
                seen_verification_names.add(command["name"])
    elif expected_kind == "managed":
        allowed_ownership = {
            "AGENTS.md": {"managed_block"},
            ".gitignore": {"managed_block"},
            "docs/README.md": {"seeded", "user_owned"},
            "docs/project.md": {"seeded", "user_owned"},
            "docs/architecture.md": {"seeded", "user_owned"},
            "docs/governance/document-lifecycle.md": {
                "seeded",
                "user_owned",
            },
        }
        if set(value) - {"schema_version", "kind", "entries"}:
            errors.append("managed state has unsupported fields")
        entries = value.get("entries")
        if not isinstance(entries, list):
            errors.append("entries must be a list")
        else:
            seen: set[str] = set()
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    errors.append(f"entries[{index}] must be an object")
                    continue
                if set(entry) != {
                    "path",
                    "ownership",
                    "sha256",
                    "preserve_on_drift",
                }:
                    errors.append(f"entries[{index}] has unsupported or missing fields")
                path = entry.get("path")
                if not isinstance(path, str) or not path:
                    errors.append(f"entries[{index}].path must be a non-empty string")
                elif path in seen:
                    errors.append(f"duplicate managed path: {path}")
                else:
                    seen.add(path)
                    relative = Path(path)
                    if relative.is_absolute() or ".." in relative.parts:
                        errors.append(f"entries[{index}].path must stay inside the repository")
                expected_ownership = (
                    allowed_ownership.get(path)
                    if isinstance(path, str)
                    else None
                )
                if expected_ownership is None:
                    errors.append(f"entries[{index}].path is unsupported")
                elif entry.get("ownership") not in expected_ownership:
                    errors.append(f"entries[{index}].ownership is unsupported")
                digest = entry.get("sha256")
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)
                ):
                    errors.append(f"entries[{index}].sha256 must be a SHA-256 digest")
                if entry.get("preserve_on_drift") is not True:
                    errors.append(f"entries[{index}].preserve_on_drift must be true")
            missing_core_paths = sorted(
                {
                    "AGENTS.md",
                    ".gitignore",
                    "docs/README.md",
                    "docs/governance/document-lifecycle.md",
                }
                - seen
            )
            if missing_core_paths:
                errors.append(f"missing core managed paths: {missing_core_paths}")
    else:
        if set(value) - {
            "schema_version",
            "kind",
            "framework",
            "registry",
            "managed",
            "adapters",
        }:
            errors.append("lock state has unsupported fields")
        framework = value.get("framework")
        registry = value.get("registry")
        managed_lock = value.get("managed")
        adapters = value.get("adapters")
        if (
            not isinstance(framework, dict)
            or set(framework) != {"name", "version"}
            or framework.get("name") != "harness-maestro"
            or not isinstance(framework.get("version"), str)
            or not framework["version"]
        ):
            errors.append("framework lock is incomplete")
        if (
            not isinstance(registry, dict)
            or set(registry) != {"version", "sha256"}
            or not isinstance(registry.get("version"), int)
            or isinstance(registry.get("version"), bool)
            or registry["version"] != REGISTRY_FORMAT_VERSION
            or not isinstance(registry.get("sha256"), str)
            or len(registry["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in registry["sha256"])
        ):
            errors.append("registry lock is incomplete")
        if (
            not isinstance(managed_lock, dict)
            or set(managed_lock) != {"sha256"}
            or not isinstance(managed_lock.get("sha256"), str)
            or len(managed_lock["sha256"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in managed_lock["sha256"]
            )
        ):
            errors.append("managed lock is incomplete")
        if not isinstance(adapters, list):
            errors.append("adapters must be a list")
        elif any(
            not isinstance(adapter, dict)
            or set(adapter) != {"id", "version"}
            or not isinstance(adapter.get("id"), str)
            or not adapter["id"]
            or not isinstance(adapter.get("version"), int)
            or isinstance(adapter.get("version"), bool)
            or adapter["version"] < 1
            for adapter in adapters
        ):
            errors.append("adapter lock entries are invalid")
    return errors


def doctor_report(
    repo_path: str | Path,
    *,
    host_id: str | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    checks: list[dict[str, str]] = []
    required = [
        ".maestro/project.json",
        ".maestro/managed.json",
        ".maestro/lock.json",
        "docs/README.md",
        "docs/governance/document-lifecycle.md",
    ]
    optional_safe_paths = [".maestro/state"]
    required_targets: dict[str, Path] = {}
    unsafe_required: dict[str, str] = {}
    for path in required:
        try:
            required_targets[path] = safe_target(repo, path)
        except MaestroError as exc:
            unsafe_required[path] = exc.message
    for path in optional_safe_paths:
        try:
            safe_target(repo, path)
        except MaestroError as exc:
            unsafe_required[path] = exc.message
    checks.append(
        _check(
            "STATE_PATH_SAFETY",
            "FAIL" if unsafe_required else "PASS",
            f"unsafe={unsafe_required}",
            "Replace harness state symlinks with repository-owned files."
            if unsafe_required
            else "",
        )
    )
    missing = [
        path
        for path in required
        if path not in required_targets or not required_targets[path].is_file()
    ]
    checks.append(
        _check(
            "PROJECT_INITIALIZED",
            "FAIL" if missing else "PASS",
            f"missing={missing}",
            "Run maestro init and apply the reviewed plan." if missing else "",
        )
    )

    project: dict[str, Any] | None = None
    managed: dict[str, Any] | None = None
    lock: dict[str, Any] | None = None
    for name, path, expected_kind in (
        ("PROJECT_SCHEMA", ".maestro/project.json", "project"),
        ("MANAGED_SCHEMA", ".maestro/managed.json", "managed"),
        ("LOCK_SCHEMA", ".maestro/lock.json", "lock"),
    ):
        target = required_targets.get(path)
        if target is None or not target.is_file():
            continue
        try:
            value = read_json(target)
            state_errors = _state_errors(value, expected_kind)
            checks.append(
                _check(
                    name,
                    "FAIL" if state_errors else "PASS",
                    f"errors={state_errors}",
                    "Repair the typed Maestro state file." if state_errors else "",
                )
            )
            if not state_errors:
                if expected_kind == "project":
                    project = value
                elif expected_kind == "managed":
                    managed = value
                else:
                    lock = value
        except Exception as exc:
            checks.append(_check(name, "FAIL", str(exc), "Repair the invalid JSON."))

    if managed:
        for entry in managed.get("entries", []):
            path = str(entry.get("path", ""))
            try:
                target = safe_target(repo, path)
            except MaestroError as exc:
                checks.append(
                    _check(
                        f"MANAGED:{path}",
                        "FAIL",
                        exc.message,
                        "Remove unsafe paths from .maestro/managed.json.",
                    )
                )
                continue
            if not target.is_file():
                checks.append(
                    _check(
                        f"MANAGED:{path}",
                        "FAIL",
                        "file missing",
                        "Review and re-apply a fresh init plan.",
                    )
                )
                continue
            if entry.get("ownership") == "managed_block":
                if target.stat().st_size > MAX_MANAGED_TEXT_BYTES:
                    checks.append(
                        _check(
                            f"MANAGED:{path}",
                            "FAIL",
                            f"file exceeds {MAX_MANAGED_TEXT_BYTES} bytes",
                            "Reduce the managed guidance file before reviewing a fresh plan.",
                        )
                    )
                    continue
                text = target.read_text(encoding="utf-8", errors="replace")
                if path == "AGENTS.md":
                    block = extract_managed_block(text, AGENTS_BEGIN, AGENTS_END)
                else:
                    block = extract_managed_block(text, GITIGNORE_BEGIN, GITIGNORE_END)
                actual = sha256_text(block or "")
            else:
                actual = file_sha256(target)
            expected = entry.get("sha256")
            drift_status = (
                "FAIL"
                if entry.get("ownership") == "managed_block"
                else "WARN"
            )
            checks.append(
                _check(
                    f"MANAGED:{path}",
                    "PASS" if actual == expected else drift_status,
                    f"expected={expected} actual={actual}",
                    "Do not auto-repair. Review ownership and generate a new plan."
                    if actual != expected
                    else "",
                )
                )

    if project:
        documentation = project["documentation"]
        configured_paths = {
            "entrypoint": documentation["entrypoint"],
            **documentation["core_documents"],
        }
        path_errors: dict[str, str] = {}
        for key, relative_path in configured_paths.items():
            try:
                target = safe_target(repo, relative_path)
                if target.is_symlink() or not target.is_file():
                    path_errors[key] = f"missing or unsafe: {relative_path}"
            except MaestroError as exc:
                path_errors[key] = exc.message
        checks.append(
            _check(
                "DOCUMENT_ENTRYPOINTS",
                "FAIL" if path_errors else "PASS",
                f"errors={path_errors}",
                "Repair the configured repository-local document paths."
                if path_errors
                else "",
            )
        )
        try:
            catalog = load_expertise_catalog(repo)
            project_packs = [
                pack
                for pack in catalog
                if pack["_maestro"]["origin"] == "project"
            ]
            ignored_project_packs = [
                pack["_maestro"]["pack_path"]
                for pack in project_packs
                if git_ignored(repo, pack["_maestro"]["pack_path"]) is True
            ]
            checks.append(
                _check(
                    "PROJECT_EXPERTISE",
                    "FAIL" if ignored_project_packs else "PASS",
                    (
                        f"active={len(project_packs)} "
                        f"ignored={ignored_project_packs}"
                    ),
                    (
                        "Keep active project Expertise under tracked "
                        ".agents/skills paths."
                    )
                    if ignored_project_packs
                    else "",
                )
            )
        except MaestroError as exc:
            checks.append(
                _check(
                    "PROJECT_EXPERTISE",
                    "FAIL",
                    f"{exc.code}: {exc.message}",
                    "Repair or disable the invalid project Expertise Pack.",
                )
            )
        custom_errors: list[str] = []
        if documentation["provider"] == "custom":
            instructions_path = documentation["custom_adapter"]["instructions_path"]
            try:
                target = safe_target(repo, instructions_path)
                if target.is_symlink() or not target.is_file():
                    custom_errors.append(
                        f"missing or unsafe instructions: {instructions_path}"
                    )
            except MaestroError as exc:
                custom_errors.append(exc.message)
        checks.append(
            _check(
                "CUSTOM_DOCUMENT_ADAPTER",
                "FAIL" if custom_errors else "PASS",
                f"errors={custom_errors}",
                "Provide a repository-local instruction file; arbitrary Adapter commands are not supported."
                if custom_errors
                else "",
            )
        )

    if managed and lock:
        locked_managed = lock.get("managed", {}).get("sha256")
        actual_managed = file_sha256(required_targets[".maestro/managed.json"])
        checks.append(
            _check(
                "MANAGED_LOCK",
                "PASS" if locked_managed == actual_managed else "FAIL",
                f"locked={locked_managed} actual={actual_managed}",
                "Do not trust or repair an unlocked managed index; review version-control history."
                if locked_managed != actual_managed
                else "",
            )
        )

    ignored_required = [
        path for path in required[:3] if git_ignored(repo, path) is True
    ]
    checks.append(
        _check(
            "TRACKED_HARNESS_STATE",
            "FAIL" if ignored_required else "PASS",
            f"ignored={ignored_required}",
            "Stop ignoring required .maestro state files; ignore only .maestro/state/."
            if ignored_required
            else "",
        )
    )

    docs_root = repo / "docs"
    document_paths, unsafe_doc_paths = scan_document_paths(repo)
    checks.append(
        _check(
            "DOC_PATH_SAFETY",
            "FAIL" if unsafe_doc_paths else "PASS",
            f"unsafe={unsafe_doc_paths}",
            "Replace documentation symlinks with repository-owned snapshots."
            if unsafe_doc_paths
            else "",
        )
    )
    indexed_metadata: list[tuple[str, dict[str, str]]] = []
    for path in document_paths:
        if "archive" in path.relative_to(docs_root).parts:
            continue
        indexed_metadata.append(
            (
                path.relative_to(repo).as_posix(),
                frontmatter_fields(
                    path.read_text(encoding="utf-8", errors="replace")
                ),
            )
        )
    metadata_failures = {
        path: sorted(
            field
            for field in REQUIRED_DOCUMENT_FIELDS
            if field not in metadata or not metadata[field].strip()
        )
        for path, metadata in indexed_metadata
        if any(
            field not in metadata or not metadata[field].strip()
            for field in REQUIRED_DOCUMENT_FIELDS
        )
    }
    checks.append(
        _check(
            "DOC_FRONTMATTER",
            "FAIL" if metadata_failures else "PASS",
            f"missing_fields={metadata_failures}",
            (
                "Add typed frontmatter to every active Markdown document. "
                "See the Frontmatter contract in "
                "docs/governance/document-lifecycle.md."
            )
            if metadata_failures
            else "",
        )
    )
    allowed_statuses = {"active", "draft", "superseded", "deprecated", "archived"}
    allowed_types = {
        "map",
        "index",
        "project",
        "architecture",
        "governance",
        "decision",
        "convention",
        "plan",
        "runbook",
        "analysis",
        "evidence",
        "external-snapshot",
    }
    allowed_authorities = {
        "repository",
        "external-snapshot",
        "generated",
        "historical",
    }
    invalid_values: dict[str, list[str]] = {}
    for path, metadata in indexed_metadata:
        problems: list[str] = []
        if metadata.get("type") and metadata["type"] not in allowed_types:
            problems.append(f"unsupported type={metadata['type']!r}")
        if metadata.get("status") and metadata["status"] not in allowed_statuses:
            problems.append(f"unsupported status={metadata['status']!r}")
        if metadata.get("authority") and metadata["authority"] not in allowed_authorities:
            problems.append(f"unsupported authority={metadata['authority']!r}")
        if metadata.get("maestro_doc") not in {None, "1"}:
            problems.append("maestro_doc must equal 1")
        if problems:
            invalid_values[path] = problems
    checks.append(
        _check(
            "DOC_METADATA_VALUES",
            "FAIL" if invalid_values else "PASS",
            f"invalid={invalid_values}",
            "Use the documented status and authority vocabulary."
            if invalid_values
            else "",
        )
    )

    document_ids = {
        metadata.get("id", "")
        for _, metadata in indexed_metadata
        if metadata.get("id")
    }
    convention_metadata_issues: dict[str, list[str]] = {}
    convention_supersession_issues: dict[str, list[str]] = {}
    active_topics: dict[str, list[str]] = {}
    convention_fields = {
        "topic",
        "scope",
        "last_verified",
        "supersedes",
        "sensitivity",
    }
    for path, metadata in indexed_metadata:
        if metadata.get("type") != "convention":
            continue
        issues: list[str] = []
        missing = sorted(
            field
            for field in convention_fields
            if field not in metadata or not metadata[field].strip()
        )
        if missing:
            issues.append(f"missing={missing}")
        topic = metadata.get("topic")
        if topic and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic) is None:
            issues.append("topic must be a lowercase ASCII slug")
        scopes = frontmatter_list(metadata.get("scope"))
        if "scope" in metadata and not scopes:
            issues.append("scope must contain at least one path or topic")
        for scope in scopes:
            normalized = scope.replace("\\", "/")
            if (
                normalized.startswith("/")
                or normalized.startswith("./")
                or ".." in Path(normalized).parts
            ):
                issues.append(f"unsafe scope={scope!r}")
        last_verified = metadata.get("last_verified")
        if metadata.get("status") == "active":
            try:
                if last_verified is None:
                    raise ValueError
                date.fromisoformat(last_verified)
            except ValueError:
                issues.append("active last_verified must use YYYY-MM-DD")
        elif last_verified not in {None, "null"}:
            try:
                date.fromisoformat(last_verified)
            except ValueError:
                issues.append("last_verified must be null or YYYY-MM-DD")
        sensitivity = metadata.get("sensitivity")
        if sensitivity and sensitivity not in {"public", "internal", "restricted"}:
            issues.append(f"unsupported sensitivity={sensitivity!r}")
        if issues:
            convention_metadata_issues[path] = issues

        supersedes = frontmatter_list(metadata.get("supersedes"))
        missing_targets = sorted(
            target for target in supersedes if target not in document_ids
        )
        if missing_targets:
            convention_supersession_issues[path] = [
                f"unknown document IDs: {missing_targets}"
            ]
        if metadata.get("status") == "active" and topic:
            active_topics.setdefault(topic, []).append(path)

    checks.append(
        _check(
            "CONVENTION_METADATA",
            "WARN" if convention_metadata_issues else "PASS",
            f"issues={convention_metadata_issues}",
            (
                "Add stable topic, scope, verification date, supersession, and "
                "sensitivity metadata before activating or revising the Convention."
            )
            if convention_metadata_issues
            else "",
        )
    )
    duplicate_topics = {
        topic: paths
        for topic, paths in active_topics.items()
        if len(paths) > 1
    }
    checks.append(
        _check(
            "CONVENTION_TOPIC_AUTHORITY",
            "FAIL" if duplicate_topics else "PASS",
            f"duplicates={duplicate_topics}",
            "Keep one active Convention authority per stable topic."
            if duplicate_topics
            else "",
        )
    )
    checks.append(
        _check(
            "CONVENTION_SUPERSESSION",
            "FAIL" if convention_supersession_issues else "PASS",
            f"issues={convention_supersession_issues}",
            "Point supersedes only to an existing document ID."
            if convention_supersession_issues
            else "",
        )
    )

    documents = active_documents(repo) if not unsafe_doc_paths else []
    ids: dict[str, list[str]] = {}
    for document in documents:
        doc_id = document["metadata"].get("id")
        if doc_id:
            ids.setdefault(doc_id, []).append(document["path"])
    duplicates = {key: value for key, value in ids.items() if len(value) > 1}
    checks.append(
        _check(
            "DOC_DUPLICATE_ACTIVE",
            "FAIL" if duplicates else "PASS",
            f"duplicates={duplicates}",
            "Keep one active authority and supersede or archive the others."
            if duplicates
            else "",
        )
    )

    links = broken_links(repo) if not unsafe_doc_paths else []
    checks.append(
        _check(
            "DOC_LINKS",
            "FAIL" if links else "PASS",
            f"broken={links}",
            "Repair or remove broken relative links." if links else "",
        )
    )

    registry = load_registry()
    registry_errors = validate_registry(registry)
    checks.append(
        _check(
            "REGISTRY_VALID",
            "FAIL" if registry_errors else "PASS",
            f"errors={registry_errors}",
            "Separate Lens, Executor, Department, and Adapter responsibilities."
            if registry_errors
            else "",
        )
    )
    if project and lock and not registry_errors:
        adapters_by_id = {
            adapter["adapter_id"]: adapter
            for adapter in registry["adapters"]
        }
        configured_adapter_ids = project.get("adapters", [])
        expected_adapter_locks = [
            {
                "id": adapter_id,
                "version": adapters_by_id[adapter_id]["version"],
            }
            for adapter_id in configured_adapter_ids
            if adapter_id in adapters_by_id
        ]
        adapter_binding_errors: list[str] = []
        unknown_adapters = sorted(
            set(configured_adapter_ids) - set(adapters_by_id)
        )
        if unknown_adapters:
            adapter_binding_errors.append(
                f"unknown project adapters: {unknown_adapters}"
            )
        if lock.get("adapters") != expected_adapter_locks:
            adapter_binding_errors.append(
                "lock adapters do not match configured registry adapters"
            )
        if (
            lock.get("registry", {}).get("version")
            != REGISTRY_FORMAT_VERSION
        ):
            adapter_binding_errors.append(
                f"registry lock version must equal {REGISTRY_FORMAT_VERSION}"
            )
        checks.append(
            _check(
                "ADAPTER_BINDINGS",
                "FAIL" if adapter_binding_errors else "PASS",
                f"errors={adapter_binding_errors}",
                "Generate and apply a fresh init plan after reviewing adapter changes."
                if adapter_binding_errors
                else "",
            )
        )
        inspection = inspect_adapter(repo)
        adapter_drift = {
            "profiles": {
                "configured": project.get("profiles"),
                "detected": inspection["profiles_detected"],
            },
            "commands": {
                "configured": project.get("commands"),
                "detected": inspection["candidate_commands"],
            },
        }
        drifted = any(
            values["configured"] != values["detected"]
            for values in adapter_drift.values()
        )
        checks.append(
            _check(
                "ADAPTER_DRIFT",
                "WARN" if drifted else "PASS",
                f"drift={adapter_drift}",
                "Review and apply a fresh init plan to accept static adapter facts."
                if drifted
                else "",
            )
        )
    if lock:
        locked_framework = lock.get("framework", {}).get("version")
        checks.append(
            _check(
                "FRAMEWORK_LOCK",
                "PASS" if locked_framework == __version__ else "WARN",
                f"locked={locked_framework} current={__version__}",
                "Generate and review a fresh init plan before upgrading the lock."
                if locked_framework != __version__
                else "",
            )
        )
        locked_digest = lock.get("registry", {}).get("sha256")
        current_digest = registry_digest()
        checks.append(
            _check(
                "REGISTRY_LOCK",
                "PASS" if locked_digest == current_digest else "WARN",
                f"locked={locked_digest} current={current_digest}",
                "Review the registry change and update the lock through an approved plan."
                if locked_digest != current_digest
                else "",
            )
        )

    if host_id is not None:
        checks.extend(host_installation_checks(host_id, project_root=repo))

    failures = [item for item in checks if item["status"] == "FAIL"]
    warnings = [item for item in checks if item["status"] == "WARN"]
    return {
        "schema_version": "maestro_doctor_report_v1",
        "repo_root": str(repo),
        "status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        "checks": checks,
        "summary": {
            "pass": sum(item["status"] == "PASS" for item in checks),
            "warn": len(warnings),
            "fail": len(failures),
        },
        "writes_performed": False,
        "project_id": project.get("project_id") if project else None,
        "host_id": host_id,
    }
