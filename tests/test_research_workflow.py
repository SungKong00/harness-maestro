from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from maestro.cli import main
from maestro.research import (
    BUNDLE_VERSION,
    PACKET_VERSION,
    validate_research_artifact,
    validate_research_bundle,
    validate_research_packet,
)
from tests.support import write_json


def _packet(
    lane_id: str = "official",
    *,
    source_id: str = "source-1",
    claim_id: str = "claim-1",
    tier: int = 1,
    adoption: str = "checklist",
) -> dict[str, object]:
    return {
        "schema_version": PACKET_VERSION,
        "question": "Which current evidence changes the design decision?",
        "lane_id": lane_id,
        "sources": [
            {
                "source_id": source_id,
                "tier": tier,
                "title": "Exact authoritative source",
                "url": "https://example.com/exact",
                "artifact_ref": None,
                "version": "current",
                "checked_at": "2026-07-26",
                "limitations": [],
            }
        ],
        "claims": [
            {
                "claim_id": claim_id,
                "kind": "fact",
                "text": "The source supports one bounded decision criterion.",
                "source_refs": [source_id],
                "artifact_refs": [],
                "adoption": adoption,
            }
        ],
        "conflicts": [],
        "limitations": [],
    }


def _bundle() -> dict[str, object]:
    packet = _packet()
    return {
        "schema_version": BUNDLE_VERSION,
        "workflow_owner": "maestro",
        "question": packet["question"],
        "depth": "quick",
        "packets": [packet],
        "synthesis": {
            "adopted_claim_ids": ["claim-1"],
            "conflicts": [],
            "open_questions": [],
            "limitations": [],
        },
        "follow_up_waves": 0,
        "status": "completed",
    }


class ResearchValidationTests(unittest.TestCase):
    def test_valid_packet_and_bundle_are_content_addressed(self) -> None:
        packet_result = validate_research_packet(_packet())
        bundle_result = validate_research_bundle(_bundle())

        self.assertEqual("PASS", packet_result["status"])
        self.assertEqual(64, len(packet_result["artifact_digest"]))
        self.assertEqual("PASS", bundle_result["status"])
        self.assertEqual(64, len(bundle_result["artifact_digest"]))

    def test_unknown_source_and_weak_rule_are_rejected(self) -> None:
        packet = _packet(tier=5, adoption="rule")
        packet["claims"][0]["source_refs"] = ["missing-source"]

        result = validate_research_packet(packet)
        codes = {issue["code"] for issue in result["issues"]}

        self.assertEqual("FAIL", result["status"])
        self.assertIn("RESEARCH_CLAIM_SOURCE_UNKNOWN", codes)
        self.assertIn("RESEARCH_RULE_AUTHORITY_INSUFFICIENT", codes)

    def test_follow_up_requires_material_conflict(self) -> None:
        bundle = _bundle()
        bundle["follow_up_waves"] = 1

        result = validate_research_bundle(bundle)

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "RESEARCH_FOLLOW_UP_UNJUSTIFIED",
            {issue["code"] for issue in result["issues"]},
        )

    def test_one_follow_up_may_revisit_a_lane_for_new_evidence(self) -> None:
        bundle = _bundle()
        follow_up = _packet(
            "official",
            source_id="source-2",
            claim_id="claim-2",
            adoption="warning",
        )
        bundle["packets"].append(follow_up)
        bundle["synthesis"]["conflicts"] = [
            {
                "claim_ids": ["claim-1", "claim-2"],
                "material": True,
                "resolution": "qualified",
                "evidence_refs": ["source-1", "source-2"],
            }
        ]
        bundle["follow_up_waves"] = 1

        result = validate_research_bundle(bundle)

        self.assertEqual("PASS", result["status"])

    def test_cli_validates_bundle_and_binds_actual_file_to_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.json"
            write_json(path, _bundle())

            validation_output = StringIO()
            with redirect_stdout(validation_output):
                validation_exit = main(
                    [
                        "validate-research",
                        "--artifact",
                        str(path),
                        "--json",
                    ]
                )

            route_output = StringIO()
            with redirect_stdout(route_output):
                route_exit = main(
                    [
                        "route",
                        "--goal",
                        "Find current references for a modern landing page design",
                        "--risk",
                        "medium",
                        "--intent",
                        "implementation",
                        "--route-version",
                        "v2",
                        "--research-evidence",
                        str(path),
                        "--json",
                    ]
                )

        validation = json.loads(validation_output.getvalue())
        route = json.loads(route_output.getvalue())
        self.assertEqual(0, validation_exit)
        self.assertEqual("PASS", validation["status"])
        self.assertEqual(0, route_exit)
        self.assertEqual(
            "satisfied",
            route["expertise"]["research_requirement"]["gate"],
        )
        self.assertEqual(
            validation["artifact_digest"],
            route["expertise"]["research_requirement"]["evidence_digest"],
        )

    def test_cli_rejects_packet_and_mismatched_digest_as_gate_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            bundle_path = Path(temporary) / "bundle.json"
            write_json(packet_path, _packet())
            write_json(bundle_path, _bundle())

            packet_output = StringIO()
            with redirect_stdout(packet_output):
                packet_exit = main(
                    [
                        "route",
                        "--goal",
                        "Find current references for a modern landing page design",
                        "--route-version",
                        "v2",
                        "--research-evidence",
                        str(packet_path),
                        "--json",
                    ]
                )

            digest_output = StringIO()
            with redirect_stdout(digest_output):
                digest_exit = main(
                    [
                        "route",
                        "--goal",
                        "Find current references for a modern landing page design",
                        "--route-version",
                        "v2",
                        "--research-evidence",
                        str(bundle_path),
                        "--research-evidence-digest",
                        "0" * 64,
                        "--json",
                    ]
                )

        self.assertEqual(2, packet_exit)
        self.assertEqual(
            "RESEARCH_BUNDLE_REQUIRED",
            json.loads(packet_output.getvalue())["code"],
        )
        self.assertEqual(2, digest_exit)
        self.assertEqual(
            "RESEARCH_EVIDENCE_DIGEST_MISMATCH",
            json.loads(digest_output.getvalue())["code"],
        )

    def test_artifact_dispatches_packet_and_invalid_shapes(self) -> None:
        self.assertEqual(
            "PASS",
            validate_research_artifact(_packet())["status"],
        )
        invalid = copy.deepcopy(_bundle())
        invalid["workflow_owner"] = "another-orchestrator"
        self.assertEqual(
            "FAIL",
            validate_research_artifact(invalid)["status"],
        )


if __name__ == "__main__":
    unittest.main()
