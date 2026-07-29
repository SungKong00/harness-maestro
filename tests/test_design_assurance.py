from __future__ import annotations

import copy
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Any

from tests.support import (
    apply_fresh_init,
    record_managed_completion_graph,
    write_json,
)
from tests.test_assignment_contracts import baseline_for

from maestro.assignment_contracts import (
    TERMINAL_PACKET_VERSION,
    VERIFICATION_VERDICT_VERSION,
    assignment_output_schema,
    project_assignment_input,
    validate_assignment_packet,
)
from maestro.design_assurance import (
    SYSTEM_POLICY,
    SURFACE_IDS,
    build_design_decision_packet,
    design_result_digest,
    validate_design_decision_packet,
)
from maestro.errors import MaestroError
from maestro.expertise_routing import normalize_route_hints
from maestro.governance import finalize_run
from maestro.observations import (
    record_stage_observation,
    start_run_observation,
)
from maestro.planning import route_goal_v2, validate_route_v2
from maestro.util import canonical_json, file_sha256, sha256_text


def compact_draft(repo: Path, plan: dict[str, Any]) -> dict[str, Any]:
    decision_id = "primary-action-token"
    system_path = repo / "design-system.json"
    write_json(
        system_path,
        {
            "tokens": {
                "token:action.primary": {
                    "status": "stable",
                }
            },
            "components": {
                "component:primary-button": {
                    "status": "stable",
                }
            },
        },
    )
    system_digest = file_sha256(system_path)
    system_ref = (
        f"project:design-system.json#sha256={system_digest}"
    )
    covered = {
        "action-control-semantics",
        "state-feedback-recovery",
        "token-component-governance",
        "rendered-verification",
    }
    return {
        "scope": {
            "change_kind": "element",
            "target_refs": ["primary-action"],
            "system_mode": "reuse",
        },
        "system_context": {
            "status": "existing",
            "artifacts": [
                {
                    "path": "design-system.json",
                    "sha256": system_digest,
                    "role": "tokens",
                },
                {
                    "path": "design-system.json",
                    "sha256": system_digest,
                    "role": "components",
                }
            ],
            "inventory": [
                {
                    "kind": "token",
                    "ref": "token:action.primary",
                    "artifact_path": "design-system.json",
                    "artifact_sha256": system_digest,
                },
                {
                    "kind": "component",
                    "ref": "component:primary-button",
                    "artifact_path": "design-system.json",
                    "artifact_sha256": system_digest,
                },
            ],
            **SYSTEM_POLICY,
        },
        "compact_eligibility": {
            field: {
                "satisfied": True,
                "evidence_refs": [system_ref],
            }
            for field in (
                "semantic_role_unchanged",
                "interaction_contract_unchanged",
                "approved_tokens_only",
                "no_new_variant",
                "no_unresolved_accessibility_or_locale_risk",
                "affected_contexts_known",
            )
        },
        "surface_checks": [
            {
                "surface_id": surface_id,
                "status": (
                    "covered"
                    if surface_id in covered
                    else "not_applicable"
                ),
                "decision_ids": (
                    [decision_id] if surface_id in covered else []
                ),
                "reason": (
                    "The existing primary action contract owns this surface."
                    if surface_id in covered
                    else "This bounded token reuse does not change this surface."
                ),
                "evidence_refs": [
                    (
                        f"decision:{decision_id}"
                        if surface_id in covered
                        else system_ref
                    )
                ],
            }
            for surface_id in SURFACE_IDS
        ],
        "decisions": [
            {
                "decision_id": decision_id,
                "target_ref": "primary-action",
                "property_group": "action",
                "semantic_role": "primary reversible action",
                "authority_class": "project-system",
                "basis_refs": [system_ref],
                "chosen_rule": (
                    "Reuse the established primary action token and component "
                    "contract without a new visual primitive."
                ),
                "value_lineage": {
                    "kind": "existing-token",
                    "ref": "token:action.primary",
                    "exception_reason": None,
                },
                "affected_states": [
                    "default",
                    "hover",
                    "focus-visible",
                    "disabled",
                ],
                "verification_scenario_ids": ["primary-action-context"],
                "rationale": (
                    "The semantic and interaction contracts are unchanged, "
                    "so system reuse is more coherent than a new value."
                ),
            }
        ],
        "verification_scenarios": [
            {
                "scenario_id": "primary-action-context",
                "target_ref": "primary-action",
                "states": [
                    "default",
                    "hover",
                    "focus-visible",
                    "disabled",
                ],
                "contexts": ["representative-page-content"],
                "viewport": {
                    "name": "regular",
                    "width": 1280,
                    "height": 800,
                },
                "locale": "ko-KR",
                "input_methods": ["pointer", "keyboard"],
                "checks": [
                    "visual-hierarchy",
                    "token-lineage",
                    "interaction",
                    "keyboard-focus",
                ],
                "artifact_path": (
                    ".maestro/state/design-assurance/"
                    f"{plan['plan_id']}/primary-action-context.png"
                ),
            }
        ],
        "unresolved": [],
    }


def png_bytes(
    width: int,
    height: int,
    *,
    filter_byte: int = 0,
    trailing_zlib_bytes: bytes = b"",
) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + kind
            + payload
            + (zlib.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(
                4,
                "big",
            )
        )

    header = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    row = bytes([filter_byte]) + bytes(width * 3)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(
            b"IDAT",
            zlib.compress(row * height) + trailing_zlib_bytes,
        )
        + chunk(b"IEND", b"")
    )


class ProductDesignAssuranceTests(unittest.TestCase):
    def _repo_and_plan(
        self,
        root: Path,
    ) -> tuple[Path, dict[str, Any]]:
        repo = root / "repo"
        repo.mkdir()
        (repo / "README.md").write_text(
            "# Test UI\n\nThe primary button component uses token action.primary.\n",
            encoding="utf-8",
        )
        apply_fresh_init(repo)
        for path in (repo / "docs/project.md", repo / "docs/architecture.md"):
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "status: draft",
                    "status: active",
                    1,
                ),
                encoding="utf-8",
            )
        hints = normalize_route_hints(
            work_kinds=["user-interface"],
            design_assurance_mode="compact",
        )
        plan = route_goal_v2(
            "Reuse the existing primary action token for this control",
            "low",
            intent="implementation",
            route_hints=hints,
            repo_path=repo,
        )
        return repo, plan

    def test_standard_ui_route_opens_research_and_binds_assurance(self) -> None:
        hints = normalize_route_hints(work_kinds=["user-interface"])
        plan = route_goal_v2(
            "Redesign the furniture landing page",
            "medium",
            intent="implementation",
            route_hints=hints,
        )

        self.assertEqual("standard", hints["design_assurance_mode"])
        self.assertEqual(
            "product-design-evidence-v1",
            plan["design_assurance"]["profile_id"],
        )
        self.assertEqual(
            "contextualize",
            plan["expertise"]["research_requirement"]["mode"],
        )
        self.assertEqual(
            "RESEARCH_REQUIRED",
            validate_route_v2(plan)["execution_status"],
        )

    def test_rehashed_ui_plan_cannot_remove_assurance(self) -> None:
        hints = normalize_route_hints(
            work_kinds=["user-interface"],
            design_assurance_mode="compact",
        )
        plan = route_goal_v2(
            "Reuse the existing action token",
            "low",
            intent="implementation",
            route_hints=hints,
        )
        forged = copy.deepcopy(plan)
        forged.pop("design_assurance")
        from maestro.util import canonical_json, sha256_text

        payload = copy.deepcopy(forged)
        payload.pop("plan_id")
        forged["plan_id"] = sha256_text(canonical_json(payload))

        result = validate_route_v2(forged)
        self.assertIn(
            "DESIGN_ASSURANCE_REQUIREMENT_MISMATCH",
            {item["code"] for item in result["issues"]},
        )

    def test_structured_ui_cannot_omit_or_route_around_assurance(
        self,
    ) -> None:
        legacy = normalize_route_hints(work_kinds=["user-interface"])
        legacy.pop("design_assurance_mode")
        with self.assertRaises(MaestroError) as omitted:
            route_goal_v2(
                "Reuse the existing action token",
                "low",
                intent="implementation",
                route_hints=legacy,
            )
        self.assertEqual(
            "EXPERTISE_ROUTE_HINTS_MISMATCH",
            omitted.exception.code,
        )

        mixed = normalize_route_hints(
            work_kinds=["software-structure", "user-interface"],
        )
        with self.assertRaises(MaestroError) as conflict:
            route_goal_v2(
                "Change the UI component and its module boundary",
                "medium",
                intent="implementation",
                route_hints=mixed,
            )
        self.assertEqual(
            "DESIGN_ASSURANCE_ROUTE_CONFLICT",
            conflict.exception.code,
        )

    def test_writer_is_blocked_until_complete_decision_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, plan = self._repo_and_plan(Path(temp))
            missing = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline_for(plan),
            )
            self.assertEqual("BLOCKED", missing["status"])
            self.assertEqual(
                "DESIGN_DECISION_REQUIRED",
                missing["execution_status"],
            )

            draft = compact_draft(repo, plan)
            packet = build_design_decision_packet(repo, plan, draft)
            projection = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline_for(plan),
                design_decision_packet=packet,
            )

            self.assertEqual("PASS", projection["status"])
            self.assertEqual(
                packet,
                projection["input"]["design_assurance_context"][
                    "decision_packet"
                ],
            )
            schema = assignment_output_schema(projection)
            self.assertIn("design_assurance_result", schema["required"])

            incomplete = copy.deepcopy(packet)
            incomplete["surface_checks"] = incomplete["surface_checks"][:-1]
            incomplete["packet_id"] = ""
            from maestro.util import canonical_json, sha256_text

            incomplete["packet_id"] = sha256_text(
                canonical_json(incomplete)
            )
            rejected = validate_design_decision_packet(
                incomplete,
                plan,
                repo_path=repo,
            )
            self.assertEqual("FAIL", rejected["status"])
            self.assertIn(
                "DESIGN_SURFACE_SCAN_INVALID",
                {item["code"] for item in rejected["issues"]},
            )

            forged_plan = copy.deepcopy(plan)
            forged_plan["assignments"] = []
            forged_plan["entry_assignments"] = []
            forged_plan["terminal_assignments"] = []
            forged_plan["mutation_owner_assignment_id"] = None
            forged_plan["plan_id"] = ""
            forged_plan["plan_id"] = sha256_text(
                canonical_json(
                    {
                        key: value
                        for key, value in forged_plan.items()
                        if key != "plan_id"
                    }
                )
            )
            with self.assertRaises(MaestroError) as invalid_plan:
                build_design_decision_packet(
                    repo,
                    forged_plan,
                    draft,
                )
            self.assertEqual(
                "DESIGN_BOUND_PLAN_NOT_READY",
                invalid_plan.exception.code,
            )

    def test_writer_and_verifier_must_close_exact_render_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, plan = self._repo_and_plan(Path(temp))
            decision_packet = build_design_decision_packet(
                repo,
                plan,
                compact_draft(repo, plan),
            )
            writer_projection = project_assignment_input(
                repo,
                plan,
                "implementation",
                baseline_for(plan),
                design_decision_packet=decision_packet,
            )
            render_path = repo / decision_packet[
                "verification_scenarios"
            ][0]["artifact_path"]
            render_path.parent.mkdir(parents=True)
            viewport = decision_packet["verification_scenarios"][0][
                "viewport"
            ]
            render_path.write_bytes(
                png_bytes(viewport["width"], viewport["height"])
            )
            render_digest = file_sha256(render_path)
            design_result = {
                "decision_packet_id": decision_packet["packet_id"],
                "decision_dispositions": [
                    {
                        "decision_id": "primary-action-token",
                        "disposition": "applied",
                        "implementation_refs": ["README.md"],
                        "evidence_refs": [
                            "design-material:primary-action-token"
                        ],
                        "reason": (
                            "The existing token and component contract were "
                            "retained."
                        ),
                    }
                ],
                "rendered_artifacts": [
                    {
                        "scenario_id": "primary-action-context",
                        "artifact_path": decision_packet[
                            "verification_scenarios"
                        ][0]["artifact_path"],
                        "sha256": render_digest,
                    }
                ],
                "unresolved": [],
            }
            writer_packet = {
                "schema_version": TERMINAL_PACKET_VERSION,
                "plan_id": plan["plan_id"],
                "assignment_id": "implementation",
                "packet_type": "ChangeReceipt",
                "status": "completed",
                "summary": "Applied the exact Product Design decision Packet.",
                "evidence_refs": [
                    "readme",
                    f"design-decision:{decision_packet['packet_id']}",
                ],
                "retryable": False,
                "design_assurance_result": design_result,
            }
            accepted_writer = validate_assignment_packet(
                writer_packet,
                plan,
                "implementation",
                writer_projection,
                repo_path=repo,
            )
            self.assertEqual("PASS", accepted_writer["status"])

            render_path.write_bytes(
                png_bytes(
                    viewport["width"],
                    viewport["height"],
                    filter_byte=255,
                )
            )
            invalid_image_writer = copy.deepcopy(writer_packet)
            invalid_image_writer["design_assurance_result"][
                "rendered_artifacts"
            ][0]["sha256"] = file_sha256(render_path)
            rejected_image = validate_assignment_packet(
                invalid_image_writer,
                plan,
                "implementation",
                writer_projection,
                repo_path=repo,
            )
            self.assertIn(
                "DESIGN_RESULT_RENDER_INVALID",
                {item["code"] for item in rejected_image["issues"]},
            )
            render_path.write_bytes(
                png_bytes(
                    viewport["width"],
                    viewport["height"],
                    trailing_zlib_bytes=b"\x00",
                )
            )
            trailing_stream_writer = copy.deepcopy(writer_packet)
            trailing_stream_writer["design_assurance_result"][
                "rendered_artifacts"
            ][0]["sha256"] = file_sha256(render_path)
            rejected_trailing_stream = validate_assignment_packet(
                trailing_stream_writer,
                plan,
                "implementation",
                writer_projection,
                repo_path=repo,
            )
            self.assertIn(
                "DESIGN_RESULT_RENDER_INVALID",
                {
                    item["code"]
                    for item in rejected_trailing_stream["issues"]
                },
            )
            render_path.write_bytes(
                png_bytes(viewport["width"], viewport["height"])
            )

            verifier_projection = project_assignment_input(
                repo,
                plan,
                "verification",
                baseline_for(plan),
                dependency_packets=[writer_packet],
                dependency_projections=[writer_projection],
            )
            self.assertEqual("PASS", verifier_projection["status"])
            verifier_schema = assignment_output_schema(verifier_projection)
            self.assertIn("design_verification", verifier_schema["required"])
            target = verifier_projection["input"]["verification_target"]
            verifier_packet = {
                "schema_version": VERIFICATION_VERDICT_VERSION,
                "plan_id": plan["plan_id"],
                "assignment_id": "verification",
                "packet_type": "VerificationVerdict",
                "target_assignment_id": target["assignment_id"],
                "target_execution_unit_id": target["execution_unit_id"],
                "target_model_route_id": target["model_route_id"],
                "verdict": "passed",
                "failure_cause": "none",
                "failure_categories": [],
                "evidence_refs": [
                    f"design-decision:{decision_packet['packet_id']}",
                    (
                        "design-render:primary-action-context:"
                        f"{render_digest}"
                    ),
                ],
                "summary": "Every declared Product Design render scenario passed.",
                "writes_performed": False,
                "design_verification": {
                    "decision_packet_id": decision_packet["packet_id"],
                    "implementation_result_digest": design_result_digest(
                        design_result
                    ),
                    "scenario_results": [
                        {
                            "scenario_id": "primary-action-context",
                            "verdict": "passed",
                            "artifact_path": decision_packet[
                                "verification_scenarios"
                            ][0]["artifact_path"],
                            "artifact_sha256": render_digest,
                            "checks_applied": decision_packet[
                                "verification_scenarios"
                            ][0]["checks"],
                            "summary": (
                                "The real context retained hierarchy, token "
                                "lineage, keyboard focus, and state behavior."
                            ),
                        }
                    ],
                },
            }
            accepted_verifier = validate_assignment_packet(
                verifier_packet,
                plan,
                "verification",
                verifier_projection,
                repo_path=repo,
            )
            self.assertEqual("PASS", accepted_verifier["status"])

            forged = copy.deepcopy(verifier_packet)
            forged["design_verification"]["scenario_results"] = []
            rejected = validate_assignment_packet(
                forged,
                plan,
                "verification",
                verifier_projection,
                repo_path=repo,
            )
            self.assertIn(
                "DESIGN_VERIFICATION_SET_INVALID",
                {item["code"] for item in rejected["issues"]},
            )

    def test_compact_mode_rejects_self_attested_new_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, plan = self._repo_and_plan(Path(temp))
            owner_path = repo / "docs/decisions/test-owner-value.md"
            owner_path.parent.mkdir(parents=True, exist_ok=True)
            owner_path.write_text(
                "# Owner value\n\nUse a one-off visual value.\n",
                encoding="utf-8",
            )
            owner_ref = (
                "owner:docs/decisions/test-owner-value.md#sha256="
                + file_sha256(owner_path)
            )
            draft = compact_draft(repo, plan)
            decision = draft["decisions"][0]
            decision["authority_class"] = "owner-preference"
            decision["basis_refs"] = [owner_ref]
            decision["value_lineage"] = {
                "kind": "owner-preference",
                "ref": owner_ref,
                "exception_reason": "The owner asked for a one-off value.",
            }

            with self.assertRaises(MaestroError) as rejected:
                build_design_decision_packet(repo, plan, draft)
            self.assertIn(
                rejected.exception.code,
                {
                    "DESIGN_COMPACT_AUTHORITY_INVALID",
                    "DESIGN_COMPACT_VALUE_LINEAGE_INVALID",
                },
            )

            guide_only = compact_draft(repo, plan)
            for eligibility in guide_only[
                "compact_eligibility"
            ].values():
                eligibility["evidence_refs"] = [
                    "guide:design-system-and-components"
                ]
            with self.assertRaises(MaestroError) as unbound_eligibility:
                build_design_decision_packet(repo, plan, guide_only)
            self.assertEqual(
                "DESIGN_COMPACT_ELIGIBILITY_INVALID",
                unbound_eligibility.exception.code,
            )

            unrelated_ref = (
                "project:README.md#sha256="
                + file_sha256(repo / "README.md")
            )
            unrelated_evidence = compact_draft(repo, plan)
            for eligibility in unrelated_evidence[
                "compact_eligibility"
            ].values():
                eligibility["evidence_refs"] = [unrelated_ref]
            with self.assertRaises(MaestroError) as unrelated:
                build_design_decision_packet(
                    repo,
                    plan,
                    unrelated_evidence,
                )
            self.assertEqual(
                "DESIGN_COMPACT_ELIGIBILITY_SYSTEM_EVIDENCE_REQUIRED",
                unrelated.exception.code,
            )

            for fake_ref in (
                "token:does-not-exist",
                "token:stable",
                "token:tokens",
                "token:components",
                "token:status",
            ):
                with self.subTest(fake_ref=fake_ref):
                    invented_symbol = compact_draft(repo, plan)
                    invented_symbol["system_context"]["inventory"][0][
                        "ref"
                    ] = fake_ref
                    invented_symbol["decisions"][0]["value_lineage"][
                        "ref"
                    ] = fake_ref
                    with self.assertRaises(
                        MaestroError
                    ) as unresolved_symbol:
                        build_design_decision_packet(
                            repo,
                            plan,
                            invented_symbol,
                        )
                    self.assertIn(
                        unresolved_symbol.exception.code,
                        {
                            "DESIGN_COMPACT_INVENTORY_REQUIRED",
                            "DESIGN_SYSTEM_SYMBOL_UNRESOLVED",
                        },
                    )

    def test_assured_completion_rejects_current_host_attestation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, plan = self._repo_and_plan(root)
            plan_path = root / "plan.json"
            write_json(plan_path, plan)
            run_id = "assured-fallback-bypass"
            started = start_run_observation(
                repo,
                run_id=run_id,
                task_label="Assured fallback bypass",
                plan_path=plan_path,
                execution_binding={
                    "schema_version": "maestro_execution_binding_v1",
                    "mode": "explicit_fallback",
                    "reason": "capability_unavailable",
                    "evidence": "The fixture exercises the fallback boundary.",
                },
            )
            for assignment in plan["assignments"]:
                record_stage_observation(
                    repo,
                    observation_id=started["observation_id"],
                    run_id=run_id,
                    assignment_id=assignment["assignment_id"],
                    status="completed",
                    evidence_source="current_host",
                    evidence_refs=[
                        f"tests:stage:{assignment['assignment_id']}"
                    ],
                )
            record_managed_completion_graph(
                repo,
                observation_id=started["observation_id"],
                run_id=run_id,
                plan=plan,
                prefix="assured-fallback",
            )
            with self.assertRaises(MaestroError) as rejected:
                finalize_run(
                    repo,
                    run_id=run_id,
                    observation_id=started["observation_id"],
                    outcome="completed",
                    evidence_refs=["tests:forged-design-completion"],
                    verifier_result="passed",
                )
            self.assertEqual(
                "RUN_STAGE_OUTCOME_CONFLICT",
                rejected.exception.code,
            )

    def test_published_schemas_close_design_context_shapes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        design_schema = json.loads(
            (
                root
                / "src/maestro/resources/schemas/design-assurance.schema.json"
            ).read_text(encoding="utf-8")
        )
        definitions = design_schema["$defs"]
        for name in (
            "systemContext",
            "compactEligibility",
            "research",
            "surfaceCheck",
            "decision",
            "verificationScenario",
        ):
            self.assertFalse(definitions[name]["additionalProperties"])
            self.assertTrue(definitions[name]["required"])
        self.assertEqual(
            "maestro_product_design_decision_packet_v2",
            definitions["packet"]["properties"]["schema_version"]["const"],
        )

        assignment_schema = json.loads(
            (
                root
                / "src/maestro/resources/schemas/"
                "assignment-contracts.schema.json"
            ).read_text(encoding="utf-8")
        )
        context = assignment_schema["$defs"]["assignmentInput"][
            "properties"
        ]["design_assurance_context"]
        self.assertEqual(3, len(context["oneOf"]))
        required_by_role = {
            branch["properties"]["role"]["const"]: set(
                branch["required"]
            )
            for branch in context["oneOf"]
        }
        self.assertEqual(
            {"role", "requirement", "decision_packet"},
            required_by_role["implementation"],
        )
        self.assertEqual(
            {
                "role",
                "requirement",
                "decision_packet",
                "implementation_result",
            },
            required_by_role["verification"],
        )

    def test_non_design_projection_shape_remains_unextended(self) -> None:
        plan = route_goal_v2(
            "Implement one backend scheduler behavior",
            "low",
            intent="implementation",
        )
        projection = project_assignment_input(
            Path(__file__).resolve().parents[1],
            plan,
            "implementation",
            baseline_for(plan),
        )
        self.assertEqual("PASS", projection["status"])
        self.assertNotIn(
            "design_assurance",
            plan,
        )
        self.assertNotIn(
            "design_assurance_context",
            projection["input"],
        )

    def test_malformed_design_packet_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, plan = self._repo_and_plan(Path(temp))
            packet = build_design_decision_packet(
                repo,
                plan,
                compact_draft(repo, plan),
            )
            mutations = [
                lambda value: value["scope"].update(
                    {"change_kind": {}}
                ),
                lambda value: value["system_context"].update(
                    {"status": {}}
                ),
                lambda value: value[
                    "compact_eligibility"
                ]["approved_tokens_only"].update(
                    {"evidence_refs": [{}]}
                ),
                lambda value: value["decisions"][0].update(
                    {"property_group": {}}
                ),
                lambda value: value["decisions"][0].update(
                    {"authority_class": {}}
                ),
                lambda value: value["decisions"][0].update(
                    {"basis_refs": [{}]}
                ),
                lambda value: value["decisions"][0][
                    "value_lineage"
                ].update({"kind": {}}),
                lambda value: value["decisions"][0][
                    "value_lineage"
                ].update({"ref": {}}),
                lambda value: value["surface_checks"][0].update(
                    {"status": {}}
                ),
                lambda value: value["surface_checks"][0].update(
                    {"decision_ids": [{}]}
                ),
                lambda value: value["verification_scenarios"][0].update(
                    {"input_methods": [{}]}
                ),
                lambda value: value["verification_scenarios"][0].update(
                    {"checks": [{}]}
                ),
                lambda value: value.update(
                    {"verification_scenarios": None}
                ),
                lambda value: value.update(
                    {"verification_scenarios": 1}
                ),
                lambda value: value.update(
                    {"verification_scenarios": True}
                ),
            ]
            for mutate in mutations:
                with self.subTest(mutation=mutate):
                    malformed = copy.deepcopy(packet)
                    mutate(malformed)
                    malformed["packet_id"] = ""
                    malformed["packet_id"] = sha256_text(
                        canonical_json(malformed)
                    )
                    result = validate_design_decision_packet(
                        malformed,
                        plan,
                        repo_path=repo,
                    )
                    self.assertEqual("FAIL", result["status"])


if __name__ == "__main__":
    unittest.main()
