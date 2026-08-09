from __future__ import annotations

import unittest

from tests.support import application_work_span

from maestro.expertise_changes import expertise_change_sets
from maestro.expertise_usage import expertise_usage_evidence


class ExpertiseUsageEvidenceTests(unittest.TestCase):
    def test_selection_only_is_not_counted_as_application(self) -> None:
        event = {
            "run_id": "selection-only",
            "timestamp": "2026-07-28T00:00:00Z",
            "selected_expertise_packs": ["product-design"],
            "selected_decision_guides": ["design-brief"],
            "verifier_result": "passed",
            "work_spans": [],
        }

        evidence = expertise_usage_evidence(
            [event],
            pack_id="product-design",
            guide_id="design-brief",
        )

        self.assertEqual(1, evidence["selection_count"])
        self.assertEqual(0, evidence["assigned_count"])
        self.assertEqual(0, evidence["application_count"])
        self.assertEqual(0, evidence["verified_count"])

    def test_application_requires_matching_work_span_evidence(self) -> None:
        event = {
            "run_id": "applied",
            "timestamp": "2026-07-28T00:00:00Z",
            "selected_expertise_packs": ["product-design"],
            "selected_decision_guides": ["design-brief"],
            "verifier_result": "passed",
            "plan_summary": {
                "assignments": [
                    {
                        "expertise_pack_ids": ["product-design"],
                        "decision_guide_ids": ["design-brief"],
                    }
                ]
            },
            "work_spans": [
                application_work_span(
                    "product-design",
                    ["design-brief"],
                )
            ],
        }

        evidence = expertise_usage_evidence(
            [event],
            pack_id="product-design",
            guide_id="design-brief",
        )

        self.assertEqual(1, evidence["selection_count"])
        self.assertEqual(1, evidence["assigned_count"])
        self.assertEqual(1, evidence["loaded_count"])
        self.assertEqual(1, evidence["application_count"])
        self.assertEqual(1, evidence["verified_count"])


class ExpertiseChangeSetProjectionTests(unittest.TestCase):
    def test_grouped_pack_redistribution_is_one_atomic_change_set(self) -> None:
        inventory = {
            "candidates": [
                {
                    "candidate_id": "design-split-copy",
                    "expertise_pack_id": "content-design",
                    "runtime_status": "available",
                    "definition_digest": "a" * 64,
                    "component_change": {
                        "kind": "guide-copy",
                        "change_set_id": "design-redistribution",
                        "operation_id": "copy-content-guide",
                        "source_pack_ids": ["product-design"],
                        "target_pack_ids": ["content-design"],
                        "target_guide_id": "content-claims",
                    },
                    "pack_preview": {
                        "problem": "콘텐츠 판단 책임을 분리합니다.",
                    },
                    "global_adoption": None,
                },
                {
                    "candidate_id": "design-split-move",
                    "expertise_pack_id": "frontend-composition",
                    "runtime_status": "available",
                    "definition_digest": "b" * 64,
                    "component_change": {
                        "kind": "guide-move",
                        "change_set_id": "design-redistribution",
                        "operation_id": "move-composition-guide",
                        "source_pack_ids": ["product-design"],
                        "target_pack_ids": ["frontend-composition"],
                        "target_guide_id": "page-composition",
                    },
                    "pack_preview": {
                        "problem": "프론트엔드 조합 책임을 분리합니다.",
                    },
                    "global_adoption": None,
                },
            ],
        }
        health = {
            "candidates": [
                {
                    "candidate_id": "design-split-copy",
                    "component_selection_count": 3,
                    "component_application_count": 2,
                    "review_due": False,
                    "review_reasons": [],
                },
                {
                    "candidate_id": "design-split-move",
                    "component_selection_count": 2,
                    "component_application_count": 1,
                    "review_due": False,
                    "review_reasons": [],
                },
            ],
        }

        projection = expertise_change_sets(inventory, health)
        change_set = projection["change_sets"][0]

        self.assertEqual("design-redistribution", change_set["change_set_id"])
        self.assertTrue(change_set["grouped"])
        self.assertTrue(change_set["atomic_required"])
        self.assertFalse(change_set["partial_approval_allowed"])
        self.assertEqual(
            {"copy-guide", "move-guide"},
            {item["kind"] for item in change_set["operations"]},
        )
        self.assertEqual(5, change_set["usage_evidence"]["selected"])
        self.assertEqual(3, change_set["usage_evidence"]["applied"])
        self.assertEqual(
            "group_review_required",
            change_set["project_approval"]["status"],
        )


if __name__ == "__main__":
    unittest.main()
