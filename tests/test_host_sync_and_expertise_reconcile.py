from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.support import ROOT, write_json

from maestro.expertise_reconcile import (
    apply_expertise_reconcile_plan,
    build_expertise_reconcile_plan,
)
from maestro.expertise import project_expertise_storage_status
from maestro.host import apply_host_sync_plan, build_host_sync_plan


class HostSyncTests(unittest.TestCase):
    def test_sync_creates_only_missing_release_bound_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_root = Path(temporary) / "skills"
            plan = build_host_sync_plan(
                "codex",
                ROOT,
                skill_root=skill_root,
            )

            self.assertFalse(plan["writes_performed"])
            self.assertFalse(plan["conflicts"])
            result = apply_host_sync_plan(plan)

            self.assertTrue(result["writes_performed"])
            self.assertTrue(
                (skill_root / "maestro").is_symlink()
            )
            self.assertEqual(
                (ROOT / "skills/maestro").resolve(),
                (skill_root / "maestro").resolve(),
            )
            second = build_host_sync_plan(
                "codex",
                ROOT,
                skill_root=skill_root,
            )
            self.assertEqual([], second["links"])

    def test_sync_reports_existing_path_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_root = Path(temporary) / "skills"
            target = skill_root / "maestro"
            target.mkdir(parents=True)
            marker = target / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            plan = build_host_sync_plan(
                "codex",
                ROOT,
                skill_root=skill_root,
            )

            self.assertTrue(plan["conflicts"])
            with self.assertRaisesRegex(Exception, "existing Host Skill"):
                apply_host_sync_plan(plan)
            self.assertEqual("keep", marker.read_text(encoding="utf-8"))


class ExpertiseReconcileTests(unittest.TestCase):
    def _harness_project(self, root: Path) -> Path:
        repo = root / "repo"
        (repo / ".maestro").mkdir(parents=True)
        shutil.copytree(
            ROOT / "src/maestro/resources",
            repo / "src/maestro/resources",
        )
        global_skill = ROOT / "skills/maestro-data-engineering"
        shutil.copytree(
            global_skill,
            repo / "skills/maestro-data-engineering",
        )
        local_skill = repo / ".agents/skills/maestro-data-engineering"
        shutil.copytree(global_skill, local_skill)
        pack = json.loads(
            (
                ROOT
                / "src/maestro/resources/registry/expertise-packs/"
                "data-engineering.json"
            ).read_text(encoding="utf-8")
        )
        pack["portability"] = "project"
        write_json(local_skill / "maestro-pack.json", pack)
        write_json(local_skill / "activation.json", {"candidate_id": "data"})
        write_json(
            repo / ".maestro/project.json",
            {
                "expertise": {
                    "active_pack_paths": [
                        (
                            ".agents/skills/maestro-data-engineering/"
                            "maestro-pack.json"
                        )
                    ]
                }
            },
        )
        return repo

    def test_exact_global_successor_moves_out_of_host_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._harness_project(Path(temporary))
            plan = build_expertise_reconcile_plan(repo)

            self.assertEqual(1, len(plan["moves"]))
            self.assertEqual("globally-superseded", plan["moves"][0]["reason"])
            self.assertEqual(
                "data-engineering",
                project_expertise_storage_status(repo)[
                    "globally_superseded"
                ][0]["expertise_pack_id"],
            )
            result = apply_expertise_reconcile_plan(plan, repo)

            self.assertFalse(
                (repo / ".agents/skills/maestro-data-engineering").exists()
            )
            self.assertTrue(
                (repo / result["archived"][0]["archive_path"]).is_dir()
            )
            project = json.loads(
                (repo / ".maestro/project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [],
                project["expertise"]["active_pack_paths"],
            )

    def test_different_active_content_is_never_moved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._harness_project(Path(temporary))
            skill = (
                repo
                / ".agents/skills/maestro-data-engineering/SKILL.md"
            )
            skill.write_text(
                skill.read_text(encoding="utf-8") + "\nProject rule.\n",
                encoding="utf-8",
            )

            plan = build_expertise_reconcile_plan(repo)

            self.assertEqual([], plan["moves"])
            self.assertEqual(
                "data-engineering",
                project_expertise_storage_status(repo)[
                    "active_conflicts"
                ][0]["expertise_pack_id"],
            )
            self.assertEqual(
                "active-content-differs-from-global",
                plan["conflicts"][0]["reason"],
            )
            with self.assertRaisesRegex(Exception, "decision"):
                apply_expertise_reconcile_plan(plan, repo)
            self.assertTrue(skill.is_file())

    def test_global_skill_id_prefix_is_a_safe_canonical_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = self._harness_project(Path(temporary))
            original = repo / ".agents/skills/maestro-data-engineering"
            local = repo / ".agents/skills/data-engineering"
            original.rename(local)
            pack_path = local / "maestro-pack.json"
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            pack["skill_id"] = "data-engineering"
            write_json(pack_path, pack)
            skill = local / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "name: maestro-data-engineering",
                    "name: data-engineering",
                    1,
                ),
                encoding="utf-8",
            )
            policy = local / "agents/openai.yaml"
            policy.write_text(
                policy.read_text(encoding="utf-8").replace(
                    "$maestro-data-engineering",
                    "$data-engineering",
                ),
                encoding="utf-8",
            )
            project_path = repo / ".maestro/project.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project["expertise"]["active_pack_paths"] = [
                ".agents/skills/data-engineering/maestro-pack.json"
            ]
            write_json(project_path, project)

            plan = build_expertise_reconcile_plan(repo)

            self.assertEqual([], plan["conflicts"])
            self.assertEqual("globally-superseded", plan["moves"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
