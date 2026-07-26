from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .decisions import (
    build_decision_plan,
    build_execution_plan,
    validate_decision_plan,
    validate_specialist_packet,
)
from .conventions import (
    apply_convention_draft_plan,
    build_convention_draft_plan,
)
from .doctor import doctor_report
from .documents import select_documents
from .errors import MaestroError
from .expertise_lifecycle import (
    apply_expertise_activation_plan,
    build_expertise_activation_plan,
    expertise_inventory,
)
from .governance import govern_report, record_run
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
from .util import read_json


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

    expertise = commands.add_parser(
        "expertise",
        help="Inspect or explicitly activate project-local Expertise",
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
    expertise_activate = expertise_commands.add_parser(
        "activate",
        help="Preview or apply candidate publication as a tracked project pilot",
    )
    expertise_activate.add_argument("--repo", default=".")
    expertise_activate.add_argument("--candidate")
    expertise_activate.add_argument("--approval-ref")
    expertise_activate.add_argument("--apply-plan")
    expertise_activate.add_argument("--json", action="store_true")

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

    record = commands.add_parser(
        "record",
        help="Append one validated compact RunReceipt at task completion",
    )
    record.add_argument("--repo", default=".")
    record.add_argument("--receipt", required=True)
    record.add_argument("--json", action="store_true")

    govern = commands.add_parser("govern", help="Read-only harness governance")
    govern_commands = govern.add_subparsers(dest="govern_command", required=True)
    report = govern_commands.add_parser("report", help="Report repeated evidence without promotion")
    report.add_argument("--repo", default=".")
    report.add_argument("--window", type=int, default=20)
    report.add_argument("--threshold", type=int, default=3)
    report.add_argument("--json", action="store_true")
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
        if args.command == "expertise" and args.expertise_command == "list":
            result = expertise_inventory(args.repo)
            _emit(result, args.json)
            return 0
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
        if args.command == "record":
            result = record_run(args.repo, args.receipt)
            _emit(result, args.json)
            return 0
        if args.command == "govern" and args.govern_command == "report":
            result = govern_report(args.repo, window=args.window, threshold=args.threshold)
            _emit(result, args.json)
            return 0
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
