from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.support import ROOT, apply_fresh_init, write_json

from maestro.cli import main
from maestro.governance import govern_report, record_run
from maestro.planning import route_goal_v2, validate_route_v2
from maestro.registry import load_registry, validate_registry
from maestro.snapshot import snapshot_report
from maestro.util import canonical_json, sha256_text


def _rehash(plan: dict[str, object]) -> None:
    payload = copy.deepcopy(plan)
    payload.pop("plan_id", None)
    plan["plan_id"] = sha256_text(canonical_json(payload))


class ExpertiseRegistryTests(unittest.TestCase):
    def test_expertise_packs_are_registry_backed_and_resolvable(self) -> None:
        registry = load_registry()

        self.assertEqual([], validate_registry(registry))
        self.assertEqual(
            {"marketing", "product-design", "software-qa"},
            {
                pack["expertise_pack_id"]
                for pack in registry["expertise_packs"]
            },
        )
        for pack in registry["expertise_packs"]:
            with self.subTest(pack=pack["expertise_pack_id"]):
                self.assertEqual("expertise-pack", pack["kind"])
                self.assertEqual("pilot", pack["status"])
                skill_root = ROOT / "skills" / pack["skill_id"]
                self.assertTrue((skill_root / "SKILL.md").is_file())
                self.assertTrue(
                    (skill_root / pack["source_manifest"]).is_file()
                )
                self.assertTrue(
                    (skill_root / pack["evaluation_suite"]).is_file()
                )
                for guide in pack["guides"]:
                    self.assertTrue(
                        (
                            skill_root
                            / "references"
                            / f"{guide['guide_id']}.md"
                        ).is_file()
                    )

    def test_expertise_candidate_schema_and_builder_are_bundled(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "src/maestro/resources/schemas/expertise-candidate.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            "maestro_expertise_candidate_v1",
            schema["properties"]["schema_version"]["const"],
        )
        quality_schema = json.loads(
            (
                ROOT
                / "src/maestro/resources/schemas/"
                "expertise-quality-evaluation.schema.json"
            ).read_text(encoding="utf-8")
        )
        artifact_schema = json.loads(
            (
                ROOT
                / "src/maestro/resources/schemas/"
                "expertise-case-artifact.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            "maestro_expertise_quality_eval_v1",
            quality_schema["properties"]["schema_version"]["const"],
        )
        self.assertEqual(
            "maestro_expertise_case_artifact_v1",
            artifact_schema["properties"]["schema_version"]["const"],
        )
        builder = ROOT / "skills/maestro-expertise-builder/SKILL.md"
        self.assertTrue(builder.is_file())
        text = builder.read_text(encoding="utf-8")
        self.assertIn(".maestro/state/candidates/expertise/", text)
        self.assertIn("Candidate use is not publication", text)
        self.assertIn("immediately eligible", text)
        self.assertIn("## Entry contract", text)
        self.assertIn("## Definition of done", text)
        self.assertIn("evals/quality.json", text)
        self.assertIn("Repair validator failures at most twice", text)
        maestro = (
            ROOT / "skills/maestro/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Expertise authoring intent", maestro)
        self.assertIn(
            "user does not need to restate the\n     lifecycle",
            maestro,
        )


class ExpertiseRoutingTests(unittest.TestCase):
    def test_routine_design_reuses_only_selected_guides(self) -> None:
        plan = route_goal_v2(
            "Improve the product dashboard layout",
            "medium",
            intent="implementation",
        )

        expertise = plan["expertise"]
        self.assertEqual(["product-design"], expertise["selected_pack_ids"])
        self.assertEqual("reuse", expertise["research_requirement"]["mode"])
        self.assertEqual(
            "not-required",
            expertise["research_requirement"]["gate"],
        )
        self.assertLessEqual(len(expertise["selected_guide_ids"]), 4)
        result = validate_route_v2(plan)
        self.assertEqual("PASS", result["status"])
        self.assertEqual("READY", result["execution_status"])
        for assignment in plan["assignments"]:
            if assignment["kind"] == "verification":
                self.assertNotIn("expertise_pack_ids", assignment)
            else:
                self.assertEqual(
                    ["product-design"],
                    assignment["expertise_pack_ids"],
                )

    def test_korean_typography_guide_is_selected_without_general_research(self) -> None:
        plan = route_goal_v2(
            "한글 웹 디자인의 폰트와 글자 위계를 개선해줘",
            "medium",
            intent="implementation",
        )

        expertise = plan["expertise"]
        self.assertIn("typography-korean", expertise["selected_guide_ids"])
        self.assertIn(
            "visual-hierarchy-layout",
            expertise["selected_guide_ids"],
        )
        self.assertEqual("reuse", expertise["research_requirement"]["mode"])

    def test_current_reference_work_opens_then_satisfies_research_gate(self) -> None:
        goal = "최신 레퍼런스를 찾아 현대적인 랜딩 페이지를 디자인해줘"
        open_plan = route_goal_v2(
            goal,
            "medium",
            intent="implementation",
        )

        requirement = open_plan["expertise"]["research_requirement"]
        self.assertEqual("contextualize", requirement["mode"])
        self.assertEqual("open", requirement["gate"])
        self.assertIn(
            "EXPERTISE_RESEARCH_REQUIRED",
            [
                warning["code"]
                for warning in open_plan["expertise"]["warnings"]
            ],
        )
        open_result = validate_route_v2(open_plan)
        self.assertEqual("PASS", open_result["status"])
        self.assertEqual("RESEARCH_REQUIRED", open_result["execution_status"])

        ready_plan = route_goal_v2(
            goal,
            "medium",
            intent="implementation",
            research_evidence_digest="a" * 64,
        )
        ready_requirement = ready_plan["expertise"]["research_requirement"]
        self.assertEqual("satisfied", ready_requirement["gate"])
        self.assertEqual("a" * 64, ready_requirement["evidence_digest"])
        self.assertEqual(
            [item["assignment_id"] for item in open_plan["assignments"]],
            [item["assignment_id"] for item in ready_plan["assignments"]],
        )
        ready_result = validate_route_v2(ready_plan)
        self.assertEqual("PASS", ready_result["status"])
        self.assertEqual("READY", ready_result["execution_status"])

    def test_research_intent_performs_discovery_inside_its_assignment(self) -> None:
        plan = route_goal_v2(
            "Research architecture choice best practices",
            "medium",
            intent="research",
        )

        self.assertEqual(
            "discover",
            plan["expertise"]["research_requirement"]["mode"],
        )
        self.assertEqual(
            "in-plan",
            plan["expertise"]["research_requirement"]["gate"],
        )
        result = validate_route_v2(plan)
        self.assertEqual("READY", result["execution_status"])

    def test_tampered_pack_selection_is_rejected(self) -> None:
        plan = route_goal_v2(
            "Improve the web design layout",
            "medium",
            intent="review",
        )
        plan["expertise"]["selected_guide_ids"] = ["invented-guide"]
        _rehash(plan)

        result = validate_route_v2(plan)

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "ADAG_EXPERTISE_SELECTION_MISMATCH",
            {issue["code"] for issue in result["issues"]},
        )

    def test_optional_extension_preserves_pre_expertise_v2_compatibility(self) -> None:
        plan = route_goal_v2(
            "Review the web design layout",
            "medium",
            intent="review",
        )
        plan.pop("expertise")
        for assignment in plan["assignments"]:
            assignment.pop("expertise_pack_ids", None)
            assignment.pop("decision_guide_ids", None)
        _rehash(plan)

        result = validate_route_v2(plan)

        self.assertEqual("PASS", result["status"])
        self.assertEqual("READY", result["execution_status"])

    def test_cli_research_digest_requires_artifact(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "route",
                    "--goal",
                    "Review the API contract",
                    "--research-evidence-digest",
                    "a" * 64,
                    "--json",
                ]
            )

        result = json.loads(output.getvalue())
        self.assertEqual(2, exit_code)
        self.assertEqual(
            "RESEARCH_EVIDENCE_ARTIFACT_REQUIRED",
            result["code"],
        )

    def test_validate_plan_uses_nonzero_exit_for_open_research_gate(self) -> None:
        plan = route_goal_v2(
            "Find current references for a modern landing page design",
            "medium",
            intent="implementation",
            repo_path=ROOT,
        )
        with tempfile.TemporaryDirectory() as temporary:
            plan_path = Path(temporary) / "plan.json"
            write_json(plan_path, plan)
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "validate-plan",
                        "--plan",
                        str(plan_path),
                        "--json",
                    ]
                )

        result = json.loads(output.getvalue())
        self.assertEqual(4, exit_code)
        self.assertEqual("PASS", result["status"])
        self.assertEqual("RESEARCH_REQUIRED", result["execution_status"])

    def test_frozen_product_design_cases_match_modes_and_guides(self) -> None:
        cases = json.loads(
            (
                ROOT / "skills/maestro-product-design/evals/cases.json"
            ).read_text(encoding="utf-8")
        )["cases"]

        for case in cases:
            with self.subTest(case=case["case_id"]):
                plan = route_goal_v2(
                    case["goal"],
                    "medium",
                    intent="implementation",
                )
                expertise = plan.get("expertise")
                if expertise is None:
                    self.assertIsNone(case["expected_pack_id"])
                    self.assertEqual("reuse", case["expected_mode"])
                    self.assertEqual([], case["expected_guides"])
                    continue
                self.assertEqual(
                    (
                        [case["expected_pack_id"]]
                        if case["expected_pack_id"] is not None
                        else []
                    ),
                    expertise["selected_pack_ids"],
                )
                self.assertEqual(
                    case["expected_mode"],
                    expertise["research_requirement"]["mode"],
                )
                self.assertTrue(
                    set(case["expected_guides"]).issubset(
                        expertise["selected_guide_ids"]
                    )
                )

    def test_frozen_marketing_and_qa_cases_match_modes_and_guides(self) -> None:
        for skill_id in ("maestro-marketing", "maestro-software-qa"):
            cases = json.loads(
                (ROOT / f"skills/{skill_id}/evals/cases.json").read_text(
                    encoding="utf-8"
                )
            )["cases"]
            for case in cases:
                with self.subTest(skill=skill_id, case=case["case_id"]):
                    plan = route_goal_v2(
                        case["goal"],
                        "medium",
                        intent="implementation",
                    )
                    expertise = plan.get(
                        "expertise",
                        {
                            "selected_pack_ids": [],
                            "selected_guide_ids": [],
                            "research_requirement": {"mode": "reuse"},
                        },
                    )
                    self.assertEqual(
                        (
                            [case["expected_pack_id"]]
                            if case["expected_pack_id"] is not None
                            else []
                        ),
                        expertise["selected_pack_ids"],
                    )
                    self.assertEqual(
                        case["expected_mode"],
                        expertise["research_requirement"]["mode"],
                    )
                    self.assertTrue(
                        set(case["expected_guides"]).issubset(
                            expertise["selected_guide_ids"]
                        )
                    )

    def test_landing_page_routes_by_dominant_decision(self) -> None:
        visual = route_goal_v2(
            "Improve the Korean typography and visual hierarchy of this landing page",
            "medium",
            intent="review",
        )
        message = route_goal_v2(
            "Choose positioning and landing page messaging for this campaign",
            "medium",
            intent="review",
        )
        implementation_copy = route_goal_v2(
            "Implement the approved positioning copy on the landing page",
            "medium",
            intent="implementation",
        )

        self.assertEqual(
            ["product-design"],
            visual["expertise"]["selected_pack_ids"],
        )
        self.assertEqual(
            ["marketing"],
            message["expertise"]["selected_pack_ids"],
        )
        self.assertEqual(
            ["marketing"],
            implementation_copy["expertise"]["selected_pack_ids"],
        )


class ExpertiseReceiptTests(unittest.TestCase):
    def test_receipt_records_compact_expertise_usage_for_governance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            receipt_path = Path(temporary) / "receipt.json"
            write_json(
                receipt_path,
                {
                    "run_id": "design-run",
                    "risk": "low",
                    "route_depth": "fast",
                    "selected_lenses": [],
                    "selected_expertise_packs": ["product-design"],
                    "selected_decision_guides": [
                        "design-brief",
                        "visual-hierarchy-layout",
                    ],
                    "expertise_research_mode": "contextualize",
                    "expertise_research_gate": "satisfied",
                    "executor_runs": 1,
                    "primary_executor_id": "implementation-engineer",
                    "executor_ids": ["implementation-engineer"],
                    "outcome": "completed",
                    "evidence_refs": ["screenshots:after"],
                    "duration_ms": 100,
                    "tokens": None,
                    "correction_count": 0,
                    "agent_calls": 1,
                    "verifier_result": "not_run",
                    "command_artifact_ref": None,
                },
            )

            result = record_run(repo, receipt_path)
            event = json.loads(
                (repo / result["event_path"])
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            report = govern_report(repo, window=20, threshold=2)
            snapshot = snapshot_report(repo, window=20)

            self.assertEqual(
                ["product-design"],
                event["selected_expertise_packs"],
            )
            self.assertEqual(
                "contextualize",
                event["expertise_research_mode"],
            )
            self.assertEqual(
                {"product-design": 1},
                report["expertise_pack_usage"],
            )
            self.assertEqual(
                {
                    "count": 1,
                    "last_used_timestamp": event["timestamp"],
                    "recent_run_ids": ["design-run"],
                    "failed_verification_run_count": 0,
                    "corrected_run_count": 0,
                },
                report["decision_guide_usage"]["design-brief"],
            )
            self.assertEqual(
                {
                    "count": 1,
                    "last_used_timestamp": event["timestamp"],
                    "recent_run_ids": ["design-run"],
                    "failed_verification_run_count": 0,
                    "corrected_run_count": 0,
                },
                report["decision_guide_usage"][
                    "visual-hierarchy-layout"
                ],
            )
            self.assertEqual(
                report["decision_guide_usage"],
                snapshot["governance"]["decision_guide_usage"],
            )
            self.assertEqual(
                {"contextualize": 1},
                report["expertise_research_modes"],
            )


if __name__ == "__main__":
    unittest.main()
