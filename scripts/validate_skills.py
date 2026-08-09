#!/usr/bin/env python3
"""Validate the small, bundled Skill packages without external dependencies."""

from __future__ import annotations

import re
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
ALLOWED_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
}
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REFERENCE_PATTERN = re.compile(r"references/[A-Za-z0-9_.-]+\.md")
MAX_SKILL_LINES = 500
MAX_REFERENCE_BYTES = 20_000


def _frontmatter(skill_file: Path) -> dict[str, str]:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("unterminated YAML frontmatter")
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith((" ", "\t")) or ":" not in line:
            raise ValueError(
                "bundled Skills require flat key: value frontmatter"
            )
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key in result:
            raise ValueError(f"duplicate frontmatter key: {key}")
        result[key] = value
    unexpected = sorted(set(result) - ALLOWED_FRONTMATTER_KEYS)
    if unexpected:
        raise ValueError(f"unsupported frontmatter keys: {unexpected}")
    return result


def validate_skill(skill_root: Path) -> list[str]:
    failures: list[str] = []
    skill_file = skill_root / "SKILL.md"
    if not skill_file.is_file():
        return ["SKILL.md is missing"]
    try:
        metadata = _frontmatter(skill_file)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [str(exc)]

    expected_name = skill_root.name
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    if name != expected_name:
        failures.append(
            f"name must match directory {expected_name!r}; received {name!r}"
        )
    if not NAME_PATTERN.fullmatch(name) or len(name) > 64:
        failures.append("name must be hyphen-case and at most 64 characters")
    if not description or len(description) > 1024:
        failures.append("description must contain 1..1024 characters")
    if "<" in description or ">" in description:
        failures.append("description cannot contain angle brackets")

    text = skill_file.read_text(encoding="utf-8")
    if len(text.splitlines()) > MAX_SKILL_LINES:
        failures.append(
            f"SKILL.md exceeds the {MAX_SKILL_LINES}-line context limit"
        )
    for reference in sorted(set(REFERENCE_PATTERN.findall(text))):
        reference_path = skill_root / reference
        if not reference_path.is_file():
            failures.append(f"missing reference: {reference}")
        elif reference_path.stat().st_size > MAX_REFERENCE_BYTES:
            failures.append(
                f"reference exceeds {MAX_REFERENCE_BYTES} bytes: {reference}"
            )
    agent_metadata = skill_root / "agents" / "openai.yaml"
    if not agent_metadata.is_file():
        failures.append("agents/openai.yaml is missing")
    return failures


def validate_expertise_packs() -> dict[str, list[str]]:
    failures: dict[str, list[str]] = {}
    registry_root = (
        ROOT / "src/maestro/resources/registry/expertise-packs"
    )
    if not registry_root.is_dir():
        return failures
    for pack_path in sorted(registry_root.glob("*.json")):
        messages: list[str] = []
        try:
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            failures[f"expertise:{pack_path.stem}"] = [str(exc)]
            continue
        pack_id = pack.get("expertise_pack_id")
        skill_id = pack.get("skill_id")
        skill_root = SKILLS_ROOT / str(skill_id)
        if not skill_root.is_dir():
            messages.append(f"missing Skill directory: {skill_id}")
        guides = pack.get("guides")
        guide_ids = {
            guide.get("guide_id")
            for guide in guides
            if isinstance(guide, dict)
            and isinstance(guide.get("guide_id"), str)
        } if isinstance(guides, list) else set()
        for guide_id in sorted(guide_ids):
            guide_path = skill_root / "references" / f"{guide_id}.md"
            if not guide_path.is_file():
                messages.append(f"missing Decision Guide: {guide_id}")
            elif guide_path.stat().st_size > MAX_REFERENCE_BYTES:
                messages.append(
                    f"Decision Guide exceeds {MAX_REFERENCE_BYTES} bytes: {guide_id}"
                )

        source_path = skill_root / str(pack.get("source_manifest", ""))
        eval_path = skill_root / str(pack.get("evaluation_suite", ""))
        for label, path in (("source manifest", source_path), ("evaluation", eval_path)):
            if not path.is_file():
                messages.append(f"missing {label}: {path.name}")
        try:
            sources = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            sources = None
        if not isinstance(sources, dict):
            messages.append("source manifest must be valid JSON")
        else:
            if sources.get("expertise_pack_id") != pack_id:
                messages.append("source manifest pack ID does not match Registry")
            for source in sources.get("sources", []):
                if not isinstance(source, dict):
                    messages.append("source entries must be objects")
                    continue
                tier = source.get("tier")
                used_by = source.get("used_by")
                if (
                    not isinstance(tier, int)
                    or isinstance(tier, bool)
                    or tier not in range(0, 6)
                    or source.get("freshness")
                    not in {"stable", "versioned", "volatile"}
                    or not isinstance(used_by, list)
                    or not all(isinstance(item, str) for item in used_by)
                    or not set(used_by).issubset(guide_ids)
                ):
                    messages.append(
                        f"invalid source coverage: {source.get('source_id', '?')}"
                    )
        try:
            evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            evaluation = None
        if not isinstance(evaluation, dict):
            messages.append("evaluation suite must be valid JSON")
        else:
            if evaluation.get("expertise_pack_id") != pack_id:
                messages.append("evaluation suite pack ID does not match Registry")
            case_ids: list[str] = []
            for case in evaluation.get("cases", []):
                if not isinstance(case, dict):
                    messages.append("evaluation cases must be objects")
                    continue
                case_ids.append(str(case.get("case_id")))
                expected_guides = case.get("expected_guides")
                if (
                    not isinstance(expected_guides, list)
                    or not all(
                        isinstance(item, str) for item in expected_guides
                    )
                    or not set(expected_guides).issubset(guide_ids)
                ):
                    messages.append(
                        f"evaluation references unknown guide: {case.get('case_id', '?')}"
                    )
            if len(case_ids) != len(set(case_ids)):
                messages.append("evaluation case IDs must be unique")
        if messages:
            failures[f"expertise:{pack_path.stem}"] = messages
    return failures


def main() -> int:
    failures: dict[str, list[str]] = {}
    for skill_root in sorted(SKILLS_ROOT.iterdir()):
        if not skill_root.is_dir():
            continue
        skill_failures = validate_skill(skill_root)
        if skill_failures:
            failures[skill_root.name] = skill_failures
    failures.update(validate_expertise_packs())
    if failures:
        for name, messages in failures.items():
            for message in messages:
                print(f"[FAIL] {name}: {message}")
        return 1
    pack_count = len(
        list(
            (
                ROOT / "src/maestro/resources/registry/expertise-packs"
            ).glob("*.json")
        )
    )
    print(
        f"[OK] validated {len(list(SKILLS_ROOT.iterdir()))} bundled Skills "
        f"and {pack_count} Expertise Packs"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
