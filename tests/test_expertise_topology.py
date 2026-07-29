from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tests.support import apply_fresh_init, write_json

from maestro.expertise import (
    expertise_manifest_digest,
    load_expertise_catalog,
)
from maestro.expertise_topology import (
    expertise_candidate_content_digest,
    validate_candidate_change_semantics,
    validate_expertise_change_set_manifest,
)


COVERAGE_ID = "a" * 64
ADAPTATION_ID = "b" * 64


def _packs(repo: Path) -> dict[str, dict[str, object]]:
    return {
        pack["expertise_pack_id"]: copy.deepcopy(pack)
        for pack in load_expertise_catalog(
            repo,
            include_candidates=False,
        )
    }


def _member(
    repo: Path,
    *,
    candidate_id: str,
    operation: str,
    operation_id: str,
    role: str,
    pack: dict[str, object],
    source_pack_ids: list[str],
    target_pack_ids: list[str],
    target_guide_id: str | None = None,
    change_set_id: str = "topology-change",
) -> dict[str, object]:
    root = (
        repo
        / ".maestro/state/candidates/expertise"
        / candidate_id
    )
    pack = copy.deepcopy(pack)
    guide_ids = [
        guide["guide_id"]
        for guide in pack.get("guides", [])
    ]
    defaults = [
        guide_id
        for guide_id in pack.get("default_guides", [])
        if guide_id in guide_ids
    ]
    if not defaults and guide_ids:
        defaults = [guide_ids[0]]
    pack["default_guides"] = defaults
    write_json(
        root / "candidate.json",
        {
            "generation": {
                "mode": "task-gap",
                "signal_fingerprint": "0" * 24,
            },
            "component_change": {
                "kind": operation,
                "target_guide_id": target_guide_id,
                "source_pack_ids": source_pack_ids,
                "target_pack_ids": target_pack_ids,
                "change_set_id": change_set_id,
                "operation_id": operation_id,
                "operation_role": role,
            },
            "adaptation": {
                "coverage_ref": {
                    "path": "evidence/task-coverage.json",
                    "sha256": "0" * 64,
                },
                "plan_ref": {
                    "path": "evidence/adaptation-plan.json",
                    "sha256": "0" * 64,
                },
            },
        },
    )
    write_json(root / "draft/maestro-pack.json", pack)
    active = _packs(repo)
    source_root = Path(__file__).resolve().parents[1]
    for guide_id in guide_ids:
        source_pack = next(
            current
            for current in active.values()
            if guide_id
            in {
                guide["guide_id"]
                for guide in current.get("guides", [])
            }
        )
        source_path = (
            source_root
            / "skills"
            / source_pack["skill_id"]
            / "references"
            / f"{guide_id}.md"
        )
        (root / "draft/references").mkdir(
            parents=True,
            exist_ok=True,
        )
        (root / "draft/references" / f"{guide_id}.md").write_text(
            source_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    write_json(
        root / "evidence/task-coverage.json",
        {"coverage_id": COVERAGE_ID},
    )
    write_json(
        root / "evidence/adaptation-plan.json",
        {"plan_id": ADAPTATION_ID},
    )
    return {
        "candidate_id": candidate_id,
        "operation_id": operation_id,
        "role": role,
        "candidate_digest": expertise_candidate_content_digest(root),
    }


def _source(pack: dict[str, object]) -> dict[str, object]:
    return {
        "pack_id": pack["expertise_pack_id"],
        "definition_digest": expertise_manifest_digest(pack),
    }


def _manifest(
    repo: Path,
    *,
    operation: str,
    members: list[dict[str, object]],
    sources: list[dict[str, object]],
    mappings: list[dict[str, object]],
    retirement: str,
    change_set_id: str = "topology-change",
) -> Path:
    path = (
        repo
        / ".maestro/state/candidates/expertise-change-sets"
        / f"{change_set_id}.json"
    )
    default_guides = []
    for member in members:
        candidate_pack = json.loads(
            (
                repo
                / ".maestro/state/candidates/expertise"
                / member["candidate_id"]
                / "draft/maestro-pack.json"
            ).read_text(encoding="utf-8")
        )
        default_guides.append(
            {
                "pack_id": candidate_pack["expertise_pack_id"],
                "guide_ids": candidate_pack["default_guides"],
            }
        )
    write_json(
        path,
        {
            "schema_version": "maestro_expertise_change_set_manifest_v1",
            "change_set_id": change_set_id,
            "operation": operation,
            "coverage_id": COVERAGE_ID,
            "adaptation_plan_id": ADAPTATION_ID,
            "members": members,
            "sources": sources,
            "guide_mappings": mappings,
            "default_guides": default_guides,
            "source_retirement": retirement,
            "rollback_summary": "Archive every member and restore the prior project allowlist.",
        },
    )
    return path


class ExpertiseTopologyTests(unittest.TestCase):
    def test_non_list_manifest_fields_return_typed_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            path = (
                repo
                / ".maestro/state/candidates/expertise-change-sets/"
                "malformed-change.json"
            )
            write_json(
                path,
                {
                    "schema_version": (
                        "maestro_expertise_change_set_manifest_v1"
                    ),
                    "change_set_id": "malformed-change",
                    "operation": "guide-copy",
                    "coverage_id": COVERAGE_ID,
                    "adaptation_plan_id": ADAPTATION_ID,
                    "members": 7,
                    "sources": 7,
                    "guide_mappings": 7,
                    "default_guides": 7,
                    "source_retirement": "not-applicable",
                    "rollback_summary": "Restore the prior topology.",
                },
            )

            result = validate_expertise_change_set_manifest(
                repo,
                "malformed-change",
            )
            self.assertEqual("FAIL", result["status"])
            self.assertIn(
                "EXPERTISE_CHANGE_SET_MANIFEST_CARDINALITY_INVALID",
                {issue["code"] for issue in result["issues"]},
            )

    def test_guide_revision_and_deprecation_reject_unrelated_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            base = _packs(repo)["product-design"]
            target = base["guides"][0]["guide_id"]
            revision = copy.deepcopy(base)
            revision["guides"][0]["summary"] += " Revised."
            candidate = {
                "expertise_pack_id": "product-design",
                "generation": {"mode": "task-gap"},
                "component_change": {
                    "kind": "guide-revision",
                    "target_guide_id": target,
                },
            }

            passed = validate_candidate_change_semantics(
                repo,
                candidate,
                revision,
            )
            revision["guides"][1]["summary"] += " Undeclared."
            failed = validate_candidate_change_semantics(
                repo,
                candidate,
                revision,
            )

            self.assertEqual([], passed)
            self.assertIn(
                "EXPERTISE_GUIDE_CHANGE_UNDECLARED_DRIFT",
                {issue["code"] for issue in failed},
            )

            deprecation = copy.deepcopy(base)
            deprecation["guides"] = [
                guide
                for guide in deprecation["guides"]
                if guide["guide_id"] != target
            ]
            deprecation["default_guides"] = [
                guide_id
                for guide_id in deprecation["default_guides"]
                if guide_id != target
            ]
            candidate["component_change"]["kind"] = "guide-deprecation"
            self.assertEqual(
                [],
                validate_candidate_change_semantics(
                    repo,
                    candidate,
                    deprecation,
                ),
            )
            deprecation["guides"].pop()
            failed = validate_candidate_change_semantics(
                repo,
                candidate,
                deprecation,
            )
            self.assertIn(
                "EXPERTISE_GUIDE_DEPRECATION_SCOPE_INVALID",
                {issue["code"] for issue in failed},
            )

    def test_guide_copy_and_move_validate_before_after_topology(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            base = _packs(repo)["product-design"]
            guide = copy.deepcopy(base["guides"][0])
            guide_id = guide["guide_id"]

            copy_target = {
                "expertise_pack_id": "copied-design",
                "guides": [guide],
            }
            member = _member(
                repo,
                candidate_id="copy-target",
                operation="guide-copy",
                operation_id="copy-guide",
                role="target",
                pack=copy_target,
                source_pack_ids=["product-design"],
                target_pack_ids=["copied-design"],
                target_guide_id=guide_id,
                change_set_id="copy-change",
            )
            manifest = _manifest(
                repo,
                operation="guide-copy",
                members=[member],
                sources=[_source(base)],
                mappings=[
                    {
                        "guide_id": guide_id,
                        "source_pack_id": "product-design",
                        "target_pack_ids": ["copied-design"],
                        "mode": "copy",
                    }
                ],
                retirement="not-applicable",
                change_set_id="copy-change",
            )
            self.assertEqual(
                "PASS",
                validate_expertise_change_set_manifest(
                    repo,
                    "copy-change",
                )["status"],
            )
            target_path = (
                repo
                / ".maestro/state/candidates/expertise/copy-target"
                / "draft/maestro-pack.json"
            )
            changed = json.loads(target_path.read_text(encoding="utf-8"))
            changed["guides"][0]["summary"] = "Not the copied Guide."
            write_json(target_path, changed)
            manifest_value = json.loads(
                manifest.read_text(encoding="utf-8")
            )
            manifest_value["members"][0][
                "candidate_digest"
            ] = expertise_candidate_content_digest(target_path.parents[1])
            write_json(manifest, manifest_value)
            failed = validate_expertise_change_set_manifest(
                repo,
                "copy-change",
            )
            self.assertIn(
                "EXPERTISE_GUIDE_COPY_TOPOLOGY_INVALID",
                {issue["code"] for issue in failed["issues"]},
            )

            # Use a separate ChangeSet to prove that move includes source removal.
            source_after = copy.deepcopy(base)
            source_after["guides"] = source_after["guides"][1:]
            move_target = {
                "expertise_pack_id": "moved-design",
                "guides": [guide],
            }
            source_member = _member(
                repo,
                candidate_id="move-source",
                operation="guide-move",
                operation_id="remove-guide",
                role="source",
                pack=source_after,
                source_pack_ids=["product-design"],
                target_pack_ids=["moved-design"],
                target_guide_id=guide_id,
                change_set_id="move-change",
            )
            target_member = _member(
                repo,
                candidate_id="move-target",
                operation="guide-move",
                operation_id="add-guide",
                role="target",
                pack=move_target,
                source_pack_ids=["product-design"],
                target_pack_ids=["moved-design"],
                target_guide_id=guide_id,
                change_set_id="move-change",
            )
            _manifest(
                repo,
                operation="guide-move",
                members=[source_member, target_member],
                sources=[_source(base)],
                mappings=[
                    {
                        "guide_id": guide_id,
                        "source_pack_id": "product-design",
                        "target_pack_ids": ["moved-design"],
                        "mode": "move",
                    }
                ],
                retirement="represented-by-members",
                change_set_id="move-change",
            )
            self.assertEqual(
                "PASS",
                validate_expertise_change_set_manifest(
                    repo,
                    "move-change",
                )["status"],
            )

    def test_pack_split_preserves_every_guide_and_merge_preserves_union(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            packs = _packs(repo)
            source = packs["product-design"]
            source_guides = copy.deepcopy(source["guides"])
            remainder = copy.deepcopy(source)
            remainder["guides"] = [source_guides[0]]
            left_guides = source_guides[1::2]
            right_guides = source_guides[2::2]
            members = [
                _member(
                    repo,
                    candidate_id="split-source",
                    operation="pack-split",
                    operation_id="retain-source",
                    role="source",
                    pack=remainder,
                    source_pack_ids=["product-design"],
                    target_pack_ids=["split-left", "split-right"],
                    change_set_id="split-change",
                ),
                _member(
                    repo,
                    candidate_id="split-left",
                    operation="pack-split",
                    operation_id="create-left",
                    role="target",
                    pack={
                        "expertise_pack_id": "split-left",
                        "guides": left_guides,
                    },
                    source_pack_ids=["product-design"],
                    target_pack_ids=["split-left", "split-right"],
                    change_set_id="split-change",
                ),
                _member(
                    repo,
                    candidate_id="split-right",
                    operation="pack-split",
                    operation_id="create-right",
                    role="target",
                    pack={
                        "expertise_pack_id": "split-right",
                        "guides": right_guides,
                    },
                    source_pack_ids=["product-design"],
                    target_pack_ids=["split-left", "split-right"],
                    change_set_id="split-change",
                ),
            ]
            mappings = [
                {
                    "guide_id": guide["guide_id"],
                    "source_pack_id": "product-design",
                    "target_pack_ids": [
                        "split-left"
                        if guide in left_guides
                        else "split-right"
                    ],
                    "mode": "move",
                }
                for guide in source_guides[1:]
            ]
            _manifest(
                repo,
                operation="pack-split",
                members=members,
                sources=[_source(source)],
                mappings=mappings,
                retirement="represented-by-members",
                change_set_id="split-change",
            )
            self.assertEqual(
                "PASS",
                validate_expertise_change_set_manifest(
                    repo,
                    "split-change",
                )["status"],
            )

            marketing = packs["marketing"]
            union_guides = [
                *copy.deepcopy(source["guides"]),
                *copy.deepcopy(marketing["guides"]),
            ]
            result_pack = {
                "expertise_pack_id": "merged-expertise",
                "guides": union_guides,
            }
            result_member = _member(
                repo,
                candidate_id="merge-result",
                operation="pack-merge",
                operation_id="create-merge",
                role="result",
                pack=result_pack,
                source_pack_ids=["product-design", "marketing"],
                target_pack_ids=[],
                change_set_id="merge-change",
            )
            merge_mappings = [
                {
                    "guide_id": guide["guide_id"],
                    "source_pack_id": pack_id,
                    "target_pack_ids": ["merged-expertise"],
                    "mode": "consolidate",
                }
                for pack_id, pack in (
                    ("product-design", source),
                    ("marketing", marketing),
                )
                for guide in pack["guides"]
            ]
            _manifest(
                repo,
                operation="pack-merge",
                members=[result_member],
                sources=[_source(source), _source(marketing)],
                mappings=merge_mappings,
                retirement="deferred-owner-action",
                change_set_id="merge-change",
            )
            merge = validate_expertise_change_set_manifest(
                repo,
                "merge-change",
            )
            self.assertEqual("PASS", merge["status"])

    def test_pack_extraction_copies_exact_subset_from_every_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            apply_fresh_init(repo)
            packs = _packs(repo)
            source_pairs = [
                (
                    "product-design",
                    packs["product-design"],
                    copy.deepcopy(packs["product-design"]["guides"][0]),
                ),
                (
                    "software-engineering",
                    packs["software-engineering"],
                    copy.deepcopy(
                        packs["software-engineering"]["guides"][0]
                    ),
                ),
            ]
            result_id = "delivery-interface"
            member = _member(
                repo,
                candidate_id="extraction-result",
                operation="pack-extraction",
                operation_id="create-extraction",
                role="result",
                pack={
                    "expertise_pack_id": result_id,
                    "guides": [
                        guide
                        for _pack_id, _pack, guide in source_pairs
                    ],
                },
                source_pack_ids=[
                    pack_id
                    for pack_id, _pack, _guide in source_pairs
                ],
                target_pack_ids=[],
                change_set_id="extraction-change",
            )
            manifest = _manifest(
                repo,
                operation="pack-extraction",
                members=[member],
                sources=[
                    _source(pack)
                    for _pack_id, pack, _guide in source_pairs
                ],
                mappings=[
                    {
                        "guide_id": guide["guide_id"],
                        "source_pack_id": pack_id,
                        "target_pack_ids": [result_id],
                        "mode": "copy",
                    }
                    for pack_id, _pack, guide in source_pairs
                ],
                retirement="not-applicable",
                change_set_id="extraction-change",
            )

            passed = validate_expertise_change_set_manifest(
                repo,
                "extraction-change",
            )
            self.assertEqual("PASS", passed["status"])

            candidate_root = (
                repo
                / ".maestro/state/candidates/expertise"
                / "extraction-result"
            )
            reference_path = (
                candidate_root
                / "draft/references"
                / f"{source_pairs[0][2]['guide_id']}.md"
            )
            original_reference = reference_path.read_text(encoding="utf-8")
            reference_path.write_text(
                original_reference + "\nChanged extraction body.\n",
                encoding="utf-8",
            )
            manifest_value = json.loads(
                manifest.read_text(encoding="utf-8")
            )
            manifest_value["members"][0][
                "candidate_digest"
            ] = expertise_candidate_content_digest(candidate_root)
            write_json(manifest, manifest_value)
            body_failed = validate_expertise_change_set_manifest(
                repo,
                "extraction-change",
            )
            self.assertIn(
                "EXPERTISE_CHANGE_SET_GUIDE_CONTENT_MISMATCH",
                {issue["code"] for issue in body_failed["issues"]},
            )
            reference_path.write_text(
                original_reference,
                encoding="utf-8",
            )

            result_path = (
                candidate_root / "draft/maestro-pack.json"
            )
            changed = json.loads(result_path.read_text(encoding="utf-8"))
            changed["guides"].append(
                copy.deepcopy(packs["product-design"]["guides"][1])
            )
            write_json(result_path, changed)
            manifest_value = json.loads(
                manifest.read_text(encoding="utf-8")
            )
            manifest_value["members"][0][
                "candidate_digest"
            ] = expertise_candidate_content_digest(result_path.parents[1])
            manifest_value["default_guides"][0]["guide_ids"] = (
                changed["default_guides"]
            )
            write_json(manifest, manifest_value)

            failed = validate_expertise_change_set_manifest(
                repo,
                "extraction-change",
            )
            self.assertIn(
                "EXPERTISE_PACK_EXTRACTION_TOPOLOGY_INVALID",
                {issue["code"] for issue in failed["issues"]},
            )


if __name__ == "__main__":
    unittest.main()
