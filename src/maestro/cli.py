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
from .expertise_lifecycle import (
    apply_expertise_activation_plan,
    apply_expertise_deactivation_plan,
    apply_expertise_export_plan,
    apply_expertise_update_plan,
    build_expertise_activation_plan,
    build_expertise_deactivation_plan,
    build_expertise_export_plan,
    build_expertise_update_plan,
    expertise_inventory,
    validate_expertise_contribution,
    validate_expertise_candidate,
)
from .governance import govern_report, record_run
from .observations import (
    import_codex_app_server_trace,
    record_host_observation,
    start_run_observation,
)
from .project import (
    apply_plan,
    build_init_plan,
    build_upgrade_plan,
    inspect_adapter,
)
from .research import BUNDLE_VERSION, validate_research_artifact
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
) -> str | None:
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
    validation = validate_research_artifact(artifact)
    if validation["status"] != "PASS":
        first = validation["issues"][0]
        raise MaestroError(first["code"], first["message"])
    digest = validation["artifact_digest"]
    if expected_digest is not None and expected_digest != digest:
        raise MaestroError(
            "RESEARCH_EVIDENCE_DIGEST_MISMATCH",
            "The supplied digest does not match the validated ResearchBundle.",
        )
    return digest


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
    expertise_export = expertise_commands.add_parser(
        "export",
        help="Preview or write one validated project-local promotion bundle",
    )
    expertise_export.add_argument("--repo", default=".")
    expertise_export.add_argument("--candidate")
    expertise_export.add_argument("--apply-plan")
    expertise_export.add_argument("--json", action="store_true")
    expertise_validate_contribution = expertise_commands.add_parser(
        "validate-contribution",
        help="Validate one exported Expertise contribution without importing it",
    )
    expertise_validate_contribution.add_argument("--bundle", required=True)
    expertise_validate_contribution.add_argument("--json", action="store_true")

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
    validate_packet.add_argument("--json", action="store_true")

    validate_research = commands.add_parser(
        "validate-research",
        help="Validate one bounded ResearchPacket or synthesized ResearchBundle",
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
    observe_start.add_argument("--json", action="store_true")
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

    record = commands.add_parser(
        "record",
        help="Append one validated compact RunReceipt at task completion",
    )
    record.add_argument("--repo", default=".")
    record.add_argument("--receipt", required=True)
    record.add_argument(
        "--observation",
        help=(
            "Observation ID returned by observe start; fills the task label, "
            "plan summary, and missing duration"
        ),
    )
    record.add_argument("--json", action="store_true")

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
            research_evidence_digest = _research_evidence_digest(
                args.research_evidence,
                args.research_evidence_digest,
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
                    research_evidence_digest,
                    repo_path=args.repo,
                )
            else:
                if research_evidence_digest is not None:
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
            result = validate_route_v2(
                read_json(Path(args.plan).expanduser().resolve()),
                repo_path=args.repo,
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
            result = validate_assignment_packet(
                read_json(Path(args.packet).expanduser().resolve()),
                read_json(Path(args.plan).expanduser().resolve()),
                args.assignment,
                projection,
                repo_path=args.repo,
            )
            _emit(result, args.json)
            return 0 if result["status"] == "PASS" else 2
        if args.command == "validate-research":
            result = validate_research_artifact(
                read_json(Path(args.artifact).expanduser().resolve())
            )
            _emit(result, args.json)
            return 0 if result["status"] == "PASS" else 2
        if args.command == "decide":
            research_evidence_digest = _research_evidence_digest(
                args.research_evidence,
                args.research_evidence_digest,
            )
            result = build_decision_plan(
                args.repo,
                args.goal,
                args.risk,
                host_id=args.host,
                intent=args.intent,
                research_evidence_digest=research_evidence_digest,
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
            result = build_execution_plan(
                args.repo,
                plan,
                bundle,
                packets,
                authorization_source=args.authorization_source,
                host_id=args.host,
            )
            _emit(result, args.json)
            return 0
        if args.command == "adapt":
            result = inspect_adapter(args.repo)
            _emit(result, args.json)
            return 0
        if args.command == "observe" and args.observe_command == "start":
            result = start_run_observation(
                args.repo,
                run_id=args.run_id,
                task_label=args.task_label,
                plan_path=args.plan,
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
        if args.command == "record":
            result = record_run(
                args.repo,
                args.receipt,
                observation_id=args.observation,
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
                port=args.port,
                window=args.window,
                open_browser=not args.no_open,
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
