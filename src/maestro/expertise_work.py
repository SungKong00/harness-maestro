from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Iterable

from .errors import MaestroError
from .execution_contracts import normalize_execution_contract
from .expertise import (
    evaluate_pack_research_policy,
    load_expertise_catalog,
)
from .research import (
    expected_research_binding,
    require_completed_research_bundle,
)
from .model_policy import validate_model_route_shape
from .registry import _model_route, load_registry
from .task_coverage import validate_task_coverage
from .util import canonical_json, ensure_repo, sha256_text

EXPERTISE_WORK_PLAN_VERSION = "maestro_expertise_work_plan_v1"
EXPERTISE_WORK_PACKET_VERSION = "maestro_expertise_work_packet_v1"
EXPERTISE_WORK_CLOSURE_VERSION = "maestro_expertise_work_closure_v1"
MAX_GUIDES_PER_BATCH = 4
MAX_PACKET_LINES = 32
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

WORK_PLAN_FIELDS = {
    "schema_version",
    "work_plan_id",
    "coverage_id",
    "source_plan_id",
    "goal_digest",
    "pairs",
    "pack_research_requirements",
    "batches",
    "parallel_groups",
    "pair_assignment_policy",
    "writer_authority",
    "writes_performed",
}
WORK_PAIR_FIELDS = {
    "pair_id",
    "coverage_item_id",
    "target_ref",
    "pack_id",
    "guide_id",
    "pack_definition_digest",
    "skill_id",
    "skill_definition_digest",
    "resource_path",
}
WORK_BATCH_FIELDS = {
    "batch_id",
    "responsibility",
    "pack_id",
    "guide_ids",
    "coverage_pair_ids",
    "depends_on",
    "external_prerequisite_item_ids",
    "read_only",
    "may_spawn",
    "model_route",
}
LEGACY_WORK_BATCH_FIELDS = WORK_BATCH_FIELDS - {"model_route"}
WORK_RESEARCH_FIELDS = {
    "pack_id",
    "guide_ids",
    "pack_definition_digest",
    "mode",
    "reasons",
    "gate",
    "evidence_digest",
}


def _digest(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload[field] = ""
    return sha256_text(canonical_json(payload))


def _line(value: Any, maximum: int = 1_000) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and not any(character in value for character in "\r\n\x00")
    )


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _id(value: Any) -> bool:
    return isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None


def _unique_ids(
    value: Any,
    *,
    maximum: int = 1_024,
    allow_empty: bool = True,
) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and len(value) <= maximum
        and len(value) == len(set(value))
        and all(_id(item) for item in value)
    )


def _unique_lines(
    value: Any,
    *,
    maximum: int = MAX_PACKET_LINES,
    allow_empty: bool = True,
) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and len(value) <= maximum
        and len(value) == len(set(value))
        and all(_line(item) for item in value)
    )


def _work_plan_shape_error(value: Any) -> str | None:
    """Return one structural error without consulting mutable registries."""

    if (
        not isinstance(value, dict)
        or set(value) != WORK_PLAN_FIELDS
        or value.get("schema_version") != EXPERTISE_WORK_PLAN_VERSION
        or not _sha256(value.get("work_plan_id"))
        or value.get("work_plan_id") != _digest(value, "work_plan_id")
        or not _sha256(value.get("coverage_id"))
        or not _sha256(value.get("source_plan_id"))
        or not _sha256(value.get("goal_digest"))
        or value.get("pair_assignment_policy") != "exactly-once"
        or value.get("writer_authority") != "NONE"
        or value.get("writes_performed") is not False
        or not isinstance(value.get("pairs"), list)
        or len(value["pairs"]) > 1_024
        or not isinstance(value.get("pack_research_requirements"), list)
        or len(value["pack_research_requirements"]) > 1_024
        or not isinstance(value.get("batches"), list)
        or len(value["batches"]) > 1_024
        or not isinstance(value.get("parallel_groups"), list)
        or len(value["parallel_groups"]) > 1_024
    ):
        return "Expertise work plan identity or top-level fields are invalid."
    pair_ids: list[str] = []
    for pair in value["pairs"]:
        if (
            not isinstance(pair, dict)
            or set(pair) != WORK_PAIR_FIELDS
            or not _id(pair.get("pair_id"))
            or not _id(pair.get("coverage_item_id"))
            or not _line(pair.get("target_ref"))
            or not _id(pair.get("pack_id"))
            or not _id(pair.get("guide_id"))
            or not _sha256(pair.get("pack_definition_digest"))
            or not _id(pair.get("skill_id"))
            or not _sha256(pair.get("skill_definition_digest"))
            or not _line(pair.get("resource_path"))
        ):
            return "Expertise work plan contains a malformed canonical pair."
        pair_ids.append(pair["pair_id"])
    if len(pair_ids) != len(set(pair_ids)):
        return "Expertise work plan contains duplicate canonical pairs."
    research_pack_ids: list[str] = []
    for requirement in value["pack_research_requirements"]:
        if (
            not isinstance(requirement, dict)
            or set(requirement) != WORK_RESEARCH_FIELDS
            or not _id(requirement.get("pack_id"))
            or not _unique_ids(
                requirement.get("guide_ids"),
                allow_empty=False,
            )
            or not _sha256(requirement.get("pack_definition_digest"))
            or requirement.get("mode")
            not in {"reuse", "contextualize", "refresh"}
            or not _unique_lines(requirement.get("reasons"))
            or requirement.get("gate")
            not in {"not-required", "satisfied"}
            or (
                requirement.get("gate") == "not-required"
                and requirement.get("evidence_digest") is not None
            )
            or (
                requirement.get("gate") == "satisfied"
                and not _sha256(requirement.get("evidence_digest"))
            )
        ):
            return "Expertise work plan contains a malformed Pack research requirement."
        research_pack_ids.append(requirement["pack_id"])
    if (
        len(research_pack_ids) != len(set(research_pack_ids))
        or set(research_pack_ids)
        != {pair["pack_id"] for pair in value["pairs"]}
    ):
        return "Expertise work research requirements must cover every Pack exactly once."
    batch_ids: list[str] = []
    assigned_pair_ids: list[str] = []
    for batch in value["batches"]:
        if (
            not isinstance(batch, dict)
            or frozenset(batch)
            not in {frozenset(WORK_BATCH_FIELDS), frozenset(LEGACY_WORK_BATCH_FIELDS)}
            or not _id(batch.get("batch_id"))
            or not _line(batch.get("responsibility"))
            or not _id(batch.get("pack_id"))
            or not _unique_ids(
                batch.get("guide_ids"),
                maximum=MAX_GUIDES_PER_BATCH,
                allow_empty=False,
            )
            or not _unique_ids(
                batch.get("coverage_pair_ids"),
                allow_empty=False,
            )
            or not _unique_ids(batch.get("depends_on"))
            or not _unique_ids(
                batch.get("external_prerequisite_item_ids")
            )
            or batch.get("read_only") is not True
            or batch.get("may_spawn") is not False
        ):
            return "Expertise work plan contains a malformed batch."
        if "model_route" in batch and (
            validate_model_route_shape(batch.get("model_route")) is not None
            or batch["model_route"].get("execution_unit_id")
            != batch.get("batch_id")
            or batch["model_route"].get("stage_kind")
            != "expertise-review"
            or batch["model_route"].get("executor")
            != "lens-reviewer"
        ):
            return "Expertise work plan contains a malformed batch model route."
        batch_ids.append(batch["batch_id"])
        assigned_pair_ids.extend(batch["coverage_pair_ids"])
    if len(batch_ids) != len(set(batch_ids)):
        return "Expertise work plan contains duplicate batch IDs."
    if (
        sorted(assigned_pair_ids) != sorted(pair_ids)
        or len(assigned_pair_ids) != len(set(assigned_pair_ids))
    ):
        return "Expertise work plan does not assign every pair exactly once."
    if any(
        not _unique_ids(group, allow_empty=False)
        for group in value["parallel_groups"]
    ):
        return "Expertise work plan contains a malformed parallel group."
    return None


def _route_plan(
    plan: Any,
    *,
    repo: Path,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = normalize_execution_contract(
        plan,
        repo_path=repo,
        research_bundle=research_bundle,
    )
    if context["status"] != "PASS":
        first = context["issues"][0]
        raise MaestroError(first["code"], first["message"])
    return context["route_plan"]


def _guide_catalog(
    repo: Path,
) -> dict[str, list[dict[str, Any]]]:
    by_guide: dict[str, list[dict[str, Any]]] = {}
    for pack in load_expertise_catalog(repo, include_candidates=True):
        if pack.get("status") not in {"pilot", "active"}:
            continue
        metadata = pack["_maestro"]
        for guide in pack["guides"]:
            guide_id = guide["guide_id"]
            origin = metadata["guide_origins"][guide_id]
            skill_id = origin["skill_id"]
            by_guide.setdefault(guide_id, []).append(
                {
                    "pack_id": pack["expertise_pack_id"],
                    "guide_id": guide_id,
                    "pack_definition_digest": metadata[
                        "definition_digest"
                    ],
                    "skill_id": skill_id,
                    "skill_definition_digest": metadata[
                        "skill_definition_digests"
                    ][skill_id],
                    "resource_path": f"references/{guide_id}.md",
                }
            )
    return by_guide


def _canonical_pair(
    allocation_ref: str,
    *,
    item_id: str,
    catalog: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    target = allocation_ref.removeprefix("guide:")
    if "/" in target:
        pack_id, guide_id = target.split("/", 1)
        matches = [
            item
            for item in catalog.get(guide_id, [])
            if item["pack_id"] == pack_id
        ]
    else:
        guide_id = target
        matches = catalog.get(guide_id, [])
    if len(matches) != 1:
        raise MaestroError(
            "EXPERTISE_WORK_GUIDE_UNRESOLVED",
            (
                f"Guide allocation {allocation_ref} must resolve to exactly "
                "one eligible current Pack and Guide."
            ),
        )
    pair = {
        "pair_id": "",
        "coverage_item_id": item_id,
        "target_ref": allocation_ref,
        **copy.deepcopy(matches[0]),
    }
    pair["pair_id"] = "pair-" + sha256_text(
        canonical_json(
            {
                "coverage_item_id": item_id,
                "pack_id": pair["pack_id"],
                "guide_id": pair["guide_id"],
            }
        )
    )[:20]
    return pair


def _canonical_pairs(
    coverage: dict[str, Any],
    *,
    repo: Path,
) -> list[dict[str, Any]]:
    catalog = _guide_catalog(repo)
    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in coverage["items"]:
        for allocation in item["allocations"]:
            if allocation["kind"] != "expertise-guide":
                continue
            key = (item["item_id"], allocation["target_ref"])
            if key in seen:
                raise MaestroError(
                    "EXPERTISE_WORK_PAIR_DUPLICATE",
                    "Coverage expertise allocations must be unique.",
                )
            seen.add(key)
            pairs.append(
                _canonical_pair(
                    allocation["target_ref"],
                    item_id=item["item_id"],
                    catalog=catalog,
                )
            )
    return sorted(
        pairs,
        key=lambda item: (
            item["coverage_item_id"],
            item["pack_id"],
            item["guide_id"],
        ),
    )


def _research_bundle_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    if not all(isinstance(bundle, dict) for bundle in raw):
        raise MaestroError(
            "EXPERTISE_WORK_RESEARCH_SET_INVALID",
            "Expertise research evidence must be one bundle or a list of bundles.",
        )
    return copy.deepcopy(raw)


def _pack_research_requirements(
    repo: Path,
    *,
    goal: str,
    pairs: list[dict[str, Any]],
    research_bundles: Any,
) -> list[dict[str, Any]]:
    """Validate research independently for every Pack represented in Coverage."""

    bundles = _research_bundle_list(research_bundles)
    packs = {
        pack["expertise_pack_id"]: pack
        for pack in load_expertise_catalog(repo, include_candidates=True)
        if pack.get("status") in {"pilot", "active"}
    }
    used_bundle_indexes: set[int] = set()
    requirements: list[dict[str, Any]] = []
    for pack_id in sorted({pair["pack_id"] for pair in pairs}):
        pack = packs.get(pack_id)
        if pack is None:
            raise MaestroError(
                "EXPERTISE_WORK_PACK_UNAVAILABLE",
                f"Coverage Pack is no longer eligible: {pack_id}.",
            )
        pack_pairs = [pair for pair in pairs if pair["pack_id"] == pack_id]
        guide_ids = sorted({pair["guide_id"] for pair in pack_pairs})
        definition_digests = {
            pair["pack_definition_digest"] for pair in pack_pairs
        }
        if len(definition_digests) != 1:
            raise MaestroError(
                "EXPERTISE_WORK_PACK_DIGEST_CONFLICT",
                f"Coverage pairs disagree on the {pack_id} Pack digest.",
            )
        pack_digest = next(iter(definition_digests))
        mode, reasons = evaluate_pack_research_policy(goal, pack)
        expertise = {
            "selected_pack_ids": [pack_id],
            "selected_guide_ids": guide_ids,
            "pack_definition_digests": {pack_id: pack_digest},
            "research_requirement": {
                "mode": mode,
                "gate": "not-required" if mode == "reuse" else "open",
                "reasons": reasons,
                "evidence_digest": None,
            },
        }
        evidence_digest: str | None = None
        gate = "not-required"
        if mode != "reuse":
            binding = expected_research_binding(goal, expertise)
            matches = [
                (index, bundle)
                for index, bundle in enumerate(bundles)
                if bundle.get("request_binding") == binding
            ]
            if not matches:
                raise MaestroError(
                    "EXPERTISE_WORK_RESEARCH_REQUIRED",
                    (
                        f"Pack {pack_id} requires {mode} research for its "
                        "complete Coverage Guide set before batching."
                    ),
                )
            if len(matches) != 1:
                raise MaestroError(
                    "EXPERTISE_WORK_RESEARCH_DUPLICATE",
                    f"Provide exactly one matching ResearchBundle for Pack {pack_id}.",
                )
            index, bundle = matches[0]
            validation = require_completed_research_bundle(
                bundle,
                goal=goal,
                expertise=expertise,
                repo_path=repo,
            )
            used_bundle_indexes.add(index)
            gate = "satisfied"
            evidence_digest = validation["artifact_digest"]
        requirements.append(
            {
                "pack_id": pack_id,
                "guide_ids": guide_ids,
                "pack_definition_digest": pack_digest,
                "mode": mode,
                "reasons": reasons,
                "gate": gate,
                "evidence_digest": evidence_digest,
            }
        )
    unused = sorted(set(range(len(bundles))) - used_bundle_indexes)
    if unused:
        raise MaestroError(
            "EXPERTISE_WORK_RESEARCH_NOT_APPLICABLE",
            "Every Expertise ResearchBundle must match one required Coverage Pack.",
        )
    return requirements


def _topological_groups(
    dependencies: dict[str, set[str]],
) -> list[list[str]]:
    remaining = {key: set(value) for key, value in dependencies.items()}
    groups: list[list[str]] = []
    completed: set[str] = set()
    while remaining:
        ready = sorted(
            batch_id
            for batch_id, needed in remaining.items()
            if needed.issubset(completed)
        )
        if not ready:
            raise MaestroError(
                "EXPERTISE_WORK_DEPENDENCY_CYCLE",
                "Expertise work batch dependencies contain a cycle.",
            )
        groups.append(ready)
        completed.update(ready)
        for batch_id in ready:
            remaining.pop(batch_id)
    return groups


def build_expertise_work_plan(
    repo_path: str | Path,
    *,
    goal: str,
    coverage: Any,
    plan: Any,
    draft: Any,
    research_bundle: dict[str, Any] | None = None,
    expertise_research_bundles: Any = None,
) -> dict[str, Any]:
    """Validate AI-authored batching after deriving the complete pair inventory."""

    repo = ensure_repo(repo_path)
    coverage_validation = validate_task_coverage(
        coverage,
        goal=goal,
        repo_path=repo,
        require_current_revision=True,
    )
    if coverage_validation["status"] != "PASS":
        first = coverage_validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    route = _route_plan(
        plan,
        repo=repo,
        research_bundle=research_bundle,
    )
    reviewer = next(
        item
        for item in load_registry()["executors"]
        if item["executor_id"] == "lens-reviewer"
    )
    if route["goal"] != coverage["goal"]:
        raise MaestroError(
            "EXPERTISE_WORK_GOAL_MISMATCH",
            "Coverage and execution plan must bind the same goal.",
        )
    if (
        not isinstance(draft, dict)
        or set(draft) != {"batches"}
        or not isinstance(draft["batches"], list)
    ):
        raise MaestroError(
            "EXPERTISE_WORK_DRAFT_INVALID",
            "Expertise work draft must contain only a batches list.",
        )

    pairs = _canonical_pairs(coverage, repo=repo)
    pack_research_requirements = _pack_research_requirements(
        repo,
        goal=goal,
        pairs=pairs,
        research_bundles=expertise_research_bundles,
    )
    pair_by_key = {
        (pair["coverage_item_id"], pair["target_ref"]): pair
        for pair in pairs
    }
    coverage_by_id = {
        item["item_id"]: item
        for item in coverage["items"]
        if isinstance(item, dict) and isinstance(item.get("item_id"), str)
    }
    if not pairs:
        if draft["batches"]:
            raise MaestroError(
                "EXPERTISE_WORK_NOT_APPLICABLE",
                "No Expertise Guide allocations exist for batching.",
            )
        batches: list[dict[str, Any]] = []
    else:
        batches = []
    assigned: set[str] = set()
    batch_ids: set[str] = set()
    raw_dependencies: dict[str, set[str]] = {}
    batch_pair_ids: dict[str, set[str]] = {}
    item_batches: dict[str, set[str]] = {}
    for raw in draft["batches"]:
        if (
            not isinstance(raw, dict)
            or set(raw)
            != {
                "batch_id",
                "responsibility",
                "coverage_pairs",
                "depends_on",
            }
            or not _id(raw.get("batch_id"))
            or not _line(raw.get("responsibility"), 1_000)
            or not isinstance(raw.get("coverage_pairs"), list)
            or not raw["coverage_pairs"]
            or not _unique_lines(raw.get("depends_on"), maximum=1_024)
            or raw["batch_id"] in batch_ids
        ):
            raise MaestroError(
                "EXPERTISE_WORK_BATCH_INVALID",
                "Every batch needs a unique ID, responsibility, pairs, and dependency list.",
            )
        batch_id = raw["batch_id"]
        batch_ids.add(batch_id)
        selected_pairs: list[dict[str, Any]] = []
        selected_pair_ids: set[str] = set()
        for pair_ref in raw["coverage_pairs"]:
            if (
                not isinstance(pair_ref, dict)
                or set(pair_ref) != {"coverage_item_id", "target_ref"}
            ):
                raise MaestroError(
                    "EXPERTISE_WORK_PAIR_REF_INVALID",
                    "Batch pair references must bind a Coverage item and target.",
                )
            pair = pair_by_key.get(
                (
                    pair_ref.get("coverage_item_id"),
                    pair_ref.get("target_ref"),
                )
            )
            if pair is None or pair["pair_id"] in assigned:
                raise MaestroError(
                    "EXPERTISE_WORK_PAIR_ASSIGNMENT_INVALID",
                    "Every canonical Coverage pair must be assigned exactly once.",
                )
            assigned.add(pair["pair_id"])
            selected_pair_ids.add(pair["pair_id"])
            selected_pairs.append(pair)
            item_batches.setdefault(
                pair["coverage_item_id"],
                set(),
            ).add(batch_id)
        pack_ids = {pair["pack_id"] for pair in selected_pairs}
        guide_ids = {pair["guide_id"] for pair in selected_pairs}
        if len(pack_ids) != 1 or len(guide_ids) > MAX_GUIDES_PER_BATCH:
            raise MaestroError(
                "EXPERTISE_WORK_BATCH_CAPACITY_INVALID",
                "Each batch must contain one Pack and at most four distinct Guides.",
            )
        raw_dependencies[batch_id] = set(raw["depends_on"])
        batch_pair_ids[batch_id] = selected_pair_ids
        routing_subject_lines = [
            f"Expertise batch responsibility: {raw['responsibility'].strip()}"
        ]
        for item_id in sorted(
            {pair["coverage_item_id"] for pair in selected_pairs}
        ):
            item = coverage_by_id[item_id]
            routing_subject_lines.append(
                (
                    f"Coverage {item_id}: {item.get('summary', '')} "
                    f"Failure if omitted: "
                    f"{item.get('failure_if_omitted', '')} "
                    f"Materiality: {item.get('materiality', '')}."
                )
            )
        routing_subject_lines.extend(
            (
                f"Guide responsibility: {pair['pack_id']}/"
                f"{pair['guide_id']}."
            )
            for pair in selected_pairs
        )
        batches.append(
            {
                "batch_id": batch_id,
                "responsibility": raw["responsibility"].strip(),
                "pack_id": next(iter(pack_ids)),
                "guide_ids": sorted(guide_ids),
                "coverage_pair_ids": sorted(selected_pair_ids),
                "depends_on": sorted(set(raw["depends_on"])),
                "external_prerequisite_item_ids": [],
                "read_only": True,
                "may_spawn": False,
                "model_route": _model_route(
                    "\n".join(routing_subject_lines),
                    route["risk"],
                    [],
                    reviewer,
                    route["model_route"]["host"],
                    execution_unit_id=batch_id,
                    stage_kind="expertise-review",
                ),
            }
        )

    expected_pair_ids = {pair["pair_id"] for pair in pairs}
    if assigned != expected_pair_ids:
        raise MaestroError(
            "EXPERTISE_WORK_PAIR_SET_MISMATCH",
            "Batches must assign every canonical Coverage pair exactly once.",
        )
    for batch_id, dependencies in raw_dependencies.items():
        if batch_id in dependencies or not dependencies.issubset(batch_ids):
            raise MaestroError(
                "EXPERTISE_WORK_DEPENDENCY_INVALID",
                "Batch dependencies must name other declared batches.",
            )

    item_dependencies = {
        item["item_id"]: item["depends_on"]
        for item in coverage["items"]
    }
    for batch in batches:
        required: set[str] = set()
        external_required: set[str] = set()
        batch_id = batch["batch_id"]
        for pair_id in batch_pair_ids[batch_id]:
            pair = next(item for item in pairs if item["pair_id"] == pair_id)
            for dependency_item in item_dependencies[
                pair["coverage_item_id"]
            ]:
                dependency_batches = item_batches.get(
                    dependency_item,
                    set(),
                )
                if dependency_batches:
                    if batch_id in dependency_batches:
                        raise MaestroError(
                            "EXPERTISE_WORK_DEPENDENCY_CO_BATCHED",
                            (
                                f"Batch {batch_id} combines dependent "
                                f"Coverage items {dependency_item} and "
                                f"{pair['coverage_item_id']}; use separate "
                                "batches so the prerequisite can become "
                                "terminal first."
                            ),
                        )
                    required.update(dependency_batches)
                else:
                    external_required.add(dependency_item)
        required.discard(batch_id)
        batch["external_prerequisite_item_ids"] = sorted(
            external_required
        )
        if not required.issubset(raw_dependencies[batch_id]):
            raise MaestroError(
                "EXPERTISE_WORK_DEPENDENCY_BYPASSED",
                f"Batch {batch_id} omits prerequisite batches: {sorted(required - raw_dependencies[batch_id])}.",
            )
    parallel_groups = _topological_groups(raw_dependencies)

    result = {
        "schema_version": EXPERTISE_WORK_PLAN_VERSION,
        "work_plan_id": "",
        "coverage_id": coverage["coverage_id"],
        "source_plan_id": route["plan_id"],
        "goal_digest": coverage["goal_digest"],
        "pairs": pairs,
        "pack_research_requirements": pack_research_requirements,
        "batches": sorted(batches, key=lambda item: item["batch_id"]),
        "parallel_groups": parallel_groups,
        "pair_assignment_policy": "exactly-once",
        "writer_authority": "NONE",
        "writes_performed": False,
    }
    result["work_plan_id"] = _digest(result, "work_plan_id")
    return result


def validate_expertise_work_plan(
    value: Any,
    *,
    repo_path: str | Path,
    goal: str,
    coverage: Any,
    plan: Any,
    research_bundle: dict[str, Any] | None = None,
    expertise_research_bundles: Any = None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    shape_error = _work_plan_shape_error(value)
    if shape_error is not None:
        issues.append(
            {
                "code": "EXPERTISE_WORK_PLAN_INVALID",
                "path": "$",
                "message": shape_error,
            }
        )
    else:
        pair_by_id = {
            pair["pair_id"]: pair
            for pair in value["pairs"]
        }
        draft = {
            "batches": [
                {
                    "batch_id": batch.get("batch_id"),
                    "responsibility": batch.get("responsibility"),
                    "coverage_pairs": [
                        {
                            "coverage_item_id": pair_by_id[pair_id][
                                "coverage_item_id"
                            ],
                            "target_ref": pair_by_id[pair_id][
                                "target_ref"
                            ],
                        }
                        for pair_id in batch.get(
                            "coverage_pair_ids",
                            [],
                        )
                        if pair_id in pair_by_id
                    ],
                    "depends_on": batch.get("depends_on"),
                }
                for batch in value["batches"]
                if isinstance(batch, dict)
            ]
        }
        try:
            expected = build_expertise_work_plan(
                repo_path,
                goal=goal,
                coverage=coverage,
                plan=plan,
                draft=draft,
                research_bundle=research_bundle,
                expertise_research_bundles=expertise_research_bundles,
            )
        except MaestroError as exc:
            issues.append(
                {
                    "code": exc.code,
                    "path": "$",
                    "message": exc.message,
                }
            )
        else:
            compatible_expected = expected
            if value["batches"] and all(
                isinstance(batch, dict)
                and set(batch) == LEGACY_WORK_BATCH_FIELDS
                for batch in value["batches"]
            ):
                compatible_expected = copy.deepcopy(expected)
                for batch in compatible_expected["batches"]:
                    batch.pop("model_route", None)
                compatible_expected["work_plan_id"] = _digest(
                    compatible_expected,
                    "work_plan_id",
                )
            if compatible_expected != value:
                issues.append(
                    {
                        "code": "EXPERTISE_WORK_PLAN_MISMATCH",
                        "path": "$",
                        "message": "Expertise work plan no longer matches Coverage, route, or catalog digests.",
                    }
                )
    legacy_batches = (
        isinstance(value, dict)
        and isinstance(value.get("batches"), list)
        and bool(value["batches"])
        and all(
            isinstance(batch, dict)
            and set(batch) == LEGACY_WORK_BATCH_FIELDS
            for batch in value["batches"]
        )
    )
    return {
        "schema_version": "maestro_expertise_work_plan_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "execution_status": (
            "UPGRADE_REQUIRED"
            if not issues and legacy_batches
            else "READY"
            if not issues
            else "INVALID"
        ),
        "work_plan_id": (
            value.get("work_plan_id")
            if isinstance(value, dict)
            else None
        ),
        "issues": issues,
        "writes_performed": False,
    }


def _validate_packet(
    packet: Any,
    *,
    work_plan: dict[str, Any],
    batch: dict[str, Any],
) -> list[dict[str, str]]:
    fields = {
        "schema_version",
        "packet_digest",
        "work_plan_id",
        "batch_id",
        "status",
        "coverage_pair_ids",
        "criteria_applied",
        "recommendations",
        "evidence_refs",
        "conflicts",
        "unresolved",
        "writes_performed",
    }
    issues: list[dict[str, str]] = []
    if (
        not isinstance(packet, dict)
        or set(packet) != fields
        or packet.get("schema_version") != EXPERTISE_WORK_PACKET_VERSION
        or packet.get("work_plan_id") != work_plan["work_plan_id"]
        or packet.get("batch_id") != batch["batch_id"]
        or packet.get("status") not in {"completed", "blocked", "failed"}
        or packet.get("coverage_pair_ids")
        != batch["coverage_pair_ids"]
        or packet.get("writes_performed") is not False
        or packet.get("packet_digest") != _digest(packet, "packet_digest")
    ):
        issues.append(
            {
                "code": "EXPERTISE_WORK_PACKET_INVALID",
                "path": batch["batch_id"],
                "message": "Expertise work packet identity, status, pairs, or digest is invalid.",
            }
        )
        return issues
    for field in (
        "criteria_applied",
        "recommendations",
        "evidence_refs",
        "conflicts",
        "unresolved",
    ):
        if not _unique_lines(
            packet.get(field),
            allow_empty=field not in {"criteria_applied", "evidence_refs"}
            or packet["status"] != "completed",
        ):
            issues.append(
                {
                    "code": "EXPERTISE_WORK_PACKET_CONTENT_INVALID",
                    "path": f"{batch['batch_id']}.{field}",
                    "message": f"{field} is not a bounded unique list.",
                }
            )
    return issues


def build_expertise_work_closure(
    work_plan: Any,
    packets: Iterable[Any],
) -> dict[str, Any]:
    """Close all read-only Expertise batches before the separate writer."""

    plan_error = _work_plan_shape_error(work_plan)
    if plan_error is not None:
        raise MaestroError(
            "EXPERTISE_WORK_PLAN_INVALID",
            plan_error,
        )
    if work_plan["batches"] and any(
        not isinstance(batch.get("model_route"), dict)
        for batch in work_plan["batches"]
    ):
        raise MaestroError(
            "EXPERTISE_WORK_ROUTE_UPGRADE_REQUIRED",
            (
                "Legacy Expertise batches remain readable but cannot create "
                "a new closure without typed stage model routes."
            ),
        )
    packet_by_batch: dict[str, dict[str, Any]] = {}
    for packet in packets:
        batch_id = (
            packet.get("batch_id") if isinstance(packet, dict) else None
        )
        if not isinstance(batch_id, str) or batch_id in packet_by_batch:
            raise MaestroError(
                "EXPERTISE_WORK_PACKET_SET_INVALID",
                "Provide exactly one packet per Expertise batch.",
            )
        packet_by_batch[batch_id] = packet
    batches = {
        batch["batch_id"]: batch for batch in work_plan["batches"]
    }
    if set(packet_by_batch) != set(batches):
        raise MaestroError(
            "EXPERTISE_WORK_PACKET_SET_INVALID",
            "Provide exactly one packet per Expertise batch.",
        )

    issues: list[dict[str, str]] = []
    summaries: list[dict[str, Any]] = []
    all_conflicts: list[str] = []
    all_unresolved: list[str] = []
    for batch_id in sorted(batches):
        packet = packet_by_batch[batch_id]
        packet_issues = _validate_packet(
            packet,
            work_plan=work_plan,
            batch=batches[batch_id],
        )
        issues.extend(packet_issues)
        if packet_issues:
            continue
        all_conflicts.extend(packet["conflicts"])
        all_unresolved.extend(packet["unresolved"])
        summaries.append(
            {
                "batch_id": batch_id,
                "status": packet["status"],
                "packet_digest": packet["packet_digest"],
                "coverage_pair_ids": packet["coverage_pair_ids"],
                "criteria_applied": packet["criteria_applied"],
                "recommendations": packet["recommendations"],
                "evidence_refs": packet["evidence_refs"],
                "conflicts": packet["conflicts"],
                "unresolved": packet["unresolved"],
            }
        )
    if issues:
        first = issues[0]
        raise MaestroError(first["code"], first["message"])
    ready = (
        all(item["status"] == "completed" for item in summaries)
        and not all_conflicts
        and not all_unresolved
    )
    result = {
        "schema_version": EXPERTISE_WORK_CLOSURE_VERSION,
        "closure_id": "",
        "work_plan_id": work_plan["work_plan_id"],
        "coverage_id": work_plan["coverage_id"],
        "source_plan_id": work_plan["source_plan_id"],
        "status": "READY" if ready else "BLOCKED",
        "expected_pair_ids": sorted(
            pair["pair_id"] for pair in work_plan["pairs"]
        ),
        "terminal_pair_ids": sorted(
            pair_id
            for summary in summaries
            for pair_id in summary["coverage_pair_ids"]
        ),
        "batch_results": summaries,
        "conflicts": list(dict.fromkeys(all_conflicts)),
        "unresolved": list(dict.fromkeys(all_unresolved)),
        "execution_authority": "NONE",
        "writes_performed": False,
    }
    result["closure_id"] = _digest(result, "closure_id")
    return result


def validate_expertise_work_closure(
    value: Any,
    *,
    work_plan: Any,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    expected_fields = {
        "schema_version",
        "closure_id",
        "work_plan_id",
        "coverage_id",
        "source_plan_id",
        "status",
        "expected_pair_ids",
        "terminal_pair_ids",
        "batch_results",
        "conflicts",
        "unresolved",
        "execution_authority",
        "writes_performed",
    }
    work_plan_error = _work_plan_shape_error(work_plan)
    if work_plan_error is not None:
        issues.append(
            {
                "code": "EXPERTISE_WORK_PLAN_INVALID",
                "path": "work_plan",
                "message": work_plan_error,
            }
        )
    if (
        not isinstance(value, dict)
        or set(value) != expected_fields
        or value.get("schema_version")
        != EXPERTISE_WORK_CLOSURE_VERSION
        or value.get("closure_id") != _digest(value, "closure_id")
        or (
            isinstance(work_plan, dict)
            and value.get("work_plan_id") != work_plan.get("work_plan_id")
        )
        or (
            isinstance(work_plan, dict)
            and value.get("coverage_id") != work_plan.get("coverage_id")
        )
        or (
            isinstance(work_plan, dict)
            and value.get("source_plan_id") != work_plan.get("source_plan_id")
        )
        or value.get("execution_authority") != "NONE"
        or value.get("writes_performed") is not False
        or value.get("status") not in {"READY", "BLOCKED"}
        or not _unique_ids(value.get("expected_pair_ids"))
        or not _unique_ids(value.get("terminal_pair_ids"))
        or not _unique_lines(value.get("conflicts"))
        or not _unique_lines(value.get("unresolved"))
    ):
        issues.append(
            {
                "code": "EXPERTISE_WORK_CLOSURE_INVALID",
                "path": "$",
                "message": "Expertise work closure identity or fields are invalid.",
            }
        )
    if not issues:
        expected_pairs = sorted(
            pair["pair_id"] for pair in work_plan["pairs"]
        )
        batch_by_id = {
            batch["batch_id"]: batch for batch in work_plan["batches"]
        }
        results = value.get("batch_results")
        if (
            value.get("expected_pair_ids") != expected_pairs
            or value.get("terminal_pair_ids") != expected_pairs
            or not isinstance(results, list)
            or len(results) != len(batch_by_id)
        ):
            issues.append(
                {
                    "code": "EXPERTISE_WORK_CLOSURE_PAIR_SET_INVALID",
                    "path": "terminal_pair_ids",
                    "message": "Closure must cover every canonical pair exactly once.",
                }
            )
        else:
            seen_batches: set[str] = set()
            seen_pairs: list[str] = []
            valid_results = True
            for result in results:
                batch_id = (
                    result.get("batch_id")
                    if isinstance(result, dict)
                    else None
                )
                batch = batch_by_id.get(batch_id)
                if (
                    batch is None
                    or batch_id in seen_batches
                    or set(result)
                    != {
                        "batch_id",
                        "status",
                        "packet_digest",
                        "coverage_pair_ids",
                        "criteria_applied",
                        "recommendations",
                        "evidence_refs",
                        "conflicts",
                        "unresolved",
                    }
                    or result.get("coverage_pair_ids")
                    != batch["coverage_pair_ids"]
                    or result.get("status")
                    not in {"completed", "blocked", "failed"}
                    or not _sha256(result.get("packet_digest"))
                    or not _unique_lines(
                        result.get("criteria_applied"),
                        allow_empty=result.get("status") != "completed",
                    )
                    or not _unique_lines(result.get("recommendations"))
                    or not _unique_lines(
                        result.get("evidence_refs"),
                        allow_empty=result.get("status") != "completed",
                    )
                    or not _unique_lines(result.get("conflicts"))
                    or not _unique_lines(result.get("unresolved"))
                ):
                    issues.append(
                        {
                            "code": "EXPERTISE_WORK_CLOSURE_BATCH_INVALID",
                            "path": "batch_results",
                            "message": "Closure batch results do not match the work plan.",
                        }
                    )
                    valid_results = False
                    break
                reconstructed_packet = {
                    "schema_version": EXPERTISE_WORK_PACKET_VERSION,
                    "packet_digest": result["packet_digest"],
                    "work_plan_id": work_plan["work_plan_id"],
                    "batch_id": result["batch_id"],
                    "status": result["status"],
                    "coverage_pair_ids": result[
                        "coverage_pair_ids"
                    ],
                    "criteria_applied": result["criteria_applied"],
                    "recommendations": result["recommendations"],
                    "evidence_refs": result["evidence_refs"],
                    "conflicts": result["conflicts"],
                    "unresolved": result["unresolved"],
                    "writes_performed": False,
                }
                packet_issues = _validate_packet(
                    reconstructed_packet,
                    work_plan=work_plan,
                    batch=batch,
                )
                if packet_issues:
                    issues.extend(packet_issues)
                    valid_results = False
                    break
                seen_batches.add(batch_id)
                seen_pairs.extend(result["coverage_pair_ids"])
            if valid_results and (
                sorted(seen_pairs) != expected_pairs
                or len(seen_pairs) != len(set(seen_pairs))
            ):
                issues.append(
                    {
                        "code": "EXPERTISE_WORK_CLOSURE_PAIR_SET_INVALID",
                        "path": "batch_results",
                        "message": "Closure pair results are missing or duplicated.",
                    }
                )
            if valid_results:
                calculated_conflicts = list(
                    dict.fromkeys(
                        conflict
                        for result in results
                        for conflict in result["conflicts"]
                    )
                )
                calculated_unresolved = list(
                    dict.fromkeys(
                        unresolved
                        for result in results
                        for unresolved in result["unresolved"]
                    )
                )
                if (
                    value.get("conflicts") != calculated_conflicts
                    or value.get("unresolved") != calculated_unresolved
                ):
                    issues.append(
                        {
                            "code": "EXPERTISE_WORK_CLOSURE_SUMMARY_INVALID",
                            "path": "conflicts",
                            "message": (
                                "Closure conflicts and unresolved items must "
                                "exactly preserve every terminal batch result."
                            ),
                        }
                    )
                calculated_ready = (
                    all(
                        result["status"] == "completed"
                        for result in results
                    )
                    and not calculated_conflicts
                    and not calculated_unresolved
                )
                if value.get("status") != (
                    "READY" if calculated_ready else "BLOCKED"
                ):
                    issues.append(
                        {
                            "code": "EXPERTISE_WORK_CLOSURE_STATUS_INVALID",
                            "path": "status",
                            "message": "Closure status does not match its terminal batch results.",
                        }
                    )
    return {
        "schema_version": "maestro_expertise_work_closure_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "closure_id": (
            value.get("closure_id")
            if isinstance(value, dict)
            else None
        ),
        "execution_status": (
            value.get("status")
            if not issues and isinstance(value, dict)
            else "INVALID"
        ),
        "issues": issues,
        "writes_performed": False,
    }
