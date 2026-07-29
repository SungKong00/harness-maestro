from __future__ import annotations

import copy
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .authorization import resolve_authorized_write_roots
from .errors import MaestroError
from .expertise import load_expertise_catalog, select_expertise
from .expertise_routing import require_route_hints
from .planning import (
    build_coverage_binding,
    route_goal_v2,
    validate_route_v2,
)
from .model_policy import LEGACY_MODEL_ROUTE_FIELDS
from .research import require_completed_research_bundle
from .registry import (
    _model_route,
    load_registry,
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
EXECUTION_PLAN_FIELDS = {
    "schema_version",
    "execution_plan_id",
    "decision_plan_id",
    "decision_bundle_digest",
    "decision_evidence",
    "execution_authorization",
    "route_plan",
    "writes_performed",
}
EXECUTION_DECISION_EVIDENCE_FIELDS = {
    "decision_plan",
    "decision_bundle",
    "specialist_packets",
}
EXECUTION_AUTHORIZATION_FIELDS = {
    "decision_bundle_digest",
    "authorization_source",
    "allowed_side_effects",
    "allowed_paths",
    "prohibited_changes",
    "status",
}
MAX_DECISION_ASSIGNMENTS = 5
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_PATH_PATTERN = re.compile(
    r"^(?:(?:skills|\.agents/skills)/[a-z0-9]+(?:-[a-z0-9]+)*"
    r"|\.maestro/state/candidates/expertise/[a-z0-9]+(?:-[a-z0-9]+)*/draft)"
    r"/SKILL\.md$"
)
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
    "coverage_binding",
}
DECISION_PLAN_OPTIONAL_FIELDS = {"coverage_binding"}
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


def _route_expertise_binding(route_plan: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical expertise view used by build and validation."""

    expertise = route_plan.get("expertise")
    if isinstance(expertise, dict):
        return expertise
    return {
        "selected_pack_ids": [],
        "selected_guide_ids": [],
        "pack_definition_digests": {},
        "research_requirement": {
            "mode": "reuse",
            "gate": "not-required",
            "reasons": [],
            "evidence_digest": None,
        },
    }


def _decision_expertise_preflight_gaps(
    coverage: dict[str, Any],
    expertise: dict[str, Any],
    *,
    repo_path: str | Path,
) -> list[str]:
    """Return material Guide allocations missing from the staged decision."""

    selected_pack_ids = set(expertise.get("selected_pack_ids", []))
    selected_guide_ids = set(expertise.get("selected_guide_ids", []))
    catalog = load_expertise_catalog(
        repo_path,
        include_candidates=True,
    )
    guide_owners: dict[str, set[str]] = {}
    for pack in catalog:
        if pack.get("status") not in {"pilot", "active"}:
            continue
        pack_id = pack["expertise_pack_id"]
        for guide in pack["guides"]:
            guide_owners.setdefault(guide["guide_id"], set()).add(pack_id)

    missing: list[str] = []
    for item in coverage.get("items", []):
        if (
            not isinstance(item, dict)
            or item.get("materiality") not in {"blocking", "important"}
        ):
            continue
        for allocation in item.get("allocations", []):
            if (
                not isinstance(allocation, dict)
                or allocation.get("kind") != "expertise-guide"
                or not isinstance(allocation.get("target_ref"), str)
            ):
                continue
            target_ref = allocation["target_ref"]
            target = target_ref.removeprefix("guide:")
            if "/" in target:
                pack_id, guide_id = target.split("/", 1)
            else:
                guide_id = target
                owners = guide_owners.get(guide_id, set())
                pack_id = next(iter(owners)) if len(owners) == 1 else ""
            if (
                pack_id not in selected_pack_ids
                or guide_id not in selected_guide_ids
            ):
                missing.append(f"{item.get('item_id')}:{target_ref}")
    return sorted(set(missing))


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
        "expertise_load": {
            "application_mode": "not-applicable",
            "packs": [],
            "host_attestation": {
                "status": "unavailable",
                "loaded_skill_digests": [],
                "loaded_guide_refs": [],
            },
        },
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
            "information-architecture-and-user-flow",
            "interaction-responsive-accessibility",
            "reference-selection",
        }
    ]
    assigned_guides = {*visual_guides, *ux_guides}
    ux_guides.extend(
        item
        for item in selected_guides
        if item not in assigned_guides
    )
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


def _marketing_specialists(
    selected_guides: list[str],
) -> list[dict[str, Any]]:
    strategy_guides = [
        item
        for item in selected_guides
        if item
        in {
            "marketing-brief",
            "positioning-message",
            "measurement-experiment",
        }
    ]
    evidence_guides = [
        item
        for item in selected_guides
        if item
        in {
            "claim-substantiation",
            "customer-market-evidence",
            "competitor-reference-analysis",
            "channel-platform-rules",
        }
    ]
    return [
        _specialist(
            "marketing-strategy",
            summary=(
                "Judge audience, offer, positioning, message hierarchy, and "
                "measurement without publishing or implementing."
            ),
            owns=[
                "audience-and-offer",
                "marketing-measurement",
                "message-hierarchy",
                "positioning",
            ],
            out_of_scope=[
                "implementation-command",
                "legal-conclusion",
                "publication",
                "visual-design",
            ],
            allowed_inputs=[
                "GoalDigest",
                "ProjectContext",
                "SelectedDecisionGuides",
                "ResearchArtifact",
            ],
            allowed_claim_kinds=[
                "constraint",
                "finding",
                "risk",
                "question",
            ],
            guide_ids=strategy_guides,
        ),
        _specialist(
            "marketing-evidence",
            summary=(
                "Audit claims, customer and competitor evidence, and current "
                "channel constraints without inventing facts."
            ),
            owns=[
                "channel-constraint",
                "claim-substantiation",
                "competitor-evidence",
                "customer-evidence",
            ],
            out_of_scope=[
                "implementation-command",
                "legal-conclusion",
                "positioning",
                "publication",
            ],
            allowed_inputs=[
                "GoalDigest",
                "ProjectContext",
                "SelectedDecisionGuides",
                "ResearchArtifact",
            ],
            allowed_claim_kinds=[
                "constraint",
                "finding",
                "risk",
                "question",
            ],
            guide_ids=evidence_guides,
        ),
        _technical_specialist(),
    ]


def _software_qa_specialists(
    selected_guides: list[str],
) -> list[dict[str, Any]]:
    design_guides = [
        item
        for item in selected_guides
        if item
        in {
            "qa-risk-traceability",
            "qa-test-design",
            "qa-scenario-state-exploration",
        }
    ]
    evidence_guides = [
        item
        for item in selected_guides
        if item
        in {
            "qa-quality-handoffs",
            "qa-regression-release",
            "qa-defect-evidence",
        }
    ]
    return [
        _specialist(
            "qa-risk-design",
            summary=(
                "Judge quality risk, traceability, and scenario design without "
                "running tests or modifying code."
            ),
            owns=[
                "quality-risk",
                "requirement-traceability",
                "test-design",
                "test-scenarios",
            ],
            out_of_scope=[
                "implementation-command",
                "release-authorization",
                "test-result",
                "verification-verdict",
            ],
            allowed_inputs=[
                "GoalDigest",
                "ProjectContext",
                "SelectedDecisionGuides",
                "RepositoryEvidence",
                "ResearchArtifact",
            ],
            allowed_claim_kinds=[
                "constraint",
                "finding",
                "risk",
                "question",
            ],
            guide_ids=design_guides,
        ),
        _specialist(
            "qa-release-evidence",
            summary=(
                "Judge regression, release, handoff, and defect evidence "
                "requirements without claiming unrun checks passed."
            ),
            owns=[
                "defect-evidence",
                "quality-handoff",
                "regression-scope",
                "release-evidence",
            ],
            out_of_scope=[
                "implementation-command",
                "quality-risk-priority",
                "release-authorization",
                "test-execution",
            ],
            allowed_inputs=[
                "GoalDigest",
                "ProjectContext",
                "SelectedDecisionGuides",
                "RepositoryEvidence",
                "ResearchArtifact",
            ],
            allowed_claim_kinds=[
                "constraint",
                "finding",
                "risk",
                "question",
            ],
            guide_ids=evidence_guides,
        ),
        _technical_specialist(),
    ]


def _generic_expertise_specialists(
    pack_cards: list[dict[str, Any]],
    selected_guides: list[str],
) -> list[dict[str, Any]]:
    pack = pack_cards[0]
    return [
        _specialist(
            "expertise-domain-review",
            summary=(
                f"Judge only the selected {pack['expertise_pack_id']} "
                "Decision Guides without implementing or widening the domain."
            ),
            owns=[
                f"guide:{guide_id}" for guide_id in selected_guides
            ],
            out_of_scope=[
                "implementation-command",
                "technical-feasibility",
                "unselected-guide",
            ],
            allowed_inputs=[
                "GoalDigest",
                "ProjectContext",
                "SelectedDecisionGuides",
                "RepositoryEvidence",
                "ResearchArtifact",
            ],
            allowed_claim_kinds=[
                "constraint",
                "finding",
                "risk",
                "question",
            ],
            guide_ids=selected_guides,
        ),
        _technical_specialist(),
    ]


def _bind_specialist_expertise(
    specialists: list[dict[str, Any]],
    pack_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bound: list[dict[str, Any]] = []
    for specialist in specialists:
        item = copy.deepcopy(specialist)
        selected = set(item["decision_guide_ids"])
        packs: list[dict[str, Any]] = []
        for pack in pack_cards:
            guides = [
                {
                    "guide_id": guide["guide_id"],
                    "skill_id": guide["skill_id"],
                    "resource_path": guide["resource_path"],
                    "skill_definition_digest": guide[
                        "skill_definition_digest"
                    ],
                }
                for guide in pack.get("guides", [])
                if guide.get("guide_id") in selected
            ]
            if guides:
                packs.append(
                    {
                        "expertise_pack_id": pack["expertise_pack_id"],
                        "skill_id": pack["skill_id"],
                        "skill_path": pack["skill_path"],
                        "definition_digest": pack["definition_digest"],
                        "skill_definition_digest": pack[
                            "skill_definition_digest"
                        ],
                        "guides": guides,
                    }
                )
        item["expertise_load"] = {
            "application_mode": (
                "advisory-only" if packs else "not-applicable"
            ),
            "packs": packs,
            "host_attestation": {
                "status": "unavailable",
                "loaded_skill_digests": [],
                "loaded_guide_refs": [],
            },
        }
        bound.append(item)
    return bound


def _lens_specialists(
    lens_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    specialists: list[dict[str, Any]] = []
    for lens in lens_cards:
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


def _decision_model_route(
    *,
    goal: str,
    risk: str,
    host_id: str,
    assignment_id: str,
    kind: str,
) -> dict[str, Any]:
    stage_kind = {
        "specialist-review": (
            "technical-feasibility"
            if assignment_id == "technical-feasibility-review"
            else "specialist-review"
        ),
        "synthesis": (
            "final-synthesis"
            if assignment_id == "final-synthesis"
            else "intermediate-synthesis"
        ),
    }.get(kind)
    if stage_kind is None:
        raise MaestroError(
            "MODEL_STAGE_UNKNOWN",
            f"Decision assignment kind {kind!r} has no model stage policy.",
        )
    executor = next(
        item
        for item in load_registry()["executors"]
        if item["executor_id"] == "lens-reviewer"
    )
    return _model_route(
        goal,
        risk,
        [],
        executor,
        host_id,
        execution_unit_id=assignment_id,
        stage_kind=stage_kind,
    )


def _decision_assignments(
    specialists: list[dict[str, Any]],
    *,
    product_design: bool,
    goal: str,
    risk: str,
    host_id: str,
) -> list[dict[str, Any]]:
    def model_route(assignment_id: str, kind: str) -> dict[str, Any]:
        return _decision_model_route(
            goal=goal,
            risk=risk,
            host_id=host_id,
            assignment_id=assignment_id,
            kind=kind,
        )

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
                model_route=model_route(
                    "visual-design-review",
                    "specialist-review",
                ),
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
                model_route=model_route(
                    "ux-product-review",
                    "specialist-review",
                ),
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
                model_route=model_route(
                    f"{specialist['specialist_id']}-assignment",
                    "specialist-review",
                ),
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
            model_route=model_route("synthesis-1", "synthesis"),
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
            model_route=model_route(
                "technical-feasibility-review",
                "specialist-review",
            ),
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
            model_route=model_route("final-synthesis", "synthesis"),
        ),
    ]


def build_decision_plan(
    repo_path: str | Path,
    goal: str,
    risk: str,
    *,
    host_id: str = "codex",
    intent: str = "implementation",
    research_evidence: dict[str, Any] | None = None,
    route_hints: dict[str, Any] | None = None,
    prior_route_plan: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
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
            "forbidden_side_effects": request_contract[
                "forbidden_side_effects"
            ],
        }

    normalized_route_hints = (
        require_route_hints(route_hints)
        if route_hints is not None
        else None
    )
    if (
        normalized_route_hints is not None
        and normalized_route_hints["route_attempt"] == 2
    ):
        if not isinstance(prior_route_plan, dict):
            raise MaestroError(
                "EXPERTISE_REROUTE_LINEAGE_REQUIRED",
                "A corrected decision route requires the exact prior route v2 plan.",
            )
        prior_validation = validate_route_v2(
            prior_route_plan,
            repo_path=repo_path,
        )
        if prior_validation["status"] != "PASS":
            first = prior_validation["issues"][0]
            raise MaestroError(first["code"], first["message"])
        if (
            normalized_route_hints["prior_plan_id"]
            != prior_route_plan["plan_id"]
            or normalized_route_hints["prior_source_route_digest"]
            != prior_route_plan["source_route_digest"]
        ):
            raise MaestroError(
                "EXPERTISE_REROUTE_LINEAGE_MISMATCH",
                "Decision route hints do not match the supplied prior route plan.",
            )

    expertise_intent = (
        "review"
        if request_contract["side_effect_policy"] == "forbidden"
        else "implementation"
    )
    expertise, _ = select_expertise(
        goal,
        intent=expertise_intent,
        route_hints=normalized_route_hints,
        repo_path=repo_path,
    )
    if research_evidence is not None:
        validation = require_completed_research_bundle(
            research_evidence,
            goal=goal,
            expertise=expertise,
            repo_path=repo_path,
        )
        expertise, _ = select_expertise(
            goal,
            intent=expertise_intent,
            route_hints=normalized_route_hints,
            research_evidence_digest=validation["artifact_digest"],
            repo_path=repo_path,
        )
    review_route = route_goal(
        goal,
        risk,
        host_id=host_id,
        intent="review",
    )
    coverage_binding: dict[str, Any] | None = None
    if coverage is not None:
        coverage_binding = build_coverage_binding(
            coverage,
            goal=goal,
            repo_path=repo_path,
        )
        preflight_gaps = _decision_expertise_preflight_gaps(
            coverage,
            expertise,
            repo_path=repo_path,
        )
        if preflight_gaps:
            raise MaestroError(
                "DECISION_MULTIPACK_PREFLIGHT_UNSUPPORTED",
                (
                    "A staged decision cannot run before all material Coverage "
                    "Guide judgments are available. The staged pre-specialist "
                    "multi-Pack closure binding is not implemented; use the "
                    "ordinary multi-Pack route only when direction is already "
                    "settled. Missing allocations: "
                    + ", ".join(preflight_gaps)
                ),
            )
    selected_pack_ids = expertise["selected_pack_ids"]
    selected_families = {
        *selected_pack_ids,
        *(
            card["extends"]["expertise_pack_id"]
            for card in expertise["pack_cards"]
            if card.get("extends") is not None
        ),
    }
    product_design = "product-design" in selected_families
    if product_design:
        specialists = _product_design_specialists(
            expertise["selected_guide_ids"]
        )
    elif "marketing" in selected_families:
        specialists = _marketing_specialists(
            expertise["selected_guide_ids"]
        )
    elif "software-qa" in selected_families:
        specialists = _software_qa_specialists(
            expertise["selected_guide_ids"]
        )
    elif expertise["pack_cards"]:
        specialists = _generic_expertise_specialists(
            expertise["pack_cards"],
            expertise["selected_guide_ids"],
        )
    else:
        specialists = [
            *_lens_specialists(review_route["lens_cards"]),
            _technical_specialist(),
        ]
        review_specialist_ids = [
            specialist["specialist_id"]
            for specialist in specialists
            if specialist["specialist_id"] != "technical-feasibility"
        ]
        if len(review_specialist_ids) > 2:
            raise MaestroError(
                "DECISION_COVERAGE_CAPACITY_EXCEEDED",
                (
                    "The decision plan selected more independent Lens reviews "
                    "than the five-assignment execution contract can preserve: "
                    f"{', '.join(review_specialist_ids)}. Nothing was truncated."
                ),
            )
    specialists = _bind_specialist_expertise(
        specialists,
        expertise["pack_cards"],
    )
    assignments = _decision_assignments(
        specialists,
        product_design=product_design,
        goal=goal,
        risk=risk,
        host_id=host_id,
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
            "pack_definition_digests": expertise[
                "pack_definition_digests"
            ],
            "research_requirement": expertise["research_requirement"],
            **(
                {"route_hints": copy.deepcopy(normalized_route_hints)}
                if normalized_route_hints is not None
                else {}
            ),
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
    if coverage_binding is not None:
        plan["coverage_binding"] = coverage_binding
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


def _validate_specialist_expertise_load(
    value: Any,
    expected_guide_ids: list[str],
    path: str,
    issues: list[dict[str, str]],
) -> None:
    expected_mode = "advisory-only" if expected_guide_ids else "not-applicable"
    if not isinstance(value, dict) or set(value) != {
        "application_mode",
        "packs",
        "host_attestation",
    }:
        issues.append(
            _error(
                "SPECIALIST_EXPERTISE_LOAD_INVALID",
                path,
                "Expertise load must contain application mode, packs, and Host attestation.",
            )
        )
        return
    packs = value.get("packs")
    host = value.get("host_attestation")
    if (
        value.get("application_mode") != expected_mode
        or not isinstance(packs, list)
        or len(packs) > 1
        or not isinstance(host, dict)
        or host
        != {
            "status": "unavailable",
            "loaded_skill_digests": [],
            "loaded_guide_refs": [],
        }
    ):
        issues.append(
            _error(
                "SPECIALIST_EXPERTISE_LOAD_INVALID",
                path,
                "Decision specialists must have a bounded advisory-only load and no fabricated Host attestation.",
            )
        )
        return

    loaded_guide_ids: list[str] = []
    for pack_index, pack in enumerate(packs):
        pack_path = f"{path}.packs[{pack_index}]"
        required = {
            "expertise_pack_id",
            "skill_id",
            "skill_path",
            "definition_digest",
            "skill_definition_digest",
            "guides",
        }
        skill_path = pack.get("skill_path") if isinstance(pack, dict) else None
        if (
            not isinstance(pack, dict)
            or set(pack) != required
            or not isinstance(pack.get("expertise_pack_id"), str)
            or ID_PATTERN.fullmatch(pack["expertise_pack_id"]) is None
            or not isinstance(pack.get("skill_id"), str)
            or ID_PATTERN.fullmatch(pack["skill_id"]) is None
            or (
                skill_path is not None
                and (
                    not isinstance(skill_path, str)
                    or SKILL_PATH_PATTERN.fullmatch(skill_path) is None
                )
            )
            or not isinstance(pack.get("definition_digest"), str)
            or DIGEST_PATTERN.fullmatch(pack["definition_digest"]) is None
            or not isinstance(pack.get("skill_definition_digest"), str)
            or DIGEST_PATTERN.fullmatch(
                pack["skill_definition_digest"]
            ) is None
            or not isinstance(pack.get("guides"), list)
            or not pack["guides"]
        ):
            issues.append(
                _error(
                    "SPECIALIST_EXPERTISE_PACK_INVALID",
                    pack_path,
                    "Specialist Expertise Pack identity, path, digest, or Guides are invalid.",
                )
            )
            continue
        for guide_index, guide in enumerate(pack["guides"]):
            guide_path = f"{pack_path}.guides[{guide_index}]"
            resource_path = (
                guide.get("resource_path")
                if isinstance(guide, dict)
                else None
            )
            if (
                not isinstance(guide, dict)
                or set(guide) != {
                    "guide_id",
                    "skill_id",
                    "resource_path",
                    "skill_definition_digest",
                }
                or not isinstance(guide.get("guide_id"), str)
                or ID_PATTERN.fullmatch(guide["guide_id"]) is None
                or guide["guide_id"] in loaded_guide_ids
                or not isinstance(guide.get("skill_id"), str)
                or ID_PATTERN.fullmatch(guide["skill_id"]) is None
                or not isinstance(resource_path, str)
                or not resource_path.startswith("references/")
                or ".." in Path(resource_path).parts
                or not isinstance(
                    guide.get("skill_definition_digest"),
                    str,
                )
                or DIGEST_PATTERN.fullmatch(
                    guide["skill_definition_digest"]
                ) is None
            ):
                issues.append(
                    _error(
                        "SPECIALIST_EXPERTISE_GUIDE_INVALID",
                        guide_path,
                        "Specialist Guide identity, resource path, or digest is invalid.",
                    )
                )
                continue
            loaded_guide_ids.append(guide["guide_id"])

    if set(loaded_guide_ids) != set(expected_guide_ids):
        issues.append(
            _error(
                "SPECIALIST_EXPERTISE_GUIDE_MISMATCH",
                path,
                "Specialist Expertise load must resolve every and only its selected Decision Guides.",
            )
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
        "forbidden_side_effects",
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
    forbidden_side_effects = value.get("forbidden_side_effects")
    if (
        not isinstance(forbidden_side_effects, list)
        or len(forbidden_side_effects) > 2
        or len(set(forbidden_side_effects)) != len(forbidden_side_effects)
        or any(
            item not in {"git_commit", "remote_write"}
            for item in forbidden_side_effects
        )
    ):
        issues.append(
            _error(
                "REQUEST_CONTRACT_INVALID",
                f"{path}.forbidden_side_effects",
                "Forbidden side effects must use the closed external-effect vocabulary.",
            )
        )


def validate_decision_plan(plan: Any) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if not isinstance(plan, dict):
        issues.append(
            _error("DECISION_PLAN_INVALID", "$", "Decision plan must be an object.")
        )
    else:
        if (
            set(plan) - DECISION_PLAN_OPTIONAL_FIELDS
            != DECISION_PLAN_FIELDS - DECISION_PLAN_OPTIONAL_FIELDS
            or set(plan) - DECISION_PLAN_FIELDS
        ):
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
        coverage_binding = plan.get("coverage_binding")
        if coverage_binding is not None and (
            not isinstance(coverage_binding, dict)
            or set(coverage_binding)
            != {
                "schema_version",
                "coverage_id",
                "goal_digest",
                "required_for_mutation",
            }
            or coverage_binding.get("schema_version")
            != "maestro_task_coverage_binding_v1"
            or not isinstance(coverage_binding.get("coverage_id"), str)
            or DIGEST_PATTERN.fullmatch(
                coverage_binding["coverage_id"]
            )
            is None
            or coverage_binding.get("goal_digest")
            != plan.get("goal_digest")
            or coverage_binding.get("required_for_mutation") is not True
        ):
            issues.append(
                _error(
                    "DECISION_COVERAGE_BINDING_INVALID",
                    "coverage_binding",
                    "Decision Coverage binding is invalid.",
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
                "expertise_load",
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
            _validate_specialist_expertise_load(
                specialist.get("expertise_load"),
                specialist.get("decision_guide_ids", []),
                f"{path}.expertise_load",
                issues,
            )
        expertise = plan.get("expertise")
        if isinstance(expertise, dict) and "route_hints" in expertise:
            try:
                require_route_hints(expertise["route_hints"])
            except MaestroError as exc:
                issues.append(
                    _error(
                        exc.code,
                        "expertise.route_hints",
                        exc.message,
                    )
                )
        selected_guide_ids = (
            expertise.get("selected_guide_ids", [])
            if isinstance(expertise, dict)
            else []
        )
        assigned_guide_ids = {
            guide_id
            for specialist in specialists
            if isinstance(specialist, dict)
            for guide_id in specialist.get("decision_guide_ids", [])
            if isinstance(guide_id, str)
        }
        if (
            isinstance(selected_guide_ids, list)
            and set(selected_guide_ids) != assigned_guide_ids
        ):
            issues.append(
                _error(
                    "SPECIALIST_GUIDE_COVERAGE_INVALID",
                    "specialist_contracts",
                    (
                        "Every selected Decision Guide must be assigned to "
                        "at least one specialist, with no unselected Guide "
                        "introduced."
                    ),
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
            expected_model_routes = {
                assignment_id: _decision_model_route(
                    goal=plan.get("goal", ""),
                    risk=plan.get("risk", ""),
                    host_id=plan.get("host", ""),
                    assignment_id=assignment_id,
                    kind=assignment.get("kind", ""),
                )
                for assignment_id, assignment in by_id.items()
            }
        except (MaestroError, TypeError, StopIteration):
            expected_model_routes = {}
        legacy_routes = {
            assignment_id
            for assignment_id, assignment in by_id.items()
            if isinstance(assignment.get("model_route"), dict)
            and set(assignment["model_route"]) == LEGACY_MODEL_ROUTE_FIELDS
        }
        if (
            set(expected_model_routes) != set(by_id)
            or bool(legacy_routes)
            or any(
                assignment.get("model_route")
                != expected_model_routes.get(assignment_id)
                for assignment_id, assignment in by_id.items()
            )
        ):
            issues.append(
                _error(
                    "DECISION_MODEL_ROUTE_MISMATCH",
                    "assignments",
                    (
                        "Decision Assignment model routes must be typed and "
                        "match their explicit stage policies; legacy routes "
                        "must be regenerated before reuse."
                    ),
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
        elif len(findings) > 5:
            issues.append(
                _error(
                    "SPECIALIST_FINDING_LIMIT_EXCEEDED",
                    "findings",
                    "Specialist packets permit at most five findings.",
                )
            )
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
        elif len(escalations) > 3:
            issues.append(
                _error(
                    "SPECIALIST_ESCALATION_LIMIT_EXCEEDED",
                    "escalations",
                    "Specialist packets permit at most three escalations.",
                )
            )
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
    scope_shape_valid = (
        isinstance(scope, dict)
        and set(scope) == {"allowed_paths", "prohibited_changes"}
        and _valid_string_list(scope.get("allowed_paths"), nonempty=True)
        and _valid_string_list(scope.get("prohibited_changes"))
    )
    if not scope_shape_valid:
        issues.append(
            _error(
                "EXECUTION_SCOPE_INVALID",
                "execution_scope",
                "Execution scope needs safe repository-relative allowed paths.",
            )
        )
    else:
        try:
            resolve_authorized_write_roots(
                repo_path,
                scope["allowed_paths"],
            )
        except MaestroError as exc:
            issues.append(
                _error(
                    "EXECUTION_SCOPE_INVALID",
                    "execution_scope.allowed_paths",
                    exc.message,
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
    research_evidence: dict[str, Any] | None = None,
    prior_route_plan: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
    model_policy_overlays: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    packet_list = sorted(
        [copy.deepcopy(packet) for packet in packets],
        key=lambda packet: str(
            packet.get("assignment_id")
            if isinstance(packet, dict)
            else ""
        ),
    )
    validation = validate_decision_bundle(
        bundle,
        plan,
        packet_list,
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
    if evidence_digest is not None:
        if research_evidence is None:
            raise MaestroError(
                "RESEARCH_EVIDENCE_ARTIFACT_REQUIRED",
                "Enactment requires the exact completed ResearchBundle, not only its digest.",
            )
        research_validation = require_completed_research_bundle(
            research_evidence,
            goal=bundle["goal"],
            expertise=bundle["expertise"],
            repo_path=repo_path,
        )
        if research_validation["artifact_digest"] != evidence_digest:
            raise MaestroError(
                "RESEARCH_EVIDENCE_DIGEST_MISMATCH",
                "Enactment ResearchBundle does not match the decision bundle.",
            )
    elif research_evidence is not None:
        raise MaestroError(
            "RESEARCH_EVIDENCE_NOT_APPLICABLE",
            "This decision bundle has no satisfied research gate.",
        )
    route_hints = plan.get("expertise", {}).get("route_hints")
    coverage_binding = plan.get("coverage_binding")
    if coverage_binding is not None:
        if coverage is None:
            raise MaestroError(
                "TASK_COVERAGE_REQUIRED",
                "Enactment requires the exact Task Coverage bound by the decision plan.",
            )
        if build_coverage_binding(
            coverage,
            goal=bundle["goal"],
            repo_path=repo_path,
        ) != coverage_binding:
            raise MaestroError(
                "TASK_COVERAGE_BINDING_MISMATCH",
                "Enactment Task Coverage does not match the decision plan.",
            )
    elif coverage is not None:
        raise MaestroError(
            "TASK_COVERAGE_NOT_APPLICABLE",
            "Unbound Task Coverage cannot be introduced during enactment.",
        )
    if (
        isinstance(route_hints, dict)
        and route_hints.get("route_attempt") == 2
        and prior_route_plan is None
    ):
        raise MaestroError(
            "EXPERTISE_REROUTE_LINEAGE_REQUIRED",
            "Enactment of a corrected decision requires the exact prior route v2 plan.",
        )
    route_plan = route_goal_v2(
        bundle["goal"],
        bundle["risk"],
        host_id=host_id or plan["host"],
        intent="implementation",
        research_evidence=research_evidence,
        decision_authorized=True,
        repo_path=repo_path,
        route_hints=route_hints,
        prior_route_plan=prior_route_plan,
        coverage=coverage,
        model_policy_overlays=model_policy_overlays,
    )
    current_expertise = _route_expertise_binding(route_plan)
    if (
        current_expertise["selected_pack_ids"]
        != bundle["expertise"]["selected_pack_ids"]
        or current_expertise["selected_guide_ids"]
        != bundle["expertise"]["selected_guide_ids"]
        or current_expertise["pack_definition_digests"]
        != bundle["expertise"]["pack_definition_digests"]
        or current_expertise["research_requirement"]
        != bundle["expertise"]["research_requirement"]
        or current_expertise.get("route_hints")
        != bundle["expertise"].get("route_hints")
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
        "decision_evidence": {
            "decision_plan": copy.deepcopy(plan),
            "decision_bundle": copy.deepcopy(bundle),
            "specialist_packets": packet_list,
        },
        "execution_authorization": execution_authorization,
        "route_plan": route_plan,
        "writes_performed": False,
    }
    execution["execution_plan_id"] = _digest_payload(
        execution,
        "execution_plan_id",
    )
    return execution


def validate_execution_plan(
    execution: Any,
    *,
    repo_path: str | Path | None = None,
    research_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the decision authorization wrapper and its executable route."""

    issues: list[dict[str, str]] = []
    if not isinstance(execution, dict):
        issues.append(
            _error(
                "EXECUTION_PLAN_INVALID",
                "$",
                "Execution plan must be an object.",
            )
        )
        execution = {}
    elif set(execution) != EXECUTION_PLAN_FIELDS:
        issues.append(
            _error(
                "EXECUTION_PLAN_FIELDS_INVALID",
                "$",
                "Execution plan fields do not match the published contract.",
            )
        )

    if execution.get("schema_version") != EXECUTION_PLAN_VERSION:
        issues.append(
            _error(
                "EXECUTION_PLAN_VERSION_INVALID",
                "schema_version",
                f"Expected {EXECUTION_PLAN_VERSION}.",
            )
        )
    execution_plan_id = execution.get("execution_plan_id")
    if (
        not isinstance(execution_plan_id, str)
        or DIGEST_PATTERN.fullmatch(execution_plan_id) is None
        or execution_plan_id != _digest_payload(execution, "execution_plan_id")
    ):
        issues.append(
            _error(
                "EXECUTION_PLAN_DIGEST_MISMATCH",
                "execution_plan_id",
                "Execution plan digest does not match its canonical content.",
            )
        )
    for field in ("decision_plan_id", "decision_bundle_digest"):
        value = execution.get(field)
        if (
            not isinstance(value, str)
            or DIGEST_PATTERN.fullmatch(value) is None
        ):
            issues.append(
                _error(
                    "EXECUTION_PLAN_BINDING_INVALID",
                    field,
                    f"{field} must be a SHA-256 digest.",
                )
            )
    if execution.get("writes_performed") is not False:
        issues.append(
            _error(
                "EXECUTION_PLAN_WRITE_INVALID",
                "writes_performed",
                "Building an execution plan must remain read-only.",
            )
        )

    decision_evidence = execution.get("decision_evidence")
    evidence_plan: Any = None
    evidence_bundle: Any = None
    evidence_packets: Any = None
    if (
        not isinstance(decision_evidence, dict)
        or set(decision_evidence)
        != EXECUTION_DECISION_EVIDENCE_FIELDS
    ):
        issues.append(
            _error(
                "EXECUTION_DECISION_EVIDENCE_INVALID",
                "decision_evidence",
                (
                    "Execution authorization requires the exact bounded "
                    "DecisionPlan, DecisionBundle, and Specialist packets."
                ),
            )
        )
    else:
        evidence_plan = decision_evidence.get("decision_plan")
        evidence_bundle = decision_evidence.get("decision_bundle")
        evidence_packets = decision_evidence.get("specialist_packets")
        if not isinstance(evidence_packets, list):
            issues.append(
                _error(
                    "EXECUTION_DECISION_EVIDENCE_INVALID",
                    "decision_evidence.specialist_packets",
                    "Specialist evidence packets must be a bounded list.",
                )
            )
        elif not isinstance(evidence_plan, dict) or not isinstance(
            evidence_bundle,
            dict,
        ):
            issues.append(
                _error(
                    "EXECUTION_DECISION_EVIDENCE_INVALID",
                    "decision_evidence",
                    "DecisionPlan and DecisionBundle evidence must be objects.",
                )
            )
        elif repo_path is None:
            issues.append(
                _error(
                    "EXECUTION_AUTHORIZATION_CONTEXT_REQUIRED",
                    "decision_evidence",
                    "Execution authorization must be verified against one repository.",
                )
            )
        else:
            decision_validation = validate_decision_bundle(
                evidence_bundle,
                evidence_plan,
                evidence_packets,
                repo_path,
            )
            if decision_validation["status"] != "PASS":
                for issue in decision_validation["issues"]:
                    issues.append(
                        _error(
                            "EXECUTION_DECISION_EVIDENCE_INVALID",
                            (
                                "decision_evidence."
                                + issue.get("path", "$")
                            ),
                            issue.get(
                                "message",
                                "Decision evidence is invalid.",
                            ),
                        )
                    )
        if (
            not isinstance(evidence_plan, dict)
            or evidence_plan.get("plan_id")
            != execution.get("decision_plan_id")
            or not isinstance(evidence_bundle, dict)
            or evidence_bundle.get("bundle_digest")
            != execution.get("decision_bundle_digest")
        ):
            issues.append(
                _error(
                    "EXECUTION_DECISION_EVIDENCE_BINDING_MISMATCH",
                    "decision_evidence",
                    "Embedded decision evidence does not match the execution wrapper.",
                )
            )

    authorization = execution.get("execution_authorization")
    if (
        not isinstance(authorization, dict)
        or set(authorization) != EXECUTION_AUTHORIZATION_FIELDS
    ):
        issues.append(
            _error(
                "EXECUTION_AUTHORIZATION_INVALID",
                "execution_authorization",
                "Execution authorization fields are invalid.",
            )
        )
    else:
        if (
            authorization.get("decision_bundle_digest")
            != execution.get("decision_bundle_digest")
        ):
            issues.append(
                _error(
                    "EXECUTION_AUTHORIZATION_BINDING_MISMATCH",
                    "execution_authorization.decision_bundle_digest",
                    "Execution authorization must bind the wrapper DecisionBundle digest.",
                )
            )
        if authorization.get("authorization_source") not in {
            "explicit_user",
            "prior_explicit_request",
        }:
            issues.append(
                _error(
                    "EXECUTION_AUTHORIZATION_INVALID",
                    "execution_authorization.authorization_source",
                    "Execution authorization source is unsupported.",
                )
            )
        if (
            authorization.get("allowed_side_effects")
            != ["repository_write"]
            or authorization.get("status") != "authorized"
            or not _valid_string_list(
                authorization.get("allowed_paths"),
                nonempty=True,
            )
            or not _valid_string_list(
                authorization.get("prohibited_changes")
            )
        ):
            issues.append(
                _error(
                    "EXECUTION_AUTHORIZATION_INVALID",
                    "execution_authorization",
                    "Execution authorization must contain one writer effect, bounded paths, and prohibited changes.",
                )
            )
        if isinstance(evidence_bundle, dict):
            scope = evidence_bundle.get("execution_scope")
            if (
                not isinstance(scope, dict)
                or authorization.get("allowed_paths")
                != scope.get("allowed_paths")
                or authorization.get("prohibited_changes")
                != scope.get("prohibited_changes")
            ):
                issues.append(
                    _error(
                        "EXECUTION_AUTHORIZATION_SCOPE_MISMATCH",
                        "execution_authorization",
                        "Execution authorization scope must exactly match the validated DecisionBundle.",
                    )
                )
            if (
                evidence_bundle.get("risk") in {"high", "critical"}
                and authorization.get("authorization_source")
                != "explicit_user"
            ):
                issues.append(
                    _error(
                        "USER_DECISION_REQUIRED",
                        "execution_authorization.authorization_source",
                        "High or critical risk enactment requires explicit user authorization.",
                    )
                )

    route_plan = execution.get("route_plan")
    try:
        route_validation = validate_route_v2(
            route_plan,
            repo_path=repo_path,
            research_bundle=research_bundle,
        )
    except (MaestroError, OSError, TypeError, ValueError) as exc:
        route_validation = {
            "status": "FAIL",
            "execution_status": "INVALID",
            "issues": [
                {
                    "code": "EXECUTION_ROUTE_INVALID",
                    "path": "route_plan",
                    "message": str(exc),
                }
            ],
        }
    if route_validation["status"] != "PASS":
        for issue in route_validation.get("issues", []):
            issues.append(
                _error(
                    "EXECUTION_ROUTE_INVALID",
                    f"route_plan.{issue.get('path', '$')}",
                    issue.get("message", "Execution route is invalid."),
                )
            )
    elif (
        route_validation.get("execution_status") != "READY"
        or not isinstance(route_plan, dict)
        or route_plan.get("intent") != "implementation"
        or route_plan.get("mutation_owner_assignment_id") is None
    ):
        issues.append(
            _error(
                "EXECUTION_ROUTE_NOT_READY",
                "route_plan",
                "Execution authorization requires one ready implementation route with a mutation owner.",
            )
        )
    elif isinstance(evidence_plan, dict) and isinstance(
        evidence_bundle,
        dict,
    ):
        route_expertise = _route_expertise_binding(route_plan)
        if (
            route_plan.get("goal") != evidence_bundle.get("goal")
            or route_plan.get("risk") != evidence_bundle.get("risk")
            or route_plan.get("registry_digest")
            != evidence_bundle.get("registry_digest")
            or route_plan.get("coverage_binding")
            != evidence_plan.get("coverage_binding")
            or route_expertise.get("selected_pack_ids", [])
            != evidence_bundle.get("expertise", {}).get(
                "selected_pack_ids",
                [],
            )
            or route_expertise.get("selected_guide_ids", [])
            != evidence_bundle.get("expertise", {}).get(
                "selected_guide_ids",
                [],
            )
            or route_expertise.get("pack_definition_digests", {})
            != evidence_bundle.get("expertise", {}).get(
                "pack_definition_digests",
                {},
            )
            or route_expertise.get("research_requirement")
            != evidence_bundle.get("research_gate")
            or route_expertise.get("route_hints")
            != evidence_bundle.get("expertise", {}).get("route_hints")
        ):
            issues.append(
                _error(
                    "EXECUTION_DECISION_ROUTE_MISMATCH",
                    "route_plan",
                    "Executable route does not preserve the validated Decision evidence.",
                )
            )

    issues.sort(key=lambda item: (item["code"], item["path"], item["message"]))
    return {
        "schema_version": "maestro_execution_plan_validation_v1",
        "status": "PASS" if not issues else "FAIL",
        "execution_status": (
            "READY"
            if not issues
            else (
                "RESEARCH_REQUIRED"
                if route_validation.get("execution_status")
                == "RESEARCH_REQUIRED"
                else "INVALID"
            )
        ),
        "execution_plan_id": execution_plan_id,
        "route_plan_id": (
            route_plan.get("plan_id")
            if isinstance(route_plan, dict)
            else None
        ),
        "issues": issues,
        "writes_performed": False,
    }
