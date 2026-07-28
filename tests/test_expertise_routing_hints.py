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
from maestro.expertise_routing import normalize_route_hints
from maestro.planning import route_goal_v2, validate_route_v2
from maestro.util import canonical_json, sha256_text


def _rehash(plan: dict[str, object]) -> None:
    payload = copy.deepcopy(plan)
    payload.pop("plan_id", None)
    plan["plan_id"] = sha256_text(canonical_json(payload))


class ExpertiseRouteHintTests(unittest.TestCase):
    def test_frozen_hint_cases_preserve_top_one_and_conflict_policy(
        self,
    ) -> None:
        cases = json.loads(
            (
                ROOT
                / "tests/fixtures/expertise-route-hint-cases.json"
            ).read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(cases), 7)

        for case in cases:
            with self.subTest(case=case["case_id"]):
                baseline = route_goal_v2(
                    case["goal"],
                    case["risk"],
                    intent="review",
                    repo_path=ROOT,
                )
                baseline_ids = baseline.get("expertise", {}).get(
                    "selected_pack_ids",
                    [],
                )
                self.assertEqual(
                    (
                        []
                        if case["baseline_pack_id"] is None
                        else [case["baseline_pack_id"]]
                    ),
                    baseline_ids,
                )
                hints = normalize_route_hints(
                    work_kinds=case["work_kinds"],
                    affected_paths=case["affected_paths"],
                    explicit_pack_id=case.get("explicit_pack_id"),
                )
                if case.get("expected_error"):
                    with self.assertRaises(MaestroError) as raised:
                        route_goal_v2(
                            case["goal"],
                            case["risk"],
                            intent="review",
                            repo_path=ROOT,
                            route_hints=hints,
                        )
                    self.assertEqual(
                        case["expected_error"],
                        raised.exception.code,
                    )
                    continue

                plan = route_goal_v2(
                    case["goal"],
                    case["risk"],
                    intent="review",
                    repo_path=ROOT,
                    route_hints=hints,
                )
                expertise = plan["expertise"]
                expected_pack_id = case["expected_pack_id"]
                self.assertEqual(
                    [] if expected_pack_id is None else [expected_pack_id],
                    expertise["selected_pack_ids"],
                )
                self.assertLessEqual(len(expertise["selected_pack_ids"]), 1)
                self.assertEqual(
                    "audit-only",
                    expertise["route_hints"]["path_policy"],
                )
                if case.get("expected_warning"):
                    self.assertIn(
                        case["expected_warning"],
                        {
                            warning["code"]
                            for warning in expertise["warnings"]
                        },
                    )
                result = validate_route_v2(plan, repo_path=ROOT)
                self.assertEqual("PASS", result["status"])
                self.assertEqual("READY", result["execution_status"])

    def test_hintless_routes_keep_the_optional_contract_absent(self) -> None:
        plan = route_goal_v2(
            "Review the API contract",
            "medium",
            intent="review",
            repo_path=ROOT,
        )

        self.assertNotIn("expertise", plan)
        self.assertEqual("PASS", validate_route_v2(plan)["status"])

    def test_paths_are_canonical_audit_evidence_not_selection_authority(
        self,
    ) -> None:
        hints = normalize_route_hints(
            affected_paths=[
                "src/zeta.ts",
                "./src/alpha.ts",
                "src/zeta.ts",
            ],
        )
        plan = route_goal_v2(
            "내부 이름을 정리해줘",
            "medium",
            intent="review",
            route_hints=hints,
        )

        self.assertEqual(
            ["src/alpha.ts", "src/zeta.ts"],
            plan["expertise"]["route_hints"]["affected_paths"],
        )
        self.assertEqual([], plan["expertise"]["selected_pack_ids"])
        self.assertEqual(
            "audit-only",
            plan["expertise"]["selection_trace"]["structured_routing"][
                "path_policy"
            ],
        )

    def test_invalid_hints_are_rejected_before_selection(self) -> None:
        invalid_calls = [
            (
                "EXPERTISE_WORK_KIND_LIMIT_EXCEEDED",
                {
                    "work_kinds": [
                        "user-interface",
                        "content-claim",
                        "software-structure",
                    ]
                },
            ),
            (
                "EXPERTISE_AFFECTED_PATH_INVALID",
                {"affected_paths": ["/Users/example/private.py"]},
            ),
            (
                "EXPERTISE_AFFECTED_PATH_INVALID",
                {"affected_paths": ["../outside.py"]},
            ),
            (
                "EXPERTISE_AFFECTED_PATH_INVALID",
                {"affected_paths": ["src\\windows.py"]},
            ),
            (
                "EXPERTISE_AFFECTED_PATH_INVALID",
                {"affected_paths": ["C:/private/windows.py"]},
            ),
            (
                "EXPERTISE_ROUTE_LINEAGE_REQUIRED",
                {"route_attempt": 2},
            ),
        ]

        for expected_code, arguments in invalid_calls:
            with self.subTest(code=expected_code):
                with self.assertRaises(MaestroError) as raised:
                    normalize_route_hints(**arguments)
                self.assertEqual(expected_code, raised.exception.code)

    def test_unknown_explicit_pack_is_rejected(self) -> None:
        hints = normalize_route_hints(explicit_pack_id="missing-pack")

        with self.assertRaises(MaestroError) as raised:
            route_goal_v2(
                "검토해줘",
                "medium",
                intent="review",
                repo_path=ROOT,
                route_hints=hints,
            )

        self.assertEqual(
            "EXPERTISE_PACK_EXPLICIT_UNKNOWN",
            raised.exception.code,
        )

    def test_tampered_hint_policy_is_rejected_on_plan_replay(self) -> None:
        plan = route_goal_v2(
            "검토해줘",
            "medium",
            intent="review",
            repo_path=ROOT,
            route_hints=normalize_route_hints(
                work_kinds=["software-structure"],
            ),
        )
        plan["expertise"]["route_hints"]["policy_digest"] = "0" * 64
        _rehash(plan)

        result = validate_route_v2(plan, repo_path=ROOT)

        self.assertEqual("FAIL", result["status"])
        self.assertIn(
            "ADAG_EXPERTISE_SELECTION_MISMATCH",
            {issue["code"] for issue in result["issues"]},
        )

    def test_cli_requires_v2_for_hints(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "route",
                    "--goal",
                    "검토해줘",
                    "--work-kind",
                    "software-structure",
                    "--json",
                ]
            )

        result = json.loads(output.getvalue())
        self.assertEqual(2, exit_code)
        self.assertEqual("ROUTE_VERSION_REQUIRED", result["code"])

    def test_one_correction_binds_prior_plan_and_rejects_a_third_route(
        self,
    ) -> None:
        goal = "두 페이지에서 같은 의미인 부분만 함께 쓰게 정리해줘"
        initial = route_goal_v2(
            goal,
            "medium",
            intent="review",
            repo_path=ROOT,
        )
        with tempfile.TemporaryDirectory() as temporary:
            initial_path = Path(temporary) / "initial.json"
            corrected_path = Path(temporary) / "corrected.json"
            write_json(initial_path, initial)

            corrected_output = StringIO()
            with redirect_stdout(corrected_output):
                corrected_exit = main(
                    [
                        "route",
                        "--repo",
                        str(ROOT),
                        "--goal",
                        goal,
                        "--risk",
                        "medium",
                        "--intent",
                        "review",
                        "--route-version",
                        "v2",
                        "--work-kind",
                        "software-structure",
                        "--prior-route-plan",
                        str(initial_path),
                        "--json",
                    ]
                )
            corrected = json.loads(corrected_output.getvalue())
            write_json(corrected_path, corrected)

            third_output = StringIO()
            with redirect_stdout(third_output):
                third_exit = main(
                    [
                        "route",
                        "--repo",
                        str(ROOT),
                        "--goal",
                        goal,
                        "--risk",
                        "medium",
                        "--intent",
                        "review",
                        "--route-version",
                        "v2",
                        "--work-kind",
                        "software-structure",
                        "--prior-route-plan",
                        str(corrected_path),
                        "--json",
                    ]
                )

        self.assertEqual(0, corrected_exit)
        hints = corrected["expertise"]["route_hints"]
        self.assertEqual(2, hints["route_attempt"])
        self.assertEqual(initial["plan_id"], hints["prior_plan_id"])
        self.assertEqual(
            initial["source_route_digest"],
            hints["prior_source_route_digest"],
        )
        self.assertEqual(2, third_exit)
        third = json.loads(third_output.getvalue())
        self.assertEqual(
            "EXPERTISE_REROUTE_LIMIT_EXCEEDED",
            third["code"],
        )

    def test_correction_cannot_change_stage_identity(self) -> None:
        initial = route_goal_v2(
            "첫 목표",
            "medium",
            intent="review",
            repo_path=ROOT,
        )
        with tempfile.TemporaryDirectory() as temporary:
            initial_path = Path(temporary) / "initial.json"
            write_json(initial_path, initial)
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "route",
                        "--repo",
                        str(ROOT),
                        "--goal",
                        "다른 목표",
                        "--risk",
                        "medium",
                        "--intent",
                        "review",
                        "--route-version",
                        "v2",
                        "--work-kind",
                        "software-structure",
                        "--prior-route-plan",
                        str(initial_path),
                        "--json",
                    ]
                )

        result = json.loads(output.getvalue())
        self.assertEqual(2, exit_code)
        self.assertEqual("EXPERTISE_REROUTE_STAGE_CHANGED", result["code"])


if __name__ == "__main__":
    unittest.main()
