from __future__ import annotations

from typing import Any


def undeclared_routing_removals(
    existing_pack: dict[str, Any],
    revised_pack: dict[str, Any],
) -> list[str]:
    """Return routing signals removed by a full Pack revision."""

    removals: list[str] = []
    _record_removed_values(
        removals,
        "Pack triggers",
        existing_pack.get("triggers"),
        revised_pack.get("triggers"),
    )
    _record_removed_values(
        removals,
        "dominance triggers",
        existing_pack.get("dominance_triggers"),
        revised_pack.get("dominance_triggers"),
    )
    _record_removed_values(
        removals,
        "default Guides",
        existing_pack.get("default_guides"),
        revised_pack.get("default_guides"),
    )

    existing_policy = existing_pack.get("research_policy")
    revised_policy = revised_pack.get("research_policy")
    for field in ("contextualize_triggers", "refresh_triggers"):
        _record_removed_values(
            removals,
            f"research policy {field}",
            (
                existing_policy.get(field)
                if isinstance(existing_policy, dict)
                else None
            ),
            (
                revised_policy.get(field)
                if isinstance(revised_policy, dict)
                else None
            ),
        )

    revised_guides = {
        guide["guide_id"]: guide
        for guide in revised_pack.get("guides", [])
        if isinstance(guide, dict)
        and isinstance(guide.get("guide_id"), str)
    }
    for existing_guide in existing_pack.get("guides", []):
        if (
            not isinstance(existing_guide, dict)
            or not isinstance(existing_guide.get("guide_id"), str)
        ):
            continue
        guide_id = existing_guide["guide_id"]
        revised_guide = revised_guides.get(guide_id)
        if revised_guide is None:
            continue
        _record_removed_values(
            removals,
            f"Guide {guide_id} triggers",
            existing_guide.get("triggers"),
            revised_guide.get("triggers"),
        )
    return removals


def _record_removed_values(
    removals: list[str],
    label: str,
    existing: Any,
    revised: Any,
) -> None:
    existing_values = {
        value for value in existing or [] if isinstance(value, str)
    }
    revised_values = {
        value for value in revised or [] if isinstance(value, str)
    }
    removed = sorted(existing_values - revised_values)
    if removed:
        removals.append(f"{label}: {', '.join(removed)}")
