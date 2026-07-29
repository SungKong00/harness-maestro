from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .candidate_origin import validate_component_candidate_origin
from .evaluation_attestation import observed_read_only_evaluation
from .expertise_adaptation import validate_expertise_adaptation_plan
from .surface_classification import RESULT_VERSION, classify_surface
from .util import canonical_json, ensure_repo, file_sha256, read_json, safe_target

CANDIDATE_VERSION = "maestro_registry_component_candidate_v1"
CANDIDATE_V2_VERSION = "maestro_registry_component_candidate_v2"
DEFINITION_VERSION = "maestro_registry_component_draft_v1"
EVIDENCE_VERSION = "maestro_component_evidence_v1"
EVALUATION_VERSION = "maestro_component_evaluation_v1"
EVALUATION_RESULTS_VERSION = "maestro_component_evaluation_results_v1"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
FINGERPRINT_PATTERN = re.compile(r"^[a-f0-9]{24}$")
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
V2_REFERENCE_FIELDS = REFERENCE_FIELDS | {
    "coverage_ref",
    "adaptation_ref",
    "source_route_ref",
    "source_admission_ref",
    "evaluation_result_ref",
}
BASE_CANDIDATE_FIELDS = {
    "schema_version",
    "candidate_id",
    "component_kind",
    "status",
    "owner",
    "portability",
    "failure_pattern",
    "existing_coverage",
    *REFERENCE_FIELDS,
    "cost",
    "rollback",
    "review_after",
    "approval_requirement",
}
V2_CANDIDATE_FIELDS = BASE_CANDIDATE_FIELDS | {
    "generation",
    "coverage_ref",
    "adaptation_ref",
    "source_route_ref",
    "source_admission_ref",
    "evaluation_result_ref",
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
    if (
        not isinstance(value, list)
        or not minimum <= len(value) <= maximum
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        return False
    return len(value) == len(set(value))


def _reference_valid(value: Any, expected_path: str) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"path", "sha256"}
        and value.get("path") == expected_path
        and isinstance(value.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None
    )


def _candidate_contract_valid(candidate: Any, candidate_id: str) -> bool:
    if not isinstance(candidate, dict):
        return False
    version = candidate.get("schema_version")
    expected_fields = (
        V2_CANDIDATE_FIELDS
        if version == CANDIDATE_V2_VERSION
        else BASE_CANDIDATE_FIELDS
    )
    if set(candidate) != expected_fields:
        return False
    if (
        version not in {CANDIDATE_VERSION, CANDIDATE_V2_VERSION}
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
        "coverage_ref": "evidence/task-coverage.json",
        "adaptation_ref": "evidence/adaptation-plan.json",
        "source_route_ref": "evidence/source-route.json",
        "source_admission_ref": "evidence/source-admission.json",
        "evaluation_result_ref": "evals/results.json",
    }
    reference_fields = (
        V2_REFERENCE_FIELDS
        if version == CANDIDATE_V2_VERSION
        else REFERENCE_FIELDS
    )
    if any(
        not _reference_valid(candidate[field], expected_paths[field])
        for field in reference_fields
    ):
        return False
    if version == CANDIDATE_V2_VERSION:
        generation = candidate.get("generation")
        if (
            not isinstance(generation, dict)
            or set(generation) != {
                "mode",
                "signal_fingerprint",
                "unit_id",
            }
            or generation.get("mode") != "task-gap"
            or not isinstance(generation.get("signal_fingerprint"), str)
            or FINGERPRINT_PATTERN.fullmatch(
                generation["signal_fingerprint"]
            )
            is None
            or not isinstance(generation.get("unit_id"), str)
            or ID_PATTERN.fullmatch(generation["unit_id"]) is None
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


def component_evaluation_subject(
    repo_path: str | Path,
    candidate_id: str,
) -> dict[str, Any]:
    """Return frozen definition and case refs for an external evaluator."""

    repo = ensure_repo(repo_path)
    root = _candidate_root(repo, candidate_id)
    candidate = read_json(safe_target(root, "candidate.json"))
    if not _candidate_contract_valid(candidate, candidate_id):
        raise MaestroError(
            "COMPONENT_CANDIDATE_INVALID",
            "Candidate metadata does not satisfy the closed component contract.",
        )
    definition_digest = file_sha256(
        safe_target(root, candidate["definition_ref"]["path"])
    )
    cases_digest = file_sha256(
        safe_target(root, candidate["evaluation_ref"]["path"])
    )
    if definition_digest is None or cases_digest is None:
        raise MaestroError(
            "COMPONENT_EVALUATION_SUBJECT_INVALID",
            "Definition or frozen cases are missing.",
        )
    return {
        "schema_version": "maestro_component_evaluation_subject_v1",
        "candidate_id": candidate_id,
        "definition_sha256": definition_digest,
        "cases_sha256": cases_digest,
        "evidence_refs": [
            f"component-definition:{definition_digest}",
            f"component-cases:{cases_digest}",
        ],
        "writes_performed": False,
    }


def _validate_v2_lineage(
    repo: Path,
    candidate: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    issues: list[dict[str, str]] = []
    coverage = artifacts.get("evidence/task-coverage.json")
    adaptation = artifacts.get("evidence/adaptation-plan.json")
    source_route = artifacts.get("evidence/source-route.json")
    source_admission = artifacts.get("evidence/source-admission.json")
    goal = coverage.get("goal") if isinstance(coverage, dict) else None
    if not isinstance(goal, str):
        return [
            _issue(
                "COMPONENT_ADAPTATION_LINEAGE_INVALID",
                "evidence/task-coverage.json",
                "Task-gap component candidate requires exact copied coverage.",
            )
        ], None
    validation = validate_expertise_adaptation_plan(
        adaptation,
        coverage=coverage,
        source_route=source_route,
        source_admission=source_admission,
        goal=goal,
        repo_path=repo,
        require_current_revision=False,
    )
    if validation["status"] != "PASS":
        issues.extend(validation["issues"])
        return issues, None
    matching_units = [
        unit
        for unit in adaptation["units"]
        if unit.get("unit_id") == candidate["generation"]["unit_id"]
        and unit.get("surface") == candidate["component_kind"]
        and unit.get("candidate_builder") == "maestro-registry-builder"
        and unit.get("same_task_eligible") is False
    ]
    if (
        len(matching_units) != 1
        or adaptation.get("signal_fingerprint")
        != candidate["generation"]["signal_fingerprint"]
    ):
        issues.append(
            _issue(
                "COMPONENT_ADAPTATION_UNIT_MISMATCH",
                "evidence/adaptation-plan.json",
                "Component candidate must bind exactly one matching review-only adaptation unit.",
            )
        )
    else:
        definition = artifacts.get("draft/component.json")
        component_id = (
            definition.get("component_id")
            if isinstance(definition, dict)
            else None
        )
    if (
        len(matching_units) == 1
        and not issues
        and matching_units[0].get("target_ref")
        != f"{candidate['component_kind']}:{component_id}"
    ):
        issues.append(
            _issue(
                "COMPONENT_ADAPTATION_TARGET_MISMATCH",
                "evidence/adaptation-plan.json",
                (
                    "Adaptation target must match the exact Registry "
                    "component definition identity."
                ),
            )
        )
    if issues or len(matching_units) != 1:
        return issues, None
    return issues, {
        "goal_digest": coverage.get("goal_digest"),
        "plan_id": adaptation.get("plan_id"),
        "source_admission_id": adaptation.get("source_admission_id"),
        "unit_id": matching_units[0].get("unit_id"),
        "change_set_id": matching_units[0].get("change_set_id"),
        "target_ref": matching_units[0].get("target_ref"),
    }


def _validate_evaluation_results(
    repo: Path,
    candidate: dict[str, Any],
    root: Path,
    cases: dict[str, Any],
    value: Any,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    evaluator = value.get("evaluator") if isinstance(value, dict) else None
    results = value.get("results") if isinstance(value, dict) else None
    definition_digest = file_sha256(
        safe_target(root, candidate["definition_ref"]["path"])
    )
    cases_digest = file_sha256(
        safe_target(root, candidate["evaluation_ref"]["path"])
    )
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema_version",
            "candidate_id",
            "definition_sha256",
            "cases_sha256",
            "evaluator",
            "results",
        }
        or value.get("schema_version") != EVALUATION_RESULTS_VERSION
        or value.get("candidate_id") != candidate["candidate_id"]
        or value.get("definition_sha256") != definition_digest
        or value.get("cases_sha256") != cases_digest
        or not isinstance(evaluator, dict)
        or set(evaluator)
        != {
            "kind",
            "authoring_run_ref",
            "evaluation_run_ref",
            "observation_id",
        }
        or evaluator.get("kind") not in {"fresh-context", "human"}
        or not isinstance(evaluator.get("authoring_run_ref"), str)
        or not evaluator["authoring_run_ref"].strip()
        or not isinstance(evaluator.get("evaluation_run_ref"), str)
        or not evaluator["evaluation_run_ref"].strip()
        or evaluator["authoring_run_ref"]
        == evaluator["evaluation_run_ref"]
        or not isinstance(results, list)
    ):
        return [
            _issue(
                "COMPONENT_EVALUATION_RESULTS_INVALID",
                "evals/results.json",
                "Evaluation results do not bind the exact candidate, cases, and evaluator.",
            )
        ]
    if not observed_read_only_evaluation(
        repo,
        observation_id=evaluator.get("observation_id"),
        evaluation_run_id=evaluator.get("evaluation_run_ref"),
        authoring_run_id=evaluator.get("authoring_run_ref"),
        subject_evidence_refs={
            f"component-definition:{definition_digest}",
            f"component-cases:{cases_digest}",
        },
        result_evidence_ref=(
            "component-results:"
            f"{file_sha256(safe_target(root, 'evals/results.json'))}"
        ),
        evaluator_kind=evaluator.get("kind"),
    ):
        issues.append(
            _issue(
                "COMPONENT_EVALUATION_ATTESTATION_INVALID",
                "evals/results.json.evaluator",
                "Results require a completed Host-observed read-only evaluation.",
            )
        )
    expected_cases = {
        case["case_id"]: case
        for case in cases.get("cases", [])
        if isinstance(case, dict)
        and isinstance(case.get("case_id"), str)
    }
    result_ids: set[str] = set()
    for index, result in enumerate(results):
        case_id = result.get("case_id") if isinstance(result, dict) else None
        expected = expected_cases.get(case_id)
        forbidden_results = (
            result.get("forbidden_behavior_results")
            if isinstance(result, dict)
            else None
        )
        forbidden_by_name = {
            item.get("behavior"): item
            for item in forbidden_results
            if isinstance(item, dict)
            and set(item) == {"behavior", "observed", "evidence_ref"}
            and isinstance(item.get("behavior"), str)
            and item.get("observed") is False
            and isinstance(item.get("evidence_ref"), str)
            and item["evidence_ref"].strip()
        } if isinstance(forbidden_results, list) else {}
        if (
            not isinstance(result, dict)
            or set(result)
            != {
                "case_id",
                "observed_outcome",
                "evidence_refs",
                "forbidden_behavior_results",
                "verdict",
            }
            or not isinstance(case_id, str)
            or case_id in result_ids
            or expected is None
            or result.get("observed_outcome")
            != expected.get("expected_outcome")
            or not _nonempty_strings(
                result.get("evidence_refs"),
                maximum=8,
            )
            or result.get("verdict") != "pass"
            or set(forbidden_by_name)
            != set(expected.get("forbidden_behaviors", []))
        ):
            issues.append(
                _issue(
                    "COMPONENT_EVALUATION_RESULT_CASE_INVALID",
                    f"evals/results.json.results[{index}]",
                    "Every frozen case must pass with exact forbidden-behavior evidence.",
                )
            )
            continue
        result_ids.add(case_id)
    if result_ids != set(expected_cases):
        issues.append(
            _issue(
                "COMPONENT_EVALUATION_RESULT_COVERAGE_MISSING",
                "evals/results.json",
                "Evaluation results must cover every frozen case exactly once.",
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
    if (
        isinstance(candidate, dict)
        and candidate.get("schema_version") != CANDIDATE_V2_VERSION
        and any(
            (
                target := safe_target(root, relative_path)
            ).is_file()
            and not target.is_symlink()
            for relative_path in (
                "evidence/task-coverage.json",
                "evidence/adaptation-plan.json",
                "evidence/source-route.json",
                "evidence/source-admission.json",
                "evals/results.json",
            )
        )
    ):
        issues.append(
            _issue(
                "COMPONENT_TASK_GAP_MODE_DOWNGRADE",
                "candidate.json.schema_version",
                (
                    "A component containing task-gap lineage or results "
                    "cannot be reclassified as a v1 candidate."
                ),
            )
        )
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
    reference_fields = (
        V2_REFERENCE_FIELDS
        if candidate["schema_version"] == CANDIDATE_V2_VERSION
        else REFERENCE_FIELDS
    )
    for field in sorted(reference_fields):
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
    task_gap_binding: dict[str, Any] | None = None
    if candidate["schema_version"] == CANDIDATE_V2_VERSION:
        lineage_issues, task_gap_binding = _validate_v2_lineage(
            repo,
            candidate,
            artifacts,
        )
        issues.extend(lineage_issues)
    origin_path = safe_target(
        repo,
        (
            ".maestro/state/candidate-origins/components/"
            f"{candidate_id}.json"
        ),
    )
    if (
        candidate["schema_version"] == CANDIDATE_V2_VERSION
        or origin_path.exists()
        or origin_path.is_symlink()
    ):
        issues.extend(
            validate_component_candidate_origin(
                repo,
                candidate=candidate,
                task_gap_binding=task_gap_binding,
            )
        )
    if candidate["schema_version"] == CANDIDATE_V2_VERSION:
        evaluation_results = artifacts.get("evals/results.json")
        if evaluation is not None and evaluation_results is not None:
            issues.extend(
                _validate_evaluation_results(
                    repo,
                    candidate,
                    root,
                    evaluation,
                    evaluation_results,
                )
            )

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
