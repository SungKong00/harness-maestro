from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .documents import core_document_status
from .doctor import doctor_report
from .errors import MaestroError
from .governance import govern_report
from .project import build_upgrade_plan
from .util import ensure_repo, read_json, safe_target


def status_report(repo_path: str | Path) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    project_path = safe_target(repo, ".maestro/project.json")
    managed_path = safe_target(repo, ".maestro/managed.json")
    lock_path = safe_target(repo, ".maestro/lock.json")
    initialized = all(path.is_file() for path in (project_path, managed_path, lock_path))
    doctor = doctor_report(repo)
    project: dict[str, Any] | None = None
    lock: dict[str, Any] | None = None
    if project_path.is_file():
        value = read_json(project_path)
        project = value if isinstance(value, dict) else None
    if lock_path.is_file():
        value = read_json(lock_path)
        lock = value if isinstance(value, dict) else None

    pending_operations: list[dict[str, Any]] = []
    plan_error: dict[str, str] | None = None
    try:
        pending_operations = build_upgrade_plan(repo)["operations"]
    except MaestroError as exc:
        plan_error = {"code": exc.code, "message": exc.message}

    core_status = core_document_status(repo) if initialized else []
    core_gaps = [item for item in core_status if item["status"] != "active"]
    if not initialized:
        readiness_state = "blocked"
        readiness_reasons = ["project_not_initialized"]
    elif any(item["status"] != "draft" for item in core_gaps):
        readiness_state = "blocked"
        readiness_reasons = [
            f"core_document_{item['status']}:{item['role']}"
            for item in core_gaps
        ]
    elif core_gaps:
        readiness_state = "draft"
        readiness_reasons = [
            f"core_document_draft:{item['role']}"
            for item in core_gaps
        ]
    else:
        readiness_state = "ready"
        readiness_reasons = []

    commands = project.get("commands") if project else None
    verification_commands = (
        project.get("verification_commands")
        if project
        else None
    )
    candidate_command_count = len(commands) if isinstance(commands, list) else 0
    approved_command_count = (
        len(verification_commands)
        if isinstance(verification_commands, list)
        else 0
    )

    governance: dict[str, Any] = {
        "status": "not_available",
        "review_due": False,
        "candidate_count": 0,
        "evidence_status": "uninitialized",
    }
    if initialized:
        try:
            governance_report = govern_report(repo)
            governance = {
                "status": "available",
                "review_due": governance_report["governance_review_due"],
                "candidate_count": len(
                    governance_report["candidates_for_review"]
                ),
                "evidence_status": governance_report["evidence_status"],
                "included_compatible_records": governance_report[
                    "included_compatible_records"
                ],
                "retention_review_due": governance_report["retention"][
                    "review_due"
                ],
            }
        except MaestroError as exc:
            governance = {
                "status": "unavailable",
                "review_due": False,
                "candidate_count": 0,
                "evidence_status": "unavailable",
                "error": {"code": exc.code, "message": exc.message},
            }

    next_actions: list[dict[str, Any]] = []
    if not initialized:
        next_actions.append(
            {
                "id": "run_init",
                "command": f"maestro init --repo {repo} --json",
                "reason": "The project has not completed reviewed initialization.",
            }
        )
    elif core_gaps:
        next_actions.append(
            {
                "id": "complete_core_documents",
                "paths": [item["path"] for item in core_gaps if item["path"]],
                "reason": (
                    "Project initialization is installed, but core project facts "
                    "are not active evidence yet."
                ),
            }
        )
    elif pending_operations:
        next_actions.append(
            {
                "id": "review_upgrade",
                "command": f"maestro upgrade --repo {repo} --json",
                "reason": f"{len(pending_operations)} managed change(s) are pending review.",
            }
        )
    elif doctor["status"] != "PASS":
        next_actions.append(
            {
                "id": "repair_doctor_findings",
                "command": f"maestro doctor --repo {repo} --json",
                "reason": "Doctor reports drift or invalid project state.",
            }
        )
    elif candidate_command_count and not approved_command_count:
        next_actions.append(
            {
                "id": "review_verification_commands",
                "path": ".maestro/project.json",
                "reason": (
                    "Detected commands are candidates only; copy verified commands "
                    "into verification_commands to make them project authority."
                ),
            }
        )
    if governance["review_due"]:
        next_actions.append(
            {
                "id": "review_governance_candidates",
                "command": f"maestro govern report --repo {repo} --json",
                "reason": (
                    f"{governance['candidate_count']} repeated, verified "
                    "improvement candidate(s) need owner review."
                ),
            }
        )

    documentation = project.get("documentation") if project else None
    self_improvement = project.get("self_improvement") if project else None
    return {
        "schema_version": "maestro_status_v1",
        "repo_root": str(repo),
        "initialized": initialized,
        "project_id": project.get("project_id") if project else None,
        "framework": {
            "current": __version__,
            "locked": (
                lock.get("framework", {}).get("version")
                if isinstance(lock, dict)
                else None
            ),
        },
        "doctor": {
            "status": doctor["status"],
            "summary": doctor["summary"],
        },
        "documentation": documentation,
        "readiness": {
            "state": readiness_state,
            "reason_codes": readiness_reasons,
            "core_documents": core_status,
            "verification_commands": {
                "candidate_count": candidate_command_count,
                "approved_count": approved_command_count,
            },
        },
        "self_improvement": self_improvement,
        "governance": governance,
        "pending_managed_operations": [
            {
                "op": item["op"],
                "path": item["path"],
            }
            for item in pending_operations
        ],
        "plan_error": plan_error,
        "next_actions": next_actions,
        "writes_performed": False,
    }
