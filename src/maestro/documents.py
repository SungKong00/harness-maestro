from __future__ import annotations

import hashlib
import os
import re
from fnmatch import fnmatchcase
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from .errors import MaestroError
from .matching import searchable_terms, term_matches
from .registry import route_goal
from .util import ensure_repo, read_json, safe_target

MAX_SELECTED_DOCUMENTS = 8
MAX_SELECTED_DOCUMENT_BYTES = 48 * 1024
MAX_DOCUMENT_ENTRIES = 5_000
MAX_DOCUMENT_FILE_BYTES = 1_000_000
MAX_DOCUMENT_TOTAL_BYTES = 16_000_000
DOCUMENT_READ_CHUNK_BYTES = 64 * 1024
SCAN_LIMIT_PREFIX = "<scan-limit>:"
REQUIRED_DOCUMENT_FIELDS = frozenset(
    {"id", "type", "status", "authority", "owner", "summary"}
)
STOPWORDS = {
    "a",
    "add",
    "an",
    "and",
    "as",
    "at",
    "audit",
    "be",
    "by",
    "change",
    "changes",
    "code",
    "for",
    "from",
    "feature",
    "fix",
    "in",
    "inspect",
    "implement",
    "implementation",
    "is",
    "it",
    "modify",
    "of",
    "on",
    "or",
    "project",
    "review",
    "repository",
    "so",
    "state",
    "task",
    "that",
    "the",
    "this",
    "to",
    "update",
    "with",
    "work",
    "개발",
    "검토",
    "기능",
    "변경",
    "수정",
    "작업",
    "진행",
    "처리",
    "추가",
    "코드",
    "프로젝트",
}
SEARCHABLE_METADATA_FIELDS = frozenset(
    {
        "id",
        "owner",
        "scope",
        "summary",
        "supersedes",
        "tags",
    }
)


def _scan_limit_notice(kind: str, path: str) -> str:
    return f"{SCAN_LIMIT_PREFIX}{kind}:{path}"


def _record_scan_limit(
    trace: dict[str, Any],
    notices: list[str],
    kind: str,
    path: str,
) -> None:
    notice = _scan_limit_notice(kind, path)
    notices.append(notice)
    trace["truncated"] = True
    trace["truncation_reasons"].append(notice)
    trace["skipped_documents"].append(path)


def frontmatter_fields(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip("\"'")
    return result


def _without_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    if end < 0:
        return text
    return text[end + 4 :].lstrip("\r\n")


def scan_document_paths(
    repo: Path,
    trace: dict[str, Any] | None = None,
) -> tuple[list[Path], list[str]]:
    scan_trace: dict[str, Any] = {
        "entries_seen": 0,
        "entry_limit": MAX_DOCUMENT_ENTRIES,
        "eligible_bytes": 0,
        "total_byte_limit": MAX_DOCUMENT_TOTAL_BYTES,
        "per_file_byte_limit": MAX_DOCUMENT_FILE_BYTES,
        "archive_documents_seen": 0,
        "truncated": False,
        "truncation_reasons": [],
        "skipped_documents": [],
    }
    docs_root = repo / "docs"
    if not docs_root.exists() and not docs_root.is_symlink():
        if trace is not None:
            trace.clear()
            trace.update(scan_trace)
        return [], []
    if docs_root.is_symlink() or not docs_root.is_dir():
        if trace is not None:
            trace.clear()
            trace.update(scan_trace)
        return [], ["docs"]

    candidates: list[Path] = []
    unsafe: list[str] = []
    pending = [docs_root]
    resolved_repo = repo.resolve()
    entry_limit_reached = False
    while pending:
        directory = pending.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            unsafe.append(directory.relative_to(repo).as_posix())
            continue
        with entries:
            for entry in entries:
                if scan_trace["entries_seen"] >= MAX_DOCUMENT_ENTRIES:
                    _record_scan_limit(
                        scan_trace,
                        unsafe,
                        "entry-count",
                        directory.relative_to(repo).as_posix(),
                    )
                    pending.clear()
                    entry_limit_reached = True
                    break
                scan_trace["entries_seen"] += 1
                candidate = Path(entry.path)
                relative = candidate.relative_to(repo).as_posix()
                try:
                    if entry.is_symlink():
                        unsafe.append(relative)
                    elif entry.is_dir(follow_symlinks=False):
                        pending.append(candidate)
                    elif entry.is_file(follow_symlinks=False) and candidate.suffix == ".md":
                        candidate.resolve().relative_to(resolved_repo)
                        candidates.append(candidate)
                except (OSError, ValueError):
                    unsafe.append(relative)
        if entry_limit_reached:
            break

    paths: list[Path] = []
    for candidate in sorted(candidates):
        relative_to_docs = candidate.relative_to(docs_root)
        if "archive" in relative_to_docs.parts:
            scan_trace["archive_documents_seen"] += 1
            paths.append(candidate)
            continue
        relative = candidate.relative_to(repo).as_posix()
        try:
            size = candidate.stat().st_size
        except OSError:
            unsafe.append(relative)
            continue
        if size > MAX_DOCUMENT_FILE_BYTES:
            _record_scan_limit(
                scan_trace,
                unsafe,
                "per-file-bytes",
                relative,
            )
            continue
        if scan_trace["eligible_bytes"] + size > MAX_DOCUMENT_TOTAL_BYTES:
            _record_scan_limit(
                scan_trace,
                unsafe,
                "total-bytes",
                relative,
            )
            continue
        scan_trace["eligible_bytes"] += size
        paths.append(candidate)

    scan_trace["truncation_reasons"] = sorted(
        set(scan_trace["truncation_reasons"])
    )
    scan_trace["skipped_documents"] = sorted(
        set(scan_trace["skipped_documents"])
    )
    if trace is not None:
        trace.clear()
        trace.update(scan_trace)
    return paths, sorted(set(unsafe))


def _read_document_bounded(path: Path, maximum_bytes: int) -> tuple[str, str, int] | None:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    bytes_read = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(
                min(DOCUMENT_READ_CHUNK_BYTES, maximum_bytes - bytes_read + 1)
            )
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > maximum_bytes:
                return None
            digest.update(chunk)
            chunks.append(chunk)
    return (
        b"".join(chunks).decode("utf-8", errors="replace"),
        digest.hexdigest(),
        bytes_read,
    )


def active_documents(
    repo: Path,
    trace: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    docs_root = repo / "docs"
    scan_trace: dict[str, Any] = {}
    document_paths, scan_notices = scan_document_paths(repo, scan_trace)
    unsafe_paths = [
        path for path in scan_notices if not path.startswith(SCAN_LIMIT_PREFIX)
    ]
    if unsafe_paths:
        raise MaestroError(
            "DOC_PATH_UNSAFE",
            f"Documentation contains symlinks or unsafe paths: {unsafe_paths}",
        )
    documents: list[dict[str, Any]] = []
    bytes_read = 0
    for path in document_paths:
        relative = path.relative_to(repo).as_posix()
        if "archive" in path.relative_to(docs_root).parts:
            continue
        remaining_total = MAX_DOCUMENT_TOTAL_BYTES - bytes_read
        maximum_bytes = min(MAX_DOCUMENT_FILE_BYTES, remaining_total)
        if maximum_bytes <= 0:
            _record_scan_limit(
                scan_trace,
                scan_notices,
                "total-bytes-read",
                relative,
            )
            continue
        read_result = _read_document_bounded(path, maximum_bytes)
        if read_result is None:
            limit_kind = (
                "total-bytes-read"
                if remaining_total < MAX_DOCUMENT_FILE_BYTES
                else "per-file-bytes-read"
            )
            _record_scan_limit(
                scan_trace,
                scan_notices,
                limit_kind,
                relative,
            )
            continue
        content, digest, document_bytes = read_result
        bytes_read += document_bytes
        metadata = frontmatter_fields(content)
        if not REQUIRED_DOCUMENT_FIELDS.issubset(metadata) or any(
            not metadata[field].strip() for field in REQUIRED_DOCUMENT_FIELDS
        ):
            continue
        if metadata.get("status") != "active":
            continue
        if metadata.get("authority") not in {
            "repository",
            "external-snapshot",
            "generated",
        }:
            continue
        documents.append(
            {
                "path": relative,
                "sha256": digest,
                "bytes": document_bytes,
                "metadata": metadata,
                "path_terms": searchable_terms(relative),
                "metadata_terms": searchable_terms(
                    " ".join(
                        metadata[field]
                        for field in SEARCHABLE_METADATA_FIELDS
                        if field in metadata
                    )
                ),
                "body_terms": searchable_terms(
                    _without_frontmatter(content)[:12_000]
                ),
            }
        )
    scan_trace["bytes_read"] = bytes_read
    scan_trace["truncation_reasons"] = sorted(
        set(scan_trace["truncation_reasons"])
    )
    scan_trace["skipped_documents"] = sorted(
        set(scan_trace["skipped_documents"])
    )
    if trace is not None:
        trace.clear()
        trace.update(scan_trace)
    return documents


def _frontmatter_list(value: str | None) -> list[str]:
    if not isinstance(value, str):
        return []
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1]
    return [
        item.strip().strip("\"'")
        for item in stripped.split(",")
        if item.strip().strip("\"'")
    ]


def _path_scopes(metadata: dict[str, str]) -> list[str]:
    scopes: list[str] = []
    for item in _frontmatter_list(metadata.get("scope")):
        if item.startswith("path:"):
            pattern = item.removeprefix("path:").strip()
        elif any(marker in item for marker in ("/", "*", "?")):
            pattern = item
        else:
            continue
        if pattern:
            scopes.append(pattern)
    return scopes


def _normalize_target_paths(target_paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_path in target_paths:
        candidate = raw_path.strip().replace("\\", "/")
        parsed = PurePosixPath(candidate)
        if (
            not candidate
            or parsed.is_absolute()
            or ".." in parsed.parts
            or candidate.startswith("./")
        ):
            raise MaestroError(
                "TARGET_PATH_INVALID",
                f"Target paths must be normalized repository-relative paths: {raw_path!r}",
            )
        normalized.append(parsed.as_posix())
    return list(dict.fromkeys(normalized))


def _scope_matches(target_path: str, scope: str) -> bool:
    normalized_scope = scope.removeprefix("./")
    if normalized_scope.endswith("/**"):
        prefix = normalized_scope[:-3].rstrip("/")
        return target_path == prefix or target_path.startswith(f"{prefix}/")
    if not any(marker in normalized_scope for marker in ("*", "?", "[")):
        prefix = normalized_scope.rstrip("/")
        return target_path == prefix or target_path.startswith(f"{prefix}/")
    return fnmatchcase(target_path, normalized_scope)


def _custom_adapter_handoff(
    repo: Path,
    task: str,
    lenses: list[str],
    target_paths: list[str],
) -> dict[str, Any] | None:
    project_path = safe_target(repo, ".maestro/project.json")
    if not project_path.is_file():
        return None
    project = read_json(project_path)
    documentation = project.get("documentation")
    if not isinstance(documentation, dict) or documentation.get("provider") != "custom":
        return None
    adapter = documentation.get("custom_adapter")
    if not isinstance(adapter, dict):
        raise MaestroError(
            "CUSTOM_ADAPTER_INVALID",
            "Custom documentation provider requires custom_adapter metadata.",
        )
    adapter_id = adapter.get("id")
    instructions_path = adapter.get("instructions_path")
    if (
        set(adapter) != {"id", "instructions_path"}
        or not isinstance(adapter_id, str)
        or not adapter_id.strip()
        or not isinstance(instructions_path, str)
        or not instructions_path.strip()
    ):
        raise MaestroError(
            "CUSTOM_ADAPTER_INVALID",
            "Custom Adapter id and instructions_path must be non-empty.",
        )
    target = safe_target(repo, instructions_path)
    if target.is_symlink() or not target.is_file():
        raise MaestroError(
            "CUSTOM_ADAPTER_MISSING",
            f"Custom Adapter instructions are missing or unsafe: {instructions_path}",
        )
    return {
        "schema_version": "maestro_docs_selection_v1",
        "repo_root": str(repo),
        "task": task,
        "target_paths": target_paths,
        "requested_lenses": lenses,
        "inferred_lenses": [],
        "documents": [],
        "core_document_status": [],
        "selected_conventions": [],
        "convention_status": "adapter_required",
        "archive_included": False,
        "excluded_summary": {
            "archive_documents": 0,
            "archive_count_complete": False,
            "inactive_documents_not_loaded": True,
        },
        "evidence_status": "custom_adapter_required",
        "custom_adapter": {
            "id": adapter_id,
            "instructions_path": instructions_path,
            "output_contract": "maestro_docs_selection_v1",
        },
        "selection_trace": {
            "provider": "custom",
            "core_execution": "not_performed",
            "full_document_bodies_returned": 0,
        },
        "missing_evidence": [
            "Follow the repository-local Adapter instructions and return the standard document selection contract."
        ],
        "writes_performed": False,
    }


def _core_document_status(repo: Path) -> list[dict[str, str]]:
    project_path = safe_target(repo, ".maestro/project.json")
    if not project_path.is_file() or project_path.is_symlink():
        return []
    project = read_json(project_path)
    documentation = project.get("documentation")
    if (
        not isinstance(documentation, dict)
        or documentation.get("provider") != "markdown"
    ):
        return []
    configured = documentation.get("core_documents")
    if not isinstance(configured, dict):
        return []

    result: list[dict[str, str]] = []
    for role in ("project", "architecture"):
        relative_path = configured.get(role)
        if not isinstance(relative_path, str) or not relative_path.strip():
            result.append(
                {
                    "role": role,
                    "path": "",
                    "status": "missing",
                }
            )
            continue
        try:
            target = safe_target(repo, relative_path)
        except MaestroError:
            result.append(
                {
                    "role": role,
                    "path": relative_path,
                    "status": "missing",
                }
            )
            continue
        if target.is_symlink() or not target.is_file():
            status = "missing"
        else:
            read_result = _read_document_bounded(
                target,
                MAX_DOCUMENT_FILE_BYTES,
            )
            if read_result is None or not read_result[0].strip():
                status = "missing"
            else:
                metadata = frontmatter_fields(read_result[0])
                if not REQUIRED_DOCUMENT_FIELDS.issubset(metadata) or any(
                    not metadata[field].strip()
                    for field in REQUIRED_DOCUMENT_FIELDS
                ):
                    status = "untyped"
                elif metadata["status"] == "active":
                    status = (
                        "active"
                        if metadata["authority"]
                        in {"repository", "external-snapshot", "generated"}
                        else "invalid"
                    )
                elif metadata["status"] == "draft":
                    status = "draft"
                else:
                    status = "inactive"
        result.append(
            {
                "role": role,
                "path": relative_path,
                "status": status,
            }
        )
    return result


def _core_document_gaps(
    statuses: list[dict[str, str]],
) -> list[str]:
    messages: list[str] = []
    for item in statuses:
        status = item["status"]
        if status == "active":
            continue
        role = item["role"]
        path = item["path"] or "<not configured>"
        if status == "draft":
            action = "replace the draft placeholder with verified project facts"
        elif status == "untyped":
            action = "add typed frontmatter before treating it as active evidence"
        elif status == "inactive":
            action = "configure an active core document"
        elif status == "invalid":
            action = "repair unsupported core document metadata"
        else:
            action = "create or configure the missing core document"
        messages.append(
            f"Core document {role} is {status}: {path}; {action}."
        )
    return messages


def select_documents(
    repo_path: str | Path,
    task: str,
    lenses: list[str],
    target_paths: list[str] | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    normalized_target_paths = _normalize_target_paths(target_paths or [])
    custom_handoff = _custom_adapter_handoff(
        repo,
        task,
        lenses,
        normalized_target_paths,
    )
    if custom_handoff is not None:
        return custom_handoff
    inferred_route = (
        route_goal(task, "medium")
        if not lenses and task.strip()
        else None
    )
    deterministic_verification = (
        inferred_route is not None
        and inferred_route["model_route"]["task_class"]
        == "deterministic-verification"
    )
    task_tokens = (
        searchable_terms(task, STOPWORDS)
        if not deterministic_verification
        else frozenset()
    )
    inferred_lenses = (
        inferred_route["selected_lenses"]
        if inferred_route is not None
        else []
    )
    effective_lenses = list(dict.fromkeys([*lenses, *inferred_lenses]))
    lens_tokens = set(effective_lenses)
    selected_index: dict[str, Any] | None = None
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    scan_trace: dict[str, Any] = {}
    active = active_documents(repo, scan_trace)
    for document in active:
        if document["path"] == "docs/README.md":
            selected_index = {
                "path": document["path"],
                "sha256": document["sha256"],
                "reason": "project documentation index",
                "score": 0,
                "bytes": document["bytes"],
            }
            continue

        metadata_matches = sorted(
            token
            for token in task_tokens
            if term_matches(document["path_terms"], token)
            or term_matches(document["metadata_terms"], token)
        )
        body_matches = sorted(
            token
            for token in task_tokens - set(metadata_matches)
            if term_matches(document["body_terms"], token)
        )
        lens_matches = sorted(
            token
            for token in lens_tokens
            if term_matches(document["path_terms"], token)
            or term_matches(document["metadata_terms"], token)
            or term_matches(document["body_terms"], token)
        )
        path_scopes = _path_scopes(document["metadata"])
        scope_matches = sorted(
            {
                scope
                for scope in path_scopes
                if any(
                    _scope_matches(target_path, scope)
                    for target_path in normalized_target_paths
                )
            }
        )
        if (
            document["metadata"]["type"] == "convention"
            and normalized_target_paths
            and path_scopes
            and not scope_matches
        ):
            continue
        score = (
            len(metadata_matches) * 4
            + len(body_matches)
            + len(lens_matches) * 6
            + len(scope_matches) * 8
        )
        body_match_minimum = (
            2 if document["metadata"]["type"] == "convention" else 3
        )
        if (
            not metadata_matches
            and len(body_matches) < body_match_minimum
            and not lens_matches
            and not scope_matches
        ):
            continue
        reasons = []
        if metadata_matches:
            reasons.append(f"metadata: {', '.join(metadata_matches[:5])}")
        if body_matches:
            reasons.append(f"body: {', '.join(body_matches[:5])}")
        if lens_matches:
            reasons.append(f"lens: {', '.join(lens_matches[:3])}")
        if scope_matches:
            reasons.append(f"path scope: {', '.join(scope_matches[:3])}")
        ranked.append(
            (
                score,
                document["path"],
                {
                    "path": document["path"],
                    "sha256": document["sha256"],
                    "reason": "; ".join(reasons),
                    "score": score,
                    "bytes": document["bytes"],
                    "document_type": document["metadata"]["type"],
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1]))
    ranked = [
        *[item for item in ranked if item[2]["document_type"] == "convention"],
        *[item for item in ranked if item[2]["document_type"] != "convention"],
    ]
    candidates = ([selected_index] if selected_index else []) + [
        item[2] for item in ranked
    ]
    selected: list[dict[str, Any]] = []
    budget_skipped_documents: list[str] = []
    limit_skipped_documents: list[str] = []
    selected_bytes = 0
    for index, candidate in enumerate(candidates):
        if len(selected) >= MAX_SELECTED_DOCUMENTS:
            limit_skipped_documents.extend(
                item["path"] for item in candidates[index:]
            )
            break
        if selected_bytes + candidate["bytes"] > MAX_SELECTED_DOCUMENT_BYTES:
            budget_skipped_documents.append(candidate["path"])
            continue
        selected.append(candidate)
        selected_bytes += candidate["bytes"]
    index_selected = any(
        item["path"] == "docs/README.md"
        for item in selected
    )
    matched_documents = len(selected) - (1 if index_selected else 0)
    archive_count = scan_trace["archive_documents_seen"]
    core_document_status = _core_document_status(repo)
    missing_evidence: list[str] = []
    if scan_trace["truncated"]:
        missing_evidence.append(
            "Documentation scan was truncated by resource limits; selection evidence is incomplete."
        )
    missing_evidence.extend(
        _core_document_gaps(core_document_status)
    )
    if budget_skipped_documents:
        missing_evidence.append(
            "Matched documents were omitted by the selection byte budget; "
            "narrow the task or target paths before treating the evidence as complete."
        )
    if limit_skipped_documents:
        missing_evidence.append(
            "Matched documents were omitted by the document-count limit; "
            "narrow the task or target paths before treating the evidence as complete."
        )
    evidence_status = "insufficient" if missing_evidence else "sufficient"
    selected_conventions = [
        item["path"]
        for item in selected
        if item.get("document_type") == "convention"
        and item["path"].startswith("docs/conventions/")
    ]
    return {
        "schema_version": "maestro_docs_selection_v1",
        "repo_root": str(repo),
        "task": task,
        "target_paths": normalized_target_paths,
        "requested_lenses": lenses,
        "inferred_lenses": inferred_lenses,
        "documents": selected,
        "core_document_status": core_document_status,
        "selected_conventions": selected_conventions,
        "convention_status": "found" if selected_conventions else "none",
        "archive_included": False,
        "excluded_summary": {
            "archive_documents": archive_count,
            "archive_count_complete": not scan_trace["truncated"],
            "inactive_documents_not_loaded": True,
        },
        "evidence_status": evidence_status,
        "selection_trace": {
            "active_documents_considered": len(active),
            "matched_documents": matched_documents,
            "selected_document_count": len(selected),
            "selected_document_bytes": selected_bytes,
            "selection_byte_budget": MAX_SELECTED_DOCUMENT_BYTES,
            "selection_budget_truncated": bool(budget_skipped_documents),
            "budget_skipped_documents": budget_skipped_documents,
            "selection_limit": MAX_SELECTED_DOCUMENTS,
            "selection_limit_truncated": bool(limit_skipped_documents),
            "limit_skipped_documents": limit_skipped_documents,
            "full_document_bodies_returned": 0,
            "evidence_status": evidence_status,
            "deterministic_verification": deterministic_verification,
            "scan_truncated": scan_trace["truncated"],
            "scan_truncation_reasons": scan_trace["truncation_reasons"],
            "skipped_documents": scan_trace["skipped_documents"],
            "entries_seen": scan_trace["entries_seen"],
            "entry_limit": scan_trace["entry_limit"],
            "eligible_bytes": scan_trace["eligible_bytes"],
            "bytes_read": scan_trace["bytes_read"],
            "total_byte_limit": scan_trace["total_byte_limit"],
            "per_file_byte_limit": scan_trace["per_file_byte_limit"],
        },
        "missing_evidence": missing_evidence,
        "writes_performed": False,
    }


def _inline_link_payloads(content: str) -> list[str]:
    payloads: list[str] = []
    cursor = 0
    while True:
        match = re.search(r"(?<!\\)\]\(", content[cursor:])
        if match is None:
            break
        payload_start = cursor + match.end()
        index = payload_start
        depth = 1
        quote: str | None = None
        angle_destination = False
        destination_started = False
        destination_complete = False
        while index < len(content):
            character = content[index]
            if character == "\\":
                destination_started = True
                index += 2
                continue
            if angle_destination:
                if character == ">":
                    angle_destination = False
                index += 1
                continue
            if not destination_started and character.isspace():
                index += 1
                continue
            if character == "<" and not destination_started:
                destination_started = True
                angle_destination = True
                index += 1
                continue
            if (
                destination_started
                and not destination_complete
                and character.isspace()
                and depth == 1
            ):
                destination_complete = True
                index += 1
                continue
            if quote:
                if character == quote:
                    quote = None
                index += 1
                continue
            if destination_complete and character in {'"', "'"}:
                quote = character
                index += 1
                continue
            destination_started = True
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    payloads.append(content[payload_start:index])
                    cursor = index + 1
                    break
            index += 1
        else:
            break
    return payloads


def _unescape_markdown(value: str) -> str:
    return re.sub(r"\\(.)", r"\1", value)


def _link_destination(payload: str) -> str | None:
    value = payload.lstrip()
    if not value:
        return None
    if value.startswith("<"):
        escaped = False
        destination: list[str] = []
        for character in value[1:]:
            if escaped:
                destination.append(character)
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == ">":
                return "".join(destination)
            else:
                destination.append(character)
        return None

    destination = []
    escaped = False
    nested_parentheses = 0
    for character in value:
        if escaped:
            destination.append(character)
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character.isspace() and nested_parentheses == 0:
            break
        if character == "(":
            nested_parentheses += 1
        elif character == ")" and nested_parentheses:
            nested_parentheses -= 1
        destination.append(character)
    if escaped:
        destination.append("\\")
    return _unescape_markdown("".join(destination)) or None


def broken_links(repo: Path) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    docs_root = repo / "docs"
    resolved_repo = repo.resolve()
    scan_trace: dict[str, Any] = {}
    document_paths, scan_notices = scan_document_paths(repo, scan_trace)
    unsafe_paths = [
        path for path in scan_notices if not path.startswith(SCAN_LIMIT_PREFIX)
    ]
    if unsafe_paths:
        raise MaestroError(
            "DOC_PATH_UNSAFE",
            f"Documentation contains symlinks or unsafe paths: {unsafe_paths}",
        )
    bytes_read = 0
    for path in document_paths:
        if "archive" in path.relative_to(docs_root).parts:
            continue
        remaining_total = MAX_DOCUMENT_TOTAL_BYTES - bytes_read
        if remaining_total <= 0:
            break
        read_result = _read_document_bounded(
            path,
            min(MAX_DOCUMENT_FILE_BYTES, remaining_total),
        )
        if read_result is None:
            continue
        content, _, document_bytes = read_result
        bytes_read += document_bytes
        for payload in _inline_link_payloads(content):
            target = _link_destination(payload)
            if target is None:
                continue
            if target.casefold().startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            clean_path = Path(clean)
            if clean_path.is_absolute():
                failures.append(
                    {
                        "path": path.relative_to(repo).as_posix(),
                        "target": target,
                        "reason": "unsafe local link",
                    }
                )
                continue
            destination = (path.parent / clean).resolve()
            try:
                destination.relative_to(resolved_repo)
            except ValueError:
                failures.append(
                    {
                        "path": path.relative_to(repo).as_posix(),
                        "target": target,
                        "reason": "local link escapes repository",
                    }
                )
                continue
            if not destination.exists():
                failures.append(
                    {
                        "path": path.relative_to(repo).as_posix(),
                        "target": target,
                        "reason": "target missing",
                    }
                )
    return failures
