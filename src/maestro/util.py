from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from .errors import MaestroError

MAX_JSON_BYTES = 16_000_000
HASH_CHUNK_BYTES = 1024 * 1024

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise MaestroError("PATH_NOT_FILE", f"Expected a file: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as exc:
        raise MaestroError("FILE_UNREADABLE", f"Cannot read file: {path}") from exc
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        if size > MAX_JSON_BYTES:
            raise MaestroError(
                "JSON_TOO_LARGE",
                f"JSON file exceeds the {MAX_JSON_BYTES}-byte limit: {path}",
            )
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MaestroError("FILE_MISSING", f"Required file is missing: {path}") from exc
    except UnicodeDecodeError as exc:
        raise MaestroError("JSON_INVALID", f"JSON is not valid UTF-8: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MaestroError(
            "JSON_INVALID",
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}",
        ) from exc
    if not isinstance(value, dict):
        raise MaestroError("JSON_INVALID", f"Expected a JSON object in {path}")
    return value


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = (
        stat.S_IMODE(path.stat().st_mode)
        if path.exists() and path.is_file() and not path.is_symlink()
        else None
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if existing_mode is not None:
            os.chmod(temporary_path, existing_mode)
        os.replace(temporary_path, path)
        directory_fd = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def slugify(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return result or "project"


def ensure_repo(path: str | Path) -> Path:
    repo = Path(path).expanduser().resolve()
    if not repo.exists() or not repo.is_dir():
        raise MaestroError("REPO_NOT_FOUND", f"Repository directory does not exist: {repo}")
    return repo


def safe_target(repo: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if (
        not relative.parts
        or relative == Path(".")
        or relative.is_absolute()
        or ".." in relative.parts
    ):
        raise MaestroError("PATH_ESCAPE", f"Unsafe managed path: {relative_path}", exit_code=3)

    repo = repo.resolve()
    current = repo
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise MaestroError(
                "PATH_ESCAPE",
                f"Managed path traverses a symlink: {relative_path}",
                exit_code=3,
            )

    target = repo / relative
    resolved_parent = target.parent.resolve()
    try:
        resolved_parent.relative_to(repo)
    except ValueError as exc:
        raise MaestroError(
            "PATH_ESCAPE",
            f"Managed path escapes the repository through a symlink: {relative_path}",
            exit_code=3,
        ) from exc
    return target


def managed_block(text: str, begin: str, end: str, body: str) -> str:
    block = f"{begin}\n{body.rstrip()}\n{end}"
    if begin in text or end in text:
        if text.count(begin) != 1 or text.count(end) != 1:
            raise MaestroError("MANAGED_BLOCK_INVALID", f"Malformed managed block: {begin}")
        start = text.index(begin)
        finish_index = text.find(end, start + len(begin))
        if finish_index < 0:
            raise MaestroError("MANAGED_BLOCK_INVALID", f"Malformed managed block: {begin}")
        finish = finish_index + len(end)
        return text[:start] + block + text[finish:]
    if not text:
        return f"{block}\n"
    if text.endswith("\n\n"):
        separator = ""
    elif text.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    return f"{text}{separator}{block}\n"


def extract_managed_block(text: str, begin: str, end: str) -> str | None:
    if begin not in text or end not in text:
        return None
    if text.count(begin) != 1 or text.count(end) != 1:
        return None
    start = text.index(begin)
    finish_index = text.find(end, start + len(begin))
    if finish_index < 0:
        return None
    finish = finish_index + len(end)
    return text[start:finish]
