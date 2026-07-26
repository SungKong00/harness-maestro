from __future__ import annotations

import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import ROOT, apply_fresh_init, check_by_id, write_json

from maestro import conventions as conventions_module
from maestro import __version__
from maestro.conventions import (
    apply_convention_draft_plan,
    apply_convention_lifecycle_plan,
    build_convention_activation_plan,
    build_convention_draft_plan,
    build_convention_update_plan,
)
from maestro.doctor import doctor_report
from maestro.decisions import repository_revision
from maestro.errors import MaestroError
from maestro.host import CODEX_SKILLS, host_installation_checks
from maestro.documents import select_documents
from maestro.util import canonical_json, sha256_text


class HostInstallationTests(unittest.TestCase):
    def test_codex_host_checks_cli_version_and_skill_wiring(self) -> None:
        with (
            patch("maestro.host.shutil.which", return_value="/tools/maestro"),
            patch("maestro.host.metadata.version", return_value=__version__),
        ):
            checks = host_installation_checks(
                "codex",
                skill_root=ROOT / "skills",
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
            self.assertEqual("FAIL", by_id["HOST_SKILL_RELEASE_BINDING"]["status"])
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

    def _held_out_evidence(
        self,
        repo: Path,
        convention: Path,
        evidence: Path,
    ) -> None:
        candidate = conventions_module._render_active_from_draft(
            convention.read_text(encoding="utf-8")
        )
        cases = [
            {
                "case_id": "positive-api",
                "category": "positive",
                "assertion": "API changes select the Convention.",
                "result": "passed",
                "critical": True,
                "evidence_ref": "case:positive-api",
            },
            {
                "case_id": "negative-batch",
                "category": "negative_scope",
                "assertion": "Batch-only changes do not apply the Convention.",
                "result": "passed",
                "critical": True,
                "evidence_ref": "case:negative-batch",
            },
            {
                "case_id": "regression-envelope",
                "category": "regression",
                "assertion": "The stable API envelope remains verifiable.",
                "result": "passed",
                "critical": True,
                "evidence_ref": "case:regression-envelope",
            },
        ]
        revision = repository_revision(repo)
        write_json(
            evidence,
            {
                "schema_version": (
                    "maestro_convention_held_out_evaluation_v1"
                ),
                "candidate_sha256": sha256_text(candidate),
                "suite_sha256": sha256_text(canonical_json(cases)),
                "source_revision": (
                    revision["head"]
                    if revision["kind"] == "git"
                    else "unavailable"
                ),
                "held_out": True,
                "cases": cases,
                "critical_regressions": 0,
                "verifier": {
                    "command": "python -m unittest tests.test_api_contract",
                    "exit_code": 0,
                    "executed_at": "2026-07-27T00:00:00Z",
                },
                "conditions": {
                    "tool": "unittest",
                    "model": None,
                    "budget": None,
                },
            },
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

    def test_activation_and_update_are_evidence_bound_transactions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            draft = self._plan(repo)
            draft_path = Path(temporary) / "draft.json"
            write_json(draft_path, draft)
            apply_convention_draft_plan(draft_path, repo)
            evidence = repo / "docs/evidence/api-contract.json"
            self._held_out_evidence(
                repo,
                repo / "docs/conventions/api-error-contract.md",
                evidence,
            )

            activation = build_convention_activation_plan(
                repo,
                topic="api-error-contract",
                basis="held_out_evaluation",
                approval_ref="held_out_evaluation:api-contract-v1",
                verification_artifact=(
                    "docs/evidence/api-contract.json"
                ),
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            result = apply_convention_lifecycle_plan(
                activation_path,
                repo,
            )

            target = repo / "docs/conventions/api-error-contract.md"
            self.assertEqual("convention-activate", result["command"])
            self.assertIn("status: active", target.read_text(encoding="utf-8"))
            self.assertIn(
                "(conventions/api-error-contract.md)",
                (repo / "docs/README.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                ["docs/conventions/api-error-contract.md"],
                select_documents(
                    repo,
                    "Change the API error contract",
                    [],
                )["selected_conventions"],
            )

            update = build_convention_update_plan(
                repo,
                topic="api-error-contract",
                summary="API errors use the versioned stable envelope.",
                scopes=["src/api"],
                owner="backend",
                rule="API handlers MUST return the versioned error envelope.",
                applies_when=["Changing an HTTP API handler."],
                does_not_apply=["Internal batch jobs."],
                evidence=["OpenAPI and held-out contract results."],
                verification=["python -m unittest tests.test_api_contract"],
                exceptions=["Owner-approved compatibility migrations."],
                basis="owner_decision",
                approval_ref="owner_decision:issue-42",
                verification_artifact=(
                    "docs/evidence/api-contract.json"
                ),
                decision_summary="Adopt the versioned envelope for HTTP APIs.",
            )
            update_path = Path(temporary) / "update.json"
            write_json(update_path, update)
            updated = apply_convention_lifecycle_plan(update_path, repo)
            self.assertEqual("convention-update", updated["command"])
            self.assertIn(
                "versioned error envelope",
                target.read_text(encoding="utf-8"),
            )

    def test_held_out_activation_rejects_an_opaque_pass_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            draft_path = Path(temporary) / "draft.json"
            write_json(draft_path, self._plan(repo))
            apply_convention_draft_plan(draft_path, repo)
            request = build_convention_activation_plan(
                repo,
                topic="api-error-contract",
                basis="held_out_evaluation",
                approval_ref=None,
                verification_artifact=None,
            )
            self.assertEqual(
                "maestro_convention_evaluation_request_v1",
                request["schema_version"],
            )
            self.assertEqual("evaluation_required", request["status"])
            self.assertRegex(request["candidate_sha256"], r"^[a-f0-9]{64}$")
            self.assertFalse(request["writes_performed"])
            evidence = repo / "docs/evidence/opaque.json"
            write_json(evidence, {"status": "pass", "held_out": True})

            with self.assertRaises(MaestroError) as invalid:
                build_convention_activation_plan(
                    repo,
                    topic="api-error-contract",
                    basis="held_out_evaluation",
                    approval_ref="held_out_evaluation:opaque",
                    verification_artifact="docs/evidence/opaque.json",
                )
            self.assertEqual(
                "CONVENTION_HELD_OUT_EVALUATION_INVALID",
                invalid.exception.code,
            )

    def test_update_rejects_unapproved_scope_expansion_and_stale_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            draft = self._plan(repo)
            draft_path = Path(temporary) / "draft.json"
            write_json(draft_path, draft)
            apply_convention_draft_plan(draft_path, repo)
            evidence = repo / "docs/evidence/api-contract.json"
            write_json(evidence, {"status": "pass"})
            activation = build_convention_activation_plan(
                repo,
                topic="api-error-contract",
                basis="owner_decision",
                approval_ref="owner_decision:issue-1",
                verification_artifact=(
                    "docs/evidence/api-contract.json"
                ),
                decision_summary="Activate the reviewed API rule.",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            apply_convention_lifecycle_plan(activation_path, repo)

            arguments = {
                "topic": "api-error-contract",
                "summary": "API error contract.",
                "scopes": ["src/api", "src/jobs"],
                "owner": "backend",
                "rule": "Use the stable envelope.",
                "applies_when": ["Changing APIs."],
                "does_not_apply": ["Unrelated UI."],
                "evidence": ["Contract evidence."],
                "verification": ["Run contract tests."],
                "exceptions": [],
                "basis": "owner_decision",
                "approval_ref": "owner_decision:issue-2",
                "verification_artifact": (
                    "docs/evidence/api-contract.json"
                ),
                "decision_summary": "Expand the rule after explicit review.",
            }
            with self.assertRaises(MaestroError) as expansion:
                build_convention_update_plan(repo, **arguments)
            self.assertEqual(
                "CONVENTION_SCOPE_EXPANSION_REQUIRES_APPROVAL",
                expansion.exception.code,
            )

            update = build_convention_update_plan(
                repo,
                **arguments,
                allow_scope_expansion=True,
            )
            update_path = Path(temporary) / "update.json"
            write_json(update_path, update)
            write_json(evidence, {"status": "changed"})
            with self.assertRaises(MaestroError) as stale:
                apply_convention_lifecycle_plan(update_path, repo)
            self.assertEqual("PLAN_STALE", stale.exception.code)

    def test_activation_rejects_a_changed_git_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            draft = self._plan(repo)
            draft_path = Path(temporary) / "draft.json"
            write_json(draft_path, draft)
            apply_convention_draft_plan(draft_path, repo)
            evidence = repo / "docs/evidence/api-contract.json"
            write_json(evidence, {"status": "pass"})
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "add", "."],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Maestro Test",
                    "-c",
                    "user.email=maestro@example.invalid",
                    "commit",
                    "-qm",
                    "baseline",
                ],
                check=True,
            )
            activation = build_convention_activation_plan(
                repo,
                topic="api-error-contract",
                basis="owner_decision",
                approval_ref="owner_decision:issue-3",
                verification_artifact=(
                    "docs/evidence/api-contract.json"
                ),
                decision_summary="Activate the reviewed API rule.",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            readme = repo / "docs/project.md"
            readme.write_text(
                readme.read_text(encoding="utf-8") + "\nChanged.\n",
                encoding="utf-8",
            )

            with self.assertRaises(MaestroError) as stale:
                apply_convention_lifecycle_plan(activation_path, repo)
            self.assertEqual("PLAN_STALE", stale.exception.code)

    def test_activation_rolls_back_both_files_after_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            draft = self._plan(repo)
            draft_path = Path(temporary) / "draft.json"
            write_json(draft_path, draft)
            apply_convention_draft_plan(draft_path, repo)
            evidence = repo / "docs/evidence/api-contract.json"
            write_json(evidence, {"status": "pass"})
            activation = build_convention_activation_plan(
                repo,
                topic="api-error-contract",
                basis="owner_decision",
                approval_ref="owner_decision:issue-4",
                verification_artifact=(
                    "docs/evidence/api-contract.json"
                ),
                decision_summary="Activate the reviewed API rule.",
            )
            activation_path = Path(temporary) / "activation.json"
            write_json(activation_path, activation)
            target = repo / "docs/conventions/api-error-contract.md"
            entrypoint = repo / "docs/README.md"
            before_target = target.read_bytes()
            before_entrypoint = entrypoint.read_bytes()
            real_atomic_write = conventions_module.atomic_write
            calls = 0

            def fail_second_write(path: Path, content: bytes) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated second write failure")
                real_atomic_write(path, content)

            with (
                patch(
                    "maestro.conventions.atomic_write",
                    side_effect=fail_second_write,
                ),
                self.assertRaises(OSError),
            ):
                apply_convention_lifecycle_plan(activation_path, repo)

            self.assertEqual(before_target, target.read_bytes())
            self.assertEqual(before_entrypoint, entrypoint.read_bytes())

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

    def test_doctor_warns_on_empty_future_or_unindexed_active_convention(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            convention = repo / "docs/conventions/incomplete.md"
            convention.parent.mkdir(parents=True)
            convention.write_text(
                "---\n"
                "maestro_doc: 1\n"
                "id: convention-incomplete\n"
                "type: convention\n"
                "status: active\n"
                "authority: repository\n"
                "owner: test\n"
                "summary: Incomplete active rule.\n"
                "topic: incomplete\n"
                "scope: [src]\n"
                "last_verified: 2999-01-01\n"
                "supersedes: []\n"
                "sensitivity: internal\n"
                "---\n\n"
                "# Convention: incomplete\n\n"
                "## Rule\n\n"
                "Use the rule.\n\n"
                "## Applies when\n\n"
                "- Source changes.\n\n"
                "## Does not apply\n\n"
                "- Documentation only.\n\n"
                "## Evidence\n\n"
                "- Current tests.\n\n"
                "## Verification\n\n"
                "\n"
                "## Exceptions\n\n"
                "- None.\n",
                encoding="utf-8",
            )

            check = check_by_id(
                doctor_report(repo),
                "CONVENTION_METADATA",
            )
            self.assertEqual("WARN", check["status"])
            self.assertIn("future", check["evidence"])
            self.assertIn("Verification", check["evidence"])
            self.assertIn("not reachable", check["evidence"])


if __name__ == "__main__":
    unittest.main()
