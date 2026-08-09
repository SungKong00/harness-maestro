from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .errors import MaestroError
from .project import checkout_id
from .util import (
    atomic_write,
    canonical_json,
    ensure_repo,
    pretty_json,
    read_json,
    safe_target,
    sha256_text,
)
from .work import observation_write_lock


REQUEST_LINEAGE_VERSION = "maestro_request_lineage_v1"
REQUEST_ALIAS_VERSION = "maestro_request_lineage_aliases_v1"
DESKTOP_REQUEST_SOURCE = "codex-desktop-request-meta"
REQUEST_ALIAS_PATH = ".maestro/state/request-lineage-aliases.json"
_LINEAGE_LOCK_TARGET = ".maestro/state/request-lineage"
_MAX_REQUEST_KEY_LENGTH = 160
_MAX_LINEAGE_OBSERVATIONS = 10_000
_LINEAGE_FIELDS = {
    "schema_version",
    "root_request_id",
    "root_run_id",
    "parent_run_id",
    "parent_observation_id",
    "relation",
    "identity_source",
}
_ALIAS_FIELDS = {
    "schema_version",
    "project_id",
    "checkout_id",
    "groups",
}
_ALIAS_GROUP_FIELDS = {
    "root_request_id",
    "root_run_id",
    "members",
}
_ALIAS_MEMBER_FIELDS = {
    "run_id",
    "event_id",
    "event_sha256",
    "relation",
    "parent_run_id",
}


def _opaque_request_id(seed: str) -> str:
    return f"request-{sha256_text(seed)[:20]}"


def _valid_request_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 28
        and value.startswith("request-")
        and all(character in "0123456789abcdef" for character in value[8:])
    )


def _valid_observation_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


def request_record_id_for_desktop_correlation(correlation_id: str) -> str:
    if (
        not isinstance(correlation_id, str)
        or not correlation_id.strip()
        or "\n" in correlation_id
        or "\r" in correlation_id
    ):
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "Desktop request correlation must be one non-empty line.",
        )
    return _opaque_request_id(correlation_id)


def desktop_root_lineage(
    *,
    run_id: str,
    thread_id: str,
    turn_id: str,
) -> dict[str, Any]:
    correlation_id = f"{thread_id}:{turn_id}"
    return {
        "schema_version": REQUEST_LINEAGE_VERSION,
        "root_request_id": request_record_id_for_desktop_correlation(
            correlation_id
        ),
        "root_run_id": run_id,
        "parent_run_id": None,
        "parent_observation_id": None,
        "relation": "root",
        "identity_source": "desktop_thread_turn",
    }


def generated_root_lineage(
    *,
    project_id: str,
    current_checkout: str,
    run_id: str,
    request_key: str,
) -> dict[str, Any]:
    if (
        not isinstance(request_key, str)
        or not request_key.strip()
        or len(request_key.strip()) > _MAX_REQUEST_KEY_LENGTH
        or "\n" in request_key
        or "\r" in request_key
    ):
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            (
                "request-key must be one non-empty line no longer than "
                f"{_MAX_REQUEST_KEY_LENGTH} characters."
            ),
        )
    seed = canonical_json(
        {
            "project_id": project_id,
            "checkout_id": current_checkout,
            "request_key": request_key.strip(),
        }
    )
    return {
        "schema_version": REQUEST_LINEAGE_VERSION,
        "root_request_id": _opaque_request_id(seed),
        "root_run_id": run_id,
        "parent_run_id": None,
        "parent_observation_id": None,
        "relation": "root",
        "identity_source": "generated_intake",
    }


def inherited_request_lineage(
    parent_lineage: dict[str, Any],
    *,
    parent_run_id: str,
    parent_observation_id: str,
    child_run_id: str,
    relation: str,
) -> dict[str, Any]:
    if not validate_request_lineage(
        parent_lineage,
        current_run_id=parent_run_id,
    ):
        raise MaestroError(
            "REQUEST_LINEAGE_UNAVAILABLE",
            "The parent observation has no valid request lineage.",
        )
    if relation not in {"child", "retry"}:
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "Child relation must be child or retry.",
        )
    if child_run_id == parent_run_id:
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "A child run must differ from its parent run.",
        )
    if not _valid_observation_id(parent_observation_id):
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "parent-observation must be a 32-character observation ID.",
        )
    return {
        "schema_version": REQUEST_LINEAGE_VERSION,
        "root_request_id": parent_lineage["root_request_id"],
        "root_run_id": parent_lineage["root_run_id"],
        "parent_run_id": parent_run_id,
        "parent_observation_id": parent_observation_id,
        "relation": relation,
        "identity_source": "inherited",
    }


def validate_request_lineage(
    value: Any,
    *,
    current_run_id: str | None = None,
) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != _LINEAGE_FIELDS
        or value.get("schema_version") != REQUEST_LINEAGE_VERSION
        or not _valid_request_id(value.get("root_request_id"))
        or not isinstance(value.get("root_run_id"), str)
        or not value["root_run_id"].strip()
        or value.get("relation") not in {"root", "child", "retry"}
        or value.get("identity_source")
        not in {"desktop_thread_turn", "generated_intake", "inherited"}
    ):
        return False
    if current_run_id is not None and (
        not isinstance(current_run_id, str)
        or not current_run_id
    ):
        return False
    relation = value["relation"]
    if relation == "root":
        return (
            value.get("parent_run_id") is None
            and value.get("parent_observation_id") is None
            and value["identity_source"]
            in {"desktop_thread_turn", "generated_intake"}
            and (
                current_run_id is None
                or value["root_run_id"] == current_run_id
            )
        )
    return (
        value["identity_source"] == "inherited"
        and isinstance(value.get("parent_run_id"), str)
        and bool(value["parent_run_id"].strip())
        and _valid_observation_id(value.get("parent_observation_id"))
        and value["parent_run_id"] != current_run_id
        and value["root_run_id"] != current_run_id
    )


@contextmanager
def request_lineage_write_lock(repo: Path) -> Iterator[None]:
    lock_target = safe_target(repo, _LINEAGE_LOCK_TARGET)
    with observation_write_lock(lock_target):
        yield


def _observation_lineages(repo: Path) -> list[dict[str, Any]]:
    directory = safe_target(repo, ".maestro/state/inflight")
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "The in-flight observation path must be a directory.",
        )
    paths = sorted(directory.glob("*.json"))
    if len(paths) > _MAX_LINEAGE_OBSERVATIONS:
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "Too many observations exist to prove request-lineage uniqueness.",
        )
    values: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise MaestroError(
                "REQUEST_LINEAGE_INVALID",
                "Request-lineage observation state is not a regular file.",
            )
        value = read_json(path)
        lineage = value.get("request_lineage")
        if lineage is None:
            continue
        if not validate_request_lineage(
            lineage,
            current_run_id=value.get("run_id"),
        ):
            raise MaestroError(
                "REQUEST_LINEAGE_INVALID",
                "An existing observation has invalid request lineage.",
            )
        values.append(value)
    return values


def assert_request_lineage_available(
    repo: Path,
    *,
    observation_id: str,
    run_id: str,
    lineage: dict[str, Any],
) -> None:
    if not validate_request_lineage(lineage, current_run_id=run_id):
        raise MaestroError(
            "REQUEST_LINEAGE_INVALID",
            "The request lineage does not match the run being started.",
        )
    observations = _observation_lineages(repo)
    matching_parent: dict[str, Any] | None = None
    for observation in observations:
        existing = observation["request_lineage"]
        if (
            existing["root_request_id"] == lineage["root_request_id"]
            and existing["root_run_id"] != lineage["root_run_id"]
        ):
            raise MaestroError(
                "RUN_REQUEST_LINEAGE_CONFLICT",
                "The request ID is already bound to a different root run.",
            )
        if (
            observation.get("run_id") == run_id
            and observation.get("observation_id") != observation_id
        ):
            raise MaestroError(
                "RUN_REQUEST_LINEAGE_CONFLICT",
                "The run ID is already bound to another observation.",
            )
        if (
            observation.get("observation_id")
            == lineage.get("parent_observation_id")
        ):
            matching_parent = observation
    if lineage["relation"] == "root":
        for observation in observations:
            existing = observation["request_lineage"]
            if (
                existing["root_request_id"] == lineage["root_request_id"]
                and existing["relation"] == "root"
                and observation.get("observation_id") != observation_id
            ):
                raise MaestroError(
                    "RUN_REQUEST_LINEAGE_CONFLICT",
                    "The request already has a root observation; start a child run.",
                )
        return
    if matching_parent is None:
        raise MaestroError(
            "REQUEST_LINEAGE_PARENT_NOT_FOUND",
            "The exact parent observation could not be found.",
        )
    parent_lineage = matching_parent["request_lineage"]
    if (
        matching_parent.get("run_id") != lineage["parent_run_id"]
        or parent_lineage["root_request_id"] != lineage["root_request_id"]
        or parent_lineage["root_run_id"] != lineage["root_run_id"]
    ):
        raise MaestroError(
            "RUN_REQUEST_LINEAGE_CONFLICT",
            "The child lineage does not inherit the exact parent request.",
        )


def _trusted_desktop_correlation(value: dict[str, Any]) -> str | None:
    host = value.get("host_observation")
    if (
        not isinstance(host, dict)
        or host.get("schema_version") != "maestro_host_observation_v2"
        or host.get("source") != DESKTOP_REQUEST_SOURCE
        or host.get("quality") != "host_reported"
        or not isinstance(host.get("correlation_id"), str)
        or not host["correlation_id"].strip()
    ):
        return None
    return host["correlation_id"]


def event_sha256(event: dict[str, Any]) -> str:
    return sha256_text(canonical_json(event))


def _legacy_root_request_id(
    *,
    project_id: str,
    current_checkout: str,
    root_event: dict[str, Any],
) -> str:
    return _opaque_request_id(
        canonical_json(
            {
                "project_id": project_id,
                "checkout_id": current_checkout,
                "root_run_id": root_event.get("run_id"),
                "event_id": root_event.get("event_id"),
                "event_sha256": event_sha256(root_event),
            }
        )
    )


def _alias_error(code: str, message: str) -> MaestroError:
    return MaestroError(code, message)


def load_request_alias_bindings(
    repo_path: str | Path,
    events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    repo = ensure_repo(repo_path)
    target = safe_target(repo, REQUEST_ALIAS_PATH)
    if not target.exists():
        return {}
    if not target.is_file() or target.is_symlink():
        raise _alias_error(
            "REQUEST_LINEAGE_ALIAS_INVALID",
            "The request-lineage alias state must be a regular file.",
        )
    value = read_json(target)
    project = read_json(safe_target(repo, ".maestro/project.json"))
    current_checkout = checkout_id(repo)
    if (
        set(value) != _ALIAS_FIELDS
        or value.get("schema_version") != REQUEST_ALIAS_VERSION
        or value.get("project_id") != project.get("project_id")
        or value.get("checkout_id") != current_checkout
        or not isinstance(value.get("groups"), list)
    ):
        raise _alias_error(
            "REQUEST_LINEAGE_ALIAS_INVALID",
            "The request-lineage alias header does not match this checkout.",
        )
    events_by_run = {
        event["run_id"]: event
        for event in events
        if isinstance(event, dict)
        and isinstance(event.get("run_id"), str)
    }
    bindings: dict[str, dict[str, Any]] = {}
    seen_event_ids: set[str] = set()
    seen_root_ids: set[str] = set()
    for group in value["groups"]:
        if (
            not isinstance(group, dict)
            or set(group) != _ALIAS_GROUP_FIELDS
            or not _valid_request_id(group.get("root_request_id"))
            or not isinstance(group.get("root_run_id"), str)
            or not group["root_run_id"].strip()
            or not isinstance(group.get("members"), list)
            or not group["members"]
            or group["root_request_id"] in seen_root_ids
        ):
            raise _alias_error(
                "REQUEST_LINEAGE_ALIAS_INVALID",
                "A request-lineage alias group is malformed or duplicated.",
            )
        root_event = events_by_run.get(group["root_run_id"])
        if root_event is None:
            raise _alias_error(
                "REQUEST_LINEAGE_ALIAS_STALE",
                "The linked root run no longer resolves to a current event.",
            )
        expected_root_request_id = _legacy_root_request_id(
            project_id=value["project_id"],
            current_checkout=value["checkout_id"],
            root_event=root_event,
        )
        if group["root_request_id"] != expected_root_request_id:
            raise _alias_error(
                "REQUEST_LINEAGE_ALIAS_INVALID",
                (
                    "The request-lineage alias root is not the "
                    "content-addressed ID of its bound event."
                ),
            )
        seen_root_ids.add(group["root_request_id"])
        root_members = 0
        member_run_ids = {
            member.get("run_id")
            for member in group["members"]
            if isinstance(member, dict)
        }
        for member in group["members"]:
            if (
                not isinstance(member, dict)
                or set(member) != _ALIAS_MEMBER_FIELDS
                or not isinstance(member.get("run_id"), str)
                or not member["run_id"].strip()
                or not isinstance(member.get("event_id"), str)
                or not member["event_id"].strip()
                or not isinstance(member.get("event_sha256"), str)
                or len(member["event_sha256"]) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in member["event_sha256"]
                )
                or member.get("relation") not in {"root", "child", "retry"}
                or (
                    member["relation"] == "root"
                    and member.get("parent_run_id") is not None
                )
                or (
                    member["relation"] != "root"
                    and (
                        not isinstance(member.get("parent_run_id"), str)
                        or member["parent_run_id"] not in member_run_ids
                        or member["parent_run_id"] == member["run_id"]
                    )
                )
            ):
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_INVALID",
                    "A request-lineage alias member is malformed.",
                )
            event = events_by_run.get(member["run_id"])
            if event is None:
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_STALE",
                    "A linked run no longer resolves to a current event.",
                )
            if (
                event.get("project_id") != value["project_id"]
                or event.get("checkout_id") != value["checkout_id"]
                or event.get("event_id") != member["event_id"]
                or event_sha256(event) != member["event_sha256"]
            ):
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_STALE",
                    "A linked event changed after the alias was reviewed.",
                )
            if (
                member["run_id"] in bindings
                or member["event_id"] in seen_event_ids
            ):
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_CONFLICT",
                    "One run or event is linked to more than one request.",
                )
            native = event.get("request_lineage")
            if native is not None:
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_CONFLICT",
                    "A legacy alias cannot replace native request lineage.",
                )
            correlation = _trusted_desktop_correlation(event)
            if correlation is not None:
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_CONFLICT",
                    "A legacy alias cannot replace trusted Desktop identity.",
                )
            root_members += member["relation"] == "root"
            seen_event_ids.add(member["event_id"])
            bindings[member["run_id"]] = {
                "schema_version": REQUEST_ALIAS_VERSION,
                "root_request_id": group["root_request_id"],
                "root_run_id": group["root_run_id"],
                "parent_run_id": member["parent_run_id"],
                "relation": member["relation"],
                "event_id": member["event_id"],
                "event_sha256": member["event_sha256"],
            }
        root_binding = bindings.get(group["root_run_id"])
        if (
            root_members != 1
            or root_binding is None
            or root_binding["relation"] != "root"
        ):
            raise _alias_error(
                "REQUEST_LINEAGE_ALIAS_INVALID",
                "Each alias group must contain exactly one matching root member.",
            )
        for member_run_id in member_run_ids:
            current_run_id = member_run_id
            visited: set[str] = set()
            while current_run_id != group["root_run_id"]:
                if current_run_id in visited:
                    raise _alias_error(
                        "REQUEST_LINEAGE_ALIAS_INVALID",
                        "A request-lineage alias contains a parent cycle.",
                    )
                visited.add(current_run_id)
                current_binding = bindings.get(current_run_id)
                if (
                    current_binding is None
                    or current_binding["root_request_id"]
                    != group["root_request_id"]
                    or not isinstance(
                        current_binding.get("parent_run_id"),
                        str,
                    )
                ):
                    raise _alias_error(
                        "REQUEST_LINEAGE_ALIAS_INVALID",
                        (
                            "Every alias member must reach the exact "
                            "root through its parent chain."
                        ),
                    )
                current_run_id = current_binding["parent_run_id"]
    return bindings


def write_legacy_request_alias(
    repo_path: str | Path,
    *,
    events: list[dict[str, Any]],
    root_run_id: str,
    member_run_ids: list[str],
    retry_run_ids: list[str] | None = None,
) -> dict[str, Any]:
    repo = ensure_repo(repo_path)
    project = read_json(safe_target(repo, ".maestro/project.json"))
    current_checkout = checkout_id(repo)
    normalized_members = list(
        dict.fromkeys([root_run_id, *member_run_ids])
    )
    retries = set(retry_run_ids or [])
    if (
        not isinstance(root_run_id, str)
        or not root_run_id.strip()
        or not normalized_members
        or any(
            not isinstance(run_id, str) or not run_id.strip()
            for run_id in normalized_members
        )
        or not retries.issubset(set(normalized_members) - {root_run_id})
    ):
        raise _alias_error(
            "REQUEST_LINEAGE_ALIAS_INVALID",
            "Alias members and retry members must be non-empty known run IDs.",
        )
    events_by_run = {
        event["run_id"]: event
        for event in events
        if isinstance(event, dict)
        and isinstance(event.get("run_id"), str)
    }
    missing = [
        run_id
        for run_id in normalized_members
        if run_id not in events_by_run
    ]
    if missing:
        raise _alias_error(
            "REQUEST_LINEAGE_ALIAS_STALE",
            "Alias members do not resolve to current events: "
            + ", ".join(missing),
        )
    mismatched_scope = [
        run_id
        for run_id in normalized_members
        if (
            events_by_run[run_id].get("project_id")
            != project.get("project_id")
            or events_by_run[run_id].get("checkout_id")
            != current_checkout
            or not isinstance(events_by_run[run_id].get("event_id"), str)
            or not events_by_run[run_id]["event_id"]
        )
    ]
    if mismatched_scope:
        raise _alias_error(
            "REQUEST_LINEAGE_ALIAS_INVALID",
            "Alias events do not belong to this project checkout: "
            + ", ".join(mismatched_scope),
        )
    member_events = [events_by_run[run_id] for run_id in normalized_members]
    if len(
        {event["event_id"] for event in member_events}
    ) != len(member_events):
        raise _alias_error(
            "REQUEST_LINEAGE_ALIAS_CONFLICT",
            "One event ID cannot identify more than one linked run.",
        )
    if any(
        event.get("request_lineage") is not None
        or _trusted_desktop_correlation(event) is not None
        for event in member_events
    ):
        raise _alias_error(
            "REQUEST_LINEAGE_ALIAS_CONFLICT",
            "Legacy aliases cannot override native or trusted Desktop identity.",
        )
    root_event = events_by_run[root_run_id]
    root_request_id = _legacy_root_request_id(
        project_id=project["project_id"],
        current_checkout=current_checkout,
        root_event=root_event,
    )
    members = []
    for run_id in sorted(normalized_members, key=lambda item: item != root_run_id):
        event = events_by_run[run_id]
        relation = (
            "root"
            if run_id == root_run_id
            else ("retry" if run_id in retries else "child")
        )
        members.append(
            {
                "run_id": run_id,
                "event_id": event["event_id"],
                "event_sha256": event_sha256(event),
                "relation": relation,
                "parent_run_id": None if relation == "root" else root_run_id,
            }
        )
    group = {
        "root_request_id": root_request_id,
        "root_run_id": root_run_id,
        "members": members,
    }
    target = safe_target(repo, REQUEST_ALIAS_PATH)
    with request_lineage_write_lock(repo):
        if target.exists():
            existing = read_json(target)
            load_request_alias_bindings(repo, events)
        else:
            existing = {
                "schema_version": REQUEST_ALIAS_VERSION,
                "project_id": project.get("project_id"),
                "checkout_id": current_checkout,
                "groups": [],
            }
        for existing_group in existing.get("groups", []):
            existing_runs = {
                member["run_id"]
                for member in existing_group.get("members", [])
                if isinstance(member, dict)
            }
            requested_runs = set(normalized_members)
            if existing_group.get("root_run_id") == root_run_id:
                if existing_group == group:
                    return {
                        "schema_version": "maestro_command_result_v1",
                        "command": "request-link",
                        "status": "already_linked",
                        "root_request_id": root_request_id,
                        "root_run_id": root_run_id,
                        "member_run_ids": normalized_members,
                        "writes_performed": False,
                    }
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_CONFLICT",
                    "The root run already has a different immutable alias group.",
                )
            if existing_group.get("root_request_id") == root_request_id:
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_CONFLICT",
                    "The derived request ID is already owned by another root.",
                )
            if existing_runs & requested_runs:
                raise _alias_error(
                    "REQUEST_LINEAGE_ALIAS_CONFLICT",
                    "One or more runs already belong to another request alias.",
                )
        updated = {
            **existing,
            "groups": [*existing.get("groups", []), group],
        }
        atomic_write(target, pretty_json(updated).encode("utf-8"))
        load_request_alias_bindings(repo, events)
    return {
        "schema_version": "maestro_command_result_v1",
        "command": "request-link",
        "status": "linked",
        "root_request_id": root_request_id,
        "root_run_id": root_run_id,
        "member_run_ids": normalized_members,
        "writes_performed": True,
    }


def resolve_request_identity(
    value: dict[str, Any],
    *,
    alias: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = value.get("run_id")
    lineage = value.get("request_lineage")
    if lineage is not None:
        if not validate_request_lineage(lineage, current_run_id=run_id):
            raise MaestroError(
                "REQUEST_LINEAGE_INVALID",
                "A run carries invalid native request lineage.",
            )
        return {
            "identity": f"request:{lineage['root_request_id']}",
            "request_record_id": lineage["root_request_id"],
            "root_request_id": lineage["root_request_id"],
            "root_run_id": lineage["root_run_id"],
            "parent_run_id": lineage["parent_run_id"],
            "relation": lineage["relation"],
            "evidence": "explicit_request_lineage",
        }
    effective_alias = alias or value.get("request_lineage_alias")
    if effective_alias is not None:
        if (
            not isinstance(effective_alias, dict)
            or effective_alias.get("schema_version") != REQUEST_ALIAS_VERSION
            or not _valid_request_id(
                effective_alias.get("root_request_id")
            )
            or not isinstance(effective_alias.get("root_run_id"), str)
            or effective_alias.get("relation")
            not in {"root", "child", "retry"}
        ):
            raise MaestroError(
                "REQUEST_LINEAGE_ALIAS_INVALID",
                "A run carries an invalid request-lineage alias projection.",
            )
        return {
            "identity": (
                f"request:{effective_alias['root_request_id']}"
            ),
            "request_record_id": effective_alias["root_request_id"],
            "root_request_id": effective_alias["root_request_id"],
            "root_run_id": effective_alias["root_run_id"],
            "parent_run_id": effective_alias.get("parent_run_id"),
            "relation": effective_alias["relation"],
            "evidence": "content_addressed_legacy_alias",
        }
    correlation = _trusted_desktop_correlation(value)
    if correlation is not None:
        request_record_id = request_record_id_for_desktop_correlation(
            correlation
        )
        return {
            "identity": f"request:{request_record_id}",
            "request_record_id": request_record_id,
            "root_request_id": request_record_id,
            "root_run_id": None,
            "parent_run_id": None,
            "relation": None,
            "evidence": "trusted_desktop_thread_turn",
        }
    event_id = value.get("event_id")
    return {
        "identity": f"event:{event_id}",
        "request_record_id": f"event-{event_id}",
        "root_request_id": None,
        "root_run_id": run_id,
        "parent_run_id": None,
        "relation": "root",
        "evidence": "single_run_fallback",
    }
