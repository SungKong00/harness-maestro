from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .errors import MaestroError
from .util import (
    canonical_json,
    ensure_repo,
    read_json,
    safe_target,
    sha256_text,
)


ORIGIN_VERSION = "maestro_expertise_candidate_origin_v1"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
FINGERPRINT_PATTERN = re.compile(r"^[a-f0-9]{24}$")
ORIGIN_FIELDS = {
    "schema_version",
    "origin_id",
    "namespace",
    "candidate_id",
    "candidate_schema_version",
    "subject_ref",
    "mode",
    "signal_fingerprint",
    "goal_digest",
    "adaptation_plan_id",
    "source_admission_id",
    "unit_id",
    "change_set_id",
    "authorization_ref",
    "writes_performed",
}
SCHEMA_VERSION_BY_NAMESPACE = {
    "expertise": "maestro_expertise_candidate_v2",
    "components": "maestro_registry_component_candidate_v2",
}


def _digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["origin_id"] = ""
    return sha256_text(canonical_json(payload))


def build_expertise_candidate_origin(
    *,
    namespace: str,
    candidate_id: str,
    subject_ref: str,
    mode: str,
    signal_fingerprint: str | None = None,
    goal_digest: str | None = None,
    adaptation_plan_id: str | None = None,
    source_admission_id: str | None = None,
    unit_id: str | None = None,
    change_set_id: str | None = None,
    authorization_ref: str | None = None,
) -> dict[str, Any]:
    """Build an external, candidate-ID-bound provenance receipt."""

    if (
        not isinstance(candidate_id, str)
        or ID_PATTERN.fullmatch(candidate_id) is None
        or namespace not in SCHEMA_VERSION_BY_NAMESPACE
        or not isinstance(subject_ref, str)
        or not subject_ref.strip()
        or mode not in {"task-gap", "user-requested", "automatic"}
    ):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_ORIGIN_INVALID",
            "Candidate origin identity or mode is invalid.",
        )
    if mode == "task-gap":
        if (
            not isinstance(signal_fingerprint, str)
            or FINGERPRINT_PATTERN.fullmatch(signal_fingerprint) is None
            or any(
                not isinstance(value, str)
                or DIGEST_PATTERN.fullmatch(value) is None
                for value in (
                    goal_digest,
                    adaptation_plan_id,
                    source_admission_id,
                )
            )
            or not isinstance(unit_id, str)
            or ID_PATTERN.fullmatch(unit_id) is None
            or (
                change_set_id is not None
                and (
                    not isinstance(change_set_id, str)
                    or ID_PATTERN.fullmatch(change_set_id) is None
                )
            )
            or authorization_ref is not None
        ):
            raise MaestroError(
                "EXPERTISE_CANDIDATE_ORIGIN_INVALID",
                "Task-gap origin must bind its fingerprint, goal, plan, and admission.",
            )
    elif mode == "user-requested" and (
        signal_fingerprint is not None
        or goal_digest is not None
        or adaptation_plan_id is not None
        or source_admission_id is not None
        or unit_id is not None
        or change_set_id is not None
        or not isinstance(authorization_ref, str)
        or not authorization_ref.startswith(
            ("owner_decision:", "request_record:")
        )
    ):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_ORIGIN_INVALID",
            "User-requested origin requires one explicit authorization reference.",
        )
    elif mode == "automatic" and (
        namespace != "expertise"
        or not isinstance(signal_fingerprint, str)
        or FINGERPRINT_PATTERN.fullmatch(signal_fingerprint) is None
        or goal_digest is not None
        or adaptation_plan_id is not None
        or source_admission_id is not None
        or unit_id is not None
        or change_set_id is not None
        or authorization_ref is not None
    ):
        raise MaestroError(
            "EXPERTISE_CANDIDATE_ORIGIN_INVALID",
            "Automatic origin requires one signal fingerprint and no task-gap lineage.",
        )
    result = {
        "schema_version": ORIGIN_VERSION,
        "origin_id": "",
        "namespace": namespace,
        "candidate_id": candidate_id,
        "candidate_schema_version": SCHEMA_VERSION_BY_NAMESPACE[namespace],
        "subject_ref": subject_ref,
        "mode": mode,
        "signal_fingerprint": signal_fingerprint,
        "goal_digest": goal_digest,
        "adaptation_plan_id": adaptation_plan_id,
        "source_admission_id": source_admission_id,
        "unit_id": unit_id,
        "change_set_id": change_set_id,
        "authorization_ref": authorization_ref,
        "writes_performed": False,
    }
    result["origin_id"] = _digest(result)
    return result


def _validate_candidate_origin(
    repo_path: str | Path,
    *,
    candidate: dict[str, Any],
    task_gap_binding: dict[str, Any] | None,
    namespace: str,
) -> list[dict[str, str]]:
    """Validate the provenance receipt kept outside the mutable candidate tree."""

    repo = ensure_repo(repo_path)
    candidate_id = candidate.get("candidate_id")
    if (
        not isinstance(candidate_id, str)
        or ID_PATTERN.fullmatch(candidate_id) is None
    ):
        return [
            {
                "code": "EXPERTISE_CANDIDATE_ORIGIN_INVALID",
                "path": "candidate.json.candidate_id",
                "message": "Candidate origin requires one valid candidate ID.",
            }
        ]
    path = safe_target(
        repo,
        (
            f".maestro/state/candidate-origins/{namespace}/"
            f"{candidate_id}.json"
        ),
    )
    if path.is_symlink() or not path.is_file():
        return [
            {
                "code": "EXPERTISE_CANDIDATE_ORIGIN_MISSING",
                "path": path.relative_to(repo).as_posix(),
                "message": (
                    "Candidate v2 requires an external origin receipt so "
                    "task-gap provenance cannot be removed with its files."
                ),
            }
        ]
    try:
        value = read_json(path)
    except MaestroError as exc:
        return [
            {
                "code": exc.code,
                "path": path.relative_to(repo).as_posix(),
                "message": exc.message,
            }
        ]
    return validate_candidate_origin_payload(
        candidate=candidate,
        task_gap_binding=task_gap_binding,
        namespace=namespace,
        value=value,
        path=path.relative_to(repo).as_posix(),
    )


def validate_candidate_origin_payload(
    *,
    candidate: dict[str, Any],
    task_gap_binding: dict[str, Any] | None,
    namespace: str,
    value: Any,
    path: str = "provenance/candidate-origin.json",
) -> list[dict[str, str]]:
    """Validate one portable origin receipt against its candidate."""

    candidate_id = candidate.get("candidate_id")
    generation = candidate.get("generation")
    mode = (
        generation.get("mode")
        if isinstance(generation, dict)
        else None
    )
    structurally_valid = (
        isinstance(value, dict)
        and set(value) == ORIGIN_FIELDS
        and value.get("schema_version") == ORIGIN_VERSION
        and value.get("origin_id") == _digest(value)
        and value.get("namespace") == namespace
        and value.get("candidate_id") == candidate_id
        and value.get("candidate_schema_version")
        == candidate.get("schema_version")
        and value.get("mode") == mode
        and value.get("writes_performed") is False
    )
    if not structurally_valid:
        return [
            {
                "code": "EXPERTISE_CANDIDATE_ORIGIN_MISMATCH",
                "path": path,
                "message": "External origin receipt does not match candidate generation.",
            }
        ]
    if mode == "task-gap":
        expected = task_gap_binding or {}
        expected_subject = (
            f"pack:{candidate.get('expertise_pack_id')}"
            if namespace == "expertise"
            else expected.get("target_ref")
        )
        matches = (
            value.get("subject_ref") == expected_subject
            and value.get("signal_fingerprint")
            == generation.get("signal_fingerprint")
            and value.get("goal_digest") == expected.get("goal_digest")
            and value.get("adaptation_plan_id") == expected.get("plan_id")
            and value.get("source_admission_id")
            == expected.get("source_admission_id")
            and value.get("unit_id") == expected.get("unit_id")
            and value.get("change_set_id") == expected.get("change_set_id")
            and value.get("authorization_ref") is None
        )
    elif mode == "user-requested":
        matches = (
            namespace == "expertise"
            and value.get("subject_ref")
            == f"pack:{candidate.get('expertise_pack_id')}"
            and value.get("signal_fingerprint") is None
            and value.get("goal_digest") is None
            and value.get("adaptation_plan_id") is None
            and value.get("source_admission_id") is None
            and value.get("unit_id") is None
            and value.get("change_set_id") is None
            and isinstance(value.get("authorization_ref"), str)
            and value["authorization_ref"].startswith(
                ("owner_decision:", "request_record:")
            )
        )
    else:
        matches = (
            namespace == "expertise"
            and value.get("subject_ref")
            == f"pack:{candidate.get('expertise_pack_id')}"
            and value.get("signal_fingerprint")
            == generation.get("signal_fingerprint")
            and value.get("goal_digest") is None
            and value.get("adaptation_plan_id") is None
            and value.get("source_admission_id") is None
            and value.get("unit_id") is None
            and value.get("change_set_id") is None
            and value.get("authorization_ref") is None
        )
    if matches:
        return []
    return [
        {
            "code": "EXPERTISE_CANDIDATE_ORIGIN_MISMATCH",
            "path": path,
            "message": "External origin receipt does not bind the exact candidate lineage.",
        }
    ]


def validate_expertise_candidate_origin(
    repo_path: str | Path,
    *,
    candidate: dict[str, Any],
    task_gap_binding: dict[str, Any] | None,
) -> list[dict[str, str]]:
    return _validate_candidate_origin(
        repo_path,
        candidate=candidate,
        task_gap_binding=task_gap_binding,
        namespace="expertise",
    )


def validate_component_candidate_origin(
    repo_path: str | Path,
    *,
    candidate: dict[str, Any],
    task_gap_binding: dict[str, Any] | None,
) -> list[dict[str, str]]:
    return _validate_candidate_origin(
        repo_path,
        candidate=candidate,
        task_gap_binding=task_gap_binding,
        namespace="components",
    )
