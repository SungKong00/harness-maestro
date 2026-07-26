from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from tests.support import ROOT, write_json

from maestro.assignment_contracts import (
    ASSIGNMENT_INPUT_VERSION,
    ENGINEERING_BASELINE_VERSION,
    FINDING_PACKET_VERSION,
    TERMINAL_PACKET_VERSION,
    project_assignment_input,
    validate_assignment_packet,
    validate_engineering_baseline,
)
from maestro.cli import main
from maestro.planning import route_goal_v2
from maestro.util import canonical_json, sha256_text


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


class AssignmentBoundaryContractTests(unittest.TestCase):
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
        self.assertEqual(["README.md"], [
            item["path"] for item in projected["document_refs"]
        ])
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

        result = project_assignment_input(
            ROOT,
            plan,
            "implementation",
            baseline_for(plan),
            dependency_packets=[dependency],
        )

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "PROJECTION_DEPENDENCY_INVALID",
            {item["code"] for item in result["issues"]},
        )
        self.assertIsNone(result["input"])

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
