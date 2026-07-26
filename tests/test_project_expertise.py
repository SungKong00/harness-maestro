from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.support import apply_fresh_init, check_by_id, write_json

from maestro.doctor import doctor_report
from maestro.expertise import expertise_manifest_digest
from maestro.expertise_lifecycle import (
    apply_expertise_activation_plan,
    apply_expertise_deactivation_plan,
    apply_expertise_update_plan,
    build_expertise_activation_plan,
    build_expertise_deactivation_plan,
    build_expertise_update_plan,
    expertise_inventory,
)
from maestro.governance import govern_report, record_run
from maestro.planning import route_goal_v2, validate_route_v2
from maestro.registry import load_registry


def _candidate(
    repo: Path,
    *,
    candidate_id: str = "project-design",
    pack_id: str = "project-design",
    version: int = 1,
    guide_id: str = "project-type-rules",
    guide_text: str = (
        "# Project type rules\n\n"
        "purpose: Preserve the approved project typography.\n"
    ),
    stale_base: bool = False,
    standalone: bool = False,
) -> None:
    root = (
        repo
        / ".maestro/state/candidates/expertise"
        / candidate_id
    )
    base = next(
        pack
        for pack in load_registry()["expertise_packs"]
        if pack["expertise_pack_id"] == "product-design"
    )
    digest = "0" * 64 if stale_base else expertise_manifest_digest(base)
    candidate = {
        "schema_version": "maestro_expertise_candidate_v1",
        "candidate_id": candidate_id,
        "expertise_pack_id": pack_id,
        "status": "candidate",
        "portability": "project",
        "owner": "test-owner",
        "review_after": "2026-08-31",
        "problem": "Project typography rules are repeatedly omitted.",
        "reusable_when": ["Designing project screens"],
        "not_for": ["Unrelated backend work"],
        "existing_coverage": "Adds project typography to product-design.",
        "evidence_refs": ["research:project-type"],
        "proposed_guides": [
            {
                "guide_id": guide_id,
                "failure_prevented": "Wrong project font hierarchy",
                "decision_checks": ["Use approved families", "Verify hierarchy"],
                "freshness": "versioned",
            }
        ],
        "evaluation": {
            "baseline": "existing-pack",
            "cases_path": "evals/cases.json",
            "pass_criteria": ["Catches the project font mismatch"],
            "regression_criteria": ["Does not trigger on backend work"],
        },
    }
    pack = {
        "schema_version": "maestro_expertise_pack_v1",
        "kind": "expertise-pack",
        "expertise_pack_id": pack_id,
        "summary": "Project-specific product design criteria.",
        "status": "pilot",
        "portability": "project",
        "version": version,
        "triggers": ["project typography", "프로젝트 타이포그래피"],
        "skill_id": pack_id,
        "default_guides": [guide_id],
        "guides": [
            {
                "guide_id": guide_id,
                "summary": "Apply the project's approved font and hierarchy rules.",
                "triggers": ["project typography", "프로젝트 타이포그래피"],
                "freshness": "versioned",
            }
        ],
        "research_policy": {
            "default_mode": "reuse",
            "contextualize_triggers": ["current project font"],
            "refresh_triggers": ["refresh project typography"],
        },
        "source_manifest": "evidence/sources.json",
        "evaluation_suite": "evals/cases.json",
    }
    if not standalone:
        pack["extends"] = {
            "expertise_pack_id": "product-design",
            "version": base["version"],
            "digest": digest,
        }
    write_json(root / "candidate.json", candidate)
    write_json(root / "draft/maestro-pack.json", pack)
    (root / "draft/references").mkdir(parents=True, exist_ok=True)
    (root / "draft/agents").mkdir(parents=True, exist_ok=True)
    (root / "draft/SKILL.md").write_text(
        "---\n"
        f"name: {pack_id}\n"
        f"description: Use only when Maestro selects the {pack_id} pack.\n"
        "---\n\n"
        "# Project design\n\n"
        "Load only the selected project guide.\n",
        encoding="utf-8",
    )
    (root / f"draft/references/{guide_id}.md").write_text(
        guide_text,
        encoding="utf-8",
    )
    (root / "draft/agents/openai.yaml").write_text(
        "interface:\n"
        '  display_name: "Project design"\n'
        "policy:\n"
        "  allow_implicit_invocation: false\n",
        encoding="utf-8",
    )
    write_json(root / "evidence/sources.json", {"sources": ["project:design-system"]})
    write_json(root / "evals/cases.json", {"cases": ["target", "near-miss"]})


class ProjectExpertiseLifecycleTests(unittest.TestCase):
    def test_candidate_is_not_routed_until_reviewed_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)

            before = route_goal_v2(
                "Apply our project typography to the product design",
                "medium",
                intent="review",
                repo_path=repo,
            )
            self.assertNotIn(
                "project-design",
                before.get("expertise", {}).get("selected_pack_ids", []),
            )

            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="held_out_evaluation:eval-7",
            )
            plan_path = Path(temporary) / "activation.json"
            write_json(plan_path, activation)
            result = apply_expertise_activation_plan(plan_path, repo)

            self.assertTrue(result["candidate_retained"])
            self.assertTrue(
                (repo / ".agents/skills/project-design/SKILL.md").is_file()
            )
            snapshot = json.loads(
                (
                    repo
                    / ".agents/skills/project-design/evidence/candidate.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual("project-design", snapshot["candidate_id"])
            after = route_goal_v2(
                "Apply our project typography to the product design",
                "medium",
                intent="review",
                repo_path=repo,
            )
            expertise = after["expertise"]
            self.assertEqual(
                ["project-design"],
                expertise["selected_pack_ids"],
            )
            card = expertise["pack_cards"][0]
            self.assertEqual("project", card["origin"])
            self.assertEqual(
                "product-design",
                card["extends"]["expertise_pack_id"],
            )
            self.assertEqual(
                "project",
                next(
                    guide["origin"]
                    for guide in card["guides"]
                    if guide["guide_id"] == "project-type-rules"
                ),
            )
            self.assertEqual(
                "PASS",
                validate_route_v2(after, repo_path=repo)["status"],
            )
            self.assertEqual(
                "FAIL",
                validate_route_v2(after)["status"],
            )
            self.assertEqual(
                "PASS",
                check_by_id(doctor_report(repo), "PROJECT_EXPERTISE")["status"],
            )
            inventory = expertise_inventory(repo)
            self.assertEqual(1, len(inventory["candidates"]))
            self.assertIn(
                "project-design",
                {
                    pack["expertise_pack_id"]
                    for pack in inventory["packs"]
                    if pack["origin"] == "project"
                },
            )

    def test_activation_rejects_stale_base_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo, stale_base=True)

            with self.assertRaisesRegex(Exception, "extends must pin"):
                build_expertise_activation_plan(
                    repo,
                    candidate_id="project-design",
                    approval_ref="owner_decision:issue-12",
                )

    def test_activation_rejects_an_expired_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            candidate_path = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "candidate.json"
            )
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["review_after"] = "2020-01-01"
            write_json(candidate_path, candidate)

            with self.assertRaisesRegex(Exception, "Expired candidates"):
                build_expertise_activation_plan(
                    repo,
                    candidate_id="project-design",
                    approval_ref="owner_decision:issue-expired",
                )

    def test_activation_rejects_a_git_ignored_active_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(repo)],
                check=True,
            )
            apply_fresh_init(repo)
            _candidate(repo)
            ignore = repo / ".gitignore"
            ignore.write_text(
                ignore.read_text(encoding="utf-8") + "\n.agents/\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(Exception, "must not be Git-ignored"):
                build_expertise_activation_plan(
                    repo,
                    candidate_id="project-design",
                    approval_ref="owner_decision:issue-ignore",
                )

    def test_standalone_project_pack_is_supported_for_a_new_domain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo, standalone=True)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="held_out_evaluation:eval-standalone",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)

            route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )

            self.assertEqual(
                ["project-design"],
                route["expertise"]["selected_pack_ids"],
            )
            self.assertIsNone(route["expertise"]["pack_cards"][0]["extends"])

    def test_route_validation_detects_changed_active_skill_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-13",
            )
            plan_path = Path(temporary) / "activation.json"
            write_json(plan_path, activation)
            apply_expertise_activation_plan(plan_path, repo)
            route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )

            skill = repo / ".agents/skills/project-design/SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nChanged.\n",
                encoding="utf-8",
            )

            validation = validate_route_v2(route, repo_path=repo)
            self.assertEqual("FAIL", validation["status"])
            self.assertIn(
                "ADAG_EXPERTISE_SELECTION_MISMATCH",
                {issue["code"] for issue in validation["issues"]},
            )

    def test_local_pack_usage_is_accepted_by_project_governance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-14",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            receipt_path = Path(temporary) / "receipt.json"
            write_json(
                receipt_path,
                {
                    "run_id": "project-design-run",
                    "risk": "low",
                    "route_depth": "fast",
                    "selected_lenses": [],
                    "selected_expertise_packs": ["project-design"],
                    "selected_decision_guides": ["project-type-rules"],
                    "expertise_research_mode": "reuse",
                    "expertise_research_gate": "not-required",
                    "executor_runs": 1,
                    "primary_executor_id": "implementation-engineer",
                    "executor_ids": ["implementation-engineer"],
                    "outcome": "completed",
                    "evidence_refs": ["artifact:screen"],
                    "duration_ms": 100,
                    "tokens": None,
                    "correction_count": 0,
                    "agent_calls": 1,
                    "verifier_result": "not_run",
                    "command_artifact_ref": None,
                },
            )

            recorded = record_run(repo, receipt_path)
            event = json.loads(
                (repo / recorded["event_path"])
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            report = govern_report(repo, window=20, threshold=2)

            self.assertIn(
                "project-design",
                event["expertise_pack_definition_digests"],
            )
            self.assertEqual(
                {"project-design": 1},
                report["expertise_pack_usage"],
            )

    def test_stale_activation_plan_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-15",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            skill = (
                repo
                / ".maestro/state/candidates/expertise/project-design"
                / "draft/SKILL.md"
            )
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nCandidate changed.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(Exception, "changed after preview"):
                apply_expertise_activation_plan(activation_path, repo)

            self.assertFalse((repo / ".agents/skills/project-design").exists())
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            self.assertEqual([], project["expertise"]["active_pack_paths"])

    def test_reviewed_update_replaces_one_version_and_keeps_a_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-16",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            old_route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )

            _candidate(
                repo,
                candidate_id="project-design-v2",
                pack_id="project-design",
                version=2,
                guide_id="project-layout-rules",
                guide_text=(
                    "# Project layout rules\n\n"
                    "purpose: Verify hierarchy and layout together.\n"
                ),
            )
            update = build_expertise_update_plan(
                repo,
                candidate_id="project-design-v2",
                approval_ref="held_out_evaluation:eval-16",
            )
            update_path = Path(temporary) / "update.json"
            write_json(update_path, update)
            result = apply_expertise_update_plan(update_path, repo)

            self.assertEqual(2, result["version"])
            self.assertFalse(
                (
                    repo
                    / ".agents/skills/project-design/references/"
                    "project-type-rules.md"
                ).exists()
            )
            self.assertTrue(
                (
                    repo
                    / ".agents/skills/project-design/references/"
                    "project-layout-rules.md"
                ).is_file()
            )
            snapshot = json.loads(
                (
                    repo
                    / ".agents/skills/project-design/evidence/candidate.json"
                ).read_text(encoding="utf-8")
            )
            publication = json.loads(
                (
                    repo / ".agents/skills/project-design/activation.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual("project-design-v2", snapshot["candidate_id"])
            self.assertEqual("update", publication["action"])
            self.assertIsNotNone(
                publication["previous_definition_digest"]
            )
            self.assertEqual(
                "FAIL",
                validate_route_v2(old_route, repo_path=repo)["status"],
            )
            new_route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )
            self.assertEqual(
                "PASS",
                validate_route_v2(new_route, repo_path=repo)["status"],
            )
            self.assertEqual(
                2,
                new_route["expertise"]["pack_cards"][0]["version"],
            )

    def test_update_requires_exactly_one_version_increment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-17",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            _candidate(
                repo,
                candidate_id="project-design-same-version",
                pack_id="project-design",
                version=1,
            )

            with self.assertRaisesRegex(Exception, "exactly one"):
                build_expertise_update_plan(
                    repo,
                    candidate_id="project-design-same-version",
                    approval_ref="owner_decision:issue-17-update",
                )

    def test_stale_update_plan_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-18",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            _candidate(
                repo,
                candidate_id="project-design-v2",
                pack_id="project-design",
                version=2,
            )
            update = build_expertise_update_plan(
                repo,
                candidate_id="project-design-v2",
                approval_ref="owner_decision:issue-18-update",
            )
            update_path = Path(temporary) / "update.json"
            write_json(update_path, update)
            candidate_guide = (
                repo
                / ".maestro/state/candidates/expertise/project-design-v2"
                / "draft/references/project-type-rules.md"
            )
            candidate_guide.write_text(
                candidate_guide.read_text(encoding="utf-8") + "\nChanged.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(Exception, "changed after preview"):
                apply_expertise_update_plan(update_path, repo)

            active_pack = json.loads(
                (
                    repo / ".agents/skills/project-design/maestro-pack.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(1, active_pack["version"])

    def test_deactivation_preserves_skill_files_and_stops_routing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-19",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)
            deactivation = build_expertise_deactivation_plan(
                repo,
                expertise_pack_id="project-design",
            )
            deactivation_path = Path(temporary) / "deactivation.json"
            write_json(deactivation_path, deactivation)
            result = apply_expertise_deactivation_plan(
                deactivation_path,
                repo,
            )

            self.assertEqual(
                ".agents/skills/project-design/maestro-pack.json",
                result["preserved_pack_path"],
            )
            self.assertTrue(
                (repo / ".agents/skills/project-design/SKILL.md").is_file()
            )
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            self.assertEqual([], project["expertise"]["active_pack_paths"])
            route = route_goal_v2(
                "Review project typography",
                "medium",
                intent="review",
                repo_path=repo,
            )
            self.assertNotIn(
                "project-design",
                route["expertise"]["selected_pack_ids"],
            )

    def test_doctor_warns_until_active_expertise_is_in_the_git_index(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "project"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            apply_fresh_init(repo)
            _candidate(repo)
            activation = build_expertise_activation_plan(
                repo,
                candidate_id="project-design",
                approval_ref="owner_decision:issue-20",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_expertise_activation_plan(activation_path, repo)

            before = check_by_id(
                doctor_report(repo),
                "PROJECT_EXPERTISE_GIT_TRACKING",
            )
            self.assertEqual("WARN", before["status"])
            subprocess.run(
                [
                    "git",
                    "add",
                    "--",
                    ".agents/skills/project-design",
                    ".maestro/project.json",
                ],
                cwd=repo,
                check=True,
            )
            after = check_by_id(
                doctor_report(repo),
                "PROJECT_EXPERTISE_GIT_TRACKING",
            )
            self.assertEqual("PASS", after["status"])


if __name__ == "__main__":
    unittest.main()
