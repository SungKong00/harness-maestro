from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import MaestroError
from .expertise import (
    PROJECT_PACK_FILENAME,
    expertise_manifest_digest,
    load_expertise_catalog,
)
from .project import git_ignored
from .registry import load_registry, resource_root, validate_registry
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
EXPORT_PLAN_VERSION = "maestro_expertise_export_plan_v1"
CONTRIBUTION_VERSION = "maestro_expertise_contribution_v1"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
APPROVAL_PATTERN = re.compile(
    r"^(?:owner_decision|held_out_evaluation):\S.+$"
)
MAX_CANDIDATES = 100
MAX_ACTIVATION_FILE_BYTES = 2_000_000
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
CANDIDATE_OPTIONAL_FIELDS = {"component_change"}
COMPONENT_CHANGE_FIELDS = {
    "kind",
    "target_guide_id",
}
COMPONENT_CHANGE_KINDS = {
    "new-pack",
    "guide-addition",
    "guide-revision",
    "guide-deprecation",
    "trigger-adjustment",
    "source-refresh",
    "evaluation-extension",
}
GUIDE_COMPONENT_CHANGE_KINDS = {
    "guide-addition",
    "guide-revision",
    "guide-deprecation",
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
    "pass_criteria",
    "regression_criteria",
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
            or set(component_change) != COMPONENT_CHANGE_FIELDS
            or component_change.get("kind") not in COMPONENT_CHANGE_KINDS
        ):
            return False
        target_guide_id = component_change.get("target_guide_id")
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
    evaluation = candidate.get("evaluation")
    return (
        isinstance(evaluation, dict)
        and set(evaluation) == EVALUATION_FIELDS
        and evaluation.get("baseline")
        in {"no-pack", "persona-only", "existing-pack"}
        and evaluation.get("cases_path") == "evals/cases.json"
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
        expected_by_case: dict[str, dict[str, Any]] = {}
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


def build_expertise_export_plan(
    repo_path: str | Path,
    *,
    candidate_id: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
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


def expertise_inventory(repo_path: str | Path) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    catalog = load_expertise_catalog(repo)
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
                validation = validate_expertise_candidate(repo, path.name)
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
                candidates.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "expertise_pack_id": candidate["expertise_pack_id"],
                        "owner": candidate["owner"],
                        "review_after": candidate["review_after"],
                        "ready_for_activation_review": (
                            validation["status"] == "PASS"
                            and date.fromisoformat(
                                candidate["review_after"]
                            )
                            >= date.today()
                        ),
                        "validation_status": validation["status"],
                        "validation_issue_codes": [
                            issue["code"] for issue in validation["issues"]
                        ],
                        "component_change": _candidate_component_change(
                            candidate,
                            candidate_pack,
                        ),
                        "recommended_action": (
                            "update"
                            if matching_project_pack is not None
                            else "activate"
                        ),
                    }
                )
            except MaestroError as exc:
                candidates.append(
                    {
                        "candidate_id": path.name,
                        "error": f"{exc.code}: {exc.message}",
                        "ready_for_activation_review": False,
                    }
                )
    return {
        "schema_version": "maestro_expertise_inventory_v1",
        "status": "ok",
        "repo_root": str(repo),
        "packs": entries,
        "candidates": candidates,
        "writes_performed": False,
    }


def build_expertise_activation_plan(
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


def build_expertise_update_plan(
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
        if project_only:
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
) -> None:
    try:
        for operation in operations:
            target = safe_target(repo, operation["path"])
            if operation["op"] == "delete":
                target.unlink()
            else:
                atomic_write(target, operation["content"].encode("utf-8"))
        load_expertise_catalog(repo)
    except BaseException:
        for target, content in reversed(list(originals.items())):
            if content is None:
                if target.exists() and target.is_file():
                    target.unlink()
            else:
                atomic_write(target, content)
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
        "promotion_performed": False,
        "install_performed": False,
        "writes_performed": True,
    }
