from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .expertise import load_expertise_catalog
from .release import skill_record
from .util import canonical_json, safe_target, sha256_bytes, sha256_text

EXPERTISE_PROMPT_CONTEXT_VERSION = "maestro_expertise_prompt_context_v1"
MAX_EXPERTISE_FILE_BYTES = 96_000
MAX_EXPERTISE_CONTEXT_BYTES = 192_000


def unavailable_expertise_observation() -> dict[str, Any]:
    return {
        "packs": [],
        "load": {
            "status": "unavailable",
            "evidence_refs": [],
        },
        "application": {
            "status": "unavailable",
            "guide_ids": [],
            "evidence_refs": [],
        },
    }


def _skill_root(
    repo: Path,
    *,
    skill_id: str,
    skill_path: Any,
) -> Path:
    candidates: list[Path] = []
    if isinstance(skill_path, str) and skill_path.strip():
        candidates.append(safe_target(repo, skill_path))
    candidates.extend(
        [
            repo / "skills" / skill_id,
            repo / ".agents" / "skills" / skill_id,
            Path.home() / ".agents" / "skills" / skill_id,
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir():
            return resolved
    raise MaestroError(
        "EXPERTISE_SKILL_UNAVAILABLE",
        f"The exact projected Expertise Skill is not installed: {skill_id}.",
    )


def _strict_text(root: Path, relative: str) -> tuple[str, str]:
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        metadata = candidate.lstat()
    except (OSError, ValueError) as exc:
        raise MaestroError(
            "EXPERTISE_RESOURCE_INVALID",
            f"Expertise resource escapes or is missing: {relative}.",
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > MAX_EXPERTISE_FILE_BYTES
    ):
        raise MaestroError(
            "EXPERTISE_RESOURCE_INVALID",
            f"Expertise resource must be a bounded regular file: {relative}.",
        )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            resolved,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > MAX_EXPERTISE_FILE_BYTES
            ):
                raise MaestroError(
                    "EXPERTISE_RESOURCE_INVALID",
                    (
                        "Expertise resource must remain a bounded regular "
                        f"file while read: {relative}."
                    ),
                )
            content = handle.read(MAX_EXPERTISE_FILE_BYTES + 1)
        if len(content) > MAX_EXPERTISE_FILE_BYTES:
            raise MaestroError(
                "EXPERTISE_RESOURCE_INVALID",
                f"Expertise resource exceeds the byte limit: {relative}.",
            )
        return (
            content.decode("utf-8", errors="strict"),
            sha256_bytes(content),
        )
    except (OSError, UnicodeError) as exc:
        raise MaestroError(
            "EXPERTISE_RESOURCE_INVALID",
            f"Expertise resource must be readable strict UTF-8: {relative}.",
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_assignment_expertise(
    repo: Path,
    projection: dict[str, Any],
) -> dict[str, Any]:
    """Load and attest exact projected Skill and Guide bodies for one Host turn."""

    expertise_load = projection.get("expertise_load")
    projected_packs = (
        expertise_load.get("packs")
        if isinstance(expertise_load, dict)
        else None
    )
    if not isinstance(projected_packs, list) or not projected_packs:
        return {
            "prompt_context": None,
            "observation": unavailable_expertise_observation(),
            "evidence_ref": None,
            "attestation_digest": None,
        }

    catalog = {
        item["expertise_pack_id"]: item
        for item in load_expertise_catalog(repo)
    }
    prompt_packs: list[dict[str, Any]] = []
    observed_packs: list[dict[str, Any]] = []
    attested_packs: list[dict[str, Any]] = []
    for projected_pack in projected_packs:
        if not isinstance(projected_pack, dict):
            raise MaestroError(
                "EXPERTISE_PROJECTION_INVALID",
                "Projected Expertise Pack entries must be objects.",
            )
        pack_id = projected_pack.get("expertise_pack_id")
        skill_id = projected_pack.get("skill_id")
        definition_digest = projected_pack.get("definition_digest")
        skill_digest = projected_pack.get("skill_definition_digest")
        catalog_pack = catalog.get(pack_id)
        metadata = (
            catalog_pack.get("_maestro")
            if isinstance(catalog_pack, dict)
            else None
        )
        if (
            not isinstance(pack_id, str)
            or not isinstance(skill_id, str)
            or not isinstance(definition_digest, str)
            or not isinstance(skill_digest, str)
            or not isinstance(metadata, dict)
            or metadata.get("definition_digest") != definition_digest
            or metadata.get("skill_definition_digests", {}).get(skill_id)
            != skill_digest
        ):
            raise MaestroError(
                "EXPERTISE_PROJECTION_MISMATCH",
                "Projected Pack and Skill digests do not match the active catalog.",
            )
        root = _skill_root(
            repo,
            skill_id=skill_id,
            skill_path=projected_pack.get("skill_path"),
        )
        initial_skill_digest = skill_record(root)["sha256"]
        if initial_skill_digest != skill_digest:
            raise MaestroError(
                "EXPERTISE_SKILL_DIGEST_MISMATCH",
                f"Installed Expertise Skill changed after projection: {skill_id}.",
            )
        skill_text, _ = _strict_text(root, "SKILL.md")
        projected_guides = projected_pack.get("guides")
        if not isinstance(projected_guides, list) or not projected_guides:
            raise MaestroError(
                "EXPERTISE_GUIDE_REQUIRED",
                "A projected Expertise Pack must select at least one Guide.",
            )
        prompt_guides: list[dict[str, str]] = []
        guide_ids: list[str] = []
        loaded_refs: list[str] = []
        attested_guides: list[dict[str, str]] = []
        for guide in projected_guides:
            if (
                not isinstance(guide, dict)
                or guide.get("skill_id") != skill_id
                or guide.get("skill_definition_digest") != skill_digest
                or not isinstance(guide.get("guide_id"), str)
                or not isinstance(guide.get("resource_path"), str)
            ):
                raise MaestroError(
                    "EXPERTISE_GUIDE_PROJECTION_MISMATCH",
                    "Projected Guide identity is not bound to the projected Skill.",
                )
            guide_id = guide["guide_id"]
            resource_path = guide["resource_path"]
            guide_text, guide_digest = _strict_text(
                root,
                resource_path,
            )
            loaded_ref = f"guide:{pack_id}:{guide_id}:{guide_digest}"
            guide_ids.append(guide_id)
            loaded_refs.append(loaded_ref)
            prompt_guides.append(
                {
                    "guide_id": guide_id,
                    "resource_path": resource_path,
                    "content": guide_text,
                }
            )
            attested_guides.append(
                {
                    "guide_id": guide_id,
                    "resource_path": resource_path,
                    "sha256": guide_digest,
                }
            )
        if skill_record(root)["sha256"] != initial_skill_digest:
            raise MaestroError(
                "EXPERTISE_SKILL_DIGEST_MISMATCH",
                (
                    "Installed Expertise Skill changed while its prompt "
                    f"context was constructed: {skill_id}."
                ),
            )
        prompt_packs.append(
            {
                "expertise_pack_id": pack_id,
                "definition_digest": definition_digest,
                "skill_id": skill_id,
                "skill_definition_digest": skill_digest,
                "skill_content": skill_text,
                "guides": prompt_guides,
            }
        )
        observed_packs.append(
            {
                "expertise_pack_id": pack_id,
                "definition_digest": definition_digest,
                "skill_id": skill_id,
                "skill_definition_digest": skill_digest,
                "guide_ids": guide_ids,
                "loaded_guide_refs": loaded_refs,
            }
        )
        attested_packs.append(
            {
                "expertise_pack_id": pack_id,
                "definition_digest": definition_digest,
                "skill_id": skill_id,
                "skill_definition_digest": skill_digest,
                "skill_sha256": skill_digest,
                "guides": attested_guides,
            }
        )

    attestation = {
        "schema_version": "maestro_expertise_load_attestation_v1",
        "application_mode": expertise_load.get("application_mode"),
        "packs": attested_packs,
    }
    attestation_digest = sha256_text(canonical_json(attestation))
    evidence_ref = f"expertise-load:{attestation_digest}"
    prompt_context = {
        "schema_version": EXPERTISE_PROMPT_CONTEXT_VERSION,
        "application_mode": expertise_load.get("application_mode"),
        "packs": prompt_packs,
    }
    if len(canonical_json(prompt_context).encode("utf-8")) > MAX_EXPERTISE_CONTEXT_BYTES:
        raise MaestroError(
            "EXPERTISE_CONTEXT_TOO_LARGE",
            "Selected Expertise content exceeds the bounded Host context.",
        )
    return {
        "prompt_context": prompt_context,
        "observation": {
            "packs": observed_packs,
            "load": {
                "status": "host_loaded",
                "evidence_refs": [evidence_ref],
            },
            "application": {
                "status": "not_reported",
                "guide_ids": [],
                "evidence_refs": [],
            },
        },
        "evidence_ref": evidence_ref,
        "attestation_digest": attestation_digest,
    }
