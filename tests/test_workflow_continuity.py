from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import ROOT, apply_fresh_init
from tests.test_assignment_contracts import (
    baseline_for,
    completed_terminal_packet,
)
from tests.test_decision_workflow import _bundle, _packets
from tests.test_research_workflow import _bundle as _research_bundle

from maestro.assignment_contracts import (
    project_assignment_input,
    validate_assignment_packet,
)
from maestro.cli import parser
from maestro.coverage_admission import build_task_coverage_admission
from maestro.coverage_projection import build_coverage_projection
from maestro.decisions import (
    build_decision_plan,
    build_execution_plan,
    validate_decision_bundle,
    validate_execution_plan,
    validate_specialist_packet,
)
from maestro.errors import MaestroError
from maestro.expertise_adaptation import build_expertise_adaptation_plan
from maestro.expertise import load_expertise_catalog
from maestro.expertise_routing import normalize_route_hints
from maestro.expertise_work import (
    build_expertise_work_closure,
    build_expertise_work_plan,
    validate_expertise_work_closure,
    validate_expertise_work_plan,
)
from maestro.planning import route_goal_v2
from maestro.research import expected_research_binding
from maestro.registry import route_goal
from maestro.task_coverage import build_task_coverage
from maestro.util import canonical_json, file_sha256, sha256_text


def _coverage_item(
    item_id: str,
    *,
    allocation_kind: str,
    target_ref: str,
    evidence_type: str,
    depends_on: list[str] | None = None,
) -> dict[str, object]:
    return {
        "item_id": item_id,
        "kind": "decision",
        "summary": f"Resolve {item_id}.",
        "failure_if_omitted": f"{item_id} would be omitted.",
        "materiality": "blocking",
        "evidence_types": [evidence_type],
        "source_refs": [],
        "depends_on": list(depends_on or []),
        "allocations": [
            {
                "kind": allocation_kind,
                "target_ref": target_ref,
                "evidence_types": [evidence_type],
                "rationale": "This exact allocation owns the judgment.",
            }
        ],
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


def _work_packet(
    work_plan: dict[str, object],
    batch: dict[str, object],
    *,
    status: str = "completed",
) -> dict[str, object]:
    packet = {
        "schema_version": "maestro_expertise_work_packet_v1",
        "packet_digest": "",
        "work_plan_id": work_plan["work_plan_id"],
        "batch_id": batch["batch_id"],
        "status": status,
        "coverage_pair_ids": batch["coverage_pair_ids"],
        "criteria_applied": (
            ["Apply the selected Guide criterion."]
            if status == "completed"
            else []
        ),
        "recommendations": ["Keep the responsibility boundary explicit."],
        "evidence_refs": ["project:README.md"] if status == "completed" else [],
        "conflicts": [],
        "unresolved": [],
        "writes_performed": False,
    }
    packet["packet_digest"] = sha256_text(canonical_json(packet))
    return packet


class DecisionContinuityTests(unittest.TestCase):
    def test_technology_choice_cannot_bypass_decision_first(self) -> None:
        with self.assertRaises(MaestroError) as raised:
            route_goal(
                "Choose between PostgreSQL and DynamoDB and implement the winner",
                "medium",
                intent="implementation",
            )
        self.assertEqual("DECISION_WORKFLOW_REQUIRED", raised.exception.code)

    def test_enactment_authorization_reaches_assignment_projection(self) -> None:
        goal = "Review architecture then implement the approved change"
        plan = build_decision_plan(ROOT, goal, "medium")
        packets = _packets(plan)
        bundle = _bundle(plan, packets)
        execution = build_execution_plan(
            ROOT,
            plan,
            bundle,
            packets,
            authorization_source="prior_explicit_request",
        )
        assignment_id = execution["route_plan"]["entry_assignments"][0]
        projection = project_assignment_input(
            ROOT,
            execution,
            assignment_id,
            baseline_for(execution["route_plan"]),
        )

        self.assertEqual("PASS", validate_execution_plan(
            execution,
            repo_path=ROOT,
        )["status"])
        self.assertEqual("PASS", projection["status"])
        self.assertEqual(
            bundle["bundle_digest"],
            projection["input"]["execution_authorization"][
                "decision_bundle_digest"
            ],
        )

    def test_structured_expertise_hint_survives_decide_and_enact(self) -> None:
        goal = "Assess security boundaries then implement the approved change"
        hints = normalize_route_hints(
            work_kinds=["security-sensitive"],
            affected_paths=["src/maestro"],
        )
        plan = build_decision_plan(
            ROOT,
            goal,
            "medium",
            route_hints=hints,
        )
        packets = _packets(plan)
        execution = build_execution_plan(
            ROOT,
            plan,
            _bundle(plan, packets),
            packets,
            authorization_source="prior_explicit_request",
        )

        self.assertEqual(hints, plan["expertise"]["route_hints"])
        self.assertEqual(
            hints,
            execution["route_plan"]["expertise"]["route_hints"],
        )
        self.assertEqual(
            ["security-engineering"],
            execution["route_plan"]["expertise"]["selected_pack_ids"],
        )

    def test_staged_decision_batches_all_omitted_guide_judgments_before_specialists(
        self,
    ) -> None:
        goal = "제품 화면의 일곱 판단 축을 확정한 후 구현해줘"
        guide_ids = [
            "design-brief",
            "typography-korean",
            "visual-hierarchy-layout",
            "design-system-and-components",
            "interaction-responsive-accessibility",
            "reference-selection",
            "information-architecture-and-user-flow",
        ]
        coverage = _coverage(
            ROOT,
            goal,
            [
                _coverage_item(
                    f"guide-{index}",
                    allocation_kind="expertise-guide",
                    target_ref=f"guide:product-design/{guide_id}",
                    evidence_type="external-stable",
                )
                for index, guide_id in enumerate(guide_ids, start=1)
            ],
        )
        plan = build_decision_plan(
            ROOT,
            goal,
            "medium",
            route_hints=normalize_route_hints(
                explicit_pack_id="product-design",
                affected_paths=["src"],
            ),
            coverage=coverage,
        )
        requirement = plan["expertise_work_requirement"]
        selected = [
            item
            for item in requirement["allocations"]
            if item["selected_in_decision"]
        ]
        omitted = [
            item
            for item in requirement["allocations"]
            if not item["selected_in_decision"]
        ]

        self.assertEqual("required", requirement["status"])
        self.assertEqual(
            "DECISION_GUIDE_BATCHING_REQUIRED",
            requirement["reason_code"],
        )
        self.assertEqual(7, requirement["required_guide_count"])
        self.assertEqual(4, len(selected))
        self.assertEqual(3, len(omitted))
        self.assertTrue(
            all(item["omission_impact"] for item in omitted)
        )
        self.assertTrue(
            all(
                "ExpertiseWorkClosure" in assignment["input_packets"]
                for assignment in plan["assignments"]
                if not assignment["depends_on"]
            )
        )

        blocked_packet = _packets(plan)[0]
        blocked_validation = validate_specialist_packet(
            blocked_packet,
            plan,
        )
        self.assertIn(
            "DECISION_EXPERTISE_CLOSURE_REQUIRED",
            {
                issue["code"]
                for issue in blocked_validation["issues"]
            },
        )

        first_pairs = [
            {
                "coverage_item_id": f"guide-{index}",
                "target_ref": f"guide:product-design/{guide_id}",
            }
            for index, guide_id in enumerate(
                guide_ids[:4],
                start=1,
            )
        ]
        second_pairs = [
            {
                "coverage_item_id": f"guide-{index}",
                "target_ref": f"guide:product-design/{guide_id}",
            }
            for index, guide_id in enumerate(
                guide_ids[4:],
                start=5,
            )
        ]
        work_plan = build_expertise_work_plan(
            ROOT,
            goal=goal,
            coverage=coverage,
            plan=plan,
            draft={
                "batches": [
                    {
                        "batch_id": "product-design-primary",
                        "responsibility": (
                            "Apply the first four Product Design judgments."
                        ),
                        "coverage_pairs": first_pairs,
                        "depends_on": [],
                    },
                    {
                        "batch_id": "product-design-secondary",
                        "responsibility": (
                            "Apply the remaining Product Design judgments."
                        ),
                        "coverage_pairs": second_pairs,
                        "depends_on": [],
                    },
                ]
            },
        )
        self.assertEqual(
            [4, 3],
            sorted(
                (
                    len(batch["guide_ids"])
                    for batch in work_plan["batches"]
                ),
                reverse=True,
            ),
        )
        work_packets = [
            _work_packet(work_plan, batch)
            for batch in work_plan["batches"]
        ]
        blocked_work_packets = copy.deepcopy(work_packets)
        blocked_work_packets[0] = _work_packet(
            work_plan,
            work_plan["batches"][0],
            status="blocked",
        )
        blocked_closure = build_expertise_work_closure(
            work_plan,
            blocked_work_packets,
        )
        blocked_closure_validation = validate_specialist_packet(
            blocked_packet,
            plan,
            expertise_work_plan=work_plan,
            expertise_work_closure=blocked_closure,
        )
        self.assertIn(
            "DECISION_EXPERTISE_CLOSURE_BLOCKED",
            {
                issue["code"]
                for issue in blocked_closure_validation["issues"]
            },
        )
        closure = build_expertise_work_closure(
            work_plan,
            work_packets,
        )
        self.assertEqual("READY", closure["status"])

        packets = _packets(plan)
        packet_validation = validate_specialist_packet(
            packets[0],
            plan,
            expertise_work_plan=work_plan,
            expertise_work_closure=closure,
        )
        self.assertEqual("PASS", packet_validation["status"])
        bundle = _bundle(
            plan,
            packets,
            expertise_work_plan=work_plan,
            expertise_work_closure=closure,
        )
        with patch(
            "maestro.decisions.repository_revision",
            return_value=plan["base_revision"],
        ), patch(
            "maestro.task_coverage.repository_revision",
            return_value=plan["base_revision"],
        ):
            bundle_validation = validate_decision_bundle(
                bundle,
                plan,
                packets,
                ROOT,
                coverage=coverage,
                expertise_work_plan=work_plan,
                expertise_work_closure=closure,
            )
            self.assertEqual("PASS", bundle_validation["status"])
            execution = build_execution_plan(
                ROOT,
                plan,
                bundle,
                packets,
                authorization_source="prior_explicit_request",
                coverage=coverage,
                expertise_work_plan=work_plan,
                expertise_work_closure=closure,
            )
            self.assertEqual(
                work_plan,
                execution["decision_evidence"][
                    "expertise_work_plan"
                ],
            )
            self.assertEqual(
                "PASS",
                validate_execution_plan(
                    execution,
                    repo_path=ROOT,
                )["status"],
            )
            admission = build_task_coverage_admission(
                ROOT,
                goal=goal,
                coverage=coverage,
                plan=execution,
                expertise_work_plan=work_plan,
                expertise_closure=closure,
            )
        self.assertEqual("READY", admission["status"])
        alternate_packets = copy.deepcopy(work_packets)
        alternate_packets[0]["recommendations"] = [
            "A different post-decision recommendation."
        ]
        alternate_packets[0]["packet_digest"] = ""
        alternate_packets[0]["packet_digest"] = sha256_text(
            canonical_json(alternate_packets[0])
        )
        alternate_closure = build_expertise_work_closure(
            work_plan,
            alternate_packets,
        )
        with patch(
            "maestro.decisions.repository_revision",
            return_value=plan["base_revision"],
        ):
            mismatched = build_task_coverage_admission(
                ROOT,
                goal=goal,
                coverage=coverage,
                plan=execution,
                expertise_work_plan=work_plan,
                expertise_closure=alternate_closure,
            )
        self.assertEqual("INVALID", mismatched["status"])
        self.assertIn(
            "TASK_COVERAGE_DECISION_EXPERTISE_MISMATCH",
            {issue["code"] for issue in mismatched["issues"]},
        )


class CoverageAndMultiPackTests(unittest.TestCase):
    def test_pack_research_evidence_is_repeatable_across_cli_boundaries(
        self,
    ) -> None:
        common = [
            "--expertise-research-evidence",
            "product-design.json",
            "--expertise-research-evidence",
            "software-engineering.json",
        ]
        commands = [
            [
                "expertise",
                "plan-work",
                "--goal",
                "goal",
                "--coverage",
                "coverage.json",
                "--plan",
                "plan.json",
                "--draft",
                "draft.json",
            ],
            [
                "admit-coverage",
                "--goal",
                "goal",
                "--coverage",
                "coverage.json",
                "--plan",
                "plan.json",
            ],
            [
                "assignment",
                "project",
                "--plan",
                "plan.json",
                "--assignment",
                "implementation",
                "--baseline",
                "baseline.json",
            ],
            [
                "host",
                "codex",
                "--run-id",
                "run",
                "--task-label",
                "label",
                "--plan",
                "plan.json",
                "--assignment",
                "implementation",
                "--projection",
                "projection.json",
                "--baseline",
                "baseline.json",
            ],
        ]
        for command in commands:
            with self.subTest(command=command[:2]):
                args = parser().parse_args([*command, *common])
                self.assertEqual(
                    [
                        "product-design.json",
                        "software-engineering.json",
                    ],
                    args.expertise_research_evidence,
                )

    def test_bound_coverage_blocks_writer_until_typed_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertTrue(temporary)
            repo = ROOT
            goal = "Implement bounded project manifest behavior"
            coverage = _coverage(
                repo,
                goal,
                [
                    _coverage_item(
                        "manifest",
                        allocation_kind="project-fact",
                        target_ref="project:.maestro/project.json",
                        evidence_type="project-fact",
                    )
                ],
            )
            plan = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                coverage=coverage,
            )
            baseline = baseline_for(plan)

            blocked = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline,
            )
            projection = build_coverage_projection(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                draft={
                    "items": [
                        {
                            "item_id": "manifest",
                            "target_ref": "project:.maestro/project.json",
                            "evidence_ref": ".maestro/project.json",
                            "authority_ref": "repository-state",
                            "reason": "Use the current project manifest.",
                        }
                    ]
                },
            )
            admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                projected_item_ids=["manifest"],
                coverage_projection=projection,
            )
            unexpected_admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                projected_item_ids=["manifest"],
                coverage_projection=projection,
                expertise_research_bundles=[{}],
            )
            unbound_plan = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
            )
            unexpected_projection = project_assignment_input(
                repo,
                unbound_plan,
                "implementation",
                baseline_for(unbound_plan),
                expertise_research_bundles=[{}],
            )
            ready = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline,
                coverage=coverage,
                coverage_admission=admission,
                coverage_projection=projection,
            )

            self.assertEqual("FAIL", blocked["status"])
            self.assertIn(
                "PROJECTION_COVERAGE_REQUIRED",
                {item["code"] for item in blocked["issues"]},
            )
            self.assertEqual("INVALID", unexpected_admission["status"])
            self.assertIn(
                "TASK_COVERAGE_EXPERTISE_RESEARCH_UNEXPECTED",
                {
                    item["code"]
                    for item in unexpected_admission["issues"]
                },
            )
            self.assertEqual("FAIL", unexpected_projection["status"])
            self.assertIn(
                "PROJECTION_COVERAGE_UNEXPECTED",
                {
                    item["code"]
                    for item in unexpected_projection["issues"]
                },
            )
            self.assertEqual("READY", admission["status"])
            self.assertEqual("PASS", ready["status"])
            packet = completed_terminal_packet(
                plan,
                "implementation",
                ready,
            )
            missing = validate_assignment_packet(
                packet,
                plan,
                "implementation",
                ready,
                repo_path=repo,
            )
            packet["coverage_dispositions"] = [
                {
                    "item_id": "manifest",
                    "target_ref": "project:.maestro/project.json",
                    "disposition": "applied",
                    "reason": "The manifest constraint was applied.",
                    "evidence_refs": [
                        f"coverage-admission:{admission['admission_id']}"
                    ],
                }
            ]
            complete = validate_assignment_packet(
                packet,
                plan,
                "implementation",
                ready,
                repo_path=repo,
            )
            self.assertIn(
                "PACKET_COVERAGE_DISPOSITIONS_REQUIRED",
                {item["code"] for item in missing["issues"]},
            )
            self.assertEqual("PASS", complete["status"])

    def test_complete_pair_inventory_batches_and_closes_before_admission(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Implement architecture contracts and security requirements"
            coverage = _coverage(
                repo,
                goal,
                [
                    _coverage_item(
                        "contract",
                        allocation_kind="expertise-guide",
                        target_ref=(
                            "guide:software-engineering/"
                            "contracts-and-invariants"
                        ),
                        evidence_type="external-stable",
                    ),
                    _coverage_item(
                        "security",
                        allocation_kind="expertise-guide",
                        target_ref=(
                            "guide:security-engineering/"
                            "threat-model-and-security-requirements"
                        ),
                        evidence_type="external-stable",
                        depends_on=["contract"],
                    ),
                ],
            )
            plan = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                coverage=coverage,
            )
            draft = {
                "batches": [
                    {
                        "batch_id": "software-review",
                        "responsibility": "Apply contract criteria.",
                        "coverage_pairs": [
                            {
                                "coverage_item_id": "contract",
                                "target_ref": (
                                    "guide:software-engineering/"
                                    "contracts-and-invariants"
                                ),
                            }
                        ],
                        "depends_on": [],
                    },
                    {
                        "batch_id": "security-review",
                        "responsibility": "Apply threat-model criteria.",
                        "coverage_pairs": [
                            {
                                "coverage_item_id": "security",
                                "target_ref": (
                                    "guide:security-engineering/"
                                    "threat-model-and-security-requirements"
                                ),
                            }
                        ],
                        "depends_on": ["software-review"],
                    },
                ]
            }
            work_plan = build_expertise_work_plan(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                draft=draft,
            )
            packets = [
                _work_packet(work_plan, batch)
                for batch in work_plan["batches"]
            ]
            closure = build_expertise_work_closure(work_plan, packets)
            admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                expertise_work_plan=work_plan,
                expertise_closure=closure,
            )

            self.assertEqual(
                [["software-review"], ["security-review"]],
                work_plan["parallel_groups"],
            )
            self.assertTrue(
                all(
                    batch["model_route"]["stage_kind"]
                    == "expertise-review"
                    and batch["model_route"]["execution_unit_id"]
                    == batch["batch_id"]
                    and batch["model_route"]["reasoning_effort"]
                    == "high"
                    for batch in work_plan["batches"]
                )
            )
            routes_by_batch = {
                batch["batch_id"]: batch["model_route"]
                for batch in work_plan["batches"]
            }
            self.assertEqual(
                "gpt-5.6-terra",
                routes_by_batch["software-review"]["selected_model"],
            )
            self.assertEqual(
                "gpt-5.6-sol",
                routes_by_batch["security-review"]["selected_model"],
            )
            self.assertEqual(
                "PASS",
                validate_expertise_work_plan(
                    work_plan,
                    repo_path=repo,
                    goal=goal,
                    coverage=coverage,
                    plan=plan,
                )["status"],
            )
            self.assertEqual(
                "PASS",
                validate_expertise_work_closure(
                    closure,
                    work_plan=work_plan,
                )["status"],
            )
            self.assertEqual("READY", admission["status"])
            self.assertEqual(
                closure["closure_id"],
                admission["expertise_closure_id"],
            )

            legacy_plan = copy.deepcopy(work_plan)
            for batch in legacy_plan["batches"]:
                batch.pop("model_route")
            legacy_plan["work_plan_id"] = ""
            legacy_plan["work_plan_id"] = sha256_text(
                canonical_json(legacy_plan)
            )
            legacy_validation = validate_expertise_work_plan(
                legacy_plan,
                repo_path=repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
            )
            self.assertEqual("PASS", legacy_validation["status"])
            self.assertEqual(
                "UPGRADE_REQUIRED",
                legacy_validation["execution_status"],
            )
            with self.assertRaises(MaestroError) as raised:
                build_expertise_work_closure(legacy_plan, [])
            self.assertEqual(
                "EXPERTISE_WORK_ROUTE_UPGRADE_REQUIRED",
                raised.exception.code,
            )
            legacy_admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                expertise_work_plan=legacy_plan,
                expertise_closure={},
            )
            self.assertNotEqual("READY", legacy_admission["status"])
            self.assertIn(
                "TASK_COVERAGE_EXPERTISE_ROUTE_UPGRADE_REQUIRED",
                {
                    issue["code"]
                    for issue in legacy_admission["issues"]
                },
            )

            incomplete = copy.deepcopy(draft)
            incomplete["batches"].pop()
            with self.assertRaises(MaestroError) as raised:
                build_expertise_work_plan(
                    repo,
                    goal=goal,
                    coverage=coverage,
                    plan=plan,
                    draft=incomplete,
                )
            self.assertEqual(
                "EXPERTISE_WORK_PAIR_SET_MISMATCH",
                raised.exception.code,
            )

            malformed_plan = copy.deepcopy(work_plan)
            malformed_plan["pairs"][0].pop("target_ref")
            malformed_plan["work_plan_id"] = ""
            malformed_plan["work_plan_id"] = sha256_text(
                canonical_json(malformed_plan)
            )
            self.assertEqual(
                "FAIL",
                validate_expertise_work_plan(
                    malformed_plan,
                    repo_path=repo,
                    goal=goal,
                    coverage=coverage,
                    plan=plan,
                )["status"],
            )
            with self.assertRaises(MaestroError) as raised:
                build_expertise_work_closure(
                    malformed_plan,
                    [],
                )
            self.assertEqual(
                "EXPERTISE_WORK_PLAN_INVALID",
                raised.exception.code,
            )

            invalid_batch_id = copy.deepcopy(draft)
            invalid_batch_id["batches"][0]["batch_id"] = (
                "Software Review"
            )
            invalid_batch_id["batches"][1]["depends_on"] = [
                "Software Review"
            ]
            with self.assertRaises(MaestroError) as raised:
                build_expertise_work_plan(
                    repo,
                    goal=goal,
                    coverage=coverage,
                    plan=plan,
                    draft=invalid_batch_id,
                )
            self.assertEqual(
                "EXPERTISE_WORK_BATCH_INVALID",
                raised.exception.code,
            )

            blocked_packet = _work_packet(
                work_plan,
                work_plan["batches"][0],
            )
            blocked_packet["conflicts"] = [
                "The two Guide criteria materially conflict."
            ]
            blocked_packet["packet_digest"] = ""
            blocked_packet["packet_digest"] = sha256_text(
                canonical_json(blocked_packet)
            )
            blocked_packets = [
                blocked_packet,
                _work_packet(
                    work_plan,
                    work_plan["batches"][1],
                ),
            ]
            blocked_closure = build_expertise_work_closure(
                work_plan,
                blocked_packets,
            )
            tampered_closure = copy.deepcopy(blocked_closure)
            tampered_closure["batch_results"][0]["conflicts"] = []
            tampered_closure["conflicts"] = []
            tampered_closure["status"] = "READY"
            tampered_closure["closure_id"] = ""
            tampered_closure["closure_id"] = sha256_text(
                canonical_json(tampered_closure)
            )
            self.assertEqual(
                "FAIL",
                validate_expertise_work_closure(
                    tampered_closure,
                    work_plan=work_plan,
                )["status"],
            )

            malformed_closure = copy.deepcopy(closure)
            malformed_closure["batch_results"][0].pop("conflicts")
            malformed_closure["closure_id"] = ""
            malformed_closure["closure_id"] = sha256_text(
                canonical_json(malformed_closure)
            )
            self.assertEqual(
                "FAIL",
                validate_expertise_work_closure(
                    malformed_closure,
                    work_plan=work_plan,
                )["status"],
            )

    def test_existing_unselected_guide_is_capacity_not_a_candidate_gap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Implement architecture contracts and security requirements"
            targets = [
                (
                    "contract",
                    "guide:software-engineering/contracts-and-invariants",
                ),
                (
                    "security",
                    (
                        "guide:security-engineering/"
                        "threat-model-and-security-requirements"
                    ),
                ),
            ]
            coverage = _coverage(
                repo,
                goal,
                [
                    _coverage_item(
                        item_id,
                        allocation_kind="expertise-guide",
                        target_ref=target_ref,
                        evidence_type="external-stable",
                    )
                    for item_id, target_ref in targets
                ],
            )
            plan = route_goal_v2(
                goal,
                "high",
                intent="implementation",
                repo_path=repo,
                coverage=coverage,
            )
            admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
            )

            self.assertEqual("GAPS", admission["status"])
            capacity_gaps = [
                gap
                for gap in admission["gaps"]
                if gap["reason"] == "route-capacity"
            ]
            self.assertTrue(capacity_gaps)
            with self.assertRaises(MaestroError) as raised:
                build_expertise_adaptation_plan(
                    repo,
                    goal=goal,
                    coverage=coverage,
                    source_route=plan,
                    source_admission=admission,
                    draft={
                        "units": [
                            {
                                "unit_id": "revise-existing-guide",
                                "coverage_item_ids": [
                                    item_id for item_id, _ in targets
                                ],
                                "surface": "decision-guide",
                                "change_kind": "guide-revision",
                                "target_ref": capacity_gaps[0][
                                    "target_ref"
                                ],
                                "depends_on": [],
                                "change_set_id": None,
                                "evidence_refs": [
                                    target_ref
                                    for _, target_ref in targets
                                ],
                            }
                        ]
                    },
                )
            self.assertEqual(
                "EXPERTISE_ADAPTATION_DRAFT_INVALID",
                raised.exception.code,
            )
            self.assertIn(
                "Durable candidate work requires",
                raised.exception.message,
            )

    def test_dependent_guide_pairs_cannot_share_one_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Implement contract and failure recovery rules"
            coverage = _coverage(
                repo,
                goal,
                [
                    _coverage_item(
                        "contract",
                        allocation_kind="expertise-guide",
                        target_ref=(
                            "guide:software-engineering/"
                            "contracts-and-invariants"
                        ),
                        evidence_type="external-stable",
                    ),
                    _coverage_item(
                        "recovery",
                        allocation_kind="expertise-guide",
                        target_ref=(
                            "guide:software-engineering/"
                            "failure-semantics-and-recovery"
                        ),
                        evidence_type="external-stable",
                        depends_on=["contract"],
                    ),
                ],
            )
            plan = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                coverage=coverage,
            )

            with self.assertRaises(MaestroError) as raised:
                build_expertise_work_plan(
                    repo,
                    goal=goal,
                    coverage=coverage,
                    plan=plan,
                    draft={
                        "batches": [
                            {
                                "batch_id": "software-review",
                                "responsibility": (
                                    "Apply contract and recovery criteria."
                                ),
                                "coverage_pairs": [
                                    {
                                        "coverage_item_id": "contract",
                                        "target_ref": (
                                            "guide:software-engineering/"
                                            "contracts-and-invariants"
                                        ),
                                    },
                                    {
                                        "coverage_item_id": "recovery",
                                        "target_ref": (
                                            "guide:software-engineering/"
                                            "failure-semantics-and-recovery"
                                        ),
                                    },
                                ],
                                "depends_on": [],
                            }
                        ]
                    },
                )
            self.assertEqual(
                "EXPERTISE_WORK_DEPENDENCY_CO_BATCHED",
                raised.exception.code,
            )

    def test_owner_projection_requires_a_durable_repository_decision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Implement the owner's approved interface choice"
            coverage = _coverage(
                repo,
                goal,
                [
                    _coverage_item(
                        "owner-choice",
                        allocation_kind="owner-decision",
                        target_ref="owner:user/interface-choice",
                        evidence_type="owner-preference",
                    )
                ],
            )
            plan = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                coverage=coverage,
            )
            invented_ref = "owner_decision:invented-by-the-model"
            with self.assertRaises(MaestroError) as raised:
                build_coverage_projection(
                    repo,
                    goal=goal,
                    coverage=coverage,
                    plan=plan,
                    draft={
                        "items": [
                            {
                                "item_id": "owner-choice",
                                "target_ref": "owner:user/interface-choice",
                                "evidence_ref": invented_ref,
                                "authority_ref": invented_ref,
                                "reason": "Apply the approved interface choice.",
                            }
                        ]
                    },
                )
            self.assertEqual(
                "COVERAGE_PROJECTION_OWNER_AUTHORITY_INVALID",
                raised.exception.code,
            )

            decision_file = repo / "docs" / "decisions" / "interface.md"
            decision_file.parent.mkdir(parents=True)
            decision_file.write_text(
                "# Approved interface\n\nUse the compact interface.\n",
                encoding="utf-8",
            )
            authority_ref = "owner_decision:docs/decisions/interface.md"
            projection = build_coverage_projection(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                draft={
                    "items": [
                        {
                            "item_id": "owner-choice",
                            "target_ref": "owner:user/interface-choice",
                            "evidence_ref": authority_ref,
                            "authority_ref": authority_ref,
                            "reason": "Apply the approved interface choice.",
                        }
                    ]
                },
            )

            self.assertEqual(
                file_sha256(decision_file),
                projection["entries"][0]["evidence_digest"],
            )

    def test_every_coverage_pack_must_satisfy_its_own_research_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Implement architecture boundaries using latest design references"
            coverage = _coverage(
                repo,
                goal,
                [
                    _coverage_item(
                        "architecture",
                        allocation_kind="expertise-guide",
                        target_ref=(
                            "guide:software-engineering/"
                            "architecture-boundaries-and-tradeoffs"
                        ),
                        evidence_type="external-stable",
                    ),
                    _coverage_item(
                        "references",
                        allocation_kind="expertise-guide",
                        target_ref=(
                            "guide:product-design/reference-selection"
                        ),
                        evidence_type="external-stable",
                    ),
                ],
            )
            plan = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                coverage=coverage,
                route_hints=normalize_route_hints(
                    work_kinds=["software-structure"],
                    affected_paths=["src"],
                ),
            )
            draft = {
                "batches": [
                    {
                        "batch_id": "software-review",
                        "responsibility": "Apply architecture criteria.",
                        "coverage_pairs": [
                            {
                                "coverage_item_id": "architecture",
                                "target_ref": (
                                    "guide:software-engineering/"
                                    "architecture-boundaries-and-tradeoffs"
                                ),
                            }
                        ],
                        "depends_on": [],
                    },
                    {
                        "batch_id": "design-review",
                        "responsibility": "Apply reference-selection criteria.",
                        "coverage_pairs": [
                            {
                                "coverage_item_id": "references",
                                "target_ref": (
                                    "guide:product-design/reference-selection"
                                ),
                            }
                        ],
                        "depends_on": [],
                    },
                ]
            }

            with self.assertRaises(MaestroError) as raised:
                build_expertise_work_plan(
                    repo,
                    goal=goal,
                    coverage=coverage,
                    plan=plan,
                    draft=draft,
                )
            self.assertEqual(
                "EXPERTISE_WORK_RESEARCH_REQUIRED",
                raised.exception.code,
            )

            product_pack = next(
                pack
                for pack in load_expertise_catalog(
                    repo,
                    include_candidates=True,
                )
                if pack["expertise_pack_id"] == "product-design"
            )
            expertise = {
                "selected_pack_ids": ["product-design"],
                "selected_guide_ids": ["reference-selection"],
                "pack_definition_digests": {
                    "product-design": product_pack["_maestro"][
                        "definition_digest"
                    ]
                },
                "research_requirement": {
                    "mode": "contextualize",
                    "gate": "open",
                    "reasons": ["latest"],
                    "evidence_digest": None,
                },
            }
            research_bundle = _research_bundle(goal)
            research_bundle["request_binding"] = expected_research_binding(
                goal,
                expertise,
            )
            work_plan = build_expertise_work_plan(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                draft=draft,
                expertise_research_bundles=[research_bundle],
            )
            closure = build_expertise_work_closure(
                work_plan,
                [
                    _work_packet(work_plan, batch)
                    for batch in work_plan["batches"]
                ],
            )
            admission = build_task_coverage_admission(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                expertise_work_plan=work_plan,
                expertise_closure=closure,
                expertise_research_bundles=[research_bundle],
            )

            product_requirement = next(
                requirement
                for requirement in work_plan[
                    "pack_research_requirements"
                ]
                if requirement["pack_id"] == "product-design"
            )
            self.assertEqual("contextualize", product_requirement["mode"])
            self.assertEqual("satisfied", product_requirement["gate"])
            self.assertEqual("READY", admission["status"])

    def test_external_coverage_prerequisites_remain_visible_to_the_host(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            goal = "Apply project constraints before architecture review"
            coverage = _coverage(
                repo,
                goal,
                [
                    _coverage_item(
                        "manifest",
                        allocation_kind="project-fact",
                        target_ref="project:.maestro/project.json",
                        evidence_type="project-fact",
                    ),
                    _coverage_item(
                        "contract",
                        allocation_kind="expertise-guide",
                        target_ref=(
                            "guide:software-engineering/"
                            "contracts-and-invariants"
                        ),
                        evidence_type="external-stable",
                        depends_on=["manifest"],
                    ),
                ],
            )
            plan = route_goal_v2(
                goal,
                "medium",
                intent="implementation",
                repo_path=repo,
                coverage=coverage,
            )
            work_plan = build_expertise_work_plan(
                repo,
                goal=goal,
                coverage=coverage,
                plan=plan,
                draft={
                    "batches": [
                        {
                            "batch_id": "software-review",
                            "responsibility": "Apply contract criteria.",
                            "coverage_pairs": [
                                {
                                    "coverage_item_id": "contract",
                                    "target_ref": (
                                        "guide:software-engineering/"
                                        "contracts-and-invariants"
                                    ),
                                }
                            ],
                            "depends_on": [],
                        }
                    ]
                },
            )

            self.assertEqual(
                ["manifest"],
                work_plan["batches"][0][
                    "external_prerequisite_item_ids"
                ],
            )


if __name__ == "__main__":
    unittest.main()
