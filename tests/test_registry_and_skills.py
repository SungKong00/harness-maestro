from __future__ import annotations

import copy
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import ROOT

from maestro.cli import parser
from maestro.errors import MaestroError
from maestro.registry import (
    load_domain_index_document,
    load_registry,
    registry_digest,
    route_goal,
    validate_registry,
)


class RegistryContractTests(unittest.TestCase):
    def test_bundled_registry_is_valid_and_separates_kinds(self) -> None:
        registry = load_registry()

        self.assertEqual([], validate_registry(registry))
        self.assertTrue(registry["lenses"])
        self.assertTrue(registry["executors"])
        self.assertTrue(registry["departments"])
        self.assertTrue(registry["adapters"])
        self.assertTrue(all(item["kind"] == "lens" for item in registry["lenses"]))
        self.assertTrue(
            all(item["kind"] == "executor" for item in registry["executors"])
        )

    def test_lens_rejects_executor_capabilities(self) -> None:
        registry = copy.deepcopy(load_registry())
        registry["lenses"][0]["capabilities"] = ["filesystem_write"]

        errors = validate_registry(registry)

        self.assertTrue(
            any("mixes executor fields: capabilities" in error for error in errors),
            errors,
        )

    def test_executor_rejects_lens_questions(self) -> None:
        registry = copy.deepcopy(load_registry())
        registry["executors"][0]["questions"] = ["What should this inspect?"]

        errors = validate_registry(registry)

        self.assertTrue(
            any("mixes lens fields: questions" in error for error in errors),
            errors,
        )

    def test_department_rejects_majority_and_unbounded_routing(self) -> None:
        registry = copy.deepcopy(load_registry())
        department = registry["departments"][0]
        department["routing"]["default_max_lenses"] = 3
        department["routing"]["high_risk_max_lenses"] = 4
        department["routing"]["lens_count_implies_agent_count"] = True
        department["deliberation"]["majority_vote"] = True
        department["deliberation"]["max_rebuttal_rounds"] = 2

        errors = validate_registry(registry)

        expected_fragments = (
            "default_max_lenses",
            "high_risk_max_lenses",
            "lens_count_implies_agent_count",
            "majority_vote",
            "max_rebuttal_rounds",
        )
        for fragment in expected_fragments:
            self.assertTrue(any(fragment in error for error in errors), errors)

    def test_boolean_is_not_accepted_as_one_rebuttal_round(self) -> None:
        registry = copy.deepcopy(load_registry())
        registry["departments"][0]["deliberation"]["max_rebuttal_rounds"] = True

        errors = validate_registry(registry)

        self.assertTrue(
            any("max_rebuttal_rounds" in error for error in errors),
            errors,
        )

    def test_domain_index_wrapper_is_validated_and_hashed(self) -> None:
        registry = load_registry()
        invalid = copy.deepcopy(load_domain_index_document())
        invalid["schema_version"] = "unknown"
        invalid["extra"] = True

        with patch(
            "maestro.registry.load_domain_index_document",
            return_value=invalid,
        ):
            errors = validate_registry(registry)

        self.assertTrue(any("domain index" in error for error in errors), errors)
        original_digest = registry_digest()
        changed = copy.deepcopy(load_domain_index_document())
        changed["domains"][0]["summary"] += " Changed."
        with patch(
            "maestro.registry.load_domain_index_document",
            return_value=changed,
        ):
            changed_digest = registry_digest()
        self.assertNotEqual(original_digest, changed_digest)

    def test_executor_capabilities_cannot_also_be_forbidden(self) -> None:
        registry = copy.deepcopy(load_registry())
        capability = registry["executors"][0]["capabilities"][0]
        registry["executors"][0]["forbidden_capabilities"].append(capability)

        errors = validate_registry(registry)

        self.assertTrue(
            any("allows and forbids" in error for error in errors),
            errors,
        )

    def test_executor_model_policy_rejects_unbounded_auto_effort(self) -> None:
        registry = copy.deepcopy(load_registry())
        policy = registry["executors"][0]["model_policy"]
        policy["maximum_auto_reasoning_effort"] = "ultra"
        policy["automatic_escalations"] = 2

        errors = validate_registry(registry)

        self.assertTrue(
            any("maximum reasoning effort" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("automatic escalations" in error for error in errors),
            errors,
        )


class RoutingContractTests(unittest.TestCase):
    def test_low_risk_is_capped_at_one_lens(self) -> None:
        route = route_goal("Review the API response", "low", ["contract"])

        self.assertEqual("fast", route["depth"])
        self.assertEqual(["contract"], route["selected_lenses"])
        self.assertEqual(
            "implementation-engineer",
            route["binding"]["executor"],
        )
        self.assertEqual(1, route["binding"]["runs"])
        self.assertFalse(route["selection_trace"]["load_all"])

        with self.assertRaises(MaestroError) as raised:
            route_goal(
                "Review the API and tests",
                "low",
                ["contract", "test-proof"],
            )
        self.assertEqual("LENS_LIMIT_EXCEEDED", raised.exception.code)

    def test_medium_risk_combines_two_lenses_in_one_reviewer_run(self) -> None:
        route = route_goal(
            "Review API behavior and its tests",
            "medium",
            ["contract", "test-proof"],
        )

        self.assertEqual("standard", route["depth"])
        self.assertEqual(2, len(route["selected_lenses"]))
        self.assertEqual("lens-reviewer", route["binding"]["executor"])
        self.assertEqual(1, route["binding"]["runs"])
        self.assertFalse(route["binding"]["fresh_context_per_lens"])
        self.assertEqual("combined_review", route["deliberation"]["mode"])

    def test_high_risk_uses_at_most_three_isolated_lens_runs(self) -> None:
        route = route_goal(
            "Review authorization, transactions, and rollback",
            "high",
            [
                "auth-boundary",
                "transaction-concurrency",
                "rollback-observability",
            ],
        )

        self.assertEqual("deep", route["depth"])
        self.assertEqual(3, route["binding"]["runs"])
        self.assertTrue(route["binding"]["fresh_context_per_lens"])
        self.assertEqual(
            "independent_blind_review",
            route["deliberation"]["mode"],
        )
        self.assertTrue(route["deliberation"]["blind_first"])
        self.assertFalse(route["deliberation"]["majority_vote"])
        self.assertFalse(route["deliberation"]["free_form_debate"])
        self.assertEqual(1, route["deliberation"]["max_rebuttal_rounds"])

        with self.assertRaises(MaestroError) as raised:
            route_goal(
                "Review four areas",
                "critical",
                [
                    "contract",
                    "auth-boundary",
                    "data-integrity",
                    "test-proof",
                ],
            )
        self.assertEqual("LENS_LIMIT_EXCEEDED", raised.exception.code)

    def test_unmatched_goal_does_not_load_the_catalog(self) -> None:
        route = route_goal("Rename an internal local variable", "medium")

        self.assertEqual("implementation", route["intent"])
        self.assertEqual("inferred", route["intent_source"])
        self.assertEqual([], route["selected_lenses"])
        self.assertEqual(0, route["selection_trace"]["returned_lens_bodies"])
        self.assertEqual(
            "implementation-engineer",
            route["binding"]["executor"],
        )
        self.assertEqual("none", route["deliberation"]["mode"])

    def test_unmatched_read_only_intents_use_read_only_executors(self) -> None:
        review = route_goal("Review the code organization", "low")
        research = route_goal("Research recent storage alternatives", "low")

        self.assertEqual("review", review["intent"])
        self.assertEqual("lens-reviewer", review["binding"]["executor"])
        self.assertIsNone(review["handoff_contract"])
        self.assertEqual("research", research["intent"])
        self.assertEqual("researcher", research["binding"]["executor"])
        self.assertIsNone(research["handoff_contract"])

    def test_explicit_intent_overrides_ambiguous_wording(self) -> None:
        route = route_goal(
            "Research alternatives before the requested change",
            "medium",
            intent="implementation",
        )

        self.assertEqual("implementation", route["intent"])
        self.assertEqual("explicit", route["intent_source"])
        self.assertEqual("implementation-engineer", route["binding"]["executor"])
        with self.assertRaises(MaestroError) as raised:
            route_goal("Review this", "low", intent="unsupported")
        self.assertEqual("INTENT_INVALID", raised.exception.code)

        arguments = parser().parse_args(
            [
                "route",
                "--goal",
                "Review this",
                "--intent",
                "review",
            ]
        )
        self.assertEqual("review", arguments.intent)

    def test_repository_word_does_not_imply_data_integrity(self) -> None:
        generic = route_goal("Review repository health", "medium")
        persistence = route_goal(
            "Migrate the persistence repository schema",
            "high",
        )

        self.assertNotIn("data-integrity", generic["selected_lenses"])
        self.assertIn("data-integrity", persistence["selected_lenses"])

    def test_low_risk_broad_scope_warns_without_changing_the_route(self) -> None:
        broad = route_goal("Implement a 500-file monolith rewrite", "low")
        small = route_goal("Rename 5 files", "low")
        medium = route_goal("Implement a 500-file monolith rewrite", "medium")

        self.assertEqual("low", broad["risk"])
        self.assertEqual("fast", broad["depth"])
        self.assertEqual([], broad["selected_lenses"])
        self.assertTrue(
            any(
                warning["code"] == "RISK_SCOPE_MISMATCH"
                for warning in broad["warnings"]
            )
        )
        self.assertEqual([], small["warnings"])
        self.assertEqual([], medium["warnings"])

    def test_ascii_triggers_do_not_match_arbitrary_word_prefixes(self) -> None:
        cases = (
            ("Rename the city variable", "test-proof"),
            ("Write an apiary description", "contract"),
            ("Document the dbus service", "data-integrity"),
        )
        for goal, forbidden_lens in cases:
            with self.subTest(goal=goal):
                route = route_goal(goal, "medium")
                self.assertNotIn(forbidden_lens, route["selected_lenses"])

    def test_korean_triggers_do_not_match_longer_unrelated_words(self) -> None:
        login = route_goal("로그인 실패 메시지 문구 수정", "medium")
        logging = route_goal("로그 보존 정책 수정", "medium")
        privacy = route_goal("개인정보 보존 정책 변경", "critical")

        self.assertNotIn(
            "rollback-observability",
            login["selected_lenses"],
        )
        self.assertIn(
            "rollback-observability",
            logging["selected_lenses"],
        )
        self.assertIn("data-integrity", privacy["selected_lenses"])

    def test_korean_case_markers_preserve_lens_recall(self) -> None:
        cases = (
            ("로그를 개선해줘", "rollback-observability"),
            ("인증을 검토해줘", "auth-boundary"),
            ("권한을 변경해줘", "auth-boundary"),
            ("데이터를 마이그레이션해줘", "data-integrity"),
            ("테스트를 추가해줘", "test-proof"),
        )

        for goal, expected_lens in cases:
            with self.subTest(goal=goal):
                self.assertIn(
                    expected_lens,
                    route_goal(goal, "medium")["selected_lenses"],
                )

    def test_review_route_declares_compact_writer_handoff(self) -> None:
        route = route_goal(
            "Change authorization behavior",
            "medium",
            ["auth-boundary"],
        )

        self.assertEqual(
            {
                "from_executor": "lens-reviewer",
                "to_executor": "implementation-engineer",
                "packet": "FindingPacket",
                "required_runtime_inputs": [
                    "objective",
                    "completion_contract",
                    "authorized_paths_or_interfaces",
                    "selected_convention_digests",
                    "stop_condition",
                ],
                "include": [
                    "findings",
                    "evidence_refs",
                    "recommended_action",
                    "open_questions",
                ],
                "exclude": [
                    "messages",
                    "hidden_reasoning",
                    "full_transcript",
                    "file_bodies",
                ],
                "fresh_artifact_read_required": True,
            },
            route["handoff_contract"],
        )
        implementation = next(
            item
            for item in load_registry()["executors"]
            if item["executor_id"] == "implementation-engineer"
        )
        self.assertIn("FindingPacket", implementation["accepts"])
        self.assertNotIn("DesignEnvelope", implementation["accepts"])

    def test_full_idempotency_and_deployment_variants_still_route(self) -> None:
        idempotency = route_goal(
            "Implement idempotency for payment retries",
            "medium",
        )
        deployment = route_goal(
            "Prepare the production deployment",
            "medium",
        )

        self.assertIn(
            "transaction-concurrency",
            idempotency["selected_lenses"],
        )
        self.assertIn(
            "rollback-observability",
            deployment["selected_lenses"],
        )

    def test_every_route_binding_names_a_registered_executor(self) -> None:
        executor_ids = {
            item["executor_id"] for item in load_registry()["executors"]
        }
        routes = (
            route_goal("Rename a local variable", "low"),
            route_goal("Review the API contract", "medium"),
            route_goal("Review auth and rollback", "high"),
        )

        for route in routes:
            self.assertIn(route["binding"]["executor"], executor_ids)

    def test_large_mechanical_rename_uses_economy_not_frontier(self) -> None:
        route = route_goal(
            "Rename the old_customer_id field across many generated fixtures",
            "medium",
        )

        self.assertEqual("mechanical-change", route["model_route"]["task_class"])
        self.assertEqual("economy", route["model_route"]["selected_class"])
        self.assertEqual("gpt-5.6-luna", route["model_route"]["selected_model"])
        self.assertIn(
            route["model_route"]["reasoning_effort"],
            {"low", "medium"},
        )

    def test_mechanical_auth_change_does_not_hide_high_impact_boundary(self) -> None:
        route = route_goal(
            "Rename authorization roles across policy fixtures",
            "medium",
        )

        self.assertEqual("frontier", route["model_route"]["selected_class"])
        self.assertEqual("gpt-5.6-sol", route["model_route"]["selected_model"])

    def test_security_policy_uses_frontier_even_when_change_is_small(self) -> None:
        route = route_goal(
            "Make a small authorization policy change for admin tokens",
            "low",
        )

        self.assertEqual("high-impact-judgment", route["model_route"]["task_class"])
        self.assertEqual("frontier", route["model_route"]["selected_class"])
        self.assertEqual("gpt-5.6-sol", route["model_route"]["selected_model"])
        self.assertEqual("high", route["model_route"]["reasoning_effort"])
        self.assertFalse(route["model_route"]["escalation_allowed"])
        self.assertIn("NEEDS_DECISION", route["model_route"]["fallback"])

    def test_general_crud_uses_balanced_model(self) -> None:
        route = route_goal(
            "Implement a CRUD endpoint for project labels",
            "medium",
        )

        self.assertEqual("general-implementation", route["model_route"]["task_class"])
        self.assertEqual("balanced", route["model_route"]["selected_class"])
        self.assertEqual("gpt-5.6-terra", route["model_route"]["selected_model"])
        self.assertEqual("medium", route["model_route"]["reasoning_effort"])
        self.assertEqual(
            {
                "executor",
                "task_class",
                "risk",
                "host",
                "selected_class",
                "selected_model",
                "reasoning_effort",
                "selection_reason",
                "escalation_allowed",
                "fallback",
            },
            set(route["model_route"]),
        )

    def test_metadata_extraction_uses_economy_model(self) -> None:
        route = route_goal(
            "Extract Markdown frontmatter metadata into a sorted table",
            "low",
        )

        self.assertEqual("metadata-extraction", route["model_route"]["task_class"])
        self.assertEqual("economy", route["model_route"]["selected_class"])
        self.assertEqual("gpt-5.6-luna", route["model_route"]["selected_model"])

    def test_deterministic_test_execution_has_no_model_route(self) -> None:
        route = route_goal("Run the unit tests and lint command", "medium")

        self.assertEqual(
            "deterministic-verification",
            route["model_route"]["task_class"],
        )
        self.assertIsNone(route["model_route"]["selected_class"])
        self.assertIsNone(route["model_route"]["selected_model"])
        self.assertIsNone(route["model_route"]["reasoning_effort"])
        self.assertFalse(route["model_route"]["escalation_allowed"])
        self.assertEqual([], route["selected_lenses"])
        self.assertEqual("none", route["deliberation"]["mode"])

    def test_mixed_test_and_authorization_change_is_not_command_only(self) -> None:
        route = route_goal(
            "Run tests and fix authorization policy failures",
            "high",
        )

        self.assertIn("auth-boundary", route["selected_lenses"])
        self.assertEqual("frontier", route["model_route"]["selected_class"])
        self.assertEqual("gpt-5.6-sol", route["model_route"]["selected_model"])

    def test_critical_risk_uses_one_reversibility_fallback_lens(self) -> None:
        route = route_goal(
            "Delete the production search index after approval",
            "critical",
        )

        self.assertEqual(["delivery-feasibility"], route["selected_lenses"])
        self.assertEqual(
            ["critical-risk-fallback"],
            route["selection_reasons"]["delivery-feasibility"],
        )
        self.assertEqual("frontier", route["model_route"]["selected_class"])
        self.assertEqual("gpt-5.6-sol", route["model_route"]["selected_model"])

    def test_executor_default_class_and_reasoning_are_authoritative(self) -> None:
        registry = load_registry()
        executor = next(
            item
            for item in registry["executors"]
            if item["executor_id"] == "implementation-engineer"
        )
        executor["model_policy"]["default_class"] = "frontier"
        executor["model_policy"]["default_reasoning_effort"] = "high"

        with patch("maestro.registry.load_registry", return_value=registry):
            route = route_goal("Implement a CRUD endpoint", "medium")

        self.assertEqual("frontier", route["model_route"]["selected_class"])
        self.assertEqual("high", route["model_route"]["reasoning_effort"])

    def test_material_conflict_routes_only_one_explicit_lane(self) -> None:
        initial = route_goal(
            "Review the API response and its tests",
            "medium",
            ["contract", "test-proof"],
        )
        escalated = route_goal(
            "Resolve material conflict: the contract fixture contradicts the implementation response",
            "medium",
            ["contract"],
            conflict_evidence="The executable contract fixture returns 409 while the implementation claims 200.",
        )

        self.assertEqual("gpt-5.6-terra", initial["model_route"]["selected_model"])
        self.assertEqual("gpt-5.6-sol", escalated["model_route"]["selected_model"])
        self.assertEqual(
            "frontier",
            escalated["model_route"]["selected_class"],
        )
        self.assertNotIn(
            initial["model_route"]["reasoning_effort"],
            {"max", "ultra"},
        )
        with self.assertRaises(MaestroError) as raised:
            route_goal(
                "Resolve material conflict across both disputed lanes",
                "medium",
                ["contract", "test-proof"],
            )
        self.assertEqual("CONFLICT_SCOPE_INVALID", raised.exception.code)

        with self.assertRaises(MaestroError) as raised:
            route_goal(
                "Resolve material conflict",
                "medium",
                ["contract"],
            )
        self.assertEqual("CONFLICT_EVIDENCE_REQUIRED", raised.exception.code)


class SkillPackageTests(unittest.TestCase):
    SKILL_NAMES = (
        "maestro",
        "maestro-adapter-builder",
        "maestro-govern",
    )

    def test_each_skill_has_matching_metadata_and_resolvable_references(self) -> None:
        for name in self.SKILL_NAMES:
            with self.subTest(skill=name):
                skill_root = ROOT / "skills" / name
                skill_file = skill_root / "SKILL.md"
                metadata = skill_root / "agents" / "openai.yaml"
                self.assertTrue(skill_file.is_file())
                self.assertTrue(metadata.is_file())

                text = skill_file.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                frontmatter_end = text.find("\n---", 4)
                self.assertGreater(frontmatter_end, 4)
                frontmatter = text[4:frontmatter_end]
                self.assertRegex(frontmatter, rf"(?m)^name: {re.escape(name)}$")
                description = re.search(
                    r"(?m)^description:\s*(.+)$",
                    frontmatter,
                )
                self.assertIsNotNone(description)
                self.assertGreater(len(description.group(1).strip()), 40)
                self.assertNotIn("TODO", text.upper())

                references = sorted(
                    set(re.findall(r"references/[A-Za-z0-9_.-]+\.md", text))
                )
                self.assertTrue(references)
                for relative in references:
                    self.assertTrue((skill_root / relative).is_file(), relative)

                yaml_text = metadata.read_text(encoding="utf-8")
                self.assertIn(f"$" + name, yaml_text)
                expected = "true" if name == "maestro" else "false"
                self.assertRegex(
                    yaml_text,
                    rf"(?m)^  allow_implicit_invocation: {expected}$",
                )

    def test_generic_runtime_and_skills_have_no_project_or_home_path_leakage(
        self,
    ) -> None:
        project_name = "SS" + "ING"
        home_prefix = "/" + "Users" + "/"
        failures: dict[str, list[str]] = {}
        for base in (ROOT / "src", ROOT / "skills"):
            for path in sorted(base.rglob("*")):
                if not path.is_file() or path.suffix not in {
                    ".py",
                    ".json",
                    ".md",
                    ".yaml",
                    ".yml",
                }:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                found: list[str] = []
                if re.search(
                    rf"(?<![A-Za-z]){project_name}(?![A-Za-z])",
                    text,
                ):
                    found.append(project_name)
                if home_prefix in text:
                    found.append(home_prefix)
                if found:
                    failures[path.relative_to(ROOT).as_posix()] = found

        self.assertEqual({}, failures)

    def test_maestro_separates_project_conventions_from_global_candidates(
        self,
    ) -> None:
        text = (ROOT / "skills/maestro/SKILL.md").read_text(encoding="utf-8")

        self.assertIn("selected_conventions", text)
        self.assertIn("convention_status", text)
        self.assertIn("self_improvement", text)
        self.assertIn("at most one `docs/conventions/<topic>.md`", text)
        self.assertIn("automatically report", text)
        self.assertIn("Do not create or update an active Convention", text)
        self.assertIn("Do not let same-run evidence activate a Convention", text)
        self.assertIn("global_harness_candidates", text)
        self.assertIn("maestro record", text)
        self.assertIn("`NEEDS_DECISION` instead of convention-writing", text)
        self.assertIn("$reference-research-team", text)
        self.assertIn("$orchestrated-work-session", text)
        self.assertNotIn(
            "promote a convention during the same run",
            text,
        )


if __name__ == "__main__":
    unittest.main()
