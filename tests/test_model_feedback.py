from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import ROOT, apply_fresh_init, event, write_json

from maestro import __version__
from maestro.execution_units import project_route_execution_units
from maestro.errors import MaestroError
from maestro.model_feedback import (
    MODEL_FEEDBACK_REPORT_VERSION,
    MODEL_POLICY_OVERLAY_VERSION,
    build_model_feedback_report,
    build_model_policy_overlay,
    current_model_policy_authority,
    validate_model_feedback_report,
    validate_model_policy_overlay,
    validate_model_policy_overlay_authority,
    validate_verification_assessment,
    wilson_interval,
)
from maestro.observations import _assignment_plan_summary
from maestro.planning import route_goal_v2
from maestro.request_records import project_request_records
from maestro.snapshot_runs import _run_card
from maestro.util import canonical_json, file_sha256, sha256_text


def _assessment(
    writer: dict[str, object],
    verifier: dict[str, object],
    *,
    failed: bool,
) -> dict[str, object]:
    value = {
        "schema_version": "maestro_verification_assessment_v1",
        "assessment_id": "",
        "packet_digest": sha256_text(
            f"packet:{writer['assignment_id']}:{failed}"
        ),
        "verifier_assignment_id": verifier["assignment_id"],
        "target_assignment_id": writer["assignment_id"],
        "target_execution_unit_id": writer["execution_unit_id"],
        "target_model_route_id": writer["model_route_id"],
        "verdict": "failed" if failed else "passed",
        "failure_cause": "implementation" if failed else "none",
        "failure_categories": ["correctness"] if failed else [],
        "evidence_refs": ["tests:model-feedback:verification"],
    }
    value["assessment_id"] = sha256_text(
        canonical_json({**value, "assessment_id": ""})
    )
    return value


class ModelFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.route = route_goal_v2(
            "Implement API behavior and tests",
            "medium",
            ["contract", "test-proof"],
            intent="implementation",
        )
        units = {
            unit["local_unit_id"]: unit
            for unit in project_route_execution_units(self.route)
        }
        self.plan = {
            "schema_version": "maestro_plan_summary_v1",
            "plan_id": self.route["plan_id"],
            "risk": self.route["risk"],
            "execution_receipts_required": True,
            "assignments": [
                _assignment_plan_summary(
                    assignment,
                    execution_unit=units[assignment["assignment_id"]],
                )
                for assignment in self.route["assignments"]
            ],
        }
        self.writer = next(
            assignment
            for assignment in self.plan["assignments"]
            if assignment["mutation_owner"] is True
        )
        self.verifier = next(
            assignment
            for assignment in self.plan["assignments"]
            if assignment["executor_id"] == "verifier"
        )

    def _events(
        self,
        *,
        samples: int,
        failures: int,
        authority: dict[str, str] | None = None,
        rerouted_index: int | None = None,
    ) -> list[dict[str, object]]:
        authority = authority or {
            "project_id": "model-feedback-project",
            "checkout_id": "a" * 12,
            "registry_digest": "b" * 64,
            "framework_version": __version__,
        }
        events = []
        for index in range(samples):
            failed = index < failures
            rerouted = index == rerouted_index
            fallback = self.writer["fallback_route"]
            actual_model = (
                fallback["selected_model"]
                if rerouted
                else self.writer["planned_model"]
            )
            reroutes = (
                [
                    {
                        "from_model": self.writer["planned_model"],
                        "to_model": actual_model,
                        "reason": "selected model unavailable",
                    }
                ]
                if rerouted
                else []
            )
            assessment = _assessment(
                self.writer,
                self.verifier,
                failed=failed,
            )
            events.append(
                {
                    "run_id": f"feedback-run-{index:03d}",
                    "observation_id": f"feedback-observation-{index:03d}",
                    "framework_version": authority[
                        "framework_version"
                    ],
                    "project_id": authority["project_id"],
                    "checkout_id": authority["checkout_id"],
                    "registry_digest": authority["registry_digest"],
                    "risk": self.route["risk"],
                    "execution_binding": {
                        "schema_version": "maestro_execution_binding_v1",
                        "mode": "maestro_owned_codex_app_server",
                    },
                    "plan_summary": copy.deepcopy(self.plan),
                    "stage_results": [
                        {
                            "assignment_id": self.writer["assignment_id"],
                            "status": "completed",
                            "model_route_id": self.writer["model_route_id"],
                            "execution_unit_id": self.writer[
                                "execution_unit_id"
                            ],
                            "model_evidence": "complete",
                            "actual_model": actual_model,
                            "reroutes": reroutes,
                            "execution_unit_receipt": {
                                "fixture": "validated-by-boundary-patch"
                            },
                        },
                        {
                            "assignment_id": self.verifier[
                                "assignment_id"
                            ],
                            "status": "completed",
                            "evidence_refs": [
                                "assignment-packet:"
                                + assessment["packet_digest"]
                            ],
                            "execution_unit_receipt": {
                                "output_packet_digest": assessment[
                                    "packet_digest"
                                ],
                                "verification_assessment_id": (
                                    assessment["assessment_id"]
                                ),
                            },
                            "verification_assessment": assessment,
                        },
                    ],
                    "verifier_result": "failed" if failed else "passed",
                    "completion_policy": {},
                    "completion_closure": {},
                    "execution_measurements": {},
                    "work_spans": [],
                }
            )
        return events

    def _build_report(
        self,
        events: list[dict[str, object]],
        **options: object,
    ) -> dict[str, object]:
        receipt_result = {
            "schema_version": (
                "maestro_stage_execution_receipt_validation_v1"
            ),
            "status": "PASS",
            "issues": [],
            "writes_performed": False,
        }
        with (
            patch(
                "maestro.execution_units.validate_stage_execution_receipts",
                return_value=receipt_result,
            ),
            patch(
                "maestro.work.validate_completion_policy",
                return_value=True,
            ),
            patch(
                "maestro.work.validate_execution_measurements",
                return_value=True,
            ),
            patch(
                "maestro.work.validate_completion_closure",
                return_value=True,
            ),
        ):
            return build_model_feedback_report(events, **options)

    def test_wilson_interval_has_safe_zero_and_gate_boundary(self) -> None:
        self.assertEqual((None, None), wilson_interval(0, 0))
        lower, upper = wilson_interval(6, 20)
        self.assertIsNotNone(lower)
        self.assertIsNotNone(upper)
        assert lower is not None
        assert upper is not None
        self.assertGreater(lower, 0.10)
        self.assertLess(lower, 6 / 20)
        self.assertGreater(upper, 6 / 20)

        with self.assertRaises(MaestroError) as raised:
            build_model_feedback_report(
                [{} for _ in range(201)],
                evidence_window=200,
            )
        self.assertEqual(
            "MODEL_FEEDBACK_WINDOW_EXCEEDED",
            raised.exception.code,
        )

    def test_feedback_separates_three_failure_axes_and_never_writes(self) -> None:
        report = self._build_report(
            self._events(samples=20, failures=6)
        )
        self.assertTrue(validate_model_feedback_report(report))
        self.assertEqual(MODEL_FEEDBACK_REPORT_VERSION, report["schema_version"])
        self.assertFalse(report["automatic_policy_mutation_allowed"])
        self.assertFalse(report["writes_performed"])
        self.assertFalse(report["policy"]["automatic_downgrade_allowed"])
        group = report["groups"][0]
        self.assertEqual(20, group["route_recommendation_failure"]["sample_count"])
        self.assertEqual(20, group["applied_model_failure"]["sample_count"])
        self.assertEqual(20, group["model_attributed_failure"]["sample_count"])
        self.assertEqual(6, group["model_attributed_failure"]["failure_count"])
        self.assertEqual("eligible", group["evaluation_gate"]["state"])
        self.assertEqual("quality_escalation", group["advice"]["action"])
        self.assertEqual("frontier", group["advice"]["target"]["selected_class"])

    def test_rerouted_run_is_observed_but_not_attributed_to_recommendation(
        self,
    ) -> None:
        report = self._build_report(
            self._events(
                samples=20,
                failures=6,
                rerouted_index=0,
            )
        )
        self.assertTrue(validate_model_feedback_report(report))
        group = report["groups"][0]
        self.assertEqual(20, group["route_recommendation_failure"]["sample_count"])
        self.assertEqual(20, group["applied_model_failure"]["sample_count"])
        self.assertEqual(19, group["model_attributed_failure"]["sample_count"])
        self.assertEqual(1, group["model_attributed_failure"]["excluded_count"])
        self.assertEqual(
            1,
            group["model_attributed_failure"]["exclusion_reasons"][
                "applied-route-differs-from-recommendation"
            ],
        )

    def test_feedback_excludes_noncurrent_framework_authority(
        self,
    ) -> None:
        authority = {
            "project_id": "model-feedback-project",
            "checkout_id": "a" * 12,
            "registry_digest": "b" * 64,
            "framework_version": __version__,
        }
        events = self._events(
            samples=20,
            failures=6,
            authority=authority,
        )
        events[0]["framework_version"] = "0.2.0"
        report = self._build_report(
            events,
            expected_authority=authority,
        )
        self.assertTrue(validate_model_feedback_report(report))
        self.assertEqual(19, report["source"]["run_count"])
        self.assertEqual(
            1,
            report["source"]["exclusion_reasons"][
                "current-definition-authority-mismatch"
            ],
        )
        self.assertEqual(
            __version__,
            report["authority"]["framework_version"],
        )

    def test_nonproduction_or_incomplete_windows_cannot_create_overlay(
        self,
    ) -> None:
        events = self._events(samples=20, failures=6)
        reports = [
            self._build_report(events, evidence_window=201),
            self._build_report(events, source_complete=False),
        ]
        for report in reports:
            with self.subTest(source=report["source"]):
                with self.assertRaises(MaestroError) as raised:
                    build_model_policy_overlay(
                        report,
                        group_id=report["groups"][0]["group_id"],
                        basis="owner_decision",
                        approval_ref=(
                            "owner_decision:"
                            ".maestro/nonexistent-approval.json"
                        ),
                        repo_path=ROOT,
                    )
                self.assertEqual(
                    "MODEL_POLICY_OVERLAY_POLICY_INVALID",
                    raised.exception.code,
                )

    def test_missing_real_receipt_can_never_become_attributed_evidence(
        self,
    ) -> None:
        report = build_model_feedback_report(
            self._events(samples=1, failures=1)
        )
        self.assertTrue(validate_model_feedback_report(report))
        attributed = report["groups"][0]["model_attributed_failure"]
        self.assertEqual(0, attributed["sample_count"])
        self.assertEqual(1, attributed["excluded_count"])
        self.assertEqual(
            1,
            attributed["exclusion_reasons"][
                "execution-unit-receipt-missing-or-invalid"
            ],
        )

    def test_verification_assessment_is_exact_and_tamper_evident(self) -> None:
        assessment = _assessment(
            self.writer,
            self.verifier,
            failed=True,
        )
        self.assertTrue(
            validate_verification_assessment(
                assessment,
                plan_summary=self.plan,
            )
        )
        verifier_stage = {
            "evidence_refs": [
                "assignment-packet:" + assessment["packet_digest"]
            ],
            "execution_unit_receipt": {
                "output_packet_digest": assessment["packet_digest"],
                "verification_assessment_id": assessment[
                    "assessment_id"
                ],
            },
        }
        self.assertTrue(
            validate_verification_assessment(
                assessment,
                plan_summary=self.plan,
                verifier_stage=verifier_stage,
            )
        )
        changed = copy.deepcopy(assessment)
        changed["target_assignment_id"] = "review"
        self.assertFalse(
            validate_verification_assessment(
                changed,
                plan_summary=self.plan,
            )
        )
        changed_cause = copy.deepcopy(assessment)
        changed_cause["failure_cause"] = "specification"
        changed_cause["assessment_id"] = sha256_text(
            canonical_json(
                {
                    **changed_cause,
                    "assessment_id": "",
                }
            )
        )
        self.assertFalse(
            validate_verification_assessment(
                changed_cause,
                plan_summary=self.plan,
                verifier_stage=verifier_stage,
            )
        )

    def test_snapshot_links_only_the_exact_current_writer_subject(self) -> None:
        report = self._build_report(
            self._events(samples=20, failures=6)
        )
        raw = event(
            "model-feedback-project",
            "a" * 12,
            "feedback-projection",
            "feedback-projection",
        )
        raw["plan_summary"] = copy.deepcopy(self.plan)
        raw["stage_results"] = []
        current = _run_card(
            raw,
            history_evidence={
                "governance_eligible": True,
                "definition_status": "current",
            },
            model_feedback_report=report,
        )
        reference = current["model_feedback_ref"]
        self.assertEqual(
            self.writer["assignment_id"],
            next(
                stage["assignment_id"]
                for stage in current["flow"]
                if stage.get("model_feedback_ref") == reference
            ),
        )
        self.assertEqual(
            1,
            sum(
                stage.get("model_feedback_ref") == reference
                for stage in current["work_detail"]["stages"]
            ),
        )
        record = project_request_records([current])[0]
        self.assertEqual(reference, record["model_feedback_ref"])
        self.assertEqual(
            1,
            sum(
                stage.get("model_feedback_ref") == reference
                for stage in record["work_detail"]["stages"]
            ),
        )

        historical = _run_card(
            raw,
            history_evidence={
                "governance_eligible": False,
                "definition_status": "historical",
            },
            model_feedback_report=report,
        )
        self.assertNotIn("model_feedback_ref", historical)

    def test_browser_contract_rejects_dangling_feedback_references(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is required for the snapshot contract test")
        report = self._build_report(
            self._events(samples=20, failures=6)
        )
        raw = event(
            "model-feedback-project",
            "a" * 12,
            "feedback-browser-contract",
            "feedback-browser-contract",
        )
        raw["plan_summary"] = copy.deepcopy(self.plan)
        raw["stage_results"] = []
        run = _run_card(
            raw,
            history_evidence={
                "governance_eligible": True,
                "definition_status": "current",
            },
            model_feedback_report=report,
        )
        snapshot = {
            "schema_version": "maestro_snapshot_v1",
            "project_id": "model-feedback-project",
            "runs": [run],
            "request_records": project_request_records([run]),
            "governance": {
                "model_feedback_window": 200,
                "model_feedback_authority": report["authority"],
                "model_feedback": report,
            },
        }
        contract_path = (
            ROOT
            / "src/maestro/resources/viewer/snapshot-contract.js"
        )
        script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const contract = require(process.argv[1]);
const snapshot = JSON.parse(fs.readFileSync(0, "utf8"));
const writer = snapshot.runs[0].flow.find(
  (item) => item.model_feedback_ref,
);
const feedbackCard = (reference) => ({
  work_id: "feedback-work",
  assignment: {assignment_id: writer.assignment_id},
  relationships: {},
  models: {},
  measurements: {duration_ms: null},
  execution_facts: {
    duration: {value_ms: null},
    tokens: {value: null},
  },
  evidence: {},
  expertise: {},
  model_feedback_ref: structuredClone(reference),
});
snapshot.runs[0].work_detail.execution.cards.push(
  feedbackCard(snapshot.runs[0].model_feedback_ref),
);
snapshot.request_records[0].work_detail.execution.cards.push(
  feedbackCard(snapshot.request_records[0].model_feedback_ref),
);
assert.equal(contract.validateSnapshot(snapshot), snapshot);

const dangling = structuredClone(snapshot);
dangling.request_records[0].model_feedback_ref.group_id = "0".repeat(64);
assert.throws(() => contract.validateSnapshot(dangling));

const mismatched = structuredClone(snapshot);
const stage = mismatched.request_records[0].work_detail.stages.find(
  (item) => item.model_feedback_ref,
);
stage.model_feedback_ref.subject.risk = "high";
assert.throws(() => contract.validateSnapshot(mismatched));

const missing = structuredClone(snapshot);
delete missing.request_records[0].work_detail.stages.find(
  (item) => item.model_feedback_ref,
).model_feedback_ref;
assert.throws(() => contract.validateSnapshot(missing));

const missingCards = structuredClone(snapshot);
delete missingCards.runs[0].work_detail.execution.cards[0]
  .model_feedback_ref;
delete missingCards.request_records[0].work_detail.execution.cards[0]
  .model_feedback_ref;
assert.throws(() => contract.validateSnapshot(missingCards));

const mutable = structuredClone(snapshot);
mutable.governance.model_feedback.automatic_policy_mutation_allowed = true;
assert.throws(() => contract.validateSnapshot(mutable));
"""
        completed = subprocess.run(
            [node, "-e", script, str(contract_path)],
            input=json.dumps(snapshot, ensure_ascii=False),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(
            0,
            completed.returncode,
            completed.stdout + completed.stderr,
        )

    def test_policy_changes_only_through_exact_explicit_owner_overlay(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            authority = current_model_policy_authority(repo)
            report = self._build_report(
                self._events(
                    samples=20,
                    failures=6,
                    authority=authority,
                )
            )
            group = report["groups"][0]
            report_path = repo / ".maestro/model-feedback-report.json"
            write_json(report_path, report)
            report_ref = (
                "model_feedback_report:"
                ".maestro/model-feedback-report.json"
            )
            report_digest = file_sha256(report_path)
            approval_path = repo / ".maestro/model-policy-owner.json"
            write_json(
                approval_path,
                {
                    "schema_version": (
                        "maestro_model_policy_owner_decision_v1"
                    ),
                    "report_ref": report_ref,
                    "report_digest": report_digest,
                    "report_id": report["report_id"],
                    "group_id": group["group_id"],
                    "authority": authority,
                    "scope": group["subject"],
                    "target": group["advice"]["target"],
                    "decision": "accept",
                    "rationale": (
                        "검증된 구현 귀속 실패율에 따라 한 단계 상향합니다."
                    ),
                    "evidence_refs": [
                        "tests:model-feedback:owner-decision"
                    ],
                },
            )
            overlay = build_model_policy_overlay(
                report,
                group_id=group["group_id"],
                basis="owner_decision",
                approval_ref=(
                    "owner_decision:.maestro/model-policy-owner.json"
                ),
                repo_path=repo,
            )
            self.assertEqual(MODEL_POLICY_OVERLAY_VERSION, overlay["schema_version"])
            self.assertTrue(
                validate_model_policy_overlay(overlay, report=report)
            )
            self.assertTrue(
                validate_model_policy_overlay_authority(
                    overlay,
                    repo_path=repo,
                )
            )

            ordinary = route_goal_v2(
                "Implement API behavior and tests",
                "medium",
                ["contract", "test-proof"],
                intent="implementation",
            )
            adapted = route_goal_v2(
                "Implement API behavior and tests",
                "medium",
                ["contract", "test-proof"],
                intent="implementation",
                repo_path=repo,
                model_policy_overlays=[overlay],
            )
            ordinary_writer = next(
                item for item in ordinary["assignments"]
                if item["mutation_owner"] is True
            )
            adapted_writer = next(
                item for item in adapted["assignments"]
                if item["mutation_owner"] is True
            )
            self.assertEqual(
                "gpt-5.6-terra",
                ordinary_writer["model_route"]["selected_model"],
            )
            self.assertEqual(
                overlay["target"]["selected_model"],
                adapted_writer["model_route"]["selected_model"],
            )
            self.assertEqual(
                "high",
                adapted_writer["model_route"]["reasoning_effort"],
            )

            held_out_path = (
                repo / ".maestro/model-policy-held-out.json"
            )
            write_json(
                held_out_path,
                {
                    "schema_version": (
                        "maestro_model_policy_held_out_evaluation_v1"
                    ),
                    "report_ref": report_ref,
                    "report_digest": report_digest,
                    "report_id": report["report_id"],
                    "group_id": group["group_id"],
                    "authority": authority,
                    "scope": group["subject"],
                    "target": group["advice"]["target"],
                    "held_out": True,
                    "verdict": "accept",
                    "evidence_refs": [
                        "tests:model-feedback:held-out:one",
                        "tests:model-feedback:held-out:two",
                        "tests:model-feedback:held-out:three",
                    ],
                },
            )
            held_out_overlay = build_model_policy_overlay(
                report,
                group_id=group["group_id"],
                basis="held_out_evaluation",
                approval_ref=(
                    "held_out_evaluation:"
                    ".maestro/model-policy-held-out.json"
                ),
                repo_path=repo,
            )
            self.assertTrue(
                validate_model_policy_overlay_authority(
                    held_out_overlay,
                    repo_path=repo,
                )
            )

            retargeted_path = (
                repo / ".maestro/model-policy-retargeted.json"
            )
            retargeted_approval = json.loads(
                approval_path.read_text(encoding="utf-8")
            )
            retargeted_approval["scope"]["risk"] = "high"
            write_json(retargeted_path, retargeted_approval)
            retargeted_overlay = copy.deepcopy(overlay)
            retargeted_overlay["scope"]["risk"] = "high"
            retargeted_overlay["acceptance"]["approval_ref"] = (
                "owner_decision:"
                ".maestro/model-policy-retargeted.json"
            )
            retargeted_overlay["acceptance"][
                "approval_digest"
            ] = file_sha256(retargeted_path)
            retargeted_overlay["overlay_id"] = sha256_text(
                canonical_json(
                    {
                        **retargeted_overlay,
                        "overlay_id": "",
                    }
                )
            )
            self.assertTrue(
                validate_model_policy_overlay(retargeted_overlay)
            )
            self.assertFalse(
                validate_model_policy_overlay_authority(
                    retargeted_overlay,
                    repo_path=repo,
                )
            )

            invalid_approval = json.loads(
                approval_path.read_text(encoding="utf-8")
            )
            invalid_approval["decision"] = "reject"
            write_json(approval_path, invalid_approval)
            self.assertFalse(
                validate_model_policy_overlay_authority(
                    overlay,
                    repo_path=repo,
                )
            )

    def test_public_feedback_schema_exports_every_boundary_artifact(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "src/maestro/resources/schemas/model-feedback.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(
            {
                "verificationAssessment",
                "modelFeedbackReport",
                "modelPolicyOverlay",
                "modelPolicyOwnerDecision",
                "modelPolicyHeldOutEvaluation",
            }.issubset(schema["$defs"])
        )

    def test_dashboard_keeps_feedback_separate_from_live_model_facts(
        self,
    ) -> None:
        viewer = ROOT / "src/maestro/resources/viewer"
        source = (viewer / "app.js").read_text(encoding="utf-8")
        markup = (viewer / "index.html").read_text(encoding="utf-8")
        self.assertIn("function renderModelFeedback", source)
        self.assertIn("경로 권고 후 검증 실패", source)
        self.assertIn("실제 적용 모델에서 검증 실패", source)
        self.assertIn("모델에 귀속 가능한 구현 실패", source)
        self.assertIn("자동 정책 변경 없음 · 자동 하향 없음", source)
        self.assertIn("정책 후보일 뿐 현재 경로 아님", source)
        self.assertNotIn("모델 실패 탐지율", source)
        self.assertIn('id="model-feedback"', markup)


if __name__ == "__main__":
    unittest.main()
