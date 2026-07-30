from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.support import (
    ROOT,
    application_work_span,
    apply_fresh_init,
    check_by_id,
    write_json,
)

from maestro.doctor import doctor_report
from maestro.cli import main
from maestro.dashboard import create_dashboard_server
from maestro.decisions import build_decision_plan, validate_decision_plan
from maestro.errors import MaestroError
from maestro.candidate_origin import build_expertise_candidate_origin
from maestro.expertise import (
    candidate_expertise_statuses,
    expertise_manifest_digest,
    load_expertise_catalog,
)
from maestro.expertise_health import expertise_component_health
from maestro.expertise_lifecycle import (
    EXPERTISE_AUTHORITY_BLOCK,
    apply_expertise_activation_plan,
    apply_expertise_archive_plan,
    apply_expertise_change_set_plan,
    apply_expertise_delete_plan,
    apply_expertise_deactivation_plan,
    apply_expertise_export_plan,
    apply_expertise_global_promotion_plan,
    apply_expertise_rejection_plan,
    apply_expertise_restore_plan,
    apply_expertise_update_plan,
    build_expertise_activation_plan,
    build_expertise_archive_plan,
    build_expertise_change_set_plan,
    build_expertise_delete_plan,
    build_expertise_deactivation_plan,
    build_expertise_export_plan,
    build_expertise_global_promotion_plan,
    build_expertise_rejection_plan,
    build_expertise_restore_plan,
    build_expertise_update_plan,
    expertise_inventory,
    expertise_evaluation_subject,
    validate_expertise_contribution,
    validate_expertise_candidate,
)
from maestro.observations import (
    record_stage_observation,
    start_run_observation,
)
from maestro.expertise_promotion import (
    apply_expertise_promotion_decision_plan,
    build_expertise_promotion_decision_plan,
)
from maestro.governance import govern_report, recent_run_events, record_run
from maestro.planning import route_goal_v2, validate_route_v2
from maestro.registry import load_registry
from maestro.release import (
    build_release_manifest,
    load_source_release_manifest,
    load_source_registry,
    source_registry_digest,
)
from maestro.snapshot import snapshot_report
from maestro.util import canonical_json, file_sha256, sha256_text


def _candidate(
    repo: Path,
    *,
    candidate_id: str = "project-design",
    pack_id: str = "project-design",
    skill_id: str | None = None,
    version: int = 1,
    guide_id: str = "project-type-rules",
    guide_text: str = (
        "# Project type rules\n\n"
        "## Purpose\n\nPreserve the approved project typography.\n\n"
        "## Use when\n\nProject screens use the approved type system.\n\n"
        "## Inputs\n\nThe project design tokens and target screen.\n\n"
        "## Decision checks\n\n- Use approved families.\n- Verify hierarchy.\n\n"
        "## Required evidence\n\nRendered before and after screenshots.\n\n"
        "## Reject or stop when\n\nThe approved font assets are unavailable.\n\n"
        "## Verification\n\nInspect Hangul wrapping and computed fonts.\n\n"
        "## Counterexamples\n\nDo not apply to unrelated backend changes.\n"
    ),
    stale_base: bool = False,
    standalone: bool = False,
    portability: str = "project",
    component_change: dict[str, object] | None = None,
    generation_mode: str = "user-requested",
    signal_fingerprint: str | None = None,
    attest: bool = True,
) -> None:
    root = (
        repo
        / ".maestro/state/candidates/expertise"
        / candidate_id
    )
    base = next(
        pack
        for pack in load_registry()["expertise_packs"]
        if pack["expertise_pack_id"] == "product-design"
    )
    digest = "0" * 64 if stale_base else expertise_manifest_digest(base)
    resolved_skill_id = skill_id or pack_id
    candidate = {
        "schema_version": "maestro_expertise_candidate_v2",
        "candidate_id": candidate_id,
        "expertise_pack_id": pack_id,
        "status": "candidate",
        "portability": portability,
        "owner": "test-owner",
        "review_after": "2026-08-31",
        "problem": "Project typography rules are repeatedly omitted.",
        "reusable_when": ["Designing project screens"],
        "not_for": ["Unrelated backend work"],
        "existing_coverage": "Adds project typography to product-design.",
        "evidence_refs": ["research:project-type"],
        "proposed_guides": [
            {
                "guide_id": guide_id,
                "failure_prevented": "Wrong project font hierarchy",
                "decision_checks": ["Use approved families", "Verify hierarchy"],
                "freshness": "versioned",
            }
        ],
        "evaluation": {
            "baseline": "existing-pack",
            "cases_path": "evals/cases.json",
            "quality_path": "evals/quality.json",
            "pass_criteria": ["Catches the project font mismatch"],
            "regression_criteria": ["Does not trigger on backend work"],
        },
        "generation": {
            "mode": generation_mode,
            "signal_fingerprint": signal_fingerprint,
        },
        "coverage": {
            "decision_map_path": "evidence/decision-map.json",
            "discovery_complete": True,
            "allocation_complete": True,
        },
    }
    if component_change is not None:
        candidate["component_change"] = component_change
    pack = {
        "schema_version": "maestro_expertise_pack_v1",
        "kind": "expertise-pack",
        "expertise_pack_id": pack_id,
        "summary": "Project-specific product design criteria.",
        "status": "pilot",
        "portability": "project",
        "version": version,
        "triggers": ["project typography", "프로젝트 타이포그래피"],
        "skill_id": resolved_skill_id,
        "default_guides": [guide_id],
        "guides": [
            {
                "guide_id": guide_id,
                "summary": "Apply the project's approved font and hierarchy rules.",
                "triggers": ["project typography", "프로젝트 타이포그래피"],
                "freshness": "versioned",
            }
        ],
        "research_policy": {
            "default_mode": "reuse",
            "contextualize_triggers": ["current project font"],
            "refresh_triggers": ["refresh project typography"],
        },
        "source_manifest": "evidence/sources.json",
        "evaluation_suite": "evals/cases.json",
    }
    if not standalone:
        pack["extends"] = {
            "expertise_pack_id": "product-design",
            "version": base["version"],
            "digest": digest,
        }
    write_json(root / "candidate.json", candidate)
    write_json(root / "draft/maestro-pack.json", pack)
    (root / "draft/references").mkdir(parents=True, exist_ok=True)
    (root / "draft/agents").mkdir(parents=True, exist_ok=True)
    (root / "draft/SKILL.md").write_text(
        "---\n"
        f"name: {resolved_skill_id}\n"
        f"description: Use only when Maestro selects the {pack_id} pack.\n"
        "---\n\n"
        "# Project design\n\n"
        "Load only the selected project guide.\n\n"
        f"{EXPERTISE_AUTHORITY_BLOCK}\n",
        encoding="utf-8",
    )
    (root / f"draft/references/{guide_id}.md").write_text(
        guide_text,
        encoding="utf-8",
    )
    (root / "draft/agents/openai.yaml").write_text(
        "interface:\n"
        '  display_name: "Project design"\n'
        "policy:\n"
        "  allow_implicit_invocation: false\n",
        encoding="utf-8",
    )
    write_json(
        root / "evidence/sources.json",
        {
            "schema_version": "maestro_expertise_sources_v1",
            "expertise_pack_id": pack_id,
            "verified_on": "2026-07-27",
            "sources": [
                {
                    "source_id": "project-design-system",
                    "tier": 1,
                    "authority": "Project-owned design system",
                    "url": "https://example.invalid/project-design-system",
                    "supports": ["Approved typography and hierarchy rules"],
                    "used_by": [guide_id],
                    "freshness": "versioned",
                }
            ],
        },
    )
    write_json(
        root / "evidence/decision-map.json",
        {
            "schema_version": "maestro_expertise_decision_map_v1",
            "candidate_id": candidate_id,
            "decision_areas": [
                {
                    "area_id": "project-type-hierarchy",
                    "decision": "Choose the approved project type hierarchy.",
                    "failure_if_omitted": "The screen uses an unapproved hierarchy.",
                    "materiality": "important",
                    "evidence_types": ["external-stable"],
                    "evidence_refs": ["project-design-system"],
                    "disposition": {
                        "kind": "proposed-guide",
                        "target_id": guide_id,
                        "rationale": "The Guide owns the reusable decision.",
                    },
                }
            ],
        },
    )
    if generation_mode != "task-gap":
        write_json(
            repo
            / ".maestro/state/candidate-origins/expertise"
            / f"{candidate_id}.json",
            build_expertise_candidate_origin(
                namespace="expertise",
                candidate_id=candidate_id,
                subject_ref=f"pack:{pack_id}",
                mode=generation_mode,
                signal_fingerprint=signal_fingerprint,
                authorization_ref=(
                    f"owner_decision:test:{candidate_id}"
                    if generation_mode == "user-requested"
                    else None
                ),
            ),
        )
    evaluation_cases = [
        {
            "case_id": "normal-project-type",
            "stratum": "normal",
            "goal": "Apply our project typography to the product design",
            "expected_pack_id": pack_id,
            "expected_mode": "reuse",
            "expected_guides": [guide_id],
            "observable_criteria": ["Selects the project Pack and Guide"],
            "forbidden_behaviors": ["Falls back to generic typography only"],
        },
        {
            "case_id": "edge-korean-type",
            "stratum": "edge",
            "goal": "프로젝트 타이포그래피를 화면에 적용해줘",
            "expected_pack_id": pack_id,
            "expected_mode": "reuse",
            "expected_guides": [guide_id],
            "observable_criteria": ["Routes the Korean project phrase"],
            "forbidden_behaviors": ["Drops the project Guide"],
        },
        {
            "case_id": "non-trigger-backend",
            "stratum": "non-trigger",
            "goal": "Implement a backend formatting helper",
            "expected_pack_id": None,
            "expected_mode": "reuse",
            "expected_guides": [],
            "observable_criteria": ["Does not select the project Pack"],
            "forbidden_behaviors": ["Routes typography for backend work"],
        },
        {
            "case_id": "overlap-product-design",
            "stratum": "overlap",
            "goal": "Review product design using our project typography",
            "expected_pack_id": pack_id,
            "expected_mode": "reuse",
            "expected_guides": [guide_id],
            "observable_criteria": ["Project Pack dominates its bundled base"],
            "forbidden_behaviors": ["Selects only the bundled base Pack"],
        },
    ]
    results = {
        "schema_version": "maestro_expertise_eval_results_v1",
        "expertise_pack_id": pack_id,
        "results": [
            {
                "case_id": case["case_id"],
                "observed_pack_id": case["expected_pack_id"],
                "observed_mode": case["expected_mode"],
                "observed_guides": case["expected_guides"],
                "verdict": "pass",
            }
            for case in evaluation_cases
        ],
    }
    write_json(root / "evals/results.json", results)
    result_digest = file_sha256(root / "evals/results.json")
    assert result_digest is not None
    write_json(
        root / "evals/cases.json",
        {
            "schema_version": "maestro_expertise_eval_v2",
            "expertise_pack_id": pack_id,
            "evaluated_on": "2026-07-27",
            "evaluation_artifact": {
                "path": "evals/results.json",
                "sha256": result_digest,
            },
            "cases": evaluation_cases,
        },
    )
    quality_cases = []
    for case in evaluation_cases:
        artifact_path = f"evals/artifacts/{case['case_id']}.json"
        write_json(
            root / artifact_path,
            {
                "schema_version": "maestro_expertise_case_artifact_v1",
                "case_id": case["case_id"],
                "baseline_observation": "The current surface misses or lacks the declared project criterion.",
                "candidate_observation": "The candidate route and Guide satisfy the frozen expectation.",
                "evidence_refs": ["test:deterministic-route-replay"],
            },
        )
        artifact_digest = file_sha256(root / artifact_path)
        assert artifact_digest is not None
        quality_cases.append(
            {
                "case_id": case["case_id"],
                "artifact": {
                    "path": artifact_path,
                    "sha256": artifact_digest,
                },
                "criterion_results": [
                    {
                        "criterion": criterion,
                        "verdict": "pass",
                        "evidence_ref": artifact_path,
                    }
                    for criterion in case["observable_criteria"]
                ],
                "forbidden_behavior_results": [
                    {
                        "behavior": behavior,
                        "observed": False,
                        "evidence_ref": artifact_path,
                    }
                    for behavior in case["forbidden_behaviors"]
                ],
                "verdict": "pass",
            }
        )
    write_json(
        root / "evals/quality.json",
        {
            "schema_version": "maestro_expertise_quality_eval_v1",
            "expertise_pack_id": pack_id,
            "evaluated_on": "2026-07-27",
            "evaluator": {
                "kind": "fresh-context",
                "authoring_run_ref": f"authoring:{candidate_id}",
                "evaluation_run_ref": f"evaluation:{candidate_id}",
            },
            "cases": quality_cases,
        },
    )
    if attest and generation_mode != "task-gap":
        _attest_candidate(repo, candidate_id)


def _attest_candidate(repo: Path, candidate_id: str) -> None:
    root = (
        repo
        / ".maestro/state/candidates/expertise"
        / candidate_id
    )
    candidate = json.loads(
        (root / "candidate.json").read_text(encoding="utf-8")
    )
    evaluation = json.loads(
        (root / "evals/cases.json").read_text(encoding="utf-8")
    )
    quality_cases = []
    for case in evaluation["cases"]:
        artifact_path = f"evals/artifacts/{case['case_id']}.json"
        artifact_digest = file_sha256(root / artifact_path)
        assert artifact_digest is not None
        quality_cases.append(
            {
                "case_id": case["case_id"],
                "artifact": {
                    "path": artifact_path,
                    "sha256": artifact_digest,
                },
                "criterion_results": [
                    {
                        "criterion": criterion,
                        "verdict": "pass",
                        "evidence_ref": artifact_path,
                    }
                    for criterion in case["observable_criteria"]
                ],
                "forbidden_behavior_results": [
                    {
                        "behavior": behavior,
                        "observed": False,
                        "evidence_ref": artifact_path,
                    }
                    for behavior in case["forbidden_behaviors"]
                ],
                "verdict": "pass",
            }
        )
    subject = expertise_evaluation_subject(repo, candidate_id)
    previous_evaluation_run = ""
    quality_path = root / "evals/quality.json"
    if quality_path.is_file():
        previous_quality = json.loads(
            quality_path.read_text(encoding="utf-8")
        )
        previous_evaluator = previous_quality.get("evaluator")
        if isinstance(previous_evaluator, dict):
            previous_evaluation_run = str(
                previous_evaluator.get("evaluation_run_ref", "")
            )
    attestation_id = sha256_text(
        f"{subject['candidate_digest']}:{previous_evaluation_run}"
    )[:12]
    authoring_run = f"author-{candidate_id}-{attestation_id}"
    evaluation_run = f"evaluate-{candidate_id}-{attestation_id}"
    plan_root = repo / ".maestro/state/test-evaluation-plans"
    authoring_plan = route_goal_v2(
        f"Author candidate {candidate_id}",
        "medium",
        intent="implementation",
        repo_path=repo,
    )
    authoring_plan_path = (
        plan_root / f"{candidate_id}-{attestation_id}-author.json"
    )
    write_json(authoring_plan_path, authoring_plan)
    authored = start_run_observation(
        repo,
        run_id=authoring_run,
        request_key=authoring_run,
        task_label=f"Author {candidate_id}",
        plan_path=authoring_plan_path,
    )
    for assignment in authoring_plan["assignments"]:
        record_stage_observation(
            repo,
            observation_id=authored["observation_id"],
            run_id=authoring_run,
            assignment_id=assignment["assignment_id"],
            status="completed",
            evidence_source="deterministic_command",
            evidence_refs=(
                subject["evidence_refs"]
                if assignment["mutation_owner"]
                else [f"authoring:{assignment['assignment_id']}"]
            ),
        )
    evaluation_plan = route_goal_v2(
        f"Evaluate candidate {candidate_id}",
        "medium",
        intent="review",
        repo_path=repo,
    )
    evaluation_plan_path = (
        plan_root / f"{candidate_id}-{attestation_id}-evaluate.json"
    )
    write_json(evaluation_plan_path, evaluation_plan)
    evaluated = start_run_observation(
        repo,
        run_id=evaluation_run,
        request_key=evaluation_run,
        task_label=f"Evaluate {candidate_id}",
        plan_path=evaluation_plan_path,
    )
    write_json(
        quality_path,
        {
            "schema_version": "maestro_expertise_quality_eval_v2",
            "expertise_pack_id": candidate["expertise_pack_id"],
            "evaluated_on": "2026-07-27",
            "subject": {
                "candidate_digest": subject["candidate_digest"],
                "cases_sha256": subject["cases_sha256"],
            },
            "evaluator": {
                "kind": "fresh-context",
                "authoring_run_ref": authoring_run,
                "evaluation_run_ref": evaluation_run,
                "observation_id": evaluated["observation_id"],
            },
            "cases": quality_cases,
        },
    )
    for assignment in evaluation_plan["assignments"]:
        record_stage_observation(
            repo,
            observation_id=evaluated["observation_id"],
            run_id=evaluation_run,
            assignment_id=assignment["assignment_id"],
            status="completed",
            evidence_source="codex_app_server",
            evidence_refs=[
                *subject["evidence_refs"],
                f"candidate-quality:{file_sha256(quality_path)}",
            ],
            requested_model=assignment["model_route"]["selected_model"],
            requested_reasoning_effort=assignment["model_route"][
                "reasoning_effort"
            ],
            actual_model=assignment["model_route"]["selected_model"],
            model_evidence="complete",
            reroutes=[],
            duration_ms=1.0,
        )


def _write_user_candidate_origin(repo: Path, candidate_id: str) -> None:
    write_json(
        repo
        / ".maestro/state/candidate-origins/expertise"
        / f"{candidate_id}.json",
        build_expertise_candidate_origin(
            namespace="expertise",
            candidate_id=candidate_id,
            subject_ref=f"pack:{candidate_id.removesuffix('-v2')}",
            mode="user-requested",
            authorization_ref=f"owner_decision:test:{candidate_id}",
        ),
    )


class ProjectExpertiseLifecycleTests(unittest.TestCase):
    def test_change_set_scan_limits_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            candidate_root = (
                repo / ".maestro/state/candidates/expertise"
            )
            for index in range(101):
                candidate_id = f"overflow-{index:03d}"
                component_change = {
                    "kind": "guide-revision",
                    "target_guide_id": "shared-guide",
                }
                if index in {0, 100}:
                    component_change["change_set_id"] = "bounded-set"
                write_json(
                    candidate_root / candidate_id / "candidate.json",
                    {"component_change": component_change},
                )

            with self.assertRaises(MaestroError) as individual:
                build_expertise_archive_plan(
                    repo,
                    candidate_id="overflow-100",
                    reason="스캔 밖 후보를 개별 처리하지 않음",
                )
            self.assertEqual(
                "EXPERTISE_CHANGE_SET_ATOMIC_REQUIRED",
                individual.exception.code,
            )
            with self.assertRaises(MaestroError) as grouped:
                build_expertise_change_set_plan(
                    repo,
                    change_set_id="bounded-set",
                    action="archive",
                    reason="전체 구성원을 확인할 수 있을 때만 처리",
                )
            self.assertEqual(
                "EXPERTISE_CHANGE_SET_MEMBERSHIP_UNCERTAIN",
                grouped.exception.code,
            )

    def test_change_set_manifest_scan_limits_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            manifest_root = (
                repo
                / ".maestro/state/candidates/expertise-change-sets"
            )
            for index in range(101):
                change_set_id = f"manifest-{index:03d}"
                write_json(
                    manifest_root / f"{change_set_id}.json",
                    {
                        "schema_version": (
                            "maestro_expertise_change_set_manifest_v1"
                        ),
                        "change_set_id": change_set_id,
                        "members": [
                            {"candidate_id": f"candidate-{index:03d}"}
                        ],
                    },
                )

            with self.assertRaises(MaestroError) as raised:
                build_expertise_change_set_plan(
                    repo,
                    change_set_id="manifest-100",
                    action="archive",
                    reason="누락된 manifest를 추측하지 않음",
                )
            self.assertEqual(
                "EXPERTISE_CHANGE_SET_MEMBERSHIP_UNCERTAIN",
                raised.exception.code,
            )

    def test_atomic_change_set_is_the_only_management_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            for candidate_id, pack_id in (
                ("layout-copy", "content-layout"),
                ("layout-move", "frontend-layout"),
            ):
                _candidate(
                    repo,
                    candidate_id=candidate_id,
                    pack_id=pack_id,
                    skill_id=pack_id,
                    standalone=True,
                    component_change={
                        "kind": "new-pack",
                        "target_guide_id": None,
                        "change_set_id": "layout-redistribution",
                    },
                )

            with self.assertRaises(MaestroError) as raised:
                build_expertise_activation_plan(
                    repo,
                    candidate_id="layout-copy",
                    approval_ref="owner_decision:test:individual",
                )
            self.assertEqual(
                "EXPERTISE_CHANGE_SET_ATOMIC_REQUIRED",
                raised.exception.code,
            )
            with self.assertRaises(MaestroError):
                build_expertise_archive_plan(
                    repo,
                    candidate_id="layout-move",
                    reason="개별 우회 시도",
                )

            preview = build_expertise_change_set_plan(
                repo,
                change_set_id="layout-redistribution",
                action="project-approve",
                approval_ref="owner_decision:test:change-set",
            )
            self.assertEqual(
                1,
                sum(
                    operation["path"] == ".maestro/project.json"
                    for operation in preview["operations"]
                ),
            )
            with patch(
                "maestro.expertise_lifecycle.load_expertise_catalog",
                side_effect=MaestroError(
                    "TEST_CHANGE_SET_VALIDATION_FAILURE",
                    "force rollback",
                ),
            ):
                with self.assertRaises(MaestroError):
                    apply_expertise_change_set_plan(preview, repo)
            self.assertFalse(
                (
                    repo
                    / ".agents/skills/content-layout/maestro-pack.json"
                ).exists()
            )
            self.assertFalse(
                (
                    repo
                    / ".agents/skills/frontend-layout/maestro-pack.json"
                ).exists()
            )
            self.assertEqual(
                [],
                json.loads(
                    (repo / ".maestro/project.json").read_text(
                        encoding="utf-8"
                    )
                )["expertise"]["active_pack_paths"],
            )
            result = apply_expertise_change_set_plan(preview, repo)
            self.assertEqual("project_approved", result["status"])
            self.assertEqual(
                {"content-layout", "frontend-layout"},
                {
                    pack["expertise_pack_id"]
                    for pack in load_expertise_catalog(repo)
                    if pack["_maestro"]["origin"] == "project"
                },
            )

    def test_change_set_pauses_valid_siblings_and_deletes_as_one_unit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            for candidate_id, pack_id in (
                ("claims-copy", "content-claims"),
                ("claims-move", "product-claims"),
            ):
                _candidate(
                    repo,
                    candidate_id=candidate_id,
                    pack_id=pack_id,
                    skill_id=pack_id,
                    standalone=True,
                    component_change={
                        "kind": "new-pack",
                        "target_guide_id": None,
                        "change_set_id": "claims-redistribution",
                    },
                )
            invalid_path = (
                repo
                / ".maestro/state/candidates/expertise/"
                "claims-move/candidate.json"
            )
            invalid = json.loads(invalid_path.read_text(encoding="utf-8"))
            invalid_path.write_text("{", encoding="utf-8")
            unreadable_statuses = candidate_expertise_statuses(repo)
            self.assertEqual(
                "change_set_paused",
                unreadable_statuses["claims-copy"]["runtime_status"],
            )
            self.assertFalse(
                unreadable_statuses["claims-copy"][
                    "immediate_use_allowed"
                ],
            )
            write_json(invalid_path, invalid)
            invalid["review_after"] = "2020-01-01"
            write_json(invalid_path, invalid)
            _attest_candidate(repo, "claims-move")

            statuses = candidate_expertise_statuses(repo)
            self.assertEqual(
                "change_set_paused",
                statuses["claims-copy"]["runtime_status"],
            )
            self.assertFalse(
                statuses["claims-copy"]["immediate_use_allowed"],
            )
            self.assertEqual(
                "expired",
                statuses["claims-move"]["runtime_status"],
            )
            with self.assertRaises(MaestroError):
                build_expertise_change_set_plan(
                    repo,
                    change_set_id="claims-redistribution",
                    action="project-approve",
                    approval_ref="owner_decision:test:paused",
                )

            invalid["review_after"] = "2026-08-31"
            write_json(invalid_path, invalid)
            _attest_candidate(repo, "claims-move")
            ready_statuses = candidate_expertise_statuses(repo)
            for candidate_id in ("claims-copy", "claims-move"):
                with self.subTest(candidate_id=candidate_id):
                    self.assertEqual(
                        "available",
                        ready_statuses[candidate_id]["runtime_status"],
                    )
                    self.assertEqual(
                        "management-only",
                        ready_statuses[candidate_id]["routing_role"],
                    )
                    self.assertEqual(
                        "atomic-change-set",
                        ready_statuses[candidate_id]["routing_reason"],
                    )
                    self.assertFalse(
                        ready_statuses[candidate_id][
                            "immediate_use_allowed"
                        ],
                    )
            archive = build_expertise_change_set_plan(
                repo,
                change_set_id="claims-redistribution",
                action="archive",
                reason="변경안 전체를 보관",
            )
            apply_expertise_change_set_plan(archive, repo)
            mode_path = (
                repo
                / ".maestro/state/candidates/expertise/"
                "claims-copy/candidate.json"
            )
            mode_path.chmod(0o744)
            deletion = build_expertise_change_set_plan(
                repo,
                change_set_id="claims-redistribution",
                action="delete",
                confirmation="claims-redistribution",
                replacement_pack_ids=["marketing"],
            )
            with patch(
                (
                    "maestro.expertise_lifecycle."
                    "_remove_empty_candidate_roots"
                ),
                side_effect=OSError("forced cleanup failure"),
            ):
                with self.assertRaises(OSError):
                    apply_expertise_change_set_plan(deletion, repo)
            for candidate_id in ("claims-copy", "claims-move"):
                self.assertTrue(
                    (
                        repo
                        / ".maestro/state/candidates/expertise"
                        / candidate_id
                        / "candidate.json"
                    ).is_file()
                )
                self.assertFalse(
                    (
                        repo
                        / ".maestro/state/candidates/"
                        "expertise-tombstones"
                        / f"{candidate_id}.json"
                    ).exists()
                )
            self.assertEqual(0o744, mode_path.stat().st_mode & 0o777)
            deleted = apply_expertise_change_set_plan(deletion, repo)
            self.assertEqual("deleted", deleted["status"])
            for candidate_id in ("claims-copy", "claims-move"):
                self.assertFalse(
                    (
                        repo
                        / ".maestro/state/candidates/expertise"
                        / candidate_id
                    ).exists()
                )
                self.assertTrue(
                    (
                        repo
                        / ".maestro/state/candidates/"
                        "expertise-tombstones"
                        / f"{candidate_id}.json"
                    ).is_file()
                )

    def test_archive_restore_and_confirmed_permanent_removal_are_distinct(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)

            archive = build_expertise_archive_plan(
                repo,
                candidate_id="project-design",
                reason="후속 검토 전까지 보관",
            )
            archived = apply_expertise_archive_plan(archive, repo)
            candidate = expertise_inventory(repo)["candidates"][0]
            self.assertEqual("archived", archived["status"])
            self.assertEqual("archived", candidate["runtime_status"])
            self.assertFalse(candidate["immediate_use_allowed"])

            restore = build_expertise_restore_plan(
                repo,
                candidate_id="project-design",
            )
            apply_expertise_restore_plan(restore, repo)
            self.assertEqual(
                "available",
                expertise_inventory(repo)["candidates"][0][
                    "runtime_status"
                ],
            )

            archive = build_expertise_archive_plan(
                repo,
                candidate_id="project-design",
                reason="영구 제거 전 보관",
            )
            apply_expertise_archive_plan(archive, repo)
            with self.assertRaises(MaestroError) as raised:
                build_expertise_delete_plan(
                    repo,
                    candidate_id="project-design",
                    confirmation="wrong-id",
                )
            self.assertEqual(
                "EXPERTISE_CANDIDATE_DELETE_CONFIRMATION_INVALID",
                raised.exception.code,
            )

            deletion = build_expertise_delete_plan(
                repo,
                candidate_id="project-design",
                confirmation="project-design",
                replacement_pack_ids=["product-design"],
            )
            deleted = apply_expertise_delete_plan(deletion, repo)
            inventory = expertise_inventory(repo)
            self.assertEqual("deleted", deleted["status"])
            self.assertFalse(
                (
                    repo
                    / ".maestro/state/candidates/expertise/"
                    "project-design"
                ).exists()
            )
            self.assertEqual([], inventory["candidates"])
            self.assertEqual(
                ["product-design"],
                inventory["deleted_candidates"][0][
                    "replacement_pack_ids"
                ],
            )

    def test_automatic_candidate_is_marked_reviewed_by_component_and_reversible(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(
                repo,
                portability="global",
                generation_mode="automatic",
                signal_fingerprint="a" * 24,
                component_change={
                    "kind": "guide-addition",
                    "target_guide_id": "project-type-rules",
                },
            )
            inventory = expertise_inventory(repo)
            candidate = inventory["candidates"][0]
            digest = candidate["definition_digest"]
            events = [
                {
                    "run_id": f"candidate-use-{index}",
                    "timestamp": f"2026-07-{20 + index:02d}T00:00:00Z",
                    "selected_expertise_packs": ["project-design"],
                    "selected_decision_guides": ["project-type-rules"],
                    "expertise_pack_definition_digests": {
                        "project-design": digest,
                    },
                    "work_spans": [
                        application_work_span(
                            "project-design",
                            ["project-type-rules"],
                            work_id=f"candidate-use-{index}",
                        )
                    ],
                    "expertise_observations": [],
                    "verifier_result": "passed",
                    "correction_count": 0,
                }
                for index in range(1, 6)
            ]
            health = expertise_component_health(inventory, events)
            candidate_health = health["candidates"][0]

            self.assertEqual(
                "automatic",
                candidate["generation"]["mode"],
            )
            preview = candidate["pack_preview"]
            self.assertEqual(
                "Project-specific product design criteria.",
                preview["summary"],
            )
            self.assertEqual(
                ["Use approved families", "Verify hierarchy"],
                preview["guides"][0]["decision_checks"],
            )
            self.assertEqual(
                "Wrong project font hierarchy",
                preview["guides"][0]["failure_prevented"],
            )
            self.assertEqual(
                "project-design-system",
                preview["guides"][0]["sources"][0]["source_id"],
            )
            self.assertEqual(4, preview["evaluation"]["case_count"])
            self.assertEqual(
                4,
                preview["evaluation"]["passed_case_count"],
            )
            self.assertEqual(
                ["project-type-rules"],
                preview["evaluation"]["cases"][0]["expected_guides"],
            )
            self.assertNotIn("guide_markdown", preview)
            self.assertNotIn(
                "Rendered before and after screenshots.",
                canonical_json(preview),
            )
            self.assertEqual(5, candidate_health["component_usage_count"])
            self.assertEqual("review_due", candidate_health["utility_verdict"])
            self.assertTrue(candidate_health["review_due"])
            promotion = candidate_health["global_promotion"]
            self.assertEqual("ask_owner", promotion["status"])
            self.assertEqual(5, promotion["required_usage_count"])
            self.assertEqual(5, promotion["observed_usage_count"])
            self.assertEqual(0, promotion["remaining_usage_count"])
            self.assertTrue(promotion["request_available"])
            self.assertTrue(promotion["eligible"])
            self.assertTrue(promotion["owner_prompt_due"])
            self.assertFalse(promotion["problem_review_required"])
            self.assertFalse(promotion["automatic_promotion_allowed"])

            events[0]["expertise_observations"] = [
                {
                    "pack_id": "project-design",
                    "guide_id": "project-type-rules",
                    "kind": "unsafe_recommendation",
                    "severity": "critical",
                }
            ]
            warned_promotion = expertise_component_health(
                inventory,
                events,
            )["candidates"][0]["global_promotion"]
            self.assertEqual(
                "ask_owner",
                warned_promotion["status"],
            )
            self.assertTrue(warned_promotion["request_available"])
            self.assertTrue(warned_promotion["eligible"])
            self.assertTrue(warned_promotion["owner_prompt_due"])
            self.assertTrue(warned_promotion["problem_review_required"])

            rejection = build_expertise_rejection_plan(
                repo,
                candidate_id="project-design",
                reason="Repeated use did not improve the target outcome.",
            )
            rejected = apply_expertise_rejection_plan(rejection, repo)
            rejected_candidate = expertise_inventory(repo)["candidates"][0]
            self.assertEqual("rejected", rejected["runtime_status"])
            self.assertEqual(
                "rejected",
                rejected_candidate["runtime_status"],
            )
            self.assertFalse(
                rejected_candidate["immediate_use_allowed"]
            )
            self.assertEqual(
                "Repeated use did not improve the target outcome.",
                rejected_candidate["disposition"]["reason"],
            )

            restore = build_expertise_restore_plan(
                repo,
                candidate_id="project-design",
            )
            restored = apply_expertise_restore_plan(restore, repo)
            restored_candidate = expertise_inventory(repo)["candidates"][0]
            self.assertEqual("restored", restored["status"])
            self.assertEqual("available", restored["runtime_status"])
            self.assertTrue(restored["immediate_use_allowed"])
            self.assertIsNone(restored_candidate["disposition"])

    def test_legacy_candidate_is_retained_but_cannot_route_or_publish(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            candidate_path = (
                repo
                / ".maestro/state/candidates/expertise/project-design/"
                "candidate.json"
            )
            candidate = json.loads(
                candidate_path.read_text(encoding="utf-8")
            )
            candidate["schema_version"] = (
                "maestro_expertise_candidate_v1"
            )
            candidate.pop("coverage")
            write_json(candidate_path, candidate)

            validation = validate_expertise_candidate(
                repo,
                "project-design",
            )
            inventory = expertise_inventory(repo)["candidates"]

            self.assertIn(
                "EXPERTISE_CANDIDATE_UPGRADE_REQUIRED",
                {issue["code"] for issue in validation["issues"]},
            )
            self.assertEqual(1, len(inventory))
            self.assertEqual("invalid", inventory[0]["runtime_status"])
            self.assertFalse(inventory[0]["immediate_use_allowed"])

    def test_duplicate_automatic_signal_candidates_all_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            fingerprint = "b" * 24
            for candidate_id, pack_id in (
                ("design-gap-a", "design-gap-a"),
                ("design-gap-b", "design-gap-b"),
            ):
                _candidate(
                    repo,
                    candidate_id=candidate_id,
                    pack_id=pack_id,
                    skill_id=pack_id,
                    standalone=True,
                    generation_mode="automatic",
                    signal_fingerprint=fingerprint,
                    component_change={
                        "kind": "new-pack",
                        "target_guide_id": None,
                    },
                )

            for candidate_id in ("design-gap-a", "design-gap-b"):
                validation = validate_expertise_candidate(
                    repo,
                    candidate_id,
                )
                self.assertIn(
                    "EXPERTISE_AUTOMATIC_CANDIDATE_DUPLICATE",
                    {issue["code"] for issue in validation["issues"]},
                )
            statuses = candidate_expertise_statuses(repo)
            self.assertTrue(
                all(
                    statuses[candidate_id]["runtime_status"] == "invalid"
                    and not statuses[candidate_id][
                        "immediate_use_allowed"
                    ]
                    for candidate_id in ("design-gap-a", "design-gap-b")
                )
            )
    def test_component_change_is_visible_and_exports_as_a_review_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(
                repo,
                portability="global",
                component_change={
                    "kind": "guide-addition",
                    "target_guide_id": "project-type-rules",
                },
            )

            candidate = expertise_inventory(repo)["candidates"][0]
            self.assertEqual(
                {
                    "kind": "guide-addition",
                    "target_guide_id": "project-type-rules",
                },
                candidate["component_change"],
            )
            self.assertEqual(
                "not_created",
                candidate["global_request"]["status"],
            )
            self.assertEqual(
                "not_tracked",
                candidate["global_request"][
                    "repository_submission_status"
                ],
            )
            self.assertFalse(
                candidate["global_request"][
                    "automatic_push_performed"
                ]
            )
            preview = build_expertise_export_plan(
                repo,
                candidate_id="project-design",
            )
            self.assertFalse(preview["writes_performed"])
            self.assertFalse(
                (repo / preview["output_path"]).exists()
            )
            result = apply_expertise_export_plan(preview, repo)
            bundle = repo / result["output_path"]
            validation = validate_expertise_contribution(bundle)

            self.assertEqual("exported", result["status"])
            self.assertEqual(
                "local_review_bundle_created",
                result["review_bundle_status"],
            )
            self.assertFalse(result["promotion_performed"])
            self.assertFalse(result["commit_performed"])
            self.assertFalse(result["push_performed"])
            self.assertFalse(result["pull_request_performed"])
            self.assertFalse(result["release_performed"])
            self.assertEqual("PASS", validation["status"])
            self.assertEqual(
                "guide-addition",
                validation["component_change"]["kind"],
            )
            exported_candidate = expertise_inventory(repo)[
                "candidates"
            ][0]
            global_request = exported_candidate["global_request"]
            self.assertEqual(
                "local_review_bundle_created",
                global_request["status"],
            )
            self.assertEqual("PASS", global_request["validation_status"])
            self.assertTrue(
                global_request["matches_current_candidate"]
            )
            self.assertEqual(
                preview["output_path"],
                global_request["output_path"],
            )
            self.assertEqual(
                "not_tracked",
                global_request["repository_submission_status"],
            )
            self.assertEqual(
                "not_tracked",
                global_request["release_status"],
            )
            value = json.loads(bundle.read_text(encoding="utf-8"))
            exported_paths = {
                item["path"] for item in value["files"]
            }
            self.assertIn("evals/quality.json", exported_paths)
            self.assertIn(
                "evals/artifacts/normal-project-type.json",
                exported_paths,
            )
            value["promotion"]["automatic_install_allowed"] = True
            write_json(bundle, value)
            invalid = validate_expertise_contribution(bundle)
            self.assertEqual("FAIL", invalid["status"])
            self.assertIn(
                "EXPERTISE_CONTRIBUTION_PROMOTION_INVALID",
                {issue["code"] for issue in invalid["issues"]},
            )
            invalid_candidate = expertise_inventory(repo)[
                "candidates"
            ][0]
            self.assertEqual(
                "local_review_bundle_invalid",
                invalid_candidate["global_request"]["status"],
            )

    def test_contribution_rejects_rehashed_invalid_quality_artifact(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo, portability="global")
            preview = build_expertise_export_plan(
                repo,
                candidate_id="project-design",
            )
            result = apply_expertise_export_plan(preview, repo)
            bundle = repo / result["output_path"]
            value = json.loads(bundle.read_text(encoding="utf-8"))
            artifact = next(
                item
                for item in value["files"]
                if item["path"].startswith("evals/artifacts/")
            )
            artifact_value = json.loads(artifact["content"])
            artifact_value["case_id"] = "different-case"
            artifact["content"] = json.dumps(
                artifact_value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n"
            artifact["sha256"] = sha256_text(artifact["content"])
            file_digests = {
                item["path"]: item["sha256"]
                for item in value["files"]
            }
            value["candidate_digest"] = sha256_text(
                canonical_json(file_digests)
            )
            unsigned = {
                key: item
                for key, item in value.items()
                if key != "bundle_digest"
            }
            value["bundle_digest"] = sha256_text(
                canonical_json(unsigned)
            )
            write_json(bundle, value)

            validation = validate_expertise_contribution(bundle)

            self.assertEqual("FAIL", validation["status"])
            self.assertIn(
                "EXPERTISE_CONTRIBUTION_QUALITY_CASE_INVALID",
                {issue["code"] for issue in validation["issues"]},
            )

    def test_global_promotion_requires_a_second_preview_and_never_pushes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="global-design",
                pack_id="global-design",
                skill_id="maestro-global-design",
                standalone=True,
                portability="global",
                component_change={
                    "kind": "new-pack",
                    "target_guide_id": None,
                },
            )
            before = expertise_inventory(repo)["candidates"][0]
            self.assertEqual(
                "ready_for_harness_source",
                before["global_adoption"]["status"],
            )
            self.assertTrue(
                before["global_adoption"]["action_available"]
            )
            self.assertFalse(
                (
                    repo
                    / ".maestro/exports/expertise/"
                    "global-design.maestro-contribution.json"
                ).exists()
            )
            preview = build_expertise_global_promotion_plan(
                repo,
                candidate_id="global-design",
                approval_ref="owner_decision:test:global-design",
            )
            registry_path = (
                repo
                / "src/maestro/resources/registry/expertise-packs"
                / "global-design.json"
            )
            skill_path = repo / "skills/maestro-global-design/SKILL.md"
            lock_path = repo / ".maestro/lock.json"
            lock_before = lock_path.read_bytes()
            self.assertFalse(preview["writes_performed"])
            self.assertFalse(registry_path.exists())
            self.assertFalse(skill_path.exists())
            self.assertIn(
                ".maestro/lock.json",
                {
                    operation["path"]
                    for operation in preview["operations"]
                },
            )

            result = apply_expertise_global_promotion_plan(
                preview,
                repo,
            )

            self.assertEqual(
                "harness_source_applied",
                result["status"],
            )
            self.assertTrue(registry_path.is_file())
            self.assertTrue(skill_path.is_file())
            self.assertFalse(result["commit_performed"])
            self.assertFalse(result["push_performed"])
            self.assertFalse(result["pull_request_performed"])
            self.assertFalse(result["release_performed"])
            promoted_pack = json.loads(
                registry_path.read_text(encoding="utf-8")
            )
            self.assertEqual("global", promoted_pack["portability"])
            self.assertEqual("pilot", promoted_pack["status"])
            self.assertNotEqual(lock_before, lock_path.read_bytes())
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            release_manifest = build_release_manifest(repo)
            self.assertEqual(
                release_manifest["registry"]["sha256"],
                lock["registry"]["sha256"],
            )
            self.assertIn(
                ".maestro/lock.json",
                result["git_stage_paths"],
            )
            self.assertIn(
                "maestro-global-design",
                release_manifest["skills"],
            )
            self.assertIn(
                "maestro-global-design",
                load_source_release_manifest(repo)["skills"],
            )
            after = expertise_inventory(repo)["candidates"][0]
            self.assertEqual(
                "harness_source_applied",
                after["global_adoption"]["status"],
            )
            self.assertEqual("PASS", after["validation_status"])
            self.assertEqual(
                "globally_promoted",
                after["runtime_status"],
            )
            self.assertFalse(
                after["global_adoption"]["action_available"]
            )

    def test_global_guide_addition_updates_the_bundled_base_directly(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            base_pack = json.loads(
                (
                    repo
                    / "src/maestro/resources/registry/"
                    "expertise-packs/product-design.json"
                ).read_text(encoding="utf-8")
            )
            _candidate(
                repo,
                candidate_id="design-flow-extension",
                pack_id="design-flow-extension",
                skill_id="design-flow-extension",
                guide_id="project-type-rules",
                portability="global",
                component_change={
                    "kind": "guide-addition",
                    "target_guide_id": "project-type-rules",
                },
            )
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="design-flow-extension",
                approval_ref="owner_decision:test:guide-project-copy",
            )
            apply_expertise_activation_plan(activation, repo)

            preview = build_expertise_global_promotion_plan(
                repo,
                candidate_id="design-flow-extension",
                approval_ref="owner_decision:test:guide-global",
            )

            self.assertEqual("candidate_snapshot", preview["source_kind"])
            self.assertIsNone(preview["bundle_path"])
            self.assertEqual("product-design", preview["expertise_pack_id"])
            self.assertFalse(
                (
                    repo
                    / ".maestro/exports/expertise/"
                    "design-flow-extension.maestro-contribution.json"
                ).exists()
            )
            self.assertIn(
                ".maestro/project.json",
                {
                    operation["path"]
                    for operation in preview["operations"]
                },
            )

            result = apply_expertise_global_promotion_plan(
                preview,
                repo,
            )

            self.assertEqual(
                "harness_source_applied",
                result["status"],
            )
            promoted = json.loads(
                (
                    repo
                    / "src/maestro/resources/registry/"
                    "expertise-packs/product-design.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(base_pack["version"] + 1, promoted["version"])
            self.assertIn(
                "project-type-rules",
                {
                    guide["guide_id"]
                    for guide in promoted["guides"]
                },
            )
            self.assertTrue(
                (
                    repo
                    / "skills/maestro-product-design/references/"
                    "project-type-rules.md"
                ).is_file()
            )
            self.assertEqual(
                json.loads(
                    (
                        repo
                        / "skills/maestro-product-design/evidence/sources.json"
                    ).read_text(encoding="utf-8")
                ),
                json.loads(
                    (
                        repo
                        / "src/maestro/resources/expertise-sources/"
                        "product-design.json"
                    ).read_text(encoding="utf-8")
                ),
            )
            skill = (
                repo / "skills/maestro-product-design/SKILL.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "`project-type-rules`",
                skill,
            )
            cases = json.loads(
                (
                    repo / "skills/maestro-product-design/evals/cases.json"
                ).read_text(encoding="utf-8")
            )
            added_case = next(
                case
                for case in cases["cases"]
                if case["case_id"] == "normal-project-type"
            )
            self.assertEqual(
                "product-design",
                added_case["expected_pack_id"],
            )
            project = json.loads(
                (repo / ".maestro/project.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertNotIn(
                (
                    ".agents/skills/design-flow-extension/"
                    "maestro-pack.json"
                ),
                project["expertise"]["active_pack_paths"],
            )
            self.assertTrue(
                (
                    repo
                    / ".agents/skills/design-flow-extension/"
                    "maestro-pack.json"
                ).is_file()
            )
            candidate = next(
                item
                for item in expertise_inventory(repo)["candidates"]
                if item["candidate_id"] == "design-flow-extension"
            )
            self.assertEqual(
                "globally_promoted",
                candidate["runtime_status"],
            )
            self.assertEqual(
                "harness_source_applied",
                candidate["global_adoption"]["status"],
            )

    def test_global_pack_revision_replaces_one_complete_version(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="global-design-v1",
                pack_id="global-design",
                skill_id="maestro-global-design",
                standalone=True,
                portability="global",
                component_change={
                    "kind": "new-pack",
                    "target_guide_id": None,
                },
            )
            first = build_expertise_global_promotion_plan(
                repo,
                candidate_id="global-design-v1",
                approval_ref="owner_decision:test:global-design-v1",
            )
            apply_expertise_global_promotion_plan(first, repo)
            _candidate(
                repo,
                candidate_id="global-design-v2",
                pack_id="global-design",
                skill_id="maestro-global-design",
                version=2,
                standalone=True,
                portability="global",
                component_change={
                    "kind": "pack-revision",
                    "target_guide_id": None,
                },
            )
            preview = build_expertise_global_promotion_plan(
                repo,
                candidate_id="global-design-v2",
                approval_ref="owner_decision:test:global-design-v2",
            )
            result = apply_expertise_global_promotion_plan(
                preview,
                repo,
            )

            revised = json.loads(
                (
                    repo
                    / "src/maestro/resources/registry/"
                    "expertise-packs/global-design.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(2, revised["version"])
            self.assertEqual(
                "harness_source_applied",
                result["status"],
            )
            self.assertTrue(
                (
                    repo
                    / "skills/maestro-global-design/"
                    "evidence/decision-map.json"
                ).is_file()
            )
            inventory = {
                item["candidate_id"]: item
                for item in expertise_inventory(repo)["candidates"]
            }
            self.assertEqual(
                "globally_promoted",
                inventory["global-design-v2"]["runtime_status"],
            )

    def test_global_pack_revision_rejects_silent_routing_removal(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="global-design-v1",
                pack_id="global-design",
                skill_id="maestro-global-design",
                standalone=True,
                portability="global",
                component_change={
                    "kind": "new-pack",
                    "target_guide_id": None,
                },
            )
            first = build_expertise_global_promotion_plan(
                repo,
                candidate_id="global-design-v1",
                approval_ref="owner_decision:test:global-design-v1",
            )
            apply_expertise_global_promotion_plan(first, repo)
            _candidate(
                repo,
                candidate_id="global-design-v2",
                pack_id="global-design",
                skill_id="maestro-global-design",
                version=2,
                standalone=True,
                portability="global",
                component_change={
                    "kind": "pack-revision",
                    "target_guide_id": None,
                },
            )
            revised_path = (
                repo
                / ".maestro/state/candidates/expertise/global-design-v2/"
                "draft/maestro-pack.json"
            )
            revised = json.loads(
                revised_path.read_text(encoding="utf-8")
            )
            revised["triggers"] = ["project typography"]
            write_json(revised_path, revised)
            _attest_candidate(repo, "global-design-v2")

            with self.assertRaisesRegex(
                Exception,
                "may not silently remove routing coverage",
            ):
                build_expertise_global_promotion_plan(
                    repo,
                    candidate_id="global-design-v2",
                    approval_ref=(
                        "owner_decision:test:global-design-v2"
                    ),
                )

    def test_global_promotion_updates_manifest_before_catalog_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="global-design",
                pack_id="global-design",
                skill_id="maestro-global-design",
                standalone=True,
                portability="global",
                component_change={
                    "kind": "new-pack",
                    "target_guide_id": None,
                },
            )
            export = build_expertise_export_plan(
                repo,
                candidate_id="global-design",
            )
            apply_expertise_export_plan(export, repo)
            preview = build_expertise_global_promotion_plan(
                repo,
                candidate_id="global-design",
                approval_ref="owner_decision:test:manifest-order",
            )

            with patch(
                "maestro.expertise_lifecycle.load_expertise_catalog",
                side_effect=lambda repo_path: [
                    load_source_release_manifest(repo_path)
                ],
            ):
                result = apply_expertise_global_promotion_plan(
                    preview,
                    repo,
                )

            self.assertEqual(
                "harness_source_applied",
                result["status"],
            )
            self.assertIn(
                "maestro-global-design",
                load_source_release_manifest(repo)["skills"],
            )

    def test_global_promotion_supersedes_matching_active_project_copy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="global-design",
                pack_id="global-design",
                skill_id="maestro-global-design",
                standalone=True,
                portability="global",
                component_change={
                    "kind": "new-pack",
                    "target_guide_id": None,
                },
            )
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="global-design",
                approval_ref="owner_decision:test:project-copy",
            )
            apply_expertise_activation_plan(activation, repo)
            export = build_expertise_export_plan(
                repo,
                candidate_id="global-design",
            )
            apply_expertise_export_plan(export, repo)
            preview = build_expertise_global_promotion_plan(
                repo,
                candidate_id="global-design",
                approval_ref="owner_decision:test:global-copy",
            )

            with (
                patch(
                    "maestro.expertise.load_registry",
                    side_effect=lambda: load_source_registry(repo),
                ),
                patch(
                    "maestro.expertise.load_packaged_release_manifest",
                    side_effect=lambda: load_source_release_manifest(repo),
                ),
                patch(
                    "maestro.expertise_lifecycle.load_registry",
                    side_effect=lambda: load_source_registry(repo),
                ),
            ):
                result = apply_expertise_global_promotion_plan(
                    preview,
                    repo,
                )
                catalog = load_expertise_catalog(repo)
                promoted_candidate = next(
                    item
                    for item in expertise_inventory(repo)["candidates"]
                    if item["candidate_id"] == "global-design"
                )

            self.assertEqual(
                "harness_source_applied",
                result["status"],
            )
            matching = [
                pack
                for pack in catalog
                if pack["expertise_pack_id"] == "global-design"
            ]
            self.assertEqual(1, len(matching))
            self.assertEqual(
                "bundled",
                matching[0]["_maestro"]["origin"],
            )
            self.assertEqual(
                "harness_source_applied",
                promoted_candidate["global_adoption"]["status"],
            )
            project_pack = (
                repo
                / ".agents/skills/maestro-global-design"
                / "maestro-pack.json"
            )
            self.assertTrue(project_pack.is_file())
            project = json.loads(
                (repo / ".maestro/project.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn(
                (
                    ".agents/skills/maestro-global-design/"
                    "maestro-pack.json"
                ),
                project["expertise"]["active_pack_paths"],
            )

            snapshot_path = (
                repo
                / ".agents/skills/maestro-global-design"
                / "evidence/candidate.json"
            )
            snapshot = json.loads(
                snapshot_path.read_text(encoding="utf-8")
            )
            snapshot["portability"] = "project"
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )
            with (
                patch(
                    "maestro.expertise.load_registry",
                    side_effect=lambda: load_source_registry(repo),
                ),
                patch(
                    "maestro.expertise.load_packaged_release_manifest",
                    side_effect=lambda: load_source_release_manifest(repo),
                ),
                self.assertRaisesRegex(
                    MaestroError,
                    "duplicate expertise_pack_id",
                ),
            ):
                load_expertise_catalog(repo)

    def test_project_confirmed_pack_promotes_without_candidate_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="project-design",
                pack_id="project-design",
                skill_id="project-design",
                standalone=True,
                portability="project",
            )
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:test:project-confirmed",
            )
            apply_expertise_activation_plan(activation, repo)
            rejection = build_expertise_rejection_plan(
                repo,
                candidate_id="project-design",
                reason="The project publication is the retained source.",
            )
            apply_expertise_rejection_plan(rejection, repo)

            inventory = expertise_inventory(repo)
            project_pack = next(
                pack
                for pack in inventory["packs"]
                if pack["expertise_pack_id"] == "project-design"
            )
            self.assertEqual("project", project_pack["origin"])
            self.assertEqual(
                "ready_for_harness_source",
                project_pack["global_adoption"]["status"],
            )
            self.assertTrue(
                project_pack["global_adoption"]["action_available"]
            )
            self.assertFalse(
                (
                    repo
                    / ".maestro/exports/expertise/"
                    "project-design.maestro-contribution.json"
                ).exists()
            )

            preview = build_expertise_global_promotion_plan(
                repo,
                expertise_pack_id="project-design",
                approval_ref="owner_decision:test:project-to-global",
            )

            self.assertEqual(
                "project_publication",
                preview["source_kind"],
            )
            self.assertEqual(
                (
                    ".agents/skills/project-design/"
                    "maestro-pack.json"
                ),
                preview["source_ref"],
            )
            self.assertIsNone(preview["bundle_path"])
            self.assertEqual(
                "maestro-project-design",
                preview["skill_id"],
            )

            result = apply_expertise_global_promotion_plan(
                preview,
                repo,
            )

            self.assertEqual(
                "harness_source_applied",
                result["status"],
            )
            self.assertEqual(
                "project_publication",
                result["source_kind"],
            )
            promoted_pack = json.loads(
                (
                    repo
                    / "src/maestro/resources/registry/"
                    "expertise-packs/project-design.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual("global", promoted_pack["portability"])
            self.assertEqual(
                "maestro-project-design",
                promoted_pack["skill_id"],
            )
            promoted_skill = (
                repo / "skills/maestro-project-design/SKILL.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "name: maestro-project-design",
                promoted_skill,
            )
            self.assertIn(
                "maestro-project-design",
                load_source_release_manifest(repo)["skills"],
            )
            self.assertFalse(result["commit_performed"])
            self.assertFalse(result["push_performed"])
            with (
                patch(
                    "maestro.expertise.load_registry",
                    side_effect=lambda: load_source_registry(repo),
                ),
                patch(
                    "maestro.expertise.load_packaged_release_manifest",
                    side_effect=lambda: load_source_release_manifest(repo),
                ),
                patch(
                    "maestro.expertise_lifecycle.load_registry",
                    side_effect=lambda: load_source_registry(repo),
                ),
                patch(
                    "maestro.governance.registry_digest",
                    side_effect=lambda: source_registry_digest(repo),
                ),
            ):
                catalog = load_expertise_catalog(repo)
                snapshot = snapshot_report(repo)
                candidate_after = next(
                    item
                    for item in expertise_inventory(repo)["candidates"]
                    if item["candidate_id"] == "project-design"
                )

            matching = [
                item
                for item in catalog
                if item["expertise_pack_id"] == "project-design"
            ]
            self.assertEqual(1, len(matching))
            self.assertEqual(
                "bundled",
                matching[0]["_maestro"]["origin"],
            )
            self.assertEqual(
                "maestro_snapshot_v1",
                snapshot["schema_version"],
            )
            self.assertEqual(
                "harness_source_applied",
                candidate_after["global_adoption"]["status"],
            )
            self.assertEqual(
                "PASS",
                candidate_after["validation_status"],
            )
            self.assertEqual(
                "rejected",
                candidate_after["runtime_status"],
            )
            project = json.loads(
                (repo / ".maestro/project.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn(
                ".agents/skills/project-design/maestro-pack.json",
                project["expertise"]["active_pack_paths"],
            )
            self.assertTrue(
                (
                    repo
                    / ".agents/skills/project-design/"
                    "maestro-pack.json"
                ).is_file()
            )

            snapshot_path = (
                repo
                / ".agents/skills/project-design/"
                "evidence/candidate.json"
            )
            project_candidate = json.loads(
                snapshot_path.read_text(encoding="utf-8")
            )
            project_candidate["problem"] = "Unreviewed change."
            snapshot_path.write_text(
                json.dumps(project_candidate, ensure_ascii=False),
                encoding="utf-8",
            )
            with (
                patch(
                    "maestro.expertise.load_registry",
                    side_effect=lambda: load_source_registry(repo),
                ),
                patch(
                    "maestro.expertise.load_packaged_release_manifest",
                    side_effect=lambda: load_source_release_manifest(repo),
                ),
                self.assertRaisesRegex(
                    MaestroError,
                    "duplicate expertise_pack_id",
                ),
            ):
                load_expertise_catalog(repo)

    def test_project_promotion_rejects_changed_publication_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="project-design",
                pack_id="project-design",
                standalone=True,
                portability="project",
            )
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:test:project-confirmed",
            )
            apply_expertise_activation_plan(activation, repo)
            skill_path = (
                repo / ".agents/skills/project-design/SKILL.md"
            )
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8")
                + "\nUnreviewed change.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                MaestroError,
                "changed after activation",
            ) as raised:
                build_expertise_global_promotion_plan(
                    repo,
                    expertise_pack_id="project-design",
                    approval_ref=(
                        "owner_decision:test:tampered-project"
                    ),
                )

            self.assertEqual(
                "EXPERTISE_PROJECT_PROMOTION_SOURCE_STALE",
                raised.exception.code,
            )

    def test_global_promotion_rolls_back_source_when_manifest_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="global-design",
                pack_id="global-design",
                skill_id="maestro-global-design",
                standalone=True,
                portability="global",
                component_change={
                    "kind": "new-pack",
                    "target_guide_id": None,
                },
            )
            export = build_expertise_export_plan(
                repo,
                candidate_id="global-design",
            )
            apply_expertise_export_plan(export, repo)
            preview = build_expertise_global_promotion_plan(
                repo,
                candidate_id="global-design",
                approval_ref="owner_decision:test:rollback",
            )
            registry_path = (
                repo
                / "src/maestro/resources/registry/expertise-packs"
                / "global-design.json"
            )
            skill_root = repo / "skills/maestro-global-design"
            manifest_path = (
                repo
                / "src/maestro/resources/release-manifest.json"
            )
            manifest_before = manifest_path.read_bytes()
            lock_path = repo / ".maestro/lock.json"
            lock_before = lock_path.read_bytes()

            with patch(
                "maestro.expertise_lifecycle.build_release_manifest",
                side_effect=RuntimeError("manifest generation failed"),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "manifest generation failed",
                ):
                    apply_expertise_global_promotion_plan(preview, repo)

            self.assertFalse(registry_path.exists())
            self.assertFalse(skill_root.exists())
            self.assertEqual(manifest_before, manifest_path.read_bytes())
            self.assertEqual(lock_before, lock_path.read_bytes())
            adoption = expertise_inventory(repo)["candidates"][0][
                "global_adoption"
            ]
            self.assertEqual(
                "ready_for_harness_source",
                adoption["status"],
            )

    def test_global_promotion_rolls_back_when_project_catalog_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="project-design",
                pack_id="project-design",
                standalone=True,
                portability="project",
            )
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:test:project-catalog",
            )
            apply_expertise_activation_plan(activation, repo)
            preview = build_expertise_global_promotion_plan(
                repo,
                expertise_pack_id="project-design",
                approval_ref="owner_decision:test:project-catalog",
            )
            registry_path = (
                repo
                / "src/maestro/resources/registry/expertise-packs/"
                "project-design.json"
            )
            skill_root = repo / "skills/maestro-project-design"
            manifest_path = (
                repo
                / "src/maestro/resources/release-manifest.json"
            )
            lock_path = repo / ".maestro/lock.json"
            manifest_before = manifest_path.read_bytes()
            lock_before = lock_path.read_bytes()

            with patch(
                (
                    "maestro.expertise_lifecycle."
                    "validate_project_expertise_against_registry"
                ),
                side_effect=MaestroError(
                    "PROJECT_EXPERTISE_INVALID",
                    "duplicate expertise_pack_id: project-design",
                ),
            ):
                with self.assertRaisesRegex(
                    MaestroError,
                    "duplicate expertise_pack_id",
                ):
                    apply_expertise_global_promotion_plan(
                        preview,
                        repo,
                    )

            self.assertFalse(registry_path.exists())
            self.assertFalse(skill_root.exists())
            self.assertEqual(manifest_before, manifest_path.read_bytes())
            self.assertEqual(lock_before, lock_path.read_bytes())

    def test_component_change_must_match_the_candidate_guide_set(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(
                repo,
                component_change={
                    "kind": "guide-revision",
                    "target_guide_id": "missing-guide",
                },
                attest=False,
            )

            report = validate_expertise_candidate(
                repo,
                "project-design",
            )

            self.assertEqual("FAIL", report["status"])
            self.assertIn(
                "EXPERTISE_CANDIDATE_INVALID",
                {issue["code"] for issue in report["issues"]},
            )

    def test_dashboard_exports_only_after_typed_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo, portability="global")
            server, token, url = create_dashboard_server(repo)
            thread = threading.Thread(
                target=server.serve_forever,
                daemon=True,
            )
            thread.start()
            base = url.split("/#token=", 1)[0]

            def post(path: str, payload: dict[str, object]):
                request = urllib.request.Request(
                    f"{base}{path}",
                    method="POST",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Maestro-Token": token,
                        "Origin": base,
                    },
                )
                with urllib.request.urlopen(
                    request,
                    timeout=5,
                ) as response:
                    return json.loads(response.read())

            try:
                preview = post(
                    "/api/expertise-actions/preview",
                    {
                        "action": "export",
                        "candidate_id": "project-design",
                        "pack_id": None,
                    },
                )
                self.assertFalse(preview["writes_performed"])
                self.assertFalse(
                    (repo / preview["output_path"]).exists()
                )

                result = post(
                    "/api/expertise-actions/apply",
                    {
                        "plan_id": preview["plan_id"],
                        "plan_digest": preview["plan_digest"],
                    },
                )

                self.assertEqual("exported", result["status"])
                self.assertEqual(
                    "local_review_bundle_created",
                    result["review_bundle_status"],
                )
                self.assertFalse(result["commit_performed"])
                self.assertFalse(result["push_performed"])
                self.assertFalse(result["pull_request_performed"])
                self.assertFalse(result["release_performed"])
                self.assertTrue(
                    (repo / result["output_path"]).is_file()
                )

                rejection = post(
                    "/api/expertise-actions/preview",
                    {
                        "action": "reject",
                        "candidate_id": "project-design",
                        "pack_id": None,
                    },
                )
                disposition = (
                    repo
                    / ".maestro/state/candidates/expertise/project-design"
                    / "disposition.json"
                )
                self.assertFalse(rejection["writes_performed"])
                self.assertFalse(disposition.exists())
                rejected = post(
                    "/api/expertise-actions/apply",
                    {
                        "plan_id": rejection["plan_id"],
                        "plan_digest": rejection["plan_digest"],
                    },
                )
                self.assertEqual("rejected", rejected["status"])
                self.assertTrue(disposition.is_file())

                restoration = post(
                    "/api/expertise-actions/preview",
                    {
                        "action": "restore",
                        "candidate_id": "project-design",
                        "pack_id": None,
                    },
                )
                restored = post(
                    "/api/expertise-actions/apply",
                    {
                        "plan_id": restoration["plan_id"],
                        "plan_digest": restoration["plan_digest"],
                    },
                )
                self.assertEqual("restored", restored["status"])
                self.assertFalse(disposition.exists())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_dashboard_previews_project_confirmed_global_promotion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "harness-source"
            repo.mkdir()
            shutil.copytree(ROOT / "src", repo / "src")
            shutil.copytree(ROOT / "skills", repo / "skills")
            shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="project-design",
                pack_id="project-design",
                standalone=True,
                portability="project",
            )
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:test:dashboard-project",
            )
            apply_expertise_activation_plan(activation, repo)
            server, token, url = create_dashboard_server(repo)
            thread = threading.Thread(
                target=server.serve_forever,
                daemon=True,
            )
            thread.start()
            base = url.split("/#token=", 1)[0]
            try:
                request = urllib.request.Request(
                    f"{base}/api/expertise-actions/preview",
                    method="POST",
                    data=json.dumps(
                        {
                            "action": "promote_global",
                            "candidate_id": None,
                            "pack_id": "project-design",
                        }
                    ).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-Maestro-Token": token,
                        "Origin": base,
                    },
                )
                with urllib.request.urlopen(
                    request,
                    timeout=5,
                ) as response:
                    preview = json.loads(response.read())

                self.assertEqual(
                    "promote_global",
                    preview["action"],
                )
                self.assertEqual(
                    "project-design",
                    preview["pack_id"],
                )
                self.assertFalse(preview["writes_performed"])
                self.assertIn(
                    (
                        "src/maestro/resources/registry/"
                        "expertise-packs/project-design.json"
                    ),
                    preview["changed_paths"],
                )
                self.assertFalse(
                    (
                        repo
                        / "src/maestro/resources/registry/"
                        "expertise-packs/project-design.json"
                    ).exists()
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_fifth_candidate_use_prompts_owner_without_auto_export(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo, portability="global")

            results = []
            for index in range(6):
                receipt_path = Path(temporary) / f"receipt-{index}.json"
                write_json(
                    receipt_path,
                    {
                        "run_id": f"global-promotion-{index}",
                        "risk": "low",
                        "route_depth": "fast",
                        "selected_lenses": [],
                        "selected_expertise_packs": ["project-design"],
                        "selected_decision_guides": [
                            "project-type-rules"
                        ],
                        "expertise_research_mode": "reuse",
                        "expertise_research_gate": "not-required",
                        "executor_runs": 1,
                        "primary_executor_id": (
                            "implementation-engineer"
                        ),
                        "executor_ids": [
                            "implementation-engineer"
                        ],
                        "outcome": "completed",
                        "evidence_refs": ["artifact:screen"],
                        "duration_ms": 100,
                        "tokens": None,
                        "correction_count": 0,
                        "agent_calls": 1,
                        "work_spans": [
                            application_work_span(
                                "project-design",
                                ["project-type-rules"],
                                work_id=(
                                    f"global-promotion-{index}"
                                ),
                            )
                        ],
                        "verifier_result": "not_run",
                        "command_artifact_ref": None,
                    },
                )
                results.append(record_run(repo, receipt_path))

            for result in results[:4]:
                management = result["management_check"]
                self.assertFalse(management["owner_prompt_due"])
                self.assertEqual(
                    [],
                    management["global_promotion_prompts"],
                )

            management = results[4]["management_check"]
            self.assertTrue(management["review_due"])
            self.assertTrue(management["owner_prompt_due"])
            self.assertFalse(management["automatic_mutation_allowed"])
            self.assertEqual(
                [
                    {
                        "candidate_id": "project-design",
                        "pack_id": "project-design",
                        "observed_usage_count": 5,
                        "required_usage_count": 5,
                        "problem_review_required": False,
                        "question": (
                            "project-design 후보가 서로 다른 작업에서 "
                            "5회 적용이 확인됐습니다. Harness 기본 Pack에 "
                            "반영할까요?"
                        ),
                    }
                ],
                management["global_promotion_prompts"],
            )

            snapshot = snapshot_report(repo)
            prompt_attention = [
                item
                for item in snapshot["attention"]
                if item["id"] == "ask_global_expertise_promotion"
            ]
            self.assertEqual(1, len(prompt_attention))
            self.assertEqual(
                "project-design",
                prompt_attention[0]["candidate_id"],
            )
            self.assertFalse(
                (
                    repo / ".maestro/exports/expertise"
                ).exists()
            )

            sixth_management = results[5]["management_check"]
            self.assertTrue(sixth_management["owner_prompt_due"])
            self.assertEqual(
                6,
                sixth_management["global_promotion_prompts"][0][
                    "observed_usage_count"
                ],
            )

            decline = build_expertise_promotion_decision_plan(
                repo,
                candidate_id="project-design",
                decision="decline",
                reason="이 후보 버전은 전역 기본값으로 사용하지 않음",
            )
            apply_expertise_promotion_decision_plan(decline, repo)
            declined_snapshot = snapshot_report(repo)
            declined_health = next(
                item
                for item in declined_snapshot["expertise"][
                    "component_health"
                ]["candidates"]
                if item["candidate_id"] == "project-design"
            )
            self.assertEqual(
                "declined",
                declined_health["global_promotion"]["status"],
            )
            self.assertNotIn(
                "project-design",
                [
                    item.get("candidate_id")
                    for item in declined_snapshot["attention"]
                    if item["id"] == "ask_global_expertise_promotion"
                ],
            )

            reconsider = build_expertise_promotion_decision_plan(
                repo,
                candidate_id="project-design",
                decision="reconsider",
            )
            apply_expertise_promotion_decision_plan(reconsider, repo)
            reconsidered_snapshot = snapshot_report(repo)
            self.assertIn(
                "project-design",
                [
                    item.get("candidate_id")
                    for item in reconsidered_snapshot["attention"]
                    if item["id"] == "ask_global_expertise_promotion"
                ],
            )

    def test_candidate_bundle_validation_checks_semantic_links_and_receipt(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)

            self.assertEqual(
                "PASS",
                validate_expertise_candidate(
                    repo,
                    "project-design",
                )["status"],
            )
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "expertise",
                        "validate-candidate",
                        "--repo",
                        str(repo),
                        "--candidate",
                        "project-design",
                        "--json",
                    ]
                )
            self.assertEqual(0, exit_code)
            self.assertEqual("PASS", json.loads(output.getvalue())["status"])
            results = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "evals/results.json"
            )
            value = json.loads(results.read_text(encoding="utf-8"))
            value["results"][0]["verdict"] = "fail"
            write_json(results, value)
            report = validate_expertise_candidate(repo, "project-design")
            self.assertEqual("FAIL", report["status"])
            self.assertIn(
                "EXPERTISE_EVALUATION_ARTIFACT_INVALID",
                {item["code"] for item in report["issues"]},
            )

    def test_quality_evaluation_requires_independent_exact_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            quality_path = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "evals/quality.json"
            )
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            quality["evaluator"]["evaluation_run_ref"] = quality[
                "evaluator"
            ]["authoring_run_ref"]
            write_json(quality_path, quality)

            report = validate_expertise_candidate(repo, "project-design")

            self.assertEqual("FAIL", report["status"])
            self.assertIn(
                "EXPERTISE_QUALITY_EVALUATION_INVALID",
                {item["code"] for item in report["issues"]},
            )

    def test_quality_evaluation_rejects_missing_criterion_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            quality_path = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "evals/quality.json"
            )
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            quality["cases"][0]["criterion_results"] = []
            write_json(quality_path, quality)

            report = validate_expertise_candidate(repo, "project-design")

            self.assertEqual("FAIL", report["status"])
            self.assertIn(
                "EXPERTISE_QUALITY_CRITERIA_INCOMPLETE",
                {item["code"] for item in report["issues"]},
            )

    def test_quality_evaluation_reports_malformed_case_without_crashing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            quality_path = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "evals/quality.json"
            )
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            quality["cases"][0]["case_id"] = ["not", "an", "id"]
            write_json(quality_path, quality)

            report = validate_expertise_candidate(repo, "project-design")

            self.assertEqual("FAIL", report["status"])
            self.assertIn(
                "EXPERTISE_QUALITY_CASE_INVALID",
                {item["code"] for item in report["issues"]},
            )

    def test_valid_candidate_is_immediately_routed_before_publication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo, portability="global")

            before = route_goal_v2(
                "Apply our project typography to the product design",
                "medium",
                intent="review",
                repo_path=repo,
            )
            draft_candidate = expertise_inventory(repo)["candidates"][0]
            self.assertTrue(
                draft_candidate["ready_for_activation_review"]
            )
            self.assertTrue(
                draft_candidate["ready_for_export_review"]
            )
            draft_health = expertise_component_health(
                expertise_inventory(repo),
                [],
            )["candidates"][0]
            self.assertEqual(
                "request_available",
                draft_health["global_promotion"]["status"],
            )
            self.assertEqual(
                5,
                draft_health["global_promotion"]["remaining_usage_count"],
            )
            self.assertTrue(
                draft_health["global_promotion"]["request_available"],
            )
            self.assertTrue(
                draft_health["global_promotion"]["eligible"],
            )
            self.assertFalse(
                draft_health["global_promotion"]["owner_prompt_due"],
            )
            self.assertEqual(
                ["project-design"],
                before["expertise"]["selected_pack_ids"],
            )
            candidate_card = before["expertise"]["pack_cards"][0]
            self.assertEqual("candidate", candidate_card["origin"])
            self.assertEqual(
                "candidate",
                candidate_card["lifecycle_state"],
            )
            self.assertEqual(
                "project-design",
                candidate_card["candidate_id"],
            )
            self.assertIn(
                "EXPERTISE_CANDIDATE_IN_USE",
                {
                    warning["code"]
                    for warning in before["expertise"]["warnings"]
                },
            )
            self.assertEqual(
                "PASS",
                validate_route_v2(before, repo_path=repo)["status"],
            )
            implementation = route_goal_v2(
                "Implement our project typography in the product design",
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            writer = next(
                assignment
                for assignment in implementation["assignments"]
                if assignment["mutation_owner"]
            )
            self.assertIn(
                "project-type-rules",
                writer["decision_guide_ids"],
            )
            self.assertEqual(
                "PASS",
                validate_route_v2(
                    implementation,
                    repo_path=repo,
                )["status"],
            )
            decision = build_decision_plan(
                repo,
                "Choose our project typography for the product design",
                "medium",
            )
            candidate_loads = [
                pack
                for specialist in decision["specialist_contracts"]
                for pack in specialist["expertise_load"]["packs"]
                if pack["expertise_pack_id"] == "project-design"
            ]
            self.assertEqual("PASS", validate_decision_plan(decision)["status"])
            self.assertTrue(candidate_loads)
            self.assertTrue(
                candidate_loads[0]["skill_path"].startswith(
                    ".maestro/state/candidates/expertise/"
                )
            )
            self.assertTrue(
                all(
                    assignment["read_only"]
                    for assignment in decision["assignments"]
                )
            )

            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="held_out_evaluation:eval-7",
            )
            plan_path = Path(temporary) / "activation.json"
            write_json(plan_path, activation)
            result = apply_expertise_activation_plan(plan_path, repo)

            self.assertTrue(result["candidate_retained"])
            self.assertTrue(
                (repo / ".agents/skills/project-design/SKILL.md").is_file()
            )
            snapshot = json.loads(
                (
                    repo
                    / ".agents/skills/project-design/evidence/candidate.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual("project-design", snapshot["candidate_id"])
            after = route_goal_v2(
                "Apply our project typography to the product design",
                "medium",
                intent="review",
                repo_path=repo,
            )
            expertise = after["expertise"]
            self.assertEqual(
                ["project-design"],
                expertise["selected_pack_ids"],
            )
            card = expertise["pack_cards"][0]
            self.assertEqual("project", card["origin"])
            self.assertEqual(
                "product-design",
                card["extends"]["expertise_pack_id"],
            )
            self.assertEqual(
                "project",
                next(
                    guide["origin"]
                    for guide in card["guides"]
                    if guide["guide_id"] == "project-type-rules"
                ),
            )
            self.assertEqual(
                "PASS",
                validate_route_v2(after, repo_path=repo)["status"],
            )
            self.assertEqual(
                "FAIL",
                validate_route_v2(after)["status"],
            )
            self.assertEqual(
                "PASS",
                check_by_id(doctor_report(repo), "PROJECT_EXPERTISE")["status"],
            )
            inventory = expertise_inventory(repo)
            self.assertEqual(1, len(inventory["candidates"]))
            published_candidate = inventory["candidates"][0]
            self.assertEqual(
                "published",
                published_candidate["runtime_status"],
            )
            self.assertFalse(
                published_candidate["ready_for_activation_review"]
            )
            self.assertTrue(
                published_candidate["ready_for_export_review"]
            )
            self.assertIn(
                "project-design",
                {
                    pack["expertise_pack_id"]
                    for pack in inventory["packs"]
                    if pack["origin"] == "project"
                },
            )

    def test_invalid_or_expired_candidate_is_not_immediately_routed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            quality_path = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "evals/quality.json"
            )
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            quality["cases"][0]["criterion_results"] = []
            write_json(quality_path, quality)

            invalid_route = route_goal_v2(
                "Apply our project typography to the product design",
                "medium",
                intent="review",
                repo_path=repo,
            )

            self.assertNotIn(
                "project-design",
                invalid_route["expertise"]["selected_pack_ids"],
            )
            invalid_candidate = expertise_inventory(repo)["candidates"][0]
            self.assertEqual("invalid", invalid_candidate["runtime_status"])
            self.assertFalse(
                invalid_candidate["immediate_use_allowed"]
            )

            _candidate(
                repo,
                candidate_id="expired-project-design",
                pack_id="expired-project-design",
                standalone=True,
            )
            expired_path = (
                repo
                / ".maestro/state/candidates/expertise/"
                "expired-project-design/candidate.json"
            )
            expired = json.loads(expired_path.read_text(encoding="utf-8"))
            expired["review_after"] = "2020-01-01"
            write_json(expired_path, expired)
            _attest_candidate(repo, "expired-project-design")

            statuses = {
                item["candidate_id"]: item
                for item in expertise_inventory(repo)["candidates"]
            }
            self.assertEqual(
                "expired",
                statuses["expired-project-design"]["runtime_status"],
            )
            self.assertFalse(
                statuses["expired-project-design"][
                    "immediate_use_allowed"
                ]
            )

    def test_bundled_successor_is_not_reported_as_candidate_validation_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="old-software-engineering",
                pack_id="software-engineering",
                skill_id="maestro-software-engineering",
                standalone=True,
                portability="global",
                component_change={
                    "kind": "new-pack",
                    "target_guide_id": None,
                },
            )

            validation = validate_expertise_candidate(
                repo,
                "old-software-engineering",
            )
            status = candidate_expertise_statuses(repo)[
                "old-software-engineering"
            ]

            self.assertEqual("PASS", validation["status"])
            self.assertEqual("superseded", status["runtime_status"])
            self.assertFalse(status["immediate_use_allowed"])

    def test_candidate_v2_requires_complete_decision_area_allocation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            root = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
            )
            decision_map_path = root / "evidence/decision-map.json"

            self.assertEqual(
                "PASS",
                validate_expertise_candidate(
                    repo,
                    "project-design",
                )["status"],
            )

            decision_map = json.loads(
                decision_map_path.read_text(encoding="utf-8")
            )
            decision_map["decision_areas"][0]["disposition"][
                "target_id"
            ] = "missing-guide"
            write_json(decision_map_path, decision_map)
            failed = validate_expertise_candidate(
                repo,
                "project-design",
            )
            self.assertEqual("FAIL", failed["status"])
            self.assertIn(
                "EXPERTISE_DECISION_AREA_GUIDE_MISSING",
                {issue["code"] for issue in failed["issues"]},
            )

    def test_same_version_candidate_conflict_blocks_immediate_use(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(
                repo,
                candidate_id="project-design-a",
            )
            _candidate(
                repo,
                candidate_id="project-design-b",
            )

            inventory = expertise_inventory(repo)
            conflicting = [
                candidate
                for candidate in inventory["candidates"]
                if candidate["expertise_pack_id"] == "project-design"
            ]

            self.assertEqual(2, len(conflicting))
            self.assertTrue(
                all(
                    candidate["runtime_status"] == "conflict"
                    and not candidate["immediate_use_allowed"]
                    for candidate in conflicting
                )
            )

    def test_activation_rejects_stale_base_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo, stale_base=True)

            with self.assertRaisesRegex(Exception, "extends must pin"):
                build_expertise_activation_plan(
                    repo,
                    candidate_id="project-design",
                    approval_ref="owner_decision:issue-12",
                )

    def test_activation_rejects_an_expired_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            candidate_path = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "candidate.json"
            )
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["review_after"] = "2020-01-01"
            write_json(candidate_path, candidate)

            with self.assertRaisesRegex(Exception, "Expired candidates"):
                build_expertise_activation_plan(
                    repo,
                    candidate_id="project-design",
                    approval_ref="owner_decision:issue-expired",
                )

    def test_activation_rejects_a_git_ignored_active_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(repo)],
                check=True,
            )
            apply_fresh_init(repo)
            _candidate(repo)
            ignore = repo / ".gitignore"
            ignore.write_text(
                ignore.read_text(encoding="utf-8") + "\n.agents/\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(Exception, "must not be Git-ignored"):
                build_expertise_activation_plan(
                    repo,
                    candidate_id="project-design",
                    approval_ref="owner_decision:issue-ignore",
                )

    def test_standalone_project_pack_is_supported_for_a_new_domain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo, standalone=True)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="held_out_evaluation:eval-standalone",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)

            route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )

            self.assertEqual(
                ["project-design"],
                route["expertise"]["selected_pack_ids"],
            )
            self.assertIsNone(route["expertise"]["pack_cards"][0]["extends"])

    def test_route_validation_detects_changed_active_skill_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-13",
            )
            plan_path = Path(temporary) / "activation.json"
            write_json(plan_path, activation)
            apply_expertise_activation_plan(plan_path, repo)
            route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )

            skill = repo / ".agents/skills/project-design/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nChanged.\n",
                encoding="utf-8",
            )

            validation = validate_route_v2(route, repo_path=repo)
            self.assertEqual("FAIL", validation["status"])
            self.assertIn(
                "ADAG_EXPERTISE_SELECTION_MISMATCH",
                {issue["code"] for issue in validation["issues"]},
            )

    def test_local_pack_usage_is_accepted_by_project_governance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-14",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            receipt_path = Path(temporary) / "receipt.json"
            write_json(
                receipt_path,
                {
                    "run_id": "project-design-run",
                    "risk": "low",
                    "route_depth": "fast",
                    "selected_lenses": [],
                    "selected_expertise_packs": ["project-design"],
                    "selected_decision_guides": ["project-type-rules"],
                    "expertise_research_mode": "reuse",
                    "expertise_research_gate": "not-required",
                    "executor_runs": 1,
                    "primary_executor_id": "implementation-engineer",
                    "executor_ids": ["implementation-engineer"],
                    "outcome": "completed",
                    "evidence_refs": ["artifact:screen"],
                    "duration_ms": 100,
                    "tokens": None,
                    "correction_count": 0,
                    "agent_calls": 1,
                    "work_spans": [
                        application_work_span(
                            "project-design",
                            ["project-type-rules"],
                            work_id="candidate-project-design-run",
                        )
                    ],
                    "verifier_result": "not_run",
                    "command_artifact_ref": None,
                },
            )

            recorded = record_run(repo, receipt_path)
            event = json.loads(
                (repo / recorded["event_path"])
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            report = govern_report(repo, window=20, threshold=2)

            self.assertIn(
                "project-design",
                event["expertise_pack_definition_digests"],
            )
            self.assertEqual(
                {"project-design": 1},
                report["expertise_pack_usage"],
            )

    def test_candidate_usage_is_recorded_separately_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            receipt_path = Path(temporary) / "candidate-receipt.json"
            write_json(
                receipt_path,
                {
                    "run_id": "candidate-project-design-run",
                    "task_label": "프로젝트 타이포그래피 구현",
                    "risk": "low",
                    "route_depth": "fast",
                    "selected_lenses": [],
                    "selected_expertise_packs": ["project-design"],
                    "selected_decision_guides": ["project-type-rules"],
                    "expertise_research_mode": "reuse",
                    "expertise_research_gate": "not-required",
                    "executor_runs": 1,
                    "primary_executor_id": "implementation-engineer",
                    "executor_ids": ["implementation-engineer"],
                    "outcome": "completed",
                    "evidence_refs": ["artifact:screen"],
                    "duration_ms": 100,
                    "tokens": None,
                    "correction_count": 0,
                    "agent_calls": 1,
                    "work_spans": [
                        application_work_span(
                            "project-design",
                            ["project-type-rules"],
                            work_id="candidate-project-design-run",
                        )
                    ],
                    "verifier_result": "not_run",
                    "command_artifact_ref": None,
                },
            )

            recorded = record_run(repo, receipt_path)
            event = json.loads(
                (repo / recorded["event_path"])
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            inventory = expertise_inventory(repo)
            health = expertise_component_health(
                inventory,
                recent_run_events(repo, window=20)["runs"],
            )
            candidate = inventory["candidates"][0]
            candidate_health = health["candidates"][0]

            self.assertTrue(candidate["immediate_use_allowed"])
            self.assertEqual("available", candidate["runtime_status"])
            self.assertEqual(
                candidate["definition_digest"],
                event["expertise_pack_definition_digests"][
                    "project-design"
                ],
            )
            self.assertEqual(
                candidate["candidate_id"],
                candidate_health["candidate_id"],
            )
            self.assertEqual(1, candidate_health["usage_count"])
            self.assertEqual(
                "프로젝트 타이포그래피 구현",
                candidate_health["recent_runs"][0]["task_label"],
            )

    def test_stale_activation_plan_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-15",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            skill = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "draft/SKILL.md"
            )
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nCandidate changed.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(Exception, "changed after preview"):
                apply_expertise_activation_plan(activation_path, repo)

            self.assertFalse((repo / ".agents/skills/project-design").exists())
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            self.assertEqual([], project["expertise"]["active_pack_paths"])

    def test_reviewed_update_replaces_one_version_and_keeps_a_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-16",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            obsolete_artifact = (
                repo
                / ".agents/skills/project-design/evals/artifacts/"
                "obsolete-case.json"
            )
            write_json(
                obsolete_artifact,
                {
                    "schema_version": "maestro_expertise_case_artifact_v1",
                    "case_id": "obsolete-case",
                    "baseline_observation": "Old observation.",
                    "candidate_observation": "Old observation.",
                    "evidence_refs": ["test:obsolete"],
                },
            )
            old_route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )

            _candidate(
                repo,
                candidate_id="project-design-v2",
                pack_id="project-design",
                version=2,
                guide_id="project-layout-rules",
                guide_text=(
                    "# Project layout rules\n\n"
                    "## Purpose\n\nVerify hierarchy and layout together.\n\n"
                    "## Use when\n\nProject layouts use the approved system.\n\n"
                    "## Inputs\n\nDesign tokens and a rendered screen.\n\n"
                    "## Decision checks\n\n- Verify hierarchy.\n- Verify layout.\n\n"
                    "## Required evidence\n\nBefore and after screenshots.\n\n"
                    "## Reject or stop when\n\nLayout inputs are unavailable.\n\n"
                    "## Verification\n\nInspect the rendered hierarchy.\n\n"
                    "## Counterexamples\n\nDo not apply to backend work.\n"
                ),
            )
            update = build_expertise_update_plan(
                repo,
                candidate_id="project-design-v2",
                approval_ref="held_out_evaluation:eval-16",
            )
            update_path = Path(temporary) / "update.json"
            write_json(update_path, update)
            result = apply_expertise_update_plan(update_path, repo)

            self.assertEqual(2, result["version"])
            self.assertFalse(
                (
                    repo
                    / ".agents/skills/project-design/references/"
                    "project-type-rules.md"
                ).exists()
            )
            self.assertTrue(
                (
                    repo
                    / ".agents/skills/project-design/references/"
                    "project-layout-rules.md"
                ).is_file()
            )
            self.assertFalse(obsolete_artifact.exists())
            snapshot = json.loads(
                (
                    repo
                    / ".agents/skills/project-design/evidence/candidate.json"
                ).read_text(encoding="utf-8")
            )
            publication = json.loads(
                (
                    repo / ".agents/skills/project-design/activation.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual("project-design-v2", snapshot["candidate_id"])
            self.assertEqual("update", publication["action"])
            self.assertIsNotNone(
                publication["previous_definition_digest"]
            )
            self.assertEqual(
                "FAIL",
                validate_route_v2(old_route, repo_path=repo)["status"],
            )
            new_route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )
            self.assertEqual(
                "PASS",
                validate_route_v2(new_route, repo_path=repo)["status"],
            )
            self.assertEqual(
                2,
                new_route["expertise"]["pack_cards"][0]["version"],
            )

    def test_update_requires_exactly_one_version_increment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-17",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            _candidate(
                repo,
                candidate_id="project-design-same-version",
                pack_id="project-design",
                version=1,
            )

            with self.assertRaisesRegex(Exception, "exactly one"):
                build_expertise_update_plan(
                    repo,
                    candidate_id="project-design-same-version",
                    approval_ref="owner_decision:issue-17-update",
                )

    def test_stale_update_plan_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-18",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            _candidate(
                repo,
                candidate_id="project-design-v2",
                pack_id="project-design",
                version=2,
            )
            update = build_expertise_update_plan(
                repo,
                candidate_id="project-design-v2",
                approval_ref="owner_decision:issue-18-update",
            )
            update_path = Path(temporary) / "update.json"
            write_json(update_path, update)
            candidate_guide = (
                repo
                / ".maestro/state/candidates/expertise/project-design-v2"
                / "draft/references/project-type-rules.md"
            )
            candidate_guide.write_text(
                candidate_guide.read_text(encoding="utf-8") + "\nChanged.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(Exception, "changed after preview"):
                apply_expertise_update_plan(update_path, repo)

            active_pack = json.loads(
                (
                    repo / ".agents/skills/project-design/maestro-pack.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(1, active_pack["version"])

    def test_deactivation_preserves_skill_files_and_stops_routing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-19",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            deactivation = build_expertise_deactivation_plan(
                repo,
                expertise_pack_id="project-design",
            )
            deactivation_path = Path(temporary) / "deactivation.json"
            write_json(deactivation_path, deactivation)
            result = apply_expertise_deactivation_plan(
                deactivation_path,
                repo,
            )

            self.assertEqual(
                ".agents/skills/project-design/maestro-pack.json",
                result["preserved_pack_path"],
            )
            self.assertTrue(
                (repo / ".agents/skills/project-design/SKILL.md").is_file()
            )
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            self.assertEqual([], project["expertise"]["active_pack_paths"])
            route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )
            self.assertNotIn(
                "project-design",
                route["expertise"]["selected_pack_ids"],
            )

    def test_doctor_warns_until_active_expertise_is_in_the_git_index(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-20",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)

            before = check_by_id(
                doctor_report(repo),
                "PROJECT_EXPERTISE_GIT_TRACKING",
            )
            self.assertEqual("WARN", before["status"])
            subprocess.run(
                [
                    "git",
                    "add",
                    "--",
                    ".agents/skills/project-design",
                    ".maestro/project.json",
                ],
                cwd=repo,
                check=True,
            )
            after = check_by_id(
                doctor_report(repo),
                "PROJECT_EXPERTISE_GIT_TRACKING",
            )
            self.assertEqual("PASS", after["status"])


if __name__ == "__main__":
    unittest.main()
