from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from . import __version__
from .documents import (
    REQUIRED_DOCUMENT_FIELDS,
    SCAN_LIMIT_PREFIX,
    frontmatter_fields,
    scan_document_paths,
)
from .errors import MaestroError
from .registry import (
    REGISTRY_FORMAT_VERSION,
    load_registry,
    registry_digest,
    validate_registry,
)
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    extract_managed_block,
    file_sha256,
    managed_block,
    pretty_json,
    read_json,
    safe_target,
    sha256_bytes,
    sha256_text,
    slugify,
)

AGENTS_BEGIN = "<!-- MAESTRO:BEGIN -->"
AGENTS_END = "<!-- MAESTRO:END -->"
GITIGNORE_BEGIN = "# MAESTRO:BEGIN"
GITIGNORE_END = "# MAESTRO:END"
INIT_MANAGED_PATHS = frozenset(
    {
        "AGENTS.md",
        ".gitignore",
        ".maestro/project.json",
        ".maestro/managed.json",
        ".maestro/lock.json",
        "docs/README.md",
        "docs/project.md",
        "docs/architecture.md",
        "docs/governance/document-lifecycle.md",
    }
)
SCAN_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "vendor",
        "build",
        "dist",
        "__pycache__",
    }
)
MAX_ADAPTER_SCAN_ENTRIES = 5_000
MAX_MANIFEST_BYTES = 1_000_000
MAX_MANAGED_TEXT_BYTES = 2_000_000
CORE_APPROVAL_GATES = [
    "external_write",
    "authority_change",
    "adapter_change",
    "harness_promotion",
]

AGENTS_BODY = """## Harness Maestro

- Read `.maestro/project.json`, the configured document entrypoint, and only task-relevant project conventions before implementation.
- Use `$maestro` for explicit routing when risk, research, or multiple review lenses matter.
- Run `maestro doctor --repo . --json` when the manifest or document index changed.
- Default to one writer. Review lanes are read-only and may not edit the same files.
- Keep initial lens conclusions isolated; discuss only material conflicts once.
- Never treat majority vote as correctness. Preserve evidence-backed minority risks.
- Record operational telemetry under the configured state root, not as one Markdown file per run.
- When project-local self-improvement is enabled, keep same-run reusable rules as candidates; create or update at most one active project Convention only from an explicit `owner_decision` or accepted `held_out_evaluation`.
- Never auto-edit global Skills, Agents, Lenses, Executors, Departments, or Adapter definitions."""

GITIGNORE_BODY = """.maestro/state/
.maestro/backups/"""

def _docs_index_link(relative_path: str) -> str:
    return (
        relative_path.removeprefix("docs/")
        if relative_path.startswith("docs/")
        else f"../{relative_path}"
    )


def _docs_index(core_documents: dict[str, str]) -> str:
    return f"""---
maestro_doc: 1
id: project-docs-index
type: map
status: active
authority: repository
owner: project
summary: Project documentation map.
tags: [documentation, index]
---

# Project documentation

The document provider and one editable authority per topic are declared in `.maestro/project.json`.

- [Project context]({_docs_index_link(core_documents["project"])})
- [Architecture]({_docs_index_link(core_documents["architecture"])})

Create directories only when the first real document needs them:

- `architecture/` — current system structure and boundaries
- `conventions/` — active, reviewable development rules
- `decisions/` — important choices, alternatives, and reversal conditions
- `plans/active/` and `plans/completed/` — bounded plans, not raw transcripts
- `runbooks/` — repeatable operational procedures
- `research/` — adopted research briefs and source provenance
- `archive/` — superseded material; excluded from default retrieval

Run `maestro docs --repo . --task "<goal>" --json` to select relevant documents without loading the full tree. Read `required_documents` by default; open `optional_documents` only when the task enters that research or plan boundary.
Use returned `selected_conventions` as implementation and verification criteria. No matching convention is not a blocker.
"""


PROJECT_DOC = """---
maestro_doc: 1
id: project-context
type: project
status: draft
authority: repository
owner: project
summary: Project goal, users, scope, non-goals, and priorities.
tags: [project, scope]
---

# Project

## Goal

Describe why this project exists.

## Users

Describe the primary users or operators.

## Scope and non-goals

List the current scope and explicit non-goals.

## Priorities

List the quality or delivery priorities in order.
"""


ARCHITECTURE_DOC = """---
maestro_doc: 1
id: architecture-overview
type: architecture
status: draft
authority: repository
owner: project
summary: Current structure, boundaries, constraints, and quality priorities.
tags: [architecture, constraints]
---

# Architecture

## Current structure

Describe the major components and their responsibilities.

## Boundaries

Describe module, service, data, and external-system boundaries.

## Constraints

List constraints that materially affect implementation choices.

## Quality priorities

List the qualities that should win when trade-offs are required.
"""

DOCUMENT_POLICY = """---
maestro_doc: 1
id: document-lifecycle
type: governance
status: active
authority: repository
owner: project
summary: Rules for promoting operational observations into durable documentation.
tags: [documentation, governance, lifecycle]
---

# Document lifecycle

Keep operational events in JSONL under the configured state root. Promote content to Markdown only when it is reusable, evidence-backed, owned, and not already represented by an active document.

Active Markdown uses this minimum frontmatter:

```yaml
---
maestro_doc: 1
id: project-unique-id
type: architecture
status: active
authority: repository
owner: project
summary: One searchable sentence.
---
```

Required fields are `id`, `type`, `status`, `authority`, `owner`, and `summary`.
Convention documents also declare stable `topic`, `scope`, `last_verified`,
`supersedes`, and `sensitivity` metadata. Use `maestro convention draft` to
preview a structured inactive draft; applying the reviewed plan never activates it.
Use `draft` while project facts are incomplete and `active` only after they have
been checked. Supported status values are `draft`, `active`, `superseded`,
`deprecated`, and `archived`. Supported authority values are `repository`,
`external-snapshot`, `generated`, and `historical`.

For an existing Markdown file, keep its body unchanged and add metadata manually.
Then run `maestro status`, review and apply the reported `maestro upgrade` plan
so only the user-owned baseline advances, and finish with
`maestro doctor --strict`.

When `.maestro/project.json` enables `verified-project-conventions`, a reusable project rule may be recorded automatically as a candidate. Same-run implementation success does not activate it. Create or update at most one active Convention only after an explicit owner decision or an accepted held-out evaluation. Security policy, external contracts, data policy, irreversible decisions, and global Harness components require a separate decision or candidate review.

One topic has one authority. Markdown is the built-in provider. A project may instead name a repository-local custom Adapter instruction file; Maestro validates the pointer but does not execute arbitrary Adapter commands or implement every external system. If Notion or another external source is authoritative for an explicit topic, repository Markdown is a read-only snapshot with revision and digest metadata, not a second editable master.

Archive is excluded from normal selection. Superseded documents name their replacement. Deletion requires an owner decision, reference scan, support window, and rollback path.
"""


def _bounded_text(path: Path, *, default: str) -> str:
    if not path.exists():
        return default
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise MaestroError("FILE_UNREADABLE", f"Cannot inspect managed file: {path}") from exc
    if size > MAX_MANAGED_TEXT_BYTES:
        raise MaestroError(
            "MANAGED_FILE_TOO_LARGE",
            f"Managed text exceeds the {MAX_MANAGED_TEXT_BYTES}-byte limit: {path}",
        )
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MaestroError("FILE_UNREADABLE", f"Cannot read managed text: {path}") from exc


def _safe_regular_file(repo: Path, relative_path: str) -> bool:
    target = repo / relative_path
    return target.is_file() and not target.is_symlink()


def _package_commands(
    repo: Path,
    scan_warnings: list[str],
) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    if _safe_regular_file(repo, "gradlew"):
        commands.extend(
            [
                {"name": "test", "command": "./gradlew test", "status": "candidate"},
                {"name": "check", "command": "./gradlew check", "status": "candidate"},
            ]
        )
    elif _safe_regular_file(repo, "mvnw"):
        commands.append({"name": "test", "command": "./mvnw test", "status": "candidate"})
    package_json = repo / "package.json"
    if _safe_regular_file(repo, "package.json"):
        if package_json.stat().st_size > MAX_MANIFEST_BYTES:
            scan_warnings.append(
                f"package.json exceeds the {MAX_MANIFEST_BYTES}-byte static read limit"
            )
            package = {}
        else:
            try:
                package = json.loads(package_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeError):
                package = {}
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        if isinstance(scripts, dict):
            for name in ("test", "lint", "check", "build"):
                script = scripts.get(name)
                if isinstance(script, str) and script.strip():
                    commands.append(
                        {"name": name, "command": f"npm run {name}", "status": "candidate"}
                    )
                elif name in scripts:
                    scan_warnings.append(
                        f"ignored non-string or empty package.json script: {name}"
                    )
    tests_path = repo / "tests"
    if (
        _safe_regular_file(repo, "pyproject.toml")
        and tests_path.is_dir()
        and not tests_path.is_symlink()
    ):
        commands.append(
            {
                "name": "test",
                "command": "python3 -m unittest discover -s tests -v",
                "status": "candidate",
            }
        )
    return commands


def _notion_hints(repo: Path) -> tuple[list[str], bool]:
    hints: list[str] = []
    inspected = 0
    pending = [repo]
    while pending:
        root = pending.pop()
        try:
            entries = os.scandir(root)
        except OSError:
            continue
        with entries:
            for entry in entries:
                inspected += 1
                if inspected > MAX_ADAPTER_SCAN_ENTRIES:
                    return sorted(hints), True
                candidate = Path(entry.path)
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in SCAN_EXCLUDED_DIRS:
                            continue
                        if root == repo / ".maestro" and entry.name in {"state", "backups"}:
                            continue
                        pending.append(candidate)
                        continue
                    if entry.is_file(follow_symlinks=False) and "notion" in entry.name.casefold():
                        hints.append(candidate.relative_to(repo).as_posix())
                        if len(hints) >= 20:
                            return sorted(hints), True
                except OSError:
                    continue
    return sorted(hints), False


def inspect_adapter(repo_path: str | Path) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    profiles: list[str] = []
    evidence: list[dict[str, str]] = []
    scan_warnings: list[str] = []
    markers = {
        "jvm-build": ["gradlew", "mvnw", "pom.xml", "build.gradle", "build.gradle.kts"],
        "node": ["package.json"],
        "python": ["pyproject.toml", "requirements.txt"],
        "rust": ["Cargo.toml"],
    }
    registry = load_registry()
    registry_errors = validate_registry(registry)
    if registry_errors:
        raise MaestroError("REGISTRY_INVALID", "; ".join(registry_errors))
    adapter = next(
        (
            item
            for item in registry["adapters"]
            if item["adapter_id"] == "generic-repo"
        ),
        None,
    )
    if adapter is None:
        raise MaestroError("REGISTRY_INVALID", "generic-repo adapter is missing")
    declared_markers = set(adapter["detection"]["markers"])
    profile_markers = {path for paths in markers.values() for path in paths}
    if declared_markers != profile_markers:
        raise MaestroError(
            "REGISTRY_INVALID",
            "generic-repo marker registry and profile mapping differ",
        )
    marker_paths = sorted(declared_markers)
    for path in marker_paths:
        target = repo / path
        if target.is_symlink():
            scan_warnings.append(f"ignored symlinked marker: {path}")
        elif target.exists() and not target.is_file():
            scan_warnings.append(f"ignored non-file marker: {path}")
    for profile, paths in markers.items():
        found = [path for path in paths if _safe_regular_file(repo, path)]
        if found:
            profiles.append(profile)
            evidence.extend({"profile": profile, "path": path} for path in found)

    notion_hints, scan_truncated = _notion_hints(repo)
    authority_decision = "required" if notion_hints else "not_required"

    return {
        "schema_version": "maestro_adapter_inspection_v1",
        "repo_root": str(repo),
        "adapter": "generic-repo",
        "profiles_detected": sorted(profiles),
        "evidence": sorted(evidence, key=lambda item: (item["profile"], item["path"])),
        "candidate_commands": _package_commands(repo, scan_warnings),
        "notion_hints": notion_hints,
        "authority_decision": authority_decision,
        "scan_truncated": scan_truncated,
        "scan_limit_entries": MAX_ADAPTER_SCAN_ENTRIES,
        "scan_warnings": sorted(set(scan_warnings)),
        "writes_performed": False,
        "unsupported_suggestions": [
            f"{profile}: no specialized adapter is installed; generic-repo remains active"
            for profile in sorted(profiles)
        ],
    }


def _first_existing_regular(repo: Path, candidates: tuple[str, ...]) -> str | None:
    for relative_path in candidates:
        if _safe_regular_file(repo, relative_path):
            return relative_path
    return None


def _core_documents(repo: Path) -> dict[str, str]:
    return {
        "project": _first_existing_regular(
            repo,
            (
                "docs/project.md",
                "PROJECT.md",
                "docs/product.md",
            ),
        )
        or "docs/project.md",
        "architecture": _first_existing_regular(
            repo,
            (
                "docs/architecture.md",
                "ARCHITECTURE.md",
                "docs/architecture/overview.md",
                "docs/architecture/maestro-v0.md",
            ),
        )
        or "docs/architecture.md",
    }


def _default_documentation(repo: Path) -> dict[str, Any]:
    return {
        "provider": "markdown",
        "entrypoint": "docs/README.md",
        "core_documents": _core_documents(repo),
        "external_topics": {},
    }


def _project_state(repo: Path, inspection: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "maestro_project_v1",
        "kind": "project",
        "project_id": slugify(repo.name),
        "state_root": ".maestro/state",
        "documentation": _default_documentation(repo),
        "self_improvement": {
            "mode": "verified-project-conventions",
            "max_updates_per_run": 1,
        },
        "adapters": ["generic-repo"],
        "profiles": inspection["profiles_detected"],
        "commands": inspection["candidate_commands"],
        "verification_commands": [],
        "expertise": {
            "active_pack_paths": [],
        },
        "approval_required_for": CORE_APPROVAL_GATES,
    }


def checkout_id(repo: Path) -> str:
    return sha256_text(str(repo.resolve()))[:12]


def _lock_state(managed_sha256: str) -> dict[str, Any]:
    registry = load_registry()
    adapter = next(
        item
        for item in registry["adapters"]
        if item["adapter_id"] == "generic-repo"
    )
    return {
        "schema_version": "maestro_lock_v1",
        "kind": "lock",
        "framework": {"name": "harness-maestro", "version": __version__},
        "registry": {
            "version": REGISTRY_FORMAT_VERSION,
            "sha256": registry_digest(),
        },
        "managed": {"sha256": managed_sha256},
        "adapters": [
            {
                "id": adapter["adapter_id"],
                "version": adapter["version"],
            }
        ],
    }


def _desired_seed_files(
    repo: Path,
    inspection: dict[str, Any] | None = None,
) -> dict[str, str]:
    for relative_path in INIT_MANAGED_PATHS:
        safe_target(repo, relative_path)
    inspection = inspection or inspect_adapter(repo)
    desired: dict[str, str] = {}
    core_documents = _core_documents(repo)

    agents_path = repo / "AGENTS.md"
    agents_text = _bounded_text(agents_path, default="# AGENTS.md\n")
    desired["AGENTS.md"] = managed_block(
        agents_text, AGENTS_BEGIN, AGENTS_END, AGENTS_BODY
    )

    ignore_path = repo / ".gitignore"
    ignore_text = _bounded_text(ignore_path, default="")
    desired[".gitignore"] = managed_block(
        ignore_text, GITIGNORE_BEGIN, GITIGNORE_END, GITIGNORE_BODY
    )

    project_path = repo / ".maestro/project.json"
    if not project_path.exists():
        desired[".maestro/project.json"] = pretty_json(_project_state(repo, inspection))
    else:
        existing_project = read_json(project_path)
        if not isinstance(existing_project, dict):
            raise MaestroError("STATE_INVALID", "project.json must contain an object")
        updated_project = dict(existing_project)
        updated_project.pop("checkout_id", None)
        updated_project["state_root"] = ".maestro/state"
        updated_project["adapters"] = ["generic-repo"]
        updated_project["profiles"] = inspection["profiles_detected"]
        updated_project["commands"] = inspection["candidate_commands"]
        updated_project.setdefault("verification_commands", [])
        updated_project.setdefault(
            "expertise",
            {"active_pack_paths": []},
        )
        existing_approval_gates = updated_project.get("approval_required_for")
        if not isinstance(existing_approval_gates, list) or not all(
            isinstance(item, str) and bool(item.strip())
            for item in existing_approval_gates
        ):
            existing_approval_gates = []
        updated_project["approval_required_for"] = list(
            dict.fromkeys([*existing_approval_gates, *CORE_APPROVAL_GATES])
        )
        documentation = updated_project.get("documentation")
        if not isinstance(documentation, dict):
            documentation = _default_documentation(repo)
        else:
            documentation = dict(documentation)
            legacy_authority = documentation.pop("default_authority", None)
            documentation.setdefault(
                "provider",
                "markdown" if legacy_authority in {None, "markdown"} else "custom",
            )
            documentation.setdefault("entrypoint", "docs/README.md")
            documentation.setdefault("core_documents", core_documents)
            documentation.setdefault("external_topics", {})
        updated_project["documentation"] = documentation
        updated_project.setdefault(
            "self_improvement",
            {
                "mode": "verified-project-conventions",
                "max_updates_per_run": 1,
            },
        )
        if updated_project != existing_project:
            desired[".maestro/project.json"] = pretty_json(updated_project)
    if not (repo / "docs/README.md").exists():
        desired["docs/README.md"] = _docs_index(core_documents)
    if (
        core_documents["project"] == "docs/project.md"
        and not (repo / "docs/project.md").exists()
    ):
        desired["docs/project.md"] = PROJECT_DOC
    if (
        core_documents["architecture"] == "docs/architecture.md"
        and not (repo / "docs/architecture.md").exists()
    ):
        desired["docs/architecture.md"] = ARCHITECTURE_DOC
    if not (repo / "docs/governance/document-lifecycle.md").exists():
        desired["docs/governance/document-lifecycle.md"] = DOCUMENT_POLICY

    managed_path = repo / ".maestro/managed.json"
    lock_path = repo / ".maestro/lock.json"
    if managed_path.exists() != lock_path.exists():
        raise MaestroError(
            "STATE_INCOMPLETE",
            "managed.json and lock.json must either both exist or both be initialized",
        )
    if not managed_path.exists():
        entries: list[dict[str, Any]] = []
        for path, content in sorted(desired.items()):
            if path == ".maestro/project.json":
                continue
            if path == "AGENTS.md":
                block = extract_managed_block(content, AGENTS_BEGIN, AGENTS_END)
                entries.append(
                    {
                        "path": path,
                        "ownership": "managed_block",
                        "sha256": sha256_text(block or ""),
                        "preserve_on_drift": True,
                    }
                )
            elif path == ".gitignore":
                block = extract_managed_block(content, GITIGNORE_BEGIN, GITIGNORE_END)
                entries.append(
                    {
                        "path": path,
                        "ownership": "managed_block",
                        "sha256": sha256_text(block or ""),
                        "preserve_on_drift": True,
                    }
                )
            else:
                entries.append(
                    {
                        "path": path,
                        "ownership": "seeded",
                        "sha256": sha256_text(content),
                        "preserve_on_drift": True,
                    }
                )
        indexed_paths = {str(entry["path"]) for entry in entries}
        for path in (
            "docs/README.md",
            "docs/project.md",
            "docs/architecture.md",
            "docs/governance/document-lifecycle.md",
        ):
            if path in indexed_paths or not (repo / path).is_file():
                continue
            target = safe_target(repo, path)
            entries.append(
                {
                    "path": path,
                    "ownership": "user_owned",
                    "sha256": file_sha256(target),
                    "preserve_on_drift": True,
                }
            )
        entries.sort(key=lambda entry: entry["path"])
        managed = {
            "schema_version": "maestro_managed_v1",
            "kind": "managed",
            "entries": entries,
        }
        managed_content = pretty_json(managed)
        desired[".maestro/managed.json"] = managed_content
        desired[".maestro/lock.json"] = pretty_json(
            _lock_state(sha256_text(managed_content))
        )
    else:
        existing_managed = read_json(managed_path)
        existing_lock = read_json(lock_path)
        locked_managed_digest = existing_lock.get("managed", {}).get("sha256")
        current_managed_digest = file_sha256(managed_path)
        if locked_managed_digest != current_managed_digest:
            raise MaestroError(
                "MANAGED_INDEX_DRIFT",
                "managed.json no longer matches lock.json; diagnose before generating an upgrade plan",
                exit_code=3,
            )
        existing_entries = existing_managed.get("entries")
        if not isinstance(existing_entries, list) or any(
            not isinstance(entry, dict) for entry in existing_entries
        ):
            raise MaestroError("STATE_INVALID", "managed.json entries are invalid")
        entries_by_path: dict[str, dict[str, Any]] = {}
        supported_entry_paths = {
            "AGENTS.md",
            ".gitignore",
            "docs/README.md",
            "docs/project.md",
            "docs/architecture.md",
            "docs/governance/document-lifecycle.md",
        }
        seen_paths: set[str] = set()
        for entry in existing_entries:
            path = entry.get("path")
            if not isinstance(path, str) or path in seen_paths:
                raise MaestroError("STATE_INVALID", "managed.json contains invalid paths")
            seen_paths.add(path)
            if path in supported_entry_paths:
                safe_target(repo, path)
                entries_by_path[path] = entry
        for path, begin, end in (
            ("AGENTS.md", AGENTS_BEGIN, AGENTS_END),
            (".gitignore", GITIGNORE_BEGIN, GITIGNORE_END),
        ):
            block = extract_managed_block(desired[path], begin, end)
            entries_by_path[path] = {
                "path": path,
                "ownership": "managed_block",
                "sha256": sha256_text(block or ""),
                "preserve_on_drift": True,
            }
        for path in (
            "docs/README.md",
            "docs/project.md",
            "docs/architecture.md",
            "docs/governance/document-lifecycle.md",
        ):
            if path in desired:
                entries_by_path[path] = {
                    "path": path,
                    "ownership": "seeded",
                    "sha256": sha256_text(desired[path]),
                    "preserve_on_drift": True,
                }
            elif path not in entries_by_path:
                target = safe_target(repo, path)
                if not target.is_file():
                    continue
                entries_by_path[path] = {
                    "path": path,
                    "ownership": "user_owned",
                    "sha256": file_sha256(target),
                    "preserve_on_drift": True,
                }
            else:
                target = safe_target(repo, path)
                existing_entry = entries_by_path[path]
                ownership = existing_entry.get("ownership")
                digest = existing_entry.get("sha256")
                digest_valid = (
                    isinstance(digest, str)
                    and len(digest) == 64
                    and all(
                        character in "0123456789abcdef"
                        for character in digest
                    )
                )
                if ownership == "user_owned":
                    current_digest = file_sha256(target)
                    if digest_valid and current_digest != digest:
                        inspection["scan_warnings"].append(
                            "user-owned document baseline will advance after review: "
                            f"{path}"
                        )
                    entries_by_path[path] = {
                        "path": path,
                        "ownership": "user_owned",
                        "sha256": current_digest,
                        "preserve_on_drift": True,
                    }
                elif ownership == "seeded" and digest_valid:
                    current_digest = file_sha256(target)
                    if current_digest != digest:
                        inspection["scan_warnings"].append(
                            "seeded document changed; review reclassification "
                            f"to user_owned: {path}"
                        )
                        entries_by_path[path] = {
                            "path": path,
                            "ownership": "user_owned",
                            "sha256": current_digest,
                            "preserve_on_drift": True,
                        }
                    else:
                        entries_by_path[path] = {
                            "path": path,
                            "ownership": ownership,
                            "sha256": digest,
                            "preserve_on_drift": True,
                        }
                else:
                    entries_by_path[path] = {
                        "path": path,
                        "ownership": "user_owned",
                        "sha256": file_sha256(target),
                        "preserve_on_drift": True,
                    }
        updated_managed = {
            "schema_version": "maestro_managed_v1",
            "kind": "managed",
            "entries": [
                entries_by_path[path]
                for path in sorted(entries_by_path)
            ],
        }
        managed_content = pretty_json(updated_managed)
        managed_digest = sha256_text(managed_content)
        if file_sha256(managed_path) != managed_digest:
            desired[".maestro/managed.json"] = managed_content
        lock_content = pretty_json(_lock_state(managed_digest))
        if file_sha256(lock_path) != sha256_text(lock_content):
            desired[".maestro/lock.json"] = lock_content

    return desired


def build_init_plan(repo_path: str | Path) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    for relative_path in INIT_MANAGED_PATHS:
        safe_target(repo, relative_path)
    inspection = inspect_adapter(repo)
    desired = _desired_seed_files(repo, inspection)
    operations: list[dict[str, Any]] = []
    for relative_path, content in sorted(desired.items()):
        target = safe_target(repo, relative_path)
        before = file_sha256(target)
        after = sha256_text(content)
        if before == after:
            continue
        operations.append(
            {
                "op": "create" if before is None else "replace_managed_content",
                "path": relative_path,
                "before_sha256": before,
                "after_sha256": after,
                "content": content,
            }
        )
    snapshot = {
        relative_path: file_sha256(safe_target(repo, relative_path))
        for relative_path in sorted(INIT_MANAGED_PATHS)
    }
    warnings: list[str] = []
    if inspection["authority_decision"] == "required":
        warnings.append(
            "Notion-like files were detected. Markdown remains the default authority "
            "until a topic-specific external authority is explicitly approved."
        )
    if inspection["scan_truncated"]:
        warnings.append(
            f"Static adapter discovery stopped after {inspection['scan_limit_entries']} entries."
        )
    warnings.extend(sorted(inspection["scan_warnings"]))
    document_paths, document_scan_notices = scan_document_paths(repo)
    if any(
        notice.startswith(SCAN_LIMIT_PREFIX)
        for notice in document_scan_notices
    ):
        warnings.append(
            "Documentation metadata migration scanning was truncated by "
            "resource limits; Maestro Doctor can report only the same bounded "
            "file-to-field evidence."
        )
    metadata_migrations: list[str] = []
    docs_root = repo / "docs"
    for path in document_paths:
        if "archive" in path.relative_to(docs_root).parts:
            continue
        metadata = frontmatter_fields(
            path.read_text(encoding="utf-8", errors="replace")
        )
        missing = sorted(
            field
            for field in REQUIRED_DOCUMENT_FIELDS
            if field not in metadata or not metadata[field].strip()
        )
        if missing:
            metadata_migrations.append(
                f"{path.relative_to(repo).as_posix()} "
                f"(missing: {', '.join(missing)})"
            )
    for item in metadata_migrations[:8]:
        warnings.append(
            "Existing Markdown document was preserved and needs typed "
            f"frontmatter: {item}."
        )
    if len(metadata_migrations) > 8:
        warnings.append(
            f"{len(metadata_migrations) - 8} additional existing Markdown "
            "documents need typed frontmatter; run Maestro Doctor for its "
            "bounded file-to-field map."
        )
    if metadata_migrations:
        warnings.append(
            "After adding frontmatter manually, preview Maestro upgrade and "
            "accept only the reviewed user-owned document baseline changes."
        )
    base = {
        "schema_version": "maestro_operation_plan_v1",
        "command": "init",
        "repo_realpath": str(repo),
        "base_fingerprint": sha256_text(canonical_json(snapshot)),
        "operations": operations,
        "preconditions": [
            "repository realpath is unchanged",
            "managed paths do not traverse symlinks",
            "every before digest still matches",
            "the plan matches the current initializer",
        ],
        "conflicts": [],
        "warnings": warnings,
    }
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def build_upgrade_plan(repo_path: str | Path) -> dict[str, Any]:
    plan = build_init_plan(repo_path)
    plan["command"] = "upgrade"
    unsigned = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(unsigned))
    plan["plan_id"] = digest[:20]
    plan["plan_digest"] = digest
    return plan


def apply_plan(
    plan_path: str | Path,
    repo_override: str | Path | None = None,
    *,
    expected_command: str = "init",
) -> dict[str, Any]:
    plan = read_json(Path(plan_path))
    if plan.get("schema_version") != "maestro_operation_plan_v1":
        raise MaestroError("PLAN_INVALID", "Unsupported plan schema")
    if expected_command not in {"init", "upgrade"}:
        raise MaestroError("PLAN_INVALID", "Unsupported plan application command")
    if plan.get("command") != expected_command:
        raise MaestroError(
            "PLAN_INVALID",
            f"Plan belongs to maestro {plan.get('command')}, not maestro {expected_command}",
        )
    expected = dict(plan)
    supplied_digest = expected.pop("plan_digest", None)
    expected.pop("plan_id", None)
    actual_digest = sha256_text(canonical_json(expected))
    if supplied_digest != actual_digest:
        raise MaestroError("PLAN_TAMPERED", "Plan digest does not match its contents", exit_code=3)
    if plan.get("plan_id") != actual_digest[:20]:
        raise MaestroError("PLAN_TAMPERED", "Plan ID does not match its digest", exit_code=3)

    repo = ensure_repo(repo_override or plan.get("repo_realpath", ""))
    if str(repo) != plan.get("repo_realpath"):
        raise MaestroError("PLAN_REPO_MISMATCH", "Plan belongs to a different repository", exit_code=3)

    operations = plan.get("operations")
    if not isinstance(operations, list):
        raise MaestroError("PLAN_INVALID", "Plan operations must be a list")

    originals: dict[Path, bytes | None] = {}
    for operation in operations:
        if not isinstance(operation, dict):
            raise MaestroError("PLAN_INVALID", "Plan operation must be an object")
        if set(operation) != {
            "op",
            "path",
            "before_sha256",
            "after_sha256",
            "content",
        }:
            raise MaestroError("PLAN_INVALID", "Plan operation has unsupported fields")
        relative_path = operation.get("path")
        if not isinstance(relative_path, str) or relative_path not in INIT_MANAGED_PATHS:
            raise MaestroError(
                "PLAN_INVALID",
                f"Init plan may not manage this path: {relative_path!r}",
                exit_code=3,
            )
        if operation.get("op") not in {"create", "replace_managed_content"}:
            raise MaestroError("PLAN_INVALID", f"Unsupported init operation: {operation.get('op')!r}")
        if not isinstance(operation.get("content"), str):
            raise MaestroError("PLAN_INVALID", f"Operation content must be text: {relative_path}")
        target = safe_target(repo, relative_path)
        current = file_sha256(target)
        if current != operation.get("before_sha256"):
            raise MaestroError(
                "PLAN_STALE",
                f"File changed after preview: {relative_path}",
                exit_code=3,
            )
        content = operation["content"].encode("utf-8")
        if sha256_bytes(content) != operation.get("after_sha256"):
            raise MaestroError("PLAN_TAMPERED", f"Content hash mismatch: {relative_path}", exit_code=3)
        originals[target] = target.read_bytes() if target.exists() else None

    fresh_plan = (
        build_upgrade_plan(repo)
        if expected_command == "upgrade"
        else build_init_plan(repo)
    )
    if plan != fresh_plan:
        raise MaestroError(
            "PLAN_STALE",
            "Plan no longer matches the current repository and initializer; generate a fresh preview",
            exit_code=3,
        )

    created_directories: set[Path] = set()
    for target in originals:
        parent = target.parent
        while parent != repo and not parent.exists():
            created_directories.add(parent)
            parent = parent.parent

    written: list[Path] = []
    try:
        for operation in operations:
            target = safe_target(repo, str(operation["path"]))
            if file_sha256(target) != operation["before_sha256"]:
                raise MaestroError(
                    "PLAN_STALE",
                    f"File changed while applying the plan: {operation['path']}",
                    exit_code=3,
                )
            atomic_write(target, operation["content"].encode("utf-8"))
            written.append(target)
    except BaseException:
        for target in reversed(written):
            original = originals[target]
            if original is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write(target, original)
        for directory in sorted(
            created_directories,
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise

    return {
        "schema_version": "maestro_command_result_v1",
        "command": expected_command,
        "status": "applied",
        "repo_root": str(repo),
        "plan_id": plan.get("plan_id"),
        "changed_paths": [operation["path"] for operation in operations],
        "writes_performed": bool(operations),
    }


def git_ignored(repo: Path, relative_path: str) -> bool | None:
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", "--", relative_path],
            cwd=repo,
            check=False,
            capture_output=True,
        )
    except OSError:
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def git_indexed_paths(
    repo: Path,
    relative_paths: list[str],
) -> set[str] | None:
    """Return repository-relative paths present in Git's index.

    ``None`` means the directory is not a Git worktree or Git is unavailable.
    An empty set means Git is available but none of the requested paths are
    indexed. Index membership deliberately does not claim that a path has
    already been committed or pushed.
    """

    if not relative_paths:
        return set()
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", *relative_paths],
            cwd=repo,
            check=False,
            capture_output=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }
