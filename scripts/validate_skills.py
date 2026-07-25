#!/usr/bin/env python3
"""Validate the small, bundled Skill packages without external dependencies."""

from __future__ import annotations

import re
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
    for reference in sorted(set(REFERENCE_PATTERN.findall(text))):
        if not (skill_root / reference).is_file():
            failures.append(f"missing reference: {reference}")
    agent_metadata = skill_root / "agents" / "openai.yaml"
    if not agent_metadata.is_file():
        failures.append("agents/openai.yaml is missing")
    return failures


def main() -> int:
    failures: dict[str, list[str]] = {}
    for skill_root in sorted(SKILLS_ROOT.iterdir()):
        if not skill_root.is_dir():
            continue
        skill_failures = validate_skill(skill_root)
        if skill_failures:
            failures[skill_root.name] = skill_failures
    if failures:
        for name, messages in failures.items():
            for message in messages:
                print(f"[FAIL] {name}: {message}")
        return 1
    print(f"[OK] validated {len(list(SKILLS_ROOT.iterdir()))} bundled Skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
