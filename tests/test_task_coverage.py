from __future__ import annotations

import copy
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tests.support import ROOT, write_json

from maestro.cli import main
from maestro.errors import MaestroError
from maestro.planning import route_goal_v2
from maestro.task_coverage import (
    MAX_COVERAGE_ITEMS,
    TASK_COVERAGE_VERSION,
    build_task_coverage,
    validate_task_coverage,
)
from maestro.util import canonical_json, sha256_text


def _allocation(
    kind: str,
    target_ref: str,
    evidence_type: str,
) -> dict[str, object]:
    return {
        "kind": kind,
        "target_ref": target_ref,
        "evidence_types": [evidence_type],
        "rationale": f"{kind} supplies the required {evidence_type} lane.",
    }


def _item(
    item_id: str,
    evidence_type: str,
    allocation: dict[str, object],
    *,
    materiality: str = "important",
) -> dict[str, object]:
    return {
        "item_id": item_id,
        "kind": "decision",
        "summary": f"Resolve {item_id}.",
        "failure_if_omitted": f"{item_id} would remain implicit.",
        "materiality": materiality,
        "evidence_types": [evidence_type],
        "source_refs": [],
        "depends_on": [],
        "allocations": [allocation],
    }


def _complete_draft() -> dict[str, object]:
    return {
        "discovery_status": "complete",
        "allocation_status": "complete",
        "items": [
            _item(
                "project-contract",
                "project-fact",
                _allocation(
                    "project-fact",
                    "project:pyproject.toml",
                    "project-fact",
                ),
                materiality="blocking",
            ),
            _item(
                "current-practice",
                "external-current",
                _allocation(
                    "research",
                    "research:researcher/current-practice",
                    "external-current",
                ),
            ),
            _item(
                "stable-method",
                "external-stable",
                _allocation(
                    "expertise-guide",
                    "guide:design-brief",
                    "external-stable",
                ),
            ),
            _item(
                "owner-choice",
                "owner-preference",
                _allocation(
                    "owner-decision",
                    "owner:user/choice",
                    "owner-preference",
                ),
            ),
            _item(
                "runtime-proof",
                "runtime-verification",
                _allocation(
                    "checker",
                    "checker:verifier/test-suite",
                    "runtime-verification",
                ),
            ),
        ],
    }


def _rehash(coverage: dict[str, object]) -> None:
    payload = copy.deepcopy(coverage)
    payload["coverage_id"] = ""
    coverage["coverage_id"] = sha256_text(canonical_json(payload))


class TaskCoverageTests(unittest.TestCase):
    def test_complete_coverage_is_deterministic_and_read_only(self) -> None:
        before = route_goal_v2(
            "Review the API contract",
            "medium",
            intent="review",
            repo_path=ROOT,
        )
        first = build_task_coverage(
            ROOT,
            "Review all material API decisions",
            _complete_draft(),
        )
        second = build_task_coverage(
            ROOT,
            "Review all material API decisions",
            _complete_draft(),
        )
        after = route_goal_v2(
            "Review the API contract",
            "medium",
            intent="review",
            repo_path=ROOT,
        )

        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertFalse(first["writes_performed"])
        validation = validate_task_coverage(
            first,
            goal="Review all material API decisions",
            repo_path=ROOT,
        )
        self.assertEqual("PASS", validation["status"])
        self.assertEqual("COMPLETE", validation["coverage_status"])
        self.assertEqual("NONE", validation["execution_authority"])

    def test_incomplete_inventory_is_valid_but_has_no_authority(self) -> None:
        draft = _complete_draft()
        draft["allocation_status"] = "incomplete"
        draft["items"][1]["allocations"] = [
            _allocation(
                "unresolved",
                "unresolved:current-practice",
                "external-current",
            )
        ]

        coverage = build_task_coverage(
            ROOT,
            "Review all material API decisions",
            draft,
        )
        result = validate_task_coverage(
            coverage,
            goal="Review all material API decisions",
            repo_path=ROOT,
        )

        self.assertEqual("PASS", result["status"])
        self.assertEqual("INCOMPLETE", result["coverage_status"])
        self.assertEqual("NONE", result["execution_authority"])

    def test_registry_and_project_targets_must_resolve(self) -> None:
        for allocation_index, target_ref in (
            (0, "project:missing-project-fact.md"),
            (2, "guide:missing-guide"),
            (4, "checker:missing-checker/test-suite"),
        ):
            with self.subTest(target_ref=target_ref):
                draft = _complete_draft()
                draft["items"][allocation_index]["allocations"][0][
                    "target_ref"
                ] = target_ref

                with self.assertRaises(MaestroError) as raised:
                    build_task_coverage(
                        ROOT,
                        "Review all material API decisions",
                        draft,
                    )

                self.assertIn(
                    "does not resolve",
                    raised.exception.message,
                )

    def test_validation_requires_the_exact_expected_goal(self) -> None:
        coverage = build_task_coverage(
            ROOT,
            "Review all material API decisions",
            _complete_draft(),
        )

        result = validate_task_coverage(
            coverage,
            goal="Review a different task",
            repo_path=ROOT,
        )

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "TASK_COVERAGE_GOAL_MISMATCH",
            {issue["code"] for issue in result["issues"]},
        )

    def test_supporting_work_may_be_explicitly_out_of_scope(self) -> None:
        draft = _complete_draft()
        draft["items"] = [
            _item(
                "future-benchmark",
                "external-current",
                _allocation(
                    "out-of-scope-explicit",
                    "out-of-scope:future-benchmark",
                    "external-current",
                ),
                materiality="supporting",
            )
        ]

        coverage = build_task_coverage(
            ROOT,
            "Review all material API decisions",
            draft,
        )
        result = validate_task_coverage(
            coverage,
            goal="Review all material API decisions",
            repo_path=ROOT,
        )

        self.assertEqual("PASS", result["status"])
        self.assertEqual("COMPLETE", result["coverage_status"])

    def test_complete_allocation_fails_on_uncovered_or_duplicate_work(
        self,
    ) -> None:
        uncovered_draft = _complete_draft()
        uncovered_draft["items"][1]["allocations"] = [
            _allocation(
                "lens",
                "lens:contract",
                "external-current",
            )
        ]
        with self.assertRaises(MaestroError) as uncovered:
            build_task_coverage(
                ROOT,
                "Review all material API decisions",
                uncovered_draft,
            )
        self.assertEqual("TASK_COVERAGE_INVALID", uncovered.exception.code)
        self.assertIn("external-current requires", uncovered.exception.message)

        duplicate_draft = _complete_draft()
        duplicate_draft["items"][0]["allocations"].append(
            copy.deepcopy(
                duplicate_draft["items"][0]["allocations"][0]
            )
        )
        with self.assertRaises(MaestroError) as duplicate:
            build_task_coverage(
                ROOT,
                "Review all material API decisions",
                duplicate_draft,
            )
        self.assertIn("must be unique", duplicate.exception.message)

    def test_dependencies_and_blocking_exclusions_fail_closed(self) -> None:
        cycle_draft = _complete_draft()
        cycle_draft["items"][0]["depends_on"] = ["current-practice"]
        cycle_draft["items"][1]["depends_on"] = ["project-contract"]
        with self.assertRaises(MaestroError) as cycle:
            build_task_coverage(
                ROOT,
                "Review all material API decisions",
                cycle_draft,
            )
        self.assertIn("contain a cycle", cycle.exception.message)

        excluded_draft = _complete_draft()
        excluded_draft["items"][0]["allocations"] = [
            _allocation(
                "out-of-scope-explicit",
                "out-of-scope:project-contract",
                "project-fact",
            )
        ]
        with self.assertRaises(MaestroError) as excluded:
            build_task_coverage(
                ROOT,
                "Review all material API decisions",
                excluded_draft,
            )
        self.assertIn("blocking item", excluded.exception.message)

    def test_more_than_sixty_four_items_are_rejected_without_truncation(
        self,
    ) -> None:
        draft = _complete_draft()
        template = draft["items"][0]
        draft["items"] = []
        for index in range(MAX_COVERAGE_ITEMS + 1):
            item = copy.deepcopy(template)
            item["item_id"] = f"item-{index}"
            draft["items"].append(item)

        with self.assertRaises(MaestroError) as raised:
            build_task_coverage(
                ROOT,
                "Review all material API decisions",
                draft,
            )

        self.assertEqual(MAX_COVERAGE_ITEMS + 1, len(draft["items"]))
        self.assertIn("never truncated", raised.exception.message)

    def test_item_identifiers_share_the_schema_length_limit(self) -> None:
        draft = _complete_draft()
        draft["items"][0]["item_id"] = "a" * 129

        with self.assertRaises(MaestroError) as raised:
            build_task_coverage(
                ROOT,
                "Review all material API decisions",
                draft,
            )

        self.assertIn(
            "unique lowercase kebab-case",
            raised.exception.message,
        )

    def test_digest_registry_and_revision_bindings_fail_when_tampered(
        self,
    ) -> None:
        coverage = build_task_coverage(
            ROOT,
            "Review all material API decisions",
            _complete_draft(),
        )
        digest_tampered = copy.deepcopy(coverage)
        digest_tampered["items"][0]["summary"] = "Changed after binding."
        digest_result = validate_task_coverage(
            digest_tampered,
            goal="Review all material API decisions",
            repo_path=ROOT,
        )
        self.assertIn(
            "TASK_COVERAGE_DIGEST_INVALID",
            {issue["code"] for issue in digest_result["issues"]},
        )

        registry_tampered = copy.deepcopy(coverage)
        registry_tampered["registry_digest"] = "0" * 64
        _rehash(registry_tampered)
        registry_result = validate_task_coverage(
            registry_tampered,
            goal="Review all material API decisions",
            repo_path=ROOT,
        )
        self.assertIn(
            "TASK_COVERAGE_REGISTRY_STALE",
            {issue["code"] for issue in registry_result["issues"]},
        )

        revision_tampered = copy.deepcopy(coverage)
        revision_tampered["base_revision"]["dirty_path_count"] += 1
        _rehash(revision_tampered)
        revision_result = validate_task_coverage(
            revision_tampered,
            goal="Review all material API decisions",
            repo_path=ROOT,
        )
        self.assertIn(
            "TASK_COVERAGE_REVISION_STALE",
            {issue["code"] for issue in revision_result["issues"]},
        )

    def test_malformed_lists_return_issues_instead_of_type_errors(self) -> None:
        coverage = build_task_coverage(
            ROOT,
            "Review all material API decisions",
            _complete_draft(),
        )
        coverage["items"][0]["source_refs"] = [{"unexpected": True}]
        _rehash(coverage)

        result = validate_task_coverage(
            coverage,
            goal="Review all material API decisions",
            repo_path=ROOT,
        )

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "TASK_COVERAGE_SOURCE_REFS_INVALID",
            {issue["code"] for issue in result["issues"]},
        )

    def test_unhashable_enum_values_return_diagnostics(self) -> None:
        for target, malformed in (
            (("items", 0, "kind"), {"kind": "decision"}),
            (("items", 0, "materiality"), ["blocking"]),
            (("items", 0, "evidence_types"), [{"type": "project-fact"}]),
            (
                ("items", 0, "allocations", 0, "kind"),
                {"kind": "project-fact"},
            ),
            (
                ("items", 0, "allocations", 0, "evidence_types"),
                [{"type": "project-fact"}],
            ),
        ):
            with self.subTest(target=target):
                coverage = build_task_coverage(
                    ROOT,
                    "Review all material API decisions",
                    _complete_draft(),
                )
                cursor: object = coverage
                for part in target[:-1]:
                    cursor = cursor[part]
                cursor[target[-1]] = malformed
                _rehash(coverage)

                result = validate_task_coverage(
                    coverage,
                    goal="Review all material API decisions",
                    repo_path=ROOT,
                )

                self.assertEqual("FAIL", result["status"])
                self.assertTrue(result["issues"])

    def test_invalid_unicode_returns_typed_diagnostics(self) -> None:
        coverage = build_task_coverage(
            ROOT,
            "Review all material API decisions",
            _complete_draft(),
        )
        coverage["items"][0]["summary"] = "\ud800"

        result = validate_task_coverage(
            coverage,
            goal="Review all material API decisions",
            repo_path=ROOT,
        )

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "TASK_COVERAGE_DIGEST_INVALID",
            {issue["code"] for issue in result["issues"]},
        )
        with self.assertRaises(MaestroError) as raised:
            build_task_coverage(ROOT, "\ud800", _complete_draft())
        self.assertEqual(
            "TASK_COVERAGE_GOAL_INVALID",
            raised.exception.code,
        )

    def test_cli_uses_distinct_complete_incomplete_and_invalid_exits(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            complete_draft_path = root / "complete-draft.json"
            incomplete_draft_path = root / "incomplete-draft.json"
            write_json(complete_draft_path, _complete_draft())
            incomplete_draft = _complete_draft()
            incomplete_draft["allocation_status"] = "incomplete"
            write_json(incomplete_draft_path, incomplete_draft)

            complete_output = StringIO()
            with redirect_stdout(complete_output):
                complete_exit = main(
                    [
                        "coverage",
                        "--repo",
                        str(ROOT),
                        "--goal",
                        "Review all material API decisions",
                        "--draft",
                        str(complete_draft_path),
                        "--json",
                    ]
                )
            coverage = json.loads(complete_output.getvalue())
            coverage_path = root / "coverage.json"
            write_json(coverage_path, coverage)

            validation_output = StringIO()
            with redirect_stdout(validation_output):
                validation_exit = main(
                    [
                        "validate-coverage",
                        "--repo",
                        str(ROOT),
                        "--goal",
                        "Review all material API decisions",
                        "--coverage",
                        str(coverage_path),
                        "--json",
                    ]
                )

            wrong_goal_output = StringIO()
            with redirect_stdout(wrong_goal_output):
                wrong_goal_exit = main(
                    [
                        "validate-coverage",
                        "--repo",
                        str(ROOT),
                        "--goal",
                        "Review a different task",
                        "--coverage",
                        str(coverage_path),
                        "--json",
                    ]
                )

            incomplete_output = StringIO()
            with redirect_stdout(incomplete_output):
                incomplete_exit = main(
                    [
                        "coverage",
                        "--repo",
                        str(ROOT),
                        "--goal",
                        "Review all material API decisions",
                        "--draft",
                        str(incomplete_draft_path),
                        "--json",
                    ]
                )

            invalid_coverage = copy.deepcopy(coverage)
            invalid_coverage["coverage_id"] = "0" * 64
            invalid_path = root / "invalid-coverage.json"
            write_json(invalid_path, invalid_coverage)
            invalid_output = StringIO()
            with redirect_stdout(invalid_output):
                invalid_exit = main(
                    [
                        "validate-coverage",
                        "--repo",
                        str(ROOT),
                        "--goal",
                        "Review all material API decisions",
                        "--coverage",
                        str(invalid_path),
                        "--json",
                    ]
                )

        self.assertEqual(0, complete_exit)
        self.assertEqual(0, validation_exit)
        self.assertEqual(2, wrong_goal_exit)
        self.assertEqual(4, incomplete_exit)
        self.assertEqual(2, invalid_exit)
        self.assertIn(
            "TASK_COVERAGE_GOAL_MISMATCH",
            {
                issue["code"]
                for issue in json.loads(
                    wrong_goal_output.getvalue()
                )["issues"]
            },
        )
        self.assertEqual(
            "COMPLETE",
            json.loads(validation_output.getvalue())["coverage_status"],
        )
        self.assertFalse(coverage["writes_performed"])

    def test_published_schema_matches_runtime_limits(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "src/maestro/resources/schemas/task-coverage.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            TASK_COVERAGE_VERSION,
            schema["properties"]["schema_version"]["const"],
        )
        self.assertEqual(
            MAX_COVERAGE_ITEMS,
            schema["properties"]["items"]["maxItems"],
        )
        self.assertEqual("shadow", schema["properties"]["mode"]["const"])
        self.assertFalse(schema["properties"]["writes_performed"]["const"])
        allocation_rules = schema["$defs"]["allocation"]["allOf"]
        self.assertEqual(11, len(allocation_rules))
        guide_rule = next(
            rule
            for rule in allocation_rules
            if rule["if"]["properties"]["kind"].get("const")
            == "expertise-guide"
        )
        self.assertEqual(
            "^guide:.+",
            guide_rule["then"]["properties"]["target_ref"]["pattern"],
        )
        self.assertEqual(
            512,
            schema["$defs"]["boundedRef"]["maxLength"],
        )


if __name__ == "__main__":
    unittest.main()
