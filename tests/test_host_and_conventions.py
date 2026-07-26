from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import apply_fresh_init, check_by_id, write_json

from maestro import __version__
from maestro.conventions import (
    apply_convention_draft_plan,
    build_convention_draft_plan,
)
from maestro.doctor import doctor_report
from maestro.errors import MaestroError
from maestro.host import CODEX_SKILLS, host_installation_checks
from maestro.documents import select_documents


class HostInstallationTests(unittest.TestCase):
    def test_codex_host_checks_cli_version_and_skill_wiring(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_root = Path(temporary) / "skills"
            for skill_id in CODEX_SKILLS:
                skill_file = skill_root / skill_id / "SKILL.md"
                skill_file.parent.mkdir(parents=True)
                skill_file.write_text(f"---\nname: {skill_id}\n---\n", encoding="utf-8")

            with (
                patch("maestro.host.shutil.which", return_value="/tools/maestro"),
                patch("maestro.host.metadata.version", return_value=__version__),
            ):
                checks = host_installation_checks(
                    "codex",
                    skill_root=skill_root,
                )

            self.assertTrue(all(item["status"] == "PASS" for item in checks))

    def test_codex_host_reports_missing_companions_and_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_root = Path(temporary) / "skills"
            root_skill = skill_root / "maestro/SKILL.md"
            root_skill.parent.mkdir(parents=True)
            root_skill.write_text("---\nname: maestro\n---\n", encoding="utf-8")

            with (
                patch("maestro.host.shutil.which", return_value="/tools/maestro"),
                patch("maestro.host.metadata.version", return_value="0.0.1"),
            ):
                checks = host_installation_checks(
                    "codex",
                    skill_root=skill_root,
                )

            by_id = {item["id"]: item for item in checks}
            self.assertEqual("WARN", by_id["HOST_CLI_VERSION"]["status"])
            self.assertEqual("PASS", by_id["HOST_ROOT_SKILL"]["status"])
            self.assertEqual("WARN", by_id["HOST_COMPANION_SKILLS"]["status"])
            self.assertIn("maestro-product-design", by_id["HOST_COMPANION_SKILLS"]["evidence"])


class ConventionDraftTests(unittest.TestCase):
    def _plan(self, repo: Path) -> dict:
        return build_convention_draft_plan(
            repo,
            topic="api-error-contract",
            summary="API error responses use one stable envelope.",
            scopes=["src/api"],
            owner="backend",
            rule="API handlers MUST return the documented error envelope.",
            applies_when=["Changing an HTTP API handler."],
            does_not_apply=["Internal batch jobs without an HTTP contract."],
            evidence=["Existing contract tests and the public OpenAPI schema."],
            verification=["python -m unittest tests.test_api_contract"],
            exceptions=["Owner-approved compatibility migrations."],
        )

    def test_preview_then_apply_creates_only_an_inactive_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            plan = self._plan(repo)
            target = repo / "docs/conventions/api-error-contract.md"
            self.assertFalse(plan["writes_performed"])
            self.assertFalse(target.exists())

            plan_path = Path(temporary) / "convention-plan.json"
            write_json(plan_path, plan)
            result = apply_convention_draft_plan(plan_path, repo)

            self.assertTrue(result["writes_performed"])
            self.assertTrue(target.is_file())
            self.assertIn("status: draft", target.read_text(encoding="utf-8"))
            self.assertNotIn(
                target.relative_to(repo).as_posix(),
                select_documents(repo, "API error response change", [])[
                    "selected_conventions"
                ],
            )
            report = doctor_report(repo)
            self.assertEqual("PASS", check_by_id(report, "CONVENTION_METADATA")["status"])

    def test_tampered_or_stale_draft_plan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            plan = self._plan(repo)
            tampered = copy.deepcopy(plan)
            tampered["operation"]["content"] += "\nUnreviewed change.\n"
            plan_path = Path(temporary) / "tampered.json"
            write_json(plan_path, tampered)

            with self.assertRaises(MaestroError) as raised:
                apply_convention_draft_plan(plan_path, repo)
            self.assertEqual("PLAN_TAMPERED", raised.exception.code)

            clean_path = Path(temporary) / "clean.json"
            write_json(clean_path, plan)
            target = repo / "docs/conventions/api-error-contract.md"
            target.parent.mkdir(parents=True)
            target.write_text("occupied", encoding="utf-8")
            with self.assertRaises(MaestroError) as stale:
                apply_convention_draft_plan(clean_path, repo)
            self.assertEqual("PLAN_STALE", stale.exception.code)

    def test_invalid_topic_and_scope_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            with self.assertRaises(MaestroError) as topic:
                build_convention_draft_plan(
                    repo,
                    topic="API Error",
                    summary="Summary",
                    scopes=["src/api"],
                    owner="backend",
                    rule="Rule",
                    applies_when=["API work"],
                    does_not_apply=["Batch work"],
                    evidence=["Test"],
                    verification=["pytest"],
                )
            self.assertEqual("CONVENTION_TOPIC_INVALID", topic.exception.code)

            with self.assertRaises(MaestroError) as scope:
                build_convention_draft_plan(
                    repo,
                    topic="api-error",
                    summary="Summary",
                    scopes=["../outside"],
                    owner="backend",
                    rule="Rule",
                    applies_when=["API work"],
                    does_not_apply=["Batch work"],
                    evidence=["Test"],
                    verification=["pytest"],
                )
            self.assertEqual("CONVENTION_SCOPE_INVALID", scope.exception.code)

    def test_doctor_warns_on_legacy_metadata_and_fails_duplicate_topics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            conventions = repo / "docs/conventions"
            conventions.mkdir(parents=True)
            legacy = conventions / "legacy.md"
            legacy.write_text(
                "---\n"
                "maestro_doc: 1\n"
                "id: legacy-rule\n"
                "type: convention\n"
                "status: active\n"
                "authority: repository\n"
                "owner: backend\n"
                "summary: Legacy rule without the extended metadata.\n"
                "---\n\n"
                "# Legacy\n",
                encoding="utf-8",
            )

            legacy_report = doctor_report(repo)
            self.assertEqual(
                "WARN",
                check_by_id(legacy_report, "CONVENTION_METADATA")["status"],
            )

            legacy.unlink()
            for name, doc_id in (("first", "first-rule"), ("second", "second-rule")):
                (conventions / f"{name}.md").write_text(
                    "---\n"
                    "maestro_doc: 1\n"
                    f"id: {doc_id}\n"
                    "type: convention\n"
                    "status: active\n"
                    "authority: repository\n"
                    "owner: backend\n"
                    f"summary: {name} authority.\n"
                    "topic: shared-topic\n"
                    "scope: [src/api]\n"
                    "last_verified: 2026-07-26\n"
                    "supersedes: []\n"
                    "sensitivity: internal\n"
                    "---\n\n"
                    f"# {name}\n",
                    encoding="utf-8",
                )

            duplicate_report = doctor_report(repo)
            self.assertEqual(
                "FAIL",
                check_by_id(
                    duplicate_report,
                    "CONVENTION_TOPIC_AUTHORITY",
                )["status"],
            )

    def test_doctor_rejects_unknown_supersession_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            convention = repo / "docs/conventions/replacement.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                "---\n"
                "maestro_doc: 1\n"
                "id: replacement-rule\n"
                "type: convention\n"
                "status: active\n"
                "authority: repository\n"
                "owner: backend\n"
                "summary: Replacement rule.\n"
                "topic: replacement-rule\n"
                "scope: [src/api]\n"
                "last_verified: 2026-07-26\n"
                "supersedes: [missing-rule]\n"
                "sensitivity: internal\n"
                "---\n\n"
                "# Replacement\n",
                encoding="utf-8",
            )

            report = doctor_report(repo)
            self.assertEqual(
                "FAIL",
                check_by_id(report, "CONVENTION_SUPERSESSION")["status"],
            )


if __name__ == "__main__":
    unittest.main()
