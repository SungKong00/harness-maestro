from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import maestro.project as project_module
from tests.support import (
    apply_fresh_init,
    canonical_document,
    check_by_id,
    write_json,
)

from maestro.doctor import doctor_report
from maestro.errors import MaestroError
from maestro.project import (
    AGENTS_BEGIN,
    AGENTS_END,
    GITIGNORE_BEGIN,
    GITIGNORE_END,
    apply_plan,
    build_init_plan,
)
from maestro.util import canonical_json, file_sha256, safe_target, sha256_text


class InitSafetyTests(unittest.TestCase):
    def test_preview_is_read_only_and_apply_preserves_unmanaged_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            agents_before = "# Local agent rules\n\nKeep this exact rule.\n"
            ignore_before = "local-cache/\n"
            (repo / "AGENTS.md").write_text(agents_before, encoding="utf-8")
            (repo / ".gitignore").write_text(ignore_before, encoding="utf-8")

            plan = build_init_plan(repo)

            self.assertEqual(agents_before, (repo / "AGENTS.md").read_text())
            self.assertEqual(ignore_before, (repo / ".gitignore").read_text())
            self.assertFalse((repo / ".maestro").exists())
            self.assertTrue(plan["operations"])

            plan_path = Path(temporary) / "plan.json"
            write_json(plan_path, plan)
            result = apply_plan(plan_path, repo)

            self.assertTrue(result["writes_performed"])
            agents_after = (repo / "AGENTS.md").read_text(encoding="utf-8")
            ignore_after = (repo / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(agents_before.rstrip(), agents_after)
            self.assertIn(ignore_before.rstrip(), ignore_after)
            self.assertEqual(1, agents_after.count(AGENTS_BEGIN))
            self.assertEqual(1, agents_after.count(AGENTS_END))
            self.assertEqual(1, ignore_after.count(GITIGNORE_BEGIN))
            self.assertEqual(1, ignore_after.count(GITIGNORE_END))

    def test_init_is_idempotent_after_first_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            second_plan = build_init_plan(repo)

            self.assertEqual([], second_plan["operations"])
            second_plan_path = Path(temporary) / "second-plan.json"
            write_json(second_plan_path, second_plan)
            result = apply_plan(second_plan_path, repo)
            self.assertFalse(result["writes_performed"])
            self.assertEqual([], result["changed_paths"])

    def test_apply_rejects_stale_plan_without_partial_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / "AGENTS.md").write_text("# Existing\n", encoding="utf-8")
            plan = build_init_plan(repo)
            plan_path = Path(temporary) / "stale-plan.json"
            write_json(plan_path, plan)
            (repo / "AGENTS.md").write_text("# Changed later\n", encoding="utf-8")

            with self.assertRaises(MaestroError) as raised:
                apply_plan(plan_path, repo)

            self.assertEqual("PLAN_STALE", raised.exception.code)
            self.assertEqual(
                "# Changed later\n",
                (repo / "AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((repo / ".maestro").exists())

    def test_apply_rejects_plan_digest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            plan = build_init_plan(repo)
            tampered = copy.deepcopy(plan)
            tampered["operations"][0]["content"] += "\nunauthorized change\n"
            plan_path = Path(temporary) / "tampered-plan.json"
            write_json(plan_path, tampered)

            with self.assertRaises(MaestroError) as raised:
                apply_plan(plan_path, repo)

            self.assertEqual("PLAN_TAMPERED", raised.exception.code)
            self.assertFalse((repo / ".maestro").exists())

    def test_apply_rejects_an_allowlist_escape_even_with_valid_plan_digest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            plan = build_init_plan(repo)
            operation = plan["operations"][0]
            operation["path"] = "../outside.txt"
            operation["content"] = "escape"
            operation["before_sha256"] = None
            operation["after_sha256"] = sha256_text("escape")
            unsigned = {
                key: value
                for key, value in plan.items()
                if key not in {"plan_id", "plan_digest"}
            }
            digest = sha256_text(canonical_json(unsigned))
            plan["plan_id"] = digest[:20]
            plan["plan_digest"] = digest
            plan_path = Path(temporary) / "unsafe-plan.json"
            write_json(plan_path, plan)

            with self.assertRaises(MaestroError) as raised:
                apply_plan(plan_path, repo)

            self.assertEqual("PLAN_INVALID", raised.exception.code)
            self.assertFalse((Path(temporary) / "outside.txt").exists())

    def test_preview_rejects_a_managed_path_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            outside.mkdir()
            (outside / "AGENTS.md").write_text("# Outside\n", encoding="utf-8")
            (repo / "AGENTS.md").symlink_to(outside / "AGENTS.md")

            with self.assertRaises(MaestroError) as raised:
                build_init_plan(repo)

            self.assertEqual("PATH_ESCAPE", raised.exception.code)
            self.assertEqual(
                "# Outside\n",
                (outside / "AGENTS.md").read_text(encoding="utf-8"),
            )

    def test_safe_target_rejects_parent_absolute_and_directory_symlink_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            outside = root / "outside"
            repo.mkdir()
            outside.mkdir()
            (repo / "linked").symlink_to(outside, target_is_directory=True)

            for unsafe in ("../outside.txt", str(outside / "absolute.txt"), "linked/x"):
                with self.subTest(path=unsafe):
                    with self.assertRaises(MaestroError) as raised:
                        safe_target(repo, unsafe)
                    self.assertEqual("PATH_ESCAPE", raised.exception.code)

    def test_apply_failure_rolls_back_files_and_new_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            plan = build_init_plan(repo)
            plan_path = Path(temporary) / "plan.json"
            write_json(plan_path, plan)
            real_atomic_write = project_module.atomic_write

            def fail_on_lock(path: Path, content: bytes) -> None:
                if path.name == "lock.json":
                    raise OSError("injected failure")
                real_atomic_write(path, content)

            with mock.patch(
                "maestro.project.atomic_write",
                side_effect=fail_on_lock,
            ):
                with self.assertRaises(OSError):
                    apply_plan(plan_path, repo)

            self.assertFalse((repo / ".maestro").exists())
            self.assertFalse((repo / "docs").exists())
            self.assertFalse((repo / ".gitignore").exists())
            self.assertFalse((repo / "AGENTS.md").exists())

    def test_keyboard_interrupt_rolls_back_partial_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            plan = build_init_plan(repo)
            plan_path = Path(temporary) / "plan.json"
            write_json(plan_path, plan)
            real_atomic_write = project_module.atomic_write

            def interrupt_on_lock(path: Path, content: bytes) -> None:
                if path.name == "lock.json":
                    raise KeyboardInterrupt
                real_atomic_write(path, content)

            with mock.patch(
                "maestro.project.atomic_write",
                side_effect=interrupt_on_lock,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    apply_plan(plan_path, repo)

            self.assertFalse((repo / ".maestro").exists())
            self.assertFalse((repo / "docs").exists())
            self.assertFalse((repo / ".gitignore").exists())
            self.assertFalse((repo / "AGENTS.md").exists())

    def test_existing_manifest_is_normalized_by_a_reviewed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            managed_path = repo / ".maestro/managed.json"
            lock_path = repo / ".maestro/lock.json"
            managed = json.loads(managed_path.read_text(encoding="utf-8"))
            docs_entry = next(
                entry
                for entry in managed["entries"]
                if entry["path"] == "docs/README.md"
            )
            docs_entry["ownership"] = "managed_block"
            lifecycle_entry = next(
                entry
                for entry in managed["entries"]
                if entry["path"] == "docs/governance/document-lifecycle.md"
            )
            lifecycle_entry["preserve_on_drift"] = False
            lifecycle_entry["unexpected"] = "must be removed"
            write_json(managed_path, managed)
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["managed"]["sha256"] = file_sha256(managed_path)
            write_json(lock_path, lock)

            plan = build_init_plan(repo)

            self.assertIn(
                ".maestro/managed.json",
                [operation["path"] for operation in plan["operations"]],
            )
            plan_path = Path(temporary) / "repair-plan.json"
            write_json(plan_path, plan)
            apply_plan(plan_path, repo)
            self.assertEqual("PASS", doctor_report(repo)["status"])

    def test_checkout_identity_is_runtime_derived_not_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            first.mkdir()
            apply_fresh_init(first)
            shutil.copytree(first, second)

            first_project = json.loads(
                (first / ".maestro/project.json").read_text(encoding="utf-8")
            )
            second_project = json.loads(
                (second / ".maestro/project.json").read_text(encoding="utf-8")
            )

            self.assertNotIn("checkout_id", first_project)
            self.assertEqual(first_project, second_project)
            self.assertEqual([], build_init_plan(second)["operations"])

    def test_user_owned_document_drift_has_a_reviewed_acceptance_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            docs_index = repo / "docs/README.md"
            lifecycle = repo / "docs/governance/document-lifecycle.md"
            lifecycle.parent.mkdir(parents=True)
            docs_index.write_text(
                canonical_document("existing-docs-index"),
                encoding="utf-8",
            )
            lifecycle.write_text(
                canonical_document("existing-document-lifecycle"),
                encoding="utf-8",
            )
            apply_fresh_init(repo)
            docs_index.write_text(
                docs_index.read_text(encoding="utf-8") + "\nAccepted project note.\n",
                encoding="utf-8",
            )

            self.assertEqual("WARN", doctor_report(repo)["status"])
            plan = build_init_plan(repo)

            changed_paths = [operation["path"] for operation in plan["operations"]]
            self.assertEqual(
                [".maestro/lock.json", ".maestro/managed.json"],
                changed_paths,
            )
            self.assertIn(
                "user-owned document baseline will advance after review: docs/README.md",
                plan["warnings"],
            )
            plan_path = Path(temporary) / "accept-doc-plan.json"
            write_json(plan_path, plan)
            apply_plan(plan_path, repo)
            self.assertEqual("PASS", doctor_report(repo)["status"])

    def test_static_adapter_drift_updates_only_reviewed_project_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project_path = repo / ".maestro/project.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project["approval_required_for"].append("production_deploy")
            write_json(project_path, project)
            (repo / "package.json").write_text(
                json.dumps({"scripts": {"test": "node --test"}}),
                encoding="utf-8",
            )

            report = doctor_report(repo)
            self.assertEqual(
                "WARN",
                check_by_id(report, "ADAPTER_DRIFT")["status"],
            )
            plan = build_init_plan(repo)
            self.assertEqual(
                [".maestro/project.json"],
                [operation["path"] for operation in plan["operations"]],
            )
            plan_path = Path(temporary) / "adapter-plan.json"
            write_json(plan_path, plan)
            apply_plan(plan_path, repo)
            updated = json.loads(project_path.read_text(encoding="utf-8"))
            self.assertEqual(["node"], updated["profiles"])
            self.assertIn("production_deploy", updated["approval_required_for"])
            self.assertEqual([], build_init_plan(repo)["operations"])


class DoctorTests(unittest.TestCase):
    def test_fresh_initialization_passes_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)

            report = doctor_report(repo)

            self.assertEqual("PASS", report["status"])
            self.assertEqual(0, report["summary"]["fail"])
            self.assertFalse(report["writes_performed"])

    def test_managed_block_drift_is_a_failure_and_is_not_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            agents = repo / "AGENTS.md"
            changed = agents.read_text(encoding="utf-8").replace(
                "Default to one writer.",
                "Changed without a reviewed plan.",
            )
            agents.write_text(changed, encoding="utf-8")

            report = doctor_report(repo)

            check = check_by_id(report, "MANAGED:AGENTS.md")
            self.assertEqual("FAIL", check["status"])
            self.assertEqual(changed, agents.read_text(encoding="utf-8"))

    def test_harness_state_symlink_is_rejected_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project_path = repo / ".maestro/project.json"
            outside = root / "outside-project.json"
            project_path.replace(outside)
            project_path.symlink_to(outside)

            report = doctor_report(repo)

            self.assertEqual(
                "FAIL",
                check_by_id(report, "STATE_PATH_SAFETY")["status"],
            )

    def test_runtime_state_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            outside = root / "outside-state"
            repo.mkdir()
            outside.mkdir()
            apply_fresh_init(repo)
            (repo / ".maestro/state").symlink_to(
                outside,
                target_is_directory=True,
            )

            report = doctor_report(repo)

            self.assertEqual(
                "FAIL",
                check_by_id(report, "STATE_PATH_SAFETY")["status"],
            )

    def test_lock_adapter_must_match_registry_and_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            lock_path = repo / ".maestro/lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["adapters"][0]["version"] = 999
            write_json(lock_path, lock)

            report = doctor_report(repo)

            self.assertEqual(
                "FAIL",
                check_by_id(report, "ADAPTER_BINDINGS")["status"],
            )

    def test_core_managed_ownership_cannot_be_reclassified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            managed_path = repo / ".maestro/managed.json"
            lock_path = repo / ".maestro/lock.json"
            managed = json.loads(managed_path.read_text(encoding="utf-8"))
            agents_entry = next(
                entry
                for entry in managed["entries"]
                if entry["path"] == "AGENTS.md"
            )
            agents_entry["ownership"] = "user_owned"
            agents_entry["sha256"] = file_sha256(repo / "AGENTS.md")
            write_json(managed_path, managed)
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["managed"]["sha256"] = file_sha256(managed_path)
            write_json(lock_path, lock)

            report = doctor_report(repo)

            self.assertEqual(
                "FAIL",
                check_by_id(report, "MANAGED_SCHEMA")["status"],
            )

    def test_noncanonical_state_root_fails_and_init_previews_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project_path = repo / ".maestro/project.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project["state_root"] = "runtime-state"
            write_json(project_path, project)

            report = doctor_report(repo)
            plan = build_init_plan(repo)

            self.assertEqual(
                "FAIL",
                check_by_id(report, "PROJECT_SCHEMA")["status"],
            )
            project_operation = next(
                operation
                for operation in plan["operations"]
                if operation["path"] == ".maestro/project.json"
            )
            self.assertEqual(
                ".maestro/state",
                json.loads(project_operation["content"])["state_root"],
            )

    def test_seeded_document_drift_warns_instead_of_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            policy = repo / "docs/governance/document-lifecycle.md"
            changed = policy.read_text(encoding="utf-8") + "\nLocal clarification.\n"
            policy.write_text(changed, encoding="utf-8")

            report = doctor_report(repo)

            check = check_by_id(
                report,
                "MANAGED:docs/governance/document-lifecycle.md",
            )
            self.assertEqual("WARN", check["status"])
            self.assertEqual(changed, policy.read_text(encoding="utf-8"))

            plan = build_init_plan(repo)
            self.assertIn(
                "seeded document changed; review reclassification to user_owned: "
                "docs/governance/document-lifecycle.md",
                plan["warnings"],
            )
            self.assertNotIn(
                "docs/governance/document-lifecycle.md",
                [operation["path"] for operation in plan["operations"]],
            )
            plan_path = Path(temporary) / "accept-seeded-doc-plan.json"
            write_json(plan_path, plan)
            apply_plan(plan_path, repo)
            managed = json.loads(
                (repo / ".maestro/managed.json").read_text(encoding="utf-8")
            )
            entry = next(
                item
                for item in managed["entries"]
                if item["path"] == "docs/governance/document-lifecycle.md"
            )
            self.assertEqual("user_owned", entry["ownership"])
            self.assertEqual("PASS", doctor_report(repo)["status"])

    def test_active_document_without_frontmatter_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            path = repo / "docs/conventions/incomplete.md"
            path.parent.mkdir(parents=True)
            path.write_text("# Missing metadata\n", encoding="utf-8")

            report = doctor_report(repo)

            check = check_by_id(report, "DOC_FRONTMATTER")
            self.assertEqual("FAIL", check["status"])
            self.assertIn("docs/conventions/incomplete.md", check["evidence"])

    def test_empty_required_frontmatter_value_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            path = repo / "docs/conventions/empty-owner.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                canonical_document("empty-owner").replace(
                    "owner: test",
                    "owner:",
                ),
                encoding="utf-8",
            )

            report = doctor_report(repo)

            check = check_by_id(report, "DOC_FRONTMATTER")
            self.assertEqual("FAIL", check["status"])
            self.assertIn("owner", check["evidence"])

    def test_duplicate_active_document_ids_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            docs = repo / "docs/conventions"
            docs.mkdir(parents=True)
            (docs / "first.md").write_text(
                canonical_document("duplicate-topic"),
                encoding="utf-8",
            )
            (docs / "second.md").write_text(
                canonical_document("duplicate-topic"),
                encoding="utf-8",
            )

            report = doctor_report(repo)

            check = check_by_id(report, "DOC_DUPLICATE_ACTIVE")
            self.assertEqual("FAIL", check["status"])
            self.assertIn("duplicate-topic", check["evidence"])

    def test_broken_relative_document_link_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            path = repo / "docs/conventions/links.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                canonical_document(
                    "link-check",
                    body="# Links\n\n[Missing](does-not-exist.md)\n",
                ),
                encoding="utf-8",
            )

            report = doctor_report(repo)

            check = check_by_id(report, "DOC_LINKS")
            self.assertEqual("FAIL", check["status"])
            self.assertIn("does-not-exist.md", check["evidence"])

    def test_archived_documents_are_excluded_from_active_doc_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            path = repo / "docs/archive/old.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "# No frontmatter\n\n[Broken](missing.md)\n",
                encoding="utf-8",
            )

            report = doctor_report(repo)

            self.assertEqual("PASS", check_by_id(report, "DOC_FRONTMATTER")["status"])
            self.assertEqual("PASS", check_by_id(report, "DOC_LINKS")["status"])

    def test_invalid_nested_project_authority_fails_schema_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            project_path = repo / ".maestro/project.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project["documentation"]["default_authority"] = "not-valid"
            write_json(project_path, project)

            report = doctor_report(repo)

            self.assertEqual(
                "FAIL",
                check_by_id(report, "PROJECT_SCHEMA")["status"],
            )

    def test_invalid_managed_entry_contract_fails_schema_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            managed_path = repo / ".maestro/managed.json"
            managed = json.loads(managed_path.read_text(encoding="utf-8"))
            managed["entries"][0]["preserve_on_drift"] = False
            managed["entries"][0]["unexpected"] = True
            write_json(managed_path, managed)

            report = doctor_report(repo)

            self.assertEqual(
                "FAIL",
                check_by_id(report, "MANAGED_SCHEMA")["status"],
            )


if __name__ == "__main__":
    unittest.main()
