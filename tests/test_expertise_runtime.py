from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from tests.support import ROOT

from maestro.errors import MaestroError
from maestro.expertise import load_expertise_catalog
from maestro.expertise_runtime import load_assignment_expertise
from maestro.util import sha256_text


class ExpertiseRuntimeTests(unittest.TestCase):
    def _projection(self) -> dict[str, object]:
        pack = next(
            item
            for item in load_expertise_catalog(ROOT)
            if item["expertise_pack_id"] == "software-engineering"
        )
        metadata = pack["_maestro"]
        skill_id = pack["skill_id"]
        guide_id = "architecture-boundaries-and-tradeoffs"
        return {
            "expertise_load": {
                "application_mode": "authorized-executor-may-apply",
                "packs": [
                    {
                        "expertise_pack_id": pack[
                            "expertise_pack_id"
                        ],
                        "definition_digest": metadata[
                            "definition_digest"
                        ],
                        "skill_id": skill_id,
                        "skill_path": None,
                        "skill_definition_digest": metadata[
                            "skill_definition_digests"
                        ][skill_id],
                        "guides": [
                            {
                                "guide_id": guide_id,
                                "skill_id": skill_id,
                                "resource_path": (
                                    f"references/{guide_id}.md"
                                ),
                                "skill_definition_digest": metadata[
                                    "skill_definition_digests"
                                ][skill_id],
                            }
                        ],
                    }
                ],
            }
        }

    def test_host_loads_exact_skill_and_guide_with_attestation(self) -> None:
        loaded = load_assignment_expertise(
            ROOT,
            self._projection(),
        )
        self.assertEqual(
            "host_loaded",
            loaded["observation"]["load"]["status"],
        )
        self.assertTrue(
            loaded["observation"]["load"]["evidence_refs"][0].startswith(
                "expertise-load:"
            )
        )
        self.assertEqual(
            ["architecture-boundaries-and-tradeoffs"],
            loaded["observation"]["packs"][0]["guide_ids"],
        )
        self.assertIn(
            "skill_content",
            loaded["prompt_context"]["packs"][0],
        )
        guide_content = loaded["prompt_context"]["packs"][0][
            "guides"
        ][0]["content"]
        loaded_ref = loaded["observation"]["packs"][0][
            "loaded_guide_refs"
        ][0]
        self.assertEqual(
            sha256_text(guide_content),
            loaded_ref.rsplit(":", 1)[1],
        )

    def test_host_rejects_digest_drift_before_prompt_construction(self) -> None:
        projection = copy.deepcopy(self._projection())
        projection["expertise_load"]["packs"][0][
            "skill_definition_digest"
        ] = "0" * 64
        with self.assertRaises(MaestroError) as raised:
            load_assignment_expertise(ROOT, projection)
        self.assertEqual(
            "EXPERTISE_PROJECTION_MISMATCH",
            raised.exception.code,
        )

    def test_host_rejects_skill_tree_drift_during_prompt_construction(
        self,
    ) -> None:
        projection = self._projection()
        expected = projection["expertise_load"]["packs"][0][
            "skill_definition_digest"
        ]
        with patch(
            "maestro.expertise_runtime.skill_record",
            side_effect=[
                {"sha256": expected},
                {"sha256": "f" * 64},
            ],
        ):
            with self.assertRaises(MaestroError) as raised:
                load_assignment_expertise(ROOT, projection)
        self.assertEqual(
            "EXPERTISE_SKILL_DIGEST_MISMATCH",
            raised.exception.code,
        )


if __name__ == "__main__":
    unittest.main()
