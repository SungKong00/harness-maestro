from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .registry import route_goal
from .util import ensure_repo

TOKEN_PATTERN = re.compile(r"[\w가-힣-]+", re.UNICODE)
MAX_SELECTED_DOCUMENTS = 8
MAX_DOCUMENT_ENTRIES = 5_000
MAX_DOCUMENT_FILE_BYTES = 1_000_000
MAX_DOCUMENT_TOTAL_BYTES = 16_000_000
DOCUMENT_READ_CHUNK_BYTES = 64 * 1024
SCAN_LIMIT_PREFIX = "<scan-limit>:"
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
        required = {"id", "type", "status", "authority", "owner", "summary"}
        if not required.issubset(metadata) or any(
            not metadata[field].strip() for field in required
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
                "metadata": metadata,
                "path_text": relative.casefold(),
                "metadata_text": " ".join(
                    metadata[field]
                    for field in SEARCHABLE_METADATA_FIELDS
                    if field in metadata
                ).casefold(),
                "body_text": content[:12_000].casefold(),
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


def _contains(search_text: str, token: str) -> bool:
    if any(ord(character) > 127 for character in token):
        return token in search_text
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", search_text) is not None


def select_documents(repo_path: str | Path, task: str, lenses: list[str]) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    task_tokens = {
        token.casefold()
        for token in TOKEN_PATTERN.findall(task)
        if len(token) > 1 and token.casefold() not in STOPWORDS
    }
    inferred_lenses = (
        []
        if lenses or not task.strip()
        else route_goal(task, "medium")["selected_lenses"]
    )
    effective_lenses = list(dict.fromkeys([*lenses, *inferred_lenses]))
    lens_tokens = {item.casefold() for item in effective_lenses}
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
            }
            continue

        metadata_matches = sorted(
            token
            for token in task_tokens
            if _contains(document["path_text"], token)
            or _contains(document["metadata_text"], token)
        )
        body_matches = sorted(
            token
            for token in task_tokens - set(metadata_matches)
            if _contains(document["body_text"], token)
        )
        lens_matches = sorted(
            token
            for token in lens_tokens
            if _contains(document["path_text"], token)
            or _contains(document["metadata_text"], token)
            or _contains(document["body_text"], token)
        )
        score = len(metadata_matches) * 4 + len(body_matches) + len(lens_matches) * 6
        if not metadata_matches and len(body_matches) < 2 and not lens_matches:
            continue
        reasons = []
        if metadata_matches:
            reasons.append(f"metadata: {', '.join(metadata_matches[:5])}")
        if body_matches:
            reasons.append(f"body: {', '.join(body_matches[:5])}")
        if lens_matches:
            reasons.append(f"lens: {', '.join(lens_matches[:3])}")
        ranked.append(
            (
                score,
                document["path"],
                {
                    "path": document["path"],
                    "sha256": document["sha256"],
                    "reason": "; ".join(reasons),
                    "score": score,
                    "document_type": document["metadata"]["type"],
                },
            )
        )
    ranked.sort(key=lambda item: (-item[0], item[1]))
    ranked = [
        *[item for item in ranked if item[2]["document_type"] == "convention"],
        *[item for item in ranked if item[2]["document_type"] != "convention"],
    ]
    selected = ([selected_index] if selected_index else []) + [
        item[2] for item in ranked[: MAX_SELECTED_DOCUMENTS - (1 if selected_index else 0)]
    ]
    matched_documents = len(selected) - (1 if selected_index else 0)
    archive_count = scan_trace["archive_documents_seen"]
    missing_evidence: list[str] = []
    if scan_trace["truncated"]:
        missing_evidence.append(
            "Documentation scan was truncated by resource limits; selection evidence is incomplete."
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
        "requested_lenses": lenses,
        "inferred_lenses": inferred_lenses,
        "documents": selected,
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
            "selection_limit": MAX_SELECTED_DOCUMENTS,
            "full_document_bodies_returned": 0,
            "evidence_status": evidence_status,
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
