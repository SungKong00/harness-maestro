from __future__ import annotations

import json
import re
from importlib import resources
from typing import Any, Iterable

from .errors import MaestroError
from .util import canonical_json, sha256_text

LENS_FORBIDDEN = {"model", "models", "tools", "permissions", "capabilities", "context_policy"}
EXECUTOR_FORBIDDEN = {"questions", "reject_when", "required_evidence", "trigger"}
LENS_ALLOWED = {
    "schema_version",
    "kind",
    "lens_id",
    "domain",
    "summary",
    "priority",
    "triggers",
    "questions",
    "required_evidence",
    "reject_when",
    "finding_limits",
    "output",
}
EXECUTOR_ALLOWED = {
    "schema_version",
    "kind",
    "executor_id",
    "summary",
    "model_policy",
    "capabilities",
    "forbidden_capabilities",
    "context_policy",
    "accepts",
    "returns",
}
DEPARTMENT_ALLOWED = {
    "schema_version",
    "kind",
    "department_id",
    "summary",
    "candidate_lenses",
    "routing",
    "deliberation",
}
ADAPTER_ALLOWED = {
    "schema_version",
    "kind",
    "adapter_id",
    "summary",
    "version",
    "detection",
    "authority_policy",
    "writes",
}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REGISTRY_FORMAT_VERSION = 1
MODEL_CLASSES = ("economy", "balanced", "frontier")
MODEL_CLASS_CONFIG = {
    "economy": {
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "fallback": "gpt-5.6-terra with low reasoning",
    },
    "balanced": {
        "model": "gpt-5.6-terra",
        "reasoning_effort": "medium",
        "fallback": "gpt-5.6-sol with medium reasoning",
    },
    "frontier": {
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
        "fallback": "NEEDS_DECISION when gpt-5.6-sol is unavailable",
    },
}
def resource_root() -> Any:
    return resources.files("maestro.resources")


def _json_files(relative: str) -> list[Any]:
    root = resource_root().joinpath(relative)
    return sorted(
        (item for item in root.iterdir() if item.name.endswith(".json")),
        key=lambda item: item.name,
    )


def _load_file(item: Any) -> dict[str, Any]:
    try:
        value = json.loads(item.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MaestroError("REGISTRY_JSON_INVALID", f"Invalid registry JSON: {item.name}") from exc
    if not isinstance(value, dict):
        raise MaestroError("REGISTRY_JSON_INVALID", f"Registry item must be an object: {item.name}")
    return value


def load_registry() -> dict[str, list[dict[str, Any]]]:
    return {
        "lenses": [_load_file(item) for item in _json_files("registry/lenses")],
        "executors": [_load_file(item) for item in _json_files("registry/executors")],
        "departments": [_load_file(item) for item in _json_files("registry/departments")],
        "adapters": [_load_file(item) for item in _json_files("registry/adapters")],
    }


def load_domain_index_document() -> dict[str, Any]:
    item = resource_root().joinpath("registry/lens-domains.json")
    return _load_file(item)


def _domain_index_errors(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if set(value) != {"schema_version", "domains"}:
        errors.append("domain index fields are invalid")
    if value.get("schema_version") != "maestro_domain_index_v1":
        errors.append("domain index schema_version is invalid")
    domains = value.get("domains")
    if not isinstance(domains, list):
        errors.append("domain index must contain a domains list")
    return errors


def load_domain_index() -> list[dict[str, str]]:
    value = load_domain_index_document()
    errors = _domain_index_errors(value)
    if errors:
        raise MaestroError("REGISTRY_INVALID", "; ".join(errors))
    return value["domains"]


def registry_digest() -> str:
    registry = load_registry()
    return sha256_text(
        canonical_json(
            {
                "domain_index": load_domain_index_document(),
                "registry": registry,
            }
        )
    )


def definition_digest_maps() -> dict[str, dict[str, str]]:
    registry = load_registry()
    return {
        "lenses": {
            item["lens_id"]: sha256_text(canonical_json(item))
            for item in registry["lenses"]
        },
        "executors": {
            item["executor_id"]: sha256_text(canonical_json(item))
            for item in registry["executors"]
        },
    }


def _required(item: dict[str, Any], fields: Iterable[str], kind: str) -> list[str]:
    return [f"{kind} missing required field: {field}" for field in fields if field not in item]


def _string_list(value: Any, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and ID_PATTERN.fullmatch(value) is not None


def _unique_string_list(value: Any, *, nonempty: bool = False) -> bool:
    return (
        _string_list(value, nonempty=nonempty)
        and len(set(value)) == len(value)
    )


def validate_registry(registry: dict[str, list[dict[str, Any]]] | None = None) -> list[str]:
    registry = load_registry() if registry is None else registry
    errors: list[str] = []
    lens_ids: set[str] = set()
    executor_ids: set[str] = set()
    department_ids: set[str] = set()
    adapter_ids: set[str] = set()

    required_groups = {"lenses", "executors", "departments", "adapters"}
    missing_groups = sorted(required_groups - set(registry))
    extra_groups = sorted(set(registry) - required_groups)
    if missing_groups:
        errors.append(f"registry missing groups: {', '.join(missing_groups)}")
    if extra_groups:
        errors.append(f"registry has unsupported groups: {', '.join(extra_groups)}")
    if missing_groups:
        return errors
    if any(not isinstance(registry[group], list) for group in required_groups):
        return errors + ["every registry group must be a list"]

    try:
        domain_index = load_domain_index_document()
        domain_index_errors = _domain_index_errors(domain_index)
        if domain_index_errors:
            return errors + domain_index_errors
        domain_items = domain_index["domains"]
    except MaestroError as exc:
        return errors + [exc.message]
    domain_ids: set[str] = set()
    for domain in domain_items:
        if not isinstance(domain, dict):
            errors.append("domain index entries must be objects")
            continue
        if set(domain) != {"domain", "summary"}:
            errors.append("domain index entry fields are invalid")
        domain_id = domain.get("domain")
        if not _valid_id(domain_id):
            errors.append("domain index entry is missing domain")
            continue
        if domain_id in domain_ids:
            errors.append(f"duplicate lens domain: {domain_id}")
        domain_ids.add(domain_id)
        if not isinstance(domain.get("summary"), str) or not domain["summary"].strip():
            errors.append(f"lens domain {domain_id} is missing a summary")

    for lens in registry["lenses"]:
        if not isinstance(lens, dict):
            errors.append("lens entries must be objects")
            continue
        errors.extend(
            _required(
                lens,
                ("schema_version", "kind", "lens_id", "domain", "summary", "triggers", "questions"),
                "lens",
            )
        )
        if lens.get("kind") != "lens":
            errors.append(f"lens {lens.get('lens_id', '?')} has kind={lens.get('kind')!r}")
        if lens.get("schema_version") != "maestro_lens_v1":
            errors.append(f"lens {lens.get('lens_id', '?')} has unsupported schema_version")
        unexpected = sorted(set(lens) - LENS_ALLOWED)
        if unexpected:
            errors.append(
                f"lens {lens.get('lens_id', '?')} has unsupported fields: {', '.join(unexpected)}"
            )
        forbidden = sorted(LENS_FORBIDDEN.intersection(lens))
        if forbidden:
            errors.append(
                f"lens {lens.get('lens_id', '?')} mixes executor fields: {', '.join(forbidden)}"
            )
        lens_id = lens.get("lens_id")
        if not _valid_id(lens_id):
            errors.append(f"lens {lens_id or '?'} lens_id is invalid")
        else:
            if lens_id in lens_ids:
                errors.append(f"duplicate lens_id: {lens_id}")
            lens_ids.add(lens_id)
        if not isinstance(lens.get("summary"), str) or not lens["summary"].strip():
            errors.append(f"lens {lens_id or '?'} summary must be a non-empty string")
        if lens.get("domain") not in domain_ids:
            errors.append(
                f"lens {lens_id or '?'} references missing domain: {lens.get('domain')!r}"
            )
        for field in ("triggers", "questions", "required_evidence", "reject_when"):
            if not _string_list(lens.get(field), nonempty=True):
                errors.append(f"lens {lens_id or '?'} {field} must be a non-empty string list")
        if not _unique_string_list(lens.get("triggers"), nonempty=True):
            errors.append(f"lens {lens_id or '?'} triggers must be unique")
        if lens.get("output") != "FindingPacket":
            errors.append(f"lens {lens_id or '?'} output must be FindingPacket")
        if not isinstance(lens.get("priority"), int) or isinstance(lens.get("priority"), bool):
            errors.append(f"lens {lens_id or '?'} priority must be an integer")
        limits = lens.get("finding_limits", {})
        if isinstance(limits, dict) and set(limits) != {
            "max_findings",
            "minimum_severity",
        }:
            errors.append(f"lens {lens_id} finding_limits fields are invalid")
        max_findings = limits.get("max_findings") if isinstance(limits, dict) else None
        if (
            not isinstance(max_findings, int)
            or isinstance(max_findings, bool)
            or max_findings not in range(1, 6)
        ):
            errors.append(f"lens {lens_id} max_findings must be between 1 and 5")
        if not isinstance(limits, dict) or limits.get("minimum_severity") not in {
            "medium",
            "high",
            "critical",
        }:
            errors.append(f"lens {lens_id} minimum_severity is invalid")

    for executor in registry["executors"]:
        if not isinstance(executor, dict):
            errors.append("executor entries must be objects")
            continue
        errors.extend(
            _required(
                executor,
                (
                    "schema_version",
                    "kind",
                    "executor_id",
                    "summary",
                    "capabilities",
                    "context_policy",
                    "accepts",
                    "returns",
                ),
                "executor",
            )
        )
        if executor.get("kind") != "executor":
            errors.append(
                f"executor {executor.get('executor_id', '?')} has kind={executor.get('kind')!r}"
            )
        if executor.get("schema_version") != "maestro_executor_v1":
            errors.append(
                f"executor {executor.get('executor_id', '?')} has unsupported schema_version"
            )
        unexpected = sorted(set(executor) - EXECUTOR_ALLOWED)
        if unexpected:
            errors.append(
                f"executor {executor.get('executor_id', '?')} has unsupported fields: "
                f"{', '.join(unexpected)}"
            )
        forbidden = sorted(EXECUTOR_FORBIDDEN.intersection(executor))
        if forbidden:
            errors.append(
                f"executor {executor.get('executor_id', '?')} mixes lens fields: {', '.join(forbidden)}"
            )
        executor_id = executor.get("executor_id")
        if not _valid_id(executor_id):
            errors.append(f"executor {executor_id or '?'} executor_id is invalid")
        else:
            if executor_id in executor_ids:
                errors.append(f"duplicate executor_id: {executor_id}")
            executor_ids.add(executor_id)
        if not isinstance(executor.get("summary"), str) or not executor["summary"].strip():
            errors.append(
                f"executor {executor_id or '?'} summary must be a non-empty string"
            )
        for field in ("capabilities", "forbidden_capabilities", "accepts", "returns"):
            if not _unique_string_list(executor.get(field), nonempty=True):
                errors.append(
                    f"executor {executor_id or '?'} {field} must be a unique non-empty string list"
                )
        capabilities = executor.get("capabilities")
        forbidden_capabilities = executor.get("forbidden_capabilities")
        if isinstance(capabilities, list) and isinstance(
            forbidden_capabilities,
            list,
        ):
            contradictory = sorted(
                set(capabilities).intersection(forbidden_capabilities)
            )
            if contradictory:
                errors.append(
                    f"executor {executor_id or '?'} allows and forbids: "
                    f"{', '.join(contradictory)}"
                )
        context_policy = executor.get("context_policy")
        if not isinstance(context_policy, dict):
            errors.append(f"executor {executor_id or '?'} context_policy must be an object")
        elif (
            set(context_policy)
            != {
                "fresh_context_supported",
                "return_packet_only",
                "hide_other_lens_conclusions",
            }
            or any(not isinstance(value, bool) for value in context_policy.values())
        ):
            errors.append(f"executor {executor_id or '?'} context_policy is invalid")
        model_policy = executor.get("model_policy")
        if not isinstance(model_policy, dict) or set(model_policy) != {
            "default_class",
            "allowed_classes",
            "default_reasoning_effort",
            "maximum_auto_reasoning_effort",
            "automatic_escalations",
            "fixed_model",
        }:
            errors.append(f"executor {executor_id or '?'} model_policy is invalid")
        else:
            allowed_classes = model_policy.get("allowed_classes")
            default_class = model_policy.get("default_class")
            if (
                not _unique_string_list(allowed_classes, nonempty=True)
                or any(item not in MODEL_CLASSES for item in allowed_classes)
                or default_class not in allowed_classes
            ):
                errors.append(
                    f"executor {executor_id or '?'} model classes are invalid"
                )
            if model_policy.get("default_reasoning_effort") not in {
                "low",
                "medium",
                "high",
            }:
                errors.append(
                    f"executor {executor_id or '?'} default reasoning effort is invalid"
                )
            if model_policy.get("maximum_auto_reasoning_effort") not in {
                "medium",
                "high",
                "xhigh",
            }:
                errors.append(
                    f"executor {executor_id or '?'} maximum reasoning effort is invalid"
                )
            if model_policy.get("automatic_escalations") != 1:
                errors.append(
                    f"executor {executor_id or '?'} automatic escalations must equal 1"
                )
            if model_policy.get("fixed_model") is not False:
                errors.append(
                    f"executor {executor_id or '?'} fixed_model must be false"
                )

    for department in registry["departments"]:
        if not isinstance(department, dict):
            errors.append("department entries must be objects")
            continue
        errors.extend(
            _required(
                department,
                (
                    "schema_version",
                    "kind",
                    "department_id",
                    "candidate_lenses",
                    "routing",
                    "deliberation",
                ),
                "department",
            )
        )
        if department.get("kind") != "department":
            errors.append(
                f"department {department.get('department_id', '?')} has kind={department.get('kind')!r}"
            )
        if department.get("schema_version") != "maestro_department_v1":
            errors.append(
                f"department {department.get('department_id', '?')} has unsupported schema_version"
            )
        unexpected = sorted(set(department) - DEPARTMENT_ALLOWED)
        if unexpected:
            errors.append(
                f"department {department.get('department_id', '?')} has unsupported fields: "
                f"{', '.join(unexpected)}"
            )
        department_id = department.get("department_id")
        if not _valid_id(department_id):
            errors.append(f"department {department_id or '?'} department_id is invalid")
        else:
            if department_id in department_ids:
                errors.append(f"duplicate department_id: {department_id}")
            department_ids.add(department_id)
        if not isinstance(department.get("summary"), str) or not department["summary"].strip():
            errors.append(
                f"department {department_id or '?'} summary must be a non-empty string"
            )
        if not _string_list(department.get("candidate_lenses"), nonempty=True):
            errors.append(
                f"department {department_id or '?'} candidate_lenses must be a non-empty string list"
            )
        candidate_lenses = department.get("candidate_lenses", [])
        if (
            isinstance(candidate_lenses, list)
            and all(isinstance(item, str) for item in candidate_lenses)
            and len(set(candidate_lenses)) != len(candidate_lenses)
        ):
            errors.append(f"department {department_id or '?'} candidate_lenses must be unique")
        for lens_id in candidate_lenses if isinstance(candidate_lenses, list) else []:
            if lens_id not in lens_ids:
                errors.append(
                    f"department {department.get('department_id', '?')} references missing lens: {lens_id}"
                )
        routing = department.get("routing", {})
        if not isinstance(routing, dict):
            errors.append("department routing must be an object")
            routing = {}
        elif set(routing) != {
            "default_max_lenses",
            "high_risk_max_lenses",
            "load_all",
            "lens_count_implies_agent_count",
        }:
            errors.append("department routing fields are invalid")
        default_max = routing.get("default_max_lenses")
        high_max = routing.get("high_risk_max_lenses")
        if not isinstance(default_max, int) or isinstance(default_max, bool) or not 0 <= default_max <= 2:
            errors.append("department default_max_lenses must be an integer between 0 and 2")
        if not isinstance(high_max, int) or isinstance(high_max, bool) or not 0 <= high_max <= 3:
            errors.append("department high_risk_max_lenses must be an integer between 0 and 3")
        if isinstance(default_max, int) and isinstance(high_max, int) and high_max < default_max:
            errors.append("department high_risk_max_lenses must be >= default_max_lenses")
        if routing.get("load_all") is not False:
            errors.append("department load_all must be false")
        if routing.get("lens_count_implies_agent_count") is not False:
            errors.append("department lens_count_implies_agent_count must be false")
        deliberation = department.get("deliberation", {})
        if not isinstance(deliberation, dict):
            errors.append("department deliberation must be an object")
            deliberation = {}
        elif set(deliberation) != {
            "blind_first",
            "free_form_debate",
            "majority_vote",
            "conflict_only_rebuttal",
            "max_rebuttal_rounds",
            "stop_on_no_new_evidence",
            "human_gate_for_irreversible",
        }:
            errors.append("department deliberation fields are invalid")
        if deliberation.get("blind_first") is not True:
            errors.append("department blind_first must be true")
        if deliberation.get("majority_vote") is not False:
            errors.append("department majority_vote must be false")
        if deliberation.get("free_form_debate") is not False:
            errors.append("department free_form_debate must be false")
        if deliberation.get("conflict_only_rebuttal") is not True:
            errors.append("department conflict_only_rebuttal must be true")
        max_rebuttal_rounds = deliberation.get("max_rebuttal_rounds")
        if (
            not isinstance(max_rebuttal_rounds, int)
            or isinstance(max_rebuttal_rounds, bool)
            or max_rebuttal_rounds != 1
        ):
            errors.append("department max_rebuttal_rounds must equal 1")
        if deliberation.get("stop_on_no_new_evidence") is not True:
            errors.append("department stop_on_no_new_evidence must be true")
        if deliberation.get("human_gate_for_irreversible") is not True:
            errors.append("department human_gate_for_irreversible must be true")

    for adapter in registry["adapters"]:
        if not isinstance(adapter, dict):
            errors.append("adapter entries must be objects")
            continue
        errors.extend(
            _required(
                adapter,
                (
                    "schema_version",
                    "kind",
                    "adapter_id",
                    "summary",
                    "version",
                    "detection",
                    "authority_policy",
                    "writes",
                ),
                "adapter",
            )
        )
        if adapter.get("kind") != "adapter":
            errors.append(
                f"adapter {adapter.get('adapter_id', '?')} has kind={adapter.get('kind')!r}"
            )
        if adapter.get("schema_version") != "maestro_adapter_v1":
            errors.append(
                f"adapter {adapter.get('adapter_id', '?')} has unsupported schema_version"
            )
        unexpected = sorted(set(adapter) - ADAPTER_ALLOWED)
        if unexpected:
            errors.append(
                f"adapter {adapter.get('adapter_id', '?')} has unsupported fields: "
                f"{', '.join(unexpected)}"
            )
        adapter_id = adapter.get("adapter_id")
        if not _valid_id(adapter_id):
            errors.append(f"adapter {adapter_id or '?'} adapter_id is invalid")
        else:
            if adapter_id in adapter_ids:
                errors.append(f"duplicate adapter_id: {adapter_id}")
            adapter_ids.add(adapter_id)
        if not isinstance(adapter.get("summary"), str) or not adapter["summary"].strip():
            errors.append(f"adapter {adapter_id or '?'} summary must be a non-empty string")
        version = adapter.get("version")
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version < 1
        ):
            errors.append(f"adapter {adapter_id or '?'} version must be a positive integer")
        detection = adapter.get("detection", {})
        if not isinstance(detection, dict):
            errors.append(f"adapter {adapter_id or '?'} detection must be an object")
        elif (
            set(detection) != {
                "mode",
                "network",
                "subprocess_project_code",
                "markers",
            }
            or
            detection.get("mode") != "static"
            or detection.get("network") is not False
            or detection.get("subprocess_project_code") is not False
            or not _unique_string_list(detection.get("markers"))
        ):
            errors.append(f"adapter {adapter_id or '?'} v0 detection must be static and offline")
        authority_policy = adapter.get("authority_policy")
        if (
            not isinstance(authority_policy, dict)
            or set(authority_policy)
            != {
                "default",
                "external_authority_requires_approval",
                "dual_editable_master",
            }
            or authority_policy.get("default") != "markdown"
            or authority_policy.get("external_authority_requires_approval") is not True
            or authority_policy.get("dual_editable_master") is not False
        ):
            errors.append(f"adapter {adapter_id or '?'} authority policy is unsafe")
        writes = adapter.get("writes")
        if (
            not isinstance(writes, dict)
            or set(writes)
            != {
                "preview_required",
                "force_supported",
                "delete_supported",
            }
            or writes.get("preview_required") is not True
            or writes.get("force_supported") is not False
            or writes.get("delete_supported") is not False
        ):
            errors.append(f"adapter {adapter_id or '?'} write policy is unsafe")

    return errors


def _trigger_matches(trigger: str, folded_goal: str) -> bool:
    folded_trigger = trigger.casefold()
    if any(ord(character) > 127 for character in folded_trigger):
        return folded_trigger in folded_goal
    return (
        re.search(
            rf"(?<![a-z0-9]){re.escape(folded_trigger)}(?![a-z0-9])",
            folded_goal,
        )
        is not None
    )


def _goal_has(goal: str, terms: Iterable[str]) -> bool:
    folded = goal.casefold()
    return any(_trigger_matches(term, folded) for term in terms)


def _classify_model_task(
    goal: str,
    risk: str,
    lens_ids: list[str],
) -> tuple[str, str, str]:
    folded = goal.casefold()
    mutation_intent = _goal_has(
        goal,
        (
            "add",
            "change",
            "delete",
            "fix",
            "implement",
            "migrate",
            "modify",
            "remove",
            "update",
            "추가",
            "변경",
            "삭제",
            "수정",
            "구현",
            "마이그레이션",
        ),
    )
    deterministic_command = (
        re.search(
            r"\b(?:run|execute)\b.*\b(?:tests?|lint|build|schema checks?)\b",
            folded,
        )
        is not None
        or any(
            phrase in folded
            for phrase in (
                "테스트 실행",
                "린트 실행",
                "빌드 실행",
                "스키마 검사",
            )
        )
    )
    if deterministic_command and not mutation_intent:
        return (
            "deterministic-verification",
            "none",
            "Deterministic project commands, not model judgment, decide the result.",
        )
    high_impact_terms = (
        "auth",
        "authentication",
        "authorization",
        "permission",
        "security",
        "migration",
        "transaction",
        "data integrity",
        "data loss",
        "irreversible",
        "tenant",
        "material conflict",
        "important conflict",
        "architecture conflict",
        "인증",
        "인가",
        "권한",
        "보안",
        "마이그레이션",
        "트랜잭션",
        "데이터 무결성",
        "데이터 손실",
        "비가역",
        "중대한 충돌",
        "중요한 충돌",
    )
    high_impact_lenses = {
        "auth-boundary",
        "data-integrity",
        "transaction-concurrency",
    }
    if (
        _goal_has(goal, high_impact_terms)
        or bool(high_impact_lenses.intersection(lens_ids))
        or risk == "critical"
    ):
        return (
            "high-impact-judgment",
            "frontier",
            "Security, data, transaction, migration, irreversible, or material-conflict risk raises failure cost.",
        )
    if _goal_has(
        goal,
        (
            "metadata",
            "frontmatter",
            "extract metadata",
            "classify files",
            "format conversion",
            "메타데이터",
            "분류",
            "형식 변환",
        ),
    ):
        return (
            "metadata-extraction",
            "economy",
            "The task is bounded, mechanical, and directly verifiable.",
        )
    if _goal_has(
        goal,
        (
            "rename",
            "format",
            "sort",
            "generated fixtures",
            "mechanical",
            "이름 변경",
            "포맷",
            "정렬",
        ),
    ):
        return (
            "mechanical-change",
            "economy",
            "The change is repetitive and has a deterministic verification path.",
        )
    if _goal_has(
        goal,
        (
            "review",
            "analyze",
            "research",
            "architecture",
            "compare",
            "검토",
            "분석",
            "리서치",
            "아키텍처",
            "비교",
        ),
    ):
        return (
            "general-analysis",
            "balanced",
            "The task needs ordinary repository reasoning without a high-impact boundary.",
        )
    return (
        "general-implementation",
        "default",
        "General implementation uses the Executor default and deterministic verification.",
    )


def _model_route(
    goal: str,
    risk: str,
    lens_ids: list[str],
    executor: dict[str, Any],
) -> dict[str, Any]:
    task_class, selected_class, selection_reason = _classify_model_task(
        goal,
        risk,
        lens_ids,
    )
    policy = executor["model_policy"]
    if selected_class == "none":
        return {
            "executor": executor["executor_id"],
            "task_class": task_class,
            "risk": risk,
            "selected_class": None,
            "selected_model": None,
            "reasoning_effort": None,
            "selection_reason": selection_reason,
            "escalation_allowed": False,
            "fallback": "Use the actual command result.",
        }
    if selected_class == "default":
        selected_class = policy["default_class"]
        selection_reason = (
            f"{selection_reason} Executor {executor['executor_id']} defaults to "
            f"{selected_class}."
        )

    allowed_classes = policy["allowed_classes"]
    if selected_class not in allowed_classes:
        raise MaestroError(
            "MODEL_CLASS_UNAVAILABLE",
            f"Executor {executor['executor_id']} does not allow {selected_class}.",
        )
    config = MODEL_CLASS_CONFIG[selected_class]
    reasoning_effort = (
        policy["default_reasoning_effort"]
        if selected_class == policy["default_class"]
        else config["reasoning_effort"]
    )
    if (
        _goal_has(
            goal,
            (
                "material conflict",
                "important conflict",
                "architecture conflict",
                "중대한 충돌",
                "중요한 충돌",
            ),
        )
        and selected_class == "frontier"
        and risk == "critical"
        and policy["maximum_auto_reasoning_effort"] == "xhigh"
    ):
        reasoning_effort = "xhigh"
    return {
        "executor": executor["executor_id"],
        "task_class": task_class,
        "risk": risk,
        "selected_class": selected_class,
        "selected_model": config["model"],
        "reasoning_effort": reasoning_effort,
        "selection_reason": selection_reason,
        "escalation_allowed": (
            policy["automatic_escalations"] == 1
            and selected_class != "frontier"
        ),
        "fallback": config["fallback"],
    }


def route_goal(
    goal: str,
    risk: str,
    explicit_lenses: list[str] | None = None,
    department_id: str = "software-development",
    conflict_evidence: str | None = None,
) -> dict[str, Any]:
    registry = load_registry()
    errors = validate_registry(registry)
    if errors:
        raise MaestroError("REGISTRY_INVALID", "; ".join(errors))

    departments = {
        item["department_id"]: item
        for item in registry["departments"]
    }
    if department_id not in departments:
        raise MaestroError("DEPARTMENT_UNKNOWN", f"Unknown department: {department_id}")
    department = departments[department_id]
    material_conflict = _goal_has(
        goal,
        (
            "material conflict",
            "important conflict",
            "architecture conflict",
            "중대한 충돌",
            "중요한 충돌",
        ),
    )
    if not material_conflict and conflict_evidence is not None:
        raise MaestroError(
            "CONFLICT_REASON_REQUIRED",
            "Conflict evidence is accepted only for a material-conflict route.",
        )
    if material_conflict and (
        explicit_lenses is None
        or len(dict.fromkeys(explicit_lenses)) != 1
    ):
        raise MaestroError(
            "CONFLICT_SCOPE_INVALID",
            "A material-conflict reroute must target exactly one explicit Lens.",
        )
    if material_conflict and (
        conflict_evidence is None or not conflict_evidence.strip()
    ):
        raise MaestroError(
            "CONFLICT_EVIDENCE_REQUIRED",
            "A material-conflict reroute requires new bounded evidence.",
        )
    all_lenses = {item["lens_id"]: item for item in registry["lenses"]}
    candidate_ids = set(department["candidate_lenses"])
    lenses = {
        lens_id: all_lenses[lens_id]
        for lens_id in department["candidate_lenses"]
    }
    preliminary_task_class = _classify_model_task(goal, risk, [])[0]
    if explicit_lenses:
        unknown = sorted(set(explicit_lenses) - set(all_lenses))
        if unknown:
            raise MaestroError("LENS_UNKNOWN", f"Unknown lens IDs: {', '.join(unknown)}")
        outside_department = sorted(set(explicit_lenses) - candidate_ids)
        if outside_department:
            raise MaestroError(
                "LENS_NOT_IN_DEPARTMENT",
                f"Department {department_id} does not admit: {', '.join(outside_department)}",
            )
        selected = [lenses[item] for item in dict.fromkeys(explicit_lenses)]
    elif preliminary_task_class == "deterministic-verification":
        selected = []
    else:
        folded = goal.casefold()
        ranked: list[tuple[int, int, str, dict[str, Any]]] = []
        for lens in lenses.values():
            score = sum(1 for trigger in lens["triggers"] if _trigger_matches(trigger, folded))
            if score:
                ranked.append((score, int(lens.get("priority", 0)), lens["lens_id"], lens))
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        selected = [item[3] for item in ranked]

    routing = department["routing"]
    if risk == "low":
        depth, maximum = "fast", min(1, routing["default_max_lenses"])
    elif risk == "medium":
        depth, maximum = "standard", routing["default_max_lenses"]
    elif risk in {"high", "critical"}:
        depth, maximum = "deep", routing["high_risk_max_lenses"]
    else:
        raise MaestroError("RISK_INVALID", f"Unsupported risk: {risk}")

    if explicit_lenses and len(selected) > maximum:
        raise MaestroError(
            "LENS_LIMIT_EXCEEDED",
            f"Risk {risk} permits at most {maximum} Lens cards; split the review or raise the justified risk",
        )
    not_selected = [item["lens_id"] for item in selected[maximum:]]
    selected = selected[:maximum]
    lens_ids = [item["lens_id"] for item in selected]
    if not lens_ids:
        binding = {
            "executor": "implementation-engineer",
            "runs": 1,
            "fresh_context_per_lens": False,
        }
        deliberation = "none"
    elif depth == "fast":
        binding = {
            "executor": "implementation-engineer",
            "runs": 1,
            "fresh_context_per_lens": False,
        }
        deliberation = "none"
    elif depth == "standard":
        binding = {"executor": "lens-reviewer", "runs": 1, "fresh_context_per_lens": False}
        deliberation = "combined_review"
    else:
        binding = {
            "executor": "lens-reviewer",
            "runs": len(lens_ids),
            "fresh_context_per_lens": True,
        }
        deliberation = "independent_blind_review" if len(lens_ids) > 1 else "single_review"
    executors = {
        item["executor_id"]: item
        for item in registry["executors"]
    }
    model_route = _model_route(
        goal,
        risk,
        lens_ids,
        executors[binding["executor"]],
    )

    return {
        "schema_version": "maestro_route_v1",
        "goal": goal,
        "department": department_id,
        "risk": risk,
        "depth": depth,
        "selected_lenses": lens_ids,
        "selected_domains": list(dict.fromkeys(item["domain"] for item in selected)),
        "lens_cards": selected,
        "selection_reasons": {
            item["lens_id"]: (
                ["explicit"]
                if explicit_lenses
                else [
                    trigger
                    for trigger in item["triggers"]
                    if _trigger_matches(trigger, goal.casefold())
                ]
            )
            for item in selected
        },
        "selection_trace": {
            "catalog_lenses": len(lenses),
            "registry_lenses": len(all_lenses),
            "returned_lens_bodies": len(selected),
            "not_selected_due_to_limit": not_selected,
            "load_all": False,
        },
        "binding": binding,
        "model_route": model_route,
        "deliberation": {
            "mode": deliberation,
            **department["deliberation"],
        },
    }
