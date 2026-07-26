from __future__ import annotations

import copy
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .errors import MaestroError
from .expertise import select_expertise
from .planning import route_goal_v2
from .registry import (
    registry_digest,
    resolve_request_contract,
    route_goal,
)
from .util import (
    canonical_json,
    ensure_repo,
    file_sha256,
    sha256_text,
)

DECISION_PLAN_VERSION = "maestro_decision_plan_v1"
FINDING_PACKET_VERSION = "maestro_specialist_finding_packet_v1"
DECISION_BUNDLE_VERSION = "maestro_decision_bundle_v1"
EXECUTION_PLAN_VERSION = "maestro_execution_plan_v1"
MAX_DECISION_ASSIGNMENTS = 5
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
IMPLEMENTATION_COMMAND_PATTERNS = (
    r"^\s*(?:implement|edit|change|modify|add|remove|write|create)\b",
    r"^\s*(?:구현|수정|변경|추가|삭제|작성)(?:해|하|해야|하십시오|하세요)",
    r"\bapply_patch\b",
    r"\brepository_write\b",
    r"```",
)
DECISION_PLAN_FIELDS = {
    "schema_version",
    "plan_id",
    "goal",
    "goal_digest",
    "registry_digest",
    "base_revision",
    "risk",
    "host",
    "request_contract",
    "expertise",
    "specialist_contracts",
    "assignments",
    "entry_assignments",
    "terminal_assignments",
    "limits",
    "deliberation",
    "warnings",
    "writes_performed",
}
DECISION_ASSIGNMENT_FIELDS = {
    "assignment_id",
    "kind",
    "specialist_id",
    "executor_id",
    "depends_on",
    "input_packets",
    "output_packet",
    "read_only",
    "allowed_side_effects",
    "conclusion_visibility",
    "model_route",
    "may_spawn",
    "max_children",
    "max_rounds",
}


def _digest_payload(value: dict[str, Any], digest_field: str) -> str:
    payload = copy.deepcopy(value)
    payload.pop(digest_field, None)
    return sha256_text(canonical_json(payload))


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _git(repo: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    return completed.stdout


def repository_revision(repo_path: str | Path) -> dict[str, Any]:
    """Return a content-sensitive, read-only Git checkout revision."""

    repo = ensure_repo(repo_path)
    try:
        head = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
        changed = set(
            item.decode("utf-8", errors="surrogateescape")
            for item in _git(
                repo,
                "diff",
                "--name-only",
                "-z",
                "HEAD",
                "--",
            ).split(b"\0")
            if item
        )
        changed.update(
            item.decode("utf-8", errors="surrogateescape")
            for item in _git(
                repo,
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ).split(b"\0")
            if item
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {
            "kind": "unavailable",
            "head": None,
            "state_digest": None,
            "dirty_path_count": None,
        }

    path_states: list[dict[str, Any]] = []
    for relative in sorted(changed):
        candidate = repo / relative
        if candidate.is_symlink():
            state = {
                "path": relative,
                "kind": "symlink",
                "digest": sha256_text(os.readlink(candidate)),
            }
        elif candidate.is_file():
            state = {
                "path": relative,
                "kind": "file",
                "digest": file_sha256(candidate),
            }
        elif candidate.exists():
            state = {"path": relative, "kind": "other", "digest": None}
        else:
            state = {"path": relative, "kind": "deleted", "digest": None}
        path_states.append(state)

    return {
        "kind": "git",
        "head": head,
        "state_digest": sha256_text(
            canonical_json({"head": head, "paths": path_states})
        ),
        "dirty_path_count": len(path_states),
    }


def _specialist(
    specialist_id: str,
    *,
    summary: str,
    owns: list[str],
    out_of_scope: list[str],
    allowed_inputs: list[str],
    allowed_claim_kinds: list[str],
    guide_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "specialist_id": specialist_id,
        "summary": summary,
        "owns": owns,
        "out_of_scope": out_of_scope,
        "allowed_inputs": allowed_inputs,
        "allowed_claim_kinds": allowed_claim_kinds,
        "allowed_side_effects": [],
        "decision_guide_ids": guide_ids or [],
        "fresh_context": True,
        "may_spawn": False,
    }


def _technical_specialist() -> dict[str, Any]:
    return _specialist(
        "technical-feasibility",
        summary=(
            "Check whether synthesized decisions fit the current platform, "
            "constraints, delivery boundary, and verification path."
        ),
        owns=[
            "technical-feasibility",
            "platform-constraint",
            "delivery-risk",
            "verification-path",
        ],
        out_of_scope=[
            "brand-expression",
            "product-priority",
            "typography",
            "implementation-command",
        ],
        allowed_inputs=[
            "GoalDigest",
            "ProjectContext",
            "SynthesisPacket",
            "RepositoryEvidence",
        ],
        allowed_claim_kinds=["constraint", "finding", "risk", "question"],
    )


def _product_design_specialists(
    selected_guides: list[str],
) -> list[dict[str, Any]]:
    visual_guides = [
        item
        for item in selected_guides
        if item
        in {
            "design-brief",
            "typography-korean",
            "visual-hierarchy-layout",
            "reference-selection",
        }
    ]
    ux_guides = [
        item
        for item in selected_guides
        if item
        in {
            "design-brief",
            "interaction-responsive-accessibility",
            "reference-selection",
        }
    ]
    return [
        _specialist(
            "visual-design",
            summary=(
                "Judge content hierarchy, typography, composition, emphasis, "
                "and reference transfer without choosing implementation."
            ),
            owns=[
                "brand-expression",
                "composition",
                "layout",
                "typography",
                "visual-hierarchy",
            ],
            out_of_scope=[
                "implementation-command",
                "platform-constraint",
                "technical-feasibility",
                "user-flow",
            ],
            allowed_inputs=[
                "GoalDigest",
                "ProjectContext",
                "SelectedDecisionGuides",
                "RenderedArtifact",
                "ReferenceArtifact",
            ],
            allowed_claim_kinds=[
                "constraint",
                "finding",
                "reference-transfer",
                "risk",
                "question",
            ],
            guide_ids=visual_guides,
        ),
        _specialist(
            "ux-product",
            summary=(
                "Judge user flow, interaction states, responsive behavior, "
                "accessibility, and product comprehension without writing code."
            ),
            owns=[
                "accessibility",
                "interaction-state",
                "product-comprehension",
                "responsive-behavior",
                "user-flow",
            ],
            out_of_scope=[
                "brand-expression",
                "implementation-command",
                "technical-feasibility",
                "typography",
            ],
            allowed_inputs=[
                "GoalDigest",
                "ProjectContext",
                "SelectedDecisionGuides",
                "RenderedArtifact",
                "ReferenceArtifact",
            ],
            allowed_claim_kinds=[
                "constraint",
                "finding",
                "risk",
                "question",
            ],
            guide_ids=ux_guides,
        ),
        _technical_specialist(),
    ]


def _lens_specialists(
    lens_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    specialists: list[dict[str, Any]] = []
    for lens in lens_cards[:2]:
        specialists.append(
            _specialist(
                f"{lens['lens_id']}-review",
                summary=lens["summary"],
                owns=[lens["lens_id"]],
                out_of_scope=[
                    "implementation-command",
                    "unselected-lens",
                ],
                allowed_inputs=[
                    "GoalDigest",
                    "ProjectContext",
                    "LensCard",
                    "RepositoryEvidence",
                    "ResearchArtifact",
                ],
                allowed_claim_kinds=[
                    "constraint",
                    "finding",
                    "risk",
                    "question",
                ],
            )
        )
    if specialists:
        return specialists
    return [
        _specialist(
            "domain-review",
            summary=(
                "Identify domain constraints and decision-changing uncertainty "
                "without proposing repository mutations."
            ),
            owns=["domain-correctness"],
            out_of_scope=["implementation-command", "unrequested-domain"],
            allowed_inputs=[
                "GoalDigest",
                "ProjectContext",
                "RepositoryEvidence",
                "ResearchArtifact",
            ],
            allowed_claim_kinds=[
                "constraint",
                "finding",
                "risk",
                "question",
            ],
        )
    ]


def _decision_assignment(
    assignment_id: str,
    *,
    kind: str,
    specialist_id: str | None,
    depends_on: list[str],
    input_packets: list[str],
    output_packet: str,
    conclusion_visibility: str,
    model_route: dict[str, Any],
) -> dict[str, Any]:
    return {
        "assignment_id": assignment_id,
        "kind": kind,
        "specialist_id": specialist_id,
        "executor_id": "lens-reviewer",
        "depends_on": depends_on,
        "input_packets": input_packets,
        "output_packet": output_packet,
        "read_only": True,
        "allowed_side_effects": [],
        "conclusion_visibility": conclusion_visibility,
        "model_route": copy.deepcopy(model_route),
        "may_spawn": False,
        "max_children": 0,
        "max_rounds": 1,
    }


def _decision_assignments(
    specialists: list[dict[str, Any]],
    *,
    product_design: bool,
    model_route: dict[str, Any],
) -> list[dict[str, Any]]:
    if product_design:
        initial = [
            _decision_assignment(
                "visual-design-review",
                kind="specialist-review",
                specialist_id="visual-design",
                depends_on=[],
                input_packets=[
                    "DecisionTaskPacket",
                    "SpecialistContract",
                ],
                output_packet="SpecialistFindingPacket",
                conclusion_visibility="blind",
                model_route=model_route,
            ),
            _decision_assignment(
                "ux-product-review",
                kind="specialist-review",
                specialist_id="ux-product",
                depends_on=[],
                input_packets=[
                    "DecisionTaskPacket",
                    "SpecialistContract",
                ],
                output_packet="SpecialistFindingPacket",
                conclusion_visibility="blind",
                model_route=model_route,
            ),
        ]
    else:
        initial = [
            _decision_assignment(
                f"{specialist['specialist_id']}-assignment",
                kind="specialist-review",
                specialist_id=specialist["specialist_id"],
                depends_on=[],
                input_packets=[
                    "DecisionTaskPacket",
                    "SpecialistContract",
                ],
                output_packet="SpecialistFindingPacket",
                conclusion_visibility="blind",
                model_route=model_route,
            )
            for specialist in specialists
            if specialist["specialist_id"] != "technical-feasibility"
        ]

    initial_ids = [item["assignment_id"] for item in initial]
    return [
        *initial,
        _decision_assignment(
            "synthesis-1",
            kind="synthesis",
            specialist_id=None,
            depends_on=initial_ids,
            input_packets=["SpecialistFindingPacket"],
            output_packet="SynthesisPacket",
            conclusion_visibility="dependencies-only",
            model_route=model_route,
        ),
        _decision_assignment(
            "technical-feasibility-review",
            kind="specialist-review",
            specialist_id="technical-feasibility",
            depends_on=["synthesis-1"],
            input_packets=[
                "DecisionTaskPacket",
                "SpecialistContract",
                "SynthesisPacket",
            ],
            output_packet="SpecialistFindingPacket",
            conclusion_visibility="synthesis-only",
            model_route=model_route,
        ),
        _decision_assignment(
            "final-synthesis",
            kind="synthesis",
            specialist_id=None,
            depends_on=["synthesis-1", "technical-feasibility-review"],
            input_packets=[
                "SynthesisPacket",
                "SpecialistFindingPacket",
            ],
            output_packet="DecisionBundle",
            conclusion_visibility="dependencies-only",
            model_route=model_route,
        ),
    ]


def build_decision_plan(
    repo_path: str | Path,
    goal: str,
    risk: str,
    *,
    host_id: str = "codex",
    intent: str = "implementation",
    research_evidence_digest: str | None = None,
) -> dict[str, Any]:
    """Build a read-only specialist decision plan.

    Invoking ``decide`` opts a mutating request into staged execution. A
    read-only request remains forbidden from enactment.
    """

    if not isinstance(goal, str) or not goal.strip():
        raise MaestroError("GOAL_INVALID", "Decision goal must be non-empty.")
    request_contract = resolve_request_contract(goal, intent)
    if request_contract["side_effect_policy"] != "forbidden":
        request_contract = {
            "decision_mode": "staged",
            "side_effect_policy": "after_decision",
            "authorization_source": (
                "explicit_cli" if intent == "implementation" else None
            ),
        }

    expertise_intent = (
        "review"
        if request_contract["side_effect_policy"] == "forbidden"
        else "implementation"
    )
    expertise, _ = select_expertise(
        goal,
        intent=expertise_intent,
        research_evidence_digest=research_evidence_digest,
    )
    review_route = route_goal(
        goal,
        risk,
        host_id=host_id,
        intent="review",
    )
    product_design = "product-design" in expertise["selected_pack_ids"]
    if product_design:
        specialists = _product_design_specialists(
            expertise["selected_guide_ids"]
        )
    else:
        specialists = [
            *_lens_specialists(review_route["lens_cards"]),
            _technical_specialist(),
        ]
    assignments = _decision_assignments(
        specialists,
        product_design=product_design,
        model_route=review_route["model_route"],
    )
    if len(assignments) > MAX_DECISION_ASSIGNMENTS:
        raise MaestroError(
            "DECISION_ASSIGNMENT_LIMIT_EXCEEDED",
            f"Decision plans permit at most {MAX_DECISION_ASSIGNMENTS} assignments.",
        )

    dependency_targets = {
        dependency
        for assignment in assignments
        for dependency in assignment["depends_on"]
    }
    revision = repository_revision(repo_path)
    warnings = [*expertise["warnings"]]
    if revision["kind"] == "unavailable":
        warnings.append(
            {
                "code": "DECISION_REVISION_UNAVAILABLE",
                "message": (
                    "The repository has no readable Git revision. A decision may "
                    "be reviewed, but enactment is blocked because stale state "
                    "cannot be detected."
                ),
            }
        )
    plan = {
        "schema_version": DECISION_PLAN_VERSION,
        "plan_id": "",
        "goal": goal,
        "goal_digest": sha256_text(goal),
        "registry_digest": registry_digest(),
        "base_revision": revision,
        "risk": risk,
        "host": host_id,
        "request_contract": request_contract,
        "expertise": {
            "selected_pack_ids": expertise["selected_pack_ids"],
            "selected_guide_ids": expertise["selected_guide_ids"],
            "research_requirement": expertise["research_requirement"],
        },
        "specialist_contracts": specialists,
        "assignments": assignments,
        "entry_assignments": [
            assignment["assignment_id"]
            for assignment in assignments
            if not assignment["depends_on"]
        ],
        "terminal_assignments": [
            assignment["assignment_id"]
            for assignment in assignments
            if assignment["assignment_id"] not in dependency_targets
        ],
        "limits": {
            "max_assignments": MAX_DECISION_ASSIGNMENTS,
            "max_rebuttal_rounds": 1,
            "max_model_escalations_per_assignment": 1,
        },
        "deliberation": {
            "blind_first": True,
            "conflict_only_rebuttal": True,
            "majority_vote": False,
            "free_form_debate": False,
            "stop_on_no_new_evidence": True,
        },
        "warnings": warnings,
        "writes_performed": False,
    }
    plan["plan_id"] = _digest_payload(plan, "plan_id")
    result = validate_decision_plan(plan)
    if result["status"] != "PASS":
        raise MaestroError(
            "DECISION_PLAN_INVALID",
            "; ".join(item["message"] for item in result["issues"]),
        )
    return plan


def _valid_string_list(value: Any, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and all(isinstance(item, str) and item.strip() for item in value)
        and len(value) == len(set(value))
    )


def _validate_revision(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "kind",
        "head",
        "state_digest",
        "dirty_path_count",
    }:
        issues.append(
            _error(
                "DECISION_REVISION_INVALID",
                path,
                "Revision must contain kind, head, state_digest, and dirty_path_count.",
            )
        )
        return
    if value["kind"] not in {"git", "unavailable"}:
        issues.append(
            _error("DECISION_REVISION_INVALID", f"{path}.kind", "Unknown revision kind.")
        )
    if value["kind"] == "git":
        if (
            not isinstance(value["head"], str)
            or not value["head"]
            or not isinstance(value["state_digest"], str)
            or DIGEST_PATTERN.fullmatch(value["state_digest"]) is None
            or not isinstance(value["dirty_path_count"], int)
            or isinstance(value["dirty_path_count"], bool)
            or value["dirty_path_count"] < 0
        ):
            issues.append(
                _error(
                    "DECISION_REVISION_INVALID",
                    path,
                    "Git revision fields are invalid.",
                )
            )
    elif any(value[field] is not None for field in ("head", "state_digest", "dirty_path_count")):
        issues.append(
            _error(
                "DECISION_REVISION_INVALID",
                path,
                "Unavailable revision fields must be null.",
            )
        )


def _validate_request_contract(
    value: Any,
    path: str,
    issues: list[dict[str, str]],
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "decision_mode",
        "side_effect_policy",
        "authorization_source",
    }:
        issues.append(
            _error(
                "REQUEST_CONTRACT_INVALID",
                path,
                "Request contract fields are invalid.",
            )
        )
        return
    if value["decision_mode"] not in {"direct", "staged"}:
        issues.append(
            _error(
                "REQUEST_CONTRACT_INVALID",
                f"{path}.decision_mode",
                "Unknown decision mode.",
            )
        )
    if value["side_effect_policy"] not in {
        "forbidden",
        "after_decision",
        "direct",
    }:
        issues.append(
            _error(
                "REQUEST_CONTRACT_INVALID",
                f"{path}.side_effect_policy",
                "Unknown side-effect policy.",
            )
        )
    if value["authorization_source"] not in {
        None,
        "explicit_user",
        "explicit_cli",
    }:
        issues.append(
            _error(
                "REQUEST_CONTRACT_INVALID",
                f"{path}.authorization_source",
                "Unknown authorization source.",
            )
        )


def validate_decision_plan(plan: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not isinstance(plan, dict):
        issues.append(
            _error("DECISION_PLAN_INVALID", "$", "Decision plan must be an object.")
        )
    else:
        if set(plan) != DECISION_PLAN_FIELDS:
            issues.append(
                _error(
                    "DECISION_PLAN_FIELDS_INVALID",
                    "$",
                    "Decision plan fields do not match the published contract.",
                )
            )
        if plan.get("schema_version") != DECISION_PLAN_VERSION:
            issues.append(
                _error(
                    "DECISION_PLAN_VERSION_INVALID",
                    "schema_version",
                    f"Expected {DECISION_PLAN_VERSION}.",
                )
            )
        if (
            not isinstance(plan.get("plan_id"), str)
            or plan["plan_id"] != _digest_payload(plan, "plan_id")
        ):
            issues.append(
                _error(
                    "DECISION_PLAN_DIGEST_MISMATCH",
                    "plan_id",
                    "Decision plan digest does not match its canonical content.",
                )
            )
        if (
            not isinstance(plan.get("goal"), str)
            or not plan["goal"].strip()
            or plan.get("goal_digest") != sha256_text(plan.get("goal", ""))
        ):
            issues.append(
                _error(
                    "DECISION_GOAL_DIGEST_MISMATCH",
                    "goal_digest",
                    "Goal and goal digest do not agree.",
                )
            )
        _validate_revision(plan.get("base_revision"), "base_revision", issues)
        _validate_request_contract(
            plan.get("request_contract"),
            "request_contract",
            issues,
        )
        if (
            not isinstance(plan.get("risk"), str)
            or plan["risk"] not in {"low", "medium", "high", "critical"}
            or not isinstance(plan.get("host"), str)
            or ID_PATTERN.fullmatch(plan["host"]) is None
            or not isinstance(plan.get("registry_digest"), str)
            or DIGEST_PATTERN.fullmatch(plan["registry_digest"]) is None
        ):
            issues.append(
                _error(
                    "DECISION_PLAN_CONTEXT_INVALID",
                    "$",
                    "Risk, host, or Registry digest is invalid.",
                )
            )
        specialists = plan.get("specialist_contracts")
        specialist_ids: set[str] = set()
        specialist_by_id: dict[str, dict[str, Any]] = {}
        if not isinstance(specialists, list) or not specialists:
            issues.append(
                _error(
                    "SPECIALIST_CONTRACT_INVALID",
                    "specialist_contracts",
                    "At least one specialist contract is required.",
                )
            )
            specialists = []
        for index, specialist in enumerate(specialists):
            path = f"specialist_contracts[{index}]"
            required = {
                "specialist_id",
                "summary",
                "owns",
                "out_of_scope",
                "allowed_inputs",
                "allowed_claim_kinds",
                "allowed_side_effects",
                "decision_guide_ids",
                "fresh_context",
                "may_spawn",
            }
            if not isinstance(specialist, dict) or set(specialist) != required:
                issues.append(
                    _error(
                        "SPECIALIST_CONTRACT_INVALID",
                        path,
                        "Specialist contract fields are invalid.",
                    )
                )
                continue
            specialist_id = specialist["specialist_id"]
            if (
                not isinstance(specialist_id, str)
                or ID_PATTERN.fullmatch(specialist_id) is None
                or specialist_id in specialist_ids
            ):
                issues.append(
                    _error(
                        "SPECIALIST_ID_INVALID",
                        f"{path}.specialist_id",
                        "Specialist ID is invalid or duplicated.",
                    )
                )
                continue
            specialist_ids.add(specialist_id)
            specialist_by_id[specialist_id] = specialist
            owns = specialist["owns"]
            out_of_scope = specialist["out_of_scope"]
            if (
                not _valid_string_list(owns, nonempty=True)
                or not _valid_string_list(out_of_scope, nonempty=True)
                or set(owns).intersection(out_of_scope)
            ):
                issues.append(
                    _error(
                        "SPECIALIST_SCOPE_INVALID",
                        path,
                        "owns and out_of_scope must be unique, non-empty, and disjoint.",
                    )
                )
            if (
                not _valid_string_list(
                    specialist["allowed_inputs"],
                    nonempty=True,
                )
                or not _valid_string_list(
                    specialist["allowed_claim_kinds"],
                    nonempty=True,
                )
                or not _valid_string_list(specialist["decision_guide_ids"])
                or specialist["allowed_side_effects"] != []
                or specialist["fresh_context"] is not True
                or specialist["may_spawn"] is not False
            ):
                issues.append(
                    _error(
                        "SPECIALIST_CAPABILITY_INVALID",
                        path,
                        "Specialists must be fresh, non-spawning, and read-only.",
                    )
                )

        assignments = plan.get("assignments")
        if (
            not isinstance(assignments, list)
            or not assignments
            or len(assignments) > MAX_DECISION_ASSIGNMENTS
        ):
            issues.append(
                _error(
                    "DECISION_ASSIGNMENT_INVALID",
                    "assignments",
                    "Decision assignments must contain one to five items.",
                )
            )
            assignments = []
        assignment_ids: set[str] = set()
        by_id: dict[str, dict[str, Any]] = {}
        for index, assignment in enumerate(assignments):
            path = f"assignments[{index}]"
            if not isinstance(assignment, dict):
                issues.append(
                    _error(
                        "DECISION_ASSIGNMENT_INVALID",
                        path,
                        "Assignment must be an object.",
                    )
                )
                continue
            if set(assignment) != DECISION_ASSIGNMENT_FIELDS:
                issues.append(
                    _error(
                        "DECISION_ASSIGNMENT_FIELDS_INVALID",
                        path,
                        "Decision Assignment fields are invalid.",
                    )
                )
            assignment_id = assignment.get("assignment_id")
            if (
                not isinstance(assignment_id, str)
                or ID_PATTERN.fullmatch(assignment_id) is None
                or assignment_id in assignment_ids
            ):
                issues.append(
                    _error(
                        "DECISION_ASSIGNMENT_INVALID",
                        f"{path}.assignment_id",
                        "Assignment ID is invalid or duplicated.",
                    )
                )
                continue
            assignment_ids.add(assignment_id)
            by_id[assignment_id] = assignment
            specialist_id = assignment.get("specialist_id")
            if assignment.get("kind") == "specialist-review" and (
                not isinstance(specialist_id, str)
                or specialist_id not in specialist_by_id
            ):
                issues.append(
                    _error(
                        "DECISION_SPECIALIST_UNKNOWN",
                        f"{path}.specialist_id",
                        "Specialist review must reference a declared specialist.",
                    )
                )
            if (
                assignment.get("kind") == "synthesis"
                and specialist_id is not None
            ):
                issues.append(
                    _error(
                        "DECISION_SYNTHESIS_SCOPE_INVALID",
                        f"{path}.specialist_id",
                        "Synthesis is Maestro-owned and has no specialist identity.",
                    )
                )
            assignment_kind = assignment.get("kind")
            expected_output = {
                "specialist-review": "SpecialistFindingPacket",
                "synthesis": (
                    "DecisionBundle"
                    if assignment_id == "final-synthesis"
                    else "SynthesisPacket"
                ),
            }.get(assignment_kind) if isinstance(assignment_kind, str) else None
            visibility = assignment.get("conclusion_visibility")
            if (
                expected_output is None
                or assignment.get("output_packet") != expected_output
                or assignment.get("executor_id") != "lens-reviewer"
                or not _valid_string_list(
                    assignment.get("input_packets"),
                    nonempty=True,
                )
                or not isinstance(visibility, str)
                or visibility
                not in {"blind", "dependencies-only", "synthesis-only"}
                or assignment.get("max_rounds") != 1
                or not isinstance(assignment.get("model_route"), dict)
            ):
                issues.append(
                    _error(
                        "DECISION_ASSIGNMENT_CONTRACT_INVALID",
                        path,
                        "Assignment kind, Executor, packets, visibility, rounds, or model route is invalid.",
                    )
                )
            if (
                assignment.get("read_only") is not True
                or assignment.get("allowed_side_effects") != []
                or assignment.get("may_spawn") is not False
                or assignment.get("max_children") != 0
            ):
                issues.append(
                    _error(
                        "DECISION_WRITE_FORBIDDEN",
                        path,
                        "Every decision assignment must be read-only and non-spawning.",
                    )
                )
        for assignment_id, assignment in by_id.items():
            dependencies = assignment.get("depends_on")
            if not _valid_string_list(dependencies):
                issues.append(
                    _error(
                        "DECISION_DEPENDENCY_INVALID",
                        f"assignments.{assignment_id}.depends_on",
                        "Dependencies must be a unique string list.",
                    )
                )
                continue
            unknown = set(dependencies) - assignment_ids
            if unknown:
                issues.append(
                    _error(
                        "DECISION_DEPENDENCY_UNKNOWN",
                        f"assignments.{assignment_id}.depends_on",
                        f"Unknown dependencies: {', '.join(sorted(unknown))}.",
                    )
                )
            if (
                not dependencies
                and assignment.get("conclusion_visibility") != "blind"
            ):
                issues.append(
                    _error(
                        "DECISION_BLIND_REVIEW_REQUIRED",
                        f"assignments.{assignment_id}.conclusion_visibility",
                        "Initial specialist conclusions must be blind.",
                    )
                )
        declared_entries = plan.get("entry_assignments")
        declared_terminals = plan.get("terminal_assignments")
        if not _valid_string_list(declared_entries, nonempty=True):
            declared_entries = []
        if not _valid_string_list(declared_terminals, nonempty=True):
            declared_terminals = []
        expected_entry = sorted(
            assignment_id
            for assignment_id, assignment in by_id.items()
            if not assignment.get("depends_on")
        )
        dependency_targets = {
            dependency
            for assignment in by_id.values()
            for dependency in assignment.get("depends_on", [])
        }
        expected_terminal = sorted(set(by_id) - dependency_targets)
        if (
            sorted(declared_entries) != expected_entry
            or sorted(declared_terminals) != expected_terminal
            or expected_terminal != ["final-synthesis"]
        ):
            issues.append(
                _error(
                    "DECISION_BOUNDARY_INVALID",
                    "entry_assignments",
                    "Entry and terminal assignments must match the DAG and end at final-synthesis.",
                )
            )
        synthesis = by_id.get("synthesis-1")
        technical = by_id.get("technical-feasibility-review")
        final = by_id.get("final-synthesis")
        initial_ids = sorted(
            assignment_id
            for assignment_id, assignment in by_id.items()
            if assignment.get("kind") == "specialist-review"
            and assignment.get("specialist_id") != "technical-feasibility"
        )
        if (
            synthesis is None
            or sorted(synthesis.get("depends_on", [])) != initial_ids
            or technical is None
            or technical.get("specialist_id") != "technical-feasibility"
            or technical.get("depends_on") != ["synthesis-1"]
            or final is None
            or sorted(final.get("depends_on", []))
            != ["synthesis-1", "technical-feasibility-review"]
        ):
            issues.append(
                _error(
                    "DECISION_SEQUENCE_INVALID",
                    "assignments",
                    "Decision sequence must be blind reviews, synthesis, technical feasibility, then final synthesis.",
                )
            )
        try:
            expected_model_route = route_goal(
                plan.get("goal", ""),
                plan.get("risk", ""),
                host_id=plan.get("host", ""),
                intent="review",
            )["model_route"]
        except (MaestroError, TypeError):
            expected_model_route = None
        if expected_model_route is None or any(
            assignment.get("model_route") != expected_model_route
            for assignment in by_id.values()
        ):
            issues.append(
                _error(
                    "DECISION_MODEL_ROUTE_MISMATCH",
                    "assignments",
                    "Decision Assignment model routes must match the current read-only review route.",
                )
            )
        if isinstance(plan.get("assignments"), list):
            visiting: set[str] = set()
            visited: set[str] = set()

            def visit(assignment_id: str) -> None:
                if assignment_id in visiting:
                    issues.append(
                        _error(
                            "DECISION_CYCLE",
                            "assignments",
                            "Decision assignment graph contains a cycle.",
                        )
                    )
                    return
                if assignment_id in visited or assignment_id not in by_id:
                    return
                visiting.add(assignment_id)
                for dependency in by_id[assignment_id].get("depends_on", []):
                    visit(dependency)
                visiting.remove(assignment_id)
                visited.add(assignment_id)

            for assignment_id in by_id:
                visit(assignment_id)
        if plan.get("writes_performed") is not False:
            issues.append(
                _error(
                    "DECISION_WRITE_FORBIDDEN",
                    "writes_performed",
                    "Decision plan generation never performs project writes.",
                )
            )

    return {
        "schema_version": "maestro_decision_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "writes_performed": False,
    }


def _contains_implementation_command(statement: str) -> bool:
    folded = statement.casefold()
    return any(
        re.search(pattern, folded) is not None
        for pattern in IMPLEMENTATION_COMMAND_PATTERNS
    )


def validate_specialist_packet(
    packet: Any,
    plan: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    plan_result = validate_decision_plan(plan)
    if plan_result["status"] != "PASS":
        issues.append(
            _error(
                "DECISION_PLAN_INVALID",
                "plan",
                "Cannot validate a packet against an invalid decision plan.",
            )
        )
    if not isinstance(packet, dict):
        issues.append(
            _error(
                "SPECIALIST_PACKET_INVALID",
                "$",
                "Specialist packet must be an object.",
            )
        )
    else:
        required = {
            "schema_version",
            "decision_plan_id",
            "assignment_id",
            "specialist_id",
            "findings",
            "escalations",
        }
        if set(packet) != required:
            issues.append(
                _error(
                    "SPECIALIST_PACKET_INVALID",
                    "$",
                    "Specialist packet fields are invalid.",
                )
            )
        if packet.get("schema_version") != FINDING_PACKET_VERSION:
            issues.append(
                _error(
                    "SPECIALIST_PACKET_VERSION_INVALID",
                    "schema_version",
                    f"Expected {FINDING_PACKET_VERSION}.",
                )
            )
        if packet.get("decision_plan_id") != plan.get("plan_id"):
            issues.append(
                _error(
                    "SPECIALIST_PACKET_PLAN_MISMATCH",
                    "decision_plan_id",
                    "Packet is not bound to this decision plan.",
                )
            )
        assignments = {
            item["assignment_id"]: item
            for item in plan.get("assignments", [])
            if isinstance(item, dict) and "assignment_id" in item
        }
        packet_assignment_id = packet.get("assignment_id")
        packet_specialist_id = packet.get("specialist_id")
        assignment = (
            assignments.get(packet_assignment_id)
            if isinstance(packet_assignment_id, str)
            else None
        )
        if (
            assignment is None
            or assignment.get("specialist_id") != packet_specialist_id
        ):
            issues.append(
                _error(
                    "SPECIALIST_PACKET_ASSIGNMENT_MISMATCH",
                    "assignment_id",
                    "Packet assignment and specialist do not agree with the plan.",
                )
            )
        specialists = {
            item["specialist_id"]: item
            for item in plan.get("specialist_contracts", [])
            if isinstance(item, dict) and "specialist_id" in item
        }
        specialist = (
            specialists.get(packet_specialist_id)
            if isinstance(packet_specialist_id, str)
            else None
        )
        findings = packet.get("findings")
        if not isinstance(findings, list):
            issues.append(
                _error(
                    "SPECIALIST_FINDINGS_INVALID",
                    "findings",
                    "findings must be a list.",
                )
            )
            findings = []
        for index, finding in enumerate(findings):
            path = f"findings[{index}]"
            if not isinstance(finding, dict) or set(finding) != {
                "concern_id",
                "claim_kind",
                "statement",
                "evidence_refs",
                "confidence",
            }:
                issues.append(
                    _error(
                        "SPECIALIST_FINDING_INVALID",
                        path,
                        "Finding fields are invalid.",
                    )
                )
                continue
            if (
                specialist is None
                or finding["concern_id"] not in specialist["owns"]
            ):
                issues.append(
                    _error(
                        "SPECIALIST_SCOPE_VIOLATION",
                        f"{path}.concern_id",
                        "Finding concern is outside the specialist's owned scope.",
                    )
                )
            if (
                specialist is None
                or finding["claim_kind"]
                not in specialist["allowed_claim_kinds"]
            ):
                issues.append(
                    _error(
                        "SPECIALIST_CLAIM_KIND_FORBIDDEN",
                        f"{path}.claim_kind",
                        "Finding claim kind is not allowed for this specialist.",
                    )
                )
            statement = finding["statement"]
            if (
                not isinstance(statement, str)
                or not statement.strip()
                or _contains_implementation_command(statement)
            ):
                issues.append(
                    _error(
                        "SPECIALIST_IMPLEMENTATION_COMMAND_FORBIDDEN",
                        f"{path}.statement",
                        "Specialist findings may state evidence and constraints, not implementation commands or code.",
                    )
                )
            if not _valid_string_list(
                finding["evidence_refs"],
                nonempty=True,
            ):
                issues.append(
                    _error(
                        "SPECIALIST_EVIDENCE_REQUIRED",
                        f"{path}.evidence_refs",
                        "Every finding needs at least one bounded evidence reference.",
                    )
                )
            if (
                not isinstance(finding["confidence"], str)
                or finding["confidence"] not in {"low", "medium", "high"}
            ):
                issues.append(
                    _error(
                        "SPECIALIST_CONFIDENCE_INVALID",
                        f"{path}.confidence",
                        "Confidence must be low, medium, or high.",
                    )
                )
        escalations = packet.get("escalations")
        if not isinstance(escalations, list):
            issues.append(
                _error(
                    "SPECIALIST_ESCALATIONS_INVALID",
                    "escalations",
                    "escalations must be a list.",
                )
            )
            escalations = []
        for index, escalation in enumerate(escalations):
            path = f"escalations[{index}]"
            if not isinstance(escalation, dict) or set(escalation) != {
                "target_specialism",
                "question",
                "evidence_refs",
            }:
                issues.append(
                    _error(
                        "SPECIALIST_ESCALATION_INVALID",
                        path,
                        "Escalation fields are invalid.",
                    )
                )
                continue
            target_specialism = escalation["target_specialism"]
            if (
                not isinstance(target_specialism, str)
                or target_specialism not in specialists
                or target_specialism == packet_specialist_id
            ):
                issues.append(
                    _error(
                        "SPECIALIST_ESCALATION_TARGET_INVALID",
                        f"{path}.target_specialism",
                        "Escalation must target another declared specialism.",
                    )
                )
            if (
                not isinstance(escalation["question"], str)
                or not escalation["question"].strip()
                or not _valid_string_list(
                    escalation["evidence_refs"],
                    nonempty=True,
                )
            ):
                issues.append(
                    _error(
                        "SPECIALIST_ESCALATION_INVALID",
                        path,
                        "Escalation needs one bounded question and evidence.",
                    )
                )

    return {
        "schema_version": "maestro_specialist_packet_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "writes_performed": False,
    }


def validate_decision_bundle(
    bundle: Any,
    plan: dict[str, Any],
    packets: Iterable[dict[str, Any]],
    repo_path: str | Path,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    plan_result = validate_decision_plan(plan)
    if plan_result["status"] != "PASS":
        issues.extend(plan_result["issues"])
    if not isinstance(bundle, dict):
        issues.append(
            _error(
                "DECISION_BUNDLE_INVALID",
                "$",
                "Decision bundle must be an object.",
            )
        )
        return {
            "schema_version": "maestro_decision_bundle_validation_v1",
            "status": "FAIL",
            "execution_status": "INVALID",
            "issues": issues,
            "writes_performed": False,
        }

    required = {
        "schema_version",
        "bundle_digest",
        "decision_plan_id",
        "registry_digest",
        "goal",
        "goal_digest",
        "base_revision",
        "risk",
        "request_contract",
        "expertise",
        "source_packet_digests",
        "accepted_constraints",
        "accepted_decisions",
        "conflicts",
        "unresolved_questions",
        "technical_feasibility",
        "execution_scope",
        "research_gate",
        "status",
    }
    if set(bundle) != required:
        issues.append(
            _error(
                "DECISION_BUNDLE_INVALID",
                "$",
                "Decision bundle fields are invalid.",
            )
        )
    if bundle.get("schema_version") != DECISION_BUNDLE_VERSION:
        issues.append(
            _error(
                "DECISION_BUNDLE_VERSION_INVALID",
                "schema_version",
                f"Expected {DECISION_BUNDLE_VERSION}.",
            )
        )
    if (
        not isinstance(bundle.get("bundle_digest"), str)
        or bundle["bundle_digest"] != _digest_payload(bundle, "bundle_digest")
    ):
        issues.append(
            _error(
                "DECISION_BUNDLE_DIGEST_MISMATCH",
                "bundle_digest",
                "Decision bundle digest does not match its canonical content.",
            )
        )
    for field in (
        "decision_plan_id",
        "registry_digest",
        "goal",
        "goal_digest",
        "base_revision",
        "risk",
        "request_contract",
        "expertise",
        "research_gate",
    ):
        if bundle.get(field) != plan.get(
            {
                "decision_plan_id": "plan_id",
                "research_gate": "expertise",
            }.get(field, field)
        ):
            if field == "research_gate":
                expected = plan.get("expertise", {}).get(
                    "research_requirement"
                )
                matches = bundle.get(field) == expected
            else:
                matches = False
            if not matches:
                issues.append(
                    _error(
                        "DECISION_BUNDLE_PLAN_MISMATCH",
                        field,
                        f"Bundle field {field} does not match the decision plan.",
                    )
                )
    current_revision = repository_revision(repo_path)
    if current_revision["kind"] != "git":
        issues.append(
            _error(
                "DECISION_REVISION_UNAVAILABLE",
                "base_revision",
                "Enactment requires a readable Git revision.",
            )
        )
    elif current_revision != plan.get("base_revision"):
        issues.append(
            _error(
                "DECISION_REVISION_STALE",
                "base_revision",
                "Repository state changed after the decision plan was created.",
            )
        )
    if registry_digest() != plan.get("registry_digest"):
        issues.append(
            _error(
                "DECISION_REGISTRY_STALE",
                "registry_digest",
                "Registry definitions changed after the decision plan was created.",
            )
        )

    packet_by_assignment: dict[str, dict[str, Any]] = {}
    for packet in packets:
        packet_result = validate_specialist_packet(packet, plan)
        if packet_result["status"] != "PASS":
            issues.extend(packet_result["issues"])
            continue
        assignment_id = packet["assignment_id"]
        if assignment_id in packet_by_assignment:
            issues.append(
                _error(
                    "SPECIALIST_PACKET_DUPLICATE",
                    "source_packet_digests",
                    f"Duplicate packet for assignment {assignment_id}.",
                )
            )
        packet_by_assignment[assignment_id] = packet
    expected_packet_assignments = {
        item["assignment_id"]
        for item in plan.get("assignments", [])
        if item.get("specialist_id") is not None
    }
    if set(packet_by_assignment) != expected_packet_assignments:
        issues.append(
            _error(
                "SPECIALIST_PACKET_SET_MISMATCH",
                "source_packet_digests",
                "Provide exactly one valid packet for every specialist assignment.",
            )
        )
    expected_digests = {
        assignment_id: sha256_text(canonical_json(packet))
        for assignment_id, packet in sorted(packet_by_assignment.items())
    }
    if bundle.get("source_packet_digests") != expected_digests:
        issues.append(
            _error(
                "SPECIALIST_PACKET_DIGEST_MISMATCH",
                "source_packet_digests",
                "Bundle packet digests do not match the supplied packets.",
            )
        )

    _validate_request_contract(
        bundle.get("request_contract"),
        "request_contract",
        issues,
    )
    technical_feasibility = bundle.get("technical_feasibility")
    if (
        not isinstance(technical_feasibility, str)
        or technical_feasibility
        not in {"pass", "conditional", "fail"}
    ):
        issues.append(
            _error(
                "TECHNICAL_FEASIBILITY_INVALID",
                "technical_feasibility",
                "Technical feasibility must be pass, conditional, or fail.",
            )
        )
    unresolved = bundle.get("unresolved_questions")
    blocking_questions = []
    if not isinstance(unresolved, list):
        issues.append(
            _error(
                "DECISION_UNRESOLVED_INVALID",
                "unresolved_questions",
                "unresolved_questions must be a list.",
            )
        )
    else:
        for index, question in enumerate(unresolved):
            if not isinstance(question, dict) or set(question) != {
                "question",
                "blocking",
                "owner",
            }:
                issues.append(
                    _error(
                        "DECISION_UNRESOLVED_INVALID",
                        f"unresolved_questions[{index}]",
                        "Unresolved question fields are invalid.",
                    )
                )
                continue
            if question["blocking"] is True:
                blocking_questions.append(question)
            elif question["blocking"] is not False:
                issues.append(
                    _error(
                        "DECISION_UNRESOLVED_INVALID",
                        f"unresolved_questions[{index}].blocking",
                        "blocking must be boolean.",
                    )
                )
    scope = bundle.get("execution_scope")
    if (
        not isinstance(scope, dict)
        or set(scope) != {"allowed_paths", "prohibited_changes"}
        or not _valid_string_list(scope.get("allowed_paths"), nonempty=True)
        or not _valid_string_list(scope.get("prohibited_changes"))
        or any(
            Path(item).is_absolute() or ".." in Path(item).parts
            for item in scope.get("allowed_paths", [])
        )
    ):
        issues.append(
            _error(
                "EXECUTION_SCOPE_INVALID",
                "execution_scope",
                "Execution scope needs safe repository-relative allowed paths.",
            )
        )
    research_gate = bundle.get("research_gate")
    gate = (
        research_gate.get("gate")
        if isinstance(research_gate, dict)
        else None
    )
    request_contract = bundle.get("request_contract")
    side_effect_policy = (
        request_contract.get("side_effect_policy")
        if isinstance(request_contract, dict)
        else None
    )
    ready = (
        not blocking_questions
        and technical_feasibility in {"pass", "conditional"}
        and gate in {"not-required", "satisfied"}
        and side_effect_policy == "after_decision"
    )
    expected_status = "ready" if ready else "blocked"
    if bundle.get("status") != expected_status:
        issues.append(
            _error(
                "DECISION_BUNDLE_STATUS_MISMATCH",
                "status",
                f"Bundle status must be {expected_status}.",
            )
        )
    if side_effect_policy == "forbidden":
        issues.append(
            _error(
                "DECISION_SIDE_EFFECT_FORBIDDEN",
                "request_contract.side_effect_policy",
                "A review-only decision cannot authorize implementation.",
            )
        )
    if technical_feasibility == "fail":
        issues.append(
            _error(
                "DECISION_FEASIBILITY_FAILED",
                "technical_feasibility",
                "Failed technical feasibility blocks implementation.",
            )
        )
    if blocking_questions:
        issues.append(
            _error(
                "DECISION_BLOCKER_OPEN",
                "unresolved_questions",
                "Blocking questions must be resolved before implementation.",
            )
        )
    if gate == "open":
        issues.append(
            _error(
                "DECISION_RESEARCH_REQUIRED",
                "research_gate",
                "Open research gate blocks implementation.",
            )
        )

    return {
        "schema_version": "maestro_decision_bundle_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "execution_status": "READY" if not issues and ready else "BLOCKED",
        "issues": issues,
        "writes_performed": False,
    }


def build_execution_plan(
    repo_path: str | Path,
    plan: dict[str, Any],
    bundle: dict[str, Any],
    packets: Iterable[dict[str, Any]],
    *,
    authorization_source: str,
    host_id: str | None = None,
) -> dict[str, Any]:
    validation = validate_decision_bundle(
        bundle,
        plan,
        packets,
        repo_path,
    )
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    if authorization_source not in {
        "explicit_user",
        "prior_explicit_request",
    }:
        raise MaestroError(
            "EXECUTION_AUTHORIZATION_INVALID",
            "Authorization source must be explicit_user or prior_explicit_request.",
        )
    if (
        bundle["risk"] in {"high", "critical"}
        and authorization_source != "explicit_user"
    ):
        raise MaestroError(
            "USER_DECISION_REQUIRED",
            "High or critical risk enactment requires explicit user authorization.",
        )

    research_requirement = bundle["research_gate"]
    evidence_digest = (
        research_requirement["evidence_digest"]
        if research_requirement["gate"] == "satisfied"
        else None
    )
    route_plan = route_goal_v2(
        bundle["goal"],
        bundle["risk"],
        host_id=host_id or plan["host"],
        intent="implementation",
        research_evidence_digest=evidence_digest,
        decision_authorized=True,
    )
    current_expertise = route_plan.get(
        "expertise",
        {
            "selected_pack_ids": [],
            "selected_guide_ids": [],
            "research_requirement": {
                "mode": "reuse",
                "gate": "not-required",
                "reasons": [],
                "evidence_digest": None,
            },
        },
    )
    if (
        current_expertise["selected_pack_ids"]
        != bundle["expertise"]["selected_pack_ids"]
        or current_expertise["selected_guide_ids"]
        != bundle["expertise"]["selected_guide_ids"]
        or current_expertise["research_requirement"]
        != bundle["expertise"]["research_requirement"]
    ):
        raise MaestroError(
            "DECISION_EXPERTISE_STALE",
            "Expertise selection changed after the decision was made.",
        )

    execution_authorization = {
        "decision_bundle_digest": bundle["bundle_digest"],
        "authorization_source": authorization_source,
        "allowed_side_effects": ["repository_write"],
        "allowed_paths": bundle["execution_scope"]["allowed_paths"],
        "prohibited_changes": bundle["execution_scope"][
            "prohibited_changes"
        ],
        "status": "authorized",
    }
    execution = {
        "schema_version": EXECUTION_PLAN_VERSION,
        "execution_plan_id": "",
        "decision_plan_id": plan["plan_id"],
        "decision_bundle_digest": bundle["bundle_digest"],
        "execution_authorization": execution_authorization,
        "route_plan": route_plan,
        "writes_performed": False,
    }
    execution["execution_plan_id"] = _digest_payload(
        execution,
        "execution_plan_id",
    )
    return execution
