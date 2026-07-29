from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .decisions import repository_revision
from .errors import MaestroError
from .expertise import load_expertise_catalog
from .registry import load_registry, registry_digest
from .util import (
    canonical_json,
    ensure_repo,
    read_json,
    safe_target,
    sha256_text,
)

TASK_COVERAGE_VERSION = "maestro_task_coverage_v1"
MAX_COVERAGE_ITEMS = 64
MAX_ALLOCATIONS_PER_ITEM = 16
MAX_SOURCE_REFS_PER_ITEM = 16
MAX_ID_CHARS = 128
MAX_GOAL_CHARS = 8_000
MAX_ITEM_TEXT_CHARS = 2_000
MAX_REF_CHARS = 512
MAX_RATIONALE_CHARS = 2_000
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")

ITEM_KINDS = {
    "outcome",
    "decision",
    "constraint",
    "prohibition",
    "verification",
    "learning",
}
MATERIALITY_LEVELS = {"blocking", "important", "supporting"}
EVIDENCE_TYPES = {
    "project-fact",
    "external-current",
    "external-stable",
    "owner-preference",
    "runtime-verification",
}
ALLOCATION_KINDS = {
    "project-fact",
    "expertise-guide",
    "lens",
    "research",
    "owner-decision",
    "runtime-verification",
    "checker",
    "convention",
    "deferred-explicit",
    "out-of-scope-explicit",
    "unresolved",
}
ALLOCATION_PREFIXES = {
    "project-fact": "project:",
    "expertise-guide": "guide:",
    "lens": "lens:",
    "research": "research:",
    "owner-decision": "owner:",
    "runtime-verification": "verification:",
    "checker": "checker:",
    "convention": "convention:",
    "deferred-explicit": "deferred:",
    "out-of-scope-explicit": "out-of-scope:",
    "unresolved": "unresolved:",
}
EVIDENCE_ALLOCATION_KINDS = {
    "project-fact": {"project-fact"},
    "external-current": {"research"},
    "external-stable": {"expertise-guide", "research"},
    "owner-preference": {"owner-decision", "convention"},
    "runtime-verification": {"runtime-verification", "checker"},
}
NON_CLOSING_ALLOCATION_KINDS = {
    "deferred-explicit",
    "out-of-scope-explicit",
    "unresolved",
}
TASK_COVERAGE_FIELDS = {
    "schema_version",
    "coverage_id",
    "goal",
    "goal_digest",
    "registry_digest",
    "base_revision",
    "mode",
    "assurance",
    "discovery_status",
    "allocation_status",
    "items",
    "writes_performed",
}
TASK_COVERAGE_DRAFT_FIELDS = {
    "discovery_status",
    "allocation_status",
    "items",
}
ITEM_FIELDS = {
    "item_id",
    "kind",
    "summary",
    "failure_if_omitted",
    "materiality",
    "evidence_types",
    "source_refs",
    "depends_on",
    "allocations",
}
ALLOCATION_FIELDS = {
    "kind",
    "target_ref",
    "evidence_types",
    "rationale",
}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _digest_payload(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["coverage_id"] = ""
    return sha256_text(canonical_json(payload))


def _valid_string(
    value: Any,
    *,
    maximum: int | None = None,
) -> bool:
    if (
        not isinstance(value, str)
        or not value.strip()
        or (maximum is not None and len(value) > maximum)
    ):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _valid_unique_strings(
    value: Any,
    *,
    maximum: int,
    nonempty: bool = False,
    string_maximum: int | None = None,
) -> bool:
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and len(value) <= maximum
        and all(
            _valid_string(item, maximum=string_maximum)
            for item in value
        )
        and len(value) == len(set(value))
    )


def _safe_text_digest(value: Any) -> str | None:
    if not _valid_string(value, maximum=MAX_GOAL_CHARS):
        return None
    try:
        return sha256_text(value)
    except UnicodeEncodeError:
        return None


def _target_context(
    repo_path: str | Path | None,
    *,
    include_candidates: bool = True,
) -> dict[str, set[str]]:
    registry = load_registry()
    catalog = load_expertise_catalog(
        repo_path,
        include_candidates=(
            repo_path is not None and include_candidates
        ),
    )
    guide_targets: set[str] = set()
    for pack in catalog:
        pack_id = pack.get("expertise_pack_id")
        for guide in pack.get("guides", []):
            guide_id = guide.get("guide_id")
            if isinstance(guide_id, str):
                guide_targets.add(guide_id)
                if isinstance(pack_id, str):
                    guide_targets.add(f"{pack_id}/{guide_id}")
    checker_ids = {"test-suite"}
    if repo_path is not None:
        try:
            project = read_json(
                safe_target(Path(repo_path), ".maestro/project.json")
            )
        except MaestroError:
            project = {}
        for command in project.get("commands", []):
            name = (
                command.get("name")
                if isinstance(command, dict)
                else None
            )
            if (
                isinstance(name, str)
                and ID_PATTERN.fullmatch(name) is not None
            ):
                checker_ids.add(name)
    return {
        "lens": {
            item["lens_id"]
            for item in registry["lenses"]
            if isinstance(item.get("lens_id"), str)
        },
        "expertise-guide": guide_targets,
        "executor": {
            item["executor_id"]
            for item in registry["executors"]
            if isinstance(item.get("executor_id"), str)
        },
        "checker": checker_ids,
    }


def _target_resolves(
    kind: str,
    target_ref: str,
    *,
    repo: Path | None,
    target_context: dict[str, set[str]],
) -> bool:
    suffix = target_ref[len(ALLOCATION_PREFIXES[kind]) :]
    if kind in {"project-fact", "convention"}:
        if repo is None:
            return False
        relative_path = suffix.split("#", 1)[0]
        try:
            target = safe_target(repo, relative_path)
        except MaestroError:
            return False
        return target.is_file() and not target.is_symlink()
    if kind in {"lens", "expertise-guide"}:
        return suffix in target_context[kind]
    if kind == "checker":
        parts = suffix.split("/", 1)
        executor_id = parts[0]
        return (
            len(parts) == 2
            and executor_id == "verifier"
            and executor_id in target_context["executor"]
            and parts[1] in target_context["checker"]
        )
    if kind == "runtime-verification":
        parts = suffix.split("/", 1)
        executor_id = parts[0]
        return (
            len(parts) == 2
            and executor_id == "verifier"
            and executor_id in target_context["executor"]
            and parts[1] in target_context["checker"]
        )
    if kind == "research":
        executor_id = suffix.split("/", 1)[0]
        return (
            executor_id == "researcher"
            and executor_id in target_context["executor"]
        )
    if kind == "owner-decision":
        return suffix.split("/", 1)[0] in {"user", "project-owner"}
    return True


def _validate_revision(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    fields = {"kind", "head", "state_digest", "dirty_path_count"}
    if not isinstance(value, dict) or set(value) != fields:
        issues.append(
            _issue(
                "TASK_COVERAGE_REVISION_INVALID",
                path,
                "Revision must contain kind, head, state_digest, and dirty_path_count.",
            )
        )
        return
    if value["kind"] == "git":
        if (
            not _valid_string(value["head"])
            or not isinstance(value["state_digest"], str)
            or DIGEST_PATTERN.fullmatch(value["state_digest"]) is None
            or not isinstance(value["dirty_path_count"], int)
            or isinstance(value["dirty_path_count"], bool)
            or value["dirty_path_count"] < 0
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_REVISION_INVALID",
                    path,
                    "Git revision fields are invalid.",
                )
            )
    elif value["kind"] == "unavailable":
        if any(
            value[field] is not None
            for field in ("head", "state_digest", "dirty_path_count")
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_REVISION_INVALID",
                    path,
                    "Unavailable revision fields must be null.",
                )
            )
    else:
        issues.append(
            _issue(
                "TASK_COVERAGE_REVISION_INVALID",
                f"{path}.kind",
                "Revision kind must be git or unavailable.",
            )
        )


def _find_dependency_cycle(
    dependencies: dict[str, list[str]],
) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(item_id: str) -> list[str] | None:
        if item_id in visiting:
            start = stack.index(item_id)
            return [*stack[start:], item_id]
        if item_id in visited:
            return None
        visiting.add(item_id)
        stack.append(item_id)
        for dependency in dependencies.get(item_id, []):
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        stack.pop()
        visiting.remove(item_id)
        visited.add(item_id)
        return None

    for item_id in dependencies:
        cycle = visit(item_id)
        if cycle is not None:
            return cycle
    return None


def _validate_allocation(
    allocation: Any,
    *,
    item_evidence_types: set[str],
    repo: Path | None,
    target_context: dict[str, set[str]],
    path: str,
    issues: list[dict[str, str]],
) -> tuple[str, str] | None:
    if not isinstance(allocation, dict) or set(allocation) != ALLOCATION_FIELDS:
        issues.append(
            _issue(
                "TASK_COVERAGE_ALLOCATION_INVALID",
                path,
                "Allocation fields are incomplete or unknown.",
            )
        )
        return None
    kind = allocation.get("kind")
    target_ref = allocation.get("target_ref")
    evidence_types = allocation.get("evidence_types")
    if not isinstance(kind, str) or kind not in ALLOCATION_KINDS:
        issues.append(
            _issue(
                "TASK_COVERAGE_ALLOCATION_KIND_INVALID",
                f"{path}.kind",
                "Allocation kind is not supported.",
            )
        )
    elif (
        not _valid_string(target_ref, maximum=MAX_REF_CHARS)
        or not target_ref.startswith(ALLOCATION_PREFIXES[kind])
        or target_ref == ALLOCATION_PREFIXES[kind]
    ):
        issues.append(
            _issue(
                "TASK_COVERAGE_TARGET_REF_INVALID",
                f"{path}.target_ref",
                f"{kind} target_ref must start with {ALLOCATION_PREFIXES[kind]}",
            )
        )
    elif not _target_resolves(
        kind,
        target_ref,
        repo=repo,
        target_context=target_context,
    ):
        issues.append(
            _issue(
                "TASK_COVERAGE_TARGET_UNRESOLVED",
                f"{path}.target_ref",
                "Allocation target does not resolve in the bound project and Registry.",
            )
        )
    if (
        not _valid_unique_strings(
            evidence_types,
            maximum=len(EVIDENCE_TYPES),
            nonempty=True,
            string_maximum=MAX_REF_CHARS,
        )
        or not set(evidence_types).issubset(EVIDENCE_TYPES)
        or not set(evidence_types).issubset(item_evidence_types)
    ):
        issues.append(
            _issue(
                "TASK_COVERAGE_ALLOCATION_EVIDENCE_INVALID",
                f"{path}.evidence_types",
                "Allocation evidence types must be unique and required by the item.",
            )
        )
    if not _valid_string(
        allocation.get("rationale"),
        maximum=MAX_RATIONALE_CHARS,
    ):
        issues.append(
            _issue(
                "TASK_COVERAGE_ALLOCATION_RATIONALE_INVALID",
                f"{path}.rationale",
                "Allocation rationale must be non-empty.",
            )
        )
    if isinstance(kind, str) and isinstance(target_ref, str):
        return kind, target_ref
    return None


def _validate_items(
    items: Any,
    *,
    allocation_complete: bool,
    repo: Path | None,
    target_context: dict[str, set[str]],
    issues: list[dict[str, str]],
) -> None:
    if (
        not isinstance(items, list)
        or not 1 <= len(items) <= MAX_COVERAGE_ITEMS
    ):
        issues.append(
            _issue(
                "TASK_COVERAGE_ITEM_LIMIT_INVALID",
                "items",
                (
                    "Coverage must contain between one and "
                    f"{MAX_COVERAGE_ITEMS} items; items are never truncated."
                ),
            )
        )
        return

    item_ids: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    valid_items: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        path = f"items[{index}]"
        if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
            issues.append(
                _issue(
                    "TASK_COVERAGE_ITEM_INVALID",
                    path,
                    "Coverage item fields are incomplete or unknown.",
                )
            )
            continue
        item_id = item.get("item_id")
        if (
            not isinstance(item_id, str)
            or len(item_id) > MAX_ID_CHARS
            or ID_PATTERN.fullmatch(item_id) is None
            or item_id in item_ids
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_ITEM_ID_INVALID",
                    f"{path}.item_id",
                    "item_id must be a unique lowercase kebab-case identifier.",
                )
            )
            continue
        item_ids.add(item_id)
        raw_dependencies = item.get("depends_on")
        dependencies[item_id] = (
            raw_dependencies
            if isinstance(raw_dependencies, list)
            and all(isinstance(value, str) for value in raw_dependencies)
            else []
        )
        valid_items.append((index, item))

    for index, item in valid_items:
        path = f"items[{index}]"
        evidence_types = item.get("evidence_types")
        if (
            not isinstance(item.get("kind"), str)
            or item["kind"] not in ITEM_KINDS
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_ITEM_KIND_INVALID",
                    f"{path}.kind",
                    "Coverage item kind is not supported.",
                )
            )
        for field in ("summary", "failure_if_omitted"):
            if not _valid_string(
                item.get(field),
                maximum=MAX_ITEM_TEXT_CHARS,
            ):
                issues.append(
                    _issue(
                        "TASK_COVERAGE_ITEM_TEXT_INVALID",
                        f"{path}.{field}",
                        f"{field} must be non-empty.",
                    )
                )
        if (
            not isinstance(item.get("materiality"), str)
            or item["materiality"] not in MATERIALITY_LEVELS
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_MATERIALITY_INVALID",
                    f"{path}.materiality",
                    "Materiality must be blocking, important, or supporting.",
                )
            )
        if (
            not _valid_unique_strings(
                evidence_types,
                maximum=len(EVIDENCE_TYPES),
                nonempty=True,
                string_maximum=MAX_REF_CHARS,
            )
            or not set(evidence_types).issubset(EVIDENCE_TYPES)
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_EVIDENCE_TYPES_INVALID",
                    f"{path}.evidence_types",
                    "Evidence types must be a non-empty unique supported list.",
                )
            )
            item_evidence_types: set[str] = set()
        else:
            item_evidence_types = set(evidence_types)
        if not _valid_unique_strings(
            item.get("source_refs"),
            maximum=MAX_SOURCE_REFS_PER_ITEM,
            string_maximum=MAX_REF_CHARS,
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_SOURCE_REFS_INVALID",
                    f"{path}.source_refs",
                    "source_refs must be a unique bounded string list.",
                )
            )
        depends_on = item.get("depends_on")
        if not _valid_unique_strings(
            depends_on,
            maximum=MAX_COVERAGE_ITEMS,
            string_maximum=MAX_ID_CHARS,
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_DEPENDENCIES_INVALID",
                    f"{path}.depends_on",
                    "depends_on must be a unique bounded item-id list.",
                )
            )
        else:
            missing = sorted(set(depends_on) - item_ids)
            if item["item_id"] in depends_on or missing:
                issues.append(
                    _issue(
                        "TASK_COVERAGE_DEPENDENCY_INVALID",
                        f"{path}.depends_on",
                        (
                            "Dependencies must name other declared items"
                            + (f": {', '.join(missing)}" if missing else ".")
                        ),
                    )
                )

        allocations = item.get("allocations")
        if (
            not isinstance(allocations, list)
            or len(allocations) > MAX_ALLOCATIONS_PER_ITEM
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_ALLOCATION_LIMIT_INVALID",
                    f"{path}.allocations",
                    (
                        "allocations must be a list with at most "
                        f"{MAX_ALLOCATIONS_PER_ITEM} entries."
                    ),
                )
            )
            continue
        allocation_keys: set[tuple[str, str]] = set()
        covered: dict[str, set[str]] = {
            evidence_type: set() for evidence_type in item_evidence_types
        }
        for allocation_index, allocation in enumerate(allocations):
            allocation_path = f"{path}.allocations[{allocation_index}]"
            key = _validate_allocation(
                allocation,
                item_evidence_types=item_evidence_types,
                repo=repo,
                target_context=target_context,
                path=allocation_path,
                issues=issues,
            )
            if key is not None:
                if key in allocation_keys:
                    issues.append(
                        _issue(
                            "TASK_COVERAGE_ALLOCATION_DUPLICATE",
                            allocation_path,
                            "Allocation kind and target_ref must be unique per item.",
                        )
                    )
                allocation_keys.add(key)
            if not isinstance(allocation, dict):
                continue
            allocation_kind = allocation.get("kind")
            allocation_evidence = allocation.get("evidence_types")
            if (
                isinstance(allocation_kind, str)
                and allocation_kind in ALLOCATION_KINDS
                and isinstance(allocation_evidence, list)
            ):
                for evidence_type in allocation_evidence:
                    if (
                        isinstance(evidence_type, str)
                        and evidence_type in covered
                    ):
                        covered[evidence_type].add(allocation_kind)

        if not allocation_complete:
            continue
        if any(
            allocation.get("kind") == "unresolved"
            for allocation in allocations
            if isinstance(allocation, dict)
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_UNRESOLVED_ALLOCATION",
                    f"{path}.allocations",
                    "A complete allocation cannot contain unresolved work.",
                )
            )
        for evidence_type, allocation_kinds in covered.items():
            allowed_kinds = {
                *EVIDENCE_ALLOCATION_KINDS[evidence_type],
                "deferred-explicit",
                "out-of-scope-explicit",
            }
            if not allocation_kinds.intersection(allowed_kinds):
                issues.append(
                    _issue(
                        "TASK_COVERAGE_EVIDENCE_UNCOVERED",
                        f"{path}.evidence_types",
                        (
                            f"{evidence_type} requires one of: "
                            f"{', '.join(sorted(allowed_kinds))}."
                        ),
                    )
                )
        if item.get("materiality") == "blocking":
            closing_kinds = {
                allocation.get("kind")
                for allocation in allocations
                if isinstance(allocation, dict)
                and isinstance(allocation.get("kind"), str)
            } - NON_CLOSING_ALLOCATION_KINDS
            if not closing_kinds:
                issues.append(
                    _issue(
                        "TASK_COVERAGE_BLOCKING_ITEM_DEFERRED",
                        f"{path}.allocations",
                        "A blocking item cannot be closed only by deferral or exclusion.",
                    )
                )

    cycle = _find_dependency_cycle(dependencies)
    if cycle is not None:
        issues.append(
            _issue(
                "TASK_COVERAGE_DEPENDENCY_CYCLE",
                "items",
                f"Coverage dependencies contain a cycle: {' -> '.join(cycle)}.",
            )
        )


def validate_task_coverage(
    coverage: Any,
    *,
    goal: str,
    repo_path: str | Path,
    require_current_revision: bool = True,
) -> dict[str, Any]:
    """Validate declared-inventory closure without granting execution.

    ``require_current_revision=False`` is reserved for immutable lineage
    snapshots copied into a candidate after the coverage artifact was built.
    It still binds the exact goal, active Registry, and Git HEAD, but permits
    the candidate files themselves to change the dirty-worktree digest.
    """

    issues: list[dict[str, str]] = []
    try:
        repo: Path | None = ensure_repo(repo_path)
    except MaestroError as exc:
        repo = None
        issues.append(_issue(exc.code, "repo_path", exc.message))
    try:
        target_context = _target_context(
            repo,
            include_candidates=require_current_revision,
        )
    except MaestroError as exc:
        target_context = {
            "lens": set(),
            "expertise-guide": set(),
            "executor": set(),
            "checker": set(),
        }
        issues.append(_issue(exc.code, "target_context", exc.message))
    expected_goal_digest = _safe_text_digest(goal)
    if expected_goal_digest is None:
        issues.append(
            _issue(
                "TASK_COVERAGE_EXPECTED_GOAL_INVALID",
                "goal",
                "Expected coverage goal must be bounded, non-empty UTF-8 text.",
            )
        )
    if not isinstance(coverage, dict):
        issues.append(
            _issue(
                "TASK_COVERAGE_INVALID",
                "$",
                "Task Coverage must be an object.",
            )
        )
    else:
        if set(coverage) != TASK_COVERAGE_FIELDS:
            issues.append(
                _issue(
                    "TASK_COVERAGE_FIELDS_INVALID",
                    "$",
                    "Task Coverage fields are incomplete or unknown.",
                )
            )
        if coverage.get("schema_version") != TASK_COVERAGE_VERSION:
            issues.append(
                _issue(
                    "TASK_COVERAGE_VERSION_INVALID",
                    "schema_version",
                    f"Expected {TASK_COVERAGE_VERSION}.",
                )
            )
        if not _valid_string(
            coverage.get("goal"),
            maximum=MAX_GOAL_CHARS,
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_GOAL_INVALID",
                    "goal",
                    "Coverage goal must be non-empty.",
                )
            )
        if coverage.get("goal") != goal:
            issues.append(
                _issue(
                    "TASK_COVERAGE_GOAL_MISMATCH",
                    "goal",
                    "Coverage is bound to a different expected goal.",
                )
            )
        artifact_goal_digest = _safe_text_digest(coverage.get("goal"))
        if (
            not isinstance(coverage.get("goal_digest"), str)
            or artifact_goal_digest is None
            or coverage.get("goal_digest") != artifact_goal_digest
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_GOAL_DIGEST_INVALID",
                    "goal_digest",
                    "goal_digest does not bind the exact goal.",
                )
            )
        try:
            digest_valid = (
                isinstance(coverage.get("coverage_id"), str)
                and DIGEST_PATTERN.fullmatch(coverage["coverage_id"])
                is not None
                and coverage["coverage_id"] == _digest_payload(coverage)
            )
        except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
            digest_valid = False
        if not digest_valid:
            issues.append(
                _issue(
                    "TASK_COVERAGE_DIGEST_INVALID",
                    "coverage_id",
                    "coverage_id does not bind the complete coverage artifact.",
                )
            )
        if (
            not isinstance(coverage.get("registry_digest"), str)
            or DIGEST_PATTERN.fullmatch(coverage["registry_digest"]) is None
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_REGISTRY_DIGEST_INVALID",
                    "registry_digest",
                    "registry_digest must be a SHA-256 digest.",
                )
            )
        _validate_revision(coverage.get("base_revision"), "base_revision", issues)
        if coverage.get("mode") != "shadow":
            issues.append(
                _issue(
                    "TASK_COVERAGE_MODE_INVALID",
                    "mode",
                    "Task Coverage currently supports shadow mode only.",
                )
            )
        if coverage.get("assurance") != "declared-inventory-only":
            issues.append(
                _issue(
                    "TASK_COVERAGE_ASSURANCE_INVALID",
                    "assurance",
                    "Coverage assurance must state declared-inventory-only.",
                )
            )
        discovery_status = coverage.get("discovery_status")
        allocation_status = coverage.get("allocation_status")
        if (
            not isinstance(discovery_status, str)
            or discovery_status not in {"complete", "incomplete"}
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_DISCOVERY_STATUS_INVALID",
                    "discovery_status",
                    "Discovery status must be complete or incomplete.",
                )
            )
        if (
            not isinstance(allocation_status, str)
            or allocation_status not in {"complete", "incomplete"}
        ):
            issues.append(
                _issue(
                    "TASK_COVERAGE_ALLOCATION_STATUS_INVALID",
                    "allocation_status",
                    "Allocation status must be complete or incomplete.",
                )
            )
        if discovery_status == "incomplete" and allocation_status == "complete":
            issues.append(
                _issue(
                    "TASK_COVERAGE_STATUS_CONTRADICTION",
                    "allocation_status",
                    "Allocation cannot be complete while discovery is incomplete.",
                )
            )
        _validate_items(
            coverage.get("items"),
            allocation_complete=allocation_status == "complete",
            repo=repo,
            target_context=target_context,
            issues=issues,
        )
        if coverage.get("writes_performed") is not False:
            issues.append(
                _issue(
                    "TASK_COVERAGE_WRITES_INVALID",
                    "writes_performed",
                    "Task Coverage planning must remain read-only.",
                )
            )

        if repo is not None:
            if coverage.get("registry_digest") != registry_digest():
                issues.append(
                    _issue(
                        "TASK_COVERAGE_REGISTRY_STALE",
                        "registry_digest",
                        "Coverage was built against a different active Registry.",
                    )
                )
            current_revision = repository_revision(repo)
            if require_current_revision:
                revision_matches = (
                    coverage.get("base_revision") == current_revision
                )
            else:
                base_revision = coverage.get("base_revision")
                revision_matches = (
                    isinstance(base_revision, dict)
                    and (
                        (
                            base_revision.get("kind") == "git"
                            and current_revision.get("kind") == "git"
                            and base_revision.get("head")
                            == current_revision.get("head")
                        )
                        or (
                            base_revision.get("kind") != "git"
                            and base_revision == current_revision
                        )
                    )
                )
            if not revision_matches:
                issues.append(
                    _issue(
                        "TASK_COVERAGE_REVISION_STALE",
                        "base_revision",
                        (
                            "Coverage was built against a different repository "
                            "revision."
                        ),
                    )
                )

    coverage_status = "INVALID"
    if not issues and isinstance(coverage, dict):
        if (
            coverage.get("discovery_status") == "complete"
            and coverage.get("allocation_status") == "complete"
        ):
            coverage_status = "COMPLETE"
        else:
            coverage_status = "INCOMPLETE"
    return {
        "schema_version": "maestro_task_coverage_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "coverage_status": coverage_status,
        "execution_authority": "NONE",
        "issues": issues,
        "writes_performed": False,
    }


def build_task_coverage(
    repo_path: str | Path,
    goal: str,
    draft: Any,
) -> dict[str, Any]:
    """Bind a Host-declared coverage inventory to current project state."""

    if not _valid_string(goal, maximum=MAX_GOAL_CHARS):
        raise MaestroError(
            "TASK_COVERAGE_GOAL_INVALID",
            "Coverage goal must be bounded, non-empty UTF-8 text.",
        )
    if not isinstance(draft, dict) or set(draft) != TASK_COVERAGE_DRAFT_FIELDS:
        raise MaestroError(
            "TASK_COVERAGE_DRAFT_INVALID",
            (
                "Coverage draft must contain only discovery_status, "
                "allocation_status, and items."
            ),
        )
    coverage = {
        "schema_version": TASK_COVERAGE_VERSION,
        "coverage_id": "",
        "goal": goal,
        "goal_digest": _safe_text_digest(goal),
        "registry_digest": registry_digest(),
        "base_revision": repository_revision(repo_path),
        "mode": "shadow",
        "assurance": "declared-inventory-only",
        "discovery_status": draft.get("discovery_status"),
        "allocation_status": draft.get("allocation_status"),
        "items": copy.deepcopy(draft.get("items")),
        "writes_performed": False,
    }
    try:
        coverage["coverage_id"] = _digest_payload(coverage)
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError) as exc:
        raise MaestroError(
            "TASK_COVERAGE_TEXT_INVALID",
            "Coverage draft must contain bounded UTF-8 JSON values.",
        ) from exc
    result = validate_task_coverage(
        coverage,
        goal=goal,
        repo_path=repo_path,
    )
    if result["status"] != "PASS":
        raise MaestroError(
            "TASK_COVERAGE_INVALID",
            "; ".join(issue["message"] for issue in result["issues"]),
        )
    return coverage
