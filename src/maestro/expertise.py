from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .matching import searchable_terms, term_matches
from .registry import load_registry, validate_registry
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    read_json,
    safe_target,
    sha256_text,
)


DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
MAX_SELECTED_PACKS = 1
MAX_SELECTED_GUIDES = 4
DISCOVERY_TRIGGERS = (
    "expert criteria",
    "expert workflow",
    "specialist workflow",
    "expertise pack",
    "specialist skill",
    "best practice",
    "technology stack",
    "architecture choice",
    "전문가 기준",
    "전문가 작업 방식",
    "전문가 워크플로우",
    "전문성 팩",
    "전문가 스킬",
    "모범 사례",
    "기술 스택",
    "아키텍처 선택",
    "큰 방향",
)
PROJECT_PACK_FILENAME = "maestro-pack.json"
PROJECT_PACK_ROOT = (".agents", "skills")
MAX_PROJECT_PACK_FILES = 64
MAX_PROJECT_PACK_FILE_BYTES = 2_000_000


def expertise_manifest_digest(pack: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in pack.items()
        if key != "_maestro"
    }
    return sha256_text(canonical_json(payload))


def _project_pack_paths(repo: Path) -> list[str]:
    project_path = safe_target(repo, ".maestro/project.json")
    if not project_path.exists():
        return []
    project = read_json(project_path)
    configuration = project.get("expertise")
    if configuration is None:
        return []
    if (
        not isinstance(configuration, dict)
        or set(configuration) != {"active_pack_paths"}
        or not isinstance(configuration["active_pack_paths"], list)
        or len(configuration["active_pack_paths"])
        != len(set(configuration["active_pack_paths"]))
        or any(
            not isinstance(item, str) or not item.strip()
            for item in configuration["active_pack_paths"]
        )
    ):
        raise MaestroError(
            "PROJECT_EXPERTISE_CONFIG_INVALID",
            "project.json expertise must contain one unique active_pack_paths list.",
        )
    return configuration["active_pack_paths"]


def _project_pack_target(repo: Path, relative_path: str) -> tuple[Path, str]:
    if "\\" in relative_path:
        raise MaestroError(
            "PROJECT_EXPERTISE_PATH_INVALID",
            f"Expertise Pack path must use repository POSIX separators: {relative_path}",
        )
    parts = Path(relative_path).parts
    if (
        len(parts) != 4
        or parts[:2] != PROJECT_PACK_ROOT
        or parts[3] != PROJECT_PACK_FILENAME
        or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", parts[2]) is None
    ):
        raise MaestroError(
            "PROJECT_EXPERTISE_PATH_INVALID",
            "Active project Expertise Packs must use "
            ".agents/skills/<skill-id>/maestro-pack.json.",
        )
    return safe_target(repo, relative_path), parts[2]


def _skill_tree_digest(skill_root: Path) -> str:
    files: list[dict[str, str]] = []
    for path in sorted(skill_root.rglob("*")):
        if path.is_symlink():
            raise MaestroError(
                "PROJECT_EXPERTISE_SYMLINK",
                f"Project Expertise may not contain symlinks: {path}",
            )
        if not path.is_file():
            continue
        if len(files) >= MAX_PROJECT_PACK_FILES:
            raise MaestroError(
                "PROJECT_EXPERTISE_TOO_LARGE",
                f"Project Expertise exceeds {MAX_PROJECT_PACK_FILES} files: {skill_root}",
            )
        if path.stat().st_size > MAX_PROJECT_PACK_FILE_BYTES:
            raise MaestroError(
                "PROJECT_EXPERTISE_FILE_TOO_LARGE",
                f"Project Expertise file exceeds {MAX_PROJECT_PACK_FILE_BYTES} bytes: {path}",
            )
        digest = file_sha256(path)
        if digest is None:
            raise MaestroError(
                "PROJECT_EXPERTISE_FILE_MISSING",
                f"Project Expertise file disappeared during inspection: {path}",
            )
        files.append(
            {
                "path": path.relative_to(skill_root).as_posix(),
                "sha256": digest,
            }
        )
    return sha256_text(canonical_json(files))


def _required_pack_file(skill_root: Path, relative_path: str) -> Path:
    target = safe_target(skill_root, relative_path)
    if target.is_symlink() or not target.is_file():
        raise MaestroError(
            "PROJECT_EXPERTISE_FILE_MISSING",
            f"Project Expertise requires a regular file: {target}",
        )
    return target


def _load_project_packs(
    repo: Path,
    bundled_registry: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    bundled_by_id = {
        pack["expertise_pack_id"]: pack
        for pack in bundled_registry["expertise_packs"]
    }
    raw_packs: list[tuple[dict[str, Any], str, Path]] = []
    for relative_path in _project_pack_paths(repo):
        target, skill_id = _project_pack_target(repo, relative_path)
        if target.is_symlink() or not target.is_file():
            raise MaestroError(
                "PROJECT_EXPERTISE_FILE_MISSING",
                f"Enabled project Expertise Pack is missing: {relative_path}",
            )
        pack = read_json(target)
        if pack.get("skill_id") != skill_id:
            raise MaestroError(
                "PROJECT_EXPERTISE_SKILL_MISMATCH",
                f"{relative_path} skill_id must match its directory name.",
            )
        raw_packs.append((pack, relative_path, target.parent))

    combined = copy.deepcopy(bundled_registry)
    combined["expertise_packs"].extend(pack for pack, _, _ in raw_packs)
    errors = validate_registry(combined)
    if errors:
        raise MaestroError("PROJECT_EXPERTISE_INVALID", "; ".join(errors))

    result: list[dict[str, Any]] = []
    for pack, relative_path, skill_root in raw_packs:
        pack_id = pack["expertise_pack_id"]
        if pack["portability"] != "project":
            raise MaestroError(
                "PROJECT_EXPERTISE_SCOPE_INVALID",
                f"Project pack {pack_id} must declare portability=project.",
            )
        if pack["status"] not in {"pilot", "active"}:
            raise MaestroError(
                "PROJECT_EXPERTISE_STATUS_INVALID",
                f"Enabled project pack {pack_id} must be pilot or active.",
            )
        _required_pack_file(skill_root, "SKILL.md")
        _required_pack_file(skill_root, "agents/openai.yaml")
        _required_pack_file(skill_root, pack["source_manifest"])
        _required_pack_file(skill_root, pack["evaluation_suite"])
        for guide in pack["guides"]:
            _required_pack_file(
                skill_root,
                f"references/{guide['guide_id']}.md",
            )
        openai_policy = _required_pack_file(
            skill_root,
            "agents/openai.yaml",
        ).read_text(encoding="utf-8", errors="replace")
        if not re.search(
            r"(?m)^\s*allow_implicit_invocation:\s*false\s*$",
            openai_policy,
        ):
            raise MaestroError(
                "PROJECT_EXPERTISE_INVOCATION_UNSAFE",
                f"Project pack {pack_id} must keep OpenAI implicit invocation disabled.",
            )

        extends = pack.get("extends")
        resolved = copy.deepcopy(pack)
        guide_origins = {
            guide["guide_id"]: {
                "origin": "project",
                "skill_id": pack["skill_id"],
            }
            for guide in pack["guides"]
        }
        base_card: dict[str, Any] | None = None
        if extends is not None:
            base = bundled_by_id.get(extends["expertise_pack_id"])
            if base is None:
                raise MaestroError(
                    "PROJECT_EXPERTISE_BASE_INVALID",
                    f"Project pack {pack_id} may extend only one bundled Expertise Pack.",
                )
            base_digest = expertise_manifest_digest(base)
            if (
                base["version"] != extends["version"]
                or base_digest != extends["digest"]
            ):
                raise MaestroError(
                    "PROJECT_EXPERTISE_BASE_STALE",
                    f"Project pack {pack_id} pins a different base version or digest.",
                )
            base_guide_ids = {
                guide["guide_id"] for guide in base["guides"]
            }
            local_guide_ids = {
                guide["guide_id"] for guide in pack["guides"]
            }
            collisions = sorted(base_guide_ids & local_guide_ids)
            if collisions:
                raise MaestroError(
                    "PROJECT_EXPERTISE_GUIDE_COLLISION",
                    f"Project pack {pack_id} redefines inherited guides: {collisions}",
                )
            resolved["triggers"] = list(
                dict.fromkeys([*base["triggers"], *pack["triggers"]])
            )
            resolved["guides"] = [
                *copy.deepcopy(base["guides"]),
                *copy.deepcopy(pack["guides"]),
            ]
            resolved["default_guides"] = list(
                dict.fromkeys(
                    [*pack["default_guides"], *base["default_guides"]]
                )
            )
            resolved["research_policy"] = {
                "default_mode": "reuse",
                "contextualize_triggers": list(
                    dict.fromkeys(
                        [
                            *base["research_policy"]["contextualize_triggers"],
                            *pack["research_policy"]["contextualize_triggers"],
                        ]
                    )
                ),
                "refresh_triggers": list(
                    dict.fromkeys(
                        [
                            *base["research_policy"]["refresh_triggers"],
                            *pack["research_policy"]["refresh_triggers"],
                        ]
                    )
                ),
            }
            guide_origins.update(
                {
                    guide["guide_id"]: {
                        "origin": "bundled",
                        "skill_id": base["skill_id"],
                    }
                    for guide in base["guides"]
                }
            )
            base_card = {
                "expertise_pack_id": base["expertise_pack_id"],
                "version": base["version"],
                "digest": base_digest,
                "skill_id": base["skill_id"],
            }

        resolved["_maestro"] = {
            "origin": "project",
            "pack_path": relative_path,
            "skill_path": (
                skill_root.relative_to(repo) / "SKILL.md"
            ).as_posix(),
            "definition_digest": _skill_tree_digest(skill_root),
            "guide_origins": guide_origins,
            "base": base_card,
        }
        result.append(resolved)
    return result


def load_expertise_catalog(
    repo_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    registry = load_registry()
    errors = validate_registry(registry)
    if errors:
        raise MaestroError("REGISTRY_INVALID", "; ".join(errors))
    bundled = []
    for pack in registry["expertise_packs"]:
        item = copy.deepcopy(pack)
        item["_maestro"] = {
            "origin": "bundled",
            "pack_path": None,
            "skill_path": None,
            "definition_digest": expertise_manifest_digest(pack),
            "guide_origins": {
                guide["guide_id"]: {
                    "origin": "bundled",
                    "skill_id": pack["skill_id"],
                }
                for guide in pack["guides"]
            },
            "base": None,
        }
        bundled.append(item)
    if repo_path is None:
        return bundled
    repo = ensure_repo(repo_path)
    return [*bundled, *_load_project_packs(repo, registry)]


def expertise_definition_map(
    repo_path: str | Path | None = None,
) -> dict[str, str]:
    return {
        pack["expertise_pack_id"]: pack["_maestro"]["definition_digest"]
        for pack in load_expertise_catalog(repo_path)
    }


def _matches(goal_terms: frozenset[str], trigger: str) -> bool:
    return term_matches(goal_terms, trigger)


def _minimal_pack_card(
    pack: dict[str, Any],
    selected_guides: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata = pack["_maestro"]
    return {
        "expertise_pack_id": pack["expertise_pack_id"],
        "summary": pack["summary"],
        "status": pack["status"],
        "portability": pack["portability"],
        "version": pack["version"],
        "skill_id": pack["skill_id"],
        "origin": metadata["origin"],
        "pack_path": metadata["pack_path"],
        "skill_path": metadata["skill_path"],
        "definition_digest": metadata["definition_digest"],
        "extends": metadata["base"],
        "guides": [
            {
                "guide_id": guide["guide_id"],
                "summary": guide["summary"],
                "freshness": guide["freshness"],
                **metadata["guide_origins"][guide["guide_id"]],
            }
            for guide in selected_guides
        ],
        "source_manifest": pack["source_manifest"],
        "evaluation_suite": pack["evaluation_suite"],
    }


def select_expertise(
    goal: str,
    *,
    intent: str,
    research_evidence_digest: str | None = None,
    repo_path: str | Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select one compact reusable expertise pack and an explicit research gate."""

    if research_evidence_digest is not None and (
        not isinstance(research_evidence_digest, str)
        or DIGEST_PATTERN.fullmatch(research_evidence_digest) is None
    ):
        raise MaestroError(
            "RESEARCH_EVIDENCE_DIGEST_INVALID",
            "Research evidence digest must be a canonical SHA-256 digest.",
        )

    catalog = load_expertise_catalog(repo_path)

    goal_terms = searchable_terms(goal)
    ranked: list[tuple[int, bool, str, dict[str, Any]]] = []
    eligible_packs = [
        pack
        for pack in catalog
        if pack["status"] in {"pilot", "active"}
    ]
    for pack in eligible_packs:
        selectable_triggers = set(pack["triggers"])
        selectable_triggers.update(
            trigger
            for guide in pack["guides"]
            for trigger in guide["triggers"]
        )
        selectable_triggers.update(
            pack["research_policy"]["contextualize_triggers"]
        )
        selectable_triggers.update(
            pack["research_policy"]["refresh_triggers"]
        )
        score = sum(
            1
            for trigger in selectable_triggers
            if _matches(goal_terms, trigger)
        )
        if score:
            project_priority = pack["_maestro"]["origin"] == "project"
            ranked.append(
                (
                    score,
                    project_priority,
                    pack["expertise_pack_id"],
                    pack,
                )
            )
    ranked.sort(key=lambda item: (-item[0], -int(item[1]), item[2]))
    selected_packs = [item[3] for item in ranked[:MAX_SELECTED_PACKS]]

    selected_guide_ids: list[str] = []
    pack_cards: list[dict[str, Any]] = []
    research_mode = "reuse"
    research_reasons: list[str] = []
    warnings: list[dict[str, Any]] = []

    for pack in selected_packs:
        guide_by_id = {guide["guide_id"]: guide for guide in pack["guides"]}
        matched_guides = [
            guide
            for guide in pack["guides"]
            if any(_matches(goal_terms, trigger) for trigger in guide["triggers"])
        ]
        matched_guides.sort(
            key=lambda guide: (
                guide["freshness"] != "volatile",
                guide["guide_id"],
            )
        )
        ordered_ids = list(
            dict.fromkeys(
                [
                    *(guide["guide_id"] for guide in matched_guides),
                    *pack["default_guides"],
                ]
            )
        )[:MAX_SELECTED_GUIDES]
        selected_guides = [guide_by_id[guide_id] for guide_id in ordered_ids]
        selected_guide_ids.extend(ordered_ids)
        pack_cards.append(_minimal_pack_card(pack, selected_guides))

        policy = pack["research_policy"]
        refresh_matches = [
            trigger
            for trigger in policy["refresh_triggers"]
            if _matches(goal_terms, trigger)
        ]
        contextual_matches = [
            trigger
            for trigger in policy["contextualize_triggers"]
            if _matches(goal_terms, trigger)
        ]
        if refresh_matches:
            research_mode = "refresh"
            research_reasons.extend(refresh_matches)
        elif contextual_matches and research_mode == "reuse":
            research_mode = "contextualize"
            research_reasons.extend(contextual_matches)

        if pack["status"] == "pilot":
            warnings.append(
                {
                    "code": "EXPERTISE_PACK_PILOT",
                    "expertise_pack_id": pack["expertise_pack_id"],
                    "message": (
                        "The selected Expertise Pack is in pilot status; "
                        "verify its rubric against the task result."
                    ),
                }
            )

    if not selected_packs:
        discovery_matches = [
            trigger
            for trigger in DISCOVERY_TRIGGERS
            if _matches(goal_terms, trigger)
        ]
        if discovery_matches:
            research_mode = "discover"
            research_reasons = discovery_matches

    if research_evidence_digest is not None and (
        research_mode == "reuse" or intent == "research"
    ):
        raise MaestroError(
            "RESEARCH_EVIDENCE_NOT_APPLICABLE",
            "The routed task has no external research gate to satisfy.",
        )

    if research_mode == "reuse":
        gate = "not-required"
        evidence_digest = None
    elif intent == "research":
        gate = "in-plan"
        evidence_digest = None
    elif research_evidence_digest is not None:
        gate = "satisfied"
        evidence_digest = research_evidence_digest
    else:
        gate = "open"
        evidence_digest = None
        warnings.append(
            {
                "code": "EXPERTISE_RESEARCH_REQUIRED",
                "mode": research_mode,
                "message": (
                    "Run bounded reference research and re-route with its "
                    "artifact digest before executing assignments."
                ),
            }
        )

    selection = {
        "schema_version": "maestro_expertise_selection_v1",
        "selected_pack_ids": [
            pack["expertise_pack_id"] for pack in selected_packs
        ],
        "selected_guide_ids": selected_guide_ids,
        "pack_definition_digests": {
            pack["expertise_pack_id"]: pack["_maestro"]["definition_digest"]
            for pack in selected_packs
        },
        "pack_cards": pack_cards,
        "research_requirement": {
            "mode": research_mode,
            "gate": gate,
            "reasons": list(dict.fromkeys(research_reasons)),
            "evidence_digest": evidence_digest,
        },
        "warnings": warnings,
        "selection_trace": {
            "catalog_packs": len(catalog),
            "project_packs": sum(
                pack["_maestro"]["origin"] == "project"
                for pack in catalog
            ),
            "eligible_packs": len(eligible_packs),
            "returned_pack_bodies": len(pack_cards),
            "returned_guide_bodies": len(selected_guide_ids),
            "max_selected_packs": MAX_SELECTED_PACKS,
            "max_selected_guides": MAX_SELECTED_GUIDES,
        },
    }
    return selection, warnings
