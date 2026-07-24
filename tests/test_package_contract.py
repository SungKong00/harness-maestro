from __future__ import annotations

import json
import re
import tomllib
import unittest
from importlib import resources

from maestro.project import AGENTS_BODY
from tests.support import ROOT


class PackageContractTests(unittest.TestCase):
    def test_runtime_resources_and_cli_entrypoint_are_declared(self) -> None:
        pyproject = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "maestro.cli:main",
            pyproject["project"]["scripts"]["maestro"],
        )
        self.assertIn(
            "resources/**/*.json",
            pyproject["tool"]["setuptools"]["package-data"]["maestro"],
        )

        resource_root = resources.files("maestro.resources")
        source_root = ROOT / "src" / "maestro" / "resources"
        expected = {
            item.relative_to(source_root).as_posix()
            for item in source_root.rglob("*.json")
        }
        self.assertGreater(len(expected), 20)
        for relative in expected:
            with self.subTest(resource=relative):
                item = resource_root.joinpath(relative)
                self.assertTrue(item.is_file(), relative)
                self.assertIsInstance(
                    json.loads(item.read_text(encoding="utf-8")),
                    dict,
                )

    def test_source_checkout_contains_valid_skill_references(self) -> None:
        for skill_root in sorted((ROOT / "skills").iterdir()):
            if not skill_root.is_dir():
                continue
            skill_file = skill_root / "SKILL.md"
            self.assertTrue(skill_file.is_file())
            text = skill_file.read_text(encoding="utf-8")
            for reference in set(
                re.findall(r"references/[A-Za-z0-9_.-]+\.md", text)
            ):
                self.assertTrue((skill_root / reference).is_file(), reference)

    def test_root_guidance_matches_generated_self_improvement_policy(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        architecture = (
            ROOT / "docs/architecture/maestro-v0.md"
        ).read_text(encoding="utf-8")

        self.assertIn(AGENTS_BODY, agents)
        self.assertIn("same-run reusable rules as candidates", AGENTS_BODY)
        self.assertIn("`owner_decision`", AGENTS_BODY)
        self.assertIn("`held_out_evaluation`", AGENTS_BODY)
        self.assertNotIn("같은 작업에서 갱신한다", architecture)
        self.assertIn("같은 실행에서는 candidate로만", architecture)

    def test_installation_uses_an_isolated_tool_environment(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("uv tool install --editable", readme)
        self.assertIn("command -v maestro", readme)
        self.assertIn("restart the agent client", readme)
        self.assertNotIn(
            "python3 -m pip install -e /path/to/harness-maestro",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
