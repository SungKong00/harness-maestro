from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .assignment_contracts import (
    project_assignment_input,
    validate_assignment_packet,
)
from .component_candidates import validate_component_candidate
from .codex_host import (
    DEFAULT_TIMEOUT_SECONDS,
    run_codex_host,
)
from .decisions import (
    build_decision_plan,
    build_execution_plan,
    validate_decision_plan,
    validate_specialist_packet,
)
from .conventions import (
    apply_convention_draft_plan,
    apply_convention_lifecycle_plan,
    build_convention_activation_plan,
    build_convention_draft_plan,
    build_convention_update_plan,
)
from .doctor import doctor_report
from .dashboard import serve_dashboard
from .documents import select_documents
from .errors import MaestroError
from .expertise import select_expertise
from .expertise_routing import (
    WORK_KIND_TO_PACK_ID,
    normalize_route_hints,
)
from .expertise_lifecycle import (
    apply_expertise_activation_plan,
    apply_expertise_archive_plan,
    apply_expertise_change_set_plan,
    apply_expertise_delete_plan,
    apply_expertise_deactivation_plan,
    apply_expertise_export_plan,
    apply_expertise_global_promotion_plan,
    apply_expertise_rejection_plan,
    apply_expertise_restore_plan,
    apply_expertise_update_plan,
    build_expertise_activation_plan,
    build_expertise_archive_plan,
    build_expertise_change_set_plan,
    build_expertise_delete_plan,
    build_expertise_deactivation_plan,
    build_expertise_export_plan,
    build_expertise_global_promotion_plan,
    build_expertise_rejection_plan,
    build_expertise_restore_plan,
    build_expertise_update_plan,
    expertise_inventory,
    validate_expertise_contribution,
    validate_expertise_candidate,
)
from .expertise_reconcile import (
    apply_expertise_reconcile_plan,
    build_expertise_reconcile_plan,
)
from .expertise_promotion import (
    apply_expertise_promotion_decision_plan,
    build_expertise_promotion_decision_plan,
)
from .governance import finalize_run, govern_report, record_run
from .host import apply_host_sync_plan, build_host_sync_plan
from .observations import (
    attach_run_plan,
    import_codex_app_server_trace,
    record_execution_fallback,
    record_host_observation,
    record_stage_observation,
    record_work_finish,
    record_work_start,
    start_desktop_request_observation,
    start_run_observation,
)
from .project import (
    apply_plan,
    build_init_plan,
    build_upgrade_plan,
    inspect_adapter,
)
from .research import (
    BUNDLE_VERSION,
    expected_research_binding,
    validate_research_artifact,
)
from .planning import route_goal_v2, validate_route_v2
from .registry import route_goal
from .status import status_report
from .snapshot import snapshot_report
from .surface_classification import classify_surface_file
from .util import read_json
from .verification import (
    apply_verification_approval_plan,
    build_verification_approval_plan,
    verification_inventory,
)


def _research_evidence_digest(
    artifact_path: str | None,
    expected_digest: str | None,
    *,
    repo_path: str,
    goal: str,
    intent: str,
    route_hints: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if artifact_path is None:
        if expected_digest is not None:
            raise MaestroError(
                "RESEARCH_EVIDENCE_ARTIFACT_REQUIRED",
                "--research-evidence-digest must be paired with a validated "
                "--research-evidence ResearchBundle file.",
            )
        return None

    path = Path(artifact_path).expanduser().resolve()
    if not path.is_file():
        raise MaestroError(
            "RESEARCH_EVIDENCE_NOT_FOUND",
            f"Research evidence is not a readable file: {path}",
        )
    artifact = read_json(path)
    if (
        not isinstance(artifact, dict)
        or artifact.get("schema_version") != BUNDLE_VERSION
    ):
        raise MaestroError(
            "RESEARCH_BUNDLE_REQUIRED",
            "A research gate requires a synthesized Maestro ResearchBundle, "
            "not an individual lane packet.",
        )
    validation = validate_research_artifact(
        artifact,
        repo_path=repo_path,
    )
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    if validation["evidence_status"] != "completed":
        raise MaestroError(
            "RESEARCH_EVIDENCE_INSUFFICIENT",
            "Only a completed ResearchBundle can satisfy an execution gate.",
        )
    expertise, _ = select_expertise(
        goal,
        intent=intent,
        route_hints=route_hints,
        repo_path=repo_path,
    )
    requirement = expertise["research_requirement"]
    if requirement["mode"] == "reuse" or intent == "research":
        raise MaestroError(
            "RESEARCH_EVIDENCE_NOT_APPLICABLE",
            "The routed task has no external research gate to satisfy.",
        )
    expected_binding = expected_research_binding(goal, expertise)
    if artifact["request_binding"] != expected_binding:
        raise MaestroError(
            "RESEARCH_EVIDENCE_BINDING_MISMATCH",
            "The ResearchBundle does not match this goal, research mode, "
            "selected Pack, Guides, and Pack definition digests.",
        )
    digest = validation["artifact_digest"]
    if expected_digest is not None and expected_digest != digest:
        raise MaestroError(
            "RESEARCH_EVIDENCE_DIGEST_MISMATCH",
            "The supplied digest does not match the validated ResearchBundle.",
        )
    return artifact


def _emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
        return
    status = value.get("status") or value.get("evidence_status") or "ok"
    print(f"{value.get('schema_version', 'maestro')}: {status}")
    for key in (
        "repo_root",
        "plan_id",
        "execution_status",
        "selected_lenses",
        "changed_paths",
    ):
        if key in value:
            print(f"{key}: {value[key]}")


def _host_token_summary(args: argparse.Namespace) -> dict[str, int] | None:
    fields = {
        "input": args.input_tokens,
        "output": args.output_tokens,
        "cached": args.cached_tokens,
        "reasoning": args.reasoning_tokens,
        "total": args.total_tokens,
    }
    supplied = {key: value for key, value in fields.items() if value is not None}
    if supplied and "total" not in supplied:
        raise MaestroError(
            "HOST_OBSERVATION_INVALID",
            "Host token telemetry requires --total-tokens.",
        )
    return supplied or None


def _host_model_reroutes(args: argparse.Namespace) -> list[dict[str, str]]:
    reroutes: list[dict[str, str]] = []
    for raw in args.reroute_event:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MaestroError(
                "HOST_OBSERVATION_INVALID",
                "Each --reroute-event must be one JSON object.",
            ) from exc
        if not isinstance(value, dict):
            raise MaestroError(
                "HOST_OBSERVATION_INVALID",
                "Each --reroute-event must be one JSON object.",
            )
        reroutes.append(value)
    return reroutes


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="maestro")
    root.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Preview or apply a safe project initialization plan")
    init.add_argument("--repo", default=".")
    init.add_argument("--apply-plan")
    init.add_argument("--json", action="store_true")

    upgrade = commands.add_parser(
        "upgrade",
        help="Preview or apply the same safe plan against the installed framework",
    )
    upgrade.add_argument("--repo", default=".")
    upgrade.add_argument("--apply-plan")
    upgrade.add_argument("--json", action="store_true")

    status = commands.add_parser("status", help="Summarize project harness state")
    status.add_argument("--repo", default=".")
    status.add_argument("--json", action="store_true")

    doctor = commands.add_parser("doctor", help="Run read-only harness checks")
    doctor.add_argument("--repo", default=".")
    doctor.add_argument(
        "--host",
        choices=["codex"],
        help="Also inspect the selected agent host's local CLI and Skill wiring",
    )
    doctor.add_argument("--strict", action="store_true")
    doctor.add_argument("--json", action="store_true")

    docs = commands.add_parser("docs", help="Select relevant active documentation")
    docs.add_argument("--repo", default=".")
    docs.add_argument("--task", default="")
    docs.add_argument("--lens", action="append", default=[])
    docs.add_argument(
        "--path",
        action="append",
        default=[],
        help="Repository-relative planned or changed path; repeat as needed",
    )
    docs.add_argument("--json", action="store_true")

    convention = commands.add_parser(
        "convention",
        help="Preview or apply project Convention authoring operations",
    )
    convention_commands = convention.add_subparsers(
        dest="convention_command",
        required=True,
    )
    draft = convention_commands.add_parser(
        "draft",
        help="Create a reviewed draft plan; never activate a Convention",
    )
    draft.add_argument("--repo", default=".")
    draft.add_argument("--topic")
    draft.add_argument("--summary")
    draft.add_argument("--scope", action="append", default=[])
    draft.add_argument("--owner")
    draft.add_argument("--rule")
    draft.add_argument("--applies-when", action="append", default=[])
    draft.add_argument("--does-not-apply", action="append", default=[])
    draft.add_argument("--evidence", action="append", default=[])
    draft.add_argument("--verification", action="append", default=[])
    draft.add_argument("--exception", action="append", default=[])
    draft.add_argument("--apply-plan")
    draft.add_argument("--json", action="store_true")
    convention_activate = convention_commands.add_parser(
        "activate",
        help="Preview or apply one evidence-bound draft activation",
    )
    convention_activate.add_argument("--repo", default=".")
    convention_activate.add_argument("--topic")
    convention_activate.add_argument(
        "--basis",
        choices=["owner_decision", "held_out_evaluation"],
    )
    convention_activate.add_argument("--approval-ref")
    convention_activate.add_argument("--verification-artifact")
    convention_activate.add_argument("--decision-summary")
    convention_activate.add_argument("--apply-plan")
    convention_activate.add_argument("--json", action="store_true")
    convention_update = convention_commands.add_parser(
        "update",
        help="Preview or apply one evidence-bound active Convention revision",
    )
    convention_update.add_argument("--repo", default=".")
    convention_update.add_argument("--topic")
    convention_update.add_argument("--summary")
    convention_update.add_argument("--scope", action="append", default=[])
    convention_update.add_argument("--owner")
    convention_update.add_argument("--rule")
    convention_update.add_argument(
        "--applies-when",
        action="append",
        default=[],
    )
    convention_update.add_argument(
        "--does-not-apply",
        action="append",
        default=[],
    )
    convention_update.add_argument("--evidence", action="append", default=[])
    convention_update.add_argument(
        "--verification",
        action="append",
        default=[],
    )
    convention_update.add_argument(
        "--exception",
        action="append",
        default=[],
    )
    convention_update.add_argument(
        "--basis",
        choices=["owner_decision", "held_out_evaluation"],
    )
    convention_update.add_argument("--approval-ref")
    convention_update.add_argument("--verification-artifact")
    convention_update.add_argument("--decision-summary")
    convention_update.add_argument(
        "--allow-scope-expansion",
        action="store_true",
    )
    convention_update.add_argument("--apply-plan")
    convention_update.add_argument("--json", action="store_true")

    expertise = commands.add_parser(
        "expertise",
        help="Inspect or explicitly manage project-local Expertise",
    )
    expertise_commands = expertise.add_subparsers(
        dest="expertise_command",
        required=True,
    )
    expertise_list = expertise_commands.add_parser(
        "list",
        help="List bundled, active project, and retained candidate Expertise",
    )
    expertise_list.add_argument("--repo", default=".")
    expertise_list.add_argument("--json", action="store_true")
    expertise_validate = expertise_commands.add_parser(
        "validate-candidate",
        help="Validate one complete candidate bundle without writing files",
    )
    expertise_validate.add_argument("--repo", default=".")
    expertise_validate.add_argument("--candidate", required=True)
    expertise_validate.add_argument("--json", action="store_true")
    expertise_activate = expertise_commands.add_parser(
        "activate",
        help="Preview or apply candidate publication as a tracked project pilot",
    )
    expertise_activate.add_argument("--repo", default=".")
    expertise_activate.add_argument("--candidate")
    expertise_activate.add_argument("--approval-ref")
    expertise_activate.add_argument("--apply-plan")
    expertise_activate.add_argument("--json", action="store_true")
    expertise_update = expertise_commands.add_parser(
        "update",
        help="Preview or apply one reviewed project pilot version increment",
    )
    expertise_update.add_argument("--repo", default=".")
    expertise_update.add_argument("--candidate")
    expertise_update.add_argument("--approval-ref")
    expertise_update.add_argument("--apply-plan")
    expertise_update.add_argument("--json", action="store_true")
    expertise_deactivate = expertise_commands.add_parser(
        "deactivate",
        help="Preview or remove a project Pack from the active allowlist",
    )
    expertise_deactivate.add_argument("--repo", default=".")
    expertise_deactivate.add_argument("--pack")
    expertise_deactivate.add_argument("--apply-plan")
    expertise_deactivate.add_argument("--json", action="store_true")
    expertise_reject = expertise_commands.add_parser(
        "reject-candidate",
        help="Preview or reversibly stop one retained candidate from routing",
    )
    expertise_reject.add_argument("--repo", default=".")
    expertise_reject.add_argument("--candidate")
    expertise_reject.add_argument("--reason")
    expertise_reject.add_argument("--apply-plan")
    expertise_reject.add_argument("--json", action="store_true")
    expertise_archive = expertise_commands.add_parser(
        "archive-candidate",
        help="Preview or archive one retained candidate without rejecting it",
    )
    expertise_archive.add_argument("--repo", default=".")
    expertise_archive.add_argument("--candidate")
    expertise_archive.add_argument("--reason")
    expertise_archive.add_argument("--apply-plan")
    expertise_archive.add_argument("--json", action="store_true")
    expertise_restore = expertise_commands.add_parser(
        "restore-candidate",
        help="Preview or restore one archived or rejected candidate",
    )
    expertise_restore.add_argument("--repo", default=".")
    expertise_restore.add_argument("--candidate")
    expertise_restore.add_argument("--apply-plan")
    expertise_restore.add_argument("--json", action="store_true")
    expertise_delete = expertise_commands.add_parser(
        "delete-candidate",
        help="Preview or permanently remove one archived candidate",
    )
    expertise_delete.add_argument("--repo", default=".")
    expertise_delete.add_argument("--candidate")
    expertise_delete.add_argument("--confirm")
    expertise_delete.add_argument(
        "--replacement-pack",
        action="append",
        default=[],
    )
    expertise_delete.add_argument("--apply-plan")
    expertise_delete.add_argument("--json", action="store_true")
    expertise_change_set = expertise_commands.add_parser(
        "change-set",
        help="Preview or apply one atomic multi-Pack Expertise change",
    )
    expertise_change_set.add_argument("--repo", default=".")
    expertise_change_set.add_argument("--id")
    expertise_change_set.add_argument(
        "--action",
        choices=["project-approve", "archive", "restore", "delete"],
    )
    expertise_change_set.add_argument("--approval-ref")
    expertise_change_set.add_argument("--reason")
    expertise_change_set.add_argument("--confirm")
    expertise_change_set.add_argument(
        "--replacement-pack",
        action="append",
        default=[],
    )
    expertise_change_set.add_argument("--apply-plan")
    expertise_change_set.add_argument("--json", action="store_true")
    expertise_promotion_decision = expertise_commands.add_parser(
        "promotion-decision",
        help="Decline or reconsider the global promotion of one candidate",
    )
    expertise_promotion_decision.add_argument("--repo", default=".")
    expertise_promotion_decision.add_argument("--candidate")
    expertise_promotion_decision.add_argument(
        "--decision",
        choices=["decline", "reconsider"],
    )
    expertise_promotion_decision.add_argument("--reason")
    expertise_promotion_decision.add_argument("--apply-plan")
    expertise_promotion_decision.add_argument("--json", action="store_true")
    expertise_export = expertise_commands.add_parser(
        "export",
        help="Preview or write one validated project-local promotion bundle",
    )
    expertise_export.add_argument("--repo", default=".")
    expertise_export.add_argument("--candidate")
    expertise_export.add_argument("--apply-plan")
    expertise_export.add_argument("--json", action="store_true")
    expertise_promote_global = expertise_commands.add_parser(
        "promote-global",
        help="Preview or apply a contribution to Harness global source",
    )
    expertise_promote_global.add_argument("--repo", default=".")
    expertise_promote_global.add_argument("--candidate")
    expertise_promote_global.add_argument("--pack")
    expertise_promote_global.add_argument("--approval-ref")
    expertise_promote_global.add_argument("--apply-plan")
    expertise_promote_global.add_argument("--json", action="store_true")
    expertise_validate_contribution = expertise_commands.add_parser(
        "validate-contribution",
        help="Validate one exported Expertise contribution without importing it",
    )
    expertise_validate_contribution.add_argument("--bundle", required=True)
    expertise_validate_contribution.add_argument("--json", action="store_true")
    expertise_reconcile = expertise_commands.add_parser(
        "reconcile",
        help=(
            "Preview or archive inactive and globally superseded project "
            "Expertise outside Host discovery"
        ),
    )
    expertise_reconcile.add_argument("--repo", default=".")
    expertise_reconcile.add_argument(
        "--source-root",
        help=(
            "Harness source checkout providing the bundled global Pack; "
            "defaults to --repo"
        ),
    )
    expertise_reconcile.add_argument("--apply-plan")
    expertise_reconcile.add_argument("--json", action="store_true")

    component = commands.add_parser(
        "component",
        help="Validate isolated non-Expertise component candidates",
    )
    component_commands = component.add_subparsers(
        dest="component_command",
        required=True,
    )
    component_validate = component_commands.add_parser(
        "validate-candidate",
        help="Validate one project-local component candidate without promotion",
    )
    component_validate.add_argument("--repo", default=".")
    component_validate.add_argument("--candidate", required=True)
    component_validate.add_argument("--json", action="store_true")

    route = commands.add_parser("route", help="Create a deterministic Lens and Executor plan")
    route.add_argument(
        "--repo",
        default=".",
        help="Repository whose explicitly enabled project Expertise may be routed.",
    )
    route.add_argument("--goal", required=True)
    route.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="medium")
    route.add_argument(
        "--intent",
        choices=["auto", "implementation", "review", "research"],
        default="auto",
    )
    route.add_argument("--department", default="software-development")
    route.add_argument("--host", default="codex")
    route.add_argument("--lens", action="append", default=[])
    route.add_argument(
        "--conflict-evidence",
        help="New bounded evidence required for a material-conflict reroute; never emitted",
    )
    route.add_argument(
        "--route-version",
        choices=["v1", "v2"],
        default="v1",
        help="Keep v1 compatibility by default; v2 emits a validated Assignment DAG",
    )
    route.add_argument(
        "--research-evidence",
        help=(
            "Path to a validated synthesized ResearchBundle used to satisfy "
            "an open route v2 expertise gate"
        ),
    )
    route.add_argument(
        "--research-evidence-digest",
        help=(
            "Optional expected SHA-256 digest; valid only together with "
            "--research-evidence"
        ),
    )
    route.add_argument(
        "--work-kind",
        action="append",
        default=[],
        choices=sorted(WORK_KIND_TO_PACK_ID),
        help=(
            "Host-confirmed work kind; repeat at most twice. The first kind is "
            "primary when a non-high-risk route warns and continues."
        ),
    )
    route.add_argument(
        "--affected-path",
        action="append",
        default=[],
        help=(
            "Repository-relative path recorded for audit only; a project "
            "Adapter must translate paths into --work-kind when relevant."
        ),
    )
    route.add_argument(
        "--explicit-pack",
        help="One eligible Expertise Pack explicitly selected by the user.",
    )
    route.add_argument(
        "--prior-route-plan",
        help=(
            "Exact initial route v2 plan when producing the stage's one "
            "corrected route. Attach only the final plan to an observation."
        ),
    )
    route.add_argument("--json", action="store_true")

    validate_plan = commands.add_parser(
        "validate-plan",
        help="Validate a route v2 Assignment DAG before host execution",
    )
    validate_plan.add_argument("--plan", required=True)
    validate_plan.add_argument(
        "--repo",
        default=".",
        help="Repository used to re-resolve project Expertise.",
    )
    validate_plan.add_argument(
        "--research-evidence",
        help="Exact completed ResearchBundle required to revalidate a satisfied gate.",
    )
    validate_plan.add_argument("--json", action="store_true")

    assignment = commands.add_parser(
        "assignment",
        help="Project a bounded input contract for one route v2 Assignment",
    )
    assignment_commands = assignment.add_subparsers(
        dest="assignment_command",
        required=True,
    )
    assignment_project = assignment_commands.add_parser(
        "project",
        help="Validate a baseline and emit only the Assignment input allowlist",
    )
    assignment_project.add_argument("--repo", default=".")
    assignment_project.add_argument("--plan", required=True)
    assignment_project.add_argument("--assignment", required=True)
    assignment_project.add_argument("--baseline", required=True)
    assignment_project.add_argument(
        "--document",
        action="append",
        default=[],
        help=(
            "Additional repository document; cannot replace the automatic "
            "maestro docs selection"
        ),
    )
    assignment_project.add_argument(
        "--dependency-packet",
        action="append",
        default=[],
    )
    assignment_project.add_argument(
        "--dependency-projection",
        action="append",
        default=[],
        help=(
            "Exact source projection paired by assignment_id with each "
            "dependency Packet"
        ),
    )
    assignment_project.add_argument(
        "--research-evidence",
        help=(
            "Validated completed ResearchBundle required by a satisfied "
            "expertise research gate"
        ),
    )
    assignment_project.add_argument("--json", action="store_true")

    validate_packet = commands.add_parser(
        "validate-packet",
        help="Fail closed on an invalid Assignment result packet",
    )
    validate_packet.add_argument("--repo", default=".")
    validate_packet.add_argument("--plan", required=True)
    validate_packet.add_argument("--assignment", required=True)
    validate_packet.add_argument("--packet", required=True)
    validate_packet.add_argument(
        "--projection",
        help="Optional Assignment projection used to enforce evidence scope",
    )
    validate_packet.add_argument(
        "--research-evidence",
        help="Exact completed ResearchBundle bound into the Assignment projection.",
    )
    validate_packet.add_argument("--json", action="store_true")

    validate_research = commands.add_parser(
        "validate-research",
        help="Validate one bounded ResearchPacket or synthesized ResearchBundle",
    )
    validate_research.add_argument(
        "--repo",
        default=".",
        help="Repository used to resolve checked local evidence artifacts",
    )
    validate_research.add_argument("--artifact", required=True)
    validate_research.add_argument("--json", action="store_true")

    decide = commands.add_parser(
        "decide",
        help="Create a read-only specialist decision plan before implementation",
    )
    decide.add_argument("--repo", default=".")
    decide.add_argument("--goal", required=True)
    decide.add_argument(
        "--risk",
        choices=["low", "medium", "high", "critical"],
        default="medium",
    )
    decide.add_argument(
        "--intent",
        choices=["implementation", "review", "research"],
        default="implementation",
    )
    decide.add_argument("--host", default="codex")
    decide.add_argument(
        "--research-evidence",
        help=(
            "Path to a validated synthesized ResearchBundle satisfying a "
            "selected decision research gate"
        ),
    )
    decide.add_argument(
        "--research-evidence-digest",
        help=(
            "Optional expected SHA-256 digest; valid only together with "
            "--research-evidence"
        ),
    )
    decide.add_argument("--json", action="store_true")

    validate_decision = commands.add_parser(
        "validate-decision",
        help="Validate a decision plan or one specialist packet",
    )
    validate_decision.add_argument("--plan", required=True)
    validate_decision.add_argument("--packet")
    validate_decision.add_argument("--json", action="store_true")

    enact = commands.add_parser(
        "enact",
        help="Authorize a validated decision bundle as an execution plan",
    )
    enact.add_argument("--repo", default=".")
    enact.add_argument("--plan", required=True)
    enact.add_argument("--bundle", required=True)
    enact.add_argument(
        "--packet",
        action="append",
        default=[],
        required=True,
        help="Validated specialist packet; repeat for every specialist assignment",
    )
    enact.add_argument(
        "--authorization-source",
        choices=["explicit_user", "prior_explicit_request"],
        required=True,
    )
    enact.add_argument("--host")
    enact.add_argument(
        "--research-evidence",
        help="Exact completed ResearchBundle when the decision gate is satisfied.",
    )
    enact.add_argument("--json", action="store_true")

    adapt = commands.add_parser("adapt", help="Inspect project adapter candidates without writing")
    adapt.add_argument("--repo", default=".")
    adapt.add_argument("--json", action="store_true")

    observe = commands.add_parser(
        "observe",
        help="Capture bounded task metadata without storing prompts or messages",
    )
    observe_commands = observe.add_subparsers(
        dest="observe_command",
        required=True,
    )
    observe_start = observe_commands.add_parser(
        "start",
        help="Start one project-local run observation",
    )
    observe_start.add_argument("--repo", default=".")
    observe_start.add_argument("--run-id", required=True)
    observe_start.add_argument("--task-label", required=True)
    observe_start.add_argument(
        "--plan",
        help="Optional validated route v2 plan whose compact assignments are recorded",
    )
    observe_start.add_argument(
        "--fallback-reason",
        choices=[
            "interactive_required",
            "network_required",
            "app_connector_required",
            "capability_unavailable",
        ],
        help=(
            "Why the current Host must execute this run instead of the "
            "Maestro-owned App Server"
        ),
    )
    observe_start.add_argument(
        "--fallback-evidence",
        help=(
            "One bounded factual line supporting --fallback-reason; use this "
            "path when public Desktop request model metadata is unavailable"
        ),
    )
    observe_start.add_argument("--json", action="store_true")
    observe_desktop = observe_commands.add_parser(
        "desktop",
        help=(
            "Start a run and attach allowlisted Codex Desktop request "
            "settings; applied model and tokens remain unmeasured"
        ),
    )
    observe_desktop.add_argument("--repo", default=".")
    observe_desktop.add_argument("--run-id", required=True)
    observe_desktop.add_argument("--task-label", required=True)
    observe_desktop.add_argument("--thread-id", required=True)
    observe_desktop.add_argument("--turn-id", required=True)
    observe_desktop.add_argument("--requested-model", required=True)
    observe_desktop.add_argument("--requested-reasoning-effort")
    observe_desktop.add_argument(
        "--plan",
        help="Optional validated route v2 plan whose compact assignments are recorded",
    )
    observe_desktop.add_argument("--json", action="store_true")
    observe_fallback = observe_commands.add_parser(
        "fallback",
        help=(
            "Record why an observed Desktop run cannot use the "
            "Maestro-owned Codex App Server"
        ),
    )
    observe_fallback.add_argument("--repo", default=".")
    observe_fallback.add_argument("--observation", required=True)
    observe_fallback.add_argument("--run-id", required=True)
    observe_fallback.add_argument(
        "--reason",
        choices=[
            "interactive_required",
            "network_required",
            "app_connector_required",
            "capability_unavailable",
        ],
        required=True,
    )
    observe_fallback.add_argument(
        "--evidence",
        required=True,
        help="One bounded factual line proving why current-Host execution is required.",
    )
    observe_fallback.add_argument("--json", action="store_true")
    observe_plan = observe_commands.add_parser(
        "plan",
        help="Attach one validated route v2 plan to an already observed request",
    )
    observe_plan.add_argument("--repo", default=".")
    observe_plan.add_argument("--observation", required=True)
    observe_plan.add_argument("--run-id", required=True)
    observe_plan.add_argument("--plan", required=True)
    observe_plan.add_argument("--json", action="store_true")
    observe_stage = observe_commands.add_parser(
        "stage",
        help="Record one immutable terminal Assignment result",
    )
    observe_stage.add_argument("--repo", default=".")
    observe_stage.add_argument("--observation", required=True)
    observe_stage.add_argument("--run-id", required=True)
    observe_stage.add_argument("--assignment", required=True)
    observe_stage.add_argument(
        "--status",
        choices=[
            "completed",
            "failed",
            "blocked",
            "skipped",
            "interrupted",
        ],
        required=True,
    )
    observe_stage.add_argument(
        "--evidence-source",
        choices=[
            "current_host",
            "deterministic_command",
        ],
        required=True,
        help=(
            "Current Desktop/CLI assertion source. Codex App Server evidence "
            "is written only by maestro host codex."
        ),
    )
    observe_stage.add_argument(
        "--evidence",
        action="append",
        default=[],
        required=True,
        help="Bounded evidence reference; repeat up to three times",
    )
    observe_stage.add_argument("--duration-ms", type=float)
    observe_stage.add_argument("--json", action="store_true")
    observe_work_start = observe_commands.add_parser(
        "work-start",
        help="Record one bounded orchestrator or delegated work attempt",
    )
    observe_work_start.add_argument("--repo", default=".")
    observe_work_start.add_argument("--observation", required=True)
    observe_work_start.add_argument("--run-id", required=True)
    observe_work_start.add_argument("--work-id", required=True)
    observe_work_start.add_argument("--parent-work")
    observe_work_start.add_argument("--assignment")
    observe_work_start.add_argument(
        "--kind",
        choices=[
            "orchestration",
            "delegation",
            "research",
            "review",
            "implementation",
            "synthesis",
            "verification",
        ],
        required=True,
    )
    observe_work_start.add_argument("--role", required=True)
    observe_work_start.add_argument("--executor", required=True)
    observe_work_start.add_argument("--summary", required=True)
    work_access = observe_work_start.add_mutually_exclusive_group(
        required=True,
    )
    work_access.add_argument(
        "--read-only",
        dest="work_read_only",
        action="store_true",
    )
    work_access.add_argument(
        "--mutation-owner",
        dest="work_read_only",
        action="store_false",
    )
    observe_work_start.add_argument("--attempt", type=int, default=1)
    observe_work_start.add_argument("--followup-of")
    observe_work_start.add_argument(
        "--depends-on",
        action="append",
        default=[],
    )
    observe_work_start.add_argument(
        "--joins",
        action="append",
        default=[],
    )
    observe_work_start.add_argument("--requested-model")
    observe_work_start.add_argument("--requested-reasoning-effort")
    observe_work_start.add_argument(
        "--lens",
        action="append",
        default=[],
    )
    observe_work_start.add_argument(
        "--expertise-pack",
        action="append",
        default=[],
    )
    observe_work_start.add_argument(
        "--decision-guide",
        action="append",
        default=[],
    )
    observe_work_start.add_argument(
        "--expertise-evidence",
        choices=["unavailable", "selection_only"],
        default="unavailable",
    )
    observe_work_start.add_argument("--json", action="store_true")
    observe_work_finish = observe_commands.add_parser(
        "work-finish",
        help="Complete one observed work attempt with a bounded result",
    )
    observe_work_finish.add_argument("--repo", default=".")
    observe_work_finish.add_argument("--observation", required=True)
    observe_work_finish.add_argument("--run-id", required=True)
    observe_work_finish.add_argument("--work-id", required=True)
    observe_work_finish.add_argument(
        "--status",
        choices=[
            "completed",
            "failed",
            "blocked",
            "interrupted",
        ],
        required=True,
    )
    observe_work_finish.add_argument("--summary", required=True)
    observe_work_finish.add_argument(
        "--evidence",
        action="append",
        default=[],
    )
    observe_work_finish.add_argument(
        "--expertise-evidence",
        choices=[
            "unavailable",
            "selection_only",
            "host_loaded",
            "application_observed",
        ],
    )
    observe_work_finish.add_argument("--json", action="store_true")
    observe_host = observe_commands.add_parser(
        "host",
        help="Attach explicit Host-reported model and token telemetry",
    )
    observe_host.add_argument("--repo", default=".")
    observe_host.add_argument("--observation", required=True)
    observe_host.add_argument("--run-id", required=True)
    observe_host.add_argument("--source", required=True)
    observe_host.add_argument(
        "--quality",
        choices=["host_reported", "host_delta"],
        required=True,
    )
    observe_host.add_argument("--correlation-id", required=True)
    observe_host.add_argument("--requested-model")
    observe_host.add_argument(
        "--requested-reasoning-effort",
        help=(
            "Host-reported requested/configured reasoning effort. This is "
            "not a claim about reasoning tokens actually consumed."
        ),
    )
    applied_model = observe_host.add_mutually_exclusive_group()
    applied_model.add_argument("--applied-model")
    applied_model.add_argument("--actual-model", help=argparse.SUPPRESS)
    observe_host.add_argument(
        "--model-event-evidence",
        choices=["unavailable", "complete"],
        default="unavailable",
        help=(
            "Use complete only when the Host observed turn completion and the "
            "full model/reroute event stream."
        ),
    )
    observe_host.add_argument(
        "--reroute-event",
        action="append",
        default=[],
        help=(
            "Bounded Host event JSON with from_model, to_model, and reason; "
            "repeat in observed order."
        ),
    )
    observe_host.add_argument("--input-tokens", type=int)
    observe_host.add_argument("--output-tokens", type=int)
    observe_host.add_argument("--cached-tokens", type=int)
    observe_host.add_argument("--reasoning-tokens", type=int)
    observe_host.add_argument("--total-tokens", type=int)
    observe_host.add_argument("--json", action="store_true")
    observe_import_codex = observe_commands.add_parser(
        "import-codex",
        help=(
            "Import one fully captured public Codex App Server JSON-RPC "
            "turn stream"
        ),
    )
    observe_import_codex.add_argument("--repo", default=".")
    observe_import_codex.add_argument("--observation", required=True)
    observe_import_codex.add_argument("--run-id", required=True)
    observe_import_codex.add_argument("--trace", required=True)
    observe_import_codex.add_argument(
        "--turn-id",
        help="Required only when the trace contains more than one turn",
    )
    observe_import_codex.add_argument("--json", action="store_true")

    host = commands.add_parser(
        "host",
        help="Run a bounded task through a Host adapter with verified telemetry",
    )
    host_commands = host.add_subparsers(
        dest="host_command",
        required=True,
    )
    host_sync = host_commands.add_parser(
        "sync",
        help="Preview or create only missing bundled Host Skill links",
    )
    host_sync.add_argument("--host", default="codex", choices=["codex"])
    host_sync.add_argument("--source-root", default=".")
    host_sync.add_argument("--skill-root")
    host_sync.add_argument("--apply-plan")
    host_sync.add_argument("--json", action="store_true")
    host_codex = host_commands.add_parser(
        "codex",
        help=(
            "Run one Maestro-owned Codex App Server turn and record its "
            "model, reroute, token, effort, and completion events"
        ),
    )
    host_codex.add_argument("--repo", default=".")
    host_codex.add_argument("--run-id", required=True)
    host_codex.add_argument("--task-label", required=True)
    host_codex.add_argument(
        "--prompt-file",
        help=(
            "Standalone-only regular UTF-8 request file; Assignment execution "
            "derives its prompt from the exact validated projection"
        ),
    )
    host_codex.add_argument(
        "--plan",
        help="Optional validated route v2 plan recorded in the observation",
    )
    host_codex.add_argument(
        "--assignment",
        help=(
            "Assignment in --plan; derives sandbox, model, and reasoning "
            "effort and rejects conflicting overrides"
        ),
    )
    host_codex.add_argument(
        "--projection",
        help=(
            "Exact Assignment projection previously emitted by "
            "`maestro assignment project`; required with --assignment"
        ),
    )
    host_codex.add_argument(
        "--baseline",
        help="Authoritative Engineering Baseline used to reconstruct the projection",
    )
    host_codex.add_argument(
        "--document",
        action="append",
        default=[],
        help="Additional repository document used when projecting the Assignment",
    )
    host_codex.add_argument(
        "--dependency-packet",
        action="append",
        default=[],
        help="Validated direct-dependency Packet; repeat in dependency order",
    )
    host_codex.add_argument(
        "--dependency-projection",
        action="append",
        default=[],
        help="Exact projection paired with each direct-dependency Packet",
    )
    host_codex.add_argument(
        "--research-evidence",
        help="Exact completed ResearchBundle bound to a satisfied research gate",
    )
    host_codex.add_argument(
        "--observation",
        help=(
            "Existing parent observation for this plan. Assignment telemetry "
            "is appended to that run instead of creating a separate run."
        ),
    )
    host_codex.add_argument(
        "--sandbox",
        choices=["read-only", "workspace-write"],
        help=(
            "Required without --assignment; workspace-write is restricted "
            "to the repository and network remains disabled"
        ),
    )
    host_codex.add_argument("--model")
    host_codex.add_argument(
        "--reasoning-effort",
        help=(
            "Requested/configured effort such as low, medium, high, or xhigh; "
            "actual reasoning token use is measured separately"
        ),
    )
    host_codex.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "Whole-turn timeout in seconds; default "
            f"{DEFAULT_TIMEOUT_SECONDS:g}"
        ),
    )
    host_codex.add_argument("--json", action="store_true")

    record = commands.add_parser(
        "record",
        help="Append one validated compact RunReceipt at task completion",
    )
    record.add_argument("--repo", default=".")
    record.add_argument("--receipt", required=True)
    record.add_argument(
        "--observation",
        help=(
            "Observation ID returned by observe start; when omitted, record "
            "automatically attaches the matching run observation from this "
            "project checkout"
        ),
    )
    record.add_argument("--json", action="store_true")
    finalize = commands.add_parser(
        "finalize",
        help=(
            "Derive one final RunReceipt from the observed plan and terminal "
            "Assignment results"
        ),
    )
    finalize.add_argument("--repo", default=".")
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--observation")
    finalize.add_argument(
        "--outcome",
        choices=["completed", "failed", "corrected", "blocked", "no_change"],
        required=True,
    )
    finalize.add_argument(
        "--evidence",
        action="append",
        default=[],
        required=True,
    )
    finalize.add_argument(
        "--verifier-result",
        choices=["passed", "failed", "not_run"],
        required=True,
    )
    finalize.add_argument("--command-artifact-ref")
    finalize.add_argument("--correction-count", type=int, default=0)
    finalize.add_argument(
        "--correction-summary",
        action="append",
        default=[],
    )
    finalize.add_argument("--human-fix-required", action="store_true")
    finalize.add_argument("--decision-changed", action="store_true")
    finalize.add_argument("--json", action="store_true")

    snapshot = commands.add_parser(
        "snapshot",
        help="Build one read-only operations snapshot for people or tools",
    )
    snapshot.add_argument("--repo", default=".")
    snapshot.add_argument("--window", type=int, default=20)
    snapshot.add_argument("--json", action="store_true")

    dashboard = commands.add_parser(
        "dashboard",
        help="Serve the read-only project operations viewer on localhost",
    )
    dashboard.add_argument("--repo", default=".")
    dashboard.add_argument(
        "--project",
        action="append",
        default=[],
        help=(
            "Additional initialized Maestro project to include in the local "
            "project switcher; repeat as needed"
        ),
    )
    dashboard.add_argument("--window", type=int, default=20)
    dashboard.add_argument(
        "--port",
        type=int,
        default=0,
        help="Local port; zero selects a free ephemeral port",
    )
    dashboard.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the viewer in the default browser",
    )
    dashboard.add_argument(
        "--no-saved-projects",
        action="store_true",
        help=(
            "Start an isolated dashboard session without restoring projects "
            "remembered by earlier dashboard launches"
        ),
    )

    verification = commands.add_parser(
        "verification",
        help="Inspect or approve detected verification commands without executing them",
    )
    verification_commands = verification.add_subparsers(
        dest="verification_command",
        required=True,
    )
    verification_list = verification_commands.add_parser(
        "list",
        help="List detected verification candidates and approval state",
    )
    verification_list.add_argument("--repo", default=".")
    verification_list.add_argument("--json", action="store_true")
    verification_approve = verification_commands.add_parser(
        "approve",
        help="Preview or apply one exact candidate approval",
    )
    verification_approve.add_argument("--repo", default=".")
    verification_approve.add_argument("--candidate")
    verification_approve.add_argument("--apply-plan")
    verification_approve.add_argument("--json", action="store_true")

    govern = commands.add_parser("govern", help="Read-only harness governance")
    govern_commands = govern.add_subparsers(dest="govern_command", required=True)
    report = govern_commands.add_parser("report", help="Report repeated evidence without promotion")
    report.add_argument("--repo", default=".")
    report.add_argument("--window", type=int, default=20)
    report.add_argument("--threshold", type=int, default=3)
    report.add_argument("--json", action="store_true")
    classify = govern_commands.add_parser(
        "classify",
        help="Classify structured evidence into the narrowest durable surface",
    )
    classify.add_argument("--input", required=True)
    classify.add_argument("--json", action="store_true")
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            result = (
                apply_plan(args.apply_plan, args.repo)
                if args.apply_plan
                else build_init_plan(args.repo)
            )
            _emit(result, args.json)
            return 0
        if args.command == "upgrade":
            result = (
                apply_plan(
                    args.apply_plan,
                    args.repo,
                    expected_command="upgrade",
                )
                if args.apply_plan
                else build_upgrade_plan(args.repo)
            )
            _emit(result, args.json)
            return 0
        if args.command == "status":
            result = status_report(args.repo)
            _emit(result, args.json)
            return 0
        if args.command == "doctor":
            result = doctor_report(args.repo, host_id=args.host)
            _emit(result, args.json)
            if result["status"] == "FAIL":
                return 2
            if args.strict and result["status"] == "WARN":
                return 2
            return 0
        if args.command == "docs":
            result = select_documents(
                args.repo,
                args.task,
                args.lens,
                args.path,
            )
            _emit(result, args.json)
            return 0
        if args.command == "convention" and args.convention_command == "draft":
            result = (
                apply_convention_draft_plan(args.apply_plan, args.repo)
                if args.apply_plan
                else build_convention_draft_plan(
                    args.repo,
                    topic=args.topic,
                    summary=args.summary,
                    scopes=args.scope,
                    owner=args.owner,
                    rule=args.rule,
                    applies_when=args.applies_when,
                    does_not_apply=args.does_not_apply,
                    evidence=args.evidence,
                    verification=args.verification,
                    exceptions=args.exception,
                )
            )
            _emit(result, args.json)
            return 0
        if (
            args.command == "convention"
            and args.convention_command == "activate"
        ):
            result = (
                apply_convention_lifecycle_plan(
                    args.apply_plan,
                    args.repo,
                )
                if args.apply_plan
                else build_convention_activation_plan(
                    args.repo,
                    topic=args.topic,
                    basis=args.basis,
                    approval_ref=args.approval_ref,
                    verification_artifact=args.verification_artifact,
                    decision_summary=args.decision_summary,
                )
            )
            _emit(result, args.json)
            return 0
        if (
            args.command == "convention"
            and args.convention_command == "update"
        ):
            result = (
                apply_convention_lifecycle_plan(
                    args.apply_plan,
                    args.repo,
                )
                if args.apply_plan
                else build_convention_update_plan(
                    args.repo,
                    topic=args.topic,
                    summary=args.summary,
                    scopes=args.scope,
                    owner=args.owner,
                    rule=args.rule,
                    applies_when=args.applies_when,
                    does_not_apply=args.does_not_apply,
                    evidence=args.evidence,
                    verification=args.verification,
                    exceptions=args.exception,
                    basis=args.basis,
                    approval_ref=args.approval_ref,
                    verification_artifact=args.verification_artifact,
                    decision_summary=args.decision_summary,
                    allow_scope_expansion=args.allow_scope_expansion,
                )
            )
            _emit(result, args.json)
            return 0
        if args.command == "expertise" and args.expertise_command == "list":
            result = expertise_inventory(args.repo)
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "validate-candidate"
        ):
            result = validate_expertise_candidate(
                args.repo,
                args.candidate,
            )
            _emit(result, args.json)
            return 0 if result["status"] == "PASS" else 2
        if args.command == "expertise" and args.expertise_command == "activate":
            if args.apply_plan:
                result = apply_expertise_activation_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate or not args.approval_ref:
                    raise MaestroError(
                        "EXPERTISE_ACTIVATION_ARGUMENTS_REQUIRED",
                        "Preview requires --candidate and --approval-ref.",
                    )
                result = build_expertise_activation_plan(
                    args.repo,
                    candidate_id=args.candidate,
                    approval_ref=args.approval_ref,
                )
            _emit(result, args.json)
            return 0
        if args.command == "expertise" and args.expertise_command == "update":
            if args.apply_plan:
                result = apply_expertise_update_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate or not args.approval_ref:
                    raise MaestroError(
                        "EXPERTISE_UPDATE_ARGUMENTS_REQUIRED",
                        "Preview requires --candidate and --approval-ref.",
                    )
                result = build_expertise_update_plan(
                    args.repo,
                    candidate_id=args.candidate,
                    approval_ref=args.approval_ref,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "deactivate"
        ):
            if args.apply_plan:
                result = apply_expertise_deactivation_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.pack:
                    raise MaestroError(
                        "EXPERTISE_DEACTIVATION_ARGUMENTS_REQUIRED",
                        "Preview requires --pack.",
                    )
                result = build_expertise_deactivation_plan(
                    args.repo,
                    expertise_pack_id=args.pack,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "reject-candidate"
        ):
            if args.apply_plan:
                result = apply_expertise_rejection_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate or not args.reason:
                    raise MaestroError(
                        "EXPERTISE_CANDIDATE_REJECTION_ARGUMENTS_REQUIRED",
                        "Preview requires --candidate and --reason.",
                    )
                result = build_expertise_rejection_plan(
                    args.repo,
                    candidate_id=args.candidate,
                    reason=args.reason,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "archive-candidate"
        ):
            if args.apply_plan:
                result = apply_expertise_archive_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate or not args.reason:
                    raise MaestroError(
                        "EXPERTISE_CANDIDATE_ARCHIVE_ARGUMENTS_REQUIRED",
                        "Preview requires --candidate and --reason.",
                    )
                result = build_expertise_archive_plan(
                    args.repo,
                    candidate_id=args.candidate,
                    reason=args.reason,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "restore-candidate"
        ):
            if args.apply_plan:
                result = apply_expertise_restore_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate:
                    raise MaestroError(
                        "EXPERTISE_CANDIDATE_RESTORE_ARGUMENTS_REQUIRED",
                        "Preview requires --candidate.",
                    )
                result = build_expertise_restore_plan(
                    args.repo,
                    candidate_id=args.candidate,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "delete-candidate"
        ):
            if args.apply_plan:
                result = apply_expertise_delete_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate or not args.confirm:
                    raise MaestroError(
                        "EXPERTISE_CANDIDATE_DELETE_ARGUMENTS_REQUIRED",
                        "Preview requires --candidate and --confirm.",
                    )
                result = build_expertise_delete_plan(
                    args.repo,
                    candidate_id=args.candidate,
                    confirmation=args.confirm,
                    replacement_pack_ids=args.replacement_pack,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "change-set"
        ):
            if args.apply_plan:
                result = apply_expertise_change_set_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.id or not args.action:
                    raise MaestroError(
                        "EXPERTISE_CHANGE_SET_ARGUMENTS_REQUIRED",
                        "Preview requires --id and --action.",
                    )
                result = build_expertise_change_set_plan(
                    args.repo,
                    change_set_id=args.id,
                    action=args.action,
                    approval_ref=args.approval_ref,
                    reason=args.reason,
                    confirmation=args.confirm,
                    replacement_pack_ids=args.replacement_pack,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "promotion-decision"
        ):
            if args.apply_plan:
                result = apply_expertise_promotion_decision_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate or not args.decision:
                    raise MaestroError(
                        "EXPERTISE_PROMOTION_DECISION_ARGUMENTS_REQUIRED",
                        "Preview requires --candidate and --decision.",
                    )
                result = build_expertise_promotion_decision_plan(
                    args.repo,
                    candidate_id=args.candidate,
                    decision=args.decision,
                    reason=args.reason,
                )
            _emit(result, args.json)
            return 0
        if args.command == "expertise" and args.expertise_command == "export":
            if args.apply_plan:
                result = apply_expertise_export_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate:
                    raise MaestroError(
                        "EXPERTISE_EXPORT_ARGUMENTS_REQUIRED",
                        "Preview requires --candidate.",
                    )
                result = build_expertise_export_plan(
                    args.repo,
                    candidate_id=args.candidate,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "promote-global"
        ):
            if args.apply_plan:
                result = apply_expertise_global_promotion_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if (
                    (bool(args.candidate) == bool(args.pack))
                    or not args.approval_ref
                ):
                    raise MaestroError(
                        "EXPERTISE_GLOBAL_PROMOTION_ARGUMENTS_REQUIRED",
                        (
                            "Preview requires exactly one of --candidate or "
                            "--pack, plus --approval-ref."
                        ),
                    )
                result = build_expertise_global_promotion_plan(
                    args.repo,
                    candidate_id=args.candidate,
                    expertise_pack_id=args.pack,
                    approval_ref=args.approval_ref,
                )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "reconcile"
        ):
            result = (
                apply_expertise_reconcile_plan(
                    args.apply_plan,
                    args.repo,
                )
                if args.apply_plan
                else build_expertise_reconcile_plan(
                    args.repo,
                    source_root=args.source_root,
                )
            )
            _emit(result, args.json)
            return 0
        if (
            args.command == "expertise"
            and args.expertise_command == "validate-contribution"
        ):
            result = validate_expertise_contribution(args.bundle)
            _emit(result, args.json)
            return 0 if result["status"] == "PASS" else 2
        if (
            args.command == "component"
            and args.component_command == "validate-candidate"
        ):
            result = validate_component_candidate(
                args.repo,
                args.candidate,
            )
            _emit(result, args.json)
            return 0 if result["status"] == "PASS" else 2
        if args.command == "route":
            prior_route_plan = (
                read_json(
                    Path(args.prior_route_plan).expanduser().resolve()
                )
                if args.prior_route_plan
                else None
            )
            if prior_route_plan is not None:
                prior_validation = validate_route_v2(
                    prior_route_plan,
                    repo_path=args.repo,
                )
                if prior_validation["status"] != "PASS":
                    first_issue = prior_validation["issues"][0]
                    raise MaestroError(
                        first_issue["code"],
                        first_issue["message"],
                    )
            has_route_hints = bool(
                args.work_kind
                or args.affected_path
                or args.explicit_pack
                or prior_route_plan is not None
            )
            route_hints = (
                normalize_route_hints(
                    work_kinds=args.work_kind,
                    affected_paths=args.affected_path,
                    explicit_pack_id=args.explicit_pack,
                    route_attempt=2 if prior_route_plan is not None else 1,
                    prior_plan_id=(
                        prior_route_plan.get("plan_id")
                        if prior_route_plan is not None
                        else None
                    ),
                    prior_source_route_digest=(
                        prior_route_plan.get("source_route_digest")
                        if prior_route_plan is not None
                        else None
                    ),
                )
                if has_route_hints
                else None
            )
            if route_hints is not None and args.route_version != "v2":
                raise MaestroError(
                    "ROUTE_VERSION_REQUIRED",
                    "Expertise route hints are supported only by route v2.",
                )
            research_evidence = _research_evidence_digest(
                args.research_evidence,
                args.research_evidence_digest,
                repo_path=args.repo,
                goal=args.goal,
                intent=args.intent,
                route_hints=route_hints,
            )
            if args.route_version == "v2":
                result = route_goal_v2(
                    args.goal,
                    args.risk,
                    args.lens or None,
                    args.department,
                    args.conflict_evidence,
                    args.host,
                    args.intent,
                    research_evidence=research_evidence,
                    repo_path=args.repo,
                    route_hints=route_hints,
                    prior_route_plan=prior_route_plan,
                )
            else:
                if research_evidence is not None:
                    raise MaestroError(
                        "ROUTE_VERSION_REQUIRED",
                        "--research-evidence is supported only by route v2.",
                    )
                result = route_goal(
                    args.goal,
                    args.risk,
                    args.lens or None,
                    args.department,
                    args.conflict_evidence,
                    args.host,
                    args.intent,
                )
            _emit(result, args.json)
            return 0
        if args.command == "validate-plan":
            research_bundle = (
                read_json(
                    Path(args.research_evidence).expanduser().resolve()
                )
                if args.research_evidence
                else None
            )
            result = validate_route_v2(
                read_json(Path(args.plan).expanduser().resolve()),
                repo_path=args.repo,
                research_bundle=research_bundle,
            )
            _emit(result, args.json)
            if result["status"] != "PASS":
                return 2
            return 4 if result["execution_status"] == "RESEARCH_REQUIRED" else 0
        if (
            args.command == "assignment"
            and args.assignment_command == "project"
        ):
            result = project_assignment_input(
                args.repo,
                read_json(Path(args.plan).expanduser().resolve()),
                args.assignment,
                read_json(Path(args.baseline).expanduser().resolve()),
                document_paths=args.document,
                dependency_packets=[
                    read_json(Path(path).expanduser().resolve())
                    for path in args.dependency_packet
                ],
                dependency_projections=[
                    read_json(Path(path).expanduser().resolve())
                    for path in args.dependency_projection
                ],
                research_bundle=(
                    read_json(
                        Path(args.research_evidence).expanduser().resolve()
                    )
                    if args.research_evidence
                    else None
                ),
            )
            _emit(result, args.json)
            if result["status"] == "FAIL":
                return 2
            return 4 if result["status"] == "BLOCKED" else 0
        if args.command == "validate-packet":
            projection = (
                read_json(Path(args.projection).expanduser().resolve())
                if args.projection
                else None
            )
            research_bundle = (
                read_json(
                    Path(args.research_evidence).expanduser().resolve()
                )
                if args.research_evidence
                else None
            )
            result = validate_assignment_packet(
                read_json(Path(args.packet).expanduser().resolve()),
                read_json(Path(args.plan).expanduser().resolve()),
                args.assignment,
                projection,
                repo_path=args.repo,
                research_bundle=research_bundle,
            )
            _emit(result, args.json)
            return 0 if result["status"] == "PASS" else 2
        if args.command == "validate-research":
            result = validate_research_artifact(
                read_json(Path(args.artifact).expanduser().resolve()),
                repo_path=args.repo,
            )
            _emit(result, args.json)
            return 0 if result["status"] == "PASS" else 2
        if args.command == "decide":
            research_evidence = _research_evidence_digest(
                args.research_evidence,
                args.research_evidence_digest,
                repo_path=args.repo,
                goal=args.goal,
                intent=args.intent,
            )
            result = build_decision_plan(
                args.repo,
                args.goal,
                args.risk,
                host_id=args.host,
                intent=args.intent,
                research_evidence=research_evidence,
            )
            _emit(result, args.json)
            gate = result["expertise"]["research_requirement"]["gate"]
            return 4 if gate == "open" else 0
        if args.command == "validate-decision":
            plan = read_json(Path(args.plan).expanduser().resolve())
            result = (
                validate_specialist_packet(
                    read_json(Path(args.packet).expanduser().resolve()),
                    plan,
                )
                if args.packet
                else validate_decision_plan(plan)
            )
            _emit(result, args.json)
            return 0 if result["status"] == "PASS" else 2
        if args.command == "enact":
            plan = read_json(Path(args.plan).expanduser().resolve())
            bundle = read_json(Path(args.bundle).expanduser().resolve())
            packets = [
                read_json(Path(path).expanduser().resolve())
                for path in args.packet
            ]
            research_evidence = (
                read_json(
                    Path(args.research_evidence).expanduser().resolve()
                )
                if args.research_evidence
                else None
            )
            result = build_execution_plan(
                args.repo,
                plan,
                bundle,
                packets,
                authorization_source=args.authorization_source,
                host_id=args.host,
                research_evidence=research_evidence,
            )
            _emit(result, args.json)
            return 0
        if args.command == "adapt":
            result = inspect_adapter(args.repo)
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "start":
            if bool(args.fallback_reason) != bool(args.fallback_evidence):
                raise MaestroError(
                    "RUN_EXECUTION_FALLBACK_INVALID",
                    "fallback-reason and fallback-evidence must be provided together.",
                )
            execution_binding = (
                {
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": args.fallback_reason,
                    "evidence": args.fallback_evidence,
                }
                if args.fallback_reason
                else None
            )
            result = start_run_observation(
                args.repo,
                run_id=args.run_id,
                task_label=args.task_label,
                plan_path=args.plan,
                execution_binding=execution_binding,
            )
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "desktop":
            result = start_desktop_request_observation(
                args.repo,
                run_id=args.run_id,
                task_label=args.task_label,
                thread_id=args.thread_id,
                turn_id=args.turn_id,
                requested_model=args.requested_model,
                requested_reasoning_effort=(
                    args.requested_reasoning_effort
                ),
                plan_path=args.plan,
            )
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "fallback":
            result = record_execution_fallback(
                args.repo,
                observation_id=args.observation,
                run_id=args.run_id,
                reason=args.reason,
                evidence=args.evidence,
            )
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "plan":
            result = attach_run_plan(
                args.repo,
                observation_id=args.observation,
                run_id=args.run_id,
                plan_path=args.plan,
            )
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "stage":
            result = record_stage_observation(
                args.repo,
                observation_id=args.observation,
                run_id=args.run_id,
                assignment_id=args.assignment,
                status=args.status,
                evidence_source=args.evidence_source,
                evidence_refs=args.evidence,
                duration_ms=args.duration_ms,
            )
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "work-start":
            model_evidence = (
                "host_request"
                if args.requested_model is not None
                else "unavailable"
            )
            result = record_work_start(
                args.repo,
                observation_id=args.observation,
                run_id=args.run_id,
                work_id=args.work_id,
                parent_work_id=args.parent_work,
                assignment_id=args.assignment,
                kind=args.kind,
                role=args.role,
                executor_id=args.executor,
                task_summary=args.summary,
                read_only=args.work_read_only,
                attempt=args.attempt,
                followup_of_work_id=args.followup_of,
                depends_on_work_ids=args.depends_on,
                joins_work_ids=args.joins,
                requested_model=args.requested_model,
                requested_reasoning_effort=(
                    args.requested_reasoning_effort
                ),
                model_evidence=model_evidence,
                lens_ids=args.lens,
                expertise_pack_ids=args.expertise_pack,
                decision_guide_ids=args.decision_guide,
                expertise_evidence=args.expertise_evidence,
            )
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "work-finish":
            result = record_work_finish(
                args.repo,
                observation_id=args.observation,
                run_id=args.run_id,
                work_id=args.work_id,
                status=args.status,
                result_summary=args.summary,
                evidence_refs=args.evidence,
                expertise_evidence=args.expertise_evidence,
            )
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "host":
            result = record_host_observation(
                args.repo,
                observation_id=args.observation,
                run_id=args.run_id,
                source=args.source,
                quality=args.quality,
                correlation_id=args.correlation_id,
                requested_model=args.requested_model,
                requested_reasoning_effort=(
                    args.requested_reasoning_effort
                ),
                applied_model=args.applied_model,
                model_event_evidence=args.model_event_evidence,
                reroutes=_host_model_reroutes(args),
                actual_model=args.actual_model,
                tokens=_host_token_summary(args),
            )
            _emit(result, args.json)
            return 0
        if (
            args.command == "observe"
            and args.observe_command == "import-codex"
        ):
            result = import_codex_app_server_trace(
                args.repo,
                observation_id=args.observation,
                run_id=args.run_id,
                trace_path=args.trace,
                turn_id=args.turn_id,
            )
            _emit(result, args.json)
            return 0
        if args.command == "host" and args.host_command == "sync":
            result = (
                apply_host_sync_plan(args.apply_plan)
                if args.apply_plan
                else build_host_sync_plan(
                    args.host,
                    args.source_root,
                    skill_root=args.skill_root,
                )
            )
            _emit(result, args.json)
            return 0
        if args.command == "host" and args.host_command == "codex":
            result = run_codex_host(
                args.repo,
                run_id=args.run_id,
                task_label=args.task_label,
                prompt_file=args.prompt_file,
                plan_path=args.plan,
                assignment_id=args.assignment,
                projection_path=args.projection,
                baseline_path=args.baseline,
                document_paths=args.document,
                dependency_packet_paths=args.dependency_packet,
                dependency_projection_paths=args.dependency_projection,
                research_evidence_path=args.research_evidence,
                observation_id=args.observation,
                sandbox=args.sandbox,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                timeout_seconds=args.timeout,
            )
            _emit(result, args.json)
            if not args.json and result.get("final_message"):
                print(result["final_message"])
            return 0 if result["status"] == "completed" else 4
        if args.command == "record":
            result = record_run(
                args.repo,
                args.receipt,
                observation_id=args.observation,
            )
            _emit(result, args.json)
            return 0
        if args.command == "finalize":
            result = finalize_run(
                args.repo,
                run_id=args.run_id,
                observation_id=args.observation,
                outcome=args.outcome,
                evidence_refs=args.evidence,
                verifier_result=args.verifier_result,
                command_artifact_ref=args.command_artifact_ref,
                correction_count=args.correction_count,
                correction_summary=args.correction_summary,
                human_fix_required=(
                    True if args.human_fix_required else None
                ),
                decision_changed=args.decision_changed,
            )
            _emit(result, args.json)
            return 0
        if args.command == "snapshot":
            result = snapshot_report(args.repo, window=args.window)
            _emit(result, args.json)
            return 0
        if args.command == "dashboard":
            serve_dashboard(
                args.repo,
                project_paths=args.project,
                port=args.port,
                window=args.window,
                open_browser=not args.no_open,
                include_saved_projects=not args.no_saved_projects,
            )
            return 0
        if (
            args.command == "verification"
            and args.verification_command == "list"
        ):
            result = verification_inventory(args.repo)
            _emit(result, args.json)
            return 0
        if (
            args.command == "verification"
            and args.verification_command == "approve"
        ):
            if args.apply_plan:
                result = apply_verification_approval_plan(
                    args.apply_plan,
                    args.repo,
                )
            else:
                if not args.candidate:
                    raise MaestroError(
                        "VERIFICATION_CANDIDATE_REQUIRED",
                        "Preview requires --candidate.",
                    )
                result = build_verification_approval_plan(
                    args.repo,
                    candidate_id=args.candidate,
                )
            _emit(result, args.json)
            return 0
        if args.command == "govern" and args.govern_command == "report":
            result = govern_report(args.repo, window=args.window, threshold=args.threshold)
            _emit(result, args.json)
            return 0
        if args.command == "govern" and args.govern_command == "classify":
            result = classify_surface_file(args.input)
            _emit(result, args.json)
            return 0 if result["status"] == "classified" else 2
    except MaestroError as exc:
        error = {
            "schema_version": "maestro_error_v1",
            "status": "error",
            "code": exc.code,
            "message": exc.message,
        }
        print(json.dumps(error, ensure_ascii=False, sort_keys=True, indent=2))
        return exc.exit_code
    except Exception as exc:
        error = {
            "schema_version": "maestro_error_v1",
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": str(exc),
        }
        print(json.dumps(error, ensure_ascii=False, sort_keys=True, indent=2))
        return 5
    return 5


if __name__ == "__main__":
    sys.exit(main())
