from __future__ import annotations

import copy
from typing import Any

from .expertise_changes import expertise_change_sets
from .expertise_health import expertise_component_health


def project_expertise_operations(
    inventory: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compose domain read models without collecting sources or rendering UI."""

    projected = copy.deepcopy(inventory)
    component_health = expertise_component_health(projected, events)
    changes = expertise_change_sets(projected, component_health)
    projected["component_health"] = component_health
    projected["change_sets"] = changes["change_sets"]
    projected["pack_change_set_ids"] = changes["pack_change_set_ids"]
    return projected
