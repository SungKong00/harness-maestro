from __future__ import annotations

from typing import Any


def _line(value: Any, fallback: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return (text or fallback)[:240]


def allocation_from_assignment(
    *,
    plan_id: str,
    assignment: dict[str, Any],
    projection_digest: str,
) -> dict[str, Any]:
    dependencies = list(assignment.get("depends_on", []))
    dependency_text = (
        " after " + ", ".join(dependencies)
        if dependencies
        else " as an entry assignment"
    )
    return {
        "status": "observed",
        "source": "route_plan",
        "reason": _line(
            (
                f"Route plan assigned {assignment['kind']} to "
                f"{assignment['executor_id']}{dependency_text}."
            ),
            "The validated route plan assigned this work.",
        ),
        "basis_refs": [
            f"route-plan:{plan_id}",
            f"assignment-input:{projection_digest}",
        ],
        "dependency_assignment_ids": dependencies,
    }


def outcome_from_assignment_packet(packet: dict[str, Any]) -> dict[str, Any]:
    version = packet.get("schema_version")
    finding_summary: str | None = None
    verification: dict[str, Any] | None = None
    if version == "maestro_finding_packet_v2":
        findings = packet.get("findings", [])
        first = findings[0] if isinstance(findings, list) and findings else {}
        finding_summary = _line(
            first.get("claim") if isinstance(first, dict) else None,
            f"{len(findings)} bounded finding(s) were reported.",
        )
        verdict = packet.get("verdict")
        conclusion = _line(
            f"Review closed with {verdict}; {len(findings)} finding(s).",
            "Review Packet was validated.",
        )
        decision = _line(
            f"Preserve the validated reviewer verdict: {verdict}.",
            "Preserve the reviewer verdict.",
        )
        next_action = {
            "PASS": "continue",
            "FINDINGS": "revise",
            "BLOCK": "blocked",
            "INSUFFICIENT_EVIDENCE": "blocked",
        }.get(verdict, "blocked")
    elif version == "maestro_verification_verdict_v1":
        verdict = packet.get("verdict")
        conclusion = _line(packet.get("summary"), "Verification Packet was validated.")
        decision = _line(
            f"Verification verdict is {verdict}.",
            "Preserve the verification verdict.",
        )
        next_action = "finish" if verdict == "passed" else "blocked"
        verification = {
            "target": _line(
                packet.get("target_assignment_id"),
                "assignment",
            ),
            "basis": _line(
                packet.get("target_execution_unit_id"),
                "validated execution unit",
            ),
            "assertion": conclusion,
            "command_result": (
                "passed"
                if verdict == "passed"
                else ("failed" if verdict == "failed" else "not_run")
            ),
            "evidence_refs": list(packet.get("evidence_refs", []))[:5],
        }
    else:
        status = packet.get("status")
        conclusion = _line(packet.get("summary"), "Terminal Packet was validated.")
        decision = _line(
            f"Assignment terminal status is {status}.",
            "Preserve the terminal status.",
        )
        next_action = {
            "completed": "verify",
            "failed_transient": "redelegate",
            "failed_semantic": "revise",
            "blocked": "blocked",
            "cancelled": "blocked",
            "skipped": "finish",
        }.get(status, "blocked")
    return {
        "finding_summary": finding_summary,
        "conclusion": conclusion,
        "decision": decision,
        "next_action": next_action,
        "consumed_work_ids": [],
        "handoff": None,
        "artifacts": [],
        "verification": verification,
    }


def application_from_packet(
    load_observation: dict[str, Any],
    packet: dict[str, Any],
    *,
    packet_evidence_ref: str,
) -> tuple[dict[str, Any], str]:
    observation = {
        "packs": [dict(item) for item in load_observation["packs"]],
        "load": dict(load_observation["load"]),
        "application": dict(load_observation["application"]),
    }
    if observation["load"]["status"] != "host_loaded":
        return observation, "unavailable"
    dispositions = packet.get("expertise_dispositions")
    if not isinstance(dispositions, list):
        return observation, "host_loaded"
    if any(
        item.get("disposition") == "conflict"
        for item in dispositions
        if isinstance(item, dict)
    ):
        return observation, "host_loaded"
    applied = [
        item["guide_id"]
        for item in dispositions
        if item["disposition"] in {"consulted", "applied"}
    ]
    not_applicable = [
        item["guide_id"]
        for item in dispositions
        if item["disposition"] == "not_applicable"
    ]
    if applied:
        observation["application"] = {
            "status": "observed",
            "guide_ids": applied,
            "evidence_refs": [packet_evidence_ref],
        }
        return observation, "application_observed"
    if len(not_applicable) == len(dispositions):
        observation["application"] = {
            "status": "not_applicable",
            "guide_ids": not_applicable,
            "evidence_refs": [packet_evidence_ref],
        }
    return observation, "host_loaded"
