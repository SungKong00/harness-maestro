from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.support import (
    apply_fresh_init,
    record_managed_completion_graph,
    write_json,
)
from tests.test_component_candidates import _write_lens_candidate
from tests.test_project_expertise import _candidate
from tests.test_research_workflow import _bundle as research_bundle

from maestro.cli import main
from maestro.candidate_origin import build_expertise_candidate_origin
from maestro.errors import MaestroError
from maestro.evaluation_attestation import _assignment_stage_valid
from maestro.component_candidates import (
    component_evaluation_subject,
    validate_component_candidate,
)
from maestro.coverage_admission import build_task_coverage_admission
from maestro.coverage_projection import build_coverage_projection
from maestro.expertise_adaptation import (
    build_expertise_adaptation_plan,
    validate_task_gap_candidate_lineage,
    validate_expertise_adaptation_plan,
)
from maestro.expertise_lifecycle import (
    build_expertise_export_plan,
    expertise_evaluation_subject,
    validate_expertise_candidate,
)
from maestro.expertise_routing import normalize_route_hints
from maestro.governance import finalize_run
from maestro.observations import (
    attach_run_plan,
    record_stage_observation,
    start_run_observation,
)
from maestro.planning import route_goal_v2
from maestro.research import (
    expected_research_binding,
    validate_research_bundle,
)
from maestro.task_coverage import build_task_coverage
from maestro.util import canonical_json, file_sha256, sha256_text
from maestro.model_policy import MODEL_ROUTE_FIELDS


FINGERPRINT = "0123456789abcdef01234567"


class EvaluationAttestationRouteTests(unittest.TestCase):
    def test_legacy_or_untyped_assignments_cannot_attest_stage_kind(
        self,
    ) -> None:
        legacy_route = {
            "executor": "lens-reviewer",
            "task_class": "semantic-review",
            "risk": "medium",
            "host": "codex",
            "selected_class": "balanced",
            "selected_model": "gpt-5.6-terra",
            "reasoning_effort": "medium",
            "selection_reason": "legacy",
            "escalation_allowed": True,
            "fallback": "legacy",
        }
        self.assertFalse(
            _assignment_stage_valid(
                {"model_route": legacy_route},
                allowed_stage_kinds={"semantic-verification"},
            )
        )
        downgraded = {
            "schema_version": "maestro_stage_model_route_v1",
            "model_route_id": "",
            "execution_unit_id": "verification",
            "stage_kind": "semantic-verification",
            "execution_kind": "model",
            "quality_profile": "pro-quality",
            "executor": "verifier",
            "task_class": "semantic-verification",
            "risk": "medium",
            "host": "codex",
            "selected_class": "economy",
            "selected_model": "gpt-5.6-luna",
            "reasoning_effort": "low",
            "selection_reason": "self-declared downgrade",
            "quality_floor": {
                "acceptable_routes": [
                    {
                        "selected_class": "economy",
                        "reasoning_effort": "low",
                    }
                ],
                "failure_action": "reject-or-reroute",
            },
            "escalation_allowed": True,
            "fallback": "self-declared",
            "fallback_route": None,
        }
        downgraded["model_route_id"] = sha256_text(
            canonical_json(
                {
                    key: value
                    for key, value in downgraded.items()
                    if key != "model_route_id"
                }
            )
        )
        self.assertEqual(MODEL_ROUTE_FIELDS, set(downgraded))
        self.assertFalse(
            _assignment_stage_valid(
                {"model_route": downgraded},
                allowed_stage_kinds={"semantic-verification"},
            )
        )
        self.assertFalse(
            _assignment_stage_valid(
                {
                    "planned_model": "gpt-5.6-terra",
                    "reasoning_effort": "medium",
                },
                allowed_stage_kinds={"semantic-verification"},
            )
        )


def _coverage_item(
    item_id: str,
    *,
    depends_on: list[str] | None = None,
    research: bool = False,
) -> dict[str, object]:
    evidence_type = "external-stable" if research else "project-fact"
    allocation = (
        {
            "kind": "research",
            "target_ref": f"research:researcher/{item_id}",
            "evidence_types": [evidence_type],
            "rationale": "External expert criteria change this decision.",
        }
        if research
        else {
            "kind": "project-fact",
            "target_ref": "project:.maestro/project.json",
            "evidence_types": [evidence_type],
            "rationale": "The project manifest owns this fact.",
        }
    )
    return {
        "item_id": item_id,
        "kind": "decision",
        "summary": f"Resolve {item_id}.",
        "failure_if_omitted": f"{item_id} would be silently omitted.",
        "materiality": "blocking",
        "evidence_types": [evidence_type],
        "source_refs": [],
        "depends_on": list(depends_on or []),
        "allocations": [allocation],
    }


def _coverage(
    repo: Path,
    goal: str,
    items: list[dict[str, object]],
) -> dict[str, object]:
    return build_task_coverage(
        repo,
        goal,
        {
            "discovery_status": "complete",
            "allocation_status": "complete",
            "items": items,
        },
    )


def _coverage_projection(
    repo: Path,
    goal: str,
    coverage: dict[str, object],
    route: dict[str, object],
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for coverage_item in coverage["items"]:
        for allocation in coverage_item["allocations"]:
            kind = allocation["kind"]
            if kind == "project-fact":
                evidence_ref = allocation["target_ref"].split(
                    ":",
                    1,
                )[1].split("#", 1)[0]
                authority_ref = "repository-state"
            elif kind in {"checker", "runtime-verification"}:
                evidence_ref = allocation["target_ref"]
                authority_ref = f"plan:{route['plan_id']}"
            else:
                continue
            items.append(
                {
                    "item_id": coverage_item["item_id"],
                    "target_ref": allocation["target_ref"],
                    "evidence_ref": evidence_ref,
                    "authority_ref": authority_ref,
                    "reason": "Bind the exact projected evidence.",
                }
            )
    return build_coverage_projection(
        repo,
        goal=goal,
        coverage=coverage,
        plan=route,
        draft={"items": items},
    )


def _unit(
    unit_id: str,
    item_ids: list[str],
    *,
    surface: str = "none",
    change_kind: str = "no-change",
    target_ref: str | None = None,
    depends_on: list[str] | None = None,
    evidence_ref: str | None = None,
) -> dict[str, object]:
    return {
        "unit_id": unit_id,
        "coverage_item_ids": item_ids,
        "surface": surface,
        "change_kind": change_kind,
        "target_ref": target_ref,
        "depends_on": list(depends_on or []),
        "change_set_id": None,
        "evidence_refs": [
            evidence_ref
            or (
                f"research:researcher/{item_ids[0]}"
                if surface != "none"
                else "project:.maestro/project.json"
            )
        ],
    }


def _record_authoring(
    repo: Path,
    root: Path,
    evidence_refs: list[str],
    *,
    run_id: str,
) -> None:
    plan = route_goal_v2(
        "Author a frozen expertise candidate",
        "medium",
        intent="implementation",
        repo_path=repo,
    )
    plan_path = root / f"{run_id}-plan.json"
    write_json(plan_path, plan)
    started = start_run_observation(
        repo,
        run_id=run_id,
        task_label="후보 작성",
        plan_path=plan_path,
        execution_binding={
            "schema_version": "maestro_execution_binding_v1",
            "mode": "explicit_fallback",
            "reason": "capability_unavailable",
            "evidence": "The deterministic fixture records bounded candidate work.",
        },
    )
    for assignment in plan["assignments"]:
        refs = [f"authoring:{assignment['assignment_id']}"]
        if assignment["mutation_owner"]:
            refs = list(evidence_refs)
        record_stage_observation(
            repo,
            observation_id=started["observation_id"],
            run_id=run_id,
            assignment_id=assignment["assignment_id"],
            status="completed",
            evidence_source="deterministic_command",
            evidence_refs=refs,
        )
    record_managed_completion_graph(
        repo,
        observation_id=started["observation_id"],
        run_id=run_id,
        plan=plan,
        prefix=f"{run_id}-completion",
    )
    finalize_run(
        repo,
        run_id=run_id,
        observation_id=started["observation_id"],
        outcome="completed",
        evidence_refs=evidence_refs,
        verifier_result=(
            "passed"
            if any(
                assignment["executor_id"] == "verifier"
                for assignment in plan["assignments"]
            )
            else "not_run"
        ),
        command_artifact_ref=evidence_refs[0],
    )


def _start_evaluation(
    repo: Path,
    root: Path,
    *,
    run_id: str,
) -> tuple[str, dict[str, object]]:
    plan = route_goal_v2(
        "Read-only evaluation of a frozen expertise candidate",
        "medium",
        intent="review",
        repo_path=repo,
    )
    plan_path = root / f"{run_id}-plan.json"
    write_json(plan_path, plan)
    started = start_run_observation(
        repo,
        run_id=run_id,
        task_label="독립 후보 평가",
        plan_path=plan_path,
    )
    return started["observation_id"], plan


def _finish_evaluation(
    repo: Path,
    *,
    observation_id: str,
    run_id: str,
    plan: dict[str, object],
    evidence_refs: list[str],
) -> None:
    for assignment in plan["assignments"]:
        record_stage_observation(
            repo,
            observation_id=observation_id,
            run_id=run_id,
            assignment_id=assignment["assignment_id"],
            status="completed",
            evidence_source="codex_app_server",
            evidence_refs=evidence_refs,
            requested_model=assignment["model_route"]["selected_model"],
            requested_reasoning_effort=assignment["model_route"][
                "reasoning_effort"
            ],
            actual_model=assignment["model_route"]["selected_model"],
            model_evidence="complete",
            reroutes=[],
            duration_ms=1.0,
        )
    record_managed_completion_graph(
        repo,
        observation_id=observation_id,
        run_id=run_id,
        plan=plan,
        prefix=f"{run_id}-completion",
    )
    finalize_run(
        repo,
        run_id=run_id,
        observation_id=observation_id,
        outcome="completed",
        evidence_refs=evidence_refs,
        verifier_result=(
            "passed"
            if any(
                assignment["executor_id"] == "verifier"
                for assignment in plan["assignments"]
            )
            else "not_run"
        ),
        command_artifact_ref=evidence_refs[0],
    )


class ExpertiseAdaptationPlanTests(unittest.TestCase):
    def test_checker_admission_requires_a_registered_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Verify one exact runtime proof"
            item = _coverage_item("runtime-proof")
            item["evidence_types"] = ["runtime-verification"]
            item["allocations"] = [
                {
                    "kind": "checker",
                    "target_ref": "checker:verifier/test-suite",
                    "evidence_types": ["runtime-verification"],
                    "rationale": "Run the registered project test suite.",
                }
            ]
            coverage = _coverage(repo, goal, [item])
            route = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )

            ready = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
                coverage_projection=_coverage_projection(
                    repo,
                    goal,
                    coverage,
                    route,
                ),
            )
            invented = copy.deepcopy(coverage)
            invented["items"][0]["allocations"][0]["target_ref"] = (
                "checker:verifier/invented-check"
            )
            invented["coverage_id"] = ""
            invented["coverage_id"] = sha256_text(
                canonical_json(invented)
            )
            rejected = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=invented,
                plan=route,
            )

            self.assertEqual("READY", ready["status"])
            self.assertEqual("INVALID", rejected["status"])
            self.assertIn(
                "TASK_COVERAGE_TARGET_UNRESOLVED",
                {issue["code"] for issue in rejected["issues"]},
            )

    def test_malformed_admission_and_adaptation_inputs_fail_typed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Reject malformed orchestration lists"
            coverage = _coverage(
                repo,
                goal,
                [_coverage_item("project-boundary")],
            )
            route = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
                projected_item_ids=7,
            )
            source_admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
            )

            self.assertEqual("INVALID", admission["status"])
            self.assertIn(
                "TASK_COVERAGE_PROJECTION_IDS_INVALID",
                {issue["code"] for issue in admission["issues"]},
            )
            with self.assertRaises(MaestroError) as raised:
                build_expertise_adaptation_plan(
                    repo,
                    goal=goal,
                    coverage=coverage,
                    source_route=route,
                    source_admission=source_admission,
                    draft={"units": 7},
                )
            self.assertEqual(
                "EXPERTISE_ADAPTATION_DRAFT_INVALID",
                raised.exception.code,
            )

    def test_cli_plans_validates_and_admits_complete_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Project and admit every declared requirement"
            coverage = _coverage(
                repo,
                goal,
                [_coverage_item("project-boundary")],
            )
            route = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            draft = {
                "units": [
                    _unit("project-unit", ["project-boundary"]),
                ],
            }
            coverage_path = root / "coverage.json"
            route_path = root / "route.json"
            draft_path = root / "adaptation-draft.json"
            plan_path = root / "adaptation.json"
            admission_path = root / "source-admission.json"
            projection_path = root / "coverage-projection.json"
            write_json(coverage_path, coverage)
            write_json(route_path, route)
            write_json(draft_path, draft)
            source_admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
            )
            write_json(admission_path, source_admission)
            write_json(
                projection_path,
                _coverage_projection(repo, goal, coverage, route),
            )

            output = StringIO()
            with redirect_stdout(output):
                planned_exit = main(
                    [
                        "expertise",
                        "plan-adaptation",
                        "--repo",
                        str(repo),
                        "--goal",
                        goal,
                        "--coverage",
                        str(coverage_path),
                        "--source-route",
                        str(route_path),
                        "--source-admission",
                        str(admission_path),
                        "--draft",
                        str(draft_path),
                        "--json",
                    ]
                )
            plan = json.loads(output.getvalue())
            write_json(plan_path, plan)

            with redirect_stdout(StringIO()):
                validate_exit = main(
                    [
                        "expertise",
                        "validate-adaptation",
                        "--repo",
                        str(repo),
                        "--goal",
                        goal,
                        "--coverage",
                        str(coverage_path),
                        "--source-route",
                        str(route_path),
                        "--source-admission",
                        str(admission_path),
                        "--plan",
                        str(plan_path),
                        "--json",
                    ]
                )
                admission_exit = main(
                    [
                        "admit-coverage",
                        "--repo",
                        str(repo),
                        "--goal",
                        goal,
                        "--coverage",
                        str(coverage_path),
                        "--plan",
                        str(route_path),
                        "--coverage-projection",
                        str(projection_path),
                        "--json",
                    ]
                )

            self.assertEqual(0, planned_exit)
            self.assertEqual(0, validate_exit)
            self.assertEqual(0, admission_exit)

    def test_discovers_all_units_before_parallel_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Allocate every discovered expertise gap"
            items = [
                _coverage_item("area-one"),
                _coverage_item("area-two"),
                _coverage_item("area-three"),
                _coverage_item("area-four"),
                _coverage_item(
                    "area-five",
                    depends_on=["area-one"],
                ),
            ]
            coverage = _coverage(repo, goal, items)
            route = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            units = [
                _unit(f"unit-{index}", [item["item_id"]])
                for index, item in enumerate(items[:4], start=1)
            ]
            units.append(
                _unit(
                    "unit-five",
                    ["area-five"],
                    depends_on=["unit-1"],
                )
            )
            source_admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
            )

            plan = build_expertise_adaptation_plan(
                repo,
                goal=goal,
                coverage=coverage,
                source_route=route,
                source_admission=source_admission,
                draft={
                    "units": units,
                },
            )

            self.assertEqual(5, len(plan["units"]))
            self.assertEqual(
                ["unit-1", "unit-2", "unit-3", "unit-4"],
                plan["parallel_groups"][0],
            )
            self.assertEqual(["unit-five"], plan["parallel_groups"][1])
            self.assertEqual(
                "PASS",
                validate_expertise_adaptation_plan(
                    plan,
                    coverage=coverage,
                    source_route=route,
                    source_admission=source_admission,
                    goal=goal,
                    repo_path=repo,
                )["status"],
            )

    def test_pack_extraction_is_complex_and_never_same_task_eligible(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Extract selected Guides into a new expert Pack"
            coverage = _coverage(
                repo,
                goal,
                [_coverage_item("selected-guide-boundary", research=True)],
            )
            route = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            source_admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
            )

            plan = build_expertise_adaptation_plan(
                repo,
                goal=goal,
                coverage=coverage,
                source_route=route,
                source_admission=source_admission,
                draft={
                    "units": [
                        _unit(
                            "extract-guides",
                            ["selected-guide-boundary"],
                            surface="expertise-pack",
                            change_kind="pack-extraction",
                            target_ref="pack:extracted-expertise",
                        )
                        | {"change_set_id": "extract-guides"},
                    ],
                },
            )

            unit = plan["units"][0]
            self.assertEqual(
                "maestro-expertise-builder",
                unit["candidate_builder"],
            )
            self.assertTrue(unit["research_required"])
            self.assertFalse(unit["same_task_eligible"])
            self.assertEqual("extract-guides", unit["change_set_id"])
            self.assertEqual(
                "PASS",
                validate_expertise_adaptation_plan(
                    plan,
                    coverage=coverage,
                    source_route=route,
                    source_admission=source_admission,
                    goal=goal,
                    repo_path=repo,
                )["status"],
            )

    def test_missing_discovered_item_is_rejected_instead_of_truncated(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Do not truncate adaptation work"
            coverage = _coverage(
                repo,
                goal,
                [
                    _coverage_item("first-area"),
                    _coverage_item("second-area"),
                ],
            )
            route = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            source_admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
            )

            with self.assertRaisesRegex(Exception, "Every discovered"):
                build_expertise_adaptation_plan(
                    repo,
                    goal=goal,
                    coverage=coverage,
                    source_route=route,
                    source_admission=source_admission,
                    draft={
                        "units": [
                            _unit("only-first", ["first-area"]),
                        ],
                    },
                )

    def test_admission_distinguishes_projection_from_route_gaps(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Implement a bounded project fact"
            coverage = _coverage(
                repo,
                goal,
                [_coverage_item("project-boundary")],
            )
            route = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )

            pending = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
            )
            ready = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
                projected_item_ids=["project-boundary"],
            )
            typed_ready = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=route,
                coverage_projection=_coverage_projection(
                    repo,
                    goal,
                    coverage,
                    route,
                ),
            )

            self.assertEqual("PROJECTION_REQUIRED", pending["status"])
            self.assertEqual("GAPS", ready["status"])
            self.assertEqual("legacy-id-unverified", ready["gaps"][0]["reason"])
            self.assertEqual("READY", typed_ready["status"])
            self.assertEqual("NONE", typed_ready["execution_authority"])


class TaskGapCandidateTests(unittest.TestCase):
    def _write_candidate(
        self,
        repo: Path,
        root: Path,
        goal: str,
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        str,
    ]:
        coverage = _coverage(
            repo,
            goal,
            [_coverage_item("expert-rules", research=True)],
        )
        source_route = route_goal_v2(
            goal,
            "medium",
            intent="implementation",
            repo_path=repo,
        )
        source_admission = build_task_coverage_admission(
            repo,
            goal=goal,
            coverage=coverage,
            plan=source_route,
        )
        adaptation = build_expertise_adaptation_plan(
            repo,
            goal=goal,
            coverage=coverage,
            source_route=source_route,
            source_admission=source_admission,
            draft={
                "units": [
                    _unit(
                        "expert-pack",
                        ["expert-rules"],
                        surface="expertise-pack",
                        change_kind="new-pack",
                        target_ref="pack:project-design",
                    )
                ],
            },
        )
        bundle = research_bundle(goal)
        bundle["depth"] = "deep"
        for packet in bundle["packets"]:
            packet["depth"] = "deep"
        bundle["request_binding"] = expected_research_binding(
            goal,
            {
                "selected_pack_ids": [],
                "selected_guide_ids": [],
                "pack_definition_digests": {},
                "research_requirement": {"mode": "discover"},
            },
        )
        research_validation = validate_research_bundle(
            bundle,
            repo_path=repo,
        )
        self.assertEqual("PASS", research_validation["status"])
        research_digest = research_validation["artifact_digest"]

        _candidate(
            repo,
            candidate_id="task-gap-design",
            pack_id="project-design",
            skill_id="project-design",
            standalone=True,
            generation_mode="task-gap",
            signal_fingerprint=adaptation["signal_fingerprint"],
            component_change={
                "kind": "new-pack",
                "target_guide_id": None,
            },
        )
        candidate_root = (
            repo
            / ".maestro/state/candidates/expertise/task-gap-design"
        )
        write_json(
            repo
            / ".maestro/state/candidate-origins/expertise/"
            "task-gap-design.json",
            build_expertise_candidate_origin(
                namespace="expertise",
                candidate_id="task-gap-design",
                subject_ref="pack:project-design",
                mode="task-gap",
                signal_fingerprint=adaptation["signal_fingerprint"],
                goal_digest=coverage["goal_digest"],
                adaptation_plan_id=adaptation["plan_id"],
                source_admission_id=source_admission["admission_id"],
                unit_id="expert-pack",
                change_set_id=None,
            ),
        )
        write_json(
            candidate_root / "evidence/task-coverage.json",
            coverage,
        )
        write_json(
            candidate_root / "evidence/adaptation-plan.json",
            adaptation,
        )
        write_json(
            candidate_root / "evidence/source-route.json",
            source_route,
        )
        write_json(
            candidate_root / "evidence/source-admission.json",
            source_admission,
        )
        write_json(
            candidate_root / "evidence/research-bundle.json",
            bundle,
        )
        candidate_path = candidate_root / "candidate.json"
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate["schema_version"] = "maestro_expertise_candidate_v2"
        candidate["coverage"] = {
            "decision_map_path": "evidence/decision-map.json",
            "discovery_complete": True,
            "allocation_complete": True,
        }
        candidate["adaptation"] = {
            "schema_version": "maestro_task_gap_adaptation_v1",
            "coverage_ref": {
                "path": "evidence/task-coverage.json",
                "sha256": file_sha256(
                    candidate_root / "evidence/task-coverage.json"
                ),
            },
            "plan_ref": {
                "path": "evidence/adaptation-plan.json",
                "sha256": file_sha256(
                    candidate_root / "evidence/adaptation-plan.json"
                ),
            },
            "source_route_ref": {
                "path": "evidence/source-route.json",
                "sha256": file_sha256(
                    candidate_root / "evidence/source-route.json"
                ),
            },
            "source_admission_ref": {
                "path": "evidence/source-admission.json",
                "sha256": file_sha256(
                    candidate_root / "evidence/source-admission.json"
                ),
            },
            "unit_id": "expert-pack",
            "authoring_research_ref": {
                "path": "evidence/research-bundle.json",
                "sha256": file_sha256(
                    candidate_root / "evidence/research-bundle.json"
                ),
            },
        }
        write_json(candidate_path, candidate)
        write_json(
            candidate_root / "evidence/decision-map.json",
            {
                "schema_version": "maestro_expertise_decision_map_v1",
                "candidate_id": "task-gap-design",
                "decision_areas": [
                    {
                        "area_id": "expert-rules",
                        "decision": "Apply the researched expert rule.",
                        "failure_if_omitted": "The writer would improvise.",
                        "materiality": "blocking",
                        "evidence_types": ["external-stable"],
                        "evidence_refs": [
                            f"research-bundle:{research_digest}"
                        ],
                        "disposition": {
                            "kind": "proposed-guide",
                            "target_id": "project-type-rules",
                            "rationale": "The Guide owns the reusable decision.",
                        },
                    }
                ],
            },
        )

        subject = expertise_evaluation_subject(
            repo,
            "task-gap-design",
        )
        authoring_run = "task-gap-author"
        _record_authoring(
            repo,
            root,
            subject["evidence_refs"],
            run_id=authoring_run,
        )
        evaluation_run = "task-gap-evaluator"
        observation_id, evaluation_plan = _start_evaluation(
            repo,
            root,
            run_id=evaluation_run,
        )
        quality_path = candidate_root / "evals/quality.json"
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        quality["schema_version"] = "maestro_expertise_quality_eval_v2"
        quality["subject"] = {
            "candidate_digest": subject["candidate_digest"],
            "cases_sha256": subject["cases_sha256"],
        }
        quality["evaluator"] = {
            "kind": "fresh-context",
            "authoring_run_ref": authoring_run,
            "evaluation_run_ref": evaluation_run,
            "observation_id": observation_id,
        }
        write_json(quality_path, quality)
        _finish_evaluation(
            repo,
            observation_id=observation_id,
            run_id=evaluation_run,
            plan=evaluation_plan,
            evidence_refs=[
                *subject["evidence_refs"],
                f"candidate-quality:{file_sha256(quality_path)}",
            ],
        )
        return coverage, source_route, research_digest

    def test_real_research_and_independent_evaluation_enable_one_reroute(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Build a frobnicator with reusable expert rules"
            coverage, source_route, _research_digest = self._write_candidate(
                repo,
                root,
                goal,
            )

            validation = validate_expertise_candidate(
                repo,
                "task-gap-design",
            )
            corrected = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                route_hints=normalize_route_hints(
                    explicit_pack_id="project-design",
                    route_attempt=2,
                    prior_plan_id=source_route["plan_id"],
                    prior_source_route_digest=source_route[
                        "source_route_digest"
                    ],
                ),
                prior_route_plan=source_route,
            )
            admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=corrected,
                candidate_ids=["task-gap-design"],
            )

            self.assertEqual("PASS", validation["status"])
            self.assertEqual("READY", admission["status"], admission)
            self.assertEqual(
                ["task-gap-design"],
                admission["compiled_candidate_ids"],
            )
            self.assertEqual(
                ["expert-rules"],
                admission["compiled_item_ids"],
            )
            with self.assertRaises(MaestroError) as raised:
                build_expertise_export_plan(
                    repo,
                    candidate_id="task-gap-design",
                )
            self.assertEqual(
                "EXPERTISE_EXPORT_PORTABLE_ATTESTATION_UNSUPPORTED",
                raised.exception.code,
            )
            corrected_path = root / "corrected-route.json"
            write_json(corrected_path, corrected)
            source_path = root / "source-route.json"
            write_json(source_path, source_route)
            initial = start_run_observation(
                repo,
                run_id="initial-route-observation",
                task_label="초기 경로",
                plan_path=source_path,
            )
            with self.assertRaises(MaestroError) as attach_conflict:
                attach_run_plan(
                    repo,
                    observation_id=initial["observation_id"],
                    run_id="initial-route-observation",
                    plan_path=corrected_path,
                )
            self.assertEqual(
                "RUN_OBSERVATION_PLAN_CONFLICT",
                attach_conflict.exception.code,
            )
            corrected_observation = start_run_observation(
                repo,
                run_id="corrected-route-one",
                task_label="첫 보정 경로",
                plan_path=corrected_path,
            )
            receipt_path = (
                repo
                / ".maestro/state/route-corrections"
                / f"{source_route['plan_id']}.json"
            )
            receipt = json.loads(
                receipt_path.read_text(encoding="utf-8")
            )
            write_json(
                receipt_path,
                {
                    "schema_version": (
                        "maestro_corrected_route_consumption_v1"
                    ),
                    "prior_plan_id": receipt["prior_plan_id"],
                    "prior_source_route_digest": receipt[
                        "prior_source_route_digest"
                    ],
                    "corrected_plan_id": receipt["corrected_plan_id"],
                },
            )
            with self.assertRaises(MaestroError) as legacy_consumed:
                start_run_observation(
                    repo,
                    run_id="corrected-route-reuse",
                    task_label="다른 관찰의 같은 보정 경로",
                    plan_path=corrected_path,
                )
            self.assertEqual(
                "EXPERTISE_CORRECTED_ROUTE_ALREADY_CONSUMED",
                legacy_consumed.exception.code,
            )
            start_run_observation(
                repo,
                run_id="corrected-route-one",
                task_label="첫 보정 경로",
                plan_path=corrected_path,
            )
            migrated_receipt = json.loads(
                receipt_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                "maestro_corrected_route_consumption_v2",
                migrated_receipt["schema_version"],
            )
            self.assertEqual(
                corrected_observation["observation_id"],
                migrated_receipt["consumer_observation_id"],
            )
            sibling = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                route_hints=normalize_route_hints(
                    explicit_pack_id="software-engineering",
                    route_attempt=2,
                    prior_plan_id=source_route["plan_id"],
                    prior_source_route_digest=source_route[
                        "source_route_digest"
                    ],
                ),
                prior_route_plan=source_route,
            )
            sibling_path = root / "sibling-corrected-route.json"
            write_json(sibling_path, sibling)
            with self.assertRaises(MaestroError) as consumed:
                start_run_observation(
                    repo,
                    run_id="corrected-route-two",
                    task_label="두 번째 보정 경로",
                    plan_path=sibling_path,
                )
            self.assertEqual(
                "EXPERTISE_CORRECTED_ROUTE_ALREADY_CONSUMED",
                consumed.exception.code,
            )

    def test_origin_binds_namespace_subject_and_schema_floor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Build a frobnicator with reusable expert rules"
            self._write_candidate(repo, root, goal)
            origin_path = (
                repo
                / ".maestro/state/candidate-origins/expertise/"
                "task-gap-design.json"
            )
            wrong = json.loads(origin_path.read_text(encoding="utf-8"))
            wrong["subject_ref"] = "pack:another-pack"
            wrong["origin_id"] = ""
            wrong["origin_id"] = sha256_text(canonical_json(wrong))
            write_json(origin_path, wrong)

            mismatch = validate_expertise_candidate(
                repo,
                "task-gap-design",
            )
            self.assertIn(
                "EXPERTISE_CANDIDATE_ORIGIN_MISMATCH",
                {issue["code"] for issue in mismatch["issues"]},
            )

            candidate_root = (
                repo
                / ".maestro/state/candidates/expertise/task-gap-design"
            )
            candidate_path = candidate_root / "candidate.json"
            candidate = json.loads(
                candidate_path.read_text(encoding="utf-8")
            )
            candidate["schema_version"] = "maestro_expertise_candidate_v1"
            candidate.pop("coverage")
            candidate.pop("adaptation")
            candidate["generation"] = {
                "mode": "user-requested",
                "signal_fingerprint": None,
            }
            write_json(candidate_path, candidate)
            for relative in (
                "evidence/task-coverage.json",
                "evidence/adaptation-plan.json",
                "evidence/source-route.json",
                "evidence/source-admission.json",
            ):
                (candidate_root / relative).unlink()
            downgraded = validate_expertise_candidate(
                repo,
                "task-gap-design",
            )
            self.assertIn(
                "EXPERTISE_CANDIDATE_ORIGIN_MISMATCH",
                {issue["code"] for issue in downgraded["issues"]},
            )

    def test_complex_candidate_lineage_is_valid_but_not_same_task_routable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Merge expert packs without bypassing atomic approval"
            self._write_candidate(repo, root, goal)
            candidate_root = (
                repo
                / ".maestro/state/candidates/expertise/task-gap-design"
            )
            plan_path = candidate_root / "evidence/adaptation-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            unit = plan["units"][0]
            unit["change_kind"] = "pack-merge"
            unit["change_set_id"] = "merge-design-packs"
            unit["same_task_eligible"] = False
            plan["signal_fingerprint"] = sha256_text(
                canonical_json(
                    {
                        "coverage_id": plan["coverage_id"],
                        "source_route_plan_id": plan[
                            "source_route_plan_id"
                        ],
                        "source_admission_id": plan[
                            "source_admission_id"
                        ],
                        "units": plan["units"],
                    }
                )
            )[:24]
            plan_payload = copy.deepcopy(plan)
            plan_payload.pop("plan_id")
            plan["plan_id"] = sha256_text(canonical_json(plan_payload))
            write_json(plan_path, plan)

            candidate_path = candidate_root / "candidate.json"
            candidate = json.loads(
                candidate_path.read_text(encoding="utf-8")
            )
            candidate["component_change"] = {
                "kind": "pack-merge",
                "target_guide_id": None,
                "change_set_id": "merge-design-packs",
            }
            candidate["generation"]["signal_fingerprint"] = plan[
                "signal_fingerprint"
            ]
            candidate["adaptation"]["plan_ref"]["sha256"] = file_sha256(
                plan_path
            )
            write_json(candidate_path, candidate)

            issues, binding = validate_task_gap_candidate_lineage(
                repo,
                candidate_root,
                candidate,
            )

            self.assertEqual([], issues)
            self.assertIsNotNone(binding)
            self.assertFalse(binding["same_task_eligible"])

    def test_missing_research_or_observed_evaluation_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Build a frobnicator with reusable expert rules"
            self._write_candidate(repo, root, goal)
            candidate_root = (
                repo
                / ".maestro/state/candidates/expertise/task-gap-design"
            )
            quality_path = candidate_root / "evals/quality.json"
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            quality["evaluator"]["observation_id"] = "0" * 32
            write_json(quality_path, quality)
            research_path = candidate_root / "evidence/research-bundle.json"
            research = json.loads(research_path.read_text(encoding="utf-8"))
            research["status"] = "insufficient"
            write_json(research_path, research)

            result = validate_expertise_candidate(
                repo,
                "task-gap-design",
            )
            codes = {issue["code"] for issue in result["issues"]}

            self.assertEqual("FAIL", result["status"])
            self.assertIn(
                "EXPERTISE_ADAPTATION_ARTIFACT_INVALID",
                codes,
            )
            self.assertIn(
                "EXPERTISE_QUALITY_ATTESTATION_INVALID",
                codes,
            )


class TaskGapLensCandidateTests(unittest.TestCase):
    def test_lens_candidate_requires_real_results_but_never_routes_same_task(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Add an indexability verdict boundary"
            coverage = _coverage(
                repo,
                goal,
                [_coverage_item("indexability-boundary", research=True)],
            )
            source_route = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            source_admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=source_route,
            )
            adaptation = build_expertise_adaptation_plan(
                repo,
                goal=goal,
                coverage=coverage,
                source_route=source_route,
                source_admission=source_admission,
                draft={
                    "units": [
                        _unit(
                            "indexability-lens",
                            ["indexability-boundary"],
                            surface="lens",
                            change_kind="lens-candidate",
                            target_ref="lens:indexability",
                        )
                    ],
                },
            )
            candidate_root = _write_lens_candidate(
                repo,
                candidate_id="indexability",
            )
            write_json(
                repo
                / ".maestro/state/candidate-origins/components/"
                "indexability.json",
                build_expertise_candidate_origin(
                    namespace="components",
                    candidate_id="indexability",
                    subject_ref="lens:indexability",
                    mode="task-gap",
                    signal_fingerprint=adaptation["signal_fingerprint"],
                    goal_digest=coverage["goal_digest"],
                    adaptation_plan_id=adaptation["plan_id"],
                    source_admission_id=source_admission["admission_id"],
                    unit_id="indexability-lens",
                    change_set_id=None,
                ),
            )
            write_json(
                candidate_root / "evidence/task-coverage.json",
                coverage,
            )
            write_json(
                candidate_root / "evidence/adaptation-plan.json",
                adaptation,
            )
            write_json(
                candidate_root / "evidence/source-route.json",
                source_route,
            )
            write_json(
                candidate_root / "evidence/source-admission.json",
                source_admission,
            )
            candidate_path = candidate_root / "candidate.json"
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["schema_version"] = (
                "maestro_registry_component_candidate_v2"
            )
            candidate["generation"] = {
                "mode": "task-gap",
                "signal_fingerprint": adaptation["signal_fingerprint"],
                "unit_id": "indexability-lens",
            }
            for field, path in (
                ("coverage_ref", "evidence/task-coverage.json"),
                ("adaptation_ref", "evidence/adaptation-plan.json"),
                ("source_route_ref", "evidence/source-route.json"),
                (
                    "source_admission_ref",
                    "evidence/source-admission.json",
                ),
            ):
                candidate[field] = {
                    "path": path,
                    "sha256": file_sha256(candidate_root / path),
                }
            candidate["evaluation_result_ref"] = {
                "path": "evals/results.json",
                "sha256": "0" * 64,
            }
            write_json(candidate_path, candidate)

            subject = component_evaluation_subject(repo, "indexability")
            authoring_run = "task-gap-lens-author"
            _record_authoring(
                repo,
                root,
                subject["evidence_refs"],
                run_id=authoring_run,
            )
            evaluation_run = "task-gap-lens-evaluator"
            observation_id, evaluation_plan = _start_evaluation(
                repo,
                root,
                run_id=evaluation_run,
            )
            cases = json.loads(
                (candidate_root / "evals/cases.json").read_text(
                    encoding="utf-8"
                )
            )
            results = {
                "schema_version": "maestro_component_evaluation_results_v1",
                "candidate_id": "indexability",
                "definition_sha256": subject["definition_sha256"],
                "cases_sha256": subject["cases_sha256"],
                "evaluator": {
                    "kind": "fresh-context",
                    "authoring_run_ref": authoring_run,
                    "evaluation_run_ref": evaluation_run,
                    "observation_id": observation_id,
                },
                "results": [
                    {
                        "case_id": case["case_id"],
                        "observed_outcome": case["expected_outcome"],
                        "evidence_refs": ["evaluation:observed-outcome"],
                        "forbidden_behavior_results": [
                            {
                                "behavior": behavior,
                                "observed": False,
                                "evidence_ref": "evaluation:forbidden-check",
                            }
                            for behavior in case["forbidden_behaviors"]
                        ],
                        "verdict": "pass",
                    }
                    for case in cases["cases"]
                ],
            }
            write_json(candidate_root / "evals/results.json", results)
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["evaluation_result_ref"]["sha256"] = file_sha256(
                candidate_root / "evals/results.json"
            )
            write_json(candidate_path, candidate)
            _finish_evaluation(
                repo,
                observation_id=observation_id,
                run_id=evaluation_run,
                plan=evaluation_plan,
                evidence_refs=[
                    *subject["evidence_refs"],
                    (
                        "component-results:"
                        f"{file_sha256(candidate_root / 'evals/results.json')}"
                    ),
                ],
            )

            validation = validate_component_candidate(
                repo,
                "indexability",
            )

            self.assertEqual("PASS", validation["status"])
            self.assertFalse(validation["promotion_available"])
            unit = adaptation["units"][0]
            self.assertFalse(unit["same_task_eligible"])

            results["evaluator"]["observation_id"] = "0" * 32
            write_json(candidate_root / "evals/results.json", results)
            candidate["evaluation_result_ref"]["sha256"] = file_sha256(
                candidate_root / "evals/results.json"
            )
            write_json(candidate_path, candidate)
            failed = validate_component_candidate(repo, "indexability")
            self.assertIn(
                "COMPONENT_EVALUATION_ATTESTATION_INVALID",
                {issue["code"] for issue in failed["issues"]},
            )


if __name__ == "__main__":
    unittest.main()
