from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .doctor import doctor_report
from .errors import MaestroError
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

    next_actions: list[dict[str, str]] = []
    if not initialized:
        next_actions.append(
            {
                "id": "run_init",
                "command": f"maestro init --repo {repo} --json",
                "reason": "The project has not completed reviewed initialization.",
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
        "self_improvement": self_improvement,
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
