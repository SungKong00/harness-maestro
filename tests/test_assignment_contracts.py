from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests.support import ROOT, apply_fresh_init, write_json

from maestro.assignment_contracts import (
    ASSIGNMENT_INPUT_VERSION,
    ENGINEERING_BASELINE_VERSION,
    FINDING_PACKET_VERSION,
    TERMINAL_PACKET_VERSION,
    assignment_output_schema,
    project_assignment_input,
    validate_assignment_packet,
    validate_engineering_baseline,
)
from maestro.cli import main
from maestro.planning import route_goal_v2
from maestro.util import canonical_json, file_sha256, sha256_text
from tests.test_research_workflow import GOAL as RESEARCH_GOAL
from tests.test_research_workflow import _bundle as research_bundle


CHECK_IDS = (
    "affected-surface",
    "behavior-contract",
    "compatibility",
    "completion-evidence",
    "failure-recovery",
    "risk-ownership",
)


def baseline_for(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": ENGINEERING_BASELINE_VERSION,
        "goal_digest": sha256_text(plan["goal"]),
        "surface_map": {
            "artifacts": [
                {
                    "artifact_id": "readme",
                    "kind": "documentation",
                    "path": "README.md",
                    "state": "existing",
                }
            ],
            "affected_boundaries": [
                {
                    "boundary_id": "usage-contract",
                    "artifact_ids": ["readme"],
                }
            ],
            "stakeholders": [
                {
                    "stakeholder_id": "maintainer",
                    "concern": "Documented behavior must match the executable CLI.",
                }
            ],
            "lifecycle_states": [
                {
                    "state_id": "success",
                    "kind": "success",
                    "artifact_ids": ["readme"],
                }
            ],
        },
        "checks": [
            {
                "check_id": check_id,
                "status": "covered",
                "owner": "task-contract",
                "evidence_refs": ["readme"],
                "note": "The mapped artifact and task contract own this baseline check.",
            }
            for check_id in CHECK_IDS
        ],
    }


def finding_packet(
    plan: dict[str, Any],
    assignment_id: str,
    *,
    verdict: str = "PASS",
) -> dict[str, Any]:
    assignment = next(
        item
        for item in plan["assignments"]
        if item["assignment_id"] == assignment_id
    )
    return {
        "schema_version": FINDING_PACKET_VERSION,
        "plan_id": plan["plan_id"],
        "assignment_id": assignment_id,
        "lens_ids": assignment["lens_ids"],
        "verdict": verdict,
        "findings": [],
        "coverage_gaps": [],
        "uncertainties": [],
        "inspected": ["readme"],
        "skipped": [],
    }


def completed_terminal_packet(
    plan: dict[str, Any],
    assignment_id: str,
    projection: dict[str, Any],
) -> dict[str, Any]:
    assignment = next(
        item
        for item in plan["assignments"]
        if item["assignment_id"] == assignment_id
    )
    projected = projection["input"]
    evidence_ref = projected["artifact_refs"][0]["artifact_id"]
    packet = {
        "schema_version": TERMINAL_PACKET_VERSION,
        "plan_id": plan["plan_id"],
        "assignment_id": assignment_id,
        "packet_type": assignment["output_packet"],
        "status": "completed",
        "summary": f"{assignment_id} completed with projected evidence.",
        "evidence_refs": [evidence_ref],
        "retryable": False,
    }
    selected = projected["convention_selection"]["selected_conventions"]
    if assignment["mutation_owner"] and selected:
        packet["convention_dispositions"] = [
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "disposition": "applied",
                "reason": "Applied the selected Convention.",
                "approval_ref": None,
            }
            for item in selected
        ]
    research = projected.get("research_context")
    if assignment["mutation_owner"] and isinstance(research, dict):
        packet["evidence_refs"].append(
            f"research-bundle:{research['evidence_digest']}"
        )
        packet["research_dispositions"] = [
            {
                "claim_id": claim_id,
                "disposition": "applied",
                "reason": "Applied the bounded research criterion.",
                "evidence_refs": [evidence_ref],
            }
            for claim_id in research["synthesis"]["adopted_claim_ids"]
        ]
    return packet


class AssignmentBoundaryContractTests(unittest.TestCase):
    def test_assignment_output_schema_binds_exact_packet_contract(self) -> None:
        review_plan = route_goal_v2(
            "Review the README usage contract",
            "medium",
            ["contract"],
            intent="review",
            repo_path=ROOT,
        )
        review = project_assignment_input(
            ROOT,
            review_plan,
            "review",
            baseline_for(review_plan),
        )
        self.assertEqual("PASS", review["status"])

        finding_schema = assignment_output_schema(review)
        self.assertEqual(
            [FINDING_PACKET_VERSION],
            finding_schema["properties"]["schema_version"]["enum"],
        )
        self.assertEqual(
            [review_plan["plan_id"]],
            finding_schema["properties"]["plan_id"]["enum"],
        )
        self.assertEqual(
            ["review"],
            finding_schema["properties"]["assignment_id"]["enum"],
        )
        self.assertEqual(
            ["contract"],
            finding_schema["properties"]["lens_ids"]["items"]["enum"],
        )
        self.assertEqual(
            ["contract"],
            finding_schema["$defs"]["finding"]["properties"][
                "owner_lens_id"
            ]["enum"],
        )
        projected_refs = {
            item["artifact_id"] for item in review["input"]["artifact_refs"]
        } | {
            item["ref_id"] for item in review["input"]["document_refs"]
        }
        self.assertEqual(
            projected_refs,
            set(
                finding_schema["$defs"]["finding"]["properties"][
                    "evidence_refs"
                ]["items"]["enum"]
            ),
        )
        coverage_properties = finding_schema["$defs"]["coverageGap"][
            "properties"
        ]
        self.assertEqual(
            {
                item["artifact_id"]
                for item in review["input"]["artifact_refs"]
            },
            set(coverage_properties["affected_artifact"]["enum"]),
        )
        suggested_lens = coverage_properties["suggested_lens"]["anyOf"]
        self.assertIn({"type": "null"}, suggested_lens)
        self.assertNotIn(
            "contract",
            next(
                item["enum"]
                for item in suggested_lens
                if "enum" in item
            ),
        )
        self.assertEqual(
            projected_refs,
            set(finding_schema["properties"]["inspected"]["items"]["enum"]),
        )
        self.assertFalse(finding_schema["additionalProperties"])
        self.assertEqual(
            set(finding_schema["required"]),
            set(finding_schema["properties"]),
        )
        provider_schema = canonical_json(finding_schema)
        for unsupported in (
            '"$schema"',
            '"const"',
            '"format"',
            '"maxItems"',
            '"maxLength"',
            '"minItems"',
            '"minLength"',
            '"oneOf"',
            '"pattern"',
            '"uniqueItems"',
        ):
            self.assertNotIn(unsupported, provider_schema)

        implementation_plan = route_goal_v2(
            "Implement one local CLI behavior",
            "low",
            intent="implementation",
            repo_path=ROOT,
        )
        implementation = project_assignment_input(
            ROOT,
            implementation_plan,
            "implementation",
            baseline_for(implementation_plan),
        )
        self.assertEqual("PASS", implementation["status"])

        terminal_schema = assignment_output_schema(implementation)
        self.assertEqual(
            [TERMINAL_PACKET_VERSION],
            terminal_schema["properties"]["schema_version"]["enum"],
        )
        self.assertEqual(
            [implementation_plan["plan_id"]],
            terminal_schema["properties"]["plan_id"]["enum"],
        )
        self.assertEqual(
            ["implementation"],
            terminal_schema["properties"]["assignment_id"]["enum"],
        )
        self.assertEqual(
            ["ChangeReceipt"],
            terminal_schema["properties"]["packet_type"]["enum"],
        )
        self.assertFalse(terminal_schema["additionalProperties"])
        self.assertEqual(
            set(terminal_schema["required"]),
            set(terminal_schema["properties"]),
        )

    def test_open_research_gate_blocks_projection_and_completed_bundle_is_used(
        self,
    ) -> None:
        open_plan = route_goal_v2(
            RESEARCH_GOAL,
            "medium",
            intent="implementation",
            repo_path=ROOT,
        )
        blocked = project_assignment_input(
            ROOT,
            open_plan,
            open_plan["assignments"][0]["assignment_id"],
            baseline_for(open_plan),
        )
        self.assertEqual("BLOCKED", blocked["status"])
        self.assertEqual("RESEARCH_REQUIRED", blocked["execution_status"])

        bundle = research_bundle(RESEARCH_GOAL)
        plan = route_goal_v2(
            RESEARCH_GOAL,
            "medium",
            intent="implementation",
            research_evidence=bundle,
            repo_path=ROOT,
        )
        missing = project_assignment_input(
            ROOT,
            plan,
            "implementation",
            baseline_for(plan),
        )
        self.assertEqual("BLOCKED", missing["status"])
        self.assertEqual("RESEARCH_REQUIRED", missing["execution_status"])
        self.assertIn(
            "PROJECTION_RESEARCH_REQUIRED",
            {item["code"] for item in missing["issues"]},
        )

        implementation = project_assignment_input(
            ROOT,
            plan,
            "implementation",
            baseline_for(plan),
            research_bundle=bundle,
        )
        self.assertEqual("PASS", implementation["status"])
        context = implementation["input"]["research_context"]
        self.assertEqual(bundle["source_plan"], context["source_plan"])
        self.assertEqual(bundle["packets"][0]["claims"], context["claims"])
        packet = completed_terminal_packet(
            plan,
            "implementation",
            implementation,
        )
        accepted = validate_assignment_packet(
            packet,
            plan,
            "implementation",
            implementation,
            repo_path=ROOT,
            research_bundle=bundle,
        )
        self.assertEqual("PASS", accepted["status"])

        missing_usage = copy.deepcopy(packet)
        missing_usage.pop("research_dispositions")
        missing_usage["evidence_refs"] = ["readme"]
        rejected = validate_assignment_packet(
            missing_usage,
            plan,
            "implementation",
            implementation,
            repo_path=ROOT,
            research_bundle=bundle,
        )
        codes = {item["code"] for item in rejected["issues"]}
        self.assertIn("PACKET_RESEARCH_EVIDENCE_REQUIRED", codes)
        self.assertIn("PACKET_RESEARCH_DISPOSITIONS_REQUIRED", codes)

        forged_projection = copy.deepcopy(implementation)
        forged_projection["input"]["research_context"] = None
        forged_payload = copy.deepcopy(forged_projection["input"])
        forged_payload.pop("projection_digest")
        forged_projection["input"]["projection_digest"] = sha256_text(
            canonical_json(forged_payload)
        )
        forged = validate_assignment_packet(
            packet,
            plan,
            "implementation",
            forged_projection,
            repo_path=ROOT,
            research_bundle=bundle,
        )
        self.assertIn(
            "PACKET_RESEARCH_CONTEXT_MISMATCH",
            {item["code"] for item in forged["issues"]},
        )

    def test_projection_is_a_bounded_allowlist_and_does_not_claim_host_proof(
        self,
    ) -> None:
        plan = route_goal_v2(
            "Review the README usage contract",
            "medium",
            ["contract"],
            intent="review",
            repo_path=ROOT,
        )
        baseline = baseline_for(plan)

        result = project_assignment_input(
            ROOT,
            plan,
            "review",
            baseline,
            document_paths=["README.md"],
        )

        self.assertEqual("PASS", result["status"])
        projected = result["input"]
        self.assertEqual(ASSIGNMENT_INPUT_VERSION, projected["schema_version"])
        self.assertEqual(["contract"], [
            card["lens_id"] for card in projected["selected_lens_cards"]
        ])
        projected_document_paths = [
            item["path"] for item in projected["document_refs"]
        ]
        self.assertIn("README.md", projected_document_paths)
        self.assertIn("docs/README.md", projected_document_paths)
        self.assertEqual(
            "maestro_convention_selection_v1",
            projected["convention_selection"]["schema_version"],
        )
        self.assertIn(
            projected["convention_selection"]["evidence_status"],
            {"sufficient", "insufficient"},
        )
        self.assertRegex(
            projected["convention_selection"]["selection_digest"],
            r"^[a-f0-9]{64}$",
        )
        self.assertNotIn("content", canonical_json(projected))
        self.assertEqual(
            {
                "fresh_context": "unavailable",
                "packet_only": "unavailable",
                "read_only": "unavailable",
            },
            projected["context_policy"]["host_attestation"],
        )
        self.assertTrue(
            projected["context_policy"]["requests"]["fresh_context"]
        )
        payload = copy.deepcopy(projected)
        digest = payload.pop("projection_digest")
        self.assertEqual(sha256_text(canonical_json(payload)), digest)

    def test_expertise_projection_binds_resources_without_claiming_host_load(
        self,
    ) -> None:
        review_plan = route_goal_v2(
            "Review the Korean typography and visual hierarchy",
            "medium",
            intent="review",
            repo_path=ROOT,
        )
        review = project_assignment_input(
            ROOT,
            review_plan,
            review_plan["assignments"][0]["assignment_id"],
            baseline_for(review_plan),
        )

        self.assertEqual("PASS", review["status"])
        load = review["input"]["expertise_load"]
        self.assertEqual("advisory-only", load["application_mode"])
        self.assertEqual("unavailable", load["host_attestation"]["status"])
        self.assertEqual([], load["host_attestation"]["loaded_skill_digests"])
        self.assertEqual(
            review_plan["expertise"]["selected_pack_ids"],
            [item["expertise_pack_id"] for item in load["packs"]],
        )
        self.assertRegex(
            load["packs"][0]["skill_definition_digest"],
            r"^[a-f0-9]{64}$",
        )
        guide_refs = {
            item["guide_id"]: item["resource_path"]
            for item in load["packs"][0]["guides"]
        }
        self.assertEqual(
            "references/typography-korean.md",
            guide_refs["typography-korean"],
        )

        implementation_plan = route_goal_v2(
            "Implement the approved Korean typography and visual hierarchy",
            "medium",
            intent="implementation",
            repo_path=ROOT,
        )
        implementation = project_assignment_input(
            ROOT,
            implementation_plan,
            "implementation",
            baseline_for(implementation_plan),
        )
        self.assertEqual("PASS", implementation["status"])
        self.assertEqual(
            "authorized-executor-may-apply",
            implementation["input"]["expertise_load"]["application_mode"],
        )

    def test_writer_must_report_every_bound_convention_disposition(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / "README.md").write_text(
                "# Test\n",
                encoding="utf-8",
            )
            apply_fresh_init(repo)
            convention = repo / "docs/conventions/readme-style.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                "# Active Convention\n",
                encoding="utf-8",
            )
            plan = route_goal_v2(
                "Implement the approved README wording",
                "low",
                intent="implementation",
                repo_path=repo,
            )
            baseline = baseline_for(plan)
            selected = {
                "schema_version": "maestro_docs_selection_v1",
                "required_documents": [
                    {
                        "path": "docs/README.md",
                        "sha256": file_sha256(repo / "docs/README.md"),
                        "reason": "project documentation index",
                    },
                    {
                        "path": "docs/conventions/readme-style.md",
                        "sha256": file_sha256(convention),
                        "reason": "path scope: README.md",
                        "document_type": "convention",
                    },
                ],
                "selected_conventions": [
                    "docs/conventions/readme-style.md"
                ],
                "evidence_status": "sufficient",
                "missing_evidence": [],
            }
            with patch(
                "maestro.assignment_contracts.select_documents",
                return_value=selected,
            ):
                projection = project_assignment_input(
                    repo,
                    plan,
                    "implementation",
                    baseline,
                )

            self.assertEqual("PASS", projection["status"])
            projected = projection["input"]
            self.assertEqual(
                ["docs/conventions/readme-style.md"],
                [
                    item["path"]
                    for item in projected["convention_selection"][
                        "selected_conventions"
                    ]
                ],
            )
            packet = {
                "schema_version": TERMINAL_PACKET_VERSION,
                "plan_id": plan["plan_id"],
                "assignment_id": "implementation",
                "packet_type": next(
                    item["output_packet"]
                    for item in plan["assignments"]
                    if item["assignment_id"] == "implementation"
                ),
                "status": "completed",
                "summary": "Updated the approved README wording.",
                "evidence_refs": ["readme"],
                "retryable": False,
            }
            missing = validate_assignment_packet(
                packet,
                plan,
                "implementation",
                projection,
                repo_path=repo,
            )
            self.assertEqual("FAIL", missing["status"])
            self.assertIn(
                "PACKET_CONVENTION_DISPOSITIONS_REQUIRED",
                {item["code"] for item in missing["issues"]},
            )

            selected_convention = projected["convention_selection"][
                "selected_conventions"
            ][0]
            packet["convention_dispositions"] = [
                {
                    "path": selected_convention["path"],
                    "sha256": selected_convention["sha256"],
                    "disposition": "applied",
                    "reason": "The implementation followed the selected rule.",
                    "approval_ref": None,
                }
            ]
            accepted = validate_assignment_packet(
                packet,
                plan,
                "implementation",
                projection,
                repo_path=repo,
            )
            self.assertEqual("PASS", accepted["status"])

            tampered = copy.deepcopy(projection)
            tampered_input = tampered["input"]
            tampered_input["convention_selection"]["selection_digest"] = (
                "0" * 64
            )
            projection_payload = copy.deepcopy(tampered_input)
            projection_payload.pop("projection_digest")
            tampered_input["projection_digest"] = sha256_text(
                canonical_json(projection_payload)
            )
            rejected = validate_assignment_packet(
                packet,
                plan,
                "implementation",
                tampered,
                repo_path=repo,
            )
            self.assertIn(
                "PACKET_CONVENTION_SELECTION_INVALID",
                {item["code"] for item in rejected["issues"]},
            )

    def test_baseline_gap_allows_review_but_blocks_mutation(self) -> None:
        plan = route_goal_v2(
            "Implement README contract behavior and verification",
            "medium",
            ["contract"],
            intent="implementation",
            repo_path=ROOT,
        )
        baseline = baseline_for(plan)
        risk = next(
            item
            for item in baseline["checks"]
            if item["check_id"] == "risk-ownership"
        )
        risk.update(status="gap", owner=None)
        review = project_assignment_input(
            ROOT,
            plan,
            "review",
            baseline,
        )
        self.assertEqual("PASS", review["status"])
        self.assertEqual("GAPS_PRESENT", review["execution_status"])

        dependency = finding_packet(plan, "review")
        implementation = project_assignment_input(
            ROOT,
            plan,
            "implementation",
            baseline,
            dependency_packets=[dependency],
            dependency_projections=[review],
        )
        self.assertEqual("BLOCKED", implementation["status"])
        self.assertEqual("GAPS_PRESENT", implementation["execution_status"])

    def test_finding_packet_is_bound_to_projection_and_lens(self) -> None:
        plan = route_goal_v2(
            "Review the README usage contract",
            "medium",
            ["contract"],
            intent="review",
            repo_path=ROOT,
        )
        projection = project_assignment_input(
            ROOT,
            plan,
            "review",
            baseline_for(plan),
        )
        packet = finding_packet(plan, "review", verdict="FINDINGS")
        packet["findings"] = [
            {
                "owner_lens_id": "contract",
                "location": "README.md:1",
                "severity": "medium",
                "claim": "The documented invocation can drift from the CLI.",
                "evidence_refs": ["readme"],
                "counterexample": None,
                "suggested_action": "Verify the invocation against parser behavior.",
                "fingerprint": "readme-cli-contract-drift",
            }
        ]

        self.assertEqual(
            "PASS",
            validate_assignment_packet(
                packet,
                plan,
                "review",
                projection,
                repo_path=ROOT,
            )["status"],
        )

        tampered_projection = copy.deepcopy(projection)
        tampered_projection["input"]["artifact_refs"][0]["path"] = "other.md"
        codes = {
            item["code"]
            for item in validate_assignment_packet(
                packet,
                plan,
                "review",
                tampered_projection,
                repo_path=ROOT,
            )["issues"]
        }
        self.assertIn("PACKET_PROJECTION_INVALID", codes)

        contaminated = copy.deepcopy(packet)
        contaminated["findings"][0]["owner_lens_id"] = "data-integrity"
        contaminated["findings"][0]["evidence_refs"] = ["unprojected"]
        codes = {
            item["code"]
            for item in validate_assignment_packet(
                contaminated,
                plan,
                "review",
                projection,
                repo_path=ROOT,
            )["issues"]
        }
        self.assertIn("PACKET_FINDING_SCOPE_INVALID", codes)
        self.assertIn("PACKET_EVIDENCE_OUT_OF_PROJECTION", codes)

        contaminated["messages"] = ["full conversation"]
        codes = {
            item["code"]
            for item in validate_assignment_packet(
                contaminated,
                plan,
                "review",
                projection,
                repo_path=ROOT,
            )["issues"]
        }
        self.assertIn("CONTRACT_FIELDS_UNKNOWN", codes)

    def test_coverage_gap_is_evidence_bound_and_limited(self) -> None:
        plan = route_goal_v2(
            "Review the README usage contract",
            "high",
            ["contract"],
            intent="review",
            repo_path=ROOT,
        )
        projection = project_assignment_input(
            ROOT,
            plan,
            "review",
            baseline_for(plan),
        )
        packet = finding_packet(
            plan,
            "review",
            verdict="INSUFFICIENT_EVIDENCE",
        )
        packet["coverage_gaps"] = [
            {
                "affected_artifact": "readme",
                "possible_failure": "Concurrent update rules may be undocumented.",
                "evidence_refs": ["readme"],
                "severity": "medium",
                "why_uncovered": "The selected Contract Lens does not own concurrency.",
                "suggested_lens": "transaction-concurrency",
            }
        ]
        self.assertEqual(
            "PASS",
            validate_assignment_packet(
                packet,
                plan,
                "review",
                projection,
                repo_path=ROOT,
            )["status"],
        )

        noisy = copy.deepcopy(packet)
        noisy["coverage_gaps"] *= 3
        codes = {
            item["code"]
            for item in validate_assignment_packet(
                noisy,
                plan,
                "review",
                projection,
                repo_path=ROOT,
            )["issues"]
        }
        self.assertIn("PACKET_COVERAGE_GAPS_INVALID", codes)

    def test_invalid_dependency_packet_never_reaches_the_writer(self) -> None:
        plan = route_goal_v2(
            "Implement README contract behavior and verification",
            "medium",
            ["contract"],
            intent="implementation",
            repo_path=ROOT,
        )
        dependency = finding_packet(plan, "review")
        dependency["inspected"] = ["outside-projection"]
        review_projection = project_assignment_input(
            ROOT,
            plan,
            "review",
            baseline_for(plan),
        )

        result = project_assignment_input(
            ROOT,
            plan,
            "implementation",
            baseline_for(plan),
            dependency_packets=[dependency],
            dependency_projections=[review_projection],
        )

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "PROJECTION_DEPENDENCY_INVALID",
            {item["code"] for item in result["issues"]},
        )
        self.assertIsNone(result["input"])

    def test_review_implementation_verification_preserves_source_projections(
        self,
    ) -> None:
        plan = route_goal_v2(
            "Implement the approved Korean typography and visual hierarchy and verify it",
            "medium",
            intent="implementation",
            repo_path=ROOT,
        )
        baseline = baseline_for(plan)
        review_projection = project_assignment_input(
            ROOT,
            plan,
            "review",
            baseline,
        )
        review_packet = finding_packet(plan, "review")
        implementation_projection = project_assignment_input(
            ROOT,
            plan,
            "implementation",
            baseline,
            dependency_packets=[review_packet],
            dependency_projections=[review_projection],
        )
        self.assertEqual("PASS", implementation_projection["status"])
        implementation_packet = completed_terminal_packet(
            plan,
            "implementation",
            implementation_projection,
        )
        self.assertEqual(
            "PASS",
            validate_assignment_packet(
                implementation_packet,
                plan,
                "implementation",
                implementation_projection,
                repo_path=ROOT,
            )["status"],
        )

        verification_projection = project_assignment_input(
            ROOT,
            plan,
            "verification",
            baseline,
            dependency_packets=[implementation_packet],
            dependency_projections=[implementation_projection],
        )

        self.assertEqual("PASS", verification_projection["status"])
        dependency_ref = verification_projection["input"][
            "dependency_packets"
        ][0]
        self.assertEqual(
            implementation_projection["input"]["projection_digest"],
            dependency_ref["projection_digest"],
        )

    def test_terminal_failure_is_an_observation_not_a_retry_engine(self) -> None:
        plan = route_goal_v2(
            "Implement README contract behavior and verification",
            "medium",
            ["contract"],
            intent="implementation",
            repo_path=ROOT,
        )
        packet = {
            "schema_version": TERMINAL_PACKET_VERSION,
            "plan_id": plan["plan_id"],
            "assignment_id": "implementation",
            "packet_type": "ChangeReceipt",
            "status": "failed_transient",
            "summary": "The public dependency registry timed out once.",
            "evidence_refs": [],
            "retryable": True,
        }
        self.assertEqual(
            "PASS",
            validate_assignment_packet(
                packet,
                plan,
                "implementation",
                repo_path=ROOT,
            )["status"],
        )

        semantic = copy.deepcopy(packet)
        semantic["status"] = "failed_semantic"
        codes = {
            item["code"]
            for item in validate_assignment_packet(
                semantic,
                plan,
                "implementation",
                repo_path=ROOT,
            )["issues"]
        }
        self.assertIn("PACKET_RETRYABLE_MISMATCH", codes)

    def test_cli_projects_and_validates_without_writing_repository_state(
        self,
    ) -> None:
        plan = route_goal_v2(
            "Review the README usage contract",
            "medium",
            ["contract"],
            intent="review",
            repo_path=ROOT,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            baseline_path = root / "baseline.json"
            packet_path = root / "packet.json"
            write_json(plan_path, plan)
            write_json(baseline_path, baseline_for(plan))
            write_json(packet_path, finding_packet(plan, "review"))

            output = StringIO()
            with redirect_stdout(output):
                project_code = main(
                    [
                        "assignment",
                        "project",
                        "--repo",
                        str(ROOT),
                        "--plan",
                        str(plan_path),
                        "--assignment",
                        "review",
                        "--baseline",
                        str(baseline_path),
                        "--json",
                    ]
                )
            projection = json.loads(output.getvalue())
            projection_path = root / "projection.json"
            write_json(projection_path, projection)

            output = StringIO()
            with redirect_stdout(output):
                validation_code = main(
                    [
                        "validate-packet",
                        "--repo",
                        str(ROOT),
                        "--plan",
                        str(plan_path),
                        "--assignment",
                        "review",
                        "--packet",
                        str(packet_path),
                        "--projection",
                        str(projection_path),
                        "--json",
                    ]
                )

        self.assertEqual(0, project_code)
        self.assertEqual(0, validation_code)
        self.assertEqual("PASS", json.loads(output.getvalue())["status"])

    def test_malformed_contracts_fail_closed_without_crashing(self) -> None:
        plan = route_goal_v2(
            "Review the README usage contract",
            "medium",
            ["contract"],
            intent="review",
            repo_path=ROOT,
        )
        malformed = (
            None,
            True,
            0,
            "packet",
            [],
            {},
            {"schema_version": []},
            {"schema_version": FINDING_PACKET_VERSION},
            {"schema_version": TERMINAL_PACKET_VERSION},
        )
        for value in malformed:
            with self.subTest(value=value):
                self.assertEqual(
                    "FAIL",
                    validate_engineering_baseline(
                        value,
                        repo_path=ROOT,
                        plan=plan,
                    )["status"],
                )
                self.assertEqual(
                    "FAIL",
                    validate_assignment_packet(
                        value,
                        plan,
                        "review",
                        repo_path=ROOT,
                    )["status"],
                )


if __name__ == "__main__":
    unittest.main()
