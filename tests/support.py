from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def apply_fresh_init(repo: Path) -> dict[str, Any]:
    from maestro.project import apply_plan, build_init_plan

    plan = build_init_plan(repo)
    plan_path = repo.parent / f"{repo.name}-init-plan.json"
    write_json(plan_path, plan)
    return apply_plan(plan_path, repo)


def check_by_id(report: dict[str, Any], check_id: str) -> dict[str, str]:
    return next(item for item in report["checks"] if item["id"] == check_id)


def canonical_document(
    doc_id: str,
    *,
    summary: str = "Test document.",
    body: str = "# Test document\n",
    status: str = "active",
) -> str:
    return (
        "---\n"
        "maestro_doc: 1\n"
        f"id: {doc_id}\n"
        "type: convention\n"
        f"status: {status}\n"
        "authority: repository\n"
        "owner: test\n"
        f"summary: {summary}\n"
        "---\n\n"
        f"{body}"
    )


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def event(
    project_id: str,
    checkout_id: str,
    run_id: str,
    fingerprint: str,
    *,
    tokens: dict[str, int | None] | None = None,
    duration_ms: int | None = None,
    event_id: str | None = None,
    timestamp: str = "2026-07-24T00:00:00Z",
    selected_lenses: list[str] | None = None,
    lens_definition_digests: dict[str, str] | None = None,
    executor_definition_digests: dict[str, str] | None = None,
    primary_executor_id: str = "lens-reviewer",
    executor_ids: list[str] | None = None,
    finding_severity: str | None = "high",
    decision_changed: bool = True,
    verifier_result: str = "failed",
    command_artifact_ref: str | None = None,
) -> dict[str, Any]:
    from maestro import __version__
    from maestro.registry import definition_digest_maps, registry_digest

    definitions = definition_digest_maps()
    selected_lenses = selected_lenses or []
    if lens_definition_digests is None:
        lens_definition_digests = {
            lens_id: definitions["lenses"][lens_id]
            for lens_id in selected_lenses
        }
    if executor_definition_digests is None:
        executor_ids = executor_ids or [primary_executor_id, "verifier"]
        executor_definition_digests = {
            executor_id: definitions["executors"][executor_id]
            for executor_id in executor_ids
        }
    else:
        executor_ids = executor_ids or list(executor_definition_digests)

    return {
        "schema_version": "maestro_event_v1",
        "event_id": event_id or f"event-{run_id}",
        "timestamp": timestamp,
        "project_id": project_id,
        "checkout_id": checkout_id,
        "run_id": run_id,
        "framework_version": __version__,
        "registry_digest": registry_digest(),
        "lens_definition_digests": lens_definition_digests,
        "executor_definition_digests": executor_definition_digests,
        "risk": "medium",
        "route_depth": "standard",
        "selected_lenses": selected_lenses,
        "executor_runs": len(executor_ids),
        "primary_executor_id": primary_executor_id,
        "executor_ids": executor_ids,
        "kind": "correction",
        "outcome": "corrected",
        "fingerprint": fingerprint,
        "evidence_refs": [f"artifact:{run_id}"],
        "tokens": tokens,
        "duration_ms": duration_ms,
        "correction_count": 1,
        "agent_calls": 0,
        "human_fix_required": None,
        "finding_severity": finding_severity,
        "decision_changed": decision_changed,
        "verifier_result": verifier_result,
        "command_artifact_ref": (
            command_artifact_ref
            if command_artifact_ref is not None
            else f"artifact:command:{run_id}"
        ),
        "project_convention_action": "none",
        "project_convention_basis": "none",
        "project_convention_path": None,
    }
