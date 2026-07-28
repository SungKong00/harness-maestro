from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import MaestroError
from .expertise import (
    PROJECT_PACK_FILENAME,
    candidate_expertise_statuses,
    expertise_manifest_digest,
    load_expertise_catalog,
    project_publication_snapshot,
    validate_project_expertise_against_registry,
)
from .expertise_changes import (
    candidate_change_set_context,
    require_change_set,
)
from .project import git_ignored
from .registry import load_registry, resource_root, validate_registry
from .release import (
    build_release_manifest,
    load_source_release_manifest,
    load_source_registry,
    release_manifest_path,
    source_registry_digest,
)
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
UPDATE_PLAN_VERSION = "maestro_expertise_update_plan_v1"
DEACTIVATION_PLAN_VERSION = "maestro_expertise_deactivation_plan_v1"
REJECTION_PLAN_VERSION = "maestro_expertise_rejection_plan_v1"
ARCHIVE_PLAN_VERSION = "maestro_expertise_archive_plan_v1"
RESTORE_PLAN_VERSION = "maestro_expertise_restore_plan_v1"
DELETE_PLAN_VERSION = "maestro_expertise_delete_plan_v1"
CHANGE_SET_PLAN_VERSION = "maestro_expertise_change_set_plan_v1"
EXPORT_PLAN_VERSION = "maestro_expertise_export_plan_v1"
GLOBAL_PROMOTION_PLAN_VERSION = (
    "maestro_expertise_global_promotion_plan_v2"
)
CONTRIBUTION_VERSION = "maestro_expertise_contribution_v1"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
APPROVAL_PATTERN = re.compile(
    r"^(?:owner_decision|held_out_evaluation):\S.+$"
)
MAX_CANDIDATES = 100
MAX_ACTIVATION_FILE_BYTES = 2_000_000
MAX_VIEWER_EVALUATION_CASES = 12
CANDIDATE_DISPOSITION_FILENAME = "disposition.json"
CANDIDATE_TOMBSTONE_VERSION = "maestro_expertise_candidate_tombstone_v1"
CANDIDATE_TOMBSTONE_ROOT = (
    ".maestro/state/candidates/expertise-tombstones"
)
CANDIDATE_DISPOSITION_VERSION = (
    "maestro_expertise_candidate_disposition_v1"
)
EXPERTISE_AUTHORITY_BLOCK = """<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->"""
GUIDE_REQUIRED_SECTIONS = (
    "purpose",
    "use when",
    "inputs",
    "decision checks",
    "required evidence",
    "reject or stop when",
    "verification",
    "counterexamples",
)
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
CANDIDATE_OPTIONAL_FIELDS = {"component_change", "generation"}
GENERATION_FIELDS = {
    "mode",
    "signal_fingerprint",
}
COMPONENT_CHANGE_REQUIRED_FIELDS = {
    "kind",
    "target_guide_id",
}
COMPONENT_CHANGE_OPTIONAL_FIELDS = {
    "source_pack_ids",
    "target_pack_ids",
    "change_set_id",
    "operation_id",
    "summary",
}
COMPONENT_CHANGE_KINDS = {
    "new-pack",
    "pack-merge",
    "pack-split",
    "guide-addition",
    "guide-revision",
    "guide-deprecation",
    "guide-move",
    "guide-copy",
    "trigger-adjustment",
    "source-refresh",
    "evaluation-extension",
}
GUIDE_COMPONENT_CHANGE_KINDS = {
    "guide-addition",
    "guide-revision",
    "guide-deprecation",
    "guide-move",
    "guide-copy",
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
    "quality_path",
    "pass_criteria",
    "regression_criteria",
}
QUALITY_EVALUATION_FIELDS = {
    "schema_version",
    "expertise_pack_id",
    "evaluated_on",
    "evaluator",
    "cases",
}
QUALITY_EVALUATOR_FIELDS = {
    "kind",
    "authoring_run_ref",
    "evaluation_run_ref",
}
QUALITY_CASE_FIELDS = {
    "case_id",
    "artifact",
    "criterion_results",
    "forbidden_behavior_results",
    "verdict",
}
QUALITY_ARTIFACT_FIELDS = {
    "schema_version",
    "case_id",
    "baseline_observation",
    "candidate_observation",
    "evidence_refs",
}
PUBLICATION_PLAN_FIELDS = {
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
CANDIDATE_DISPOSITION_PLAN_FIELDS = {
    "schema_version",
    "command",
    "repo_realpath",
    "candidate_id",
    "candidate_digest",
    "reason",
    "operations",
    "warnings",
    "writes_performed",
    "plan_id",
    "plan_digest",
}
DELETE_PLAN_FIELDS = {
    "schema_version",
    "command",
    "repo_realpath",
    "candidate_id",
    "candidate_digest",
    "confirmation",
    "replacement_pack_ids",
    "deleted_at",
    "operations",
    "warnings",
    "writes_performed",
    "plan_id",
    "plan_digest",
}
CHANGE_SET_PLAN_FIELDS = {
    "schema_version",
    "command",
    "repo_realpath",
    "change_set_id",
    "action",
    "candidate_ids",
    "approval_ref",
    "reason",
    "confirmation",
    "replacement_pack_ids",
    "deleted_at",
    "member_plan_digests",
    "operations",
    "warnings",
    "writes_performed",
    "plan_id",
    "plan_digest",
}
GLOBAL_PROMOTION_PLAN_FIELDS = {
    "schema_version",
    "command",
    "repo_realpath",
    "candidate_id",
    "expertise_pack_id",
    "skill_id",
    "approval_ref",
    "source_kind",
    "source_ref",
    "source_digest",
    "candidate_digest",
    "bundle_path",
    "bundle_digest",
    "release_manifest_before_sha256",
    "operations",
    "warnings",
    "writes_performed",
    "plan_id",
    "plan_digest",
}


def _require_individual_candidate_action(
    repo: Path,
    *,
    candidate_id: str,
) -> None:
    context = candidate_change_set_context(
        repo,
        candidate_id=candidate_id,
    )
    if context["atomic_required"]:
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_ATOMIC_REQUIRED",
            (
                f"{candidate_id} belongs to atomic ChangeSet "
                f"{context['change_set_id']}; preview and apply the "
                "ChangeSet as one unit."
            ),
        )


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
        not CANDIDATE_REQUIRED_FIELDS.issubset(candidate)
        or set(candidate) - CANDIDATE_REQUIRED_FIELDS
        - CANDIDATE_OPTIONAL_FIELDS
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
    component_change = candidate.get("component_change")
    if component_change is not None:
        if (
            not isinstance(component_change, dict)
            or not COMPONENT_CHANGE_REQUIRED_FIELDS.issubset(
                component_change
            )
            or set(component_change)
            - COMPONENT_CHANGE_REQUIRED_FIELDS
            - COMPONENT_CHANGE_OPTIONAL_FIELDS
            or component_change.get("kind") not in COMPONENT_CHANGE_KINDS
        ):
            return False
        target_guide_id = component_change.get("target_guide_id")
        source_pack_ids = component_change.get("source_pack_ids", [])
        target_pack_ids = component_change.get("target_pack_ids", [])
        if (
            not isinstance(source_pack_ids, list)
            or len(source_pack_ids) != len(set(source_pack_ids))
            or len(source_pack_ids) > 4
            or any(
                not isinstance(pack_id, str)
                or ID_PATTERN.fullmatch(pack_id) is None
                for pack_id in source_pack_ids
            )
            or not isinstance(target_pack_ids, list)
            or len(target_pack_ids) != len(set(target_pack_ids))
            or len(target_pack_ids) > 4
            or any(
                not isinstance(pack_id, str)
                or ID_PATTERN.fullmatch(pack_id) is None
                for pack_id in target_pack_ids
            )
        ):
            return False
        for field in ("change_set_id", "operation_id"):
            value = component_change.get(field)
            if value is not None and (
                not isinstance(value, str)
                or ID_PATTERN.fullmatch(value) is None
            ):
                return False
        if (
            component_change["kind"]
            in {"pack-merge", "pack-split", "guide-move", "guide-copy"}
            and not isinstance(component_change.get("change_set_id"), str)
        ):
            return False
        summary = component_change.get("summary")
        if summary is not None and (
            not isinstance(summary, str)
            or not summary.strip()
            or len(summary) > 200
        ):
            return False
        if component_change["kind"] in GUIDE_COMPONENT_CHANGE_KINDS:
            if (
                not isinstance(target_guide_id, str)
                or ID_PATTERN.fullmatch(target_guide_id) is None
            ):
                return False
            if (
                component_change["kind"] in {
                    "guide-addition",
                    "guide-revision",
                    "guide-move",
                    "guide-copy",
                }
                and target_guide_id not in guide_ids
            ):
                return False
            if (
                component_change["kind"] == "guide-deprecation"
                and target_guide_id in guide_ids
            ):
                return False
        elif target_guide_id is not None:
            return False
        if component_change["kind"] == "pack-merge":
            if (
                len(source_pack_ids) < 2
                or len(guide_ids) < 2
                or target_pack_ids
            ):
                return False
        elif component_change["kind"] == "pack-split":
            if len(source_pack_ids) != 1 or len(target_pack_ids) < 2:
                return False
        elif component_change["kind"] in {"guide-move", "guide-copy"}:
            if len(source_pack_ids) != 1 or len(target_pack_ids) > 1:
                return False
        elif source_pack_ids or target_pack_ids:
            return False
    generation = candidate.get("generation")
    if generation is not None:
        if (
            not isinstance(generation, dict)
            or set(generation) != GENERATION_FIELDS
            or generation.get("mode")
            not in {"automatic", "user-requested"}
        ):
            return False
        fingerprint = generation.get("signal_fingerprint")
        if generation["mode"] == "automatic":
            if (
                not isinstance(fingerprint, str)
                or re.fullmatch(r"[a-f0-9]{24}", fingerprint) is None
            ):
                return False
        elif fingerprint is not None:
            return False
    evaluation = candidate.get("evaluation")
    return (
        isinstance(evaluation, dict)
        and set(evaluation) == EVALUATION_FIELDS
        and evaluation.get("baseline")
        in {"no-pack", "persona-only", "existing-pack"}
        and evaluation.get("cases_path") == "evals/cases.json"
        and evaluation.get("quality_path") == "evals/quality.json"
        and _nonempty_unique_strings(evaluation.get("pass_criteria"))
        and _nonempty_unique_strings(evaluation.get("regression_criteria"))
    )


def _candidate_component_change(
    candidate: dict[str, Any],
    pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    declared = candidate.get("component_change")
    if isinstance(declared, dict):
        return copy.deepcopy(declared)
    if isinstance(pack, dict) and pack.get("extends") is not None:
        guide_ids = [
            guide["guide_id"]
            for guide in candidate.get("proposed_guides", [])
            if isinstance(guide, dict)
            and isinstance(guide.get("guide_id"), str)
        ]
        return {
            "kind": "guide-addition",
            "target_guide_id": guide_ids[0] if len(guide_ids) == 1 else None,
        }
    return {"kind": "new-pack", "target_guide_id": None}


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


def _candidate_tree_digest(root: Path) -> str:
    digests: list[dict[str, str]] = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise MaestroError(
                "EXPERTISE_CANDIDATE_SYMLINK_UNSAFE",
                f"Candidate contains a symlink: {path.relative_to(root)}",
            )
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        if relative_path in {
            CANDIDATE_DISPOSITION_FILENAME,
            "promotion-decision.json",
        }:
            continue
        size = path.stat().st_size
        total_bytes += size
        if (
            size > MAX_ACTIVATION_FILE_BYTES
            or total_bytes > MAX_ACTIVATION_FILE_BYTES
            or len(digests) >= 200
        ):
            raise MaestroError(
                "EXPERTISE_CANDIDATE_TOO_LARGE",
                "Candidate files exceed the bounded disposition digest limit.",
            )
        digests.append(
            {
                "path": relative_path,
                "sha256": sha256_bytes(path.read_bytes()),
            }
        )
    if not digests:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_EMPTY",
            "Candidate has no regular files to review.",
        )
    return sha256_text(canonical_json(digests))


def read_candidate_disposition(
    repo_path: str | Path,
    candidate_id: str,
) -> dict[str, Any] | None:
    repo = ensure_repo(repo_path)
    root = _candidate_root(repo, candidate_id)
    path = safe_target(root, CANDIDATE_DISPOSITION_FILENAME)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DISPOSITION_INVALID",
            f"Candidate disposition is not a regular file: {candidate_id}",
        )
    value = read_json(path)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "candidate_id",
            "status",
            "reason",
            "candidate_digest",
        }
        or value.get("schema_version") != CANDIDATE_DISPOSITION_VERSION
        or value.get("candidate_id") != candidate_id
        or value.get("status") not in {"rejected", "archived"}
        or not isinstance(value.get("reason"), str)
        or not value["reason"].strip()
        or len(value["reason"]) > 200
        or not isinstance(value.get("candidate_digest"), str)
        or re.fullmatch(r"[a-f0-9]{64}", value["candidate_digest"]) is None
    ):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DISPOSITION_INVALID",
            f"Candidate disposition is invalid: {candidate_id}",
        )
    if value["candidate_digest"] != _candidate_tree_digest(root):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DISPOSITION_STALE",
            f"Disposed candidate changed after its disposition: {candidate_id}",
        )
    return value


def _candidate_tombstones(repo: Path) -> list[dict[str, Any]]:
    root = safe_target(repo, CANDIDATE_TOMBSTONE_ROOT)
    if not root.is_dir() or root.is_symlink():
        return []
    tombstones: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json"))[:MAX_CANDIDATES]:
        if path.is_symlink() or not path.is_file():
            continue
        value = read_json(path)
        if (
            isinstance(value, dict)
            and value.get("schema_version") == CANDIDATE_TOMBSTONE_VERSION
            and value.get("candidate_id") == path.stem
        ):
            tombstones.append(value)
    return tombstones


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


def _candidate_issue(
    code: str,
    path: str,
    message: str,
) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _safe_candidate_reference(root: Path, value: Any) -> Path | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value.startswith(("/", "."))
        or "\\" in value
        or ".." in Path(value).parts
    ):
        return None
    try:
        return safe_target(root, value)
    except MaestroError:
        return None


def _quality_artifact_valid(value: Any, case_id: str) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == QUALITY_ARTIFACT_FIELDS
        and value.get("schema_version")
        == "maestro_expertise_case_artifact_v1"
        and value.get("case_id") == case_id
        and isinstance(value.get("baseline_observation"), str)
        and bool(value["baseline_observation"].strip())
        and isinstance(value.get("candidate_observation"), str)
        and bool(value["candidate_observation"].strip())
        and _nonempty_unique_strings(
            value.get("evidence_refs"),
            maximum=8,
        )
    )


def _validate_quality_evaluation(
    root: Path,
    candidate: dict[str, Any],
    expected_by_case: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    quality_path = candidate["evaluation"]["quality_path"]
    try:
        quality = read_json(safe_target(root, quality_path))
        evaluator = quality.get("evaluator")
        cases = quality.get("cases")
        if (
            set(quality) != QUALITY_EVALUATION_FIELDS
            or quality.get("schema_version")
            != "maestro_expertise_quality_eval_v1"
            or quality.get("expertise_pack_id")
            != candidate["expertise_pack_id"]
            or not isinstance(evaluator, dict)
            or set(evaluator) != QUALITY_EVALUATOR_FIELDS
            or evaluator.get("kind") not in {"fresh-context", "human"}
            or not isinstance(evaluator.get("authoring_run_ref"), str)
            or not evaluator["authoring_run_ref"].strip()
            or not isinstance(evaluator.get("evaluation_run_ref"), str)
            or not evaluator["evaluation_run_ref"].strip()
            or evaluator["authoring_run_ref"]
            == evaluator["evaluation_run_ref"]
            or not isinstance(cases, list)
            or not 3 <= len(cases) <= 12
        ):
            raise MaestroError(
                "EXPERTISE_QUALITY_EVALUATION_INVALID",
                "quality.json does not satisfy maestro_expertise_quality_eval_v1.",
            )
        date.fromisoformat(quality["evaluated_on"])
    except (MaestroError, TypeError, ValueError) as exc:
        message = exc.message if isinstance(exc, MaestroError) else str(exc)
        return [
            _candidate_issue(
                "EXPERTISE_QUALITY_EVALUATION_INVALID",
                quality_path,
                message,
            )
        ]

    case_ids: set[str] = set()
    for index, result in enumerate(cases):
        path = f"{quality_path}.cases[{index}]"
        case_id = result.get("case_id") if isinstance(result, dict) else None
        expected = (
            expected_by_case.get(case_id)
            if isinstance(case_id, str)
            else None
        )
        if (
            not isinstance(result, dict)
            or set(result) != QUALITY_CASE_FIELDS
            or not isinstance(case_id, str)
            or case_id in case_ids
            or expected is None
            or result.get("verdict") != "pass"
        ):
            issues.append(
                _candidate_issue(
                    "EXPERTISE_QUALITY_CASE_INVALID",
                    path,
                    "Quality result must uniquely bind one frozen case and pass.",
                )
            )
            continue
        case_ids.add(case_id)

        artifact = result.get("artifact")
        artifact_path_value = (
            artifact.get("path") if isinstance(artifact, dict) else None
        )
        artifact_path = _safe_candidate_reference(
            root,
            artifact_path_value,
        )
        if (
            not isinstance(artifact, dict)
            or set(artifact) != {"path", "sha256"}
            or not isinstance(artifact_path_value, str)
            or ID_PATTERN.fullmatch(
                Path(artifact_path_value).stem
            ) is None
            or Path(artifact_path_value).suffix != ".json"
            or Path(artifact_path_value).parent.as_posix()
            != "evals/artifacts"
            or artifact_path is None
            or artifact_path.is_symlink()
            or not artifact_path.is_file()
            or file_sha256(artifact_path) != artifact.get("sha256")
        ):
            issues.append(
                _candidate_issue(
                    "EXPERTISE_QUALITY_ARTIFACT_INVALID",
                    f"{path}.artifact",
                    "Quality artifact is missing, unsafe, or has a different digest.",
                )
            )
            continue
        try:
            artifact_value = json.loads(
                _read_text_file(root, artifact_path_value)
            )
        except (MaestroError, json.JSONDecodeError):
            artifact_value = None
        if not _quality_artifact_valid(artifact_value, case_id):
            issues.append(
                _candidate_issue(
                    "EXPERTISE_QUALITY_ARTIFACT_CONTENT_INVALID",
                    f"{path}.artifact",
                    "Quality artifact must be a compact case-bound observation record.",
                )
            )

        criterion_results = result.get("criterion_results")
        criterion_by_name: dict[str, dict[str, Any]] = {}
        if isinstance(criterion_results, list):
            for item in criterion_results:
                if (
                    isinstance(item, dict)
                    and set(item) == {
                        "criterion",
                        "verdict",
                        "evidence_ref",
                    }
                    and isinstance(item.get("criterion"), str)
                    and item["criterion"].strip()
                    and item.get("verdict") == "pass"
                    and item.get("evidence_ref") == artifact_path_value
                    and item["criterion"] not in criterion_by_name
                ):
                    criterion_by_name[item["criterion"]] = item
        if (
            not isinstance(criterion_results, list)
            or len(criterion_results)
            != len(expected["observable_criteria"])
            or set(criterion_by_name)
            != set(expected["observable_criteria"])
        ):
            issues.append(
                _candidate_issue(
                    "EXPERTISE_QUALITY_CRITERIA_INCOMPLETE",
                    f"{path}.criterion_results",
                    "Quality result must pass every exact observable criterion.",
                )
            )

        forbidden_results = result.get("forbidden_behavior_results")
        forbidden_by_name: dict[str, dict[str, Any]] = {}
        if isinstance(forbidden_results, list):
            for item in forbidden_results:
                if (
                    isinstance(item, dict)
                    and set(item) == {
                        "behavior",
                        "observed",
                        "evidence_ref",
                    }
                    and isinstance(item.get("behavior"), str)
                    and item["behavior"].strip()
                    and item.get("observed") is False
                    and item.get("evidence_ref") == artifact_path_value
                    and item["behavior"] not in forbidden_by_name
                ):
                    forbidden_by_name[item["behavior"]] = item
        if (
            not isinstance(forbidden_results, list)
            or len(forbidden_results)
            != len(expected["forbidden_behaviors"])
            or set(forbidden_by_name)
            != set(expected["forbidden_behaviors"])
        ):
            issues.append(
                _candidate_issue(
                    "EXPERTISE_QUALITY_FORBIDDEN_INCOMPLETE",
                    f"{path}.forbidden_behavior_results",
                    "Quality result must check every exact forbidden behavior and observe none.",
                )
            )

    if case_ids != set(expected_by_case):
        issues.append(
            _candidate_issue(
                "EXPERTISE_QUALITY_CASE_COVERAGE_MISSING",
                quality_path,
                "Quality evaluation must cover every frozen evaluation case.",
            )
        )
    return issues


def validate_expertise_candidate(
    repo_path: str | Path,
    candidate_id: str,
) -> dict[str, Any]:
    """Validate one complete candidate bundle without changing the repository."""

    repo = ensure_repo(repo_path)
    issues: list[dict[str, str]] = []
    try:
        root, candidate = _read_candidate(repo, candidate_id)
    except MaestroError as exc:
        return {
            "schema_version": "maestro_expertise_candidate_validation_v1",
            "status": "FAIL",
            "candidate_id": candidate_id,
            "issues": [
                _candidate_issue(exc.code, "candidate.json", exc.message)
            ],
            "writes_performed": False,
        }

    try:
        pack = read_json(safe_target(root, f"draft/{PROJECT_PACK_FILENAME}"))
        _validate_activation_pack(candidate, pack)
    except MaestroError as exc:
        issues.append(
            _candidate_issue(
                exc.code,
                f"draft/{PROJECT_PACK_FILENAME}",
                exc.message,
            )
        )
        pack = None

    component_change = candidate.get("component_change")
    if (
        isinstance(component_change, dict)
        and component_change.get("kind") == "pack-merge"
    ):
        source_pack_ids = component_change.get("source_pack_ids", [])
        available_pack_ids = {
            item["expertise_pack_id"]
            for item in load_expertise_catalog(repo)
        }
        missing_pack_ids = sorted(
            set(source_pack_ids) - available_pack_ids
        )
        if missing_pack_ids:
            issues.append(
                _candidate_issue(
                    "EXPERTISE_PACK_MERGE_SOURCE_MISSING",
                    "candidate.json",
                    "Pack integration sources are not active or bundled: "
                    + ", ".join(missing_pack_ids),
                )
            )
        if candidate["expertise_pack_id"] in source_pack_ids:
            issues.append(
                _candidate_issue(
                    "EXPERTISE_PACK_MERGE_SELF_REFERENCE",
                    "candidate.json",
                    "A consolidated Pack cannot list itself as a source Pack.",
                )
            )

    try:
        skill = _read_text_file(root, "draft/SKILL.md")
        if EXPERTISE_AUTHORITY_BLOCK not in skill:
            issues.append(
                _candidate_issue(
                    "EXPERTISE_AUTHORITY_CONTRACT_MISSING",
                    "draft/SKILL.md",
                    "Candidate Skill must contain the exact Maestro expertise authority block.",
                )
            )
    except MaestroError as exc:
        issues.append(_candidate_issue(exc.code, "draft/SKILL.md", exc.message))

    guide_ids = {
        guide["guide_id"]
        for guide in pack.get("guides", [])
    } if isinstance(pack, dict) else {
        guide["guide_id"] for guide in candidate["proposed_guides"]
    }
    guide_freshness = {
        guide["guide_id"]: guide["freshness"]
        for guide in pack.get("guides", [])
    } if isinstance(pack, dict) else {
        guide["guide_id"]: guide["freshness"]
        for guide in candidate["proposed_guides"]
    }
    for guide_id in sorted(guide_ids):
        path = f"draft/references/{guide_id}.md"
        try:
            body = _read_text_file(root, path)
        except MaestroError as exc:
            issues.append(_candidate_issue(exc.code, path, exc.message))
            continue
        headings = {
            re.sub(r"[-_]+", " ", match.group(1).strip().lower())
            for match in re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", body)
        }
        missing = [
            section for section in GUIDE_REQUIRED_SECTIONS
            if section not in headings
        ]
        if missing:
            issues.append(
                _candidate_issue(
                    "EXPERTISE_GUIDE_SECTIONS_MISSING",
                    path,
                    f"Guide is missing required sections: {', '.join(missing)}.",
                )
            )

    sources_path = "evidence/sources.json"
    covered_guides: set[str] = set()
    try:
        sources = read_json(safe_target(root, sources_path))
        if (
            set(sources) != {
                "schema_version",
                "expertise_pack_id",
                "verified_on",
                "sources",
            }
            or sources.get("schema_version") != "maestro_expertise_sources_v1"
            or not isinstance(sources.get("sources"), list)
            or not sources["sources"]
            or sources.get("expertise_pack_id")
            != candidate["expertise_pack_id"]
        ):
            raise MaestroError(
                "EXPERTISE_SOURCES_INVALID",
                "sources.json does not satisfy maestro_expertise_sources_v1.",
            )
        date.fromisoformat(sources["verified_on"])
        source_ids: set[str] = set()
        for index, source in enumerate(sources["sources"]):
            path = f"{sources_path}.sources[{index}]"
            allowed = {
                "source_id",
                "tier",
                "authority",
                "url",
                "artifact_ref",
                "supports",
                "used_by",
                "freshness",
            }
            if (
                not isinstance(source, dict)
                or not set(source).issubset(allowed)
                or not {
                    "source_id",
                    "tier",
                    "authority",
                    "supports",
                    "used_by",
                    "freshness",
                }.issubset(source)
                or not _valid_source_id(source.get("source_id"))
                or source["source_id"] in source_ids
                or source.get("tier") not in {1, 2, 3}
                or not isinstance(source.get("authority"), str)
                or not source["authority"].strip()
                or not _nonempty_unique_strings(source.get("supports"))
                or not _nonempty_unique_strings(source.get("used_by"))
                or not set(source["used_by"]).issubset(guide_ids)
                or source.get("freshness")
                not in {"stable", "versioned", "volatile"}
                or (
                    not isinstance(source.get("url"), str)
                    and not isinstance(source.get("artifact_ref"), str)
                )
                or (
                    isinstance(source.get("url"), str)
                    and (
                        not source["url"].strip()
                        or urlparse(source["url"]).scheme
                        not in {"http", "https"}
                        or not urlparse(source["url"]).netloc
                    )
                )
                or (
                    isinstance(source.get("artifact_ref"), str)
                    and not source["artifact_ref"].strip()
                )
            ):
                issues.append(
                    _candidate_issue(
                        "EXPERTISE_SOURCE_INVALID",
                        path,
                        "Source fields, authority tier, evidence location, or Guide links are invalid.",
                    )
                )
                continue
            source_ids.add(source["source_id"])
            covered_guides.update(source["used_by"])
            artifact_ref = source.get("artifact_ref")
            if artifact_ref is not None:
                artifact = _safe_candidate_reference(root, artifact_ref)
                if artifact is None or artifact.is_symlink() or not artifact.is_file():
                    issues.append(
                        _candidate_issue(
                            "EXPERTISE_SOURCE_ARTIFACT_MISSING",
                            path,
                            f"Source artifact is missing or unsafe: {artifact_ref}.",
                        )
                    )
    except (MaestroError, TypeError, ValueError) as exc:
        message = exc.message if isinstance(exc, MaestroError) else str(exc)
        issues.append(
            _candidate_issue(
                "EXPERTISE_SOURCES_INVALID",
                sources_path,
                message,
            )
        )
    uncovered = sorted(
        guide_id
        for guide_id in guide_ids - covered_guides
        if guide_freshness.get(guide_id) != "volatile"
    )
    if uncovered:
        issues.append(
            _candidate_issue(
                "EXPERTISE_GUIDE_EVIDENCE_MISSING",
                sources_path,
                f"Non-volatile Guides lack source linkage: {', '.join(uncovered)}.",
            )
        )

    cases_path = "evals/cases.json"
    expected_by_case: dict[str, dict[str, Any]] = {}
    try:
        suite = read_json(safe_target(root, cases_path))
        cases = suite.get("cases")
        artifact = suite.get("evaluation_artifact")
        if (
            set(suite) != {
                "schema_version",
                "expertise_pack_id",
                "evaluated_on",
                "evaluation_artifact",
                "cases",
            }
            or suite.get("schema_version") != "maestro_expertise_eval_v2"
            or suite.get("expertise_pack_id")
            != candidate["expertise_pack_id"]
            or not isinstance(cases, list)
            or not 3 <= len(cases) <= 12
            or not isinstance(artifact, dict)
            or set(artifact) != {"path", "sha256"}
            or artifact.get("path") != "evals/results.json"
        ):
            raise MaestroError(
                "EXPERTISE_EVALUATION_INVALID",
                "cases.json does not satisfy maestro_expertise_eval_v2.",
            )
        date.fromisoformat(suite["evaluated_on"])
        case_ids: set[str] = set()
        strata: set[str] = set()
        for index, case in enumerate(cases):
            case_path = f"{cases_path}.cases[{index}]"
            if (
                not isinstance(case, dict)
                or set(case) != {
                    "case_id",
                    "stratum",
                    "goal",
                    "expected_pack_id",
                    "expected_mode",
                    "expected_guides",
                    "observable_criteria",
                    "forbidden_behaviors",
                }
                or not _valid_source_id(case.get("case_id"))
                or case["case_id"] in case_ids
                or case.get("stratum")
                not in {"normal", "edge", "non-trigger", "overlap"}
                or not isinstance(case.get("goal"), str)
                or not case["goal"].strip()
                or (
                    case.get("expected_pack_id") is not None
                    and case["expected_pack_id"] != candidate["expertise_pack_id"]
                )
                or case.get("expected_mode")
                not in {"reuse", "contextualize", "refresh", "discover"}
                or not isinstance(case.get("expected_guides"), list)
                or not set(case["expected_guides"]).issubset(guide_ids)
                or not _nonempty_unique_strings(
                    case.get("observable_criteria")
                )
                or not _nonempty_unique_strings(
                    case.get("forbidden_behaviors")
                )
            ):
                issues.append(
                    _candidate_issue(
                        "EXPERTISE_EVALUATION_CASE_INVALID",
                        case_path,
                        "Evaluation case fields, strata, expectations, or observable criteria are invalid.",
                    )
                )
                continue
            case_ids.add(case["case_id"])
            strata.add(case["stratum"])
            expected_by_case[case["case_id"]] = case
        missing_strata = {"normal", "edge", "non-trigger"} - strata
        if missing_strata:
            issues.append(
                _candidate_issue(
                    "EXPERTISE_EVALUATION_COVERAGE_MISSING",
                    cases_path,
                    f"Evaluation lacks required strata: {', '.join(sorted(missing_strata))}.",
                )
            )
        artifact_path = _safe_candidate_reference(root, artifact.get("path"))
        if (
            artifact_path is None
            or artifact_path.is_symlink()
            or not artifact_path.is_file()
            or file_sha256(artifact_path) != artifact.get("sha256")
        ):
            issues.append(
                _candidate_issue(
                    "EXPERTISE_EVALUATION_ARTIFACT_INVALID",
                    cases_path,
                    "Evaluation artifact is missing, unsafe, or has a different digest.",
                )
            )
        else:
            results = read_json(artifact_path)
            result_rows = results.get("results")
            if (
                results.get("schema_version")
                != "maestro_expertise_eval_results_v1"
                or results.get("expertise_pack_id")
                != candidate["expertise_pack_id"]
                or not isinstance(result_rows, list)
                or {
                    row.get("case_id")
                    for row in result_rows
                    if isinstance(row, dict)
                }
                != set(expected_by_case)
                or any(
                    not isinstance(row, dict)
                    or set(row)
                    != {
                        "case_id",
                        "observed_pack_id",
                        "observed_mode",
                        "observed_guides",
                        "verdict",
                    }
                    or row.get("verdict") != "pass"
                    or row.get("observed_pack_id")
                    != expected_by_case.get(row.get("case_id"), {}).get(
                        "expected_pack_id"
                    )
                    or row.get("observed_mode")
                    != expected_by_case.get(row.get("case_id"), {}).get(
                        "expected_mode"
                    )
                    or not set(
                        expected_by_case.get(row.get("case_id"), {}).get(
                            "expected_guides",
                            [],
                        )
                    ).issubset(set(row.get("observed_guides", [])))
                    for row in result_rows
                )
            ):
                issues.append(
                    _candidate_issue(
                        "EXPERTISE_EVALUATION_RESULTS_INVALID",
                        artifact["path"],
                        "Evaluation results do not bind every case to passing observed outcomes.",
                    )
                )
    except (MaestroError, TypeError, ValueError) as exc:
        message = exc.message if isinstance(exc, MaestroError) else str(exc)
        issues.append(
            _candidate_issue(
                "EXPERTISE_EVALUATION_INVALID",
                cases_path,
                message,
            )
        )

    if expected_by_case:
        issues.extend(
            _validate_quality_evaluation(
                root,
                candidate,
                expected_by_case,
            )
        )

    return {
        "schema_version": "maestro_expertise_candidate_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "candidate_id": candidate_id,
        "issues": issues,
        "writes_performed": False,
    }


def _valid_source_id(value: Any) -> bool:
    return isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None


def _validate_candidate_bundle_or_raise(
    repo: Path,
    candidate_id: str,
) -> None:
    report = validate_expertise_candidate(repo, candidate_id)
    if report["status"] != "PASS":
        summary = "; ".join(
            f"{item['code']}: {item['message']}" for item in report["issues"]
        )
        raise MaestroError("EXPERTISE_CANDIDATE_BUNDLE_INVALID", summary)


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


def _validate_approval_ref(approval_ref: str) -> None:
    if (
        not isinstance(approval_ref, str)
        or APPROVAL_PATTERN.fullmatch(approval_ref) is None
    ):
        raise MaestroError(
            "EXPERTISE_PUBLICATION_APPROVAL_INVALID",
            "approval-ref must be owner_decision:<ref> or "
            "held_out_evaluation:<ref>.",
        )


def _fresh_candidate_pack(
    repo: Path,
    candidate_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    candidate_root, candidate = _read_candidate(repo, candidate_id)
    if read_candidate_disposition(repo, candidate_id) is not None:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_REJECTED",
            "Restore a rejected candidate before publication or export.",
        )
    _validate_candidate_bundle_or_raise(repo, candidate_id)
    if date.fromisoformat(candidate["review_after"]) < date.today():
        raise MaestroError(
            "EXPERTISE_CANDIDATE_EXPIRED",
            "Expired candidates must be revalidated before publication.",
        )
    pack = read_json(
        safe_target(candidate_root, f"draft/{PROJECT_PACK_FILENAME}")
    )
    _validate_activation_pack(candidate, pack)
    return candidate_root, candidate, pack


def _project_expertise_configuration(
    repo: Path,
) -> tuple[Path, dict[str, Any], list[str]]:
    project_path = safe_target(repo, ".maestro/project.json")
    project = read_json(project_path)
    expertise = project.get("expertise", {"active_pack_paths": []})
    if (
        not isinstance(expertise, dict)
        or set(expertise) != {"active_pack_paths"}
        or not isinstance(expertise["active_pack_paths"], list)
        or len(expertise["active_pack_paths"])
        != len(set(expertise["active_pack_paths"]))
        or any(
            not isinstance(path, str) or not path.strip()
            for path in expertise["active_pack_paths"]
        )
    ):
        raise MaestroError(
            "PROJECT_EXPERTISE_CONFIG_INVALID",
            "Repair project.json expertise configuration before publication.",
        )
    return project_path, project, expertise["active_pack_paths"]


def _candidate_publication_contents(
    candidate_root: Path,
    pack: dict[str, Any],
    destination_root: str,
) -> tuple[dict[str, str], str]:
    source_to_destination = {
        f"draft/{PROJECT_PACK_FILENAME}": (
            f"{destination_root}/{PROJECT_PACK_FILENAME}"
        ),
        "draft/SKILL.md": f"{destination_root}/SKILL.md",
        "draft/agents/openai.yaml": (
            f"{destination_root}/agents/openai.yaml"
        ),
        "candidate.json": f"{destination_root}/evidence/candidate.json",
        "evidence/sources.json": (
            f"{destination_root}/evidence/sources.json"
        ),
        "evals/cases.json": f"{destination_root}/evals/cases.json",
    }
    suite = read_json(safe_target(candidate_root, "evals/cases.json"))
    evaluation_artifact = suite.get("evaluation_artifact", {}).get("path")
    if isinstance(evaluation_artifact, str):
        source_to_destination[evaluation_artifact] = (
            f"{destination_root}/{evaluation_artifact}"
        )
    candidate = read_json(safe_target(candidate_root, "candidate.json"))
    quality_path = candidate["evaluation"]["quality_path"]
    source_to_destination[quality_path] = (
        f"{destination_root}/{quality_path}"
    )
    quality = read_json(safe_target(candidate_root, quality_path))
    for result in quality.get("cases", []):
        artifact_path = result.get("artifact", {}).get("path")
        if isinstance(artifact_path, str):
            source_to_destination[artifact_path] = (
                f"{destination_root}/{artifact_path}"
            )
    for guide in pack["guides"]:
        guide_id = guide["guide_id"]
        source_to_destination[
            f"draft/references/{guide_id}.md"
        ] = f"{destination_root}/references/{guide_id}.md"

    contents: dict[str, str] = {}
    source_digests: dict[str, str] = {}
    for source, destination in sorted(source_to_destination.items()):
        content = _read_text_file(candidate_root, source)
        source_digests[source] = sha256_text(content)
        contents[destination] = content
    return contents, sha256_text(canonical_json(source_digests))


def _candidate_contribution_files(
    candidate_root: Path,
    pack: dict[str, Any],
) -> list[dict[str, str]]:
    relative_paths = {
        "candidate.json",
        f"draft/{PROJECT_PACK_FILENAME}",
        "draft/SKILL.md",
        "draft/agents/openai.yaml",
        "evidence/sources.json",
        "evals/cases.json",
    }
    suite = read_json(safe_target(candidate_root, "evals/cases.json"))
    evaluation_artifact = suite.get("evaluation_artifact", {}).get("path")
    if isinstance(evaluation_artifact, str):
        relative_paths.add(evaluation_artifact)
    candidate = read_json(safe_target(candidate_root, "candidate.json"))
    quality_path = candidate["evaluation"]["quality_path"]
    relative_paths.add(quality_path)
    quality = read_json(safe_target(candidate_root, quality_path))
    for result in quality.get("cases", []):
        artifact_path = result.get("artifact", {}).get("path")
        if isinstance(artifact_path, str):
            relative_paths.add(artifact_path)
    for guide in pack["guides"]:
        relative_paths.add(
            f"draft/references/{guide['guide_id']}.md"
        )

    files: list[dict[str, str]] = []
    for relative_path in sorted(relative_paths):
        content = _read_text_file(candidate_root, relative_path)
        files.append(
            {
                "path": relative_path,
                "sha256": sha256_text(content),
                "content": content,
            }
        )
    return files


def _validate_contribution_quality(
    candidate: dict[str, Any],
    file_contents: dict[str, str],
    file_digests: dict[str, str],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    evaluation = candidate.get("evaluation")
    quality_path = (
        evaluation.get("quality_path")
        if isinstance(evaluation, dict)
        else None
    )
    try:
        suite = json.loads(file_contents["evals/cases.json"])
        quality = json.loads(file_contents[quality_path])
        expected_by_case = {
            case["case_id"]: case
            for case in suite["cases"]
            if isinstance(case, dict)
            and isinstance(case.get("case_id"), str)
        }
        evaluator = quality["evaluator"]
        quality_cases = quality["cases"]
        if (
            quality_path != "evals/quality.json"
            or quality.get("schema_version")
            != "maestro_expertise_quality_eval_v1"
            or quality.get("expertise_pack_id")
            != candidate.get("expertise_pack_id")
            or not isinstance(evaluator, dict)
            or set(evaluator) != QUALITY_EVALUATOR_FIELDS
            or evaluator.get("kind") not in {"fresh-context", "human"}
            or not isinstance(evaluator.get("authoring_run_ref"), str)
            or not evaluator["authoring_run_ref"].strip()
            or not isinstance(evaluator.get("evaluation_run_ref"), str)
            or not evaluator["evaluation_run_ref"].strip()
            or evaluator["authoring_run_ref"]
            == evaluator["evaluation_run_ref"]
            or not isinstance(quality_cases, list)
            or not 3 <= len(quality_cases) <= 12
            or len(expected_by_case) != len(suite["cases"])
        ):
            raise ValueError("quality evaluation identity is invalid")
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        return [
            {
                "code": "EXPERTISE_CONTRIBUTION_QUALITY_INVALID",
                "message": (
                    "Embedded quality evaluation is invalid: "
                    f"{exc}"
                ),
            }
        ]

    observed_cases: set[str] = set()
    for result in quality_cases:
        case_id = result.get("case_id") if isinstance(result, dict) else None
        expected = (
            expected_by_case.get(case_id)
            if isinstance(case_id, str)
            else None
        )
        artifact = result.get("artifact") if isinstance(result, dict) else None
        artifact_path = (
            artifact.get("path") if isinstance(artifact, dict) else None
        )
        criterion_results = (
            result.get("criterion_results")
            if isinstance(result, dict)
            else None
        )
        forbidden_results = (
            result.get("forbidden_behavior_results")
            if isinstance(result, dict)
            else None
        )
        expected_criteria = (
            expected.get("observable_criteria")
            if isinstance(expected, dict)
            else None
        )
        expected_forbidden = (
            expected.get("forbidden_behaviors")
            if isinstance(expected, dict)
            else None
        )
        try:
            artifact_value = json.loads(file_contents[artifact_path])
        except (KeyError, TypeError, json.JSONDecodeError):
            artifact_value = None
        valid_criteria = {
            item["criterion"]
            for item in criterion_results
            if isinstance(item, dict)
            and set(item) == {
                "criterion",
                "verdict",
                "evidence_ref",
            }
            and item.get("verdict") == "pass"
            and item.get("evidence_ref") == artifact_path
            and isinstance(item.get("criterion"), str)
        } if isinstance(criterion_results, list) else set()
        valid_forbidden = {
            item["behavior"]
            for item in forbidden_results
            if isinstance(item, dict)
            and set(item) == {
                "behavior",
                "observed",
                "evidence_ref",
            }
            and item.get("observed") is False
            and item.get("evidence_ref") == artifact_path
            and isinstance(item.get("behavior"), str)
        } if isinstance(forbidden_results, list) else set()
        if (
            not isinstance(result, dict)
            or set(result) != QUALITY_CASE_FIELDS
            or not isinstance(case_id, str)
            or case_id in observed_cases
            or expected is None
            or result.get("verdict") != "pass"
            or not isinstance(artifact, dict)
            or set(artifact) != {"path", "sha256"}
            or not isinstance(artifact_path, str)
            or artifact_path not in file_contents
            or file_digests.get(artifact_path)
            != artifact.get("sha256")
            or not _quality_artifact_valid(artifact_value, case_id)
            or not _nonempty_unique_strings(expected_criteria)
            or not _nonempty_unique_strings(expected_forbidden)
            or not isinstance(criterion_results, list)
            or len(criterion_results) != len(expected_criteria)
            or not isinstance(forbidden_results, list)
            or len(forbidden_results) != len(expected_forbidden)
            or valid_criteria
            != set(expected_criteria)
            or valid_forbidden
            != set(expected_forbidden)
        ):
            issues.append(
                {
                    "code": "EXPERTISE_CONTRIBUTION_QUALITY_CASE_INVALID",
                    "message": (
                        "Embedded quality result does not exactly bind "
                        f"the frozen case and artifact: {case_id!r}."
                    ),
                }
            )
            continue
        observed_cases.add(case_id)
    if observed_cases != set(expected_by_case):
        issues.append(
            {
                "code": "EXPERTISE_CONTRIBUTION_QUALITY_COVERAGE_MISSING",
                "message": (
                    "Embedded quality evaluation does not cover every "
                    "frozen case."
                ),
            }
        )
    return issues


def _publication_record(
    *,
    action: str,
    candidate_id: str,
    candidate_digest: str,
    approval_ref: str,
    pack_version: int,
    previous_definition_digest: str | None,
) -> str:
    return pretty_json(
        {
            "schema_version": "maestro_expertise_publication_v1",
            "action": action,
            "candidate_id": candidate_id,
            "candidate_digest": candidate_digest,
            "approval_ref": approval_ref,
            "source_candidate_path": (
                f".maestro/state/candidates/expertise/{candidate_id}"
            ),
            "pack_version": pack_version,
            "previous_definition_digest": previous_definition_digest,
        }
    )


def _text_operation(
    repo: Path,
    path: str,
    content: str,
    *,
    require_missing: bool = False,
) -> dict[str, Any]:
    before = file_sha256(safe_target(repo, path))
    if require_missing and before is not None:
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_EXISTS",
            f"Project Expertise target already exists: {path}",
        )
    return {
        "op": "create" if before is None else "replace",
        "path": path,
        "before_sha256": before,
        "after_sha256": sha256_text(content),
        "content": content,
    }


def _delete_operation(repo: Path, path: str) -> dict[str, Any]:
    before = file_sha256(safe_target(repo, path))
    if before is None:
        raise MaestroError(
            "EXPERTISE_UPDATE_TARGET_MISSING",
            f"Cannot remove a missing project Expertise file: {path}",
        )
    return {
        "op": "delete",
        "path": path,
        "before_sha256": before,
        "after_sha256": None,
        "content": None,
    }


def _finalize_plan(base: dict[str, Any]) -> dict[str, Any]:
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def _expertise_contribution(
    *,
    candidate_id: str,
    candidate: dict[str, Any],
    pack: dict[str, Any],
    files: list[dict[str, str]],
) -> dict[str, Any]:
    file_digests = {
        item["path"]: item["sha256"] for item in files
    }
    contribution = {
        "schema_version": CONTRIBUTION_VERSION,
        "candidate_id": candidate_id,
        "expertise_pack_id": candidate["expertise_pack_id"],
        "portability": candidate["portability"],
        "component_change": _candidate_component_change(
            candidate,
            pack,
        ),
        "base": copy.deepcopy(pack.get("extends")),
        "pack_version": pack["version"],
        "candidate_digest": sha256_text(
            canonical_json(file_digests)
        ),
        "files": files,
        "promotion": {
            "status": (
                "review_required"
                if candidate["portability"] in {"profile", "global"}
                else "project_only"
            ),
            "automatic_install_allowed": False,
            "requires_repository_review": True,
            "requires_release": True,
        },
    }
    contribution["bundle_digest"] = sha256_text(
        canonical_json(contribution)
    )
    return contribution


def build_expertise_export_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _require_individual_candidate_action(
        repo,
        candidate_id=candidate_id,
    )
    candidate_root, candidate, pack = _fresh_candidate_pack(
        repo,
        candidate_id,
    )
    files = _candidate_contribution_files(candidate_root, pack)
    repository_path = str(repo)
    if any(repository_path in item["content"] for item in files):
        raise MaestroError(
            "EXPERTISE_CONTRIBUTION_PRIVATE_PATH",
            "Candidate content contains the producing repository's absolute path.",
        )
    contribution = _expertise_contribution(
        candidate_id=candidate_id,
        candidate=candidate,
        pack=pack,
        files=files,
    )
    content = pretty_json(contribution)
    output_path = (
        f".maestro/exports/expertise/{candidate_id}."
        "maestro-contribution.json"
    )
    base = {
        "schema_version": EXPORT_PLAN_VERSION,
        "command": "expertise-export",
        "repo_realpath": str(repo),
        "candidate_id": candidate_id,
        "candidate_digest": contribution["candidate_digest"],
        "output_path": output_path,
        "output_before_sha256": file_sha256(
            safe_target(repo, output_path)
        ),
        "output_after_sha256": sha256_text(content),
        "content": content,
        "warnings": [
            (
                "Export is a review bundle, not a global promotion, install, "
                "commit, or push."
            ),
            (
                "Review the bundle for project-private knowledge and source "
                "licensing before moving it to the Harness repository."
            ),
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def validate_expertise_contribution(
    bundle_path: str | Path,
) -> dict[str, Any]:
    path = Path(bundle_path).expanduser().resolve()
    try:
        contribution = read_json(path)
    except MaestroError as exc:
        return {
            "schema_version": "maestro_expertise_contribution_validation_v1",
            "status": "FAIL",
            "issues": [{"code": exc.code, "message": exc.message}],
            "writes_performed": False,
        }
    issues: list[dict[str, str]] = []
    required = {
        "schema_version",
        "candidate_id",
        "expertise_pack_id",
        "portability",
        "component_change",
        "base",
        "pack_version",
        "candidate_digest",
        "files",
        "promotion",
        "bundle_digest",
    }
    if set(contribution) != required:
        issues.append(
            {
                "code": "EXPERTISE_CONTRIBUTION_FIELDS_INVALID",
                "message": "Contribution fields do not match the v1 contract.",
            }
        )
    if (
        contribution.get("schema_version") != CONTRIBUTION_VERSION
        or not isinstance(contribution.get("candidate_id"), str)
        or ID_PATTERN.fullmatch(contribution.get("candidate_id", "")) is None
        or not isinstance(contribution.get("expertise_pack_id"), str)
        or ID_PATTERN.fullmatch(
            contribution.get("expertise_pack_id", "")
        )
        is None
        or contribution.get("portability")
        not in {"project", "profile", "global"}
        or not isinstance(contribution.get("pack_version"), int)
        or isinstance(contribution.get("pack_version"), bool)
        or contribution.get("pack_version", 0) < 1
    ):
        issues.append(
            {
                "code": "EXPERTISE_CONTRIBUTION_IDENTITY_INVALID",
                "message": "Contribution identity, portability, or version is invalid.",
            }
        )
    files = contribution.get("files")
    file_digests: dict[str, str] = {}
    file_contents: dict[str, str] = {}
    if (
        not isinstance(files, list)
        or not 7 <= len(files) <= 32
    ):
        issues.append(
            {
                "code": "EXPERTISE_CONTRIBUTION_FILES_INVALID",
                "message": "Contribution must contain a bounded file list.",
            }
        )
    else:
        for item in files:
            if (
                not isinstance(item, dict)
                or set(item) != {"path", "sha256", "content"}
                or not isinstance(item.get("path"), str)
                or _safe_candidate_reference(Path("/"), item["path"]) is None
                or not isinstance(item.get("sha256"), str)
                or not isinstance(item.get("content"), str)
                or sha256_text(item.get("content", ""))
                != item.get("sha256")
                or item["path"] in file_digests
            ):
                issues.append(
                    {
                        "code": "EXPERTISE_CONTRIBUTION_FILE_INVALID",
                        "message": "Contribution contains an unsafe, duplicate, or mismatched file.",
                    }
                )
                break
            file_digests[item["path"]] = item["sha256"]
            file_contents[item["path"]] = item["content"]
    required_paths = {
        "candidate.json",
        f"draft/{PROJECT_PACK_FILENAME}",
        "draft/SKILL.md",
        "draft/agents/openai.yaml",
        "evidence/sources.json",
        "evals/cases.json",
        "evals/results.json",
        "evals/quality.json",
    }
    if file_contents and not required_paths.issubset(file_contents):
        issues.append(
            {
                "code": "EXPERTISE_CONTRIBUTION_FILES_INCOMPLETE",
                "message": "Contribution is missing one or more canonical candidate files.",
            }
        )
    candidate: dict[str, Any] | None = None
    pack: dict[str, Any] | None = None
    try:
        candidate_value = json.loads(file_contents["candidate.json"])
        pack_value = json.loads(
            file_contents[f"draft/{PROJECT_PACK_FILENAME}"]
        )
        if not isinstance(candidate_value, dict) or not isinstance(
            pack_value,
            dict,
        ):
            raise ValueError("Candidate and Pack files must contain objects.")
        candidate = candidate_value
        pack = pack_value
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if file_contents:
            issues.append(
                {
                    "code": "EXPERTISE_CONTRIBUTION_CONTENT_INVALID",
                    "message": f"Embedded candidate or Pack is invalid: {exc}",
                }
            )
    if candidate is not None and pack is not None:
        guide_ids = {
            guide.get("guide_id")
            for guide in pack.get("guides", [])
            if isinstance(guide, dict)
            and isinstance(guide.get("guide_id"), str)
        }
        expected_guide_paths = {
            f"draft/references/{guide_id}.md"
            for guide_id in guide_ids
        }
        if (
            not _candidate_contract_valid(
                candidate,
                contribution.get("candidate_id", ""),
            )
            or candidate.get("expertise_pack_id")
            != contribution.get("expertise_pack_id")
            or candidate.get("portability")
            != contribution.get("portability")
            or _candidate_component_change(candidate, pack)
            != contribution.get("component_change")
            or pack.get("expertise_pack_id")
            != contribution.get("expertise_pack_id")
            or pack.get("version") != contribution.get("pack_version")
            or pack.get("portability") != "project"
            or pack.get("status") != "pilot"
        ):
            issues.append(
                {
                    "code": "EXPERTISE_CONTRIBUTION_CONTENT_MISMATCH",
                    "message": "Embedded candidate, Pack, component change, or bundle identity differs.",
                }
            )
        if not expected_guide_paths.issubset(file_contents):
            issues.append(
                {
                    "code": "EXPERTISE_CONTRIBUTION_GUIDES_INCOMPLETE",
                    "message": "Contribution is missing a Guide referenced by its Pack.",
                }
            )
        issues.extend(
            _validate_contribution_quality(
                candidate,
                file_contents,
                file_digests,
            )
        )
    promotion = contribution.get("promotion")
    if (
        not isinstance(promotion, dict)
        or set(promotion)
        != {
            "status",
            "automatic_install_allowed",
            "requires_repository_review",
            "requires_release",
        }
        or promotion.get("status") not in {"project_only", "review_required"}
        or promotion.get("automatic_install_allowed") is not False
        or promotion.get("requires_repository_review") is not True
        or promotion.get("requires_release") is not True
    ):
        issues.append(
            {
                "code": "EXPERTISE_CONTRIBUTION_PROMOTION_INVALID",
                "message": "Contribution must preserve the review-and-release promotion boundary.",
            }
        )
    if (
        file_digests
        and contribution.get("candidate_digest")
        != sha256_text(canonical_json(file_digests))
    ):
        issues.append(
            {
                "code": "EXPERTISE_CONTRIBUTION_DIGEST_INVALID",
                "message": "Contribution candidate digest does not match its files.",
            }
        )
    unsigned = {
        key: value
        for key, value in contribution.items()
        if key != "bundle_digest"
    }
    if contribution.get("bundle_digest") != sha256_text(
        canonical_json(unsigned)
    ):
        issues.append(
            {
                "code": "EXPERTISE_CONTRIBUTION_BUNDLE_TAMPERED",
                "message": "Contribution bundle digest does not match its contents.",
            }
        )
    return {
        "schema_version": "maestro_expertise_contribution_validation_v1",
        "status": "FAIL" if issues else "PASS",
        "candidate_id": contribution.get("candidate_id"),
        "expertise_pack_id": contribution.get("expertise_pack_id"),
        "portability": contribution.get("portability"),
        "component_change": contribution.get("component_change"),
        "issues": issues,
        "writes_performed": False,
    }


def _candidate_pack_preview(
    candidate_root: Path,
    candidate: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    source_manifest = read_json(
        safe_target(candidate_root, pack["source_manifest"])
    )
    evaluation_suite = read_json(
        safe_target(candidate_root, pack["evaluation_suite"])
    )
    quality = read_json(
        safe_target(
            candidate_root,
            candidate["evaluation"]["quality_path"],
        )
    )
    quality_by_case = {
        item["case_id"]: item
        for item in quality.get("cases", [])
        if isinstance(item, dict)
        and isinstance(item.get("case_id"), str)
    }
    source_by_guide: dict[str, list[dict[str, Any]]] = {
        guide["guide_id"]: [] for guide in pack["guides"]
    }
    bounded_sources: list[dict[str, Any]] = []
    for source in source_manifest.get("sources", [])[:20]:
        if not isinstance(source, dict):
            continue
        bounded = {
            key: copy.deepcopy(source.get(key))
            for key in (
                "source_id",
                "tier",
                "authority",
                "url",
                "used_by",
                "freshness",
            )
        }
        bounded_sources.append(bounded)
        for guide_id in source.get("used_by", []):
            if guide_id in source_by_guide:
                source_by_guide[guide_id].append(
                    {
                        "source_id": source.get("source_id"),
                        "tier": source.get("tier"),
                        "freshness": source.get("freshness"),
                    }
                )
    proposed_by_guide = {
        guide["guide_id"]: guide
        for guide in candidate["proposed_guides"]
    }
    evaluation_cases: list[dict[str, Any]] = []
    for case in evaluation_suite.get("cases", [])[
        :MAX_VIEWER_EVALUATION_CASES
    ]:
        if not isinstance(case, dict):
            continue
        quality_case = quality_by_case.get(case.get("case_id"), {})
        evaluation_cases.append(
            {
                "case_id": case.get("case_id"),
                "stratum": case.get("stratum"),
                "goal": case.get("goal"),
                "expected_mode": case.get("expected_mode"),
                "expected_guides": copy.deepcopy(
                    case.get("expected_guides", [])
                ),
                "observable_criteria": copy.deepcopy(
                    case.get("observable_criteria", [])
                ),
                "forbidden_behaviors": copy.deepcopy(
                    case.get("forbidden_behaviors", [])
                ),
                "quality_verdict": quality_case.get("verdict"),
            }
        )
    passed_cases = sum(
        item.get("quality_verdict") == "pass"
        for item in evaluation_cases
    )
    return {
        "summary": pack["summary"],
        "status": pack["status"],
        "portability": pack["portability"],
        "version": pack["version"],
        "triggers": list(pack.get("triggers", [])),
        "default_guides": list(pack.get("default_guides", [])),
        "research_policy": {
            "default_mode": pack.get(
                "research_policy",
                {},
            ).get("default_mode"),
            "contextualize_triggers": list(
                pack.get(
                    "research_policy",
                    {},
                ).get("contextualize_triggers", [])
            ),
            "refresh_triggers": list(
                pack.get(
                    "research_policy",
                    {},
                ).get("refresh_triggers", [])
            ),
        },
        "problem": candidate["problem"],
        "reusable_when": list(candidate["reusable_when"]),
        "not_for": list(candidate["not_for"]),
        "existing_coverage": candidate["existing_coverage"],
        "guides": [
            {
                "guide_id": guide["guide_id"],
                "summary": guide["summary"],
                "freshness": guide["freshness"],
                "triggers": list(guide.get("triggers", [])),
                "sources": source_by_guide.get(
                    guide["guide_id"],
                    [],
                ),
                "failure_prevented": proposed_by_guide.get(
                    guide["guide_id"],
                    {},
                ).get("failure_prevented"),
                "decision_checks": copy.deepcopy(
                    proposed_by_guide.get(
                        guide["guide_id"],
                        {},
                    ).get("decision_checks", [])
                ),
            }
            for guide in pack["guides"]
        ],
        "source_manifest": {
            "status": "available",
            "verified_on": source_manifest.get("verified_on"),
            "sources": bounded_sources,
        },
        "evaluation": {
            "status": "available",
            "evaluated_on": quality.get("evaluated_on"),
            "evaluator_kind": quality.get(
                "evaluator",
                {},
            ).get("kind"),
            "case_count": len(evaluation_cases),
            "passed_case_count": passed_cases,
            "cases": evaluation_cases,
        },
    }


def _candidate_global_request_status(
    repo: Path,
    *,
    candidate_root: Path,
    candidate: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = candidate["candidate_id"]
    output_path = (
        f".maestro/exports/expertise/{candidate_id}."
        "maestro-contribution.json"
    )
    target = safe_target(repo, output_path)
    base = {
        "output_path": output_path,
        "repository_submission_status": "not_tracked",
        "release_status": "not_tracked",
        "automatic_commit_performed": False,
        "automatic_push_performed": False,
        "automatic_pull_request_performed": False,
        "automatic_release_performed": False,
    }
    if not target.exists():
        return {
            **base,
            "status": "not_created",
            "validation_status": "not_run",
            "matches_current_candidate": False,
            "bundle_digest": None,
        }
    if target.is_symlink() or not target.is_file():
        return {
            **base,
            "status": "local_review_bundle_invalid",
            "validation_status": "FAIL",
            "matches_current_candidate": False,
            "bundle_digest": None,
        }
    validation = validate_expertise_contribution(target)
    try:
        contribution = read_json(target)
    except MaestroError:
        contribution = {}
    expected_files = _candidate_contribution_files(
        candidate_root,
        pack,
    )
    expected_candidate_digest = sha256_text(
        canonical_json(
            {
                item["path"]: item["sha256"]
                for item in expected_files
            }
        )
    )
    matches_current_candidate = (
        contribution.get("candidate_id") == candidate_id
        and contribution.get("expertise_pack_id")
        == candidate["expertise_pack_id"]
        and contribution.get("candidate_digest")
        == expected_candidate_digest
        and contribution.get("pack_version") == pack["version"]
        and contribution.get("portability") == candidate["portability"]
        and contribution.get("component_change")
        == _candidate_component_change(candidate, pack)
    )
    return {
        **base,
        "status": (
            "local_review_bundle_created"
            if validation["status"] == "PASS"
            and matches_current_candidate
            else (
                "local_review_bundle_stale"
                if validation["status"] == "PASS"
                else "local_review_bundle_invalid"
            )
        ),
        "validation_status": validation["status"],
        "matches_current_candidate": matches_current_candidate,
        "bundle_digest": (
            contribution.get("bundle_digest")
            if isinstance(contribution.get("bundle_digest"), str)
            else None
        ),
    }


def _global_skill_identity(
    content: str,
    *,
    current_skill_id: str,
    global_skill_id: str,
) -> str:
    matches = list(
        re.finditer(r"(?m)^name:\s*([^\s]+)\s*$", content)
    )
    if len(matches) != 1:
        raise MaestroError(
            "EXPERTISE_PROJECT_PROMOTION_SKILL_INVALID",
            "Project Skill must contain exactly one frontmatter name.",
        )
    rewritten = (
        content[: matches[0].start()]
        + f"name: {global_skill_id}"
        + content[matches[0].end() :]
    )
    if current_skill_id != global_skill_id:
        rewritten = rewritten.replace(
            f"${current_skill_id}",
            f"${global_skill_id}",
        )
    return rewritten


def _project_promotion_source(
    repo: Path,
    *,
    expertise_pack_id: str,
) -> dict[str, Any]:
    if (
        not isinstance(expertise_pack_id, str)
        or ID_PATTERN.fullmatch(expertise_pack_id) is None
    ):
        raise MaestroError(
            "EXPERTISE_PROJECT_PROMOTION_ID_INVALID",
            "Project promotion requires a lowercase ASCII Pack ID.",
        )
    _, _, active_pack_paths = _project_expertise_configuration(repo)
    matches: list[tuple[str, Path, dict[str, Any]]] = []
    for pack_path in active_pack_paths:
        target = safe_target(repo, pack_path)
        if target.is_symlink() or not target.is_file():
            continue
        pack = read_json(target)
        if pack.get("expertise_pack_id") == expertise_pack_id:
            matches.append((pack_path, target.parent, pack))
    if len(matches) != 1:
        raise MaestroError(
            "EXPERTISE_PROJECT_PROMOTION_SOURCE_MISSING",
            (
                "Global promotion requires exactly one active project "
                f"publication for {expertise_pack_id}."
            ),
        )
    pack_path, skill_root, pack = matches[0]
    if pack.get("extends") is not None:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_UNSUPPORTED",
            (
                "Direct global promotion supports standalone project Packs. "
                "Extensions require a separately reviewed Registry change."
            ),
        )
    if (
        pack.get("portability") != "project"
        or pack.get("status") not in {"pilot", "active"}
        or pack.get("source_manifest") != "evidence/sources.json"
        or pack.get("evaluation_suite") != "evals/cases.json"
    ):
        raise MaestroError(
            "EXPERTISE_PROJECT_PROMOTION_SOURCE_INVALID",
            "The active project Pack does not satisfy the publication contract.",
        )

    validation_registry = copy.deepcopy(
        load_source_registry(repo)
        if _is_harness_source_repository(repo)
        else load_registry()
    )
    validation_registry["expertise_packs"] = [
        item
        for item in validation_registry["expertise_packs"]
        if item.get("expertise_pack_id") != expertise_pack_id
    ]
    validation_registry["expertise_packs"].append(copy.deepcopy(pack))
    registry_errors = validate_registry(validation_registry)
    if registry_errors:
        raise MaestroError(
            "EXPERTISE_PROJECT_PROMOTION_SOURCE_INVALID",
            "; ".join(registry_errors),
        )

    try:
        publication = project_publication_snapshot(
            pack,
            skill_root=skill_root,
        )
    except MaestroError as exc:
        if exc.code == "PROJECT_EXPERTISE_PUBLICATION_STALE":
            raise MaestroError(
                "EXPERTISE_PROJECT_PROMOTION_SOURCE_STALE",
                (
                    "The project-confirmed Skill changed after activation. "
                    "Confirm a new project version before global promotion."
                ),
            ) from exc
        raise MaestroError(
            "EXPERTISE_PROJECT_PROMOTION_SOURCE_INVALID",
            "Project publication provenance does not match its Pack.",
        ) from exc
    activation = publication["activation"]
    candidate = publication["candidate"]
    candidate_id = activation["candidate_id"]
    if (
        not _candidate_contract_valid(candidate, candidate_id)
        or candidate.get("expertise_pack_id") != expertise_pack_id
    ):
        raise MaestroError(
            "EXPERTISE_PROJECT_PROMOTION_SOURCE_INVALID",
            "Project publication provenance does not match its Pack.",
        )
    source_files = publication["files"]
    source_digests = {
        path: sha256_text(content)
        for path, content in source_files.items()
    }

    global_skill_id = f"maestro-{expertise_pack_id}"
    global_candidate = copy.deepcopy(candidate)
    global_candidate["portability"] = "global"
    global_candidate["component_change"] = {
        "kind": "new-pack",
        "target_guide_id": None,
    }
    global_pack = copy.deepcopy(pack)
    global_pack["portability"] = "project"
    global_pack["status"] = "pilot"
    global_pack["skill_id"] = global_skill_id
    global_pack.pop("extends", None)
    promoted_files = copy.deepcopy(source_files)
    promoted_files["candidate.json"] = pretty_json(global_candidate)
    promoted_files[f"draft/{PROJECT_PACK_FILENAME}"] = pretty_json(
        global_pack
    )
    promoted_files["draft/SKILL.md"] = _global_skill_identity(
        promoted_files["draft/SKILL.md"],
        current_skill_id=pack["skill_id"],
        global_skill_id=global_skill_id,
    )
    if pack["skill_id"] != global_skill_id:
        promoted_files["draft/agents/openai.yaml"] = promoted_files[
            "draft/agents/openai.yaml"
        ].replace(
            f"${pack['skill_id']}",
            f"${global_skill_id}",
        )
    files = [
        {
            "path": path,
            "sha256": sha256_text(content),
            "content": content,
        }
        for path, content in sorted(promoted_files.items())
    ]
    if any(str(repo) in item["content"] for item in files):
        raise MaestroError(
            "EXPERTISE_CONTRIBUTION_PRIVATE_PATH",
            "Project publication contains the repository's absolute path.",
        )
    contribution = _expertise_contribution(
        candidate_id=candidate_id,
        candidate=global_candidate,
        pack=global_pack,
        files=files,
    )
    source_digest = sha256_text(
        canonical_json(
            {
                "activation": activation,
                "publication_files": source_digests,
                "promotion_transform": (
                    "maestro_project_publication_to_global_v1"
                ),
            }
        )
    )
    return {
        "source_kind": "project_publication",
        "source_ref": pack_path,
        "source_digest": source_digest,
        "candidate_id": candidate_id,
        "contribution": contribution,
    }


def _candidate_promotion_source(
    repo: Path,
    *,
    candidate_root: Path,
    candidate: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    files = _candidate_contribution_files(candidate_root, pack)
    if any(str(repo) in item["content"] for item in files):
        raise MaestroError(
            "EXPERTISE_CONTRIBUTION_PRIVATE_PATH",
            "Candidate content contains the producing repository's absolute path.",
        )
    contribution = _expertise_contribution(
        candidate_id=candidate["candidate_id"],
        candidate=candidate,
        pack=pack,
        files=files,
    )
    return {
        "source_kind": "candidate_snapshot",
        "source_ref": (
            ".maestro/state/candidates/expertise/"
            f"{candidate['candidate_id']}"
        ),
        "source_digest": contribution["bundle_digest"],
        "candidate_id": candidate["candidate_id"],
        "contribution": contribution,
    }


def _is_harness_source_repository(repo: Path) -> bool:
    required = (
        "pyproject.toml",
        "src/maestro/release.py",
        "src/maestro/resources/registry/expertise-packs",
        "skills/maestro/SKILL.md",
    )
    for relative_path in required:
        path = safe_target(repo, relative_path)
        if path.is_symlink() or not path.exists():
            return False
    return True


def _contribution_file_contents(
    contribution: dict[str, Any],
) -> dict[str, str]:
    return {
        item["path"]: item["content"]
        for item in contribution["files"]
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("content"), str)
    }


def _merged_unique_strings(
    *values: Any,
) -> list[str]:
    merged: list[str] = []
    for value in values:
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, str) and item not in merged:
                merged.append(item)
    return merged


def _merge_guide_source_manifests(
    base: dict[str, Any],
    addition: dict[str, Any],
    *,
    target_pack_id: str,
) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    merged["expertise_pack_id"] = target_pack_id
    merged["verified_on"] = max(
        str(base.get("verified_on") or ""),
        str(addition.get("verified_on") or ""),
    )
    by_id = {
        source["source_id"]: source
        for source in merged.get("sources", [])
        if isinstance(source, dict)
        and isinstance(source.get("source_id"), str)
    }
    for source in addition.get("sources", []):
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("source_id"), str)
        ):
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_SOURCE_INVALID",
                "Guide-addition source metadata is invalid.",
            )
        existing = by_id.get(source["source_id"])
        if existing is None:
            copied = copy.deepcopy(source)
            merged.setdefault("sources", []).append(copied)
            by_id[source["source_id"]] = copied
            continue
        for field in ("tier", "url", "freshness"):
            if existing.get(field) != source.get(field):
                raise MaestroError(
                    "EXPERTISE_GLOBAL_PROMOTION_SOURCE_CONFLICT",
                    (
                        "A guide-addition source ID conflicts with the "
                        f"bundled source: {source['source_id']}."
                    ),
                )
        existing["supports"] = _merged_unique_strings(
            existing.get("supports"),
            source.get("supports"),
        )
        existing["used_by"] = _merged_unique_strings(
            existing.get("used_by"),
            source.get("used_by"),
        )
    return merged


def _rewrite_evaluation_pack_id(
    value: Any,
    *,
    source_pack_id: str,
    target_pack_id: str,
) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                target_pack_id
                if key in {"expertise_pack_id", "expected_pack_id", "observed_pack_id"}
                and item == source_pack_id
                else _rewrite_evaluation_pack_id(
                    item,
                    source_pack_id=source_pack_id,
                    target_pack_id=target_pack_id,
                )
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _rewrite_evaluation_pack_id(
                item,
                source_pack_id=source_pack_id,
                target_pack_id=target_pack_id,
            )
            for item in value
        ]
    return value


def _merge_guide_evaluations(
    base_cases: dict[str, Any],
    base_results: dict[str, Any],
    addition_cases: dict[str, Any],
    addition_results: dict[str, Any],
    *,
    source_pack_id: str,
    target_pack_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    incoming_cases = _rewrite_evaluation_pack_id(
        addition_cases,
        source_pack_id=source_pack_id,
        target_pack_id=target_pack_id,
    )
    incoming_results = _rewrite_evaluation_pack_id(
        addition_results,
        source_pack_id=source_pack_id,
        target_pack_id=target_pack_id,
    )
    existing_case_ids = {
        case.get("case_id")
        for case in base_cases.get("cases", [])
        if isinstance(case, dict)
    }
    incoming_case_ids = {
        case.get("case_id")
        for case in incoming_cases.get("cases", [])
        if isinstance(case, dict)
    }
    if existing_case_ids & incoming_case_ids:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_EVALUATION_CONFLICT",
            "Guide-addition evaluation case IDs overlap the bundled Pack.",
        )
    merged_results = copy.deepcopy(base_results)
    merged_results["expertise_pack_id"] = target_pack_id
    merged_results["results"] = [
        *copy.deepcopy(base_results.get("results", [])),
        *copy.deepcopy(incoming_results.get("results", [])),
    ]
    merged_cases = copy.deepcopy(base_cases)
    merged_cases["expertise_pack_id"] = target_pack_id
    merged_cases["evaluated_on"] = max(
        str(base_cases.get("evaluated_on") or ""),
        str(incoming_cases.get("evaluated_on") or ""),
    )
    merged_cases["cases"] = [
        *copy.deepcopy(base_cases.get("cases", [])),
        *copy.deepcopy(incoming_cases.get("cases", [])),
    ]
    merged_cases["evaluation_artifact"] = {
        "path": "evals/results.json",
        "sha256": sha256_text(pretty_json(merged_results)),
    }
    return merged_cases, merged_results


def _skill_with_guide_reference(
    content: str,
    *,
    guide_id: str,
) -> str:
    if f"`{guide_id}`" in content:
        return content
    guide_heading = "\n## Guide loading\n"
    next_heading = "\n## Research gate\n"
    loading_tail = "\nDo not open every reference by default."
    if guide_heading not in content or next_heading not in content:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_SKILL_INVALID",
            (
                "The bundled Skill must contain Guide loading and Research "
                "gate sections before a Guide can be added automatically."
            ),
        )
    insertion_point = (
        loading_tail
        if loading_tail in content
        else next_heading
    )
    before, after = content.split(insertion_point, 1)
    entry = (
        f"- `{guide_id}` →\n"
        f"  `references/{guide_id}.md`\n"
    )
    return before.rstrip() + "\n" + entry + insertion_point + after


def _guide_addition_marker_path(
    *,
    skill_id: str,
    candidate_id: str,
) -> str:
    return (
        f"skills/{skill_id}/evidence/promotions/"
        f"{candidate_id}.json"
    )


def _guide_addition_applied(
    repo: Path,
    *,
    contribution: dict[str, Any],
) -> bool:
    component_change = contribution.get("component_change")
    base = contribution.get("base")
    if (
        not isinstance(component_change, dict)
        or component_change.get("kind") != "guide-addition"
        or not isinstance(base, dict)
        or not isinstance(base.get("expertise_pack_id"), str)
    ):
        return False
    registry = load_source_registry(repo)
    target = next(
        (
            pack
            for pack in registry["expertise_packs"]
            if pack.get("expertise_pack_id")
            == base["expertise_pack_id"]
        ),
        None,
    )
    if target is None:
        return False
    marker_path = _guide_addition_marker_path(
        skill_id=target["skill_id"],
        candidate_id=contribution["candidate_id"],
    )
    target_guide_id = component_change.get("target_guide_id")
    try:
        marker = read_json(safe_target(repo, marker_path))
    except MaestroError:
        return False
    return (
        marker.get("schema_version")
        == "maestro_expertise_global_component_promotion_v1"
        and marker.get("candidate_id") == contribution["candidate_id"]
        and marker.get("candidate_digest")
        == contribution["candidate_digest"]
        and marker.get("bundle_digest")
        == contribution["bundle_digest"]
        and marker.get("target_pack_id")
        == base["expertise_pack_id"]
        and marker.get("target_guide_id") == target_guide_id
        and any(
            guide.get("guide_id") == target_guide_id
            for guide in target.get("guides", [])
            if isinstance(guide, dict)
        )
        and file_sha256(
            safe_target(
                repo,
                (
                    f"skills/{target['skill_id']}/references/"
                    f"{target_guide_id}.md"
                ),
            )
        )
        == marker.get("reference_sha256")
    )


def _guide_addition_global_payload(
    repo: Path,
    *,
    source: dict[str, Any],
    contribution: dict[str, Any],
    file_contents: dict[str, str],
    registry: dict[str, Any],
) -> dict[str, Any]:
    component_change = contribution["component_change"]
    base_pin = contribution.get("base")
    if (
        not isinstance(base_pin, dict)
        or set(base_pin) != {"expertise_pack_id", "version", "digest"}
    ):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_BASE_INVALID",
            "Guide addition must pin one bundled base Pack.",
        )
    base_pack = next(
        (
            pack
            for pack in registry["expertise_packs"]
            if pack.get("expertise_pack_id")
            == base_pin["expertise_pack_id"]
        ),
        None,
    )
    if (
        base_pack is None
        or base_pack.get("portability") != "global"
        or base_pack.get("version") != base_pin["version"]
        or expertise_manifest_digest(base_pack) != base_pin["digest"]
    ):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_BASE_STALE",
            "The Guide addition no longer matches the current bundled base Pack.",
        )
    source_pack_id = contribution["expertise_pack_id"]
    try:
        addition_pack = json.loads(
            file_contents[f"draft/{PROJECT_PACK_FILENAME}"]
        )
        addition_sources = json.loads(
            file_contents["evidence/sources.json"]
        )
        addition_cases = json.loads(
            file_contents["evals/cases.json"]
        )
        addition_results = json.loads(
            file_contents["evals/results.json"]
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_BUNDLE_INVALID",
            f"Guide-addition content is invalid: {exc}",
        ) from exc
    target_guide_id = component_change.get("target_guide_id")
    addition_guides = [
        guide
        for guide in addition_pack.get("guides", [])
        if isinstance(guide, dict)
    ]
    if (
        addition_pack.get("expertise_pack_id") != source_pack_id
        or addition_pack.get("extends") != base_pin
        or len(addition_guides) != 1
        or addition_guides[0].get("guide_id") != target_guide_id
        or any(
            guide.get("guide_id") == target_guide_id
            for guide in base_pack.get("guides", [])
            if isinstance(guide, dict)
        )
    ):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_GUIDE_INVALID",
            (
                "Guide addition must contain one new Guide that does not "
                "already exist in the pinned bundled Pack."
            ),
        )

    target_pack = copy.deepcopy(base_pack)
    target_pack["version"] += 1
    target_pack["triggers"] = _merged_unique_strings(
        base_pack.get("triggers"),
        addition_pack.get("triggers"),
    )
    target_pack["dominance_triggers"] = _merged_unique_strings(
        base_pack.get("dominance_triggers"),
        addition_pack.get("dominance_triggers"),
    )
    target_pack["guides"] = [
        *copy.deepcopy(base_pack["guides"]),
        copy.deepcopy(addition_guides[0]),
    ]
    base_policy = target_pack["research_policy"]
    addition_policy = addition_pack.get("research_policy", {})
    if (
        addition_policy.get("default_mode")
        != base_policy.get("default_mode")
    ):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_RESEARCH_POLICY_CONFLICT",
            "Guide addition must preserve the bundled Pack's default research mode.",
        )
    base_policy["contextualize_triggers"] = _merged_unique_strings(
        base_policy.get("contextualize_triggers"),
        addition_policy.get("contextualize_triggers"),
    )
    base_policy["refresh_triggers"] = _merged_unique_strings(
        base_policy.get("refresh_triggers"),
        addition_policy.get("refresh_triggers"),
    )

    prospective_registry = copy.deepcopy(registry)
    prospective_registry["expertise_packs"] = [
        target_pack
        if pack.get("expertise_pack_id")
        == target_pack["expertise_pack_id"]
        else pack
        for pack in prospective_registry["expertise_packs"]
    ]
    registry_errors = validate_registry(prospective_registry)
    if registry_errors:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_REGISTRY_INVALID",
            "; ".join(registry_errors),
        )

    skill_root = f"skills/{target_pack['skill_id']}"
    base_skill = safe_target(repo, f"{skill_root}/SKILL.md").read_text(
        encoding="utf-8",
    )
    base_sources = read_json(
        safe_target(repo, f"{skill_root}/evidence/sources.json")
    )
    base_cases = read_json(
        safe_target(repo, f"{skill_root}/evals/cases.json")
    )
    base_results = read_json(
        safe_target(repo, f"{skill_root}/evals/results.json")
    )
    merged_sources = _merge_guide_source_manifests(
        base_sources,
        addition_sources,
        target_pack_id=target_pack["expertise_pack_id"],
    )
    merged_cases, merged_results = _merge_guide_evaluations(
        base_cases,
        base_results,
        addition_cases,
        addition_results,
        source_pack_id=source_pack_id,
        target_pack_id=target_pack["expertise_pack_id"],
    )
    reference_source = (
        f"draft/references/{target_guide_id}.md"
    )
    if reference_source not in file_contents:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_BUNDLE_INCOMPLETE",
            "Guide addition is missing its Decision Guide reference.",
        )
    reference_content = file_contents[reference_source]
    marker = {
        "schema_version": (
            "maestro_expertise_global_component_promotion_v1"
        ),
        "candidate_id": contribution["candidate_id"],
        "candidate_digest": contribution["candidate_digest"],
        "bundle_digest": contribution["bundle_digest"],
        "component_change": copy.deepcopy(component_change),
        "source_pack_id": source_pack_id,
        "target_pack_id": target_pack["expertise_pack_id"],
        "base_before": copy.deepcopy(base_pin),
        "base_after": {
            "version": target_pack["version"],
            "digest": expertise_manifest_digest(target_pack),
        },
        "target_guide_id": target_guide_id,
        "reference_sha256": sha256_text(reference_content),
    }
    expected_files: dict[str, str] = {
        (
            "src/maestro/resources/registry/expertise-packs/"
            f"{target_pack['expertise_pack_id']}.json"
        ): pretty_json(target_pack),
        f"{skill_root}/SKILL.md": _skill_with_guide_reference(
            base_skill,
            guide_id=target_guide_id,
        ),
        f"{skill_root}/references/{target_guide_id}.md": (
            reference_content
        ),
        f"{skill_root}/evidence/sources.json": pretty_json(
            merged_sources
        ),
        f"{skill_root}/evals/cases.json": pretty_json(merged_cases),
        f"{skill_root}/evals/results.json": pretty_json(
            merged_results
        ),
        _guide_addition_marker_path(
            skill_id=target_pack["skill_id"],
            candidate_id=contribution["candidate_id"],
        ): pretty_json(marker),
    }
    packaged_sources_path = (
        "src/maestro/resources/expertise-sources/"
        f"{target_pack['expertise_pack_id']}.json"
    )
    packaged_sources_target = safe_target(repo, packaged_sources_path)
    if (
        packaged_sources_target.is_file()
        and not packaged_sources_target.is_symlink()
    ):
        expected_files[packaged_sources_path] = pretty_json(
            merged_sources
        )

    quality_path = "evals/quality.json"
    if quality_path in file_contents:
        evidence_root = (
            f"{skill_root}/evals/promotions/"
            f"{contribution['candidate_id']}"
        )
        expected_files[f"{evidence_root}/quality.json"] = (
            file_contents[quality_path]
        )
        for path, content in sorted(file_contents.items()):
            if path.startswith("evals/artifacts/"):
                expected_files[
                    f"{evidence_root}/"
                    + path.removeprefix("evals/")
                ] = content

    replaceable_paths = {
        (
            "src/maestro/resources/registry/expertise-packs/"
            f"{target_pack['expertise_pack_id']}.json"
        ),
        f"{skill_root}/SKILL.md",
        f"{skill_root}/evidence/sources.json",
        f"{skill_root}/evals/cases.json",
        f"{skill_root}/evals/results.json",
    }
    if packaged_sources_path in expected_files:
        replaceable_paths.add(packaged_sources_path)
    project_path = safe_target(repo, ".maestro/project.json")
    if project_path.is_file() and not project_path.is_symlink():
        project = read_json(project_path)
        configuration = project.get("expertise")
        active_paths = (
            configuration.get("active_pack_paths", [])
            if isinstance(configuration, dict)
            else []
        )
        published_path = (
            f".agents/skills/{addition_pack['skill_id']}/"
            f"{PROJECT_PACK_FILENAME}"
        )
        if published_path in active_paths:
            activation_path = safe_target(
                repo,
                (
                    f".agents/skills/{addition_pack['skill_id']}/"
                    "activation.json"
                ),
            )
            activation = (
                read_json(activation_path)
                if activation_path.is_file()
                and not activation_path.is_symlink()
                else {}
            )
            if (
                activation.get("candidate_id")
                == contribution["candidate_id"]
            ):
                updated_project = copy.deepcopy(project)
                updated_project["expertise"]["active_pack_paths"] = [
                    path for path in active_paths
                    if path != published_path
                ]
                expected_files[".maestro/project.json"] = pretty_json(
                    updated_project
                )
                replaceable_paths.add(".maestro/project.json")

    lock_path = safe_target(repo, ".maestro/lock.json")
    if lock_path.exists():
        if lock_path.is_symlink() or not lock_path.is_file():
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_PROJECT_LOCK_INVALID",
                "Harness project lock must be a regular file.",
            )
        lock = read_json(lock_path)
        lock_registry = lock.get("registry")
        current_registry_digest = source_registry_digest(repo)
        if (
            not isinstance(lock_registry, dict)
            or lock_registry.get("sha256")
            != current_registry_digest
        ):
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_PROJECT_LOCK_STALE",
                "Review and apply a fresh project upgrade before global promotion.",
            )
        updated_lock = copy.deepcopy(lock)
        updated_lock["registry"]["sha256"] = source_registry_digest(
            repo,
            registry=prospective_registry,
        )
        expected_files[".maestro/lock.json"] = pretty_json(
            updated_lock
        )
        replaceable_paths.add(".maestro/lock.json")

    return {
        "source_kind": source["source_kind"],
        "source_ref": source["source_ref"],
        "source_digest": source["source_digest"],
        "bundle_path": None,
        "bundle_digest": contribution["bundle_digest"],
        "candidate_digest": contribution["candidate_digest"],
        "expertise_pack_id": target_pack["expertise_pack_id"],
        "skill_id": target_pack["skill_id"],
        "skill_root": skill_root,
        "existing_pack": base_pack,
        "expected_files": expected_files,
        "replaceable_paths": sorted(replaceable_paths),
        "target_mode": "update",
    }


def _global_promotion_payload(
    repo: Path,
    *,
    source: dict[str, Any],
) -> dict[str, Any]:
    if not _is_harness_source_repository(repo):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_TARGET_INVALID",
            "Global promotion must run in a Harness Maestro source checkout.",
        )
    contribution = source["contribution"]
    if contribution.get("portability") != "global":
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_UNSUPPORTED",
            "Harness source promotion requires a globally portable candidate.",
        )
    file_contents = _contribution_file_contents(contribution)
    registry = load_source_registry(repo)
    component_kind = contribution.get(
        "component_change",
        {},
    ).get("kind")
    if component_kind == "guide-addition":
        return _guide_addition_global_payload(
            repo,
            source=source,
            contribution=contribution,
            file_contents=file_contents,
            registry=registry,
        )
    if (
        component_kind != "new-pack"
        or contribution.get("base") is not None
    ):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_UNSUPPORTED",
            (
                "Direct Harness promotion currently supports standalone new "
                "Packs and one-Guide additions to a pinned bundled Pack."
            ),
        )
    try:
        global_pack = json.loads(
            file_contents[f"draft/{PROJECT_PACK_FILENAME}"]
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_BUNDLE_INVALID",
            f"Contribution Pack content is invalid: {exc}",
        ) from exc
    if not isinstance(global_pack, dict):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_BUNDLE_INVALID",
            "Contribution Pack content must be an object.",
        )
    global_pack = copy.deepcopy(global_pack)
    global_pack["portability"] = "global"
    global_pack["status"] = "pilot"
    global_pack.pop("extends", None)
    pack_id = global_pack.get("expertise_pack_id")
    skill_id = global_pack.get("skill_id")
    if (
        pack_id != contribution.get("expertise_pack_id")
        or skill_id != f"maestro-{pack_id}"
    ):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_IDENTITY_INVALID",
            "Global Pack and Skill IDs must match the contribution identity.",
        )

    existing_pack = next(
        (
            item
            for item in registry["expertise_packs"]
            if item.get("expertise_pack_id") == pack_id
            or item.get("skill_id") == skill_id
        ),
        None,
    )
    prospective_registry = copy.deepcopy(registry)
    if existing_pack is None:
        prospective_registry["expertise_packs"].append(global_pack)
        prospective_registry["expertise_packs"].sort(
            key=lambda item: item["expertise_pack_id"]
        )
        registry_errors = validate_registry(prospective_registry)
        if registry_errors:
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_REGISTRY_INVALID",
                "; ".join(registry_errors),
            )

    skill_root = f"skills/{skill_id}"
    expected_files: dict[str, str] = {
        (
            "src/maestro/resources/registry/expertise-packs/"
            f"{pack_id}.json"
        ): pretty_json(global_pack),
    }
    for source_path, content in sorted(file_contents.items()):
        destination: str | None = None
        if source_path == "draft/SKILL.md":
            destination = f"{skill_root}/SKILL.md"
        elif source_path.startswith("draft/agents/"):
            destination = (
                f"{skill_root}/"
                + source_path.removeprefix("draft/")
            )
        elif source_path.startswith("draft/references/"):
            destination = (
                f"{skill_root}/"
                + source_path.removeprefix("draft/")
            )
        elif source_path.startswith(("evidence/", "evals/")):
            destination = f"{skill_root}/{source_path}"
        if destination is not None:
            expected_files[destination] = content

    required_destinations = {
        f"{skill_root}/SKILL.md",
        f"{skill_root}/agents/openai.yaml",
        f"{skill_root}/evidence/sources.json",
        f"{skill_root}/evals/cases.json",
        f"{skill_root}/evals/results.json",
        *{
            f"{skill_root}/references/{guide['guide_id']}.md"
            for guide in global_pack["guides"]
        },
    }
    if not required_destinations.issubset(expected_files):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_BUNDLE_INCOMPLETE",
            "Contribution is missing one or more global Skill files.",
        )
    lock_path = safe_target(repo, ".maestro/lock.json")
    if lock_path.exists():
        if lock_path.is_symlink() or not lock_path.is_file():
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_PROJECT_LOCK_INVALID",
                "Harness project lock must be a regular file.",
            )
        lock = read_json(lock_path)
        lock_registry = lock.get("registry")
        current_registry_digest = source_registry_digest(repo)
        if (
            not isinstance(lock_registry, dict)
            or lock_registry.get("sha256")
            != current_registry_digest
        ):
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_PROJECT_LOCK_STALE",
                "Review and apply a fresh project upgrade before global promotion.",
            )
        updated_lock = copy.deepcopy(lock)
        updated_lock["registry"]["sha256"] = source_registry_digest(
            repo,
            registry=prospective_registry,
        )
        expected_files[".maestro/lock.json"] = pretty_json(
            updated_lock
        )
    return {
        "source_kind": source["source_kind"],
        "source_ref": source["source_ref"],
        "source_digest": source["source_digest"],
        "bundle_path": (
            source["source_ref"]
            if source["source_kind"] == "candidate_contribution"
            else None
        ),
        "bundle_digest": contribution["bundle_digest"],
        "candidate_digest": contribution["candidate_digest"],
        "expertise_pack_id": pack_id,
        "skill_id": skill_id,
        "skill_root": skill_root,
        "existing_pack": existing_pack,
        "expected_files": expected_files,
        "replaceable_paths": (
            [".maestro/lock.json"]
            if ".maestro/lock.json" in expected_files
            else []
        ),
        "target_mode": "create",
    }


def _global_adoption_status(
    repo: Path,
    *,
    source: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "promotion_source_kind": source["source_kind"],
        "promotion_source_ref": source["source_ref"],
        "commit_status": "not_tracked",
        "push_status": "not_tracked",
        "release_status": "not_tracked",
        "automatic_commit_performed": False,
        "automatic_push_performed": False,
        "automatic_release_performed": False,
    }
    if not _is_harness_source_repository(repo):
        return {
            **base,
            "status": "requires_harness_repository",
            "action_available": False,
            "changed_paths": [],
        }
    if _guide_addition_applied(
        repo,
        contribution=source["contribution"],
    ):
        return {
            **base,
            "status": "harness_source_applied",
            "action_available": False,
            "changed_paths": [],
        }
    try:
        payload = _global_promotion_payload(
            repo,
            source=source,
        )
    except MaestroError as exc:
        return {
            **base,
            "status": "promotion_unavailable",
            "action_available": False,
            "changed_paths": [],
            "issue": {
                "code": exc.code,
                "message": exc.message,
            },
        }
    matches = [
        file_sha256(safe_target(repo, path))
        == sha256_text(content)
        for path, content in payload["expected_files"].items()
    ]
    replaceable_paths = set(payload["replaceable_paths"])
    exists = [
        safe_target(repo, path).exists()
        for path in payload["expected_files"]
        if path not in replaceable_paths
    ]
    skill_root_exists = safe_target(
        repo,
        payload["skill_root"],
    ).exists()
    if all(matches):
        status = "harness_source_applied"
        action_available = False
    elif payload.get("target_mode") == "update":
        status = "ready_for_harness_source"
        action_available = True
    elif any(exists) or skill_root_exists:
        status = "harness_source_conflict"
        action_available = False
    else:
        status = "ready_for_harness_source"
        action_available = True
    return {
        **base,
        "status": status,
        "action_available": action_available,
        "changed_paths": sorted(payload["expected_files"]),
    }


def _candidate_global_adoption_status(
    repo: Path,
    *,
    candidate_root: Path,
    candidate: dict[str, Any],
    pack: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "promotion_source_kind": "candidate_snapshot",
        "promotion_source_ref": None,
        "commit_status": "not_tracked",
        "push_status": "not_tracked",
        "release_status": "not_tracked",
        "automatic_commit_performed": False,
        "automatic_push_performed": False,
        "automatic_release_performed": False,
    }
    if not _is_harness_source_repository(repo):
        return {
            **base,
            "status": "requires_harness_repository",
            "action_available": False,
            "changed_paths": [],
        }
    try:
        source = _candidate_promotion_source(
            repo,
            candidate_root=candidate_root,
            candidate=candidate,
            pack=pack,
        )
    except MaestroError as exc:
        return {
            **base,
            "status": "promotion_unavailable",
            "action_available": False,
            "changed_paths": [],
            "issue": {
                "code": exc.code,
                "message": exc.message,
            },
        }
    return _global_adoption_status(repo, source=source)


def _project_global_adoption_status(
    repo: Path,
    *,
    expertise_pack_id: str,
) -> dict[str, Any]:
    base = {
        "promotion_source_kind": "project_publication",
        "promotion_source_ref": None,
        "commit_status": "not_tracked",
        "push_status": "not_tracked",
        "release_status": "not_tracked",
        "automatic_commit_performed": False,
        "automatic_push_performed": False,
        "automatic_release_performed": False,
    }
    if not _is_harness_source_repository(repo):
        return {
            **base,
            "status": "requires_harness_repository",
            "action_available": False,
            "changed_paths": [],
        }
    try:
        source = _project_promotion_source(
            repo,
            expertise_pack_id=expertise_pack_id,
        )
    except MaestroError as exc:
        return {
            **base,
            "status": (
                "promotion_unsupported"
                if exc.code == "EXPERTISE_GLOBAL_PROMOTION_UNSUPPORTED"
                else "promotion_unavailable"
            ),
            "action_available": False,
            "changed_paths": [],
            "issue": {
                "code": exc.code,
                "message": exc.message,
            },
        }
    return _global_adoption_status(repo, source=source)


def _candidate_project_global_adoption_status(
    repo: Path,
    *,
    candidate_id: str,
    expertise_pack_id: str,
) -> dict[str, Any] | None:
    """Resolve an applied project-publication promotion for its source candidate."""

    try:
        source = _project_promotion_source(
            repo,
            expertise_pack_id=expertise_pack_id,
        )
    except MaestroError:
        return None
    if source["candidate_id"] != candidate_id:
        return None
    adoption = _global_adoption_status(repo, source=source)
    return (
        adoption
        if adoption["status"] == "harness_source_applied"
        else None
    )


def build_expertise_global_promotion_plan(
    repo_path: str | Path,
    *,
    candidate_id: str | None = None,
    expertise_pack_id: str | None = None,
    approval_ref: str,
    promotion_source_kind: str | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _validate_approval_ref(approval_ref)
    if (
        (candidate_id is None) == (expertise_pack_id is None)
        or promotion_source_kind
        not in {
            None,
            "candidate_contribution",
            "candidate_snapshot",
            "project_publication",
        }
        or (
            promotion_source_kind
            in {"candidate_contribution", "candidate_snapshot"}
            and candidate_id is None
        )
        or (
            promotion_source_kind == "project_publication"
            and expertise_pack_id is None
        )
    ):
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_SOURCE_REQUIRED",
            "Choose exactly one candidate or active project Pack.",
        )
    if (
        promotion_source_kind == "project_publication"
        or expertise_pack_id is not None
    ):
        if expertise_pack_id is None:
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_SOURCE_REQUIRED",
                "Project publication promotion requires a Pack ID.",
            )
        source = _project_promotion_source(
            repo,
            expertise_pack_id=expertise_pack_id,
        )
    else:
        if candidate_id is None:
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_SOURCE_REQUIRED",
                "Candidate contribution promotion requires a candidate ID.",
            )
        candidate_root, candidate, pack = _fresh_candidate_pack(
            repo,
            candidate_id,
        )
        source = _candidate_promotion_source(
            repo,
            candidate_root=candidate_root,
            candidate=candidate,
            pack=pack,
        )
    _require_individual_candidate_action(
        repo,
        candidate_id=source["candidate_id"],
    )
    from .expertise_promotion import read_expertise_promotion_decision

    runtime_digest = candidate_expertise_statuses(repo).get(
        source["candidate_id"],
        {},
    ).get("definition_digest")
    promotion_decision = read_expertise_promotion_decision(
        repo,
        candidate_id=source["candidate_id"],
        candidate_digest=runtime_digest,
    )
    if promotion_decision["status"] == "declined":
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_DECLINED",
            (
                "This candidate digest was declined for global promotion. "
                "Reconsider the decision before creating a promotion plan."
            ),
        )
    adoption = _global_adoption_status(repo, source=source)
    if adoption["status"] == "harness_source_applied":
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_ALREADY_APPLIED",
            "This promotion source already matches the Harness global source.",
        )
    if adoption["status"] == "harness_source_conflict":
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_CONFLICT",
            "Harness global source paths already exist with different content.",
        )
    if adoption["status"] != "ready_for_harness_source":
        issue = adoption.get("issue")
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_NOT_READY",
            (
                issue["message"]
                if isinstance(issue, dict)
                and isinstance(issue.get("message"), str)
                else "The selected source is not ready for Harness promotion."
            ),
        )
    payload = _global_promotion_payload(
        repo,
        source=source,
    )
    operations = [
        _text_operation(
            repo,
            path,
            content,
            require_missing=path not in set(
                payload["replaceable_paths"]
            ),
        )
        for path, content in sorted(payload["expected_files"].items())
    ]
    base = {
        "schema_version": GLOBAL_PROMOTION_PLAN_VERSION,
        "command": "expertise-promote-global",
        "repo_realpath": str(repo),
        "candidate_id": source["candidate_id"],
        "expertise_pack_id": payload["expertise_pack_id"],
        "skill_id": payload["skill_id"],
        "approval_ref": approval_ref,
        "source_kind": payload["source_kind"],
        "source_ref": payload["source_ref"],
        "source_digest": payload["source_digest"],
        "candidate_digest": payload["candidate_digest"],
        "bundle_path": payload["bundle_path"],
        "bundle_digest": payload["bundle_digest"],
        "release_manifest_before_sha256": file_sha256(
            release_manifest_path(repo)
        ),
        "operations": operations,
        "warnings": [
            (
                "This applies the validated project publication or candidate "
                "contribution to the Harness Registry and bundled Skill source."
            ),
            (
                "It regenerates the local release manifest but does not "
                "stage, commit, push, open a pull request, tag, or release."
            ),
            (
                "When this Harness checkout is initialized, the same plan "
                "updates its project Registry lock to the promoted source."
            ),
            (
                "Delete the newly created Registry and Skill paths, then "
                "restore the prior Registry lock and release manifest to "
                "roll back before commit."
            ),
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def expertise_inventory(repo_path: str | Path) -> dict[str, Any]:
    from .expertise_promotion import read_expertise_promotion_decision

    repo = ensure_repo(repo_path)
    catalog = load_expertise_catalog(repo)
    runtime_statuses = candidate_expertise_statuses(repo)
    entries: list[dict[str, Any]] = []
    for pack in catalog:
        metadata = pack["_maestro"]
        if metadata["origin"] == "project":
            skill_path = metadata["skill_path"]
            source_path = safe_target(
                repo,
                (
                    Path(skill_path).parent
                    / pack["source_manifest"]
                ).as_posix(),
            )
            publication_path = safe_target(
                repo,
                (
                    Path(skill_path).parent
                    / "activation.json"
                ).as_posix(),
            )
        else:
            source_path = Path(
                str(
                    resource_root().joinpath(
                        f"expertise-sources/{pack['expertise_pack_id']}.json"
                    )
                )
            )
            publication_path = None
        source_manifest: dict[str, Any] | None = None
        if source_path.is_file() and not source_path.is_symlink():
            try:
                candidate = read_json(source_path)
                if (
                    candidate.get("schema_version")
                    == "maestro_expertise_sources_v1"
                    and candidate.get("expertise_pack_id")
                    == pack["expertise_pack_id"]
                    and isinstance(candidate.get("sources"), list)
                    and len(candidate["sources"]) <= 20
                ):
                    source_manifest = candidate
            except MaestroError:
                source_manifest = None
        publication: dict[str, Any] | None = None
        if (
            publication_path is not None
            and publication_path.is_file()
            and not publication_path.is_symlink()
        ):
            try:
                value = read_json(publication_path)
                publication = {
                    key: value.get(key)
                    for key in (
                        "action",
                        "candidate_id",
                        "pack_version",
                        "previous_definition_digest",
                    )
                }
            except MaestroError:
                publication = None
        sources_by_guide: dict[str, list[dict[str, Any]]] = {
            guide["guide_id"]: [] for guide in pack["guides"]
        }
        if source_manifest is not None:
            for source in source_manifest["sources"]:
                if not isinstance(source, dict):
                    continue
                for guide_id in source.get("used_by", []):
                    if guide_id in sources_by_guide:
                        sources_by_guide[guide_id].append(
                            {
                                "source_id": source.get("source_id"),
                                "tier": source.get("tier"),
                                "freshness": source.get("freshness"),
                            }
                        )
        entries.append(
            {
                "expertise_pack_id": pack["expertise_pack_id"],
                "summary": pack["summary"],
                "skill_id": pack["skill_id"],
                "status": pack["status"],
                "portability": pack["portability"],
                "version": pack["version"],
                "origin": metadata["origin"],
                "pack_path": metadata["pack_path"],
                "definition_digest": metadata["definition_digest"],
                "extends": metadata["base"],
                "global_adoption": (
                    _project_global_adoption_status(
                        repo,
                        expertise_pack_id=pack[
                            "expertise_pack_id"
                        ],
                    )
                    if metadata["origin"] == "project"
                    else None
                ),
                "triggers": list(pack.get("triggers", [])),
                "dominance_triggers": list(
                    pack.get("dominance_triggers", [])
                ),
                "guides": [
                    {
                        "guide_id": guide["guide_id"],
                        "summary": guide["summary"],
                        "freshness": guide["freshness"],
                        "triggers": list(guide.get("triggers", [])),
                        "sources": sources_by_guide.get(
                            guide["guide_id"],
                            [],
                        ),
                    }
                    for guide in pack["guides"]
                ],
                "source_manifest": (
                    {
                        "status": "available",
                        "verified_on": source_manifest.get("verified_on"),
                        "sources": [
                            {
                                key: source.get(key)
                                for key in (
                                    "source_id",
                                    "tier",
                                    "authority",
                                    "url",
                                    "used_by",
                                    "freshness",
                                )
                            }
                            for source in source_manifest["sources"]
                            if isinstance(source, dict)
                        ],
                    }
                    if source_manifest is not None
                    else {
                        "status": "unavailable",
                        "verified_on": None,
                        "sources": [],
                    }
                ),
                "publication": publication,
            }
        )
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
                disposition = read_candidate_disposition(
                    repo,
                    path.name,
                )
                validation = validate_expertise_candidate(repo, path.name)
                runtime_state = runtime_statuses.get(
                    candidate["candidate_id"],
                    {},
                )
                candidate_pack = read_json(
                    safe_target(
                        path,
                        f"draft/{PROJECT_PACK_FILENAME}",
                    )
                )
                matching_project_pack = next(
                    (
                        pack
                        for pack in catalog
                        if pack["_maestro"]["origin"] == "project"
                        and pack["expertise_pack_id"]
                        == candidate["expertise_pack_id"]
                    ),
                    None,
                )
                global_request = _candidate_global_request_status(
                    repo,
                    candidate_root=path,
                    candidate=candidate,
                    pack=candidate_pack,
                )
                global_adoption = _candidate_global_adoption_status(
                    repo,
                    candidate_root=path,
                    candidate=candidate,
                    pack=candidate_pack,
                )
                if (
                    global_adoption["status"]
                    != "harness_source_applied"
                ):
                    project_adoption = (
                        _candidate_project_global_adoption_status(
                            repo,
                            candidate_id=candidate["candidate_id"],
                            expertise_pack_id=candidate[
                                "expertise_pack_id"
                            ],
                        )
                    )
                    if project_adoption is not None:
                        global_adoption = project_adoption
                if (
                    validation["status"] != "PASS"
                    and global_adoption["status"]
                    != "harness_source_applied"
                ):
                    global_request = {
                        "status": "unavailable",
                        "output_path": None,
                        "validation_status": "not_run",
                        "matches_current_candidate": False,
                        "bundle_digest": None,
                        "repository_submission_status": (
                            "not_tracked"
                        ),
                        "release_status": "not_tracked",
                        "automatic_commit_performed": False,
                        "automatic_push_performed": False,
                        "automatic_pull_request_performed": False,
                        "automatic_release_performed": False,
                    }
                    global_adoption = {
                        "status": "promotion_unavailable",
                        "action_available": False,
                        "changed_paths": [],
                        "commit_status": "not_tracked",
                        "push_status": "not_tracked",
                        "release_status": "not_tracked",
                        "automatic_commit_performed": False,
                        "automatic_push_performed": False,
                        "automatic_release_performed": False,
                    }
                source_applied = (
                    global_adoption["status"]
                    == "harness_source_applied"
                )
                effective_validation_status = (
                    "PASS"
                    if source_applied
                    else validation["status"]
                )
                effective_runtime_status = runtime_state.get(
                    "runtime_status",
                    "invalid",
                )
                change_set_context = candidate_change_set_context(
                    repo,
                    candidate_id=candidate["candidate_id"],
                )
                if (
                    source_applied
                    and disposition is None
                ):
                    effective_runtime_status = "globally_promoted"
                elif disposition is not None:
                    effective_runtime_status = disposition["status"]
                candidates.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "expertise_pack_id": candidate["expertise_pack_id"],
                        "owner": candidate["owner"],
                        "review_after": candidate["review_after"],
                        "portability": candidate["portability"],
                        "generation": copy.deepcopy(
                            candidate.get("generation")
                        ),
                        "disposition": copy.deepcopy(disposition),
                        "ready_for_activation_review": (
                            disposition is None
                            and
                            runtime_state.get("runtime_status")
                            == "available"
                            and not change_set_context[
                                "atomic_required"
                            ]
                            and not source_applied
                        ),
                        "ready_for_export_review": (
                            disposition is None
                            and
                            runtime_state.get("runtime_status")
                            in {"available", "published"}
                            and candidate["portability"]
                            in {"profile", "global"}
                        ),
                        "validation_status": (
                            effective_validation_status
                        ),
                        "validation_issue_codes": (
                            []
                            if source_applied
                            else [
                                issue["code"]
                                for issue in validation["issues"]
                            ]
                        ),
                        "runtime_status": effective_runtime_status,
                        "immediate_use_allowed": runtime_state.get(
                            "immediate_use_allowed",
                            False,
                        )
                        and disposition is None,
                        "definition_digest": runtime_state.get(
                            "definition_digest"
                        ),
                        "promotion_decision": (
                            read_expertise_promotion_decision(
                                repo,
                                candidate_id=candidate["candidate_id"],
                                candidate_digest=runtime_state.get(
                                    "definition_digest"
                                ),
                            )
                        ),
                        "change_set_id": change_set_context[
                            "change_set_id"
                        ],
                        "change_set_candidate_ids": change_set_context[
                            "candidate_ids"
                        ],
                        "change_set_status": runtime_state.get(
                            "change_set_status"
                        ),
                        "proposed_guide_ids": [
                            guide["guide_id"]
                            for guide in candidate["proposed_guides"]
                        ],
                        "component_change": _candidate_component_change(
                            candidate,
                            candidate_pack,
                        ),
                        "global_request": global_request,
                        "global_adoption": global_adoption,
                        "pack_preview": (
                            _candidate_pack_preview(
                                path,
                                candidate,
                                candidate_pack,
                            )
                            if effective_validation_status == "PASS"
                            else None
                        ),
                        "recommended_action": (
                            "update"
                            if matching_project_pack is not None
                            else "activate"
                        ),
                    }
                )
            except MaestroError as exc:
                raw_change: dict[str, Any] | None = None
                raw_candidate_path = safe_target(path, "candidate.json")
                if (
                    raw_candidate_path.is_file()
                    and not raw_candidate_path.is_symlink()
                ):
                    try:
                        raw_candidate = read_json(raw_candidate_path)
                        value = raw_candidate.get("component_change")
                        if isinstance(value, dict):
                            raw_change = copy.deepcopy(value)
                    except MaestroError:
                        raw_change = None
                candidates.append(
                    {
                        "candidate_id": path.name,
                        "error": f"{exc.code}: {exc.message}",
                        "ready_for_activation_review": False,
                        "ready_for_export_review": False,
                        "runtime_status": "invalid",
                        "immediate_use_allowed": False,
                        "definition_digest": None,
                        "component_change": raw_change,
                    }
                )
    return {
        "schema_version": "maestro_expertise_inventory_v1",
        "status": "ok",
        "repo_root": str(repo),
        "packs": entries,
        "candidates": candidates,
        "deleted_candidates": _candidate_tombstones(repo),
        "writes_performed": False,
    }


def _build_expertise_activation_member_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    approval_ref: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _validate_approval_ref(approval_ref)
    candidate_root, _, pack = _fresh_candidate_pack(repo, candidate_id)

    skill_id = pack["skill_id"]
    destination_root = f".agents/skills/{skill_id}"
    if safe_target(repo, destination_root).exists():
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_EXISTS",
            f"Project Skill already exists: {destination_root}",
        )
    _, project, active_pack_paths = (
        _project_expertise_configuration(repo)
    )
    pack_path = f"{destination_root}/{PROJECT_PACK_FILENAME}"
    if git_ignored(repo, pack_path) is True:
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_IGNORED",
            "Active project Expertise must not be Git-ignored. "
            "Repair the project ignore policy before activation.",
        )
    if pack_path in active_pack_paths:
        raise MaestroError(
            "EXPERTISE_ALREADY_ACTIVE",
            f"Project Expertise is already enabled: {pack_path}",
        )

    contents, candidate_digest = _candidate_publication_contents(
        candidate_root,
        pack,
        destination_root,
    )
    operations = [
        _text_operation(
            repo,
            path,
            content,
            require_missing=True,
        )
        for path, content in sorted(contents.items())
    ]

    activation_content = _publication_record(
        action="activate",
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        approval_ref=approval_ref,
        pack_version=pack["version"],
        previous_definition_digest=None,
    )
    operations.append(
        _text_operation(
            repo,
            f"{destination_root}/activation.json",
            activation_content,
            require_missing=True,
        )
    )

    updated_project = copy.deepcopy(project)
    updated_project["expertise"] = {
        "active_pack_paths": [
            *active_pack_paths,
            pack_path,
        ]
    }
    project_content = pretty_json(updated_project)
    operations.append(
        _text_operation(
            repo,
            ".maestro/project.json",
            project_content,
        )
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
            "A compact candidate snapshot is copied into the active Pack; the ignored working candidate is retained.",
            "Stage and commit the changed project files after Doctor passes.",
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def build_expertise_activation_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    approval_ref: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _require_individual_candidate_action(
        repo,
        candidate_id=candidate_id,
    )
    return _build_expertise_activation_member_plan(
        repo,
        candidate_id=candidate_id,
        approval_ref=approval_ref,
    )


def _build_expertise_update_member_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    approval_ref: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _validate_approval_ref(approval_ref)
    candidate_root, _, pack = _fresh_candidate_pack(repo, candidate_id)
    _, _, active_pack_paths = _project_expertise_configuration(repo)

    destination_root = f".agents/skills/{pack['skill_id']}"
    pack_path = f"{destination_root}/{PROJECT_PACK_FILENAME}"
    if pack_path not in active_pack_paths:
        raise MaestroError(
            "EXPERTISE_UPDATE_TARGET_NOT_ACTIVE",
            "Update requires an active project Expertise with the same Skill "
            "identity. Use activate for a new Pack.",
        )
    if git_ignored(repo, pack_path) is True:
        raise MaestroError(
            "EXPERTISE_ACTIVE_TARGET_IGNORED",
            "Active project Expertise must not be Git-ignored. "
            "Repair the project ignore policy before updating it.",
        )

    catalog = load_expertise_catalog(repo)
    current = next(
        (
            item
            for item in catalog
            if item["_maestro"]["origin"] == "project"
            and item["_maestro"]["pack_path"] == pack_path
        ),
        None,
    )
    if current is None:
        raise MaestroError(
            "EXPERTISE_UPDATE_TARGET_INVALID",
            f"Active project Expertise cannot be loaded: {pack_path}",
        )
    if (
        pack["expertise_pack_id"] != current["expertise_pack_id"]
        or pack["skill_id"] != current["skill_id"]
    ):
        raise MaestroError(
            "EXPERTISE_UPDATE_IDENTITY_CHANGED",
            "An update must preserve expertise_pack_id and skill_id.",
        )
    if current["status"] != "pilot" or pack["status"] != current["status"]:
        raise MaestroError(
            "EXPERTISE_UPDATE_STATUS_UNSUPPORTED",
            "The v0.3 update path supports project pilot revisions only; "
            "active promotion remains a separate owner decision.",
        )
    if pack["version"] != current["version"] + 1:
        raise MaestroError(
            "EXPERTISE_UPDATE_VERSION_INVALID",
            "A project Expertise update must increment version by exactly one.",
        )

    contents, candidate_digest = _candidate_publication_contents(
        candidate_root,
        pack,
        destination_root,
    )
    publication_path = f"{destination_root}/activation.json"
    contents[publication_path] = _publication_record(
        action="update",
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        approval_ref=approval_ref,
        pack_version=pack["version"],
        previous_definition_digest=current["_maestro"]["definition_digest"],
    )
    operations = [
        _text_operation(repo, path, content)
        for path, content in sorted(contents.items())
    ]

    desired_guide_paths = {
        f"{destination_root}/references/{guide['guide_id']}.md"
        for guide in pack["guides"]
    }
    current_guide_paths = {
        f"{destination_root}/references/{guide['guide_id']}.md"
        for guide in current["guides"]
        if current["_maestro"]["guide_origins"][guide["guide_id"]]["origin"]
        == "project"
    }
    for obsolete_path in sorted(
        current_guide_paths - desired_guide_paths
    ):
        operations.append(_delete_operation(repo, obsolete_path))
    desired_artifact_paths = {
        path
        for path in contents
        if path.startswith(f"{destination_root}/evals/artifacts/")
    }
    artifact_root = safe_target(
        repo,
        f"{destination_root}/evals/artifacts",
    )
    current_artifact_paths = {
        path.relative_to(repo).as_posix()
        for path in artifact_root.iterdir()
        if artifact_root.is_dir()
        and path.is_file()
        and not path.is_symlink()
        and path.suffix == ".json"
    } if artifact_root.is_dir() else set()
    for obsolete_path in sorted(
        current_artifact_paths - desired_artifact_paths
    ):
        operations.append(_delete_operation(repo, obsolete_path))
    operations.sort(key=lambda item: item["path"])

    base = {
        "schema_version": UPDATE_PLAN_VERSION,
        "command": "expertise-update",
        "repo_realpath": str(repo),
        "candidate_id": candidate_id,
        "approval_ref": approval_ref,
        "operations": operations,
        "warnings": [
            "Update keeps the same project Pack identity and publishes one reviewed version increment.",
            "A changed bundled base pin is accepted only when the candidate pins the currently installed base.",
            "The ignored working candidate is retained; stage and commit the changed project files after Doctor passes.",
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def build_expertise_update_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    approval_ref: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _require_individual_candidate_action(
        repo,
        candidate_id=candidate_id,
    )
    return _build_expertise_update_member_plan(
        repo,
        candidate_id=candidate_id,
        approval_ref=approval_ref,
    )


def build_expertise_deactivation_plan(
    repo_path: str | Path,
    *,
    expertise_pack_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    if (
        not isinstance(expertise_pack_id, str)
        or ID_PATTERN.fullmatch(expertise_pack_id) is None
    ):
        raise MaestroError(
            "EXPERTISE_DEACTIVATION_ID_INVALID",
            "pack must be a lowercase ASCII Expertise Pack ID.",
        )
    _, project, active_pack_paths = _project_expertise_configuration(repo)
    catalog = load_expertise_catalog(repo)
    current = next(
        (
            item
            for item in catalog
            if item["_maestro"]["origin"] == "project"
            and item["expertise_pack_id"] == expertise_pack_id
        ),
        None,
    )
    if current is None:
        raise MaestroError(
            "EXPERTISE_DEACTIVATION_TARGET_NOT_ACTIVE",
            f"Active project Expertise is missing: {expertise_pack_id}",
        )
    pack_path = current["_maestro"]["pack_path"]
    if pack_path not in active_pack_paths:
        raise MaestroError(
            "EXPERTISE_DEACTIVATION_TARGET_NOT_ACTIVE",
            f"Project Expertise is not allowlisted: {expertise_pack_id}",
        )

    updated_project = copy.deepcopy(project)
    updated_project["expertise"] = {
        "active_pack_paths": [
            path for path in active_pack_paths if path != pack_path
        ]
    }
    operations = [
        _text_operation(
            repo,
            ".maestro/project.json",
            pretty_json(updated_project),
        )
    ]
    base = {
        "schema_version": DEACTIVATION_PLAN_VERSION,
        "command": "expertise-deactivate",
        "repo_realpath": str(repo),
        "expertise_pack_id": expertise_pack_id,
        "pack_path": pack_path,
        "definition_digest": current["_maestro"]["definition_digest"],
        "operations": operations,
        "warnings": [
            "Deactivation removes only the Maestro allowlist entry; project Skill files are preserved for review and rollback.",
            "The preserved project Skill may remain explicitly visible to the Host; deactivation stops Maestro routing, not Host discovery.",
            "Commit the project manifest change after review.",
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def _validate_candidate_disposition_reason(reason: str) -> str:
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason.strip()) > 200
        or any(character in reason for character in "\r\n\x00")
    ):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_REJECTION_REASON_INVALID",
            "reason must be one non-empty line of at most 200 characters.",
        )
    return reason.strip()


def build_expertise_rejection_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    reason: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _require_individual_candidate_action(
        repo,
        candidate_id=candidate_id,
    )
    root, _candidate = _read_candidate(repo, candidate_id)
    if read_candidate_disposition(repo, candidate_id) is not None:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_ALREADY_REJECTED",
            f"Candidate is already rejected: {candidate_id}",
        )
    normalized_reason = _validate_candidate_disposition_reason(reason)
    candidate_digest = _candidate_tree_digest(root)
    disposition = {
        "schema_version": CANDIDATE_DISPOSITION_VERSION,
        "candidate_id": candidate_id,
        "status": "rejected",
        "reason": normalized_reason,
        "candidate_digest": candidate_digest,
    }
    relative_path = (
        f".maestro/state/candidates/expertise/{candidate_id}/"
        f"{CANDIDATE_DISPOSITION_FILENAME}"
    )
    base = {
        "schema_version": REJECTION_PLAN_VERSION,
        "command": "expertise-reject-candidate",
        "repo_realpath": str(repo),
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "reason": normalized_reason,
        "operations": [
            _text_operation(
                repo,
                relative_path,
                pretty_json(disposition),
            )
        ],
        "warnings": [
            "Rejection stops candidate routing but preserves every candidate file.",
            "Restore requires a fresh typed preview; an expired or invalid restored candidate still remains non-routable.",
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def _build_expertise_archive_member_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    reason: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    root, _candidate = _read_candidate(repo, candidate_id)
    if read_candidate_disposition(repo, candidate_id) is not None:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_ALREADY_DISPOSED",
            f"Candidate already has a disposition: {candidate_id}",
        )
    normalized_reason = _validate_candidate_disposition_reason(reason)
    candidate_digest = _candidate_tree_digest(root)
    disposition = {
        "schema_version": CANDIDATE_DISPOSITION_VERSION,
        "candidate_id": candidate_id,
        "status": "archived",
        "reason": normalized_reason,
        "candidate_digest": candidate_digest,
    }
    relative_path = (
        f".maestro/state/candidates/expertise/{candidate_id}/"
        f"{CANDIDATE_DISPOSITION_FILENAME}"
    )
    return _finalize_plan(
        {
            "schema_version": ARCHIVE_PLAN_VERSION,
            "command": "expertise-archive-candidate",
            "repo_realpath": str(repo),
            "candidate_id": candidate_id,
            "candidate_digest": candidate_digest,
            "reason": normalized_reason,
            "operations": [
                _text_operation(
                    repo,
                    relative_path,
                    pretty_json(disposition),
                )
            ],
            "warnings": [
                "Archive stops candidate routing and preserves every candidate file.",
                "Restore requires a fresh typed preview.",
                "Permanent removal is available only through a separate archive-only confirmed preview.",
            ],
            "writes_performed": False,
        }
    )


def build_expertise_archive_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    reason: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _require_individual_candidate_action(
        repo,
        candidate_id=candidate_id,
    )
    return _build_expertise_archive_member_plan(
        repo,
        candidate_id=candidate_id,
        reason=reason,
    )


def _build_expertise_restore_member_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    root, _candidate = _read_candidate(repo, candidate_id)
    disposition = read_candidate_disposition(repo, candidate_id)
    if disposition is None:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_NOT_REJECTED",
            f"Candidate is not rejected: {candidate_id}",
        )
    candidate_digest = _candidate_tree_digest(root)
    relative_path = (
        f".maestro/state/candidates/expertise/{candidate_id}/"
        f"{CANDIDATE_DISPOSITION_FILENAME}"
    )
    base = {
        "schema_version": RESTORE_PLAN_VERSION,
        "command": "expertise-restore-candidate",
        "repo_realpath": str(repo),
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "reason": disposition["reason"],
        "operations": [_delete_operation(repo, relative_path)],
        "warnings": [
            "Restore removes only the archive or rejection marker.",
            "Runtime use resumes only if the complete candidate still validates, is not expired, is newer than the active Pack, and has no version conflict.",
        ],
        "writes_performed": False,
    }
    return _finalize_plan(base)


def build_expertise_restore_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _require_individual_candidate_action(
        repo,
        candidate_id=candidate_id,
    )
    return _build_expertise_restore_member_plan(
        repo,
        candidate_id=candidate_id,
    )


def _active_candidate_publications(
    repo: Path,
    *,
    candidate_id: str,
) -> list[str]:
    skill_root = safe_target(repo, ".agents/skills")
    if not skill_root.is_dir() or skill_root.is_symlink():
        return []
    matches: list[str] = []
    for path in sorted(skill_root.glob("*/activation.json"))[:MAX_CANDIDATES]:
        if path.is_symlink() or not path.is_file():
            continue
        value = read_json(path)
        if (
            isinstance(value, dict)
            and value.get("candidate_id") == candidate_id
        ):
            matches.append(path.relative_to(repo).as_posix())
    return matches


def _build_expertise_delete_member_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    confirmation: str,
    replacement_pack_ids: list[str] | None = None,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    if confirmation != candidate_id:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DELETE_CONFIRMATION_INVALID",
            "Permanent removal requires the exact candidate ID.",
        )
    root, candidate = _read_candidate(repo, candidate_id)
    disposition = read_candidate_disposition(repo, candidate_id)
    if (
        disposition is None
        or disposition.get("status") not in {"archived", "rejected"}
    ):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DELETE_REQUIRES_ARCHIVE",
            "Permanent removal is available only for an archived candidate "
            "or a legacy reversibly rejected candidate.",
        )
    publications = _active_candidate_publications(
        repo,
        candidate_id=candidate_id,
    )
    if publications:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DELETE_DEPENDENCY",
            "Deactivate the project Pack publication before permanent removal: "
            + ", ".join(publications),
        )
    replacements = list(replacement_pack_ids or [])
    if (
        len(replacements) != len(set(replacements))
        or len(replacements) > 4
        or any(
            not isinstance(item, str)
            or ID_PATTERN.fullmatch(item) is None
            for item in replacements
        )
    ):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DELETE_REPLACEMENTS_INVALID",
            "replacement_pack_ids must contain at most four unique Pack IDs.",
        )
    resolved_deleted_at = deleted_at or (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    try:
        parsed_deleted_at = datetime.fromisoformat(
            resolved_deleted_at.replace("Z", "+00:00")
        )
    except (AttributeError, ValueError) as exc:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DELETE_TIMESTAMP_INVALID",
            "deleted_at must be an ISO-8601 timestamp.",
        ) from exc
    if parsed_deleted_at.tzinfo is None:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DELETE_TIMESTAMP_INVALID",
            "deleted_at must include a timezone.",
        )
    candidate_digest = _candidate_tree_digest(root)
    tombstone = {
        "schema_version": CANDIDATE_TOMBSTONE_VERSION,
        "candidate_id": candidate_id,
        "expertise_pack_id": candidate["expertise_pack_id"],
        "candidate_digest": candidate_digest,
        "deleted_at": resolved_deleted_at,
        "reason": disposition["reason"],
        "replacement_pack_ids": replacements,
        "component_change": _candidate_component_change(candidate),
    }
    operations: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            raise MaestroError(
                "EXPERTISE_CANDIDATE_SYMLINK_UNSAFE",
                f"Candidate contains a symlink: {path.relative_to(root)}",
            )
        if path.is_file():
            operations.append(
                _delete_operation(
                    repo,
                    path.relative_to(repo).as_posix(),
                )
            )
    tombstone_path = f"{CANDIDATE_TOMBSTONE_ROOT}/{candidate_id}.json"
    operations.append(
        _text_operation(
            repo,
            tombstone_path,
            pretty_json(tombstone),
            require_missing=True,
        )
    )
    return _finalize_plan(
        {
            "schema_version": DELETE_PLAN_VERSION,
            "command": "expertise-delete-candidate",
            "repo_realpath": str(repo),
            "candidate_id": candidate_id,
            "candidate_digest": candidate_digest,
            "confirmation": confirmation,
            "replacement_pack_ids": replacements,
            "deleted_at": resolved_deleted_at,
            "operations": operations,
            "warnings": [
                "Permanent removal deletes the archived working candidate files.",
                "A compact tombstone remains so the deleted identity and replacement mapping cannot be silently reused.",
                "This operation does not delete an active project Pack, global Pack source, commit, or release.",
            ],
            "writes_performed": False,
        }
    )


def build_expertise_delete_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
    confirmation: str,
    replacement_pack_ids: list[str] | None = None,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    _require_individual_candidate_action(
        repo,
        candidate_id=candidate_id,
    )
    return _build_expertise_delete_member_plan(
        repo,
        candidate_id=candidate_id,
        confirmation=confirmation,
        replacement_pack_ids=replacement_pack_ids,
        deleted_at=deleted_at,
    )


def _merge_change_set_operations(
    member_plans: list[dict[str, Any]],
    *,
    extra_operations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    operations = [
        copy.deepcopy(operation)
        for plan in member_plans
        for operation in plan["operations"]
        if operation["path"] != ".maestro/project.json"
    ]
    operations.extend(copy.deepcopy(extra_operations or []))
    paths = [operation["path"] for operation in operations]
    if len(paths) != len(set(paths)):
        duplicates = sorted(
            {
                path
                for path in paths
                if paths.count(path) > 1
            }
        )
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_PATH_CONFLICT",
            "ChangeSet members target the same path: "
            + ", ".join(duplicates),
        )
    return sorted(operations, key=lambda item: item["path"])


def build_expertise_change_set_plan(
    repo_path: str | Path,
    *,
    change_set_id: str,
    action: str,
    approval_ref: str | None = None,
    reason: str | None = None,
    confirmation: str | None = None,
    replacement_pack_ids: list[str] | None = None,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    """Build one digest-bound transaction for an atomic Expertise ChangeSet."""

    repo = ensure_repo(repo_path)
    context = require_change_set(
        repo,
        change_set_id=change_set_id,
    )
    candidate_ids = context["candidate_ids"]
    replacements = list(replacement_pack_ids or [])
    resolved_approval_ref: str | None = None
    resolved_reason: str | None = None
    resolved_confirmation: str | None = None
    resolved_deleted_at: str | None = None
    member_plans: list[dict[str, Any]]
    extra_operations: list[dict[str, Any]] = []

    if action == "project-approve":
        if not isinstance(approval_ref, str):
            raise MaestroError(
                "EXPERTISE_CHANGE_SET_APPROVAL_REQUIRED",
                "Project approval requires approval_ref.",
            )
        _validate_approval_ref(approval_ref)
        resolved_approval_ref = approval_ref
        _, project, active_pack_paths = _project_expertise_configuration(repo)
        activated_pack_paths: list[str] = []
        member_plans = []
        for candidate_id in candidate_ids:
            _, _, pack = _fresh_candidate_pack(repo, candidate_id)
            pack_path = (
                f".agents/skills/{pack['skill_id']}/"
                f"{PROJECT_PACK_FILENAME}"
            )
            if pack_path in active_pack_paths:
                member_plan = _build_expertise_update_member_plan(
                    repo,
                    candidate_id=candidate_id,
                    approval_ref=approval_ref,
                )
            else:
                member_plan = _build_expertise_activation_member_plan(
                    repo,
                    candidate_id=candidate_id,
                    approval_ref=approval_ref,
                )
                activated_pack_paths.append(pack_path)
            member_plans.append(member_plan)
        if activated_pack_paths:
            if len(activated_pack_paths) != len(set(activated_pack_paths)):
                raise MaestroError(
                    "EXPERTISE_CHANGE_SET_PATH_CONFLICT",
                    "Multiple ChangeSet members publish the same project Skill.",
                )
            updated_project = copy.deepcopy(project)
            updated_project["expertise"] = {
                "active_pack_paths": [
                    *active_pack_paths,
                    *activated_pack_paths,
                ]
            }
            extra_operations.append(
                _text_operation(
                    repo,
                    ".maestro/project.json",
                    pretty_json(updated_project),
                )
            )
    elif action == "archive":
        if not isinstance(reason, str):
            raise MaestroError(
                "EXPERTISE_CHANGE_SET_REASON_REQUIRED",
                "Archive requires one reason.",
            )
        resolved_reason = _validate_candidate_disposition_reason(reason)
        member_plans = [
            _build_expertise_archive_member_plan(
                repo,
                candidate_id=candidate_id,
                reason=resolved_reason,
            )
            for candidate_id in candidate_ids
        ]
    elif action == "restore":
        member_plans = [
            _build_expertise_restore_member_plan(
                repo,
                candidate_id=candidate_id,
            )
            for candidate_id in candidate_ids
        ]
    elif action == "delete":
        if confirmation != change_set_id:
            raise MaestroError(
                "EXPERTISE_CHANGE_SET_DELETE_CONFIRMATION_INVALID",
                "Permanent removal requires the exact ChangeSet ID.",
            )
        resolved_confirmation = confirmation
        resolved_deleted_at = deleted_at or (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        member_plans = [
            _build_expertise_delete_member_plan(
                repo,
                candidate_id=candidate_id,
                confirmation=candidate_id,
                replacement_pack_ids=replacements,
                deleted_at=resolved_deleted_at,
            )
            for candidate_id in candidate_ids
        ]
    else:
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_ACTION_INVALID",
            (
                "action must be project-approve, archive, restore, or delete."
            ),
        )

    operations = _merge_change_set_operations(
        member_plans,
        extra_operations=extra_operations,
    )
    return _finalize_plan(
        {
            "schema_version": CHANGE_SET_PLAN_VERSION,
            "command": "expertise-change-set",
            "repo_realpath": str(repo),
            "change_set_id": change_set_id,
            "action": action,
            "candidate_ids": candidate_ids,
            "approval_ref": resolved_approval_ref,
            "reason": resolved_reason,
            "confirmation": resolved_confirmation,
            "replacement_pack_ids": replacements,
            "deleted_at": resolved_deleted_at,
            "member_plan_digests": [
                {
                    "candidate_id": plan["candidate_id"],
                    "command": plan["command"],
                    "plan_digest": plan["plan_digest"],
                }
                for plan in member_plans
            ],
            "operations": operations,
            "warnings": [
                (
                    "Every candidate in this ChangeSet is validated and "
                    "applied as one transaction."
                ),
                (
                    "If any write or final catalog validation fails, all "
                    "file changes are restored to their previewed state."
                ),
                (
                    "The action does not commit, push, open a pull request, "
                    "or perform a global Harness promotion."
                ),
            ],
            "writes_performed": False,
        }
    )


def _read_publication_plan(
    plan_path: dict[str, Any] | str | Path,
    *,
    schema_version: str,
    command: str,
    allowed_fields: set[str],
    label: str,
) -> dict[str, Any]:
    plan = (
        copy.deepcopy(plan_path)
        if isinstance(plan_path, dict)
        else read_json(Path(plan_path).expanduser().resolve())
    )
    if (
        set(plan) != allowed_fields
        or plan.get("schema_version") != schema_version
        or plan.get("command") != command
        or plan.get("writes_performed") is not False
    ):
        raise MaestroError(
            f"EXPERTISE_{label}_PLAN_INVALID",
            f"Unsupported Expertise {label.casefold()} plan.",
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
            f"EXPERTISE_{label}_PLAN_TAMPERED",
            f"{label.title()} plan digest does not match its contents.",
            exit_code=3,
        )
    return plan


def _publication_repo(
    plan: dict[str, Any],
    *,
    repo_override: str | Path | None,
    label: str,
) -> Path:
    repo = ensure_repo(repo_override or plan["repo_realpath"])
    if str(repo) != plan["repo_realpath"]:
        raise MaestroError(
            f"EXPERTISE_{label}_REPO_MISMATCH",
            f"{label.title()} plan belongs to a different repository.",
            exit_code=3,
        )
    return repo


def _operation_originals(
    repo: Path,
    operations: Any,
    *,
    allow_delete: bool,
    project_only: bool,
    candidate_state_only: bool = False,
    candidate_tree_only: bool = False,
    candidate_id: str | None = None,
    candidate_ids: list[str] | None = None,
    harness_source_only: bool = False,
    label: str,
) -> dict[Path, bytes | None]:
    if not isinstance(operations, list) or not operations:
        raise MaestroError(
            f"EXPERTISE_{label}_PLAN_INVALID",
            f"{label.title()} operations must be a non-empty list.",
            exit_code=3,
        )

    originals: dict[Path, bytes | None] = {}
    seen_paths: set[str] = set()
    allowed_operations = (
        {"create", "replace", "delete"}
        if allow_delete
        else {"create", "replace"}
    )
    for operation in operations:
        if (
            not isinstance(operation, dict)
            or set(operation)
            != {"op", "path", "before_sha256", "after_sha256", "content"}
            or operation.get("op") not in allowed_operations
            or not isinstance(operation.get("path"), str)
        ):
            raise MaestroError(
                f"EXPERTISE_{label}_PLAN_INVALID",
                f"{label.title()} operation is invalid.",
                exit_code=3,
            )
        path = operation["path"]
        if path in seen_paths:
            raise MaestroError(
                f"EXPERTISE_{label}_PLAN_INVALID",
                f"{label.title()} plan contains a duplicate path: {path}",
                exit_code=3,
            )
        seen_paths.add(path)
        if harness_source_only:
            path_allowed = (
                path == ".maestro/lock.json"
                or path == ".maestro/project.json"
                or
                (
                    path.startswith(
                        "src/maestro/resources/registry/"
                        "expertise-packs/"
                    )
                    and path.endswith(".json")
                )
                or
                (
                    path.startswith(
                        "src/maestro/resources/expertise-sources/"
                    )
                    and path.endswith(".json")
                )
                or path.startswith("skills/maestro-")
            )
        elif candidate_tree_only:
            allowed_candidate_ids = (
                candidate_ids
                if isinstance(candidate_ids, list)
                else [candidate_id]
            )
            path_allowed = any(
                isinstance(item, str)
                and (
                    path.startswith(
                        ".maestro/state/candidates/expertise/"
                        f"{item}/"
                    )
                    or path
                    == f"{CANDIDATE_TOMBSTONE_ROOT}/{item}.json"
                )
                for item in allowed_candidate_ids
            )
        elif candidate_state_only:
            path_allowed = (
                path.startswith(
                    ".maestro/state/candidates/expertise/"
                )
                and path.endswith(
                    f"/{CANDIDATE_DISPOSITION_FILENAME}"
                )
            )
        elif project_only:
            path_allowed = path == ".maestro/project.json"
        else:
            path_allowed = (
                path == ".maestro/project.json"
                or path.startswith(".agents/skills/")
            )
        if not path_allowed:
            raise MaestroError(
                f"EXPERTISE_{label}_PATH_INVALID",
                f"{label.title()} may not change this path: {path}",
                exit_code=3,
            )
        target = safe_target(repo, path)
        if file_sha256(target) != operation["before_sha256"]:
            raise MaestroError(
                f"EXPERTISE_{label}_PLAN_STALE",
                f"File changed after preview: {path}",
                exit_code=3,
            )

        if operation["op"] == "delete":
            if (
                operation.get("content") is not None
                or operation.get("after_sha256") is not None
                or operation.get("before_sha256") is None
            ):
                raise MaestroError(
                    f"EXPERTISE_{label}_PLAN_INVALID",
                    f"Delete operation is invalid: {path}",
                    exit_code=3,
                )
        else:
            if not isinstance(operation.get("content"), str):
                raise MaestroError(
                    f"EXPERTISE_{label}_PLAN_INVALID",
                    f"Text operation is invalid: {path}",
                    exit_code=3,
                )
            content = operation["content"].encode("utf-8")
            if sha256_bytes(content) != operation["after_sha256"]:
                raise MaestroError(
                    f"EXPERTISE_{label}_PLAN_TAMPERED",
                    f"Content hash mismatch: {path}",
                    exit_code=3,
                )
        originals[target] = target.read_bytes() if target.exists() else None
    return originals


def _apply_publication_operations(
    repo: Path,
    operations: list[dict[str, Any]],
    originals: dict[Path, bytes | None],
    *,
    validate_catalog: bool = True,
) -> None:
    created_directories: set[Path] = set()
    for operation in operations:
        if operation["op"] == "delete":
            continue
        parent = safe_target(repo, operation["path"]).parent
        while parent != repo and not parent.exists():
            created_directories.add(parent)
            parent = parent.parent
    try:
        for operation in operations:
            target = safe_target(repo, operation["path"])
            if operation["op"] == "delete":
                target.unlink()
            else:
                atomic_write(target, operation["content"].encode("utf-8"))
        if validate_catalog:
            load_expertise_catalog(repo)
    except BaseException:
        for target, content in reversed(list(originals.items())):
            if content is None:
                if target.exists() and target.is_file():
                    target.unlink()
            else:
                atomic_write(target, content)
        for directory in sorted(
            created_directories,
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        raise


def _published_skill_root(plan: dict[str, Any]) -> str:
    pack_paths = [
        operation["path"]
        for operation in plan["operations"]
        if operation["op"] != "delete"
        and Path(operation["path"]).name == PROJECT_PACK_FILENAME
    ]
    if len(pack_paths) != 1:
        raise MaestroError(
            "EXPERTISE_PUBLICATION_PLAN_INVALID",
            "Publication plan must contain exactly one Expertise Pack file.",
            exit_code=3,
        )
    return Path(pack_paths[0]).parent.as_posix()


def apply_expertise_change_set_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=CHANGE_SET_PLAN_VERSION,
        command="expertise-change-set",
        allowed_fields=CHANGE_SET_PLAN_FIELDS,
        label="CHANGE_SET",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="CHANGE_SET",
    )
    fresh = build_expertise_change_set_plan(
        repo,
        change_set_id=plan["change_set_id"],
        action=plan["action"],
        approval_ref=plan["approval_ref"],
        reason=plan["reason"],
        confirmation=plan["confirmation"],
        replacement_pack_ids=plan["replacement_pack_ids"],
        deleted_at=plan["deleted_at"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_CHANGE_SET_PLAN_STALE",
            (
                "A ChangeSet member, project destination, disposition, or "
                "confirmation changed after preview."
            ),
            exit_code=3,
        )

    action = plan["action"]
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=action in {"project-approve", "restore", "delete"},
        project_only=False,
        candidate_state_only=action in {"archive", "restore"},
        candidate_tree_only=action == "delete",
        candidate_ids=plan["candidate_ids"],
        label="CHANGE_SET",
    )
    _apply_publication_operations(
        repo,
        plan["operations"],
        originals,
        validate_catalog=action != "delete",
    )
    if action == "delete":
        for candidate_id in plan["candidate_ids"]:
            root = _candidate_root(repo, candidate_id)
            if not root.exists():
                continue
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_dir():
                    path.rmdir()
            root.rmdir()

    result_status = {
        "project-approve": "project_approved",
        "archive": "archived",
        "restore": "restored",
        "delete": "deleted",
    }[action]
    skill_roots = sorted(
        {
            Path(operation["path"]).parent.as_posix()
            for operation in plan["operations"]
            if Path(operation["path"]).name == PROJECT_PACK_FILENAME
            and operation["path"].startswith(".agents/skills/")
        }
    )
    git_stage_paths = [
        *(
            [".maestro/project.json"]
            if any(
                operation["path"] == ".maestro/project.json"
                for operation in plan["operations"]
            )
            else []
        ),
        *skill_roots,
    ]
    return {
        "schema_version": "maestro_expertise_change_set_result_v1",
        "status": result_status,
        "repo_root": str(repo),
        "change_set_id": plan["change_set_id"],
        "action": action,
        "candidate_ids": plan["candidate_ids"],
        "changed_paths": [
            operation["path"] for operation in plan["operations"]
        ],
        "git_stage_paths": git_stage_paths,
        "candidate_recoverable": action != "delete",
        "writes_performed": True,
    }


def apply_expertise_activation_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=ACTIVATION_PLAN_VERSION,
        command="expertise-activate",
        allowed_fields=PUBLICATION_PLAN_FIELDS,
        label="ACTIVATION",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="ACTIVATION",
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

    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=False,
        project_only=False,
        label="ACTIVATION",
    )
    skill_root = _published_skill_root(plan)
    _apply_publication_operations(repo, plan["operations"], originals)

    return {
        "schema_version": "maestro_expertise_activation_result_v1",
        "status": "applied",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "changed_paths": [
            operation["path"] for operation in plan["operations"]
        ],
        "git_stage_paths": [
            ".maestro/project.json",
            skill_root,
        ],
        "candidate_retained": True,
        "writes_performed": True,
    }


def apply_expertise_update_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=UPDATE_PLAN_VERSION,
        command="expertise-update",
        allowed_fields=PUBLICATION_PLAN_FIELDS,
        label="UPDATE",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="UPDATE",
    )
    fresh = build_expertise_update_plan(
        repo,
        candidate_id=plan["candidate_id"],
        approval_ref=plan["approval_ref"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_UPDATE_PLAN_STALE",
            "Candidate or active project Expertise changed after preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=True,
        project_only=False,
        label="UPDATE",
    )
    skill_root = _published_skill_root(plan)
    _apply_publication_operations(repo, plan["operations"], originals)
    pack_path = f"{skill_root}/{PROJECT_PACK_FILENAME}"
    catalog = load_expertise_catalog(repo)
    updated = next(
        pack
        for pack in catalog
        if pack["_maestro"]["origin"] == "project"
        and pack["_maestro"]["pack_path"] == pack_path
    )
    return {
        "schema_version": "maestro_expertise_update_result_v1",
        "status": "applied",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "expertise_pack_id": updated["expertise_pack_id"],
        "version": updated["version"],
        "changed_paths": [
            operation["path"] for operation in plan["operations"]
        ],
        "git_stage_paths": [
            skill_root,
        ],
        "candidate_retained": True,
        "writes_performed": True,
    }


def apply_expertise_deactivation_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    allowed_fields = {
        "schema_version",
        "command",
        "repo_realpath",
        "expertise_pack_id",
        "pack_path",
        "definition_digest",
        "operations",
        "warnings",
        "writes_performed",
        "plan_id",
        "plan_digest",
    }
    plan = _read_publication_plan(
        plan_path,
        schema_version=DEACTIVATION_PLAN_VERSION,
        command="expertise-deactivate",
        allowed_fields=allowed_fields,
        label="DEACTIVATION",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="DEACTIVATION",
    )
    fresh = build_expertise_deactivation_plan(
        repo,
        expertise_pack_id=plan["expertise_pack_id"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_DEACTIVATION_PLAN_STALE",
            "Active project Expertise or project configuration changed after preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=False,
        project_only=True,
        label="DEACTIVATION",
    )
    _apply_publication_operations(repo, plan["operations"], originals)
    return {
        "schema_version": "maestro_expertise_deactivation_result_v1",
        "status": "applied",
        "repo_root": str(repo),
        "expertise_pack_id": plan["expertise_pack_id"],
        "preserved_pack_path": plan["pack_path"],
        "changed_paths": [".maestro/project.json"],
        "git_stage_paths": [".maestro/project.json"],
        "writes_performed": True,
    }


def apply_expertise_rejection_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=REJECTION_PLAN_VERSION,
        command="expertise-reject-candidate",
        allowed_fields=CANDIDATE_DISPOSITION_PLAN_FIELDS,
        label="CANDIDATE_REJECTION",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="CANDIDATE_REJECTION",
    )
    fresh = build_expertise_rejection_plan(
        repo,
        candidate_id=plan["candidate_id"],
        reason=plan["reason"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_REJECTION_PLAN_STALE",
            "Candidate changed after rejection preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=False,
        project_only=False,
        candidate_state_only=True,
        label="CANDIDATE_REJECTION",
    )
    _apply_publication_operations(repo, plan["operations"], originals)
    return {
        "schema_version": "maestro_expertise_rejection_result_v1",
        "status": "rejected",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "runtime_status": "rejected",
        "reason": plan["reason"],
        "candidate_retained": True,
        "writes_performed": True,
    }


def apply_expertise_archive_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=ARCHIVE_PLAN_VERSION,
        command="expertise-archive-candidate",
        allowed_fields=CANDIDATE_DISPOSITION_PLAN_FIELDS,
        label="CANDIDATE_ARCHIVE",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="CANDIDATE_ARCHIVE",
    )
    fresh = build_expertise_archive_plan(
        repo,
        candidate_id=plan["candidate_id"],
        reason=plan["reason"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_ARCHIVE_PLAN_STALE",
            "Candidate changed after archive preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=False,
        project_only=False,
        candidate_state_only=True,
        label="CANDIDATE_ARCHIVE",
    )
    _apply_publication_operations(repo, plan["operations"], originals)
    return {
        "schema_version": "maestro_expertise_archive_result_v1",
        "status": "archived",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "runtime_status": "archived",
        "reason": plan["reason"],
        "candidate_retained": True,
        "writes_performed": True,
    }


def apply_expertise_restore_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=RESTORE_PLAN_VERSION,
        command="expertise-restore-candidate",
        allowed_fields=CANDIDATE_DISPOSITION_PLAN_FIELDS,
        label="CANDIDATE_RESTORE",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="CANDIDATE_RESTORE",
    )
    fresh = build_expertise_restore_plan(
        repo,
        candidate_id=plan["candidate_id"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_RESTORE_PLAN_STALE",
            "Candidate or rejection marker changed after restore preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=True,
        project_only=False,
        candidate_state_only=True,
        label="CANDIDATE_RESTORE",
    )
    _apply_publication_operations(repo, plan["operations"], originals)
    runtime_status = candidate_expertise_statuses(repo).get(
        plan["candidate_id"],
        {},
    )
    return {
        "schema_version": "maestro_expertise_restore_result_v1",
        "status": "restored",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "runtime_status": runtime_status.get(
            "runtime_status",
            "invalid",
        ),
        "immediate_use_allowed": runtime_status.get(
            "immediate_use_allowed",
            False,
        ),
        "writes_performed": True,
    }


def apply_expertise_delete_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=DELETE_PLAN_VERSION,
        command="expertise-delete-candidate",
        allowed_fields=DELETE_PLAN_FIELDS,
        label="CANDIDATE_DELETE",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="CANDIDATE_DELETE",
    )
    fresh = build_expertise_delete_plan(
        repo,
        candidate_id=plan["candidate_id"],
        confirmation=plan["confirmation"],
        replacement_pack_ids=plan["replacement_pack_ids"],
        deleted_at=plan["deleted_at"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_CANDIDATE_DELETE_PLAN_STALE",
            "Archived candidate changed after permanent-removal preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=True,
        project_only=False,
        candidate_tree_only=True,
        candidate_id=plan["candidate_id"],
        label="CANDIDATE_DELETE",
    )
    _apply_publication_operations(
        repo,
        plan["operations"],
        originals,
        validate_catalog=False,
    )
    root = _candidate_root(repo, plan["candidate_id"])
    if root.exists():
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        root.rmdir()
    return {
        "schema_version": "maestro_expertise_delete_result_v1",
        "status": "deleted",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "tombstone_path": (
            f"{CANDIDATE_TOMBSTONE_ROOT}/"
            f"{plan['candidate_id']}.json"
        ),
        "replacement_pack_ids": plan["replacement_pack_ids"],
        "candidate_recoverable": False,
        "writes_performed": True,
    }


def apply_expertise_global_promotion_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    plan = _read_publication_plan(
        plan_path,
        schema_version=GLOBAL_PROMOTION_PLAN_VERSION,
        command="expertise-promote-global",
        allowed_fields=GLOBAL_PROMOTION_PLAN_FIELDS,
        label="GLOBAL_PROMOTION",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="GLOBAL_PROMOTION",
    )
    if plan["source_kind"] == "project_publication":
        fresh = build_expertise_global_promotion_plan(
            repo,
            expertise_pack_id=plan["expertise_pack_id"],
            approval_ref=plan["approval_ref"],
            promotion_source_kind="project_publication",
        )
    elif plan["source_kind"] in {
        "candidate_contribution",
        "candidate_snapshot",
    }:
        fresh = build_expertise_global_promotion_plan(
            repo,
            candidate_id=plan["candidate_id"],
            approval_ref=plan["approval_ref"],
            promotion_source_kind="candidate_snapshot",
        )
    else:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_PLAN_INVALID",
            "Global promotion plan source kind is invalid.",
            exit_code=3,
        )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_PLAN_STALE",
            "Contribution, Harness source, or release manifest changed after preview.",
            exit_code=3,
        )
    originals = _operation_originals(
        repo,
        plan["operations"],
        allow_delete=False,
        project_only=False,
        harness_source_only=True,
        label="GLOBAL_PROMOTION",
    )
    manifest_path = release_manifest_path(repo)
    manifest_before = (
        manifest_path.read_bytes()
        if manifest_path.exists()
        else None
    )
    if file_sha256(manifest_path) != plan[
        "release_manifest_before_sha256"
    ]:
        raise MaestroError(
            "EXPERTISE_GLOBAL_PROMOTION_PLAN_STALE",
            "Release manifest changed after preview.",
            exit_code=3,
        )
    try:
        _apply_publication_operations(
            repo,
            plan["operations"],
            originals,
            validate_catalog=False,
        )
        registry_errors = validate_registry(load_source_registry(repo))
        if registry_errors:
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_REGISTRY_INVALID",
                "; ".join(registry_errors),
                exit_code=3,
            )
        release_manifest = build_release_manifest(repo)
        atomic_write(
            manifest_path,
            pretty_json(release_manifest).encode("utf-8"),
        )
        load_source_release_manifest(repo)
        validate_project_expertise_against_registry(
            repo,
            load_source_registry(repo),
        )
        if plan["source_kind"] == "project_publication":
            source = _project_promotion_source(
                repo,
                expertise_pack_id=plan["expertise_pack_id"],
            )
        else:
            candidate_root, candidate = _read_candidate(
                repo,
                plan["candidate_id"],
            )
            pack = read_json(
                safe_target(
                    candidate_root,
                    f"draft/{PROJECT_PACK_FILENAME}",
                )
            )
            source = _candidate_promotion_source(
                repo,
                candidate_root=candidate_root,
                candidate=candidate,
                pack=pack,
            )
        adoption = _global_adoption_status(
            repo,
            source=source,
        )
        if adoption["status"] != "harness_source_applied":
            raise MaestroError(
                "EXPERTISE_GLOBAL_PROMOTION_VERIFICATION_FAILED",
                "Harness source does not match the promoted contribution.",
                exit_code=3,
            )
    except BaseException:
        for target, content in reversed(list(originals.items())):
            if content is None:
                if target.exists() and target.is_file():
                    target.unlink()
            else:
                atomic_write(target, content)
        if manifest_before is None:
            manifest_path.unlink(missing_ok=True)
        else:
            atomic_write(manifest_path, manifest_before)
        skill_root = safe_target(repo, f"skills/{plan['skill_id']}")
        skill_directories = sorted(
            {
                target.parent
                for target, content in originals.items()
                if content is None and target.is_relative_to(skill_root)
            },
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in (*skill_directories, skill_root):
            if directory.is_dir():
                try:
                    directory.rmdir()
                except OSError:
                    pass
        raise

    changed_paths = [
        operation["path"] for operation in plan["operations"]
    ]
    changed_paths.append(
        manifest_path.relative_to(repo).as_posix()
    )
    return {
        "schema_version": "maestro_expertise_global_promotion_result_v1",
        "status": "harness_source_applied",
        "repo_root": str(repo),
        "candidate_id": plan["candidate_id"],
        "expertise_pack_id": plan["expertise_pack_id"],
        "skill_id": plan["skill_id"],
        "source_kind": plan["source_kind"],
        "source_ref": plan["source_ref"],
        "bundle_path": plan["bundle_path"],
        "bundle_digest": plan["bundle_digest"],
        "release_id": release_manifest["release_id"],
        "changed_paths": changed_paths,
        "git_stage_paths": [
            (
                "src/maestro/resources/registry/expertise-packs/"
                f"{plan['expertise_pack_id']}.json"
            ),
            *(
                [
                    "src/maestro/resources/expertise-sources/"
                    f"{plan['expertise_pack_id']}.json"
                ]
                if any(
                    operation["path"]
                    == (
                        "src/maestro/resources/expertise-sources/"
                        f"{plan['expertise_pack_id']}.json"
                    )
                    for operation in plan["operations"]
                )
                else []
            ),
            f"skills/{plan['skill_id']}",
            "src/maestro/resources/release-manifest.json",
            *(
                [".maestro/project.json"]
                if any(
                    operation["path"] == ".maestro/project.json"
                    for operation in plan["operations"]
                )
                else []
            ),
            *(
                [".maestro/lock.json"]
                if any(
                    operation["path"] == ".maestro/lock.json"
                    for operation in plan["operations"]
                )
                else []
            ),
        ],
        "commit_performed": False,
        "push_performed": False,
        "pull_request_performed": False,
        "release_performed": False,
        "writes_performed": True,
    }


def apply_expertise_export_plan(
    plan_path: dict[str, Any] | str | Path,
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    allowed_fields = {
        "schema_version",
        "command",
        "repo_realpath",
        "candidate_id",
        "candidate_digest",
        "output_path",
        "output_before_sha256",
        "output_after_sha256",
        "content",
        "warnings",
        "writes_performed",
        "plan_id",
        "plan_digest",
    }
    plan = _read_publication_plan(
        plan_path,
        schema_version=EXPORT_PLAN_VERSION,
        command="expertise-export",
        allowed_fields=allowed_fields,
        label="EXPORT",
    )
    repo = _publication_repo(
        plan,
        repo_override=repo_override,
        label="EXPORT",
    )
    fresh = build_expertise_export_plan(
        repo,
        candidate_id=plan["candidate_id"],
    )
    if fresh != plan:
        raise MaestroError(
            "EXPERTISE_EXPORT_PLAN_STALE",
            "Candidate or existing export changed after preview.",
            exit_code=3,
        )
    output_path = plan["output_path"]
    if (
        not isinstance(output_path, str)
        or not output_path.startswith(".maestro/exports/expertise/")
        or not output_path.endswith(".maestro-contribution.json")
    ):
        raise MaestroError(
            "EXPERTISE_EXPORT_PATH_INVALID",
            "Expertise exports must use the project-local export directory.",
            exit_code=3,
        )
    target = safe_target(repo, output_path)
    if file_sha256(target) != plan["output_before_sha256"]:
        raise MaestroError(
            "EXPERTISE_EXPORT_PLAN_STALE",
            "Existing export changed after preview.",
            exit_code=3,
        )
    content = plan.get("content")
    if (
        not isinstance(content, str)
        or sha256_text(content) != plan.get("output_after_sha256")
    ):
        raise MaestroError(
            "EXPERTISE_EXPORT_PLAN_TAMPERED",
            "Export content digest does not match the plan.",
            exit_code=3,
        )
    temporary = safe_target(
        repo,
        f"{output_path}.{plan['plan_id']}.tmp",
    )
    atomic_write(temporary, content.encode("utf-8"))
    validation = validate_expertise_contribution(temporary)
    if validation["status"] != "PASS":
        temporary.unlink(missing_ok=True)
        raise MaestroError(
            "EXPERTISE_EXPORT_INVALID",
            "Generated contribution failed validation.",
            exit_code=3,
        )
    temporary.replace(target)
    return {
        "schema_version": "maestro_expertise_export_result_v1",
        "status": "exported",
        "candidate_id": plan["candidate_id"],
        "output_path": output_path,
        "candidate_digest": plan["candidate_digest"],
        "review_bundle_status": "local_review_bundle_created",
        "promotion_performed": False,
        "install_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "pull_request_performed": False,
        "release_performed": False,
        "writes_performed": True,
    }
