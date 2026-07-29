from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .matching import searchable_terms, term_matches
from .util import canonical_json, sha256_text

MODEL_ROUTE_VERSION = "maestro_stage_model_route_v1"
EXECUTION_KINDS = {"model", "deterministic"}
STAGE_KINDS = {
    "implementation",
    "semantic-review",
    "research",
    "semantic-verification",
    "deterministic-verification",
    "specialist-review",
    "intermediate-synthesis",
    "technical-feasibility",
    "final-synthesis",
    "expertise-review",
}
REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}

MODEL_ROUTE_FIELDS = {
    "schema_version",
    "model_route_id",
    "execution_unit_id",
    "stage_kind",
    "execution_kind",
    "quality_profile",
    "executor",
    "task_class",
    "risk",
    "host",
    "selected_class",
    "selected_model",
    "reasoning_effort",
    "selection_reason",
    "quality_floor",
    "escalation_allowed",
    "fallback",
    "fallback_route",
}
LEGACY_MODEL_ROUTE_FIELDS = {
    "executor",
    "task_class",
    "risk",
    "host",
    "selected_class",
    "selected_model",
    "reasoning_effort",
    "selection_reason",
    "escalation_allowed",
    "fallback",
}
QUALITY_FLOOR_FIELDS = {"acceptable_routes", "failure_action"}
QUALITY_ROUTE_FIELDS = {"selected_class", "reasoning_effort"}
FALLBACK_ROUTE_FIELDS = {
    "selected_class",
    "selected_model",
    "reasoning_effort",
    "trigger",
}

_HIGH_IMPACT_LENSES = {
    "auth-boundary",
    "data-integrity",
    "transaction-concurrency",
}
_HIGH_IMPACT_TERMS = (
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
    "인증",
    "인가",
    "권한",
    "보안",
    "마이그레이션",
    "트랜잭션",
    "데이터 무결성",
    "데이터 손실",
    "비가역",
)
_CONFLICT_TERMS = (
    "material conflict",
    "important conflict",
    "architecture conflict",
    "중대한 충돌",
    "중요한 충돌",
)
_ARCHITECTURE_TERMS = (
    "architecture",
    "system design",
    "design decision",
    "cross-service",
    "아키텍처",
    "시스템 설계",
    "설계 결정",
)
_ARCHITECTURE_IMPLEMENTATION_TERMS = (
    "architecture decision",
    "architecture judgment",
    "design the architecture",
    "choose the architecture",
    "아키텍처 결정",
    "아키텍처 판단",
    "아키텍처 설계",
    "설계 결정을 구현",
)
_COMPLEX_IMPLEMENTATION_TERMS = (
    "complex implementation",
    "difficult implementation",
    "hard implementation",
    "complex algorithm",
    "difficult algorithm",
    "multi-service coordination",
    "cross-module refactor",
    "고난도 구현",
    "어려운 구현",
    "복잡한 구현",
    "복잡한 알고리즘",
    "다중 서비스 조정",
    "여러 모듈에 걸친 리팩터링",
)
_DIFFICULTY_MARKERS = (
    "difficult",
    "hard",
    "complex",
    "intricate",
    "nontrivial",
    "subtle",
    "challenging",
    "고난도",
    "어려운",
    "복잡한",
    "까다로운",
    "미묘한",
)
_IMPLEMENTATION_COMPLEXITY_CONTEXT = (
    "implement",
    "implementation",
    "rewrite",
    "refactor",
    "algorithm",
    "compiler",
    "optimizer",
    "parser",
    "state machine",
    "invariant",
    "cross-cutting",
    "cross-module",
    "distributed",
    "concurrency",
    "coordination",
    "구현",
    "재작성",
    "리팩터링",
    "알고리즘",
    "컴파일러",
    "최적화기",
    "파서",
    "상태 머신",
    "불변식",
    "여러 모듈",
    "분산",
    "동시성",
    "조정",
)
_SEMANTIC_COMPLEXITY_CONTEXT = (
    "review",
    "research",
    "investigate",
    "analyze",
    "analysis",
    "compare",
    "synthesize",
    "synthesis",
    "reason",
    "judgment",
    "proof",
    "causal",
    "invariant",
    "semantics",
    "검토",
    "리서치",
    "연구",
    "조사",
    "분석",
    "비교",
    "종합",
    "판단",
    "증명",
    "인과",
    "불변식",
    "의미론",
)
_NEGATED_DIFFICULTY_PATTERNS = (
    r"\bnot\s+(?:(?:a|an)\s+)?(?:difficult|hard|complex|intricate|challenging)\b",
    r"\b(?:is|should be)\s+not\s+(?:(?:a|an)\s+)?(?:difficult|hard|complex)\b",
    r"\bavoid(?:ing)?\s+(?:(?:a|an)\s+)?(?:difficult|hard|complex|intricate|challenging)\b",
    r"\bdo\s+not\s+use\s+(?:(?:a|an)\s+)?(?:difficult|hard|complex|intricate|challenging)\b",
    r"\bwithout\s+(?:(?:a|an)\s+)?(?:difficult|hard|complex|intricate|challenging)\b",
    r"(?:어렵|복잡|까다롭)지\s*않",
    r"(?:어려운|복잡한|까다로운)\s+(?:구현|알고리즘|판단)(?:을|를)?\s*(?:피하|쓰지|사용하지)",
)
_MIXED_BOUNDED_MUTATION_PATTERNS = (
    r"\b(?:and|then|plus)\s+(?:also\s+)?(?:implement|add|create|fix|rewrite|refactor)\b",
    r"\b(?:implement|add|create|fix|rewrite|refactor)\b.+\b(?:parser|algorithm|endpoint|feature|behavior|workflow)\b",
    r"(?:그리고|그다음|동시에|추가로).{0,32}(?:구현|추가|생성|수정|재작성|리팩터링)",
    r"(?:파서|알고리즘|엔드포인트|기능|동작|워크플로).{0,20}(?:구현|추가|변경|수정)",
)
_CLASSIFICATION_TERMS = (
    "metadata",
    "frontmatter",
    "extract metadata",
    "classify files",
    "format conversion",
    "메타데이터",
    "형식 변환",
    "파일 분류",
    "문서 분류",
    "분류해",
    "분류 작업",
)
_MECHANICAL_TERMS = (
    "rename",
    "format",
    "sort",
    "generated fixtures",
    "mechanical",
    "이름 변경",
    "포맷",
    "정렬",
    "기계적",
)
_BROAD_IMPLEMENTATION_TERMS = (
    "architecture",
    "dashboard",
    "workflow",
    "router",
    "routing",
    "model policy",
    "quality policy",
    "아키텍처",
    "대시보드",
    "워크플로",
    "라우터",
    "라우팅",
    "모델 정책",
    "품질 정책",
    "작업 단계",
)


def _has(text: str, terms: tuple[str, ...]) -> bool:
    searchable = searchable_terms(text)
    return any(term_matches(searchable, term) for term in terms)


def is_deterministic_command(goal: str) -> bool:
    folded = goal.casefold()
    mutation_intent = _has(
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
    command = (
        re.search(
            r"\b(?:run|execute)\b.*\b(?:tests?|lint|build|schema checks?)\b",
            folded,
        )
        is not None
        or _has(
            goal,
            (
                "테스트 실행",
                "린트 실행",
                "빌드 실행",
                "스키마 검사",
            ),
        )
    )
    return command and not mutation_intent


def default_stage_kind(
    *,
    executor_id: str,
    goal: str,
) -> str:
    if executor_id == "implementation-engineer":
        return "implementation"
    if executor_id == "lens-reviewer":
        return "semantic-review"
    if executor_id == "researcher":
        return "research"
    if executor_id == "verifier":
        return (
            "deterministic-verification"
            if is_deterministic_command(goal)
            else "semantic-verification"
        )
    raise MaestroError(
        "MODEL_STAGE_UNKNOWN",
        (
            f"Executor {executor_id!r} has no explicit model-bearing stage "
            "policy; routing fails closed."
        ),
    )


def _bounded_task_shape(goal: str) -> str | None:
    """Recognize a narrowly stated mechanical task, not quoted policy terms."""

    if _has(goal, _BROAD_IMPLEMENTATION_TERMS):
        return None
    if any(
        re.search(pattern, goal, flags=re.IGNORECASE)
        for pattern in _MIXED_BOUNDED_MUTATION_PATTERNS
    ):
        return None
    word_count = len(re.findall(r"\w+", goal, flags=re.UNICODE))
    if word_count > 48:
        return None
    if _has(goal, _CLASSIFICATION_TERMS):
        return "classification"
    if _has(goal, _MECHANICAL_TERMS):
        return "mechanical"
    return None


def _explicit_complex_stage(goal: str, stage_kind: str) -> bool:
    """Recognize explicit difficulty only when it describes this stage's work."""

    clauses = re.split(
        r"(?:[.;:\n]+|\b(?:and|but|then)\b|(?:그리고|하지만|그런데|그다음))",
        goal,
        flags=re.IGNORECASE,
    )
    for clause in clauses:
        if not clause.strip() or any(
            re.search(pattern, clause, flags=re.IGNORECASE)
            for pattern in _NEGATED_DIFFICULTY_PATTERNS
        ):
            continue
        if stage_kind == "implementation" and _has(
            clause,
            _COMPLEX_IMPLEMENTATION_TERMS,
        ):
            return True
        if not _has(clause, _DIFFICULTY_MARKERS):
            continue
        if (
            stage_kind == "implementation"
            and _has(clause, _IMPLEMENTATION_COMPLEXITY_CONTEXT)
        ):
            return True
        if (
            stage_kind
            in {
                "semantic-review",
                "research",
                "semantic-verification",
                "specialist-review",
                "expertise-review",
            }
            and _has(clause, _SEMANTIC_COMPLEXITY_CONTEXT)
        ):
            return True
    return False


def _policy_choice(
    *,
    goal: str,
    risk: str,
    lens_ids: list[str],
    stage_kind: str,
) -> tuple[str, str | None, str | None, str]:
    if stage_kind not in STAGE_KINDS:
        raise MaestroError(
            "MODEL_STAGE_UNKNOWN",
            (
                f"Unknown model-bearing stage {stage_kind!r}; routing fails "
                "closed instead of silently inheriting a whole-goal default."
            ),
        )
    if stage_kind == "deterministic-verification":
        return (
            "deterministic-verification",
            None,
            None,
            "Deterministic project commands, not model judgment, decide the result.",
        )
    if (
        risk == "critical"
        or _has(goal, _HIGH_IMPACT_TERMS)
        or bool(_HIGH_IMPACT_LENSES.intersection(lens_ids))
    ):
        return (
            "high-impact-judgment",
            "frontier",
            "high",
            "Security, data, transaction, migration, irreversible, or critical risk raises failure cost.",
        )
    if _has(goal, _CONFLICT_TERMS):
        return (
            "material-conflict-resolution",
            "frontier",
            "high",
            "A material conflict requires one bounded frontier judgment lane.",
        )
    if (
        risk == "high"
        or (
            stage_kind != "implementation"
            and _has(goal, _ARCHITECTURE_TERMS)
        )
        or (
            stage_kind == "implementation"
            and _has(goal, _ARCHITECTURE_IMPLEMENTATION_TERMS)
        )
        or (
            stage_kind == "implementation"
            and _explicit_complex_stage(goal, stage_kind)
        )
        or (
            stage_kind
            in {
                "semantic-review",
                "research",
                "semantic-verification",
                "specialist-review",
                "expertise-review",
            }
            and _explicit_complex_stage(goal, stage_kind)
        )
    ):
        return (
            (
                "complex-implementation"
                if (
                    stage_kind == "implementation"
                    and _explicit_complex_stage(goal, stage_kind)
                    and risk != "high"
                    and not _has(goal, _ARCHITECTURE_IMPLEMENTATION_TERMS)
                )
                else (
                    "complex-semantic-judgment"
                    if _explicit_complex_stage(goal, stage_kind)
                    else "architecture-judgment"
                )
            ),
            "frontier",
            "high",
            "High-risk, explicitly difficult stage work, or explicit architecture judgment can reach Sol instead of being capped at Terra.",
        )
    if stage_kind in {
        "intermediate-synthesis",
        "technical-feasibility",
        "final-synthesis",
    }:
        return (
            (
                "final-synthesis"
                if stage_kind == "final-synthesis"
                else "architecture-judgment"
            ),
            "frontier",
            "high",
            "Architecture and synthesis stages integrate decision-changing constraints.",
        )
    if stage_kind == "implementation":
        bounded_shape = _bounded_task_shape(goal)
        if bounded_shape == "classification":
            return (
                "metadata-extraction",
                "economy",
                "high",
                "A bounded classification task uses Luna with stronger reasoning and a typed Terra fallback.",
            )
        if bounded_shape == "mechanical":
            return (
                "mechanical-change",
                "economy",
                "high",
                "A bounded mechanical change uses Luna with stronger reasoning and a typed Terra fallback.",
            )
        return (
            "general-implementation",
            "balanced",
            "high",
            "Ordinary implementation uses Terra with high reasoning under the Pro quality profile.",
        )
    if stage_kind in {
        "semantic-review",
        "specialist-review",
        "expertise-review",
    }:
        return (
            "semantic-review",
            "balanced",
            "high",
            "Semantic review uses Terra with high reasoning so classification words in the goal cannot lower the stage.",
        )
    if stage_kind == "research":
        return (
            "research-analysis",
            "balanced",
            "high",
            "Research requires evidence synthesis and uses Terra with high reasoning.",
        )
    if stage_kind == "semantic-verification":
        return (
            "semantic-verification",
            "balanced",
            "high",
            "Semantic verification uses Terra with high reasoning; deterministic commands remain a separate model-free stage.",
        )
    raise MaestroError(
        "MODEL_STAGE_UNKNOWN",
        f"Stage {stage_kind!r} does not define a model policy.",
    )


def _quality_floor(
    selected_class: str | None,
    reasoning_effort: str | None,
) -> dict[str, Any]:
    if selected_class is None:
        acceptable = [
            {
                "selected_class": None,
                "reasoning_effort": None,
            }
        ]
    elif selected_class == "economy":
        acceptable = [
            {"selected_class": "economy", "reasoning_effort": "high"},
            {"selected_class": "balanced", "reasoning_effort": "medium"},
            {"selected_class": "balanced", "reasoning_effort": "high"},
            {"selected_class": "frontier", "reasoning_effort": "medium"},
            {"selected_class": "frontier", "reasoning_effort": "high"},
        ]
    elif selected_class == "balanced":
        acceptable = [
            {"selected_class": "balanced", "reasoning_effort": "high"},
            {"selected_class": "frontier", "reasoning_effort": "high"},
        ]
    else:
        acceptable = [
            {"selected_class": "frontier", "reasoning_effort": "high"},
        ]
    return {
        "acceptable_routes": acceptable,
        "failure_action": "reject-or-reroute",
    }


def _typed_fallback(
    *,
    selected_class: str | None,
    host_profile: dict[str, Any],
) -> dict[str, Any] | None:
    if selected_class == "economy":
        return {
            "selected_class": "balanced",
            "selected_model": host_profile["classes"]["balanced"]["model"],
            "reasoning_effort": "medium",
            "trigger": "selected-model-unavailable",
        }
    if selected_class == "balanced":
        return {
            "selected_class": "frontier",
            "selected_model": host_profile["classes"]["frontier"]["model"],
            "reasoning_effort": "high",
            "trigger": "selected-model-unavailable",
        }
    return None


def build_stage_model_route(
    *,
    goal: str,
    risk: str,
    lens_ids: list[str],
    executor: dict[str, Any],
    host_id: str,
    host_profile: dict[str, Any],
    execution_unit_id: str,
    stage_kind: str,
    model_policy_overlays: list[dict[str, Any]] | None = None,
    model_policy_authority: dict[str, str] | None = None,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(execution_unit_id, str) or re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*",
        execution_unit_id,
    ) is None:
        raise MaestroError(
            "MODEL_EXECUTION_UNIT_INVALID",
            "execution_unit_id must be a lowercase kebab-case identifier.",
        )
    task_class, selected_class, reasoning_effort, reason = _policy_choice(
        goal=goal,
        risk=risk,
        lens_ids=lens_ids,
        stage_kind=stage_kind,
    )
    policy = executor["model_policy"]
    if selected_class is not None and selected_class not in policy["allowed_classes"]:
        raise MaestroError(
            "MODEL_CLASS_UNAVAILABLE",
            f"Executor {executor['executor_id']} does not allow {selected_class}.",
        )
    if (
        reasoning_effort is not None
        and reasoning_effort not in REASONING_EFFORTS
    ):
        raise MaestroError(
            "MODEL_REASONING_EFFORT_INVALID",
            f"Unsupported reasoning effort: {reasoning_effort}.",
        )
    selected_model = (
        None
        if selected_class is None
        else host_profile["classes"][selected_class]["model"]
    )
    fallback_route = _typed_fallback(
        selected_class=selected_class,
        host_profile=host_profile,
    )
    if selected_class is None:
        fallback = "Use the actual command result."
    elif fallback_route is None:
        fallback = (
            f"NEEDS_DECISION when {selected_model} is unavailable or the "
            "quality floor cannot be met."
        )
    else:
        fallback = (
            f"{fallback_route['selected_model']} with "
            f"{fallback_route['reasoning_effort']} reasoning"
        )
    route = {
        "schema_version": MODEL_ROUTE_VERSION,
        "model_route_id": "",
        "execution_unit_id": execution_unit_id,
        "stage_kind": stage_kind,
        "execution_kind": (
            "deterministic"
            if selected_class is None
            else "model"
        ),
        "quality_profile": "pro-quality",
        "executor": executor["executor_id"],
        "task_class": task_class,
        "risk": risk,
        "host": host_id,
        "selected_class": selected_class,
        "selected_model": selected_model,
        "reasoning_effort": reasoning_effort,
        "selection_reason": f"{reason} Quality profile: pro-quality.",
        "quality_floor": _quality_floor(
            selected_class,
            reasoning_effort,
        ),
        "escalation_allowed": (
            selected_class is not None
            and selected_class != "frontier"
            and policy["automatic_escalations"] == 1
        ),
        "fallback": fallback,
        "fallback_route": fallback_route,
    }
    identity = copy.deepcopy(route)
    identity.pop("model_route_id")
    route["model_route_id"] = sha256_text(canonical_json(identity))
    return apply_model_policy_overlays(
        route,
        model_policy_overlays or [],
        host_profile=host_profile,
        authority=model_policy_authority,
        repo_path=repo_path,
    )


def apply_model_policy_overlays(
    route: dict[str, Any],
    overlays: list[dict[str, Any]],
    *,
    host_profile: dict[str, Any],
    authority: dict[str, str] | None = None,
    repo_path: str | Path | None = None,
) -> dict[str, Any]:
    """Apply at most one explicitly supplied, accepted quality overlay.

    The router never discovers overlays from operational state. A caller must
    supply the accepted artifact while constructing a new typed route.
    """

    if validate_model_route_shape(route) is not None:
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_ROUTE_INVALID",
            "A feedback overlay requires one valid base model route.",
        )
    if (
        not isinstance(overlays, list)
        or len(overlays) > 16
        or not isinstance(host_profile, dict)
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_INVALID",
            "At most sixteen explicit model-policy overlays may be considered.",
        )
    from .model_feedback import (
        current_model_policy_authority,
        validate_model_policy_overlay,
        validate_model_policy_overlay_authority,
    )

    overlay_ids: set[str] = set()
    matches: list[dict[str, Any]] = []
    verified_authority = None
    if overlays:
        if (
            repo_path is None
            or any(
                not validate_model_policy_overlay_authority(
                    overlay,
                    repo_path=repo_path,
                )
                for overlay in overlays
            )
        ):
            raise MaestroError(
                "MODEL_POLICY_OVERLAY_AUTHORITY_INVALID",
                "A supplied overlay requires its exact current repository approval artifact.",
            )
        verified_authority = current_model_policy_authority(repo_path)
        if authority is not None and authority != verified_authority:
            raise MaestroError(
                "MODEL_POLICY_OVERLAY_AUTHORITY_INVALID",
                "Caller authority differs from the verified current repository authority.",
            )
    subject = {
        "quality_profile": route["quality_profile"],
        "stage_kind": route["stage_kind"],
        "task_class": route["task_class"],
        "selected_class": route["selected_class"],
        "selected_model": route["selected_model"],
        "reasoning_effort": route["reasoning_effort"],
        "risk": route["risk"],
    }
    for overlay in overlays:
        if (
            not validate_model_policy_overlay(overlay)
            or overlay["overlay_id"] in overlay_ids
        ):
            raise MaestroError(
                "MODEL_POLICY_OVERLAY_INVALID",
                "Every supplied overlay must be unique and structurally accepted.",
            )
        overlay_ids.add(overlay["overlay_id"])
        if (
            verified_authority is None
            or overlay.get("authority") != verified_authority
        ):
            raise MaestroError(
                "MODEL_POLICY_OVERLAY_AUTHORITY_INVALID",
                "A supplied overlay must match the exact current project, checkout, Registry, and policy.",
            )
        if overlay["scope"] == subject:
            matches.append(overlay)
    if not matches:
        return copy.deepcopy(route)
    if len(matches) != 1:
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_AMBIGUOUS",
            "More than one accepted overlay matches the same base route.",
        )

    overlay = matches[0]
    target = overlay["target"]
    expected_step = {
        "economy": "balanced",
        "balanced": "frontier",
    }.get(route["selected_class"])
    host_classes = host_profile.get("classes")
    target_host = (
        host_classes.get(target["selected_class"])
        if isinstance(host_classes, dict)
        else None
    )
    target_pair = {
        "selected_class": target["selected_class"],
        "reasoning_effort": target["reasoning_effort"],
    }
    if (
        target["selected_class"] != expected_step
        or target_pair
        not in route["quality_floor"]["acceptable_routes"]
        or not isinstance(target_host, dict)
        or target_host.get("model") != target["selected_model"]
    ):
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_TARGET_INVALID",
            "An overlay may raise exactly one Host-backed quality tier within the base quality floor.",
        )

    derived = copy.deepcopy(route)
    derived["selected_class"] = target["selected_class"]
    derived["selected_model"] = target["selected_model"]
    derived["reasoning_effort"] = target["reasoning_effort"]
    derived["selection_reason"] = (
        f"{route['selection_reason']} Accepted observational feedback overlay "
        f"{overlay['overlay_id']} creates a new one-tier typed route."
    )
    derived["quality_floor"] = _quality_floor(
        target["selected_class"],
        target["reasoning_effort"],
    )
    fallback_route = _typed_fallback(
        selected_class=target["selected_class"],
        host_profile=host_profile,
    )
    derived["fallback_route"] = fallback_route
    derived["fallback"] = (
        (
            f"{fallback_route['selected_model']} with "
            f"{fallback_route['reasoning_effort']} reasoning"
        )
        if fallback_route is not None
        else (
            f"NEEDS_DECISION when {target['selected_model']} is unavailable "
            "or the quality floor cannot be met."
        )
    )
    derived["escalation_allowed"] = (
        target["selected_class"] != "frontier"
    )
    derived["model_route_id"] = ""
    identity = copy.deepcopy(derived)
    identity.pop("model_route_id")
    derived["model_route_id"] = sha256_text(canonical_json(identity))
    if validate_model_route_shape(derived) is not None:
        raise MaestroError(
            "MODEL_POLICY_OVERLAY_ROUTE_INVALID",
            "The accepted overlay did not produce one valid typed route.",
        )
    return derived


def validate_model_route_shape(value: Any) -> str | None:
    if not isinstance(value, dict) or set(value) != MODEL_ROUTE_FIELDS:
        return "model_route fields are incomplete or unknown."
    if (
        value.get("schema_version") != MODEL_ROUTE_VERSION
        or not isinstance(value.get("model_route_id"), str)
        or re.fullmatch(r"[a-f0-9]{64}", value["model_route_id"]) is None
        or not isinstance(value.get("execution_unit_id"), str)
        or re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*",
            value["execution_unit_id"],
        )
        is None
        or value.get("stage_kind") not in STAGE_KINDS
        or value.get("execution_kind") not in EXECUTION_KINDS
        or value.get("quality_profile") != "pro-quality"
    ):
        return "model_route identity or stage fields are invalid."
    identity = copy.deepcopy(value)
    identity.pop("model_route_id")
    if value["model_route_id"] != sha256_text(canonical_json(identity)):
        return "model_route_id does not bind the complete model route."
    quality_floor = value.get("quality_floor")
    if (
        not isinstance(quality_floor, dict)
        or set(quality_floor) != QUALITY_FLOOR_FIELDS
        or quality_floor.get("failure_action") != "reject-or-reroute"
        or not isinstance(quality_floor.get("acceptable_routes"), list)
        or not quality_floor["acceptable_routes"]
        or any(
            not isinstance(item, dict)
            or set(item) != QUALITY_ROUTE_FIELDS
            or item.get("selected_class")
            not in {None, "economy", "balanced", "frontier"}
            or item.get("reasoning_effort")
            not in {None, "low", "medium", "high", "xhigh"}
            for item in quality_floor["acceptable_routes"]
        )
    ):
        return "model_route quality_floor is invalid."
    fallback_route = value.get("fallback_route")
    if fallback_route is not None and (
        not isinstance(fallback_route, dict)
        or set(fallback_route) != FALLBACK_ROUTE_FIELDS
        or fallback_route.get("selected_class")
        not in {"economy", "balanced", "frontier"}
        or not isinstance(fallback_route.get("selected_model"), str)
        or not fallback_route["selected_model"]
        or fallback_route.get("reasoning_effort")
        not in REASONING_EFFORTS
        or fallback_route.get("trigger") != "selected-model-unavailable"
    ):
        return "model_route fallback_route is invalid."
    expected_kind = (
        "deterministic"
        if value.get("selected_class") is None
        else "model"
    )
    if value.get("execution_kind") != expected_kind:
        return "model_route execution_kind conflicts with selected_class."
    selected_pair = {
        "selected_class": value.get("selected_class"),
        "reasoning_effort": value.get("reasoning_effort"),
    }
    if selected_pair not in quality_floor["acceptable_routes"]:
        return "model_route selected pair is below its quality floor."
    return None
