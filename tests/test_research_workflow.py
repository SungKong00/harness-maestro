from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from maestro.cli import main
from maestro.expertise import select_expertise
from maestro.research import (
    BUNDLE_VERSION,
    PACKET_VERSION,
    expected_research_binding,
    project_research_context,
    validate_research_artifact,
    validate_research_bundle,
    validate_research_packet,
)
from maestro.util import file_sha256
from tests.support import write_json


GOAL = "Find current references for a modern landing page design"


def _binding(goal: str = GOAL) -> dict[str, object]:
    expertise, _ = select_expertise(
        goal,
        intent="implementation",
        repo_path=".",
    )
    return expected_research_binding(goal, expertise)


def _packet(
    lane_id: str = "official",
    *,
    wave: int = 0,
    source_id: str = "source-official",
    claim_id: str = "claim-layout",
    tier: int = 1,
    adoption: str = "checklist",
    url: str = "https://example.com/exact",
    rationale: str = "Official material can establish the current supported behavior.",
    query: str = "official current landing page design guidance",
) -> dict[str, object]:
    checklist = (
        ["Verify the hierarchy against the current official guidance."]
        if adoption == "checklist"
        else []
    )
    return {
        "schema_version": PACKET_VERSION,
        "packet_id": f"packet-{lane_id}-{wave}",
        "status": "completed",
        "workflow_owner": "maestro",
        "decision_scope": "research_only",
        "question": "Which current evidence changes the design decision?",
        "decision_needed": "Choose criteria that are safe to apply in implementation.",
        "target_context": "Harness Maestro product-design implementation route.",
        "date_checked": date.today().isoformat(),
        "depth": "quick",
        "lane_id": lane_id,
        "wave": wave,
        "lane_rationale": rationale,
        "artifacts_checked": [
            {
                "artifact_id": f"artifact-{lane_id}-{wave}",
                "kind": "user-input",
                "locator": "Bound research question supplied by Maestro.",
                "sha256": None,
            }
        ],
        "queries_used": [query],
        "sources": [
            {
                "source_id": source_id,
                "tier": tier,
                "title": "Exact inspected source",
                "url": url,
                "artifact_ref": None,
                "source_role": "direct-evidence",
                "version_sensitive": True,
                "version": "current",
                "checked_at": date.today().isoformat(),
                "inspected_evidence": (
                    "The opened source states one bounded criterion relevant "
                    "to the decision."
                ),
                "limitations": [],
            }
        ],
        "claims": [
            {
                "claim_id": claim_id,
                "kind": "fact",
                "statement": (
                    "The inspected source supports one bounded decision criterion."
                ),
                "authority": (
                    "authoritative" if tier in {0, 1} else "advisory"
                ),
                "verification_status": (
                    "verified" if tier in {0, 1} else "supported"
                ),
                "source_refs": [source_id],
                "artifact_refs": [],
                "supporting_evidence": (
                    "The source's current guidance directly states the criterion."
                ),
                "conflicting_evidence": [],
                "applicability": "Applies to the requested web design surface.",
                "project_fit": "Fits the current project without changing ownership.",
                "confidence": {
                    "level": "high" if tier in {0, 1} else "low",
                    "reason": "Confidence follows the inspected source tier.",
                },
                "adoption": adoption,
            }
        ],
        "conflicts": [],
        "open_questions": [],
        "recommended_checklist_items": checklist,
        "rejected_claim_ids": [],
        "limitations": [],
    }


def _bundle(goal: str = GOAL) -> dict[str, object]:
    packet = _packet()
    return {
        "schema_version": BUNDLE_VERSION,
        "workflow_owner": "maestro",
        "request_binding": _binding(goal),
        "question": packet["question"],
        "decision_needed": packet["decision_needed"],
        "target_context": packet["target_context"],
        "date_checked": packet["date_checked"],
        "depth": packet["depth"],
        "source_plan": {
            "lanes": [
                {
                    "lane_id": "official",
                    "wave": 0,
                    "rationale": packet["lane_rationale"],
                    "decision_impact": (
                        "A different supported behavior would change the checklist."
                    ),
                    "queries": packet["queries_used"],
                }
            ],
            "stop_conditions": [
                "Stop when the decision-changing claim has current direct support."
            ],
        },
        "packets": [packet],
        "synthesis": {
            "adopted_claim_ids": ["claim-layout"],
            "rejected_claim_ids": [],
            "recommended_checklist_items": packet[
                "recommended_checklist_items"
            ],
            "conflicts": [],
            "open_questions": [],
            "limitations": [],
            "confidence": {
                "level": "high",
                "reason": "The adopted claim has current Tier 1 support.",
            },
            "freshness_notes": ["Checked on the recorded date and version."],
        },
        "follow_up_waves": 0,
        "status": "completed",
    }


class ResearchValidationTests(unittest.TestCase):
    def test_valid_v2_packet_bundle_and_projection_preserve_decision_content(
        self,
    ) -> None:
        packet_result = validate_research_packet(_packet(), repo_path=".")
        bundle = _bundle()
        bundle_result = validate_research_bundle(bundle, repo_path=".")
        context = project_research_context(bundle, repo_path=".")

        self.assertEqual("PASS", packet_result["status"])
        self.assertEqual(64, len(packet_result["artifact_digest"]))
        self.assertEqual("PASS", bundle_result["status"])
        self.assertEqual("completed", bundle_result["evidence_status"])
        self.assertEqual(bundle["source_plan"], context["source_plan"])
        self.assertEqual(bundle["packets"][0]["claims"], context["claims"])
        self.assertEqual(bundle["synthesis"], context["synthesis"])

    def test_unknown_source_and_weak_rule_are_rejected(self) -> None:
        packet = _packet(tier=5, adoption="rule")
        packet["claims"][0]["source_refs"] = ["missing-source"]

        result = validate_research_packet(packet)
        codes = {issue["code"] for issue in result["issues"]}

        self.assertEqual("FAIL", result["status"])
        self.assertIn("RESEARCH_CLAIM_SOURCE_UNKNOWN", codes)
        self.assertIn("RESEARCH_RULE_AUTHORITY_INSUFFICIENT", codes)

    def test_tier_zero_rejects_generic_question_artifact_authority(self) -> None:
        bundle = _bundle()
        packet = bundle["packets"][0]
        source = packet["sources"][0]
        source["tier"] = 0
        source["artifact_ref"] = packet["artifacts_checked"][0]["artifact_id"]

        result = validate_research_bundle(bundle)

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "RESEARCH_TIER0_AUTHORITY_INVALID",
            {issue["code"] for issue in result["issues"]},
        )

    def test_tier_zero_owner_decision_requires_a_durable_bound_file(
        self,
    ) -> None:
        spoofed = _bundle()
        artifact = spoofed["packets"][0]["artifacts_checked"][0]
        artifact["kind"] = "owner-decision"
        artifact["locator"] = "owner_decision:invented-by-packet-author"
        artifact["sha256"] = "0" * 64
        source = spoofed["packets"][0]["sources"][0]
        source["tier"] = 0
        source["artifact_ref"] = artifact["artifact_id"]

        spoofed_result = validate_research_bundle(spoofed)
        self.assertEqual("FAIL", spoofed_result["status"])
        self.assertIn(
            "RESEARCH_OWNER_DECISION_REPO_REQUIRED",
            {issue["code"] for issue in spoofed_result["issues"]},
        )

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            decision = repo / "docs/decisions/owner-approved.md"
            decision.parent.mkdir(parents=True)
            decision.write_text(
                "# Owner decision\n\nUse the reviewed compatibility rule.\n",
                encoding="utf-8",
            )
            durable = _bundle()
            artifact = durable["packets"][0]["artifacts_checked"][0]
            artifact["kind"] = "owner-decision"
            artifact["locator"] = (
                "owner_decision:docs/decisions/owner-approved.md"
            )
            artifact["sha256"] = file_sha256(decision)
            source = durable["packets"][0]["sources"][0]
            source["tier"] = 0
            source["artifact_ref"] = artifact["artifact_id"]

            durable_result = validate_research_bundle(
                durable,
                repo_path=repo,
            )
        self.assertEqual("PASS", durable_result["status"])

    def test_tier_zero_file_cannot_claim_authority_without_bound_repo(
        self,
    ) -> None:
        bundle = _bundle()
        artifact = bundle["packets"][0]["artifacts_checked"][0]
        artifact["kind"] = "file"
        artifact["locator"] = "does-not-exist.md"
        artifact["sha256"] = "0" * 64
        source = bundle["packets"][0]["sources"][0]
        source["tier"] = 0
        source["artifact_ref"] = artifact["artifact_id"]

        result = validate_research_bundle(bundle)

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "RESEARCH_ARTIFACT_REPO_REQUIRED",
            {issue["code"] for issue in result["issues"]},
        )

    def test_bundle_uses_one_lossless_aggregate_context_limit(self) -> None:
        with patch("maestro.research.MAX_BUNDLE_BYTES", 100):
            result = validate_research_bundle(_bundle())

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "RESEARCH_BUNDLE_BYTE_LIMIT",
            {issue["code"] for issue in result["issues"]},
        )

    def test_url_version_and_conflict_references_are_semantic(self) -> None:
        bundle = _bundle()
        source = bundle["packets"][0]["sources"][0]
        source["url"] = "not-a-url"
        source["version"] = None
        bundle["synthesis"]["conflicts"] = [
            {
                "claim_ids": ["claim-layout", "missing-claim"],
                "conflict_type": "made-up",
                "material": True,
                "resolution": "qualified",
                "evidence_refs": ["invented-source"],
                "reason": "The sources disagree.",
                "remaining_uncertainty": "One behavior remains uncertain.",
                "what_would_resolve_it": "Inspect a current primary source.",
            }
        ]

        result = validate_research_bundle(bundle)
        codes = {issue["code"] for issue in result["issues"]}

        self.assertIn("RESEARCH_SOURCE_URL_INVALID", codes)
        self.assertIn("RESEARCH_SOURCE_VERSION_REQUIRED", codes)
        self.assertIn("RESEARCH_CONFLICT_TYPE_INVALID", codes)
        self.assertIn("RESEARCH_CONFLICT_CLAIM_UNKNOWN", codes)
        self.assertIn("RESEARCH_CONFLICT_EVIDENCE_UNKNOWN", codes)

    def test_source_plan_is_validated_and_exact_queries_are_preserved(self) -> None:
        bundle = _bundle()
        bundle["packets"][0]["queries_used"] = ["unplanned broad query"]

        result = validate_research_bundle(bundle)

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "RESEARCH_QUERY_PLAN_MISMATCH",
            {issue["code"] for issue in result["issues"]},
        )

    def test_follow_up_requires_material_conflict_and_new_evidence(self) -> None:
        bundle = _bundle()
        follow_up = _packet(
            "skeptic",
            wave=1,
            source_id="source-skeptic",
            claim_id="claim-risk",
            adoption="warning",
            url="https://example.org/counterexample",
            rationale="A skeptic pass can qualify the material conflict.",
            query="landing page hierarchy counterexample",
        )
        bundle["packets"].append(follow_up)
        bundle["source_plan"]["lanes"].append(
            {
                "lane_id": "skeptic",
                "wave": 1,
                "rationale": follow_up["lane_rationale"],
                "decision_impact": "Counterevidence can downgrade the checklist.",
                "queries": follow_up["queries_used"],
            }
        )
        bundle["synthesis"]["adopted_claim_ids"].append("claim-risk")
        bundle["synthesis"]["conflicts"] = [
            {
                "claim_ids": ["claim-layout", "claim-risk"],
                "conflict_type": "scope",
                "material": True,
                "resolution": "qualified",
                "evidence_refs": ["source-official", "source-skeptic"],
                "reason": "The counterexample narrows applicability.",
                "remaining_uncertainty": "Rare layouts remain untested.",
                "what_would_resolve_it": "Run the named project verification.",
            }
        ]
        bundle["follow_up_waves"] = 1

        self.assertEqual(
            "PASS",
            validate_research_bundle(bundle)["status"],
        )

        repeated = copy.deepcopy(bundle)
        repeated["packets"][1]["sources"][0]["url"] = (
            repeated["packets"][0]["sources"][0]["url"]
        )
        result = validate_research_bundle(repeated)
        self.assertIn(
            "RESEARCH_FOLLOW_UP_NEW_EVIDENCE_REQUIRED",
            {issue["code"] for issue in result["issues"]},
        )

    def test_cli_binds_completed_bundle_to_exact_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.json"
            write_json(path, _bundle())

            validation_output = StringIO()
            with redirect_stdout(validation_output):
                validation_exit = main(
                    [
                        "validate-research",
                        "--repo",
                        ".",
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
                        "--repo",
                        ".",
                        "--goal",
                        GOAL,
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

    def test_insufficient_or_unrelated_bundle_cannot_close_gate(self) -> None:
        insufficient = _bundle()
        insufficient["status"] = "insufficient"
        insufficient["synthesis"]["open_questions"] = [
            "Primary evidence is still missing."
        ]
        unrelated = _bundle()
        unrelated["request_binding"]["goal_digest"] = "0" * 64

        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for name, artifact in (
                ("insufficient", insufficient),
                ("unrelated", unrelated),
            ):
                path = Path(temporary) / f"{name}.json"
                write_json(path, artifact)
                paths.append(path)
            codes = []
            for path in paths:
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "route",
                            "--repo",
                            ".",
                            "--goal",
                            GOAL,
                            "--route-version",
                            "v2",
                            "--research-evidence",
                            str(path),
                            "--json",
                        ]
                    )
                self.assertEqual(2, exit_code)
                codes.append(json.loads(output.getvalue())["code"])

        self.assertEqual(
            [
                "RESEARCH_EVIDENCE_INSUFFICIENT",
                "RESEARCH_EVIDENCE_BINDING_MISMATCH",
            ],
            codes,
        )

    def test_cli_rejects_packet_and_mismatched_digest_as_gate_evidence(
        self,
    ) -> None:
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
                        "--repo",
                        ".",
                        "--goal",
                        GOAL,
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
                        "--repo",
                        ".",
                        "--goal",
                        GOAL,
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

    def test_artifact_dispatch_reads_legacy_but_keeps_it_gate_ineligible(
        self,
    ) -> None:
        self.assertEqual(
            "PASS",
            validate_research_artifact(_packet())["status"],
        )
        legacy_packet = {
            "schema_version": "maestro_research_packet_v1",
            "question": "Which historical evidence informed this decision?",
            "lane_id": "official",
            "sources": [
                {
                    "source_id": "legacy-source",
                    "tier": 1,
                    "title": "Historical official source",
                    "url": "https://example.com/historical",
                    "artifact_ref": None,
                    "version": "historical",
                    "checked_at": date.today().isoformat(),
                    "limitations": [],
                }
            ],
            "claims": [
                {
                    "claim_id": "legacy-claim",
                    "kind": "fact",
                    "text": "Historical source-bounded claim.",
                    "source_refs": ["legacy-source"],
                    "artifact_refs": [],
                    "adoption": "checklist",
                }
            ],
            "conflicts": [],
            "limitations": [],
        }
        legacy = {
            "schema_version": "maestro_research_bundle_v1",
            "workflow_owner": "maestro",
            "question": legacy_packet["question"],
            "depth": "quick",
            "packets": [legacy_packet],
            "synthesis": {
                "adopted_claim_ids": ["legacy-claim"],
                "conflicts": [],
                "open_questions": [],
                "limitations": [],
            },
            "follow_up_waves": 0,
            "status": "completed",
        }
        result = validate_research_artifact(legacy)
        self.assertEqual("PASS", result["status"])
        self.assertEqual("historical", result["evidence_status"])
        self.assertFalse(result["gate_eligible"])

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.json"
            write_json(path, legacy)
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "route",
                        "--repo",
                        ".",
                        "--goal",
                        GOAL,
                        "--route-version",
                        "v2",
                        "--research-evidence",
                        str(path),
                        "--json",
                    ]
                )
        self.assertEqual(2, exit_code)
        self.assertEqual(
            "RESEARCH_BUNDLE_REQUIRED",
            json.loads(output.getvalue())["code"],
        )


if __name__ == "__main__":
    unittest.main()
