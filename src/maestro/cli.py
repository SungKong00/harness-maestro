from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from .doctor import doctor_report
from .documents import select_documents
from .errors import MaestroError
from .governance import govern_report, record_run
from .project import (
    apply_plan,
    build_init_plan,
    build_upgrade_plan,
    inspect_adapter,
)
from .registry import route_goal
from .status import status_report


def _emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
        return
    status = value.get("status") or value.get("evidence_status") or "ok"
    print(f"{value.get('schema_version', 'maestro')}: {status}")
    for key in ("repo_root", "plan_id", "selected_lenses", "changed_paths"):
        if key in value:
            print(f"{key}: {value[key]}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="maestro")
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

    route = commands.add_parser("route", help="Create a deterministic Lens and Executor plan")
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
    route.add_argument("--json", action="store_true")

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
            result = doctor_report(args.repo)
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
        if args.command == "route":
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
