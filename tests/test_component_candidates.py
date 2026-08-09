from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.support import ROOT, write_json

from maestro.cli import main
from maestro.component_candidates import validate_component_candidate
from maestro.surface_classification import SIGNAL_FIELDS, classify_surface
from maestro.util import file_sha256


def _signals(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "durable": True,
        "machine_checkable": False,
        "project_specific_rule": False,
        "existing_pack_id": None,
        "existing_guide_id": None,
        "same_decision_family": False,
        "related_guide_count": 0,
        "domain_workflow": False,
        "cross_task_failure_boundary": False,
        "verdict_impact": False,
        "procedural_only": False,
        "expertise_routed": False,
        "execution_boundaries": [],
        "department_routing_change": False,
        "integration_boundary": False,
        "research_lane_boundary": False,
        "specialist_contract_boundary": False,
        "typed_handoff_gap": False,
        "existing_packet_sufficient": False,
    }
    value.update(overrides)
    return value


def _write_lens_candidate(repo: Path, candidate_id: str = "indexability") -> Path:
    root = (
        repo
        / ".maestro/state/candidates/components"
        / candidate_id
    )
    signals = {
        "schema_version": "maestro_surface_signal_v1",
        "request_id": candidate_id,
        "signals": _signals(
            cross_task_failure_boundary=True,
            verdict_impact=True,
        ),
        "evidence_refs": ["project:test-evidence"],
    }
    classification = classify_surface(signals)
    definition = {
        "schema_version": "maestro_registry_component_draft_v1",
        "candidate_id": candidate_id,
        "component_kind": "lens",
        "component_id": "indexability",
        "definition": {
            "summary": "Reject changes that make intended public pages unindexable."
        },
    }
    evidence = {
        "schema_version": "maestro_component_evidence_v1",
        "candidate_id": candidate_id,
        "evidence": [
            {
                "evidence_id": "incident-one",
                "kind": "incident",
                "ref": "artifact:indexability-regression",
                "supports": [
                    "failure crosses task types",
                    "finding changes release verdict",
                ],
            }
        ],
    }
    evaluation = {
        "schema_version": "maestro_component_evaluation_v1",
        "candidate_id": candidate_id,
        "frozen_before_evaluation": True,
        "cases": [
            {
                "case_id": "positive-one",
                "stratum": "positive",
                "input": "A public page gains noindex.",
                "expected_outcome": "Lens blocks the release.",
                "forbidden_behaviors": ["route as marketing advice only"],
                "evidence_refs": ["incident-one"],
            },
            {
                "case_id": "non-trigger-one",
                "stratum": "non-trigger",
                "input": "A private admin page gains noindex.",
                "expected_outcome": "Lens does not block.",
                "forbidden_behaviors": ["reject intended private indexing"],
                "evidence_refs": ["incident-one"],
            },
            {
                "case_id": "regression-one",
                "stratum": "regression",
                "input": "Existing contract Lens routing remains unchanged.",
                "expected_outcome": "Existing route is preserved.",
                "forbidden_behaviors": ["replace unrelated Lens"],
                "evidence_refs": ["incident-one"],
            },
        ],
        "pass_criteria": ["all observable outcomes match"],
        "regression_criteria": ["no unrelated route changes"],
    }
    artifacts = {
        "signals.json": signals,
        "classification.json": classification,
        "draft/component.json": definition,
        "evidence/manifest.json": evidence,
        "evals/cases.json": evaluation,
    }
    for path, value in artifacts.items():
        write_json(root / path, value)
    candidate = {
        "schema_version": "maestro_registry_component_candidate_v1",
        "candidate_id": candidate_id,
        "component_kind": "lens",
        "status": "candidate",
        "owner": "test-owner",
        "portability": "profile",
        "failure_pattern": "Indexability regressions escape domain-only review.",
        "existing_coverage": [
            "marketing Pack is advisory and not a cross-task rejection boundary"
        ],
        "signals_ref": {
            "path": "signals.json",
            "sha256": file_sha256(root / "signals.json"),
        },
        "classification_ref": {
            "path": "classification.json",
            "sha256": file_sha256(root / "classification.json"),
        },
        "definition_ref": {
            "path": "draft/component.json",
            "sha256": file_sha256(root / "draft/component.json"),
        },
        "evidence_ref": {
            "path": "evidence/manifest.json",
            "sha256": file_sha256(root / "evidence/manifest.json"),
        },
        "evaluation_ref": {
            "path": "evals/cases.json",
            "sha256": file_sha256(root / "evals/cases.json"),
        },
        "cost": {
            "additional_model_calls": 0,
            "context_cost": "low",
            "maintenance_owner": "test-owner",
        },
        "rollback": {
            "strategy": "discard the isolated candidate directory",
            "active_registry_unchanged": True,
        },
        "review_after": "2026-12-31",
        "approval_requirement": "owner_decision",
    }
    write_json(root / "candidate.json", candidate)
    return root


class SurfaceClassificationTests(unittest.TestCase):
    def test_pack_integration_is_considered_separately_from_guide_addition(
        self,
    ) -> None:
        result = classify_surface(
            {
                "schema_version": "maestro_surface_signal_v1",
                "request_id": "consolidate-overlapping-packs",
                "signals": {
                    **_signals(
                        domain_workflow=True,
                        related_guide_count=4,
                    ),
                    "overlapping_pack_ids": [
                        "product-design",
                        "marketing",
                    ],
                    "pack_merge_boundary": True,
                },
                "evidence_refs": [
                    "runs:handoff-correction",
                    "eval:coexistence",
                ],
            }
        )

        self.assertEqual("classified", result["status"])
        self.assertEqual("expertise-pack", result["proposed_surface"])
        self.assertEqual(
            "pack-consolidation",
            result["distinct_failure_or_decision_boundary"]["kind"],
        )
        self.assertTrue(
            result["pack_integration_assessment"]["recommended"]
        )
        self.assertEqual(
            ["product-design", "marketing"],
            result["pack_integration_assessment"]["source_pack_ids"],
        )
        self.assertIsNone(result["existing_component_to_extend"])

    def test_frozen_surface_cases_choose_the_expected_boundary(self) -> None:
        fixture = json.loads(
            (
                ROOT / "tests/fixtures/surface-classification-cases.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            "maestro_surface_classification_eval_v1",
            fixture["schema_version"],
        )
        for case in fixture["cases"]:
            with self.subTest(case=case["case_id"]):
                result = classify_surface(
                    {
                        "schema_version": "maestro_surface_signal_v1",
                        "request_id": case["case_id"],
                        "signals": _signals(**case["signals"]),
                        "evidence_refs": ["fixture:evidence"],
                    }
                )
                self.assertEqual(
                    case["expected_surface"],
                    result["proposed_surface"],
                )
                self.assertEqual(
                    case.get("expected_status", "classified"),
                    result["status"],
                )
                self.assertTrue(
                    set(case["forbidden_surfaces"]).isdisjoint(
                        {result["proposed_surface"]}
                    )
                )

    def test_surface_signal_contract_is_closed(self) -> None:
        signals = _signals()
        self.assertEqual(SIGNAL_FIELDS, set(signals))
        signals["unexpected"] = True
        with self.assertRaisesRegex(Exception, "exact surface signal fields"):
            classify_surface(
                {
                    "schema_version": "maestro_surface_signal_v1",
                    "request_id": "closed-contract",
                    "signals": signals,
                    "evidence_refs": ["fixture:evidence"],
                }
            )

    def test_candidate_handoff_requires_evidence(self) -> None:
        result = classify_surface(
            {
                "schema_version": "maestro_surface_signal_v1",
                "request_id": "missing-evidence",
                "signals": _signals(
                    cross_task_failure_boundary=True,
                    verdict_impact=True,
                ),
                "evidence_refs": [],
            }
        )

        self.assertEqual("lens", result["proposed_surface"])
        self.assertEqual("blocked", result["status"])
        self.assertIsNotNone(result["blocker"])

    def test_govern_classify_cli_uses_the_closed_signal_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "signals.json"
            write_json(
                path,
                {
                    "schema_version": "maestro_surface_signal_v1",
                    "request_id": "cli-sitemap",
                    "signals": _signals(machine_checkable=True),
                    "evidence_refs": ["fixture:sitemap-schema"],
                },
            )
            output = StringIO()
            with redirect_stdout(output):
                code = main(
                    [
                        "govern",
                        "classify",
                        "--input",
                        str(path),
                        "--json",
                    ]
                )

            self.assertEqual(0, code)
            result = json.loads(output.getvalue())
            self.assertEqual(
                "checker-schema-test",
                result["proposed_surface"],
            )

    def test_multiple_independent_boundaries_require_split(self) -> None:
        result = classify_surface(
            {
                "schema_version": "maestro_surface_signal_v1",
                "request_id": "adapter-and-executor",
                "signals": _signals(
                    integration_boundary=True,
                    execution_boundaries=["tools"],
                ),
                "evidence_refs": ["fixture:integration"],
            }
        )

        self.assertEqual("blocked", result["status"])
        self.assertIn("split them", result["blocker"])


class ComponentCandidateTests(unittest.TestCase):
    def test_complete_lens_candidate_passes_without_registry_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _write_lens_candidate(repo)

            result = validate_component_candidate(repo, "indexability")

            self.assertEqual("PASS", result["status"])
            self.assertFalse(result["promotion_available"])
            self.assertEqual([], result["issues"])

    def test_tampered_artifact_digest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            root = _write_lens_candidate(repo)
            definition = json.loads(
                (root / "draft/component.json").read_text(encoding="utf-8")
            )
            definition["definition"]["summary"] = "tampered"
            write_json(root / "draft/component.json", definition)

            result = validate_component_candidate(repo, "indexability")

            self.assertEqual("FAIL", result["status"])
            self.assertIn(
                "COMPONENT_CANDIDATE_DIGEST_MISMATCH",
                {issue["code"] for issue in result["issues"]},
            )

    def test_lens_without_verdict_impact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            root = _write_lens_candidate(repo)
            classification = json.loads(
                (root / "classification.json").read_text(encoding="utf-8")
            )
            classification["distinct_failure_or_decision_boundary"][
                "verdict_impact"
            ] = False
            write_json(root / "classification.json", classification)
            candidate = json.loads(
                (root / "candidate.json").read_text(encoding="utf-8")
            )
            candidate["classification_ref"]["sha256"] = file_sha256(
                root / "classification.json"
            )
            write_json(root / "candidate.json", candidate)

            result = validate_component_candidate(repo, "indexability")

            self.assertEqual("FAIL", result["status"])
            self.assertIn(
                "LENS_VERDICT_IMPACT_REQUIRED",
                {issue["code"] for issue in result["issues"]},
            )

    def test_registry_builder_and_schemas_are_bundled(self) -> None:
        skill = ROOT / "skills/maestro-registry-builder/SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text(encoding="utf-8")
        self.assertIn(
            ".maestro/state/candidates/components/",
            text,
        )
        self.assertIn("Never edit `src/maestro/resources/registry/`", text)
        for name in (
            "surface-classification.schema.json",
            "registry-component-candidate.schema.json",
        ):
            schema = json.loads(
                (
                    ROOT / "src/maestro/resources/schemas" / name
                ).read_text(encoding="utf-8")
            )
            self.assertIn("$id", schema)
        candidate_schema = json.loads(
            (
                ROOT
                / "src/maestro/resources/schemas/registry-component-candidate.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {
                "schema_version",
                "candidate_id",
                "component_kind",
                "status",
                "owner",
                "portability",
                "failure_pattern",
                "existing_coverage",
                "signals_ref",
                "classification_ref",
                "definition_ref",
                "evidence_ref",
                "evaluation_ref",
                "cost",
                "rollback",
                "review_after",
                "approval_requirement",
            },
            set(candidate_schema["required"]),
        )

    def test_expertise_builder_rejects_non_expertise_handoff(self) -> None:
        text = (
            ROOT / "skills/maestro-expertise-builder/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("not admitted as expertise", text)
        self.assertIn("Continue only for `decision-guide`", text)


if __name__ == "__main__":
    unittest.main()
