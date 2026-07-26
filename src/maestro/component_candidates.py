from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .surface_classification import RESULT_VERSION, classify_surface
from .util import canonical_json, ensure_repo, file_sha256, read_json, safe_target

CANDIDATE_VERSION = "maestro_registry_component_candidate_v1"
DEFINITION_VERSION = "maestro_registry_component_draft_v1"
EVIDENCE_VERSION = "maestro_component_evidence_v1"
EVALUATION_VERSION = "maestro_component_evaluation_v1"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COMPONENT_KINDS = {
    "lens",
    "executor-agent",
    "department",
    "adapter",
    "research-lane",
    "specialist-contract",
    "packet-contract",
}
EXPECTED_SURFACE = {kind: kind for kind in COMPONENT_KINDS}
BOUNDARY_KINDS = {
    "lens": {"failure-or-evidence"},
    "executor-agent": {"execution"},
    "department": {"route-selection"},
    "adapter": {"integration"},
    "research-lane": {"research-source"},
    "specialist-contract": {"decision-ownership"},
    "packet-contract": {"typed-handoff"},
}
REFERENCE_FIELDS = {
    "signals_ref",
    "classification_ref",
    "definition_ref",
    "evidence_ref",
    "evaluation_ref",
}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _candidate_root(repo: Path, candidate_id: str) -> Path:
    if not isinstance(candidate_id, str) or ID_PATTERN.fullmatch(candidate_id) is None:
        raise MaestroError(
            "COMPONENT_CANDIDATE_ID_INVALID",
            "candidate must be a lowercase ASCII slug.",
        )
    return safe_target(
        repo,
        f".maestro/state/candidates/components/{candidate_id}",
    )


def _nonempty_strings(
    value: Any,
    *,
    minimum: int = 1,
    maximum: int = 12,
) -> bool:
    return (
        isinstance(value, list)
        and minimum <= len(value) <= maximum
        and len(value) == len(set(value))
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _reference_valid(value: Any, expected_path: str) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"path", "sha256"}
        and value.get("path") == expected_path
        and isinstance(value.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None
    )


def _candidate_contract_valid(candidate: Any, candidate_id: str) -> bool:
    if not isinstance(candidate, dict) or set(candidate) != {
        "schema_version",
        "candidate_id",
        "component_kind",
        "status",
        "owner",
        "portability",
        "failure_pattern",
        "existing_coverage",
        "signals_ref",
        "classification_ref",
        "definition_ref",
        "evidence_ref",
        "evaluation_ref",
        "cost",
        "rollback",
        "review_after",
        "approval_requirement",
    }:
        return False
    if (
        candidate.get("schema_version") != CANDIDATE_VERSION
        or candidate.get("candidate_id") != candidate_id
        or candidate.get("component_kind") not in COMPONENT_KINDS
        or candidate.get("status") != "candidate"
        or candidate.get("portability") not in {"project", "profile", "global"}
        or not isinstance(candidate.get("owner"), str)
        or not candidate["owner"].strip()
        or not isinstance(candidate.get("failure_pattern"), str)
        or not candidate["failure_pattern"].strip()
        or not _nonempty_strings(candidate.get("existing_coverage"))
        or candidate.get("approval_requirement") != "owner_decision"
    ):
        return False
    try:
        date.fromisoformat(candidate.get("review_after", ""))
    except (TypeError, ValueError):
        return False
    expected_paths = {
        "signals_ref": "signals.json",
        "classification_ref": "classification.json",
        "definition_ref": "draft/component.json",
        "evidence_ref": "evidence/manifest.json",
        "evaluation_ref": "evals/cases.json",
    }
    if any(
        not _reference_valid(candidate[field], expected_paths[field])
        for field in REFERENCE_FIELDS
    ):
        return False
    cost = candidate.get("cost")
    rollback = candidate.get("rollback")
    return (
        isinstance(cost, dict)
        and set(cost) == {
            "additional_model_calls",
            "context_cost",
            "maintenance_owner",
        }
        and isinstance(cost.get("additional_model_calls"), int)
        and not isinstance(cost["additional_model_calls"], bool)
        and 0 <= cost["additional_model_calls"] <= 8
        and cost.get("context_cost") in {"low", "medium", "high"}
        and isinstance(cost.get("maintenance_owner"), str)
        and bool(cost["maintenance_owner"].strip())
        and isinstance(rollback, dict)
        and set(rollback) == {"strategy", "active_registry_unchanged"}
        and isinstance(rollback.get("strategy"), str)
        and bool(rollback["strategy"].strip())
        and rollback.get("active_registry_unchanged") is True
    )


def _read_referenced(
    root: Path,
    candidate: dict[str, Any],
    field: str,
) -> tuple[str, dict[str, Any]]:
    reference = candidate[field]
    path = reference["path"]
    target = safe_target(root, path)
    if target.is_symlink() or not target.is_file():
        raise MaestroError(
            "COMPONENT_CANDIDATE_FILE_MISSING",
            f"Candidate requires a regular file: {path}",
        )
    if file_sha256(target) != reference["sha256"]:
        raise MaestroError(
            "COMPONENT_CANDIDATE_DIGEST_MISMATCH",
            f"Candidate file digest does not match: {path}",
        )
    return path, read_json(target)


def _validate_classification(
    value: Any,
    candidate: dict[str, Any],
    signals: Any,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    kind = candidate["component_kind"]
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != RESULT_VERSION
        or value.get("status") != "classified"
        or value.get("proposed_surface") != EXPECTED_SURFACE[kind]
        or value.get("candidate_builder") != "maestro-registry-builder"
        or value.get("blocker") is not None
    ):
        issues.append(
            _issue(
                "COMPONENT_CLASSIFICATION_MISMATCH",
                "classification.json",
                "Classification must admit this exact component kind to maestro-registry-builder.",
            )
        )
        return issues
    try:
        expected = classify_surface(signals)
    except MaestroError as exc:
        issues.append(
            _issue(
                exc.code,
                "signals.json",
                exc.message,
            )
        )
    else:
        if canonical_json(expected) != canonical_json(value):
            issues.append(
                _issue(
                    "COMPONENT_CLASSIFICATION_NOT_REPRODUCIBLE",
                    "classification.json",
                    "Classification must exactly match deterministic recomputation from signals.json.",
                )
            )
    boundary = value.get("distinct_failure_or_decision_boundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("kind") not in BOUNDARY_KINDS[kind]
    ):
        issues.append(
            _issue(
                "COMPONENT_BOUNDARY_NOT_DISTINCT",
                "classification.json",
                f"{kind} requires a distinct {sorted(BOUNDARY_KINDS[kind])} boundary.",
            )
        )
    if kind == "lens" and boundary.get("verdict_impact") is not True:
        issues.append(
            _issue(
                "LENS_VERDICT_IMPACT_REQUIRED",
                "classification.json",
                "A Lens candidate must be able to change or block a verdict.",
            )
        )
    if kind == "executor-agent" and not boundary.get("details"):
        issues.append(
            _issue(
                "EXECUTOR_BOUNDARY_REQUIRED",
                "classification.json",
                "An Executor candidate needs at least one irreducible execution boundary.",
            )
        )
    return issues


def _validate_definition(
    value: Any,
    candidate: dict[str, Any],
) -> list[dict[str, str]]:
    if (
        not isinstance(value, dict)
        or set(value) != {
            "schema_version",
            "candidate_id",
            "component_kind",
            "component_id",
            "definition",
        }
        or value.get("schema_version") != DEFINITION_VERSION
        or value.get("candidate_id") != candidate["candidate_id"]
        or value.get("component_kind") != candidate["component_kind"]
        or not isinstance(value.get("component_id"), str)
        or ID_PATTERN.fullmatch(value["component_id"]) is None
        or not isinstance(value.get("definition"), dict)
        or not value["definition"]
    ):
        return [
            _issue(
                "COMPONENT_DEFINITION_INVALID",
                "draft/component.json",
                "Draft definition must bind the candidate, kind, component ID, and a non-empty definition.",
            )
        ]
    return []


def _validate_evidence(
    value: Any,
    candidate: dict[str, Any],
) -> tuple[list[dict[str, str]], set[str]]:
    issues: list[dict[str, str]] = []
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "candidate_id", "evidence"}
        or value.get("schema_version") != EVIDENCE_VERSION
        or value.get("candidate_id") != candidate["candidate_id"]
        or not isinstance(value.get("evidence"), list)
        or not 1 <= len(value["evidence"]) <= 20
    ):
        return (
            [
                _issue(
                    "COMPONENT_EVIDENCE_INVALID",
                    "evidence/manifest.json",
                    "Evidence manifest does not satisfy the bounded candidate contract.",
                )
            ],
            set(),
        )
    ids: list[str] = []
    for item in value["evidence"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"evidence_id", "kind", "ref", "supports"}
            or not isinstance(item.get("evidence_id"), str)
            or ID_PATTERN.fullmatch(item["evidence_id"]) is None
            or item.get("kind")
            not in {"project", "research", "incident", "evaluation"}
            or not isinstance(item.get("ref"), str)
            or not item["ref"].strip()
            or not _nonempty_strings(item.get("supports"), maximum=6)
        ):
            issues.append(
                _issue(
                    "COMPONENT_EVIDENCE_ENTRY_INVALID",
                    "evidence/manifest.json",
                    "Every evidence entry needs an ID, kind, reference, and supported claims.",
                )
            )
            continue
        ids.append(item["evidence_id"])
    if len(ids) != len(set(ids)):
        issues.append(
            _issue(
                "COMPONENT_EVIDENCE_DUPLICATE",
                "evidence/manifest.json",
                "Evidence IDs must be unique.",
            )
        )
    return issues, set(ids)


def _validate_evaluation(
    value: Any,
    candidate: dict[str, Any],
    evidence_ids: set[str],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if (
        not isinstance(value, dict)
        or set(value) != {
            "schema_version",
            "candidate_id",
            "frozen_before_evaluation",
            "cases",
            "pass_criteria",
            "regression_criteria",
        }
        or value.get("schema_version") != EVALUATION_VERSION
        or value.get("candidate_id") != candidate["candidate_id"]
        or value.get("frozen_before_evaluation") is not True
        or not _nonempty_strings(value.get("pass_criteria"), maximum=8)
        or not _nonempty_strings(value.get("regression_criteria"), maximum=8)
        or not isinstance(value.get("cases"), list)
        or not 3 <= len(value["cases"]) <= 30
    ):
        return [
            _issue(
                "COMPONENT_EVALUATION_INVALID",
                "evals/cases.json",
                "Evaluation must contain frozen bounded cases and pass/regression criteria.",
            )
        ]
    strata: set[str] = set()
    case_ids: list[str] = []
    for case in value["cases"]:
        if (
            not isinstance(case, dict)
            or set(case) != {
                "case_id",
                "stratum",
                "input",
                "expected_outcome",
                "forbidden_behaviors",
                "evidence_refs",
            }
            or not isinstance(case.get("case_id"), str)
            or ID_PATTERN.fullmatch(case["case_id"]) is None
            or case.get("stratum") not in {
                "positive",
                "non-trigger",
                "regression",
            }
            or not isinstance(case.get("input"), str)
            or not case["input"].strip()
            or not _nonempty_strings([case.get("expected_outcome")])
            or not _nonempty_strings(case.get("forbidden_behaviors"), maximum=8)
            or not _nonempty_strings(case.get("evidence_refs"), maximum=8)
            or not set(case["evidence_refs"]).issubset(evidence_ids)
        ):
            issues.append(
                _issue(
                    "COMPONENT_EVALUATION_CASE_INVALID",
                    "evals/cases.json",
                    "Every case needs a valid stratum, observable outcome, forbidden behavior, and evidence.",
                )
            )
            continue
        strata.add(case["stratum"])
        case_ids.append(case["case_id"])
    if len(case_ids) != len(set(case_ids)):
        issues.append(
            _issue(
                "COMPONENT_EVALUATION_CASE_DUPLICATE",
                "evals/cases.json",
                "Evaluation case IDs must be unique.",
            )
        )
    missing = {"positive", "non-trigger", "regression"} - strata
    if missing:
        issues.append(
            _issue(
                "COMPONENT_EVALUATION_STRATA_MISSING",
                "evals/cases.json",
                f"Evaluation is missing strata: {', '.join(sorted(missing))}.",
            )
        )
    return issues


def validate_component_candidate(
    repo_path: str | Path,
    candidate_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    try:
        root = _candidate_root(repo, candidate_id)
    except MaestroError as exc:
        return {
            "schema_version": "maestro_component_candidate_validation_v1",
            "status": "FAIL",
            "candidate_id": candidate_id,
            "issues": [_issue(exc.code, "candidate.json", exc.message)],
            "writes_performed": False,
        }
    if root.is_symlink() or not root.is_dir():
        return {
            "schema_version": "maestro_component_candidate_validation_v1",
            "status": "FAIL",
            "candidate_id": candidate_id,
            "issues": [
                _issue(
                    "COMPONENT_CANDIDATE_MISSING",
                    "candidate.json",
                    f"Component candidate is missing: {candidate_id}",
                )
            ],
            "writes_performed": False,
        }
    try:
        candidate = read_json(safe_target(root, "candidate.json"))
    except MaestroError as exc:
        candidate = None
        issues = [_issue(exc.code, "candidate.json", exc.message)]
    else:
        issues = []
    if not _candidate_contract_valid(candidate, candidate_id):
        issues.append(
            _issue(
                "COMPONENT_CANDIDATE_INVALID",
                "candidate.json",
                "Candidate metadata does not satisfy the closed component contract.",
            )
        )
        return {
            "schema_version": "maestro_component_candidate_validation_v1",
            "status": "FAIL",
            "candidate_id": candidate_id,
            "issues": issues,
            "writes_performed": False,
        }
    if date.fromisoformat(candidate["review_after"]) < date.today():
        issues.append(
            _issue(
                "COMPONENT_CANDIDATE_EXPIRED",
                "candidate.json",
                "Candidate review_after has passed; reclassify or discard it before review.",
            )
        )

    artifacts: dict[str, dict[str, Any]] = {}
    for field in sorted(REFERENCE_FIELDS):
        try:
            path, value = _read_referenced(root, candidate, field)
        except MaestroError as exc:
            issues.append(_issue(exc.code, candidate[field]["path"], exc.message))
            continue
        artifacts[path] = value
    signals = artifacts.get("signals.json")
    classification = artifacts.get("classification.json")
    definition = artifacts.get("draft/component.json")
    evidence = artifacts.get("evidence/manifest.json")
    evaluation = artifacts.get("evals/cases.json")
    if classification is not None and signals is not None:
        issues.extend(
            _validate_classification(classification, candidate, signals)
        )
    if definition is not None:
        issues.extend(_validate_definition(definition, candidate))
    evidence_ids: set[str] = set()
    if evidence is not None:
        evidence_issues, evidence_ids = _validate_evidence(evidence, candidate)
        issues.extend(evidence_issues)
    if evaluation is not None:
        issues.extend(_validate_evaluation(evaluation, candidate, evidence_ids))

    return {
        "schema_version": "maestro_component_candidate_validation_v1",
        "status": "FAIL" if issues else "PASS",
        "candidate_id": candidate_id,
        "component_kind": candidate["component_kind"],
        "candidate_path": root.relative_to(repo).as_posix(),
        "promotion_available": False,
        "issues": issues,
        "writes_performed": False,
    }
