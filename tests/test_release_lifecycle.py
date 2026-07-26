from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import ROOT, check_by_id, write_json

from maestro import __version__
from maestro.doctor import doctor_report
from maestro.host import CODEX_SKILLS, host_installation_checks
from maestro.project import apply_plan, build_upgrade_plan
from maestro.release import (
    build_release_manifest,
    duplicate_skill_paths,
    load_source_release_manifest,
    validate_release_manifest,
)


class ReleaseIdentityTests(unittest.TestCase):
    def test_checked_in_release_manifest_matches_source_content(self) -> None:
        expected = build_release_manifest(ROOT)
        actual = load_source_release_manifest(ROOT)

        self.assertEqual(expected, actual)
        self.assertEqual(__version__, actual["framework_version"])
        self.assertEqual(set(CODEX_SKILLS), set(actual["skills"]))

    def test_release_manifest_rejects_content_tampering(self) -> None:
        manifest = build_release_manifest(ROOT)
        manifest["skills"]["maestro"]["sha256"] = "0" * 64

        self.assertIn(
            "release manifest release_id does not match its contents",
            validate_release_manifest(manifest),
        )

    def test_host_rejects_a_skill_changed_after_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "checkout"
            shutil.copytree(ROOT / "skills", checkout / "skills")
            manifest_path = (
                checkout / "src/maestro/resources/release-manifest.json"
            )
            write_json(manifest_path, load_source_release_manifest(ROOT))
            root_skill = checkout / "skills/maestro/SKILL.md"
            root_skill.write_text(
                root_skill.read_text(encoding="utf-8") + "\nUnreleased edit.\n",
                encoding="utf-8",
            )

            with (
                patch("maestro.host.shutil.which", return_value="/tools/maestro"),
                patch("maestro.host.metadata.version", return_value=__version__),
            ):
                checks = host_installation_checks(
                    "codex",
                    skill_root=checkout / "skills",
                )

            self.assertEqual(
                "FAIL",
                check_by_id(
                    {"checks": checks},
                    "HOST_SKILL_RELEASE_BINDING",
                )["status"],
            )

    def test_duplicate_visible_skill_names_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            roots = [root / "one", root / "two"]
            for skill_root in roots:
                skill_file = skill_root / "maestro/SKILL.md"
                skill_file.parent.mkdir(parents=True)
                skill_file.write_text("---\nname: maestro\n---\n", encoding="utf-8")

            duplicates = duplicate_skill_paths(roots)

            self.assertEqual(2, len(duplicates["maestro"]))


class PreviousReleaseUpgradeTests(unittest.TestCase):
    def test_v022_project_fixture_upgrades_and_becomes_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "legacy-project"
            shutil.copytree(
                ROOT / "tests/fixtures/project-v0.2.2",
                repo,
            )

            plan = build_upgrade_plan(repo)
            self.assertTrue(plan["operations"])
            plan_path = Path(temporary) / "upgrade.json"
            write_json(plan_path, plan)
            result = apply_plan(plan_path, repo, expected_command="upgrade")

            self.assertTrue(result["writes_performed"])
            lock = json.loads(
                (repo / ".maestro/lock.json").read_text(encoding="utf-8")
            )
            self.assertEqual(__version__, lock["framework"]["version"])
            self.assertEqual("PASS", doctor_report(repo)["status"])
            self.assertEqual([], build_upgrade_plan(repo)["operations"])


if __name__ == "__main__":
    unittest.main()
