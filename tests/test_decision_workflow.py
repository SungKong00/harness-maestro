from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.support import ROOT, write_json

from maestro.authorization import resolve_authorized_write_roots
from maestro.cli import main
from maestro.decisions import (
    DECISION_BUNDLE_VERSION,
    FINDING_PACKET_VERSION,
    build_decision_plan,
    build_execution_plan,
    validate_decision_bundle,
    validate_decision_plan,
    validate_execution_plan,
    validate_specialist_packet,
)
from maestro.errors import MaestroError
from maestro.model_policy import LEGACY_MODEL_ROUTE_FIELDS
from maestro.planning import route_goal_v2
from maestro.registry import resolve_request_contract, route_goal
from maestro.util import canonical_json, sha256_text


def _packet(
    plan: dict[str, object],
    specialist_id: str,
) -> dict[str, object]:
    specialist = next(
        item
        for item in plan["specialist_contracts"]
        if item["specialist_id"] == specialist_id
    )
    assignment = next(
        item
        for item in plan["assignments"]
        if item["specialist_id"] == specialist_id
    )
    return {
        "schema_version": FINDING_PACKET_VERSION,
        "decision_plan_id": plan["plan_id"],
        "assignment_id": assignment["assignment_id"],
        "specialist_id": specialist_id,
        "findings": [
            {
                "concern_id": specialist["owns"][0],
                "claim_kind": specialist["allowed_claim_kinds"][0],
                "statement": (
                    f"Evidence exposes a material {specialist['owns'][0]} "
                    "constraint that final synthesis must preserve."
                ),
                "evidence_refs": [f"artifact:{specialist_id}"],
                "confidence": "high",
            }
        ],
        "escalations": [],
    }


def _packets(plan: dict[str, object]) -> list[dict[str, object]]:
    return [
        _packet(plan, specialist["specialist_id"])
        for specialist in plan["specialist_contracts"]
    ]


def _bundle(
    plan: dict[str, object],
    packets: list[dict[str, object]],
    *,
    status: str = "ready",
    feasibility: str = "pass",
    unresolved: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    packet_digests = {
        packet["assignment_id"]: sha256_text(canonical_json(packet))
        for packet in packets
    }
    bundle = {
        "schema_version": DECISION_BUNDLE_VERSION,
        "bundle_digest": "",
        "decision_plan_id": plan["plan_id"],
        "registry_digest": plan["registry_digest"],
        "goal": plan["goal"],
        "goal_digest": plan["goal_digest"],
        "base_revision": plan["base_revision"],
        "risk": plan["risk"],
        "request_contract": plan["request_contract"],
        "expertise": plan["expertise"],
        "source_packet_digests": packet_digests,
        "accepted_constraints": ["Preserve the evidence-backed priority."],
        "accepted_decisions": [
            {
                "decision": "Use the synthesized bounded direction.",
                "rationale": "It satisfies the specialist constraints.",
                "evidence_refs": sorted(packet_digests),
            }
        ],
        "conflicts": [],
        "unresolved_questions": unresolved or [],
        "technical_feasibility": feasibility,
        "execution_scope": {
            "allowed_paths": ["src", "tests"],
            "prohibited_changes": ["external systems"],
        },
        "research_gate": plan["expertise"]["research_requirement"],
        "status": status,
    }
    payload = copy.deepcopy(bundle)
    payload.pop("bundle_digest")
    bundle["bundle_digest"] = sha256_text(canonical_json(payload))
    return bundle


class RequestBoundaryTests(unittest.TestCase):
    def test_korean_no_write_negation_wins_over_modify_keyword(self) -> None:
        route = route_goal(
            "웹 화면 디자인 방향만 판단해줘. 코드는 수정하지 마.",
            "medium",
        )

        self.assertEqual("review", route["intent"])
        self.assertEqual("lens-reviewer", route["binding"]["executor"])

        with self.assertRaises(MaestroError) as raised:
            route_goal(
                "웹 화면 디자인 방향만 판단해줘. 코드는 수정하지 마.",
                "medium",
                intent="implementation",
            )
        self.assertEqual(
            "SIDE_EFFECT_POLICY_CONFLICT",
            raised.exception.code,
        )

    def test_unknown_auto_request_defaults_to_review(self) -> None:
        route = route_goal("Consider the repository situation", "medium")

        self.assertEqual("review", route["intent"])
        self.assertEqual("lens-reviewer", route["binding"]["executor"])

    def test_english_and_mixed_no_write_requests_stay_read_only(self) -> None:
        for goal in (
            "Review the web design only; no code changes.",
            "UX를 검토해줘, but do not modify the code.",
        ):
            with self.subTest(goal=goal):
                route = route_goal(goal, "medium")
                self.assertEqual("review", route["intent"])
                self.assertEqual(
                    "lens-reviewer",
                    route["binding"]["executor"],
                )

    def test_external_write_prohibition_does_not_revoke_local_implementation(
        self,
    ) -> None:
        goal = (
            "로컬 코드에서 대시보드 전환 기능을 구현해줘. "
            "커밋·푸시·원격 변경은 하지 마."
        )

        route = route_goal(
            goal,
            "low",
            intent="implementation",
        )
        plan = route_goal_v2(
            goal,
            "low",
            intent="implementation",
            repo_path=ROOT,
        )

        self.assertEqual("implementation", route["intent"])
        self.assertEqual(
            ["repository_write"],
            plan["task_contract"]["allowed_side_effects"],
        )
        self.assertEqual(
            ["git_commit", "remote_write"],
            plan["task_contract"]["forbidden_side_effects"],
        )

    def test_external_prohibition_does_not_cross_sentence_boundary(
        self,
    ) -> None:
        request_contract = resolve_request_contract(
            "코드는 수정하지 마. 기존 커밋 기록을 검토해줘.",
            "auto",
        )

        self.assertEqual(
            "forbidden",
            request_contract["side_effect_policy"],
        )
        self.assertEqual([], request_contract["forbidden_side_effects"])

    def test_contrastive_external_prohibition_keeps_local_write_open(
        self,
    ) -> None:
        for goal in (
            "코드는 수정하되 커밋과 푸시는 하지 마.",
            "Modify the local files, but do not commit or push.",
        ):
            with self.subTest(goal=goal):
                request_contract = resolve_request_contract(
                    goal,
                    "implementation",
                )
                self.assertEqual(
                    "direct",
                    request_contract["side_effect_policy"],
                )
                self.assertEqual(
                    ["git_commit", "remote_write"],
                    request_contract["forbidden_side_effects"],
                )

    def test_english_staged_request_requires_decision_workflow(self) -> None:
        with self.assertRaises(MaestroError) as raised:
            route_goal(
                "Review the design, then implement the approved direction.",
                "medium",
                intent="implementation",
            )

        self.assertEqual("DECISION_WORKFLOW_REQUIRED", raised.exception.code)

    def test_staged_request_cannot_reach_direct_route(self) -> None:
        with self.assertRaises(MaestroError) as raised:
            route_goal(
                "먼저 디자인 방향을 판단한 후 구현해줘",
                "medium",
                intent="implementation",
            )

        self.assertEqual("DECISION_WORKFLOW_REQUIRED", raised.exception.code)


class DecisionPlanTests(unittest.TestCase):
    def test_three_lens_route_fails_instead_of_silently_dropping_one(
        self,
    ) -> None:
        with self.assertRaises(MaestroError) as raised:
            build_decision_plan(
                ROOT,
                "authentication transaction deploy를 검토한 후 구현해줘",
                "high",
            )

        self.assertEqual(
            "DECISION_COVERAGE_CAPACITY_EXCEEDED",
            raised.exception.code,
        )
        self.assertIn("rollback-observability-review", raised.exception.message)
        self.assertIn("Nothing was truncated", raised.exception.message)

    def test_every_selected_product_design_guide_is_assigned(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 정보 구조와 사용자 흐름을 판단한 후 구현해줘",
            "medium",
        )

        selected = set(plan["expertise"]["selected_guide_ids"])
        assigned = {
            guide_id
            for specialist in plan["specialist_contracts"]
            for guide_id in specialist["decision_guide_ids"]
        }
        ux = next(
            specialist
            for specialist in plan["specialist_contracts"]
            if specialist["specialist_id"] == "ux-product"
        )

        self.assertIn(
            "information-architecture-and-user-flow",
            selected,
        )
        self.assertIn(
            "information-architecture-and-user-flow",
            ux["decision_guide_ids"],
        )
        self.assertEqual(selected, assigned)
        self.assertEqual("PASS", validate_decision_plan(plan)["status"])

    def test_published_schema_and_product_skill_keep_decision_read_only(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "src/maestro/resources/schemas/decision-workflow.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            "maestro_decision_plan_v1",
            schema["$defs"]["decisionPlan"]["properties"][
                "schema_version"
            ]["const"],
        )
        self.assertEqual(
            [],
            schema["$defs"]["specialistContract"]["properties"][
                "allowed_side_effects"
            ]["const"],
        )
        product_skill = (
            ROOT / "skills/maestro-product-design/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("advisory criteria only", product_skill)
        self.assertNotIn("Implement through", product_skill)

    def test_product_design_uses_bounded_read_only_specialists(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )

        self.assertEqual("PASS", validate_decision_plan(plan)["status"])
        self.assertEqual(
            [
                "visual-design-review",
                "ux-product-review",
                "synthesis-1",
                "technical-feasibility-review",
                "final-synthesis",
            ],
            [item["assignment_id"] for item in plan["assignments"]],
        )
        self.assertEqual(
            {"visual-design", "ux-product", "technical-feasibility"},
            {
                item["specialist_id"]
                for item in plan["specialist_contracts"]
            },
        )
        self.assertTrue(
            all(item["read_only"] for item in plan["assignments"])
        )
        self.assertTrue(
            all(
                item["allowed_side_effects"] == []
                for item in plan["assignments"]
            )
        )
        stage_routes = {
            item["assignment_id"]: item["model_route"]
            for item in plan["assignments"]
        }
        self.assertEqual(
            "gpt-5.6-terra",
            stage_routes["visual-design-review"]["selected_model"],
        )
        self.assertEqual(
            "high",
            stage_routes["visual-design-review"]["reasoning_effort"],
        )
        self.assertEqual(
            "gpt-5.6-sol",
            stage_routes["synthesis-1"]["selected_model"],
        )
        self.assertEqual(
            "gpt-5.6-sol",
            stage_routes["final-synthesis"]["selected_model"],
        )
        self.assertEqual(
            {
                "specialist-review",
                "intermediate-synthesis",
                "technical-feasibility",
                "final-synthesis",
            },
            {
                route["stage_kind"]
                for route in stage_routes.values()
            },
        )
        visual = next(
            item
            for item in plan["specialist_contracts"]
            if item["specialist_id"] == "visual-design"
        )
        self.assertEqual(
            "advisory-only",
            visual["expertise_load"]["application_mode"],
        )
        self.assertEqual(
            "unavailable",
            visual["expertise_load"]["host_attestation"]["status"],
        )
        self.assertTrue(visual["expertise_load"]["packs"])
        loaded_guides = {
            guide["guide_id"]
            for pack in visual["expertise_load"]["packs"]
            for guide in pack["guides"]
        }
        self.assertEqual(
            set(visual["decision_guide_ids"]),
            loaded_guides,
        )
        self.assertEqual(
            "after_decision",
            plan["request_contract"]["side_effect_policy"],
        )

    def test_legacy_decision_routes_require_regeneration(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        for assignment in plan["assignments"]:
            route = assignment["model_route"]
            for field in list(route):
                if field not in LEGACY_MODEL_ROUTE_FIELDS:
                    route.pop(field)
            route["executor"] = 42
            route["risk"] = []
        payload = copy.deepcopy(plan)
        payload.pop("plan_id")
        plan["plan_id"] = sha256_text(canonical_json(payload))

        validation = validate_decision_plan(plan)

        self.assertEqual("FAIL", validation["status"])
        self.assertIn(
            "DECISION_MODEL_ROUTE_MISMATCH",
            {issue["code"] for issue in validation["issues"]},
        )

    def test_specialist_packet_enforces_finding_and_escalation_limits(
        self,
    ) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        packet = _packet(plan, "visual-design")
        packet["findings"] = [
            copy.deepcopy(packet["findings"][0]) for _ in range(6)
        ]

        finding_result = validate_specialist_packet(packet, plan)

        self.assertIn(
            "SPECIALIST_FINDING_LIMIT_EXCEEDED",
            {issue["code"] for issue in finding_result["issues"]},
        )

        escalation_packet = _packet(plan, "visual-design")
        escalation_packet["escalations"] = [
            {
                "target_specialism": "ux-product",
                "question": f"Clarify evidence boundary {index}.",
                "evidence_refs": [f"artifact:boundary-{index}"],
            }
            for index in range(4)
        ]

        escalation_result = validate_specialist_packet(
            escalation_packet,
            plan,
        )

        self.assertIn(
            "SPECIALIST_ESCALATION_LIMIT_EXCEEDED",
            {issue["code"] for issue in escalation_result["issues"]},
        )

    def test_unknown_pack_uses_generic_guide_bounded_specialist(self) -> None:
        digest = "a" * 64
        expertise = {
            "schema_version": "maestro_expertise_selection_v1",
            "selected_pack_ids": ["api-resilience"],
            "selected_guide_ids": ["retry-budget", "failure-recovery"],
            "pack_definition_digests": {"api-resilience": digest},
            "pack_cards": [
                {
                    "expertise_pack_id": "api-resilience",
                    "summary": "API resilience decision criteria.",
                    "status": "pilot",
                    "portability": "project",
                    "version": 1,
                    "skill_id": "api-resilience",
                    "origin": "project",
                    "pack_path": ".agents/skills/api-resilience/maestro-pack.json",
                    "skill_path": ".agents/skills/api-resilience/SKILL.md",
                    "definition_digest": digest,
                    "skill_definition_digest": digest,
                    "extends": None,
                    "guides": [
                        {
                            "guide_id": guide_id,
                            "summary": f"{guide_id} criteria.",
                            "freshness": "stable",
                            "origin": "project",
                            "skill_id": "api-resilience",
                            "resource_path": f"references/{guide_id}.md",
                            "skill_definition_digest": digest,
                        }
                        for guide_id in (
                            "retry-budget",
                            "failure-recovery",
                        )
                    ],
                    "source_manifest": "evidence/sources.json",
                    "evaluation_suite": "evals/cases.json",
                }
            ],
            "research_requirement": {
                "mode": "reuse",
                "gate": "not-required",
                "reasons": [],
                "evidence_digest": None,
            },
            "warnings": [],
            "selection_trace": {},
        }
        with patch(
            "maestro.decisions.select_expertise",
            return_value=(expertise, []),
        ):
            plan = build_decision_plan(
                ROOT,
                "Choose the API resilience direction before implementation",
                "medium",
            )

        generic = next(
            item
            for item in plan["specialist_contracts"]
            if item["specialist_id"] == "expertise-domain-review"
        )
        self.assertEqual(
            ["retry-budget", "failure-recovery"],
            generic["decision_guide_ids"],
        )
        self.assertEqual(
            {
                "references/retry-budget.md",
                "references/failure-recovery.md",
            },
            {
                guide["resource_path"]
                for pack_load in generic["expertise_load"]["packs"]
                for guide in pack_load["guides"]
            },
        )
        self.assertEqual("PASS", validate_decision_plan(plan)["status"])

    def test_marketing_and_qa_use_bounded_domain_specialists(self) -> None:
        cases = (
            (
                "Choose marketing positioning and campaign messaging before implementation",
                {"marketing-strategy", "marketing-evidence", "technical-feasibility"},
            ),
            (
                "Create a software QA strategy and regression plan before implementation",
                {"qa-risk-design", "qa-release-evidence", "technical-feasibility"},
            ),
        )
        for goal, expected in cases:
            with self.subTest(goal=goal):
                plan = build_decision_plan(ROOT, goal, "medium")
                specialist_ids = {
                    item["specialist_id"]
                    for item in plan["specialist_contracts"]
                }
                self.assertEqual(expected, specialist_ids)
                self.assertEqual(
                    "PASS",
                    validate_decision_plan(plan)["status"],
                )
                self.assertTrue(
                    all(
                        item["allowed_side_effects"] == []
                        for item in plan["specialist_contracts"]
                    )
                )

    def test_review_only_decision_remains_non_enactable(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "화면 디자인 방향만 판단해줘. 코드는 수정하지 마.",
            "medium",
            intent="review",
        )

        self.assertEqual(
            "forbidden",
            plan["request_contract"]["side_effect_policy"],
        )

    def test_specialist_packet_rejects_role_contamination_and_code_orders(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )

        visual = _packet(plan, "visual-design")
        visual["findings"][0]["concern_id"] = "technical-feasibility"
        visual_result = validate_specialist_packet(visual, plan)
        self.assertIn(
            "SPECIALIST_SCOPE_VIOLATION",
            {item["code"] for item in visual_result["issues"]},
        )

        ux = _packet(plan, "ux-product")
        ux["findings"][0]["statement"] = "Implement this by editing app.tsx."
        ux_result = validate_specialist_packet(ux, plan)
        self.assertIn(
            "SPECIALIST_IMPLEMENTATION_COMMAND_FORBIDDEN",
            {item["code"] for item in ux_result["issues"]},
        )

        technical = _packet(plan, "technical-feasibility")
        technical["findings"][0]["concern_id"] = "typography"
        technical_result = validate_specialist_packet(technical, plan)
        self.assertIn(
            "SPECIALIST_SCOPE_VIOLATION",
            {item["code"] for item in technical_result["issues"]},
        )

    def test_tampered_reviewer_write_request_is_rejected(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        plan["assignments"][0]["allowed_side_effects"] = [
            "repository_write"
        ]
        payload = copy.deepcopy(plan)
        payload.pop("plan_id")
        plan["plan_id"] = sha256_text(canonical_json(payload))

        result = validate_decision_plan(plan)

        self.assertIn(
            "DECISION_WRITE_FORBIDDEN",
            {item["code"] for item in result["issues"]},
        )

    def test_tampered_specialist_guide_load_is_rejected(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        visual = next(
            item
            for item in plan["specialist_contracts"]
            if item["specialist_id"] == "visual-design"
        )
        visual["expertise_load"]["packs"][0]["guides"][0][
            "resource_path"
        ] = "../hidden.md"
        payload = copy.deepcopy(plan)
        payload.pop("plan_id")
        plan["plan_id"] = sha256_text(canonical_json(payload))

        result = validate_decision_plan(plan)

        self.assertIn(
            "SPECIALIST_EXPERTISE_GUIDE_INVALID",
            {item["code"] for item in result["issues"]},
        )

    def test_malformed_external_plan_returns_diagnostics(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        plan["risk"] = {}
        plan["assignments"][0]["kind"] = []
        payload = copy.deepcopy(plan)
        payload.pop("plan_id")
        plan["plan_id"] = sha256_text(canonical_json(payload))

        result = validate_decision_plan(plan)

        self.assertEqual("FAIL", result["status"])
        self.assertTrue(result["issues"])


class DecisionEnactmentTests(unittest.TestCase):
    def test_execution_scope_resolves_only_existing_regular_directories(
        self,
    ) -> None:
        self.assertEqual(
            [(ROOT / "src" / "maestro").resolve()],
            resolve_authorized_write_roots(
                ROOT,
                ["src/maestro"],
            ),
        )
        invalid_paths = [
            ".",
            "..",
            str(ROOT),
            "missing-directory-for-enactment",
            "pyproject.toml",
        ]
        for invalid_path in invalid_paths:
            with self.subTest(path=invalid_path):
                with self.assertRaises(MaestroError):
                    resolve_authorized_write_roots(
                        ROOT,
                        [invalid_path],
                    )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "real").mkdir()
            (repo / "linked").symlink_to(repo / "real", target_is_directory=True)
            with self.assertRaises(MaestroError):
                resolve_authorized_write_roots(repo, ["linked"])

    def test_valid_bundle_authorizes_existing_one_writer_route(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        packets = _packets(plan)
        bundle = _bundle(plan, packets)

        validation = validate_decision_bundle(
            bundle,
            plan,
            packets,
            ROOT,
        )
        execution = build_execution_plan(
            ROOT,
            plan,
            bundle,
            packets,
            authorization_source="prior_explicit_request",
        )

        self.assertEqual("PASS", validation["status"])
        self.assertEqual("READY", validation["execution_status"])
        self.assertEqual(
            bundle["bundle_digest"],
            execution["execution_authorization"][
                "decision_bundle_digest"
            ],
        )
        self.assertEqual(
            "implementation",
            execution["route_plan"]["mutation_owner_assignment_id"],
        )
        self.assertEqual(
            "PASS",
            validate_execution_plan(
                execution,
                repo_path=ROOT,
            )["status"],
        )

    def test_execution_wrapper_cannot_self_attest_decision_evidence(
        self,
    ) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        packets = _packets(plan)
        execution = build_execution_plan(
            ROOT,
            plan,
            _bundle(plan, packets),
            packets,
            authorization_source="prior_explicit_request",
        )
        forged = copy.deepcopy(execution)
        forged.pop("decision_evidence")
        forged["execution_plan_id"] = ""
        forged["execution_plan_id"] = sha256_text(
            canonical_json(
                {
                    key: value
                    for key, value in forged.items()
                    if key != "execution_plan_id"
                }
            )
        )

        result = validate_execution_plan(
            forged,
            repo_path=ROOT,
        )

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "EXECUTION_DECISION_EVIDENCE_INVALID",
            {issue["code"] for issue in result["issues"]},
        )

    def test_execution_scope_is_bound_to_validated_decision_bundle(
        self,
    ) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        packets = _packets(plan)
        execution = build_execution_plan(
            ROOT,
            plan,
            _bundle(plan, packets),
            packets,
            authorization_source="prior_explicit_request",
        )
        execution["execution_authorization"]["allowed_paths"] = ["."]
        payload = copy.deepcopy(execution)
        payload.pop("execution_plan_id")
        execution["execution_plan_id"] = sha256_text(
            canonical_json(payload)
        )

        result = validate_execution_plan(
            execution,
            repo_path=ROOT,
        )

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "EXECUTION_AUTHORIZATION_SCOPE_MISMATCH",
            {issue["code"] for issue in result["issues"]},
        )

    def test_decision_bundle_rejects_unexecutable_write_roots(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        packets = _packets(plan)
        bundle = _bundle(plan, packets)
        bundle["execution_scope"]["allowed_paths"] = [
            "missing-directory-for-enactment"
        ]
        payload = copy.deepcopy(bundle)
        payload.pop("bundle_digest")
        bundle["bundle_digest"] = sha256_text(canonical_json(payload))

        result = validate_decision_bundle(
            bundle,
            plan,
            packets,
            ROOT,
        )

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "EXECUTION_SCOPE_INVALID",
            {issue["code"] for issue in result["issues"]},
        )

    def test_open_research_gate_blocks_enactment(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "최신 레퍼런스를 보고 랜딩 페이지 디자인을 판단한 후 구현해줘",
            "medium",
        )
        self.assertEqual(
            "open",
            plan["expertise"]["research_requirement"]["gate"],
        )
        packets = _packets(plan)
        bundle = _bundle(plan, packets, status="blocked")

        result = validate_decision_bundle(
            bundle,
            plan,
            packets,
            ROOT,
        )

        self.assertIn(
            "DECISION_RESEARCH_REQUIRED",
            {item["code"] for item in result["issues"]},
        )

    def test_blocker_and_failed_feasibility_block_enactment(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "웹 화면 디자인 방향을 판단한 후 구현해줘",
            "medium",
        )
        packets = _packets(plan)
        bundle = _bundle(
            plan,
            packets,
            status="blocked",
            feasibility="fail",
            unresolved=[
                {
                    "question": "Which irreversible option is approved?",
                    "blocking": True,
                    "owner": "user",
                }
            ],
        )

        result = validate_decision_bundle(
            bundle,
            plan,
            packets,
            ROOT,
        )
        codes = {item["code"] for item in result["issues"]}

        self.assertIn("DECISION_FEASIBILITY_FAILED", codes)
        self.assertIn("DECISION_BLOCKER_OPEN", codes)

    def test_repository_revision_drift_blocks_reused_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.name", "Test"],
                check=True,
            )
            (repo / "README.md").write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-qm", "initial"],
                check=True,
            )
            plan = build_decision_plan(
                repo,
                "웹 화면 디자인 방향을 판단한 후 구현해줘",
                "medium",
            )
            packets = _packets(plan)
            bundle = _bundle(plan, packets)
            (repo / "README.md").write_text("changed\n", encoding="utf-8")

            result = validate_decision_bundle(
                bundle,
                plan,
                packets,
                repo,
            )

        self.assertIn(
            "DECISION_REVISION_STALE",
            {item["code"] for item in result["issues"]},
        )

    def test_high_risk_requires_explicit_user_authorization(self) -> None:
        plan = build_decision_plan(
            ROOT,
            "인증 화면 디자인 방향을 판단한 후 구현해줘",
            "high",
        )
        packets = _packets(plan)
        bundle = _bundle(plan, packets)

        with self.assertRaises(MaestroError) as raised:
            build_execution_plan(
                ROOT,
                plan,
                bundle,
                packets,
                authorization_source="prior_explicit_request",
            )

        self.assertEqual("USER_DECISION_REQUIRED", raised.exception.code)

    def test_cli_decide_and_validate_are_read_only(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "decide",
                    "--repo",
                    str(ROOT),
                    "--goal",
                    "웹 화면 디자인 방향을 판단한 후 구현해줘",
                    "--json",
                ]
            )
        plan = json.loads(output.getvalue())
        with tempfile.TemporaryDirectory() as temporary:
            plan_path = Path(temporary) / "plan.json"
            write_json(plan_path, plan)
            validate_output = StringIO()
            with redirect_stdout(validate_output):
                validate_exit = main(
                    [
                        "validate-decision",
                        "--plan",
                        str(plan_path),
                        "--json",
                    ]
                )

        self.assertEqual(0, exit_code)
        self.assertEqual(0, validate_exit)
        self.assertFalse(plan["writes_performed"])


if __name__ == "__main__":
    unittest.main()
