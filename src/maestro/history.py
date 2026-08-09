from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .governance import recent_run_events
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    file_sha256,
    pretty_json,
    read_json,
    safe_target,
    sha256_text,
    slugify,
)

HISTORY_INDEX_VERSION = "maestro_history_index_v1"
HISTORY_MANIFEST_VERSION = "maestro_history_bundle_manifest_v1"
HISTORY_SUMMARY_VERSION = "maestro_history_bundle_summary_v1"
HISTORY_PLAN_VERSION = "maestro_history_bundle_plan_v1"
RUN_LABELS_VERSION = "maestro_run_display_labels_v1"
MAX_BUNDLES = 100
MAX_EVENTS_PER_BUNDLE = 50
MAX_LABEL_LENGTH = 100
MAX_HISTORY_FILE_BYTES = 512_000


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _label(value: Any, *, field: str = "label") -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > MAX_LABEL_LENGTH
        or any(character in value for character in "\r\n\x00")
    ):
        raise MaestroError(
            "HISTORY_LABEL_INVALID",
            f"{field} must be one non-empty line of at most "
            f"{MAX_LABEL_LENGTH} characters.",
        )
    return value.strip()


def _read_optional_json(path: Path, *, empty: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(empty)
    try:
        valid = (
            not path.is_symlink()
            and path.is_file()
            and path.stat().st_size <= MAX_HISTORY_FILE_BYTES
        )
    except OSError:
        valid = False
    if not valid:
        raise MaestroError(
            "HISTORY_STATE_INVALID",
            f"History state is unsafe or too large: {path.name}",
        )
    value = read_json(path)
    if not isinstance(value, dict):
        raise MaestroError(
            "HISTORY_STATE_INVALID",
            f"History state must be one object: {path.name}",
        )
    return value


def _index(repo: Path) -> dict[str, Any]:
    value = _read_optional_json(
        safe_target(repo, ".maestro/state/history/index.json"),
        empty={"schema_version": HISTORY_INDEX_VERSION, "bundles": []},
    )
    bundles = value.get("bundles")
    if (
        value.get("schema_version") != HISTORY_INDEX_VERSION
        or not isinstance(bundles, list)
        or len(bundles) > MAX_BUNDLES
        or any(
            not isinstance(item, dict)
            or set(item)
            != {
                "bundle_id",
                "label",
                "path",
                "created_at",
                "updated_at",
                "event_count",
            }
            for item in bundles
        )
    ):
        raise MaestroError(
            "HISTORY_STATE_INVALID",
            "History index does not satisfy the bounded bundle contract.",
        )
    return value


def _bundle_files(
    repo: Path,
    entry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = entry.get("path")
    if not isinstance(root, str):
        raise MaestroError(
            "HISTORY_STATE_INVALID",
            "History bundle path is missing.",
        )
    manifest = _read_optional_json(
        safe_target(repo, f"{root}/manifest.json"),
        empty={},
    )
    summary = _read_optional_json(
        safe_target(repo, f"{root}/summary.json"),
        empty={},
    )
    if (
        manifest.get("schema_version") != HISTORY_MANIFEST_VERSION
        or manifest.get("bundle_id") != entry.get("bundle_id")
        or manifest.get("label") != entry.get("label")
        or manifest.get("created_at") != entry.get("created_at")
        or manifest.get("updated_at") != entry.get("updated_at")
        or not isinstance(manifest.get("event_ids"), list)
        or len(manifest["event_ids"]) > MAX_EVENTS_PER_BUNDLE
        or len(manifest["event_ids"]) != len(set(manifest["event_ids"]))
        or len(manifest["event_ids"]) != entry.get("event_count")
        or summary.get("schema_version") != HISTORY_SUMMARY_VERSION
        or summary.get("bundle_id") != entry.get("bundle_id")
        or summary.get("label") != entry.get("label")
        or summary.get("event_ids") != manifest.get("event_ids")
        or not isinstance(summary.get("runs"), list)
    ):
        raise MaestroError(
            "HISTORY_STATE_INVALID",
            f"History bundle is invalid: {entry.get('bundle_id')}",
        )
    return manifest, summary


def history_inventory(repo_path: str | Path) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    index = _index(repo)
    bundles: list[dict[str, Any]] = []
    bundled_event_ids: set[str] = set()
    for entry in index["bundles"]:
        manifest, summary = _bundle_files(repo, entry)
        overlap = bundled_event_ids.intersection(manifest["event_ids"])
        if overlap:
            raise MaestroError(
                "HISTORY_STATE_INVALID",
                "A run may belong to only one history bundle.",
            )
        bundled_event_ids.update(manifest["event_ids"])
        bundles.append(
            {
                **entry,
                "event_ids": list(manifest["event_ids"]),
                "runs": list(summary["runs"]),
                "outcomes": dict(summary.get("outcomes", {})),
                "period": dict(summary.get("period", {})),
                "measurement_coverage": dict(
                    summary.get("measurement_coverage", {})
                ),
            }
        )
    bundles.sort(key=lambda item: item["updated_at"], reverse=True)
    return {
        "schema_version": "maestro_history_inventory_v1",
        "bundles": bundles,
        "bundled_event_ids": sorted(bundled_event_ids),
        "writes_performed": False,
    }


def _recent_events(repo: Path) -> dict[str, dict[str, Any]]:
    history = recent_run_events(repo, window=100)
    return {
        event["event_id"]: event
        for event in history.get("display_runs", history["runs"])
    }


def _compact_run(event: dict[str, Any]) -> dict[str, Any]:
    host = event.get("host_observation")
    requested_model = None
    applied_model = None
    if (
        isinstance(host, dict)
        and host.get("schema_version") == "maestro_host_observation_v2"
    ):
        requested_model = host.get("requested_model")
        if host.get("model_event_evidence") == "complete":
            applied_model = host.get("applied_model")
    return {
        "event_id": event["event_id"],
        "run_id": event["run_id"],
        "task_label": event.get("task_label") or event["run_id"],
        "timestamp": event["timestamp"],
        "outcome": event["outcome"],
        "duration_ms": event.get("duration_ms"),
        "tokens": event.get("tokens"),
        "requested_model": requested_model,
        "applied_model": applied_model,
        "expertise_pack_ids": list(
            event.get("selected_expertise_packs", [])
        ),
    }


def _summary(
    *,
    bundle_id: str,
    label: str,
    event_ids: list[str],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    outcomes: dict[str, int] = {}
    for run in runs:
        outcomes[run["outcome"]] = outcomes.get(run["outcome"], 0) + 1
    timestamps = sorted(
        run["timestamp"]
        for run in runs
        if isinstance(run.get("timestamp"), str)
    )
    total = len(runs)

    def coverage(field: str) -> dict[str, Any]:
        count = sum(run.get(field) is not None for run in runs)
        return {
            "measured_runs": count,
            "total_runs": total,
            "ratio": round(count / total, 3) if total else None,
        }

    return {
        "schema_version": HISTORY_SUMMARY_VERSION,
        "bundle_id": bundle_id,
        "label": label,
        "event_ids": event_ids,
        "run_count": total,
        "period": {
            "started_at": timestamps[0] if timestamps else None,
            "completed_at": timestamps[-1] if timestamps else None,
        },
        "outcomes": dict(sorted(outcomes.items())),
        "measurement_coverage": {
            "duration": coverage("duration_ms"),
            "tokens": coverage("tokens"),
            "requested_model": coverage("requested_model"),
            "applied_model": coverage("applied_model"),
        },
        "runs": runs,
    }


def _operation(repo: Path, path: str, content: str) -> dict[str, Any]:
    target = safe_target(repo, path)
    return {
        "op": "replace" if target.is_file() else "create",
        "path": path,
        "before_sha256": file_sha256(target),
        "after_sha256": sha256_text(content),
        "content": content,
    }


def build_history_bundle_plan(
    repo_path: str | Path,
    *,
    label: str,
    event_ids: list[str],
    bundle_id: str | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    normalized_label = _label(label)
    selected_ids = list(dict.fromkeys(event_ids))
    if (
        not selected_ids
        or len(selected_ids) > MAX_EVENTS_PER_BUNDLE
        or any(
            not isinstance(item, str) or not item
            for item in selected_ids
        )
    ):
        raise MaestroError(
            "HISTORY_EVENT_SELECTION_INVALID",
            "Select from 1 to 50 unique recorded events.",
        )
    index = _index(repo)
    inventory = history_inventory(repo)
    entries = {
        item["bundle_id"]: item
        for item in index["bundles"]
    }
    membership = {
        event_id: item["bundle_id"]
        for item in inventory["bundles"]
        for event_id in item["event_ids"]
    }
    if bundle_id is None:
        if any(
            item["label"].casefold() == normalized_label.casefold()
            for item in index["bundles"]
        ):
            raise MaestroError(
                "HISTORY_LABEL_CONFLICT",
                "A bundle with this name already exists; add to that bundle instead.",
            )
        if len(index["bundles"]) >= MAX_BUNDLES:
            raise MaestroError(
                "HISTORY_BUNDLE_LIMIT",
                f"At most {MAX_BUNDLES} history bundles are retained.",
            )
        conflicting = sorted(
            event_id
            for event_id in selected_ids
            if event_id in membership
        )
        if conflicting:
            raise MaestroError(
                "HISTORY_EVENT_ALREADY_BUNDLED",
                "Selected runs already belong to a history bundle.",
            )
        bundle_id = sha256_text(
            canonical_json(
                {
                    "label": normalized_label,
                    "event_ids": sorted(selected_ids),
                    "created_at": _timestamp(),
                }
            )
        )[:16]
        created_at = _timestamp()
        existing_event_ids: list[str] = []
        existing_runs: list[dict[str, Any]] = []
        directory = (
            f".maestro/state/history/{slugify(normalized_label)}--{bundle_id}"
        )
    else:
        entry = entries.get(bundle_id)
        if entry is None:
            raise MaestroError(
                "HISTORY_BUNDLE_NOT_FOUND",
                "The selected history bundle no longer exists.",
            )
        if normalized_label != entry["label"]:
            raise MaestroError(
                "HISTORY_LABEL_MISMATCH",
                "Existing bundle additions must preserve its current name.",
            )
        manifest, summary = _bundle_files(repo, entry)
        conflicts = sorted(
            event_id
            for event_id in selected_ids
            if event_id in membership
            and membership[event_id] != bundle_id
        )
        if conflicts:
            raise MaestroError(
                "HISTORY_EVENT_ALREADY_BUNDLED",
                "A selected run already belongs to another history bundle.",
            )
        selected_ids = [
            event_id
            for event_id in selected_ids
            if event_id not in manifest["event_ids"]
        ]
        if not selected_ids:
            raise MaestroError(
                "HISTORY_BUNDLE_NO_CHANGES",
                "Every selected run is already in this bundle.",
            )
        existing_event_ids = list(manifest["event_ids"])
        existing_runs = list(summary["runs"])
        created_at = manifest["created_at"]
        directory = entry["path"]

    events = _recent_events(repo)
    missing = sorted(set(selected_ids) - set(events))
    if missing:
        raise MaestroError(
            "HISTORY_EVENT_NOT_FOUND",
            "Selected runs are outside the retained 100-run history window.",
        )
    combined_event_ids = [*existing_event_ids, *selected_ids]
    if len(combined_event_ids) > MAX_EVENTS_PER_BUNDLE:
        raise MaestroError(
            "HISTORY_BUNDLE_LIMIT",
            f"One bundle may contain at most {MAX_EVENTS_PER_BUNDLE} runs.",
        )
    compact_by_id = {
        item["event_id"]: item
        for item in existing_runs
        if isinstance(item, dict) and isinstance(item.get("event_id"), str)
    }
    compact_by_id.update(
        {
            event_id: _compact_run(events[event_id])
            for event_id in selected_ids
        }
    )
    combined_runs = [
        compact_by_id[event_id]
        for event_id in combined_event_ids
    ]
    now = _timestamp()
    manifest = {
        "schema_version": HISTORY_MANIFEST_VERSION,
        "bundle_id": bundle_id,
        "label": normalized_label,
        "event_ids": combined_event_ids,
        "created_at": created_at,
        "updated_at": now,
    }
    summary = _summary(
        bundle_id=bundle_id,
        label=normalized_label,
        event_ids=combined_event_ids,
        runs=combined_runs,
    )
    updated_entries = [
        item for item in index["bundles"]
        if item["bundle_id"] != bundle_id
    ]
    updated_entries.append(
        {
            "bundle_id": bundle_id,
            "label": normalized_label,
            "path": directory,
            "created_at": created_at,
            "updated_at": now,
            "event_count": len(combined_event_ids),
        }
    )
    updated_entries.sort(key=lambda item: item["updated_at"], reverse=True)
    updated_index = {
        "schema_version": HISTORY_INDEX_VERSION,
        "bundles": updated_entries,
    }
    base = {
        "schema_version": HISTORY_PLAN_VERSION,
        "repo_realpath": str(repo),
        "bundle_id": bundle_id,
        "label": normalized_label,
        "added_event_digests": {
            event_id: sha256_text(canonical_json(events[event_id]))
            for event_id in selected_ids
        },
        "operations": [
            _operation(
                repo,
                f"{directory}/manifest.json",
                pretty_json(manifest),
            ),
            _operation(
                repo,
                f"{directory}/summary.json",
                pretty_json(summary),
            ),
            _operation(
                repo,
                ".maestro/state/history/index.json",
                pretty_json(updated_index),
            ),
        ],
        "writes_performed": False,
    }
    digest = sha256_text(canonical_json(base))
    base["plan_id"] = digest[:20]
    base["plan_digest"] = digest
    return base


def apply_history_bundle_plan(
    plan: dict[str, Any],
    repo_override: str | Path | None = None,
) -> dict[str, Any]:
    allowed = {
        "schema_version",
        "repo_realpath",
        "bundle_id",
        "label",
        "added_event_digests",
        "operations",
        "writes_performed",
        "plan_id",
        "plan_digest",
    }
    if (
        not isinstance(plan, dict)
        or set(plan) != allowed
        or plan.get("schema_version") != HISTORY_PLAN_VERSION
        or plan.get("writes_performed") is not False
    ):
        raise MaestroError(
            "HISTORY_PLAN_INVALID",
            "History bundle plan does not satisfy the typed contract.",
        )
    unsigned = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "plan_digest"}
    }
    digest = sha256_text(canonical_json(unsigned))
    if plan.get("plan_id") != digest[:20] or plan.get("plan_digest") != digest:
        raise MaestroError(
            "PLAN_TAMPERED",
            "History bundle plan digest does not match.",
        )
    repo = ensure_repo(repo_override or plan["repo_realpath"])
    if str(repo) != plan["repo_realpath"]:
        raise MaestroError(
            "PLAN_REPO_MISMATCH",
            "History bundle plan belongs to a different repository.",
        )
    events = _recent_events(repo)
    if any(
        events.get(event_id) is None
        or sha256_text(canonical_json(events[event_id])) != expected
        for event_id, expected in plan["added_event_digests"].items()
    ):
        raise MaestroError(
            "PLAN_STALE",
            "Selected RunReceipt evidence changed after history preview.",
        )
    operations = plan.get("operations")
    if not isinstance(operations, list) or len(operations) != 3:
        raise MaestroError(
            "HISTORY_PLAN_INVALID",
            "History plan must contain manifest, summary, and index operations.",
        )
    manifest_path = (
        operations[0].get("path")
        if isinstance(operations[0], dict)
        else None
    )
    summary_path = (
        operations[1].get("path")
        if isinstance(operations[1], dict)
        else None
    )
    index_path = (
        operations[2].get("path")
        if isinstance(operations[2], dict)
        else None
    )
    if (
        not isinstance(manifest_path, str)
        or not manifest_path.startswith(".maestro/state/history/")
        or not manifest_path.endswith("/manifest.json")
        or summary_path
        != manifest_path.removesuffix("manifest.json") + "summary.json"
        or index_path != ".maestro/state/history/index.json"
    ):
        raise MaestroError(
            "HISTORY_PLAN_INVALID",
            "History plan paths exceed the bounded history directory contract.",
        )
    originals: dict[Path, bytes | None] = {}
    for operation in operations:
        if (
            not isinstance(operation, dict)
            or set(operation)
            != {
                "op",
                "path",
                "before_sha256",
                "after_sha256",
                "content",
            }
            or operation["op"] not in {"create", "replace"}
            or not isinstance(operation["content"], str)
            or sha256_text(operation["content"]) != operation["after_sha256"]
        ):
            raise MaestroError(
                "HISTORY_PLAN_INVALID",
                "History operation does not satisfy the bounded write contract.",
            )
        target = safe_target(repo, operation["path"])
        if file_sha256(target) != operation["before_sha256"]:
            raise MaestroError(
                "PLAN_STALE",
                f"History state changed after preview: {operation['path']}",
            )
        originals[target] = target.read_bytes() if target.is_file() else None
    try:
        manifest_value = json.loads(operations[0]["content"])
        summary_value = json.loads(operations[1]["content"])
        index_value = json.loads(operations[2]["content"])
    except json.JSONDecodeError as exc:
        raise MaestroError(
            "HISTORY_PLAN_INVALID",
            "History operation content must be valid JSON.",
        ) from exc
    if (
        not isinstance(manifest_value, dict)
        or manifest_value.get("bundle_id") != plan["bundle_id"]
        or manifest_value.get("label") != plan["label"]
        or not isinstance(summary_value, dict)
        or summary_value.get("bundle_id") != plan["bundle_id"]
        or summary_value.get("label") != plan["label"]
        or not isinstance(index_value, dict)
        or index_value.get("schema_version") != HISTORY_INDEX_VERSION
    ):
        raise MaestroError(
            "HISTORY_PLAN_INVALID",
            "History operation content is not bound to the previewed bundle.",
        )
    changed: list[str] = []
    try:
        for operation in operations:
            target = safe_target(repo, operation["path"])
            atomic_write(target, operation["content"].encode("utf-8"))
            changed.append(operation["path"])
        history_inventory(repo)
    except BaseException:
        for target, original in originals.items():
            if original is None:
                if target.exists() and not target.is_symlink():
                    target.unlink()
            else:
                atomic_write(target, original)
        raise
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "history-bundle-apply",
        "status": "applied",
        "bundle_id": plan["bundle_id"],
        "label": plan["label"],
        "changed_paths": changed,
        "writes_performed": True,
    }


def run_display_labels(repo_path: str | Path) -> dict[str, str]:
    repo = ensure_repo(repo_path)
    value = _read_optional_json(
        safe_target(repo, ".maestro/state/history/run-labels.json"),
        empty={"schema_version": RUN_LABELS_VERSION, "labels": {}},
    )
    labels = value.get("labels")
    if (
        value.get("schema_version") != RUN_LABELS_VERSION
        or not isinstance(labels, dict)
        or len(labels) > 100
        or any(
            not isinstance(event_id, str)
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > MAX_LABEL_LENGTH
            for event_id, label in labels.items()
        )
    ):
        raise MaestroError(
            "HISTORY_STATE_INVALID",
            "Run display labels do not satisfy the bounded contract.",
        )
    return dict(labels)


def set_run_display_label(
    repo_path: str | Path,
    *,
    event_id: str,
    label: str,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    normalized = _label(label, field="run label")
    if event_id not in _recent_events(repo):
        raise MaestroError(
            "HISTORY_EVENT_NOT_FOUND",
            "Run display labels may target only a retained recent event.",
        )
    labels = run_display_labels(repo)
    if labels.get(event_id) == normalized:
        return {
            "schema_version": "maestro_command_result_v1",
            "command": "history-label-run",
            "status": "already_set",
            "event_id": event_id,
            "label": normalized,
            "writes_performed": False,
        }
    labels[event_id] = normalized
    target = safe_target(repo, ".maestro/state/history/run-labels.json")
    atomic_write(
        target,
        pretty_json(
            {"schema_version": RUN_LABELS_VERSION, "labels": labels}
        ).encode("utf-8"),
    )
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "history-label-run",
        "status": "set",
        "event_id": event_id,
        "label": normalized,
        "writes_performed": True,
    }
