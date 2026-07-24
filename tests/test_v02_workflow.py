from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from maestro.governance import govern_report, record_run
from maestro.doctor import doctor_report
from maestro.errors import MaestroError
from maestro.project import apply_plan, build_init_plan, build_upgrade_plan
from maestro.registry import load_host_profile, route_goal
from maestro.status import status_report
from tests.support import apply_fresh_init, canonical_document, write_json


class CoreWorkflowV02Tests(unittest.TestCase):
    def test_init_creates_small_core_docs_and_project_local_improvement_policy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            self.assertTrue((repo / "docs/project.md").is_file())
            self.assertTrue((repo / "docs/architecture.md").is_file())
            self.assertEqual(
                {
                    "mode": "verified-project-conventions",
                    "max_updates_per_run": 1,
                },
                project["self_improvement"],
            )
            self.assertEqual("markdown", project["documentation"]["provider"])
            self.assertEqual(
                {
                    "project": "docs/project.md",
                    "architecture": "docs/architecture.md",
                },
                project["documentation"]["core_documents"],
            )
            guidance = (repo / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(
                "keep same-run reusable rules as candidates",
                guidance,
            )
            self.assertIn("`owner_decision`", guidance)
            self.assertIn("`held_out_evaluation`", guidance)

    def test_init_maps_existing_core_doc_equivalents_without_copying_them(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            (repo / "docs/architecture").mkdir(parents=True)
            (repo / "PROJECT.md").write_text("# Existing project\n", encoding="utf-8")
            (repo / "docs/architecture/overview.md").write_text(
                canonical_document(
                    "existing-architecture",
                    body="# Existing architecture\n",
                ).replace("type: convention", "type: architecture"),
                encoding="utf-8",
            )

            apply_fresh_init(repo)

            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                "PROJECT.md",
                project["documentation"]["core_documents"]["project"],
            )
            self.assertEqual(
                "docs/architecture/overview.md",
                project["documentation"]["core_documents"]["architecture"],
            )
            self.assertFalse((repo / "docs/project.md").exists())
            self.assertFalse((repo / "docs/architecture.md").exists())
            self.assertEqual("PASS", doctor_report(repo)["status"])

    def test_custom_document_adapter_is_a_local_instruction_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            instructions = repo / ".maestro/adapters/team-docs.md"
            instructions.parent.mkdir(parents=True)
            instructions.write_text(
                "# Team docs\nReturn repository-relative document references.\n",
                encoding="utf-8",
            )
            project_path = repo / ".maestro/project.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project["documentation"] = {
                "provider": "custom",
                "entrypoint": ".maestro/adapters/team-docs.md",
                "core_documents": project["documentation"]["core_documents"],
                "external_topics": {},
                "custom_adapter": {
                    "id": "team-docs",
                    "instructions_path": ".maestro/adapters/team-docs.md",
                },
            }
            write_json(project_path, project)

            from maestro.documents import select_documents

            packet = select_documents(repo, "change login", [])
            self.assertEqual("custom_adapter_required", packet["evidence_status"])
            self.assertEqual("team-docs", packet["custom_adapter"]["id"])
            self.assertNotIn("command", packet["custom_adapter"])
            self.assertFalse(packet["writes_performed"])

            project["documentation"]["custom_adapter"]["command"] = "unsafe"
            write_json(project_path, project)
            with self.assertRaises(MaestroError) as raised:
                select_documents(repo, "change login", [])
            self.assertEqual("CUSTOM_ADAPTER_INVALID", raised.exception.code)

    def test_status_is_read_only_and_reports_the_next_bounded_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            before = sorted(path.relative_to(repo) for path in repo.rglob("*"))

            report = status_report(repo)

            after = sorted(path.relative_to(repo) for path in repo.rglob("*"))
            self.assertEqual(before, after)
            self.assertFalse(report["initialized"])
            self.assertEqual("run_init", report["next_actions"][0]["id"])
            self.assertFalse(report["writes_performed"])

    def test_upgrade_reuses_the_reviewed_init_plan_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            plan = build_upgrade_plan(repo)

            self.assertEqual("upgrade", plan["command"])
            plan_path = Path(temporary) / "upgrade.json"
            write_json(plan_path, plan)
            result = apply_plan(plan_path, repo, expected_command="upgrade")
            self.assertEqual("upgrade", result["command"])
            self.assertFalse(result["writes_performed"])

    def test_model_names_come_from_the_selected_host_profile(self) -> None:
        profile = load_host_profile("codex")
        route = route_goal("review architecture", "medium", host_id="codex")

        selected_class = route["model_route"]["selected_class"]
        self.assertEqual("codex", route["model_route"]["host"])
        self.assertEqual(
            profile["classes"][selected_class]["model"],
            route["model_route"]["selected_model"],
        )

    def test_record_run_appends_one_compact_project_scoped_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            convention = repo / "docs/conventions/run-receipts.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                canonical_document(
                    "run-receipts",
                    body="# Run receipts\n\nRecord one final receipt.\n",
                ),
                encoding="utf-8",
            )
            receipt_path = Path(temporary) / "receipt.json"
            write_json(
                receipt_path,
                {
                    "run_id": "run-1",
                    "risk": "low",
                    "route_depth": "fast",
                    "selected_lenses": [],
                    "executor_runs": 2,
                    "primary_executor_id": "implementation-engineer",
                    "executor_ids": ["implementation-engineer", "verifier"],
                    "outcome": "completed",
                    "evidence_refs": ["tests:test_record_run"],
                    "duration_ms": 1200,
                    "tokens": {"total": 42},
                    "correction_count": 0,
                    "agent_calls": 2,
                    "verifier_result": "passed",
                    "command_artifact_ref": "tests.log",
                    "project_convention_action": "created",
                    "project_convention_basis": "owner_decision",
                    "project_convention_path": "docs/conventions/run-receipts.md",
                },
            )

            result = record_run(repo, receipt_path)
            repeated = record_run(repo, receipt_path)

            self.assertEqual("recorded", result["status"])
            self.assertEqual("already_recorded", repeated["status"])
            self.assertFalse(repeated["writes_performed"])
            event_path = repo / result["event_path"]
            lines = event_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(lines))
            event = json.loads(lines[0])
            self.assertEqual("run_summary", event["kind"])
            self.assertEqual("run-1", event["run_id"])
            self.assertEqual("created", event["project_convention_action"])
            self.assertEqual("owner_decision", event["project_convention_basis"])
            self.assertNotIn("messages", event)

    def test_same_run_evidence_cannot_activate_a_convention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            convention = repo / "docs/conventions/unsafe-promotion.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                canonical_document("unsafe-promotion"),
                encoding="utf-8",
            )
            receipt_path = Path(temporary) / "receipt.json"
            write_json(
                receipt_path,
                {
                    "run_id": "run-same-run-promotion",
                    "risk": "medium",
                    "route_depth": "standard",
                    "selected_lenses": [],
                    "executor_runs": 2,
                    "primary_executor_id": "implementation-engineer",
                    "executor_ids": ["implementation-engineer", "verifier"],
                    "outcome": "completed",
                    "evidence_refs": ["tests:passed"],
                    "duration_ms": 10,
                    "tokens": None,
                    "correction_count": 0,
                    "agent_calls": 2,
                    "verifier_result": "passed",
                    "command_artifact_ref": "tests.log",
                    "project_convention_action": "created",
                    "project_convention_basis": "same_run_candidate",
                    "project_convention_path": (
                        "docs/conventions/unsafe-promotion.md"
                    ),
                },
            )

            with self.assertRaises(MaestroError) as raised:
                record_run(repo, receipt_path)

            self.assertEqual("RUN_RECEIPT_INVALID", raised.exception.code)
            self.assertFalse((repo / ".maestro/state/events").exists())

    def test_same_run_convention_candidate_records_without_active_document(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            receipt_path = Path(temporary) / "receipt.json"
            write_json(
                receipt_path,
                {
                    "run_id": "run-convention-candidate",
                    "risk": "medium",
                    "route_depth": "standard",
                    "selected_lenses": [],
                    "executor_runs": 1,
                    "primary_executor_id": "implementation-engineer",
                    "executor_ids": ["implementation-engineer"],
                    "outcome": "completed",
                    "evidence_refs": ["tests:repeated-rule"],
                    "duration_ms": 10,
                    "tokens": None,
                    "correction_count": 0,
                    "agent_calls": 1,
                    "verifier_result": "not_run",
                    "command_artifact_ref": None,
                    "project_convention_action": "candidate",
                    "project_convention_basis": "same_run_candidate",
                    "project_convention_path": None,
                },
            )

            result = record_run(repo, receipt_path)
            event = json.loads(
                (repo / result["event_path"])
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )

            self.assertEqual("candidate", event["project_convention_action"])
            self.assertEqual(
                "same_run_candidate",
                event["project_convention_basis"],
            )
            self.assertIsNone(event["project_convention_path"])
            self.assertFalse((repo / "docs/conventions").exists())

    def test_reused_run_id_rejects_different_receipt_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            receipt_path = Path(temporary) / "receipt.json"
            receipt = {
                "run_id": "run-conflict",
                "risk": "low",
                "route_depth": "fast",
                "selected_lenses": [],
                "executor_runs": 1,
                "primary_executor_id": "implementation-engineer",
                "executor_ids": ["implementation-engineer"],
                "outcome": "completed",
                "evidence_refs": ["tests:first"],
                "duration_ms": 10,
                "tokens": {"total": 10},
                "correction_count": 0,
                "agent_calls": 1,
                "verifier_result": "not_run",
                "command_artifact_ref": None,
            }
            write_json(receipt_path, receipt)
            first = record_run(repo, receipt_path)

            receipt["tokens"] = {"total": 11}
            write_json(receipt_path, receipt)
            with self.assertRaises(MaestroError) as raised:
                record_run(repo, receipt_path)

            self.assertEqual("RUN_ID_CONFLICT", raised.exception.code)
            self.assertEqual(
                1,
                len(
                    (repo / first["event_path"])
                    .read_text(encoding="utf-8")
                    .splitlines()
                ),
            )

    def test_public_receipts_can_open_a_governance_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            for index in range(3):
                receipt_path = Path(temporary) / f"receipt-{index}.json"
                write_json(
                    receipt_path,
                    {
                        "run_id": f"run-correction-{index}",
                        "kind": "correction",
                        "fingerprint": "repeated-verification-gap",
                        "finding_severity": "high",
                        "risk": "medium",
                        "route_depth": "standard",
                        "selected_lenses": ["test-proof"],
                        "executor_runs": 2,
                        "primary_executor_id": "lens-reviewer",
                        "executor_ids": ["lens-reviewer", "verifier"],
                        "outcome": "corrected",
                        "evidence_refs": [f"tests:correction-{index}"],
                        "duration_ms": 20,
                        "tokens": None,
                        "correction_count": 1,
                        "correction_summary": ["Verifier exposed the same gap."],
                        "agent_calls": 2,
                        "human_fix_required": False,
                        "decision_changed": True,
                        "verifier_result": "failed",
                        "command_artifact_ref": f"tests-{index}.log",
                    },
                )
                result = record_run(repo, receipt_path)
                self.assertEqual("recorded", result["status"])

            report = govern_report(repo, window=20, threshold=3)

            self.assertEqual(
                [
                    {
                        "fingerprint": "repeated-verification-gap",
                        "occurrences": 3,
                        "status": "candidate_for_review",
                        "automatic_change_allowed": False,
                    }
                ],
                report["candidates_for_review"],
            )


if __name__ == "__main__":
    unittest.main()
